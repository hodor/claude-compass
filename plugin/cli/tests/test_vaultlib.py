"""Tests for the shared vault library."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vaultlib  # noqa: E402


def make_tempdir(test_case):
    """Create a temp dir cleaned up when the test finishes."""
    tmp = tempfile.mkdtemp()
    test_case.addCleanup(shutil.rmtree, tmp, True)
    return Path(tmp)


VALID_FRONTMATTER = """---
title: A Spec
type: spec
status: approved
area: methodology
tags: [token-efficiency, hooks, cli]
depends_on:
  - "[[SPEC-001-foo]]"
  - "[[LESSON-bar]]"
created: 2026-06-14
---

# Body
Some text.
"""


class ParseFrontmatterTests(unittest.TestCase):
    def test_scalars_inline_list_and_block_list(self):
        data, error = vaultlib.parse_frontmatter_text(VALID_FRONTMATTER)
        self.assertIsNone(error)
        self.assertEqual(data["title"], "A Spec")
        self.assertEqual(data["type"], "spec")
        self.assertEqual(data["status"], "approved")
        self.assertEqual(data["tags"], ["token-efficiency", "hooks", "cli"])
        self.assertEqual(data["depends_on"], ["[[SPEC-001-foo]]", "[[LESSON-bar]]"])

    def test_missing_frontmatter_reports_error(self):
        data, error = vaultlib.parse_frontmatter_text("# Just a heading\n\ntext\n")
        self.assertEqual(data, {})
        self.assertEqual(error, "no frontmatter")

    def test_unterminated_frontmatter_reports_error(self):
        data, error = vaultlib.parse_frontmatter_text("---\ntitle: X\ntype: spec\n")
        self.assertEqual(data, {})
        self.assertEqual(error, "unterminated frontmatter")

    def test_empty_inline_list(self):
        data, error = vaultlib.parse_frontmatter_text("---\ntags: []\n---\n")
        self.assertIsNone(error)
        self.assertEqual(data["tags"], [])

    def test_quoted_values_are_unwrapped(self):
        data, _ = vaultlib.parse_frontmatter_text('---\ngit_branch: "master"\n---\n')
        self.assertEqual(data["git_branch"], "master")


class ScanArtifactsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = make_tempdir(self)

    def _write(self, rel, body="---\ntype: spec\n---\n"):
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_flat_folder_and_nested_classification(self):
        self._write("specs/SPEC-001-flat.md")
        self._write("specs/SPEC-002-tile-editor/index.md")
        self._write("specs/SPEC-002-tile-editor/SPEC-001-master-material.md")
        self._write("specs/SPEC-002-tile-editor/SPEC-002-brush/index.md")
        self._write("specs/SPEC-002-tile-editor/SPEC-002-brush/SPEC-001-stroke.md")

        records = vaultlib.scan_artifacts(self.tmp)
        by_name = {r["name"]: r for r in records}

        self.assertEqual(by_name["SPEC-001-flat"]["kind"], "flat")
        self.assertEqual(by_name["SPEC-002-tile-editor"]["kind"], "folder-index")
        self.assertEqual(
            by_name["SPEC-002-tile-editor/SPEC-001-master-material"]["kind"], "child"
        )
        self.assertEqual(
            by_name["SPEC-002-tile-editor/SPEC-002-brush"]["kind"], "folder-index"
        )
        self.assertEqual(
            by_name["SPEC-002-tile-editor/SPEC-002-brush/SPEC-001-stroke"]["depth"], 2
        )

    def test_missing_type_dirs_are_skipped(self):
        self._write("specs/SPEC-001-only.md")
        records = vaultlib.scan_artifacts(self.tmp)
        self.assertEqual(len(records), 1)


class DiscoverTypeDirsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = make_tempdir(self)

    def _write(self, rel, body):
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def test_core_dirs_typed_extras_yes_untyped_junk_no(self):
        # core dir (always), even empty
        (self.tmp / "specs").mkdir()
        # custom dir WITH a typed artifact -> included
        self._write("retro/RETRO-1.md", "---\ntype: retro\n---\nx\n")
        # incidental dir of non-artifact md (e.g. a symlinked install) -> excluded
        self._write("claude/CLAUDE.md", "# Project instructions\n")
        self._write("claude/agents/builder.md", "---\nname: builder\n---\nx\n")
        # reserved dirs -> excluded
        (self.tmp / "meta").mkdir()
        (self.tmp / "tmp").mkdir()

        dirs = vaultlib.discover_type_dirs(self.tmp)
        self.assertIn("specs", dirs)
        self.assertIn("retro", dirs)
        self.assertNotIn("claude", dirs)
        self.assertNotIn("meta", dirs)
        self.assertNotIn("tmp", dirs)


class WriteTextLfTests(unittest.TestCase):
    def test_no_carriage_return_in_output(self):
        target = make_tempdir(self) / "out.md"
        vaultlib.write_text_lf(target, "line1\r\nline2\rline3\n")
        raw = target.read_bytes()
        self.assertNotIn(b"\r", raw)
        self.assertEqual(raw, b"line1\nline2\nline3\n")


class CountTokensTests(unittest.TestCase):
    def test_approximation(self):
        self.assertEqual(vaultlib.count_tokens("a" * 40), 10)
        self.assertEqual(vaultlib.count_tokens(""), 0)


class FindVaultRootTests(unittest.TestCase):
    def test_env_var_takes_precedence(self):
        tmp = make_tempdir(self)
        (tmp / ".compass").mkdir()
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(tmp)
        try:
            self.assertEqual(
                vaultlib.find_vault_root().resolve(), (tmp / ".compass").resolve()
            )
        finally:
            if old is None:
                del os.environ["CLAUDE_PROJECT_DIR"]
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = old

    def test_walks_up_to_find_vault(self):
        tmp = make_tempdir(self)
        (tmp / ".compass").mkdir()
        nested = tmp / "a" / "b"
        nested.mkdir(parents=True)
        old = os.environ.pop("CLAUDE_PROJECT_DIR", None)
        try:
            self.assertEqual(
                vaultlib.find_vault_root(start=nested).resolve(),
                (tmp / ".compass").resolve(),
            )
        finally:
            if old is not None:
                os.environ["CLAUDE_PROJECT_DIR"] = old


if __name__ == "__main__":
    unittest.main()
