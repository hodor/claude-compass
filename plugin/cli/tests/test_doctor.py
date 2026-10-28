"""Tests for `compass doctor`, the install-drift diagnostic. Adversarial:
most cases build a specific partial install (missing plugin.yaml, an
unregistered hooks.json, a hole in the CLI's command modules, a v0.2.0-shaped
install with skills but no hooks anywhere) and assert doctor names the
defect and exits 1, never 2, and never raises."""

import datetime
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import capturelib  # noqa: E402
from commands import doctor  # noqa: E402


def make_project(test_case):
    """A bare project dir with an empty `.compass/`, nothing under
    `.claude/`. Host detection is pinned off so doctor's row set does not
    depend on whether the machine running the suite has dsh; tests about
    the dsh rows re-pin it on."""
    import hostlib
    test_case.addCleanup(setattr, hostlib, "dsh_available", hostlib.dsh_available)
    hostlib.dsh_available = lambda: False
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    (tmp / ".compass").mkdir()
    isolate_user_settings(test_case)
    return tmp


def isolate_user_settings(test_case):
    """Point HOME, USERPROFILE and CLAUDE_CONFIG_DIR at temp dirs so no test
    reads the real ~/.claude/settings.json, and seed the isolated user
    settings with a long retention so the session-retention row is OK unless
    a test overrides it."""
    base = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, base, True)
    home = base / "home"
    config = base / "cfg"
    home.mkdir()
    config.mkdir()
    with_env(test_case, "HOME", str(home))
    with_env(test_case, "USERPROFILE", str(home))
    with_env(test_case, "CLAUDE_CONFIG_DIR", str(config))
    (config / "settings.json").write_text(
        json.dumps({"cleanupPeriodDays": 3650}), encoding="utf-8")
    return config


def with_env(test_case, name, value):
    old = os.environ.get(name)
    os.environ[name] = value

    def restore():
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old

    test_case.addCleanup(restore)


def with_project_env(test_case, project_root):
    old = os.environ.get("CLAUDE_PROJECT_DIR")
    os.environ["CLAUDE_PROJECT_DIR"] = str(project_root)

    def restore():
        if old is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = old

    test_case.addCleanup(restore)


def write_plugin_yaml(project_root, version="0.4.0"):
    path = project_root / ".compass" / "meta" / "plugin.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"plugin:\n  name: compass\n  version: {version}\n", encoding="utf-8")


def write_lessons_catalog(project_root):
    path = project_root / ".compass" / "meta" / "lessons-catalog.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("lessons: []\n", encoding="utf-8")


def _hook_entry(command_text):
    return {"hooks": [{"type": "command", "command": command_text}]}


def write_settings(project_root, events, filename="settings.json"):
    """`events` maps event name -> command text (or a list of command texts).
    Writes a settings file with a top-level `hooks` key holding those events."""
    hooks = {}
    for event_name, commands in events.items():
        texts = commands if isinstance(commands, list) else [commands]
        hooks[event_name] = [_hook_entry(text) for text in texts]
    path = project_root / ".claude" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"hooks": hooks}), encoding="utf-8")


def write_malformed_settings(project_root, filename="settings.json"):
    path = project_root / ".claude" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")


def write_hooks_json(project_root):
    path = project_root / ".claude" / "hooks" / "hooks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"hooks": {}}), encoding="utf-8")


FULL_HOOK_EVENTS = {
    "PreToolUse": 'python "$CLAUDE_PROJECT_DIR/.claude/cli/compass" guard --hook',
    "PostToolUse": 'python "$CLAUDE_PROJECT_DIR/.claude/cli/compass" sync --hook',
    "Stop": 'python "$CLAUDE_PROJECT_DIR/.claude/cli/compass" capture-check --hook',
    "SubagentStop": 'python "$CLAUDE_PROJECT_DIR/.claude/cli/compass" capture-signal --hook',
    "TeammateIdle": 'python "$CLAUDE_PROJECT_DIR/.claude/cli/compass" capture-signal --hook',
}


def write_full_cli(project_root, commands=("sync", "capture-check", "capture-signal")):
    cli_dir = project_root / ".claude" / "cli"
    commands_dir = cli_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    (commands_dir / "__init__.py").write_text("", encoding="utf-8")
    specs_lines = "\n".join(f'    ("{name}", "help"),' for name in commands)
    (cli_dir / "maincli.py").write_text(f"COMMAND_SPECS = [\n{specs_lines}\n]\n", encoding="utf-8")
    for name in commands:
        module_name = name.replace("-", "_") + ".py"
        (commands_dir / module_name).write_text("def run(args):\n    return 0\n", encoding="utf-8")


def write_agents(project_root, names=("builder.md", "debug.md")):
    path = project_root / ".claude" / "agents"
    path.mkdir(parents=True, exist_ok=True)
    for name in names:
        (path / name).write_text("", encoding="utf-8")


def write_skills(project_root, names=("build", "checkup")):
    path = project_root / ".claude" / "skills"
    path.mkdir(parents=True, exist_ok=True)
    for name in names:
        (path / name).mkdir(parents=True, exist_ok=True)


def build_complete_install(project_root):
    write_plugin_yaml(project_root)
    write_lessons_catalog(project_root)
    write_settings(project_root, FULL_HOOK_EVENTS)
    write_hooks_json(project_root)
    write_full_cli(project_root)
    write_agents(project_root)
    write_skills(project_root)


def run_doctor(args=None):
    out = io.StringIO()
    with redirect_stdout(out):
        code = doctor.run(args or [])
    return code, out.getvalue()


