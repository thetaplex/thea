import json
import os

import httpx
import pytest
from pydantic_ai import ModelRetry, ToolFailed

from thea_agent.tools import ledger, research

LIVE = pytest.mark.skipif(not os.environ.get("THEA_LIVE"), reason="live network")


def mock(monkeypatch, handler):
    """Route every research HTTP call through `handler`; no test touches the network."""
    monkeypatch.setattr(
        research,
        "client_factory",
        lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=False
        ),
    )


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    async def resolve(host, port):
        return [host] if host.replace(".", "").isdigit() else ["93.184.216.34"]

    monkeypatch.setattr(research, "resolve_host", resolve)
    monkeypatch.setattr(research, "SEARCH_BACKOFF", 0)


def test_rejects_private_and_loopback_targets():
    for u in [
        "http://127.0.0.1:11434/",
        "http://localhost/x",
        "http://169.254.169.254/latest",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://100.64.0.1/",
        "http://[::1]/",
        "http://[fd00::1]/",
        "http://[::ffff:127.0.0.1]/",
        "ftp://example.com/",
        "file:///etc/passwd",
        "http://host.internal/",
    ]:
        assert not research.is_public_http_url(u), u
    assert research.is_public_http_url("https://arxiv.org/abs/2303.11366")


def test_html_to_text_strips_boilerplate_and_keeps_title():
    title, text = research.html_to_text(
        "<html><head><title>Hi &amp; bye</title><script>x()</script></head>"
        "<body><nav>menu</nav><p>One</p><p>Two &lt;3</p></body></html>"
    )
    assert title == "Hi & bye"
    assert "menu" not in text and "x()" not in text
    assert "One\n" in text and "Two <3" in text


def test_truncation_adds_marker():
    t = research.truncate_marked("a" * 100, 10)
    assert t.startswith("a" * 10) and "[truncated at 10 chars" in t
    assert research.truncate_marked("short", 10) == "short"


def test_parses_duckduckgo_results():
    html = (
        '<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Farxiv.org%2Fabs%2F2303.11366&amp;rut=abc">Reflexion: Language Agents</a>\n'
        '<a class="result__snippet" href="x">Verbal <b>reinforcement</b> learning</a>\n'
        '<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=http%3A%2F%2F127.0.0.1%2Fevil">Local</a><a class="result__snippet">bad</a>'
    )
    hits = research.parse_duckduckgo_html(html, 5)
    assert len(hits) == 1
    assert hits[0].url == "https://arxiv.org/abs/2303.11366"
    assert hits[0].title == "Reflexion: Language Agents"
    assert hits[0].snippet == "Verbal reinforcement learning"


def test_percent_decode_handles_utf8_and_plus():
    assert research.percent_decode("a%20b%2Fc+d") == "a b/c+d"
    assert research.percent_decode("%E2%9C%93") == "✓"


def test_parses_openalex_work_and_abstract():
    v = {
        "title": "Reflexion",
        "publication_year": 2023,
        "doi": "https://doi.org/10.48550/arxiv.2303.11366",
        "primary_location": {"source": {"display_name": "arXiv"}},
        "authorships": [{"author": {"display_name": "Noah Shinn"}}],
        "abstract_inverted_index": {"Large": [0], "language": [1], "agents": [2]},
    }
    p = research.parse_openalex_work(v)
    assert p.year == 2023
    assert p.doi == "10.48550/arxiv.2303.11366"
    assert p.authors == ["Noah Shinn"]
    assert p.summary == "Large language agents"


def test_parses_crossref_message():
    v = {
        "message": {
            "title": ["A Paper"],
            "author": [{"given": "A", "family": "B"}],
            "issued": {"date-parts": [[2021, 5]]},
            "container-title": ["Journal"],
            "DOI": "10.1/x",
            "URL": "https://doi.org/10.1/x",
        }
    }
    p = research.parse_crossref_work(v)
    assert (p.title, p.authors, p.year, p.venue) == (
        "A Paper",
        ["A B"],
        2021,
        "Journal",
    )


def test_parses_arxiv_atom():
    xml = (
        "<feed><entry><id>http://arxiv.org/abs/2303.11366v4</id>"
        "<title>Reflexion: Language Agents</title><published>2023-03-20T00:00:00Z</published>"
        "<author><name>Noah Shinn</name></author><summary>Abs.</summary></entry></feed>"
    )
    p = research.parse_arxiv_atom(xml)
    assert p.title == "Reflexion: Language Agents"
    assert p.year == 2023
    assert p.url == "http://arxiv.org/abs/2303.11366v4"


