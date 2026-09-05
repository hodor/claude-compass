"""Tests for the host seam: the roster in plugin.yaml and the dsh
hooks-file materializer.

Adversarial classes: a hostless plugin.yaml must behave exactly as today
(claude-code only, no .dsh/ artifacts created); the generated dsh hooks
file must carry no sh-dialect syntax dsh's PowerShell executor would choke
on, no events dsh's bridge does not parse, and no `if` fields; and
regeneration must be idempotent.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hostlib  # noqa: E402


def make_project(test_case, plugin_yaml=None):
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    (tmp / ".compass" / "meta").mkdir(parents=True)
    if plugin_yaml is not None:
        (tmp / ".compass" / "meta" / "plugin.yaml").write_text(
            plugin_yaml, encoding="utf-8")
    return tmp


MANIFEST = Path(__file__).resolve().parents[2] / "hooks" / "hooks.json"


class ReadHostsTests(unittest.TestCase):
    def test_missing_plugin_yaml_defaults_to_claude_code(self):
        project = make_project(self)
        self.assertEqual(hostlib.read_hosts(project / ".compass"), ["claude-code"])

    def test_hostless_plugin_yaml_defaults_to_claude_code(self):
        project = make_project(self, "source: F:/x\nversion: 0.18.4\n")
        self.assertEqual(hostlib.read_hosts(project / ".compass"), ["claude-code"])

    def test_roster_parses_inline_list(self):
        project = make_project(
            self, "source: F:/x\nversion: 0.18.4\nhosts: [claude-code, dsh]\n")
        self.assertEqual(
            hostlib.read_hosts(project / ".compass"), ["claude-code", "dsh"])

    def test_roster_parses_nested_under_plugin_mapping(self):
        # The shape setup actually writes: fields indented under `plugin:`.
        project = make_project(
            self,
            "plugin:\n  name: compass\n  version: 0.18.4\n"
            "  hosts: [claude-code, dsh]\n")
        self.assertEqual(
            hostlib.read_hosts(project / ".compass"), ["claude-code", "dsh"])

    def test_unknown_host_names_survive_verbatim(self):
        # A newer roster read by an older CLI must not be silently dropped.
        project = make_project(
            self, "hosts: [claude-code, kimi-code]\n")
        self.assertIn("kimi-code", hostlib.read_hosts(project / ".compass"))


class MaterializeDshHooksTests(unittest.TestCase):
    def _materialize(self):
        project = make_project(self)
        hostlib.materialize_dsh_hooks(project, MANIFEST)
        out = project / ".dsh" / "hooks.json"
        self.assertTrue(out.is_file())
        return json.loads(out.read_text(encoding="utf-8")), project

    def test_commands_are_dialect_neutral(self):
        data, _ = self._materialize()
        for groups in data["hooks"].values():
            for g in groups:
                for h in g["hooks"]:
                    cmd = h["command"]
                    self.assertNotIn("command -v", cmd)
                    self.assertNotIn("; then", cmd)
                    self.assertNotIn("fi", cmd.split()[-1])
                    self.assertTrue(cmd.startswith('python "${CLAUDE_PROJECT_DIR}'), cmd)

    def test_no_if_fields_and_no_unsupported_events(self):
        data, _ = self._materialize()
        self.assertNotIn("TeammateIdle", data["hooks"])
        for groups in data["hooks"].values():
            for g in groups:
                for h in g["hooks"]:
                    self.assertNotIn("if", h)

    def test_posttooluse_matchers_cover_dsh_tool_names(self):
        data, _ = self._materialize()
        matchers = "|".join(
            g.get("matcher", "") for g in data["hooks"]["PostToolUse"])
        self.assertIn("write", matchers)
        self.assertIn("edit", matchers)

    def test_sessionstart_startup_matcher_survives(self):
        data, _ = self._materialize()
        self.assertIn(
            "startup",
            [g.get("matcher") for g in data["hooks"]["SessionStart"]])

    def test_regeneration_is_idempotent(self):
        data, project = self._materialize()
        hostlib.materialize_dsh_hooks(project, MANIFEST)
        again = json.loads(
            (project / ".dsh" / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(data, again)


class ApplyHostLoopTests(unittest.TestCase):
    """`self_update._apply` refreshes every rostered host in one run."""

    def _src(self):
        src = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, src, True)
        (src / "templates" / "agents").mkdir(parents=True)
        (src / "templates" / "agents" / "builder.md").write_text("agent", encoding="utf-8")
        (src / "templates" / "rules").mkdir(parents=True)
        (src / "skills" / "s").mkdir(parents=True)
        (src / "skills" / "s" / "SKILL.md").write_text("skill", encoding="utf-8")
        (src / "cli").mkdir()
        (src / "cli" / "compass").write_text("#!", encoding="utf-8")
        (src / "hooks").mkdir()
        shutil.copy2(MANIFEST, src / "hooks" / "hooks.json")
        return src

    def test_dual_roster_gets_both_materializations_in_one_apply(self):
        from commands import self_update
        project = make_project(
            self, "source: F:/x\nversion: 0.18.4\nhosts: [claude-code, dsh]\n")
        self_update._apply(self._src(), project, apply_models=False)
        self.assertTrue((project / ".claude" / "agents" / "builder.md").is_file())
        self.assertTrue((project / ".dsh" / "hooks.json").is_file())

    def test_default_roster_behaves_exactly_as_today(self):
        from commands import self_update
        project = make_project(self, "source: F:/x\nversion: 0.18.4\n")
        self_update._apply(self._src(), project, apply_models=False)
        self.assertTrue((project / ".claude" / "agents" / "builder.md").is_file())
        self.assertFalse((project / ".dsh").exists())


if __name__ == "__main__":
    unittest.main()