class CompleteInstallTests(unittest.TestCase):
    def test_complete_install_exits_0(self):
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        code, out = run_doctor()
        self.assertEqual(code, 0)
        self.assertIn("OK", out)
        self.assertNotIn("FAIL", out)

    def test_complete_install_json_flag(self):
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        code, out = run_doctor(["--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(all(row["status"] != "FAIL" for row in payload["checks"]))


class ObsidianReviewCheckTests(unittest.TestCase):
    def row(self, project):
        code, out = run_doctor(["--json"])
        rows = [r for r in json.loads(out)["checks"] if r["check"] == "obsidian review"]
        self.assertEqual(len(rows), 1, out)
        return code, rows[0]

    def setUp(self):
        self.project = make_project(self)
        with_project_env(self, self.project)
        build_complete_install(self.project)
        self.config = self.project / "obsidian.json"
        with_env(self, "COMPASS_OBSIDIAN_CONFIG", str(self.config))
        self.obsidian = self.project / ".compass" / ".obsidian"

    def listed(self):
        self.config.write_text(json.dumps({"vaults": {"v1": {"path": str(self.project / ".compass")}}}), encoding="utf-8")

    def plugin(self, on):
        d = self.obsidian / "plugins" / "compass-review"
        d.mkdir(parents=True, exist_ok=True)
        (d / "main.js").write_text("//", encoding="utf-8")
        (self.obsidian / "community-plugins.json").write_text(json.dumps(["compass-review"] if on else []), encoding="utf-8")

    def test_no_obsidian_vault_is_ok(self):
        code, row = self.row(self.project)
        self.assertEqual((code, row["status"]), (0, "OK"))
        self.assertIn("terminal", row["detail"])

    def test_absent_plugin_warns_with_install_and_enable_steps(self):
        self.obsidian.mkdir()
        self.listed()
        code, row = self.row(self.project)
        self.assertEqual((code, row["status"]), (0, "WARN"))
        self.assertIn("compass review --install", row["fix"])
        self.assertIn("restricted mode", row["fix"])

    def test_off_plugin_warns_with_enable_steps(self):
        self.plugin(on=False)
        self.listed()
        _, row = self.row(self.project)
        self.assertEqual(row["status"], "WARN")
        self.assertIn("switch on Compass Review", row["fix"])

    def test_on_but_unlisted_vault_warns(self):
        self.plugin(on=True)
        _, row = self.row(self.project)
        self.assertEqual(row["status"], "WARN")
        self.assertIn("open this vault once in Obsidian", row["fix"])

    def test_on_and_listed_is_ok(self):
        self.plugin(on=True)
        self.listed()
        _, row = self.row(self.project)
        self.assertEqual(row["status"], "OK")


class HookRegistrationTests(unittest.TestCase):
    def test_hooks_json_present_without_settings_registration_fails_naming_defect(self):
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        # Remove settings registration, keep the bare hooks.json.
        (project / ".claude" / "settings.json").unlink()
        code, out = run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out)
        self.assertIn("hooks.json", out)
        self.assertIn("never reads", out)

    def test_missing_stop_entry_fails(self):
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        events = dict(FULL_HOOK_EVENTS)
        del events["Stop"]
        write_settings(project, events)
        code, out = run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("Stop", out)

    def test_no_hooks_anywhere_fails(self):
        project = make_project(self)
        with_project_env(self, project)
        write_plugin_yaml(project)
        write_lessons_catalog(project)
        write_full_cli(project)
        write_agents(project)
        write_skills(project)
        code, out = run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("missing registration", out)

    def test_malformed_settings_json_fails_not_crashes(self):
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        write_malformed_settings(project)
        code, out = run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("not valid JSON", out)

    def test_teammate_idle_absent_is_warn_not_fail(self):
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        events = dict(FULL_HOOK_EVENTS)
        del events["TeammateIdle"]
        write_settings(project, events)
        code, out = run_doctor()
        self.assertEqual(code, 0)
        self.assertIn("WARN", out)
        self.assertIn("TeammateIdle", out)

    def test_registration_split_across_settings_and_settings_local(self):
        project = make_project(self)
        with_project_env(self, project)
        write_plugin_yaml(project)
        write_lessons_catalog(project)
        write_full_cli(project)
        write_agents(project)
        write_skills(project)
        write_settings(project, {
            "PreToolUse": FULL_HOOK_EVENTS["PreToolUse"],
            "PostToolUse": FULL_HOOK_EVENTS["PostToolUse"],
            "Stop": FULL_HOOK_EVENTS["Stop"],
        }, filename="settings.json")
        write_settings(project, {
            "SubagentStop": FULL_HOOK_EVENTS["SubagentStop"],
        }, filename="settings.local.json")
        code, out = run_doctor()
        self.assertEqual(code, 0)


class PluginYamlTests(unittest.TestCase):
    def test_missing_plugin_yaml_fails(self):
        project = make_project(self)
        with_project_env(self, project)
        write_lessons_catalog(project)
        write_settings(project, FULL_HOOK_EVENTS)
        write_full_cli(project)
        write_agents(project)
        write_skills(project)
        code, out = run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("plugin.yaml", out)

    def test_plugin_yaml_without_version_fails(self):
        project = make_project(self)
        with_project_env(self, project)
        path = project / ".compass" / "meta" / "plugin.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("plugin:\n  name: compass\n", encoding="utf-8")
        write_lessons_catalog(project)
        write_settings(project, FULL_HOOK_EVENTS)
        write_full_cli(project)
        write_agents(project)
        write_skills(project)
        code, out = run_doctor()
        self.assertEqual(code, 1)


class CliCompletenessTests(unittest.TestCase):
    def test_missing_one_command_module_fails_naming_it(self):
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        (project / ".claude" / "cli" / "commands" / "capture_check.py").unlink()
        code, out = run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("capture-check", out)

    def test_missing_cli_dir_fails(self):
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        shutil.rmtree(project / ".claude" / "cli")
        code, out = run_doctor()
        self.assertEqual(code, 1)


class V02ShapeTests(unittest.TestCase):
    def test_skills_present_no_hooks_anywhere_is_the_drift_class(self):
        project = make_project(self)
        with_project_env(self, project)
        write_plugin_yaml(project)
        write_lessons_catalog(project)
        write_full_cli(project)
        write_agents(project)
        write_skills(project)
        # v0.2.0 shape: skills dir exists, nothing hooks-related exists at all.
        code, out = run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("automatic step registration", out)


class AgentsSkillsTests(unittest.TestCase):
    def test_missing_agents_dir_is_flagged(self):
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        shutil.rmtree(project / ".claude" / "agents")
        code, out = run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("agents", out)

    def test_empty_agents_dir_is_flagged(self):
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        for child in (project / ".claude" / "agents").iterdir():
            child.unlink()
        code, out = run_doctor()
        self.assertEqual(code, 1)

    def test_missing_skills_dir_is_flagged(self):
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        shutil.rmtree(project / ".claude" / "skills")
        code, out = run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("skills", out)


class LessonsCatalogTests(unittest.TestCase):
    def test_missing_lessons_catalog_fails(self):
        project = make_project(self)
        with_project_env(self, project)
        write_plugin_yaml(project)
        write_settings(project, FULL_HOOK_EVENTS)
        write_full_cli(project)
        write_agents(project)
        write_skills(project)
        code, out = run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("lessons-catalog.yaml", out)


class EmptyVaultTests(unittest.TestCase):
    def test_empty_compass_exits_1_gracefully(self):
        project = make_project(self)
        with_project_env(self, project)
        code, out = run_doctor()
        self.assertEqual(code, 1)
        self.assertNotEqual(code, 2)

    def test_no_compass_dir_exits_1_gracefully(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        old_cwd = os.getcwd()
        os.chdir(tmp)
        self.addCleanup(os.chdir, old_cwd)
        with_project_env(self, tmp)
        code, out = run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("vault", out.lower())


class ExitCodeNeverTwoTests(unittest.TestCase):
    def test_malformed_and_incomplete_install_never_exits_2(self):
        project = make_project(self)
        with_project_env(self, project)
        write_malformed_settings(project)
        code, _ = run_doctor()
        self.assertIn(code, (0, 1))

    def test_internal_error_never_crashes(self):
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        import vaultlib
        original = vaultlib.find_vault_root
        vaultlib.find_vault_root = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            code, out = run_doctor()
        finally:
            vaultlib.find_vault_root = original
        self.assertIn(code, (0, 1))
        self.assertNotEqual(code, 2)


def write_vault(project_root, rel, body):
    """Write a vault artifact under `<project_root>/.compass/<rel>`."""
    path = project_root / ".compass" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


UNIT_CHECK_SPEC = "---\ntitle: Core\ntype: spec\nstatus: approved\n---\n\nbody\n"


def unit_check_doc(type_, deps):
    """A tracer artifact of `type_` whose `depends_on` wikilinks `deps`,
    matching the fixture shape `unit_check.find_candidates` itself is tested
    against in test_commands.py::UnitCheckTests."""
    dep_items = ", ".join(f'"[[{d}]]"' for d in deps)
    return (
        f"---\ntitle: T\ntype: {type_}\nstatus: active\n"
        f"depends_on: [{dep_items}]\n---\n\nbody\n"
    )


# The check names `compass doctor` emits today, established by actually
# running `doctor.run(["--json"])` against a fully-passing install with an
# empty `.compass/` (no vault content) before TASK-082 exists: plugin.yaml,
# hook registration, CLI completeness, agents, skills, lessons-catalog.yaml -
# six rows, all "OK", exit 0. The unit-promotion-candidates check is
# identified as whichever row this baseline does not already name, so these
# tests never hard-code the new check's own name or wording.
KNOWN_BASELINE_CHECKS = {
    "plugin.yaml",
    "automatic step registration",
    "CLI completeness",
    "agents",
    "skills",
    "lessons-catalog.yaml",
    "commands you have not run",
    "local additions",
}


def non_baseline_rows(payload):
    return [row for row in payload["checks"] if row["check"] not in KNOWN_BASELINE_CHECKS]


class UnitPromotionCandidateTests(unittest.TestCase):
    def test_type_spread_exactly_three_produces_advisory_candidate_row(self):
        """Adversarial where: type-spread sits exactly at the promotion
        threshold (3 distinct artifact types, spec included) rather than
        comfortably above it. A check written to fire only when clearly over
        threshold, instead of at it, would miss this boundary. The row must
        still be advisory: present, but not FAIL, and not enough to move the
        exit code off 0."""
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        write_vault(project, "specs/SPEC-001-core.md", UNIT_CHECK_SPEC)
        write_vault(project, "plans/PLAN-001-impl.md", unit_check_doc("plan", ["SPEC-001-core"]))
        write_vault(project, "decisions/ADR-001-choice.md", unit_check_doc("decision", ["SPEC-001-core"]))
        code, out = run_doctor(["--json"])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        # 15 rows: the baseline checks (session retention, the review-surface rows
        # and the host-roster row included) plus unit-promotion.
        self.assertEqual(len(payload["checks"]), 15)
        new_rows = non_baseline_rows(payload)
        self.assertEqual(len(new_rows), 1)
        row = new_rows[0]
        self.assertNotEqual(row["status"], "FAIL")
        self.assertIn("compass unit-check", row.get("fix", ""))
        self.assertNotIn("\n", row["detail"])
        self.assertIn("core", row["detail"])

    def test_type_spread_two_below_threshold_produces_clean_row(self):
        """Adversarial where: type-spread sits exactly one below the
        threshold (2 distinct types: spec + research) rather than at zero
        dependents. An off-by-one in the threshold comparison (`>` instead of
        `>=`, or counting the spec's own type twice) would still misfire a
        candidate here even though `unit_check.find_candidates` itself does
        not consider two types a spread."""
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        write_vault(project, "specs/SPEC-001-core.md", UNIT_CHECK_SPEC)
        for n in range(1, 4):
            write_vault(
                project,
                f"research/RESEARCH-topic-{n}.md",
                unit_check_doc("research", ["SPEC-001-core"]),
            )
        code, out = run_doctor(["--json"])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        # 15 rows: the baseline checks (session retention, the review-surface rows
        # and the host-roster row included) plus unit-promotion.
        self.assertEqual(len(payload["checks"]), 15)
        new_rows = non_baseline_rows(payload)
        self.assertEqual(len(new_rows), 1)
        self.assertEqual(new_rows[0]["status"], "OK")
        self.assertNotIn("core", new_rows[0]["detail"])

    def test_members_already_inside_a_unit_produce_no_candidate(self):
        """Adversarial where: a type-spread-3 group that would otherwise
        qualify already lives inside a promoted unit folder. Re-detecting
        already-settled members and recommending promotion again is the
        defect `unit_check.find_candidates` itself guards against by
        filtering `unit is None`; doctor's wiring must not bypass that
        filter by, say, scanning a different root."""
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        write_vault(project, "compass-cli/index.md", "---\ntitle: U\ntype: unit\n---\n")
        write_vault(project, "compass-cli/specs/SPEC-001-core.md", UNIT_CHECK_SPEC)
        write_vault(
            project,
            "compass-cli/plans/PLAN-001-impl.md",
            unit_check_doc("plan", ["SPEC-001-core"]),
        )
        write_vault(
            project,
            "compass-cli/decisions/ADR-001-choice.md",
            unit_check_doc("decision", ["SPEC-001-core"]),
        )
        code, out = run_doctor(["--json"])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        new_rows = non_baseline_rows(payload)
        self.assertEqual(len(new_rows), 1)
        self.assertEqual(new_rows[0]["status"], "OK")
        self.assertNotIn("core", new_rows[0]["detail"])

    def test_unreadable_artifact_degrades_to_warn_other_rows_survive(self):
        """Adversarial where: `find_candidates` walks and decodes every
        vault artifact - far more file-system exposure than any existing
        doctor check - and one artifact with invalid UTF-8 bytes raises
        `UnicodeDecodeError` inside `vaultlib.read_vault_text`, uncaught by
        `unit_check.find_candidates` itself (it only swallows frontmatter
        parse errors, not decode errors). If the new check lacks its own
        try/except and the exception reaches `_run_checks`'s outer bare
        `except Exception`, every other row - plugin.yaml, hooks, CLI,
        agents, skills, lessons-catalog - collapses into one generic FAIL
        and the exit code flips to 1. The correct behavior is a local WARN
        naming the scan failure, with the other six rows unchanged from a
        clean install and the exit code still 0."""
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        garbage = project / ".compass" / "specs" / "SPEC-002-garbage.md"
        garbage.parent.mkdir(parents=True, exist_ok=True)
        garbage.write_bytes(b"\xff\xfe\x00\x01not valid utf-8")
        code, out = run_doctor(["--json"])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        # 15 rows: the baseline checks (session retention, the review-surface rows
        # and the host-roster row included) plus unit-promotion.
        self.assertEqual(len(payload["checks"]), 15)
        new_rows = non_baseline_rows(payload)
        self.assertEqual(len(new_rows), 1)
        self.assertEqual(new_rows[0]["status"], "WARN")
        self.assertNotIn("\n", new_rows[0]["detail"])
        self.assertTrue(new_rows[0]["detail"])
        baseline_rows = {row["check"]: row["status"] for row in payload["checks"]
                          if row["check"] in KNOWN_BASELINE_CHECKS}
        self.assertTrue(all(status == "OK" for status in baseline_rows.values()))
        self.assertEqual(set(baseline_rows), KNOWN_BASELINE_CHECKS)

    def test_genuine_fail_alongside_candidate_still_exits_one(self):
        """Adversarial where: a real install defect (missing plugin.yaml, the
        same fixture PluginYamlTests.test_missing_plugin_yaml_fails uses) and
        an advisory unit-promotion candidate co-occur in the same run. The
        candidate row's own advisory status must never suppress the genuine
        FAIL's effect on the exit code, and the genuine FAIL must never be
        reported as the candidate check's own status."""
        project = make_project(self)
        with_project_env(self, project)
        write_lessons_catalog(project)
        write_settings(project, FULL_HOOK_EVENTS)
        write_hooks_json(project)
        write_full_cli(project)
        write_agents(project)
        write_skills(project)
        write_vault(project, "specs/SPEC-001-core.md", UNIT_CHECK_SPEC)
        write_vault(project, "plans/PLAN-001-impl.md", unit_check_doc("plan", ["SPEC-001-core"]))
        write_vault(
            project, "decisions/ADR-001-choice.md", unit_check_doc("decision", ["SPEC-001-core"])
        )
        code, out = run_doctor(["--json"])
        payload = json.loads(out)
        self.assertEqual(code, 1)
        fail_rows = [row for row in payload["checks"] if row["status"] == "FAIL"]
        self.assertTrue(any(row["check"] == "plugin.yaml" for row in fail_rows))
        new_rows = non_baseline_rows(payload)
        self.assertEqual(len(new_rows), 1)
        self.assertNotEqual(new_rows[0]["status"], "FAIL")

    def test_json_stays_one_parseable_object_with_two_candidates(self):
        """Adversarial where: two independent candidate groups both qualify
        in the same run, doubling the member list `format_report`'s
        multi-line text block would need. `--json` exposes only
        check/status/detail/fix, so reusing that multi-line block for the
        JSON `detail` field (instead of a one-line summary) would either
        break `json.loads` outright or smuggle embedded newlines into a
        field a downstream consumer expects to be single-line."""
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        write_vault(project, "specs/SPEC-001-core.md", UNIT_CHECK_SPEC)
        write_vault(project, "plans/PLAN-001-impl.md", unit_check_doc("plan", ["SPEC-001-core"]))
        write_vault(
            project, "decisions/ADR-001-choice.md", unit_check_doc("decision", ["SPEC-001-core"])
        )
        write_vault(
            project,
            "specs/SPEC-002-widgets.md",
            "---\ntitle: Widgets\ntype: spec\nstatus: approved\n---\n\nbody\n",
        )
        write_vault(
            project, "plans/PLAN-002-widgets.md", unit_check_doc("plan", ["SPEC-002-widgets"])
        )
        write_vault(
            project,
            "decisions/ADR-002-widgets.md",
            unit_check_doc("decision", ["SPEC-002-widgets"]),
        )
        code, out = run_doctor(["--json"])
        payload = json.loads(out)  # raises if the object is not one parseable blob
        self.assertEqual(code, 0)
        self.assertIsInstance(payload, dict)
        self.assertIsInstance(payload["checks"], list)
        new_rows = non_baseline_rows(payload)
        self.assertEqual(len(new_rows), 1)
        self.assertNotIn("\n", new_rows[0]["detail"])
        self.assertIn("core", new_rows[0]["detail"])
        self.assertIn("widgets", new_rows[0]["detail"])


# ---------------------------------------------------------------------------
# TASK-093: doctor reconciles the worker ledger (PLAN-010, ADR-013 D-10)
# ---------------------------------------------------------------------------
#
# `capturelib.log_event`/`read_log` and the five worker ledger kinds
# (`worker-started`, `worker-spawn-error`, `worker-finished`, `worker-failed`,
# `fallback-fired`) are real (TASK-091). The doctor row that reconciles them
# does not exist yet. Fixtures write the ledger the same way the worker
# wrapper and the future capture-check spawn point do: through
# `capturelib.log_event` for "now" rows, and a raw JSONL append (`log_row`)
# for rows that must be backdated past `worker_grace_seconds` -
# `capturelib.log_event` always stamps the current time, so a boundary-age
# fixture has no other way onto the ledger. The `no_headless_at` latch is a
# state field, not a log row, so its fixture goes through
# `capturelib.save_state` directly, per the task's own instruction.
#
# `PRE_TASK_093_CHECKS` is `KNOWN_BASELINE_CHECKS` (the six install-drift
# rows) plus `"workstreams that could get their own folder"` (TASK-082, already shipped): the
# seven check names a `build_complete_install` fixture produces before this
# task's row exists. The new row is whichever check name a run adds beyond
# that set - the same elimination `non_baseline_rows` uses to isolate the
# unit-promotion row itself, applied one task later so this class never
# hardcodes a name the plan does not fix.

PRE_TASK_093_CHECKS = KNOWN_BASELINE_CHECKS | {"workstreams that could get their own folder"}

# Sanctioned collateral edit for TASK-093: doctor's new "worker ledger" row
# makes `UnitPromotionCandidateTests.non_baseline_rows()` return two rows
# instead of one (the unit-promotion row and this one), since that helper
# still filters on the original 6-name `KNOWN_BASELINE_CHECKS`. This mutation
# runs after `PRE_TASK_093_CHECKS` above has already captured the constant's
# prior value in a new set object, so it does not also swallow this row out
# of `ledger_rows`; `non_baseline_rows` re-reads the module global at call
# time (test methods run long after import), so it sees the addition and
# keeps isolating the unit-promotion row as the older class's own row.
KNOWN_BASELINE_CHECKS.add("background helper log")
# The host-roster row (PLAN-017) appears in every run and is baseline;
# the dsh-only rows appear only in dsh-rostered fixtures, which never
# use these counting helpers.
KNOWN_BASELINE_CHECKS.add("tools in use")
PRE_TASK_093_CHECKS.add("tools in use")
# The session-retention row also appears in every run.
KNOWN_BASELINE_CHECKS.add("session retention")
PRE_TASK_093_CHECKS.add("session retention")
# The review-surface rows also appear in every run.
for _surface_row in ("obsidian review", "vscode review", "cursor review"):
    KNOWN_BASELINE_CHECKS.add(_surface_row)
    PRE_TASK_093_CHECKS.add(_surface_row)


def ledger_rows(payload):
    return [row for row in payload["checks"] if row["check"] not in PRE_TASK_093_CHECKS]


def capture_root(project_root):
    return project_root / ".compass"


def write_capture_config(project_root, **overrides):
    config = dict(capturelib.DEFAULT_CONFIG)
    config.update(overrides)
    path = capture_root(project_root) / "meta" / "capture.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config), encoding="utf-8")
    return config


def iso_ago(seconds):
    dt = capturelib._now() - datetime.timedelta(seconds=seconds)
    return capturelib._iso(dt)


def log_row(project_root, event, at=None, **fields):
    """Append one raw row to `.compass/tmp/capture-log.jsonl`, optionally
    backdating `at`. `capturelib.log_event` always stamps "now", so a
    boundary-age fixture (the grace-period tests need a row aged to the
    exact second) has no way onto the ledger except a direct append
    matching the row shape `capturelib._log_event` itself writes."""
    path = capture_root(project_root) / "tmp" / "capture-log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"at": at or capturelib._iso(capturelib._now()), "event": event}
    row.update(fields)
    with open(path, "a", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(row) + "\n")


def set_no_headless_latch(project_root, at=None):
    root = capture_root(project_root)
    state = capturelib.load_state(root)
    state["no_headless_at"] = at or capturelib._iso(capturelib._now())
    capturelib.save_state(root, state)


class LedgerCountsTests(unittest.TestCase):
    def test_counts_report_accurately(self):
        """Adversarial where: an empty ledger and a populated one are two
        equivalence classes of the same 'reports counts' behavior. A check
        exercised only against a populated fixture during development could
        still misreport the empty case as WARN instead of OK (D-10 requires
        OK, not just 'no exception'). The populated case uses distinct,
        non-adjacent counts (4 started, 3 finished, 1 failed) with
        non-numeric opp-ids so no fixture id text could coincidentally
        satisfy a numeral assertion meant to check the real count."""
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        code, out = run_doctor(["--json"])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        rows = ledger_rows(payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "OK")

        project2 = make_project(self)
        with_project_env(self, project2)
        build_complete_install(project2)
        root = capture_root(project2)
        ids = ["alpha", "beta", "gamma", "delta"]
        for opp_id in ids:
            capturelib.log_event(root, "worker-started", id=f"OPP-{opp_id}", pid=1)
        for opp_id in ids[:3]:
            capturelib.log_event(root, "worker-finished", id=f"OPP-{opp_id}")
        capturelib.log_event(root, "worker-failed", id="OPP-delta", reason="exit 1")
        code, out = run_doctor(["--json"])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        rows = ledger_rows(payload)
        self.assertEqual(len(rows), 1)
        detail = rows[0]["detail"]
        self.assertRegex(detail, r"\b4\b")
        self.assertRegex(detail, r"\b3\b")
        self.assertRegex(detail, r"\b1\b")


class UnfinishedPastGraceTests(unittest.TestCase):
    def test_started_without_end_past_grace_warns_naming_opp_id_and_age(self):
        """Adversarial where: three scenarios share the shape 'a started row
        with no finished row', but only one should WARN. The
        boundary-and-fixture rule requires the exact grace cutoff, not only
        values comfortably on either side, plus a distinct case a
        start-age-only check would get wrong: an old start later matched by
        a finish must never be flagged, even though its start row alone is
        far past grace. `worker_grace_seconds` is overridden to 50 (not
        `DEFAULT_CONFIG`'s 600), so a check that ignores the configured
        grace and silently falls back to the hardcoded default would pass
        this test for the wrong reason."""
        grace = 50
        cases = [
            ("one second under grace: not yet unfinished", grace - 1, False, False),
            ("exactly at grace: unfinished", grace, True, False),
            ("old start matched by a later finish: never unfinished", grace + 500, False, True),
        ]
        for name, age, expect_warn, with_finish in cases:
            with self.subTest(name=name):
                project = make_project(self)
                with_project_env(self, project)
                build_complete_install(project)
                write_capture_config(project, worker_grace_seconds=grace)
                root = capture_root(project)
                log_row(project, "worker-started", at=iso_ago(age), id="OPP-lonely", pid=999)
                if with_finish:
                    capturelib.log_event(root, "worker-finished", id="OPP-lonely")
                code, out = run_doctor(["--json"])
                payload = json.loads(out)
                self.assertEqual(code, 0)
                rows = ledger_rows(payload)
                self.assertEqual(len(rows), 1)
                row = rows[0]
                if expect_warn:
                    self.assertEqual(row["status"], "WARN")
                    self.assertIn("OPP-lonely", row["detail"])
                else:
                    self.assertEqual(row["status"], "OK")


class NoHeadlessLatchTests(unittest.TestCase):
    def test_latch_set_warns_with_date(self):
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        latch_at = iso_ago(3600)
        set_no_headless_latch(project, at=latch_at)
        code, out = run_doctor(["--json"])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        rows = ledger_rows(payload)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["status"], "WARN")
        # The date portion (YYYY-MM-DD) must be legible in the detail, not
        # just an opaque "latch set" flag - D-10 exists specifically so the
        # latch's age is visible at a glance.
        date_part = latch_at[:10]
        self.assertIn(date_part, row["detail"])

    def test_malformed_latch_value_does_not_crash(self):
        """Adversarial where: `no_headless_at` is present (not None) but is
        not a parseable ISO string - a hand-edited or half-written state
        file. `capturelib.load_state` does not type-check this field, so a
        doctor row that slices or parses the raw value without going
        through a None-safe path would raise here. That must degrade to a
        non-crashing status, never propagate past `_run_checks`'s own bare
        except and collapse every other row into one generic FAIL."""
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        set_no_headless_latch(project, at="not-a-real-timestamp")
        code, out = run_doctor(["--json"])
        payload = json.loads(out)
        self.assertIn(code, (0, 1))
        self.assertNotEqual(code, 2)
        rows = ledger_rows(payload)
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0]["status"], "FAIL")
        self.assertNotIn("\n", rows[0]["detail"])


