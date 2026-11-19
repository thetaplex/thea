"""Docket: tool-managed task ledger (`docket/docket.json` + `docket/DOCKET.md`) and RFC 5545 export."""

import difflib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError
from pydantic_ai import ModelRetry, RunContext, ToolFailed, ToolReturn

from thea_agent import approvals
from thea_agent.deps import TurnDeps

DOCKET_JSON_REL = "docket/docket.json"
DOCKET_MD_REL = "docket/DOCKET.md"
READ_ONLY_PATHS = (DOCKET_JSON_REL,)

KINDS = ("task", "event", "decision", "note")
STATUSES = ("open", "done", "cancelled")


class DocketItem(BaseModel):
    key: str  # "[D1]"
    kind: str
    title: str
    status: str
    priority: int = 2
    due: str | None = None
    detail: str | None = None
    created_at: str


def load_docket(root: Path) -> list[DocketItem]:
    path = root / DOCKET_JSON_REL
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return []
        return [DocketItem.model_validate(i) for i in json.loads(raw)]
    except (ValueError, TypeError, ValidationError) as e:
        raise ToolFailed(f"{DOCKET_JSON_REL} is not valid JSON: {e}") from e
    except OSError as e:
        raise ToolFailed(f"Failed to read {DOCKET_JSON_REL}: {e}") from e


def save_docket(root: Path, items: list[DocketItem]) -> None:
    path = root / DOCKET_JSON_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps([i.model_dump() for i in items], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(path)
        (root / DOCKET_MD_REL).write_text(render_markdown(items), encoding="utf-8")
    except OSError as e:
        raise ToolFailed(f"Failed to write {DOCKET_JSON_REL}: {e}") from e


def _key_num(key: str) -> int | None:
    m = re.fullmatch(r"\[D(\d+)\]", key)
    return int(m[1]) if m else None


def next_key(items: list[DocketItem]) -> str:
    return f"[D{max((n for i in items if (n := _key_num(i.key))), default=0) + 1}]"


def normalize_key(raw: str) -> str:
    t = raw.strip().lstrip("[").rstrip("]").strip()
    if t[:1] in ("D", "d"):
        t = t[1:]
    return f"[D{t.strip()}]"


def sort_docket(items: list[DocketItem]) -> None:
    """Open first, then priority 3 to 1, then earliest due, then key."""
    rank = {"open": 0, "done": 1}
    items.sort(
        key=lambda i: (
            rank.get(i.status, 2),
            -i.priority,
            i.due or "9999-99-99",
            _key_num(i.key) if _key_num(i.key) is not None else 10**18,
        )
    )


def _line_tail(i: DocketItem) -> str:
    due = f" (due: {i.due})" if i.due else ""
    detail = f" — {i.detail}" if i.detail else ""
    return f"{i.title}{due}{detail}"


def format_docket(items: list[DocketItem]) -> str:
    return "\n".join(
        f"{i.key} [{i.kind} | {i.status} | p{i.priority}] {_line_tail(i)}"
        for i in items
    )


def render_markdown(items: list[DocketItem]) -> str:
    items = list(items)
    sort_docket(items)
    out = "# Docket\n\n"
    if not items:
        return out + "No items recorded.\n"
    for status, heading in zip(STATUSES, ("Open", "Done", "Cancelled"), strict=True):
        group = [i for i in items if i.status == status]
        if not group:
            continue
        out += f"## {heading}\n"
        for i in group:
            box = "x" if i.status == "done" else " "
            out += f"- [{box}] {i.key} ({i.kind}, p{i.priority}) {_line_tail(i)}\n"
        out += "\n"
    return out


def _diff(root: Path, items: list[DocketItem]) -> str:
    md = root / DOCKET_MD_REL
    old = md.read_text(encoding="utf-8") if md.exists() else ""
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            render_markdown(items).splitlines(keepends=True),
            DOCKET_MD_REL,
            DOCKET_MD_REL,
        )
    )


def _clean(s: str | None) -> str | None:
    return (s or "").strip() or None


