"""Tests for `compass requirements <spec> [--json] [--for-task T --plan P]`.

Adversarial themes: the exit code is 1 only for a missing spec and 0 for
every readable spec, including one with zero rows; `--json` prints exactly
one JSON array whose rows match the library's rows; a `[deferred]` or
`[informational]` decision shows its tag in the plain listing and a live
decision does not; `--for-task` narrows decisions to the task's citations
while keeping every non-decision row.

The command module is `commands.requirements` with `run(args) -> int`; the
spec and plan are named by absolute path.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requirementslib  # noqa: E402
from commands import requirements  # noqa: E402

SPEC = """---
title: "Sample"
type: spec
status: approved
---

# Sample

## Desired Outcome

- Outcome one.

KPI: every planted instance is flagged.

## Constraints

- Constraint one mentions the `## Decisions` heading.

## Decisions

- **D-01:** Live decision.
- **D-02 [deferred]:** Postponed decision.
- **D-03 [informational]:** Background decision.
"""

NO_REQUIREMENTS_SPEC = "---\ntitle: Bare\ntype: spec\nstatus: draft\n---\n\n# Bare\n\n## Problem\n\nProse only.\n"

PLAN = """---
title: Plan
type: plan
status: active
---

# Plan

- [ ] TASK-7: seventh - complexity: S, depends_on: none, files: [a.py], decisions: [SPEC-099-sample/D-02]
- [ ] TASK-8: eighth - complexity: S, depends_on: none, files: [b.py]
"""


class RequirementsCommandTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        (self.root / ".compass" / "specs").mkdir(parents=True)
        (self.root / ".compass" / "plans").mkdir(parents=True)
        self.spec = self.root / ".compass" / "specs" / "SPEC-099-sample.md"
        self.spec.write_text(SPEC, encoding="utf-8")
        self.plan = self.root / ".compass" / "plans" / "PLAN-099-sample.md"
        self.plan.write_text(PLAN, encoding="utf-8")
        previous_cwd = os.getcwd()
        previous_env = os.environ.pop("CLAUDE_PROJECT_DIR", None)
        os.chdir(self.root)

        def restore():
            os.chdir(previous_cwd)
            if previous_env is not None:
                os.environ["CLAUDE_PROJECT_DIR"] = previous_env

        self.addCleanup(restore)

    def call(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = requirements.run([str(arg) for arg in args])
        return code, out.getvalue(), err.getvalue()

    def test_missing_spec_exits_one_and_prints_no_rows(self):
        """Adversarial where: a spec path that does not exist must exit 1
        with the complaint on stderr and nothing on stdout; exiting 0 would
        let the validator read "no requirements" as a clean spec."""
        code, out, err = self.call(self.root / "nope.md")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertNotEqual(err.strip(), "")

    def test_spec_with_zero_rows_exits_zero_and_json_is_an_empty_array(self):
        """Adversarial where: a readable spec with no requirement sections
        is not an error; it must exit 0, and `--json` must still print a
        parseable empty array rather than nothing."""
        bare = self.root / ".compass" / "specs" / "SPEC-098-bare.md"
        bare.write_text(NO_REQUIREMENTS_SPEC, encoding="utf-8")
        code, out, _ = self.call(bare)
        self.assertEqual(code, 0)
        code, out, _ = self.call(bare, "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [])

    def test_plain_listing_shows_ids_hashes_and_tags_only_where_tagged(self):
        """Adversarial where: the plain listing must name every row's id and
        hash, show `[deferred]` and `[informational]` on exactly their own
        decision rows, and show no tag on the live decision; a tag printed
        on the wrong row hides which decisions the task still owes."""
        rows = {r["id"]: r for r in requirementslib.extract_requirements(SPEC)}
        code, out, _ = self.call(self.spec)
        self.assertEqual(code, 0)
        lines = {row_id: [l for l in out.splitlines() if row_id in l] for row_id in rows}
        for row_id, row in rows.items():
            with self.subTest(row=row_id):
                self.assertEqual(len(lines[row_id]), 1, out)
                self.assertIn(row["hash"], lines[row_id][0])
        self.assertIn("[deferred]", lines["D-02"][0])
        self.assertIn("[informational]", lines["D-03"][0])
        self.assertNotIn("[deferred]", lines["D-01"][0] + lines["D-03"][0])
        self.assertNotIn("[informational]", lines["D-01"][0] + lines["D-02"][0])

    def test_json_rows_carry_id_section_text_hash(self):
        """Adversarial where: `--json` must print one JSON array, in
        document order, each row holding id, section, text and a 12-hex
        hash; a downstream validator parses these keys by name."""
        code, out, _ = self.call(self.spec, "--json")
        self.assertEqual(code, 0)
        rows = json.loads(out)
        self.assertEqual(
            [row["id"] for row in rows], ["O-1", "K-1", "C-1", "D-01", "D-02", "D-03"]
        )
        for row in rows:
            with self.subTest(row=row["id"]):
                self.assertLessEqual({"id", "section", "text", "hash"}, set(row))
                self.assertRegex(row["hash"], r"^[0-9a-f]{12}$")
        self.assertEqual(rows[3]["text"], "Live decision.")
        self.assertIn("every planted instance is flagged", rows[1]["text"])

    def test_for_task_keeps_cited_decisions_and_every_non_decision_row(self):
        """Adversarial where: `--for-task TASK-7` must keep D-02 (cited) and
        drop D-01 and D-03 (uncited) while keeping O-1, K-1 and C-1; TASK-8,
        which cites nothing, must keep only the non-decision rows."""
        code, out, _ = self.call(self.spec, "--json", "--for-task", "TASK-7", "--plan", self.plan)
        self.assertEqual(code, 0)
        self.assertEqual(
            [row["id"] for row in json.loads(out)], ["O-1", "K-1", "C-1", "D-02"]
        )
        code, out, _ = self.call(self.spec, "--json", "--for-task", "TASK-8", "--plan", self.plan)
        self.assertEqual(code, 0)
        self.assertEqual([row["id"] for row in json.loads(out)], ["O-1", "K-1", "C-1"])


if __name__ == "__main__":
    unittest.main()
