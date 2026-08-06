"""Tests for the capture-family commands (`capture-signal` today; `capture-check`
and `capture-stats` land in later tasks and append here). Adversarial: the
SubagentStop hook path must never fail the turn that triggered it, so most
cases assert "exits 0, records nothing" under a malformed or absent input
rather than a happy path."""

import builtins
import datetime
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import capturelib  # noqa: E402
from commands import capture_check  # noqa: E402
from commands import capture_signal  # noqa: E402
from commands import capture_stats  # noqa: E402


def make_vault(test_case):
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    root = tmp / ".compass"
    root.mkdir(parents=True)
    return root


def with_vault_env(test_case, vault_root):
    """Point find_vault_root at this vault (or, when `vault_root` is a bare
    project dir with no .compass, at nowhere) for the duration of the test."""
    old = os.environ.get("CLAUDE_PROJECT_DIR")
    os.environ["CLAUDE_PROJECT_DIR"] = str(vault_root)

    def restore():
        if old is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = old

    test_case.addCleanup(restore)


def feed_stdin(test_case, payload):
    """Pipe `payload` (a dict, serialized as JSON, or a raw string for
    malformed-input cases) as the process's stdin for the duration of the
    test."""
    test_case.addCleanup(setattr, sys, "stdin", sys.stdin)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    sys.stdin = io.StringIO(text)


def captures_dir(vault_root):
    return vault_root / "tmp" / "subagent-captures"


def opportunities_dir(vault_root):
    return vault_root / "tmp" / "capture-opportunities"


def capture_log_path(vault_root):
    return vault_root / "tmp" / "capture-log.jsonl"


def read_log_rows(vault_root):
    path = capture_log_path(vault_root)
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_capture_config(root, **overrides):
    """Write `.compass/meta/capture.json` with `DEFAULT_CONFIG` overridden by
    `overrides`, bypassing `load_config`'s materialize-on-read so a test can
    set `interval`/`max_reemits`/`enabled` before the first `capture-check`
    call sees them."""
    config = dict(capturelib.DEFAULT_CONFIG)
    config.update(overrides)
    path = root / "meta" / "capture.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config), encoding="utf-8")
    return config


