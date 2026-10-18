"""Tests for sensorlib: the result-event parser, the domain sensor runner,
the ledger spend sums and the before/after change judgment.

Public contract these tests pin (module `plugin/cli/sensorlib.py`):

    NoResultEvent(ValueError)
        raised by parse_result; its message contains "no result event".

    parse_result(text: str) -> ResultEvent
        `text` is the stdout of `claude -p --output-format json`. Returns an
        object with attributes: cost_usd (float, from `total_cost_usd`),
        num_turns (int), duration_ms (int), subtype (str), is_error (bool),
        result (str or None; None when the envelope has no `result` key),
        input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens
        (ints, each summed over every model in `modelUsage`; the top-level
        `usage` block is never read).

    Reading(valid, value=None, items=(), reason=None)
        valid: bool; value: float or None; items: list of identity strings,
        duplicates kept; reason: non-empty str whenever valid is False.

    run_sensor(command: list[str], cwd, timeout: float) -> Reading
        Runs `command` (an argv list) with working directory `cwd`, parses its
        stdout as {"valid": bool, "value": number, "items": [str, ...]}.
        Never raises: every failure is an invalid Reading carrying a reason.

    judge(before: Reading, after: Reading, direction: str) -> str
        direction is "down" or "up". Returns "helpful", "neutral" or
        "harmful". Items compare as a multiset.

    Ledger rows are dicts. A row may carry `ts` (ISO-8601 with an explicit
    offset, e.g. "2026-03-01T23:59:00+00:00") and `cost_usd` (number). Rows
    without `cost_usd` (transitions, reviews) contribute nothing.

    spend_by_day(rows) -> dict[str, float]    keys are UTC "YYYY-MM-DD"
    spend_today(rows, now: datetime) -> float  sum for now's UTC day
    spend_lifetime(rows) -> float              sum over every row
"""

import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sensorlib  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "result_events"


