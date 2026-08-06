"""Tests for `plugin/hooks/hooks.json`: every hook entry is a command, never
an agent, and every command string names a subcommand the CLI actually
registers. This is the guard against the class of drift where a hook is
edited to invoke a command that was renamed or never added to
`COMMAND_SPECS`."""

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maincli  # noqa: E402

HOOKS_JSON = (
    Path(__file__).resolve().parents[2] / "hooks" / "hooks.json"
)

ORIGINAL_SUBAGENTSTOP_MATCHER = (
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

    def test_subagentstop_matcher_preserved(self):
        group = self.data["hooks"]["SubagentStop"][0]
        self.assertEqual(group["matcher"], ORIGINAL_SUBAGENTSTOP_MATCHER)

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
            self.assertIn("else python ", command)


if __name__ == "__main__":
    unittest.main()