class CaptureSignalTests(unittest.TestCase):
    def _run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = capture_signal.run(["--hook"])
        return code, out.getvalue()

    def test_validator_writes_capture_and_records_validator_finished(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {
            "agent_type": "validator",
            "agent_id": "agent-1",
            "last_assistant_message": "PASS: all checks green",
        })
        code, _ = self._run()
        self.assertEqual(code, 0)

        files = list(captures_dir(root).glob("*_validator.md"))
        self.assertEqual(len(files), 1)
        text = files[0].read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("type: subagent_capture\n", text)
        self.assertIn("agent_type: validator\n", text)
        self.assertIn("agent_id: agent-1\n", text)
        self.assertIn("captured_at: ", text)
        # Body is the message verbatim - byte-identical past the frontmatter.
        body = text.split("---\n", 2)[2].lstrip("\n")
        self.assertEqual(body, "PASS: all checks green")

        state = capturelib.load_state(root)
        self.assertEqual(len(state["signals"]), 1)
        self.assertEqual(state["signals"][0]["kind"], "validator-finished")

    def test_debug_records_debug_finished(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"agent_type": "debug", "last_assistant_message": "found it"})
        self._run()
        state = capturelib.load_state(root)
        self.assertEqual(state["signals"][0]["kind"], "debug-finished")

    def test_builder_records_builder_finished(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"agent_type": "builder", "last_assistant_message": "done"})
        self._run()
        state = capturelib.load_state(root)
        self.assertEqual(state["signals"][0]["kind"], "builder-finished")

    def test_other_agent_type_records_subagent_finished(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"agent_type": "researcher", "last_assistant_message": "notes"})
        self._run()
        state = capturelib.load_state(root)
        self.assertEqual(state["signals"][0]["kind"], "subagent-finished")

    def test_malformed_json_exits_0_and_records_nothing(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, "{not json at all")
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertFalse(captures_dir(root).is_dir())
        state = capturelib.load_state(root)
        self.assertEqual(state["signals"], [])

    def test_empty_stdin_exits_0_and_records_nothing(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, "")
        code, _ = self._run()
        self.assertEqual(code, 0)
        self.assertFalse(captures_dir(root).is_dir())

    def test_missing_vault_exits_0(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        # find_vault_root falls back to walking up from cwd when
        # CLAUDE_PROJECT_DIR has no .compass/, so cwd must also sit outside
        # this repo's own vault - otherwise the fallback would find it.
        old_cwd = os.getcwd()
        os.chdir(tmp)
        self.addCleanup(os.chdir, old_cwd)
        with_vault_env(self, tmp)  # no .compass/ under this dir either
        feed_stdin(self, {"agent_type": "builder", "last_assistant_message": "x"})
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_agent_type_absent_still_writes_and_records_default_signal(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"last_assistant_message": "no agent_type on this event"})
        code, _ = self._run()
        self.assertEqual(code, 0)
        files = list(captures_dir(root).glob("*_unknown.md"))
        self.assertEqual(len(files), 1)
        state = capturelib.load_state(root)
        self.assertEqual(state["signals"][0]["kind"], "subagent-finished")

    def test_empty_last_assistant_message_still_writes_capture(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"agent_type": "builder", "last_assistant_message": ""})
        code, _ = self._run()
        self.assertEqual(code, 0)
        files = list(captures_dir(root).glob("*_builder.md"))
        self.assertEqual(len(files), 1)
        body = files[0].read_text(encoding="utf-8").split("---\n", 2)[2].lstrip("\n")
        self.assertEqual(body, "")

    def test_huge_message_is_not_truncated(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        huge = "x" * 500_000
        feed_stdin(self, {"agent_type": "builder", "last_assistant_message": huge})
        code, _ = self._run()
        self.assertEqual(code, 0)
        files = list(captures_dir(root).glob("*_builder.md"))
        body = files[0].read_text(encoding="utf-8").split("---\n", 2)[2].lstrip("\n")
        self.assertEqual(len(body), 500_000)

    def test_same_second_collision_does_not_overwrite(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"agent_type": "builder", "last_assistant_message": "first"})
        self._run()
        feed_stdin(self, {"agent_type": "builder", "last_assistant_message": "second"})
        self._run()

        files = sorted(captures_dir(root).glob("*_builder*.md"))
        self.assertEqual(len(files), 2)
        bodies = {
            f.read_text(encoding="utf-8").split("---\n", 2)[2].lstrip("\n") for f in files
        }
        self.assertEqual(bodies, {"first", "second"})

    def test_filenames_match_expected_timestamp_shape(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"agent_type": "builder", "last_assistant_message": "x"})
        self._run()
        files = list(captures_dir(root).glob("*.md"))
        self.assertEqual(len(files), 1)
        self.assertRegex(
            files[0].name, r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}_builder\.md$"
        )

    def test_no_hook_flag_never_reads_stdin(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)

        class _Boom:
            def read(self_inner):
                raise AssertionError("no --hook flag: stdin must never be read")

        self.addCleanup(setattr, sys, "stdin", sys.stdin)
        sys.stdin = _Boom()
        code = capture_signal.run([])
        self.assertEqual(code, 0)
        self.assertFalse(captures_dir(root).is_dir())

    def test_internal_error_after_stdin_parse_still_exits_0(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"agent_type": "builder", "last_assistant_message": "x"})
        original = capturelib.record_signal
        capturelib.record_signal = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            code, out = self._run()
        finally:
            capturelib.record_signal = original
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


