import io
import json
from pathlib import Path

import pytest
from conftest import allow_all
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai_harness import DetectLoops, FileSystem, Shell, Skills, ToolOutputLimits

from thea_agent import toolsets
from thea_agent.capabilities import ThoughtCap, ToolErrors, WrapUpNearRequestLimit
from thea_agent.deps import TurnDeps
from thea_agent.models import Capabilities, PromptBudget
from thea_agent.protocol import McpServer

CAPS = Capabilities(True, False, None, None, "medium")
BUDGET = PromptBudget.for_tier("medium")


@pytest.fixture
def mcp_log(tmp_path: Path):
    """A real file: the stdio transport needs a fileno for server stderr."""
    with open(tmp_path / "mcp.log", "w") as f:
        yield f


def _deps(root: Path) -> TurnDeps:
    return TurnDeps(
        root=root, emit=lambda n, p: None, chat_id="c1", approvals=allow_all()
    )


async def _build(req, root: Path, caps=CAPS, log=None):
    return await toolsets.build(req, _deps(root), caps, BUDGET, log or io.StringIO())


def _all_tools(turn_req):
    req = turn_req()
    req.persona.tool_ids = []
    return req


async def test_sources_json_is_read_only(turn_req, tmp_path: Path):
    for rel in ("research/sources.json", "docket/docket.json"):
        (tmp_path / rel).parent.mkdir(exist_ok=True)
        (tmp_path / rel).write_text("[]")
    tt = await _build(_all_tools(turn_req), tmp_path)
    targets = ["research/sources.json", "docket/docket.json"]

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        step = sum(isinstance(m, ModelResponse) for m in messages)
        if step < 2:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "write_file", {"path": targets[step], "content": "HACKED"}
                    )
                ]
            )
        if step < 4:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "edit_file",
                        {
                            "path": targets[step - 2],
                            "old_text": "[]",
                            "new_text": "HACKED",
                        },
                    )
                ]
            )
        return ModelResponse(parts=[TextPart("gave up")])

    agent = Agent(
        FunctionModel(model),
        deps_type=TurnDeps,
        capabilities=tt.capabilities,
        toolsets=tt.toolsets,
        retries={"tools": 5},
    )
    result = await agent.run("go", deps=_deps(tmp_path))
    assert result.output == "gave up"
    for rel in targets:
        assert (tmp_path / rel).read_text() == "[]"


async def test_env_files_are_hidden(turn_req, tmp_path: Path):
    names = [".env", ".env.local", ".envrc", ".env-local"]
    for n in names:
        (tmp_path / n).write_text("SECRET=1")
    (tmp_path / "notes.md").write_text("ok")
    tt = await _build(_all_tools(turn_req), tmp_path)
    calls = [ToolCallPart("read_file", {"path": n}) for n in names] + [
        ToolCallPart("list_directory", {"path": "."}),
        ToolCallPart("find_files", {"pattern": ".env*"}),
        ToolCallPart("search_files", {"pattern": "SECRET"}),
    ]
    seen: list[str] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        step = sum(isinstance(m, ModelResponse) for m in messages)
        if step < len(calls):
            return ModelResponse(parts=[calls[step]])
        seen.append(" ".join(str(m) for m in messages))
        return ModelResponse(parts=[TextPart("done")])

    agent = Agent(
        FunctionModel(model),
        deps_type=TurnDeps,
        capabilities=tt.capabilities,
        toolsets=tt.toolsets,
        retries={"tools": 5},
    )
    await agent.run("go", deps=_deps(tmp_path))
    assert "SECRET=1" not in seen[0]
    out = seen[0]
    assert "SECRET=1" not in out
    assert out.count("is denied by pattern") == len(names)
    assert "4 hidden entries omitted" in out  # list_directory
    assert "No matches found." in out  # find_files


async def test_failing_mcp_server_is_skipped(turn_req, tmp_path: Path, capsys, mcp_log):
    server = McpServer(
        id="m1",
        name="Broken One",
        command="false",
        args=[],
        env={},
        enabled=True,
        auto_approve=False,
    )
    req = _all_tools(turn_req)
    req.persona.mcp_server_ids = ["m1"]
    req.mcp_servers = [server]
    tt = await _build(req, tmp_path, log=mcp_log)
    assert not [n for n in tt.tool_names if n.startswith("mcp__")]
    assert all("mcp" not in type(t).__name__.lower() for t in tt.toolsets)
    assert "Broken One" in capsys.readouterr().err
    await tt.aclose()


def test_mcp_servers_for_follows_persona(turn_req):
    def srv(id: str, enabled: bool = True) -> McpServer:
        return McpServer(
            id=id,
            name=id,
            command="x",
            args=[],
            env={},
            enabled=enabled,
            auto_approve=False,
        )

    servers = [srv("a"), srv("b"), srv("c", enabled=False)]
    p = turn_req().persona
    p.mcp_server_ids, p.builtin = [], False
    assert [s.id for s in toolsets.mcp_servers_for(p, servers)] == ["a", "b"]
    p.builtin = True
    assert toolsets.mcp_servers_for(p, servers) == []
    p.mcp_server_ids = ["b", "c"]
    assert [s.id for s in toolsets.mcp_servers_for(p, servers)] == ["b"]


async def test_no_tools_when_model_cannot_call_tools(turn_req, tmp_path: Path):
    tt = await _build(
        _all_tools(turn_req),
        tmp_path,
        caps=Capabilities(False, False, None, None, "small"),
    )
    assert tt.toolsets == [] and tt.tool_names == []
    assert not [
        c for c in tt.capabilities if isinstance(c, (FileSystem, Shell, Skills))
    ]


