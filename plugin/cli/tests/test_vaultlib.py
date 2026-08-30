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
        self.assertEqual(by_name["specs/SPEC-002-tile-editor"]["kind"], "folder-index")
        self.assertEqual(
            by_name["specs/SPEC-002-tile-editor/SPEC-001-master-material"]["kind"], "child"
        )
        self.assertEqual(
            by_name["specs/SPEC-002-tile-editor/SPEC-002-brush"]["kind"], "folder-index"
        )
        self.assertEqual(
            by_name["specs/SPEC-002-tile-editor/SPEC-002-brush/SPEC-001-stroke"]["depth"], 2
        )

    def test_missing_type_dirs_are_skipped(self):
        self._write("specs/SPEC-001-only.md")
        records = vaultlib.scan_artifacts(self.tmp)
        self.assertEqual(len(records), 1)


class LooseNestedDocTests(unittest.TestCase):
    """A child record whose immediate parent folder has no `index.md` of
    its own (a plain grouping subfolder, not a folder-spec) is "loose": its
    `name` is the full vault-relative form so it stays unique against a
    same-named file in a sibling subfolder (issue #1)."""

    def setUp(self):
        self.tmp = make_tempdir(self)

    def _write(self, rel, body="---\ntype: research\n---\n"):
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_is_loose_nested_true_without_sibling_index(self):
        path = self._write("research/sub/note.md")
        self.assertTrue(vaultlib.is_loose_nested(path, "child"))

    def test_is_loose_nested_false_with_sibling_index(self):
        self._write("specs/SPEC-002-tile/index.md")
        path = self._write("specs/SPEC-002-tile/SPEC-001-master.md")
        self.assertFalse(vaultlib.is_loose_nested(path, "child"))

    def test_is_loose_nested_false_for_non_child_kinds(self):
        path = self._write("research/flat.md")
        self.assertFalse(vaultlib.is_loose_nested(path, "flat"))
        self.assertFalse(vaultlib.is_loose_nested(path, "folder-index"))

    def test_loose_child_name_includes_the_type_dir(self):
        self._write("research/sub/note.md")
        records = vaultlib.scan_artifacts(self.tmp)
        self.assertEqual(records[0]["name"], "research/sub/note")
        self.assertEqual(records[0]["kind"], "child")

    def test_folder_spec_child_name_is_vault_relative(self):
        self._write("specs/SPEC-002-tile/index.md")
        self._write("specs/SPEC-002-tile/SPEC-001-master.md")
        by_name = {r["rel"]: r for r in vaultlib.scan_artifacts(self.tmp)}
        child = by_name["SPEC-002-tile/SPEC-001-master.md"]
        self.assertEqual(child["name"], "specs/SPEC-002-tile/SPEC-001-master")

    def test_two_loose_children_sharing_a_stem_get_distinct_names(self):
        self._write("research/sub-a/note.md")
        self._write("research/sub-b/note.md")
        names = {r["name"] for r in vaultlib.scan_artifacts(self.tmp)}
        self.assertEqual(names, {"research/sub-a/note", "research/sub-b/note"})

    def test_loose_child_inside_a_unit_is_unaffected(self):
        # A unit-owned child was already vault-relative (unit/type_dir/...)
        # before this fix; the loose-nested branch must not double the
        # type dir prefix for it.
        self._write("unitx/index.md", "---\ntitle: X\ntype: unit\nstatus: active\n---\n")
        self._write("unitx/research/sub/note.md")
        by_name = {r["name"]: r for r in vaultlib.scan_artifacts(self.tmp)}
        self.assertIn("unitx/research/sub/note", by_name)
        self.assertNotIn("unitx/research/research/sub/note", by_name)


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


UNIT_INDEX = """---
title: Compass CLI
type: unit
status: active
---

# Compass CLI

One body of work: the CLI and everything that shaped it.
"""


