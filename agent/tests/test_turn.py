import asyncio
import json
from pathlib import Path

import pytest
from conftest import Recorder, stream_model
from pydantic_ai import CancellationToken
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.profiles import ModelProfile

from thea_agent import turn
from thea_agent.__main__ import DefaultHandlers, serve
from thea_agent.approvals import Approvals
from thea_agent.models import Capabilities, PromptBudget
from thea_agent.protocol import StoredRow
from thea_agent.turn import MAX_ROUNDS, resolve_budget, run_turn

CAPS = Capabilities(True, False, None, None, "medium")


def user(text: str) -> StoredRow:
    return StoredRow(
        role="user", content=text, tool_calls_json=None, tool_call_id=None,
        tool_name=None, model_message_json=None,
    )  # fmt: skip


def allowed(rec, project="w1") -> Approvals:
    a = Approvals(rec)
    a.allowed |= {(project, c) for c in ("write", "shell", "mcp")}
    return a


def make_req(turn_req, text="go", tools=("read_file",), max_steps=6, chat=True, **kw):
    """A turn for tests about events; `chat=False` turns on the TASK.md workflow."""
    req = turn_req(history=[user(text)], lessons=[], chat=chat, **kw)
    req.persona.tool_ids = list(tools)
    req.persona.max_steps = max_steps
    return req


async def go(req, rec=None, approvals=None):
    rec = rec or Recorder()
    await run_turn(req, rec, approvals or allowed(rec), CancellationToken())
    return rec


def reply(text):
    return lambda messages, info: ModelResponse(parts=[TextPart(text)])


def last_user_text(messages) -> str:
    return [
        p.content
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, UserPromptPart)
    ][-1]


async def test_one_finished_per_turn(turn_req, use_model):
    use_model(stream_model(reply("hello")))
    rec = await go(make_req(turn_req))
    assert rec.named("chat:finished") == [{"chat_id": "c1", "error": None}]
    assert [d["delta"] for d in rec.named("chat:delta")] == ["hello"]
    [row] = rec.named("message")
    assert (row["role"], row["content"]) == ("assistant", "hello")
    assert rec.events[-1][0] == "chat:finished"

    def boom(messages, info):
        raise RuntimeError("boom")

    use_model(stream_model(boom))
    rec = await go(make_req(turn_req))
    assert rec.named("chat:finished") == [{"chat_id": "c1", "error": "boom"}]


async def test_first_prompt_and_prompt_size(turn_req, use_model):
    use_model(stream_model(reply("hi")))
    rec = await go(make_req(turn_req, max_steps=3))
    names = [n for n, _ in rec.events]
    assert names.index("agent:first-prompt") < names.index("chat:delta")
    [fp] = rec.named("agent:first-prompt")
    assert fp["messages"][0]["role"] == "system"
    assert "Tool steps this turn: 3." in fp["messages"][0]["content"]
    assert [t["name"] for t in fp["tools"]] == ["read_file"]
    [size] = rec.named("agent:prompt-size")
    assert size["chat_id"] == "c1" and size["chars"] > len("go")


async def test_round_rollover_at_step_cap(turn_req, use_model, tmp_path: Path):
    (tmp_path / "TASK.md").write_text("- [ ] a\n")
    round2_first: list = []

    def model(messages, info):
        if last_user_text(messages).startswith("Round 2 of 6"):
            if not round2_first:
                round2_first.append(list(messages))
            (tmp_path / "TASK.md").write_text("- [x] a\n")
            return ModelResponse(parts=[TextPart("done")])
        if info.function_tools:
            return ModelResponse(parts=[ToolCallPart("read_file", {"path": "TASK.md"})])
        return ModelResponse(parts=[TextPart("status: half")])

    use_model(stream_model(model))
    rec = await go(make_req(turn_req, text="write it", max_steps=2, chat=False))
    assert rec.named("agent:round") == [
        {"chat_id": "c1", "round": 2, "max_rounds": MAX_ROUNDS}
    ]
    [first] = round2_first
    assert len(first) == 1 and isinstance(first[0], ModelRequest)
    [brief] = first[0].parts
    assert isinstance(brief, UserPromptPart)
    assert "Original request:\nwrite it\n" in brief.content
    assert "Status at the end of the last round:\nstatus: half\n" in brief.content
    assert "TASK.md now:\n- [ ] a\n" in brief.content
    assert rec.named("agent:incomplete") == []
    assert rec.named("chat:finished") == [{"chat_id": "c1", "error": None}]
    assert len(rec.named("agent:first-prompt")) == 1
    assert len(rec.named("agent:prompt-size")) == 3  # one per request
    # The brief has no UI row of its own; it rides in the JSON of round 2's first row.
    rows = rec.named("message")
    assert [r["role"] for r in rows][-1] == "assistant"
    assert "Round 2 of 6" in rows[-1]["model_message_json"]


