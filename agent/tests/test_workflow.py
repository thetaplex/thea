"""Workflow turn: code plans the files and the order; a scripted model only fills in text."""

import json
from datetime import UTC, datetime
from pathlib import Path

from conftest import Recorder, stream_model
from pydantic_ai import ToolFailed
from pydantic_ai.messages import ModelResponse, TextPart
from test_turn import allowed, go, make_req

from thea_agent import workflow
from thea_agent.tools import ledger, research

SKILL = """---
name: write-brief
description: Write a brief. Use when the user asks for a brief.
---
File: `research/drafts/<slug>-brief.md`. Length: 500 to 700 words.

```markdown
# <Title>

## Key message
TODO key message: 1 sentence.

## Evidence
TODO evidence: 150 to 250 words.

## References
TODO references
```
"""

PLAN = {
    "title": "Heat pumps in cold climates",
    "slug": "Heat Pumps!",
    "questions": [
        {
            "question": "Do heat pumps work below -15 C?",
            "query": "heat pump -15 C capacity",
        }
    ],
    "min_words": 500,
    "max_words": 700,
}
Q1 = "Q1 Do heat pumps work below -15 C?"


def scripted(seen: list[str]):
    """Answers by which workflow call it is, read from the instructions."""

    def decide(messages, info):
        ins = info.instructions or ""
        if ins.startswith("Pick the writing skill"):
            seen.append("pick")
            return ModelResponse(parts=[TextPart("write-brief")])
        if ins.startswith("Plan the research"):
            seen.append("plan")
            # No questions first: the plan check sends it back. The slug is code's to fix.
            return ModelResponse(
                parts=[
                    TextPart(
                        json.dumps(
                            PLAN if len(messages) > 1 else {**PLAN, "questions": []}
                        )
                    )
                ]
            )
        if ins.startswith("List the facts"):
            seen.append("facts")
            page = messages[0].parts[-1].content
            if "Looping" in page:  # never valid JSON: after the retries, the next hit
                return ModelResponse(
                    parts=[TextPart('{"facts": ["x"]}<tool_call|>\n\n')]
                )
            if (
                "Unrelated" in page
            ):  # off the question: no facts; code reads the next hit
                return ModelResponse(parts=[TextPart(json.dumps({"facts": []}))])
            fact = "They keep 70% of capacity at -15 C (Table 2)."
            return ModelResponse(parts=[TextPart(json.dumps({"facts": [fact]}))])
        if ins.startswith("You write one part"):
            seen.append("write")
            if len(messages) == 1 and "Write the `Key message`" in str(
                messages[0].parts[-1].content
            ):  # the whole document in one part: the heading check sends it back
                paper = "They work [S1].\n\n## Evidence\nThe other part [S1]."
                return ModelResponse(parts=[TextPart(paper)])
            if len(messages) == 1:  # the key check sends it back as a new prompt
                return ModelResponse(parts=[TextPart("They work [S9].")])
            return ModelResponse(
                parts=[TextPart("Heat pumps keep 70% of capacity at -15 C [S1].")]
            )
        if ins.startswith("You clean up"):
            seen.append("cleanup")
            return ModelResponse(
                parts=[TextPart("# Heat pumps\n\n## Evidence\n\nThey work.")]
            )  # drops [S1]
        raise AssertionError(f"unexpected call: {ins[:40]}")

    return decide


