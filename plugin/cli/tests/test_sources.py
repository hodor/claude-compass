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


# --- Post-build tests: defect classes only the implementation reveals ----
#
# The four sections below probe branches `commands/sources.py` introduced
# that the task text never dictated the shape of: how `_probe` reacts to
# `urllib.error.HTTPError`, how it retries a retriever that needs a subject
# argument versus one that needs more than it can supply, whether one
# entry's network failure stops the rows after it from printing, and what
# `classify_response`'s body sniff actually keys on rather than what the
# task's prose suggests it keys on.

def _fake_response(status, content_type, body_text):
    response = mock.MagicMock()
    response.getcode.return_value = status
    response.headers = {"Content-Type": content_type}
    response.read.return_value = body_text.encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


class HTTPErrorLiveTests(unittest.TestCase):
    """`urllib.request.urlopen` raises `urllib.error.HTTPError` for any
    non-2xx status rather than returning a response object - the shape a
    live probe of Semantic Scholar's own documented 429-asking-for-a-key
    answer, or a 403, actually takes. `_probe`'s `except Exception as exc:
    return f"error: {exc}"` catches `HTTPError` (a subclass of `OSError`)
    along with every other failure and stringifies it, never reading the
    body `HTTPError` itself carries as a file-like object."""

    def test_http_error_with_json_body_is_classified_not_stringified(self):
        """Adversarial where: the task's own text says a throttled source
        "can answer a non-200 status with a genuine JSON body" and that
        this must be classified by body shape, not status - but a live
        403 or 429 never reaches `classify_response` at all, because
        `urlopen` raises before returning a response, and the blanket
        `except Exception` swallows the raised `HTTPError` into a generic
        error row instead of reading `exc.read()` and classifying it. Two
        rows, both carrying a genuine JSON body, at the two statuses the
        task text names by name."""
        import urllib.error
        cases = [
            ("403_forbidden_json_body", 403, b'{"message": "forbidden"}'),
            ("429_too_many_requests_json_body", 429, b'{"message": "please get a key"}'),
        ]
        for name, status, body in cases:
            with self.subTest(case=name):
                retriever = mock.Mock(
                    return_value=urllib.request.Request("https://example.org/alpha")
                )
                err = urllib.error.HTTPError(
                    url="https://example.org/alpha", code=status,
                    msg="error", hdrs=None, fp=io.BytesIO(body),
                )
                catalog = {
                    "sources": [{"name": "Alpha API", "reachable": "script", "retriever": "fetch_alpha"}],
                    "do_not_try": [],
                }
                with mock.patch(
                    "commands.sources.sourceslib.load_sources", return_value=catalog,
                ), mock.patch.dict(
                    sourceslib.RETRIEVERS, {"fetch_alpha": retriever},
                ), mock.patch.object(urllib.request, "urlopen", side_effect=err):
                    out = io.StringIO()
                    with redirect_stdout(out):
                        code = sources.run(["--check", "--live"])
                text = out.getvalue()
                self.assertEqual(code, 0)
                self.assertTrue(
                    re.search(r"(?<!un)\breachable\b", text),
                    f"{name}: a {status} response carrying a real JSON body should "
                    f"classify reachable, per the task's own words; got {text!r}",
                )


