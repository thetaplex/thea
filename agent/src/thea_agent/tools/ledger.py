"""Source ledger: `research/sources.json` and the citation check against it."""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_ai import ModelRetry, RunContext, ToolFailed

from thea_agent import approvals
from thea_agent.deps import TurnDeps
from thea_agent.tools import research

LEDGER_PATH = "research/sources.json"
READ_ONLY_PATHS = (LEDGER_PATH,)


class Source(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str
    kind: str
    title: str
    authors: list[str] = []
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str
    summary: str | None = Field(default=None, alias="abstract")
    note: str | None = None
    relevance: int | None = (
        None  # 1 to 5 against the question in TASK.md; None = unscored
    )
    added_at: str


def sort_by_relevance(sources: list[Source]) -> None:
    """Highest relevance first, unscored last, then by key."""
    sources.sort(key=lambda s: (-(s.relevance or 0), s.key))


def load_ledger(root: Path) -> list[Source]:
    path = root / LEDGER_PATH
    if not path.exists():
        return []
    try:
        return [
            Source.model_validate(s)
            for s in json.loads(path.read_text(encoding="utf-8"))
        ]
    except (ValueError, TypeError, ValidationError) as e:
        raise ToolFailed(f"{LEDGER_PATH} is not valid JSON: {e}") from e
    except OSError as e:
        raise ToolFailed(f"Failed to read {LEDGER_PATH}: {e}") from e


def save_ledger(root: Path, sources: list[Source]) -> None:
    path = root / LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write-then-rename in the same dir, so a crash never leaves a half-written ledger.
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(
            json.dumps(
                [s.model_dump(by_alias=True) for s in sources],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        tmp.replace(path)
    except OSError as e:
        raise ToolFailed(f"Failed to write {LEDGER_PATH}: {e}") from e


def next_key(sources: list[Source]) -> str:
    nums = [int(s.key[1:]) for s in sources if re.fullmatch(r"S\d+", s.key)]
    return f"S{max(nums, default=0) + 1}"


def find_duplicate(sources: list[Source], doi: str | None, url: str) -> Source | None:
    for s in sources:
        if (url and s.url == url) or (doi and s.doi and doi.lower() == s.doi.lower()):
            return s
    return None


def format_ledger(sources: list[Source]) -> str:
    lines = []
    for s in sources:
        meta = ", ".join([*s.authors, *([str(s.year)] if s.year is not None else [])])
        rel = f" r={s.relevance}" if s.relevance is not None else ""
        lines.append(f"[{s.key}]{rel} {s.title}{f' ({meta})' if meta else ''} {s.url}")
    return "\n".join(lines)


def is_ledger_path(user_path: str) -> bool:
    p = user_path.replace("\\", "/")
    while p.startswith(("./", "/")):
        p = p[2:] if p.startswith("./") else p[1:]
    return p == LEDGER_PATH


@dataclass
class CitationReport:
    cited: list[str]
    missing: list[str]
    orphans: list[str]
    bad_references: list[str]

    @property
    def passed(self) -> bool:
        return not self.missing and not self.bad_references


_KEY = re.compile(r"\[S(\d+)\]")
_CODE = re.compile(r"`[^`\n]*`")
_REF_ITEM = re.compile(r"^\s*[-*]\s*\[S(\d+)\]")


def check_citations_text(draft: str, ledger: list[Source]) -> CitationReport:
    known = {s.key for s in ledger}
    cited: list[str] = []
    bad: list[str] = []

    def add(keys: list[str], k: str) -> None:
        if k not in keys:
            keys.append(k)

    in_fence = in_refs = False
    for line in draft.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("#"):
            in_refs = line.lstrip("#").strip().lower() == "references"
        text = _CODE.sub("", line)
        if in_refs and (m := _REF_ITEM.match(text)):
            if f"S{m[1]}" not in known:
                add(bad, f"S{m[1]}")
            continue
        for m in _KEY.finditer(text):
            add(cited, f"S{m[1]}")
    return CitationReport(
        cited=cited,
        missing=[k for k in cited if k not in known],
        orphans=[s.key for s in ledger if s.key not in cited],
        bad_references=bad,
    )


def format_citation_report(r: CitationReport) -> str:
    out = "PASS" if r.passed else "FAIL"
    for label, keys in [
        ("Cited", r.cited),
        ("Missing from ledger (not allowed)", r.missing),
        ("Bad references (not in ledger)", r.bad_references),
        ("Orphans (in ledger, never cited)", r.orphans),
    ]:
        if keys:
            out += f"\n{label}: {', '.join(keys)}"
    return out


@dataclass
class AddSourceArgs:
    kind: Literal["doi", "url", "arxiv_id"]
    value: str
    title: str | None
    relevance: int | None
    url: str | None = (
        None  # the page the id came from; registered when the id does not resolve
    )


def parse_add_source_args(
    doi: str | None = None,
    url: str | None = None,
    arxiv_id: str | None = None,
    title: str | None = None,
    relevance: int | None = None,
) -> AddSourceArgs:
    given = {
        k: v.strip()
        for k, v in (("doi", doi), ("url", url), ("arxiv_id", arxiv_id))
        if v and v.strip()
    }
    if not given:
        raise ModelRetry("provide a doi, url or arxiv_id")
    kind = next(k for k in ("doi", "arxiv_id", "url") if k in given)
    value = given[kind]
    return AddSourceArgs(
        url=given.get("url") if kind != "url" else None,
        kind=kind,  # type: ignore[arg-type]
        value=value,
        title=(title or "").strip() or None,
        relevance=None if relevance is None else min(5, max(1, relevance)),
    )


async def resolve_source(args: AddSourceArgs) -> Source:
    """Look the source up; the key is assigned by `add_resolved`."""
    if args.kind != "url":
        try:
            paper = await research.find_paper(
                research.parse_paper_query(
                    args.value if args.kind == "doi" else None,
                    None,
                    args.value if args.kind == "arxiv_id" else None,
                )
            )
        except (ToolFailed, ModelRetry):
            paper = None
        if paper is not None:
            return Source(
                key="",
                kind="paper",
                title=paper.title,
                authors=paper.authors,
                year=paper.year,
                venue=paper.venue,
                doi=paper.doi,
                url=paper.url,
                summary=paper.summary,
                relevance=args.relevance,
                added_at=datetime.now(UTC).isoformat(),
            )
        if not args.url:
            raise ToolFailed(f"Could not resolve {args.value}; not added")
        args = AddSourceArgs("url", args.url, args.title, args.relevance)
    now = datetime.now(UTC).isoformat()
    note = None
    if args.kind == "url":
        # A page that answers 4xx/5xx exists but blocks bots: register it from the
        # search title, marked unverified. No answer at all (DNS, timeout) is refused.
        try:
            title = (await research.fetch(args.value, 1500)).title or args.value
        except research.HttpStatusError as e:
            if not args.title:
                raise ToolFailed(
                    f"{args.value} answered HTTP {e.status} (blocks bots). Call add_source again "
                    "with the same url and the title from the search result to register it unverified"
                ) from e
            title = args.title
            note = f"not fetched (HTTP {e.status}); title from search"
        except ToolFailed as e:
            raise ToolFailed(f"Could not resolve {args.value}; not added") from e
        return Source(
            key="",
            kind="web",
            title=title,
            url=args.value,
            note=note,
            relevance=args.relevance,
            added_at=now,
        )


def add_resolved(root: Path, src: Source) -> tuple[Source, bool]:
    """Return the stored record and whether it was newly added."""
    ledger = load_ledger(root)
    if dup := find_duplicate(ledger, src.doi, src.url):
        return dup, False
    src = src.model_copy(update={"key": next_key(ledger)})
    save_ledger(root, [*ledger, src])
    return src, True


async def add_source(
    ctx: RunContext[TurnDeps],
    doi: str | None = None,
    url: str | None = None,
    arxiv_id: str | None = None,
    title: str | None = None,
    relevance: int | None = None,
) -> str:
    """Register a source you will cite. Returns its key like [S3]. Only keys from this tool may be cited.

    Args:
        doi: DOI of the source.
        url: URL of the source.
        arxiv_id: arXiv identifier of the source.
        title: Title from the search result. Needed when the page blocks bots.
        relevance: 1 to 5 against the question in TASK.md. 5 = a primary source that answers it directly.
    """
    args = parse_add_source_args(doi, url, arxiv_id, title, relevance)
    root = ctx.deps.resolve(".")
    # Skip the network when the ledger already has it.
    early = find_duplicate(
        load_ledger(root),
        args.value if args.kind == "doi" else None,
        args.value if args.kind == "url" else args.url or "",
    )
    if early:
        src, added = early, False
    else:
        resolved = await resolve_source(args)
        key = next_key(load_ledger(root))
        await approvals.require(
            ctx, "write", f"Add source {key}: {resolved.title}", resolved.url, None
        )
        src, added = add_resolved(root, resolved)
    return f"{'Added' if added else 'Already registered'} [{src.key}] {src.title}"


async def list_sources(ctx: RunContext[TurnDeps]) -> str:
    """List every registered source, most relevant first; use before reading and before writing."""
    sources = load_ledger(ctx.deps.resolve("."))
    sort_by_relevance(sources)
    return format_ledger(sources) or "No sources registered yet."


async def check_citations(ctx: RunContext[TurnDeps], path: str) -> str:
    """Verify every [S#] citation in a draft exists in the source ledger; use before finishing a draft.

    Args:
        path: Relative path to the draft.
    """
    file = ctx.deps.resolve(path)
    try:
        draft = file.read_text(encoding="utf-8")
    except OSError as e:
        raise ToolFailed(f"Failed to read {path}: {e}") from e
    report = check_citations_text(draft, load_ledger(ctx.deps.resolve(".")))
    text = format_citation_report(report)
    ctx.deps.signals.citations = (report.passed, text)
    return text