class UnitVaultFixture(unittest.TestCase):
    """A vault with root type dirs, a marked unit, an unmarked look-alike,
    a custom type dir, a stray markdown folder, and an empty junk dir."""

    def setUp(self):
        self.tmp = make_tempdir(self)
        self._write("specs/SPEC-001-root.md", "---\ntype: spec\n---\nx\n")
        self._write("compass-cli/index.md", UNIT_INDEX)
        self._write("compass-cli/specs/SPEC-001-cli-spec.md", "---\ntype: spec\n---\nx\n")
        self._write("compass-cli/specs/SPEC-002-sub/index.md", "---\ntype: spec\n---\nx\n")
        self._write("compass-cli/specs/SPEC-002-sub/SPEC-001-leaf.md", "---\ntype: spec\n---\nx\n")
        self._write("compass-cli/research/RESEARCH-cli-notes.md", "---\ntype: research\n---\nx\n")
        # typed files at depth 2 but no `type: unit` marker: not a unit
        self._write("bare-unit/specs/SPEC-001-hidden.md", "---\ntype: spec\n---\nx\n")
        # custom type dir: typed markdown at depth 1 (the content signal)
        self._write("retro/RETRO-1.md", "---\ntype: retro\n---\nx\n")
        # stray folder holding non-artifact markdown
        self._write("claude/CLAUDE.md", "# Project instructions\n")
        # junk with no markdown at all
        (self.tmp / "assets").mkdir()
        (self.tmp / "assets" / "logo.png").write_bytes(b"\x89PNG")
        (self.tmp / "meta").mkdir()

    def _write(self, rel, body):
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


class ClassifyRootDirsTests(UnitVaultFixture):
    def test_classification_matrix(self):
        layout = vaultlib.classify_root_dirs(self.tmp)
        self.assertEqual(layout["type_dirs"], ["retro", "specs"])
        self.assertEqual(layout["units"], ["compass-cli"])
        self.assertEqual(layout["unclassified"], ["bare-unit", "claude"])

    def test_no_markdown_dir_appears_nowhere(self):
        layout = vaultlib.classify_root_dirs(self.tmp)
        for names in layout.values():
            self.assertNotIn("assets", names)
            self.assertNotIn("meta", names)

    def test_discover_type_dirs_excludes_units_and_unclassified(self):
        self.assertEqual(vaultlib.discover_type_dirs(self.tmp), ["retro", "specs"])

    def test_reserved_name_stays_type_dir_even_with_unit_marked_index(self):
        self._write("plans/index.md", UNIT_INDEX)
        layout = vaultlib.classify_root_dirs(self.tmp)
        self.assertIn("plans", layout["type_dirs"])
        self.assertNotIn("plans", layout["units"])


class ScanArtifactsUnitTests(UnitVaultFixture):
    def test_unit_records_carry_unit_type_dir_and_vault_relative_name(self):
        by_name = {r["name"]: r for r in vaultlib.scan_artifacts(self.tmp)}

        flat = by_name["compass-cli/specs/SPEC-001-cli-spec"]
        self.assertEqual(flat["unit"], "compass-cli")
        self.assertEqual(flat["type_dir"], "specs")
        self.assertEqual(flat["kind"], "flat")
        self.assertEqual(flat["rel"], "SPEC-001-cli-spec.md")
        self.assertEqual(flat["depth"], 0)

        folder = by_name["compass-cli/specs/SPEC-002-sub"]
        self.assertEqual(folder["kind"], "folder-index")
        self.assertEqual(folder["unit"], "compass-cli")

        child = by_name["compass-cli/specs/SPEC-002-sub/SPEC-001-leaf"]
        self.assertEqual(child["kind"], "child")
        self.assertEqual(child["depth"], 1)

        research = by_name["compass-cli/research/RESEARCH-cli-notes"]
        self.assertEqual(research["type_dir"], "research")

    def test_unit_own_index_is_not_an_artifact_record(self):
        paths = {r["path"] for r in vaultlib.scan_artifacts(self.tmp)}
        self.assertNotIn(self.tmp / "compass-cli" / "index.md", paths)

    def test_unmarked_folder_is_not_scanned(self):
        names = {r["name"] for r in vaultlib.scan_artifacts(self.tmp)}
        self.assertFalse(any("SPEC-001-hidden" in n for n in names))

    def test_root_records_have_unit_none(self):
        by_name = {r["name"]: r for r in vaultlib.scan_artifacts(self.tmp)}
        self.assertIsNone(by_name["SPEC-001-root"]["unit"])
        self.assertIsNone(by_name["RETRO-1"]["unit"])


