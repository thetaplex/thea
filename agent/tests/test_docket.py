import pytest
from pydantic_ai import ModelRetry, ToolFailed

from thea_agent.tools import docket, ledger


async def test_add_update_and_sort(ctx):
    root = ctx.deps.root
    out = await docket.add_docket_item(
        ctx,
        "Submit quarterly tax estimate",
        kind="task",
        priority=3,
        due="2026-11-20",
        detail="Check accountant spreadsheet first",
    )
    assert out.startswith("[D1]")
    dup = await docket.add_docket_item(ctx, "submit quarterly tax estimate")
    assert dup.startswith("[D1] (already on Docket)")
    out2 = await docket.add_docket_item(
        ctx, "Pick dental insurance plan", kind="decision", priority=2, due="2026-11-18"
    )
    assert out2.startswith("[D2]")

    assert "done" in await docket.update_docket_item(ctx, "D1", status="done")
    listing = (await docket.list_docket(ctx)).splitlines()
    assert listing[0].startswith("[D2]") and listing[1].startswith("[D1]")
    assert (await docket.list_docket(ctx, status="done")).startswith("[D1]")
    assert await docket.list_docket(ctx, kind="note") == "(no matching Docket items)"

    md = (root / docket.DOCKET_MD_REL).read_text(encoding="utf-8")
    assert "## Open" in md and "[D2]" in md and "## Done" in md
    assert "- [x] [D1]" in md


async def test_priority_accepts_numeric_strings_via_schema_and_clamps(ctx):
    await docket.add_docket_item(ctx, "x", priority=9)
    assert "p3" in await docket.list_docket(ctx)


async def test_invalid_arguments_retry_and_missing_key_fails(ctx):
    with pytest.raises(ModelRetry):
        await docket.add_docket_item(ctx, "  ")
    with pytest.raises(ModelRetry):
        await docket.add_docket_item(ctx, "t", kind="chore")
    with pytest.raises(ModelRetry):
        await docket.update_docket_item(ctx, "D1", status="wip")
    with pytest.raises(ToolFailed):
        await docket.update_docket_item(ctx, "D9", status="done")


async def test_approval_gets_summary_and_diff(ctx, monkeypatch):
    calls = []

    async def fake(ctx, category, summary, details, diff=None):
        calls.append((category, summary, details, diff))

    monkeypatch.setattr(docket.approvals, "require", fake)
    await docket.add_docket_item(ctx, "Pay rent", detail="by Friday")
    assert calls[0][:3] == ("write", "Add Docket task `Pay rent`", "by Friday")
    assert "+- [ ] [D1]" in calls[0][3]
    await docket.update_docket_item(ctx, "[D1]", status="done")
    assert calls[1][1] == "Update Docket item [D1]"
    assert "+- [x] [D1]" in calls[1][3]


def test_read_only_paths():
    assert docket.READ_ONLY_PATHS == ("docket/docket.json",)
    assert ledger.READ_ONLY_PATHS == ("research/sources.json",)


async def test_calendar_ics_export(ctx):
    out = await docket.export_calendar(
        ctx,
        "Dentist Appointment",
        "2026-11-22T09:30",
        end="2026-11-22T10:30",
        location="Downtown Clinic, Suite 200",
        description="Annual checkup and cleaning",
    )
    rel = "docket/calendar/dentist-appointment.ics"
    assert rel in out.return_value
    assert out.metadata == {"artifact_path": rel}
    raw = (ctx.deps.root / rel).read_bytes().decode()
    for line in (
        "BEGIN:VCALENDAR\r\n",
        "DTSTART:20261122T093000Z\r\n",
        "DTEND:20261122T103000Z\r\n",
        "SUMMARY:Dentist Appointment\r\n",
        "LOCATION:Downtown Clinic\\, Suite 200\r\n",
        "END:VCALENDAR\r\n",
    ):
        assert line in raw


async def test_calendar_rejects_bad_dates(ctx):
    with pytest.raises(ModelRetry):
        await docket.export_calendar(ctx, "x", "tomorrow")
