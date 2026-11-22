"""Tests for `requirementslib`: a spec body becomes one row per requirement.

Interface under test:

- `extract_requirements(text)` returns a list of dicts in document order.
  Every row has `id`, `section`, `text` and `hash` (the first 12 hex digits
  of the sha256 of the whitespace-normalized text). Decision rows (`D-NN`)
  also carry `tags`, a list of lowercase bracket tags.
- `rows_for_task(rows, plan_text, task_id, spec_stem)` keeps the decision
  rows the task line cites as `decisions: [<spec_stem>/D-NN, ...]` plus every
  non-decision row, in the original order.

Adversarial themes: ids come from section order and restart per section;
headings quoted inside code never open a section; a one-sentence edit moves
exactly one hash; line endings and wrapping never move a hash; a task id is
matched whole, and a decision cited from another document is never claimed.
"""

import hashlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requirementslib  # noqa: E402

REAL_SPEC = (
    Path(__file__).resolve().parents[3]
    / ".compass"
    / "specs"
    / "pipeline"
    / "SPEC-034-verification-beyond-test-pass.md"
)

SPEC = """---
title: "Sample"
type: spec
status: approved
---

# Sample

## Problem

- A problem bullet that is not a requirement.

## Desired Outcome

- Outcome one.
- Outcome two
  wrapped onto a second line.

KPI: the planted instances are all flagged.

## Success Criteria

- Success one.
- Success two.

## Constraints

- Constraint one keeps the `## Success Criteria` heading intact.
- Constraint two.

```
## Constraints
- fenced bullet that is never a requirement
```

- Constraint three.

## Decisions

- **D-01:** First decision.
- **D-02 [deferred]:** Later decision.
- **D-03 [informational]:** Note decision.
"""

PLAN = """# Plan

- [ ] TASK-1: first - complexity: S, depends_on: none, files: [a.py], decisions: [SPEC-099-sample/D-02]
- [ ] TASK-10: tenth - complexity: S, depends_on: none, files: [b.py], decisions: [SPEC-099-sample/D-01, SPEC-100-other/D-03]
- [ ] TASK-2: second - complexity: S, depends_on: none, files: [c.py]
"""


def ids(rows):
    return [row["id"] for row in rows]


def normalized_hash(text):
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:12]