class RetrySubjectArgumentTests(unittest.TestCase):
    """`_probe` retries a retriever that raised `TypeError` on a bare call
    with `PROBE_DOI`, the shape Unpaywall's own signature needs. Two
    distinct behaviors: the retry supplying the one argument a retriever
    needs, and the safety net when a second `TypeError` still doesn't clear
    (a retriever needing more than one positional)."""

    def test_typeerror_on_bare_call_is_retried_with_probe_doi(self):
        """Adversarial where: a retriever whose signature requires a
        subject (Unpaywall's `doi`) raises `TypeError` on a bare call; a
        `_probe` that does not retry would report that `TypeError` as this
        entry's error row instead of ever completing a request."""
        def subject_retriever(doi=None):
            if doi is None:
                raise TypeError("fetch_unpaywall() missing 1 required positional argument: 'doi'")
            return urllib.request.Request(f"https://example.org/unpaywall/{doi}")

        catalog = {
            "sources": [{"name": "Unpaywall-like", "reachable": "script", "retriever": "fetch_subject"}],
            "do_not_try": [],
        }
        response = _fake_response(200, "application/json", REAL_JSON_PAYLOAD)
        with mock.patch(
            "commands.sources.sourceslib.load_sources", return_value=catalog,
        ), mock.patch.dict(
            sourceslib.RETRIEVERS, {"fetch_subject": subject_retriever},
        ), mock.patch.object(urllib.request, "urlopen", return_value=response) as urlopen:
            out = io.StringIO()
            with redirect_stdout(out):
                code = sources.run(["--check", "--live"])
        self.assertEqual(code, 0)
        self.assertTrue(re.search(r"(?<!un)\breachable\b", out.getvalue()), out.getvalue())
        called_request = urlopen.call_args[0][0]
        self.assertIn(sources.PROBE_DOI, called_request.full_url)

    def test_retriever_needing_two_arguments_becomes_an_error_row_not_a_crash(self):
        """Adversarial where: a retriever whose `TypeError` isn't cleared
        by a single retry argument (it needs two positionals) is a case
        the task's own text does not name - `_probe`'s inner
        `try/except TypeError` only supplies one substitute argument, so
        the second `TypeError` must fall through to the outer
        `except Exception` and become this entry's own error row rather
        than propagating out of `run()` and aborting every row after it."""
        def two_arg_retriever(a, b):
            raise TypeError("fetch_needs_two() missing 1 required positional argument: 'b'")

        catalog = {
            "sources": [
                {"name": "Broken", "reachable": "script", "retriever": "fetch_broken"},
                {"name": "Alpha API", "reachable": "script", "retriever": "fetch_alpha"},
            ],
            "do_not_try": [],
        }
        good_retriever = mock.Mock(
            return_value=urllib.request.Request("https://example.org/alpha")
        )
        response = _fake_response(200, "application/json", REAL_JSON_PAYLOAD)
        with mock.patch(
            "commands.sources.sourceslib.load_sources", return_value=catalog,
        ), mock.patch.dict(
            sourceslib.RETRIEVERS,
            {"fetch_broken": two_arg_retriever, "fetch_alpha": good_retriever},
        ), mock.patch.object(urllib.request, "urlopen", return_value=response):
            out = io.StringIO()
            with redirect_stdout(out):
                code = sources.run(["--check", "--live"])
        text = out.getvalue()
        self.assertEqual(code, 0)
        broken_lines = [line for line in text.splitlines() if "Broken" in line]
        self.assertEqual(len(broken_lines), 1, text)
        self.assertIn("error:", broken_lines[0])
        self.assertTrue(re.search(r"(?<!un)\breachable\b", text), text)


class NetworkExceptionIsolationTests(unittest.TestCase):
    """One entry's network failure produces that entry's own error row
    without stopping `run()` from printing the entries after it - a
    multi-entry ordering the checkpointed tests, which use single-entry
    catalogs throughout, never exercise."""

    def test_exception_on_one_entry_does_not_suppress_rows_after_it(self):
        """Adversarial where: a `run()` that lets `_probe`'s exception
        propagate instead of catching it per-entry would abort the loop,
        silently dropping every row after the failing source - the failure
        mode the task's own text rules out by saying a probe failure
        "becomes this entry's own error row" rather than aborting the run."""
        catalog = {
            "sources": [
                {"name": "Down API", "reachable": "script", "retriever": "fetch_down"},
                {"name": "Alpha API", "reachable": "script", "retriever": "fetch_alpha"},
            ],
            "do_not_try": [],
        }
        down_retriever = mock.Mock(
            return_value=urllib.request.Request("https://example.org/down")
        )
        good_retriever = mock.Mock(
            return_value=urllib.request.Request("https://example.org/alpha")
        )

        def fake_urlopen(request, *a, **kw):
            if "down" in request.full_url:
                raise ConnectionError("connection refused")
            return _fake_response(200, "application/json", REAL_JSON_PAYLOAD)

        with mock.patch(
            "commands.sources.sourceslib.load_sources", return_value=catalog,
        ), mock.patch.dict(
            sourceslib.RETRIEVERS,
            {"fetch_down": down_retriever, "fetch_alpha": good_retriever},
        ), mock.patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
            out = io.StringIO()
            with redirect_stdout(out):
                code = sources.run(["--check", "--live"])
        text = out.getvalue()
        self.assertEqual(code, 0)
        down_lines = [line for line in text.splitlines() if "Down API" in line]
        alpha_lines = [line for line in text.splitlines() if "Alpha API" in line]
        self.assertEqual(len(down_lines), 1, text)
        self.assertIn("error:", down_lines[0])
        self.assertEqual(len(alpha_lines), 1, text)
        self.assertTrue(re.search(r"(?<!un)\breachable\b", alpha_lines[0]), text)


