import pytest
from pydantic_ai import ModelRetry, ToolFailed

from thea_agent.tools import ledger, research
from thea_agent.tools.ledger import Source


def src(key: str, **kw) -> Source:
    return Source(
        key=key, kind="web", title="T", url=f"https://x/{key}", added_at="", **kw
    )


def test_passes_when_every_citation_is_in_ledger():
    r = ledger.check_citations_text(
        "Claim [S1]. Other [S2].\n\n## References\n- [S1] a\n- [S2] b\n",
        [src("S1"), src("S2")],
    )
    assert r.passed
    assert r.missing == []


def test_fails_on_unknown_key_and_bad_reference():
    r = ledger.check_citations_text(
        "Claim [S3].\n\n## References\n- [S4] ghost\n", [src("S1")]
    )
    assert not r.passed
    assert r.missing == ["S3"]
    assert r.bad_references == ["S4"]
    assert r.orphans == ["S1"]


def test_ignores_keys_inside_code_fences():
    r = ledger.check_citations_text(
        "```\n[S9]\n```\nText `[S8]` here [S1].", [src("S1")]
    )
    assert r.cited == ["S1"]
    assert r.passed


def test_parses_multi_digit_keys():
    assert ledger.check_citations_text("See [S10].", [src("S1")]).missing == ["S10"]


def test_list_sorts_by_relevance_then_key():
    v = [
        src("S1", relevance=2),
        src("S2"),
        src("S3", relevance=5),
        src("S4", relevance=5),
    ]
    ledger.sort_by_relevance(v)
    assert [s.key for s in v] == ["S3", "S4", "S1", "S2"]
    assert ledger.format_ledger(v[:1]).startswith("[S3] r=5 ")


def test_next_key_increments_max():
    assert ledger.next_key([]) == "S1"
    assert ledger.next_key([src("S2"), src("S7")]) == "S8"


def test_corrupt_ledger_is_an_error_not_a_reset(tmp_path):
    (tmp_path / "research").mkdir()
    path = tmp_path / ledger.LEDGER_PATH
    path.write_text("{not json")
    with pytest.raises(ToolFailed, match="sources.json"):
        ledger.load_ledger(tmp_path)
    assert path.read_text() == "{not json"


def test_ledger_path_variants_are_detected():
    for p in [
        "research/sources.json",
        "./research/sources.json",
        "research\\sources.json",
        "/research/sources.json",
    ]:
        assert ledger.is_ledger_path(p), p
    assert not ledger.is_ledger_path("research/notes.md")


def test_add_source_args_take_an_id_with_its_url():
    with pytest.raises(ModelRetry):
        ledger.parse_add_source_args()
    # Small models give the id and the page it came from; the id leads, the url is the fallback.
    a = ledger.parse_add_source_args(
        doi="10.1/x", url="https://a", arxiv_id="2303.11366"
    )
    assert (a.kind, a.value, a.url) == ("doi", "10.1/x", "https://a")
    a = ledger.parse_add_source_args(arxiv_id="2303.11366", url="https://a")
    assert (a.kind, a.value, a.url) == ("arxiv_id", "2303.11366", "https://a")
    a = ledger.parse_add_source_args(url="https://a")
    assert (a.kind, a.value) == ("url", "https://a")
    assert a.title is None
    assert a.relevance is None
    assert ledger.parse_add_source_args(url="https://a", relevance=9).relevance == 5
    assert ledger.parse_add_source_args(url="https://a", relevance=0).relevance == 1


def test_add_resolved_dedupes_by_doi(tmp_path):
    a, new_a = ledger.add_resolved(tmp_path, src("S1", doi="10.1/X"))
    b, new_b = ledger.add_resolved(tmp_path, src("S2", doi="10.1/x"))
    assert new_a and not new_b
    assert a.key == "S1"
    assert b.key == "S1"
    assert len(ledger.load_ledger(tmp_path)) == 1


def test_add_resolved_rederives_key_from_fresh_ledger(tmp_path):
    ledger.save_ledger(tmp_path, [src("S1"), src("S2")])
    n = src("S1")
    n.url = "https://new"
    r, new = ledger.add_resolved(tmp_path, n)
    assert new
    assert r.key == "S3"
    assert len(ledger.load_ledger(tmp_path)) == 3


def test_empty_url_never_matches_in_dedupe():
    e = src("S1")
    e.url = ""
    assert ledger.find_duplicate([e], "10.1/y", "") is None


def test_ledger_round_trips_with_abstract_key(tmp_path):
    ledger.save_ledger(tmp_path, [src("S1", summary="s")])
    assert '"abstract": "s"' in (tmp_path / ledger.LEDGER_PATH).read_text()
    assert ledger.load_ledger(tmp_path)[0].summary == "s"


async def test_list_sources_and_check_citations_record_signal(ctx):
    ledger.save_ledger(ctx.deps.root, [src("S1")])
    assert (await ledger.list_sources(ctx)).startswith("[S1] ")
    (ctx.deps.root / "d.md").write_text("Claim [S1].\n\n## References\n- [S1] a\n")
    out = await ledger.check_citations(ctx, "d.md")
    assert out.startswith("PASS")
    assert ctx.deps.signals.citations is not None
    assert ctx.deps.signals.citations[0]
    (ctx.deps.root / "d.md").write_text("Claim [S2].\n")
    assert (await ledger.check_citations(ctx, "d.md")).startswith("FAIL")
    assert not ctx.deps.signals.citations[0]


async def test_check_citations_failures(ctx):
    with pytest.raises(ToolFailed):
        await ledger.check_citations(ctx, "missing.md")
    with pytest.raises(ToolFailed):
        await ledger.check_citations(ctx, "../x.md")


async def test_add_source_without_identifier_retries(ctx):
    with pytest.raises(ModelRetry):
        await ledger.add_source(ctx)


async def test_add_source_falls_back_to_the_url_when_the_id_is_unknown(
    ctx, monkeypatch
):
    async def no_paper(query):
        return None

    async def page(url, max_chars):
        return research.Fetched(
            title="Reflexion",
            url=url,
            fetched_at="t",
            text="",
            content_type="text/html",
        )

    monkeypatch.setattr(research, "find_paper", no_paper)
    monkeypatch.setattr(research, "fetch", page)
    # An arXiv id in the doi field, as gemma sends it.
    out = await ledger.add_source(
        ctx, doi="2303.11366", url="https://arxiv.org/abs/2303.11366"
    )
    assert out == "Added [S1] Reflexion"
    [s] = ledger.load_ledger(ctx.deps.root)
    assert (s.kind, s.url) == ("web", "https://arxiv.org/abs/2303.11366")


def test_add_source_takes_no_note():
    """Notes go to research/notes.md; a note here was a second, wrong place for them."""
    import inspect

    assert "note" not in inspect.signature(ledger.add_source).parameters