async def test_workflow_turn_writes_the_deliverable(
    turn_req, use_model, monkeypatch, tmp_path: Path
):
    monkeypatch.setenv("THEA_WORKFLOW", "1")
    skills = tmp_path / "skills" / "write-brief"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(SKILL)
    ledger.save_ledger(tmp_path, [ledger.Source(
        key="S1", kind="web", title="Cold climate field study", authors=["A. Author"], year=2024,
        url="https://example.org/study", added_at=datetime.now(UTC).isoformat(),
    )])  # fmt: skip
    hits = [
        research.SearchHit(title="Down", url="https://example.org/down"),
        research.SearchHit(title="Looping", url="https://example.org/loop"),
        research.SearchHit(title="Unrelated", url="https://example.org/other"),
        research.SearchHit(title="Field study", url="https://example.org/study"),
    ]
    searched: list[str] = []

    async def search(searxng_url, query, n):
        searched.append(query)
        return hits

    async def fetch(url, max_chars):
        if url.endswith("down"):
            raise ToolFailed("fetch failed")
        title = {"other": "Unrelated", "loop": "Looping"}.get(
            url.rsplit("/", 1)[1], "Cold climate field study"
        )
        return research.Fetched(
            title=title,
            url=url,
            fetched_at="t",
            text=f"{title} text " * 50,
            content_type="text/html",
        )

    monkeypatch.setattr(research, "search_one", search)
    monkeypatch.setattr(research, "fetch", fetch)
    seen: list[str] = []
    use_model(stream_model(scripted(seen)))
    req = make_req(
        turn_req, "Write a brief on heat pumps.", tools=[], chat=False,
        skill_dirs=[str(tmp_path / "skills")], skills=["write-brief"],
    )  # fmt: skip
    req.persona.id = "research-assistant"
    rec = Recorder()
    await go(req, rec, allowed(rec))

    [finished] = rec.named("chat:finished")
    assert finished["error"] is None
    # Evidence asks for 150 to 250 words: the short part goes back once, and the last try stands.
    # Code searched and read; the model only listed facts, one call per page read.
    assert searched == [
        "heat pump -15 C capacity"
    ]  # the planner's query, not the question
    assert seen == ["pick", "plan", "plan"] + ["facts"] * 5 + ["write"] * 5 + [
        "cleanup"
    ]
    brief = (tmp_path / "research/drafts/heat-pumps-brief.md").read_text()
    # Skeleton order; the cleanup that lost [S1] was not kept; code wrote the references.
    assert (
        brief.index("## Key message")
        < brief.index("## Evidence")
        < brief.index("## References")
    )
    assert brief.count("## Evidence") == 1 and "The other part" not in brief
    assert "[S9]" not in brief and "70% of capacity at -15 C [S1]" in brief
    assert (
        "- [S1] A. Author (2024). Cold climate field study. https://example.org/study"
        in brief
    )
    assert "TODO" not in brief
    task = (tmp_path / "TASK.md").read_text()
    assert (
        "- [ ]" not in task and task.count("- [x]") == 3 and f"Research: {Q1}" in task
    )
    assert (
        "- [S1] They keep 70% of capacity at -15 C (Table 2)."
        in (tmp_path / "research/notes.md").read_text()
    )  # the page already in the ledger keeps its key
    assert [s.key for s in ledger.load_ledger(tmp_path)] == [
        "S1"
    ]  # no facts, not registered
    # The model never edited a file; the last row is the reply code wrote from the real state.
    calls = [
        json.loads(r["tool_calls_json"] or "[]")
        for _, r in rec.events
        if _ == "message"
    ]
    assert not any(c["name"] in ("edit_file", "write_file") for cs in calls for c in cs)
    last = [p for n, p in rec.events if n == "message"][-1]
    assert last["content"].startswith("Wrote research/drafts/heat-pumps-brief.md")
    assert "check_citations: PASS" in last["content"]
    assert not rec.named("agent:incomplete")


def test_clean_is_safe_keeps_headings_keys_and_length():
    before = "# T\n\n## A\n\nOne two three four five [S1].\n"
    assert workflow.clean_is_safe(
        before, "# T\n\n## A\n\nOne two three four, five [S1].\n"
    )
    assert not workflow.clean_is_safe(
        before, "# T\n\n## A\n\nOne two three four five.\n"
    )
    assert not workflow.clean_is_safe(before, "# T\n\nOne two three four five [S1].\n")
    assert not workflow.clean_is_safe(before, "# T\n\n## A\n\nOne [S1].\n")


