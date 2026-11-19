"""Workflow turn (prototype): code owns the plan, the files and the order; the model fills blanks.

The writing skill's skeleton is the plan. Its File line gives the path, and each `TODO` line is a
blank, with its own instruction. The model is asked for little:

1. which writing skill fits the request, and a title, a slug and 3 to 5 research questions;
2. per page that code found and read for a question, the facts on it that answer the question;
3. per blank, the text that replaces it;
4. one cleanup of the draft, kept only if every heading and citation key survives.

Code searches, fetches, registers the sources and writes the notes, the references, the file, TASK.md and the final reply. The model never edits a
file, so it never has to know what a file says now.
"""

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_ai import (
    Agent,
    ModelRetry,
    NativeOutput,
    RunContext,
    ToolFailed,
    UsageLimitExceeded,
)
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, TextPart

from thea_agent.approvals import unified_diff
from thea_agent.deps import TurnDeps
from thea_agent.tools import ledger, notes, research

WORKFLOW_PERSONAS = ("research-assistant",)
SEARCH_HITS = 6  # search results per question, read in order
READS = 2  # sources with facts per question
PAGE_CHARS = 12000  # text of one page given to the model
MIN_PAGE_CHARS = 500  # less is a bot wall or an empty page
MAX_QUESTIONS = 5
WRITE_RETRIES = 2

# For a request no writing skill fits.
FALLBACK = """File: `research/drafts/<slug>-report.md`. Length: 400 to 800 words.
```markdown
# <Title>

## Summary
TODO summary: 100 to 200 words. The answer to the request, with keys.

## Findings
TODO findings: 300 to 600 words. Each fact has a key.

## References
TODO references
```"""

PICK = """Pick the writing skill that fits the user's request. Reply with its name only, or `none`.
Skills:
{skills}"""

PLAN = """Plan the research for the user's request. Give:
- title: the title of the document.
- slug: 2 to 4 lowercase words joined by `-`.
- questions: 3 to 5 sub-questions that together answer the request. Each has its own answer, and a search query: 3 to 8 keywords that name the subject, like `Reflexion Shinn 2023 limitations`.
- min_words, max_words: the length of the whole document. Use the length the request asks for. Else use this rule: {rule}"""

FACTS = """List the facts in this source that help answer the question: {question}
Each fact is one sentence in your own words, with where it is in the source, like `Heat pumps keep 70% of capacity at -15 C (Table 2).`
Give 3 to 8 facts. A fact that answers part of the question counts. Give an empty list only if the source is not about the subject of the question."""
FACTS_TOKENS = 1024  # 8 facts fit; a reply that loops on whitespace stops here


class Facts(BaseModel):
    facts: list[str]


WRITE = """You write one part of a document. Reply with that part's text only: no heading, no notes about your work.
Use only facts from the notes. Put the key of each fact after it, like `... in 2024 [S3].` Use only keys from the sources list.
Write in ASD-STE100 Simplified Technical English."""

CLEANUP = """You clean up a draft. Keep every heading line, every fact and every key like [S3], in the same section.
Remove repeated sentences, smooth the joins between sentences, fix grammar. Do not add facts. Reply with the whole draft only."""

_REFS = ("todo references", "todo sources")


class Question(BaseModel):
    question: str
    query: str


class Plan(BaseModel):
    title: str
    slug: str
    questions: list[Question]
    min_words: int
    max_words: int


@dataclass
class Blank:
    line: int  # index in the skeleton
    heading: str  # the nearest heading above, or "" before the first
    todo: str  # the TODO line, the instruction for this blank


@dataclass
class Skeleton:
    path: str  # with <slug>
    lines: list[str]
    blanks: list[Blank]
    length: tuple[int, int] | None = None  # the length the section ranges are sized for
    rule: str = ""  # the skill's Length line, for the planner


