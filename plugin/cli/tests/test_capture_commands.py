"""Tests for the capture-family commands: `capture-signal` and `capture-check`,
the two hook entry points, `capture-note`, the agent's own signal, and `capture-stats` and `capture-close`, the
ordinary CLI surfaces that read and close what the hooks produced.
Adversarial for the hook path: a SubagentStop or Stop hook must never fail
the turn that triggered it, so most of those cases assert "exits 0, records
nothing" under a malformed or absent input rather than a happy path.
`capture-close` is not hook-gated and reports its own errors, so its cases
assert ordinary exit-1 failure instead."""

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
from commands import capture_close  # noqa: E402
from commands import capture_note  # noqa: E402
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


def _backdate_opportunity(root, opp_id, seconds):
    """Rewrite an opportunity's `opened_at` to `seconds` ago, so age-gated
    behavior is testable without sleeping."""
    path = opportunities_dir(root) / opp_id / "opportunity.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    past = capturelib._now() - datetime.timedelta(seconds=seconds)
    record["opened_at"] = capturelib._iso(past)
    path.write_text(json.dumps(record), encoding="utf-8", newline="\n")


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
        """TASK-092: due now spawns the detached worker and prints nothing,
        replacing the rendered block on this common path (ADR-013 D-01)."""
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, interval=1)
        capturelib.record_signal(root, "vault-write", "specs/SPEC-001.md")
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            mock_popen.return_value = mock.Mock(pid=4242)
            code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "", "the conversation must see nothing on a spawn")
        self.assertEqual(mock_popen.call_count, 1)

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
        """TASK-092: due now spawns the detached worker and prints nothing,
        replacing the rendered block on this common path (ADR-013 D-01)."""
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {
            "agent_type": "validator",
            "agent_id": "agent-1",
            "last_assistant_message": "PASS: all checks green",
        })
        capture_signal.run(["--hook"])  # a real subagent finishing, in the window

        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            mock_popen.return_value = mock.Mock(pid=4242)
            code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "", "the conversation must see nothing on a spawn")
        self.assertEqual(mock_popen.call_count, 1)

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
        """TASK-092: due now spawns the detached worker and prints nothing,
        replacing the rendered block on this common path (ADR-013 D-01)."""
        root = make_vault(self)
        with_vault_env(self, root.parent)  # default interval (12), one turn only
        capturelib.record_signal(root, "handoff-written", "handoffs/HANDOFF-1.md")
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            mock_popen.return_value = mock.Mock(pid=4242)
            code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "", "the conversation must see nothing on a spawn")
        self.assertEqual(mock_popen.call_count, 1)
        opps = self._opportunities(root)
        record = json.loads((opps[0] / "opportunity.json").read_text(encoding="utf-8"))
        self.assertEqual(record["kind"], "signal")
        self.assertEqual(record["triggers"], ["handoff-written"])
        self.assertEqual(record["evidence"], ["handoffs/HANDOFF-1.md"])

    def test_open_opportunity_stays_silent_between_spaced_reemits(self):
        """Adversarial where: every block reason is rendered into the human's
        conversation, so a hook that re-nags on each turn while the extraction
        pass runs fills the transcript with scaffolding. The turns immediately
        after the announcement must be silent; the reminder fires only after
        REEMIT_SPACING_TURNS turns.

        TASK-092: the block last resort is now entered through the fallback
        ladder (quiet already fired, then aged past another worker_grace_seconds)
        rather than opened directly by a due check. Seeded here instead of
        walked turn-by-turn; the spacing and abandon assertions below are
        otherwise unchanged from the pre-worker mechanism."""
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, max_reemits=3, worker_grace_seconds=600)
        directory = capturelib.open_opportunity(
            root, "interval", ["vault-write"], ["specs/SPEC-001.md"]
        )
        opp_id = directory.name
        _set_state_fields(
            root, worker_attempts=2,
            worker_quiet_at=capturelib._iso(
                capturelib._now() - datetime.timedelta(seconds=650)
            ),
        )
        _write_raw_log_row(root, "fallback-fired", at_offset_seconds=650, id=opp_id, channel="quiet")
        feed_stdin(self, {"hook_event_name": "Stop"})
        self._run()  # transitions quiet -> block, entering the block-last-resort state
        self.assertEqual(capturelib.load_state(root)["open_opportunity"], opp_id)

        for _ in range(capture_check.REEMIT_SPACING_TURNS - 1):
            feed_stdin(self, {"hook_event_name": "Stop"})
            code, out = self._run()
            self.assertEqual(code, 0)
            self.assertEqual(out, "")
        state = capturelib.load_state(root)
        self.assertEqual(state["open_opportunity"], opp_id)
        self.assertEqual(state["reemits"], 0)

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
        """TASK-092: the block last resort is now entered through the
        fallback ladder (quiet already fired, then aged past another
        worker_grace_seconds) rather than opened directly by a due check.
        Seeded here instead of walked turn-by-turn; the spacing and abandon
        assertions below are otherwise unchanged from the pre-worker
        mechanism."""
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, max_reemits=1, worker_grace_seconds=600)
        directory = capturelib.open_opportunity(
            root, "interval", ["vault-write"], ["specs/SPEC-001.md"]
        )
        opp_id = directory.name
        _set_state_fields(
            root, worker_attempts=2,
            worker_quiet_at=capturelib._iso(
                capturelib._now() - datetime.timedelta(seconds=650)
            ),
        )
        _write_raw_log_row(root, "fallback-fired", at_offset_seconds=650, id=opp_id, channel="quiet")
        feed_stdin(self, {"hook_event_name": "Stop"})
        self._run()  # transitions quiet -> block, entering the block-last-resort state; reemits=0

        for _ in range(capture_check.REEMIT_SPACING_TURNS - 1):
            feed_stdin(self, {"hook_event_name": "Stop"})
            self._run()  # silent turns inside the spacing window
        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()  # 1 reemit, within the budget of 1
        self.assertIn("still open", json.loads(out)["reason"])
        self.assertEqual(capturelib.load_state(root)["reemits"], 1)

        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()  # budget exhausted but young: silent, still open
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        state = capturelib.load_state(root)
        self.assertEqual(state["open_opportunity"], opp_id)

        _backdate_opportunity(root, opp_id, seconds=901)
        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()  # budget exhausted and past grace: abandon
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        state = capturelib.load_state(root)
        self.assertIsNone(state["open_opportunity"])
        record = json.loads(
            (opportunities_dir(root) / opp_id / "opportunity.json").read_text(encoding="utf-8")
        )
        self.assertEqual(record["outcome"], "abandoned")
        self.assertIsNotNone(record["closed_at"])

    def test_concurrent_check_blocked_by_run_lock(self):
        """Adversarial where: two Stop hooks racing the read-decide-write
        window would each open an identical opportunity; the holder of the
        run lock must be the only one that can."""
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, interval=1)
        capturelib.record_signal(root, "vault-write", "specs/SPEC-001.md")
        self.assertTrue(capturelib.acquire_run_lock(root))
        self.addCleanup(capturelib.release_run_lock, root)
        feed_stdin(self, {"hook_event_name": "Stop"})
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertFalse(opportunities_dir(root).exists())
        capturelib.release_run_lock(root)
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch.object(capture_check.subprocess, "Popen") as popen:
            code, out = self._run()
        self.assertEqual(code, 0)
        # The unblocked call opens the opportunity and spawns silently.
        self.assertEqual(out, "")
        self.assertEqual(popen.call_count, 1)
        self.assertTrue(opportunities_dir(root).exists())

    def test_stale_run_lock_is_broken_and_retaken(self):
        """Adversarial where: a crashed capture-check would leave its lock
        behind forever, silencing capture in the vault permanently."""
        root = make_vault(self)
        path = capturelib._run_lock_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stale", encoding="utf-8")
        old = capturelib._now().timestamp() - capturelib.RUN_LOCK_STALE_SECONDS - 5
        os.utime(path, (old, old))
        self.assertTrue(capturelib.acquire_run_lock(root))
        capturelib.release_run_lock(root)

    def test_unprocessed_phase_summary_opens_phase_opportunity(self):
        """TASK-092: due now spawns the detached worker and prints nothing,
        replacing the rendered block on this common path (ADR-013 D-01)."""
        root = make_vault(self)
        with_vault_env(self, root.parent)
        phase_dir = root / "tmp" / "phase-reports" / "PHASE-001-plan-001"
        phase_dir.mkdir(parents=True)
        (phase_dir / "phase-summary.yaml").write_text("phase_id: PHASE-001\n", encoding="utf-8")
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            mock_popen.return_value = mock.Mock(pid=4242)
            code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "", "the conversation must see nothing on a spawn")
        self.assertEqual(mock_popen.call_count, 1)
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


