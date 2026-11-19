"""One turn: up to MAX_ROUNDS runs of one agent, its stream mapped to the UI events."""

import asyncio
import os
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from pydantic_ai import (
    Agent,
    CancellationToken,
    ModelMessagesTypeAdapter,
    RunCancelled,
    UsageLimitExceeded,
    UsageLimits,
)
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models import ModelRequestContext

from thea_agent import reflection, toolsets, workflow
from thea_agent.approvals import Approvals
from thea_agent.capabilities import (
    MAX_NUDGES,
    open_items,
    reset_finished_task,
    task_md,
    task_nudge,
    waiting_on_user,
)
from thea_agent.deps import TurnDeps
from thea_agent.emit import Emit
from thea_agent.history import message_events, to_model_messages, tool_output, ui_rows
from thea_agent.models import (
    Capabilities,
    PromptBudget,
    build_model,
    model_capabilities,
)
from thea_agent.prompt import build_system_prompt
from thea_agent.protocol import StoredRow, TurnRequest

MAX_ROUNDS = 6

# Reflection tasks still running; held so they are not garbage-collected.
background: set[asyncio.Task] = set()

# Verbatim from agent/mod.rs `round_brief`, including the runs of spaces its literal carries.
_ROUND_BRIEF = "Round {round} of {max_rounds}. Earlier rounds' tool outputs are not in this context.\n\n         Original request:\n{request}\n\n         Status at the end of the last round:\n{status}\n\n         TASK.md now:\n{task_md}\n\n         Your notes are in research/notes.md (read_file) and the sources in the ledger (list_sources).          Read the notes before you fetch anything again. Continue with the next open item."

_PATH_TOOLS = ("read_file", "write_file", "edit_file")
_STATUS = {"success": "done", "denied": "rejected"}  # anything else is an error


def round_brief(round: int, request: str, status: str, task_md: str) -> str:
    return _ROUND_BRIEF.format(
        round=round,
        max_rounds=MAX_ROUNDS,
        request=request,
        status=status,
        task_md=task_md,
    )


def thea_home() -> Path:
    return Path(os.environ.get("THEA_HOME") or Path.home() / ".thea")


def open_mcp_log():
    """`~/.thea/logs/mcp.log`, appended to: MCP servers need a real file for their stderr."""
    path = thea_home() / "logs" / "mcp.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("a", encoding="utf-8")


def resolve_budget(req: TurnRequest, caps: Capabilities) -> PromptBudget:
    """The tier's budget; `small_model` forces the tier, a persona's `max_steps` the step cap."""
    tier = (
        caps.tier
        if req.small_model is None
        else "small"
        if req.small_model
        else "large"
    )
    budget = PromptBudget.for_tier(tier)
    if req.persona and req.persona.max_steps > 0:
        budget = replace(budget, max_steps=req.persona.max_steps)
    return budget


def _chars(messages: list[ModelMessage]) -> int:
    n = 0
    for m in messages:
        for p in m.parts:
            if isinstance(p, ToolCallPart):
                n += len(p.args_as_json_str())
            elif isinstance(p, ToolReturnPart):
                n += len(tool_output(p))
            elif isinstance(c := getattr(p, "content", None), str):
                n += len(c)
    return n


@dataclass
class UiEvents(AbstractCapability[TurnDeps]):
    """Stream events -> `chat:delta`, `agent:tool-event`; request size -> `agent:prompt-size`."""

    prompt: str
    rows: "Rows | None" = None
    first_prompt_sent: bool = False
    _args: dict[str, dict] = field(default_factory=dict)

    async def before_model_request(
        self, ctx, request_context: ModelRequestContext
    ) -> ModelRequestContext:
        deps, msgs = ctx.deps, request_context.messages
        # The request is final now: tool rows are stored before the model streams.
        if self.rows:
            self.rows.flush()
        if not self.first_prompt_sent:
            self.first_prompt_sent = True
            tools = request_context.model_request_parameters.function_tools
            deps.emit(
                "agent:first-prompt",
                {
                    "messages": [{"role": "system", "content": self.prompt}]
                    + ModelMessagesTypeAdapter.dump_python(msgs, mode="json"),
                    "tools": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.parameters_json_schema,
                        }
                        for t in tools
                    ],
                },
            )
        chars = len(self.prompt) + _chars(msgs)
        deps.emit("agent:prompt-size", {"chat_id": deps.chat_id, "chars": chars})
        return request_context

    async def on_event(self, ctx, *, event) -> None:
        deps = ctx.deps
        match event:
            case (
                PartStartEvent(part=TextPart(content=text))
                | PartDeltaEvent(delta=TextPartDelta(content_delta=text))
            ) if text:
                deps.emit("chat:delta", {"chat_id": deps.chat_id, "delta": text})
            case FunctionToolCallEvent(part=call):
                if call.tool_call_id not in self._args:  # a held call is announced once
                    self._args[call.tool_call_id] = call.args_as_dict()
                    self._tool_event(deps, call.tool_call_id, call.tool_name, "running")
            case FunctionToolResultEvent(part=ret):
                status = _STATUS.get(ret.outcome, "error")
                args = self._args.get(ret.tool_call_id, {})
                path = None
                if status == "done":
                    meta = ret.metadata if isinstance(ret.metadata, dict) else {}
                    path = meta.get("artifact_path") or (
                        args.get("path") if ret.tool_name in _PATH_TOOLS else None
                    )
                self._tool_event(
                    deps,
                    ret.tool_call_id,
                    ret.tool_name,
                    status,
                    tool_output(ret),
                    path,
                )

    def _tool_event(self, deps, call_id, name, status, output=None, path=None):
        deps.emit(
            "agent:tool-event",
            {
                "chat_id": deps.chat_id,
                "tool_call_id": call_id,
                "tool_name": name,
                "arguments": self._args.get(call_id, {}),
                "status": status,
                "output": output,
                "artifact_path": path,
            },
        )