def parse_skeleton(body: str) -> Skeleton | None:
    """The File line and the first markdown block of a writing skill; None when it has neither."""
    path = re.search(r"File: `([^`]+)`", body)
    block = re.search(r"```markdown\n(.*?)```", body, re.DOTALL)
    if not path or not block:
        return None
    lines = block[1].rstrip("\n").splitlines()
    heading, blanks = "", []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("#"):
            heading = s.lstrip("#").strip()
        elif s.startswith("TODO") and not s.lower().startswith(_REFS):
            blanks.append(Blank(i, heading, s.removeprefix("TODO").strip()))
    rule = re.search(r"Length: ([^\n]*)", body)
    length = word_range(rule[1]) if rule else None
    return Skeleton(path[1], lines, blanks, length, rule[1] if rule else "")


def uses_workflow(req, enabled: bool) -> bool:
    return enabled and req.persona is not None and req.persona.id in WORKFLOW_PERSONAS


def load_skills(req) -> dict[str, tuple[str, Skeleton]]:
    """name -> (description, skeleton) of the turn's writing skills, `<dir>/<name>/SKILL.md`."""
    out: dict[str, tuple[str, Skeleton]] = {}
    for d in req.skill_dirs:
        for name in req.skills:
            f = Path(d) / name / "SKILL.md"
            if name in out or not f.is_file():
                continue
            text = f.read_text(encoding="utf-8")
            front, _, body = text.removeprefix("---\n").partition("\n---\n")
            desc = next(
                (
                    ln.split(":", 1)[1].strip()
                    for ln in front.splitlines()
                    if ln.startswith("description:")
                ),
                "",
            )
            if sk := parse_skeleton(body):
                out[name] = (desc, sk)
    return out


def skeleton_path(template: str, slug: str) -> str:
    """The File line with the slug in, without doubling the suffix after <slug>:
    `sqlite-wal-report` in `<slug>-report.md` is `sqlite-wal-report.md`."""
    after = (
        template.split("<slug>", 1)[1].removesuffix(".md")
        if "<slug>" in template
        else ""
    )
    if after and slug.endswith(after):
        slug = slug.removesuffix(after) or slug
    return template.replace("<slug>", slug)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "draft"


def check_plan(plan: Plan) -> Plan:
    questions = [
        Question(
            question=q.question.strip(), query=q.query.strip() or q.question.strip()
        )
        for q in plan.questions
        if q.question.strip()
    ]
    if not questions:
        raise ModelRetry("Give 3 to 5 sub-questions.")
    if not 0 < plan.min_words <= plan.max_words:
        raise ModelRetry(
            "min_words and max_words must be positive, min_words at most max_words."
        )
    return plan.model_copy(
        update={"slug": slugify(plan.slug), "questions": questions[:MAX_QUESTIONS]}
    )


def scale_todo(todo: str, factor: float) -> str:
    """The TODO line with every `A to B words` scaled, to the nearest 10."""

    def one(m: re.Match) -> str:
        lo, hi = (max(10, round(int(g) * factor / 10) * 10) for g in (m[1], m[2]))
        return f"{lo} to {hi} words"

    return re.sub(r"(\d+) to (\d+) words", one, todo) if factor != 1 else todo


def length_factor(sk: "Skeleton", plan: "Plan") -> float:
    """How much longer or shorter than the skeleton's sizing the user asked for."""
    if not sk.length:
        return 1.0
    return (plan.min_words + plan.max_words) / sum(sk.length)


def word_range(todo: str) -> tuple[int, int] | None:
    """The words a TODO line asks for: `150 to 250 words`, or `3 bullets, 40 to 60 words each`
    as 120 to 180. None for other units, like `4 to 6 sentences`."""
    if m := re.search(r"(\d+) \w+, (\d+) to (\d+) words each", todo):
        n = int(m[1])
        return n * int(m[2]), n * int(m[3])
    m = re.search(r"(\d+) to (\d+) words(?! each)", todo)
    return (int(m[1]), int(m[2])) if m else None


def words(text: str) -> int:
    return len(re.findall(r"\b\w[\w'-]*\b", re.sub(r"\[S\d+\]", "", text)))


def keys(text: str) -> set[str]:
    return set(re.findall(r"\[S\d+\]", text))


