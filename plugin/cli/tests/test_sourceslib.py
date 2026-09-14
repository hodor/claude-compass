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


if __name__ == "__main__":
    unittest.main()
