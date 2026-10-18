"""Adversarial tests for sensorlib, aimed at defects the implementation can
introduce: numeric conversion overflow, hostile sensor output, process-tree
cleanup on timeout, timestamp parsing and the cost sums.

Contract pinned beyond test_sensorlib.py:
    run_sensor never raises; every failure is an invalid Reading with a reason.
    parse_result raises only NoResultEvent for unusable text.
    Spend sums skip a cost they cannot read and never raise.
"""

import json
import os
import sys
import tempfile
import textwrap
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sensorlib  # noqa: E402

GOOD = '{"valid": true, "value": 2, "items": ["a"]}'
HUGE_INT_TEXT = "1" + "0" * 400  # a Python int that float() cannot hold
HUGE_INT_VALUE = int(HUGE_INT_TEXT)


def emit_bytes(tmp, payload):
    """argv for a sensor that writes exactly `payload` (bytes) to stdout."""
    path = Path(tmp) / "payload.bin"
    path.write_bytes(payload)
    code = "import sys; sys.stdout.buffer.write(open(sys.argv[1], 'rb').read())"
    return [sys.executable, "-c", code, str(path)]


def envelope(**overrides):
    base = {"type": "result", "total_cost_usd": 0.5, "num_turns": 1,
            "duration_ms": 10, "subtype": "success", "is_error": False,
            "result": "ok", "modelUsage": {}}
    base.update(overrides)
    return json.dumps(base)


