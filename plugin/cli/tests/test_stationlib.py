"""Adversarial tests for `stationlib`: a finished checking subagent's report
becomes exactly one counts-only row.

Themes: the Mode section decides the tester station, only the Bugs Found
section's own items are counted, a validator's verdict is not confused with
per-check results, a report matching no form is `unparsed` rather than
guessed, the model comes from the subagent transcript before the resolved
agent model, and no report text ever reaches a row.
"""

import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stationlib  # noqa: E402


def make_tester_report(mode, bugs=(), after_bugs=""):
    """A tester report in the `tester.md` report format. `bugs` become the
    bullet items of the Bugs Found section (None omits the section), and
    `after_bugs` is text that follows it."""
    parts = [
        "## Test Report",
        "",
        "### Mode",
        mode,
        "",
        "### Tests Written",
        "- `tests/test_x.py:10` - test_x: a defect class",
        "",
        "### Checkpoint Verification",
        "**Command:** `compass test-checkpoint verify TASK-346 --against-run run.txt`",
        "",
    ]
    if bugs is not None:
        parts += ["### Bugs Found (post-build only, omit if none)"]
        parts += [f"- {b}" for b in bugs]
        parts += [""]
    parts += [after_bugs]
    return "\n".join(parts) + "\n"



def validator_report(verdict_line="VERDICT: PASS", phase_rows=(), probes=""):
    rows = "\n".join(phase_rows)
    return (
        "## Validation Report: [[PLAN-034-stations]]\n\n"
        "### Baseline\n- Commit: `abc1234` | Files changed: 4 | Commits since: 2\n\n"
        "### Phase Results\n#### Phase 1: Record\n"
        "| Task | Status | Checks | Classification |\n"
        "|------|--------|--------|----------------|\n"
        f"{rows}\n\n"
        f"{probes}\n"
        "### Summary\nTasks: 1/1 | Checks: 3 pass / 0 fail\n\n"
        f"{verdict_line}\n"
    )


PROBE_PASS = (
    "### Adversarial Probes\n**Probe:** one\n**Command:** x\n**Output:** y\n**Result:** PASS\n"
)

THREE_BUGS = [
    "**A:** `a.py:1` - repro: x - expected: 1 / actual: 2",
    "**B:** `b.py:2` - repro: y - expected: 1 / actual: 3",
    "**C:** `c.py:3` - repro: z - expected: 1 / actual: 4",
]