# ---------------------------------------------------------------------------
# TASK-092: the recursion gate, the detached spawn, and the fallback ladder
# (ADR-013 D-01/D-04/D-05/D-11, mechanism decisions in PLAN-010). `capture_check.py`
# does not import `subprocess` yet, so every test that patches
# `commands.capture_check.subprocess.Popen` raises `AttributeError` at patch
# setup until the builder adds it - a legitimate red, not a broken test, per
# [[LESSON-revert-to-prove-a-regression-test]].
# ---------------------------------------------------------------------------


def with_worker_session_env(test_case):
    """Set `COMPASS_WORKER_SESSION=1` for the duration of the test, restoring
    whatever was there before (mirrors `with_vault_env`'s save/restore
    shape, in this file already)."""
    old = os.environ.get("COMPASS_WORKER_SESSION")
    os.environ["COMPASS_WORKER_SESSION"] = "1"

    def restore():
        if old is None:
            os.environ.pop("COMPASS_WORKER_SESSION", None)
        else:
            os.environ["COMPASS_WORKER_SESSION"] = old

    test_case.addCleanup(restore)


def _write_raw_log_row(root, event, at_offset_seconds=0, **fields):
    """Append one capture-log row with a caller-controlled `at` timestamp,
    bypassing `capturelib.log_event`'s own now-stamping so a worker row's
    age can be backdated without sleeping - the same technique
    `_backdate_opportunity` above uses for `opportunity.json`."""
    ts = capturelib._now() - datetime.timedelta(seconds=at_offset_seconds)
    row = {"at": capturelib._iso(ts), "event": event}
    row.update(fields)
    path = capture_log_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def _set_state_fields(root, **fields):
    state = capturelib.load_state(root)
    state.update(fields)
    capturelib.save_state(root, state)
    return state


