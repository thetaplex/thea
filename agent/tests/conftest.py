from pathlib import Path

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from thea_agent.approvals import Approvals
from thea_agent.deps import TurnDeps


def allow_all() -> Approvals:
    """Approvals that never ask: every category is always allowed for the default project."""
    a = Approvals(lambda name, payload: None)
    a.allowed |= {("", c) for c in ("write", "shell", "mcp")}
    return a


@pytest.fixture
def ctx(tmp_path: Path) -> RunContext[TurnDeps]:
    deps = TurnDeps(
        root=tmp_path,
        emit=lambda name, payload: None,
        chat_id="c1",
        approvals=allow_all(),
    )
    return RunContext(deps=deps, model=TestModel(), usage=RunUsage())


@pytest.fixture
def turn_req(tmp_path: Path):
    """A TurnRequest from the shared fixture, rooted in `tmp_path`, with overrides."""
    from thea_agent.protocol import TurnRequest

    base = TurnRequest.model_validate_json(
        (Path(__file__).parent / "fixtures/protocol/turn.json").read_text()
    )

    def make(chat: bool = False, **overrides) -> TurnRequest:
        """`chat=True`: no TASK.md workflow, for tests about events rather than the checklist."""
        ws = base.workspace.model_copy(
            update={"root_path": str(tmp_path), "is_chat": chat}
        )
        fields = {
            "workspace": ws,
            "knowledge_files": [],
            "mcp_servers": [],
            "skill_dirs": [],
        }
        return base.model_copy(update={**fields, **overrides})

    return make


def stream_model(decide, **kw):
    """A streaming FunctionModel from `decide(messages, info) -> ModelResponse` (sync or async)."""
    import inspect

    from pydantic_ai.messages import TextPart, ToolCallPart
    from pydantic_ai.models.function import DeltaToolCall, FunctionModel

    async def stream(messages, info):
        r = decide(messages, info)
        if inspect.isawaitable(r):
            r = await r
        yielded = False
        for i, p in enumerate(r.parts):
            if isinstance(p, TextPart):
                yield p.content
            elif isinstance(p, ToolCallPart):
                yield {
                    i: DeltaToolCall(
                        p.tool_name, p.args_as_json_str(), tool_call_id=p.tool_call_id
                    )
                }
            yielded = True
        if not yielded:
            yield ""

    return FunctionModel(decide, stream_function=stream, **kw)


class Recorder:
    """A recording emit."""

    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def __call__(self, name: str, payload: dict) -> None:
        self.events.append((name, payload))

    def named(self, name: str) -> list[dict]:
        return [p for n, p in self.events if n == name]


@pytest.fixture
def use_model(monkeypatch, tmp_path: Path):
    """Patch the turn's model (and capability probe); THEA_HOME in tmp."""
    from thea_agent import turn
    from thea_agent.models import Capabilities

    monkeypatch.setenv("THEA_HOME", str(tmp_path / "home"))

    def use(model, caps: Capabilities | None = None):
        caps = caps or Capabilities(True, False, None, None, "medium")

        async def probe(provider, client=None):
            return caps

        monkeypatch.setattr(turn, "model_capabilities", probe)
        monkeypatch.setattr(turn, "build_model", lambda provider, **_: model)

    return use
