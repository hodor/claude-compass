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

import hostlib  # noqa: E402
from commands import self_update  # noqa: E402


PLUGIN_JSON = {"name": "compass", "version": "9.9.9"}

MANIFEST = {
    "hooks": {
        "PostToolUse": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "timeout": 15,
                        "command": "python compass context-check --hook",
                    }
                ],
            },
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
        # pin host detection off: these tests exercise the update flow, and
        # must neither depend on the machine having dsh nor write into its
        # real harness home
        self.addCleanup(setattr, hostlib, "dsh_available", hostlib.dsh_available)
        hostlib.dsh_available = lambda: False

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


class ObsidianPluginInstallTests(SelfUpdateFixture):
    """The apply carries the Compass Review plugin into `.claude/obsidian/` and,
    when Obsidian has opened the vault, into its `.obsidian/plugins/`."""

    def setUp(self):
        super().setUp()
        self.local_src = make_plugin_tree(self.project / "plugin", version="0.9.0")
        plugin_dir = self.local_src / "obsidian" / "compass-review"
        plugin_dir.mkdir(parents=True)
        for name in ("main.js", "manifest.json", "styles.css"):
            (plugin_dir / name).write_text(f"// {name}", encoding="utf-8")
        self.write_plugin_yaml(source=str(self.local_src))
        self.forbid_network()

    def test_installs_into_an_opened_vault_and_keeps_other_plugins(self):
        obsidian = self.vault / ".obsidian"
        obsidian.mkdir()
        (obsidian / "community-plugins.json").write_text('["dataview"]', encoding="utf-8")
        self.perform(force=True)
        self.assertTrue((self.project / ".claude" / "obsidian" / "compass-review" / "main.js").is_file())
        self.assertEqual((obsidian / "plugins" / "compass-review" / "main.js").read_text(), "// main.js")
        self.assertEqual(json.loads((obsidian / "community-plugins.json").read_text()), ["dataview", "compass-review"])

    def test_a_vault_obsidian_never_opened_gets_no_obsidian_folder(self):
        self.perform(force=True)
        self.assertFalse((self.vault / ".obsidian").exists())
        self.assertFalse((self.project / ".obsidian").exists())


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
                                    {
                                        "type": "command",
                                        "command": 'python3 "$CLAUDE_PLUGIN_ROOT/cli/compass" sync',
                                    }
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
        self.assertNotIn('python3 "$CLAUDE_PLUGIN_ROOT/cli/compass" sync', commands)
        compass_groups = [
            g
            for g in post
            if any("compass" in h["command"] for h in g["hooks"])
        ]
        # The three per-tool sync groups collapse into one; the context
        # threshold group registers beside it, matching every tool.
        self.assertEqual(len(compass_groups), 2)
        sync = [g for g in compass_groups if any(" sync --hook" in h["command"] for h in g["hooks"])]
        context = [g for g in compass_groups if any("context-check --hook" in h["command"] for h in g["hooks"])]
        self.assertEqual(len(sync), 1)
        self.assertEqual(len(context), 1)
        # dsh matches on its lowercase tool names; the extra alternatives are
        # inert under Claude Code, so one manifest stays legal on both hosts.
        self.assertEqual(sync[0]["matcher"], "Write|Edit|MultiEdit|write|edit")
        self.assertNotIn("matcher", context[0])
        for g in post:
            for h in g["hooks"]:
                self.assertNotIn("if", h)

    def test_merge_keeps_user_hooks_that_only_mention_compass(self):
        # A user's own hook can live under a path or call a tool named
        # compass; only commands that run Compass's CLI are Compass's.
        user_commands = [
            "bash /home/me/compass-app/lint.sh",
            "node F:\work\compass\check.js",
            "echo compass",
            "python3 tools/compass_report.py",
        ]
        stale = [
            'python3 "$CLAUDE_PLUGIN_ROOT/cli/compass" sync',
            'python3 "${CLAUDE_PLUGIN_ROOT}/cli/compass" sync',
            'python "$CLAUDE_PROJECT_DIR\.claude\cli\compass" sync --hook',
            "python .claude/cli/compass capture-check --hook",
        ]
        groups = [
            {"matcher": "Write", "hooks": [{"type": "command", "command": c}]}
            for c in user_commands + stale
        ]
        (self.project / ".claude" / "settings.json").write_text(
            json.dumps({"hooks": {"PostToolUse": groups}}), encoding="utf-8"
        )
        self.fake_remote()
        self.perform()
        commands = [
            h["command"]
            for g in self.settings()["hooks"]["PostToolUse"]
            for h in g["hooks"]
        ]
        for c in user_commands:
            self.assertIn(c, commands)
        for c in stale:
            self.assertNotIn(c, commands)

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