def _popen_argv(call):
    """The first positional arg `subprocess.Popen` was called with, whether
    the builder passed it positionally or as the `args=` keyword."""
    if call.args:
        return call.args[0]
    return call.kwargs.get("args")


class RecursionGateTests(unittest.TestCase):
    """`capture_check.run` and `capture_signal.run` under
    `COMPASS_WORKER_SESSION` (ADR-013 D-11): the worker's own headless
    session inherits the vault's hooks, so without this gate it would
    process the very opportunity it was spawned to close and manufacture the
    signals that make the next one due - a loop, not a pass."""

    def setUp(self):
        with_worker_session_env(self)

    def test_capture_check_gate_fires_before_any_due_work(self):
        """Adversarial where: a marker check placed after the turn bump or
        after due_and_log would still let the worker's own session advance
        the counters or open the opportunity the gate exists to suppress -
        a strong signal is armed here specifically because it would open an
        opportunity on its own, below any interval, if the gate did not fire
        first."""
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, interval=1)
        capturelib.record_signal(root, "handoff-written", "handoffs/H.md")
        feed_stdin(self, {"hook_event_name": "Stop"})
        out = io.StringIO()
        with redirect_stdout(out):
            code = capture_check.run(["--hook"])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), "")
        self.assertFalse(opportunities_dir(root).exists())
        state = capturelib.load_state(root)
        self.assertEqual(state["turns_since_capture"], 0)
        self.assertEqual(read_log_rows(root), [])

    def test_capture_signal_gate_records_nothing(self):
        """Adversarial where: the worker's own extract-lessons subagent pass
        finishing would, ungated, record a validator/builder-finished signal
        that feeds the exact due() arithmetic the recursion gate exists to
        starve."""
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {
            "agent_type": "validator", "agent_id": "a1", "last_assistant_message": "x",
        })
        code = capture_signal.run(["--hook"])
        self.assertEqual(code, 0)
        self.assertFalse(captures_dir(root).exists())
        state = capturelib.load_state(root)
        self.assertEqual(state["signals"], [])


class WorkerSpawnTests(unittest.TestCase):
    """`capture-check`'s due path spawns the detached worker instead of
    rendering the block (ADR-013 D-01, D-05's first rung): the conversation
    surface goes to zero on the common path, not just on the fallback ones."""

    def _run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = capture_check.run(["--hook"])
        return code, out.getvalue()

    def test_due_spawns_worker_detached_and_prints_nothing(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, interval=1)
        capturelib.record_signal(root, "vault-write", "specs/SPEC-001.md")
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            mock_popen.return_value = mock.Mock(pid=4242)
            code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "", "the conversation must see nothing on a spawn")
        self.assertEqual(mock_popen.call_count, 1)
        argv = _popen_argv(mock_popen.call_args)
        self.assertEqual(argv[0], sys.executable)
        self.assertEqual(argv[-2], "capture-worker")
        opp_id = argv[-1]
        self.assertTrue(opp_id.startswith("OPP-"))

        rows = [r for r in read_log_rows(root) if r["event"] == "worker-started"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["pid"], 4242)
        self.assertEqual(rows[0]["id"], opp_id)

    def test_popen_raising_writes_worker_spawn_error_and_prints_nothing(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, interval=1)
        capturelib.record_signal(root, "vault-write", "specs/SPEC-001.md")
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            mock_popen.side_effect = OSError("spawn failed")
            code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        rows = [r for r in read_log_rows(root) if r["event"] == "worker-spawn-error"]
        self.assertEqual(len(rows), 1)

    @unittest.skipUnless(sys.platform == "win32", "Windows-only detach flags")
    def test_windows_spawn_uses_detached_process_and_new_process_group(self):
        import subprocess as subprocess_mod
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, interval=1)
        capturelib.record_signal(root, "vault-write", "specs/SPEC-001.md")
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            mock_popen.return_value = mock.Mock(pid=1)
            self._run()
        kwargs = mock_popen.call_args.kwargs
        flags = kwargs.get("creationflags", 0)
        self.assertTrue(flags & subprocess_mod.DETACHED_PROCESS, "DETACHED_PROCESS not set")
        self.assertTrue(
            flags & subprocess_mod.CREATE_NEW_PROCESS_GROUP, "CREATE_NEW_PROCESS_GROUP not set"
        )

    @unittest.skipIf(sys.platform == "win32", "POSIX-only start_new_session")
    def test_posix_spawn_uses_start_new_session(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, interval=1)
        capturelib.record_signal(root, "vault-write", "specs/SPEC-001.md")
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            mock_popen.return_value = mock.Mock(pid=1)
            self._run()
        kwargs = mock_popen.call_args.kwargs
        self.assertIs(kwargs.get("start_new_session"), True)


