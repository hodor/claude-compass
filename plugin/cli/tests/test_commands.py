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
    hot_path, unit_check, validate,
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
        # Header plus the 13 agents plus the detached index-summary job row.
        self.assertEqual(len(lines), 15)
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
            self.assertEqual(make_unit.run(self.ARGS + ["--apply"]), 0)
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
            self.assertEqual(make_unit.run(self.ARGS + ["--apply"]), 0)
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
            self.assertEqual(make_unit.run(self.ARGS + ["--apply"]), 1)
        self.assertIn("target exists: core", err.getvalue())
        self.assertTrue((root / "specs" / "SPEC-001-core.md").is_file())

    def test_refuses_reserved_name(self):
        root = self._vault()
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(make_unit.run(["prs", "specs/SPEC-001-core.md", "--apply"]), 1)
        self.assertIn("reserved name: prs", err.getvalue())
        self.assertFalse((root / "prs").exists())

    def test_refuses_ambiguous_artifact_name(self):
        root = self._vault()
        write(root, "research/SPEC-001-core.md", self.SPEC)
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(make_unit.run(["core", "SPEC-001-core", "--apply"]), 1)
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
                make_unit.run(["core", "specs/SPEC-999-none.md", "--apply"]), 1
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
                make_unit.run(["core", "other/specs/SPEC-001-x.md", "--apply"]), 1
            )
        self.assertIn("not in a root type directory", err.getvalue())
        self.assertFalse((root / "core").exists())

    def test_usage_error_exits_one_never_two(self):
        root = self._vault()
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(make_unit.run([]), 1)
            self.assertEqual(make_unit.run(["core"]), 1)
        self.assertIn("usage", err.getvalue())
        self.assertFalse((root / "core").exists())


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
    def test_uncovered_trackable_decision_fails(self):
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        write(self.root, "plans/PLAN-001-p.md", self.plan([
            "- [ ] TASK-001: a - decisions: [SPEC-001-src/D-01]",
        ]))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 1)
        d2 = next(line for line in out.splitlines() if "D-02" in line)
        self.assertIn("NOT COVERED", d2)
        self.assertIn("1 covered, 1 uncovered", out)
        self.assertIn("FAIL", out)

    def test_all_trackable_covered_passes(self):
        write(self.root, "specs/SPEC-001-src.md", self.SPEC_WITH_DECISIONS)
        write(self.root, "plans/PLAN-001-p.md", self.plan([
            "- [ ] TASK-001: a - decisions: [SPEC-001-src/D-01, SPEC-001-src/D-02]",
        ]))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 0)
        self.assertIn("2 covered, 0 uncovered", out)
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
        self.assertIn("0 covered, 2 uncovered", out)

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
        self.assertIn("2 covered, 0 uncovered", out)

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


if __name__ == "__main__":
    unittest.main()
