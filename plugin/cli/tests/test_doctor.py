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


if __name__ == "__main__":
    unittest.main()
