"""Tests for two properties of a live control-loop run.

* `compass loop status` shows the reading a run took. A run that ended at a
  gate (throttled) records only `reading_before`; status falls back to it when
  the latest run row has no `reading_after`.
* The headless actuator runs with `--strict-mcp-config`, so it sees only the
  tools its `loop.json` allows and never the user's MCP servers.
"""

import os
import sys
import unittest

CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CLI_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_loop_command import LoopCommandCase  # noqa: E402
from test_looprunner import RunnerHarness  # noqa: E402


def reading_line(out):
    (line,) = [l for l in out.splitlines() if "last reading" in l]
    return line


class StatusLastReadingTests(LoopCommandCase):
    def status_line(self, folder):
        code, out, err = self.loop("status", "LOOP-001")
        self.assertEqual(code, 0, err)
        return reading_line(out)

    def test_gate_ended_run_shows_its_before_reading(self):
        """Defect class: a run that ended at the gate has only
        `reading_before`, and status printed `none` for it."""
        folder = self.new_loop("remove-bad")
        self.add_run(
            folder, "r-gate", "throttled",
            reading_before={"value": 10, "items_count": 3}, reading_after=None,
        )
        line = self.status_line(folder)
        self.assertIn("value 10, 3 items", line)
        self.assertNotIn("none", line)

    def test_reading_after_wins_over_reading_before(self):
        """Defect class: the fallback replacing the re-sensed reading of a
        completed run."""
        folder = self.new_loop("remove-bad")
        self.add_run(
            folder, "r-done", "helpful",
            reading_before={"value": 10, "items_count": 3},
            reading_after={"value": 8, "items_count": 2},
        )
        line = self.status_line(folder)
        self.assertIn("value 8, 2 items", line)
        self.assertNotIn("value 10", line)

    def test_only_the_latest_run_row_supplies_the_reading(self):
        """Defect class: falling back past the latest run row to an older
        row's reading when the latest has none at all."""
        folder = self.new_loop("remove-bad")
        self.add_run(
            folder, "r-old", "helpful",
            reading_before={"value": 10, "items_count": 3},
            reading_after={"value": 8, "items_count": 2},
        )
        self.add_run(folder, "r-new", "failed")
        self.assertIn("none", self.status_line(folder))

    def test_no_run_row_shows_none(self):
        folder = self.new_loop("remove-bad")
        self.assertIn("none", self.status_line(folder))


class ActuatorStrictMcpTests(RunnerHarness):
    def test_actuator_argv_carries_strict_mcp_config(self):
        """Defect class: the actuator inheriting the user's MCP servers
        (a live run created `.serena/` in the project)."""
        self.new_loop()
        self.assertEqual(self.iterate()[0], 0)
        (call,) = self.calls()
        argv = call["argv"]
        self.assertEqual(argv.count("--strict-mcp-config"), 1)

    def test_strict_mcp_config_does_not_swallow_the_allowed_tools(self):
        """Defect class: the new flag landing between `--allowedTools` and its
        value, or dropping the allowed list."""
        self.new_loop(definition={"allowed_tools": ["Read", "Grep"]})
        self.assertEqual(self.iterate()[0], 0)
        (call,) = self.calls()
        argv = call["argv"]
        value = argv[argv.index("--allowedTools") + 1]
        self.assertEqual(sorted(value.split(",")), ["Grep", "Read"])


if __name__ == "__main__":
    unittest.main()
