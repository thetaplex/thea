import importlib.util
import json
from pathlib import Path

import pytest
from conftest import stream_model
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart

from thea_agent import eval as ev
from thea_agent import turn

PERSONAS_DDL = """CREATE TABLE personas (id TEXT PRIMARY KEY, name TEXT, tagline TEXT,
    system_prompt TEXT, tool_ids_json TEXT, skill_ids_json TEXT, mcp_server_ids_json TEXT,
    native_thinking INTEGER, max_steps INTEGER, updated_at TEXT)"""


# As in `default_personas()`: only the personal assistant has run_command.
TOOLS = {
    "research-assistant": ["read_file", "write_file"],
    "personal-assistant": ["read_file", "write_file", "run_command"],
}


def persona_db(path: Path, *ids: str) -> Path:
    """A database with the columns the app's `personas` table has and the eval reads."""
    import sqlite3

    with sqlite3.connect(path) as conn:
        conn.execute(PERSONAS_DDL)
        for i in ids:
            conn.execute(
                "INSERT INTO personas VALUES (?,?,?,?,?,?,?,?,?,?)",
                (i, i, "t", f"You are {i}.", json.dumps(TOOLS[i]), "[]", "[]", 0, 0, "2026-11-17T10:00:00Z"),
            )  # fmt: skip
    conn.close()
    return path


@pytest.fixture(autouse=True)
def app_db(tmp_path, monkeypatch):
    db = persona_db(
        tmp_path / "thea.sqlite3", "research-assistant", "personal-assistant"
    )
    monkeypatch.setattr(ev, "APP_DB", db)
    return db


SOURCE = {
    "key": "S1", "kind": "web", "title": "Cats", "url": "https://example.com/cats",
    "added_at": "2026-11-16",
}  # fmt: skip


async def run(case, decide=None, folder: Path | None = None) -> dict:
    """One case through run_case, scored as promptfoo's provider scores it."""
    model = stream_model(decide or (lambda m, i: ModelResponse(parts=[TextPart("x")])))
    o = await ev.run_case(case, "m", "http://localhost:1", model=model)
    if folder:
        ev.write_transcript(folder, case.id, o)
    return ev.metrics(case, o)


def test_sanitize_keeps_names_inside_one_folder():
    assert ev.sanitize("../x/y") == "..-x-y"
    assert "/" not in ev.sanitize("../x/y")


def test_render_prompt_reads_system_dict_then_message_dumps():
    messages = [
        {"role": "system", "content": "S"},
        {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "U"}]},
    ]
    out = ev.render_prompt(
        {"messages": messages, "tools": [{"name": "t", "description": "D"}]}
    )
    assert out == "## system\n\nS\n\n## user-prompt\n\nU\n\n## tools\n\n- `t`: D\n"


def test_case_defaults():
    case = ev.Case(id="a", prompt="p")
    assert (case.min_sources, case.persona, case.seed_files) == (2, None, {})