def _clamp_priority(p: int) -> int:
    return min(3, max(1, p))


async def add_docket_item(
    ctx: RunContext[TurnDeps],
    title: str,
    kind: str = "task",
    priority: int = 2,
    due: str | None = None,
    detail: str | None = None,
) -> str:
    """Add a task, event, decision, or note to the project Docket (docket/docket.json and docket/DOCKET.md). Returns a key like [D1].

    Args:
        title: Short summary of the item.
        kind: Item type: 'task', 'event', 'decision', or 'note'. Defaults to 'task'.
        priority: Priority from 1 (normal) to 3 (urgent). Defaults to 2.
        due: Optional date (YYYY-MM-DD) or datetime (YYYY-MM-DDTHH:MM).
        detail: Optional context, next action, or decision rationale.
    """
    title = _clean(title)
    if not title:
        raise ModelRetry("add_docket_item requires a non-empty `title`")
    kind = (kind or "task").strip().lower()
    if kind not in KINDS:
        raise ModelRetry(
            f"Invalid docket kind '{kind}'. Expected 'task', 'event', 'decision', or 'note'."
        )
    detail, due = _clean(detail), _clean(due)
    root = ctx.deps.resolve(".")
    items = load_docket(root)
    dup = next(
        (
            i
            for i in items
            if i.kind == kind
            and i.title.lower() == title.lower()
            and i.status == "open"
        ),
        None,
    )
    item = dup or DocketItem(
        key=next_key(items),
        kind=kind,
        title=title,
        status="open",
        priority=_clamp_priority(priority),
        due=due,
        detail=detail,
        created_at=datetime.now(UTC).strftime("%Y-%m-%d"),
    )
    new_items = items if dup else [*items, item]
    await approvals.require(
        ctx,
        "write",
        f"Add Docket {kind} `{title}`",
        detail or title,
        _diff(root, new_items),
    )
    if not dup:
        save_docket(root, new_items)
    note = " (already on Docket)" if dup else ""
    return f"{item.key}{note}\n{format_docket([item])}"


async def update_docket_item(
    ctx: RunContext[TurnDeps],
    key: str,
    status: str | None = None,
    priority: int | None = None,
    due: str | None = None,
    detail: str | None = None,
    title: str | None = None,
) -> str:
    """Update the status ('open', 'done', 'cancelled'), priority, due date, or detail of an existing Docket item by key (for example [D1]).

    Args:
        key: Docket item key, for example '[D1]' or 'D1'.
        status: New status: 'open', 'done', or 'cancelled'.
        priority: New priority from 1 to 3.
        due: Updated date (YYYY-MM-DD) or datetime (YYYY-MM-DDTHH:MM).
        detail: Updated detail note.
        title: Updated title.
    """
    if not _clean(key):
        raise ModelRetry('update_docket_item requires `key` (for example "[D1]")')
    key = normalize_key(key)
    if status := _clean(status):
        status = status.lower()
        if status not in STATUSES:
            raise ModelRetry(
                f"Invalid docket status '{status}'. Expected 'open', 'done', or 'cancelled'."
            )
    root = ctx.deps.resolve(".")
    items = load_docket(root)
    item = next((i for i in items if i.key.lower() == key.lower()), None)
    if item is None:
        raise ToolFailed(f"Docket item {key} not found")
    changes = {
        "status": status,
        "priority": None if priority is None else _clamp_priority(priority),
        "due": _clean(due),
        "detail": _clean(detail),
        "title": _clean(title),
    }
    updated = item.model_copy(
        update={k: v for k, v in changes.items() if v is not None}
    )
    new_items = [updated if i is item else i for i in items]
    await approvals.require(
        ctx,
        "write",
        f"Update Docket item {key}",
        json.dumps({"key": key, **{k: v for k, v in changes.items() if v}}, indent=2),
        _diff(root, new_items),
    )
    save_docket(root, new_items)
    return format_docket([updated])