def test_arxiv_error_entry_is_not_a_paper():
    xml = (
        "<feed><entry><id>http://arxiv.org/api/errors#incorrect_id_format_for_smith2020</id>"
        "<title>Error</title><summary>incorrect id format</summary>"
        "<author><name>arXiv api core</name></author></entry></feed>"
    )
    assert research.parse_arxiv_atom(xml) is None
    with pytest.raises(ModelRetry):
        research.parse_paper_query(None, None, "arxiv:")


def test_title_similarity_gate():
    assert (
        research.title_similarity(
            "Reflexion: language agents with verbal reinforcement learning",
            "Reflexion: Language Agents with Verbal Reinforcement Learning",
        )
        > 0.9
    )
    assert (
        research.title_similarity(
            "Reflexion language agents", "Attention is all you need"
        )
        < 0.2
    )


def test_doi_path_is_encoded():
    u = research.openalex_doi_url("10.1000/a?b#c")
    assert "%3F" in u and "%23" in u and "?" not in u and "#" not in u
    assert research.crossref_doi_url("10.1000/a?b#c").endswith("10.1000/a%3Fb%23c")


def test_title_gate_filters_weak_hits():
    def rec(t):
        return research.PaperRecord(title=t, url="u")

    assert (
        research.gate_title(
            "Reflexion language agents", rec("Attention is all you need")
        )
        is None
    )
    assert research.gate_title(
        "Reflexion language agents", rec("Reflexion: Language Agents")
    )
    assert research.gate_title("x", None) is None


def test_query_parsing():
    q = research.parse_paper_query("https://doi.org/10.1/x", None, None)
    assert q == ("doi", "10.1/x")
    assert research.parse_paper_query("arxiv:2303.11366", None, None)[0] == "arxiv"
    with pytest.raises(ModelRetry):
        research.parse_paper_query(None, None, None)


def test_parses_searxng_json_and_filters_private_urls():
    body = json.dumps(
        {
            "results": [
                {
                    "url": "https://arxiv.org/abs/2303.11366",
                    "title": "Reflexion",
                    "content": "Verbal RL",
                },
                {"url": "http://192.168.1.1/", "title": "router", "content": "no"},
            ]
        }
    )
    hits = research.parse_hits_json(body, 5)
    assert (
        len(hits) == 1
        and hits[0].title == "Reflexion"
        and hits[0].snippet == "Verbal RL"
    )
    with pytest.raises(ValueError):
        research.parse_hits_json("<html>", 5)


def test_parses_tavily_json_and_filters_private_urls():
    body = json.dumps(
        {
            "results": [
                {
                    "url": "https://arxiv.org/abs/2303.11366",
                    "title": "Reflexion",
                    "content": "Verbal RL",
                },
                {"url": "http://10.0.0.1/x", "title": "lan", "content": "no"},
            ]
        }
    )
    hits = research.parse_hits_json(body, 5)
    assert len(hits) == 1 and hits[0].snippet == "Verbal RL"
    with pytest.raises(ValueError):
        research.parse_hits_json("nope", 5)


# --- fetch_url ---


