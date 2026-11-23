"""Tests for `plugin/hooks/hooks.json`: every hook entry is a command, never
an agent, and every command string names a subcommand the CLI actually
registers. This is the guard against the class of drift where a hook is
edited to invoke a command that was renamed or never added to
`COMMAND_SPECS`."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import maincli  # noqa: E402
from commands import self_update  # noqa: E402
from test_drift_hook import LOCK, log_row, log_rows, plain_repo, write_log  # noqa: E402
from test_self_update import PLUGIN_YAML, make_plugin_tree  # noqa: E402

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
AGENT_PREFILTER = "case \"$input\" in *'\"agent_id\"'*|*'\"agent_type\"'*) exit 0;; esac;"


def _shell():
    return shutil.which("sh") or shutil.which("bash")


DRIFT_STATUS = "Checking the vault's references against the code"
DRIFT_COMMAND = (
    '[ -f "$CLAUDE_PROJECT_DIR/.claude/cli/compass" ] || exit 0; '
    'if command -v python3 >/dev/null 2>&1; then '
    'python3 "$CLAUDE_PROJECT_DIR/.claude/cli/compass" drift --hook; '
    'else python "$CLAUDE_PROJECT_DIR/.claude/cli/compass" drift --hook; fi'
)


class DriftScanHookTests(unittest.TestCase):
    """The SessionStart `startup` entry that runs `drift --hook`."""

    def setUp(self):
        self.hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]

    def _drift_hooks(self):
        return [(g.get("matcher"), h)
                for event, groups in self.hooks.items() if event == "SessionStart"
                for g in groups for h in g["hooks"] if "drift" in h.get("command", "")]

    def test_startup_registers_the_drift_scan_once_with_the_neighbour_guard(self):
        # Adversarial where: the entry is missing, sits under another event
        # or matcher (a scan on every resume, clear and compaction), runs
        # without the not-installed guard (fails a session in a project
        # Compass is not set up in), tries only python3 or only python, or
        # carries no plain status text so the session shows a blank line.
        found = self._drift_hooks()
        self.assertEqual([m for m, _ in found], ["startup"])
        hook = found[0][1]
        self.assertEqual(hook["type"], "command")
        self.assertEqual(hook["command"], DRIFT_COMMAND)
        self.assertEqual(hook["statusMessage"], DRIFT_STATUS)
        self.assertGreater(hook["timeout"], 0)
        elsewhere = [e for e, groups in self.hooks.items() if e != "SessionStart"
                     for g in groups for h in g["hooks"] if "drift" in h.get("command", "")]
        self.assertEqual(elsewhere, [])


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
        # Adversarial where: adding the compact group or the drift scan
        # rewrites or drops the self-update or the capture-check group. The
        # drift hook is set aside, wherever it sits, before the comparison.
        others = []
        for group in self._manifest()["hooks"]["SessionStart"]:
            if group.get("matcher") == "compact":
                continue
            kept = [h for h in group["hooks"] if "drift" not in h["command"]]
            if kept:
                others.append({**group, "hooks": kept})
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


CLI_ROOT = Path(__file__).resolve().parents[1]


class CompactionHookExecutionTests(unittest.TestCase):
    """The compaction hook command strings run through `sh` against a
    project with the real CLI installed: event shapes the host sends, shell
    quoting of the event on its way to the CLI, and the interpreter-choice
    branch."""

    def setUp(self):
        manifest = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
        compact = [g for g in manifest["SessionStart"] if g.get("matcher") == "compact"]
        self.commands = {
            "SessionStart": compact[0]["hooks"][0]["command"],
            "PreCompact": manifest["PreCompact"][0]["hooks"][0]["command"],
        }
        self.shell = _shell()
        if self.shell is None:
            self.skipTest("no POSIX shell available")

    def _project(self, real_cli=True, name="proj"):
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        project = base / name
        (project / ".compass").mkdir(parents=True)
        if real_cli:
            shutil.copytree(
                CLI_ROOT, project / ".claude" / "cli",
                ignore=shutil.ignore_patterns("tests", "__pycache__", ".ruff_cache"))
        return project

    def _stub_cli(self, project, body):
        cli = project / ".claude" / "cli"
        cli.mkdir(parents=True)
        (cli / "compass").write_text(body, encoding="utf-8")

    def _run(self, project, command, event, env_extra=None):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": project.as_posix()}
        env.pop("COMPASS_WORKER_SESSION", None)
        env.update(env_extra or {})
        return subprocess.run(
            [self.shell, "-c", command], input=event, text=True,
            capture_output=True, env=env, cwd=project, timeout=120)

    def test_sessionstart_compact_prints_one_json_context_object(self):
        # Adversarial where: the hook's stdout is not a single JSON object
        # with hookSpecificOutput.additionalContext, so the host cannot
        # inject the state block after a compaction.
        project = self._project()
        event = json.dumps({"hook_event_name": "SessionStart", "source": "compact"})
        result = self._run(project, self.commands["SessionStart"], event)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIsInstance(out["hookSpecificOutput"]["additionalContext"], str)

    def test_precompact_prints_plain_summary_instructions(self):
        # Adversarial where: PreCompact output is wrapped as JSON (the host
        # reads PreCompact stdout as plain text) or is empty.
        project = self._project()
        event = json.dumps({"hook_event_name": "PreCompact", "trigger": "auto"})
        result = self._run(project, self.commands["PreCompact"], event)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("When summarizing"), result.stdout[:80])

    def test_sessionstart_sources_other_than_compact_print_nothing(self):
        # Adversarial where: a startup or resume event reaching the command
        # (a hand-merged settings file may drop the matcher) prints the
        # state block into a fresh session.
        project = self._project()
        for source in ("startup", "resume", "clear"):
            event = json.dumps({"hook_event_name": "SessionStart", "source": source})
            result = self._run(project, self.commands["SessionStart"], event)
            self.assertEqual((result.returncode, result.stdout), (0, ""), source)

    def test_malformed_and_empty_events_exit_zero_silently(self):
        # Adversarial where: a truncated or empty stdin raises out of the
        # JSON parse and the hook exits non-zero (exit 2 blocks the
        # compaction), or prints a traceback into the context.
        project = self._project()
        for event in ("", "   \n", "{not json", "[1, 2]", "null"):
            for name, command in self.commands.items():
                result = self._run(project, command, event)
                self.assertEqual(result.returncode, 0, (name, event, result.stderr))
                self.assertEqual(result.stdout, "", (name, event))

    def test_subagent_events_print_nothing_with_real_cli(self):
        # Adversarial where: a subagent's PreCompact receives the main
        # agent's summary instructions, or its SessionStart receives a state
        # block built from the main transcript.
        project = self._project()
        for name, command in self.commands.items():
            event = json.dumps({"hook_event_name": name, "source": "compact",
                                "agent_id": "a1", "agent_type": "builder"})
            result = self._run(project, command, event)
            self.assertEqual((result.returncode, result.stdout), (0, ""), name)

    def test_project_path_with_spaces_reaches_the_cli(self):
        # Adversarial where: an unquoted $CLAUDE_PROJECT_DIR splits at the
        # space, so the existence check or the interpreter call fails on a
        # project under a path like `My Projects`.
        project = self._project(name="my projects")
        event = json.dumps({"hook_event_name": "PreCompact"})
        result = self._run(project, self.commands["PreCompact"], event)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("When summarizing"), result.stdout[:80])

    def test_event_text_reaches_the_cli_byte_for_byte(self):
        # Adversarial where: the event is forwarded through a printf format
        # string or echo, so `%` sequences, backslash escapes or a leading
        # `-n` are interpreted and the CLI parses a different payload.
        project = self._project(real_cli=False)
        sink = project / "stdin.txt"
        self._stub_cli(
            project,
            "import pathlib, sys\n"
            f"pathlib.Path({sink.as_posix()!r}).write_bytes(sys.stdin.buffer.read())\n")
        payload = ('{"hook_event_name":"PreCompact","custom_instructions":'
                   '"100%s %d \\\\n \\t -n -e \\u00e9 $HOME `x`"}')
        for command in self.commands.values():
            sink.unlink(missing_ok=True)
            result = self._run(project, command, payload)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(sink.read_bytes().decode("utf-8"), payload)

    def _fake_interpreters(self, names):
        bindir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, bindir, True)
        log = bindir / "log.txt"
        for name in names:
            script = bindir / name
            script.write_bytes((
                "#!/bin/sh\n"
                f'echo "{name} $(basename "$1") $2 $3 stdin=$(cat)" >> "{log.as_posix()}"\n'
            ).encode("utf-8"))
            script.chmod(0o755)
        return bindir, log

    def _path_without_python(self, bindir):
        path = os.pathsep.join([str(bindir), str(Path(self.shell).parent)])
        probe = subprocess.run(
            [self.shell, "-c", "command -v python3 >/dev/null 2>&1"],
            env={**os.environ, "PATH": path}, capture_output=True, text=True)
        return path, probe.returncode == 0

    def test_falls_back_to_python_when_python3_is_absent(self):
        # Adversarial where: the else branch (a machine with only `python`)
        # drops the event from stdin or the subcommand from argv, since it
        # is a separate copy of the pipeline from the python3 branch.
        bindir, log = self._fake_interpreters(["python"])
        path, found = self._path_without_python(bindir)
        if found:
            self.skipTest("python3 is on the minimal PATH")
        project = self._project(real_cli=False)
        self._stub_cli(project, "")
        for command in self.commands.values():
            log.unlink(missing_ok=True)
            result = self._run(project, command, '{"source":"compact"}', {"PATH": path})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                log.read_text(encoding="utf-8").strip(),
                'python compass session-state --hook stdin={"source":"compact"}')

    def test_python3_is_preferred_and_receives_the_event(self):
        # Adversarial where: both interpreters run (double output), or the
        # python3 branch loses the event on stdin.
        bindir, log = self._fake_interpreters(["python3", "python"])
        path, _ = self._path_without_python(bindir)
        project = self._project(real_cli=False)
        self._stub_cli(project, "")
        for command in self.commands.values():
            log.unlink(missing_ok=True)
            result = self._run(project, command, '{"source":"compact"}', {"PATH": path})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                log.read_text(encoding="utf-8").strip(),
                'python3 compass session-state --hook stdin={"source":"compact"}')

    def test_main_agent_event_mentioning_agent_id_text_is_not_skipped(self):
        # Adversarial where: the shell prefilter matches the substring
        # `agent_id` anywhere in the raw event, so a main-agent PreCompact
        # whose `custom_instructions` (text the human typed after /compact)
        # mentions agent_id or agent_type exits before Python and the
        # summary instructions are never delivered. The CLI's own check is
        # key-based, so the shell is wider than the contract it mirrors.
        project = self._project()
        event = json.dumps({"hook_event_name": "PreCompact",
                            "custom_instructions": "keep the agent_id handling notes"})
        result = self._run(project, self.commands["PreCompact"], event)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("When summarizing"), repr(result.stdout[:60]))


# The `--hook` subcommands every SessionStart group other than `compact` runs.
# Each prints nothing on a run where nothing happened, so the text the host
# adds to a session's first request stays identical from one start to the next.
SILENT_SESSIONSTART_COMMANDS = ["capture-check --hook", "drift --hook", "self-update --hook"]
HOOK_SUBCOMMAND = re.compile(r'compass" (\S+ --hook)')


def non_compaction_sessionstart_commands(manifest):
    """The `<subcommand> --hook` of every command in the SessionStart groups
    that do not carry the `compact` matcher, sorted."""
    found = []
    for group in manifest["hooks"]["SessionStart"]:
        if group.get("matcher") == "compact":
            continue
        for hook in group["hooks"]:
            match = HOOK_SUBCOMMAND.search(hook["command"])
            found.append(match.group(1) if match else hook["command"])
    return sorted(found)


def assert_sessionstart_commands_are_pinned(case, manifest):
    case.assertEqual(
        non_compaction_sessionstart_commands(manifest), SILENT_SESSIONSTART_COMMANDS)


class SessionStartSilenceTests(unittest.TestCase):
    """SessionStart output is added to the session's first request, so a hook
    that prints there, or prints something that varies, changes the cached
    start. The commands of the `startup` group and of the group without a
    matcher are fixed here, and each prints nothing on a no-op run."""

    def _manifest(self):
        return json.loads(HOOKS_JSON.read_text(encoding="utf-8"))

    def test_the_non_compaction_sessionstart_commands_are_exactly_the_silent_three(self):
        # Adversarial where: a new SessionStart command joins the startup or
        # matcherless group without a silence case below, a listed one is
        # duplicated or dropped, or the helper compares nothing and passes on
        # a manifest it should reject.
        assert_sessionstart_commands_are_pinned(self, self._manifest())

        for name, change in (
            ("a fourth startup command", lambda groups: groups[0]["hooks"].append({
                "type": "command",
                "command": '[ -f "$CLAUDE_PROJECT_DIR/.claude/cli/compass" ] || exit 0; '
                           'python "$CLAUDE_PROJECT_DIR/.claude/cli/compass" banner --hook',
            })),
            ("a duplicated listed command", lambda groups: groups[0]["hooks"].append(
                dict(groups[0]["hooks"][0]))),
            ("a dropped listed command", lambda groups: groups[0]["hooks"].pop()),
        ):
            with self.subTest(name):
                doctored = self._manifest()
                change(doctored["hooks"]["SessionStart"])
                with self.assertRaises(AssertionError):
                    assert_sessionstart_commands_are_pinned(self, doctored)

    def test_the_compact_group_is_outside_the_pinned_set(self):
        # Adversarial where: the helper counts the compact group, so the one
        # command allowed to print (the state block after a compaction) fails
        # the pin, or a command moved into that group escapes it unseen.
        commands = non_compaction_sessionstart_commands(self._manifest())
        self.assertNotIn("session-state --hook", commands)
        doctored = self._manifest()
        doctored["hooks"]["SessionStart"][-1]["hooks"].append({
            "type": "command", "command": 'x compass" banner --hook'})
        self.assertEqual(
            non_compaction_sessionstart_commands(doctored), SILENT_SESSIONSTART_COMMANDS)

    def _run(self, project, args, stdin="", env_extra=None):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project),
               "DSH_HOME": str(Path(project).parent / "no-dsh-home")}
        env.pop("COMPASS_WORKER_SESSION", None)
        env.update(env_extra or {})
        return subprocess.run(
            [sys.executable, str(CLI_ROOT / "compass"), *args],
            input=stdin, capture_output=True, text=True, env=env,
            cwd=str(project), timeout=120)

    def _assert_silent(self, done):
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""))

    def test_self_update_in_local_mode_at_the_installed_version_prints_nothing(self):
        # Adversarial where: an up-to-date install prints a refresh notice, or
        # an unreachable network turns a check that needs none into a banner or
        # a traceback.
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        project = base / "project"
        (project / ".compass" / "meta").mkdir(parents=True)
        (project / ".claude").mkdir()
        make_plugin_tree(project / "plugin", version="0.9.0")
        (project / ".compass" / "meta" / "plugin.yaml").write_text(
            PLUGIN_YAML.format(source=str(project / "plugin")), encoding="utf-8")
        unreachable = {"HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9",
                       "GIT_TERMINAL_PROMPT": "0"}
        self._assert_silent(self._run(project, ["self-update", "--hook"], env_extra=unreachable))

    def test_capture_check_below_its_interval_with_no_signal_prints_nothing(self):
        # Adversarial where: the SessionStart event on stdin or the first turn
        # bump makes the pickup print, or open an opportunity, when nothing is
        # open and nothing is due.
        project = plain_repo(self)
        event = json.dumps({"hook_event_name": "SessionStart", "source": "startup"})
        self._assert_silent(self._run(project, ["capture-check", "--hook"], stdin=event))
        self.assertEqual(
            list((Path(project) / ".compass" / "tmp").glob("capture-opportunities/*")), [])

    def test_drift_with_the_newest_row_at_head_prints_nothing_and_spawns_no_scan(self):
        # Adversarial where: an unchanged HEAD still starts a scan (a lock
        # file appears, a new log row follows) or announces that it did not.
        project = plain_repo(self)
        head = subprocess.run(
            ["git", "-C", str(project), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True).stdout.strip()
        write_log(project, [log_row(head)])
        self._assert_silent(self._run(project, ["drift", "--hook"]))
        self.assertFalse((Path(project) / LOCK).exists())
        self.assertEqual([row["head"] for row in log_rows(project)], [head])
