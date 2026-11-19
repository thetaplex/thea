"""add_note: append one note under a heading of a Markdown notes file.

Adding a note is an append. With edit_file the model had to replace the heading with the
heading plus the note, and it nearly always sent only the note, deleting the heading."""

import re

from pydantic_ai import ModelRetry, RunContext, ToolFailed

from thea_agent import approvals
from thea_agent.deps import TurnDeps
from thea_agent.tools.ledger import READ_ONLY_PATHS, load_ledger

NOTES_PATH = "research/notes.md"


def _norm(heading: str) -> str:
    return " ".join(heading.strip().lstrip("#").split()).casefold()


def insert_note(markdown: str, heading: str, note: str) -> tuple[str, bool]:
    """`markdown` with `note` as the last line under `## heading`; True when the heading is new.

    The heading matches only when it is the same text, ignoring `#`, case and spacing."""
    lines = markdown.splitlines()
    want = _norm(heading)
    start = next(
        (i for i, ln in enumerate(lines) if ln.startswith("## ") and _norm(ln) == want),
        None,
    )
    if start is None:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ["", f"## {heading.strip().lstrip('#').strip()}", note]
        return "\n".join(lines).lstrip("\n") + "\n", True
    end = next(
        (i for i in range(start + 1, len(lines)) if re.match(r"#{1,2} ", lines[i])),
        len(lines),
    )
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    lines.insert(end, note)
    return "\n".join(lines) + "\n", False


async def add_note(
    ctx: RunContext[TurnDeps], heading: str, note: str, path: str = NOTES_PATH
) -> str:
    """Add one note as the last line under a heading. The heading is made if the file does not have it.

    Args:
        heading: The heading text, like `Q1 What does Reflexion propose?` or `Learnings`.
        note: One fact with its key, like `[S2] Reflexion reaches 91% pass@1 on HumanEval (Table 1)`.
        path: The Markdown file. Default research/notes.md.
    """
    heading, text = heading.strip(), " ".join(note.split())
    if not _norm(heading):
        raise ModelRetry("add_note needs a heading, like `Q1 <sub-question>`")
    if not text:
        raise ModelRetry(
            "add_note needs a note: one fact with its key, like `[S2] ...`"
        )
    if not path.endswith(".md") or path in READ_ONLY_PATHS:
        raise ToolFailed(f"add_note writes Markdown notes files only, not {path}")
    # A note's key must be a registered source: the drafts copy keys from the notes.
    known = {f"[{src.key}]" for src in load_ledger(ctx.deps.resolve("."))}
    if bad := sorted(set(re.findall(r"\[S\d+\]", text)) - known):
        raise ModelRetry(
            f"{', '.join(bad)} not registered. Register the source with add_source first, "
            f"or use a key it returned: {', '.join(sorted(known)) or 'none yet'}."
        )
    line = text if text.startswith("- ") else f"- {text}"
    target = ctx.deps.resolve(path)
    try:
        old = target.read_text(encoding="utf-8") if target.exists() else ""
    except (OSError, UnicodeDecodeError) as e:
        raise ToolFailed(f"Could not read {path}: {e}") from e
    new, made = insert_note(old, heading, line)
    await approvals.require(
        ctx,
        "write",
        f"Add a note to `{path}`",
        path,
        approvals.unified_diff(old, new, path),
    )
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new, encoding="utf-8")
    except OSError as e:
        raise ToolFailed(f"Could not write {path}: {e}") from e
    where = (
        f"the new heading `## {heading.lstrip('#').strip()}`" if made else "its heading"
    )
    return f"Added the note to {path} under {where}."
