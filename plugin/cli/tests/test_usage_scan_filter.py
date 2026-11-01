"""Tests for the plugin filter of `compass loop usage-scan`: the usage file
keeps only keys whose source file exists under the plugin tree, so a skill or
agent the user defined never reaches it.

Transcripts and plugin trees are built in temp dirs; HOME and USERPROFILE
point at a temp home so no default path reaches the real one.

Adversarial themes: a user-defined skill or agent name (which may be named
after a private project) surviving into the usage file through a Skill call,
an Agent call, a Read path or a nested file; a key kept because its skill
folder exists although the file does not; a path-traversal key resolving to a
real file outside the plugin tree; and an unfiltered default.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPASS = os.path.join(CLI_DIR, "compass")

PRIVATE_SKILL = "acme-client-deploy"
PRIVATE_AGENT = "acme-reviewer"


def tool_use(name, **tool_input):
    return {"type": "tool_use", "id": "toolu_01", "name": name, "input": tool_input}


def assistant(*blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


class ScanFilterTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.tmp = tmp
        (tmp / "home").mkdir()
        (tmp / "work").mkdir()
        self.projects = tmp / "projects"
        self.plugin = tmp / "plugin"
        for rel in ("skills/build/SKILL.md", "skills/build/ref/deep.md",
                    "templates/agents/tester.md"):
            (self.plugin / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.plugin / rel).write_text("x", encoding="utf-8")
        # Files the plugin ships that no skill or agent key names directly, so
        # only a `..` hop reaches them.
        (self.plugin / "outside.md").write_text("x", encoding="utf-8")
        (self.plugin / "outside").mkdir()
        (self.plugin / "outside" / "SKILL.md").write_text("x", encoding="utf-8")

    def session(self, *blocks, name="s.jsonl"):
        path = self.projects / "p1" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(assistant(*blocks)) + "\n", encoding="utf-8")

    def scan(self, *extra, plugin=True):
        out = self.tmp / "usage.json"
        args = ["usage-scan", "--projects", str(self.projects), "--out", str(out)]
        if plugin:
            args += ["--plugin", str(self.plugin)]
        env = dict(os.environ, HOME=str(self.tmp / "home"), USERPROFILE=str(self.tmp / "home"),
                   CLAUDE_PROJECT_DIR=str(self.tmp / "work"), PYTHONIOENCODING="utf-8")
        proc = subprocess.run([sys.executable, COMPASS, "loop", *args, *extra],
                              capture_output=True, text=True, encoding="utf-8", env=env,
                              cwd=str(self.tmp / "work"), timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return out.read_bytes().decode("utf-8"), json.loads(out.read_text(encoding="utf-8"))

    def test_user_defined_skill_and_agent_names_never_reach_the_file(self):
        """Adversarial where: the filter is missing, or applied to some call
        shapes only, so a private skill or agent name is written beside the
        Compass ones."""
        self.session(
            tool_use("Skill", skill=PRIVATE_SKILL),
            tool_use("Skill", skill="compass:" + PRIVATE_SKILL),
            tool_use("Agent", subagent_type=PRIVATE_AGENT, prompt="x"),
            tool_use("Task", subagent_type=PRIVATE_AGENT, prompt="x"),
            tool_use("Read", file_path=f"C:\\w\\.claude\\skills\\{PRIVATE_SKILL}\\SKILL.md"),
            tool_use("Read", file_path=f"/w/.claude/agents/{PRIVATE_AGENT}.md"),
            tool_use("Skill", skill="build"),
            tool_use("Agent", subagent_type="tester", prompt="x"),
        )
        raw, data = self.scan()
        for fragment in (PRIVATE_SKILL, PRIVATE_AGENT, "acme"):
            self.assertNotIn(fragment, raw.lower())
        self.assertEqual(data["loads"], {"skills/build/SKILL.md": 1,
                                         "templates/agents/tester.md": 1})
        self.assertEqual(data["sessions"], 1)

    def test_a_key_needs_its_own_file_not_just_an_existing_skill_folder(self):
        """Adversarial where: the filter checks the skill or agent name only,
        so a nested file the plugin does not ship is kept."""
        self.session(
            tool_use("Read", file_path="/w/.claude/skills/build/ref/deep.md"),
            tool_use("Read", file_path="/w/.claude/skills/build/ref/missing.md"),
            tool_use("Read", file_path="/w/.claude/skills/build/notes-for-acme.md"),
        )
        raw, data = self.scan()
        self.assertEqual(data["loads"], {"skills/build/ref/deep.md": 1})
        self.assertNotIn("acme", raw)

    def test_keys_that_climb_out_of_the_plugin_tree_are_dropped(self):
        """Adversarial where: a `..` hop in a Read path or a Skill name
        reaches a real plugin file that is not a skill or agent source, which
        passes an `is_file` test."""
        self.session(tool_use("Read", file_path="/w/.claude/skills/build/../../outside.md"),
                     tool_use("Skill", skill="../outside"))
        _, data = self.scan()
        self.assertEqual(data["loads"], {})

    def test_a_session_calling_only_private_sources_still_counts_when_compass_is_traced(self):
        """Adversarial where: dropping a key also drops the session's Compass
        trace, so the sessions total (the weights' denominator) shrinks."""
        self.session(tool_use("Skill", skill=PRIVATE_SKILL),
                     tool_use("Bash", command="compass status"))
        _, data = self.scan()
        self.assertEqual((data["sessions"], data["loads"]), (1, {}))

    def hook(self, command):
        path = self.projects / "p1" / "hook.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"type": "attachment", "attachment": {
            "type": "hook_success", "command": command}}) + "\n", encoding="utf-8")

    def test_only_a_call_of_the_compass_cli_marks_a_session(self):
        """Adversarial where: the word `compass` anywhere in a tool input
        (a repository path, an echo, a grep pattern) marks the session, which
        inflates the sessions total and dilutes every weight; or a real CLI
        invocation form (path, interpreter, chained, environment prefix) is
        missed."""
        rows = {
            "read of a file in a compass checkout": (
                [tool_use("Read", file_path="F:/x/plugins/compass/README.md")], 0),
            "bash in a compass checkout": (
                [tool_use("Bash", command="cd F:/x/plugins/compass && ls")], 0),
            "echo of the word": (
                [tool_use("Bash", command="echo compass")], 0),
            "grep for the word": (
                [tool_use("Bash", command="grep -r compass README.md")], 0),
            "a program whose name only contains compass": (
                [tool_use("Bash", command="compassion --help")], 0),
            "bare command": ([tool_use("Bash", command="compass sync")], 1),
            "installed cli path": ([tool_use("Bash", command=".claude/cli/compass sync")], 1),
            "windows cli path": ([tool_use("Bash", command="F:\\p\\.claude\\cli\\compass sync")], 1),
            "python and maincli": (
                [tool_use("Bash", command="python plugin/cli/maincli.py loop status")], 1),
            "interpreter flag and cli path": (
                [tool_use("Bash", command="python -I .claude/cli/compass sync")], 1),
            "environment prefix": ([tool_use("Bash", command="FOO=1 compass sync")], 1),
            "chained after another command": (
                [tool_use("Bash", command="cd /w && compass sync")], 1),
        }
        for name, (blocks, expected) in rows.items():
            with self.subTest(name):
                shutil.rmtree(self.projects, ignore_errors=True)
                self.session(*blocks)
                _, data = self.scan()
                self.assertEqual(data["sessions"], expected)

    def test_a_hook_that_runs_the_cli_marks_a_session_and_other_hooks_do_not(self):
        """Adversarial where: hook entries are ignored, or any hook whose
        text contains the word marks the session."""
        self.hook("python3 .claude/cli/compass sync")
        _, data = self.scan()
        self.assertEqual(data["sessions"], 1)
        shutil.rmtree(self.projects)
        self.hook("echo compass")
        _, data = self.scan()
        self.assertEqual(data["sessions"], 0)

    def test_a_missing_projects_folder_fails_and_leaves_an_existing_file_alone(self):
        """Adversarial where: a mistyped `--projects` scans nothing and
        overwrites the machine's good usage file with zero sessions."""
        out = self.tmp / "usage.json"
        out.write_text('{"sessions": 9}', encoding="utf-8")
        env = dict(os.environ, HOME=str(self.tmp / "home"), USERPROFILE=str(self.tmp / "home"),
                   CLAUDE_PROJECT_DIR=str(self.tmp / "work"), PYTHONIOENCODING="utf-8")
        proc = subprocess.run(
            [sys.executable, COMPASS, "loop", "usage-scan", "--projects",
             str(self.tmp / "no-such-folder"), "--out", str(out), "--plugin", str(self.plugin)],
            capture_output=True, text=True, encoding="utf-8", env=env,
            cwd=str(self.tmp / "work"), timeout=120)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("no-such-folder", proc.stderr)
        self.assertEqual(out.read_text(encoding="utf-8"), '{"sessions": 9}')

    def test_default_plugin_is_the_shipped_one_and_filters_private_names(self):
        """Adversarial where: omitting `--plugin` disables the filter instead
        of using the plugin folder the CLI ships in."""
        self.session(tool_use("Skill", skill=PRIVATE_SKILL),
                     tool_use("Skill", skill="plan"))
        raw, data = self.scan(plugin=False)
        self.assertNotIn("acme", raw)
        self.assertEqual(data["loads"], {"skills/plan/SKILL.md": 1})


if __name__ == "__main__":
    unittest.main()
