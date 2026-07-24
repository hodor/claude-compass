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
from commands import next_num, tree, hot_path, unit_check, validate  # noqa: E402


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

    def test_unit_scope_numbers_locally(self):
        root = make_vault(self)
        write(root, "specs/SPEC-005-root.md")
        write(root, "compass-cli/index.md", "---\ntitle: U\ntype: unit\n---\n")
        write(root, "compass-cli/specs/SPEC-001-a.md")
        write(root, "compass-cli/specs/SPEC-002-b.md")
        with_vault_env(self, root)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(next_num.run(["spec", "compass-cli"]), 0)
            self.assertEqual(next_num.run(["spec"]), 0)
        self.assertEqual(out.getvalue().split(), ["003", "006"])

    def test_traversal_scope_rejected(self):
        root = make_vault(self)
        (root / "specs").mkdir()
        with_vault_env(self, root)
        self.assertEqual(next_num.run(["spec", "../elsewhere"]), 1)
        self.assertEqual(next_num.run(["spec", "a/../../elsewhere"]), 1)


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

    def test_unit_branch_rendering(self):
        root = make_vault(self)
        write(root, "specs/SPEC-001-flat.md")
        write(root, "compass-cli/index.md", "---\ntitle: U\ntype: unit\n---\n")
        write(root, "compass-cli/specs/SPEC-001-cli.md")
        write(root, "compass-cli/specs/SPEC-002-sub/index.md")
        write(root, "compass-cli/specs/SPEC-002-sub/SPEC-001-child.md")
        write(root, "compass-cli/plans/PLAN-001-impl.md", "---\ntype: plan\n---\n")
        rendered = tree.render(root)
        self.assertEqual(
            rendered,
            "specs\n"
            "  SPEC-001-flat\n"
            "compass-cli\n"
            "  plans\n"
            "    PLAN-001-impl\n"
            "  specs\n"
            "    SPEC-001-cli\n"
            "    SPEC-002-sub/\n"
            "      SPEC-001-child",
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

    def test_stale_index_entry_is_warning(self):
        root = self._clean_vault()
        (root / "index.md").write_text(
            "# Index\n\n- [[SPEC-001-target]]\n- [[SPEC-999-deleted]]\n", encoding="utf-8"
        )
        errors, warnings = validate.check_vault(root)
        self.assertTrue(any("index.md" in w and "SPEC-999-deleted" in w for w in warnings))
        self.assertFalse(any("SPEC-001-target" in f for f in errors + warnings))

    def test_line_cap_is_warning(self):
        root = self._clean_vault()
        (root / "index.md").write_text("\n".join(f"line {i}" for i in range(260)), encoding="utf-8")
        errors, warnings = validate.check_vault(root)
        self.assertTrue(any("cap_exceeded" in w and "lines" in w for w in warnings))


class ValidateUnitLinkTests(unittest.TestCase):
    UNIT_INDEX = "---\ntitle: U\ntype: unit\n---\n"

    def _vault_with_stem_collision(self):
        root = make_vault(self)
        (root / "index.md").write_text("# Index\n", encoding="utf-8")
        write(root, "specs/SPEC-001-target.md", ValidateTests.SPEC_OK)
        for unit in ("unita", "unitb"):
            write(root, f"{unit}/index.md", self.UNIT_INDEX)
            write(root, f"{unit}/specs/SPEC-001-shared.md", ValidateTests.SPEC_OK)
        return root

    def test_cross_unit_stem_collision_is_ambiguous_warning(self):
        root = self._vault_with_stem_collision()
        write(root, "specs/SPEC-002-ref.md",
              ValidateTests.SPEC_OK.replace("[[SPEC-001-target]]", "[[SPEC-001-shared]]"))
        errors, warnings = validate.check_vault(root)
        ambiguous = [w for w in warnings if w.startswith("ambiguous_wikilink")]
        self.assertEqual(len(ambiguous), 1)
        self.assertIn("[[SPEC-001-shared]]", ambiguous[0])
        self.assertIn("unita/specs/SPEC-001-shared.md", ambiguous[0])
        self.assertIn("unitb/specs/SPEC-001-shared.md", ambiguous[0])
        self.assertFalse(any("SPEC-001-shared" in e for e in errors))
        self.assertFalse(any("broken_wikilink" in w and "SPEC-001-shared" in w for w in warnings))

    def test_path_qualified_link_to_collided_stem_is_clean(self):
        root = self._vault_with_stem_collision()
        write(root, "specs/SPEC-002-ref.md",
              ValidateTests.SPEC_OK.replace(
                  "[[SPEC-001-target]]", "[[unita/specs/SPEC-001-shared]]"))
        errors, warnings = validate.check_vault(root)
        self.assertFalse(any("SPEC-001-shared" in f for f in errors + warnings))

    def test_unmarked_root_folder_is_reported_not_scanned(self):
        root = make_vault(self)
        (root / "index.md").write_text("# Index\n", encoding="utf-8")
        write(root, "specs/SPEC-001-target.md", ValidateTests.SPEC_OK)
        write(root, "bare-unit/specs/SPEC-001-x.md", "---\ntype: spec\n---\n[[NoSuchThing]]\n")
        errors, warnings = validate.check_vault(root)
        self.assertTrue(
            any(w.startswith("unclassified_root_folder: bare-unit") for w in warnings)
        )
        # The folder is skipped, never guessed at: its files produce no
        # frontmatter or wikilink findings.
        self.assertFalse(any("bare-unit/" in e for e in errors))
        self.assertFalse(any("NoSuchThing" in f for f in errors + warnings))


class UnitCheckTests(unittest.TestCase):
    SPEC = "---\ntitle: Core\ntype: spec\nstatus: approved\n---\n\nbody\n"

    @staticmethod
    def doc(type_, deps):
        dep_items = ", ".join(f'"[[{d}]]"' for d in deps)
        return (
            f"---\ntitle: T\ntype: {type_}\nstatus: active\n"
            f"depends_on: [{dep_items}]\n---\n\nbody\n"
        )

    def test_chained_type_spread_reported(self):
        root = make_vault(self)
        write(root, "specs/SPEC-001-core.md", self.SPEC)
        write(root, "plans/PLAN-001-impl.md", self.doc("plan", ["SPEC-001-core"]))
        write(root, "decisions/ADR-001-choice.md", self.doc("decision", ["SPEC-001-core"]))
        write(root, "research/RESEARCH-notes.md", self.doc("research", ["PLAN-001-impl"]))
        candidates = unit_check.find_candidates(root)
        self.assertEqual(len(candidates), 1)
        spec_rel, members, types = candidates[0]
        self.assertEqual(spec_rel, "specs/SPEC-001-core.md")
        self.assertEqual(members, [
            "decisions/ADR-001-choice.md",
            "plans/PLAN-001-impl.md",
            "research/RESEARCH-notes.md",
            "specs/SPEC-001-core.md",
        ])
        self.assertEqual(types, ["decision", "plan", "research", "spec"])

    def test_type_spread_two_not_reported(self):
        root = make_vault(self)
        write(root, "specs/SPEC-001-core.md", self.SPEC)
        for n in range(1, 6):
            write(root, f"research/RESEARCH-topic-{n}.md",
                  self.doc("research", ["SPEC-001-core"]))
        self.assertEqual(unit_check.find_candidates(root), [])

    def test_run_prints_candidate_and_exits_zero(self):
        root = make_vault(self)
        write(root, "specs/SPEC-001-core.md", self.SPEC)
        write(root, "plans/PLAN-001-impl.md", self.doc("plan", ["SPEC-001-core"]))
        write(root, "decisions/ADR-001-choice.md", self.doc("decision", ["SPEC-001-core"]))
        with_vault_env(self, root)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(unit_check.run([]), 0)
        text = out.getvalue()
        self.assertIn("candidate: core (type-spread 3: decision, plan, spec)", text)
        self.assertIn("- plans/PLAN-001-impl.md", text)
        self.assertIn(
            "compass make-unit core decisions/ADR-001-choice.md "
            "plans/PLAN-001-impl.md specs/SPEC-001-core.md",
            text,
        )

    def test_run_without_candidates_exits_zero(self):
        root = make_vault(self)
        write(root, "specs/SPEC-001-core.md", self.SPEC)
        with_vault_env(self, root)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(unit_check.run([]), 0)
        self.assertIn("no candidates", out.getvalue())


if __name__ == "__main__":
    unittest.main()