class FallbackLadderTests(unittest.TestCase):
    """`capture-check`'s subsequent-check ladder for an already-open
    opportunity, branching on worker ledger rows and grace/attempt state
    instead of pure turn-based reemit spacing (ADR-013 D-04, mechanism
    decisions)."""

    def _run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = capture_check.run(["--hook"])
        return code, out.getvalue()

    def _open(self, root, grace=600):
        write_capture_config(root, worker_grace_seconds=grace)
        directory = capturelib.open_opportunity(
            root, "interval", ["vault-write"], ["specs/SPEC-001.md"]
        )
        return directory.name

    def test_dead_worker_or_zero_rows_past_grace_spend_attempt_and_respawn(self):
        """Adversarial where: a started row with no end row, and an open
        opportunity with NO worker rows at all, are two different shapes of
        the same fact - a spawn that never produced a running worker - and
        the plan calls out that the zero-rows case "behaves identically" to
        the dead-started-row case. Two setups, one claim."""
        cases = {
            "started-row-no-end-past-grace": lambda root, opp_id: _write_raw_log_row(
                root, "worker-started", at_offset_seconds=650, id=opp_id, pid=1
            ),
            "zero-worker-rows-past-grace": lambda root, opp_id: _backdate_opportunity(
                root, opp_id, seconds=650
            ),
        }
        for name, setup in cases.items():
            with self.subTest(name=name):
                root = make_vault(self)
                with_vault_env(self, root.parent)
                opp_id = self._open(root, grace=600)
                setup(root, opp_id)
                feed_stdin(self, {"hook_event_name": "Stop"})
                with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
                    mock_popen.return_value = mock.Mock(pid=9999)
                    code, out = self._run()
                self.assertEqual(code, 0)
                self.assertEqual(mock_popen.call_count, 1, f"{name}: expected a respawn")
                state = capturelib.load_state(root)
                self.assertEqual(state["worker_attempts"], 1, f"{name}: attempt not spent")

    def test_lock_held_respawns_without_spending_attempt(self):
        """Adversarial where: `lock-held` is contention, not a death - the
        worker never even started running its pass, so charging an attempt
        for it would burn through the two-attempt budget on host noise
        rather than real failures."""
        root = make_vault(self)
        with_vault_env(self, root.parent)
        opp_id = self._open(root, grace=600)
        _write_raw_log_row(root, "worker-started", at_offset_seconds=1, id=opp_id, pid=1)
        _write_raw_log_row(root, "worker-failed", at_offset_seconds=0, id=opp_id, reason="lock-held")
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            mock_popen.return_value = mock.Mock(pid=2)
            code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(mock_popen.call_count, 1)
        self.assertEqual(capturelib.load_state(root)["worker_attempts"], 0)

    def test_worker_row_with_id_but_no_pid_does_not_crash_the_ladder(self):
        """Adversarial where: a worker-started row carrying a valid,
        matching id but no pid field - a partial malformation distinct from
        a garbage row - must not raise; the ladder degrades to treating the
        row as a normal grace check rather than crashing on a missing key."""
        root = make_vault(self)
        with_vault_env(self, root.parent)
        opp_id = self._open(root, grace=600)
        _write_raw_log_row(root, "worker-started", at_offset_seconds=650, id=opp_id)  # no pid
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            mock_popen.return_value = mock.Mock(pid=1)
            code, out = self._run()
        self.assertNotEqual(code, 2)
        self.assertEqual(code, 0)