class ExtractRequirementsTest(unittest.TestCase):
    def test_ids_follow_section_order_and_skip_fences_and_other_sections(self):
        """Adversarial where: a heading quoted in inline code or inside a
        fenced block must not open or reset a section, so the bullet after
        it keeps counting (C-3, not C-1) and the fenced bullet yields no
        row; bullets under `## Problem` must yield no row at all."""
        rows = requirementslib.extract_requirements(SPEC)
        self.assertEqual(
            ids(rows),
            ["O-1", "O-2", "K-1", "S-1", "S-2", "C-1", "C-2", "C-3", "D-01", "D-02", "D-03"],
        )
        texts = [row["text"] for row in rows]
        self.assertFalse(any("fenced bullet" in text for text in texts))
        self.assertFalse(any("not a requirement" in text for text in texts))

    def test_row_text_and_kpi_placement(self):
        """Adversarial where: the KPI line sits inside `## Desired Outcome`
        and must become K-1 only, never an extra O-n; a wrapped bullet must
        read as one row whose text joins its continuation line."""
        rows = {row["id"]: row for row in requirementslib.extract_requirements(SPEC)}
        self.assertEqual(rows["O-2"]["text"], "Outcome two wrapped onto a second line.")
        self.assertIn("planted instances", rows["K-1"]["text"])
        self.assertNotIn("planted instances", rows["O-1"]["text"] + rows["O-2"]["text"])
        self.assertIn("Success Criteria", rows["C-1"]["text"])
        self.assertEqual(rows["O-1"]["section"], rows["O-2"]["section"])
        self.assertNotEqual(rows["O-1"]["section"], rows["S-1"]["section"])

    def test_decision_rows_keep_ids_text_and_tags(self):
        """Adversarial where: decision rows must keep the `D-NN` id and the
        bracket tag from the decision bullet; a tag dropped here would make
        a deferred decision look like a live requirement."""
        rows = {row["id"]: row for row in requirementslib.extract_requirements(SPEC)}
        self.assertEqual(rows["D-01"]["text"], "First decision.")
        self.assertEqual(rows["D-01"]["tags"], [])
        self.assertEqual(rows["D-02"]["tags"], ["deferred"])
        self.assertEqual(rows["D-03"]["tags"], ["informational"])

    def test_hash_is_twelve_hex_of_whitespace_normalized_text(self):
        """Adversarial where: the hash must be sha256 over text with runs of
        whitespace collapsed, truncated to 12 lowercase hex digits; hashing
        raw text would move the hash when a line is rewrapped."""
        for row in requirementslib.extract_requirements(SPEC):
            with self.subTest(row=row["id"]):
                self.assertRegex(row["hash"], r"^[0-9a-f]{12}$")
                self.assertEqual(row["hash"], normalized_hash(row["text"]))

        rewrapped = SPEC.replace("- Success one.", "- Success   one.").replace(
            "- Outcome two\n  wrapped onto a second line.",
            "- Outcome two wrapped\n    onto a second line.",
        )
        self.assertNotEqual(rewrapped, SPEC)
        before = {r["id"]: r["hash"] for r in requirementslib.extract_requirements(SPEC)}
        after = {r["id"]: r["hash"] for r in requirementslib.extract_requirements(rewrapped)}
        self.assertEqual(before, after)

    def test_one_sentence_edit_changes_only_that_hash(self):
        """Adversarial where: editing one requirement must change exactly
        that row's hash and leave every id and every other hash untouched,
        so a stale citation of the edited id is detectable."""
        edited = SPEC.replace("- Success two.", "- Success two, now stricter.")
        before = requirementslib.extract_requirements(SPEC)
        after = requirementslib.extract_requirements(edited)
        self.assertEqual(ids(before), ids(after))
        changed = [b["id"] for b, a in zip(before, after) if b["hash"] != a["hash"]]
        self.assertEqual(changed, ["S-2"])

    def test_crlf_text_gives_the_same_rows_as_lf_text(self):
        """Adversarial where: a spec checked out with CRLF endings must give
        identical ids, texts and hashes, or a Windows checkout reads as an
        edit of every requirement."""
        lf = requirementslib.extract_requirements(SPEC)
        crlf = requirementslib.extract_requirements(SPEC.replace("\n", "\r\n"))
        self.assertEqual(lf, crlf)

    def test_spec_without_requirement_sections_yields_no_rows(self):
        """Adversarial where: a spec with only unrelated headings, and an
        empty string, must give an empty list rather than raise or invent
        rows."""
        body = "# T\n\n## Problem\n\n- a bullet\n\nSome prose.\n"
        self.assertEqual(requirementslib.extract_requirements(body), [])
        self.assertEqual(requirementslib.extract_requirements(""), [])

    def test_real_spec_yields_outcome_constraint_and_kpi_without_decisions(self):
        """Adversarial where: the shipped spec has no D-NN, no Success
        Criteria and one Constraints bullet; it must yield O-1, C-1 and K-1
        and no decision or success row, with the KPI text on K-1."""
        rows = requirementslib.extract_requirements(REAL_SPEC.read_text(encoding="utf-8"))
        found = ids(rows)
        self.assertTrue({"O-1", "C-1", "K-1"} <= set(found), found)
        self.assertFalse([i for i in found if i.startswith(("D-", "S-"))], found)
        self.assertEqual(found.count("C-1"), 1)
        self.assertEqual(found.count("K-1"), 1)
        kpi = [row for row in rows if row["id"] == "K-1"][0]
        self.assertIn("planted instance", kpi["text"])


class RowsForTaskTest(unittest.TestCase):
    def setUp(self):
        self.rows = requirementslib.extract_requirements(SPEC)

    def pick(self, task_id):
        return ids(requirementslib.rows_for_task(self.rows, PLAN, task_id, "SPEC-099-sample"))

    def test_task_keeps_its_decisions_plus_every_non_decision_row(self):
        """Adversarial where: the filter must keep every O, S, C and K row
        and only the cited D rows, in document order; dropping non-D rows or
        keeping uncited decisions both break spec conformance."""
        non_d = [i for i in ids(self.rows) if not i.startswith("D-")]
        self.assertEqual(self.pick("TASK-1"), non_d + ["D-02"])

    def test_task_id_is_matched_whole_and_foreign_citations_are_ignored(self):
        """Adversarial where: TASK-1 must not pick up TASK-10's citations
        (prefix match), TASK-10 must ignore a `D-03` cited from another
        document, and a task with no decisions field keeps only non-D rows."""
        non_d = [i for i in ids(self.rows) if not i.startswith("D-")]
        self.assertEqual(self.pick("TASK-10"), non_d + ["D-01"])
        self.assertEqual(self.pick("TASK-2"), non_d)


if __name__ == "__main__":
    unittest.main()
