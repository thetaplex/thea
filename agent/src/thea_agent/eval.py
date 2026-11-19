"""Headless eval: runs one case through `run_turn` and scores the drafts.

promptfoo drives it (`just eval`, evals/promptfoo/provider.py). The persona comes from the
app's own database, `$THEA_HOME/thea.sqlite3`, so the eval runs what the app runs. Thea seeds
the built-in personas on start, so after a change to `default_personas()` start the app once.
"""

import asyncio
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_ai import CancellationToken

from thea_agent import turn, workflow
from thea_agent.approvals import Approvals
from thea_agent.protocol import (
    McpServer,
    Persona,
    Provider,
    StoredRow,
    TurnRequest,
    Workspace,
)
from thea_agent.tools import docket, ledger

DEFAULT_PERSONA = "research-assistant"
TURN_TIMEOUT = 900
REFLECTION_TIMEOUT = 120
SKILLS_SRC = (
    Path(__file__).resolve().parents[3] / "skills"
)  # repo checkout, as in `just eval`
# Read before run_case points THEA_HOME at a scratch folder.
APP_DB = Path(os.environ.get("THEA_HOME") or Path.home() / ".thea") / "thea.sqlite3"
# Same ids as `builtin_persona_ids()` in src-tauri/src/db.rs; the database has no flag for it.
BUILTIN_PERSONAS = ("personal-assistant", "research-assistant")


