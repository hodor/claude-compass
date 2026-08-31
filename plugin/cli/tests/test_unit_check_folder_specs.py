"""Tests for unit-check candidate naming and overlap on folder specs.

A folder spec's document is its `index.md`, so the candidate name must
come from the spec's folder, never the file stem - two folder specs must
never both be called `index`. Candidates that claim the same member are
surfaced as a conflict, since their suggested make-unit commands cannot
both run.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import unit_check  # noqa: E402


def doc(title, type_, deps=None):
    dep_line = ""
    if deps:
        rendered = ", ".join(f'"[[{d}]]"' for d in deps)
        dep_line = f"depends_on: [{rendered}]\n"
    return (
        f"---\ntitle: {title}\ntype: {type_}\nstatus: active\narea: w\n"
        f'tags: [x]\nsummary: "{title}"\n{dep_line}'
        f"created: 2026-08-30\nupdated: 2026-08-30\n---\n\nbody\n"
    )


class FolderSpecCandidateTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = tmp / ".compass"
        for d in ("specs", "plans", "decisions", "research"):
            (self.root / d).mkdir(parents=True)
        self.write(
            "specs/SPEC-008-gameplay-driven-rig-control/index.md",
            doc("Rig control", "spec"),
        )
        self.write(
            "plans/PLAN-003-gameplay-driven-rig-control.md",
            doc("Rig plan", "plan", ["SPEC-008-gameplay-driven-rig-control"]),
        )
        self.write(
            "decisions/ADR-008-driven-parts-block.md",
            doc("Driven parts", "decision", ["SPEC-008-gameplay-driven-rig-control"]),
        )

    def write(self, rel, body):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def report(self):
        return unit_check.format_report(
            self.root, unit_check.find_candidates(self.root)
        )

    def test_folder_spec_candidate_named_from_its_folder(self):
        out = self.report()
        self.assertIn("candidate: gameplay-driven-rig-control", out)
        self.assertNotIn("candidate: index", out)
        self.assertNotIn("make-unit index", out)

    def test_two_folder_specs_get_distinct_names(self):
        self.write(
            "specs/SPEC-009-part-streaming/index.md", doc("Part streaming", "spec")
        )
        self.write(
            "plans/PLAN-004-streaming.md",
            doc("Streaming plan", "plan", ["SPEC-009-part-streaming"]),
        )
        self.write(
            "research/RESEARCH-streaming.md",
            doc("Streaming research", "research", ["SPEC-009-part-streaming"]),
        )
        out = self.report()
        self.assertIn("candidate: gameplay-driven-rig-control", out)
        self.assertIn("candidate: part-streaming", out)
        self.assertNotIn("candidate: index", out)

    def test_shared_member_across_candidates_is_a_conflict(self):
        self.write(
            "specs/SPEC-009-part-streaming/index.md", doc("Part streaming", "spec")
        )
        self.write(
            "research/RESEARCH-streaming.md",
            doc("Streaming research", "research", ["SPEC-009-part-streaming"]),
        )
        # The ADR now traces to BOTH specs: both candidates would claim it.
        self.write(
            "decisions/ADR-008-driven-parts-block.md",
            doc(
                "Driven parts",
                "decision",
                ["SPEC-008-gameplay-driven-rig-control", "SPEC-009-part-streaming"],
            ),
        )
        out = self.report()
        self.assertIn("conflict", out)
        self.assertIn("decisions/ADR-008-driven-parts-block.md", out)

    def test_disjoint_candidates_report_no_conflict(self):
        self.write(
            "specs/SPEC-009-part-streaming/index.md", doc("Part streaming", "spec")
        )
        self.write(
            "plans/PLAN-004-streaming.md",
            doc("Streaming plan", "plan", ["SPEC-009-part-streaming"]),
        )
        self.write(
            "research/RESEARCH-streaming.md",
            doc("Streaming research", "research", ["SPEC-009-part-streaming"]),
        )
        self.assertNotIn("conflict", self.report())


if __name__ == "__main__":
    unittest.main()