def fixture_text(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def emit(stdout_text):
    """argv for a sensor that prints exactly `stdout_text` and exits 0."""
    return [sys.executable, "-c", "import sys; sys.stdout.write(%r)" % stdout_text]


def ok(value, items=()):
    return sensorlib.Reading(valid=True, value=value, items=list(items))


class ParseResultTests(unittest.TestCase):
    def test_envelope_fields_come_from_the_real_events(self):
        """Adversarial where: tokens read from the top-level `usage` block
        (zeroed on a budget stop, and different from `modelUsage` on a resumed
        session) or summed over one model instead of all, and the cost read
        from `usage` or recomputed instead of `total_cost_usd`."""
        rows = {
            # r1: max-turns stop, no `result` key
            "r1_error_max_turns": ("r1.json", dict(
                cost_usd=0.041615, num_turns=2, duration_ms=20926,
                subtype="error_max_turns", is_error=True, result=None,
                input_tokens=10, output_tokens=171,
                cache_read_tokens=0, cache_creation_tokens=20375)),
            # r2: resumed success; modelUsage input is 20 while usage says 10
            "r2_resumed_success": ("r2.json", dict(
                cost_usd=0.0463805, num_turns=1, duration_ms=1675,
                subtype="success", is_error=False, result="ok",
                input_tokens=20, output_tokens=219,
                cache_read_tokens=20375, cache_creation_tokens=21614)),
            # r3: budget stop, `usage` is all zeros and `iterations` empty
            "r3_budget_stop_empty_usage": ("r3.json", dict(
                cost_usd=0.0174133, num_turns=1, duration_ms=3987,
                subtype="error_max_budget_usd", is_error=True, result=None,
                input_tokens=10, output_tokens=280,
                cache_read_tokens=13053, cache_creation_tokens=7349)),
            # two models in modelUsage: totals are the sum of both
            "capture_worker_two_models": ("capture_worker.json", dict(
                cost_usd=0.8262580000000002, num_turns=28, duration_ms=227857,
                subtype="success", is_error=False,
                result="Both lessons synced into the catalog. Extraction complete.",
                input_tokens=1013 + 48, output_tokens=25 + 19100,
                cache_read_tokens=0 + 1829360,
                cache_creation_tokens=0 + 67038)),
        }
        for name, (fixture, expected) in rows.items():
            with self.subTest(name=name):
                event = sensorlib.parse_result(fixture_text(fixture))
                for field, want in expected.items():
                    got = getattr(event, field)
                    if isinstance(want, float):
                        self.assertAlmostEqual(got, want, places=9, msg=field)
                    else:
                        self.assertEqual(got, want, msg=field)
                self.assertIsInstance(event.is_error, bool)

    def test_text_without_a_result_event_raises_no_result_event(self):
        """Adversarial where: empty, truncated (down to one missing closing
        brace) or non-result JSON parsed into a zero-cost event, so a run that
        produced nothing would be charged nothing against the budget."""
        r2 = fixture_text("r2.json")
        rows = {
            "empty": "",
            "whitespace_only": "  \n\t\n",
            "truncated_in_half": r2[: len(r2) // 2],
            "truncated_one_char_short": fixture_text("r3.json").rstrip()[:-1],
            "json_array": "[]",
            "empty_object": "{}",
            "system_event_not_result": '{"type":"system","subtype":"init","session_id":"s"}',
            "plain_text": "Error: not logged in",
        }
        for name, text in rows.items():
            with self.subTest(name=name):
                with self.assertRaises(sensorlib.NoResultEvent) as ctx:
                    sensorlib.parse_result(text)
                self.assertIn("no result event", str(ctx.exception).lower())


class RunSensorTests(unittest.TestCase):
    def test_unusable_output_is_an_invalid_reading_with_a_reason(self):
        """Adversarial where: garbage, `valid: false`, a non-numeric, boolean
        or NaN value, a non-list items field, empty output, a missing binary
        or a hung sensor read as "no findings" (a valid zero) instead of
        halting the loop."""
        rows = {
            "garbage": emit("garbage"),
            "valid_false": emit('{"valid": false}'),
            "valid_false_with_good_looking_fields":
                emit('{"valid": false, "value": 0, "items": []}'),
            "non_numeric_value": emit('{"valid": true, "value": "abc", "items": []}'),
            "boolean_value": emit('{"valid": true, "value": true, "items": []}'),
            "nan_value": emit('{"valid": true, "value": NaN, "items": []}'),
            "items_is_a_string": emit('{"valid": true, "value": 3, "items": "abc"}'),
            "empty_stdout": emit(""),
            "exits_nonzero_with_no_output":
                [sys.executable, "-c", "import sys; sys.exit(3)"],
            "missing_binary": ["compass-no-such-sensor-binary-xyz"],
        }
        for name, command in rows.items():
            with self.subTest(name=name):
                reading = sensorlib.run_sensor(command, cwd=os.getcwd(), timeout=30)
                self.assertFalse(reading.valid)
                self.assertTrue(
                    isinstance(reading.reason, str) and reading.reason.strip(),
                    "an invalid reading must carry a reason",
                )

    def test_sensor_that_outlives_its_timeout_is_invalid_and_returns_promptly(self):
        """Adversarial where: the timeout is not enforced, so a hung sensor
        blocks the loop for its full sleep, or the call raises
        subprocess.TimeoutExpired instead of returning an invalid reading."""
        command = [sys.executable, "-c", "import time; time.sleep(60)"]
        started = time.monotonic()
        reading = sensorlib.run_sensor(command, cwd=os.getcwd(), timeout=1.5)
        elapsed = time.monotonic() - started
        self.assertFalse(reading.valid)
        self.assertIn("time", reading.reason.lower())
        self.assertLess(elapsed, 20, "the sleeping sensor was not stopped at the timeout")

    def test_well_formed_output_is_a_valid_reading(self):
        """Adversarial where: an empty items list with `valid: true` rejected
        or conflated with an invalid reading, duplicate identities collapsed
        to a set (which breaks the multiset judgment), or the command run from
        the wrong directory instead of the given project root."""
        rows = {
            "valid_zero_with_no_items": (
                '{"valid": true, "value": 0, "items": []}', 0.0, []),
            "integer_value_becomes_number": (
                '{"valid": true, "value": 3, "items": ["a.py|x"]}', 3.0, ["a.py|x"]),
            "float_value": (
                '{"valid": true, "value": 2.5, "items": ["a.py|x", "b.py|y"]}',
                2.5, ["a.py|x", "b.py|y"]),
            "duplicate_items_are_kept": (
                '{"valid": true, "value": 2, "items": ["a.py|x", "a.py|x"]}',
                2.0, ["a.py|x", "a.py|x"]),
            "trailing_newline": (
                '{"valid": true, "value": 1, "items": ["z"]}\n', 1.0, ["z"]),
        }
        for name, (stdout_text, value, items) in rows.items():
            with self.subTest(name=name):
                reading = sensorlib.run_sensor(
                    emit(stdout_text), cwd=os.getcwd(), timeout=30)
                self.assertTrue(reading.valid, reading.reason)
                self.assertEqual(reading.value, value)
                self.assertEqual(list(reading.items), items)

    def test_sensor_runs_in_the_given_working_directory(self):
        """Adversarial where: the sensor inherits the caller's cwd instead of
        the project root, so a relative-path sensor reads the wrong tree."""
        code = (
            "import json, os; "
            "print(json.dumps({'valid': True, 'value': 0, 'items': [os.getcwd()]}))"
        )
        with tempfile.TemporaryDirectory() as tmp:
            reading = sensorlib.run_sensor(
                [sys.executable, "-c", code], cwd=tmp, timeout=30)
            self.assertTrue(reading.valid, reading.reason)
            self.assertEqual(
                os.path.normcase(os.path.realpath(reading.items[0])),
                os.path.normcase(os.path.realpath(tmp)),
            )


class JudgeTests(unittest.TestCase):
    def test_classification_of_before_after_pairs(self):
        """Adversarial where: items compared as a set (a duplicate appearing
        once more, or one more copy than before, goes unseen), a new item
        forgiven because the value improved, direction ignored, or one
        removed copy of three identical items misread as a new item."""
        three = ["f.py|print(x)"] * 3
        rows = {
            "down_value_fell_no_new_item": (
                ok(5, ["a|1", "b|2"]), ok(3, ["a|1"]), "down", "helpful"),
            "down_value_rose": (
                ok(5, ["a|1"]), ok(7, ["a|1", "b|2"]), "down", "harmful"),
            "down_value_rose_with_no_item_change": (
                ok(5, ["a|1"]), ok(6, ["a|1"]), "down", "harmful"),
            "down_unchanged": (
                ok(5, ["a|1"]), ok(5, ["a|1"]), "down", "neutral"),
            "down_fewer_items_same_value": (
                ok(5, ["a|1", "b|2"]), ok(5, ["a|1"]), "down", "neutral"),
            "down_value_fell_but_a_new_item_appeared": (
                ok(5, ["a|1", "b|2"]), ok(3, ["a|1", "c|3"]), "down", "harmful"),
            "down_unchanged_value_but_a_new_item": (
                ok(5, ["a|1"]), ok(5, ["a|1", "c|3"]), "down", "harmful"),
            "duplicate_appears_once_more": (
                ok(1, ["f.py|x"]), ok(1, ["f.py|x", "f.py|x"]), "down", "harmful"),
            "duplicate_appears_once_more_while_value_falls": (
                ok(3, ["f.py|x", "g.py|y", "h.py|z"]),
                ok(2, ["f.py|x", "f.py|x"]), "down", "harmful"),
            "one_of_three_identical_items_removed": (
                ok(3, three), ok(2, three[:2]), "down", "helpful"),
            "up_value_rose": (
                ok(4, ["a|1"]), ok(6, ["a|1"]), "up", "helpful"),
            "up_value_fell": (
                ok(6, ["a|1"]), ok(4, ["a|1"]), "up", "harmful"),
            "up_unchanged": (
                ok(6, ["a|1"]), ok(6, ["a|1"]), "up", "neutral"),
            "up_value_rose_but_a_new_item": (
                ok(4, ["a|1"]), ok(6, ["a|1", "b|2"]), "up", "harmful"),
            "item_order_is_irrelevant": (
                ok(5, ["a|1", "b|2"]), ok(3, ["b|2", "a|1"]), "down", "helpful"),
        }
        for name, (before, after, direction, want) in rows.items():
            with self.subTest(name=name):
                self.assertEqual(sensorlib.judge(before, after, direction), want)


def row(ts, cost=None, **extra):
    r = {"ts": ts}
    if cost is not None:
        r["cost_usd"] = cost
    r.update(extra)
    return r


LEDGER = [
    row("2026-03-01T23:59:00+00:00", 0.10, event="run"),
    row("2026-03-01T23:59:30+00:00", event="transition"),
    row("2026-03-02T00:00:00+00:00", 0.05, event="run"),
    row("2026-03-02T00:01:00+00:00", 0.20, event="crashed"),
    row("2026-03-02T00:02:00+00:00", event="review"),
]


class SpendTests(unittest.TestCase):
    def test_spend_by_day_splits_on_the_utc_midnight(self):
        """Adversarial where: 23:59 and 00:01 UTC land in one day, a row at
        exactly 00:00:00 UTC lands in the previous day, or rows without a
        cost are counted or break the sum."""
        days = sensorlib.spend_by_day(LEDGER)
        self.assertAlmostEqual(days["2026-03-01"], 0.10, places=9)
        self.assertAlmostEqual(days["2026-03-02"], 0.25, places=9)

    def test_spend_today_uses_the_utc_day_of_now(self):
        """Adversarial where: the day is taken in the machine's local zone
        instead of UTC, the day edge is off by one at 23:59:59 or 00:00:00,
        or a day with no rows raises instead of returning zero."""
        utc = timezone.utc
        rows = {
            "last_second_of_the_first_day": (
                datetime(2026, 3, 1, 23, 59, 59, tzinfo=utc), 0.10),
            "first_second_of_the_second_day": (
                datetime(2026, 3, 2, 0, 0, 0, tzinfo=utc), 0.25),
            "local_evening_is_the_next_utc_day": (
                datetime(2026, 3, 1, 22, 0, 0, tzinfo=timezone(timedelta(hours=-3))),
                0.25),
            "day_with_no_rows": (datetime(2026, 3, 9, 12, 0, 0, tzinfo=utc), 0.0),
        }
        for name, (now, want) in rows.items():
            with self.subTest(name=name):
                self.assertAlmostEqual(
                    sensorlib.spend_today(LEDGER, now), want, places=9)

    def test_spend_lifetime_sums_every_costed_row(self):
        """Adversarial where: lifetime spend drops rows outside today or
        counts rows that carry no cost, and an empty ledger raises."""
        self.assertAlmostEqual(sensorlib.spend_lifetime(LEDGER), 0.35, places=9)
        self.assertEqual(sensorlib.spend_lifetime([]), 0)


if __name__ == "__main__":
    unittest.main()
