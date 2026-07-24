"""Corpus tests: the decision parser against real vault documents.

Every non-mutated fixture is a verbatim copy of a vault document. The five
pre-convention ADRs (authored before D-NN IDs existed) must parse
`none-present`, proving the parser ships without retrofitting any existing
document. The D-NN-authored documents must parse their exact ID lists. The
`mutated-*` fixtures seed defects into real content and must fail loud.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import decisionslib  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "decisions"


def _ids(count):
    return ["D-%02d" % n for n in range(1, count + 1)]


# (fixture filename, expected outcome, expected ID list) per document.
CORPUS = [
    # Pre-convention ADRs: prose Decision sections, zero D-NN units.
    ("ADR-001-methodology-as-skill-with-vault.md", "none-present", []),
    ("ADR-002-retrospective-lessons-subsystem.md", "none-present", []),
    ("ADR-003-drop-counter-file-jit-compute.md", "none-present", []),
    ("ADR-004-hierarchical-specs-with-facets.md", "none-present", []),
    ("ADR-005-compass-cli-for-mechanical-work.md", "none-present", []),
    # D-NN-authored documents.
    ("SPEC-007-decision-coverage-tracing.md", "parsed", _ids(6)),
    ("SPEC-009-configurable-pipeline-workflows.md", "parsed", _ids(1)),
    ("ADR-006-hybrid-hierarchy-implementation.md", "parsed", _ids(7)),
    ("ADR-007-decision-coverage-mechanism.md", "parsed", _ids(9)),
    ("ADR-008-model-resolution-table.md", "parsed", _ids(6)),
    # Seeded defects in real content. One broken bold close poisons the
    # whole document; the surviving bullets are still reported.
    (
        "mutated-SPEC-007-broken-bullet.md",
        "could-not-parse",
        ["D-01", "D-02", "D-04", "D-05", "D-06"],
    ),
    # A fence opened in prose and never closed swallows the Decision
    # section; the unterminated-fence flag keeps that loud.
    ("mutated-ADR-008-unterminated-fence.md", "could-not-parse", []),
    # A bare D- token inside a Decision section that has no parseable
    # bullets is evidence of entries the parser could not read.
    ("mutated-ADR-003-stray-token.md", "could-not-parse", []),
    # A fenced D-NN example inside the Decisions section is documentation;
    # only the real bullet parses.
    ("mutated-SPEC-009-fenced-example.md", "parsed", _ids(1)),
]


class DecisionCorpusTests(unittest.TestCase):
    def test_fixture_set_matches_corpus_table(self):
        on_disk = {p.name for p in FIXTURES.glob("*.md")}
        self.assertEqual(on_disk, {name for name, _, _ in CORPUS})

    def test_every_corpus_document(self):
        for filename, expected_outcome, expected_ids in CORPUS:
            with self.subTest(document=filename):
                text = (FIXTURES / filename).read_text(encoding="utf-8")
                decisions, outcome = decisionslib.extract_decisions(text)
                self.assertEqual(outcome, expected_outcome)
                self.assertEqual([d["id"] for d in decisions], expected_ids)

    def test_parsed_vault_documents_are_fully_trackable(self):
        for filename, expected_outcome, _ in CORPUS:
            if expected_outcome != "parsed" or filename.startswith("mutated-"):
                continue
            with self.subTest(document=filename):
                text = (FIXTURES / filename).read_text(encoding="utf-8")
                decisions, _ = decisionslib.extract_decisions(text)
                self.assertTrue(all(d["trackable"] for d in decisions))


if __name__ == "__main__":
    unittest.main()