def part_text(text: str, heading: str) -> str:
    """The model's text for a blank: without a repeated heading line or surrounding blank lines."""
    lines = text.strip().splitlines()
    if lines and heading and lines[0].lstrip("#").strip().lower() == heading.lower():
        lines = lines[1:]
    return "\n".join(lines).strip()


def fill(sk: Skeleton, title: str, filled: dict[int, str]) -> str:
    """The skeleton with its title and each filled blank; an unfilled blank and the references
    placeholder are left out, so the draft never holds a TODO line."""
    out = []
    for i, ln in enumerate(sk.lines):
        s = ln.strip()
        if s.startswith("# ") and "<" in s:
            out.append(f"# {title}")
        elif s.startswith("TODO"):
            if filled.get(i):
                out.append(filled[i])
        else:
            out.append(ln)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def references(draft: str, sources: list[ledger.Source]) -> str:
    """One line per cited key, in key order, from the ledger."""
    by_key = {f"[{s.key}]": s for s in sources}
    cited = sorted(keys(draft) & by_key.keys(), key=lambda k: int(k[2:-1]))
    return "\n".join(
        f"- {k} {', '.join(by_key[k].authors) or 'Unknown author'} "
        f"({by_key[k].year or 'n.d.'}). {by_key[k].title}. {by_key[k].url}"
        for k in cited
    )


def with_references(draft: str, refs: str) -> str:
    if not refs:
        return draft
    if re.search(r"^## (References|Sources)\s*$", draft, re.MULTILINE):
        return re.sub(
            r"^(## (?:References|Sources))\s*$",
            lambda m: f"{m[1]}\n\n{refs}",
            draft,
            count=1,
            flags=re.MULTILINE,
        )
    return draft.rstrip() + f"\n\n## References\n\n{refs}\n"


def headings(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.startswith("#")]


def body_words(text: str) -> int:
    """Words a reader reads, as the eval counts them: no headings, no References."""
    body = re.split(
        r"^## (?:References|Sources)\s*$", text, maxsplit=1, flags=re.MULTILINE
    )[0]
    return words(
        "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith("#"))
    )


def clean_is_safe(before: str, after: str, min_words: int = 0) -> bool:
    """A cleanup may smooth text, but must keep every heading and key, most of the words, and
    the length the plan asked for if the draft had it."""
    floor = max(0.8 * body_words(before), min(min_words, body_words(before)))
    return (
        keys(after) == keys(before)
        and headings(after) == headings(before)
        and body_words(after) >= floor
    )


def task_md(request: str, steps: list[str], done: dict[int, str]) -> str:
    """TASK.md as a view of the steps: `[x]` done, `[!]` failed with its reason, `[ ]` to do."""
    first = request.strip().splitlines()[0] if request.strip() else ""
    lines = ["# Task", first, "## Done when"]
    for i, s in enumerate(steps):
        if i not in done:
            lines.append(f"- [ ] {s}")
        elif done[i]:
            lines.append(f"- [!] {s}: {done[i]}")
        else:
            lines.append(f"- [x] {s}")
    return "\n".join(lines) + "\n"


