"""The tools and capabilities one turn gets, from the persona, the workspace and the model."""

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from fastmcp.client.transports import StdioTransport
from pydantic_ai.capabilities import HandleDeferredToolCalls, LocalWorkspace
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.workspaces import LocalWorkspaceBackend
from pydantic_ai_harness import DetectLoops, FileSystem, Shell, Skills, ToolOutputLimits
from pydantic_ai_harness.permissions import Permissions
from pydantic_ai_harness.tool_output_limits import Band, Truncate

from thea_agent import approvals
from thea_agent.capabilities import (
    EditFile,
    ThoughtCap,
    ToolErrors,
    WrapUpNearRequestLimit,
    WriteParents,
    ask_user,
)
from thea_agent.deps import TurnDeps
from thea_agent.models import Capabilities, PromptBudget
from thea_agent.protocol import McpServer, Persona, TurnRequest
from thea_agent.tools import docket, ledger, notes, research

DOMAIN_TOOLS = (
    research.web_search, research.fetch_url, research.lookup_paper,
    ledger.add_source, ledger.list_sources, ledger.check_citations, notes.add_note,
    docket.add_docket_item, docket.update_docket_item, docket.list_docket, docket.export_calendar,
)  # fmt: skip

# Rust tool id (persona.tool_ids) -> harness tools it now stands for.
# A plain chat (no project, so no persona): look things up, read and save files.
CHAT_TOOL_IDS = ("web_search", "fetch_url", "read_file", "write_file")

FS_TOOLS = {
    "read_file": ("read_file",),
    "write_file": ("write_file",),  # WriteParents makes missing folders
    "edit_file": ("edit_file",),
    "list_dir": ("list_directory",),
    "search": ("search_files", "find_files"),
}

# Neither readable nor writable. `.thea/credentials` holds the API keys and is inside the
# workspace when a project is opened at the home folder.
SECRET_FILES = ("**/.env*", "**/.thea/credentials")

READ_ONLY = (
    *FileSystem.read_only_patterns,
    "research/sources.json",
    "docket/docket.json",
)


@dataclass
class TurnTools:
    capabilities: list
    toolsets: list
    tool_names: list[str]
    _transports: list[StdioTransport] = field(default_factory=list, repr=False)

    async def aclose(self) -> None:
        """Stop the MCP server processes this turn started (kept alive between probe and run)."""
        results = await asyncio.gather(
            *(t.close() for t in self._transports), return_exceptions=True
        )
        for r in results:
            if isinstance(r, BaseException):
                print(f"MCP server close failed: {r!r}", file=sys.stderr)


def slug(name: str) -> str:
    return "".join(c if c.isascii() and c.isalnum() else "_" for c in name.lower())


def mcp_servers_for(persona: Persona, servers: list[McpServer]) -> list[McpServer]:
    """Enabled servers a persona gets. Empty `mcp_server_ids` means all for a custom persona,
    none for a built-in one, so built-in personas run only the servers they list."""
    return [
        s
        for s in servers
        if s.enabled
        and (
            s.id in persona.mcp_server_ids
            if persona.mcp_server_ids
            else not persona.builtin
        )
    ]


def _transport(server: McpServer, log: TextIO) -> StdioTransport:
    """mcp's default child env is a bare few vars; servers need the app's (proxies, CA files)."""
    env = {**os.environ, **server.env}
    return StdioTransport(server.command, server.args, env, log_file=log)


async def _mcp(
    server: McpServer, log: TextIO
) -> tuple[Any, StdioTransport, list[str]] | None:
    """Start a server and list its tools; None (with a stderr line) when that fails."""
    transport = _transport(server, log)
    prefix = f"mcp__{slug(server.name)}_"  # prefixed() adds "_": mcp__<server>__<tool>, as in Rust

    async def ask_first(ctx, call_tool, name: str, args: dict):
        await approvals.require(
            ctx,
            "mcp",
            f"Run MCP tool `{name}` on `{server.name}`",
            json.dumps(args, indent=2),
        )
        return await call_tool(name, args)

    toolset = MCPToolset(
        transport,
        tool_error_behavior="failed",
        process_tool_call=None if server.auto_approve else ask_first,
    )
    try:
        async with toolset:
            names = [f"{prefix}_{t.name}" for t in await toolset.list_tools()]
    except Exception as e:  # noqa: BLE001 - any failure to start just drops the server
        print(f"MCP server '{server.name}' skipped: {e!r}", file=sys.stderr)
        await transport.close()
        return None
    return toolset.prefixed(prefix), transport, names