class HostileSensorOutputTests(unittest.TestCase):
    def test_hostile_stdout_is_invalid_and_never_raises(self):
        """Adversarial where: an integer too large for float(), a deeply
        nested array, a BOM, a trailing log line or a leading log line
        escapes run_sensor as an exception (or parses as a valid reading)
        instead of reading invalid, so one odd sensor run crashes the loop."""
        rows = {
            "huge_int_value": ('{"valid": true, "value": %s, "items": []}' % HUGE_INT_TEXT).encode(),
            "deeply_nested_array": b"[" * 100000,
            "utf8_bom_prefix": b"\xef\xbb\xbf" + GOOD.encode(),
            "trailing_log_line": GOOD.encode() + b"\nsaved cache\n",
            "leading_log_line": b"starting\n" + GOOD.encode(),
            "invalid_utf8_bytes": b"\xff\xfe\x00garbage",
            "nan_value": b'{"valid": true, "value": NaN, "items": []}',
            "infinity_value": b'{"valid": true, "value": Infinity, "items": []}',
            "items_hold_numbers": b'{"valid": true, "value": 1, "items": ["a", 2]}',
            "items_hold_null": b'{"valid": true, "value": 1, "items": [null]}',
            "items_is_string": b'{"valid": true, "value": 1, "items": "a"}',
            "valid_is_truthy_string": b'{"valid": "true", "value": 1, "items": []}',
            "valid_is_one": b'{"valid": 1, "value": 1, "items": []}',
            "value_is_true": b'{"valid": true, "value": true, "items": []}',
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, payload in rows.items():
                with self.subTest(name=name):
                    try:
                        reading = sensorlib.run_sensor(emit_bytes(tmp, payload), tmp, 30)
                    except Exception as exc:  # the contract is "never raises"
                        self.fail("run_sensor raised %s: %s" % (type(exc).__name__, exc))
                    self.assertFalse(reading.valid, reading)
                    self.assertTrue(reading.reason)

    def test_large_valid_output_is_read_whole(self):
        """Adversarial where: a pipe-sized buffer boundary truncates a big
        sensor output (200k items) or a flood on stderr blocks the child, so
        a valid reading comes back short or the run hangs to its timeout."""
        items = ["file%d.py:match" % i for i in range(200000)]
        payload = json.dumps({"valid": True, "value": 7, "items": items}).encode()
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "big.py"
            script.write_text(textwrap.dedent("""
                import sys
                sys.stderr.write("e" * 1000000)
                sys.stdout.buffer.write(open(sys.argv[1], "rb").read())
            """))
            data = Path(tmp) / "data.bin"
            data.write_bytes(payload)
            reading = sensorlib.run_sensor([sys.executable, str(script), str(data)], tmp, 60)
        self.assertTrue(reading.valid, reading)
        self.assertEqual(len(reading.items), 200000)
        self.assertEqual(reading.items[-1], "file199999.py:match")

    def test_unrunnable_commands_are_invalid_readings(self):
        """Adversarial where: a missing binary, an empty argv, a missing
        working directory, a stderr-only sensor or a malformed argv element
        (None) raises out of run_sensor instead of reading invalid."""
        with tempfile.TemporaryDirectory() as tmp:
            stderr_only = [sys.executable, "-c", "import sys; sys.stderr.write('boom')"]
            rows = {
                "missing_binary": (["no_such_sensor_binary_zz"], tmp),
                "empty_argv": ([], tmp),
                "missing_cwd": ([sys.executable, "-c", "pass"], os.path.join(tmp, "absent")),
                "stderr_only_exit_zero": (stderr_only, tmp),
                "none_in_argv": ([sys.executable, None], tmp),
                "command_is_none": (None, tmp),
            }
            for name, (command, cwd) in rows.items():
                with self.subTest(name=name):
                    try:
                        reading = sensorlib.run_sensor(command, cwd, 10)
                    except Exception as exc:  # the contract is "never raises"
                        self.fail("run_sensor raised %s: %s" % (type(exc).__name__, exc))
                    self.assertFalse(reading.valid, reading)
                    self.assertTrue(reading.reason)


class TimeoutTreeTests(unittest.TestCase):
    def test_timeout_kills_the_sensors_child_process(self):
        """Adversarial where: only the direct child is killed on timeout, so a
        grandchild the sensor spawned outlives it (and keeps the stdout pipe
        open), writing to the project after the loop declared the run over."""
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "grandchild_survived.txt"
            grandchild = (
                "import time, pathlib; time.sleep(4); "
                "pathlib.Path(%r).write_text('alive')" % str(marker)
            )
            parent = Path(tmp) / "parent.py"
            parent.write_text(textwrap.dedent("""
                import subprocess, sys, time
                subprocess.Popen([sys.executable, "-c", %r])
                time.sleep(60)
            """ % grandchild))
            started = time.monotonic()
            reading = sensorlib.run_sensor([sys.executable, str(parent)], tmp, 1)
            elapsed = time.monotonic() - started
            self.assertFalse(reading.valid)
            self.assertIn("timed out", reading.reason)
            self.assertLess(elapsed, 20, "run_sensor waited on a surviving grandchild")
            time.sleep(6)
            self.assertFalse(marker.exists(), "grandchild outlived the timeout")


class ParseResultEdgeTests(unittest.TestCase):
    def test_unusable_numbers_raise_only_no_result_event(self):
        """Adversarial where: a cost or counter the float/int conversion
        cannot hold (huge int), a boolean cost, a string cost or a null cost
        escapes parse_result as OverflowError/TypeError instead of
        NoResultEvent, so a run's spend is lost rather than charged in full."""
        rows = {
            "cost_huge_int": '{"type": "result", "total_cost_usd": %s}' % HUGE_INT_TEXT,
            "cost_true": envelope(total_cost_usd=True),
            "cost_string": envelope(total_cost_usd="0.5"),
            "cost_null": envelope(total_cost_usd=None),
            "cost_infinity": envelope().replace("0.5", "Infinity"),
            "cost_nan": envelope().replace("0.5", "NaN"),
            "cost_missing": json.dumps({"type": "result", "num_turns": 1}),
            "deeply_nested": "[" * 100000,
            "bom_prefix": "﻿" + envelope(),
            "leading_log_line": "warning: hook\n" + envelope(),
            "none_input": None,
        }
        for name, text in rows.items():
            with self.subTest(name=name):
                try:
                    sensorlib.parse_result(text)
                except sensorlib.NoResultEvent:
                    continue
                except Exception as exc:
                    self.fail("raised %s instead of NoResultEvent: %s" % (type(exc).__name__, exc))
                self.fail("parse_result accepted unusable text")

    def test_odd_counters_and_usage_entries_degrade_to_zero(self):
        """Adversarial where: one bad field among good ones (a non-dict
        modelUsage entry, a huge-int token count, a string turn count, a
        null duration) aborts the parse or poisons the sums of the good
        models."""
        text = (
            '{"type": "result", "total_cost_usd": 0.5, "num_turns": "3", '
            '"duration_ms": null, "modelUsage": {'
            '"good": {"inputTokens": 5, "outputTokens": 7, '
            '"cacheReadInputTokens": 11, "cacheCreationInputTokens": 13}, '
            '"list_entry": [1, 2], "null_entry": null, '
            '"string_tokens": {"inputTokens": "9", "outputTokens": 3}, '
            '"huge_tokens": {"inputTokens": %s, "outputTokens": 1}}}' % HUGE_INT_TEXT
        )
        event = sensorlib.parse_result(text)
        self.assertEqual(event.input_tokens, 5)
        self.assertEqual(event.output_tokens, 7 + 3 + 1)
        self.assertEqual(event.cache_read_tokens, 11)
        self.assertEqual(event.cache_creation_tokens, 13)
        self.assertEqual(event.num_turns, 0)
        self.assertEqual(event.duration_ms, 0)

    def test_modelusage_that_is_not_a_mapping_reads_as_zero_tokens(self):
        """Adversarial where: modelUsage as a list, string or null is iterated
        as a mapping and raises, losing the cost the envelope did carry."""
        for name, value in {"list": [{"inputTokens": 1}], "null": None, "string": "x"}.items():
            with self.subTest(name=name):
                event = sensorlib.parse_result(envelope(modelUsage=value))
                self.assertAlmostEqual(event.cost_usd, 0.5)
                self.assertEqual(event.input_tokens, 0)

    def test_integer_zero_cost_is_a_real_result_event(self):
        """Adversarial where: a falsy-cost check (`if not cost`) rejects an
        integer 0 total_cost_usd as missing, so a free run reads as no event
        and gets charged its full run budget."""
        event = sensorlib.parse_result(envelope(total_cost_usd=0))
        self.assertEqual(event.cost_usd, 0.0)
        self.assertIsInstance(event.cost_usd, float)


class JudgeEdgeTests(unittest.TestCase):
    def test_judge_rejects_invalid_input_and_judges_by_multiset(self):
        """Adversarial where: an invalid reading, a typo'd or wrongly cased
        direction is judged instead of raising ValueError, or a reordering of
        identical items is read as a change."""
        valid = sensorlib.Reading(valid=True, value=3, items=["a", "b"])
        invalid = sensorlib.Reading(valid=False, reason="timed out")
        rows = {
            "invalid_before": (invalid, valid, "down"),
            "invalid_after": (valid, invalid, "down"),
            "both_invalid": (invalid, invalid, "down"),
            "direction_uppercase": (valid, valid, "DOWN"),
            "direction_none": (valid, valid, None),
            "direction_empty": (valid, valid, ""),
        }
        for name, args in rows.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    sensorlib.judge(*args)
        reordered = sensorlib.Reading(valid=True, value=3, items=["b", "a"])
        self.assertEqual(sensorlib.judge(valid, reordered, "down"), "neutral")
        better_reordered = sensorlib.Reading(valid=True, value=2, items=["b", "a"])
        self.assertEqual(sensorlib.judge(valid, better_reordered, "down"), "helpful")

    def test_judge_direction_up_mirrors_down(self):
        """Adversarial where: the sign flip for direction "up" is applied to
        the item rule too, or forgotten for the value rule."""
        before = sensorlib.Reading(valid=True, value=10, items=["a"])
        rows = {
            "up_value_rises": (12, ["a"], "up", "helpful"),
            "up_value_falls": (8, ["a"], "up", "harmful"),
            "up_value_flat": (10, ["a"], "up", "neutral"),
            "up_rises_but_new_item": (12, ["a", "b"], "up", "harmful"),
            "down_value_falls": (8, ["a"], "down", "helpful"),
            "down_value_rises": (12, ["a"], "down", "harmful"),
            "down_item_removed_value_flat": (10, [], "down", "neutral"),
        }
        for name, (after_value, items, direction, want) in rows.items():
            with self.subTest(name=name):
                after = sensorlib.Reading(valid=True, value=after_value, items=items)
                self.assertEqual(sensorlib.judge(before, after, direction), want)


class SpendEdgeTests(unittest.TestCase):
    def test_timestamp_forms_land_on_the_right_utc_day(self):
        """Adversarial where: a trailing Z, a negative offset that crosses
        midnight, a naive timestamp, fractional seconds, a date-only value or
        an unreadable ts is bucketed on the wrong day or raises."""
        rows = {
            "z_suffix": ("2026-03-01T23:59:59Z", "2026-03-01"),
            "z_with_fraction": ("2026-03-01T23:59:59.999999Z", "2026-03-01"),
            "offset_minus5_crosses_midnight": ("2026-03-01T23:30:00-05:00", "2026-03-02"),
            "offset_plus9_crosses_back": ("2026-03-02T05:00:00+09:00", "2026-03-01"),
            "naive_counts_as_utc": ("2026-03-01T23:59:59", "2026-03-01"),
            "exactly_midnight_utc": ("2026-03-02T00:00:00+00:00", "2026-03-02"),
            "one_microsecond_before_midnight": ("2026-03-01T23:59:59.999999+00:00", "2026-03-01"),
        }
        for name, (ts, day) in rows.items():
            with self.subTest(name=name):
                self.assertEqual(sensorlib.spend_by_day([{"ts": ts, "cost_usd": 1.5}]), {day: 1.5})
        unreadable = {"garbage": "yesterday", "none": None, "number": 1700000000,
                      "empty": "", "month_13": "2026-13-01T00:00:00Z"}
        for name, ts in unreadable.items():
            with self.subTest(name="unreadable_" + name):
                self.assertEqual(
                    sensorlib.spend_by_day([{"ts": ts, "cost_usd": 1.5}]),
                    {sensorlib.UNKNOWN_DAY: 1.5})

    def test_spend_today_converts_an_aware_now_to_utc(self):
        """Adversarial where: spend_today takes the calendar date of `now` in
        its own offset instead of UTC, so a local late evening reads the
        wrong day's budget."""
        rows = [
            {"ts": "2026-03-01T10:00:00Z", "cost_usd": 1.0},
            {"ts": "2026-03-02T01:00:00Z", "cost_usd": 4.0},
        ]
        now_local = datetime(2026, 3, 1, 22, 0, tzinfo=timezone(timedelta(hours=-5)))
        self.assertEqual(sensorlib.spend_today(rows, now_local), 4.0)
        now_naive = datetime(2026, 3, 1, 22, 0)
        self.assertEqual(sensorlib.spend_today(rows, now_naive), 1.0)
        self.assertEqual(sensorlib.spend_today(rows, datetime(2026, 4, 1, tzinfo=timezone.utc)), 0.0)

    def test_unreadable_costs_are_skipped_without_raising(self):
        """Adversarial where: one bad cost among good rows (huge int, NaN,
        Infinity, a numeric string, a boolean, null) raises or poisons the
        sum of the good rows, in the daily and the lifetime sums alike."""
        ts = "2026-03-01T12:00:00Z"
        bad = [HUGE_INT_VALUE, float("nan"), float("inf"), "2.0", True, None]
        rows = [{"ts": ts, "cost_usd": 1.0}, {"ts": ts, "cost_usd": 2.0}]
        rows += [{"ts": ts, "cost_usd": b} for b in bad]
        rows += [{"ts": ts}, {"kind": "review"}]
        self.assertEqual(sensorlib.spend_lifetime(rows), 3.0)
        self.assertEqual(sensorlib.spend_by_day(rows), {"2026-03-01": 3.0})

    def test_unreadable_ts_still_counts_toward_todays_spend(self):
        """Adversarial where: a costed row whose ts is corrupt, missing or
        not a string is dropped from the day sums, so a damaged ledger
        undercounts today's spend and the loop overspends its daily budget."""
        now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        for name, ts in {"garbage": "yesterday", "none": None, "number": 17}.items():
            with self.subTest(name=name):
                rows = [
                    {"ts": ts, "cost_usd": 2.0},
                    {"ts": "2026-03-01T01:00:00Z", "cost_usd": 1.0},
                    {"ts": "2026-02-28T01:00:00Z", "cost_usd": 8.0},
                ]
                self.assertEqual(sensorlib.spend_today(rows, now), 3.0)
                self.assertEqual(sensorlib.spend_by_day(rows)[sensorlib.UNKNOWN_DAY], 2.0)
                self.assertEqual(sensorlib.spend_lifetime(rows), 11.0)

    def test_unreadable_ts_inherits_the_preceding_rows_day(self):
        """Adversarial where: a costed row with a corrupt ts is counted
        against every day forever, so one damaged line throttles the loop
        permanently; or it is attached to the following row's day, or to the
        wrong day when an unreadable row follows another unreadable one."""
        now = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)
        rows = [
            {"ts": "2026-03-01T10:00:00Z", "cost_usd": 1.0},
            {"ts": "yesterday", "cost_usd": 2.0},
            {"cost_usd": 4.0},
            {"ts": "2026-03-02T01:00:00Z", "cost_usd": 8.0},
        ]
        self.assertEqual(sensorlib.spend_by_day(rows), {"2026-03-01": 7.0, "2026-03-02": 8.0})
        self.assertEqual(sensorlib.spend_today(rows, now), 8.0)
        self.assertEqual(sensorlib.spend_lifetime(rows), 15.0)

    def test_negative_total_cost_in_a_result_event_is_rejected(self):
        """Adversarial where: a negative total_cost_usd is accepted as a
        result event and reduces the spend charged for the run."""
        with self.assertRaises(sensorlib.NoResultEvent):
            sensorlib.parse_result(envelope(total_cost_usd=-0.01))

    def test_timestamps_at_the_datetime_range_edge_do_not_raise(self):
        """Adversarial where: a ts at year 9999 or year 1 whose UTC conversion
        leaves the datetime range raises OverflowError out of the day sums
        instead of landing in the unknown bucket, crashing the budget check
        on one corrupt ledger row."""
        now = datetime(2026, 3, 1, 12, tzinfo=timezone.utc)
        for name, ts in {"year_9999_west_offset": "9999-12-31T23:59:59-05:00",
                         "year_1_east_offset": "0001-01-01T00:00:00+05:00"}.items():
            with self.subTest(name=name):
                rows = [{"ts": ts, "cost_usd": 1.5}]
                self.assertEqual(sensorlib.spend_by_day(rows), {sensorlib.UNKNOWN_DAY: 1.5})
                self.assertEqual(sensorlib.spend_today(rows, now), 1.5)

    def test_negative_cost_cannot_erase_recorded_spend(self):
        """Adversarial where: a corrupt row with a negative cost_usd is
        summed as-is, cancelling real spend and letting a loop pass its
        daily or lifetime budget check it should have failed."""
        rows = [
            {"ts": "2026-03-01T12:00:00Z", "cost_usd": 5.0},
            {"ts": "2026-03-01T13:00:00Z", "cost_usd": -4.0},
        ]
        self.assertGreaterEqual(sensorlib.spend_lifetime(rows), 5.0)
        self.assertGreaterEqual(sensorlib.spend_by_day(rows)["2026-03-01"], 5.0)

    def test_spend_sums_accept_a_generator_and_an_empty_ledger(self):
        """Adversarial where: the day sum consumes a one-shot iterable twice,
        or an empty ledger raises / returns None instead of zero."""
        gen = ({"ts": "2026-03-01T12:00:00Z", "cost_usd": c} for c in (1.0, 2.0))
        self.assertEqual(sensorlib.spend_by_day(gen), {"2026-03-01": 3.0})
        self.assertEqual(sensorlib.spend_lifetime(iter([])), 0)
        self.assertEqual(sensorlib.spend_today([], datetime(2026, 3, 1, tzinfo=timezone.utc)), 0.0)
        self.assertEqual(sensorlib.spend_by_day([]), {})


if __name__ == "__main__":
    unittest.main()