class Workflow:
    """One workflow turn. `run_agent(agent, prompt, limit)` runs an agent with the turn's events,
    rows, deps and token, and returns its output."""

    def __init__(self, req, deps: TurnDeps, model, settings, capabilities, run_agent):
        self.req, self.deps, self.model, self.settings = req, deps, model, settings
        self.capabilities, self.run_agent = capabilities, run_agent

    def agent(
        self, instructions: str, output_type: Any = str, max_tokens: int = 0, **kw
    ) -> Agent:
        settings = {
            **(self.settings or {}),
            **({"max_tokens": max_tokens} if max_tokens else {}),
        }
        return Agent(
            self.model,
            deps_type=TurnDeps,
            instructions=instructions,
            model_settings=settings or None,
            output_type=output_type,
            capabilities=[*kw.pop("capabilities", []), *self.capabilities],
            retries={"output": WRITE_RETRIES},
            **kw,
        )

    def write_own(self, rel: str, text: str) -> None:
        """TASK.md is the plan's view, kept by code: no approval, like the app's own state."""
        path = self.deps.resolve(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    async def skeleton(self, request: str) -> Skeleton:
        skills = load_skills(self.req)
        if not skills:
            return parse_skeleton(FALLBACK)
        listing = "\n".join(f"- {n}: {d}" for n, (d, _) in skills.items())
        name = (
            (await self.run_agent(self.agent(PICK.format(skills=listing)), request, 2))
            .strip()
            .strip("`")
        )
        return skills[name][1] if name in skills else parse_skeleton(FALLBACK)

    async def plan(self, request: str, sk: Skeleton) -> Plan:
        planner = self.agent(
            PLAN.format(rule=sk.rule or "about 1000 words"), NativeOutput(Plan)
        )
        planner.output_validator(check_plan)
        return await self.run_agent(planner, request, 4)

    async def research(self, question: str, query: str) -> str:
        """Code searches and reads; the model only lists the facts on each page. Code registers
        each source it took facts from and writes the notes with its key. Returns "" when done,
        else why not."""
        text = question.split(" ", 1)[1]
        try:
            hits = await research.search_one(
                str(self.deps.settings.get("searxng_url") or ""), query, SEARCH_HITS
            )
        except ToolFailed as e:
            return str(e)
        root, read = self.deps.resolve("."), 0
        for hit in hits:
            if read == READS:
                break
            try:
                page = await research.fetch(hit.url, PAGE_CHARS)
            except ToolFailed:
                continue  # the next hit
            if len(page.text) < MIN_PAGE_CHARS:
                continue  # a bot wall or an empty page: nothing to read
            lister = self.agent(
                FACTS.format(question=text), NativeOutput(Facts), FACTS_TOKENS
            )
            title = page.title or hit.title
            try:
                got = await self.run_agent(
                    lister, f"Source: {title}\n{page.url}\n\n{page.text}", 3
                )
            except (UnexpectedModelBehavior, UsageLimitExceeded):
                continue  # no valid list from this page after the retries: the next hit
            facts = [" ".join(f.split()) for f in got.facts if f.strip()]
            if not facts:
                continue
            src = ledger.Source(
                key="", kind="web", title=title, url=hit.url,
                added_at=datetime.now(UTC).isoformat(),
            )  # fmt: skip
            if not await self.ask("add_source", f"Add source: {title}", hit.url):
                continue
            src, _ = ledger.add_resolved(root, src)
            md = self.deps.resolve(notes.NOTES_PATH)
            old = md.read_text(encoding="utf-8") if md.exists() else ""
            new = old
            for f in facts:
                new, _ = notes.insert_note(new, question, f"- [{src.key}] {f}")
            diff = unified_diff(old, new, notes.NOTES_PATH)
            if await self.ask(
                "add_note", f"Add notes from [{src.key}]", notes.NOTES_PATH, diff
            ):
                md.parent.mkdir(parents=True, exist_ok=True)
                md.write_text(new, encoding="utf-8")
                read += 1
        return "" if read else "no source with facts on it"

    async def ask(
        self, tool: str, summary: str, details: str, diff: str | None = None
    ) -> bool:
        a, d = self.deps.approvals, self.deps
        return a is None or await a.ask(
            d.chat_id, d.project_id, "write", tool, summary, details, diff
        )

    async def write(self, request: str, title: str, blank: Blank, draft: str) -> str:
        sources = ledger.load_ledger(self.deps.resolve("."))
        known = {f"[{s.key}]" for s in sources}
        notes_md = self.deps.resolve(notes.NOTES_PATH)
        facts = (
            notes_md.read_text(encoding="utf-8") if notes_md.exists() else "(no notes)"
        )
        writer = self.agent(WRITE)

        span = word_range(blank.todo)

        where = f"the `{blank.heading}` section" if blank.heading else "this part"

        @writer.output_validator
        def _check_part(ctx: RunContext, text: str) -> str:
            body = part_text(text, blank.heading)
            # The headings are the skeleton's: a heading in a part is the model writing other parts.
            if m := re.search(r"^#{1,6} ", body, flags=re.MULTILINE):
                if ctx.retry < WRITE_RETRIES:
                    raise ModelRetry(
                        f"Reply with the text of {where} only: no headings, no other sections."
                    )
                body = body[
                    : m.start()
                ].strip()  # the last try: keep this part, drop the rest
            if not body:
                raise ModelRetry("Reply with the text.")
            if bad := sorted(keys(body) - known):
                raise ModelRetry(
                    f"{', '.join(bad)} are not sources. Use only: {', '.join(sorted(known)) or 'none'}."
                )
            # The last try stands even off the range: a short part beats a missing one.
            if (
                span
                and ctx.retry < WRITE_RETRIES
                and not span[0] <= words(body) <= span[1]
            ):
                raise ModelRetry(
                    f"That is {words(body)} words. Write {span[0]} to {span[1]} words, from the notes."
                )
            return body

        # Aim at the middle: the minimum is the check, so a part that lands low still passes.
        aim = f" Aim for about {sum(span) // 2} words." if span else ""
        prompt = (
            f"Request: {request}\nDocument: {title}\n\n"
            f"Write {where}: {blank.todo}{aim}\n\n"
            f"Notes:\n{facts}\n\nSources:\n{ledger.format_ledger(sources) or '(none)'}\n\n"
            f"Draft so far:\n{draft}"
        )
        return await self.run_agent(writer, prompt, 4)

    async def run(self, request: str) -> tuple[str, bool]:
        """Returns the final reply and whether every step was done."""
        sk = await self.skeleton(request)
        plan = await self.plan(request, sk)
        factor = length_factor(sk, plan)
        sk = replace(
            sk, blanks=[replace(b, todo=scale_todo(b.todo, factor)) for b in sk.blanks]
        )
        questions = [f"Q{n} {q.question}" for n, q in enumerate(plan.questions, 1)]
        steps = [f"Research: {q}" for q in questions] + [
            f"Write: {b.heading or b.todo.split(':')[0]}" for b in sk.blanks
        ]
        done: dict[int, str] = {}
        self.write_own("TASK.md", task_md(request, steps, done))
        filled: dict[int, str] = {}
        for i, step in enumerate(steps):
            if i == len(questions) and all(done.values()):
                # No facts at all: a draft now would be the model's memory, without sources.
                why = "; ".join(f"{steps[j]}: {done[j]}" for j in range(i))
                return f"Not written: research found no source with facts. {why}", False
            try:
                if i < len(questions):
                    done[i] = await self.research(questions[i], plan.questions[i].query)
                else:
                    b = sk.blanks[i - len(questions)]
                    filled[b.line] = await self.write(
                        request, plan.title, b, fill(sk, plan.title, filled)
                    )
                    done[i] = ""
            except UnexpectedModelBehavior as e:
                done[i] = f"the model failed ({e.message[:80]})"
            self.write_own("TASK.md", task_md(request, steps, done))

        draft = fill(sk, plan.title, filled)
        try:
            clean = (await self.run_agent(self.agent(CLEANUP), draft, 2)).strip() + "\n"
            if clean_is_safe(draft, clean, plan.min_words):
                draft = clean
        except UnexpectedModelBehavior:
            pass  # the uncleaned draft stands
        sources = ledger.load_ledger(self.deps.resolve("."))
        text = with_references(draft, references(draft, sources))
        report = ledger.check_citations_text(text, sources)
        self.deps.signals.citations = (
            report.passed,
            ledger.format_citation_report(report),
        )

        path = skeleton_path(sk.path, plan.slug)
        target = self.deps.resolve(path)
        old = target.read_text(encoding="utf-8") if target.exists() else ""
        written = await self.ask(
            "write_file", f"Write file `{path}`", path, unified_diff(old, text, path)
        )
        if written:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        failed = [f"{steps[i]}: {why}" for i, why in done.items() if why]
        lines = [
            f"Wrote {path} ({body_words(text)} words)."
            if written
            else f"Not written: you rejected {path}.",
            f"check_citations: {'PASS' if report.passed else 'FAIL'}, {len(report.cited)} sources cited.",
        ]
        if failed:
            lines.append("Not done: " + "; ".join(failed) + ".")
        return "\n".join(lines), written and not failed


def reply_message(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(text)])