class ChallengeSniffKeysOnMarkupShapeTests(unittest.TestCase):
    """`classify_response` keys on the presence of an HTML marker in the
    first 200 characters of the body, never on the word "challenge" or any
    other wording - probing what the sniff actually keys on, per its own
    `HTML_MARKERS = ("<html", "<!doctype html")` constant, rather than the
    word the task's prose uses to describe the failure mode."""

    def test_html_shaped_results_page_with_no_challenge_wording_is_still_unreachable(self):
        """Adversarial where: a classifier keying on the literal word
        "challenge" would call this reachable - a real-looking results
        page, `<html>` tag and all, that never uses that word - while the
        actual sniff (any `HTML_MARKERS` string in the first 200 chars)
        still rules it out because a scripted call to a JSON/XML endpoint
        getting markup back at all is the signal, not the markup's
        wording."""
        real_looking_html = (
            "<html><body><h1>Search Results</h1>"
            "<ul><li>Paper A</li><li>Paper B</li></ul></body></html>"
        )
        result = sources.classify_response(200, "text/html", real_looking_html)
        self.assertEqual(result, "unreachable")

    def test_html_marker_past_the_200_char_sniff_window_is_missed(self):
        """Adversarial where: the sniff window is a hard 200-character
        prefix rather than a scan of the whole body, so a challenge page
        with enough leading content before its opening `<html>` tag
        evades classification entirely - exactly the false-healthy verdict
        D-03 exists to rule out, produced here not by a status code but by
        where the marker happens to sit in the response. Boundary rows:
        the marker's last byte at index 199 (inside the 200-char slice)
        against the same marker one byte later, straddling the cutoff."""
        marker_inside_window = ("x" * 195) + "<html>"
        marker_crosses_window = ("x" * 196) + "<html>"
        self.assertEqual(
            sources.classify_response(200, "text/html", marker_inside_window),
            "unreachable",
        )
        self.assertEqual(
            sources.classify_response(200, "text/html", marker_crosses_window),
            "unreachable",
            "a body that is still nothing but markup around an <html> tag "
            "is misclassified 'reachable' once the tag sits one byte past "
            "the sniff window - the window, not the shape of the body, "
            "decided the verdict",
        )


class RowCountMatchesRealCatalogTests(unittest.TestCase):
    """`compass sources` against the real shipped `sources.yaml`, not a
    fixture catalog - the checkpointed tests exercise `run()`'s logic
    entirely against mocked catalogs, so nothing yet pins that the actual
    shipped list round-trips through `run()` at exactly one row per
    entry."""

    def test_one_row_per_real_shipped_entry_no_more_no_fewer(self):
        """Adversarial where: a future edit to `sources.yaml` (adding a
        `do_not_try` row, say) or to `run()`'s filtering could change the
        printed count without any mocked-catalog test noticing, since
        every existing test supplies its own small fixture catalog."""
        catalog = sourceslib.load_sources()
        expected_names = [entry["name"] for entry in catalog["sources"]]
        out = io.StringIO()
        with redirect_stdout(out):
            code = sources.run([])
        self.assertEqual(code, 0)
        lines = [line for line in out.getvalue().strip().splitlines() if line.strip()]
        self.assertEqual(
            len(lines), len(expected_names) + 1,
            f"expected a header row plus one row per shipped entry "
            f"({len(expected_names)}); got {len(lines)} lines:\n{out.getvalue()}",
        )
        for name in expected_names:
            matching = [line for line in lines if name in line]
            self.assertEqual(len(matching), 1, f"{name!r} should appear on exactly one row")