class FallbackFiringsTests(unittest.TestCase):
    def test_fallback_firings_reported_by_channel(self):
        """Adversarial where: zero fallback rows and a mix of `quiet` and
        `block` channel rows are two equivalence classes of the 'fallback
        firings by channel' behavior. A check that reports only a total
        count (dropping the channel breakdown the task promises) would
        still show numbers here but never distinguish `quiet` from
        `block`."""
        cases = [
            ("no fallback rows: clean", [], False),
            ("mixed quiet and block channels: both named", ["quiet", "quiet", "block"], True),
        ]
        for name, channels, expect_channels_named in cases:
            with self.subTest(name=name):
                project = make_project(self)
                with_project_env(self, project)
                build_complete_install(project)
                root = capture_root(project)
                for i, channel in enumerate(channels):
                    capturelib.log_event(root, "fallback-fired", id=f"OPP-fb-{i}", channel=channel)
                code, out = run_doctor(["--json"])
                payload = json.loads(out)
                self.assertEqual(code, 0)
                rows = ledger_rows(payload)
                self.assertEqual(len(rows), 1)
                row = rows[0]
                self.assertNotEqual(row["status"], "FAIL")
                if expect_channels_named:
                    detail_lower = row["detail"].lower()
                    self.assertIn("quiet", detail_lower)
                    self.assertIn("block", detail_lower)


