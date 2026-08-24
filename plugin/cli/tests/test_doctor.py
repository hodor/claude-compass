"""Tests for `compass doctor`, the install-drift diagnostic. Adversarial:
most cases build a specific partial install (missing plugin.yaml, an
unregistered hooks.json, a hole in the CLI's command modules, a v0.2.0-shaped
install with skills but no hooks anywhere) and assert doctor names the
defect and exits 1, never 2, and never raises."""

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

from commands import doctor  # noqa: E402


def make_project(test_case):
    """A bare project dir with an empty `.compass/`, nothing under `.claude/`."""
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    (tmp / ".compass").mkdir()
    return tmp


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
        self.assertIn("hook registration", out)


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
    "hook registration",
    "CLI completeness",
    "agents",
    "skills",
    "lessons-catalog.yaml",
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
        self.assertEqual(len(payload["checks"]), 7)
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
        self.assertEqual(len(payload["checks"]), 7)
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
        self.assertEqual(len(payload["checks"]), 7)
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


if __name__ == "__main__":
    unittest.main()
