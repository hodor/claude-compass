"""Tests for `compass sources` (plugin/cli/commands/sources.py) - TASK-121
of PLAN-018-research-covers-the-whole-spec
(SPEC-023-research-covers-the-whole-spec D-03, D-09).

Written before `commands/sources.py` exists. The task's own contract fixes
two behaviors: a plain `compass sources` call prints one row per shipped
entry (the `sources` section of `sourceslib.load_sources()`, never the
`do_not_try` record) and exits 0; `compass sources --check` classifies a
probed source by the shape of its response body, never by status code
alone, because a walled source can answer a 200 status with an HTML
challenge page (dblp.org, scholar.archive.org) while a throttled one can
answer a non-200 status with a genuine JSON body (Semantic Scholar's
429-asking-for-a-key). The task also fixes that this classification runs
through a pure function "separable from the network", and that a probe
never runs at all for a `reachable: browser` entry (reported "browser-only"
instead) or for a `do_not_try` entry (never checked), and never runs live
without an explicit `--live` flag.

These tests pin the contract this task's own text and its automated-
verification bullets state, choosing `classify_response(status, content_type,
body)` as the pure function's shape (following `commands/models.py`'s
`import modelslib` style, this file assumes `commands/sources.py` does
`import sourceslib`) and `run(args)` as the command's entry point, matching
every other `commands/*.py` module in this CLI.

Adversarial classes: a naive classifier that keys off `status == 200`
instead of the body; a naive classifier that trusts a `Content-Type` header
instead of sniffing the body it claims to describe; a `run()` that computes
a correct verdict but never surfaces it (or hardcodes one); a `run()` that
probes a browser-only or do-not-try entry anyway, burning a call the task
says must never happen; and a `--check` with no `--live` that still opens a
connection, breaking the hermetic-suite guarantee the task states in plain
words.
"""

import io
import json
import os
import re
import sys
import unittest
import urllib.request
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sourceslib  # noqa: E402
from commands import sources  # noqa: E402


# A recorded 200-status body that isn't real data - the shape dblp.org and
# scholar.archive.org actually answer scripted calls with, per
# sources.yaml's own `check_request` lines.
CHALLENGE_HTML = (
    "<html><head><title>Just a moment...</title></head>"
    "<body>Checking your browser before accessing dblp.org.</body></html>"
)

REAL_JSON_PAYLOAD = json.dumps({"result": {"hits": [{"id": "x"}]}, "total": 1})


class ClassifyResponseTests(unittest.TestCase):
    """`classify_response(status, content_type, body)` is the pure,
    network-free classifier the task requires so `--check`'s judgment call
    is testable without a live connection. One behavior, one test, cases as
    table rows (test-design: "cases are rows, not tests")."""

    def test_classifies_by_body_shape_not_status_code(self):
        cases = [
            (
                "genuine_json_at_200",
                200, "application/json", REAL_JSON_PAYLOAD,
                "reachable",
                "Adversarial where: the happy path anyone would get right - "
                "a 200 status carrying a real JSON payload.",
            ),
            (
                "challenge_page_at_200",
                200, "text/html", CHALLENGE_HTML,
                "unreachable",
                "Adversarial where: a classifier that reads success straight "
                "off the status code would call this reachable, exactly the "
                "false-healthy verdict D-03 exists to rule out - the status "
                "is 200 but the body is a bot-challenge page, not data.",
            ),
            (
                "html_body_with_lying_json_header",
                200, "application/json", CHALLENGE_HTML,
                "unreachable",
                "Adversarial where: a classifier that trusts the declared "
                "Content-Type header instead of sniffing the body it claims "
                "to describe would call this reachable - the header says "
                "JSON, but the body is the same HTML challenge page as "
                "above. Asymmetric input: only the header field is wrong.",
            ),
            (
                "empty_body_at_200",
                200, "application/json", "",
                "unreachable",
                "Adversarial where: the boundary of the body-present "
                "equivalence class - a 200 status with a Content-Type "
                "claiming JSON but nothing in the body has no JSON to "
                "parse, so it cannot be evidence of a working source.",
            ),
            (
                "genuine_json_at_403",
                403, "application/json", json.dumps({"message": "forbidden"}),
                "reachable",
                "Adversarial where: a classifier gating on status code "
                "(e.g. 'if status != 200: unreachable') would call this "
                "unreachable - the same shape Semantic Scholar's own "
                "documented 429-with-a-JSON-body answer takes in "
                "sources.yaml, recorded there as script-reachable anyway "
                "because the body proves the endpoint speaks JSON.",
            ),
        ]
        for name, status, content_type, body, expected, claim in cases:
            with self.subTest(case=name):
                result = sources.classify_response(status, content_type, body)
                self.assertEqual(
                    result, expected,
                    f"{name}: {claim}\ngot {result!r}, expected {expected!r}",
                )


