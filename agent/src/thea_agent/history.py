"""Stored message rows <-> pydantic-ai messages.

A row's `model_message_json` holds a JSON list of messages (`ModelMessagesTypeAdapter`): the
message behind the row, preceded by any messages that have no UI row of their own (retry
feedback, the wrap-up prompt, a round brief). A request with several tool returns gives one row
per return; the JSON rides on the first, so replaying the JSON rows rebuilds the history exactly.
"""

import json
import sys

from pydantic import ValidationError
from pydantic_ai import ModelMessagesTypeAdapter
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
    repair_messages,
)

from thea_agent.protocol import StoredRow


def tool_output(part: ToolReturnPart) -> str:
    return part.model_response_str(wrap_if_error=False)


def _row(role: str, content: str, **kw) -> dict:
    return {
        "role": role,
        "content": content,
        "tool_calls_json": kw.get("tool_calls_json"),
        "tool_call_id": kw.get("tool_call_id"),
        "tool_name": kw.get("tool_name"),
    }


def ui_rows(msg: ModelMessage) -> list[dict]:
    """The rows the UI shows for one message; empty for one it does not show."""
    if isinstance(msg, ModelResponse):
        text = "".join(p.content for p in msg.parts if isinstance(p, TextPart))
        calls = [p for p in msg.parts if isinstance(p, ToolCallPart)]
        if not text and not calls:
            return []
        tc = [
            {"id": c.tool_call_id, "name": c.tool_name, "arguments": c.args_as_dict()}
            for c in calls
        ]
        return [_row("assistant", text, tool_calls_json=json.dumps(tc) if tc else None)]
    return [
        _row("tool", tool_output(p), tool_call_id=p.tool_call_id, tool_name=p.tool_name)
        for p in msg.parts
        if isinstance(p, ToolReturnPart)
    ]


def message_events(chat_id: str, group: list[ModelMessage]) -> list[dict]:
    """`message` payloads for the last message of `group`, carrying the whole group as JSON.
    A group with no UI row at all (a turn cut off after retry feedback) is one `system` row."""
    rows = ui_rows(group[-1]) or [_row("system", "")]
    data = ModelMessagesTypeAdapter.dump_json(group).decode()
    return [
        {"chat_id": chat_id, **r, "model_message_json": data if i == 0 else None}
        for i, r in enumerate(rows)
    ]


def _returned_ids(messages: list[ModelMessage]) -> set[str]:
    return {
        p.tool_call_id
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart)
    }


def to_model_messages(rows: list[StoredRow]) -> list[ModelMessage]:
    """History for the next run. Rows from before the migration, or whose JSON no longer
    parses, replay as plain text."""
    out: list[ModelMessage] = []
    for r in rows:
        if r.model_message_json:
            try:
                out += ModelMessagesTypeAdapter.validate_json(r.model_message_json)
                continue
            except ValidationError as e:  # schema drift after an upgrade: as text
                print(
                    f"stored {r.role} row replayed as text: {e.error_count()} errors",
                    file=sys.stderr,
                )
        if r.role == "user":
            out.append(ModelRequest(parts=[UserPromptPart(r.content)]))
        elif r.role == "assistant" and r.content:
            out.append(ModelResponse(parts=[TextPart(r.content)]))
        elif r.role == "tool" and r.tool_call_id not in _returned_ids(out):
            # Not one of the extra rows of a JSON request: an old row, as text.
            text = (
                f'<tool_result name="{r.tool_name or ""}">\n{r.content}\n</tool_result>'
            )
            out.append(ModelRequest(parts=[UserPromptPart(text)]))
    return repair_messages(out)