async def test_incomplete_when_items_left(turn_req, use_model, tmp_path: Path):
    (tmp_path / "TASK.md").write_text("- [ ] a\n- [x] b\n")
    use_model(stream_model(reply("I stop here.")))
    rec = await go(make_req(turn_req, chat=False))
    assert rec.named("agent:incomplete") == [
        {
            "chat_id": "c1",
            "reason": "The model stopped with TASK.md items still open.",
            "open_items": ["- [ ] a"],
        }
    ]

    # One step per round: every round ends at the cap until the rounds run out.
    rec = await go(make_req(turn_req, max_steps=1, chat=False))
    assert [r["round"] for r in rec.named("agent:round")] == list(
        range(2, MAX_ROUNDS + 1)
    )
    [inc] = rec.named("agent:incomplete")
    assert (
        inc["reason"]
        == f"Stopped at the step limit (1 steps per round, {MAX_ROUNDS} rounds)."
    )
    assert rec.named("chat:finished") == [{"chat_id": "c1", "error": None}]


async def test_tool_event_sequence(turn_req, use_model, tmp_path: Path):
    (tmp_path / "a.md").write_text("hello\n")

    def model(messages, info):
        if len(messages) == 1:
            return ModelResponse(
                parts=[ToolCallPart("read_file", {"path": "a.md"}, tool_call_id="t1")]
            )
        return ModelResponse(parts=[TextPart("read it")])

    use_model(stream_model(model))
    rec = await go(make_req(turn_req))
    running, done = rec.named("agent:tool-event")
    assert running == {
        "chat_id": "c1", "tool_call_id": "t1", "tool_name": "read_file",
        "arguments": {"path": "a.md"}, "status": "running", "output": None,
        "artifact_path": None,
    }  # fmt: skip
    assert (done["tool_call_id"], done["status"], done["artifact_path"]) == (
        "t1",
        "done",
        "a.md",
    )
    assert "hello" in done["output"]
    rows = rec.named("message")
    assert [r["role"] for r in rows] == ["assistant", "tool", "assistant"]
    assert json.loads(rows[0]["tool_calls_json"]) == [
        {"id": "t1", "name": "read_file", "arguments": {"path": "a.md"}}
    ]
    assert (rows[1]["tool_call_id"], rows[1]["tool_name"]) == ("t1", "read_file")
    assert all(r["model_message_json"] for r in rows)


async def test_rejected_approval_tool_event_and_run_continues(
    turn_req, use_model, tmp_path: Path
):
    def model(messages, info):
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "write_file",
                        {"path": "a.md", "content": "x"},
                        tool_call_id="w1",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart("ok, not written")])

    use_model(stream_model(model))
    rec = Recorder()
    approvals = Approvals(rec)

    def emit(name, payload):
        rec(name, payload)
        if name == "agent:approval-request":
            asyncio.get_running_loop().call_soon(
                approvals.resolve, payload["request_id"], "reject"
            )

    approvals.emit = emit
    await run_turn(
        make_req(turn_req, tools=("write_file",)), emit, approvals, CancellationToken()
    )
    statuses = [(e["tool_call_id"], e["status"]) for e in rec.named("agent:tool-event")]
    assert statuses == [("w1", "running"), ("w1", "rejected")]
    assert rec.named("agent:tool-event")[1]["artifact_path"] is None
    assert not (tmp_path / "a.md").exists()
    assert rec.named("message")[-1]["content"] == "ok, not written"
    assert rec.named("chat:finished") == [{"chat_id": "c1", "error": None}]


async def test_export_calendar_artifact_path(turn_req, use_model, tmp_path: Path):
    def model(messages, info):
        if len(messages) == 1:
            args = {"title": "Ship", "start": "2026-11-20"}
            return ModelResponse(
                parts=[ToolCallPart("export_calendar", args, tool_call_id="e1")]
            )
        return ModelResponse(parts=[TextPart("exported")])

    use_model(stream_model(model))
    rec = await go(make_req(turn_req, tools=("export_calendar",)))
    done = rec.named("agent:tool-event")[-1]
    assert done["status"] == "done"
    assert done["artifact_path"] and (tmp_path / done["artifact_path"]).is_file()


async def test_thinking_follows_persona_when_model_can_think(turn_req, use_model):
    seen = []

    def model(messages, info):
        seen.append(info.model_request_parameters.thinking)
        return ModelResponse(parts=[TextPart("hi")])

    thinker = stream_model(model, profile=ModelProfile(supports_thinking=True))
    use_model(thinker, Capabilities(True, True, None, None, "medium"))
    await go(make_req(turn_req))
    req = make_req(turn_req)
    req.persona.native_thinking = True
    await go(req)
    use_model(thinker)  # Thea's probe says it cannot think: no setting at all
    await go(make_req(turn_req))
    assert seen == [False, True, None]