class QuietFallbackTests(unittest.TestCase):
    """The quiet channel (`additionalContext`), the fallback ADR-013 D-05
    prefers over the rendered block."""

    def _run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = capture_check.run(["--hook"])
        return code, out.getvalue()

    def test_third_death_past_two_attempts_goes_quiet_instead_of_respawning(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, worker_grace_seconds=600)
        directory = capturelib.open_opportunity(
            root, "interval", ["vault-write"], ["specs/SPEC-001.md"]
        )
        opp_id = directory.name
        _set_state_fields(root, worker_attempts=2)
        _write_raw_log_row(root, "worker-started", at_offset_seconds=650, id=opp_id, pid=1)
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(
            mock_popen.call_count, 0, "past two attempts must not respawn a third time"
        )
        payload = json.loads(out)
        self.assertNotIn("decision", payload, "the quiet channel must not also render a block")
        self.assertIn("additionalContext", payload.get("hookSpecificOutput", {}))
        rows = [r for r in read_log_rows(root) if r["event"] == "fallback-fired"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["channel"], "quiet")
        state = capturelib.load_state(root)
        self.assertIsNotNone(state["worker_quiet_at"])

    def test_quiet_does_not_refire_on_the_very_next_check(self):
        """Adversarial where: "exactly once" is the claim - a ladder that
        re-evaluates "past two attempts" on every check without also
        checking whether quiet already fired would re-emit additionalContext
        on every single turn, which is exactly the per-turn scaffolding cost
        this design exists to remove."""
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, worker_grace_seconds=600)
        directory = capturelib.open_opportunity(
            root, "interval", ["vault-write"], ["specs/SPEC-001.md"]
        )
        opp_id = directory.name
        _set_state_fields(
            root, worker_attempts=2, worker_quiet_at=capturelib._iso(capturelib._now())
        )
        _write_raw_log_row(root, "fallback-fired", at_offset_seconds=0, id=opp_id, channel="quiet")
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "", "already quiet, still inside the next grace: must stay silent")
        self.assertEqual(mock_popen.call_count, 0)

    def test_no_headless_latch_goes_quiet_immediately_without_two_attempts(self):
        """Adversarial where: no-headless is a host-level fact (this
        machine cannot run headless children at all), not a per-death
        counter - it must not wait for worker_attempts to reach two the way
        an ordinary transient death does, or a permanently auth-less host
        would render two pointless respawn attempts before ever going
        quiet."""
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, worker_grace_seconds=600)
        directory = capturelib.open_opportunity(
            root, "interval", ["vault-write"], ["specs/SPEC-001.md"]
        )
        opp_id = directory.name
        _set_state_fields(
            root, worker_attempts=0, no_headless_at=capturelib._iso(capturelib._now())
        )
        _write_raw_log_row(
            root, "worker-failed", at_offset_seconds=0, id=opp_id, reason="no-headless"
        )
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(mock_popen.call_count, 0)
        payload = json.loads(out)
        self.assertIn("additionalContext", payload.get("hookSpecificOutput", {}))
        rows = [r for r in read_log_rows(root) if r["event"] == "fallback-fired"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["channel"], "quiet")


class NoHeadlessLatchSuppressesSpawnTests(unittest.TestCase):
    """The `no_headless_at` latch suppresses spawn attempts on a FRESH due
    opportunity, not just on the ladder of an already-open one, and expires
    on its own TTL (mechanism decisions: `no_headless_retry_seconds`)."""

    def _run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = capture_check.run(["--hook"])
        return code, out.getvalue()

    def test_latch_inside_ttl_attempts_no_spawn_on_a_fresh_due_opportunity(self):
        # Fixture (100) deliberately distinct from capturelib's own default
        # (86400): a broken override lookup that silently fell back to the
        # module default would treat this latch as still-fresh either way,
        # and this case alone could not tell the difference.
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, interval=1, no_headless_retry_seconds=100)
        _set_state_fields(
            root,
            no_headless_at=capturelib._iso(
                capturelib._now() - datetime.timedelta(seconds=50)
            ),
        )
        capturelib.record_signal(root, "vault-write", "specs/SPEC-001.md")
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(mock_popen.call_count, 0)

    def test_latch_past_ttl_allows_spawn_on_a_fresh_due_opportunity(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, interval=1, no_headless_retry_seconds=100)
        _set_state_fields(
            root,
            no_headless_at=capturelib._iso(
                capturelib._now() - datetime.timedelta(seconds=150)
            ),
        )
        capturelib.record_signal(root, "vault-write", "specs/SPEC-001.md")
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            mock_popen.return_value = mock.Mock(pid=1)
            code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(mock_popen.call_count, 1)