async def list_docket(
    ctx: RunContext[TurnDeps], status: str | None = None, kind: str | None = None
) -> str:
    """List items in the project Docket sorted by status, priority, and due date.

    Args:
        status: Optional filter: 'open', 'done', or 'cancelled'.
        kind: Optional filter: 'task', 'event', 'decision', or 'note'.
    """
    items = load_docket(ctx.deps.resolve("."))
    if st := _clean(status):
        items = [i for i in items if i.status.lower() == st.lower()]
    if k := _clean(kind):
        items = [i for i in items if i.kind.lower() == k.lower()]
    if not items:
        return "(no matching Docket items)"
    sort_docket(items)
    return format_docket(items)


# --- calendar export ---


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.strip().lower()).strip("-") or "event"


def format_ics_timestamp(raw: str) -> tuple[str, bool]:
    """`YYYY-MM-DD` or `YYYY-MM-DDTHH:MM[:SS]` to an RFC 5545 value; flag is True for date-only."""
    t = raw.strip()
    digits = "".join(c for c in t if c in "0123456789")
    if len(t) == 10 and len(digits) == 8:
        return digits, True
    if len(digits) == 12:
        return f"{digits[:8]}T{digits[8:]}00Z", False
    if len(digits) == 14:
        return f"{digits[:8]}T{digits[8:]}Z", False
    raise ModelRetry(
        f"Invalid date/time '{raw}'. Use 'YYYY-MM-DD' for an all-day event or 'YYYY-MM-DDTHH:MM' for a timed event."
    )


def _escape(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def build_ics(
    title: str,
    start: str,
    end: str | None = None,
    location: str | None = None,
    description: str | None = None,
) -> str:
    dtstart, start_date = format_ics_timestamp(start)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ThetaPlex//Thea Personal Assistant//EN",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{slugify(f'{title}-{start}')}@thea.thetaplex.app",
        f"DTSTAMP:{dtstart}",
        f"DTSTART;VALUE=DATE:{dtstart}" if start_date else f"DTSTART:{dtstart}",
    ]
    if end:
        dtend, end_date = format_ics_timestamp(end)
        lines.append(f"DTEND;VALUE=DATE:{dtend}" if end_date else f"DTEND:{dtend}")
    lines.append(f"SUMMARY:{_escape(title)}")
    if location:
        lines.append(f"LOCATION:{_escape(location)}")
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"


async def export_calendar(
    ctx: RunContext[TurnDeps],
    title: str,
    start: str,
    end: str | None = None,
    location: str | None = None,
    description: str | None = None,
    filename: str | None = None,
) -> ToolReturn:
    """Export a calendar event to an RFC 5545 .ics file under docket/calendar/ so it can be imported into Apple Calendar, Outlook, or Google Calendar.

    Args:
        title: Event summary/title.
        start: Start date (YYYY-MM-DD) or datetime (YYYY-MM-DDTHH:MM).
        end: Optional end date (YYYY-MM-DD) or datetime (YYYY-MM-DDTHH:MM).
        location: Optional location or meeting link.
        description: Optional event agenda or notes.
        filename: Optional .ics filename (defaults to slugified title).
    """
    title, start = _clean(title), _clean(start)
    if not title or not start:
        raise ModelRetry(
            'export_calendar requires `title` and `start` (for example "2026-11-20T14:00" or "2026-11-20")'
        )
    end, location, description = _clean(end), _clean(location), _clean(description)
    ics = build_ics(title, start, end, location, description)  # validates both dates
    name = f"{slugify((_clean(filename) or title).removesuffix('.ics'))}.ics"
    rel = f"docket/calendar/{name}"
    target = ctx.deps.resolve(rel)
    await approvals.require(
        ctx,
        "write",
        f"Export calendar event `{title}` to `{rel}`",
        f"Start: {start}",
        None,
    )
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(ics, encoding="utf-8", newline="")
    except OSError as e:
        raise ToolFailed(f"Failed to write {rel}: {e}") from e
    return ToolReturn(
        return_value=f"Wrote calendar event '{title}' to {rel}",
        metadata={"artifact_path": rel},
    )