class LastFailureReasonTests(unittest.TestCase):
    def test_last_failure_reason_is_most_recent_not_first(self):
        """Adversarial where: two failed spawns exist with different
        reasons in chronological order. A check that reports the first
        failure it encounters (e.g. keeping the earliest match while
        iterating instead of the latest) would show a stale reason; the row
        must reflect the SECOND, most recently appended reason, and must
        not still mention the first."""
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        root = capture_root(project)
        capturelib.log_event(root, "worker-started", id="OPP-first", pid=1)
        capturelib.log_event(root, "worker-failed", id="OPP-first", reason="lock-held")
        capturelib.log_event(root, "worker-started", id="OPP-second", pid=2)
        capturelib.log_event(root, "worker-failed", id="OPP-second", reason="no-headless")
        code, out = run_doctor(["--json"])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        rows = ledger_rows(payload)
        self.assertEqual(len(rows), 1)
        detail = rows[0]["detail"]
        self.assertIn("no-headless", detail)
        self.assertNotIn("lock-held", detail)


class LastThreeSpawnsFailedTests(unittest.TestCase):
    def _spawn(self, root, opp_id, succeed):
        capturelib.log_event(root, "worker-started", id=opp_id, pid=1)
        if succeed:
            capturelib.log_event(root, "worker-finished", id=opp_id, extracted="0 written")
        else:
            capturelib.log_event(root, "worker-failed", id=opp_id, reason="exit 1")

    def test_last_three_spawns_all_failed_boundary(self):
        """Adversarial where: 'the last three spawns all failed' is a
        threshold condition, not a loose 'several failures' heuristic.
        Exactly three failed spawns sits at the boundary and must WARN;
        two failed spawns is one below it and must not (too few to
        evaluate the rule at all, not a lesser degree of the same WARN);
        three spawns with one success is the same count but not ALL
        failed; four spawns where only the oldest failed must look at the
        actual most recent three, not any three, or it would wrongly WARN
        on a failure that already rolled out of the window."""
        cases = [
            ("exactly three, all failed: at the threshold", [False, False, False], True),
            ("two failed, one below threshold: too few to evaluate", [False, False], False),
            ("three total, one succeeded: not ALL failed", [False, True, False], False),
            ("four total, only the oldest failed: outside the window",
             [False, True, True, True], False),
        ]
        for name, outcomes, expect_warn in cases:
            with self.subTest(name=name):
                project = make_project(self)
                with_project_env(self, project)
                build_complete_install(project)
                root = capture_root(project)
                for i, succeed in enumerate(outcomes):
                    self._spawn(root, f"OPP-spawn-{i}", succeed)
                code, out = run_doctor(["--json"])
                payload = json.loads(out)
                self.assertEqual(code, 0)
                rows = ledger_rows(payload)
                self.assertEqual(len(rows), 1)
                row = rows[0]
                self.assertNotEqual(row["status"], "FAIL")
                self.assertEqual(row["status"], "WARN" if expect_warn else "OK")
                if expect_warn:
                    # The automated-verification bullet is explicit: WARN
                    # "with the reason", not a bare status flip.
                    self.assertIn("exit 1", row["detail"])