def test_skeleton_blanks_and_fill():
    sk = workflow.parse_skeleton(SKILL)
    assert sk.path == "research/drafts/<slug>-brief.md"
    assert [(b.heading, b.todo) for b in sk.blanks] == [
        ("Key message", "key message: 1 sentence."),
        ("Evidence", "evidence: 150 to 250 words."),
    ]
    out = workflow.fill(sk, "T", {sk.blanks[1].line: "Facts [S1]."})
    assert out == "# T\n\n## Key message\n\n## Evidence\nFacts [S1].\n\n## References\n"
    assert workflow.parse_skeleton("no skeleton here") is None


def test_word_range_reads_only_plain_word_counts():
    assert workflow.word_range("evidence: 150 to 250 words. The facts.") == (150, 250)
    assert workflow.word_range("findings: 3 bullets, 20 to 40 words each.") == (60, 120)
    assert workflow.word_range("abstract: 4 to 6 sentences.") is None
    assert workflow.words("It keeps 70% [S1] of its capacity.") == 6


def test_section_ranges_follow_the_length_asked_for():
    sk = workflow.parse_skeleton(SKILL)
    assert sk.length == (500, 700) and sk.rule == "500 to 700 words."
    short = workflow.Plan(
        title="T",
        slug="t",
        questions=[workflow.Question(question="q", query="q")],
        min_words=250,
        max_words=350,
    )
    assert workflow.length_factor(sk, short) == 0.5
    assert (
        workflow.scale_todo("evidence: 150 to 250 words.", 0.5)
        == "evidence: 80 to 120 words."
    )
    assert (
        workflow.scale_todo("3 bullets, 40 to 60 words each.", 0.5)
        == "3 bullets, 20 to 30 words each."
    )


def test_cleanup_keeps_the_planned_length():
    before = "# T\n\n## A\n\n" + "word " * 100 + "[S1].\n"
    cut = "# T\n\n## A\n\n" + "word " * 85 + "[S1].\n"
    assert workflow.clean_is_safe(
        before, cut
    )  # 85% of the words is fine without a target
    assert not workflow.clean_is_safe(
        before, cut, min_words=90
    )  # but not below the plan's minimum
    assert (
        workflow.body_words(before + "\n## References\n\n- [S1] A (2024). T. u\n")
        == 100
    )


def test_path_does_not_double_the_suffix():
    tpl = "research/drafts/<slug>-report.md"
    assert (
        workflow.skeleton_path(tpl, "sqlite-wal-report")
        == "research/drafts/sqlite-wal-report.md"
    )
    assert (
        workflow.skeleton_path(tpl, "sqlite-wal")
        == "research/drafts/sqlite-wal-report.md"
    )
    assert workflow.skeleton_path(tpl, "report") == "research/drafts/report-report.md"


async def test_no_facts_means_no_draft(
    turn_req, use_model, monkeypatch, tmp_path: Path
):
    monkeypatch.setenv("THEA_WORKFLOW", "1")
    skills = tmp_path / "skills" / "write-brief"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(SKILL)

    async def search(searxng_url, query, n):
        raise ToolFailed("web search failed on every provider (searxng: down)")

    monkeypatch.setattr(research, "search_one", search)
    seen: list[str] = []
    use_model(stream_model(scripted(seen)))
    req = make_req(
        turn_req, "Write a brief on heat pumps.", tools=[], chat=False,
        skill_dirs=[str(tmp_path / "skills")], skills=["write-brief"],
    )  # fmt: skip
    req.persona.id = "research-assistant"
    rec = Recorder()
    await go(req, rec, allowed(rec))

    assert "write" not in seen and not (tmp_path / "research/drafts").exists()
    last = [p for n, p in rec.events if n == "message"][-1]["content"]
    assert last.startswith("Not written: research found no source with facts.")
    assert "searxng: down" in last
    assert "- [!] Research: Q1" in (tmp_path / "TASK.md").read_text()