async def test_case_runs_with_function_model(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("THEA_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(ev, "MCP_PRESETS", [])  # no npx in tests

    async def probe(provider, client=None):
        return turn.Capabilities(True, False, None, None, "medium")

    monkeypatch.setattr(turn, "model_capabilities", probe)

    def decide(messages, info):
        if len(messages) == 1:
            args = {"path": "research/drafts/a.md", "content": "Cats purr [S1]."}
            return ModelResponse(parts=[ToolCallPart("write_file", args)])
        return ModelResponse(parts=[TextPart("Done.")])

    case = ev.Case(
        id="c1", prompt="write", min_sources=1,
        seed_files={
            "research/sources.json": json.dumps([SOURCE]),
            "research/drafts/.keep": "",  # write_file needs the folder
        },
    )  # fmt: skip
    out = tmp_path / "results"
    r = await run(case, decide, out)
    assert r["error"] is None
    assert (r["citations_pass"], r["sources_ok"], r["sources"], r["thought_steps"]) == (
        True,
        True,
        1,
        0,
    )
    assert r["draft_produced"] and r["steps_used"] >= 1
    assert json.loads((out / "c1.json").read_text())
    assert "## system" in (out / "c1.prompt.md").read_text()


@pytest.fixture
def headless(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("THEA_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(ev, "MCP_PRESETS", [])

    async def probe(provider, client=None):
        return turn.Capabilities(True, False, None, None, "medium")

    monkeypatch.setattr(turn, "model_capabilities", probe)


def pa_case(**kw) -> "ev.Case":
    return ev.Case(
        id="pa", prompt="go", min_sources=1, persona="personal-assistant",
        seed_files={"docket/drafts/.keep": "", **kw.pop("seed", {})}, **kw,
    )  # fmt: skip


async def test_shell_is_rejected_and_case_completes(tmp_path: Path, headless):
    def decide(messages, info):
        if len(messages) == 1:
            return ModelResponse(
                parts=[ToolCallPart("run_command", {"command": "touch pwned"})]
            )
        return ModelResponse(parts=[TextPart("Done.")])

    r = await run(pa_case(), decide, tmp_path / "r")
    rows = json.loads((tmp_path / "r" / "pa.json").read_text())
    assert any("rejected" in m["content"] for m in rows if m["role"] == "tool")
    assert r["error"] is None and r["steps_used"] >= 1


async def test_docket_refs_are_scored(tmp_path: Path, headless):
    item = {
        "key": "[D1]",
        "kind": "task",
        "title": "t",
        "status": "open",
        "created_at": "x",
    }

    def decide(draft):
        def f(messages, info):
            if len(messages) == 1:
                args = {"path": "docket/drafts/m.md", "content": draft}
                return ModelResponse(parts=[ToolCallPart("write_file", args)])
            return ModelResponse(parts=[TextPart("Done.")])

        return f

    seed = {"docket/docket.json": json.dumps([item])}
    for draft, ok in (("Do [D1] now.", True), ("Do [D9] now.", False)):
        r = await run(pa_case(seed=seed), decide(draft))
        assert (r["citations_pass"], r["sources"], r["draft_produced"]) == (ok, 1, True)


async def test_a_setup_error_is_the_case_error(tmp_path: Path, headless, monkeypatch):
    def broken(dest):
        raise OSError("no skills")

    monkeypatch.setattr(ev, "materialize_skills", broken)
    r = await run(ev.Case(id="ok", prompt="p"))
    assert r["error"] == "setup: no skills" and not r["citations_pass"]


def _load(name: str):
    path = Path(__file__).resolve().parents[2] / "evals/promptfoo" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"promptfoo_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_provider_runs_the_case_and_returns_its_scores(tmp_path: Path, monkeypatch):
    provider = _load("provider")
    seen = {}

    async def run_case(case, model_name, base_url, model=None):
        seen.update(case=case, model=model_name, base_url=base_url)
        return ev.Outcome("research-assistant", messages=[
            {"role": "assistant", "content": "The answer.", "tool_name": None},
        ])  # fmt: skip

    monkeypatch.setattr(ev, "run_case", run_case)
    monkeypatch.setattr(provider, "REPO", tmp_path)
    vars = {"id": "c1", "prompt": "p", "min_sources": 3, "suite": "research"}
    out = provider.call_api("p", {"config": {"model": "m:1"}}, {"vars": vars})
    assert (seen["case"].id, seen["case"].min_sources, seen["model"]) == (
        "c1",
        3,
        "m:1",
    )
    assert seen["base_url"] == "http://127.0.0.1:11434"
    assert out["output"] == "The answer."
    assert out["metadata"]["sources_ok"] is False and out["metadata"]["error"] is None
    [folder] = (tmp_path / "evals/results/promptfoo").iterdir()
    assert folder.name.startswith("research-m-1-") and (folder / "c1.json").exists()


def test_a_crashed_turn_fails_no_error():
    score = _load("score")
    ctx = {
        "providerResponse": {"metadata": {"error": "edit_file exceeded max retries"}}
    }
    assert score.no_error("", ctx)["pass"] is False
    assert score.no_error("", {"providerResponse": {"metadata": {"error": None}}})[
        "pass"
    ]


def test_materialize_skills_writes_agent_skills_layout(tmp_path: Path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    (src / "demo.md").write_text(
        '---\nname: demo\ndescription: Use when: x "q"\n---\n\nBody line.\n'
    )
    monkeypatch.setattr(ev, "SKILLS_SRC", src)
    ev.materialize_skills(tmp_path / "out")
    assert (tmp_path / "out" / "demo" / "SKILL.md").read_text() == (
        '---\nname: demo\ndescription: "Use when: x \\"q\\""\n---\n\nBody line.\n'
    )


def test_persona_comes_from_the_app_database(app_db):
    persona, updated = ev.load_persona("personal-assistant", app_db)
    assert persona.system_prompt == "You are personal-assistant."
    assert persona.tool_ids == TOOLS["personal-assistant"] and persona.builtin
    assert updated == "2026-11-17T10:00:00Z"


async def test_a_missing_database_is_the_case_error(monkeypatch, tmp_path):
    monkeypatch.setattr(ev, "APP_DB", tmp_path / "none.sqlite3")
    m = await run(ev.Case(id="c", prompt="go"))
    assert "Start Thea once (`just run`)" in m["error"]


async def test_a_missing_persona_is_the_case_error():
    m = await run(ev.Case(id="c", prompt="go", persona="nobody"))
    assert "No persona 'nobody'" in m["error"]


async def test_results_record_when_the_persona_was_written():
    m = await run(ev.Case(id="c", prompt="go"))
    assert m["persona_updated_at"] == "2026-11-17T10:00:00Z"


# --- checks of what the user gets ------------------------------------------------


def _out(files=None, messages=None, drafts=None, incomplete=None, reply=""):
    return ev.Outcome(
        "research-assistant", files=files or {}, messages=messages or [],
        drafts=drafts or [], incomplete=incomplete or [], reply=reply,
    )  # fmt: skip


def _tool(name, content):
    return {"role": "tool", "tool_name": name, "content": content}


BRIEF = ev.Case(
    id="b", prompt="p", min_sources=2,
    deliverable=ev.Deliverable(glob="research/drafts/*-brief.md", words=(5, 50)),
)  # fmt: skip


def test_complete_fails_on_an_incomplete_turn():
    assert ev.check_complete(_out())[0]
    inc = {
        "reason": "The model stopped with TASK.md items still open.",
        "open_items": ["- [ ] a"],
    }
    ok, why = ev.check_complete(_out(incomplete=[inc]))
    assert not ok and "Open: 1" in why


def test_deliverable_needs_the_file_no_todo_and_the_word_range():
    assert (
        ev.check_deliverable(BRIEF, _out())[1]
        == "no file matches research/drafts/*-brief.md"
    )
    todo = {"research/drafts/x-brief.md": "# T\n## Key message\nTODO key message\n"}
    assert "1 TODO lines left" in ev.check_deliverable(BRIEF, _out(files=todo))[1]
    short = {"research/drafts/x-brief.md": "# T\nOne two three.\n"}
    assert "3 words, want 5 to 50" in ev.check_deliverable(BRIEF, _out(files=short))[1]
    good = {
        "research/drafts/x-brief.md": "# T\nOne two three four five six.\n## References\n- [S1] x y z\n"
    }
    assert ev.check_deliverable(BRIEF, _out(files=good)) == (
        True,
        "research/drafts/x-brief.md: 6 words",
    )


def test_sources_counts_keys_the_drafts_cite():
    assert ev.check_sources(BRIEF, _out(drafts=["a [S1] b [S1]"])) == (
        False,
        "1 cited, 2 needed",
    )
    assert ev.check_sources(BRIEF, _out(drafts=["a [S1] b [S2]"]))[0]


def test_honest_report_names_the_file_and_a_failed_check():
    files = {"research/drafts/x-brief.md": "text"}
    fail = [_tool("check_citations", "FAIL: [S9] is not in the ledger.")]
    assert (
        "does not name" in ev.check_honest_report(BRIEF, _out(files, reply="Done."))[1]
    )
    hidden = _out(files, messages=fail, reply="Done: x-brief.md. All fixed.")
    assert (
        "check_citations failed, the reply does not say so"
        in ev.check_honest_report(BRIEF, hidden)[1]
    )
    told = _out(
        files,
        messages=fail,
        reply="Wrote x-brief.md. check_citations: FAIL, [S9] left.",
    )
    assert ev.check_honest_report(BRIEF, told)[0]


def test_event_needs_start_end_and_location():
    case = ev.Case(
        id="e", prompt="p",
        event=ev.Event(start="20261125T100000Z", end="20261125T110000Z", location="Room A"),
    )  # fmt: skip
    ics = "DTSTART:20261125T100000Z\nDTEND:20261125T110000Z\nLOCATION:Room A\n"
    assert ev.check_event(case, _out(files={"docket/calendar/a.ics": ics}))[0]
    wrong = ics.replace("Room A", "Room B")
    assert (
        "location is not Room A"
        in ev.check_event(case, _out(files={"docket/calendar/a.ics": wrong}))[1]
    )
    assert not ev.check_event(case, _out())[0]


def test_metrics_carry_every_check():
    m = ev.metrics(BRIEF, _out())
    assert set(m["checks"]) == {
        "complete", "deliverable", "sources_cited", "honest_report", "event",
    }  # fmt: skip
    assert m["checks"]["deliverable"]["pass"] is False


def test_case_files_name_what_the_user_asked_for():
    """Every case says which file the user gets; calendar cases say the event."""
    evals = Path(__file__).resolve().parents[2] / "evals"
    for f in [*evals.glob("research/*.json"), *evals.glob("assistant/*.json")]:
        case = ev.Case.model_validate_json(f.read_text())
        assert case.deliverable is not None, f.name
    for name in ("schedule-kickoff", "weekly-triage"):
        case = ev.Case.model_validate_json(
            (evals / f"assistant/{name}.json").read_text()
        )
        assert case.event is not None, name
