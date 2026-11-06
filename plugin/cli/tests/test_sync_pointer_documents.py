"""Tests for `compass sync` honouring pointer documents.

An index section may link a pointer document (an `archive/` document that
lists artifacts one click further away). An artifact that document links
counts as already indexed, so sync does not list it again in the section.
Only the document the section links itself counts: a document reached
through another link, a document outside `archive/`, and a document linked
from a different section index nothing.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import sync  # noqa: E402


def handoff(title):
    return (
        f"---\ntitle: {title}\ntype: handoff\nstatus: active\narea: workflow\n"
        f'tags: [x]\nsummary: "summary of {title}"\ncreated: 2026-08-30\n'
        f"updated: 2026-08-30\n---\n\nbody\n"
    )


def spec(title):
    return (
        f"---\ntitle: {title}\ntype: spec\nstatus: approved\narea: workflow\n"
        f'tags: [x]\nsummary: "summary of {title}"\ncreated: 2026-08-30\n'
        f"updated: 2026-08-30\n---\n\nbody\n"
    )


def archive_doc(title, links):
    body = "\n".join(f"- {link}" for link in links)
    return (
        f"---\ntitle: {title}\ntype: archive\nstatus: active\n"
        f'summary: "pointers"\ncreated: 2026-11-01\nupdated: 2026-11-01\n---\n\n'
        f"# {title}\n\n{body}\n"
    )


INDEX = """# Index

## Specs

## Handoffs

- [[handoff-pointers|Older handoffs]] - every earlier handoff

## Lessons
"""


class PointerDocumentSyncTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = tmp / ".compass"
        for sub in ("meta", "specs", "lessons", "handoffs", "archive"):
            (self.root / sub).mkdir(parents=True)
        (self.root / "index.md").write_text(INDEX, encoding="utf-8")

    def write(self, rel, body):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def index_text(self):
        return (self.root / "index.md").read_text(encoding="utf-8")

    def section(self, heading):
        text = self.index_text()
        start = text.index(heading)
        rest = text[start + len(heading):]
        end = rest.find("\n## ")
        return rest if end == -1 else rest[:end]

    def test_handoff_linked_by_pointer_document_is_not_added(self):
        self.write("handoffs/2026-03-12_old.md", handoff("Old"))
        self.write("archive/handoff-pointers.md",
                   archive_doc("Older handoffs", ["[[2026-03-12_old]] - old one"]))
        report = sync.sync(self.root)
        self.assertNotIn("handoffs", report["index_added"])
        self.assertNotIn("[[2026-03-12_old]]", self.index_text())

    def test_second_run_still_does_not_re_add(self):
        self.write("handoffs/2026-03-12_old.md", handoff("Old"))
        self.write("archive/handoff-pointers.md",
                   archive_doc("Older handoffs", ["[[2026-03-12_old]]"]))
        sync.sync(self.root)
        first = self.index_text()
        sync.sync(self.root)
        self.assertEqual(self.index_text(), first)
        self.assertNotIn("2026-03-12_old", first)

    def test_handoff_linked_nowhere_is_still_added(self):
        self.write("handoffs/2026-03-12_old.md", handoff("Old"))
        self.write("handoffs/2026-11-02_new.md", handoff("New"))
        self.write("archive/handoff-pointers.md",
                   archive_doc("Older handoffs", ["[[2026-03-12_old]]"]))
        report = sync.sync(self.root)
        self.assertEqual(report["index_added"].get("handoffs"), 1)
        handoffs = self.section("## Handoffs")
        self.assertIn("[[2026-11-02_new]]", handoffs)
        self.assertNotIn("[[2026-03-12_old]]", handoffs)

    def test_pointer_document_two_links_away_does_not_count(self):
        self.write("handoffs/2026-03-12_deep.md", handoff("Deep"))
        self.write("archive/handoff-pointers.md",
                   archive_doc("Older handoffs", ["[[second-hop]]"]))
        self.write("archive/second-hop.md",
                   archive_doc("Second hop", ["[[2026-03-12_deep]]"]))
        sync.sync(self.root)
        self.assertIn("[[2026-03-12_deep]]", self.section("## Handoffs"))

    def test_pointer_document_linking_nothing_changes_nothing(self):
        self.write("handoffs/2026-03-12_old.md", handoff("Old"))
        self.write("archive/handoff-pointers.md",
                   archive_doc("Older handoffs", []))
        sync.sync(self.root)
        handoffs = self.section("## Handoffs")
        self.assertIn("[[2026-03-12_old]]", handoffs)
        self.assertIn("[[handoff-pointers|Older handoffs]]", handoffs)

    def test_pointer_document_with_only_broken_links_does_not_crash(self):
        self.write("handoffs/2026-03-12_old.md", handoff("Old"))
        self.write("archive/handoff-pointers.md",
                   archive_doc("Older handoffs", ["[[no-such-document]]", "[[ ]]"]))
        sync.sync(self.root)
        self.assertIn("[[2026-03-12_old]]", self.section("## Handoffs"))

    def test_alias_heading_and_path_qualified_links_count(self):
        self.write("handoffs/2026-03-12_a.md", handoff("A"))
        self.write("handoffs/2026-03-13_b.md", handoff("B"))
        self.write("handoffs/PLAN-001-x/2026-03-14_c.md", handoff("C"))
        self.write("archive/handoff-pointers.md", archive_doc("Older handoffs", [
            "[[2026-03-12_a|first]]",
            "[[2026-03-13_b#Session Summary]]",
            "[[handoffs/PLAN-001-x/2026-03-14_c]]",
        ]))
        report = sync.sync(self.root)
        self.assertNotIn("handoffs", report["index_added"])
        handoffs = self.section("## Handoffs")
        for stem in ("2026-03-12_a", "2026-03-13_b", "2026-03-14_c"):
            self.assertNotIn(stem, handoffs)

    def test_document_outside_archive_does_not_count_as_pointer(self):
        self.write("specs/SPEC-002-child.md", spec("Child"))
        self.write("specs/SPEC-001-parent.md",
                   spec("Parent") + "\nSee [[SPEC-002-child]].\n")
        (self.root / "index.md").write_text(
            INDEX.replace("## Specs\n", "## Specs\n\n- [[SPEC-001-parent]] - parent\n"),
            encoding="utf-8",
        )
        sync.sync(self.root)
        self.assertIn("[[SPEC-002-child]]", self.section("## Specs"))

    def test_pointer_document_linked_from_another_section_does_not_count(self):
        self.write("handoffs/2026-03-12_old.md", handoff("Old"))
        self.write("archive/handoff-pointers.md",
                   archive_doc("Older handoffs", ["[[2026-03-12_old]]"]))
        text = INDEX.replace(
            "- [[handoff-pointers|Older handoffs]] - every earlier handoff\n", ""
        ).replace("## Specs\n", "## Specs\n\n- [[handoff-pointers|Older handoffs]]\n")
        (self.root / "index.md").write_text(text, encoding="utf-8")
        sync.sync(self.root)
        self.assertIn("[[2026-03-12_old]]", self.section("## Handoffs"))


if __name__ == "__main__":
    unittest.main()
