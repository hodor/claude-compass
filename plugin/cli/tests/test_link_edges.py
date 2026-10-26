"""Wikilinks in the shapes Obsidian documents carry: tilde and four-backtick
code fences, aliased links inside table cells (`[[x\\|alias]]`), and embeds
of images, canvases and bases. Each class pins one reading every link-aware
command shares - `validate`, `move`, `make-unit`, `sweep` and the vault
graph - so a link in code is never checked or rewritten, a table alias
resolves and survives a move, and an embed of a file that exists is never
reported broken while one that is missing still is.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vaultgraph  # noqa: E402
import vaultlib  # noqa: E402
from commands import move, sweep, validate  # noqa: E402


class FenceMask(unittest.TestCase):
    def test_tilde_fence_hides_its_lines(self):
        mask, open_ = vaultlib.fence_mask(["a", "~~~", "[[x]]", "~~~", "b"])
        self.assertEqual(mask, [False, True, True, True, False])
        self.assertFalse(open_)

    def test_three_backticks_inside_four_are_content(self):
        lines = ["````", "```", "[[x]]", "```", "````", "after"]
        mask, open_ = vaultlib.fence_mask(lines)
        self.assertEqual(mask, [True] * 5 + [False])
        self.assertFalse(open_)

    def test_backticks_do_not_close_a_tilde_fence(self):
        mask, open_ = vaultlib.fence_mask(["~~~", "```", "[[x]]", "~~~", "y"])
        self.assertEqual(mask, [True, True, True, True, False])

    def test_unclosed_fence_runs_to_the_end_and_says_so(self):
        mask, open_ = vaultlib.fence_mask(["a", "```python", "b", "c"])
        self.assertEqual(mask, [False, True, True, True])
        self.assertTrue(open_)

    def test_strip_fenced_code_keeps_line_count(self):
        text = "a\n~~~\nsecret\n~~~\nb"
        stripped, open_ = vaultlib.strip_fenced_code(text)
        self.assertEqual(stripped, "a\n\n\n\nb")
        self.assertFalse(open_)


class SplitLink(unittest.TestCase):
    def test_table_alias_backslash_goes_with_the_suffix(self):
        self.assertEqual(vaultlib.split_link("SPEC-002-b\\|B"), ("SPEC-002-b", "\\|B"))

    def test_plain_alias_and_heading(self):
        self.assertEqual(vaultlib.split_link("a|b"), ("a", "|b"))
        self.assertEqual(vaultlib.split_link("a#h|b"), ("a", "#h|b"))

    def test_backslash_before_a_heading_stays_in_the_target(self):
        self.assertEqual(vaultlib.split_link("a\\#h"), ("a\\", "#h"))


class VaultCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "specs").mkdir()
        (self.root / "specs" / "SPEC-002-b.md").write_text("---\ntitle: B\n---\n", encoding="utf-8")
        (self.root / "assets").mkdir()
        (self.root / "assets" / "pic.png").write_bytes(b"\x89PNG")
        (self.root / "map.canvas").write_text("{}", encoding="utf-8")
        (self.root / "tasks.base").write_text("views: []\n", encoding="utf-8")
        (self.root / ".obsidian").mkdir()
        (self.root / ".obsidian" / "hidden.png").write_bytes(b"x")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def warnings_for(self, body):
        warnings = []
        validate._check_links(
            "specs/SPEC-001-a.md", body, vaultlib.resolvable_names_map(self.root), warnings,
            vaultlib.attachment_names(self.root))
        return warnings


class ValidateLinks(VaultCase):
    def test_table_alias_resolves(self):
        self.assertEqual(self.warnings_for("| [[SPEC-002-b\\|B]] | 1 |\n"), [])

    def test_embeds_of_existing_files_resolve(self):
        body = "![[pic.png]]\n![[assets/pic.png]]\n![[map.canvas]]\n![[tasks.base]]\n"
        self.assertEqual(self.warnings_for(body), [])

    def test_embed_of_a_missing_file_is_broken(self):
        self.assertEqual(self.warnings_for("![[gone.png]]\n"),
                         ["broken_wikilink: specs/SPEC-001-a.md:1: [[gone.png]]"])

    def test_dot_directory_files_are_not_attachments(self):
        self.assertNotIn("hidden.png", vaultlib.attachment_names(self.root))
        self.assertEqual(len(self.warnings_for("![[hidden.png]]\n")), 1)

    def test_attachment_names_never_resolve_a_bare_stem(self):
        self.assertEqual(len(self.warnings_for("[[pic]]\n")), 1)

    def test_links_in_tilde_and_four_backtick_fences_are_skipped(self):
        body = "~~~\n[[NOPE-a]]\n~~~\n````\n```\n[[NOPE-b]]\n```\n````\n[[NOPE-c]]\n"
        self.assertEqual(self.warnings_for(body),
                         ["broken_wikilink: specs/SPEC-001-a.md:9: [[NOPE-c]]"])


class MoveRewrite(unittest.TestCase):
    renames = {"SPEC-002-b": "specs/d/SPEC-002-b"}

    def test_table_alias_is_rewritten_with_its_escape(self):
        text, n = move._rewrite_links("| [[SPEC-002-b\\|B]] |", self.renames)
        self.assertEqual((text, n), ("| [[specs/d/SPEC-002-b\\|B]] |", 1))

    def test_links_in_tilde_and_four_backtick_fences_stay(self):
        text = "~~~\n[[SPEC-002-b]]\n~~~\n````\n```\n[[SPEC-002-b]]\n```\n````\n[[SPEC-002-b]]"
        out, n = move._rewrite_links(text, self.renames)
        self.assertEqual(n, 1)
        self.assertEqual(out.split("\n")[1], "[[SPEC-002-b]]")
        self.assertEqual(out.split("\n")[5], "[[SPEC-002-b]]")
        self.assertEqual(out.split("\n")[8], "[[specs/d/SPEC-002-b]]")


class GraphLinks(unittest.TestCase):
    def test_body_links_skip_tilde_fences_and_read_table_aliases(self):
        text = "---\nt: 1\n---\n~~~\n[[in-code]]\n~~~\n| [[SPEC-002-b\\|B]] |\n"
        self.assertEqual(list(vaultgraph._body_links(text)), ["SPEC-002-b"])


class SweepSections(unittest.TestCase):
    def test_heading_inside_a_tilde_fence_opens_no_section(self):
        sections = sweep._parse_sections(["~~~", "## not a heading", "~~~", "## Real"])
        self.assertEqual([heading for heading, _ in sections], [None, "## Real"])

    def test_task_line_inside_a_tilde_fence_is_text(self):
        blocks = sweep._parse_items(["~~~", "- [x] quoted", "~~~", "- [x] real"])
        self.assertEqual([kind for kind, _ in blocks], ["text", "text", "text", "done"])


if __name__ == "__main__":
    unittest.main()
