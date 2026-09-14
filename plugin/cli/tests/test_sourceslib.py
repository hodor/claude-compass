"""Tests for `sourceslib` - the curated research-source catalog and its
per-source retrievers (SPEC-023-research-covers-the-whole-spec D-03, D-09;
PLAN-018-research-covers-the-whole-spec TASK-120).

`sourceslib.parse_sources(text)` reads the row-based catalog shape modeled
on the existing hand-rolled parsers (`lessonslib.py:parse_catalog`,
`modelslib.py:parse_models_yaml`): two top-level sections at zero indent,
`sources:` and `do_not_try:`, each holding `  - name: "..."` rows with
`    key: value` fields indented under them. It returns
`{"sources": [...], "do_not_try": [...]}`, one dict per row.
`sourceslib.load_sources()` reads the shipped `sources.yaml` next to the
module. `sourceslib.RETRIEVERS` maps each entry's `retriever` field to the
callable that actually fetches from that source.

Adversarial classes: a shipped entry's retrieval call read as present when
the field was actually left empty; two different shipped sources silently
sharing one generic retriever instead of each carrying its own working call
(D-09's "dedicated... regardless of what else we do"); a do-not-try entry
dropped, or merged into the active list, instead of surviving as its own
record; the dead OpenReview v1 host shipped instead of the v2 host the
research names as reachable; and the catalog data file ending up somewhere
other than `plugin/cli/`, where `self_update.py` would never copy it into
an installed project.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sourceslib  # noqa: E402


# One entry per D-03 access shape: keyless+scripted, keyed+scripted, and
# browser-only. Field values are drawn from the real source names D-03
# lists so a broken lookup can't quietly fall back to a same-looking
# placeholder.
FIXTURE = """
sources:
  - name: "Crossref"
    coverage: "DOI-registration metadata for journal articles and books"
    access: "REST, JSON, no auth"
    key_requirement: ""
    reachable: "script"
    retriever: "fetch_crossref"
  - name: "Semantic Scholar"
    coverage: "paper metadata, abstracts, citation graph"
    access: "REST, JSON"
    key_requirement: "free key raises the rate limit above 1 req/sec"
    reachable: "script"
    retriever: "fetch_semantic_scholar"
  - name: "ACM Digital Library"
    coverage: "ACM proceedings and journals"
    access: "web only, Cloudflare-walled to non-browser clients"
    key_requirement: ""
    reachable: "browser"
    retriever: "fetch_acm_digital_library"
do_not_try:
  - name: "CiteSeerX"
    coverage: "CS literature metadata and cached PDFs"
    reason: "oai2 endpoint 301s to a Wayback snapshot, then 404s"
"""

# One entry among two well-formed ones is missing its `retriever` field
# entirely - the asymmetric case: everything else about the row is valid,
# only the one field the automated-verification bullet checks is absent.
MISSING_RETRIEVER_FIXTURE = """
sources:
  - name: "Crossref"
    coverage: "DOI-registration metadata"
    access: "REST, JSON, no auth"
    key_requirement: ""
    reachable: "script"
    retriever: "fetch_crossref"
  - name: "OpenAlex"
    coverage: "open metadata graph"
    access: "REST, JSON, credit-metered"
    key_requirement: ""
    reachable: "script"
  - name: "Unpaywall"
    coverage: "OA-location layer over Crossref DOIs"
    access: "REST, JSON, email param"
    key_requirement: ""
    reachable: "script"
    retriever: "fetch_unpaywall"