class BlockLastResortTests(unittest.TestCase):
    """The rendered block, retained only behind the quiet channel failing to
    produce a pass (ADR-013 D-05's last resort)."""

    def _run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = capture_check.run(["--hook"])
        return code, out.getvalue()

    def test_quiet_then_another_grace_past_emits_block_with_fallback_fired_row(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, worker_grace_seconds=600)
        directory = capturelib.open_opportunity(
            root, "interval", ["vault-write"], ["specs/SPEC-001.md"]
        )
        opp_id = directory.name
        _set_state_fields(
            root, worker_attempts=2,
            worker_quiet_at=capturelib._iso(
                capturelib._now() - datetime.timedelta(seconds=650)
            ),
        )
        _write_raw_log_row(
            root, "fallback-fired", at_offset_seconds=650, id=opp_id, channel="quiet"
        )
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            code, out = self._run()
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["decision"], "block")
        rows = [r for r in read_log_rows(root) if r["event"] == "fallback-fired"]
        channels = [r["channel"] for r in rows]
        self.assertIn("block", channels)

    def test_never_emits_two_json_payloads_in_one_run(self):
        """Adversarial where: a check whose worker_quiet_at is already past
        its own second grace (block-worthy) while ALSO carrying a fresh
        started row shaped like a should-quiet death must still write
        exactly one JSON object to stdout - never two concatenated writes
        that would break the hook contract's single-payload parse."""
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, worker_grace_seconds=600)
        directory = capturelib.open_opportunity(
            root, "interval", ["vault-write"], ["specs/SPEC-001.md"]
        )
        opp_id = directory.name
        _set_state_fields(
            root, worker_attempts=2,
            worker_quiet_at=capturelib._iso(
                capturelib._now() - datetime.timedelta(seconds=650)
            ),
        )
        _write_raw_log_row(
            root, "fallback-fired", at_offset_seconds=650, id=opp_id, channel="quiet"
        )
        _write_raw_log_row(root, "worker-started", at_offset_seconds=650, id=opp_id, pid=1)
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            code, out = self._run()
        self.assertEqual(code, 0)
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertLessEqual(len(lines), 1, f"expected at most one JSON line, got: {out!r}")
        if out.strip():
            json.loads(out)  # must parse as exactly one JSON object, never two concatenated


class AbandonDefersToLiveWorkerTests(unittest.TestCase):
    """The abandon path defers while a live worker is inside its grace
    (mechanism decisions, PLAN-010's last bullet)."""

    def _run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = capture_check.run(["--hook"])
        return code, out.getvalue()

    def test_abandon_defers_while_a_live_worker_is_inside_grace(self):
        """Adversarial where: the pre-existing reemit-cap/age-based abandon
        path, applied blindly, would close an opportunity out from under a
        worker that is still legitimately running (a fresh started row, well
        inside worker_grace_seconds) - exactly the scenario D-04's "never
        abandoned out from under a running worker" guarantee exists for."""
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(
            root, interval=1, max_reemits=0, abandon_after_seconds=10, worker_grace_seconds=600
        )
        directory = capturelib.open_opportunity(
            root, "interval", ["vault-write"], ["specs/SPEC-001.md"]
        )
        opp_id = directory.name
        _backdate_opportunity(root, opp_id, seconds=20)  # past abandon_after_seconds
        _write_raw_log_row(root, "worker-started", at_offset_seconds=5, id=opp_id, pid=1)  # fresh
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            code, out = self._run()
        self.assertEqual(code, 0)
        state = capturelib.load_state(root)
        self.assertEqual(state["open_opportunity"], opp_id, "abandon must defer to the live worker")


