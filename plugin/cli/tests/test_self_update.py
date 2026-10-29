"""Tests for `compass self-update` (ADR-015).

Adversarial classes: the sha gate must prevent clones, the throttle must
prevent network entirely, local-source mode must never touch the network,
the settings merge must preserve user-owned entries and stay idempotent,
and no failure path may return nonzero or write a partial install.
"""

import hashlib
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
            r"node F:\work\compass\check.js",
            "echo compass",
            "python3 tools/compass_report.py",
        ]
        stale = [
            'python3 "$CLAUDE_PLUGIN_ROOT/cli/compass" sync',
            'python3 "${CLAUDE_PLUGIN_ROOT}/cli/compass" sync',
            r'python "$CLAUDE_PROJECT_DIR\.claude\cli\compass" sync --hook',
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
        # the first update recorded the new version; start the second from
        # the old one so its notice carries the same version change
        self.write_plugin_yaml(source=str(self.project.parent / "somewhere-else"))
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


class UpdateNoticeAdditionsAdversarialTests(SelfUpdateFixture):
    """Hostile shapes for the additions clause: crowds, odd names, mixed
    outcomes, and the branches that carry it."""

    add = UpdateNoticeAdditionsTests.add
    clause = UpdateNoticeAdditionsTests.clause
    update_log = UpdateNoticeAdditionsTests.update_log

    def run_cli(self):
        cwd = os.getcwd()
        os.chdir(self.project)
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                self_update.run(["--force"])
        finally:
            os.chdir(cwd)
        return buf.getvalue()

    def fake_overlay_report(self, report):
        from commands import overlay

        self.addCleanup(setattr, overlay, "apply_overlays", overlay.apply_overlays)
        overlay.apply_overlays = lambda *a, **k: report

    def test_many_additions_keep_one_line_with_every_name_once(self):
        """Adversarial where: a project with many additions makes the clause
        wrap, truncate, or drop names. Forty additions with no shipped file
        (names with spaces and semicolons among them) must all appear in
        order inside a single output line."""
        self.fake_remote()
        names = [f"agents/ghost-{n:02d}.md" for n in range(38)]
        names += ["agents/two words.md", "agents/semi;colon.md"]
        for rel in names:
            self.add(rel)
        out = self.run_cli()
        self.assertEqual(out.count("\n"), 1)
        for rel in names:
            self.assertEqual(out.count(rel), 1, rel)
        self.assertEqual(out.count(NO_SHIPPED), 1)
        self.assertNotIn(REAPPLIED, out)
        self.assertEqual(self.update_log().count("\n"), 1)

    def test_newline_in_an_addition_name_cannot_split_notice_or_log(self):
        """Adversarial where: a name carrying a newline (legal on POSIX
        filesystems) is joined into the clause raw, so the session-start
        output gains a second line and the log row splits in two."""
        self.fake_remote()
        self.fake_overlay_report(
            {"applied": ["agents/a\nb.md"], "orphans": ["rules/c\r\nd.md"]}
        )
        result = self.perform()
        self.assertNotIn("\n", result["notice"])
        self.assertNotIn("\r", result["notice"])
        self.assertEqual(self.update_log().count("\n"), 1)

    def test_failure_reason_with_newline_never_reaches_notice_or_log(self):
        """Adversarial where: a raise whose message spans lines leaks its
        text into the notice or the log row instead of the fixed pointer."""
        from commands import overlay

        self.fake_remote()

        def boom(*a, **k):
            raise RuntimeError("line one\nline two; local additions re-applied: x")

        self.addCleanup(setattr, overlay, "apply_overlays", overlay.apply_overlays)
        overlay.apply_overlays = boom
        result = self.perform()
        self.assertEqual(result["notice"], BASE_NOTICE + "; " + NOT_APPLIED_NOTICE)
        self.assertEqual(self.update_log().count("\n"), 1)
        self.assertNotIn("line two", self.update_log())

    def test_applied_orphan_and_failed_together_report_all_three_in_order(self):
        """Adversarial where: one clause shadows another when the report
        holds every outcome at once. A re-applied agent, a ghost, and an
        unreadable rule must yield all three clauses, in that order, in the
        notice and in the same log row."""
        self.fake_remote()
        self.add("agents/builder.md")
        self.add("agents/ghost.md")
        self.add("rules/r.md", raw=b"\xff\xfe\x00bad bytes \xc3\x28")
        expected = (
            BASE_NOTICE
            + "; " + REAPPLIED + "agents/builder.md"
            + "; " + NO_SHIPPED + "agents/ghost.md"
            + "; " + NOT_APPLIED_NOTICE
        )
        self.assertEqual(self.perform()["notice"], expected)
        self.assertTrue(self.update_log().rstrip("\n").endswith(expected[len(BASE_NOTICE):]))

    def test_local_source_version_bump_carries_failure_clause_in_log(self):
        """Adversarial where: the local-source branch reports orphans but
        loses the failure pointer, or writes the clause to the notice and
        not the `applied-local` log row."""
        make_plugin_tree(self.project / "plugin", version="1.0.0")
        self.write_plugin_yaml(source=str(self.project / "plugin"))
        self.add("agents/ghost.md")
        self.add("rules/r.md", raw=b"\xff\xfe\x00bad bytes \xc3\x28")
        self.forbid_network()
        notice = self.perform()["notice"]
        self.assertEqual(
            notice,
            "Compass updated 0.9.0 -> 1.0.0 (local source)"
            + "; " + NO_SHIPPED + "agents/ghost.md"
            + "; " + NOT_APPLIED_NOTICE,
        )
        self.assertIn("applied-local 0.9.0 -> 1.0.0; " + NO_SHIPPED, self.update_log())

    def test_dsh_host_branch_still_returns_the_additions_report(self):
        """Adversarial where: the dsh materialization branch sits between
        the copy and the overlay call; a host roster containing dsh must
        still apply the additions and report them."""
        self.fake_remote()
        self.add("agents/builder.md")
        for name in (
            "effective_hosts",
            "materialize_dsh_hooks",
            "materialize_dsh_skills",
            "materialize_dsh_instructions",
            "materialize_dsh_bundle",
            "install_dsh_bundle",
            "dsh_home",
        ):
            self.addCleanup(setattr, hostlib, name, getattr(hostlib, name))
        hostlib.effective_hosts = lambda vault: ["claude", "dsh"]
        hostlib.materialize_dsh_hooks = lambda *a, **k: None
        hostlib.materialize_dsh_skills = lambda *a, **k: None
        hostlib.materialize_dsh_instructions = lambda *a, **k: None
        hostlib.materialize_dsh_bundle = lambda *a, **k: None
        hostlib.install_dsh_bundle = lambda *a, **k: None
        hostlib.dsh_home = lambda: self.project.parent / "dsh-home"
        notice = self.perform()["notice"]
        self.assertEqual(self.clause(notice, REAPPLIED), "agents/builder.md")


KEPT = "hand edits saved to meta/local/kept: "


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


class HandEditFixture(SelfUpdateFixture):
    """Updates that run twice over one project: the first installs, the
    second meets whatever the human changed in `.claude/` in between.

    Assumed shapes: `.compass/meta/installed.json` is a JSON object mapping
    each installed file's path under `.claude/` (`agents/builder.md`) to the
    sha256 hex of the shipped bytes, either at the top level or under a
    `files` key. A hand-edited file is saved byte-for-byte as
    `.compass/meta/local/kept/<kind>/<name>.md`, named like a local addition
    (`agents/builder.md`, `skills/sweeping.md`). The notice carries
    `; hand edits saved to meta/local/kept: ` and the saved names joined by
    `, `."""

    @property
    def claude(self):
        return self.project / ".claude"

    @property
    def kept_dir(self):
        return self.vault / "meta" / "local" / "kept"

    def set_shipped(self, root, agent=None, rule=None, skill=None):
        for text, rel in (
            (agent, "templates/agents/builder.md"),
            (rule, "templates/rules/r.md"),
            (skill, "skills/sweeping/SKILL.md"),
        ):
            if text is not None:
                (Path(root) / rel).write_bytes(text.encode("utf-8"))

    def reinstall(self, **shipped):
        """Ship new text and run another remote update from the old version."""
        self.set_shipped(self.external_src, **shipped)
        self.write_plugin_yaml(source=str(self.project.parent / "somewhere-else"))
        return self.perform(force=True)

    def recorded(self):
        path = self.vault / "meta" / "installed.json"
        self.assertTrue(path.is_file(), "update wrote no installed.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data.get("files"), dict):
            data = data["files"]
        return {k.replace("\\", "/"): v for k, v in data.items()}

    def recorded_for(self, rel):
        found = {k: v for k, v in self.recorded().items() if k.endswith(rel)}
        self.assertEqual(len(found), 1, f"want one record for {rel}: {found}")
        return next(iter(found.values()))

    def write_installed(self, rel, data):
        path = self.claude / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def kept_files(self):
        if not self.kept_dir.exists():
            return []
        return sorted(
            p.relative_to(self.kept_dir).as_posix()
            for p in self.kept_dir.rglob("*")
            if p.is_file()
        )

    def kept_names(self, notice):
        for part in notice.split("; "):
            if part.startswith(KEPT):
                return part[len(KEPT):].split(", ")
        return []

    def clause(self, notice, label):
        for part in notice.split("; "):
            if part.startswith(label):
                return part[len(label):]
        return None


class InstalledRecordTests(HandEditFixture):
    def test_every_installed_file_is_recorded_with_the_hash_of_its_shipped_bytes(self):
        """Adversarial where: the record is skipped for a whole file kind,
        hashes the installed file after a local addition was appended (so
        the next update calls an untouched file hand edited), or goes stale
        when the shipped text changes. An agent, a rule and a skill each
        carry the hash of what shipped; with an addition on the agent, the
        second update still records the shipped hash, not the hash of
        shipped text plus block."""
        self.fake_remote()
        self.perform()
        self.assertEqual(self.recorded_for("agents/builder.md"), sha256_hex(b"agent"))
        self.assertEqual(self.recorded_for("rules/r.md"), sha256_hex(b"rule"))
        self.assertEqual(
            self.recorded_for("skills/sweeping/SKILL.md"), sha256_hex(b"skill")
        )

        local = self.vault / "meta" / "local" / "agents" / "builder.md"
        local.parent.mkdir(parents=True)
        local.write_bytes(b"Always cite sources.\n")
        self.reinstall(agent="agent v2")
        installed = (self.claude / "agents" / "builder.md").read_bytes()
        self.assertNotEqual(installed, b"agent v2", "the addition was not applied")
        self.assertEqual(self.recorded_for("agents/builder.md"), sha256_hex(b"agent v2"))


class HandEditSavedTests(HandEditFixture):
    def test_edited_files_are_saved_before_replacement_and_named_unedited_are_not(self):
        """Adversarial where: the update replaces an edited file without
        saving it, saves every file (not only the changed ones), saves a
        copy that is not the human's bytes, or leaves the saved file out of
        the notice. An appended line in the agent and a same-length
        one-byte change in the rule are both edits; the untouched skill is
        neither saved nor named; the installed agent and rule hold the new
        shipped text."""
        self.fake_remote()
        self.perform()
        self.write_installed("agents/builder.md", b"agent\nmy private rule\n")
        self.write_installed("rules/r.md", b"ruLe")

        result = self.reinstall(agent="agent v2", rule="rule v2", skill="skill v2")

        self.assertEqual(result["status"], "updated")
        self.assertEqual(self.kept_files(), ["agents/builder.md", "rules/r.md"])
        self.assertEqual(
            (self.kept_dir / "agents" / "builder.md").read_bytes(),
            b"agent\nmy private rule\n",
        )
        self.assertEqual((self.kept_dir / "rules" / "r.md").read_bytes(), b"ruLe")
        self.assertEqual((self.claude / "agents" / "builder.md").read_bytes(), b"agent v2")
        self.assertEqual((self.claude / "rules" / "r.md").read_bytes(), b"rule v2")
        self.assertEqual(
            (self.claude / "skills" / "sweeping" / "SKILL.md").read_bytes(), b"skill v2"
        )
        self.assertEqual(
            sorted(self.kept_names(result["notice"])), ["agents/builder.md", "rules/r.md"]
        )
        log = (self.vault / "tmp" / "self-update.log").read_text(encoding="utf-8")
        self.assertIn(KEPT, log)

    def test_unedited_deleted_and_reverted_files_save_nothing(self):
        """Adversarial where: anything that is not a live difference from the
        record counts as an edit. A file left alone, a file edited and put
        back to its exact shipped bytes before the update, and a file the
        human deleted all leave `kept/` without a file, add no clause to the
        notice, and the deleted file is installed again."""
        self.fake_remote()
        self.perform()
        self.write_installed("rules/r.md", b"changed")
        self.write_installed("rules/r.md", b"rule")
        (self.claude / "skills" / "sweeping" / "SKILL.md").unlink()

        result = self.reinstall(agent="agent v2", rule="rule v2", skill="skill v2")

        self.assertEqual(result["status"], "updated")
        self.assertEqual(self.kept_files(), [])
        self.assertEqual(result["notice"], BASE_NOTICE)
        self.assertEqual(
            (self.claude / "skills" / "sweeping" / "SKILL.md").read_bytes(), b"skill v2"
        )
        self.assertEqual(self.recorded_for("rules/r.md"), sha256_hex(b"rule v2"))

    def test_a_second_hand_edit_does_not_destroy_the_first_saved_copy(self):
        """Adversarial where: both edits of one file are saved under the
        same name and the second update overwrites the first copy, losing
        what the human typed. After two updates that each meet an edit of
        the same file, both edits' text can still be found under `kept/`."""
        self.fake_remote()
        self.perform()
        self.write_installed("agents/builder.md", b"agent\nFIRST EDIT\n")
        self.reinstall(agent="agent v2")
        self.write_installed("agents/builder.md", b"agent v2\nSECOND EDIT\n")
        self.reinstall(agent="agent v3")

        saved = b"".join(
            p.read_bytes() for p in self.kept_dir.rglob("*") if p.is_file()
        )
        self.assertIn(b"FIRST EDIT", saved)
        self.assertIn(b"SECOND EDIT", saved)

    def test_local_source_update_saves_and_names_hand_edits_too(self):
        """Adversarial where: the local-source branch builds its own notice
        and applies the shipped files separately, so it records no hashes
        or never saves an edit. A version bump from a source inside the
        project saves the edited agent and names it."""
        source = make_plugin_tree(self.project / "plugin", version="1.0.0")
        self.write_plugin_yaml(source=str(source))
        self.forbid_network()
        self.perform()
        self.assertEqual(self.recorded_for("agents/builder.md"), sha256_hex(b"agent"))

        self.write_installed("agents/builder.md", b"agent\nlocal tweak\n")
        self.set_shipped(source, agent="agent v2")
        (source / ".claude-plugin" / "plugin.json").write_text(
            json.dumps(dict(PLUGIN_JSON, version="1.1.0")), encoding="utf-8"
        )
        result = self.perform(force=True)

        self.assertEqual(result["status"], "applied-local")
        self.assertEqual(
            (self.kept_dir / "agents" / "builder.md").read_bytes(), b"agent\nlocal tweak\n"
        )
        self.assertEqual(self.kept_names(result["notice"]), ["agents/builder.md"])


class NoRecordTests(HandEditFixture):
    def test_project_without_a_record_is_unedited_on_its_first_update(self):
        """Adversarial where: with no installed.json the update has nothing
        to compare against and treats every differing file as hand edited,
        saving the whole install, or it never writes the record so the next
        update is blind too. Differing files already in `.claude/` are
        replaced without a saved copy or a notice clause, the record is
        written, and an edit made after that update is saved by the next."""
        self.write_installed("agents/builder.md", b"text from an older release")
        self.write_installed("rules/r.md", b"another older text")
        self.assertFalse((self.vault / "meta" / "installed.json").exists())
        self.fake_remote()

        result = self.perform()

        self.assertEqual(self.kept_files(), [])
        self.assertEqual(result["notice"], BASE_NOTICE)
        self.assertEqual((self.claude / "agents" / "builder.md").read_bytes(), b"agent")
        self.assertEqual(self.recorded_for("agents/builder.md"), sha256_hex(b"agent"))

        self.write_installed("agents/builder.md", b"agent\nedited after\n")
        second = self.reinstall(agent="agent v2")
        self.assertEqual(self.kept_names(second["notice"]), ["agents/builder.md"])


class LocalAdditionBlockTests(HandEditFixture):
    def test_a_files_own_addition_block_is_not_a_hand_edit_but_text_above_it_is(self):
        """Adversarial where: the installed file differs from its shipped
        hash only by the appended local addition block, and the update calls
        every file with an addition hand edited, saving it on each update.
        With the block present and nothing else changed, nothing is saved
        and the addition is re-applied; with the shipped text above the
        marker also edited, the file is saved whole."""
        self.fake_remote()
        local = self.vault / "meta" / "local" / "agents" / "builder.md"
        local.parent.mkdir(parents=True)
        local.write_bytes(b"Always cite sources.\n")
        self.perform()
        installed = (self.claude / "agents" / "builder.md").read_bytes()
        self.assertIn(b"Always cite sources.", installed)

        quiet = self.reinstall(agent="agent v2")
        self.assertEqual(self.kept_files(), [])
        self.assertEqual(self.kept_names(quiet["notice"]), [])
        self.assertEqual(self.clause(quiet["notice"], REAPPLIED), "agents/builder.md")

        path = self.claude / "agents" / "builder.md"
        edited = path.read_bytes().replace(b"agent v2", b"agent v2 EDITED", 1)
        path.write_bytes(edited)
        loud = self.reinstall(agent="agent v3")
        self.assertEqual(self.kept_names(loud["notice"]), ["agents/builder.md"])
        self.assertEqual((self.kept_dir / "agents" / "builder.md").read_bytes(), edited)


class ManualUpdateKeepsEditsTests(HandEditFixture):
    """`/compass:update` copies the clone into `.claude/` with `cp`; it first
    runs `compass self-update --keep-edits <clone>` so a hand-edited file is
    saved and the install record written, the same as an automatic update."""

    def keep_edits(self, src):
        """Run `--keep-edits` with the project as cwd and no
        CLAUDE_PROJECT_DIR, since `find_vault_root` honors that variable
        before the cwd."""
        from unittest import mock

        cwd = os.getcwd()
        os.chdir(self.project)
        buf = io.StringIO()
        try:
            with mock.patch.dict(os.environ), redirect_stdout(buf):
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
                code = self_update.run(["--keep-edits", str(src)])
        finally:
            os.chdir(cwd)
        return code, buf.getvalue()

    def test_keep_edits_saves_an_edited_file_and_records_what_ships(self):
        """Adversarial where: the manual path saves nothing, so the `cp` that
        follows destroys the human's edit; saves an untouched file; leaves
        the record describing the old release, so the next update calls the
        fresh copy hand edited; or copies anything into `.claude/` itself,
        which is the skill's own step. The edited agent is saved and named
        on one line, the untouched rule is not, the record holds the hashes
        of the new shipped text, and the installed files are unchanged."""
        self.fake_remote()
        self.perform()
        self.write_installed("agents/builder.md", b"agent\nmy private rule\n")
        self.set_shipped(self.external_src, agent="agent v2", rule="rule v2")

        code, out = self.keep_edits(self.external_src)

        self.assertEqual(code, 0)
        self.assertEqual(self.kept_files(), ["agents/builder.md"])
        self.assertEqual(
            (self.kept_dir / "agents" / "builder.md").read_bytes(),
            b"agent\nmy private rule\n",
        )
        self.assertEqual(out, KEPT + "agents/builder.md\n")
        self.assertEqual(self.recorded_for("agents/builder.md"), sha256_hex(b"agent v2"))
        self.assertEqual(self.recorded_for("rules/r.md"), sha256_hex(b"rule v2"))
        self.assertEqual(
            (self.claude / "agents" / "builder.md").read_bytes(),
            b"agent\nmy private rule\n",
        )

    def test_keep_edits_is_silent_with_nothing_edited_and_refuses_a_missing_source(self):
        """Adversarial where: the entry prints a line when nothing was saved,
        so the skill's report gains noise, or a wrong source path exits 0
        and the skill copies over edits it never checked."""
        self.fake_remote()
        self.perform()
        code, out = self.keep_edits(self.external_src)
        self.assertEqual((code, out), (0, ""))
        code, out = self.keep_edits(self.project / "no-such-clone")
        self.assertNotEqual(code, 0)
        self.assertEqual(self.kept_files(), [])


class HandEditImplementationBranchTests(HandEditFixture):
    """Branches that exist only in the hand-edit detection: the interplay
    with `apply-models`, repeated `--keep-edits`, odd file names, unusual
    line endings under an applied addition, and files a release adds or
    drops."""

    AGENT_WITH_FRONTMATTER = (
        b"---\nname: builder\nmodel: sonnet\neffort: high\n---\nbody\n"
    )

    def in_project(self, call):
        """Run `call()` with the project as cwd and no CLAUDE_PROJECT_DIR,
        since `find_vault_root` honors that variable before the cwd."""
        from unittest import mock

        cwd = os.getcwd()
        os.chdir(self.project)
        try:
            with mock.patch.dict(os.environ):
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
                return call()
        finally:
            os.chdir(cwd)

    def keep_edits(self, src):
        from contextlib import redirect_stderr

        out, err = io.StringIO(), io.StringIO()

        def call():
            with redirect_stdout(out), redirect_stderr(err):
                return self_update.run(["--keep-edits", str(src)])

        code = self.in_project(call)
        return code, out.getvalue(), err.getvalue()

    def run_apply_models(self):
        from commands import apply_models

        def call():
            with redirect_stdout(io.StringIO()):
                return apply_models.run(["--dir", str(self.claude / "agents")])

        return self.in_project(call)

    def test_a_model_override_written_by_apply_models_is_not_a_hand_edit(self):
        """Adversarial where: every real update runs `apply-models` after the
        copy, rewriting `model:`/`effort:` in the installed agents from the
        project's `models.yaml`; the record holds the shipped hash, so the
        next update calls each overridden agent hand edited, saves a copy
        of it on every update and names it in the notice. A project that
        pins builder to opus has its agent rewritten by the policy; an
        update that ships the same text saves nothing."""
        self.fake_remote()
        self.set_shipped(self.external_src)
        (self.external_src / "templates" / "agents" / "builder.md").write_bytes(
            self.AGENT_WITH_FRONTMATTER
        )
        (self.vault / "meta" / "models.yaml").write_text(
            "agents:\n  builder: opus\n", encoding="utf-8"
        )
        self.perform()
        self.run_apply_models()
        installed = (self.claude / "agents" / "builder.md").read_bytes()
        self.assertIn(b"model: opus", installed, "policy did not rewrite the agent")

        result = self.reinstall()

        self.assertEqual(self.kept_files(), [])
        self.assertEqual(self.kept_names(result["notice"]), [])

    def test_keep_edits_run_twice_saves_one_edit_once(self):
        """Adversarial where: `--keep-edits` records the new hashes without
        copying, so a second run before the copy (the skill's step 4 run
        again after a stop) finds the same edit still in place, differing
        from the fresh record, and saves a second identical copy under
        `builder.2.md` and names it again. The second run saves nothing."""
        self.fake_remote()
        self.perform()
        self.write_installed("agents/builder.md", b"agent\nmy private rule\n")
        self.set_shipped(self.external_src, agent="agent v2")

        first = self.keep_edits(self.external_src)
        second = self.keep_edits(self.external_src)

        self.assertEqual(first[:2], (0, KEPT + "agents/builder.md\n"))
        self.assertEqual(self.kept_files(), ["agents/builder.md"])
        self.assertEqual(second[:2], (0, ""))

    def test_keep_edits_refuses_without_a_vault_or_without_a_source_argument(self):
        """Adversarial where: a project with no `.compass/` raises out of
        `find_vault_root` instead of exiting 1, `--keep-edits` as the last
        argument indexes past the list, or the next flag is read as the
        source path. Each exits 1 with a message on stderr and writes
        nothing."""
        from contextlib import redirect_stderr

        bare = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, bare, True)
        rows = {
            "no vault": (bare, ["--keep-edits", str(self.external_src)]),
            "no argument": (self.project, ["--keep-edits"]),
            "flag as source": (self.project, ["--keep-edits", "--force"]),
        }
        for name, (cwd_dir, args) in rows.items():
            with self.subTest(row=name):
                err = io.StringIO()

                def call():
                    with redirect_stdout(io.StringIO()), redirect_stderr(err):
                        return self_update.run(args)

                from unittest import mock

                before = os.getcwd()
                os.chdir(cwd_dir)
                try:
                    with mock.patch.dict(os.environ):
                        os.environ.pop("CLAUDE_PROJECT_DIR", None)
                        code = call()
                finally:
                    os.chdir(before)
                self.assertEqual(code, 1)
                self.assertIn("--keep-edits", err.getvalue())
        self.assertFalse((bare / ".compass").exists())
        self.assertFalse((self.vault / "meta" / "installed.json").exists())

    def test_unusual_file_names_are_saved_byte_for_byte_and_named(self):
        """Adversarial where: a name holding the notice's own `, ` and `; `
        separators or non-ASCII characters is mangled, split or saved under
        another name, losing the edit or pointing the human at a file that
        does not exist. Both edited agents are saved under their own names
        with the edited bytes, and the notice carries each name verbatim."""
        self.fake_remote()
        names = ["my agent; v2, copy.md", "café.md"]
        agents = self.external_src / "templates" / "agents"
        for name in names:
            (agents / name).write_bytes(b"shipped")
        self.perform()
        for name in names:
            self.write_installed(f"agents/{name}", b"shipped\nedit for " + name.encode("utf-8"))

        result = self.reinstall(agent="agent v2")

        for name in names:
            with self.subTest(name=name):
                self.assertEqual(
                    (self.kept_dir / "agents" / name).read_bytes(),
                    b"shipped\nedit for " + name.encode("utf-8"),
                )
                self.assertIn(f"agents/{name}", result["notice"])

    def test_an_agent_named_like_a_numbered_copy_never_overwrites_a_saved_copy(self):
        """Adversarial where: the numbered-copy scheme (`foo.2.md` for a
        second save of `foo.md`) collides with a shipped agent that is itself
        named `foo.2.md`; the save writes over the other file's copy and one
        human's edit is lost. Three edits in one update (foo.md twice over
        two updates, foo.2.md once) all remain findable under `kept/`."""
        self.fake_remote()
        agents = self.external_src / "templates" / "agents"
        (agents / "foo.md").write_bytes(b"foo")
        (agents / "foo.2.md").write_bytes(b"foo two")
        self.perform()
        self.write_installed("agents/foo.md", b"foo\nEDIT-ONE")
        self.reinstall(agent="agent v2")
        self.write_installed("agents/foo.md", b"foo\nEDIT-TWO")
        self.write_installed("agents/foo.2.md", b"foo two\nEDIT-THREE")

        self.reinstall(agent="agent v3")

        saved = b"".join(p.read_bytes() for p in self.kept_dir.rglob("*") if p.is_file())
        for marker in (b"EDIT-ONE", b"EDIT-TWO", b"EDIT-THREE"):
            with self.subTest(marker=marker):
                self.assertIn(marker, saved)
        self.assertEqual(len(self.kept_files()), 3)

    def test_an_applied_addition_is_never_a_hand_edit_whatever_the_shipped_line_endings(self):
        """Adversarial where: applying an addition rewrites the gap between
        the shipped text and the marker, and the hash comparison recovers the
        shipped bytes from only four forms of that text. A shipped file with
        CRLF throughout, CRLF and no final newline, two or three trailing
        newlines, or mixed endings is then called hand edited on every
        update and saved each time. Each file carries an addition and an
        update that ships the same text saves nothing."""
        self.fake_remote()
        rows = {
            "crlf": b"line one\r\nline two\r\n",
            "crlf-no-final-newline": b"line one\r\nline two",
            "two-trailing-newlines": b"line one\n\n",
            "three-trailing-newlines": b"line one\n\n\n",
            "mixed": b"line one\r\nline two\nline three\n",
        }
        agents = self.external_src / "templates" / "agents"
        for name, data in rows.items():
            (agents / f"{name}.md").write_bytes(data)
            local = self.vault / "meta" / "local" / "agents" / f"{name}.md"
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(b"Local rule for " + name.encode("utf-8") + b".\n")
        self.perform()
        for name in rows:
            installed = (self.claude / "agents" / f"{name}.md").read_bytes()
            self.assertIn(b"Local rule for", installed, name)

        result = self.reinstall()

        saved = self.kept_files()
        for name in rows:
            with self.subTest(row=name):
                self.assertNotIn(f"agents/{name}.md", saved)
        self.assertEqual(self.kept_names(result["notice"]), [])

    def test_a_file_the_release_stops_shipping_is_left_alone(self):
        """Adversarial where: the comparison walks the installed tree
        instead of the release's file list, or a file missing from the new
        release breaks the walk; an edited agent the release dropped is
        replaced, saved needlessly, or aborts the update. The update lands,
        the dropped agent keeps the human's bytes and nothing is saved."""
        self.fake_remote()
        agents = self.external_src / "templates" / "agents"
        (agents / "old.md").write_bytes(b"old shipped")
        self.perform()
        self.write_installed("agents/old.md", b"old shipped\nmy edit")
        (agents / "old.md").unlink()

        result = self.reinstall(agent="agent v2")

        self.assertEqual(result["status"], "updated")
        self.assertEqual((self.claude / "agents" / "old.md").read_bytes(), b"old shipped\nmy edit")
        self.assertEqual(self.kept_files(), [])

    def test_a_file_of_the_humans_own_that_a_release_starts_shipping_is_saved(self):
        """Adversarial where: a file with no entry in the record is taken for
        unedited and replaced unsaved, destroying a project's own agent that
        happens to share a name with a newly shipped one. The release adds
        `mine.md`; the project already has its own `mine.md`; the update
        saves it and names it."""
        self.fake_remote()
        self.perform()
        self.write_installed("agents/mine.md", b"my own agent")
        (self.external_src / "templates" / "agents" / "mine.md").write_bytes(b"shipped mine")

        result = self.reinstall(agent="agent v2")

        self.assertEqual((self.kept_dir / "agents" / "mine.md").read_bytes(), b"my own agent")
        self.assertEqual((self.claude / "agents" / "mine.md").read_bytes(), b"shipped mine")
        self.assertEqual(self.kept_names(result["notice"]), ["agents/mine.md"])

    def test_an_edited_retired_skill_is_saved_before_the_update_removes_it(self):
        """Adversarial where: the comparison walks only the release's file
        list, so a skill the release retires is deleted with the human's edit
        in it. One release ships `tree`; the human edits it; the next release
        retires it. The edit is saved and named, the untouched retired copy
        of another file is not, and the skill folder is gone."""
        self.fake_remote()
        retired = self.external_src / "skills" / "tree"
        retired.mkdir(parents=True)
        (retired / "SKILL.md").write_bytes(b"tree skill")
        (retired / "NOTES.md").write_bytes(b"tree notes")
        self.perform()
        shutil.rmtree(retired)
        self.write_installed("skills/tree/SKILL.md", b"tree skill\nmy tree rule")

        result = self.reinstall(agent="agent v2")

        self.assertFalse((self.claude / "skills" / "tree").exists())
        self.assertEqual(self.kept_files(), ["skills/tree.md"])
        self.assertEqual((self.kept_dir / "skills" / "tree.md").read_bytes(), b"tree skill\nmy tree rule")
        self.assertEqual(self.kept_names(result["notice"]), ["skills/tree.md"])

    def test_a_record_with_a_byte_order_mark_still_finds_the_edit(self):
        """Adversarial where: an editor that saves `installed.json` with a
        UTF-8 byte order mark makes the record unreadable, so every file
        counts as unedited and the human's edit is replaced unsaved."""
        self.fake_remote()
        self.perform()
        path = self.vault / "meta" / "installed.json"
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        self.write_installed("agents/builder.md", b"agent\nmy private rule\n")

        result = self.reinstall(agent="agent v2")

        self.assertEqual(self.kept_names(result["notice"]), ["agents/builder.md"])

    def test_a_model_override_does_not_hide_an_edit_to_the_agent_body(self):
        """Adversarial where: the comparison that ignores the `model:` and
        `effort:` lines ignores more of the file, so an agent carrying both a
        model override and a body edit counts as unedited and the edit is
        replaced unsaved."""
        self.fake_remote()
        self.set_shipped(self.external_src, agent=self.AGENT_WITH_FRONTMATTER.decode("utf-8"))
        self.perform()
        self.write_installed(
            "agents/builder.md",
            b"---\nname: builder\nmodel: opus\neffort: low\n---\nbody\nmy private rule\n",
        )

        result = self.reinstall()

        self.assertEqual(self.kept_names(result["notice"]), ["agents/builder.md"])


if __name__ == "__main__":
    unittest.main()
