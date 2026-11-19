import asyncio
import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from thea_agent.__main__ import LINE_LIMIT, DefaultHandlers, serve
from thea_agent.protocol import Event, Incoming, Result

FIXTURES = sorted((Path(__file__).parent / "fixtures" / "protocol").glob("*.json"))
ADAPTER = TypeAdapter(Incoming | Event | Result)


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixtures_round_trip(path):
    text = path.read_text()
    assert ADAPTER.validate_json(text).model_dump(mode="json") == json.loads(text)


async def _serve(capsys, *lines: str, limit: int = LINE_LIMIT):
    reader = asyncio.StreamReader(limit=limit)
    for line in lines:
        reader.feed_data(line.encode())
    reader.feed_eof()
    await serve(reader, DefaultHandlers())
    return capsys.readouterr()


async def test_bad_line_is_ignored(capsys):
    out = await _serve(
        capsys,
        "not json\n",
        '{"type":"call","id":"1","method":"ping","params":{}}\n',
    )
    assert [json.loads(line) for line in out.out.splitlines()] == [
        {"type": "result", "id": "1", "ok": True, "value": "pong"}
    ]
    assert "bad line ignored" in out.err


async def test_unknown_method_returns_error(capsys):
    out = await _serve(capsys, '{"type":"call","id":"2","method":"nope","params":{}}\n')
    (msg,) = [json.loads(line) for line in out.out.splitlines()]
    assert msg["ok"] is False and msg["id"] == "2" and "nope" in msg["error"]


def _ping(pad: int) -> str:
    return (
        json.dumps(
            {"type": "call", "id": "1", "method": "ping", "params": {"pad": "x" * pad}}
        )
        + "\n"
    )


async def test_line_over_64kib_is_served(capsys):
    out = await _serve(capsys, _ping(200_000))
    assert json.loads(out.out)["value"] == "pong"


async def test_over_limit_line_is_skipped_and_server_keeps_serving(capsys):
    out = await _serve(
        capsys, _ping(5_000), _ping(0).replace('"1"', '"2"'), limit=1_000
    )
    assert [json.loads(line)["id"] for line in out.out.splitlines()] == ["2"]
    assert "oversized line ignored" in out.err


async def test_eof_cancels_a_turn_blocked_on_approval(capsys):
    """stdin EOF (the app quit) must not leave the process waiting on an approval forever."""

    class Blocked(DefaultHandlers):
        async def turn(self, req):
            await (
                asyncio.get_running_loop().create_future()
            )  # an approval nobody answers

    reader = asyncio.StreamReader()
    turn = (Path(__file__).parent / "fixtures/protocol/turn.json").read_text()
    reader.feed_data((json.dumps(json.loads(turn)) + "\n").encode())
    server = asyncio.create_task(serve(reader, Blocked()))
    await asyncio.sleep(0.05)  # the turn is now waiting
    reader.feed_data(b'{"type":"call","id":"1","method":"ping","params":{}}\n')
    reader.feed_eof()
    await asyncio.wait_for(server, timeout=2)
    assert '"value": "pong"' in capsys.readouterr().out  # calls still answered
