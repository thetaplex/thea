"""Per-turn behaviour on top of the framework: TASK.md nudges, wrap-up, thought cap, tool errors."""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import httpx
from pydantic_ai import ModelRetry, RunContext, ToolFailed
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import ModelResponse, SystemPromptPart, ToolCallPart
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.tools import ToolDefinition

from thea_agent.deps import TurnDeps

TASK_FILE = "TASK.md"
MAX_NUDGES = 4
MAX_THOUGHTS = 5

WRAP_UP = "Step limit reached for this round. Do not call tools. In at most eight short lines: what is done, what is not, the paths of files you wrote, and what the next round should do first."

EMPTY_REPLY_NUDGE = "Your last reply was empty. Do the next step of the skill you loaded now. If the work is done, reply with the result."

NOT_STARTED_NUDGE = "TASK.md has no checklist for this request. Write it now with write_file (see How you work), then do the first item."

ASK_ITEM = "Ask the user"

ASKED = "Asked. Now reply with the questions and stop. The user answers in the next message."

THOUGHT_LIMIT = f"You used all {MAX_THOUGHTS} thinking steps for this round. Stop planning. Do the next open TASK.md item now."

EDIT_FILE_DOC = (
    "Change one part of a text file. old_text is the exact text to change, as a tool output"
    " shows it: a TODO line, a heading or a TASK.md item. It must occur once"
    " in the file. new_text replaces it. To change the whole file, use write_file."
)

EDIT_NEEDS_OLD_TEXT = (
    "edit_file needs old_text: the exact part of the file to change."
    " To change the whole file, use write_file with the full new content."
)


# --- TASK.md (ported from task.rs) -------------------------------------------


def open_items(markdown: str) -> list[str]:
    """Every line that, trimmed, starts with `- [ ]`."""
    return [
        ln.strip() for ln in markdown.splitlines() if ln.strip().startswith("- [ ]")
    ]


def nudge_for(root: Path | None) -> str | None:
    """The nudge to send when `<root>/TASK.md` has open items; None otherwise."""
    if root is None:
        return None
    try:
        md = (root / TASK_FILE).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    items = open_items(md)
    if not items:
        return None
    return (
        f"{TASK_FILE} still has open items:\n"
        + "\n".join(items)
        + "\nDo the next one now. Tick it with edit_file when its proof has run."
    )


def has_items(markdown: str) -> bool:
    """Whether the checklist has any item: open `- [ ]`, done `- [x]` or blocked `- [!]`."""
    return any(
        ln.strip().startswith(("- [ ]", "- [x]", "- [X]", "- [!]"))
        for ln in markdown.splitlines()
    )


def waiting_on_user(items: list[str]) -> bool:
    """The next open item is a question to the user: the turn ends, the next turn resumes."""
    return bool(items) and items[0].removeprefix("- [ ]").strip().startswith(ASK_ITEM)


def task_md(root: Path | None) -> str:
    try:
        return (root / TASK_FILE).read_text(encoding="utf-8") if root else ""
    except (OSError, UnicodeDecodeError):
        return ""


def nudge_for_reply(root: Path | None, reply: str) -> str | None:
    """The nudge after a text-only reply, from the state of TASK.md: no checklist means not
    started, open items mean in progress (unless the next one asks the user), all done means
    finished. Every turn has a workspace; with none (tests only) the reply stands."""
    if root is None:
        return None
    md = task_md(root)
    if not has_items(md):
        return NOT_STARTED_NUDGE
    if waiting_on_user(open_items(md)):
        return None
    return nudge_for(root) or (EMPTY_REPLY_NUDGE if not reply.strip() else None)


def reset_finished_task(root: Path | None) -> None:
    """At the start of a turn: empty a TASK.md whose items are all done, so a new request
    starts fresh. A checklist with open items stays, so the turn resumes it."""
    md = task_md(root)
    if root and has_items(md) and not open_items(md):
        (root / TASK_FILE).write_text("", encoding="utf-8")


def _run_calls(ctx: RunContext[Any]) -> list[ToolCallPart]:
    """Tool calls the model made in this run (history from earlier turns excluded)."""
    return [
        p
        for m in ctx.messages
        if isinstance(m, ModelResponse) and m.run_id == ctx.run_id
        for p in m.parts
        if isinstance(p, ToolCallPart)
    ]


async def ask_user(ctx: RunContext[TurnDeps], questions: str) -> str:
    """Call this when you need answers from the user before you can go on. Then reply with
    the questions and stop: the user answers in the next message. Do not guess the answers."""
    ctx.deps.asked = True
    return ASKED


