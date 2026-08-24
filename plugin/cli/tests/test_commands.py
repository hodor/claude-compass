"""Tests for the read-only CLI commands, validate, make-unit, the model
resolution commands, and the decision commands (decisions, coverage)."""

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modelslib  # noqa: E402
import vaultlib  # noqa: E402
from commands import (  # noqa: E402
    coverage, decisions, make_unit, models, next_num, resolve_model, tree,
    hot_path, sizing, unit_check, validate,
)


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
        "tags: [a]\ncreated: 2026-06-14\nupdated: 2026-06-14\n"
        'summary: "a target spec"\n---\n\n'
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


class ModelCommandBase(unittest.TestCase):
    """Shared fixture: an isolated vault and a COMPASS_*-free environment."""

    def setUp(self):
        self.root = make_vault(self)
        (self.root / "meta").mkdir()
        with_vault_env(self, self.root)
        saved = {
            key: os.environ.pop(key)
            for key in list(os.environ)
            if key.startswith("COMPASS_MODEL_") or key.startswith("COMPASS_EFFORT_")
        }
        self.addCleanup(os.environ.update, saved)

    def run_command(self, module, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = module.run(args)
        return code, out.getvalue(), err.getvalue()


class ResolveModelTests(ModelCommandBase):
    def test_stdout_is_exactly_the_resolved_pair(self):
        code, out, err = self.run_command(resolve_model, ["planner"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "opus high\n")
        self.assertEqual(err, "")

    def test_cheap_agent_resolves_haiku_low(self):
        code, out, _ = self.run_command(resolve_model, ["vault-locator"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "haiku low\n")

    def test_unknown_agent_inherit_exit_zero(self):
        code, out, _ = self.run_command(resolve_model, ["no-such-agent"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "inherit high\n")

    def test_warnings_go_to_stderr_result_stays_clean(self):
        (self.root / "meta" / "models.yaml").write_text(
            ":::garbage:::\n", encoding="utf-8"
        )
        code, out, err = self.run_command(resolve_model, ["planner"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "opus high\n")
        self.assertIn("models.yaml", err)

    def test_usage_error_exits_one_never_two(self):
        code, _, err = self.run_command(resolve_model, [])
        self.assertEqual(code, 1)
        self.assertIn("usage", err)


class ModelsTests(ModelCommandBase):
    def test_table_lists_all_roster_rows(self):
        code, out, _ = self.run_command(models, [])
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        # Header plus the 13 agents plus the two detached job rows (index-summary, capture-worker).
        self.assertEqual(len(lines), 16)
        self.assertIn("source", lines[0])
        for agent in modelslib.DEFAULT_ROSTER:
            self.assertTrue(any(line.startswith(agent) for line in lines[1:]), agent)
        planner_row = next(line for line in lines if line.startswith("planner"))
        self.assertIn("opus", planner_row)
        self.assertIn("built-in", planner_row)
        locator_row = next(line for line in lines if line.startswith("vault-locator"))
        self.assertIn("haiku", locator_row)
        self.assertIn("low", locator_row)

    def test_project_override_shows_project_source(self):
        (self.root / "meta" / "models.yaml").write_text(
            "agents:\n  vault-locator: sonnet\n", encoding="utf-8"
        )
        code, out, _ = self.run_command(models, [])
        self.assertEqual(code, 0)
        locator_row = next(
            line for line in out.splitlines() if line.startswith("vault-locator")
        )
        self.assertIn("sonnet", locator_row)
        self.assertIn("project", locator_row)

    def test_env_override_shows_env_source(self):
        os.environ["COMPASS_MODEL_BUILDER"] = "opus"
        self.addCleanup(os.environ.pop, "COMPASS_MODEL_BUILDER", None)
        code, out, _ = self.run_command(models, [])
        self.assertEqual(code, 0)
        builder_row = next(
            line for line in out.splitlines() if line.startswith("builder")
        )
        self.assertIn("opus", builder_row)
        self.assertIn("env", builder_row)


class MakeUnitTests(unittest.TestCase):
    SPEC = (
        "---\ntitle: Core spec\ntype: spec\nstatus: approved\narea: x\n"
        "tags: [a]\ncreated: 2026-07-24\nupdated: 2026-07-24\n---\n\nbody\n"
    )
    PLAN = (
        "---\ntitle: Impl plan\ntype: plan\nstatus: active\narea: x\n"
        "tags: [a]\ncreated: 2026-07-24\nupdated: 2026-07-24\n"
        'depends_on: ["[[SPEC-001-core]]"]\n---\n\nbody\n'
    )
    ADR = (
        "---\ntitle: Choice\ntype: decision\nstatus: approved\nconfidence: high\n"
        "area: x\ntags: [a]\ncreated: 2026-07-24\nupdated: 2026-07-24\n---\n\nbody\n"
    )
    ARGS = [
        "core",
        "specs/SPEC-001-core.md",
        "plans/PLAN-001-impl.md",
        "decisions/ADR-001-choice.md",
    ]

    def _vault(self):
        root = make_vault(self)
        (root / "meta").mkdir()
        (root / "meta" / "lessons-catalog.yaml").write_text("lessons:\n", encoding="utf-8")
        write(root, "specs/SPEC-001-core.md", self.SPEC)
        write(root, "plans/PLAN-001-impl.md", self.PLAN)
        write(root, "decisions/ADR-001-choice.md", self.ADR)
        (root / "index.md").write_text(
            "# Index\n\n"
            "## Specs\n\n- [[SPEC-001-core]] - Core spec\n\n"
            "## Plans\n\n- [[PLAN-001-impl]] - Impl plan\n\n"
            "## Decisions\n\n- [[ADR-001-choice]] - Choice\n",
            encoding="utf-8",
        )
        with_vault_env(self, root)
        return root

    def test_dry_run_makes_no_changes(self):
        root = self._vault()
        index_before = (root / "index.md").read_text(encoding="utf-8")
        files_before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(make_unit.run(self.ARGS), 0)
        self.assertIn("dry-run", out.getvalue())
        self.assertIn("specs/SPEC-001-core.md -> core/specs/SPEC-001-core.md", out.getvalue())
        self.assertFalse((root / "core").exists())
        self.assertEqual(index_before, (root / "index.md").read_text(encoding="utf-8"))
        files_after = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
        self.assertEqual(files_before, files_after)

    def test_apply_moves_creates_unit_and_rewrites_index(self):
        root = self._vault()
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(make_unit.run(self.ARGS + ["--reason", "grouping the tile work", "--apply"]), 0)
        # Files moved into the unit's type dirs, frontmatter byte-identical.
        moved = root / "core" / "specs" / "SPEC-001-core.md"
        self.assertTrue(moved.is_file())
        self.assertEqual(moved.read_text(encoding="utf-8"), self.SPEC)
        self.assertFalse((root / "specs" / "SPEC-001-core.md").exists())
        self.assertTrue((root / "core" / "plans" / "PLAN-001-impl.md").is_file())
        self.assertTrue((root / "core" / "decisions" / "ADR-001-choice.md").is_file())
        # The unit marker index exists with the type: unit frontmatter and a
        # one-line-per-member children listing.
        data, error = vaultlib.parse_frontmatter(root / "core" / "index.md")
        self.assertIsNone(error)
        self.assertEqual(data["type"], "unit")
        unit_index = (root / "core" / "index.md").read_text(encoding="utf-8")
        self.assertIn("- [[core/specs/SPEC-001-core]] - Core spec", unit_index)
        self.assertIn("- [[core/plans/PLAN-001-impl]] - Impl plan", unit_index)
        self.assertIn("- [[core/decisions/ADR-001-choice]] - Choice", unit_index)
        # Root index: old bare-stem entries removed, sync appended the unit
        # section with path-qualified links.
        index_text = (root / "index.md").read_text(encoding="utf-8")
        self.assertNotIn("- [[SPEC-001-core]]", index_text)
        self.assertNotIn("- [[PLAN-001-impl]]", index_text)
        self.assertNotIn("- [[ADR-001-choice]]", index_text)
        self.assertIn("## core", index_text)
        self.assertIn("[[core/specs/SPEC-001-core]]", index_text)
        self.assertIn("index.md: removed 3 entry line(s)", out.getvalue())
        self.assertIn("validate:", out.getvalue())
        # The migrated vault validates with no errors and no link findings.
        errors, warnings = validate.check_vault(root)
        self.assertEqual(errors, [])
        self.assertFalse(any("wikilink" in w for w in warnings))

    def test_apply_git_history_preserved(self):
        if shutil.which("git") is None:
            self.skipTest("git unavailable")
        root = self._vault()
        repo = str(root.parent)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t",
             "-c", "commit.gpgsign=false", "commit", "-qm", "seed"],
            cwd=repo, check=True, capture_output=True,
        )
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(make_unit.run(self.ARGS + ["--reason", "grouping the tile work", "--apply"]), 0)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t",
             "-c", "commit.gpgsign=false", "commit", "-qm", "migrate"],
            cwd=repo, check=True, capture_output=True,
        )
        log = subprocess.run(
            ["git", "log", "--follow", "--oneline", "--",
             ".compass/core/specs/SPEC-001-core.md"],
            cwd=repo, capture_output=True, text=True,
        )
        self.assertEqual(log.returncode, 0)
        # Two commits reachable through the rename: the migration and the
        # pre-move seed, proving `git mv` preserved history.
        self.assertEqual(len(log.stdout.strip().splitlines()), 2)

    def test_refuses_existing_target(self):
        root = self._vault()
        (root / "core").mkdir()
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(make_unit.run(self.ARGS + ["--reason", "grouping the tile work", "--apply"]), 1)
        self.assertIn("target exists: core", err.getvalue())
        self.assertTrue((root / "specs" / "SPEC-001-core.md").is_file())

    def test_refuses_reserved_name(self):
        root = self._vault()
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(make_unit.run(["prs", "specs/SPEC-001-core.md", "--reason", "grouping the tile work", "--apply"]), 1)
        self.assertIn("reserved name: prs", err.getvalue())
        self.assertFalse((root / "prs").exists())

    def test_refuses_ambiguous_artifact_name(self):
        root = self._vault()
        write(root, "research/SPEC-001-core.md", self.SPEC)
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(make_unit.run(["core", "SPEC-001-core", "--reason", "grouping the tile work", "--apply"]), 1)
        text = err.getvalue()
        self.assertIn("ambiguous: SPEC-001-core", text)
        self.assertIn("specs/SPEC-001-core.md", text)
        self.assertIn("research/SPEC-001-core.md", text)
        self.assertFalse((root / "core").exists())

    def test_refuses_missing_artifact(self):
        root = self._vault()
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(
                make_unit.run(["core", "specs/SPEC-999-none.md", "--reason", "grouping the tile work", "--apply"]), 1
            )
        self.assertIn("not found: specs/SPEC-999-none.md", err.getvalue())
        self.assertFalse((root / "core").exists())

    def test_refuses_artifact_already_inside_unit(self):
        root = self._vault()
        write(root, "other/index.md", "---\ntitle: O\ntype: unit\n---\n")
        write(root, "other/specs/SPEC-001-x.md", self.SPEC)
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(
                make_unit.run(["core", "other/specs/SPEC-001-x.md", "--reason", "grouping the tile work", "--apply"]), 1
            )
        self.assertIn("not in a root type directory", err.getvalue())
        self.assertFalse((root / "core").exists())

    def test_zero_artifacts_apply_creates_only_index_marker(self):
        """Adversarial where: with zero artifacts the move loop -- which
        carries the module's only `mkdir` -- never runs, so a naive
        implementation would let `write_text_lf` hit a missing parent
        directory and raise `FileNotFoundError` instead of creating
        `vault_root / name` itself; and git does not track empty
        directories, so pre-creating empty `specs/`, `plans/`, etc. type
        subdirectories for a unit with nothing to put in them would vanish
        on the next clone."""
        root = self._vault()
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(make_unit.run(["core", "--reason", "grouping the tile work", "--apply"]), 0)
        core_dir = root / "core"
        self.assertTrue(core_dir.is_dir())
        data, error = vaultlib.parse_frontmatter(core_dir / "index.md")
        self.assertIsNone(error)
        self.assertEqual(data["type"], "unit")
        self.assertEqual(sorted(p.name for p in core_dir.iterdir()), ["index.md"])

    def test_zero_artifacts_apply_does_not_add_root_index_section(self):
        """Adversarial where: `_sync_index` derives unit sections from
        scanned artifact records; a unit that contributes none must not
        gain a "## core" section merely because the folder now exists on
        disk. The task accepts this gap rather than teaching sync to
        special-case an empty unit; this pins that the root index is left
        byte-identical instead of an accidental partial section leaking
        in."""
        root = self._vault()
        index_before = (root / "index.md").read_text(encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(make_unit.run(["core", "--reason", "grouping the tile work", "--apply"]), 0)
        self.assertEqual(index_before, (root / "index.md").read_text(encoding="utf-8"))

    def test_zero_artifacts_dry_run_creates_nothing(self):
        """Adversarial where: `run(["core"])` used to be a usage error
        requiring at least one artifact; it must now succeed as a dry run
        that creates nothing, not silently fall through to acting as if
        --apply were given. The message must also describe what the apply
        would create rather than reusing the multi-artifact template's "N
        artifact(s)" wording unchanged at N=0, which would literally print
        a zero count instead of naming the marker it would create."""
        root = self._vault()
        index_before = (root / "index.md").read_text(encoding="utf-8")
        files_before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(make_unit.run(["core"]), 0)
        text = out.getvalue()
        self.assertIn("dry-run", text)
        self.assertIn("core/index.md", text)
        lowered = text.lower()
        self.assertNotIn("0 artifact", lowered)
        self.assertNotIn("0 index-line", lowered)
        self.assertFalse((root / "core").exists())
        self.assertEqual(index_before, (root / "index.md").read_text(encoding="utf-8"))
        files_after = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
        self.assertEqual(files_before, files_after)

    def test_refuses_reserved_name_with_zero_artifacts(self):
        """Adversarial where: the reserved-name refusal must still fire
        when the positional-count relaxation permits an empty artifact
        list -- a relaxation that only re-checks `_check_target` inside
        the move-loop branch would let a reserved name slip through
        untouched when there's nothing to move."""
        root = self._vault()
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(make_unit.run(["prs", "--reason", "grouping the tile work", "--apply"]), 1)
        self.assertIn("reserved name: prs", err.getvalue())
        self.assertFalse((root / "prs").exists())

    def test_refuses_existing_target_with_zero_artifacts(self):
        """Adversarial where: with zero artifacts the move-loop's mkdir is
        skipped, but the existing-target guard must still run before the
        new "apply path creates the directory itself" fix -- otherwise
        that fix could write a marker straight into a directory that
        already exists for unrelated reasons."""
        root = self._vault()
        (root / "core").mkdir()
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(make_unit.run(["core", "--reason", "grouping the tile work", "--apply"]), 1)
        self.assertIn("target exists: core", err.getvalue())
        self.assertFalse((root / "core" / "index.md").exists())

    def test_refuses_name_colliding_with_existing_artifact_stem(self):
        """Adversarial where: `_check_target` today checks only reserved,
        malformed and existing-path names; a bare word that happens to
        equal an existing root artifact's stem was previously accepted,
        and after creation `resolvable_names_map` would map that name to
        two paths, turning every existing `[[name]]` wikilink into an
        `ambiguous_wikilink` warning. This pins that the refusal exists
        before that ambiguity can ever occur. The call carries a real
        artifact so today's two-positional usage check is satisfied and
        cannot be the thing masking a missing collision check."""
        root = self._vault()
        write(root, "research/helper.md")
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(
                make_unit.run(["helper", "specs/SPEC-001-core.md", "--reason", "grouping the tile work", "--apply"]), 1
            )
        self.assertFalse((root / "helper").exists())
        self.assertTrue((root / "research" / "helper.md").is_file())
        self.assertTrue((root / "specs" / "SPEC-001-core.md").is_file())

    def test_refuses_malformed_name_with_zero_artifacts(self):
        """Adversarial where: `_check_target`'s first branch refuses a
        name containing "/", containing "\\", or starting with "." before
        it ever reaches the reserved-name or existing-target checks --
        with zero artifacts, that branch must still fire for each of the
        three classes and still create nothing."""
        root = self._vault()
        cases = {
            "forward_slash": "bad/name",
            "backslash": "bad\\name",
            "leading_dot": ".hidden",
        }
        for label, name in cases.items():
            with self.subTest(name=label):
                err = io.StringIO()
                with redirect_stderr(err):
                    self.assertEqual(make_unit.run([name, "--reason", "grouping the tile work", "--apply"]), 1)
                self.assertIn("invalid unit name:", err.getvalue())
                self.assertFalse((root / name).exists())

    def test_malformed_and_reserved_name_reports_malformed_first(self):
        """Adversarial where: a name that unmistakably targets the
        reserved word "prs" but is also malformed (trailing "/") must
        report `invalid unit name`, not `reserved name` -- the malformed
        branch returns first in `_check_target`. A later refactor that
        reorders the checks (e.g. to run the cheap set-membership test
        before the string scan) would flip which reason gets reported
        without changing the exit code, so only the message content pins
        the ordering."""
        root = self._vault()
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(make_unit.run(["prs/", "--reason", "grouping the tile work", "--apply"]), 1)
        self.assertIn("invalid unit name:", err.getvalue())
        self.assertNotIn("reserved name", err.getvalue())
        self.assertFalse((root / "prs").exists())

    def test_usage_error_with_no_args_exits_one(self):
        """Adversarial where: relaxing `run()` to accept a bare name with
        zero artifacts must not also relax the true usage error -- calling
        with no arguments at all still needs the name positional and must
        exit 1 with a usage message, not be swallowed by the new
        zero-artifact success path."""
        root = self._vault()
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(make_unit.run([]), 1)
        self.assertIn("usage", err.getvalue())
        self.assertFalse((root / "core").exists())

    def test_zero_artifacts_apply_reports_preexisting_vault_problems(self):
        """Adversarial where: the multi-artifact path always runs an
        in-process validate after `--apply` and prints its findings, so a
        human sees the vault's health at the moment they mutate its shape
        (pinned by `test_apply_moves_creates_unit_and_rewrites_index`,
        which asserts "validate:" on stdout). The zero-artifact path skips
        that tail on the stated grounds that an empty unit "has nothing to
        fold into" sync's output -- but that reasoning only bears on
        whether sync would add a root-index *section* for this unit, not
        on whether an unrelated, pre-existing vault problem should still
        be surfaced. This pins that a warning that exists before the empty
        unit is created, and is unrelated to it, is silently dropped: the
        human creating new structure gets no signal the vault is not
        clean, at exactly the moment the plan's own task text worried
        about."""
        root = self._vault()
        write(root, "weird_folder/stray.md", "# stray\n")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(make_unit.run(["core", "--reason", "grouping the tile work", "--apply"]), 0)
        self.assertIn("validate:", out.getvalue())
        self.assertIn("unclassified_root_folder: weird_folder", out.getvalue())

    def test_reserved_name_precedes_stem_collision(self):
        """Adversarial where: the resolve-collision branch added by this
        task is checked last in `_check_target`, after reserved and
        malformed -- an ordering only decided once the `resolve` parameter
        existed, and never pinned before this task. A name that is both a
        reserved directory word and a stem an existing artifact resolves
        to must report the reserved-name reason, not the collision reason,
        because the reserved branch returns first."""
        root = self._vault()
        write(root, "research/meta.md", "---\ntype: spec\n---\n")
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(make_unit.run(["meta", "--reason", "grouping the tile work", "--apply"]), 1)
        self.assertIn("reserved name: meta", err.getvalue())
        self.assertNotIn("already resolves", err.getvalue())
        self.assertFalse((root / "meta" / "index.md").exists())

    def test_malformed_name_precedes_stem_collision(self):
        """Adversarial where: same ordering question as the reserved case,
        but for the malformed branch, which returns first of all four
        checks in `_check_target`. A name that is both malformed (trailing
        slash) and would otherwise collide with an existing artifact's
        stem must report the malformed reason, not the collision reason."""
        root = self._vault()
        write(root, "research/helper.md", "---\ntype: spec\n---\n")
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(make_unit.run(["helper/", "--reason", "grouping the tile work", "--apply"]), 1)
        self.assertIn("invalid unit name: helper/", err.getvalue())
        self.assertNotIn("already resolves", err.getvalue())
        self.assertFalse((root / "helper").exists())


class EmptyUnitAcceptanceTests(unittest.TestCase):
    """The rest of the vault must already tolerate a unit whose only
    content is its `type: unit` marker index -- the shape `make-unit`
    produces for a zero-artifact `--apply` -- since neither
    `classify_root_dirs` nor `validate` change as part of this task."""

    UNIT_INDEX = "---\ntitle: Core\ntype: unit\nstatus: active\n---\n\n# Core\n"

    def test_empty_unit_classified_as_unit_never_unclassified(self):
        """Adversarial where: `classify_root_dirs`'s unit detection could
        plausibly key off a populated type subdirectory, since every
        existing fixture unit has one; a unit folder holding nothing but
        an `index.md` must still land in `units` on the strength of the
        `type: unit` marker alone, not fall into `unclassified` for
        lacking children."""
        root = make_vault(self)
        write(root, "core/index.md", self.UNIT_INDEX)
        layout = vaultlib.classify_root_dirs(root)
        self.assertIn("core", layout["units"])
        self.assertNotIn("core", layout["unclassified"])
        self.assertNotIn("core", layout["type_dirs"])

    def test_validate_accepts_empty_unit_without_ambiguous_wikilink(self):
        """Adversarial where: `validate`'s stem-resolution map is built
        from scanned artifact records; a unit that contributes none could
        either be mishandled as a missing/broken artifact, or -- if the
        marker index itself gets folded into the resolvable-names map --
        spuriously flagged ambiguous. An empty unit must validate clean: 0
        errors, and no new `ambiguous_wikilink` or `unclassified_root_folder`
        finding for it."""
        root = make_vault(self)
        (root / "index.md").write_text("# Index\n", encoding="utf-8")
        write(
            root, "specs/SPEC-001-target.md",
            "---\ntitle: T\ntype: spec\nstatus: approved\narea: x\n"
            "tags: [a]\ncreated: 2026-06-14\nupdated: 2026-06-14\n---\n\nbody\n",
        )
        write(root, "core/index.md", self.UNIT_INDEX)
        errors, warnings = validate.check_vault(root)
        self.assertEqual(errors, [])
        self.assertFalse(any(w.startswith("ambiguous_wikilink") for w in warnings))
        self.assertFalse(
            any(w.startswith("unclassified_root_folder: core") for w in warnings)
        )


class SizingReconciliationTests(unittest.TestCase):
    """TASK-081: `validate` reconciles unit folders and folder specs on disk
    against `.compass/meta/sizing-log.yaml` (ADR-011 D-08). A shape with no
    `sizing_id` in frontmatter, or one whose id resolves to no row in the
    log, is reported as a warning - never an error, since the vault predates
    the log and every pre-existing shape starts out unrecorded."""

    FOLDER_SPEC_TEMPLATE = (
        "---\ntitle: T\ntype: spec\nstatus: approved\narea: x\n"
        "tags: [a]\ncreated: 2026-06-14\nupdated: 2026-06-14\n"
        "children_count: 0\n"
        "{sizing_line}"
        'summary: "a folder spec"\n---\n\nbody\n'
    )
    UNIT_TEMPLATE = (
        "---\ntitle: U\ntype: unit\nstatus: active\n"
        "{sizing_line}"
        "---\n\n# U\n"
    )

    def _vault(self):
        root = make_vault(self)
        (root / "index.md").write_text("# Index\n", encoding="utf-8")
        with_vault_env(self, root)
        return root

    def _row(self, id_, shape, subject, at="2026-08-01"):
        return {
            "id": id_, "action": "decision", "shape": shape, "subject": subject,
            "reason": "test fixture decision", "volatile": [], "by": "agent", "at": at,
        }

    def test_unit_folder_missing_sizing_id_produces_warning(self):
        """Adversarial where: an implementation might key its 'was this
        recorded' check off something other than the literal `sizing_id`
        frontmatter field - e.g. off whether the log file exists at all, or
        off a `subject:` text match against the unit's own name. A unit
        index carrying no `sizing_id` key whatsoever must still be caught."""
        root = self._vault()
        write(root, "sizingcore/index.md", self.UNIT_TEMPLATE.format(sizing_line=""))
        errors, warnings = validate.check_vault(root)
        self.assertEqual(errors, [])
        self.assertTrue(any("sizingcore" in w for w in warnings))

    def test_unit_folder_with_resolving_id_produces_no_warning(self):
        """Adversarial where: an implementation might treat 'the log is
        non-empty' as sufficient proof of a recorded decision instead of
        confirming this specific artifact's own id resolves to a row - the
        log here carries exactly one row, minted through the real
        `sizing.append_row` writer, and the unit's frontmatter carries that
        exact id."""
        root = self._vault()
        sizing.append_row(root, self._row("sz-2026-08-01-3", "unit", "sizingcore"))
        write(root, "sizingcore/index.md",
              self.UNIT_TEMPLATE.format(sizing_line="sizing_id: sz-2026-08-01-3\n"))
        errors, warnings = validate.check_vault(root)
        self.assertEqual(errors, [])
        self.assertFalse(any("sizingcore" in w for w in warnings))

    def test_folder_spec_missing_sizing_id_produces_warning(self):
        """Adversarial where: same defect class as the unit-folder case
        above, but folder specs are discovered through a structurally
        different traversal (`vaultlib.scan_artifacts`'s `folder-index`
        records, not `classify_root_dirs()['units']`); an implementation
        that wires up only the unit-folder path would pass the sibling test
        while silently never checking a single folder spec."""
        root = self._vault()
        write(root, "specs/SPEC-777-sizeme/index.md",
              self.FOLDER_SPEC_TEMPLATE.format(sizing_line=""))
        errors, warnings = validate.check_vault(root)
        self.assertEqual(errors, [])
        self.assertTrue(any("SPEC-777-sizeme" in w for w in warnings))

    def test_folder_spec_with_resolving_id_produces_no_warning(self):
        """Adversarial where: the folder-spec resolving case, mirroring the
        unit-folder resolving test above across the same structurally
        different traversal - a folder spec whose stamped id matches a real
        log row must not be flagged."""
        root = self._vault()
        sizing.append_row(root, self._row(
            "sz-2026-08-02-5", "folder", "specs/SPEC-777-sizeme/index.md", at="2026-08-02"
        ))
        write(root, "specs/SPEC-777-sizeme/index.md",
              self.FOLDER_SPEC_TEMPLATE.format(sizing_line="sizing_id: sz-2026-08-02-5\n"))
        errors, warnings = validate.check_vault(root)
        self.assertEqual(errors, [])
        self.assertFalse(any("SPEC-777-sizeme" in w for w in warnings))

    def test_id_present_but_absent_from_log_produces_distinct_warning_naming_id(self):
        """Adversarial where: an id stamped in frontmatter that names no row
        in the log must produce its own warning, naming the id, distinct
        from the no-id-at-all case - and it must do so beside a second,
        healthy shape in the same vault without either verdict bleeding
        into the other (asymmetric fixture: one shape resolves cleanly, the
        sibling carries an orphaned id; neither may contaminate the other's
        result)."""
        root = self._vault()
        sizing.append_row(root, self._row("sz-2026-08-01-3", "unit", "sizingcore"))
        write(root, "sizingcore/index.md",
              self.UNIT_TEMPLATE.format(sizing_line="sizing_id: sz-2026-08-01-3\n"))
        orphan_id = "sz-2026-05-01-9"
        write(root, "orphan/index.md",
              self.UNIT_TEMPLATE.format(sizing_line=f"sizing_id: {orphan_id}\n"))
        errors, warnings = validate.check_vault(root)
        self.assertEqual(errors, [])
        self.assertTrue(any(orphan_id in w for w in warnings))
        self.assertFalse(any("sizingcore" in w for w in warnings))
        orphan_warnings = [w for w in warnings if "orphan" in w]
        self.assertTrue(orphan_warnings)
        self.assertTrue(any(orphan_id in w for w in orphan_warnings))

    def test_reconciliation_warnings_never_change_exit_code(self):
        """Adversarial where: a reconciliation finding reads more severely
        than a stray wikilink ('the log says this should exist'), which
        could tempt an implementation into routing it through the errors
        list instead of warnings. The plan is explicit these never affect
        the exit code; assert through `validate.run` end to end, not just
        `check_vault`'s return tuple, so the exit-code wiring itself is
        exercised."""
        root = self._vault()
        write(root, "sizingcore/index.md", self.UNIT_TEMPLATE.format(sizing_line=""))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = validate.run([])
        self.assertEqual(code, 0)
        self.assertIn("0 error(s)", err.getvalue())

    def test_vault_with_no_log_file_produces_no_crash_only_unrecorded_warnings(self):
        """Adversarial where: `.compass/meta/sizing-log.yaml` does not exist
        at all - the real state of this project's own vault, which predates
        TASK-080. Code that unconditionally opens the log path would raise
        FileNotFoundError on every vault that has never run a shape-changing
        command. Neither fixture shape here carries a `sizing_id` (nothing
        has ever recorded them), so only the no-id warning class may fire -
        an implementation that also emits an id-absent-from-log warning by
        treating a missing log as 'zero rows, check anyway' would produce
        the wrong finding shape even though it doesn't crash."""
        root = self._vault()
        write(root, "sizingcore/index.md", self.UNIT_TEMPLATE.format(sizing_line=""))
        write(root, "specs/SPEC-777-sizeme/index.md",
              self.FOLDER_SPEC_TEMPLATE.format(sizing_line=""))
        self.assertFalse((root / "meta" / "sizing-log.yaml").exists())
        errors, warnings = validate.check_vault(root)
        self.assertEqual(errors, [])
        self.assertTrue(any("sizingcore" in w for w in warnings))
        self.assertTrue(any("SPEC-777-sizeme" in w for w in warnings))


class DecisionCommandBase(unittest.TestCase):
    """Shared fixture: an isolated vault plus captured-stream command runs."""

    SPEC_WITH_DECISIONS = (
        "---\ntitle: Source spec\ntype: spec\nstatus: approved\n---\n\n"
        "## Decisions\n\n"
        "- **D-01:** first ruling\n"
        "- **D-02:** second ruling\n"
        "- **D-03 [deferred]:** parked ruling\n"
    )
    ADR_WITH_DECISIONS = (
        "---\ntitle: Choice\ntype: decision\nstatus: approved\n---\n\n"
        "## Decision\n\n"
        "- **D-01:** adr ruling one\n"
        "- **D-02:** adr ruling two\n"
    )
    MALFORMED = (
        "---\ntitle: Broken\ntype: decision\nstatus: approved\n---\n\n"
        "## Decision\n\n"
        "- **D-01 no separator at all\n"
    )

    def setUp(self):
        self.root = make_vault(self)
        with_vault_env(self, self.root)

    def run_command(self, module, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = module.run(args)
        return code, out.getvalue(), err.getvalue()

    def plan(self, body_lines, deps=("SPEC-001-src",)):
        dep_items = ", ".join(f'"[[{d}]]"' for d in deps)
        return (
            f"---\ntitle: P\ntype: plan\nstatus: approved\n"
            f"depends_on: [{dep_items}]\n---\n\n## Phases\n\n"
            + "\n".join(body_lines) + "\n"
        )


class DecisionsCommandTests(DecisionCommandBase):
    def test_lists_decisions_with_flags_and_tags(self):
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        code, out, err = self.run_command(decisions, ["SPEC-001-src"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("specs/SPEC-001-src.md - 3 decision(s)", out)
        lines = out.strip().splitlines()
        d1 = next(line for line in lines if line.startswith("D-01"))
        self.assertIn("yes", d1)
        self.assertIn("first ruling", d1)
        d3 = next(line for line in lines if line.startswith("D-03"))
        self.assertIn("no", d3)
        self.assertIn("deferred", d3)

    def test_none_present_exits_zero(self):
        write(self.root, "specs/SPEC-001-src.md",
              "---\ntitle: S\ntype: spec\nstatus: approved\n---\n\nprose only\n")
        code, out, _ = self.run_command(decisions, ["SPEC-001-src"])
        self.assertEqual(code, 0)
        self.assertIn("no decisions present", out)

    def test_malformed_doc_fails_loud_naming_the_file(self):
        write(self.root, "decisions/ADR-001-broken.md", self.MALFORMED)
        code, _, err = self.run_command(decisions, ["ADR-001-broken"])
        self.assertEqual(code, 1)
        self.assertIn("could not parse decisions", err)
        self.assertIn("decisions/ADR-001-broken.md", err)

    def test_unknown_doc_exits_one(self):
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        code, _, err = self.run_command(decisions, ["NoSuchDoc"])
        self.assertEqual(code, 1)
        self.assertIn("not found: NoSuchDoc", err)

    def test_ambiguous_stem_lists_candidates(self):
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        write(self.root, "research/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        code, _, err = self.run_command(decisions, ["SPEC-001-src"])
        self.assertEqual(code, 1)
        self.assertIn("ambiguous", err)
        self.assertIn("specs/SPEC-001-src.md", err)
        self.assertIn("research/SPEC-001-src.md", err)

    def test_path_qualified_argument_resolves(self):
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        write(self.root, "research/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        code, out, _ = self.run_command(decisions, ["specs/SPEC-001-src"])
        self.assertEqual(code, 0)
        self.assertIn("specs/SPEC-001-src.md", out)

    def test_usage_error_exits_one(self):
        code, _, err = self.run_command(decisions, [])
        self.assertEqual(code, 1)
        self.assertIn("usage", err)


class CoverageCommandTests(DecisionCommandBase):
    @staticmethod
    def _line_no(body_lines, text):
        """Absolute 1-based line number of `text` inside a `plan()`
        fixture's body: nine frontmatter/heading lines (`---` block,
        blank, `## Phases`, blank) precede `body_lines[0]`."""
        return 10 + body_lines.index(text)

    def test_uncovered_trackable_decision_fails(self):
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        write(self.root, "plans/PLAN-001-p.md", self.plan([
            "- [ ] TASK-001: a - decisions: [SPEC-001-src/D-01]",
        ]))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 1)
        d2 = next(line for line in out.splitlines() if "D-02" in line)
        self.assertIn("NOT COVERED", d2)
        self.assertIn("1 covered, 0 scoped, 1 uncovered", out)
        self.assertIn("FAIL", out)

    def test_all_trackable_covered_passes(self):
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        write(self.root, "plans/PLAN-001-p.md", self.plan([
            "- [ ] TASK-001: a - decisions: [SPEC-001-src/D-01, SPEC-001-src/D-02]",
        ]))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 0)
        self.assertIn("2 covered, 0 scoped, 0 uncovered", out)
        self.assertIn("PASS", out)

    def test_deferred_decision_uncovered_is_not_counted(self):
        # D-03 is [deferred]: shown in the table, excluded from the gate.
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        write(self.root, "plans/PLAN-001-p.md", self.plan([
            "- [ ] TASK-001: a - decisions: [SPEC-001-src/D-01, SPEC-001-src/D-02]",
        ]))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 0)
        d3 = next(line for line in out.splitlines() if "D-03" in line)
        self.assertIn("no", d3)
        self.assertIn("2 trackable decision(s)", out)

    def test_malformed_source_fails_but_prints_other_rows(self):
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        write(self.root, "decisions/ADR-001-broken.md", self.MALFORMED)
        write(self.root, "plans/PLAN-001-p.md", self.plan(
            ["- [ ] TASK-001: a - decisions: [SPEC-001-src/D-01, SPEC-001-src/D-02]"],
            deps=("SPEC-001-src", "ADR-001-broken"),
        ))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 1)
        self.assertIn("COULD NOT PARSE", out)
        d1 = next(
            line for line in out.splitlines()
            if line.startswith("SPEC-001-src") and "D-01" in line
        )
        self.assertIn("covered", d1)
        self.assertIn("could not be parsed", out)

    def test_bare_citation_is_warned_and_not_counted(self):
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        write(self.root, "plans/PLAN-001-p.md", self.plan([
            "- [ ] TASK-001: a - decisions: [D-01, SPEC-001-src/D-02]",
        ]))
        code, out, err = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 1)
        d1 = next(line for line in out.splitlines() if "D-01" in line)
        self.assertIn("NOT COVERED", d1)
        self.assertIn("bare D-NN token(s)", err)

    def test_citations_in_code_never_claim(self):
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        write(self.root, "plans/PLAN-001-p.md", self.plan([
            "Fenced example:",
            "```",
            "- [ ] TASK-001: a - decisions: [SPEC-001-src/D-01]",
            "```",
            "Inline example: `SPEC-001-src/D-02`.",
        ]))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 1)
        self.assertIn("0 covered, 0 scoped, 2 uncovered", out)

    def test_research_dependency_is_not_a_source(self):
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        write(self.root, "research/RESEARCH-notes.md",
              "---\ntitle: R\ntype: research\nstatus: done\n---\n\n"
              "## Decisions\n\n- **D-09:** never scanned\n")
        write(self.root, "plans/PLAN-001-p.md", self.plan(
            ["- [ ] TASK-001: a - decisions: [SPEC-001-src/D-01, SPEC-001-src/D-02]"],
            deps=("SPEC-001-src", "RESEARCH-notes"),
        ))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 0)
        self.assertNotIn("D-09", out)
        self.assertIn("in 1 source(s)", out)

    def test_against_overrides_default_sources(self):
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        write(self.root, "decisions/ADR-001-choice.md", self.ADR_WITH_DECISIONS)
        write(self.root, "plans/PLAN-001-p.md", self.plan([
            "- [ ] TASK-001: a - decisions: "
            "[ADR-001-choice/D-01, ADR-001-choice/D-02]",
        ]))
        code, out, _ = self.run_command(
            coverage, ["PLAN-001-p", "--against", "ADR-001-choice"]
        )
        self.assertEqual(code, 0)
        self.assertNotIn("SPEC-001-src", out.split("\n", 1)[1])
        self.assertIn("2 covered, 0 scoped, 0 uncovered", out)

    def test_sources_without_decisions_report_none_and_pass(self):
        write(self.root, "specs/SPEC-001-src.md",
              "---\ntitle: S\ntype: spec\nstatus: approved\n---\n\nprose only\n")
        write(self.root, "plans/PLAN-001-p.md", self.plan(["body"]))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 0)
        self.assertIn("no trackable decisions", out)

    def test_no_sources_passes_with_note(self):
        write(self.root, "plans/PLAN-001-p.md", self.plan(["body"], deps=()))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 0)
        self.assertIn("no sources", out)

    def test_unknown_plan_exits_one(self):
        code, _, err = self.run_command(coverage, ["NoSuchPlan"])
        self.assertEqual(code, 1)
        self.assertIn("not found", err)

    def test_usage_error_exits_one(self):
        code, _, err = self.run_command(coverage, [])
        self.assertEqual(code, 1)
        self.assertIn("usage", err)

    def test_later_only_citation_is_scoped_counted_and_exits_zero(self):
        """Adversarial where: a decision claimed only by an intent line
        under `## Later` must land in its own scoped bucket - not merge
        into covered (which would hide unbuilt work) or into uncovered
        (which would fail a gate a plan is meant to pass at approval
        time)."""
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        body = [
            "- [ ] TASK-001: a - decisions: [SPEC-001-src/D-02]",
            "",
            "## Later",
            "",
            "- [ ] TASK-002: b - decisions: [SPEC-001-src/D-01]",
        ]
        write(self.root, "plans/PLAN-001-p.md", self.plan(body))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 0)
        d1 = next(line for line in out.splitlines() if "D-01" in line)
        self.assertIn(f"scoped (line {self._line_no(body, body[4])})", d1)
        self.assertIn("1 covered, 1 scoped, 0 uncovered", out)
        self.assertIn("PASS", out)

    def test_detailed_claim_beats_scoped_claim_regardless_of_file_order(self):
        """Adversarial where: precedence must be state-based (a detailed
        claim always wins) rather than order-based (the first claim seen
        wins) - `_claims` has to keep every site and let a detailed one
        beat a scoped one no matter which line the file puts first."""
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)

        detailed_first = [
            "- [ ] TASK-001: a - decisions: "
            "[SPEC-001-src/D-01, SPEC-001-src/D-02]",
            "",
            "## Later",
            "",
            "- [ ] TASK-002: b - decisions: [SPEC-001-src/D-01]",
        ]
        write(self.root, "plans/PLAN-001-p.md", self.plan(detailed_first))
        with self.subTest(order="detailed_before_scoped"):
            code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
            self.assertEqual(code, 0)
            d1 = next(line for line in out.splitlines() if "D-01" in line)
            self.assertIn(
                "covered (line "
                f"{self._line_no(detailed_first, detailed_first[0])})",
                d1,
            )

        scoped_first = [
            "## Later",
            "",
            "- [ ] TASK-001: a - decisions: [SPEC-001-src/D-01]",
            "",
            "## Risks",
            "",
            "- [ ] TASK-002: b - decisions: "
            "[SPEC-001-src/D-01, SPEC-001-src/D-02]",
        ]
        write(self.root, "plans/PLAN-002-p.md", self.plan(scoped_first))
        with self.subTest(order="scoped_before_detailed"):
            code, out, _ = self.run_command(coverage, ["PLAN-002-p"])
            self.assertEqual(code, 0)
            d1 = next(line for line in out.splitlines() if "D-01" in line)
            self.assertIn(
                "covered (line "
                f"{self._line_no(scoped_first, scoped_first[6])})",
                d1,
            )

    def test_post_later_prose_citation_does_not_upgrade_scoped_decision(self):
        """Adversarial where: a prose citation only counts when no task
        line claims the decision at all - a decision an intent line
        already claims must stay scoped even when a qualified citation
        for it later shows up in ordinary prose (e.g. `## Risks`, which
        sits after `## Later` closes and is therefore detailed); letting
        that prose citation win would quietly upgrade a promise no task
        line has elaborated yet."""
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        body = [
            "- [ ] TASK-000: setup - decisions: [SPEC-001-src/D-02]",
            "",
            "## Later",
            "",
            "- [ ] TASK-001: a - decisions: [SPEC-001-src/D-01]",
            "",
            "## Risks",
            "",
            "See SPEC-001-src/D-01 for the reasoning, written after "
            "Later closes.",
        ]
        write(self.root, "plans/PLAN-001-p.md", self.plan(body))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 0)
        d1 = next(line for line in out.splitlines() if "D-01" in line)
        self.assertIn(f"scoped (line {self._line_no(body, body[4])})", d1)
        d2 = next(line for line in out.splitlines() if "D-02" in line)
        self.assertIn(f"covered (line {self._line_no(body, body[0])})", d2)
        self.assertIn("1 covered, 1 scoped, 0 uncovered", out)
        self.assertIn("PASS", out)

    def test_prose_only_citation_with_no_task_line_claim_is_covered(self):
        """Adversarial where: the precedence rule is "a task line
        claiming the decision beats prose," not "prose never counts" - a
        decision no task line ever names, but that ordinary detailed
        prose cites, must still report covered rather than uncovered."""
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        body = [
            "Prose only: SPEC-001-src/D-01 is settled here, no task "
            "claims it.",
            "",
            "- [ ] TASK-001: a - decisions: [SPEC-001-src/D-02]",
        ]
        write(self.root, "plans/PLAN-001-p.md", self.plan(body))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 0)
        d1 = next(line for line in out.splitlines() if "D-01" in line)
        self.assertIn(f"covered (line {self._line_no(body, body[0])})", d1)
        self.assertIn("2 covered, 0 scoped, 0 uncovered", out)
        self.assertIn("PASS", out)

    def test_uncovered_and_scoped_are_counted_in_separate_columns(self):
        """Adversarial where: a decision cited nowhere at all must still
        fail the gate even though a sibling decision in the same plan is
        merely scoped - the new scoped bucket must not become a place an
        actually-uncovered decision can hide behind."""
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        body = [
            "## Later",
            "",
            "- [ ] TASK-001: a - decisions: [SPEC-001-src/D-01]",
        ]
        write(self.root, "plans/PLAN-001-p.md", self.plan(body))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 1)
        d1 = next(line for line in out.splitlines() if "D-01" in line)
        self.assertIn(f"scoped (line {self._line_no(body, body[2])})", d1)
        d2 = next(line for line in out.splitlines() if "D-02" in line)
        self.assertIn("NOT COVERED", d2)
        self.assertIn("0 covered, 1 scoped, 1 uncovered", out)
        self.assertIn("FAIL", out)

    def test_commit_upfront_task_inside_later_is_covered_not_scoped(self):
        """Adversarial where: a `commit-upfront:` field on a task line
        inside `## Later` overrides that single line back to detailed - a
        coverage command that reads only the region a line's enclosing
        heading opened, ignoring the per-line override, would misreport
        it as scoped instead of covered."""
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        body = [
            "- [ ] TASK-000: setup - decisions: [SPEC-001-src/D-02]",
            "",
            "## Later",
            "",
            "- [ ] TASK-001: b - decisions: [SPEC-001-src/D-01], "
            "commit-upfront: pinned early",
        ]
        write(self.root, "plans/PLAN-001-p.md", self.plan(body))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 0)
        d1 = next(line for line in out.splitlines() if "D-01" in line)
        self.assertIn(f"covered (line {self._line_no(body, body[4])})", d1)
        self.assertIn("2 covered, 0 scoped, 0 uncovered", out)
        self.assertIn("PASS", out)

    def test_record_region_citation_is_discarded_and_reports_uncovered(self):
        """Adversarial where: a `## Wave N elaborated` section quotes past
        intent and must claim nothing - even a citation shaped exactly
        like a task line's `decisions:` field, sitting inside that
        section, must not count, or a promoted-then-reverted line could
        resurrect a claim the plan no longer makes."""
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        body = [
            "- [ ] TASK-001: a - decisions: [SPEC-001-src/D-02]",
            "",
            "## Wave 1 elaborated",
            "",
            "- [ ] TASK-002: b - decisions: [SPEC-001-src/D-01]",
        ]
        write(self.root, "plans/PLAN-001-p.md", self.plan(body))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 1)
        d1 = next(line for line in out.splitlines() if "D-01" in line)
        self.assertIn("NOT COVERED", d1)
        d2 = next(line for line in out.splitlines() if "D-02" in line)
        self.assertIn(f"covered (line {self._line_no(body, body[0])})", d2)
        self.assertIn("1 covered, 0 scoped, 1 uncovered", out)
        self.assertIn("FAIL", out)

    def test_strict_flag_promotes_scoped_to_uncovered_for_exit_code(self):
        """Adversarial where: `--strict` exists to fail the gate on a
        scoped-only plan (nothing is actually uncovered) by counting
        scoped as uncovered for the exit code - a flag that only changes
        the summary wording and not the exit code would let plan
        completion pass with named-but-unbuilt decisions still open. On a
        plan with nothing scoped, `--strict` must change nothing at all,
        not even incidentally reformat the passing output."""
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)

        scoped_body = [
            "- [ ] TASK-001: a - decisions: [SPEC-001-src/D-02]",
            "",
            "## Later",
            "",
            "- [ ] TASK-002: b - decisions: [SPEC-001-src/D-01]",
        ]
        write(self.root, "plans/PLAN-001-p.md", self.plan(scoped_body))
        with self.subTest(case="scoped_only_plan"):
            code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
            self.assertEqual(code, 0)
            self.assertIn("PASS", out)
            code, out, _ = self.run_command(
                coverage, ["PLAN-001-p", "--strict"]
            )
            self.assertEqual(code, 1)
            self.assertIn("FAIL (strict)", out)

        nothing_scoped_body = [
            "- [ ] TASK-001: a - decisions: "
            "[SPEC-001-src/D-01, SPEC-001-src/D-02]",
        ]
        write(self.root, "plans/PLAN-002-p.md", self.plan(nothing_scoped_body))
        with self.subTest(case="nothing_scoped"):
            code_default, out_default, _ = self.run_command(
                coverage, ["PLAN-002-p"]
            )
            code_strict, out_strict, _ = self.run_command(
                coverage, ["PLAN-002-p", "--strict"]
            )
            self.assertEqual(code_default, 0)
            self.assertEqual(code_default, code_strict)
            self.assertEqual(out_default, out_strict)

    def test_malformed_source_and_scoped_decision_still_exits_one_not_two(
        self,
    ):
        """Adversarial where: two independent failure reasons landing in
        the same run - an unparseable source and an uncovered decision -
        could tempt a naive implementation to sum failure counts into the
        exit code instead of clamping to the binary 0/1 gate contract; a
        scoped row rides along too, unrelated to either failure. The exit
        code must still land on exactly 1, never 2."""
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        write(self.root, "decisions/ADR-001-broken.md", self.MALFORMED)
        body = [
            "## Later",
            "",
            "- [ ] TASK-001: a - decisions: [SPEC-001-src/D-01]",
        ]
        write(self.root, "plans/PLAN-001-p.md", self.plan(
            body, deps=("SPEC-001-src", "ADR-001-broken"),
        ))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 1)
        self.assertIn("COULD NOT PARSE", out)
        d1 = next(
            line for line in out.splitlines()
            if line.startswith("SPEC-001-src") and "D-01" in line
        )
        self.assertIn("scoped", d1)
        d2 = next(
            line for line in out.splitlines()
            if line.startswith("SPEC-001-src") and "D-02" in line
        )
        self.assertIn("NOT COVERED", d2)

    def test_unterminated_fence_notes_and_treats_everything_detailed(self):
        """Adversarial where: `classify_lines` returns an empty region map
        for an unterminated fence precisely so a caller cannot mistake
        that emptiness for "nothing scoped" - the coverage command must
        surface a note about it rather than silently proceeding, and
        every line, including one that visually sits under `## Later`,
        must classify as detailed once the region map is empty."""
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        body = [
            "## Later",
            "",
            "- [ ] TASK-001: a - decisions: "
            "[SPEC-001-src/D-01, SPEC-001-src/D-02]",
            "",
            "```",
            "deliberately unclosed",
        ]
        write(self.root, "plans/PLAN-001-p.md", self.plan(body))
        code, out, err = self.run_command(coverage, ["PLAN-001-p"])
        combined = (out + err).lower()
        self.assertIn("unterminated", combined)
        self.assertIn("fence", combined)
        self.assertEqual(code, 0)
        d1 = next(line for line in out.splitlines() if "D-01" in line)
        self.assertIn("covered", d1)
        self.assertNotIn("scoped", d1)
        self.assertIn("0 scoped", out)