class NeverFailTests(unittest.TestCase):
    def test_multiple_warn_conditions_stay_warn_not_fail(self):
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        write_capture_config(project, worker_grace_seconds=10)
        root = capture_root(project)
        log_row(project, "worker-started", at=iso_ago(999), id="OPP-dead", pid=1)
        set_no_headless_latch(project, at=iso_ago(60))
        for i in range(3):
            capturelib.log_event(root, "worker-started", id=f"OPP-f{i}", pid=1)
            capturelib.log_event(root, "worker-failed", id=f"OPP-f{i}", reason="exit 1")
        code, out = run_doctor(["--json"])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        rows = ledger_rows(payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "WARN")

    def test_ledger_row_never_fail_alongside_a_genuine_unrelated_fail(self):
        """Adversarial where: a real install defect (missing plugin.yaml)
        and a broken worker ledger co-occur. The genuine FAIL must still
        move the exit code to 1, and the ledger row's own status must never
        be reported as FAIL even while every WARN condition it owns fires
        at once - D-10 rules the row can WARN but never FAIL, so it must
        never be the thing that turns a run red, and its own WARNs must
        never suppress the unrelated genuine FAIL."""
        project = make_project(self)
        with_project_env(self, project)
        write_lessons_catalog(project)
        write_settings(project, FULL_HOOK_EVENTS)
        write_hooks_json(project)
        write_full_cli(project)
        write_agents(project)
        write_skills(project)
        # plugin.yaml deliberately omitted - the genuine defect.
        write_capture_config(project, worker_grace_seconds=10)
        log_row(project, "worker-started", at=iso_ago(999), id="OPP-dead", pid=1)
        set_no_headless_latch(project, at=iso_ago(60))
        code, out = run_doctor(["--json"])
        payload = json.loads(out)
        self.assertEqual(code, 1)
        fail_rows = [row for row in payload["checks"] if row["status"] == "FAIL"]
        self.assertTrue(any(row["check"] == "plugin.yaml" for row in fail_rows))
        rows = ledger_rows(payload)
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0]["status"], "FAIL")