class CLISubprocessEntryPointTests(unittest.TestCase):
    """`python plugin/cli/compass sources`, run as a real subprocess from
    the repository root - the one path that proves `COMMAND_SPECS`
    registration, the `commands.sources` module name, and `maincli.dispatch`
    all resolve together, which no in-process call to `sources.run()`
    exercises."""

    def test_compass_sources_via_launcher_exits_0_with_one_row_per_entry(self):
        """Adversarial where: the command is registered in `COMMAND_SPECS`
        (TASK-121's own contract point) but the module name, an import
        path, or the launcher's `sys.path` setup is wrong, so
        `maincli.dispatch` reports "not implemented yet" or crashes even
        though every in-process test against `sources.run()` directly
        passes."""
        import subprocess
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[3]
        launcher = repo_root / "plugin" / "cli" / "compass"
        self.assertTrue(launcher.is_file(), launcher)
        result = subprocess.run(
            [sys.executable, str(launcher), "sources"],
            cwd=str(repo_root), capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        entry_count = len(sourceslib.load_sources()["sources"])
        lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
        self.assertEqual(len(lines), entry_count + 1, result.stdout)


class ClassifyResponseBodyShapeExtraTests(unittest.TestCase):
    """`classify_response`'s body sniff against shapes the checkpointed
    table never rows: a JSON array rather than a JSON object, a genuine
    JSON payload wrapped in leading noise (a BOM, leading whitespace), an
    HTML page carrying a JSON-looking fragment inside a `<script>` tag, and
    plain text that is neither JSON nor markup at all."""

    def test_classifies_extra_body_shapes(self):
        cases = [
            (
                "json_array_body",
                200, "application/json", json.dumps([{"id": 1}, {"id": 2}]),
                "reachable",
                "Adversarial where: a classifier that only recognizes a "
                "JSON object (checking for a leading '{' before trying "
                "`json.loads`, say) would miss a source whose own API "
                "answers with a bare JSON array at the top level.",
            ),
            (
                "json_object_with_leading_bom",
                200, "application/json", "﻿" + REAL_JSON_PAYLOAD,
                "reachable",
                "Adversarial where: `str.strip()` does not remove a "
                "leading U+FEFF byte-order mark, so `json.loads` on the "
                "stripped text still raises - this pins that the body is "
                "still judged reachable through the non-markup fallback "
                "rather than being misclassified as a challenge page.",
            ),
            (
                "json_object_with_leading_whitespace",
                200, "application/json", "   \n\t" + REAL_JSON_PAYLOAD,
                "reachable",
                "Adversarial where: ordinary leading whitespace before a "
                "real JSON payload (a trailing newline from a proxy, "
                "say) must not by itself push the body into the "
                "unreachable branch.",
            ),
            (
                "html_challenge_with_json_looking_script_tag",
                200, "text/html",
                "<html><head><title>Just a moment...</title></head>"
                '<body><script>var cfg = {"ray": "abc123"};</script>'
                "Checking your browser before accessing dblp.org."
                "</body></html>",
                "unreachable",
                "Adversarial where: a classifier that searches the whole "
                "body for a JSON-looking substring instead of requiring "
                "the body itself to parse as JSON would call this "
                "reachable off the embedded `<script>` config object - "
                "the same false-healthy verdict D-03 rules out, produced "
                "here by a challenge page whose vendor happens to inline "
                "JSON rather than by a genuine data payload.",
            ),
            (
                "plain_text_body_neither_json_nor_html",
                503, "text/plain",
                "Service temporarily unavailable, please retry later.",
                "reachable",
                "Adversarial where: the task's own rule sorts a body into "
                "only two outcomes - markup is unreachable, the source's "
                "own data is reachable - so a plain-text body that fails "
                "the JSON parse and carries no HTML marker falls to the "
                "non-markup branch and is reachable, matching the "
                "implementation's own fallthrough rather than a third "
                "'unknown' verdict the task never names.",
            ),
        ]
        for name, status, content_type, body, expected, claim in cases:
            with self.subTest(case=name):
                result = sources.classify_response(status, content_type, body)
                self.assertEqual(
                    result, expected,
                    f"{name}: {claim}\ngot {result!r}, expected {expected!r}",
                )


if __name__ == "__main__":
    unittest.main()
