"""Tests for `compass tree` - the on-demand whole-vault view.

The render must show nested domains with their members indented by depth,
carry each artifact's own summary, and derive everything from the disk at
call time - a file added between calls appears without any other write.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import tree  # noqa: E402


def doc(title, summary, type_="spec"):
    return (
        f"---\ntitle: {title}\ntype: {type_}\nstatus: active\narea: w\n"
        f'tags: [x]\nsummary: "{summary}"\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\n\nbody\n'
    )


class TreeTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = tmp / ".compass"
        (self.root / "specs").mkdir(parents=True)
        self.write("specs/SPEC-001-flat.md", doc("Flat", "a flat spec"))
        self.write("specs/network/index.md", doc("network", "networking topics", "domain"))
        self.write("specs/network/cache/index.md", doc("cache", "cache topics", "domain"))
        self.write("specs/network/cache/SPEC-001-eviction.md", doc("Eviction", "eviction policy"))

    def write(self, rel, body):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def test_nested_domains_render_with_summaries_and_depth(self):
        out = tree.render(self.root)
        lines = out.split("\n")
        self.assertIn("specs", lines)
        self.assertIn("  SPEC-001-flat - a flat spec", lines)
        self.assertIn("  network/ - networking topics", lines)
        self.assertIn("    cache/ - cache topics", lines)
        self.assertIn("      SPEC-001-eviction - eviction policy", lines)

    def test_grouping_folder_without_index_gets_a_header_line(self):
        self.write("specs/proposals/SPEC-009-draft.md", doc("Draft", "a filed draft"))
        lines = tree.render(self.root).split("\n")
        self.assertIn("  proposals/", lines)
        self.assertLess(
            lines.index("  proposals/"), lines.index("    SPEC-009-draft - a filed draft")
        )

    def test_folder_with_index_renders_once(self):
        lines = tree.render(self.root).split("\n")
        self.assertEqual(1, sum(1 for line in lines if line.lstrip().startswith("network/")))

    def test_render_is_computed_at_invocation(self):
        before = tree.render(self.root)
        self.assertNotIn("SPEC-002-late", before)
        self.write("specs/SPEC-002-late.md", doc("Late", "added between calls"))
        self.assertIn("  SPEC-002-late - added between calls", tree.render(self.root))


if __name__ == "__main__":
    unittest.main()