class FlatVaultRecordsUnchangedTests(unittest.TestCase):
    """Pre-unit record shape on a units-free vault: every field keeps its
    exact prior value, and `unit` is the only added key."""

    def setUp(self):
        self.tmp = make_tempdir(self)

    def _write(self, rel, body="---\ntype: spec\n---\n"):
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def test_records_match_pre_unit_output_field_for_field(self):
        self._write("specs/SPEC-001-flat.md")
        self._write("specs/SPEC-002-tile/index.md")
        self._write("specs/SPEC-002-tile/SPEC-001-master.md")
        records = vaultlib.scan_artifacts(self.tmp)
        expected = [
            {"path": self.tmp / "specs" / "SPEC-001-flat.md", "type_dir": "specs",
             "kind": "flat", "rel": "SPEC-001-flat.md", "name": "SPEC-001-flat",
             "depth": 0, "unit": None},
            {"path": self.tmp / "specs" / "SPEC-002-tile" / "SPEC-001-master.md",
             "type_dir": "specs", "kind": "child",
             "rel": "SPEC-002-tile/SPEC-001-master.md",
             "name": "specs/SPEC-002-tile/SPEC-001-master", "depth": 1, "unit": None},
            {"path": self.tmp / "specs" / "SPEC-002-tile" / "index.md",
             "type_dir": "specs", "kind": "folder-index",
             "rel": "SPEC-002-tile/index.md", "name": "specs/SPEC-002-tile",
             "depth": 0, "unit": None},
        ]
        # Path.rglob order differs across platforms (WindowsPath sorts
        # case-insensitively), so compare records keyed by name.
        self.assertEqual(
            sorted(records, key=lambda r: r["name"]),
            sorted(expected, key=lambda r: r["name"]),
        )


class ResolvableNamesMapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = make_tempdir(self)

    def _write(self, rel, body="---\ntype: spec\n---\n"):
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def test_colliding_stem_maps_to_both_paths(self):
        self._write("specs/SPEC-001-setup.md")
        self._write("compass-cli/index.md", UNIT_INDEX)
        self._write("compass-cli/specs/SPEC-001-setup.md")
        mapping = vaultlib.resolvable_names_map(self.tmp)
        self.assertEqual(
            mapping["SPEC-001-setup"],
            ["compass-cli/specs/SPEC-001-setup.md", "specs/SPEC-001-setup.md"],
        )

    def test_path_qualified_names_are_unambiguous(self):
        self._write("specs/SPEC-001-setup.md")
        self._write("compass-cli/index.md", UNIT_INDEX)
        self._write("compass-cli/specs/SPEC-001-setup.md")
        mapping = vaultlib.resolvable_names_map(self.tmp)
        self.assertEqual(mapping["specs/SPEC-001-setup"], ["specs/SPEC-001-setup.md"])
        self.assertEqual(
            mapping["compass-cli/specs/SPEC-001-setup"],
            ["compass-cli/specs/SPEC-001-setup.md"],
        )

    def test_index_md_resolves_by_folder_name(self):
        self._write("compass-cli/index.md", UNIT_INDEX)
        self._write("specs/SPEC-002-tile/index.md")
        mapping = vaultlib.resolvable_names_map(self.tmp)
        self.assertEqual(mapping["compass-cli"], ["compass-cli/index.md"])
        self.assertEqual(mapping["SPEC-002-tile"], ["specs/SPEC-002-tile/index.md"])

    def test_index_md_resolves_by_folder_path(self):
        self._write("specs/SPEC-002-tile/index.md")
        self._write("compass-cli/specs/SPEC-001-core/index.md")
        mapping = vaultlib.resolvable_names_map(self.tmp)
        self.assertEqual(mapping["specs/SPEC-002-tile"], ["specs/SPEC-002-tile/index.md"])
        self.assertEqual(
            mapping["compass-cli/specs/SPEC-001-core"],
            ["compass-cli/specs/SPEC-001-core/index.md"],
        )

    def test_generated_and_archived_coverage_matches_all_markdown_files(self):
        self._write("archive/SPEC-099-old.md")
        self._write("meta/notes.md", "generated\n")
        self._write("tmp/scratch.md", "scratch\n")
        mapping = vaultlib.resolvable_names_map(self.tmp)
        self.assertIn("SPEC-099-old", mapping)
        self.assertNotIn("notes", mapping)
        self.assertNotIn("scratch", mapping)


