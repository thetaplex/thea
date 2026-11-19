from pathlib import Path

from conftest import Recorder, stream_model
from pydantic_ai import CancellationToken, capture_run_messages
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    repair_messages,
)

from thea_agent import turn
from thea_agent.approvals import Approvals
from thea_agent.history import to_model_messages
from thea_agent.models import Capabilities
from thea_agent.protocol import StoredRow


def row(role, content, **kw) -> StoredRow:
    fields = {
        "tool_calls_json": None,
        "tool_call_id": None,
        "tool_name": None,
        "model_message_json": None,
    }
    return StoredRow(role=role, content=content, **{**fields, **kw})


def patch(monkeypatch, tmp_path: Path, model) -> None:
    async def probe(provider, client=None):
        return Capabilities(True, False, None, None, "medium")

    monkeypatch.setenv("THEA_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(turn, "model_capabilities", probe)
    monkeypatch.setattr(turn, "build_model", lambda provider, **_: model)


def assert_calls_answered(messages) -> None:
    """What a provider insists on: every tool call has a return in the next request."""
    for i, m in enumerate(messages):
        if isinstance(m, ModelResponse):
            calls = {p.tool_call_id for p in m.parts if isinstance(p, ToolCallPart)}
            if calls:
                nxt = messages[i + 1]
                returned = {
                    p.tool_call_id for p in nxt.parts if isinstance(p, ToolReturnPart)
                }
                assert calls <= returned, f"unanswered tool calls {calls - returned}"


async def test_round_trip_through_model_message_json(
    turn_req, monkeypatch, tmp_path: Path
):
    (tmp_path / "a.md").write_text("A\n")
    (tmp_path / "b.md").write_text("B\n")

    def model(messages, info):
        n = sum(isinstance(m, ModelResponse) for m in messages)
        if n == 0:  # two returns in one request: two UI rows, one JSON
            return ModelResponse(parts=[
                TextPart("reading"),
                ToolCallPart("read_file", {"path": "a.md"}, tool_call_id="r1"),
                ToolCallPart("read_file", {"path": "b.md"}, tool_call_id="r2"),
            ])  # fmt: skip
        return ModelResponse(parts=[TextPart("both read")])

    patch(monkeypatch, tmp_path, stream_model(model))
    req = turn_req(history=[row("user", "read both")], lessons=[], chat=True)
    req.persona.tool_ids = ["read_file"]
    rec = Recorder()
    with capture_run_messages() as run_messages:
        await turn.run_turn(req, rec, Approvals(rec), CancellationToken())
    payloads = rec.named("message")
    assert [p["role"] for p in payloads] == ["assistant", "tool", "tool", "assistant"]
    assert payloads[2]["model_message_json"] is None
    rows = [row("user", "read both")] + [StoredRow.model_validate(p) for p in payloads]
    rebuilt = to_model_messages(rows)
    # The user row replays from text (Rust stores it without JSON); the rest is exact.
    assert rebuilt[1:] == repair_messages(run_messages)[1:]
    assert rebuilt[0].parts[0].content == "read both"


async def test_pre_migration_rows_replay_as_text(turn_req, monkeypatch, tmp_path: Path):
    calls = '[{"id":"c1","name":"read_file","arguments":{"path":"a.md"}}]'
    history = [
        row("user", "first"),
        row("assistant", "", tool_calls_json=calls),  # call with no text
        row("tool", "file text", tool_call_id="c1", tool_name="read_file"),
        row(
            "assistant",
            "Let me look.",
            tool_calls_json='[{"id":"c2","name":"read_file","arguments":{}}]',
        ),
        # c2 never got a result: the old turn was cancelled
        row("user", "again"),
    ]
    rebuilt = to_model_messages(history)
    assert not any(isinstance(p, ToolCallPart) for m in rebuilt for p in m.parts)
    text = [p.content for m in rebuilt for p in m.parts]
    assert '<tool_result name="read_file">\nfile text\n</tool_result>' in text
    assert "Let me look." in text

    def model(messages, info):
        assert_calls_answered(messages)
        assert not any(isinstance(p, ToolCallPart) for m in messages for p in m.parts)
        return ModelResponse(parts=[TextPart("fine")])

    patch(monkeypatch, tmp_path, stream_model(model))
    rec = Recorder()
    await turn.run_turn(
        turn_req(history=history, lessons=[]), rec, Approvals(rec), CancellationToken()
    )
    assert rec.named("chat:finished") == [{"chat_id": "c1", "error": None}]
    assert rec.named("message")[-1]["content"] == "fine"


def test_cancelled_json_tail_is_repaired():
    """A JSON row whose response's call never got a return: repair closes it."""
    from pydantic_ai import ModelMessagesTypeAdapter

    resp = ModelResponse(
        parts=[ToolCallPart("read_file", {"path": "a"}, tool_call_id="x")]
    )
    data = ModelMessagesTypeAdapter.dump_json([resp]).decode()
    rebuilt = to_model_messages(
        [
            row("user", "hi"),
            row("assistant", "", model_message_json=data),
            row("user", "next"),
        ]
    )
    assert_calls_answered(rebuilt)
    assert isinstance(rebuilt[-1], ModelRequest)


def test_unparseable_json_row_replays_as_text(capsys):
    """Schema drift in one stored row must not break the chat: that row replays as text."""
    rows = [
        row("user", "hi"),
        row("assistant", "hello there", model_message_json='[{"kind": "bogus"}]'),
        row("user", "again"),
    ]
    out = to_model_messages(rows)
    assert [type(m).__name__ for m in out] == [
        "ModelRequest",
        "ModelResponse",
        "ModelRequest",
    ]
    assert out[1].parts == [TextPart("hello there")]
    assert capsys.readouterr().err.count("\n") == 1