class CaptureCheckTests(unittest.TestCase):
    """Tests for `capture-check --hook`, the Stop-hook trigger. Like
    `capture-signal`, most cases assert "exits 0" under corruption or
    absence; the happy paths verify the emitted stop-hook JSON and the
    opportunity.json contract capture-check writes before emitting it."""

    def _run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = capture_check.run(["--hook"])
        return code, out.getvalue()

    def _opportunities(self, root):
        directory = opportunities_dir(root)
        return sorted(directory.iterdir()) if directory.is_dir() else []

    def test_below_interval_prints_nothing(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        state = capturelib.load_state(root)
        self.assertEqual(state["turns_since_capture"], 1)
        self.assertEqual(self._opportunities(root), [])

    def test_due_via_interval_emits_block_json_and_opportunity(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, interval=1)
        capturelib.record_signal(root, "vault-write", "specs/SPEC-001.md")
        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["decision"], "block")
        self.assertIn("tmp/capture-opportunities/OPP-", payload["reason"])
        self.assertIn("extract-lessons", payload["reason"])

        opps = self._opportunities(root)
        self.assertEqual(len(opps), 1)
        record = json.loads((opps[0] / "opportunity.json").read_text(encoding="utf-8"))
        self.assertEqual(record["kind"], "interval")
        self.assertEqual(record["triggers"], ["vault-write"])
        self.assertEqual(record["evidence"], ["specs/SPEC-001.md"])
        self.assertIsNone(record["outcome"])

        # The window that produced the opportunity is spent.
        state = capturelib.load_state(root)
        self.assertEqual(state["turns_since_capture"], 0)
        self.assertEqual(state["signals"], [])

    def test_real_subagent_capture_evidence_surfaces_in_opportunity(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {
            "agent_type": "validator",
            "agent_id": "agent-1",
            "last_assistant_message": "PASS: all checks green",
        })
        capture_signal.run(["--hook"])  # a real subagent finishing, in the window

        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["decision"], "block")

        opps = self._opportunities(root)
        self.assertEqual(len(opps), 1)
        record = json.loads((opps[0] / "opportunity.json").read_text(encoding="utf-8"))
        self.assertEqual(record["kind"], "signal")
        self.assertEqual(record["triggers"], ["validator-finished"])
        self.assertEqual(len(record["evidence"]), 1)
        evidence_path = record["evidence"][0]
        self.assertTrue(evidence_path.startswith("tmp/subagent-captures/"))
        self.assertTrue((root / evidence_path).is_file())

    def test_strong_signal_fires_below_interval(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)  # default interval (12), one turn only
        capturelib.record_signal(root, "handoff-written", "handoffs/HANDOFF-1.md")
        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["decision"], "block")
        opps = self._opportunities(root)
        record = json.loads((opps[0] / "opportunity.json").read_text(encoding="utf-8"))
        self.assertEqual(record["kind"], "signal")
        self.assertEqual(record["triggers"], ["handoff-written"])
        self.assertEqual(record["evidence"], ["handoffs/HANDOFF-1.md"])

    def test_second_call_with_open_opportunity_reemits_within_budget(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, interval=1, max_reemits=3)
        capturelib.record_signal(root, "vault-write", "specs/SPEC-001.md")
        feed_stdin(self, {"hook_event_name": "Stop"})
        self._run()  # opens the opportunity
        opp_id = capturelib.load_state(root)["open_opportunity"]
        self.assertIsNotNone(opp_id)

        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["decision"], "block")
        self.assertIn("still open", payload["reason"])
        self.assertIn(opp_id, payload["reason"])

        state = capturelib.load_state(root)
        self.assertEqual(state["open_opportunity"], opp_id)
        self.assertEqual(state["reemits"], 1)
        # Re-emitting must not open a second opportunity.
        self.assertEqual(len(self._opportunities(root)), 1)

    def test_reemit_cap_honored_then_closed_abandoned(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, interval=1, max_reemits=1)
        capturelib.record_signal(root, "vault-write", "specs/SPEC-001.md")
        feed_stdin(self, {"hook_event_name": "Stop"})
        self._run()  # opens, reemits=0
        opp_id = capturelib.load_state(root)["open_opportunity"]

        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()  # 1 reemit, within the budget of 1
        self.assertIn("still open", json.loads(out)["reason"])
        self.assertEqual(capturelib.load_state(root)["reemits"], 1)

        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()  # budget exhausted: abandon, go silent
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        state = capturelib.load_state(root)
        self.assertIsNone(state["open_opportunity"])
        record = json.loads(
            (opportunities_dir(root) / opp_id / "opportunity.json").read_text(encoding="utf-8")
        )
        self.assertEqual(record["outcome"], "abandoned")
        self.assertIsNotNone(record["closed_at"])

    def test_unprocessed_phase_summary_opens_phase_opportunity(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        phase_dir = root / "tmp" / "phase-reports" / "PHASE-001-plan-001"
        phase_dir.mkdir(parents=True)
        (phase_dir / "phase-summary.yaml").write_text("phase_id: PHASE-001\n", encoding="utf-8")
        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["decision"], "block")
        opps = self._opportunities(root)
        self.assertEqual(len(opps), 1)
        record = json.loads((opps[0] / "opportunity.json").read_text(encoding="utf-8"))
        self.assertEqual(record["kind"], "phase")
        self.assertEqual(record["triggers"], ["phase-summary"])
        self.assertEqual(record["evidence"], ["tmp/phase-reports/PHASE-001-plan-001"])

    def test_processed_marker_suppresses_phase_opportunity(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        phase_dir = root / "tmp" / "phase-reports" / "PHASE-001-plan-001"
        phase_dir.mkdir(parents=True)
        (phase_dir / "phase-summary.yaml").write_text("phase_id: PHASE-001\n", encoding="utf-8")
        (phase_dir / ".processed").write_text("", encoding="utf-8")
        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertEqual(self._opportunities(root), [])

    def test_disabled_config_silences_everything(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, enabled=False, interval=1)
        capturelib.record_signal(root, "handoff-written", "handoffs/HANDOFF-1.md")
        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertEqual(self._opportunities(root), [])

    def test_disabled_config_freezes_an_already_open_opportunity(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, interval=1)
        capturelib.record_signal(root, "vault-write", "specs/SPEC-001.md")
        feed_stdin(self, {"hook_event_name": "Stop"})
        self._run()  # opens while enabled
        before = capturelib.load_state(root)
        self.assertIsNotNone(before["open_opportunity"])

        write_capture_config(root, interval=1, enabled=False)
        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        after = capturelib.load_state(root)
        self.assertEqual(after["open_opportunity"], before["open_opportunity"])
        self.assertEqual(after["reemits"], before["reemits"])

    def test_open_opportunity_missing_on_disk_clears_stale_mutex(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        directory = capturelib.open_opportunity(
            root, "interval", ["vault-write"], ["specs/SPEC-001.md"]
        )
        shutil.rmtree(directory)
        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        state = capturelib.load_state(root)
        self.assertIsNone(state["open_opportunity"])

    def test_corrupt_state_file_exits_0(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        state_path = root / "tmp" / "capture-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text("not json at all {{{", encoding="utf-8")
        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_missing_vault_exits_0(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        old_cwd = os.getcwd()
        os.chdir(tmp)
        self.addCleanup(os.chdir, old_cwd)
        with_vault_env(self, tmp)  # no .compass/ under this dir either
        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_no_hook_flag_never_reads_stdin(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)

        class _Boom:
            def read(self_inner):
                raise AssertionError("no --hook flag: stdin must never be read")

        self.addCleanup(setattr, sys, "stdin", sys.stdin)
        sys.stdin = _Boom()
        code = capture_check.run([])
        self.assertEqual(code, 0)
        self.assertEqual(self._opportunities(root), [])

    def test_internal_error_mid_emit_leaves_no_partial_output(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, interval=1)
        capturelib.record_signal(root, "vault-write", "specs/SPEC-001.md")
        feed_stdin(self, {"hook_event_name": "Stop"})
        original = capturelib.open_opportunity
        capturelib.open_opportunity = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            code, out = self._run()
        finally:
            capturelib.open_opportunity = original
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


class CaptureLogLifecycleTests(unittest.TestCase):
    """Tests for the trace rows `capturelib` appends to
    `.compass/tmp/capture-log.jsonl` around the opportunity lifecycle: the
    direct answer to hermes Finding 11 that "reviewed and found nothing" and
    "never ran" must be distinguishable rows, never the same absence."""

    def test_full_lifecycle_produces_expected_row_sequence(self):
        root = make_vault(self)
        write_capture_config(root, interval=1)
        state = capturelib.load_state(root)
        config = capturelib.load_config(root)

        # Not due yet: a `skipped` row carrying the arithmetic reason.
        is_due, reason = capturelib.due_and_log(root, state, config)
        self.assertFalse(is_due)

        # Due: an `opened` row.
        capturelib.record_signal(root, "vault-write", "specs/SPEC-001.md")
        state = capturelib.load_state(root)
        directory = capturelib.open_opportunity(root, "interval", ["vault-write"], ["specs/SPEC-001.md"])
        opp_id = directory.name

        # Extraction ran and wrote nothing: a `fired` row, not a `closed` one -
        # "reviewed and found nothing" is distinguishable from "never ran".
        capturelib.close_opportunity(root, opp_id, "fired", candidate=2, written=0, rejected=2)

        # A second opportunity that ages out unprocessed: a `closed` row.
        second = capturelib.open_opportunity(root, "phase", ["phase-summary"], [])
        capturelib.close_opportunity(root, second.name, "abandoned")

        rows = read_log_rows(root)
        events = [r["event"] for r in rows]
        self.assertEqual(events, ["skipped", "opened", "fired", "opened", "closed"])

        self.assertEqual(rows[0]["reason"], reason)

        self.assertEqual(rows[1]["id"], opp_id)
        self.assertEqual(rows[1]["kind"], "interval")
        self.assertEqual(rows[1]["triggers"], ["vault-write"])

        self.assertEqual(rows[2]["id"], opp_id)
        self.assertEqual(rows[2]["outcome"], "fired")
        self.assertEqual(rows[2]["candidate"], 2)
        self.assertEqual(rows[2]["written"], 0)
        self.assertEqual(rows[2]["rejected"], 2)
        self.assertNotIn("recurrence", rows[2])  # never provided, never written

        self.assertEqual(rows[4]["id"], second.name)
        self.assertEqual(rows[4]["outcome"], "abandoned")
        self.assertNotIn("written", rows[4])  # abandoned: extraction never ran

        for row in rows:
            self.assertIn("at", row)

    def test_fired_and_closed_rows_are_lf_only(self):
        root = make_vault(self)
        directory = capturelib.open_opportunity(root, "interval", [], [])
        capturelib.close_opportunity(root, directory.name, "abandoned")
        raw = capture_log_path(root).read_bytes()
        self.assertNotIn(b"\r\n", raw)
        self.assertIn(b"\n", raw)

    def test_logging_failure_does_not_raise_out_of_open_or_close(self):
        root = make_vault(self)
        real_open = builtins.open

        def boom(path, *args, **kwargs):
            if str(path).endswith("capture-log.jsonl"):
                raise OSError("unwritable")
            return real_open(path, *args, **kwargs)

        with mock.patch("builtins.open", boom):
            directory = capturelib.open_opportunity(root, "interval", [], [])
            capturelib.close_opportunity(root, directory.name, "fired", written=1)

        # The lifecycle itself still completed despite the log write failing.
        record = json.loads((directory / "opportunity.json").read_text(encoding="utf-8"))
        self.assertEqual(record["outcome"], "fired")


class CaptureStatsTests(unittest.TestCase):
    def _run(self, args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = capture_stats.run(args)
        return code, out.getvalue()

    def _write_log(self, root, rows):
        path = capture_log_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(json.dumps(r) if not isinstance(r, str) else r for r in rows) + "\n",
            encoding="utf-8",
        )

    def test_rates_computed_from_fixture_log_including_zero_fire_vault(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        self._write_log(root, [
            {"at": "2026-01-01T00:00:00Z", "event": "opened", "id": "OPP-1", "kind": "interval", "triggers": ["vault-write"]},
            {"at": "2026-01-01T00:01:00Z", "event": "fired", "id": "OPP-1", "outcome": "fired", "candidate": 1, "written": 1},
            {"at": "2026-01-02T00:00:00Z", "event": "opened", "id": "OPP-2", "kind": "signal", "triggers": ["handoff-written"]},
            {"at": "2026-01-02T00:01:00Z", "event": "fired", "id": "OPP-2", "outcome": "fired", "candidate": 3, "written": 0},
            {"at": "2026-01-03T00:00:00Z", "event": "skipped", "reason": "below interval (2/12)"},
        ])
        code, out = self._run([])
        self.assertEqual(code, 0)
        self.assertIn("opportunities opened: 2", out)
        self.assertIn("fired: 2 (100.0%)", out)
        self.assertIn("written: 1 (50.0%)", out)
        self.assertIn("vault-write: 1", out)
        self.assertIn("handoff-written: 1", out)

    def test_zero_fire_vault_reports_zero_percent_not_a_crash(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        self._write_log(root, [
            {"at": "2026-01-01T00:00:00Z", "event": "opened", "id": "OPP-1", "kind": "interval", "triggers": ["vault-write"]},
            {"at": "2026-01-01T00:01:00Z", "event": "closed", "id": "OPP-1", "outcome": "abandoned"},
        ])
        code, out = self._run([])
        self.assertEqual(code, 0)
        self.assertIn("opportunities opened: 1", out)
        self.assertIn("fired: 0 (0.0%)", out)
        self.assertIn("written: 0 (0.0%)", out)

    def test_no_log_reports_zero_without_crashing(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        code, out = self._run([])
        self.assertEqual(code, 0)
        self.assertIn("opportunities opened: 0", out)

    def test_json_flag_parses(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        self._write_log(root, [
            {"at": "2026-01-01T00:00:00Z", "event": "opened", "id": "OPP-1", "kind": "interval", "triggers": ["vault-write"]},
        ])
        code, out = self._run(["--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["opened"], 1)
        self.assertEqual(payload["fired"], 0)
        self.assertIn("triggers", payload)

    def test_unknown_event_kind_skipped_without_crashing(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        self._write_log(root, [
            {"at": "2026-01-01T00:00:00Z", "event": "opened", "id": "OPP-1", "kind": "interval", "triggers": []},
            {"at": "2026-01-01T00:01:00Z", "event": "mystery-event", "id": "OPP-1"},
        ])
        code, out = self._run(["--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["opened"], 1)

    def test_malformed_jsonl_line_skipped(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        self._write_log(root, [
            {"at": "2026-01-01T00:00:00Z", "event": "opened", "id": "OPP-1", "kind": "interval", "triggers": []},
            "{not valid json at all",
        ])
        code, out = self._run(["--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["opened"], 1)

    def test_since_filters_older_rows(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        self._write_log(root, [
            {"at": "2026-01-01T00:00:00Z", "event": "opened", "id": "OPP-1", "kind": "interval", "triggers": []},
            {"at": "2026-02-01T00:00:00Z", "event": "opened", "id": "OPP-2", "kind": "interval", "triggers": []},
        ])
        code, out = self._run(["--json", "--since", "2026-01-15"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["opened"], 1)

    def test_since_bad_value_exits_1(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        code, _ = self._run(["--since", "not-a-date"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
