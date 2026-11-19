import asyncio
from pathlib import Path

from conftest import Recorder, stream_model
from pydantic_ai import CancellationToken
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)

from thea_agent import turn
from thea_agent.approvals import Approvals
from thea_agent.models import Capabilities
from thea_agent.protocol import StoredRow
from thea_agent.reflection import (
    SYSTEM,
    accept_lesson,
    describe,
    detect_repeated_errors,
    summarize_trajectory,
)


def err(tool: str, msg: str, outcome="failed") -> ModelRequest:
    return ModelRequest(
        parts=[ToolReturnPart(tool, msg, tool_call_id=msg, outcome=outcome)]
    )


def row(role, content, tool_name=None) -> StoredRow:
    return StoredRow(
        role=role, content=content, tool_calls_json=None, tool_call_id=None,
        tool_name=tool_name, model_message_json=None,
    )  # fmt: skip


# --- ported from reflection.rs ---------------------------------------------------


def test_repeated_errors_need_three_same_tool_same_message():
    two = [err("fetch_url", "Error: timeout"), err("fetch_url", "Error: timeout")]
    assert detect_repeated_errors(two) is None
    three = [*two, err("fetch_url", "Error: timeout x", outcome="retried")]
    found = detect_repeated_errors(three)
    assert found is not None and found["count"] == 3 and found["tool"] == "fetch_url"
    assert detect_repeated_errors([err("a", "x"), err("b", "x"), err("c", "x")]) is None
    ok = ModelRequest(
        parts=[ToolReturnPart("fetch_url", "Error: timeout", tool_call_id="s")]
    )
    assert detect_repeated_errors([*two, ok]) is None  # a success is not an error


def test_accept_lesson_filters_shape():
    assert (
        accept_lesson(" When a fetch times out, try lookup_paper instead. ")
        == "When a fetch times out, try lookup_paper instead."
    )
    assert accept_lesson("Sure! Here is a lesson: When x, do y.") is None
    assert accept_lesson("When x, " + "y " * 200) is None
    assert accept_lesson("When a. Do b. Then c.") is None


def test_trajectory_summary_is_capped():
    rows = [row("tool", "x" * 500, f"t{i}") for i in range(200)]
    rows.append(row("assistant", "FINAL-ANSWER-START"))
    s = summarize_trajectory(rows)
    assert len(s) <= 4000
    assert "FINAL-ANSWER-START" in s


def test_describe_signals():
    assert describe({"kind": "rating", "up": False, "comment": "too long"}) == (
        "The user rated the answer thumbs-down. Comment: too long"
    )
    assert (
        describe({"kind": "citations", "pass": True, "detail": "PASS"})
        == "check_citations passed:\nPASS"
    )


# --- in the turn -------------------------------------------------------------------


async def test_lesson_only_on_signal(turn_req, monkeypatch, tmp_path: Path):
    (tmp_path / "draft.md").write_text("The cat sat on the mat.\n")
    prompts: list[str] = []
    release = asyncio.Event()

    async def model(messages, info):
        if info.instructions == SYSTEM:  # the reflection call
            await release.wait()
            prompts.append(messages[-1].parts[-1].content)
            return ModelResponse(
                parts=[TextPart("When a draft passes, stop editing it.")]
            )
        if len(messages) == 1 and info.function_tools:
            return ModelResponse(
                parts=[ToolCallPart("check_citations", {"path": "draft.md"})]
            )
        return ModelResponse(parts=[TextPart("checked")])

    async def probe(provider, client=None):
        return Capabilities(True, False, None, None, "medium")

    monkeypatch.setenv("THEA_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(turn, "model_capabilities", probe)
    monkeypatch.setattr(turn, "build_model", lambda provider, **_: stream_model(model))

    async def run(tools: list[str]) -> Recorder:
        req = turn_req(history=[row("user", "check it")], lessons=["When x, do y."])
        req.persona.tool_ids = tools
        rec = Recorder()
        await turn.run_turn(req, rec, Approvals(rec), CancellationToken())
        return rec

    rec = await run(["read_file"])  # no check tool ran: no signal, no reflection
    assert rec.named("lesson") == [] and prompts == [] and not turn.background

    rec = await run(["check_citations"])
    # The turn returned while its reflection still waits: the next turn is not held up.
    assert rec.named("lesson") == [] and len(turn.background) == 1
    release.set()
    await asyncio.gather(*turn.background)
    assert rec.named("lesson") == [
        {
            "persona_id": "p1",
            "signal": "check_citations",
            "text": "When a draft passes, stop editing it.",
        }
    ]
    assert rec.events[-1][0] == "lesson"  # after chat:finished
    [prompt] = prompts
    assert "Signal: check_citations passed:" in prompt
    assert "Existing lessons:\n1. When x, do y." in prompt
    assert "Task:\ncheck it" in prompt