def test_resolve_budget(turn_req):
    req = turn_req(small_model=None)
    req.persona.max_steps = 0
    assert resolve_budget(req, CAPS) == PromptBudget.for_tier("medium")
    req = turn_req(small_model=True)
    req.persona.max_steps = 0
    assert resolve_budget(req, CAPS) == PromptBudget.for_tier("small")
    req = turn_req(small_model=False)
    req.persona.max_steps = 7
    b = resolve_budget(req, CAPS)
    assert (b.max_steps, b.search_results) == (
        7,
        PromptBudget.for_tier("large").search_results,
    )


async def _until(done) -> None:
    while not done():
        await asyncio.sleep(0.01)


async def _serve(handlers, lines: list[str], between=None, done=None):
    """Feed `lines`; EOF (the app quitting cancels turns) only once `done()` holds."""
    reader = asyncio.StreamReader()
    task = asyncio.create_task(serve(reader, handlers))
    for i, line in enumerate(lines):
        reader.feed_data((line + "\n").encode())
        if between and i < len(lines) - 1:
            await between()
    if done:
        await asyncio.wait_for(_until(done), 10)
    reader.feed_eof()
    await asyncio.wait_for(task, 10)


def blocking_model(started: asyncio.Event):
    async def model(messages, info):
        if last_user_text(messages) == "first":
            started.set()
            await asyncio.Event().wait()  # until cancelled
        return ModelResponse(parts=[TextPart("second done")])

    return stream_model(model)


async def test_new_turn_cancels_running_turn(turn_req, use_model):
    started = asyncio.Event()
    use_model(blocking_model(started))
    rec = Recorder()
    first, second = (
        make_req(turn_req, text=t).model_dump_json() for t in ("first", "second")
    )
    await _serve(
        DefaultHandlers(rec),
        [first, second],
        between=started.wait,
        done=lambda: len(rec.named("chat:finished")) == 2,
    )
    assert rec.named("chat:finished") == [
        {"chat_id": "c1", "error": None},  # replaced, not failed (R11)
        {"chat_id": "c1", "error": None},
    ]
    assert rec.named("message")[-1]["content"] == "second done"


async def test_cancel_line_stops_the_turn(turn_req, use_model):
    started = asyncio.Event()
    use_model(blocking_model(started))
    rec = Recorder()
    first = make_req(turn_req, text="first").model_dump_json()
    cancel = json.dumps({"type": "cancel", "chat_id": "c1"})
    handlers = DefaultHandlers(rec)
    await _serve(handlers, [first, cancel], between=started.wait)
    assert rec.named("chat:finished") == [{"chat_id": "c1", "error": None}]
    assert handlers.running == {}


async def test_cancel_while_approval_pending(turn_req, use_model, tmp_path: Path):
    """cancel_chat ends the approval wait of a task nobody cancelled: one chat:finished, and
    the dispatcher keeps serving the next line."""

    def model(messages, info):
        if last_user_text(messages) == "second":
            return ModelResponse(parts=[TextPart("second done")])
        if len(messages) == 1:
            args = {"path": "a.md", "content": "x"}
            return ModelResponse(parts=[ToolCallPart("write_file", args)])
        return ModelResponse(parts=[TextPart("unreachable")])

    use_model(stream_model(model))
    rec = Recorder()
    asked = asyncio.Event()

    def emit(name, payload):
        rec(name, payload)
        if name == "agent:approval-request":
            asked.set()

    lines = [
        make_req(turn_req, text="first", tools=("write_file",)).model_dump_json(),
        json.dumps({"type": "cancel", "chat_id": "c1"}),
        make_req(turn_req, text="second").model_dump_json(),
    ]
    reader = asyncio.StreamReader()
    task = asyncio.create_task(serve(reader, DefaultHandlers(emit)))
    reader.feed_data((lines[0] + "\n").encode())
    await asyncio.wait_for(asked.wait(), 5)
    reader.feed_data((lines[1] + "\n").encode())
    while not rec.named("chat:finished"):
        await asyncio.sleep(0.01)
    reader.feed_data((lines[2] + "\n").encode())
    await asyncio.wait_for(_until(lambda: len(rec.named("chat:finished")) == 2), 10)
    reader.feed_eof()
    await asyncio.wait_for(task, 10)
    assert not (tmp_path / "a.md").exists()
    assert rec.named("chat:finished") == [
        {"chat_id": "c1", "error": None},
        {"chat_id": "c1", "error": None},
    ]
    assert rec.named("message")[-1]["content"] == "second done"


