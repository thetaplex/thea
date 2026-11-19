"""Outgoing lines on stdout. Every write holds one lock so lines never interleave."""

import json
import sys
import threading
from collections.abc import Callable
from typing import Any

Emit = Callable[[str, dict], None]

_lock = threading.Lock()


def _write(obj: dict[str, Any]) -> None:
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    with _lock:
        sys.stdout.write(line)
        sys.stdout.flush()


def stdout_emit(name: str, payload: dict) -> None:
    _write({"type": "event", "name": name, "payload": payload})


def write_result(
    id: str, ok: bool, value: Any = None, error: str | None = None
) -> None:
    msg: dict[str, Any] = {"type": "result", "id": id, "ok": ok}
    if ok:
        msg["value"] = value
    else:
        msg["error"] = error
    _write(msg)
