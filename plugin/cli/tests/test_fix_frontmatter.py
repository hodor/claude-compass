"""Tests for `compass fix-frontmatter`."""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vaultlib  # noqa: E402
from commands import fix_frontmatter, validate  # noqa: E402


def make_vault(test_case):
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    root = tmp / ".compass"
    (root / "meta").mkdir(parents=True)
    old = os.environ.get("CLAUDE_PROJECT_DIR")
    os.environ["CLAUDE_PROJECT_DIR"] = str(root.parent)
    test_case.addCleanup(
        lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
        else os.environ.pop("CLAUDE_PROJECT_DIR", None)
    )
    return root


def write(root, rel, body):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


class FixFrontmatterTests(unittest.TestCase):
    def test_dry_run_does_not_write(self):
        root = make_vault(self)
        p = write(root, "research/READING-NOTES.md", "# Reading Notes\n\nbody\n")
        before = p.read_text(encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            fix_frontmatter.run([])
        self.assertEqual(p.read_text(encoding="utf-8"), before)

    def test_apply_adds_frontmatter_with_derived_values(self):
        root = make_vault(self)
        p = write(root, "research/READING-NOTES.md", "# Reading Notes\n\nbody\n")
        with redirect_stdout(io.StringIO()):
            fix_frontmatter.run(["--apply"])
        data, error = vaultlib.parse_frontmatter(p)
        self.assertIsNone(error)
        self.assertEqual(data["type"], "research")        # from the directory
        self.assertEqual(data["title"], "Reading Notes")  # from the first heading
        self.assertEqual(data["status"], "draft")
        self.assertIn("created", data)
        self.assertTrue(p.read_text(encoding="utf-8").endswith("body\n"))  # body preserved

    def test_title_falls_back_to_filename(self):
        root = make_vault(self)
        # A custom dir is recognized once it holds a typed artifact; the untyped
        # sibling then gets fixed with type from the dir and title from filename.
        write(root, "retro/RETRO-existing.md",
              "---\ntitle: E\ntype: retro\nstatus: active\n---\nx\n")
        p = write(root, "retro/RETRO-2026-01-01-day.md", "no heading here\n")
        with redirect_stdout(io.StringIO()):
            fix_frontmatter.run(["--apply"])
        data, _ = vaultlib.parse_frontmatter(p)
        self.assertEqual(data["type"], "retro")           # unknown dir -> dir name
        self.assertIn("RETRO", data["title"])

    def test_inserts_missing_core_field(self):
        root = make_vault(self)
        p = write(root, "handoffs/HANDOFF-x.md",
                  "---\ntitle: H\ntype: handoff\narea: w\n---\nbody\n")
        with redirect_stdout(io.StringIO()):
            fix_frontmatter.run(["--apply"])
        data, _ = vaultlib.parse_frontmatter(p)
        self.assertEqual(data["status"], "draft")
        self.assertEqual(data["title"], "H")  # existing field untouched

    def test_clean_vault_nothing_to_fix(self):
        root = make_vault(self)
        write(root, "specs/SPEC-001.md",
              "---\ntitle: T\ntype: spec\nstatus: approved\n---\nbody\n")
        out = io.StringIO()
        with redirect_stdout(out):
            code = fix_frontmatter.run([])
        self.assertEqual(code, 0)
        self.assertIn("nothing to fix", out.getvalue())

    def test_apply_clears_validate_errors(self):
        root = make_vault(self)
        write(root, "research/READING-NOTES.md", "# Notes\nbody\n")
        write(root, "handoffs/HANDOFF-x.md", "---\ntitle: H\ntype: handoff\n---\nbody\n")
        errors_before, _ = validate.check_vault(root)
        self.assertTrue(errors_before)
        with redirect_stdout(io.StringIO()):
            fix_frontmatter.run(["--apply"])
        errors_after, _ = validate.check_vault(root)
        self.assertEqual(errors_after, [])


if __name__ == "__main__":
    unittest.main()