"""


class ParseSourcesRoundTripTests(unittest.TestCase):
    """Adversarial where: a shape-specific shortcut (e.g. a parser branch
    written only for the keyless case) drops or overwrites a field for one
    of the other two shapes D-03 names - keyed, or browser-only."""

    def test_round_trip_per_entry_shape(self):
        result = sourceslib.parse_sources(FIXTURE)
        by_name = {e["name"]: e for e in result["sources"]}

        cases = [
            ("keyless_scripted", "Crossref", {
                "coverage": "DOI-registration metadata for journal articles and books",
                "access": "REST, JSON, no auth",
                "key_requirement": "",
                "reachable": "script",
                "retriever": "fetch_crossref",
            }),
            ("keyed_scripted", "Semantic Scholar", {
                "coverage": "paper metadata, abstracts, citation graph",
                "access": "REST, JSON",
                "key_requirement": "free key raises the rate limit above 1 req/sec",
                "reachable": "script",
                "retriever": "fetch_semantic_scholar",
            }),
            ("browser_only", "ACM Digital Library", {
                "coverage": "ACM proceedings and journals",
                "access": "web only, Cloudflare-walled to non-browser clients",
                "key_requirement": "",
                "reachable": "browser",
                "retriever": "fetch_acm_digital_library",
            }),
        ]
        for shape, name, expected_fields in cases:
            with self.subTest(shape=shape):
                self.assertIn(name, by_name, f"{name} missing from parsed sources")
                entry = by_name[name]
                for field, expected in expected_fields.items():
                    self.assertEqual(
                        entry.get(field), expected,
                        f"{shape} entry {name!r} field {field!r}: "
                        f"expected {expected!r}, got {entry.get(field)!r}",
                    )


class DoNotTryRecordTests(unittest.TestCase):
    """Adversarial where: a source the research found dead or closed is
    dropped on parse, or merged into the active `sources` list instead of
    kept as its own record, instead of surviving in the file."""

    def test_do_not_try_entry_is_parsed_not_dropped(self):
        result = sourceslib.parse_sources(FIXTURE)
        self.assertEqual(len(result["sources"]), 3)
        self.assertEqual(len(result["do_not_try"]), 1)
        entry = result["do_not_try"][0]
        self.assertEqual(entry["name"], "CiteSeerX")
        self.assertEqual(
            entry["reason"], "oai2 endpoint 301s to a Wayback snapshot, then 404s"
        )

    def test_do_not_try_names_never_appear_in_active_sources(self):
        result = sourceslib.parse_sources(FIXTURE)
        active_names = {e["name"] for e in result["sources"]}
        dead_names = {e["name"] for e in result["do_not_try"]}
        self.assertEqual(active_names & dead_names, set())


class RetrieverContractTests(unittest.TestCase):
    """Adversarial where: the parser reports a retriever as present for an
    entry that never named one, because the check that backs "every shipped
    entry carries a non-empty retrieval call" is satisfied by something
    other than the entry's own `retriever` field (e.g. dict truthiness, or
    a copied default)."""

    def test_missing_retriever_field_is_not_silently_defaulted(self):
        result = sourceslib.parse_sources(MISSING_RETRIEVER_FIXTURE)
        by_name = {e["name"]: e for e in result["sources"]}
        self.assertFalse(
            by_name["OpenAlex"].get("retriever"),
            "an entry with no retriever field must not read as carrying one",
        )
        # its well-formed neighbors are unaffected by the gap
        self.assertEqual(by_name["Crossref"]["retriever"], "fetch_crossref")
        self.assertEqual(by_name["Unpaywall"]["retriever"], "fetch_unpaywall")


class ShippedListLiveContractTests(unittest.TestCase):
    """Exercises the real `plugin/cli/sources.yaml` Compass ships, not a
    fixture - the automated-verification bullet's "every shipped entry"
    language names this file, not a synthetic one."""

    def test_named_keyless_scripted_sources_are_shipped(self):
        """Adversarial where: a source D-03 names as keyless and reachable
        by script is missing from the shipped list, or shipped with a
        nonzero key_requirement or a browser-only reachable value."""
        by_name = {e["name"]: e for e in sourceslib.load_sources()["sources"]}
        for name in ("Crossref", "OpenAlex", "Unpaywall", "arXiv", "GitHub"):
            with self.subTest(source=name):
                self.assertIn(name, by_name, f"{name} not in shipped list")
                entry = by_name[name]
                self.assertEqual(entry.get("reachable"), "script")
                self.assertFalse(entry.get("key_requirement"))

    def test_openreview_v2_host_is_named_not_the_dead_v1(self):
        """Adversarial where: the shipped entry names the OpenReview host
        without distinguishing it from the v1 API, which research finding
        51 (RESEARCH-source-inventory) tested as returning 403 while v2
        answers - shipping the undifferentiated name risks the dead host."""
        by_name = {e["name"]: e for e in sourceslib.load_sources()["sources"]}
        matches = [n for n in by_name if "openreview" in n.lower()]
        self.assertTrue(matches, "no OpenReview entry in shipped list")
        entry = by_name[matches[0]]
        haystack = f"{matches[0]} {entry.get('access', '')}".lower()
        self.assertIn("v2", haystack, "shipped OpenReview entry doesn't name the v2 host")
        self.assertEqual(entry.get("reachable"), "script")

    def test_semantic_scholar_is_shipped_as_key_required(self):
        """Adversarial where: Semantic Scholar is shipped without recording
        its key requirement, losing the distinction D-03 draws between it
        and the fully keyless sources."""
        by_name = {e["name"]: e for e in sourceslib.load_sources()["sources"]}
        self.assertIn("Semantic Scholar", by_name)
        entry = by_name["Semantic Scholar"]
        self.assertTrue(entry.get("key_requirement"))
        self.assertEqual(entry.get("reachable"), "script")

    def test_browser_only_sources_are_shipped_and_marked_browser(self):
        """Adversarial where: a source D-03 says is reachable only through
        a browser is shipped marked "script" - a claim that would fail the
        moment `compass sources --check` (TASK-121) tries a scripted call
        against it."""
        by_name = {e["name"]: e for e in sourceslib.load_sources()["sources"]}
        for name in ("ACM Digital Library", "DBLP", "Internet Archive Scholar"):
            with self.subTest(source=name):
                self.assertIn(name, by_name, f"{name} not in shipped list")
                self.assertEqual(by_name[name].get("reachable"), "browser")

    def test_every_shipped_entry_has_a_working_dedicated_retriever(self):
        """Adversarial where: an entry carries a `retriever` name that
        resolves to nothing in `RETRIEVERS` - a string present on the row
        but no working call behind it, which the task calls an incomplete
        entry."""
        sources = sourceslib.load_sources()["sources"]
        self.assertTrue(sources, "shipped source list is empty")
        for entry in sources:
            with self.subTest(source=entry.get("name")):
                retriever_name = entry.get("retriever")
                self.assertTrue(retriever_name, f"{entry.get('name')} has no retriever")
                self.assertIn(
                    retriever_name, sourceslib.RETRIEVERS,
                    f"{entry.get('name')}'s retriever {retriever_name!r} not registered",
                )
                self.assertTrue(
                    callable(sourceslib.RETRIEVERS[retriever_name]),
                    f"{entry.get('name')}'s retriever {retriever_name!r} is not callable",
                )

    def test_retrievers_are_dedicated_not_shared_across_the_real_shipped_list(self):
        """Adversarial where: several sources with a similar access shape
        (several of D-03's keyless REST/JSON sources look alike) are wired
        to one shared generic retriever instead of D-09's dedicated
        retriever per curated source."""
        sources = sourceslib.load_sources()["sources"]
        names = [e.get("retriever") for e in sources]
        self.assertEqual(
            len(names), len(set(names)),
            f"retrievers are not one-per-source: {names}",
        )

    def test_do_not_try_record_survives_in_the_real_file(self):
        """Adversarial where: the sources research found dead or closed
        (e.g. CiteSeerX, Papers with Code) were left out of the shipped
        file entirely rather than kept as a do-not-try record."""
        result = sourceslib.load_sources()
        self.assertTrue(result["do_not_try"], "do-not-try record is empty")
        dead_names = {e["name"] for e in result["do_not_try"]}
        active_names = {e["name"] for e in result["sources"]}
        self.assertEqual(dead_names & active_names, set())

    def test_sources_data_file_lives_under_plugin_cli_not_a_skill_dir(self):
        """Adversarial where: `sources.yaml` is placed inside a skill
        directory, which `self_update.py:246` copies only `*.md` out of -
        the catalog would never reach an installed project."""
        data_path = Path(sourceslib.__file__).resolve().parent / "sources.yaml"
        self.assertTrue(data_path.is_file(), f"{data_path} does not exist")
        self.assertNotIn("skills", data_path.parts)
        self.assertEqual(data_path.parent.name, "cli")


def _retriever_positional_args(retriever_name):
    """Positional args a retriever needs beyond the query defaults every
    other retriever supplies for itself. Unpaywall and ACM take a DOI in
    place of their host's own search term."""
    return {
        "fetch_unpaywall": ("10.1000/test",),
        "fetch_acm_digital_library": ("10.1000/test",),
    }.get(retriever_name, ())


class ParserLineShapeTests(unittest.TestCase):
    """Line-by-line edge cases the round-trip fixture, built entirely from
    well-formed rows, never exercises: what the hand-rolled regex-per-line
    parser does with a value or a layout it wasn't written against."""

    def test_field_value_containing_a_colon_is_kept_whole(self):
        """Adversarial where: a parser that split a field line on its first
        or last colon, rather than only on the key's own colon, would
        truncate a URL-shaped value at the scheme colon or at a colon
        inside a query string."""
        text = (
            'sources:\n'
            '  - name: "X"\n'
            '    check_request: "GET https://api.example.org/x?a=1 -> 200,'
            ' JSON (tested 2026-09-13)"\n'
        )
        entry = sourceslib.parse_sources(text)["sources"][0]
        self.assertEqual(
            entry["check_request"],
            "GET https://api.example.org/x?a=1 -> 200, JSON (tested 2026-09-13)",
        )

    def test_blank_line_between_fields_does_not_split_the_entry(self):
        """Adversarial where: a blank line inside a row is read as ending
        the entry (the way a blank line ends a section elsewhere in the
        file), silently splitting one row's fields across two entries or
        dropping whatever follows the gap."""
        text = (
            'sources:\n'
            '  - name: "X"\n'
            '    coverage: "before the gap"\n'
            '\n'
            '    reachable: "script"\n'
        )
        result = sourceslib.parse_sources(text)
        self.assertEqual(len(result["sources"]), 1)
        entry = result["sources"][0]
        self.assertEqual(entry["coverage"], "before the gap")
        self.assertEqual(entry["reachable"], "script")

    def test_a_section_absent_from_the_text_parses_as_empty_not_missing(self):
        """Adversarial where: a file (or a test fixture) that never writes
        a `do_not_try:` header raises a `KeyError` on `result["do_not_try"]`
        instead of `load_sources()` callers being able to rely on both keys
        always being present."""
        text = 'sources:\n  - name: "X"\n'
        result = sourceslib.parse_sources(text)
        self.assertEqual(result["do_not_try"], [])
        self.assertIn("sources", result)
        self.assertIn("do_not_try", result)

    def test_empty_value_is_present_but_absent_field_is_not(self):
        """Adversarial where: `entry.get(field)` returning a falsy value is
        used to mean "field absent" somewhere downstream, collapsing an
        explicit empty string (a keyless source's `key_requirement: ""`)
        into the same state as a field the row never wrote at all - the
        exact distinction the module's own docstring promises."""
        with_empty = sourceslib.parse_sources(
            'sources:\n  - name: "X"\n    key_requirement: ""\n'
        )["sources"][0]
        without_field = sourceslib.parse_sources(
            'sources:\n  - name: "X"\n'
        )["sources"][0]
        self.assertIn("key_requirement", with_empty)
        self.assertEqual(with_empty["key_requirement"], "")
        self.assertNotIn("key_requirement", without_field)

    def test_trailing_comment_on_a_field_line_is_stripped(self):
        """Adversarial where: a parser that strips only first-and-last-char
        quotes without first removing a trailing comment leaves the opening
        quote and the comment text embedded in the value, so a maintainer
        who adds an inline comment to `sources.yaml` expecting YAML comment
        semantics gets a corrupted field, silently. A `#` sitting inside a
        quoted value is not a comment and must survive instead."""
        outside_quotes = sourceslib.parse_sources(
            'sources:\n  - name: "X"\n    key_requirement: ""  # none needed\n'
        )["sources"][0]
        self.assertEqual(outside_quotes["key_requirement"], "")

        inside_quotes = sourceslib.parse_sources(
            'sources:\n  - name: "X"\n'
            '    access: "REST, JSON # not a comment, still quoted"\n'
        )["sources"][0]
        self.assertEqual(
            inside_quotes["access"], "REST, JSON # not a comment, still quoted"
        )

        quote_then_real_comment = sourceslib.parse_sources(
            'sources:\n  - name: "X"\n'
            '    access: "https://x/#frag"  # note\n'
        )["sources"][0]
        self.assertEqual(quote_then_real_comment["access"], "https://x/#frag")

    def test_field_value_with_an_unbalanced_embedded_quote_is_mis_split(self):
        """Adversarial where: this locks in the quote-escaping gap the
        builder's own annotation names (`_unquote` only strips one matching
        quote pair from each end). A value containing a quoted phrase
        followed by more unquoted text that itself ends in a stray quote
        character has no single correct split without escaping support, and
        `_unquote` picks the first-and-last characters regardless, moving
        the true closing delimiter into the middle of the parsed value."""
        text = (
            'sources:\n  - name: "X"\n'
            '    coverage: "opens with quote but isnt wrapped" extra text"\n'
        )
        entry = sourceslib.parse_sources(text)["sources"][0]
        self.assertEqual(
            entry["coverage"],
            'opens with quote but isnt wrapped" extra text',
        )


class RetrieverCheckRequestConsistencyTests(unittest.TestCase):
    """Adversarial where: `sources.yaml`'s hand-written `check_request` prose
    and the retriever's actual URL-building code drift apart after either
    one is edited alone - the entry would keep documenting a host or path
    its own retriever no longer calls."""

    def test_every_shipped_retriever_builds_the_host_and_path_its_own_check_request_documents(self):
        import re
        import urllib.parse

        sources = sourceslib.load_sources()["sources"]
        for entry in sources:
            name = entry["name"]
            retriever_name = entry["retriever"]
            retriever = sourceslib.RETRIEVERS[retriever_name]
            args = _retriever_positional_args(retriever_name)
            with self.subTest(source=name):
                request = retriever(*args)
                actual = urllib.parse.urlsplit(request.full_url)

                match = re.search(r'(?:GET|POST)\s+(https?://\S+)', entry["check_request"])
                self.assertIsNotNone(
                    match, f"{name}'s check_request names no GET/POST URL"
                )
                documented = urllib.parse.urlsplit(match.group(1))
                documented_path = documented.path
                for arg in args:
                    documented_path = documented_path.replace("{doi}", arg)

                self.assertEqual(
                    actual.netloc, documented.netloc,
                    f"{name}: retriever host {actual.netloc!r} != "
                    f"documented host {documented.netloc!r}",
                )
                self.assertEqual(
                    actual.path, documented_path,
                    f"{name}: retriever path {actual.path!r} != "
                    f"documented path {documented_path!r}",
                )


class RetrieverNetworkIsolationTests(unittest.TestCase):
    """Adversarial where: a retriever the module docstring promises only
    "builds the request" instead reaches out to `urlopen` itself (directly,
    or through a default-argument call at import time), which would make
    every test in this file a live network call rather than a hermetic one."""

    def test_every_retriever_builds_a_request_without_opening_a_connection(self):
        import urllib.request
        from unittest import mock

        def _network_touched(*args, **kwargs):
            raise AssertionError("a retriever called urlopen instead of only building a Request")

        with mock.patch.object(urllib.request, "urlopen", side_effect=_network_touched):
            for retriever_name, retriever in sourceslib.RETRIEVERS.items():
                args = _retriever_positional_args(retriever_name)
                with self.subTest(retriever=retriever_name):
                    request = retriever(*args)
                    self.assertIsInstance(request, urllib.request.Request)


class SemanticScholarKeyHeaderTests(unittest.TestCase):
    """Adversarial where: the key-raises-the-rate-limit contract D-03 and
    the shipped entry both describe is lost in either direction - a key
    the caller supplies never reaches the request, or a header is attached
    even with no key, which would misrepresent an anonymous call as
    authenticated to the source's own rate limiter."""

    def test_key_header_is_attached_only_when_a_key_is_given(self):
        without_key = sourceslib.fetch_semantic_scholar("test")
        with_key = sourceslib.fetch_semantic_scholar("test", api_key="secret-key")

        self.assertIsNone(without_key.get_header("X-api-key"))
        self.assertEqual(with_key.get_header("X-api-key"), "secret-key")


class DoNotTryReasonDatedTests(unittest.TestCase):
    """Adversarial where: a do-not-try entry's `reason` records only what
    was wrong, not when it was checked, which is what lets `sources.yaml`'s
    "ages" risk (PLAN-018) go unnoticed - a reason with no date reads as
    current forever, whether the source was tested last week or last year."""

    def test_every_do_not_try_entry_names_the_date_it_was_tested(self):
        import re

        dated = re.compile(r"\(tested \d{4}-\d{2}-\d{2}\)")
        entries = sourceslib.load_sources()["do_not_try"]
        self.assertTrue(entries, "do-not-try record is empty")
        for entry in entries:
            with self.subTest(source=entry.get("name")):
                self.assertTrue(
                    dated.search(entry.get("reason", "")),
                    f"{entry.get('name')}'s reason carries no (tested YYYY-MM-DD) date: "
                    f"{entry.get('reason')!r}",
                )


if __name__ == "__main__":
    unittest.main()
