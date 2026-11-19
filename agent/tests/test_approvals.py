import asyncio
import sys
from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import RunCancelled
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from thea_agent import toolsets
from thea_agent.approvals import Approvals
from thea_agent.deps import TurnDeps
from thea_agent.models import Capabilities, PromptBudget
from thea_agent.protocol import McpServer

CAPS = Capabilities(True, False, None, None, "medium")
BUDGET = PromptBudget.for_tier("medium")
PAYLOAD_KEYS = {
    "request_id",
    "chat_id",
    "project_id",
    "tool_name",
    "summary",
    "details",
    "diff",
}


class Ui:
    """Records events and answers each approval request with the next decision, from a task."""

    def __init__(self, *decisions: str):
        self.decisions = list(decisions)
        self.events: list[tuple[str, dict]] = []
        self.approvals = Approvals(self.emit)

    def emit(self, name: str, payload: dict) -> None:
        self.events.append((name, payload))
        if name == "agent:approval-request":
            decision = self.decisions.pop(0)

            async def answer() -> None:
                if decision == "cancel":
                    self.approvals.cancel_chat(payload["chat_id"])
                else:
                    assert self.approvals.resolve(payload["request_id"], decision)

            asyncio.get_running_loop().create_task(answer())

    @property
    def requests(self) -> list[dict]:
        return [p for n, p in self.events if n == "agent:approval-request"]


def calls(*parts: ToolCallPart):
    """A model that makes each call in turn, then answers with the last tool return."""

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        step = sum(isinstance(m, ModelResponse) for m in messages)
        if step < len(parts):
            return ModelResponse(parts=[parts[step]])
        return ModelResponse(parts=[TextPart("done")])

    return FunctionModel(model)


async def run(
    ui: Ui, root: Path, turn_req, *parts: ToolCallPart, project_id="p1", req=None
):
    deps = TurnDeps(
        root=root,
        emit=ui.emit,
        chat_id="c1",
        project_id=project_id,
        approvals=ui.approvals,
    )
    req = req or turn_req()
    req.persona.tool_ids = []
    # stdio MCP servers need a real fileno for their stderr
    with open(root / "mcp.log", "a") as log:  # noqa: ASYNC230
        tt = await toolsets.build(req, deps, CAPS, BUDGET, log)
        agent = Agent(
            calls(*parts),
            deps_type=TurnDeps,
            capabilities=tt.capabilities,
            toolsets=tt.toolsets,
        )
        try:
            return await agent.run("go", deps=deps)
        finally:
            await tt.aclose()


def returns(result) -> list[ToolReturnPart]:
    return [
        p
        for m in result.all_messages()
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart)
    ]


def write(path="a.md", content="hello\n"):
    return ToolCallPart("write_file", {"path": path, "content": content})


async def test_approve_runs_the_write(turn_req, tmp_path: Path):
    (tmp_path / "a.md").write_text("old\n")
    ui = Ui("approve")
    await run(ui, tmp_path, turn_req, write())
    assert (tmp_path / "a.md").read_text() == "hello\n"
    [req] = ui.requests
    assert set(req) == PAYLOAD_KEYS
    assert (req["chat_id"], req["project_id"], req["tool_name"]) == (
        "c1",
        "p1",
        "write_file",
    )
    assert req["details"] == "a.md"
    assert "-old" in req["diff"] and "+hello" in req["diff"]


async def test_reject_tells_model_and_does_not_write(turn_req, tmp_path: Path):
    ui = Ui("reject")
    result = await run(ui, tmp_path, turn_req, write())
    assert not (tmp_path / "a.md").exists()
    [ret] = [r for r in returns(result) if r.tool_name == "write_file"]
    assert ret.content == "The user rejected the call."
    assert ret.outcome == "denied"


async def test_edit_file_shows_diff(turn_req, tmp_path: Path):
    (tmp_path / "a.md").write_text("one\ntwo\n")
    ui = Ui("approve")
    edit = ToolCallPart(
        "edit_file", {"path": "a.md", "old_text": "two", "new_text": "2"}
    )
    await run(ui, tmp_path, turn_req, edit)
    assert (tmp_path / "a.md").read_text() == "one\n2\n"
    [req] = ui.requests
    assert "-two" in req["diff"] and "+2" in req["diff"]