def turn_settings(home: Path) -> dict:
    """The settings the app sends with a turn (turn_request.rs), from the app's settings.json."""
    try:
        saved = json.loads((home / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    return {"searxng_url": saved.get("searxng_url", "http://127.0.0.1:8888")}


def load_persona(persona_id: str, db: Path) -> tuple[Persona, str]:
    """The persona as the app stores it, and when it was last written."""
    if not db.is_file():
        raise RuntimeError(
            f"No Thea database at {db}. Start Thea once (`just run`) to create it."
        )
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        row = conn.execute(
            "SELECT id, name, tagline, system_prompt, tool_ids_json, skill_ids_json,"
            " mcp_server_ids_json, native_thinking, max_steps, updated_at"
            " FROM personas WHERE id = ?",
            (persona_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError(
            f"No persona {persona_id!r} in {db}. Start Thea once (`just run`) to seed it."
        )
    id, name, tagline, prompt, tools, skills, servers, thinking, steps, updated = row
    persona = Persona(
        id=id, name=name, tagline=tagline, system_prompt=prompt,
        tool_ids=json.loads(tools), skill_ids=json.loads(skills),
        mcp_server_ids=json.loads(servers), builtin=id in BUILTIN_PERSONAS,
        native_thinking=bool(thinking), max_steps=steps,
    )  # fmt: skip
    return persona, updated


def _npx(id: str, name: str, pkg: str, auto_approve: bool) -> McpServer:
    return McpServer(
        id=id, name=name, command="npx", args=["-y", pkg], env={},
        enabled=True, auto_approve=auto_approve,
    )  # fmt: skip


# Same servers and pins as `mcp_presets()` in src-tauri/src/db.rs.
MCP_PRESETS = [
    _npx("sequential-thinking", "Sequential Thinking", "@modelcontextprotocol/server-sequential-thinking@2.1.1", True),
    _npx("playwright", "Playwright", "@playwright/mcp@0.0.85", False),
]  # fmt: skip


def sanitize(s: str) -> str:
    """Keeps ASCII letters, digits, `.` and `-`; every other character becomes `-`."""
    return "".join(c if c.isascii() and c.isalnum() or c in ".-" else "-" for c in s)


class Deliverable(BaseModel):
    """The file the user asked for: a glob under the workspace, and its word range if any."""

    glob: str
    words: tuple[int, int] | None = None


class Event(BaseModel):
    """A calendar event the user asked for, as it must appear in the exported .ics."""

    start: str  # DTSTART value, e.g. 20261125T100000
    end: str
    location: str


class Case(BaseModel):
    id: str
    prompt: str
    min_sources: int = 2
    persona: str | None = None
    seed_files: dict[str, str] = {}
    deliverable: Deliverable | None = None
    event: Event | None = None


def render_prompt(v: dict) -> str:
    """One `## heading` per part, then the tool list, so a prompt reads as one document.
    `messages` is one `{role, content}` dict followed by pydantic-ai message dumps."""
    out = ""
    for m in v["messages"]:
        if "role" in m:
            out += f"## {m['role']}\n\n{m.get('content', '')}\n\n"
            continue
        for p in m["parts"]:
            body = p.get("content")
            if "tool_name" in p and body is None:
                body = f"{p['tool_name']}({p.get('args')})"
            if not isinstance(body, str):
                body = json.dumps(body, ensure_ascii=False)
            out += f"## {p['part_kind']}\n\n{body}\n\n"
    out += "## tools\n\n"
    for t in v["tools"]:
        out += f"- `{t['name']}`: {t.get('description') or ''}\n"
    return out


@dataclass
class Outcome:
    """What a case run leaves behind, read before its folders are removed."""

    persona: str
    drafts: list[str] = field(default_factory=list)
    sources: list[ledger.Source] = field(default_factory=list)
    items: list[docket.DocketItem] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    prompt: str = ""
    persona_updated_at: str = ""
    files: dict[str, str] = field(
        default_factory=dict
    )  # every .md and .ics, by workspace path
    incomplete: list[dict] = field(default_factory=list)  # agent:incomplete events
    reply: str = ""  # the last assistant text of the turn
    max_prompt_chars: int = 0
    error: str | None = None


def _drafts(root: Path, subs: tuple[str, ...]) -> list[str]:
    files = [f for s in subs for f in sorted((root / s).glob("*.md"))]
    return sorted(f.read_text(encoding="utf-8", errors="replace") for f in files)


def score(case: Case, o: Outcome) -> dict[str, Any]:
    """citations_pass, sources_ok, sources, thought_steps."""
    if o.persona == "personal-assistant":
        known = {i.key for i in o.items}
        refs_ok = True
        for d in o.drafts:  # every [D#] must be a Docket key, and one must be there
            keys = re.findall(r"\[D\d+\]", d)
            refs_ok &= bool(keys) and all(k in known for k in keys)
        passed, sources = refs_ok, len(o.items)
    else:
        passed = all(ledger.check_citations_text(d, o.sources).passed for d in o.drafts)
        sources = len(o.sources)
    return {
        "citations_pass": passed and bool(o.drafts),
        "sources_ok": sources >= case.min_sources,
        "sources": sources,
        "thought_steps": sum(
            m["role"] == "tool"
            and (m["tool_name"] or "").endswith("__sequentialthinking")
            for m in o.messages
        ),
    }


class HeadlessApprovals(Approvals):
    """No UI: a category not allowed up front is rejected at once, never waited on."""

    async def ask(self, chat_id, project_id, category, *args, **kw) -> bool:
        return (project_id, category) in self.allowed


def materialize_skills(dest: Path) -> None:
    """Built-in `skills/<name>.md` -> `<dest>/<name>/SKILL.md`, as `write_skill_library` does.
    JSON strings are valid YAML scalars, so the description needs no other escaping."""
    for f in SKILLS_SRC.glob("*.md"):
        front, _, body = (
            f.read_text(encoding="utf-8")
            .replace("\r\n", "\n")
            .removeprefix("---\n")
            .partition("\n---\n")
        )
        desc = next(
            l.removeprefix("description:").strip()
            for l in front.splitlines()
            if l.startswith("description:")
        )
        (dest / f.stem).mkdir(parents=True)
        (dest / f.stem / "SKILL.md").write_text(
            f"---\nname: {f.stem}\ndescription: {json.dumps(desc)}\n---\n\n{body.strip()}\n",
            encoding="utf-8",
        )


async def run_case(case: Case, model_name: str, base_url: str, model=None) -> Outcome:
    persona_id = case.persona or DEFAULT_PERSONA
    out = Outcome(persona_id)
    home = Path(tempfile.mkdtemp(prefix="thea-eval-home-"))
    root = Path(tempfile.mkdtemp(prefix="thea-eval-project-"))
    # ponytail: env var is process-global; cases run one at a time so this is safe.
    os.environ["THEA_HOME"] = str(home)
    events: list[tuple[str, dict]] = []
    try:
        for rel, content in case.seed_files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(content, encoding="utf-8")
        materialize_skills(home / "skills")
        persona, out.persona_updated_at = load_persona(persona_id, APP_DB)
        req = TurnRequest(
            type="turn", chat_id=case.id, persona=persona,
            provider=Provider(protocol="ollama", base_url=base_url, api_key="", model=model_name),
            small_model=None,
            workspace=Workspace(id=case.id, name=case.id, root_path=str(root), instructions="", is_chat=False),
            knowledge_files=[], skill_dirs=[str(home / "skills")], skills=persona.skill_ids,
            mcp_servers=MCP_PRESETS, settings=turn_settings(APP_DB.parent), lessons=[],
            history=[StoredRow(
                role="user", content=case.prompt, tool_calls_json=None,
                tool_call_id=None, tool_name=None, model_message_json=None,
            )],
        )  # fmt: skip
        approvals = HeadlessApprovals(lambda name, payload: None)
        # Headless: write and mcp are allowed up front; shell stays gated, so run_command is rejected.
        approvals.allowed |= {(case.id, c) for c in ("write", "mcp")}
        token = CancellationToken()
        try:
            await asyncio.wait_for(
                turn.run_turn(
                    req, lambda n, p: events.append((n, p)), approvals, token, model
                ),
                TURN_TIMEOUT,
            )
            if turn.background:  # let the lesson land in this case's THEA_HOME
                _, pending = await asyncio.wait(
                    set(turn.background), timeout=REFLECTION_TIMEOUT
                )
                if pending:
                    print(
                        f"{case.id}: reflection still running after {REFLECTION_TIMEOUT} s",
                        file=sys.stderr,
                    )
        except TimeoutError:
            out.error = "timeout"
        out.error = out.error or next(
            (p["error"] for n, p in events if n == "chat:finished" and p["error"]), None
        )
        out.messages = [p for n, p in events if n == "message"]
        out.prompt = next(
            (render_prompt(p) for n, p in events if n == "agent:first-prompt"), ""
        )
        out.max_prompt_chars = max(
            (p["chars"] for n, p in events if n == "agent:prompt-size"), default=0
        )
        out.incomplete = [p for n, p in events if n == "agent:incomplete"]
        out.reply = next(
            (m["content"] for m in reversed(out.messages)
             if m["role"] == "assistant" and m["content"]),
            "",
        )  # fmt: skip
        out.files = {
            f.relative_to(root).as_posix(): f.read_text(
                encoding="utf-8", errors="replace"
            )
            for f in sorted(root.rglob("*"))
            if f.suffix in (".md", ".ics") and f.is_file()
        }
        if persona_id == "personal-assistant":
            out.items = docket.load_docket(root)
            out.drafts = _drafts(root, ("docket/drafts", "docket/plans"))
        else:
            out.sources = ledger.load_ledger(root)
            out.drafts = _drafts(root, ("research/drafts",))
    except Exception as e:  # noqa: BLE001 - a broken case is a row in the report
        out.error = f"setup: {e}"
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(root, ignore_errors=True)
    return out


# --- checks of what the user gets ----------------------------------------------------

Check = tuple[bool, str]


# The workflow's reply and the eval count words the same way: no headings, keys or References.
words = workflow.body_words


def deliverable_file(case: Case, o: Outcome) -> str | None:
    """The workspace path of the deliverable, the last match of the case's glob."""
    if case.deliverable is None:
        return None
    hits = [p for p in o.files if Path(p).match(case.deliverable.glob)]
    return hits[-1] if hits else None


def check_complete(o: Outcome) -> Check:
    if o.incomplete:
        inc = o.incomplete[-1]
        return False, f"{inc.get('reason')} Open: {len(inc.get('open_items') or [])}"
    return True, "no open items"


def check_deliverable(case: Case, o: Outcome) -> Check:
    if case.deliverable is None:
        return True, "no deliverable named"
    path = deliverable_file(case, o)
    if path is None:
        return False, f"no file matches {case.deliverable.glob}"
    text = o.files[path]
    if todo := [ln for ln in text.splitlines() if ln.strip().startswith("TODO")]:
        return False, f"{path}: {len(todo)} TODO lines left"
    if case.deliverable.words:
        lo, hi = case.deliverable.words
        n = words(text)
        if not lo <= n <= hi:
            return False, f"{path}: {n} words, want {lo} to {hi}"
        return True, f"{path}: {n} words"
    return True, path


def cited_keys(o: Outcome) -> set[str]:
    return {k for d in o.drafts for k in re.findall(r"\[([SD]\d+)\]", d)}


def check_sources(case: Case, o: Outcome) -> Check:
    n = len(cited_keys(o))
    return n >= case.min_sources, f"{n} cited, {case.min_sources} needed"


def last_result(o: Outcome, tool: str) -> str | None:
    """PASS or FAIL from the last call of a check tool in the turn; None when it never ran."""
    for m in reversed(o.messages):
        if m["role"] == "tool" and m["tool_name"] == tool:
            return "PASS" if m["content"].startswith("PASS") else "FAIL"
    return None


def check_honest_report(case: Case, o: Outcome) -> Check:
    """The final reply names the deliverable and does not hide a failed check."""
    path = deliverable_file(case, o)
    if path and path not in o.reply and Path(path).name not in o.reply:
        return False, f"the reply does not name {path}"
    if last_result(o, "check_citations") == "FAIL" and "fail" not in o.reply.lower():
        return False, "check_citations failed, the reply does not say so"
    return True, "the reply names the file and the check results"


def check_event(case: Case, o: Outcome) -> Check:
    if case.event is None:
        return True, "no event asked for"
    e = case.event
    for path, text in o.files.items():
        if (
            path.endswith(".ics")
            and f"DTSTART:{e.start}" in text
            and f"DTEND:{e.end}" in text
        ):
            if f"LOCATION:{e.location}" in text:
                return True, path
            return False, f"{path}: location is not {e.location}"
    return False, f"no .ics with start {e.start} and end {e.end}"


def metrics(case: Case, o: Outcome) -> dict[str, Any]:
    """The scores plus what the run itself reports, for promptfoo's assertions."""
    checks = {
        "complete": check_complete(o),
        "deliverable": check_deliverable(case, o),
        "sources_cited": check_sources(case, o),
        "honest_report": check_honest_report(case, o),
        "event": check_event(case, o),
    }
    return {
        **score(case, o),
        "checks": {k: {"pass": ok, "reason": why} for k, (ok, why) in checks.items()},
        "steps_used": sum(m["role"] == "assistant" for m in o.messages),
        "draft_produced": bool(o.drafts),
        "max_prompt_chars": o.max_prompt_chars,
        "error": o.error,
        "persona_updated_at": o.persona_updated_at,
    }


def write_transcript(folder: Path, case_id: str, o: Outcome) -> None:
    """`<case>.json` (the stored rows) and `<case>.prompt.md` (the first prompt)."""
    folder.mkdir(parents=True, exist_ok=True)
    name = sanitize(case_id)
    (folder / f"{name}.json").write_text(
        json.dumps(o.messages, indent=2, ensure_ascii=False)
    )
    (folder / f"{name}.prompt.md").write_text(o.prompt)
