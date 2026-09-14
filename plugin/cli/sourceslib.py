"""Curated research-source catalog and per-source retrievers
(SPEC-023-research-covers-the-whole-spec D-03, D-09).

Reads `sources.yaml`, the row-based catalog next to this module, in the same
hand-rolled style `lessonslib.py:parse_catalog` and
`modelslib.py:parse_models_yaml` use for their own YAML-shaped files. The
file holds two sections: `sources`, the curated starting list a research
run reaches first, and `do_not_try`, sources tested and found dead or
closed rather than dropped from the record. Each active entry names a
`retriever`, a key into the module-level `RETRIEVERS` dict of callables
that build the request a source-checking command executes and classifies
by response content, not status code alone.
"""

import re
import urllib.parse
import urllib.request
from pathlib import Path

# A section header sits at zero indent (`sources:` or `do_not_try:`); each
# row starts `  - name: "..."` two spaces in, and every other field of that
# row is `    key: value` four spaces in - one section, one row, one field
# per line, the same nesting `lessonslib.py`'s `ROW_START`/`FIELD` read for
# the lessons catalog.
SECTION = re.compile(r'^([A-Za-z_]+):\s*$')
ROW_START = re.compile(r'^  - name:\s*(.*)$')
FIELD = re.compile(r'^    ([A-Za-z0-9_]+):\s*(.*)$')

SECTIONS = ("sources", "do_not_try")

USER_AGENT = "Mozilla/5.0 (compass-research)"


def _unquote(value):
    """Strip a trailing `#` comment sitting outside any quoted span, then
    strip one layer of matching quotes from what remains. A `#` reached
    while inside a quoted span is part of the value, not a comment."""
    value = value.strip()
    in_quotes = False
    quote_char = None
    comment_at = None
    for i, ch in enumerate(value):
        if in_quotes:
            if ch == quote_char:
                in_quotes = False
        elif ch in "\"'":
            in_quotes = True
            quote_char = ch
        elif ch == "#":
            comment_at = i
            break
    if comment_at is not None:
        value = value[:comment_at].rstrip()
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        return value[1:-1]
    return value


def parse_sources(text):
    """Parse the `sources.yaml` catalog shape.

    Returns `{"sources": [...], "do_not_try": [...]}`, one dict per row in
    file order, holding whatever fields that row's lines carried. A row
    missing a field simply omits that key rather than defaulting it, so a
    gap on one row can never read as present.
    """
    result = {name: [] for name in SECTIONS}
    section = None
    entry = None

    def flush():
        nonlocal entry
        if entry is not None and section in result:
            result[section].append(entry)
        entry = None

    for line in text.splitlines():
        if not line.strip():
            continue
        section_match = SECTION.match(line)
        if section_match and section_match.group(1) in SECTIONS:
            flush()
            section = section_match.group(1)
            continue
        row_match = ROW_START.match(line)
        if row_match and section is not None:
            flush()
            entry = {"name": _unquote(row_match.group(1))}
            continue
        field_match = FIELD.match(line)
        if field_match and entry is not None:
            entry[field_match.group(1)] = _unquote(field_match.group(2))
            continue
    flush()
    return result


def load_sources():
    """Load the shipped `sources.yaml` next to this module."""
    path = Path(__file__).resolve().parent / "sources.yaml"
    text = path.read_text(encoding="utf-8")
    return parse_sources(text)


def _get_request(url, params=None, headers=None):
    """Build a GET `Request` for `url`, with `params` URL-encoded and a
    Compass user agent attached. Building the request is this module's
    job; issuing it and classifying the response belongs to `compass
    sources --check`."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    merged_headers = {"User-Agent": USER_AGENT}
    if headers:
        merged_headers.update(headers)
    return urllib.request.Request(url, headers=merged_headers)


def fetch_crossref(query="test", mailto=None):
    """Crossref bibliographic works search - DOI-registration metadata,
    no auth required; an optional `mailto` joins the polite pool for
    higher, prioritized limits."""
    params = {"query.bibliographic": query, "rows": "1"}
    if mailto:
        params["mailto"] = mailto
    return _get_request("https://api.crossref.org/works", params=params)


def fetch_openalex(query="test"):
    """OpenAlex works search - CC0 metadata graph, keyless but
    credit-metered per call."""
    return _get_request(
        "https://api.openalex.org/works",
        params={"search": query, "per-page": "1"},
    )


def fetch_unpaywall(doi, email="compass-research@example.org"):
    """Unpaywall OA-location lookup for one DOI - auth is only an email
    query parameter, no key."""
    return _get_request(
        f"https://api.unpaywall.org/v2/{doi}", params={"email": email}
    )


def fetch_arxiv(query="test"):
    """arXiv API search - preprint metadata and full text, no auth."""
    return _get_request(
        "http://export.arxiv.org/api/query",
        params={"search_query": f"all:{query}", "max_results": "1"},
    )


def fetch_openreview_v2(term="test"):
    """OpenReview v2 notes search - the reachable host; the legacy v1
    host answers 403 and is not used here."""
    return _get_request(
        "https://api2.openreview.net/notes/search",
        params={"term": term, "limit": "1"},
    )


def fetch_github(query="test"):
    """GitHub repository search over the general REST API, which works
    unauthenticated; code search and GraphQL require a token and are not
    what this retriever calls."""
    return _get_request(
        "https://api.github.com/search/repositories",
        params={"q": query, "per_page": "1"},
    )


def fetch_semantic_scholar(query="test", api_key=None):
    """Semantic Scholar paper search - keyless calls work but are
    throttled after the first; an `api_key` raises the floor to a
    guaranteed 1 req/sec."""
    headers = {"x-api-key": api_key} if api_key else None
    return _get_request(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={"query": query, "limit": "1"},
        headers=headers,
    )


def fetch_acm_digital_library(doi):
    """ACM Digital Library DOI landing page - Cloudflare-walled to every
    non-browser client regardless of open-access status, so this request
    only ever completes through a real browser."""
    return _get_request(f"https://dl.acm.org/doi/{doi}")


def fetch_dblp(query="test"):
    """DBLP publication search - answers HTTP 200 with a bot-challenge
    page rather than JSON to a scripted call."""
    return _get_request(
        "https://dblp.org/search/publ/api",
        params={"q": query, "format": "json"},
    )


def fetch_internet_archive_scholar(query="test"):
    """Internet Archive Scholar search - answers HTTP 200 with a
    session-verification challenge page rather than results to a scripted
    call."""
    return _get_request(
        "https://scholar.archive.org/search",
        params={"q": query, "format": "json"},
    )


# One dedicated retriever per curated source (D-09) - never a generic call
# shared across sources with a similar access shape.
RETRIEVERS = {
    "fetch_crossref": fetch_crossref,
    "fetch_openalex": fetch_openalex,
    "fetch_unpaywall": fetch_unpaywall,
    "fetch_arxiv": fetch_arxiv,
    "fetch_openreview_v2": fetch_openreview_v2,
    "fetch_github": fetch_github,
    "fetch_semantic_scholar": fetch_semantic_scholar,
    "fetch_acm_digital_library": fetch_acm_digital_library,
    "fetch_dblp": fetch_dblp,
    "fetch_internet_archive_scholar": fetch_internet_archive_scholar,
}