class CoverageCorpusPinTests(unittest.TestCase):
    """Regression pins: `compass coverage` against this repo's own real
    plans must keep exiting 0 once the summary gains the three-state
    columns, exactly as PLAN-008-rolling-wave's own verification section
    records for PLAN-006 and PLAN-007."""

    REPO_ROOT = Path(__file__).resolve().parents[3]

    def setUp(self):
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.REPO_ROOT)

        def restore():
            if old is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = old

        self.addCleanup(restore)

    def run_command(self, module, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = module.run(args)
        return code, out.getvalue(), err.getvalue()

    def test_plan_006_learning_loop_still_passes(self):
        """Adversarial where: the three-state summary rewrite regresses a
        real plan that predates the Later region and carries no scoped
        rows - it must still exit 0, not drop into FAIL because the
        summary format changed under it."""
        code, out, err = self.run_command(
            coverage, ["PLAN-006-learning-loop"]
        )
        self.assertEqual(code, 0, err or out)

    def test_plan_007_test_quality_still_passes(self):
        """Adversarial where: same regression risk as PLAN-006, on the
        other real plan the task contract names as a corpus pin."""
        code, out, err = self.run_command(
            coverage, ["PLAN-007-test-quality"]
        )
        self.assertEqual(code, 0, err or out)


if __name__ == "__main__":
    unittest.main()
