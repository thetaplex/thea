"""Reflexion: one lesson from a real signal (ported from `reflection.rs`).

A signal is a dict with `kind`: `citations` (`pass`, `detail`), `rating` (`up`,
`comment`) or `repeated_errors` (`tool`, `error`, `count`).
"""

import sys
from collections.abc import Sequence

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart
from pydantic_ai.models import Model

from thea_agent.history import tool_output
from thea_agent.protocol import StoredRow

SYSTEM = "You improve a research assistant. Read the trajectory and the signal. Write exactly one lesson for next time, at most two sentences, in the form 'When X, do Y.' Do not repeat an existing lesson. Output only the lesson."

_LABELS = {"citations": "check_citations"}


def label(signal: dict) -> str:
    match signal["kind"]:
        case "rating":
            return "rating_up" if signal["up"] else "rating_down"
        case "repeated_errors":
            return "repeated_errors"
        case kind:
            return _LABELS[kind]


def describe(signal: dict) -> str:
    match signal["kind"]:
        case "rating":
            comment = f" Comment: {signal['comment']}" if signal.get("comment") else ""
            return f"The user rated the answer thumbs-{'up' if signal['up'] else 'down'}.{comment}"
        case "repeated_errors":
            return f"Tool {signal['tool']} failed {signal['count']} times with: {signal['error']}"
        case _:
            verdict = "passed" if signal["pass"] else "failed"
            return f"{label(signal)} {verdict}:\n{signal['detail']}"


def detect_repeated_errors(messages: Sequence[ModelMessage]) -> dict | None:
    """Same tool and the same error (first 60 chars, prefix-compatible), 3+ times."""
    errs = [
        (p.tool_name, tool_output(p)[:60])
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart) and p.outcome in ("failed", "retried")
    ]
    for t, e in errs:
        count = sum(
            t2 == t and (e2.startswith(e) or e.startswith(e2)) for t2, e2 in errs
        )
        if count >= 3:
            return {"kind": "repeated_errors", "tool": t, "error": e, "count": count}
    return None


def summarize_trajectory(rows: Sequence[StoredRow]) -> str:
    cap = 4000
    out = ""
    if u := next((r for r in rows if r.role == "user"), None):
        out += f"Task:\n{u.content[:500]}\n\n"
    if a := next((r for r in reversed(rows) if r.role == "assistant"), None):
        out += f"Final answer:\n{a.content[:1500]}\n\n"
    out = out[:cap] + "Tool calls:\n"
    lines = [
        f"{r.tool_name or 'tool'} → {r.content.replace(chr(10), ' ')[:80]}\n"
        for r in rows
        if r.role == "tool"
    ]
    # Newest last; drop the oldest first when the budget runs out.
    used, keep = len(out), []
    for line in reversed(lines):
        used += len(line)
        if used > cap:
            break
        keep.append(line)
    return (out + "".join(reversed(keep)))[:cap]


def accept_lesson(raw: str) -> str | None:
    t = " ".join(raw.split())
    sentences = sum(
        bool(s.strip()) for s in t.replace("!", ".").replace("?", ".").split(".")
    )
    return t if t.startswith("When") and sentences <= 2 and len(t) <= 300 else None


async def reflect(
    model: Model, signal: dict, transcript: str, lessons: Sequence[str]
) -> str | None:
    """At most one lesson, or None when the model's reply is not lesson-shaped."""
    existing = "\n".join(f"{i}. {t}" for i, t in enumerate(lessons, 1))
    prompt = f"Trajectory:\n{transcript}\n\nSignal: {describe(signal)}\n\nExisting lessons:\n{existing}"
    result = await Agent(model, output_type=str, instructions=SYSTEM).run(prompt)
    return accept_lesson(result.output)


async def reflect_and_emit(
    emit, persona_id, model, signal, rows, lessons
) -> str | None:
    """One reflection; a failure is logged, never raised."""
    # ponytail: a reflection still running when the sidecar exits is lost, as with Rust's spawned task.
    try:
        transcript = summarize_trajectory(rows)
        text = await reflect(model, signal, transcript, lessons)
    except Exception as e:  # noqa: BLE001 - reflection never fails the turn
        print(f"reflection failed: {e!r}", file=sys.stderr)
        return None
    if text:
        emit(
            "lesson",
            {
                "persona_id": persona_id,
                "signal": label(signal),
                "text": text,
            },
        )
    return text
