"""Tests for capturelib: config/state load, counters, signals, due-check,
and the opportunity lifecycle. Adversarial where the module claims it never
raises: corrupt files, wrong-typed fields, and a flood of signal writes."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import capturelib  # noqa: E402


def make_vault(test_case):
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    root = tmp / ".compass"
    (root / "meta").mkdir(parents=True)
    return root


class ConfigTests(unittest.TestCase):
    def test_missing_config_materializes_defaults(self):
        root = make_vault(self)
        path = root / "meta" / "capture.json"
        self.assertFalse(path.is_file())
        config = capturelib.load_config(root)
        self.assertEqual(config, capturelib.DEFAULT_CONFIG)
        self.assertTrue(path.is_file())
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk, capturelib.DEFAULT_CONFIG)

    def test_partial_config_gets_defaults_for_missing_keys_only(self):
        root = make_vault(self)
        path = root / "meta" / "capture.json"
        path.write_text(json.dumps({"interval": 5}), encoding="utf-8")
        config = capturelib.load_config(root)
        self.assertEqual(config["interval"], 5)
        self.assertEqual(config["enabled"], capturelib.DEFAULT_CONFIG["enabled"])
        self.assertEqual(config["max_reemits"], capturelib.DEFAULT_CONFIG["max_reemits"])

    def test_partial_config_file_not_overwritten(self):
        root = make_vault(self)
        path = root / "meta" / "capture.json"
        path.write_text(json.dumps({"interval": 5}), encoding="utf-8")
        capturelib.load_config(root)
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk, {"interval": 5})

    def test_corrupt_config_recovers_to_defaults(self):
        root = make_vault(self)
        path = root / "meta" / "capture.json"
        path.write_text("{not json", encoding="utf-8")
        config = capturelib.load_config(root)
        self.assertEqual(config, capturelib.DEFAULT_CONFIG)

    def test_config_not_a_dict_recovers_to_defaults(self):
        root = make_vault(self)
        path = root / "meta" / "capture.json"
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        config = capturelib.load_config(root)
        self.assertEqual(config, capturelib.DEFAULT_CONFIG)

    def test_config_written_with_lf_only(self):
        root = make_vault(self)
        capturelib.load_config(root)
        raw = (root / "meta" / "capture.json").read_bytes()
        self.assertNotIn(b"\r\n", raw)
        self.assertIn(b"\n", raw)


class StateTests(unittest.TestCase):
    def test_missing_state_returns_defaults_without_writing(self):
        root = make_vault(self)
        state = capturelib.load_state(root)
        self.assertEqual(state, capturelib.DEFAULT_STATE)
        self.assertFalse((root / "tmp" / "capture-state.json").is_file())

    def test_save_then_load_round_trips(self):
        root = make_vault(self)
        state = capturelib.load_state(root)
        state["turns_since_capture"] = 4
        capturelib.save_state(root, state)
        reloaded = capturelib.load_state(root)
        self.assertEqual(reloaded["turns_since_capture"], 4)

    def test_corrupt_state_recovers_to_defaults(self):
        root = make_vault(self)
        path = root / "tmp" / "capture-state.json"
        path.parent.mkdir(parents=True)
        path.write_text("not json at all {{{", encoding="utf-8")
        state = capturelib.load_state(root)
        self.assertEqual(state, capturelib.DEFAULT_STATE)

    def test_unreadable_state_recovers_to_defaults(self):
        root = make_vault(self)
        path = root / "tmp" / "capture-state.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"turns_since_capture": 9}), encoding="utf-8")
        original_read_text = Path.read_text

        def boom(self, *args, **kwargs):
            if self == path:
                raise PermissionError("denied")
            return original_read_text(self, *args, **kwargs)

        Path.read_text = boom
        try:
            state = capturelib.load_state(root)
        finally:
            Path.read_text = original_read_text
        self.assertEqual(state, capturelib.DEFAULT_STATE)

    def test_state_not_a_dict_recovers_to_defaults(self):
        root = make_vault(self)
        path = root / "tmp" / "capture-state.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps("just a string"), encoding="utf-8")
        state = capturelib.load_state(root)
        self.assertEqual(state, capturelib.DEFAULT_STATE)

    def test_signals_wrong_type_resets_to_empty_list_only(self):
        root = make_vault(self)
        path = root / "tmp" / "capture-state.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps({"turns_since_capture": 7, "signals": "oops"}), encoding="utf-8"
        )
        state = capturelib.load_state(root)
        self.assertEqual(state["signals"], [])
        self.assertEqual(state["turns_since_capture"], 7)

    def test_state_written_with_lf_only(self):
        root = make_vault(self)
        capturelib.save_state(root, capturelib.load_state(root))
        raw = (root / "tmp" / "capture-state.json").read_bytes()
        self.assertNotIn(b"\r\n", raw)
        self.assertIn(b"\n", raw)


class CounterAndSignalTests(unittest.TestCase):
    def test_bump_turn_increments_and_persists(self):
        root = make_vault(self)
        capturelib.bump_turn(root)
        capturelib.bump_turn(root)
        state = capturelib.load_state(root)
        self.assertEqual(state["turns_since_capture"], 2)

    def test_record_signal_appends_kind_ref_at(self):
        root = make_vault(self)
        capturelib.record_signal(root, "vault-write", "specs/SPEC-001.md")
        state = capturelib.load_state(root)
        self.assertEqual(len(state["signals"]), 1)
        signal = state["signals"][0]
        self.assertEqual(signal["kind"], "vault-write")
        self.assertEqual(signal["ref"], "specs/SPEC-001.md")
        self.assertIn("at", signal)

    def test_signals_list_bounded_under_flood(self):
        root = make_vault(self)
        for i in range(capturelib.MAX_SIGNALS + 25):
            capturelib.record_signal(root, "vault-write", f"file-{i}.md")
        state = capturelib.load_state(root)
        self.assertEqual(len(state["signals"]), capturelib.MAX_SIGNALS)
        # Bounding drops the oldest first, so the newest survives.
        self.assertEqual(
            state["signals"][-1]["ref"], f"file-{capturelib.MAX_SIGNALS + 24}.md"
        )

    def test_counter_resets_when_opportunity_opens(self):
        root = make_vault(self)
        capturelib.bump_turn(root)
        capturelib.bump_turn(root)
        capturelib.record_signal(root, "vault-write", "x.md")
        capturelib.open_opportunity(root, "interval", ["interval"], [])
        state = capturelib.load_state(root)
        self.assertEqual(state["turns_since_capture"], 0)
        self.assertEqual(state["signals"], [])


class DueTests(unittest.TestCase):
    def _config(self, **overrides):
        config = dict(capturelib.DEFAULT_CONFIG)
        config.update(overrides)
        return config

    def _state(self, **overrides):
        state = dict(capturelib.DEFAULT_STATE)
        state["signals"] = list(state["signals"])
        state.update(overrides)
        return state

    def test_false_below_interval(self):
        state = self._state(turns_since_capture=3, signals=[{"kind": "vault-write"}])
        ok, reason = capturelib.due(state, self._config(interval=12))
        self.assertFalse(ok)
        self.assertIn("below interval", reason)

    def test_false_at_interval_with_zero_signals(self):
        state = self._state(turns_since_capture=12, signals=[])
        ok, reason = capturelib.due(state, self._config(interval=12))
        self.assertFalse(ok)
        self.assertIn("no signals", reason)

    def test_true_at_interval_with_one_signal(self):
        state = self._state(
            turns_since_capture=12, signals=[{"kind": "vault-write", "ref": "x"}]
        )
        ok, reason = capturelib.due(state, self._config(interval=12))
        self.assertTrue(ok)
        self.assertIn("interval reached", reason)

    def test_true_on_strong_signal_below_interval(self):
        state = self._state(
            turns_since_capture=1, signals=[{"kind": "handoff-written", "ref": "h.md"}]
        )
        ok, reason = capturelib.due(state, self._config(interval=12))
        self.assertTrue(ok)
        self.assertIn("strong signal", reason)

    def test_all_strong_kinds_trigger(self):
        for kind in capturelib.STRONG_SIGNAL_KINDS:
            state = self._state(turns_since_capture=0, signals=[{"kind": kind}])
            ok, _ = capturelib.due(state, self._config(interval=12))
            self.assertTrue(ok, f"{kind} should be due on its own")

    def test_enabled_false_suppresses_every_path(self):
        config = self._config(enabled=False, interval=1)
        strong_state = self._state(
            turns_since_capture=99, signals=[{"kind": "handoff-written"}]
        )
        ok, reason = capturelib.due(strong_state, config)
        self.assertFalse(ok)
        self.assertIn("disabled", reason)

    def test_due_is_pure_no_filesystem_touch(self):
        # No vault_root is even passed in; a real I/O call would TypeError.
        state = self._state(turns_since_capture=12, signals=[{"kind": "vault-write"}])
        capturelib.due(state, self._config())

    def test_non_dict_signal_entry_ignored_not_crashed(self):
        state = self._state(turns_since_capture=1, signals=["not-a-dict"])
        ok, reason = capturelib.due(state, self._config(interval=12))
        self.assertFalse(ok)

    def test_turns_since_capture_wrong_type_treated_as_zero(self):
        state = self._state(turns_since_capture="oops", signals=[])
        ok, reason = capturelib.due(state, self._config(interval=1))
        self.assertFalse(ok)


class OpportunityLifecycleTests(unittest.TestCase):
    def test_open_writes_opportunity_json(self):
        root = make_vault(self)
        directory = capturelib.open_opportunity(
            root, "interval", ["interval"], ["handoffs/h.md"]
        )
        path = directory / "opportunity.json"
        self.assertTrue(path.is_file())
        record = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(record["kind"], "interval")
        self.assertEqual(record["triggers"], ["interval"])
        self.assertEqual(record["evidence"], ["handoffs/h.md"])
        self.assertIsNone(record["outcome"])

    def test_open_marks_state_mutex(self):
        root = make_vault(self)
        directory = capturelib.open_opportunity(root, "phase", [], [])
        opp_id = directory.name
        state = capturelib.load_state(root)
        self.assertEqual(state["open_opportunity"], opp_id)
        self.assertEqual(state["reemits"], 0)
        self.assertIsNotNone(state["last_opportunity_at"])

    def test_close_clears_mutex_and_records_outcome(self):
        root = make_vault(self)
        directory = capturelib.open_opportunity(root, "phase", [], [])
        opp_id = directory.name
        capturelib.close_opportunity(root, opp_id, "fired")
        state = capturelib.load_state(root)
        self.assertIsNone(state["open_opportunity"])
        record = json.loads((directory / "opportunity.json").read_text(encoding="utf-8"))
        self.assertEqual(record["outcome"], "fired")
        self.assertIsNotNone(record["closed_at"])

    def test_close_unrelated_id_does_not_clear_current_mutex(self):
        root = make_vault(self)
        directory = capturelib.open_opportunity(root, "phase", [], [])
        opp_id = directory.name
        capturelib.close_opportunity(root, "OPP-not-the-open-one", "abandoned")
        state = capturelib.load_state(root)
        self.assertEqual(state["open_opportunity"], opp_id)

    def test_close_missing_opportunity_file_does_not_raise(self):
        root = make_vault(self)
        capturelib.close_opportunity(root, "OPP-never-existed", "abandoned")

    def test_two_opportunities_get_distinct_ids(self):
        root = make_vault(self)
        first = capturelib.open_opportunity(root, "interval", [], [])
        second = capturelib.open_opportunity(root, "interval", [], [])
        self.assertNotEqual(first.name, second.name)


if __name__ == "__main__":
    unittest.main()
