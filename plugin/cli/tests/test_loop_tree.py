"""Tests for `compass tree` rendering of loop folders.

A loop folder is one artifact: it renders as a single line naming the loop
with its summary, never as a folder header over an `index` line, and its
parts (feedback, golden patterns) never appear.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import tree  # noqa: E402

LOOP_INDEX = (
    "---\ntitle: Remove bad pattern\ntype: loop\nstatus: active\narea: workflow\n"
    "tags: [loops]\ncreated: 2026-10-18\nupdated: 2026-10-18\n"
    'summary: "drives the bad pattern count to zero"\n---\n\n# Loop\n'
)


class LoopTreeTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = tmp / ".compass"
        for name in ("LOOP-001-remove-bad", "LOOP-002-other"):
            folder = self.root / "loops" / name
            (folder / "golden").mkdir(parents=True)
            (folder / "index.md").write_text(LOOP_INDEX, encoding="utf-8")
            (folder / "feedback.md").write_text("# Feedback\n", encoding="utf-8")
            (folder / "golden" / "a.md").write_text("# golden\n", encoding="utf-8")

    def test_loop_renders_as_one_line_with_summary(self):
        """Adversarial where: a loop-index record falling into the folder-spec
        or child path, emitting a `LOOP-001-remove-bad/` header over an
        `index` line, or leaking `feedback` and `golden` parts."""
        lines = tree.render(self.root).splitlines()
        self.assertEqual(
            lines,
            [
                "loops",
                "  LOOP-001-remove-bad - drives the bad pattern count to zero",
                "  LOOP-002-other - drives the bad pattern count to zero",
            ],
        )


if __name__ == "__main__":
    unittest.main()
