"""Tests for `plugin/hooks/hooks.json`: every hook entry is a command, never
an agent, and every command string names a subcommand the CLI actually
registers. This is the guard against the class of drift where a hook is
edited to invoke a command that was renamed or never added to
`COMMAND_SPECS`."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maincli  # noqa: E402
from commands import self_update  # noqa: E402

HOOKS_JSON = (
    Path(__file__).resolve().parents[2] / "hooks" / "hooks.json"
)

SUBAGENTSTOP_AGENT_NAMES = (
    "builder|tester|debug|validator|planner|researcher|reviewer|spec-writer|pr-describe"
)


def _iter_hook_entries(hooks_block):
    """Yield every individual hook dict (the `{"type": ..., "command"/"prompt": ...}`
    leaves) across every event and matcher group in the `hooks` block."""
    for event_entries in hooks_block.values():
        for group in event_entries:
            for hook in group.get("hooks", []):
                yield hook


class HooksJsonTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
        self.command_names = {name for name, _ in maincli.COMMAND_SPECS}

    def test_parses_as_json(self):
        self.assertIn("hooks", self.data)

    def test_no_agent_type_hook_remains(self):
        for hook in _iter_hook_entries(self.data["hooks"]):
            self.assertNotEqual(
                hook.get("type"), "agent",
                f"agent-type hook still present: {hook}",
            )

    def test_stop_is_a_command_hook_running_capture_check(self):
        stop_hooks = list(_iter_hook_entries({"Stop": self.data["hooks"]["Stop"]}))
        self.assertEqual(len(stop_hooks), 1)
        hook = stop_hooks[0]
        self.assertEqual(hook["type"], "command")
        self.assertIn("capture-check", hook["command"])
        self.assertIn("--hook", hook["command"])

    def test_subagentstop_is_a_command_hook_running_capture_signal(self):
        group = self.data["hooks"]["SubagentStop"][0]
        hooks = group["hooks"]
        self.assertEqual(len(hooks), 1)
        hook = hooks[0]
        self.assertEqual(hook["type"], "command")
        self.assertIn("capture-signal", hook["command"])
        self.assertIn("--hook", hook["command"])

    def test_posttooluse_runs_context_check_on_every_tool(self):
        # Defect class: the threshold hook is scoped to some tools, so a
        # session that crosses 80% on any other tool keeps working.
        groups = [
            group for group in self.data["hooks"]["PostToolUse"]
            if any("context-check --hook" in h.get("command", "") for h in group["hooks"])
        ]
        self.assertEqual(len(groups), 1)
        self.assertNotIn("matcher", groups[0])
        self.assertNotIn("if", groups[0]["hooks"][0])

    def test_context_check_skips_subagent_events_before_python(self):
        # Defect class: a subagent's tool call starts Python on the main
        # session's hot path for a check that always passes.
        command = next(
            h["command"] for group in self.data["hooks"]["PostToolUse"]
            for h in group["hooks"] if "context-check" in h["command"]
        )
        prefilter = "case \"$input\" in *agent_id*|*agent_type*) exit 0;; esac;"
        self.assertIn(prefilter, command)
        self.assertLess(command.index(prefilter), command.index("python"))

    def test_subagentstop_matcher_lists_bare_and_plugin_scoped_names(self):
        # Defect class: agents loaded from a plugin report `compass:<name>`
        # and a bare-name matcher never fires for them.
        group = self.data["hooks"]["SubagentStop"][0]
        alternatives = group["matcher"].split("|")
        for name in SUBAGENTSTOP_AGENT_NAMES.split("|"):
            self.assertIn(name, alternatives)
            self.assertIn(f"compass:{name}", alternatives)
        self.assertEqual(len(alternatives), len(set(alternatives)))
        self.assertEqual(
            len(alternatives), 2 * len(SUBAGENTSTOP_AGENT_NAMES.split("|"))
        )

    def test_every_command_string_references_a_registered_subcommand(self):
        for hook in _iter_hook_entries(self.data["hooks"]):
            command = hook.get("command")
            if command is None:
                continue
            referenced = {
                name for name in self.command_names if f"compass\" {name} " in command
            }
            self.assertTrue(
                referenced,
                f"no registered COMMAND_SPECS name found in command string: {command}",
            )

    def test_all_command_hooks_use_the_python3_else_python_guard(self):
        for hook in _iter_hook_entries(self.data["hooks"]):
            if hook.get("type") != "command":
                continue
            command = hook["command"]
            self.assertIn("command -v python3", command)
            self.assertRegex(command, r"else (printf [^|]*\| )?python \"")

    def test_every_command_exits_zero_when_the_cli_is_not_installed(self):
        # Defect class: the plugin's hooks fire in a project the plugin is
        # loaded for but not set up in; a command that runs the missing CLI
        # makes Python exit 2, which blocks the tool call before setup.
        for hook in _iter_hook_entries(self.data["hooks"]):
            if hook.get("type") != "command":
                continue
            self.assertTrue(
                hook["command"].startswith('[ -f "$CLAUDE_PROJECT_DIR/.claude/cli/compass" ] || exit 0; '),
                hook["command"][:80],
            )

    def _guard_hook(self):
        return next(
            h for group in self.data["hooks"]["PreToolUse"]
            for h in group["hooks"] if "guard --hook" in h["command"]
        )

    def test_guard_fails_closed_and_no_other_hook_does(self):
        # Defect class: a guard that crashes or times out lets a destructive
        # subagent call through; the other hooks must keep their default so
        # a fault in them never blocks the user's turn.
        self.assertEqual(self._guard_hook().get("onFailure"), "block")
        for hook in _iter_hook_entries(self.data["hooks"]):
            if hook is not self._guard_hook() and "guard --hook" not in hook.get("command", ""):
                self.assertNotIn("onFailure", hook, hook["command"][:80])

    def test_guard_shell_exits_zero_for_main_agent_and_missing_cli(self):
        # Defect class: with onFailure "block", any non-zero shell exit blocks;
        # a main-agent event or a project without the CLI must exit 0 before
        # Python is reached.
        import subprocess
        import tempfile

        sh = shutil.which("sh")
        if sh is None:
            self.skipTest("no POSIX sh available")
        command = self._guard_hook()["command"]
        main_agent_event = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        with tempfile.TemporaryDirectory() as project:
            env = dict(os.environ, CLAUDE_PROJECT_DIR=project)
            missing = subprocess.run(
                [sh, "-c", command], input=main_agent_event, text=True,
                env=env, capture_output=True,
            )
            self.assertEqual(missing.returncode, 0, missing.stderr)
            cli_dir = Path(project) / ".claude" / "cli"
            cli_dir.mkdir(parents=True)
            (cli_dir / "compass").write_text("raise SystemExit(1)\n", encoding="utf-8")
            present = subprocess.run(
                [sh, "-c", command], input=main_agent_event, text=True,
                env=env, capture_output=True,
            )
            self.assertEqual(present.returncode, 0, present.stderr)


if __name__ == "__main__":
    unittest.main()


class SessionStartPickupTests(unittest.TestCase):
    """A host that could never run workers leaves opportunities open with
    no session to wake; the next session start must run the same ladder so
    they are picked up rather than stranded."""

    def test_manifest_registers_session_start_capture_check(self):
        manifest = json.loads(
            (Path(__file__).resolve().parents[2] / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )["hooks"]
        self.assertIn("SessionStart", manifest)
        commands = [h["command"] for entry in manifest["SessionStart"] for h in entry["hooks"]]
        self.assertTrue(any("capture-check --hook" in c for c in commands))


# The two SessionStart groups the manifest shipped before the compaction
# hooks, byte for byte as at commit c59e6a6.
PRE_COMPACTION_SESSIONSTART_GROUPS = [
    {
        "matcher": "startup",
        "hooks": [
            {
                "type": "command",
                "statusMessage": "Checking for a Compass update",
                "timeout": 60,
                "command": "[ -f \"$CLAUDE_PROJECT_DIR/.claude/cli/compass\" ] || exit 0; if command -v python3 >/dev/null 2>&1; then python3 \"$CLAUDE_PROJECT_DIR/.claude/cli/compass\" self-update --hook; else python \"$CLAUDE_PROJECT_DIR/.claude/cli/compass\" self-update --hook; fi",
            }
        ],
    },
    {
        "hooks": [
            {
                "type": "command",
                "statusMessage": "Picking up a lesson check an earlier session left unfinished",
                "timeout": 30,
                "command": "[ -f \"$CLAUDE_PROJECT_DIR/.claude/cli/compass\" ] || exit 0; if command -v python3 >/dev/null 2>&1; then python3 \"$CLAUDE_PROJECT_DIR/.claude/cli/compass\" capture-check --hook; else python \"$CLAUDE_PROJECT_DIR/.claude/cli/compass\" capture-check --hook; fi",
            }
        ],
    },
]

NOT_INSTALLED_GUARD = '[ -f "$CLAUDE_PROJECT_DIR/.claude/cli/compass" ] || exit 0; '
AGENT_PREFILTER = 'case "$input" in *agent_id*|*agent_type*) exit 0;; esac;'


def _shell():
    return shutil.which("sh") or shutil.which("bash")


class CompactionHooksTests(unittest.TestCase):
    """The SessionStart `compact` group and the PreCompact group run
    `session-state --hook` under the same guard and prefilter the
    context-check entry carries."""

    def setUp(self):
        self.hooks = self._manifest()["hooks"]

    def _manifest(self):
        return json.loads(HOOKS_JSON.read_text(encoding="utf-8"))

    def _compact_groups(self):
        return [g for g in self.hooks["SessionStart"] if g.get("matcher") == "compact"]

    def _precompact_groups(self):
        return self.hooks.get("PreCompact", [])

    def _session_state_hooks(self, groups):
        return [h for g in groups for h in g["hooks"] if "session-state" in h.get("command", "")]

    def _assert_hook_shape(self, hook):
        command = hook["command"]
        self.assertEqual(hook["type"], "command")
        self.assertEqual(hook["timeout"], 15)
        self.assertIn('compass" session-state --hook', command)
        self.assertTrue(command.startswith(NOT_INSTALLED_GUARD), command[:90])
        self.assertIn(AGENT_PREFILTER, command)
        # The prefilter must exit before any interpreter starts.
        self.assertLess(command.index(AGENT_PREFILTER), command.index("python"))
        self.assertNotIn("onFailure", hook)

    def test_sessionstart_compact_group_runs_session_state(self):
        # Adversarial where: the group is missing, matches more than the
        # compact source (e.g. `compact|startup`), or is duplicated so the
        # block would print twice after a compaction.
        groups = self._compact_groups()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["matcher"], "compact")
        self.assertEqual(len(groups[0]["hooks"]), 1)
        self._assert_hook_shape(groups[0]["hooks"][0])

    def test_precompact_group_is_matcherless_and_runs_session_state(self):
        # Adversarial where: the PreCompact key is absent, carries a
        # matcher that restricts it to manual or auto compactions, or holds
        # a second group.
        groups = self._precompact_groups()
        self.assertEqual(len(groups), 1)
        self.assertNotIn("matcher", groups[0])
        self.assertEqual(len(groups[0]["hooks"]), 1)
        self._assert_hook_shape(groups[0]["hooks"][0])

    def test_session_state_runs_nowhere_else_in_sessionstart(self):
        # Adversarial where: the command is also hung on the startup or the
        # matcherless group, running it at every session start.
        owners = [g for g in self.hooks["SessionStart"]
                  if self._session_state_hooks([g])]
        self.assertEqual([g.get("matcher") for g in owners], ["compact"])

    def test_other_sessionstart_groups_are_unchanged(self):
        # Adversarial where: adding the compact group rewrites or drops the
        # self-update or the capture-check group.
        others = [g for g in self._manifest()["hooks"]["SessionStart"]
                  if g.get("matcher") != "compact"]
        self.assertEqual(others, PRE_COMPACTION_SESSIONSTART_GROUPS)

    def test_description_mentions_both_registrations(self):
        # Adversarial where: the manifest description keeps describing only
        # the old events, so a reader of it cannot learn a compaction runs
        # the command.
        description = self._manifest()["description"]
        self.assertIn("PreCompact", description)
        self.assertIn("session-state", description)

    def _run_hook(self, command, event_text, install_cli):
        shell = _shell()
        if shell is None:
            self.skipTest("no POSIX shell available")
        project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, project, True)
        marker = project / "ran.txt"
        if install_cli:
            cli = project / ".claude" / "cli"
            cli.mkdir(parents=True)
            (cli / "compass").write_text(
                "import pathlib, sys\n"
                f"pathlib.Path({marker.as_posix()!r}).write_text(' '.join(sys.argv[1:]))\n",
                encoding="utf-8",
            )
        env = {**os.environ, "CLAUDE_PROJECT_DIR": project.as_posix()}
        result = subprocess.run(
            [shell, "-c", command], input=event_text, text=True,
            capture_output=True, env=env, timeout=60,
        )
        return result, marker

    def _commands(self):
        return [
            self._compact_groups()[0]["hooks"][0]["command"],
            self._precompact_groups()[0]["hooks"][0]["command"],
        ]

    def test_main_agent_event_reaches_the_cli(self):
        # Adversarial where: the prefilter inverts, so the main agent's
        # event exits early and no summary or state block is ever produced.
        for command in self._commands():
            result, marker = self._run_hook(command, '{"source": "compact"}', True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(marker.is_file(), command[:60])
            self.assertEqual(marker.read_text(encoding="utf-8"), "session-state --hook")

    def test_subagent_event_exits_before_python(self):
        # Adversarial where: a subagent event (agent_id or agent_type in
        # the payload) starts the interpreter, paying a Python start per
        # subagent compaction.
        for command in self._commands():
            for payload in ('{"agent_id": "a1"}', '{"agent_type": "builder"}'):
                result, marker = self._run_hook(command, payload, True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(marker.exists(), payload)

    def test_not_installed_project_exits_zero_silently(self):
        # Adversarial where: a project the plugin is loaded for but not set
        # up in gets a missing-file Python failure (exit 2 blocks a
        # compaction).
        for command in self._commands():
            result, marker = self._run_hook(command, '{"source": "compact"}', False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertFalse(marker.exists())


class MergeSettingsCompactionTests(unittest.TestCase):
    """`merge_settings` writes the compact and PreCompact entries into
    `.claude/settings.json` beside the user's own groups."""

    USER_SESSIONSTART = {
        "matcher": "compact",
        "hooks": [{"type": "command", "command": "echo my own compact hook"}],
    }
    USER_PRECOMPACT = {
        "hooks": [{"type": "command", "command": "echo my own precompact hook"}],
    }

    def _project(self):
        project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, project, True)
        (project / ".claude").mkdir()
        (project / ".claude" / "settings.json").write_text(
            json.dumps({
                "permissions": {"allow": ["Bash(ls)"]},
                "hooks": {
                    "SessionStart": [self.USER_SESSIONSTART],
                    "PreCompact": [self.USER_PRECOMPACT],
                },
            }),
            encoding="utf-8",
        )
        return project

    def _merged(self, project):
        return json.loads(
            (project / ".claude" / "settings.json").read_text(encoding="utf-8"))

    def test_both_entries_land_and_user_groups_survive(self):
        # Adversarial where: the merge replaces the whole SessionStart or
        # PreCompact list (dropping a user group that shares the `compact`
        # matcher), or skips the new PreCompact event.
        project = self._project()
        self_update.merge_settings(project, HOOKS_JSON)
        settings = self._merged(project)
        self.assertEqual(settings["permissions"], {"allow": ["Bash(ls)"]})

        start = settings["hooks"]["SessionStart"]
        self.assertIn(self.USER_SESSIONSTART, start)
        compass_compact = [
            g for g in start
            if any("session-state --hook" in h["command"] for h in g["hooks"])
        ]
        self.assertEqual(len(compass_compact), 1)
        self.assertEqual(compass_compact[0]["matcher"], "compact")

        pre = settings["hooks"]["PreCompact"]
        self.assertIn(self.USER_PRECOMPACT, pre)
        compass_pre = [
            g for g in pre
            if any("session-state --hook" in h["command"] for h in g["hooks"])
        ]
        self.assertEqual(len(compass_pre), 1)
        self.assertNotIn("matcher", compass_pre[0])

    def test_second_merge_adds_no_duplicates(self):
        # Adversarial where: a re-run on update stacks a second compass
        # compact group beside the first.
        project = self._project()
        self_update.merge_settings(project, HOOKS_JSON)
        first = self._merged(project)
        self_update.merge_settings(project, HOOKS_JSON)
        self.assertEqual(self._merged(project), first)
