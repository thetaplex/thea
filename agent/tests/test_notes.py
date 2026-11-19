from pathlib import Path

from conftest import allow_all
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from thea_agent.deps import TurnDeps
from thea_agent.tools.notes import add_note, insert_note

NOTES = "# Notes\n## Q1 What is it?\n- [S1] one\n\n## Q2 Why?\n"


def test_note_goes_last_under_its_heading():
    new, made = insert_note(NOTES, "Q1 What is it?", "- [S2] two")
    assert not made
    assert new == "# Notes\n## Q1 What is it?\n- [S1] one\n- [S2] two\n\n## Q2 Why?\n"


def test_heading_matches_without_hashes_case_or_spacing():
    new, made = insert_note(NOTES, "##  q2 why?", "- [S3] three")
    assert not made and new.endswith("## Q2 Why?\n- [S3] three\n")


def test_a_near_heading_is_new_not_guessed():
    # "Q1 What is this?" is not "Q1 What is it?": a guess could file the fact under the wrong question.
    new, made = insert_note(NOTES, "Q1 What is this?", "- [S2] two")
    assert made and new.endswith("## Q2 Why?\n\n## Q1 What is this?\n- [S2] two\n")


def test_first_note_makes_the_file_heading():
    assert insert_note("", "Learnings", "- [S1] a") == (
        "## Learnings\n- [S1] a\n",
        True,
    )


async def test_add_note_writes_the_file(tmp_path: Path):
    calls = [
        {"heading": "Q1 What is it?", "note": "[S1] one"},
        {"heading": "Q1 What is it?", "note": "- [S2] two"},
        {"heading": "Q1", "note": "x", "path": "research/sources.json"},
        {"heading": "Q1 What is it?", "note": "[S7] not registered"},
    ]

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        n = sum(isinstance(m, ModelResponse) for m in messages)
        if n < len(calls):
            return ModelResponse(parts=[ToolCallPart("add_note", calls[n])])
        return ModelResponse(parts=[TextPart("done")])

    from datetime import UTC, datetime

    from thea_agent.tools import ledger

    ledger.save_ledger(tmp_path, [ledger.Source(key=k, kind="web", title=k, url=f"https://e.org/{k}",
                                                added_at=datetime.now(UTC).isoformat()) for k in ("S1", "S2")])  # fmt: skip
    deps = TurnDeps(
        root=tmp_path, emit=lambda n, p: None, chat_id="c1", approvals=allow_all()
    )
    result = await Agent(
        FunctionModel(model), deps_type=TurnDeps, tools=[add_note]
    ).run("go", deps=deps)
    assert result.output == "done"
    assert (tmp_path / "research/notes.md").read_text() == (
        "## Q1 What is it?\n- [S1] one\n- [S2] two\n"
    )
    rets = [
        p
        for m in result.all_messages()
        for p in m.parts
        if isinstance(p, ToolReturnPart)
    ]
    assert "new heading" in str(rets[0].content) and "under its heading" in str(
        rets[1].content
    )
    assert rets[2].outcome == "failed"
    assert rets[3].outcome == "retried" and "[S7] not registered" in str(
        rets[3].content
    )
