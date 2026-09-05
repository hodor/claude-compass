"""Tests for `compass self-update` (ADR-015).

Adversarial classes: the sha gate must prevent clones, the throttle must
prevent network entirely, local-source mode must never touch the network,
the settings merge must preserve user-owned entries and stay idempotent,
and no failure path may return nonzero or write a partial install.
"""

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

from commands import self_update  # noqa: E402


PLUGIN_JSON = {"name": "compass", "version": "9.9.9"}

MANIFEST = {
    "hooks": {
        "PostToolUse": [
            {
                "matcher": "Write",
                "hooks": [
                    {
                        "type": "command",
                        "if": "Write(.compass/**/*.md)",
                        "timeout": 30,
                        "command": "python compass sync --hook",
                    }
                ],
            },
            {
                "matcher": "Edit",
                "hooks": [
                    {
                        "type": "command",
                        "if": "Edit(.compass/**/*.md)",
                        "timeout": 30,
                        "command": "python compass sync --hook",
                    }
                ],
            },
        ],
        "SessionStart": [
            {
                "matcher": "startup",
                "hooks": [
                    {
                        "type": "command",
                        "timeout": 60,
                        "command": "python compass self-update --hook",
                    }
                ],
            }
        ],
    }
}


def make_plugin_tree(root, version="9.9.9"):
    """Build a minimal plugin source tree under `root`."""
    (root / ".claude-plugin").mkdir(parents=True)
    data = dict(PLUGIN_JSON, version=version)
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    (root / "templates" / "agents").mkdir(parents=True)
    (root / "templates" / "agents" / "builder.md").write_text("agent", encoding="utf-8")
    (root / "templates" / "rules").mkdir(parents=True)
    (root / "templates" / "rules" / "r.md").write_text("rule", encoding="utf-8")
    (root / "skills" / "sweeping").mkdir(parents=True)
    (root / "skills" / "sweeping" / "SKILL.md").write_text("skill", encoding="utf-8")
    (root / "cli" / "commands").mkdir(parents=True)
    (root / "cli" / "compass").write_text("#!launcher", encoding="utf-8")
    (root / "cli" / "commands" / "x.py").write_text("x = 1", encoding="utf-8")
    (root / "hooks").mkdir(parents=True)
    (root / "hooks" / "hooks.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    return root


PLUGIN_YAML = """plugin:
  name: compass
  version: 0.9.0
  source: {source}
  repository: https://github.com/example/compass
  installed_at: 2026-08-01
  installed_mode: update
  notes: |
    keep me verbatim
"""


class SelfUpdateFixture(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.project = tmp / "project"
        self.vault = self.project / ".compass"
        (self.vault / "meta").mkdir(parents=True)
        (self.vault / "tmp").mkdir()
        (self.project / ".claude").mkdir()
        # an external source dir, outside the project root
        self.external_src = make_plugin_tree(tmp / "external-plugin")
        self.write_plugin_yaml(source=str(tmp / "somewhere-else"))
        # network tripwires: tests that must not touch the network get these
        self.addCleanup(setattr, self_update, "_ls_remote", self_update._ls_remote)
        self.addCleanup(setattr, self_update, "_clone", self_update._clone)

    def write_plugin_yaml(self, source, commit=None):
        text = PLUGIN_YAML.format(source=source)
        if commit:
            text = text.replace(
                "  version: 0.9.0", f"  version: 0.9.0\n  commit: {commit}"
            )
        (self.vault / "meta" / "plugin.yaml").write_text(text, encoding="utf-8")

    def forbid_network(self):
        def boom(*a, **k):
            raise AssertionError("network path must not run")

        self_update._ls_remote = boom
        self_update._clone = boom

    def fake_remote(self, sha="abc123"):
        src = self.external_src

        self_update._ls_remote = lambda repo, timeout=5: sha

        def clone(repo, dest):
            shutil.copytree(src, Path(dest) / "clone" / "plugin")
            return True

        self_update._clone = clone

    def perform(self, **kw):
        kw.setdefault("apply_models", False)
        return self_update.perform(self.vault, **kw)

    def plugin_yaml(self):
        return (self.vault / "meta" / "plugin.yaml").read_text(encoding="utf-8")


class GateTests(SelfUpdateFixture):
    def test_throttle_skips_without_network(self):
        self.forbid_network()
        (self.vault / "tmp" / ".self-update-check").write_text("", encoding="utf-8")
        result = self.perform()
        self.assertEqual(result["status"], "throttled")

    def test_force_bypasses_throttle(self):
        self.fake_remote()
        (self.vault / "tmp" / ".self-update-check").write_text("", encoding="utf-8")
        result = self.perform(force=True)
        self.assertEqual(result["status"], "updated")

    def test_matching_sha_is_current_and_never_clones(self):
        self.write_plugin_yaml(source="nowhere", commit="abc123")
        self_update._ls_remote = lambda repo, timeout=5: "abc123"

        def boom(*a, **k):
            raise AssertionError("clone must not run when sha matches")

        self_update._clone = boom
        result = self.perform()
        self.assertEqual(result["status"], "current")

    def test_offline_is_a_silent_skip(self):
        self_update._ls_remote = lambda repo, timeout=5: None
        result = self.perform()
        self.assertEqual(result["status"], "offline")
        self.assertFalse((self.project / ".claude" / "agents").exists())

    def test_missing_plugin_yaml_is_a_silent_skip(self):
        (self.vault / "meta" / "plugin.yaml").unlink()
        self.forbid_network()
        result = self.perform()
        self.assertEqual(result["status"], "no-config")


class RemoteUpdateTests(SelfUpdateFixture):
    def test_remote_update_applies_and_records(self):
        self.fake_remote(sha="abc123")
        result = self.perform()
        self.assertEqual(result["status"], "updated")
        claude = self.project / ".claude"
        self.assertEqual(
            (claude / "agents" / "builder.md").read_text(encoding="utf-8"), "agent"
        )
        self.assertEqual(
            (claude / "rules" / "r.md").read_text(encoding="utf-8"), "rule"
        )
        self.assertEqual(
            (claude / "skills" / "sweeping" / "SKILL.md").read_text(encoding="utf-8"),
            "skill",
        )
        self.assertTrue((claude / "cli" / "commands" / "x.py").is_file())
        self.assertTrue((claude / "hooks" / "hooks.json").is_file())
        text = self.plugin_yaml()
        self.assertIn("version: 9.9.9", text)
        self.assertIn("commit: abc123", text)
        self.assertIn("installed_mode: auto-update", text)
        self.assertIn("keep me verbatim", text)

    def test_update_appends_a_log_row(self):
        self.fake_remote()
        self.perform()
        log = (self.vault / "tmp" / "self-update.log").read_text(encoding="utf-8")
        self.assertIn("0.9.0 -> 9.9.9", log)

    def test_retired_skill_removed_user_skill_kept(self):
        (self.project / ".claude" / "skills" / "bootstrap").mkdir(parents=True)
        (self.project / ".claude" / "skills" / "my-own").mkdir(parents=True)
        (self.project / ".claude" / "skills" / "my-own" / "SKILL.md").write_text(
            "mine", encoding="utf-8"
        )
        self.fake_remote()
        self.perform()
        self.assertFalse((self.project / ".claude" / "skills" / "bootstrap").exists())
        self.assertTrue(
            (self.project / ".claude" / "skills" / "my-own" / "SKILL.md").is_file()
        )

    def test_commands_copied_and_tree_skill_retired(self):
        commands_src = self.external_src / "templates" / "commands"
        commands_src.mkdir(parents=True, exist_ok=True)
        (commands_src / "tree.md").write_text("run it", encoding="utf-8")
        (self.project / ".claude" / "skills" / "tree").mkdir(parents=True)
        self.fake_remote()
        self.perform()
        self.assertEqual(
            (self.project / ".claude" / "commands" / "tree.md").read_text(
                encoding="utf-8"
            ),
            "run it",
        )
        self.assertFalse((self.project / ".claude" / "skills" / "tree").exists())

    def test_bad_clone_leaves_install_untouched(self):
        self_update._ls_remote = lambda repo, timeout=5: "abc123"

        def clone(repo, dest):
            (Path(dest) / "clone" / "plugin").mkdir(parents=True)  # no plugin.json
            return True

        self_update._clone = clone
        result = self.perform()
        self.assertEqual(result["status"], "bad-source")
        self.assertFalse((self.project / ".claude" / "agents").exists())
        self.assertIn("version: 0.9.0", self.plugin_yaml())


class LocalSourceTests(SelfUpdateFixture):
    def setUp(self):
        super().setUp()
        self.local_src = make_plugin_tree(self.project / "plugin", version="0.9.0")
        self.write_plugin_yaml(source=str(self.project / "plugin"))

    def test_local_mode_applies_without_network(self):
        self.forbid_network()
        result = self.perform()
        self.assertEqual(result["status"], "applied-local")
        self.assertTrue(
            (self.project / ".claude" / "agents" / "builder.md").is_file()
        )

    def test_local_mode_same_version_is_silent(self):
        self.forbid_network()
        result = self.perform()
        self.assertIsNone(result.get("notice"))

    def test_local_mode_version_bump_notices(self):
        make_plugin_tree(self.project / "plugin2", version="1.0.0")
        shutil.rmtree(self.project / "plugin")
        (self.project / "plugin2").rename(self.project / "plugin")
        self.forbid_network()
        result = self.perform()
        self.assertIn("0.9.0 -> 1.0.0", result["notice"])


class SettingsMergeTests(SelfUpdateFixture):
    def settings(self):
        return json.loads(
            (self.project / ".claude" / "settings.json").read_text(encoding="utf-8")
        )

    def test_merge_preserves_user_entries_and_collapses_posttooluse(self):
        (self.project / ".claude" / "settings.json").write_text(
            json.dumps(
                {
                    "permissions": {"allow": ["Bash(ls:*)"]},
                    "hooks": {
                        "PostToolUse": [
                            {
                                "matcher": "Write",
                                "hooks": [{"type": "command", "command": "my-own-hook"}],
                            },
                            {
                                "matcher": "Write",
                                "hooks": [
                                    {"type": "command", "command": "old compass sync"}
                                ],
                            },
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        self.fake_remote()
        self.perform()
        settings = self.settings()
        self.assertEqual(settings["permissions"], {"allow": ["Bash(ls:*)"]})
        post = settings["hooks"]["PostToolUse"]
        commands = [h["command"] for g in post for h in g["hooks"]]
        self.assertIn("my-own-hook", commands)
        self.assertNotIn("old compass sync", commands)
        compass_groups = [
            g
            for g in post
            if any("compass" in h["command"] for h in g["hooks"])
        ]
        self.assertEqual(len(compass_groups), 1)
        # dsh matches on its lowercase tool names; the extra alternatives are
        # inert under Claude Code, so one manifest stays legal on both hosts.
        self.assertEqual(compass_groups[0]["matcher"], "Write|Edit|MultiEdit|write|edit")
        for g in post:
            for h in g["hooks"]:
                self.assertNotIn("if", h)

    def test_merge_is_idempotent(self):
        self.fake_remote()
        self.perform()
        first = self.settings()
        self.fake_remote()
        self.perform(force=True)
        self.assertEqual(self.settings(), first)


class NeverBlocksTests(SelfUpdateFixture):
    def run_cli(self, args):
        cwd = os.getcwd()
        os.chdir(self.project)
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = self_update.run(args)
        finally:
            os.chdir(cwd)
        return code, buf.getvalue()

    def test_exit_zero_and_silent_when_current(self):
        self.write_plugin_yaml(source="nowhere", commit="abc123")
        self_update._ls_remote = lambda repo, timeout=5: "abc123"
        code, out = self.run_cli([])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_exit_zero_on_corrupt_plugin_yaml(self):
        (self.vault / "meta" / "plugin.yaml").write_text(
            "not: [valid: yaml: at all", encoding="utf-8"
        )
        self.forbid_network()
        code, _ = self.run_cli([])
        self.assertEqual(code, 0)

    def test_prints_one_line_on_update(self):
        self.fake_remote()
        code, out = self.run_cli(["--force"])
        self.assertEqual(code, 0)
        self.assertIn("0.9.0 -> 9.9.9", out)
        self.assertEqual(len(out.strip().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()


class NormalizeFlatSpecsTests(SelfUpdateFixture):
    """A spec is a file until its second member: update flattens any folder
    spec holding only its own index, logs the correction, and leaves folder
    specs with children, domains, and everything non-spec untouched."""

    def setUp(self):
        super().setUp()
        self.local_src = make_plugin_tree(self.project / "plugin", version="9.9.9")
        self.write_plugin_yaml(source=str(self.project / "plugin"))

    def _spec(self, title):
        return (
            f"---\ntitle: {title}\ntype: spec\nstatus: approved\narea: w\n"
            f"tags: [x]\nchildren_count: 0\nsizing_id: sz-2026-08-30-9\n"
            f"created: 2026-08-30\nupdated: 2026-08-30\n---\n\nbody\n"
        )

    def _domain(self, title):
        return (
            f"---\ntitle: {title}\ntype: domain\nstatus: active\ntags: []\n"
            f"summary: \"s\"\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\n\n"
            f"## Scope\n\nClass here: things\n"
        )

    def _write(self, rel, body):
        path = self.vault / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def test_lone_index_folder_spec_flattens_with_correction_row(self):
        self._write("specs/SPEC-001-lone/index.md", self._spec("Lone"))
        self.forbid_network()
        self.perform()
        self.assertFalse((self.vault / "specs" / "SPEC-001-lone").exists())
        flat = self.vault / "specs" / "SPEC-001-lone.md"
        text = flat.read_text(encoding="utf-8")
        self.assertIn("title: Lone", text)
        self.assertNotIn("children_count:", text)
        log = (self.vault / "meta" / "sizing-log.yaml").read_text(encoding="utf-8")
        self.assertIn("action: correction", log)
        self.assertIn("sz-2026-08-30-9", log)

    def test_folder_spec_with_child_is_untouched(self):
        self._write("specs/SPEC-002-pair/index.md", self._spec("Pair"))
        self._write("specs/SPEC-002-pair/SPEC-001-kid.md", self._spec("Kid"))
        self.forbid_network()
        self.perform()
        self.assertTrue((self.vault / "specs" / "SPEC-002-pair" / "index.md").is_file())
        self.assertTrue((self.vault / "specs" / "SPEC-002-pair" / "SPEC-001-kid.md").is_file())

    def test_domain_index_is_untouched(self):
        self._write("specs/network/index.md", self._domain("network"))
        self.forbid_network()
        self.perform()
        self.assertTrue((self.vault / "specs" / "network" / "index.md").is_file())
