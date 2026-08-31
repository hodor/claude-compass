"""Tests for the lessons index hierarchy sync step.

Lessons load like every other type dir: `lessons/index.md` carries the
high-level surface (domains with counts, root lessons), each domain's
`index.md` lists its members with summaries, and sync regenerates those
listings mechanically from lesson frontmatter. The hot path counts
`lessons/index.md`, not the catalog.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import hot_path, sync  # noqa: E402


def lesson(title, summary):
    return (
        f"---\ntitle: {title}\ntype: lesson\nstatus: active\ncategory: process\n"
        f'area: workflow\ntags: [x]\nscore: 5\nsummary: "{summary}"\n'
        f"created: 2026-08-30\nupdated: 2026-08-30\n---\n\nbody\n"
    )


def domain_index(name, summary):
    return (
        f"---\ntitle: {name}\ntype: domain\nstatus: active\ntags: [domain]\n"
        f'summary: "{summary}"\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\n\n'
        f"# {name}\n\n## Scope\n\nClass here: {summary}\n"
    )


class LessonsIndexSyncTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = tmp / ".compass"
        for d in ("specs", "meta", "lessons/hooks"):
            (self.root / d).mkdir(parents=True)
        (self.root / "index.md").write_text("# Index\n", encoding="utf-8")
        (self.root / "active.md").write_text("# Active\n", encoding="utf-8")
        (self.root / "meta" / "lessons-catalog.yaml").write_text(
            "lessons: []\n", encoding="utf-8"
        )
        self.write("lessons/index.md", domain_index("lessons", "lessons learned"))
        self.write("lessons/hooks/index.md", domain_index("hooks", "hook semantics"))
        self.write(
            "lessons/hooks/LESSON-hook-a.md", lesson("Hook A", "hooks fire from settings")
        )
        self.write("lessons/LESSON-loose.md", lesson("Loose", "a root lesson"))

    def write(self, rel, body):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def read(self, rel):
        return (self.root / rel).read_text(encoding="utf-8")

    def test_domain_index_gains_member_listing_with_summaries(self):
        sync.sync(self.root)
        text = self.read("lessons/hooks/index.md")
        self.assertIn("## Lessons", text)
        self.assertIn("LESSON-hook-a", text)
        self.assertIn("hooks fire from settings", text)
        self.assertIn("Class here: hook semantics", text)  # hand-written Scope survives

    def test_type_root_index_lists_domains_and_root_lessons(self):
        sync.sync(self.root)
        text = self.read("lessons/index.md")
        self.assertIn("## Lessons", text)
        self.assertIn("hooks", text)
        self.assertIn("LESSON-loose", text)
        self.assertIn("a root lesson", text)

    def test_listing_refreshes_when_a_summary_changes(self):
        sync.sync(self.root)
        self.write(
            "lessons/hooks/LESSON-hook-a.md",
            lesson("Hook A", "matchers select tools, commands filter paths"),
        )
        sync.sync(self.root)
        text = self.read("lessons/hooks/index.md")
        self.assertIn("matchers select tools", text)
        self.assertNotIn("hooks fire from settings", text)

    def test_archived_lessons_stay_out_of_listings(self):
        self.write(
            "lessons/hooks/LESSON-old.md",
            lesson("Old", "superseded").replace("status: active", "status: archived"),
        )
        sync.sync(self.root)
        self.assertNotIn("LESSON-old", self.read("lessons/hooks/index.md"))

    def test_second_sync_is_idempotent(self):
        sync.sync(self.root)
        first = self.read("lessons/hooks/index.md")
        sync.sync(self.root)
        self.assertEqual(first, self.read("lessons/hooks/index.md"))

    def test_domain_indexes_never_enter_the_catalog(self):
        self.write(
            "lessons/subagents/index.md", domain_index("subagents", "supervising agents")
        )
        report = sync.sync(self.root)
        self.assertFalse(
            [c for c in report["catalog_collisions"] if "index.md" in c],
            "domain index.md files reported as catalog filename collisions",
        )
        catalog = (self.root / "meta" / "lessons-catalog.yaml").read_text(encoding="utf-8")
        self.assertNotIn('file: "index.md"', catalog)

    def test_stale_index_cap_warning_clears_once_back_under(self):
        warning = sync.INDEX_WARNING
        (self.root / "index.md").write_text(
            warning + "\n# Index\n", encoding="utf-8"
        )
        sync.sync(self.root)
        self.assertNotIn(warning, self.read("index.md"))

    def test_hot_path_counts_lessons_index_not_catalog(self):
        self.assertIn("lessons/index.md", hot_path.HOT_PATH_FILES)
        self.assertNotIn("meta/lessons-catalog.yaml", hot_path.HOT_PATH_FILES)
        (self.root / "meta" / "lessons-catalog.yaml").write_text(
            "x" * 40_000, encoding="utf-8"
        )
        measured = hot_path.measure(self.root)
        self.assertLess(measured, 10_000)  # the bloated catalog is not counted


if __name__ == "__main__":
    unittest.main()