class LedgerReadFailureTests(unittest.TestCase):
    def test_read_log_failure_degrades_other_rows_survive(self):
        """Adversarial where: `capturelib.read_log` itself raises (a
        filesystem-level failure reading the ledger, distinct from a
        malformed JSON line, which `read_log` already swallows).
        Precedent: `_unit_candidates_check` wraps its own scan in a local
        try/except so one broken row degrades to WARN instead of reaching
        `_run_checks`'s bare except and collapsing every other check into
        one generic FAIL. The worker-ledger row must carry the same local
        guard, and the six baseline rows plus the unit-promotion row must
        come back unchanged."""
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        original = capturelib.read_log

        def boom(*_args, **_kwargs):
            raise OSError("disk gone")

        capturelib.read_log = boom
        try:
            code, out = run_doctor(["--json"])
        finally:
            capturelib.read_log = original
        payload = json.loads(out)
        self.assertEqual(code, 0)
        rows = ledger_rows(payload)
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0]["status"], "FAIL")
        baseline_statuses = {
            row["check"]: row["status"]
            for row in payload["checks"] if row["check"] in PRE_TASK_093_CHECKS
        }
        self.assertEqual(set(baseline_statuses), PRE_TASK_093_CHECKS)
        self.assertTrue(all(status == "OK" for status in baseline_statuses.values()))


class CorruptLogLineTests(unittest.TestCase):
    def test_one_corrupt_line_among_well_formed_rows_does_not_crash(self):
        """Adversarial where: the ledger file has one unparseable line
        (asymmetric malformation - one bad row among good ones, not a
        wholesale unreadable file) sitting next to an otherwise well-formed
        `worker-finished` row. `capturelib.read_log` already skips lines
        that fail to parse, so this exercises the doctor row's tolerance of
        whatever `read_log` hands back rather than a raw parse failure - a
        row built assuming every returned dict carries every expected key
        could still raise reading past the corrupt line's gap."""
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        root = capture_root(project)
        path = root / "tmp" / "capture-log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="") as handle:
            handle.write("{not valid json at all\n")
        capturelib.log_event(root, "worker-finished", id="OPP-ok")
        code, out = run_doctor(["--json"])
        payload = json.loads(out)
        self.assertEqual(code, 0)
        rows = ledger_rows(payload)
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0]["status"], "FAIL")


class WorkerLedgerJsonOutputTests(unittest.TestCase):
    def test_json_output_stays_one_parseable_object(self):
        """Adversarial where: every worker-ledger condition fires in the
        same run (unfinished-past-grace, the latch, a fallback row, a
        finish). `--json` exposes only check/status/detail/fix, so a
        multi-line summary block built for the table renderer, reused
        as-is for `detail`, would either break `json.loads` outright or
        smuggle embedded newlines into a field a downstream consumer
        expects to be single-line."""
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        write_capture_config(project, worker_grace_seconds=10)
        root = capture_root(project)
        log_row(project, "worker-started", at=iso_ago(999), id="OPP-dead", pid=1)
        set_no_headless_latch(project, at=iso_ago(60))
        capturelib.log_event(root, "fallback-fired", id="OPP-fb", channel="quiet")
        capturelib.log_event(root, "worker-finished", id="OPP-ok")
        code, out = run_doctor(["--json"])
        payload = json.loads(out)  # raises if the object is not one parseable blob
        self.assertIsInstance(payload, dict)
        self.assertIsInstance(payload["checks"], list)
        rows = ledger_rows(payload)
        self.assertEqual(len(rows), 1)
        self.assertNotIn("\n", rows[0]["detail"])


if __name__ == "__main__":
    unittest.main()


class HostChecksTests(unittest.TestCase):
    """Host-aware doctor rows: on a machine with dsh the materializations
    exist and match the plugin version and the capture posture is named;
    on a machine without dsh the project gets a roster line and nothing
    dsh-shaped. Detection is pinned so the suite is machine-independent."""

    PLUGIN_SRC = Path(__file__).resolve().parents[2]

    def _pin_dsh(self, present):
        import hostlib
        self.addCleanup(setattr, hostlib, "dsh_available", hostlib.dsh_available)
        hostlib.dsh_available = lambda: present

    def _dsh_home(self):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        with_env(self, "DSH_HOME", str(home))
        return home

    def _dsh_project(self, version="0.20.0"):
        project = make_project(self)
        self._pin_dsh(True)
        write_plugin_yaml(project, version=version)
        return project

    def test_missing_dsh_materializations_fail(self):
        self._dsh_home()
        project = self._dsh_project()
        checks = doctor._host_checks(project / ".compass", project)
        host = next(c for c in checks if c.name == "install for each tool")
        self.assertEqual(host.status, "FAIL")
        self.assertIn(".dsh/hooks.json", host.detail)

    def test_bundle_version_skew_fails(self):
        home = self._dsh_home()
        project = self._dsh_project()
        import hostlib
        hostlib.materialize_dsh_hooks(project, self.PLUGIN_SRC / "hooks" / "hooks.json")
        hostlib.materialize_dsh_skills(project, self.PLUGIN_SRC / "skills")
        hostlib.materialize_dsh_instructions(
            project, self.PLUGIN_SRC / "templates" / "rules")
        bundle = home / "compass-bundle"
        bundle.mkdir(parents=True)
        (bundle / "package.json").write_text(
            '{"name": "compass-dsh-bundle", "version": "0.1.0"}', encoding="utf-8")
        checks = doctor._host_checks(project / ".compass", project)
        host = next(c for c in checks if c.name == "install for each tool")
        self.assertEqual(host.status, "FAIL")
        self.assertIn("skew", host.detail)

    def test_clean_dual_host_passes_and_names_capture_posture(self):
        if not (self.PLUGIN_SRC / ".claude-plugin" / "plugin.json").is_file():
            self.skipTest(
                "plugin source tree absent: bundle generation needs it, and a "
                "vendored .claude/ install does not carry it")
        home = self._dsh_home()
        project = self._dsh_project()
        import hostlib
        from commands import self_update
        real_version = json.loads(
            (self.PLUGIN_SRC / ".claude-plugin" / "plugin.json").read_text(
                encoding="utf-8"))["version"]
        p = project / ".compass" / "meta" / "plugin.yaml"
        p.write_text(
            f"plugin:\n  name: compass\n  version: {real_version}\n",
            encoding="utf-8")
        hostlib.materialize_dsh_hooks(project, self.PLUGIN_SRC / "hooks" / "hooks.json")
        hostlib.materialize_dsh_skills(project, self.PLUGIN_SRC / "skills")
        hostlib.materialize_dsh_bundle(home, self.PLUGIN_SRC)
        hostlib.materialize_dsh_instructions(
            project, self.PLUGIN_SRC / "templates" / "rules")
        checks = doctor._host_checks(project / ".compass", project)
        host = next(c for c in checks if c.name == "install for each tool")
        self.assertEqual(host.status, "OK", host.detail)
        posture = next(c for c in checks if c.name == "how lesson recording is set up")
        self.assertIn(posture.status, ("OK", "WARN"))

    def test_machine_without_dsh_reports_roster_without_dsh_rows(self):
        self._pin_dsh(False)
        project = make_project(self)
        write_plugin_yaml(project)
        checks = doctor._host_checks(project / ".compass", project)
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0].status, "OK")
        self.assertIn("claude-code", checks[0].detail)


