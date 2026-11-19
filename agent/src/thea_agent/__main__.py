"""Sidecar entry point: read JSON lines from stdin, dispatch to handlers."""

import asyncio
import json
import sys
import traceback
from dataclasses import asdict
from typing import Any, Protocol

import pydantic_ai
from pydantic import TypeAdapter, ValidationError
from pydantic_ai import CancellationToken

from . import models, toolsets
from .approvals import Approvals
from .emit import Emit, stdout_emit, write_result
from .protocol import (
    Approval,
    Call,
    Cancel,
    Incoming,
    McpServer,
    StoredRow,
    TurnRequest,
)
from .reflection import reflect_and_emit
from .turn import open_mcp_log, run_turn

pydantic_ai.BANNER_ENABLED = False  # stdout carries the protocol

_incoming = TypeAdapter(Incoming)

# A turn line carries the full history and prompts; asyncio's 64 KiB default is too small.
LINE_LIMIT = 64 * 1024 * 1024

# After stdin EOF (the app quit): calls get this long to answer, then everything is cancelled.
EOF_GRACE = 1.0


class Handlers(Protocol):
    emit: Emit

    async def turn(self, req: TurnRequest) -> None: ...
    async def approval(self, msg: Approval) -> None: ...
    async def cancel(self, msg: Cancel) -> None: ...
    async def call(self, msg: Call) -> Any: ...


class DefaultHandlers:
    def __init__(self, emit: Emit = stdout_emit) -> None:
        self.emit = emit
        self.approvals = Approvals(emit)  # the one per process
        self.running: dict[str, tuple[asyncio.Task, CancellationToken]] = {}

    def _stop(self, chat_id: str) -> asyncio.Task | None:
        """Cancel the chat's running turn and drop its pending approvals."""
        self.approvals.cancel_chat(chat_id)
        if entry := self.running.get(chat_id):
            entry[1].cancel()
            return entry[0]
        return None

    async def turn(self, req: TurnRequest) -> None:
        old = self._stop(req.chat_id)
        me = asyncio.current_task()
        assert me is not None
        token = CancellationToken()
        self.running[req.chat_id] = (me, token)
        try:
            if old is not None:
                await asyncio.wait(
                    [old]
                )  # its chat:finished goes out before this turn starts
            await run_turn(req, self.emit, self.approvals, token)
        finally:
            if self.running.get(req.chat_id, (None,))[0] is me:
                del self.running[req.chat_id]

    async def approval(self, msg: Approval) -> None:
        if not self.approvals.resolve(msg.request_id, msg.decision):
            print(
                f"approval for unknown request ignored: {msg.request_id}",
                file=sys.stderr,
            )

    async def cancel(self, msg: Cancel) -> None:
        self._stop(msg.chat_id)

    async def call(self, msg: Call) -> Any:
        p = msg.params
        match msg.method:
            case "ping":
                return "pong"
            case "list_models":
                return await models.list_models(p["provider"])
            case "test_provider":
                return await models.test_provider(p["provider"])
            case "model_capabilities":
                return asdict(await models.model_capabilities(p["provider"]))
            case "test_mcp_server":
                with open_mcp_log() as log:
                    return await toolsets.list_mcp_tools(
                        McpServer.model_validate(p["server"]), log
                    )
            case "reflect_rating":
                signal = {"kind": "rating", "up": p["up"], "comment": p.get("comment")}
                rows = [StoredRow.model_validate(r) for r in p.get("history", [])]
                return await reflect_and_emit(
                    self.emit, p["persona_id"], models.build_model(p["provider"]),
                    signal, rows, p.get("lessons", []),
                )  # fmt: skip
        raise ValueError(f"unknown method: {msg.method}")


async def _answer(handlers: Handlers, msg: Call) -> None:
    try:
        write_result(msg.id, True, await handlers.call(msg))
    except Exception as e:  # noqa: BLE001 - handler errors become ok:false
        write_result(msg.id, False, error=str(e))


async def _guarded(coro) -> None:
    try:
        await coro
    except Exception:  # noqa: BLE001 - a failed task must not kill the server
        traceback.print_exc()


def _reject(line: bytes, e: ValidationError, emit: Emit) -> None:
    """Log where the line failed, never its values (a turn carries the API key); a turn
    the app counts as running still gets its `chat:finished`."""
    where = [
        (".".join(map(str, d["loc"])), d["msg"]) for d in e.errors(include_input=False)
    ]
    print(f"bad line ignored: {where}", file=sys.stderr)
    try:
        raw = json.loads(line)
    except ValueError:
        return
    if (
        isinstance(raw, dict)
        and raw.get("type") == "turn"
        and isinstance(raw.get("chat_id"), str)
    ):
        emit(
            "chat:finished",
            {"chat_id": raw["chat_id"], "error": "The agent rejected the request."},
        )


async def serve(stdin: asyncio.StreamReader, handlers: Handlers) -> None:
    tasks: set[asyncio.Task] = set()
    turns: set[asyncio.Task] = set()

    def spawn(coro) -> asyncio.Task:
        t = asyncio.create_task(_guarded(coro))
        tasks.add(t)
        t.add_done_callback(tasks.discard)
        return t

    while True:
        try:
            line = await stdin.readline()
        except ValueError as e:  # line over the reader limit: dropped, keep serving
            print(f"oversized line ignored: {e}", file=sys.stderr)
            continue
        if not line:
            break
        if not line.strip():
            continue
        try:
            msg = _incoming.validate_json(line)
        except ValidationError as e:
            _reject(line, e, handlers.emit)
            continue
        match msg:
            case TurnRequest():
                t = spawn(handlers.turn(msg))
                turns.add(t)
                t.add_done_callback(turns.discard)
            case Approval():
                spawn(handlers.approval(msg))
            case Cancel():
                spawn(handlers.cancel(msg))
            case Call():
                spawn(_answer(handlers, msg))
    # Nobody is left to approve or read: turns (and their approval waits) stop now, so no
    # tool runs after the app quit; calls get a short grace to answer.
    for t in turns:
        t.cancel()
    if tasks:
        _, late = await asyncio.wait(tasks, timeout=EOF_GRACE)
        for t in late:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _run() -> None:
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=LINE_LIMIT)
    await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin
    )
    await serve(reader, DefaultHandlers())


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
