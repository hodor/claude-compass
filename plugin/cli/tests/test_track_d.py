"""Tests for promote, touched, admit-check."""

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
from commands import promote, touched, admit_check  # noqa: E402

SPEC = (
    "---\ntitle: Tile\ntype: spec\nstatus: approved\narea: w\n"
    "tags: [x]\ncreated: 2026-06-14\nupdated: 2026-06-14\n---\n\nbody\n"
)


def make_vault(test_case):
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    root = tmp / ".compass"
    (root / "meta").mkdir(parents=True)
    return root


def use_vault(test_case, root):
    old = os.environ.get("CLAUDE_PROJECT_DIR")
    os.environ["CLAUDE_PROJECT_DIR"] = str(root.parent)
    test_case.addCleanup(
        lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
        else os.environ.pop("CLAUDE_PROJECT_DIR", None)
    )


class PromoteTests(unittest.TestCase):
    def test_dry_run_makes_no_changes(self):
        """`promote` gained the same dry-run/--apply gate `make-unit` and
        `demote` already carry - a bare invocation must preview, not act."""
        root = make_vault(self)
        (root / "specs").mkdir()
        (root / "specs" / "SPEC-002-tile.md").write_text(SPEC, encoding="utf-8")
        use_vault(self, root)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(promote.run(["SPEC-002-tile"]), 0)
        self.assertIn("dry-run", out.getvalue())
        self.assertTrue((root / "specs" / "SPEC-002-tile.md").is_file())
        self.assertFalse((root / "specs" / "SPEC-002-tile").exists())

    def test_flat_to_folder(self):
        root = make_vault(self)
        (root / "specs").mkdir()
        (root / "specs" / "SPEC-002-tile.md").write_text(SPEC, encoding="utf-8")
        use_vault(self, root)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(
                promote.run(["SPEC-002-tile", "--reason", "splitting into sub-concerns", "--apply"]), 0
            )
        self.assertFalse((root / "specs" / "SPEC-002-tile.md").exists())
        index = root / "specs" / "SPEC-002-tile" / "index.md"
        self.assertTrue(index.exists())
        text = index.read_text(encoding="utf-8")
        self.assertIn("children_count: 0", text)
        self.assertIn("body", text)  # body preserved

    def test_missing_spec_errors(self):
        root = make_vault(self)
        (root / "specs").mkdir()
        use_vault(self, root)
        self.assertEqual(promote.run(["SPEC-099-nope"]), 1)

    def test_refuses_already_folder(self):
        root = make_vault(self)
        folder = root / "specs" / "SPEC-002-tile"
        folder.mkdir(parents=True)
        (folder / "index.md").write_text(SPEC, encoding="utf-8")
        use_vault(self, root)
        self.assertEqual(promote.run(["specs/SPEC-002-tile/index.md"]), 1)


class TouchedTests(unittest.TestCase):
    def test_append_dedup_and_cap(self):
        root = make_vault(self)
        use_vault(self, root)
        for i in range(12):
            touched.run([f"specs/SPEC-{i:03d}.md"])
        items = touched.load(root)
        self.assertEqual(len(items), 10)  # capped
        self.assertEqual(items[-1], "specs/SPEC-011.md")

    def test_dedup_moves_to_end(self):
        root = make_vault(self)
        use_vault(self, root)
        touched.run(["a"])
        touched.run(["b"])
        touched.run(["a"])
        self.assertEqual(touched.load(root), ["b", "a"])


class AdmitCheckTests(unittest.TestCase):
    def test_not_in_working_set_rejected(self):
        root = make_vault(self)
        use_vault(self, root)
        self.assertEqual(admit_check.run(["specs/SPEC-001.md"]), 1)

    def test_in_set_under_cap_admitted(self):
        root = make_vault(self)
        (root / "specs").mkdir()
        (root / "specs" / "SPEC-001.md").write_text("small", encoding="utf-8")
        use_vault(self, root)
        touched.run(["specs/SPEC-001.md"])
        self.assertEqual(admit_check.run(["specs/SPEC-001.md"]), 0)

    def test_over_cap_rejected(self):
        root = make_vault(self)
        (root / "specs").mkdir()
        (root / "specs" / "SPEC-001.md").write_text("x" * 40000, encoding="utf-8")  # ~10k tokens
        use_vault(self, root)
        touched.run(["specs/SPEC-001.md"])
        self.assertEqual(admit_check.run(["specs/SPEC-001.md"]), 1)


if __name__ == "__main__":
    unittest.main()