# --- run() fixtures -------------------------------------------------------

PLAIN_LISTING_CATALOG = {
    "sources": [
        {"name": "Alpha API", "reachable": "script", "retriever": "fetch_alpha"},
        {"name": "Beta Site", "reachable": "browser", "retriever": "fetch_beta"},
    ],
    "do_not_try": [
        {"name": "Dead One", "reason": "gone (tested 2026-09-13)"},
    ],
}

SCRIPT_ONLY_CATALOG = {
    "sources": [
        {"name": "Alpha API", "reachable": "script", "retriever": "fetch_alpha"},
    ],
    "do_not_try": [],
}

BROWSER_ONLY_CATALOG = {
    "sources": [
        {"name": "Beta Site", "reachable": "browser", "retriever": "fetch_beta"},
    ],
    "do_not_try": [],
}

DO_NOT_TRY_ONLY_CATALOG = {
    "sources": [],
    "do_not_try": [
        {"name": "Dead One", "reason": "gone (tested 2026-09-13)"},
    ],
}


def _network_touched(*args, **kwargs):
    raise AssertionError(
        "compass sources opened a live connection when the contract "
        "forbids it for this call"
    )


def _fake_json_response(status, content_type, body_text):
    response = mock.MagicMock()
    response.status = status
    response.getcode.return_value = status
    response.headers = {"Content-Type": content_type}
    response.read.return_value = body_text.encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