# ---------------------------------------------------------------------------
# Session retention row (PLAN-020 TASK-141)
# ---------------------------------------------------------------------------

RETENTION_KEY = "cleanupPeriodDays"
RETENTION_FIX = 'add "cleanupPeriodDays": 3650 to ~/.claude/settings.json'
RETENTION_FIX_COMMAND = "compass retention --set 3650"


def set_user_retention(content):
    """Rewrite the isolated user settings. `None` removes the file; a dict is
    written as JSON; a string is written verbatim."""
    path = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "settings.json"
    if content is None:
        if path.exists():
            path.unlink()
        return path
    text = content if isinstance(content, str) else json.dumps(content)
    path.write_text(text, encoding="utf-8")
    return path


def retention_row(payload):
    rows = [row for row in payload["checks"] if row["check"] == "session retention"]
    assert len(rows) == 1, f"expected one session retention row, got {len(rows)}"
    return rows[0]


class SessionRetentionRowTests(unittest.TestCase):
    def setUp(self):
        self.project = make_project(self)
        with_project_env(self, self.project)
        build_complete_install(self.project)

    def row(self):
        code, out = run_doctor(["--json"])
        return code, retention_row(json.loads(out))

    def test_status_follows_the_thirty_day_boundary(self):
        """Adversarial where: the row WARNs on unset and on 30 or less, and is
        OK only above 30. 30 and 31 are the exact boundary; an `< 30` instead
        of `<= 30` check passes 30 as safe, and a reader that treats a
        missing key or a user file holding only other keys as a default
        'long enough' value reports OK for an unset setting."""
        rows = [
            ("no user settings file", None, "WARN"),
            ("user file without the key", {"model": "opus"}, "WARN"),
            ("1", {RETENTION_KEY: 1}, "WARN"),
            ("29", {RETENTION_KEY: 29}, "WARN"),
            ("30", {RETENTION_KEY: 30}, "WARN"),
            ("31", {RETENTION_KEY: 31}, "OK"),
            ("90", {RETENTION_KEY: 90}, "OK"),
            ("3650", {RETENTION_KEY: 3650}, "OK"),
        ]
        for name, content, expected in rows:
            with self.subTest(name=name):
                set_user_retention(content)
                code, row = self.row()
                self.assertEqual(row["status"], expected, row["detail"])
                self.assertEqual(code, 0)
                self.assertNotIn("\n", row["detail"])

    def test_effective_value_comes_from_the_layer_that_wins(self):
        """Adversarial where: the row judges the effective setting (local,
        then project, then user), not the user file alone. A short project or
        local value must WARN even over a long user value, and a long project
        value must make the row OK even over a user value of 30."""
        rows = [
            ("user 30, project 3650", {RETENTION_KEY: 30}, {RETENTION_KEY: 3650}, None, "OK"),
            ("user 3650, project 7", {RETENTION_KEY: 3650}, {RETENTION_KEY: 7}, None, "WARN"),
            ("user 3650, local 7", {RETENTION_KEY: 3650}, None, {RETENTION_KEY: 7}, "WARN"),
            ("user 3650, project 7, local 90", {RETENTION_KEY: 3650}, {RETENTION_KEY: 7},
             {RETENTION_KEY: 90}, "OK"),
            ("user 30, project file without the key", {RETENTION_KEY: 30}, {"model": "x"}, None, "WARN"),
            ("user unset, local 3650", None, None, {RETENTION_KEY: 3650}, "OK"),
        ]
        claude_dir = self.project / ".claude"
        for name, user, project, local, expected in rows:
            with self.subTest(name=name):
                for f in (claude_dir / "settings.local.json",):
                    if f.exists():
                        f.unlink()
                set_user_retention(user)
                # settings.json also carries the installed hooks; merge the key in.
                project_path = claude_dir / "settings.json"
                base = json.loads(project_path.read_text(encoding="utf-8"))
                base.pop(RETENTION_KEY, None)
                base.update(project or {})
                project_path.write_text(json.dumps(base), encoding="utf-8")
                if local is not None:
                    (claude_dir / "settings.local.json").write_text(
                        json.dumps(local), encoding="utf-8")
                _code, row = self.row()
                self.assertEqual(row["status"], expected, row["detail"])

    def test_warn_names_the_fix_and_ok_does_not(self):
        """Adversarial where: a WARN row must carry the concrete fix, both the
        settings line to add and the command that does it, in the JSON `fix`
        field and in the table's `fixes:` section. An OK row carries no fix,
        so a healthy install shows no stray remediation."""
        for name, content in (("unset", None), ("exactly 30", {RETENTION_KEY: 30})):
            with self.subTest(name=name):
                set_user_retention(content)
                _code, row = self.row()
                self.assertEqual(row["status"], "WARN")
                self.assertIn(RETENTION_FIX, row["fix"])
                self.assertIn(RETENTION_FIX_COMMAND, row["fix"])
                _code, table = run_doctor()
                self.assertIn("fixes:", table)
                self.assertIn(RETENTION_FIX, table)
        set_user_retention({RETENTION_KEY: 31})
        _code, row = self.row()
        self.assertEqual(row["status"], "OK")
        self.assertNotIn("fix", row)

    def test_warn_is_advisory_and_doctor_writes_no_settings(self):
        """Adversarial where: an unset retention is a warning, never a
        failure: a complete install still exits 0. Doctor is read-only, so the
        user's settings file must not be created or changed by the check, and
        the isolated config dir must stay exactly as the test left it."""
        path = set_user_retention(None)
        config = path.parent
        code, row = self.row()
        self.assertEqual(row["status"], "WARN")
        self.assertEqual(code, 0)
        self.assertEqual(list(config.iterdir()), [])
        path = set_user_retention({"model": "opus", RETENTION_KEY: 30})
        before = path.read_bytes()
        run_doctor(["--json"])
        self.assertEqual(path.read_bytes(), before)

    def test_unparseable_user_settings_degrade_to_a_row_not_a_crash(self):
        """Adversarial where: a user settings file that does not parse must
        not collapse doctor into its one generic 'internal error' FAIL row.
        Every other row is still produced (12 in total), the retention row is
        present on a single line and is not a FAIL, and the exit code stays
        0 for an otherwise complete install."""
        for name, content in (("not json", "{oops"), ("array", "[1, 2]"), ("empty", "")):
            with self.subTest(name=name):
                set_user_retention(content)
                code, out = run_doctor(["--json"])
                payload = json.loads(out)
                self.assertEqual(len(payload["checks"]), 15)
                row = retention_row(payload)
                self.assertNotEqual(row["status"], "FAIL")
                self.assertNotIn("\n", row["detail"])
                self.assertTrue(row["detail"])
                self.assertEqual(code, 0)