async def list_mcp_tools(server: McpServer, log: TextIO) -> list[dict]:
    """Start a server, list its tools as Rust's `McpRemoteTool`, stop it. Errors propagate."""
    transport = _transport(server, log)
    try:
        async with MCPToolset(transport) as toolset:
            tools = await toolset.list_tools()
    finally:
        await transport.close()
    return [
        {
            "server_id": server.id,
            "server_name": server.name,
            "tool_name": t.name,
            "qualified_name": f"mcp__{slug(server.name)}__{t.name}",
            "description": t.description or "MCP tool",
            "input_schema": t.input_schema or {"type": "object", "properties": {}},
        }
        for t in tools
    ]


async def build(
    req: TurnRequest,
    deps: TurnDeps,
    caps: Capabilities,
    budget: PromptBudget,
    mcp_log: TextIO,
) -> TurnTools:
    always: list = [
        DetectLoops(),
        ToolOutputLimits(
            bands=[
                Band(
                    over=budget.tool_output_chars,
                    action=Truncate(max_chars=budget.tool_output_chars),
                )
            ]
        ),
        WrapUpNearRequestLimit(),
        ThoughtCap(),
        EditFile(),
        ToolErrors(),
        # Every FileSystem write and Shell command is held; "always allow" is checked in
        # `approvals.ask` per (project, category), so Permissions' own `remembered` stays unused.
        Permissions("read-only"),
        WriteParents(),  # after Permissions: only an approved write makes folders
        HandleDeferredToolCalls(approvals.handler),
    ]
    if not caps.supports_tools:
        return TurnTools(always, [], [])

    ids = set(req.persona.tool_ids if req.persona else CHAT_TOOL_IDS)
    allowed = (lambda name: name in ids) if ids else (lambda name: True)
    capabilities: list = []
    names: list[str] = []

    if deps.root is not None:
        fs = tuple(
            t for rust, tools in FS_TOOLS.items() if allowed(rust) for t in tools
        )
        capabilities.append(LocalWorkspace(deps.root))
        if fs:
            # read_file pages under the output cap, so its continuation hint survives truncation.
            capabilities.append(
                FileSystem(
                    tools=fs,
                    read_only_patterns=READ_ONLY,
                    denied_patterns=SECRET_FILES,
                    max_read_chars=budget.tool_output_chars,
                    # Every write waits for the user's approval and edit_file matches old_text,
                    # so hashes only add stale-hash conflicts.
                    content_hashes=False,
                )
            )
            names += fs
        if allowed("run_command"):
            capabilities.append(Shell(tools=("run_command",), default_timeout=60))
            names.append("run_command")

    if allowed("load_skill"):
        # One library per directory, each read from its own workspace; on a name clash the
        # earlier directory wins, so Rust sends `skill_dirs` most specific first.
        capabilities += [
            Skills(
                ".",
                include=req.skills,
                missing_directories="skip",
                unknown_names="skip",
                duplicate_names="keep_first",
                workspace=LocalWorkspaceBackend(d),
            )
            for d in req.skill_dirs
            if Path(d).is_dir()
        ]

    domain = [f for f in DOMAIN_TOOLS if allowed(f.__name__)]
    if deps.checklist:  # every project turn can stop to ask, whatever the persona lists
        domain.append(ask_user)
    toolsets: list = [FunctionToolset(domain)] if domain else []
    names += [f.__name__ for f in domain]

    transports: list[StdioTransport] = []
    for server in mcp_servers_for(req.persona, req.mcp_servers) if req.persona else []:
        if started := await _mcp(server, mcp_log):
            toolset, transport, tool_names = started
            toolsets.append(toolset)
            transports.append(transport)
            names += tool_names

    return TurnTools(capabilities + always, toolsets, names, transports)