async def task_nudge(ctx: RunContext[TurnDeps], output: str) -> str:
    """Output validator: keep the run working while TASK.md has open items, up to MAX_NUDGES."""
    # Past the last nudge, or on the wrap-up request (another request would exceed the limit).
    left = requests_left(ctx)
    if ctx.retry >= MAX_NUDGES or (left is not None and left <= 0):
        return output
    if (
        not ctx.deps.checklist or ctx.deps.asked
    ):  # a plain chat, or a question: it stands
        return output
    nudge = nudge_for_reply(ctx.deps.root, output)
    # Not started gets one nudge: after it, a reply with no checklist is a direct answer.
    if nudge == NOT_STARTED_NUDGE and ctx.retry >= 1:
        return output
    if nudge:
        raise ModelRetry(nudge)
    return output


# --- capabilities --------------------------------------------------------------


def requests_left(ctx: RunContext[Any]) -> int | None:
    limit = ctx.usage_limits.request_limit if ctx.usage_limits else None
    return None if limit is None else limit - ctx.usage.requests


@dataclass
class WrapUpNearRequestLimit(AbstractCapability[Any]):
    """On the last request of the run: no tools, and a request-scoped prompt to write the status."""

    async def before_model_request(
        self, ctx: RunContext[Any], request_context: ModelRequestContext
    ) -> ModelRequestContext:
        if requests_left(ctx) == 1:
            ctx.enqueue(SystemPromptPart(WRAP_UP, scope="request"))
        return request_context

    async def prepare_tools(
        self, ctx: RunContext[Any], tool_defs: list[ToolDefinition]
    ) -> list[ToolDefinition]:
        return [] if requests_left(ctx) == 1 else tool_defs


def _is_thought(name: str) -> bool:
    return name.endswith("sequentialthinking")


def _over_thought_cap(ctx: RunContext[Any], call: ToolCallPart) -> bool:
    """Whether `call` comes after the run's first MAX_THOUGHTS thinking calls."""
    if not _is_thought(call.tool_name):
        return False
    ids = [c.tool_call_id for c in _run_calls(ctx) if _is_thought(c.tool_name)]
    return call.tool_call_id in ids[MAX_THOUGHTS:]


@dataclass
class ThoughtCap(AbstractCapability[Any]):
    """Past MAX_THOUGHTS thinking calls in a run, answer each one with THOUGHT_LIMIT.

    The tool stays offered: a model whose last thought said "next thought needed" calls it
    again, and a hidden tool makes that call an unknown-tool error that ends the turn."""

    async def wrap_tool_validate(
        self, ctx: RunContext[Any], *, call, tool_def, args, handler
    ) -> Any:
        # Over the cap the args are never used, so bad ones must not cost a retry.
        return args if _over_thought_cap(ctx, call) else await handler(args)

    async def wrap_tool_execute(
        self, ctx: RunContext[Any], *, call, tool_def, args, handler
    ) -> Any:
        return THOUGHT_LIMIT if _over_thought_cap(ctx, call) else await handler(args)


def _with_old_text_required(tool_def: ToolDefinition) -> ToolDefinition:
    schema = dict(tool_def.parameters_json_schema)
    props = {k: v for k, v in schema["properties"].items() if k != "replacements"}
    schema["properties"] = props
    schema["required"] = ["path", "old_text", "new_text"]
    return replace(tool_def, description=EDIT_FILE_DOC, parameters_json_schema=schema)


@dataclass
class EditFile(AbstractCapability[Any]):
    """edit_file changes one part of a file; write_file changes the whole file.

    The harness edit_file makes `old_text` optional (for its `replacements` form), so a model
    that wants a full rewrite sends only `new_text`. Here `old_text` is required, and the
    error names write_file as the way to change the whole file."""

    async def prepare_tools(
        self, ctx: RunContext[Any], tool_defs: list[ToolDefinition]
    ) -> list[ToolDefinition]:
        return [
            _with_old_text_required(t) if t.name == "edit_file" else t
            for t in tool_defs
        ]

    async def before_tool_execute(
        self, ctx: RunContext[Any], *, call, tool_def, args
    ) -> Any:
        if call.tool_name == "edit_file" and not args.get("old_text"):
            raise ModelRetry(EDIT_NEEDS_OLD_TEXT)
        return args


@dataclass
class WriteParents(AbstractCapability[Any]):
    """write_file makes missing parent folders, as the Rust tool did; the harness refuses.

    List it after Permissions: a held call stops there, so only an approved write gets here."""

    async def before_tool_execute(
        self, ctx: RunContext[Any], *, call, tool_def, args
    ) -> Any:
        if call.tool_name == "write_file":
            try:
                ctx.deps.resolve(args["path"]).parent.mkdir(parents=True, exist_ok=True)
            except (OSError, ToolFailed):
                pass  # the harness write reports the bad path itself
        return args


@dataclass
class ToolErrors(AbstractCapability[Any]):
    """OS and HTTP errors are the world failing, not a bug: the model sees them and adapts."""

    async def on_tool_execute_error(
        self,
        ctx: RunContext[Any],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: Any,
        error: Exception,
    ) -> Any:
        if isinstance(error, (OSError, httpx.HTTPError)):
            raise ToolFailed(str(error)) from error
        raise error
