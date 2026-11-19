"""Approval gate: held tool calls go to the UI as `agent:approval-request` and wait for an answer."""

import asyncio
import difflib
import json
import uuid
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.exceptions import ApprovalRequired
from pydantic_ai.tools import (
    DeferredToolRequests,
    DeferredToolResults,
    ToolApproved,
    ToolDenied,
)
from pydantic_ai_harness.permissions import PermissionRequest, permission_requests

from thea_agent.deps import TurnDeps
from thea_agent.emit import Emit

DENIED = "The user rejected the call."
MCP_DENIED = "User rejected MCP tool execution."


class Approvals:
    """One per process. "Always allow" holds per (project_id, category) until the sidecar exits."""

    def __init__(self, emit: Emit):
        self.emit = emit
        self.allowed: set[tuple[str, str]] = set()
        self._pending: dict[str, tuple[str, asyncio.Future[str]]] = {}

    async def ask(
        self,
        chat_id: str,
        project_id: str,
        category: str,
        tool_name: str,
        summary: str,
        details: str,
        diff: str | None = None,
    ) -> bool:
        """True when approved. Raises CancelledError when `cancel_chat` drops the request."""
        if (project_id, category) in self.allowed:
            return True
        request_id = str(uuid.uuid4())
        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = (chat_id, fut)
        self.emit(
            "agent:approval-request",
            {
                "request_id": request_id,
                "chat_id": chat_id,
                "project_id": project_id,
                "tool_name": tool_name,
                "summary": summary,
                "details": details,
                "diff": diff,
            },
        )
        try:
            decision = await fut
        finally:
            self._pending.pop(request_id, None)
        if decision == "always_allow_project":
            self.allowed.add((project_id, category))
        return decision in ("approve", "always_allow_project")

    def resolve(self, request_id: str, decision: str) -> bool:
        """Answer a pending request; False when it is unknown or already answered."""
        entry = self._pending.get(request_id)
        if entry is None or entry[1].done():
            return False
        entry[1].set_result(decision)
        return True

    def cancel_chat(self, chat_id: str) -> None:
        for cid, fut in list(self._pending.values()):
            if cid == chat_id:
                fut.cancel()


async def require(
    ctx: RunContext[TurnDeps],
    category: str,
    summary: str,
    details: str,
    diff: str | None = None,
) -> None:
    """Return when the call may run; otherwise hold it for `handler` to put to the user."""
    a = ctx.deps.approvals
    if ctx.tool_call_approved or (
        a is not None and (ctx.deps.project_id, category) in a.allowed
    ):
        return
    raise ApprovalRequired(
        metadata={
            "category": category,
            "summary": summary,
            "details": details,
            "diff": diff,
        }
    )


def unified_diff(old: str, new: str, path: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            f"a/{path}",
            f"b/{path}",
        )
    )


def _describe(
    deps: TurnDeps, req: PermissionRequest
) -> tuple[str, str, str, str | None]:
    """(category, summary, details, diff) for a call `Permissions` holds, worded as the Rust agent did."""
    if req.action == "command":
        return "shell", "Run shell command", req.subject, None
    args: dict[str, Any] = req.call.args_as_dict()
    path = req.subject
    try:
        old = deps.resolve(path).read_text()
    except Exception:  # noqa: BLE001 - new file, a directory or a refused path: diff from empty
        old = ""
    match req.call.tool_name:
        case "write_file":
            content = str(args.get("content", ""))
            summary = f"Write file `{path}` ({len(content.encode())} bytes)"
            return "write", summary, path, unified_diff(old, content, path)
        case "edit_file":
            # One old_text/new_text pair: EditFile hides the harness `replacements` form.
            target = args.get("old_text") or ""
            new = old.replace(target, args.get("new_text") or "", 1) if target else old
            return "write", f"Edit file `{path}`", path, unified_diff(old, new, path)
        case _:
            return "write", f"Create directory `{path}`", path, None


async def handler(
    ctx: RunContext[TurnDeps], requests: DeferredToolRequests
) -> DeferredToolResults | None:
    """Put each held call to the user in order. On `cancel_chat`, cancel the run before any runs."""
    a = ctx.deps.approvals
    if a is None:
        return None  # no UI to ask: the calls stay unapproved
    held = {r.call.tool_call_id: r for r in permission_requests(requests)}
    results: dict[str, ToolApproved | ToolDenied] = {}
    for call in requests.approvals:
        if p := held.get(call.tool_call_id):
            category, summary, details, diff = _describe(ctx.deps, p)
        else:
            m = requests.metadata.get(call.tool_call_id) or {}
            category = m.get("category", "write")
            summary = m.get("summary", f"Run `{call.tool_name}`")
            details = m.get("details", json.dumps(call.args_as_dict(), indent=2))
            diff = m.get("diff")
        try:
            ok = await a.ask(
                ctx.deps.chat_id, ctx.deps.project_id, category, call.tool_name,
                summary, details, diff,
            )  # fmt: skip
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise  # the task itself is being cancelled
            ctx.cancel()
            await asyncio.get_running_loop().create_future()  # RunCancelled lands here
            raise
        results[call.tool_call_id] = (
            ToolApproved()
            if ok
            else ToolDenied(MCP_DENIED if category == "mcp" else DENIED)
        )
    return requests.build_results(approvals=results)
