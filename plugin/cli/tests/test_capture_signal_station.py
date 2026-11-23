"""Adversarial tests for the station row `capture-signal --hook` appends to
`.compass/meta/station-log.jsonl` beside the capture it already writes.

Themes: one spawn gives one row (SubagentStop re-delivery included), nothing
is recorded for a malformed event or a worker session, a failing log write
never costs the capture or the exit code, and a row holds no report text.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CLI_DIR)

import capturelib  # noqa: E402
from commands import capture_signal  # noqa: E402

BUGS = [
    "**One:** `a.py:1` - repro: x - expected: 1 / actual: 2",
    "**Two:** `b.py:2` - repro: y - expected: 1 / actual: 3",
    "**Three:** `c.py:3` - repro: z - expected: 1 / actual: 4",
]


def post_build_report(bugs, marker="NEVERLOGGED-line-5521"):
    lines = ["## Test Report", "", "### Mode", "Post-build", "",
             "### Checkpoint Verification",
             "**Command:** `compass test-checkpoint verify TASK-346 --against-run r.txt`", "",
             "### Bugs Found"]
    lines += [f"- {b}" for b in bugs]
    lines += ["", "### Coverage", f"- Not covered: {marker}"]
    return "\n".join(lines) + "\n"


class StationRowCase(unittest.TestCase):
    def setUp(self):
        self.project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.project, True)
        self.root = self.project / ".compass"
        self.root.mkdir()
        saved = {k: os.environ.get(k) for k in
                 ("CLAUDE_PROJECT_DIR", "COMPASS_WORKER_SESSION", "COMPASS_MODEL_TESTER")}
        self.addCleanup(self._restore, saved)
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        os.environ.pop("COMPASS_WORKER_SESSION", None)
        os.environ["COMPASS_MODEL_TESTER"] = "claude-env-pin-7"

    @staticmethod
    def _restore(saved):
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    @property
    def log(self):
        return self.root / "meta" / "station-log.jsonl"

    def rows(self):
        if not self.log.is_file():
            return []
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines() if x.strip()]

    def deliver(self, payload):
        self.addCleanup(setattr, sys, "stdin", sys.stdin)
        sys.stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
        with redirect_stdout(io.StringIO()):
            return capture_signal.run(["--hook"])

    def spawn(self, agent_type, message, agent_id="agent-1", **extra):
        event = {"agent_type": agent_type, "agent_id": agent_id, "last_assistant_message": message}
        event.update(extra)
        return self.deliver(event)


class StationRowTests(StationRowCase):
    def test_each_station_appends_one_row_with_task_station_counts_and_model(self):
        """Adversarial where: a checking spawn finishes and no row, or a row
        missing the task, station, count or model, lands in the log. One
        row per station form, delivered through the real hook entry."""
        rows = {
            "tester post-build, three bugs": (
                "tester", post_build_report(BUGS), "tester-post", {"bugs": 3}),
            "tester pre-build": (
                "tester",
                "## Test Report\n\n### Mode\nPre-build\n\n### Tests Written\n- t\n\n"
                "### Red Evidence\n**Command:** `pytest` for TASK-346\n",
                "tester-pre", {}),
            "validator with one failing phase row": (
                "validator",
                "## Validation Report: [[PLAN-034-x]]\n\n### Phase Results\n"
                "| Task | Status | Checks | Classification |\n|---|---|---|---|\n"
                "| TASK-346: a | [x] done | 3/3 passed | Matches plan |\n"
                "| TASK-347: b | [x] done | 1/3 passed | FAIL |\n\nVERDICT: FAIL\n",
                "validator", {"result": "FAIL", "fails": 1}),
            "builder": (
                "builder", "## Build Report\n\n### Task\nTASK-346 ([[PLAN-034-x]] Phase 1)\n\n### Changes\n- `a.py` - x\n",
                "builder", {}),
            "debug": ("debug", "## Debug Report: boom\n\n### Root Cause\nx\n\nCONFIDENCE: HIGH - y\n", "debug", {}),
        }
        for name, (agent, message, station, counts) in rows.items():
            with self.subTest(name=name):
                before = len(self.rows())
                code = self.spawn(agent, message, agent_id=f"id-{station}")
                self.assertEqual(code, 0)
                new = self.rows()[before:]
                self.assertEqual(len(new), 1)
                self.assertEqual(new[0]["station"], station)
                self.assertEqual(new[0]["agent_type"], agent)
                if agent in ("tester", "builder"):
                    self.assertEqual(new[0]["task"], "TASK-346")
                for key, value in counts.items():
                    self.assertEqual(new[0][key], value)
                self.assertTrue(new[0]["model"])
                self.assertTrue(new[0]["model_source"])

    def test_row_matches_the_environment_resolved_model_for_a_plugin_scoped_type(self):
        """Adversarial where: the plugin-scoped `compass:tester` type is
        resolved as an unknown agent, so the row carries the inherit default
        instead of the configured model."""
        self.spawn("compass:tester", post_build_report(BUGS[:2]))
        row = self.rows()[0]
        self.assertEqual(row["model"], "claude-env-pin-7")
        self.assertEqual(row["model_source"], "env")
        self.assertEqual(row["bugs"], 2)

    def test_no_line_of_the_report_reaches_the_log(self):
        """Adversarial where: the row, or any file the station write
        creates, keeps report text. A unique marker sits in a line of the
        report outside every parsed section."""
        self.spawn("tester", post_build_report(BUGS, marker="NEVERLOGGED-line-5521"))
        self.assertEqual(len(self.rows()), 1)
        self.assertNotIn("NEVERLOGGED-line-5521", self.log.read_text(encoding="utf-8"))
        for line in post_build_report(BUGS).splitlines():
            if len(line.strip()) >= 12:
                self.assertNotIn(line.strip(), self.log.read_text(encoding="utf-8"))

    def test_redelivery_of_one_completion_appends_one_row(self):
        """Adversarial where: the harness delivers SubagentStop twice for
        one completion (same agent_id), and the row is appended before the
        re-delivery check, doubling the spawn counts."""
        self.spawn("tester", post_build_report(BUGS), agent_id="dup-1")
        self.spawn("tester", post_build_report(BUGS), agent_id="dup-1")
        self.assertEqual(len(self.rows()), 1)
        self.spawn("tester", post_build_report(BUGS), agent_id="dup-2")
        self.assertEqual(len(self.rows()), 2)

    def test_concurrent_redeliveries_of_one_completion_append_one_row(self):
        """Adversarial where: the harness delivers SubagentStop twice for one
        completion as concurrent processes (same agent_id), and each reads the
        capture state before another has saved the id, so each records. Every
        process stalls inside the state read to hold that window open; the
        capture files, the signals and the rows must still be one each."""
        driver = (
            "import sys, time\n"
            f"sys.path.insert(0, {CLI_DIR!r})\n"
            "import capturelib\n"
            "from commands import capture_signal\n"
            "real = capturelib.load_state\n"
            "def slow(root):\n"
            "    state = real(root)\n"
            "    time.sleep(0.4)\n"
            "    return state\n"
            "capturelib.load_state = slow\n"
            "sys.exit(capture_signal.run(['--hook']))\n"
        )
        event = json.dumps({
            "agent_type": "tester", "agent_id": "race-1",
            "last_assistant_message": post_build_report(BUGS),
        })
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project))
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", driver], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=env, cwd=str(self.project),
            )
            for _ in range(3)
        ]
        for proc in procs:
            proc.communicate(event.encode("utf-8"), timeout=60)
            self.assertEqual(proc.returncode, 0)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(len(list((self.root / "tmp" / "subagent-captures").glob("*.md"))), 1)
        self.assertEqual(len(capturelib.load_state(self.root)["signals"]), 1)

    def test_unmatched_report_is_logged_as_unparsed_with_its_agent_station(self):
        """Adversarial where: a tester report with no Mode section is
        dropped from the log or filed under a guessed station, so spawns go
        uncounted."""
        self.spawn("tester", "I wrote some tests and they pass.")
        row = self.rows()[0]
        self.assertEqual(row["station"], "tester")
        self.assertEqual(row["verdict"], "unparsed")


class StationRowIsBestEffortTests(StationRowCase):
    def test_malformed_events_write_no_row_and_exit_zero(self):
        """Adversarial where: an event that is not a JSON object leaves a
        row, a half-built log, or a non-zero exit that fails the turn.
        Rows: broken JSON, an array, empty stdin, a JSON string."""
        rows = {
            "broken json": "{not json at all",
            "json array": "[1, 2, 3]",
            "empty stdin": "",
            "json string": '"tester"',
        }
        for name, payload in rows.items():
            with self.subTest(name=name):
                self.assertEqual(self.deliver(payload), 0)
                self.assertFalse(self.log.exists())

    def test_worker_session_writes_no_row(self):
        """Adversarial where: the capture worker's own headless session
        inherits the hooks and its subagent finishing adds a station row,
        counting a spawn the build never made."""
        os.environ["COMPASS_WORKER_SESSION"] = "1"
        self.assertEqual(self.spawn("tester", post_build_report(BUGS)), 0)
        self.assertFalse(self.log.exists())

    def test_unwritable_station_log_costs_neither_the_capture_nor_the_exit_code(self):
        """Adversarial where: the station write fails (here the log path is
        a directory) and the exception escapes or aborts the capture file
        and signal the hook already owed, because the row write runs before
        them."""
        self.log.mkdir(parents=True)
        code = self.spawn("tester", post_build_report(BUGS))
        self.assertEqual(code, 0)
        captures = list((self.root / "tmp" / "subagent-captures").glob("*_tester*.md"))
        self.assertEqual(len(captures), 1)
        self.assertEqual(len(capturelib.load_state(self.root)["signals"]), 1)

    def test_event_without_a_vault_writes_nothing_and_exits_zero(self):
        """Adversarial where: a project with no `.compass/` gets a stray
        `.compass/meta/station-log.jsonl` created by the row write."""
        bare = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, bare, True)
        os.environ["CLAUDE_PROJECT_DIR"] = str(bare)
        # With no vault in the project dir the lookup climbs from the working
        # directory, so the working directory sits in the bare project too.
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(bare)
        self.assertEqual(self.spawn("tester", post_build_report(BUGS)), 0)
        self.assertFalse((bare / ".compass").exists())


if __name__ == "__main__":
    unittest.main()