async def test_call_methods(monkeypatch, tmp_path: Path):
    import sys

    from thea_agent import models
    from thea_agent.protocol import Call

    monkeypatch.setenv("THEA_HOME", str(tmp_path / "home"))
    script = tmp_path / "srv.py"
    script.write_text(
        "from mcp.server.mcpserver import MCPServer\n"
        "app = MCPServer('t')\n"
        "@app.tool()\n"
        "def echo(text: str) -> str:\n"
        "    return text\n"
        "app.run()\n"
    )
    server = {
        "id": "m1", "name": "S", "command": sys.executable, "args": [str(script)],
        "env": {}, "enabled": True, "auto_approve": False,
    }  # fmt: skip
    rec = Recorder()
    h = DefaultHandlers(rec)

    def call(method, **params):
        return h.call(Call(type="call", id="1", method=method, params=params))

    [tool] = await call("test_mcp_server", server=server)
    assert {k: tool[k] for k in tool if k != "input_schema"} == {
        "server_id": "m1",
        "server_name": "S",
        "tool_name": "echo",
        "qualified_name": "mcp__s__echo",
        "description": tool["description"],
    }
    assert tool["input_schema"]["properties"]["text"]["type"] == "string"
    assert (tmp_path / "home/logs/mcp.log").is_file()

    lesson = "When the user says too long, write less."
    monkeypatch.setattr(models, "build_model", lambda p: stream_model(reply(lesson)))
    text = await call(
        "reflect_rating", provider={}, persona_id="p1", history=[user("hi").model_dump()],
        lessons=[], up=False, comment="too long",
    )  # fmt: skip
    assert text == lesson
    assert rec.named("lesson") == [
        {"persona_id": "p1", "signal": "rating_down", "text": lesson}
    ]
    with pytest.raises(ValueError):
        await call("nope")


async def test_stray_cancelled_error_is_a_stop(turn_req, monkeypatch):
    """A CancelledError the task itself was not cancelled with ends the turn quietly."""

    async def stray(*args):
        raise asyncio.CancelledError

    monkeypatch.setattr(turn, "_turn", stray)
    rec = await go(make_req(turn_req))
    assert rec.named("chat:finished") == [{"chat_id": "c1", "error": None}]

    async def hang(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(turn, "_turn", hang)
    rec = Recorder()
    t = asyncio.create_task(go(make_req(turn_req), rec))
    await asyncio.sleep(0.01)
    t.cancel()  # the task's own cancellation still propagates
    with pytest.raises(asyncio.CancelledError):
        await t
    assert rec.named("chat:finished") == [{"chat_id": "c1", "error": None}]


async def test_rows_land_before_their_tool_events(turn_req, use_model, tmp_path: Path):
    """The assistant row is stored before its tools run, the tool row before the next model
    call, so the UI's reload on each tool-event keeps the text and shows the output."""
    (tmp_path / "a.md").write_text("hello\n")

    def model(messages, info):
        if len(messages) == 1:
            call = ToolCallPart("read_file", {"path": "a.md"}, tool_call_id="t1")
            return ModelResponse(parts=[TextPart("let me look"), call])
        return ModelResponse(parts=[TextPart("read it")])

    use_model(stream_model(model))
    rec = await go(make_req(turn_req))
    order = [
        f"{n}:{p.get('role') or p.get('status') or ''}"
        for n, p in rec.events
        if n in ("message", "agent:tool-event", "chat:delta")
    ]
    assert order == [
        "chat:delta:",
        "message:assistant",
        "agent:tool-event:running",
        "agent:tool-event:done",
        "message:tool",
        "chat:delta:",
        "message:assistant",
    ]
    rows = rec.named("message")
    assert json.loads(rows[0]["tool_calls_json"])[0]["id"] == "t1"
    # The rows still replay into the exact run history.
    from thea_agent.history import to_model_messages

    stored = [StoredRow.model_validate(r) for r in rows]
    kinds = [type(m).__name__ for m in to_model_messages(stored)]
    assert kinds == ["ModelResponse", "ModelRequest", "ModelResponse"]


async def test_rejected_turn_line_finishes_without_leaking(capsys):
    rec = Recorder()
    bad = json.dumps(
        {"type": "turn", "chat_id": "c9", "provider": {"api_key": "sk-TOPSECRET"}}
    )
    await _serve(DefaultHandlers(rec), [bad, "not json", '{"type": "turn"}'])
    assert rec.named("chat:finished") == [
        {"chat_id": "c9", "error": "The agent rejected the request."}
    ]
    err = capsys.readouterr().err
    assert "bad line ignored" in err and "TOPSECRET" not in err