class SessionRetentionPostBuildTests(unittest.TestCase):
    def setUp(self):
        self.project = make_project(self)
        with_project_env(self, self.project)
        build_complete_install(self.project)

    def row(self):
        code, out = run_doctor(["--json"])
        return code, retention_row(json.loads(out))

    def test_bom_and_crlf_user_settings_are_read(self):
        """Adversarial where: a user settings file saved with a UTF-8 BOM and
        CRLF line endings that sets a long retention must read as OK. A
        reader decoding with plain `utf-8` fails on the BOM and reports a
        parse WARN, telling the user to repair a file that is fine."""
        path = set_user_retention(None)
        path.write_bytes(b'\xef\xbb\xbf{\r\n  "cleanupPeriodDays": 3650\r\n}\r\n')
        code, row = self.row()
        self.assertEqual(row["status"], "OK", row["detail"])
        self.assertEqual(code, 0)

    def test_non_integer_values_count_as_unset(self):
        """Adversarial where: a string, bool, float or null `cleanupPeriodDays`
        is not a day count. `true` read as the int 1, or the string "3650"
        read as long enough, would turn a misconfigured setting into an OK
        or a '1 day' message; each must be the unset WARN."""
        rows = [
            ("string", '{"cleanupPeriodDays": "3650"}'),
            ("bool true", '{"cleanupPeriodDays": true}'),
            ("float", '{"cleanupPeriodDays": 3650.5}'),
            ("null", '{"cleanupPeriodDays": null}'),
        ]
        for name, content in rows:
            with self.subTest(name=name):
                set_user_retention(content)
                code, row = self.row()
                self.assertEqual(row["status"], "WARN")
                self.assertIn("unset", row["detail"])
                self.assertEqual(code, 0)

    def test_zero_and_negative_values_warn(self):
        """Adversarial where: 0 and negative day counts are integers at or
        below 30 and must WARN with the value named. A truthiness check
        (`if days`) would treat 0 as unset or skip the layer."""
        for value in (0, -1):
            with self.subTest(value=value):
                set_user_retention({RETENTION_KEY: value})
                _code, row = self.row()
                self.assertEqual(row["status"], "WARN")
                self.assertIn(str(value), row["detail"])

    def test_broken_project_or_local_settings_never_fail_the_row(self):
        """Adversarial where: a malformed project or local settings file
        beside a valid user file must degrade the row to a single-line
        non-FAIL result, never crash doctor into its generic internal-error
        row. Asymmetric: only one of three layers is broken."""
        set_user_retention({RETENTION_KEY: 3650})
        local = self.project / ".claude" / "settings.local.json"
        for name, content in (("not json", "{oops"), ("empty", "")):
            with self.subTest(name=name):
                local.write_text(content, encoding="utf-8")
                code, out = run_doctor(["--json"])
                payload = json.loads(out)
                self.assertEqual(len(payload["checks"]), 15)
                row = retention_row(payload)
                self.assertNotEqual(row["status"], "FAIL")
                self.assertNotIn("\n", row["detail"])
                self.assertEqual(code, 0)


class NonObjectSettingsTests(unittest.TestCase):
    def test_array_settings_file_is_unreadable_for_the_hook_row_only(self):
        """Adversarial where: a settings file whose JSON is an array has no
        `hooks` key to read. The hook row must name the file and keep every
        other row (12 in total) instead of collapsing doctor into one
        'internal error' FAIL row. Asymmetric: the project settings.json is
        valid and registers the hooks; only settings.local.json is bad."""
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        (project / ".claude" / "settings.local.json").write_text("[1]", encoding="utf-8")
        code, out = run_doctor(["--json"])
        payload = json.loads(out)
        checks = payload["checks"]
        self.assertEqual(len(checks), 15)
        self.assertFalse([c for c in checks if c["check"] == "doctor"])
        self.assertNotIn("internal error", out)
        hook_row = [c for c in checks if c["check"] == "automatic step registration"][0]
        self.assertIn("settings.local.json", hook_row["detail"])
        self.assertEqual(code, 0)

    def test_array_settings_file_naming_survives_when_hooks_are_missing(self):
        """Adversarial where: when the only settings file is an array, the
        hook row FAILs (nothing registered) and still names the bad file, so
        the reader learns why instead of seeing a bare missing-registration
        message."""
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        (project / ".claude" / "settings.json").write_text("[1]", encoding="utf-8")
        code, out = run_doctor(["--json"])
        checks = json.loads(out)["checks"]
        self.assertFalse([c for c in checks if c["check"] == "doctor"])
        hook_row = [c for c in checks if c["check"] == "automatic step registration"][0]
        self.assertEqual(hook_row["status"], "FAIL")
        self.assertIn("settings.json", hook_row["detail"])
        self.assertEqual(code, 1)


class WrongShapedHooksEntryTests(unittest.TestCase):
    def test_non_iterable_hook_entries_do_not_collapse_doctor(self):
        """Adversarial where: a settings file that is a JSON object but whose
        `hooks.<Event>` value (or a group's inner `hooks`) is a number or a
        boolean instead of a list must be reported on the hook row, not crash
        the whole run into a single 'internal error' FAIL row that hides every
        other check. Rows are the wrong-shaped values at each nesting level."""
        rows = {
            "event value is an int": '{"hooks": {"Stop": 5}}',
            "event value is a bool": '{"hooks": {"PreToolUse": true}}',
            "group hooks is an int": '{"hooks": {"Stop": [{"hooks": 5}]}}',
        }
        for name, content in rows.items():
            with self.subTest(name=name):
                project = make_project(self)
                with_project_env(self, project)
                build_complete_install(project)
                (project / ".claude" / "settings.local.json").write_text(content, encoding="utf-8")
                code, out = run_doctor(["--json"])
                checks = json.loads(out)["checks"]
                self.assertFalse([c for c in checks if c["check"] == "doctor"], out[:300])
                self.assertEqual(len([c for c in checks if c["check"] == "automatic step registration"]), 1)


class BomSettingsHookTests(unittest.TestCase):
    def test_bom_project_settings_still_register_hooks(self):
        """Adversarial where: a project settings.json saved with a UTF-8 BOM
        is valid to Claude Code. The hook row must read it, not report 'not
        valid JSON' for a file that is fine; a reader decoding as plain
        utf-8 fails on the BOM."""
        project = make_project(self)
        with_project_env(self, project)
        build_complete_install(project)
        path = project / ".claude" / "settings.json"
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        code, out = run_doctor(["--json"])
        checks = json.loads(out)["checks"]
        hook_row = [c for c in checks if c["check"] == "automatic step registration"][0]
        self.assertEqual(hook_row["status"], "OK", hook_row["detail"])
        self.assertNotIn("not valid JSON", hook_row["detail"])
        self.assertEqual(code, 0)