class ParseReportTests(unittest.TestCase):
    def test_station_and_counts_per_report_form(self):
        """Adversarial where: the station is read from the wrong place or the
        count from the wrong section. One behavior (`parse_report` mapping a
        report to station and counts), one row per form, boundaries at zero
        bugs, one bug, and a following section whose bullets must not be
        counted."""
        three = THREE_BUGS
        rows = {
            "post-build with three bugs": (
                "tester", make_tester_report("Post-build", three), "tester-post", {"bugs": 3}),
            "post-build with the section omitted counts zero": (
                "tester", make_tester_report("Post-build", None), "tester-post", {"bugs": 0}),
            "post-build with one bug": (
                "tester", make_tester_report("Post-build", three[:1]), "tester-post", {"bugs": 1}),
            "bullets of the next section are not bugs": (
                "tester",
                make_tester_report("Post-build", three[:2], after_bugs="### Coverage\n- Not covered: a\n- Not covered: b\n"),
                "tester-post", {"bugs": 2}),
            "bugs before a bullet-free trailing section": (
                "tester",
                make_tester_report("Post-build", three, after_bugs="### Coverage\nNothing else.\n"),
                "tester-post", {"bugs": 3}),
            "pre-build": (
                "tester", make_tester_report("Pre-build", None), "tester-pre", {}),
            "pre-build whose body shows a Bugs Found section is still pre-build": (
                "tester", make_tester_report("Pre-build", three), "tester-pre", {}),
            "plugin-scoped agent type": (
                "compass:tester", make_tester_report("Post-build", three[:2]), "tester-post", {"bugs": 2}),
        }
        for name, (agent, text, station, counts) in rows.items():
            with self.subTest(name=name):
                parsed = stationlib.parse_report(agent, text)
                self.assertEqual(parsed["station"], station)
                self.assertNotEqual(parsed.get("verdict"), "unparsed")
                for key, value in counts.items():
                    self.assertEqual(parsed[key], value)

    def test_task_id_comes_from_the_report(self):
        """Adversarial where: the task id is invented, taken from a later id
        when several appear, or crashes when none is present."""
        later = make_tester_report("Post-build", None) + "\nlater mention of TASK-999\n"
        build = "## Build Report\n\n### Task\nTASK-512 ([[PLAN-034-x]] Phase 2)\n\n### Changes\n- `a.py` - x\n"
        rows = {
            "first id in a tester report wins": ("tester", later, "TASK-346"),
            "builder report names its task under Task": ("builder", build, "TASK-512"),
        }
        for name, (agent, text, expected) in rows.items():
            with self.subTest(name=name):
                self.assertEqual(stationlib.parse_report(agent, text)["task"], expected)
        with self.subTest(name="no id anywhere"):
            parsed = stationlib.parse_report("debug", "## Debug Report: boom\n\n### Root Cause\nx\n")
            self.assertFalse(parsed["task"])

    def test_unmatched_reports_fall_back_to_agent_type_and_unparsed(self):
        """Adversarial where: a report that matches no known form is
        guessed into a tester station, crashes the parser, or loses its
        station. Asymmetric rows: a Mode heading with an unknown value,
        empty text, prose, and control characters around a Mode word."""
        rows = {
            "tester report without a Mode section": (
                "tester", "## Test Report\n\n### Tests Written\n- a\n", "tester"),
            "tester Mode section of an unknown value": (
                "tester", "## Test Report\n\n### Mode\nMid-build\n", "tester"),
            "empty text from a tester": ("tester", "", "tester"),
            "empty text from a validator": ("validator", "", "validator"),
            "free prose from a debug agent": ("debug", "I looked and found nothing.", "debug"),
            "control characters around a Mode word": ("tester", "\x00\x01## Mode\x00", "tester"),
        }
        for name, (agent, text, station) in rows.items():
            with self.subTest(name=name):
                parsed = stationlib.parse_report(agent, text)
                self.assertEqual(parsed["station"], station)
                self.assertEqual(parsed["verdict"], "unparsed")

    def test_validator_result_and_fail_rows(self):
        """Adversarial where: the validator's verdict is read from a
        per-check `**Result:** PASS` line instead of its final VERDICT line,
        or a FAIL outside the Phase Results table rows is counted.
        Asymmetric rows: one FAIL row among passing rows, and a FAIL probe
        outside the table."""
        passing = "| TASK-346: record | [x] done | 3/3 passed | Matches plan |"
        failing = "| TASK-347: report | [x] done | 1/3 passed | FAIL |"
        rows = {
            "all rows pass": (validator_report("VERDICT: PASS", [passing], PROBE_PASS), "PASS", 0),
            "one FAIL row among passing rows": (
                validator_report("VERDICT: FAIL", [passing, failing, passing], PROBE_PASS), "FAIL", 1),
            "two FAIL rows": (
                validator_report("VERDICT: FAIL", [failing, failing], PROBE_PASS), "FAIL", 2),
            "partial verdict": (
                validator_report("VERDICT: PARTIAL", [passing, failing]), "PARTIAL", 1),
            "FAIL in a probe outside the table is not a Phase Results row": (
                validator_report(
                    "VERDICT: PASS", [passing],
                    "### Adversarial Probes\n**Probe:** p\n**Result:** FAIL\n"),
                "PASS", 0),
        }
        for name, (text, result, fails) in rows.items():
            with self.subTest(name=name):
                parsed = stationlib.parse_report("validator", text)
                self.assertEqual(parsed["station"], "validator")
                self.assertEqual(parsed["result"], result)
                self.assertEqual(parsed["fails"], fails)


class TranscriptFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.vault = self.tmp / ".compass"
        self.vault.mkdir()
        self._saved = {k: os.environ.get(k) for k in ("CLAUDE_PROJECT_DIR", "COMPASS_MODEL_TESTER")}
        self.addCleanup(self._restore)
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.tmp)
        os.environ["COMPASS_MODEL_TESTER"] = "claude-env-pin-7"

    def _restore(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def transcript(self, *records, name="sub.jsonl"):
        path = self.tmp / name
        path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        return str(path)


class BuildRowTests(TranscriptFixture):
    REPORT = make_tester_report(
        "Post-build",
        ["**SECRETBUG-alpha-91:** `src/file.py:42` - repro: `run it` - expected: X / actual: Y"],
        after_bugs="### Coverage\n- Not covered: SECRET-coverage-line-77 because reasons\n",
    )

    def event(self, **extra):
        base = {"agent_type": "tester", "agent_id": "a1"}
        base.update(extra)
        return base

    def test_model_prefers_the_subagent_transcript_over_the_resolved_model(self):
        """Adversarial where: the row records the resolved agent model even
        though the subagent's transcript names the model that actually ran,
        or a transcript yielding nothing leaves the model empty instead of
        falling back to `modelslib.resolve` with its source label. The env
        pin differs from every transcript model and from the built-in
        tester default."""
        good = self.transcript(
            {"type": "attachment", "attachment": {"type": "model", "identity": {"modelId": "claude-ran-3"}}})
        empty = self.transcript(name="empty.jsonl")
        rows = {
            "transcript names the model": (
                self.event(agent_transcript_path=good), "claude-ran-3", None),
            "transcript file is empty": (
                self.event(agent_transcript_path=empty), "claude-env-pin-7", "env"),
            "transcript path names no file": (
                self.event(agent_transcript_path=str(self.tmp / "missing.jsonl")), "claude-env-pin-7", "env"),
            "event names no transcript": (self.event(), "claude-env-pin-7", "env"),
            "transcript field is not a string": (
                self.event(agent_transcript_path=12), "claude-env-pin-7", "env"),
            "plugin-scoped type resolves the bare agent": (
                self.event(agent_type="compass:tester"), "claude-env-pin-7", "env"),
        }
        for name, (event, model, source) in rows.items():
            with self.subTest(name=name):
                row = stationlib.build_row(event, self.REPORT)
                self.assertEqual(row["model"], model)
                self.assertTrue(row["model_source"])
                if source:
                    self.assertEqual(row["model_source"], source)

    def test_row_carries_the_contract_keys_and_no_report_text(self):
        """Adversarial where: a row leaks a line of the report (a bug
        description, a coverage note) or drops one of the keys downstream
        commands parse. The report holds a unique marker in a bug line and
        in a line after the section."""
        row = stationlib.build_row(self.event(), self.REPORT)
        for key in ("ts", "agent_type", "station", "task", "model", "model_source", "bugs"):
            self.assertIn(key, row)
        self.assertEqual(row["agent_type"], "tester")
        self.assertEqual(row["station"], "tester-post")
        self.assertEqual(row["bugs"], 1)
        self.assertEqual(row["task"], "TASK-346")
        dumped = json.dumps(row)
        for line in self.REPORT.splitlines():
            if len(line.strip()) >= 12:
                self.assertNotIn(line.strip(), dumped)
        for marker in ("SECRETBUG-alpha-91", "SECRET-coverage-line-77"):
            self.assertNotIn(marker, dumped)

    def test_timestamp_is_utc_iso_and_current(self):
        """Adversarial where: `ts` is a naive local time or a non-ISO value,
        so rows from machines in different zones sort wrongly."""
        row = stationlib.build_row(self.event(), self.REPORT)
        parsed = datetime.datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
        self.assertEqual(parsed.utcoffset(), datetime.timedelta(0))
        age = datetime.datetime.now(datetime.timezone.utc) - parsed
        self.assertLess(abs(age.total_seconds()), 120)


class AppendRowTests(TranscriptFixture):
    def test_rows_append_as_one_json_line_each_in_order(self):
        """Adversarial where: appends overwrite the log, join two rows on
        one line, or create the log only when its folder already exists.
        The meta folder is absent at the first append, and the third append
        follows a log whose last line lacks a trailing newline."""
        log = self.vault / "meta" / "station-log.jsonl"
        self.assertFalse(log.parent.exists())
        stationlib.append_row(self.vault, {"station": "tester-pre", "task": "TASK-1"})
        stationlib.append_row(self.vault, {"station": "tester-post", "task": "TASK-2", "bugs": 3})
        lines = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(x)["task"] for x in lines], ["TASK-1", "TASK-2"])
        log.write_text(log.read_text(encoding="utf-8").rstrip("\n"), encoding="utf-8")
        stationlib.append_row(self.vault, {"station": "validator", "task": "TASK-3"})
        lines = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(x)["task"] for x in lines], ["TASK-1", "TASK-2", "TASK-3"])


if __name__ == "__main__":
    unittest.main()
