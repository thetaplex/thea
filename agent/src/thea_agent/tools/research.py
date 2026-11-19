"""Network-facing research tools. `fetch_url` is auto-approved (read-only), so the SSRF
guard here must hold for the initial URL, every resolved address and every redirect hop."""

import asyncio
import io
import ipaddress
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from html import unescape
from urllib.parse import quote, unquote, urljoin, urlsplit

import httpx
from pydantic import BaseModel
from pydantic_ai import ModelRetry, RunContext, ToolFailed
from pypdf import PdfReader

from thea_agent.deps import TurnDeps

FETCH_DEFAULT_CHARS = 6000
FETCH_MAX_CHARS = 20000
FETCH_HEADER_ROOM = 1000  # room left for the fetch header and the truncation marker
HTTP_TIMEOUT = 15.0
PDF_TIMEOUT = 30.0
SEARCH_BACKOFF = 2.0  # seconds, times the attempt number
SEARCH_MAX = 10
USER_AGENT = "Thea/0.1 (+https://github.com/thetaplex/thea)"
MAX_REDIRECTS = 5
MAX_BODY_BYTES = 5 * 1024 * 1024
TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def _new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=False,
    )


# Tests swap this for a client on `httpx.MockTransport`.
client_factory: Callable[[], httpx.AsyncClient] = _new_client


