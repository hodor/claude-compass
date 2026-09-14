"""`compass sources` - the curated research-source catalog
(SPEC-023-research-covers-the-whole-spec D-03, D-09).

A plain call prints one row per shipped entry from `sourceslib.load_sources()`'s
`sources` section - name, reachability class, key requirement, and access
mechanics - and never the `do_not_try` record, which stays a dead-source note
rather than something a research run reaches.

`--check` probes each `script`-reachable entry through its own dedicated
retriever in `sourceslib.RETRIEVERS` and classifies the response by the shape
of its body via `classify_response`, never by status code or the declared
content-type header alone: a walled source can answer 200 status with a bot
challenge page in place of data. A `browser` entry is reported browser-only
without probing, and a `do_not_try` entry is never checked. Without `--live`,
`--check` opens no network connection at all, so the test suite stays
hermetic.
"""

import json
import sys
import urllib.error
import urllib.request

import sourceslib

# Passed to a retriever that requires a subject DOI (Unpaywall, ACM Digital
# Library) when no specific paper is being checked - a real, resolvable DOI
# already used as the test case throughout this catalog's own source
# research (RESEARCH-source-inventory.md).
PROBE_DOI = "10.1145/3411764.3445518"

HTML_MARKERS = ("<html", "<!doctype html")


def classify_response(status, content_type, body):
    """Classify a probed response by the shape of its body alone. `status`
    and `content_type` are accepted but never consulted: a walled source can
    answer a 200 status, or a header declaring JSON, while serving an HTML
    challenge page in place of data. A body that parses as JSON, or that
    opens with `{`, `[`, or `<?xml` once leading whitespace is stripped, is
    the shape a curated source's own API actually returns and is reachable.
    A body carrying an HTML marker anywhere, with no parseable JSON, is a
    challenge or interstitial page and is unreachable. An empty body is
    unreachable."""
    text = (body or "").strip()
    if not text:
        return "unreachable"
    try:
        json.loads(text)
        return "reachable"
    except ValueError:
        pass
    if text.startswith(("{", "[", "<?xml")):
        return "reachable"
    if any(marker in text.lower() for marker in HTML_MARKERS):
        return "unreachable"
    return "reachable"


def _probe(entry):
    """Call the entry's dedicated retriever for a request, issue it, and
    classify the response body. A retriever that requires a subject
    argument (Unpaywall's DOI) is retried with `PROBE_DOI` once a bare call
    raises `TypeError` for a missing positional. Any failure along the way -
    a network error, a timeout, a second `TypeError` from a retriever needing
    more than one argument - becomes this entry's own error row rather than
    aborting the rows for every other entry still to print."""
    retriever = sourceslib.RETRIEVERS.get(entry.get("retriever"))
    if retriever is None:
        return "error: no retriever registered"
    try:
        try:
            request = retriever()
        except TypeError:
            request = retriever(PROBE_DOI)
        try:
            with urllib.request.urlopen(request) as response:
                status = response.getcode()
                content_type = response.headers.get("Content-Type", "")
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            # `urlopen` raises for any non-2xx status instead of returning a
            # response, but the raised error is itself a response: its body
            # is read the same way to be classified the same way, so a
            # throttled or forbidden status carrying a real payload (Semantic
            # Scholar's 429, an ACM-style 403) is judged on that payload
            # rather than reported as a bare error.
            status = exc.code
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
            body = exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return f"error: {exc}"
    return classify_response(status, content_type, body)


def _print_rows(rows):
    if not rows:
        return
    widths = [max(len(row[col]) for row in rows) for col in range(len(rows[0]))]
    for row in rows:
        line = "  ".join(cell.ljust(width) for cell, width in zip(row, widths))
        sys.stdout.write(line.rstrip() + "\n")


def run(args):
    check = "--check" in args
    live = "--live" in args
    catalog = sourceslib.load_sources()
    entries = catalog.get("sources", [])

    if not check:
        rows = [("name", "reachable", "key_requirement", "access")]
        for entry in entries:
            rows.append((
                entry.get("name", ""),
                entry.get("reachable", ""),
                entry.get("key_requirement", ""),
                entry.get("access", ""),
            ))
        _print_rows(rows)
        return 0

    rows = [("name", "verdict")]
    for entry in entries:
        name = entry.get("name", "")
        if entry.get("reachable") == "browser":
            rows.append((name, "browser-only"))
            continue
        if not live:
            rows.append((name, "unchecked (pass --live to probe)"))
            continue
        rows.append((name, _probe(entry)))
    _print_rows(rows)
    return 0