async def test_always_allow_project_skips_next_ask(turn_req, tmp_path: Path):
    ui = Ui("always_allow_project", "reject")
    await run(ui, tmp_path, turn_req, write("a.md"), write("b.md"))
    assert (tmp_path / "a.md").exists() and (tmp_path / "b.md").exists()
    assert len(ui.requests) == 1
    assert ("p1", "write") in ui.approvals.allowed
    # Same Approvals, other project: asks again.
    await run(ui, tmp_path, turn_req, write("c.md"), project_id="p2")
    assert len(ui.requests) == 2
    assert not (tmp_path / "c.md").exists()


async def test_docket_write_shows_diff(turn_req, tmp_path: Path):
    ui = Ui("approve")
    await run(
        ui, tmp_path, turn_req, ToolCallPart("add_docket_item", {"title": "Ship it"})
    )
    [req] = ui.requests
    assert req["tool_name"] == "add_docket_item"
    assert req["diff"] and "Ship it" in req["diff"]
    assert "Ship it" in (tmp_path / "docket/docket.json").read_text()


async def test_shell_command_asks_with_the_command(turn_req, tmp_path: Path):
    ui = Ui("reject")
    result = await run(
        ui, tmp_path, turn_req, ToolCallPart("run_command", {"command": "touch x"})
    )
    [req] = ui.requests
    assert req["details"] == "touch x" and req["summary"].startswith(
        "Run shell command"
    )
    assert not (tmp_path / "x").exists()
    [ret] = [r for r in returns(result) if r.tool_name == "run_command"]
    assert ret.content == "The user rejected the call."


async def test_mcp_without_auto_approve_asks(turn_req, tmp_path: Path):
    script = tmp_path / "srv.py"
    script.write_text(
        "from mcp.server.mcpserver import MCPServer\n"
        "app = MCPServer('t')\n"
        "@app.tool()\n"
        "def echo(text: str) -> str:\n"
        "    return 'echo ' + text\n"
        "app.run()\n"
    )

    def server(auto: bool) -> McpServer:
        return McpServer(
            id="m1", name="My Srv", command=sys.executable, args=[str(script)], env={},
            enabled=True, auto_approve=auto,
        )  # fmt: skip

    echo = ToolCallPart("mcp__my_srv__echo", {"text": "hi"})
    for auto in (False, True):
        req = turn_req()
        req.persona.mcp_server_ids, req.mcp_servers = ["m1"], [server(auto)]
        ui = Ui("reject")
        result = await run(ui, tmp_path, turn_req, echo, req=req)
        [ret] = [r for r in returns(result) if r.tool_name == echo.tool_name]
        if auto:
            assert ui.requests == [] and "echo hi" in str(ret.content)
        else:
            [r] = ui.requests
            assert r["summary"] == "Run MCP tool `echo` on `My Srv`"
            assert ret.content == "User rejected MCP tool execution."


async def test_cancel_while_pending(turn_req, tmp_path: Path):
    ui = Ui("cancel")
    with pytest.raises(RunCancelled):
        await run(ui, tmp_path, turn_req, write("a.md"), write("b.md"))
    assert not (tmp_path / "a.md").exists() and not (tmp_path / "b.md").exists()
    assert len(ui.requests) == 1


async def test_resolve_unknown_request_is_false():
    assert not Approvals(lambda n, p: None).resolve("nope", "approve")


async def test_approval_line_resolves_pending_request():
    from thea_agent.__main__ import DefaultHandlers
    from thea_agent.protocol import Approval

    h = DefaultHandlers()
    seen: list[dict] = []
    h.approvals.emit = lambda name, payload: seen.append(payload)
    asked = asyncio.create_task(
        h.approvals.ask("c1", "p1", "write", "write_file", "s", "d")
    )
    await asyncio.sleep(0)
    await h.approval(
        Approval(type="approval", request_id=seen[0]["request_id"], decision="reject")
    )
    assert await asked is False


async def test_write_into_a_new_folder_makes_it(turn_req, tmp_path: Path):
    # As the Rust write_file did: missing parents are made, but only once the write is approved.
    ui = Ui("reject", "approve")
    await run(ui, tmp_path, turn_req, write("docket/a/x.md"), write("docket/b/memo.md"))
    assert not (tmp_path / "docket/a").exists()
    assert (tmp_path / "docket/b/memo.md").read_text() == "hello\n"