class PlainListingTests(unittest.TestCase):
    """`compass sources` with no `--check` - the task's own words: "prints
    one row per shipped entry and exits 0.\""""

    def test_lists_shipped_entries_only_and_excludes_do_not_try(self):
        """Adversarial where: a plain listing that iterates both catalog
        sections instead of only `sources` would print a do-not-try record
        - kept in the file only as a dead-source note, never something a
        research run should reach - as if it were a live, shipped entry."""
        with mock.patch(
            "commands.sources.sourceslib.load_sources",
            return_value=PLAIN_LISTING_CATALOG,
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                code = sources.run([])
        self.assertEqual(code, 0)
        text = out.getvalue()
        name_lines = [
            line for line in text.strip().splitlines()
            if "Alpha API" in line or "Beta Site" in line
        ]
        self.assertEqual(len(name_lines), 2, text)
        self.assertNotIn("Dead One", text)


class CheckHermeticTests(unittest.TestCase):
    """`--check` alone, without `--live`, must never open a connection -
    the task's own words: "Live calls happen only under an explicit --live
    flag, so the suite stays hermetic.\""""

    def test_check_without_live_opens_no_connection(self):
        """Adversarial where: `--check` is implemented to probe immediately
        and `--live` is read too late (or not at all) to gate it, so a bare
        `compass sources --check` in CI would make a real HTTP request."""
        with mock.patch(
            "commands.sources.sourceslib.load_sources",
            return_value=SCRIPT_ONLY_CATALOG,
        ), mock.patch.object(urllib.request, "urlopen", side_effect=_network_touched):
            out = io.StringIO()
            with redirect_stdout(out):
                code = sources.run(["--check"])
        self.assertEqual(code, 0)


class BrowserOnlySkipTests(unittest.TestCase):
    """A `reachable: browser` entry is reported without probing - the task's
    own words: "reports browser-only rather than probing.\""""

    def test_browser_only_entry_is_reported_without_probing(self):
        """Adversarial where: `--check --live` treats a browser-only entry
        like a scripted one and probes it anyway - wasted at best (the
        request only ever completes through a real browser session per
        `sourceslib.fetch_acm_digital_library`'s own docstring) and, for a
        source with rate limits, actively harmful."""
        beta_retriever = mock.Mock(side_effect=AssertionError(
            "browser-only entry's retriever was invoked; the task requires "
            "it be reported without probing"
        ))
        with mock.patch(
            "commands.sources.sourceslib.load_sources",
            return_value=BROWSER_ONLY_CATALOG,
        ), mock.patch.dict(sourceslib.RETRIEVERS, {"fetch_beta": beta_retriever}):
            out = io.StringIO()
            with redirect_stdout(out):
                code = sources.run(["--check", "--live"])
        self.assertEqual(code, 0)
        self.assertIn("browser-only", out.getvalue())
        beta_retriever.assert_not_called()


class DoNotTrySkipTests(unittest.TestCase):
    """A `do_not_try` entry is never checked - the task's own words: "a
    do-not-try entry never checked.\""""

    def test_do_not_try_entry_is_never_probed_or_printed_under_check(self):
        """Adversarial where: a future refactor that widens `--check` to
        walk both catalog sections (symmetric with the plain-listing defect
        class above, but at the probing layer instead of the printing
        layer) would open a connection to a source the catalog already
        recorded as dead."""
        with mock.patch(
            "commands.sources.sourceslib.load_sources",
            return_value=DO_NOT_TRY_ONLY_CATALOG,
        ), mock.patch.object(urllib.request, "urlopen", side_effect=_network_touched):
            out = io.StringIO()
            with redirect_stdout(out):
                code = sources.run(["--check", "--live"])
        self.assertEqual(code, 0)
        self.assertNotIn("Dead One", out.getvalue())


class CheckLiveWiringTests(unittest.TestCase):
    """`--check --live` on a scripted entry must surface
    `classify_response`'s actual verdict, not a status-derived or hardcoded
    one - exercised at both ends of the classifier's outcome so a stub that
    always prints one label cannot pass both."""

    def test_reachable_json_source_reports_reachable(self):
        """Adversarial where: `run()` computes a verdict but never wires it
        into the printed row, or derives its own verdict from the HTTP
        status instead of calling `classify_response`."""
        retriever = mock.Mock(return_value=urllib.request.Request("https://example.org/alpha"))
        response = _fake_json_response(200, "application/json", REAL_JSON_PAYLOAD)
        with mock.patch(
            "commands.sources.sourceslib.load_sources",
            return_value=SCRIPT_ONLY_CATALOG,
        ), mock.patch.dict(sourceslib.RETRIEVERS, {"fetch_alpha": retriever}), \
           mock.patch.object(urllib.request, "urlopen", return_value=response):
            out = io.StringIO()
            with redirect_stdout(out):
                code = sources.run(["--check", "--live"])
        self.assertEqual(code, 0)
        retriever.assert_called_once()
        self.assertTrue(
            re.search(r"\breachable\b", out.getvalue()),
            out.getvalue(),
        )

    def test_challenge_page_source_reports_unreachable_despite_200(self):
        """Adversarial where: the same wiring path prints "reachable" for
        any 200 response regardless of body - this pins the negative branch
        the previous test's row alone could not: a stub that always prints
        "reachable" passes the happy-path test but must fail this one."""
        retriever = mock.Mock(return_value=urllib.request.Request("https://example.org/alpha"))
        response = _fake_json_response(200, "text/html", CHALLENGE_HTML)
        with mock.patch(
            "commands.sources.sourceslib.load_sources",
            return_value=SCRIPT_ONLY_CATALOG,
        ), mock.patch.dict(sourceslib.RETRIEVERS, {"fetch_alpha": retriever}), \
           mock.patch.object(urllib.request, "urlopen", return_value=response):
            out = io.StringIO()
            with redirect_stdout(out):
                code = sources.run(["--check", "--live"])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertTrue(re.search(r"\bunreachable\b", text), text)
        self.assertFalse(re.search(r"(?<!un)\breachable\b", text), text)


if __name__ == "__main__":
    unittest.main()