BASE_NOTICE = "Compass updated 0.9.0 -> 9.9.9"
REAPPLIED = "local additions re-applied: "
NO_SHIPPED = "no shipped file: "
NOT_APPLIED_NOTICE = "local additions not applied (run compass doctor)"


class UpdateNoticeAdditionsTests(SelfUpdateFixture):
    """The update notice and log report what happened to the project's local
    additions: re-applied, no shipped file, or failed."""

    def add(self, rel, text="Always cite sources.\n", raw=None):
        path = self.vault / "meta" / "local" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if raw is not None:
            path.write_bytes(raw)
        else:
            path.write_text(text, encoding="utf-8")
        return path

    def clause(self, notice, label):
        """The text of the `; `-separated clause that starts with `label`,
        without the label, or None."""
        for part in notice.split("; "):
            if part.startswith(label):
                return part[len(label):]
        return None

    def update_log(self):
        return (self.vault / "tmp" / "self-update.log").read_text(encoding="utf-8")

    def test_reapplied_additions_are_named_in_notice_and_log(self):
        """Adversarial where: `_apply` discards the overlay report, so an
        update that re-applied additions says nothing about them. One
        addition gives the exact line; two give both names in the clause,
        and the log row carries the same clause."""
        self.fake_remote()
        self.add("agents/builder.md")
        result = self.perform()
        self.assertEqual(result["status"], "updated")
        self.assertEqual(
            result["notice"], BASE_NOTICE + "; " + REAPPLIED + "agents/builder.md"
        )
        self.assertIn(REAPPLIED + "agents/builder.md", self.update_log())

        self.add("rules/r.md", "Rule addition.\n")
        result = self.perform(force=True)
        named = self.clause(result["notice"], REAPPLIED)
        self.assertIsNotNone(named)
        self.assertIn("agents/builder.md", named)
        self.assertIn("rules/r.md", named)

    def test_addition_with_no_shipped_file_is_named_apart_from_reapplied(self):
        """Adversarial where: the orphan list is lumped into the re-applied
        list (claiming a write that never happened) or dropped. A ghost with
        no installed target must appear under `no shipped file`, a sibling
        that applied must appear under re-applied, and neither name may
        leak into the other clause."""
        self.fake_remote()
        self.add("agents/builder.md")
        self.add("agents/ghost.md")
        notice = self.perform()["notice"]
        self.assertEqual(self.clause(notice, REAPPLIED), "agents/builder.md")
        self.assertEqual(self.clause(notice, NO_SHIPPED), "agents/ghost.md")

    def test_only_orphan_additions_claim_nothing_reapplied(self):
        """Adversarial where: boundary of the re-applied list at zero
        entries. An update whose only addition has no shipped file prints
        the orphan clause and no `re-applied` clause at all, and an
        addition with an empty local file (state current, nothing written)
        leaves the notice exactly as an update with no additions."""
        self.fake_remote()
        ghost = self.add("agents/ghost.md")
        notice = self.perform()["notice"]
        self.assertEqual(notice, BASE_NOTICE + "; " + NO_SHIPPED + "agents/ghost.md")

        ghost.unlink()
        self.add("agents/builder.md", text="\n")
        self.assertEqual(self.perform(force=True)["notice"], BASE_NOTICE)

    def test_raising_overlay_apply_still_finishes_update_and_reports_failure(self):
        """Adversarial where: the try/except around the overlay call hides a
        raise from the notice, or a raise aborts the update before the
        version is recorded. The update must record its version and commit,
        and the notice and log must carry the failure text."""
        from commands import overlay

        self.fake_remote(sha="abc123")
        self.add("agents/builder.md")

        def boom(*a, **k):
            raise RuntimeError("overlay exploded")

        self.addCleanup(setattr, overlay, "apply_overlays", overlay.apply_overlays)
        overlay.apply_overlays = boom
        result = self.perform()
        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["notice"], BASE_NOTICE + "; " + NOT_APPLIED_NOTICE)
        self.assertIn("version: 9.9.9", self.plugin_yaml())
        self.assertIn("commit: abc123", self.plugin_yaml())
        self.assertIn(NOT_APPLIED_NOTICE, self.update_log())

    def test_one_failed_addition_among_good_ones_reports_both(self):
        """Adversarial where: asymmetric failure. One addition whose local
        file is not valid UTF-8 lands in the overlay report's `failed`
        entry while a sibling applies; the notice must name the sibling as
        re-applied and also carry the failure text, rather than reporting
        only the clean half."""
        self.fake_remote()
        self.add("agents/builder.md")
        self.add("rules/r.md", raw=b"\xff\xfe\x00bad bytes \xc3\x28")
        notice = self.perform()["notice"]
        self.assertEqual(self.clause(notice, REAPPLIED), "agents/builder.md")
        self.assertIn(NOT_APPLIED_NOTICE, notice)

    def test_update_without_additions_prints_the_unchanged_notice(self):
        """Adversarial where: the additions clause leaks onto every update.
        With no `meta/local` at all, and with an empty `meta/local/agents`
        directory, the notice is byte-identical to the one the update has
        always printed, and the log row has no additions text."""
        self.fake_remote()
        self.assertEqual(self.perform()["notice"], BASE_NOTICE)
        self.assertNotIn("local additions", self.update_log())

        (self.vault / "meta" / "local" / "agents").mkdir(parents=True)
        self.write_plugin_yaml(source="nowhere")
        self.assertEqual(self.perform(force=True)["notice"], BASE_NOTICE)

    def test_cli_prints_one_line_naming_the_addition(self):
        """Adversarial where: the clause is joined with a newline, or
        printed as a second line, so the session-start context gains an
        extra line per update."""
        self.fake_remote()
        self.add("agents/builder.md")
        cwd = os.getcwd()
        os.chdir(self.project)
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = self_update.run(["--force"])
        finally:
            os.chdir(cwd)
        self.assertEqual(code, 0)
        self.assertEqual(
            buf.getvalue(),
            BASE_NOTICE + "; " + REAPPLIED + "agents/builder.md\n",
        )

    def test_updates_that_print_nothing_still_print_nothing_with_additions(self):
        """Adversarial where: the re-apply result forces a notice onto a
        run that had none. Throttled, sha-current and offline runs apply
        nothing, so they stay silent with additions present; a local-source
        run at an unchanged version re-applies every session start and also
        stays silent, with no additions text in the log."""
        self.add("agents/builder.md")
        check = self.vault / "tmp" / ".self-update-check"
        check.write_text("", encoding="utf-8")
        self.forbid_network()
        self.assertIsNone(self.perform()["notice"])

        check.unlink()
        self.write_plugin_yaml(source="nowhere", commit="abc123")
        self_update._ls_remote = lambda repo, timeout=5: "abc123"
        current = self.perform()
        self.assertEqual((current["status"], current["notice"]), ("current", None))

        self_update._ls_remote = lambda repo, timeout=5: None
        offline = self.perform(force=True)
        self.assertEqual((offline["status"], offline["notice"]), ("offline", None))

        make_plugin_tree(self.project / "plugin", version="0.9.0")
        self.write_plugin_yaml(source=str(self.project / "plugin"))
        self.forbid_network()
        result = self.perform(force=True)
        self.assertEqual(result["status"], "applied-local")
        self.assertIsNone(result["notice"])
        log = self.vault / "tmp" / "self-update.log"
        logged = log.read_text(encoding="utf-8") if log.exists() else ""
        self.assertNotIn("local additions", logged)

    def test_local_source_version_bump_names_the_additions(self):
        """Adversarial where: the local-source branch builds its own notice
        and skips the additions clause that the remote branch gained."""
        make_plugin_tree(self.project / "plugin", version="1.0.0")
        self.write_plugin_yaml(source=str(self.project / "plugin"))
        self.add("agents/builder.md")
        self.forbid_network()
        notice = self.perform()["notice"]
        self.assertIn("0.9.0 -> 1.0.0", notice)
        self.assertEqual(self.clause(notice, REAPPLIED), "agents/builder.md")
