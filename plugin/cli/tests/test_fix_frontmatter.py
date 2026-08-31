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

    def test_unit_artifact_type_from_type_dir(self):
        root = make_vault(self)
        marker = write(root, "compass-cli/index.md", "---\ntitle: CLI\ntype: unit\n---\n")
        before = marker.read_text(encoding="utf-8")
        p = write(root, "compass-cli/specs/SPEC-001-thing.md", "# Thing\n\nbody\n")
        out = io.StringIO()
        with redirect_stdout(out):
            fix_frontmatter.run(["--apply"])
        data, error = vaultlib.parse_frontmatter(p)
        self.assertIsNone(error)
        self.assertEqual(data["type"], "spec")  # from the unit's own type dir
        self.assertIn("compass-cli/specs/SPEC-001-thing.md", out.getvalue())
        self.assertEqual(marker.read_text(encoding="utf-8"), before)  # marker not an artifact

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


SPEC_NO_SUMMARY = (
    "---\ntitle: Caching\ntype: spec\nstatus: approved\narea: w\n"
    "tags: [x]\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\nbody\n"
)


class LiftSummariesTests(unittest.TestCase):
    """`--lift-summaries` copies the root index's one-line description into
    the artifact's own `summary:` frontmatter (issue #16) - the text already
    exists, just in the wrong place, and lifting it is the precondition for
    ever shortening the index."""

    def _vault(self):
        root = make_vault(self)
        write(root, "specs/SPEC-001-caching.md", SPEC_NO_SUMMARY)
        return root

    def _run(self, args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = fix_frontmatter.run(args)
        return code, out.getvalue()

    def test_lifts_description_into_missing_summary(self):
        root = self._vault()
        (root / "index.md").write_text(
            "# Index\n\n## Specs\n\n- [[SPEC-001-caching]] - evict cold entries fast\n",
            encoding="utf-8")
        self._run(["--lift-summaries", "--apply"])
        data, _ = vaultlib.parse_frontmatter(root / "specs" / "SPEC-001-caching.md")
        self.assertEqual(data["summary"], "evict cold entries fast")

    def test_em_dash_separator_and_abbreviated_link_lift(self):
        root = self._vault()
        (root / "index.md").write_text(
            "# Index\n\n## Specs\n\n- [[SPEC-001]] — evict cold entries fast\n",
            encoding="utf-8")
        self._run(["--lift-summaries", "--apply"])
        data, _ = vaultlib.parse_frontmatter(root / "specs" / "SPEC-001-caching.md")
        self.assertEqual(data["summary"], "evict cold entries fast")

    def test_existing_summary_never_overwritten(self):
        root = make_vault(self)
        write(root, "specs/SPEC-001-caching.md",
              SPEC_NO_SUMMARY.replace("---\nbody",
                                      'summary: "original text"\n---\nbody'))
        (root / "index.md").write_text(
            "# Index\n\n- [[SPEC-001-caching]] - different text\n", encoding="utf-8")
        self._run(["--lift-summaries", "--apply"])
        data, _ = vaultlib.parse_frontmatter(root / "specs" / "SPEC-001-caching.md")
        self.assertEqual(data["summary"], "original text")

    def test_folder_entry_lifts_into_folder_index(self):
        root = self._vault()
        write(root, "specs/SPEC-002-pack/index.md", SPEC_NO_SUMMARY)
        write(root, "specs/SPEC-002-pack/SPEC-001-inner.md",
              SPEC_NO_SUMMARY.replace("---\nbody", 'summary: "inner"\n---\nbody'))
        (root / "index.md").write_text(
            "# Index\n\n- [[SPEC-001-caching]] - evict cold entries fast\n"
            "- [[specs/SPEC-002-pack/index|SPEC-002-pack]] (folder, 1 children)"
            " - all about packs\n",
            encoding="utf-8")
        self._run(["--lift-summaries", "--apply"])
        data, _ = vaultlib.parse_frontmatter(root / "specs" / "SPEC-002-pack" / "index.md")
        self.assertEqual(data["summary"], "all about packs")

    def test_dry_run_reports_without_writing(self):
        root = self._vault()
        (root / "index.md").write_text(
            "# Index\n\n- [[SPEC-001-caching]] - evict cold entries fast\n",
            encoding="utf-8")
        p = root / "specs" / "SPEC-001-caching.md"
        before = p.read_text(encoding="utf-8")
        code, out = self._run(["--lift-summaries"])
        self.assertEqual(code, 0)
        self.assertIn("summary", out)
        self.assertEqual(p.read_text(encoding="utf-8"), before)

    def test_conflicting_descriptions_not_lifted_and_reported(self):
        root = self._vault()
        (root / "index.md").write_text(
            "# Index\n\n- [[SPEC-001-caching]] - one description\n"
            "- [[SPEC-001-caching]] - another description\n",
            encoding="utf-8")
        code, out = self._run(["--lift-summaries", "--apply"])
        data, _ = vaultlib.parse_frontmatter(root / "specs" / "SPEC-001-caching.md")
        self.assertNotIn("summary", data)
        self.assertIn("SPEC-001-caching", out)

    def test_without_flag_summaries_stay_untouched(self):
        root = self._vault()
        (root / "index.md").write_text(
            "# Index\n\n- [[SPEC-001-caching]] - evict cold entries fast\n",
            encoding="utf-8")
        self._run(["--apply"])
        data, _ = vaultlib.parse_frontmatter(root / "specs" / "SPEC-001-caching.md")
        self.assertNotIn("summary", data)


if __name__ == "__main__":
    unittest.main()