@dataclass
class Rows:
    """Emits `message` rows as messages complete; messages without a UI row wait for the next one."""

    emit: Emit
    chat_id: str
    rows: list[StoredRow] = field(default_factory=list)
    messages: list[ModelMessage] = field(default_factory=list)
    source: Callable[[], list[ModelMessage]] | None = None  # the run's new_messages
    _pending: list[ModelMessage] = field(default_factory=list)
    _sent: int = 0

    def start_run(self) -> None:
        self._sent, self.source = 0, None

    def flush(self) -> None:
        if self.source:
            self.push(self.source(), final=True)

    def push(self, new: list[ModelMessage], final: bool = False) -> None:
        """Send `new[_sent:]`; all of it when `final`, else all but the last (it may still grow)."""
        upto = len(new) if final else len(new) - 1
        for m in new[self._sent : upto]:
            self.messages.append(m)
            self._pending.append(m)
            if ui_rows(m):
                self._send()
        self._sent = max(self._sent, upto)

    def close(self) -> None:
        if self._pending:
            self._send()

    def _send(self) -> None:
        for payload in message_events(self.chat_id, self._pending):
            self.emit("message", payload)
            self.rows.append(StoredRow.model_validate(payload))
        self._pending = []


async def _run_round(
    agent, prompt, history, deps, budget, token, rows
) -> tuple[bool, str]:
    """One run. Returns (hit the request limit, last reply text)."""
    rows.start_run()
    run = None
    limited = False
    try:
        async with agent.iter(
            prompt,
            message_history=history,
            deps=deps,
            usage_limits=UsageLimits(request_limit=budget.max_steps),
            cancellation_token=token,
        ) as run:
            rows.source = run.new_messages
            async for node in run:
                # A yielded CallToolsNode's response is complete: its row lands before the
                # tools run. Tool returns land from UiEvents, before the next model call.
                rows.push(run.new_messages(), final=Agent.is_call_tools_node(node))
    except UsageLimitExceeded:
        limited = True
    finally:
        if run is not None:
            rows.push(run.new_messages(), final=True)
    new = run.new_messages() if run is not None else []
    limited = limited or (run is not None and run.usage.requests >= budget.max_steps)
    reply = next(
        (
            "".join(p.content for p in m.parts if isinstance(p, TextPart))
            for m in reversed(new)
            if isinstance(m, ModelResponse)
        ),
        "",
    )
    return limited, reply


async def _run_agent(agent, prompt, deps, token, rows, limit: int):
    """Run one agent to its output, its messages stored as rows as they complete."""
    rows.start_run()
    run = None
    try:
        async with agent.iter(
            prompt,
            deps=deps,
            usage_limits=UsageLimits(request_limit=limit),
            cancellation_token=token,
        ) as run:
            rows.source = run.new_messages
            async for node in run:
                rows.push(run.new_messages(), final=Agent.is_call_tools_node(node))
        return run.result.output
    finally:
        if run is not None:
            rows.push(run.new_messages(), final=True)


async def _workflow_turn(
    req, emit, deps, model, settings, caps, budget, token, rows, log
):
    """THEA_WORKFLOW=1: the plan and the files are code's; the model fills in the text."""
    ui = UiEvents("(workflow)", rows)

    def run_agent(agent, prompt, limit):
        return _run_agent(agent, prompt, deps, token, rows, limit)

    request = next((r.content for r in reversed(req.history) if r.role == "user"), "")
    wf = workflow.Workflow(req, deps, model, settings, [ui], run_agent)
    reply, ok = await wf.run(request)
    emit("chat:delta", {"chat_id": req.chat_id, "delta": reply})
    rows.start_run()
    rows.push([workflow.reply_message(reply)], final=True)
    if not ok:
        items = open_items(task_md(deps.root)) + [
            ln for ln in task_md(deps.root).splitlines() if ln.startswith("- [!]")
        ]
        emit(
            "agent:incomplete",
            {
                "chat_id": req.chat_id,
                "reason": "Some workflow steps failed.",
                "open_items": items,
            },
        )