async def test_fetch_url_refuses_private_after_redirect(ctx, monkeypatch):
    seen = []

    def handler(req):
        seen.append(str(req.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/"})

    mock(monkeypatch, handler)
    with pytest.raises(ToolFailed, match="non-public"):
        await research.fetch_url(ctx, "https://a.example/x")
    assert seen == ["https://a.example/x"]


async def test_fetch_url_refuses_hostname_resolving_private(ctx, monkeypatch):
    async def resolve(host, port):
        return ["10.0.0.5"]

    monkeypatch.setattr(research, "resolve_host", resolve)
    mock(monkeypatch, lambda req: pytest.fail("must not connect"))
    with pytest.raises(ToolFailed, match="non-public"):
        await research.fetch_url(ctx, "https://sneaky.example/")


async def test_fetch_url_follows_relative_redirect_and_caps_output(ctx, monkeypatch):
    def handler(req):
        if req.url.path == "/x/y":
            return httpx.Response(301, headers={"location": "/z"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<title>T</title><p>" + "a" * 5000 + "</p>",
        )

    mock(monkeypatch, handler)
    ctx.deps.tool_output_chars = 1500  # leaves 500 after the header room
    out = await research.fetch_url(ctx, "https://a.example/x/y", max_chars=20000)
    assert "Title: T" in out and "URL: https://a.example/z" in out
    assert "[truncated at 500 chars" in out


async def test_fetch_url_http_error_and_bad_url(ctx, monkeypatch):
    mock(monkeypatch, lambda req: httpx.Response(403))
    with pytest.raises(research.HttpStatusError) as e:
        await research.fetch_url(ctx, "https://a.example/")
    assert e.value.status == 403
    with pytest.raises(ToolFailed):
        await research.fetch_url(ctx, "not a url")


# --- web_search ---

SEARX = {"results": [{"url": "https://a.example/1", "title": "A", "content": "c"}]}


async def test_web_search_prefers_searxng_and_dedupes_queries(ctx, monkeypatch):
    ctx.deps.settings["searxng_url"] = "http://searx.test"
    calls = []

    def handler(req):
        calls.append(req.url.params["q"])
        return httpx.Response(200, json=SEARX)

    mock(monkeypatch, handler)
    out = await research.web_search(ctx, ["one", "two", "three", "four"])
    assert calls == ["one", "two", "three"]  # at most 3 queries
    assert out.count("https://a.example/1") == 1  # deduped by URL
    assert out.startswith("1. A")


async def test_web_search_falls_back_to_tavily_then_duckduckgo(ctx, monkeypatch):
    ctx.deps.settings["searxng_url"] = "http://searx.test"
    hosts = []

    def handler(req):
        hosts.append(req.url.host)
        if req.url.host == "searx.test":
            return httpx.Response(500)
        if req.url.host == "api.tavily.com":
            return httpx.Response(200, json={"results": []})
        return httpx.Response(
            200,
            text='<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fb.example%2F">B</a>',
        )

    mock(monkeypatch, handler)
    out = await research.web_search(ctx, "q")
    assert hosts == ["searx.test", "api.tavily.com", "html.duckduckgo.com"]
    assert "https://b.example/" in out


async def test_web_search_all_providers_down_fails(ctx, monkeypatch):
    mock(monkeypatch, lambda req: httpx.Response(500))
    with pytest.raises(ToolFailed, match="every provider"):
        await research.web_search(ctx, "q")


async def test_web_search_needs_a_query(ctx):
    with pytest.raises(ModelRetry):
        await research.web_search(ctx, [])
    with pytest.raises(ModelRetry):
        await research.web_search(ctx, "  ")


async def test_web_search_default_and_clamped_result_count(ctx, monkeypatch):
    many = {
        "results": [
            {"url": f"https://a.example/{i}", "title": "t", "content": ""}
            for i in range(20)
        ]
    }
    ctx.deps.settings["searxng_url"] = "http://searx.test"
    ctx.deps.search_results = 3
    mock(monkeypatch, lambda req: httpx.Response(200, json=many))
    assert (await research.web_search(ctx, "q")).count("https://") == 3
    assert (await research.web_search(ctx, "q", max_results=99)).count("https://") == 10


# --- lookup_paper ---


async def test_lookup_paper_no_match_is_a_normal_result(ctx, monkeypatch):
    mock(monkeypatch, lambda req: httpx.Response(404))
    assert (
        await research.lookup_paper(ctx, doi="10.1/none") == "No matching paper found."
    )


async def test_lookup_paper_falls_back_to_crossref(ctx, monkeypatch):
    def handler(req):
        if req.url.host == "api.openalex.org":
            return httpx.Response(500)
        return httpx.Response(
            200,
            json={
                "message": {
                    "title": ["A Paper"],
                    "DOI": "10.1/x",
                    "URL": "https://doi.org/10.1/x",
                }
            },
        )

    mock(monkeypatch, handler)
    out = await research.lookup_paper(ctx, doi="10.1/x")
    assert out.startswith("A Paper") and "DOI: 10.1/x" in out


async def test_lookup_paper_arxiv_and_missing_args(ctx, monkeypatch):
    xml = "<feed><entry><id>http://arxiv.org/abs/1</id><title>T</title></entry></feed>"
    mock(monkeypatch, lambda req: httpx.Response(200, text=xml))
    assert (await research.lookup_paper(ctx, arxiv_id="arXiv:1")).startswith("T")
    with pytest.raises(ModelRetry):
        await research.lookup_paper(ctx)


async def test_lookup_paper_transport_failure_raises(ctx, monkeypatch):
    mock(monkeypatch, lambda req: httpx.Response(500))
    with pytest.raises(ToolFailed):
        await research.lookup_paper(ctx, arxiv_id="1")


# --- ledger.resolve_source wiring ---


async def test_resolve_source_url_uses_page_title(monkeypatch):
    mock(
        monkeypatch,
        lambda req: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<title>The Page</title><p>hi</p>",
        ),
    )
    s = await ledger.resolve_source(
        ledger.parse_add_source_args(url="https://a.example/p")
    )
    assert (s.kind, s.title, s.url) == ("web", "The Page", "https://a.example/p")


async def test_resolve_source_blocked_page_needs_a_title(monkeypatch):
    mock(monkeypatch, lambda req: httpx.Response(403))
    with pytest.raises(ToolFailed, match="HTTP 403"):
        await ledger.resolve_source(
            ledger.parse_add_source_args(url="https://a.example/p")
        )
    s = await ledger.resolve_source(
        ledger.parse_add_source_args(url="https://a.example/p", title="Blocked report")
    )
    assert s.title == "Blocked report"
    assert s.note == "not fetched (HTTP 403); title from search"


async def test_resolve_source_unreachable_is_refused(monkeypatch):
    def boom(req):
        raise httpx.ConnectError("down")

    mock(monkeypatch, boom)
    with pytest.raises(ToolFailed, match="Could not resolve"):
        await ledger.resolve_source(
            ledger.parse_add_source_args(url="https://a.example/p", title="T")
        )


async def test_resolve_source_doi_and_unknown(monkeypatch):
    def handler(req):
        if req.url.path.endswith("10.1/x"):
            return httpx.Response(
                200, json={"title": "Paper", "doi": "https://doi.org/10.1/x"}
            )
        return httpx.Response(404)

    mock(monkeypatch, handler)
    s = await ledger.resolve_source(
        ledger.parse_add_source_args(doi="10.1/x", relevance=4)
    )
    assert (s.kind, s.title, s.doi, s.relevance) == ("paper", "Paper", "10.1/x", 4)
    with pytest.raises(ToolFailed, match="Could not resolve"):
        await ledger.resolve_source(ledger.parse_add_source_args(doi="10.9/none"))


async def test_add_source_registers_through_the_ledger(ctx, monkeypatch):
    mock(
        monkeypatch,
        lambda req: httpx.Response(
            200, headers={"content-type": "text/html"}, text="<title>The Page</title>"
        ),
    )
    assert (await ledger.add_source(ctx, url="https://a.example/p")).startswith(
        "Added [S1]"
    )
    assert (await ledger.add_source(ctx, url="https://a.example/p")).startswith(
        "Already registered [S1]"
    )


async def test_add_source_asks_approval_with_key_and_title(ctx, monkeypatch):
    calls = []

    async def fake(ctx, category, summary, details, diff=None):
        calls.append((category, summary, details))

    monkeypatch.setattr(ledger.approvals, "require", fake)
    mock(
        monkeypatch,
        lambda req: httpx.Response(
            200, headers={"content-type": "text/html"}, text="<title>The Page</title>"
        ),
    )
    await ledger.add_source(ctx, url="https://a.example/p")
    assert calls == [("write", "Add source S1: The Page", "https://a.example/p")]
    await ledger.add_source(ctx, url="https://a.example/p")  # duplicate: no approval
    assert len(calls) == 1


# --- live (THEA_LIVE=1) ---


@LIVE
async def test_blocked_page_registers_only_with_a_title():
    # httpstat.us answers 403 without a body; a bot wall looks the same to us.
    url = "https://httpstat.us/403"
    with pytest.raises(ToolFailed) as e:
        await ledger.resolve_source(ledger.parse_add_source_args(url=url))
    assert "HTTP 403" in str(e.value) or "Could not resolve" in str(e.value)
    s = await ledger.resolve_source(
        ledger.parse_add_source_args(url=url, title="Blocked report")
    )
    assert s.title == "Blocked report"
    assert "not fetched (HTTP 403)" in (s.note or "")
