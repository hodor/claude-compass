"""Tests for Phase 2 read-only commands and validate."""

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
from commands import next_num, tree, hot_path, validate  # noqa: E402


def make_vault(test_case):
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    (tmp / ".compass").mkdir()
    return tmp / ".compass"


def write(root, rel, body="---\ntype: spec\n---\n"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def with_vault_env(test_case, vault_root):
    """Point find_vault_root at this vault for the duration of the test."""
    old = os.environ.get("CLAUDE_PROJECT_DIR")
    os.environ["CLAUDE_PROJECT_DIR"] = str(vault_root.parent)

    def restore():
        if old is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = old

    test_case.addCleanup(restore)


class NextNumTests(unittest.TestCase):
    def test_max_plus_one(self):
        root = make_vault(self)
        for n in (1, 2, 3, 4):
            write(root, f"specs/SPEC-00{n}-thing.md")
        with_vault_env(self, root)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(next_num.run(["spec"]), 0)
        self.assertEqual(out.getvalue().strip(), "005")

    def test_empty_type_starts_at_one(self):
        root = make_vault(self)
        (root / "specs").mkdir()
        with_vault_env(self, root)
        out = io.StringIO()
        with redirect_stdout(out):
            next_num.run(["spec"])
        self.assertEqual(out.getvalue().strip(), "001")

    def test_local_numbering_inside_folder(self):
        root = make_vault(self)
        write(root, "specs/SPEC-002-tile/SPEC-001-a.md")
        write(root, "specs/SPEC-002-tile/SPEC-002-b.md")
        with_vault_env(self, root)
        out = io.StringIO()
        with redirect_stdout(out):
            next_num.run(["spec", "SPEC-002-tile"])
        self.assertEqual(out.getvalue().strip(), "003")

    def test_unnumbered_type_errors(self):
        root = make_vault(self)
        with_vault_env(self, root)
        self.assertEqual(next_num.run(["handoff"]), 1)


class TreeTests(unittest.TestCase):
    def test_nested_rendering(self):
        root = make_vault(self)
        write(root, "specs/SPEC-001-flat.md")
        write(root, "specs/SPEC-002-tile/index.md")
        write(root, "specs/SPEC-002-tile/SPEC-001-master.md")
        rendered = tree.render(root)
        self.assertEqual(
            rendered,
            "specs\n  SPEC-001-flat\n  SPEC-002-tile/\n    SPEC-001-master",
        )


class HotPathTests(unittest.TestCase):
    def test_token_sum(self):
        root = make_vault(self)
        (root / "meta").mkdir()
        (root / "index.md").write_text("a" * 400, encoding="utf-8")
        (root / "active.md").write_text("b" * 400, encoding="utf-8")
        (root / "meta" / "lessons-catalog.yaml").write_text("c" * 400, encoding="utf-8")
        self.assertEqual(hot_path.measure(root), 300)  # 1200 chars / 4


class ValidateTests(unittest.TestCase):
    SPEC_OK = (
        "---\ntitle: T\ntype: spec\nstatus: approved\narea: x\n"
        "tags: [a]\ncreated: 2026-06-14\nupdated: 2026-06-14\n---\n\n"
        "Refers to [[SPEC-001-target]].\n"
    )

    def _clean_vault(self):
        root = make_vault(self)
        write(root, "specs/SPEC-001-target.md", self.SPEC_OK)
        (root / "index.md").write_text("# Index\n", encoding="utf-8")
        return root

    def test_clean_vault(self):
        self.assertEqual(validate.check_vault(self._clean_vault()), ([], []))

    def test_broken_wikilink_is_warning_not_error(self):
        root = self._clean_vault()
        write(root, "specs/SPEC-002-bad.md",
              self.SPEC_OK.replace("[[SPEC-001-target]]", "[[NoSuchSpec]]"))
        errors, warnings = validate.check_vault(root)
        self.assertTrue(any("NoSuchSpec" in w for w in warnings))
        self.assertFalse(any("NoSuchSpec" in e for e in errors))

    def test_missing_core_field_is_error(self):
        root = self._clean_vault()
        write(root, "specs/SPEC-003-nostatus.md", self.SPEC_OK.replace("status: approved\n", ""))
        errors, _ = validate.check_vault(root)
        self.assertTrue(any("status" in e for e in errors))

    def test_missing_recommended_field_is_warning(self):
        root = self._clean_vault()
        write(root, "specs/SPEC-004-noarea.md", self.SPEC_OK.replace("area: x\n", ""))
        errors, warnings = validate.check_vault(root)
        self.assertTrue(any("area" in w for w in warnings))
        self.assertFalse(any("area" in e for e in errors))

    def test_wikilinks_in_code_ignored(self):
        root = self._clean_vault()
        body = self.SPEC_OK + "\nInline `[[NotReal]]` and fenced:\n```\n[[AlsoNotReal]]\n```\n"
        write(root, "specs/SPEC-005-code.md", body)
        errors, warnings = validate.check_vault(root)
        self.assertFalse(any("NotReal" in f for f in errors + warnings))

    def test_link_to_custom_type_dir_resolves(self):
        root = self._clean_vault()
        write(root, "retro/RETRO-2026-01-01-day.md",
              "---\ntitle: R\ntype: retro\nstatus: active\n---\nbody\n")
        write(root, "specs/SPEC-006-ref.md",
              self.SPEC_OK.replace("[[SPEC-001-target]]", "[[RETRO-2026-01-01-day]]"))
        errors, warnings = validate.check_vault(root)
        self.assertFalse(any("RETRO-2026-01-01-day" in f for f in errors + warnings))

    def test_link_to_archived_artifact_resolves(self):
        root = self._clean_vault()
        write(root, "archive/SPEC-099-old.md", "---\ntitle: O\ntype: spec\nstatus: archived\n---\nx\n")
        write(root, "specs/SPEC-007-ref.md",
              self.SPEC_OK.replace("[[SPEC-001-target]]", "[[SPEC-099-old]]"))
        errors, warnings = validate.check_vault(root)
        self.assertFalse(any("SPEC-099-old" in f for f in errors + warnings))

    def test_line_cap_is_warning(self):
        root = self._clean_vault()
        (root / "index.md").write_text("\n".join(f"line {i}" for i in range(260)), encoding="utf-8")
        errors, warnings = validate.check_vault(root)
        self.assertTrue(any("cap_exceeded" in w and "lines" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