class WorkerAttemptsResetOnOpenTests(unittest.TestCase):
    """`worker_attempts` is a flat, vault-wide state field (mechanism
    decisions, PLAN-010) reset on open - a value carried over from a prior
    opportunity's spawn deaths must not make the NEXT opportunity's fallback
    ladder think it already lost attempts before it ever spawned once."""

    def _run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = capture_check.run(["--hook"])
        return code, out.getvalue()

    def test_worker_attempts_reset_when_a_new_opportunity_opens(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_capture_config(root, interval=1)
        first = capturelib.open_opportunity(
            root, "interval", ["vault-write"], ["specs/SPEC-001.md"]
        )
        _set_state_fields(root, worker_attempts=2)
        capturelib.close_opportunity(root, first.name, "fired", written=1)

        capturelib.record_signal(root, "vault-write", "specs/SPEC-002.md")
        feed_stdin(self, {"hook_event_name": "Stop"})
        with mock.patch("commands.capture_check.subprocess.Popen") as mock_popen:
            mock_popen.return_value = mock.Mock(pid=1)
            code, out = self._run()
        self.assertEqual(code, 0)
        state = capturelib.load_state(root)
        self.assertEqual(state["worker_attempts"], 0)


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


class CaptureCloseTests(unittest.TestCase):
    """Tests for `capture-close`, the extraction pass's own way to close the
    opportunity it just processed. Unlike the hook commands, this is an
    ordinary CLI surface: no `--hook` gate, no stdin, and a bad argument or
    an id the caller has lost track of is a reported error, not a
    best-effort no-op."""

    def _run(self, args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = capture_close.run(args)
        return code, out.getvalue()

    def test_close_writes_fired_row_with_counts_and_clears_mutex(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        directory = capturelib.open_opportunity(
            root, "interval", ["vault-write"], ["specs/SPEC-001.md"]
        )
        opp_id = directory.name
        self.assertEqual(capturelib.load_state(root)["open_opportunity"], opp_id)

        code, out = self._run([
            opp_id, "--outcome", "fired",
            "--candidates", "3", "--written", "2", "--recurrence", "1",
            "--rejected", "1", "--revised", "1", "--archived", "1", "--errors", "0",
        ])
        self.assertEqual(code, 0)
        self.assertIn(opp_id, out)

        state = capturelib.load_state(root)
        self.assertIsNone(state["open_opportunity"])

        record = json.loads((directory / "opportunity.json").read_text(encoding="utf-8"))
        self.assertEqual(record["outcome"], "fired")
        self.assertIsNotNone(record["closed_at"])

        rows = read_log_rows(root)
        fired = [r for r in rows if r["event"] == "fired"]
        self.assertEqual(len(fired), 1)
        row = fired[0]
        self.assertEqual(row["id"], opp_id)
        self.assertEqual(row["candidate"], 3)
        self.assertEqual(row["written"], 2)
        self.assertEqual(row["recurrence"], 1)
        self.assertEqual(row["rejected"], 1)
        self.assertEqual(row["revised"], 1)
        self.assertEqual(row["archived"], 1)
        self.assertEqual(row["error"], 0)

    def test_missing_counts_omitted_from_row_not_zeroed(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        directory = capturelib.open_opportunity(root, "phase", ["phase-summary"], [])
        opp_id = directory.name

        code, _ = self._run([opp_id, "--outcome", "fired"])
        self.assertEqual(code, 0)

        rows = read_log_rows(root)
        row = [r for r in rows if r["event"] == "fired"][0]
        for key in ("candidate", "written", "recurrence", "rejected", "revised", "archived", "error"):
            self.assertNotIn(key, row)

    def test_unknown_id_exits_1(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        code, _ = self._run(["OPP-never-existed", "--outcome", "fired"])
        self.assertEqual(code, 1)

    def test_already_closed_id_exits_1(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        directory = capturelib.open_opportunity(root, "interval", [], [])
        opp_id = directory.name
        capturelib.close_opportunity(root, opp_id, "fired", written=1)

        code, _ = self._run([opp_id, "--outcome", "fired", "--written", "1"])
        self.assertEqual(code, 1)

    def test_real_outcome_supersedes_auto_abandon(self):
        """Adversarial where: an extraction pass that outran the automatic
        abandon would have its close refused, leaving the trace undercounting
        a pass that finished and wrote lessons."""
        root = make_vault(self)
        with_vault_env(self, root.parent)
        directory = capturelib.open_opportunity(root, "interval", [], [])
        opp_id = directory.name
        capturelib.close_opportunity(root, opp_id, "abandoned")

        code, out = self._run([opp_id, "--outcome", "fired", "--written", "2"])
        self.assertEqual(code, 0)
        self.assertIn("superseding auto-abandon", out)
        record = json.loads(
            (directory / "opportunity.json").read_text(encoding="utf-8")
        )
        self.assertEqual(record["outcome"], "fired")

        code, _ = self._run([opp_id, "--outcome", "fired"])
        self.assertEqual(code, 1)  # a superseded close is final

    def test_abandoned_never_supersedes_a_real_outcome(self):
        """Adversarial where: a late auto-abandon overriding a real fired
        outcome would erase the pass's counts from the record."""
        root = make_vault(self)
        with_vault_env(self, root.parent)
        directory = capturelib.open_opportunity(root, "interval", [], [])
        opp_id = directory.name
        capturelib.close_opportunity(root, opp_id, "fired", written=1)

        code, _ = self._run([opp_id, "--outcome", "abandoned"])
        self.assertEqual(code, 1)

    def test_missing_outcome_flag_exits_1_not_2(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        directory = capturelib.open_opportunity(root, "interval", [], [])
        code, _ = self._run([directory.name])
        self.assertEqual(code, 1)

    def test_non_integer_count_exits_1_not_2(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        directory = capturelib.open_opportunity(root, "interval", [], [])
        code, _ = self._run([directory.name, "--outcome", "fired", "--written", "not-a-number"])
        self.assertEqual(code, 1)

    def test_unknown_flag_exits_1_not_2(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        directory = capturelib.open_opportunity(root, "interval", [], [])
        code, _ = self._run([directory.name, "--outcome", "fired", "--bogus", "1"])
        self.assertEqual(code, 1)

    def test_no_opportunity_id_exits_1_not_2(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        code, _ = self._run(["--outcome", "fired"])
        self.assertEqual(code, 1)


class TeammateIdleTests(unittest.TestCase):
    def _run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = capture_signal.run(["--hook"])
        return code, out.getvalue()

    def test_teammate_idle_records_signal_and_writes_no_capture_file(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {
            "hook_event_name": "TeammateIdle",
            "teammate_name": "build-046",
            "team_name": "session-x",
            "session_id": "abc",
        })
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertFalse(captures_dir(root).exists())
        state = capturelib.load_state(root)
        self.assertEqual(len(state["signals"]), 1)
        self.assertEqual(state["signals"][0]["kind"], "subagent-finished")
        self.assertEqual(state["signals"][0]["ref"], "teammate:build-046")

    def test_teammate_idle_without_name_records_unknown(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"hook_event_name": "TeammateIdle"})
        code, _ = self._run()
        self.assertEqual(code, 0)
        state = capturelib.load_state(root)
        self.assertEqual(state["signals"][0]["ref"], "teammate:unknown")


if __name__ == "__main__":
    unittest.main()


class CaptureNoteTests(unittest.TestCase):
    """`capture-note` is the main agent's own door into the capture loop: a
    note becomes evidence in subagent-captures plus a strong `agent-noted`
    signal, so the worker fires at the next Stop without the human doing
    anything. Adversarial on the two ways it could misfire: an empty note
    must record nothing, and a note from inside the worker's own session
    must record nothing (it would reopen the loop the worker closes)."""

    def _run(self, args):
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            code = capture_note.run(args)
        return code, err.getvalue()

    def test_note_writes_evidence_file_and_records_strong_signal(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        code, _ = self._run(["a destructive test read the shared store"])
        self.assertEqual(code, 0)

        files = list(captures_dir(root).glob("*_note.md"))
        self.assertEqual(len(files), 1)
        text = files[0].read_text(encoding="utf-8")
        self.assertIn("type: agent_note\n", text)
        body = text.split("---\n", 2)[2].strip()
        self.assertEqual(body, "a destructive test read the shared store")

        state = capturelib.load_state(root)
        self.assertEqual(len(state["signals"]), 1)
        self.assertEqual(state["signals"][0]["kind"], "agent-noted")
        self.assertEqual(
            state["signals"][0]["ref"], files[0].relative_to(root).as_posix()
        )
        is_due, reason = capturelib.due(state, capturelib.DEFAULT_CONFIG)
        self.assertTrue(is_due, reason)

    def test_multiword_args_join_into_one_note(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        code, _ = self._run(["shared", "default", "target"])
        self.assertEqual(code, 0)
        files = list(captures_dir(root).glob("*_note.md"))
        body = files[0].read_text(encoding="utf-8").split("---\n", 2)[2].strip()
        self.assertEqual(body, "shared default target")

    def test_empty_note_records_nothing_and_fails(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        code, err = self._run([])
        self.assertEqual(code, 1)
        self.assertIn("usage", err)
        self.assertFalse(captures_dir(root).exists())
        self.assertEqual(capturelib.load_state(root)["signals"], [])

    def test_worker_session_gate_records_nothing(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        with mock.patch.dict(os.environ, {"COMPASS_WORKER_SESSION": "1"}):
            code, _ = self._run(["a note from inside the worker"])
        self.assertEqual(code, 0)
        self.assertFalse(captures_dir(root).exists())
        self.assertEqual(capturelib.load_state(root)["signals"], [])

    def test_two_notes_in_one_second_do_not_overwrite(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        fixed = datetime.datetime(2026, 8, 24, 12, 0, 0, tzinfo=datetime.timezone.utc)
        with mock.patch.object(capture_note, "_now", return_value=fixed):
            self.assertEqual(self._run(["first"])[0], 0)
            self.assertEqual(self._run(["second"])[0], 0)
        files = sorted(captures_dir(root).glob("*_note*.md"))
        self.assertEqual(len(files), 2)
        bodies = {f.read_text(encoding="utf-8").split("---\n", 2)[2].strip() for f in files}
        self.assertEqual(bodies, {"first", "second"})