async def test_wired_framework_capabilities(turn_req, tmp_path: Path):
    tt = await _build(_all_tools(turn_req), tmp_path)
    kinds = {type(c) for c in tt.capabilities}
    for k in (
        DetectLoops,
        ToolOutputLimits,
        WrapUpNearRequestLimit,
        ThoughtCap,
        ToolErrors,
        FileSystem,
        Shell,
    ):
        assert k in kinds, k
    [limits] = [c for c in tt.capabilities if isinstance(c, ToolOutputLimits)]
    assert limits.bands[0].over == BUDGET.tool_output_chars
    assert limits.bands[0].action.max_chars == BUDGET.tool_output_chars
    assert {
        "read_file",
        "write_file",
        "list_directory",
        "run_command",
        "add_source",
    } <= set(tt.tool_names)


async def test_persona_tool_ids_filter_tools(turn_req, tmp_path: Path):
    req = turn_req()
    req.persona.tool_ids = ["read_file", "list_dir", "web_search"]
    tt = await _build(req, tmp_path)
    assert sorted(tt.tool_names) == ["list_directory", "read_file", "web_search"]
    assert Shell not in {type(c) for c in tt.capabilities}
    assert Skills not in {type(c) for c in tt.capabilities}  # no load_skill


async def test_skills_narrowed_to_enabled_names(turn_req, tmp_path: Path):
    lib = tmp_path / "skills"
    for name in ("report", "other"):
        (lib / name).mkdir(parents=True)
        (lib / name / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {name} skill\n---\nBody of {name}.\n"
        )
    shadowed = tmp_path / "global" / "report"
    shadowed.mkdir(parents=True)
    (shadowed / "SKILL.md").write_text(
        "---\nname: report\ndescription: shadowed copy\n---\nOld.\n"
    )
    req = _all_tools(turn_req)
    req.skill_dirs = [str(lib), str(tmp_path / "global"), str(tmp_path / "missing")]
    req.skills = ["report", "not-installed"]
    tt = await _build(req, tmp_path)
    offered: list[str] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        offered.append(
            json.dumps([t.name for t in info.function_tools])
            + (info.instructions or "")
        )
        return ModelResponse(parts=[TextPart("ok")])

    agent = Agent(
        FunctionModel(model),
        deps_type=TurnDeps,
        capabilities=tt.capabilities,
        toolsets=tt.toolsets,
    )
    await agent.run("go", deps=_deps(tmp_path))
    assert "load_capability" in offered[0]
    assert "report: report skill" in offered[0]
    assert "other skill" not in offered[0] and "shadowed" not in offered[0]


async def test_mcp_tools_are_prefixed_and_callable(
    turn_req, tmp_path: Path, mcp_log, monkeypatch
):
    """Servers inherit the app's environment (proxies, CA files), their own env on top."""
    import sys

    monkeypatch.setenv("THEA_PROBE", "app")

    script = tmp_path / "srv.py"
    script.write_text(
        "from mcp.server.mcpserver import MCPServer\n"
        "app = MCPServer('t')\n"
        "@app.tool()\n"
        "def echo(text: str) -> str:\n"
        "    import os\n"
        "    return 'echo ' + text + os.environ['THEA_PROBE'] + os.environ['OWN']\n"
        "app.run()\n"
    )
    server = McpServer(
        id="m1", name="My Srv", command=sys.executable, args=[str(script)],
        env={"OWN": "-own"},
        enabled=True, auto_approve=False,
    )  # fmt: skip
    req = _all_tools(turn_req)
    req.persona.mcp_server_ids, req.mcp_servers = ["m1"], [server]
    tt = await _build(req, tmp_path, log=mcp_log)
    assert "mcp__my_srv__echo" in tt.tool_names

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(
                parts=[ToolCallPart("mcp__my_srv__echo", {"text": "hi"})]
            )
        return ModelResponse(parts=[TextPart(str(messages[-1].parts[0].content))])

    agent = Agent(
        FunctionModel(model),
        deps_type=TurnDeps,
        capabilities=tt.capabilities,
        toolsets=tt.toolsets,
    )
    try:
        result = await agent.run("go", deps=_deps(tmp_path))
    finally:
        await tt.aclose()
    assert "echo hiapp-own" in result.output


async def test_shell_timeout_matches_rust(turn_req, tmp_path: Path):
    """shell.rs waited 60 s per command."""
    tt = await _build(_all_tools(turn_req), tmp_path)
    [shell] = [c for c in tt.capabilities if isinstance(c, Shell)]
    assert shell.default_timeout == 60


async def test_aclose_closes_every_transport(capsys):
    closed = []

    class T:
        def __init__(self, fail):
            self.fail = fail

        async def close(self):
            closed.append(self)
            if self.fail:
                raise RuntimeError("stuck")

    ts = [T(True), T(False)]
    await toolsets.TurnTools([], [], [], ts).aclose()
    assert closed == ts
    assert "stuck" in capsys.readouterr().err


async def test_plain_chat_tools(turn_req, tmp_path: Path):
    req = turn_req(persona=None, chat=True, skill_dirs=[str(tmp_path)])
    tt = await _build(req, tmp_path)
    assert sorted(tt.tool_names) == [
        "fetch_url", "read_file", "web_search", "write_file",
    ]  # fmt: skip
    assert not any(isinstance(c, Skills) for c in tt.capabilities)


async def test_a_project_turn_can_always_ask_the_user(turn_req, tmp_path: Path):
    req = turn_req()
    req.persona.tool_ids = ["read_file"]
    deps = _deps(tmp_path)
    deps.checklist = True
    tt = await toolsets.build(req, deps, CAPS, BUDGET, io.StringIO())
    assert sorted(tt.tool_names) == ["ask_user", "read_file"]
