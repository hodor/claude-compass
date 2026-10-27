"""`compass validate` resolves block links: `[[doc#^id]]` warns
`broken_block_link` when the target document carries no line ending in
`^id`. A block link counts only where a wikilink counts (never inside code),
and an id counts only where Obsidian reads it (never inside a fence).
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import validate  # noqa: E402

FRONT = (
    "---\ntitle: T\ntype: spec\nstatus: approved\narea: x\ntags: [a]\n"
    "created: 2026-06-14\nupdated: 2026-06-14\nsummary: \"a spec\"\n---\n\n"
)
CODE = "broken_block_link"


class BlockLinkTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = tmp / ".compass"
        self.root.mkdir()
        (self.root / "index.md").write_text("# Index\n", encoding="utf-8")

    def write(self, rel, body):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(FRONT + body, encoding="utf-8")

    def block_warnings(self, target_body, source_body):
        """Write a target and a source, run the vault check, and return the
        broken_block_link warnings the source earned."""
        self.write("specs/SPEC-001-target.md", target_body)
        self.write("specs/SPEC-002-source.md", source_body)
        _, warnings = validate.check_vault(self.root)
        return [w for w in warnings if w.startswith(CODE)]

    def test_block_link_resolves_only_to_an_id_the_target_carries(self):
        """Adversarial where: a resolver that checks only that the document
        exists, or that finds the id by substring, passes `^d-01` against a
        target holding `^d-010`, or against an id quoted in a fenced
        example, and the citation points at nothing. Rows pair each link
        shape with a target that does or does not carry the exact id."""
        rows = [
            ("id at the end of a plain line",
             "A ruling. ^d-01\n", "See [[SPEC-001-target#^d-01]].\n", 0),
            ("id at the end of a callout line",
             "> [!important] You decide\n> - **D-01:** Ship it. ^d-01\n",
             "See [[SPEC-001-target#^d-01]].\n", 0),
            ("id alone on its own line after a block",
             "| a | b |\n| - | - |\n| 1 | 2 |\n\n^tbl\n",
             "See [[SPEC-001-target#^tbl]].\n", 0),
            ("trailing spaces after the id",
             "A ruling. ^d-01   \n", "See [[SPEC-001-target#^d-01]].\n", 0),
            ("missing id",
             "A ruling. ^d-01\n", "See [[SPEC-001-target#^d-02]].\n", 1),
            ("longer id does not satisfy a shorter link",
             "A ruling. ^d-010\n", "See [[SPEC-001-target#^d-01]].\n", 1),
            ("shorter id does not satisfy a longer link",
             "A ruling. ^d-01\n", "See [[SPEC-001-target#^d-010]].\n", 1),
            ("id quoted inside a fenced example is not an id",
             "```markdown\nA ruling. ^d-01\n```\n",
             "See [[SPEC-001-target#^d-01]].\n", 1),
            ("target without any id",
             "Plain prose.\n", "See [[SPEC-001-target#^d-01]].\n", 1),
            ("aliased link, id present",
             "A ruling. ^d-01\n", "See [[SPEC-001-target#^d-01|the ruling]].\n", 0),
            ("aliased link, id missing",
             "A ruling. ^d-01\n", "See [[SPEC-001-target#^d-09|the ruling]].\n", 1),
            ("table alias with escaped pipe, id missing",
             "A ruling. ^d-01\n", "| [[SPEC-001-target#^d-09\\|r]] | 1 |\n", 1),
            ("path-qualified link, id missing",
             "A ruling. ^d-01\n", "See [[specs/SPEC-001-target#^d-09]].\n", 1),
            ("heading link is not a block link",
             "## Decisions\n\nA ruling.\n", "See [[SPEC-001-target#Decisions]].\n", 0),
            ("two links, one good one bad",
             "A ruling. ^d-01\n",
             "See [[SPEC-001-target#^d-01]] and [[SPEC-001-target#^d-02]].\n", 1),
        ]
        for name, target, source, expected in rows:
            with self.subTest(name=name):
                found = self.block_warnings(target, source)
                self.assertEqual(len(found), expected, found)
                for warning in found:
                    self.assertIn("specs/SPEC-002-source.md", warning)

    def test_warning_names_the_missing_id(self):
        """Adversarial where: a warning that says only `broken_block_link`
        without the id sends the reader hunting through the file for which
        of several links broke."""
        found = self.block_warnings(
            "A ruling. ^d-01\n",
            "Good [[SPEC-001-target#^d-01]], bad [[SPEC-001-target#^d-77]].\n")
        self.assertEqual(len(found), 1)
        self.assertIn("^d-77", found[0])
        self.assertNotIn("^d-01", found[0])

    def test_block_link_in_code_is_skipped(self):
        """Adversarial where: documentation that shows a block link as an
        example (inline code, a fence of either marker, an indented four
        backtick fence holding three) is not a citation. Only the plain
        link after the code earns a warning, so a validator that scans raw
        text reports every example as broken."""
        source = (
            "Inline `[[SPEC-001-target#^nope-a]]` is an example.\n"
            "~~~\n[[SPEC-001-target#^nope-b]]\n~~~\n"
            "````\n```\n[[SPEC-001-target#^nope-c]]\n```\n````\n"
            "```markdown\n[[SPEC-001-target#^nope-d]]\n```\n"
            "Real [[SPEC-001-target#^nope-e]].\n"
        )
        found = self.block_warnings("A ruling. ^d-01\n", source)
        self.assertEqual(len(found), 1, found)
        self.assertIn("^nope-e", found[0])

    def test_block_link_in_a_callout_is_checked(self):
        """Adversarial where: the link scan treats a `>` line as quoted text
        and skips it, so a citation inside the "You decide" callout breaks
        silently while the same link in prose is caught."""
        source = "> [!important] You decide\n> See [[SPEC-001-target#^d-09]].\n"
        found = self.block_warnings("A ruling. ^d-01\n", source)
        self.assertEqual(len(found), 1, found)
        self.assertIn("^d-09", found[0])


if __name__ == "__main__":
    unittest.main()