class HttpStatusError(ToolFailed):
    """The server answered, with an error status."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


async def resolve_host(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=0, proto=0, family=0
    )
    return [i[4][0] for i in infos]


def ip_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return ip_is_public(ip.ipv4_mapped)
    # is_global is false for loopback, private, link-local (incl. 169.254.169.254),
    # unique-local, CGNAT, unspecified and reserved ranges.
    return ip.is_global and not ip.is_multicast


def is_public_http_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not host:
        return False
    try:
        return ip_is_public(ipaddress.ip_address(host))
    except ValueError:
        pass
    d = host.rstrip(".").lower()
    return not (
        not d or d == "localhost" or d.endswith((".localhost", ".local", ".internal"))
    )


async def resolves_public(url: str) -> bool:
    if not is_public_http_url(url):
        return False
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        addrs = await resolve_host(parts.hostname or "", port)
        return bool(addrs) and all(
            ip_is_public(ipaddress.ip_address(a.split("%")[0])) for a in addrs
        )
    except (OSError, ValueError):
        return False


# --- html to text ---

_RE_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_RE_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_RE_DROP = re.compile(
    r"<(script|style|nav|header|footer|aside|noscript|title)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_RE_BLOCK = re.compile(r"</?(?:br|p|div|li|h[1-6]|tr)\b[^>]*>", re.IGNORECASE)
_RE_TAG = re.compile(r"<[^>]*>", re.DOTALL)


def html_to_text(html: str) -> tuple[str | None, str]:
    m = _RE_TITLE.search(html)
    title = unescape(_RE_TAG.sub("", m[1])).strip() if m else ""
    s = _RE_COMMENT.sub("", html)
    s = _RE_DROP.sub("", s)
    s = _RE_BLOCK.sub("\n", s)
    s = unescape(_RE_TAG.sub("", s))
    out: list[str] = []
    blank = False
    for line in (ln.strip() for ln in s.splitlines()):
        if not line:
            blank = bool(out)
            continue
        if blank:
            out.append("")
            blank = False
        out.append(line)
    return title or None, "\n".join(out)


def truncate_marked(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return (
        f"{text[:max_chars]}\n[truncated at {max_chars} chars; "
        "ask with a larger max_chars or a narrower question]"
    )


# --- fetch_url ---


class Fetched(BaseModel):
    title: str | None
    url: str
    fetched_at: str
    text: str
    content_type: str


async def _pdf_text(body: bytes) -> str:
    def extract() -> str:
        return "\n".join(
            p.extract_text() or "" for p in PdfReader(io.BytesIO(body)).pages
        )

    # ponytail: timeout abandons the worker thread, it is not killed; fine for a 5 MB cap
    try:
        return await asyncio.wait_for(asyncio.to_thread(extract), PDF_TIMEOUT)
    except TimeoutError as e:
        raise ToolFailed(f"pdf extraction timed out after {PDF_TIMEOUT:.0f}s") from e
    except Exception as e:  # pypdf raises its own hierarchy plus assorted parse errors
        raise ToolFailed(f"pdf extraction failed: {e}") from e


async def fetch(url: str, max_chars: int) -> Fetched:
    current = url.strip()
    try:
        httpx.URL(current)
    except httpx.InvalidURL as e:
        raise ToolFailed(f"invalid URL: {e}") from e
    # ponytail: DNS is checked per hop before connect; rebinding between check and connect is a known ceiling, fix = custom transport resolver
    try:
        async with client_factory() as client:
            for hop in range(MAX_REDIRECTS + 1):
                if not await resolves_public(current):
                    raise ToolFailed(
                        f"fetch_url refuses non-public or non-http(s) URLs: {current}"
                    )
                async with client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        loc = resp.headers.get("location")
                        if not loc:
                            raise ToolFailed(
                                f"redirect without a usable Location at {current}"
                            )
                        if hop == MAX_REDIRECTS:
                            raise ToolFailed("too many redirects")
                        current = urljoin(current, loc)
                        continue
                    if resp.status_code >= 400:
                        raise HttpStatusError(
                            f"{current} answered HTTP {resp.status_code}",
                            resp.status_code,
                        )
                    content_type = resp.headers.get("content-type", "")
                    if int(resp.headers.get("content-length") or 0) > MAX_BODY_BYTES:
                        raise ToolFailed("response larger than 5 MB")
                    body = bytearray()
                    async for chunk in resp.aiter_bytes():
                        body += chunk
                        if len(body) > MAX_BODY_BYTES:
                            raise ToolFailed("response larger than 5 MB")
                    break
    except httpx.HTTPError as e:
        raise ToolFailed(f"fetch failed for {current}: {e or type(e).__name__}") from e
    if "pdf" in content_type.lower() or body.startswith(b"%PDF"):
        title, text = None, await _pdf_text(bytes(body))
    else:
        title, text = html_to_text(body.decode("utf-8", errors="replace"))
    return Fetched(
        title=title,
        url=current,
        fetched_at=datetime.now(UTC).isoformat(),
        text=truncate_marked(text, min(FETCH_MAX_CHARS, max(500, max_chars))),
        content_type=content_type,
    )


def format_fetched(f: Fetched) -> str:
    return f"Title: {f.title or ''}\nURL: {f.url}\nFetched: {f.fetched_at}\n\n{f.text}"


async def fetch_url(
    ctx: RunContext[TurnDeps], url: str, max_chars: int = FETCH_DEFAULT_CHARS
) -> str:
    """Fetch a web page or PDF and return its text. Public http(s) URLs only.

    Args:
        url: The URL to fetch.
        max_chars: Maximum characters of text to return.
    """
    cap = max(0, ctx.deps.tool_output_chars - FETCH_HEADER_ROOM)
    return format_fetched(await fetch(url, min(max_chars, cap)))


# --- web_search ---


class SearchHit(BaseModel):
    title: str
    url: str
    snippet: str = ""


_RE_DDG_RESULT = re.compile(
    r'<a\b[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_RE_DDG_SNIPPET = re.compile(
    r'<a\b[^>]*class="result__snippet"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL
)


def percent_decode(s: str) -> str:
    return unquote(s)  # leaves `+` alone, like URL path semantics


def _ddg_target(href: str) -> str | None:
    _, sep, rest = href.replace("&amp;", "&").partition("uddg=")
    return percent_decode(rest.split("&")[0]) if sep else None


def parse_duckduckgo_html(html: str, max_hits: int) -> list[SearchHit]:
    results = list(_RE_DDG_RESULT.finditer(html))
    hits: list[SearchHit] = []
    for i, m in enumerate(results):
        if len(hits) >= min(max(max_hits, 1), SEARCH_MAX):
            break
        url = _ddg_target(m[1])
        if not url or not is_public_http_url(url):
            continue
        end = results[i + 1].start() if i + 1 < len(results) else len(html)
        sm = _RE_DDG_SNIPPET.search(html, m.end(), end)
        hits.append(
            SearchHit(
                title=html_to_text(m[2])[1],
                url=url,
                snippet=html_to_text(sm[1])[1] if sm else "",
            )
        )
    return hits


def parse_hits_json(body: str, max_hits: int) -> list[SearchHit]:
    """SearXNG and Tavily share the `{"results": [{url, title, content}]}` shape."""
    try:
        results = json.loads(body)["results"]
        return [
            SearchHit(
                title=r.get("title", ""),
                url=r["url"],
                snippet=truncate_marked(r.get("content", ""), 400),
            )
            for r in results
            if is_public_http_url(r["url"])
        ][: min(max(max_hits, 1), SEARCH_MAX)]
    except (TypeError, KeyError, AttributeError) as e:
        raise ValueError(f"unexpected search response: {e}") from e


async def searxng_search(base_url: str, query: str, n: int) -> list[SearchHit]:
    async with client_factory() as c:
        r = await c.get(
            f"{base_url.rstrip('/')}/search", params={"q": query, "format": "json"}
        )
    r.raise_for_status()
    return parse_hits_json(r.text, n)


async def tavily_search(query: str, n: int) -> list[SearchHit]:
    """Keyless mode: no account, rate limited, queries leave the machine."""
    async with client_factory() as c:
        r = await c.post(
            TAVILY_SEARCH_URL,
            headers={"X-Tavily-Access-Mode": "keyless"},
            json={"query": query, "max_results": min(max(n, 1), SEARCH_MAX)},
        )
    if not r.is_success:
        raise ValueError(f"HTTP {r.status_code}: {truncate_marked(r.text, 120)}")
    return parse_hits_json(r.text, n)


async def duckduckgo_search(query: str, n: int) -> list[SearchHit]:
    # ponytail: fixed 3-attempt backoff; a per-process rate limiter if throttling persists
    async with client_factory() as c:
        for attempt in range(3):
            if attempt:
                await asyncio.sleep(SEARCH_BACKOFF * attempt)
            r = await c.get("https://html.duckduckgo.com/html/", params={"q": query})
            r.raise_for_status()
            hits = parse_duckduckgo_html(r.text, n)
            # Neither results nor DuckDuckGo's own "no results" marker means a bot
            # challenge or rate limit, not an empty result set.
            if hits or "result__a" in r.text or "no-results" in r.text:
                return hits
    raise ValueError("duckduckgo is rate limiting this app")


async def search_one(searxng_url: str, query: str, n: int) -> list[SearchHit]:
    """Providers in order: local SearXNG, Tavily keyless, DuckDuckGo. The first with
    results wins; an empty result set counts as a failure so the next one is tried."""
    failures: list[str] = []
    providers = [
        *(
            [("searxng", lambda: searxng_search(searxng_url, query, n))]
            if searxng_url.strip()
            else []
        ),
        ("tavily", lambda: tavily_search(query, n)),
        ("duckduckgo", lambda: duckduckgo_search(query, n)),
    ]
    for name, run in providers:
        try:
            if hits := await run():
                return hits
            failures.append(f"{name}: no results")
        except (httpx.HTTPError, ValueError) as e:
            failures.append(f"{name}: {e or type(e).__name__}")
    raise ToolFailed(
        f"web search failed on every provider ({'; '.join(failures)}). "
        "Do not retry the same query. Use lookup_paper for known papers, fetch_url for URLs you "
        "already have, or go on to the next TASK.md item. If SearXNG is not running, start it with `just searxng`"
    )


def format_hits(hits: list[SearchHit]) -> str:
    if not hits:
        return "No results."
    return "".join(
        f"{i}. {h.title}\n   {h.url}\n   {h.snippet}\n" for i, h in enumerate(hits, 1)
    )


async def web_search(
    ctx: RunContext[TurnDeps], query: str | list[str], max_results: int | None = None
) -> str:
    """Search the web; returns titles, URLs and snippets.

    Args:
        query: What to search for.
        max_results: Maximum number of results to return.
    """
    queries = [query] if isinstance(query, str) else query
    queries = [q.strip() for q in queries if isinstance(q, str) and q.strip()]
    if not queries:
        raise ModelRetry(
            'web_search needs a `query` string, for example {"query": "causes of war"}'
        )
    n = min(max(max_results or ctx.deps.search_results, 1), SEARCH_MAX)
    searxng_url = str(ctx.deps.settings.get("searxng_url") or "")
    hits: list[SearchHit] = []
    last_err: ToolFailed | None = None
    for q in queries[:3]:
        try:
            hits += await search_one(searxng_url, q, n)
        except ToolFailed as e:
            last_err = e
    seen: set[str] = set()
    hits = [h for h in hits if not (h.url in seen or seen.add(h.url))][:n]
    if last_err and not hits:
        raise last_err
    return format_hits(hits)


# --- lookup_paper ---


class PaperRecord(BaseModel):
    title: str
    authors: list[str] = []
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str
    summary: str | None = None


PaperQuery = tuple[str, str]  # ("doi" | "title" | "arxiv", value)


def parse_paper_query(
    doi: str | None, title: str | None, arxiv_id: str | None
) -> PaperQuery:
    def arxiv(s: str) -> PaperQuery:
        i = s[6:] if s[:6].lower() == "arxiv:" else s
        if not i.strip():
            raise ModelRetry("empty arXiv id")
        return "arxiv", i.strip()

    a, d, t = ((x or "").strip() for x in (arxiv_id, doi, title))
    if a:
        return arxiv(a)
    if d:
        if d[:6].lower() == "arxiv:":
            return arxiv(d)
        for p in ("https://doi.org/", "http://dx.doi.org/"):
            d = d.removeprefix(p)
        return "doi", d
    if t:
        return "title", t
    raise ModelRetry("provide a doi, title or arxiv_id")


def _summarize(s: str) -> str | None:
    return s.strip()[:800] or None


def _strip_markup(s: str) -> str:
    return unescape(_RE_TAG.sub("", s)).strip()


def _get(v, *path):
    """Safe nested lookup over dicts and lists; None when any step is missing."""
    for p in path:
        try:
            v = v[p]
        except (KeyError, IndexError, TypeError):
            return None
    return v


def parse_openalex_work(v: dict) -> PaperRecord | None:
    title = v.get("title") if isinstance(v, dict) else None
    if not title:
        return None
    doi = (v.get("doi") or "").removeprefix("https://doi.org/") or None
    words = sorted(
        (p, w)
        for w, pos in (v.get("abstract_inverted_index") or {}).items()
        for p in pos
    )
    url = f"https://doi.org/{doi}" if doi else v.get("id")
    if not url:
        return None
    return PaperRecord(
        title=title,
        authors=[
            n
            for a in v.get("authorships") or []
            if (n := _get(a, "author", "display_name"))
        ],
        year=v.get("publication_year"),
        venue=_get(v, "primary_location", "source", "display_name"),
        doi=doi,
        url=url,
        summary=_summarize(" ".join(w for _, w in words)),
    )


def parse_crossref_work(v: dict) -> PaperRecord | None:
    """`v` is the Crossref envelope: `{"message": <work>}`."""
    m = v.get("message") or {}
    title = _get(m, "title", 0)
    doi = m.get("DOI")
    url = m.get("URL") or (f"https://doi.org/{doi}" if doi else None)
    if not title or not url:
        return None
    authors = [
        f"{a.get('given', '')} {a.get('family', '')}".strip()
        for a in m.get("author") or []
    ]
    abstract = m.get("abstract")
    return PaperRecord(
        title=title,
        authors=[a for a in authors if a],
        year=_get(m, "issued", "date-parts", 0, 0),
        venue=_get(m, "container-title", 0),
        doi=doi,
        url=url,
        summary=_summarize(_strip_markup(abstract)) if abstract else None,
    )


def _xml_field(entry: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", entry, re.DOTALL)
    return " ".join(_strip_markup(m[1]).split()) if m else None


def parse_arxiv_atom(xml: str) -> PaperRecord | None:
    m = re.search(r"<entry>(.*?)</entry>", xml, re.DOTALL)
    if not m:
        return None
    e = m[1]
    # arXiv answers a malformed id with an <entry> titled "Error" whose id is an
    # /api/errors URL; that is not a paper.
    url, title = _xml_field(e, "id"), _xml_field(e, "title")
    if not url or "/api/errors" in url or not title or title == "Error":
        return None
    published = _xml_field(e, "published") or ""
    return PaperRecord(
        title=title,
        authors=[
            _strip_markup(n) for n in re.findall(r"<name>(.*?)</name>", e, re.DOTALL)
        ],
        year=int(published[:4]) if published[:4].isdigit() else None,
        venue="arXiv",
        url=url,
        summary=_summarize(_xml_field(e, "summary") or ""),
    )


def title_similarity(a: str, b: str) -> float:
    def toks(s: str) -> set[str]:
        return {t for t in re.split(r"\W+", s.lower()) if t}

    ta, tb = toks(a), toks(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def encode_path_segment(s: str) -> str:
    """Escape everything except unreserved characters and `/`, so `?` and `#` in a DOI stay in the path."""
    return quote(s, safe="/-._~")


def openalex_doi_url(doi: str) -> str:
    return f"https://api.openalex.org/works/https://doi.org/{encode_path_segment(doi)}"


def crossref_doi_url(doi: str) -> str:
    return f"https://api.crossref.org/works/{encode_path_segment(doi)}"


def gate_title(query: str, rec: PaperRecord | None) -> PaperRecord | None:
    """A title hit only counts when it is close enough to what was asked for."""
    return rec if rec and title_similarity(query, rec.title) >= 0.6 else None


async def api_get(url: str, params: dict[str, str] | None = None) -> str | None:
    """GET returning the body, or None on 404."""
    try:
        async with client_factory() as c:
            r = await c.get(url, params=params)
    except httpx.HTTPError as e:
        raise ToolFailed(f"lookup failed for {url}: {e or type(e).__name__}") from e
    if r.status_code == 404:
        return None
    if r.is_error:
        raise HttpStatusError(f"{url} answered HTTP {r.status_code}", r.status_code)
    return r.text


async def api_json(url: str, params: dict[str, str] | None = None):
    body = await api_get(url, params)
    try:
        return None if body is None else json.loads(body)
    except ValueError as e:
        raise ToolFailed(f"{url} returned invalid JSON") from e


async def _openalex(kind: str, value: str) -> PaperRecord | None:
    if kind == "doi":
        v = await api_json(openalex_doi_url(value))
        return parse_openalex_work(v) if v else None
    v = await api_json(
        "https://api.openalex.org/works", {"search": value, "per-page": "1"}
    )
    return parse_openalex_work(_get(v, "results", 0)) if v else None


async def _crossref(kind: str, value: str) -> PaperRecord | None:
    if kind == "doi":
        v = await api_json(crossref_doi_url(value))
        return parse_crossref_work(v) if v else None
    v = await api_json(
        "https://api.crossref.org/works",
        {"query.bibliographic": value, "rows": "1"},
    )
    item = _get(v, "message", "items", 0)
    return parse_crossref_work({"message": item}) if item else None


async def find_paper(q: PaperQuery) -> PaperRecord | None:
    """None means not found; ToolFailed only when every source failed in transport."""
    kind, value = q
    if kind == "arxiv":
        xml = await api_get("https://export.arxiv.org/api/query", {"id_list": value})
        return parse_arxiv_atom(xml) if xml else None

    def gate(r: PaperRecord | None) -> PaperRecord | None:
        return gate_title(value, r) if kind == "title" else r

    try:
        if r := gate(await _openalex(kind, value)):
            return r
    except ToolFailed:
        pass
    return gate(await _crossref(kind, value))


def format_paper(p: PaperRecord) -> str:
    out = f"{p.title}\n"
    if p.authors:
        out += f"Authors: {', '.join(p.authors)}\n"
    if published := [str(x) for x in (p.venue, p.year) if x]:
        out += f"Published: {', '.join(published)}\n"
    if p.doi:
        out += f"DOI: {p.doi}\n"
    out += f"URL: {p.url}\n"
    if p.summary:
        out += f"Summary: {p.summary}\n"
    return out


async def lookup_paper(
    ctx: RunContext[TurnDeps],
    doi: str | None = None,
    title: str | None = None,
    arxiv_id: str | None = None,
) -> str:
    """Look up a scholarly paper by DOI, title or arXiv id; use to verify a paper exists and get its metadata.

    Args:
        doi: DOI of the paper.
        title: Title of the paper.
        arxiv_id: arXiv identifier, e.g. 2303.11366.
    """
    paper = await find_paper(parse_paper_query(doi, title, arxiv_id))
    return format_paper(paper) if paper else "No matching paper found."