class WriteTextLfTests(unittest.TestCase):
    def test_no_carriage_return_in_output(self):
        target = make_tempdir(self) / "out.md"
        vaultlib.write_text_lf(target, "line1\r\nline2\rline3\n")
        raw = target.read_bytes()
        self.assertNotIn(b"\r", raw)
        self.assertEqual(raw, b"line1\nline2\nline3\n")


class StripFencedCodeTests(unittest.TestCase):
    def test_terminated_fence_blanked_prose_kept(self):
        text = "before\n```python\ncode [[LINK]]\n```\nafter"
        stripped, unterminated = vaultlib.strip_fenced_code(text)
        self.assertFalse(unterminated)
        self.assertEqual(stripped.split("\n"), ["before", "", "", "", "after"])

    def test_line_count_is_stable(self):
        text = "a\n```\nx\ny\n```\nb\n~~~\nz\n~~~\nc"
        stripped, _ = vaultlib.strip_fenced_code(text)
        self.assertEqual(len(stripped.split("\n")), len(text.split("\n")))
        self.assertEqual(stripped.split("\n")[5], "b")
        self.assertEqual(stripped.split("\n")[9], "c")

    def test_unterminated_fence_flags_and_blanks_remainder(self):
        text = "prose\n```\n- **D-01:** swallowed\nmore"
        stripped, unterminated = vaultlib.strip_fenced_code(text)
        self.assertTrue(unterminated)
        self.assertNotIn("swallowed", stripped)
        self.assertEqual(stripped.split("\n")[0], "prose")
        self.assertEqual(len(stripped.split("\n")), len(text.split("\n")))

    def test_no_fence_returns_text_unchanged(self):
        stripped, unterminated = vaultlib.strip_fenced_code("just\nprose\n")
        self.assertFalse(unterminated)
        self.assertEqual(stripped, "just\nprose\n")

    def test_backtick_fence_not_closed_by_tilde(self):
        text = "```\ncode\n~~~\nstill code\n```\nafter"
        stripped, unterminated = vaultlib.strip_fenced_code(text)
        self.assertFalse(unterminated)
        self.assertNotIn("still code", stripped)
        self.assertIn("after", stripped)

    def test_closing_fence_must_be_at_least_as_long(self):
        text = "````\ncode\n```\nstill code\n````\nafter"
        stripped, unterminated = vaultlib.strip_fenced_code(text)
        self.assertFalse(unterminated)
        self.assertNotIn("still code", stripped)
        self.assertIn("after", stripped)

    def test_indented_fence_delimiters_are_recognized(self):
        text = "before\n  ```\n  code\n  ```\nafter"
        stripped, unterminated = vaultlib.strip_fenced_code(text)
        self.assertFalse(unterminated)
        self.assertNotIn("code", stripped)


class StripInlineCodeTests(unittest.TestCase):
    def test_spans_removed_prose_kept(self):
        self.assertEqual(
            vaultlib.strip_inline_code("keep `drop this` keep"), "keep  keep"
        )

    def test_span_does_not_cross_lines(self):
        text = "open `span\nnot closed` here"
        self.assertEqual(vaultlib.strip_inline_code(text), text)

    def test_multiple_spans_on_one_line(self):
        self.assertEqual(vaultlib.strip_inline_code("`a` and `b`"), " and ")


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