def _signal(deps: TurnDeps, messages: list[ModelMessage]) -> dict | None:
    if (verdict := deps.signals.citations) is not None:
        return {"kind": "citations", "pass": verdict[0], "detail": verdict[1]}
    return reflection.detect_repeated_errors(messages)


async def _turn(
    req: TurnRequest, emit: Emit, approvals: Approvals, token, rows: Rows, model=None
):
    """The rounds; returns what reflection needs, or None when there is no signal."""
    if token.cancelled:  # replaced before it started
        raise RunCancelled("Cancelled")
    ws = req.workspace
    root = Path(ws.root_path) if ws else None
    checklist = req.persona is not None and ws is not None and not ws.is_chat
    if checklist:
        reset_finished_task(root)
    provider = req.provider.model_dump()
    caps = await model_capabilities(provider)
    budget = resolve_budget(req, caps)
    deps = TurnDeps(
        root=root,
        emit=emit,
        chat_id=req.chat_id,
        settings=req.settings,
        project_id=ws.id if ws else "",
        search_results=budget.search_results,
        tool_output_chars=budget.tool_output_chars,
        approvals=approvals,
        checklist=checklist,
    )
    model = model or build_model(provider, thinking=caps.supports_thinking)
    settings: Any = (
        {"thinking": bool(req.persona and req.persona.native_thinking)}
        if caps.supports_thinking
        else None
    )
    with open_mcp_log() as log:
        if checklist and workflow.uses_workflow(
            req, os.environ.get("THEA_WORKFLOW") == "1"
        ):
            await _workflow_turn(
                req, emit, deps, model, settings, caps, budget, token, rows, log
            )
            signal = _signal(deps, rows.messages)
            return (model, signal) if signal else None
        tools = await toolsets.build(req, deps, caps, budget, log)
        try:
            prompt = build_system_prompt(req, tools.tool_names, budget)
            agent = Agent(
                model,
                deps_type=TurnDeps,
                instructions=prompt,
                model_settings=settings,
                capabilities=[*tools.capabilities, UiEvents(prompt, rows)],
                toolsets=tools.toolsets,
                retries={"output": MAX_NUDGES},
            )
            agent.output_validator(task_nudge)
            request = next(
                (r.content for r in reversed(req.history) if r.role == "user"), ""
            )
            history, brief = to_model_messages(req.history), None
            for rnd in range(1, MAX_ROUNDS + 1):
                limited, status = await _run_round(
                    agent, brief, history, deps, budget, token, rows
                )
                md = task_md(root)
                if (
                    checklist
                    and limited
                    and not deps.asked
                    and open_items(md)
                    and rnd < MAX_ROUNDS
                ):
                    status = (
                        status.strip()
                        or f"Step limit of {budget.max_steps} reached for this round."
                    )
                    history, brief = None, round_brief(rnd + 1, request, status, md)
                    emit(
                        "agent:round",
                        {
                            "chat_id": req.chat_id,
                            "round": rnd + 1,
                            "max_rounds": MAX_ROUNDS,
                        },
                    )
                    continue
                break
        finally:
            await tools.aclose()
    items = open_items(task_md(root)) if checklist else []
    reason = (
        f"Stopped at the step limit ({budget.max_steps} steps per round, {MAX_ROUNDS} rounds)."
        if limited
        else "The model stopped with TASK.md items still open."
        if items and not (deps.asked or waiting_on_user(items))
        else None
    )
    if reason:
        emit(
            "agent:incomplete",
            {"chat_id": req.chat_id, "reason": reason, "open_items": items},
        )
    if signal := _signal(deps, rows.messages):
        return model, signal
    return None


async def run_turn(
    req: TurnRequest,
    emit: Emit,
    approvals: Approvals,
    token: CancellationToken,
    model=None,
) -> None:
    """Run one turn; `chat:finished` is emitted exactly once, then the reflection runs.
    `model` replaces the one built from `req.provider` (evals and tests)."""
    rows = Rows(emit, req.chat_id)
    error: str | None = (
        None  # a stop or a replaced turn finishes without one, as in Rust
    )
    found = None
    try:
        found = await _turn(req, emit, approvals, token, rows, model)
    except asyncio.CancelledError:
        # Our own task being cancelled propagates; a cancelled approval wait (cancel_chat) is a stop.
        current = asyncio.current_task()
        if current is not None and current.cancelling():
            raise
    except RunCancelled:
        pass
    except Exception as e:  # noqa: BLE001 - any failure ends the turn with its text
        traceback.print_exc()
        error = str(e) or type(e).__name__
    finally:
        try:
            rows.close()
        finally:
            emit("chat:finished", {"chat_id": req.chat_id, "error": error})
    if found and req.persona:
        # Its own task: the chat's next turn must not wait for the extra model call.
        task = asyncio.create_task(
            reflection.reflect_and_emit(
                emit, req.persona.id, *found, [*req.history, *rows.rows], req.lessons
            )
        )
        background.add(task)
        task.add_done_callback(background.discard)
