"""Tests for `looplib`, the control-loop library: the loop definition, the
state machine, the state file, the ledger and the run lock.

Public API under test (module `looplib`, importable from `plugin/cli`). Every
`loop_dir` is the loop's folder (`.compass/loops/LOOP-NNN-name/`) and holds
`loop.json`, `state.json` and `ledger.jsonl`:

    STATES, RESTING, WORKING, EVENTS
        frozensets of state and event names. RESTING is idle, throttled,
        paused, halted, done; WORKING is sensing, gating, controlling,
        actuating, verifying; STATES is their union.
    TRANSITIONS: dict[(state, event)] -> state
        The one declared table of the state machine.
    TransitionError(ValueError), DefinitionError(ValueError),
    StateError(ValueError), LockHeld(RuntimeError)
    transition(state, event) -> str
        Pure lookup in TRANSITIONS; raises TransitionError for any pair not in
        the table, including an unknown state or an unknown event.
    advance(loop_dir, event, reason) -> str
        Reads state.json, applies transition(), writes the new state back and
        appends a ledger row {"type": "transition", "from", "event", "to",
        "reason"}. An illegal event raises TransitionError and leaves
        state.json and the ledger untouched.

    load_definition(loop_dir) -> dict
        Reads and validates `<loop_dir>/loop.json` and returns it as a dict
        keyed exactly as the file. Raises DefinitionError whose message names
        the offending field. Keys (all required unless noted):
          sensor_command (non-blank str), sensor_timeout_s (number > 0),
          target (number), direction ("down" | "up"),
          controller ("first" | "command"),
          controller_command (non-blank str; required only when controller
          is "command"), wip_command (non-blank str, optional),
          model (str), max_turns (int > 0), max_budget_usd (number > 0),
          timeout_s (number > 0), allowed_tools (list of str),
          daily_budget_usd (number >= 0), total_budget_usd (number >= 0),
          wip_limit (int >= 0), max_actuator_failures (int >= 0),
          max_harmful_runs (int >= 0), max_runs_without_help (int >= 0).
        Any other key is an unknown key.

    read_state(loop_dir) -> dict
        Parsed `state.json`; a missing file reads as {"state": "idle"}.
        Raises StateError for an unparseable file or a "state" value outside
        STATES.
    write_state(loop_dir, state_dict) -> None
        Writes `state.json` pretty-printed (indent 2, multi-line) with LF line
        endings on every platform, through an atomic replace a reader never sees torn.

    append_ledger(loop_dir, row) -> None
        Appends `row` as one JSON line, LF-terminated, to `ledger.jsonl`.
        Every row carries `ts`, ISO-8601 with a UTC offset (for example
        2026-10-18T18:09:07+00:00); append_ledger stamps the current time when
        the row has no `ts` and keeps a caller-supplied one. Spend is always
        the `cost_usd` key.
    read_ledger(loop_dir) -> (rows, skipped)
        rows: every parsed JSON-object line in file order. skipped: one
        {"line": <1-based line number>, "text": <raw line>} per non-blank line
        that does not parse as a JSON object. Never raises on a bad line; a
        missing ledger reads as ([], []).
    fold(rows) -> dict
        Counters over ledger rows. Row shapes:
          run:        {"type": "run", "run_id", "outcome", "item", "cost_usd"}
                      outcome is one of helpful, neutral, harmful (verified:
                      the run reached `verifying` and left an increment),
                      failed, throttled, crashed.
          review:     {"type": "review", "run_id", "decision": accept|reject}
          transition: {"type": "transition", "from", "event", "to", "reason"}
        A transition row whose event is "resume" resets the three consecutive
        counters. Returned keys:
          wip                    count of verified runs with no review row
          held_items             sorted items of those unreviewed runs
          consecutive_failures   trailing failed runs since the last resume,
                                 ended by any verified run
          consecutive_harmful    trailing harmful runs since the last resume,
                                 ended by a helpful or neutral run
          runs_without_help      verified runs since the last helpful run (or
                                 the last resume); failed, throttled and
                                 crashed runs never count

    acquire_lock(lock_path, timeout_s, now=None) -> None
        Creates the lock file with O_CREAT|O_EXCL (parents created), holding
        JSON {"pid": os.getpid(), "started": <epoch seconds>}; `now` defaults
        to time.time(). Raises LockHeld when the file exists.
    release_lock(lock_path) -> None
    is_stale(lock_path, timeout_s, now=None) -> bool
        True when `now - started` exceeds timeout_s + 600.
    recover(loop_dir, lock_path, definition, now=None) -> bool
        A resting state on disk: returns False and changes nothing. A working
        state with a stale or absent lock: removes the lock, sets state to
        idle, appends a run row {"outcome": "crashed", "run_id": <the state's
        run_id>, "cost_usd": definition["max_budget_usd"]} and a transition
        row with event "crash-recovered"; returns True. A working state with a
        live lock raises LockHeld and changes nothing."""

import itertools
import json
import os
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import looplib  # noqa: E402

RESTING = ["idle", "throttled", "paused", "halted", "done"]
WORKING = ["sensing", "gating", "controlling", "actuating", "verifying"]

# The Design table, one (state, event) -> state entry per listed pair.
EXPECTED_TABLE = {
    ("idle", "start"): "sensing",
    ("throttled", "start"): "sensing",
    ("sensing", "at-set-point"): "done",
    ("sensing", "invalid-reading"): "halted",
    ("sensing", "off-set-point"): "gating",
    ("gating", "wip-full"): "throttled",
    ("gating", "daily-budget-spent"): "throttled",
    ("gating", "total-budget-spent"): "halted",
    ("gating", "clear"): "controlling",
    ("controlling", "selected"): "actuating",
    ("controlling", "nothing-selected"): "halted",
    ("actuating", "finished"): "verifying",
    ("actuating", "failed"): "idle",
    ("actuating", "failed-limit"): "halted",
    ("actuating", "controls-changed"): "halted",
    ("verifying", "helpful"): "idle",
    ("verifying", "neutral"): "idle",
    ("verifying", "harmful"): "idle",
    ("verifying", "harmful-limit"): "halted",
    ("verifying", "no-progress-limit"): "halted",
    ("verifying", "controls-changed"): "halted",
    ("idle", "pause"): "paused",
    ("throttled", "pause"): "paused",
    ("paused", "resume"): "idle",
    ("halted", "resume"): "idle",
    ("done", "reopen"): "idle",
    ("sensing", "crash-recovered"): "idle",
    ("gating", "crash-recovered"): "idle",
    ("controlling", "crash-recovered"): "idle",
    ("actuating", "crash-recovered"): "idle",
    ("verifying", "crash-recovered"): "idle",
}

ALL_EVENTS = sorted({event for (_state, event) in EXPECTED_TABLE})

BASE_DEFINITION = {
    "sensor_command": "python sense.py",
    "sensor_timeout_s": 41,
    "target": 3,
    "direction": "down",
    "controller": "first",
    "model": "haiku",
    "max_turns": 7,
    "max_budget_usd": 0.37,
    "timeout_s": 523,
    "allowed_tools": ["Read", "Edit"],
    "daily_budget_usd": 1.9,
    "total_budget_usd": 8.3,
    "wip_limit": 4,
    "max_actuator_failures": 4,
    "max_harmful_runs": 3,
    "max_runs_without_help": 8,
}


def run_row(run_id, outcome, item=None, cost=0.0):
    return {
        "type": "run",
        "run_id": run_id,
        "outcome": outcome,
        "item": item,
        "cost_usd": cost,
    }


def without_ts(row):
    return {k: v for k, v in row.items() if k != "ts"}


def review_row(run_id, decision="accept"):
    return {"type": "review", "run_id": run_id, "decision": decision}


def transition_row(event, frm="halted", to="idle"):
    return {
        "type": "transition",
        "from": frm,
        "event": event,
        "to": to,
        "reason": "test",
    }


class LoopDirTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.loop_dir = self.root / "LOOP-001-demo"
        self.loop_dir.mkdir()
        self.lock_path = self.root / "tmp" / "loops" / "LOOP-001.lock"

    def write_definition(self, mapping):
        (self.loop_dir / "loop.json").write_text(
            json.dumps(mapping), encoding="utf-8", newline="\n"
        )

    def ledger_rows(self):
        return looplib.read_ledger(self.loop_dir)[0]


class TestTransitionTable(unittest.TestCase):
    def test_declared_table_and_state_sets_match_design(self):
        """Adversarial where: the declared table (or a state set) drifts from
        the Design table, so a row is silently added, dropped or retargeted."""
        actual_table = dict(looplib.TRANSITIONS)
        self.assertEqual(actual_table, EXPECTED_TABLE)
        for name, actual, expected in [
            ("RESTING", looplib.RESTING, RESTING),
            ("WORKING", looplib.WORKING, WORKING),
            ("STATES", looplib.STATES, RESTING + WORKING),
        ]:
            with self.subTest(name=name):
                self.assertEqual(set(actual), set(expected))

    def test_every_state_event_pair_in_the_full_product(self):
        """Adversarial where: transition() accepts a pair the table does not
        list (for example `resume` from a working state, or `crash-recovered`
        from a resting state) or retargets a listed one; every pair of the
        full state x event product is checked, none sampled."""
        for state, event in itertools.product(RESTING + WORKING, ALL_EVENTS):
            with self.subTest(state=state, event=event):
                if (state, event) in EXPECTED_TABLE:
                    self.assertEqual(
                        looplib.transition(state, event),
                        EXPECTED_TABLE[(state, event)],
                    )
                else:
                    with self.assertRaises(looplib.TransitionError):
                        looplib.transition(state, event)

    def test_unknown_state_or_event_is_refused(self):
        """Adversarial where: a state or event name outside the vocabulary
        (wrong case, trailing space, empty) falls through to a default
        instead of raising."""
        rows = [
            ("unknown state", "Idle", "start"),
            ("padded state", "idle ", "start"),
            ("empty state", "", "start"),
            ("unknown event", "idle", "Start"),
            ("padded event", "idle", "start "),
            ("empty event", "idle", ""),
        ]
        for name, state, event in rows:
            with self.subTest(name=name):
                with self.assertRaises(looplib.TransitionError):
                    looplib.transition(state, event)


class TestAdvance(LoopDirTestCase):
    def test_advance_writes_state_and_ledger_with_reason(self):
        """Adversarial where: a legal transition updates state.json but
        forgets the ledger row (or records the wrong from/to/reason), so the
        record of why the loop moved is lost."""
        looplib.write_state(self.loop_dir, {"state": "idle"})
        new = looplib.advance(self.loop_dir, "start", "scheduled tick")
        self.assertEqual(new, "sensing")
        self.assertEqual(looplib.read_state(self.loop_dir)["state"], "sensing")
        rows = self.ledger_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["type"], "transition")
        self.assertEqual(
            (rows[0]["from"], rows[0]["event"], rows[0]["to"]),
            ("idle", "start", "sensing"),
        )
        self.assertEqual(rows[0]["reason"], "scheduled tick")

    def test_illegal_event_leaves_state_and_ledger_untouched(self):
        """Adversarial where: advance() writes the ledger row (or the state)
        before validating the event, leaving a record of a transition that
        never happened."""
        looplib.write_state(self.loop_dir, {"state": "halted"})
        before = (self.loop_dir / "state.json").read_bytes()
        with self.assertRaises(looplib.TransitionError):
            looplib.advance(self.loop_dir, "start", "should be refused")
        self.assertEqual((self.loop_dir / "state.json").read_bytes(), before)
        self.assertFalse((self.loop_dir / "ledger.jsonl").exists())


class TestLoadDefinition(LoopDirTestCase):
    def test_valid_definitions_load_unchanged(self):
        """Adversarial where: validation rejects or rewrites a good file; the
        optional wip_command and the command controller with its companion
        key must load."""
        command_controller = dict(
            BASE_DEFINITION,
            controller="command",
            controller_command="python pick.py",
            wip_command="python wip.py",
        )
        for name, mapping in [
            ("first controller", BASE_DEFINITION),
            ("command controller", command_controller),
            ("up direction", dict(BASE_DEFINITION, direction="up")),
        ]:
            with self.subTest(name=name):
                self.write_definition(mapping)
                self.assertEqual(looplib.load_definition(self.loop_dir), mapping)

    def test_malformed_definition_names_the_field(self):
        """Adversarial where: one bad field among otherwise valid ones (an
        unknown key, a missing or blank sensor command, a negative cap, an
        unknown controller, a wrong type) passes silently or fails with a
        message that does not say which field to fix."""

        def without(key):
            return {k: v for k, v in BASE_DEFINITION.items() if k != key}

        rows = [
            ("unknown key typo", "sensor_comand",
             dict(BASE_DEFINITION, sensor_comand="x")),
            ("unknown extra key", "retries", dict(BASE_DEFINITION, retries=3)),
            ("missing sensor command", "sensor_command",
             without("sensor_command")),
            ("empty sensor command", "sensor_command",
             dict(BASE_DEFINITION, sensor_command="")),
            ("blank sensor command", "sensor_command",
             dict(BASE_DEFINITION, sensor_command="   ")),
            ("unknown controller", "controller",
             dict(BASE_DEFINITION, controller="median")),
            ("command controller without command", "controller_command",
             dict(BASE_DEFINITION, controller="command")),
            ("bad direction", "direction",
             dict(BASE_DEFINITION, direction="sideways")),
            ("max_turns as text", "max_turns",
             dict(BASE_DEFINITION, max_turns="ten")),
            ("allowed_tools as text", "allowed_tools",
             dict(BASE_DEFINITION, allowed_tools="Read")),
        ]
        negative_caps = [
            ("sensor_timeout_s", -1),
            ("max_turns", -1),
            ("max_budget_usd", -0.01),
            ("timeout_s", -1),
            ("daily_budget_usd", -0.01),
            ("total_budget_usd", -5),
            ("wip_limit", -1),
            ("max_actuator_failures", -1),
            ("max_harmful_runs", -1),
            ("max_runs_without_help", -1),
        ]
        for field, value in negative_caps:
            rows.append(
                (f"negative {field}", field, dict(BASE_DEFINITION, **{field: value}))
            )
        for name, field, mapping in rows:
            with self.subTest(name=name):
                self.write_definition(mapping)
                with self.assertRaises(looplib.DefinitionError) as ctx:
                    looplib.load_definition(self.loop_dir)
                self.assertIn(field, str(ctx.exception))


class TestStateFile(LoopDirTestCase):
    def test_state_round_trip_and_lf_endings(self):
        """Adversarial where: write_state emits CRLF on Windows (text-mode
        open) or a one-line file; read_state must give back what was
        written."""
        state = {"state": "actuating", "run_id": "r-17", "note": "line1\nline2"}
        looplib.write_state(self.loop_dir, state)
        data = (self.loop_dir / "state.json").read_bytes()
        self.assertTrue(data)
        self.assertNotIn(b"\r", data)
        self.assertIn(b"\n", data)
        self.assertEqual(looplib.read_state(self.loop_dir), state)

    def test_overwrite_replaces_previous_state_fully(self):
        """Adversarial where: a shorter second write leaves the tail of a
        longer first write behind, producing unparseable JSON."""
        looplib.write_state(
            self.loop_dir,
            {"state": "actuating", "run_id": "r-1", "padding": "x" * 400},
        )
        looplib.write_state(self.loop_dir, {"state": "idle"})
        self.assertEqual(looplib.read_state(self.loop_dir), {"state": "idle"})

    def test_missing_corrupt_and_unknown_state(self):
        """Adversarial where: a missing file crashes the first run, a corrupt
        file reads as a made-up state, or an unknown state name is accepted
        and later fails inside transition()."""
        self.assertEqual(looplib.read_state(self.loop_dir), {"state": "idle"})
        state_file = self.loop_dir / "state.json"
        for name, text in [
            ("truncated json", '{"state": "idl'),
            ("unknown state", '{"state": "napping"}'),
            ("not an object", '["idle"]'),
        ]:
            with self.subTest(name=name):
                state_file.write_text(text, encoding="utf-8", newline="\n")
                with self.assertRaises(looplib.StateError):
                    looplib.read_state(self.loop_dir)


class TestLedger(LoopDirTestCase):
    def test_append_is_append_only_lf_and_round_trips(self):
        """Adversarial where: append_ledger rewrites the file (losing earlier
        rows), writes CRLF on Windows, or splits a row across lines."""
        first = run_row("r1", "helpful", "a.py::x", 0.11)
        second = run_row("r2", "failed", "b.py::y", 0.29)
        looplib.append_ledger(self.loop_dir, first)
        after_first = (self.loop_dir / "ledger.jsonl").read_bytes()
        looplib.append_ledger(self.loop_dir, second)
        data = (self.loop_dir / "ledger.jsonl").read_bytes()
        self.assertTrue(data.startswith(after_first))
        self.assertNotIn(b"\r", data)
        self.assertEqual(data.count(b"\n"), 2)
        rows, skipped = looplib.read_ledger(self.loop_dir)
        self.assertEqual([without_ts(r) for r in rows], [first, second])
        self.assertEqual(skipped, [])

    def test_every_row_carries_a_utc_offset_timestamp(self):
        """Adversarial where: a ledger row lacks `ts` (so spend cannot be
        bucketed per UTC day), carries a naive timestamp with no offset, or a
        caller-supplied `ts` is overwritten. Rows written by advance() and
        recover() are stamped the same way as rows appended directly."""
        supplied = "2026-01-02T03:04:05+00:00"
        looplib.append_ledger(self.loop_dir, run_row("r1", "helpful", "a", 0.1))
        looplib.append_ledger(
            self.loop_dir, dict(run_row("r2", "neutral", "b", 0.2), ts=supplied)
        )
        looplib.write_state(self.loop_dir, {"state": "idle"})
        looplib.advance(self.loop_dir, "start", "tick")
        rows = self.ledger_rows()
        self.assertEqual(len(rows), 3)
        for row in rows:
            with self.subTest(run=row.get("run_id"), type=row["type"]):
                stamp = datetime.fromisoformat(row["ts"])
                self.assertEqual(stamp.utcoffset(), timedelta(0))
        self.assertEqual(rows[1]["ts"], supplied)

    def test_unparseable_lines_are_skipped_and_reported(self):
        """Adversarial where: one torn or non-object line among good rows
        aborts the whole read (fatal), is dropped silently, or hides the good
        rows after it."""
        good_a = run_row("r1", "helpful", "a")
        good_b = run_row("r2", "neutral", "b")
        lines = [
            json.dumps(good_a),
            '{"type": "run", "outc',
            json.dumps(good_b),
            "[1, 2]",
            "",
            "not json at all",
        ]
        (self.loop_dir / "ledger.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
        )
        rows, skipped = looplib.read_ledger(self.loop_dir)
        self.assertEqual(rows, [good_a, good_b])
        self.assertEqual([s["line"] for s in skipped], [2, 4, 6])
        self.assertEqual(skipped[0]["text"], '{"type": "run", "outc')

    def test_missing_ledger_reads_empty(self):
        """Adversarial where: the first run of a new loop crashes reading a
        ledger that does not exist yet."""
        self.assertEqual(looplib.read_ledger(self.loop_dir), ([], []))


class TestFold(unittest.TestCase):
    def counters(self, rows):
        result = looplib.fold(rows)
        return {
            key: result[key]
            for key in (
                "wip",
                "held_items",
                "consecutive_failures",
                "consecutive_harmful",
                "runs_without_help",
            )
        }

    def test_hand_built_ledger_with_interleaved_reviews(self):
        """Adversarial where: review rows interleaved between run rows break
        a streak, a review of an unknown run is counted, or failed and
        throttled runs leak into the increment count and the no-help count."""
        rows = [
            run_row("r1", "helpful", "a.py::x"),
            run_row("r2", "neutral", "b.py::y"),
            review_row("r1", "accept"),
            run_row("r3", "harmful", "c.py::z"),
            run_row("r4", "failed", "d.py::w"),
            review_row("r3", "reject"),
            run_row("r5", "throttled"),
            run_row("r6", "harmful", "e.py::v"),
            review_row("r99", "accept"),
            run_row("r7", "neutral", "f.py::u"),
            review_row("r7", "reject"),
        ]
        self.assertEqual(
            self.counters(rows),
            {
                "wip": 2,
                "held_items": ["b.py::y", "e.py::v"],
                "consecutive_failures": 0,
                "consecutive_harmful": 0,
                "runs_without_help": 4,
            },
        )

    def test_streak_counters_by_equivalence_class(self):
        """Adversarial where: a streak counter counts non-consecutive
        occurrences, is not ended by the right row kinds, or is broken by a
        review row or a non-resume transition row between two run rows."""
        rows = [
            ("single harmful", [run_row("a", "harmful", "i")],
             {"consecutive_harmful": 1, "consecutive_failures": 0}),
            ("two harmful in a row",
             [run_row("a", "neutral", "i"), run_row("b", "harmful", "j"),
              run_row("c", "harmful", "k")],
             {"consecutive_harmful": 2, "consecutive_failures": 0}),
            ("harmful ended by neutral",
             [run_row("a", "harmful", "i"), run_row("b", "harmful", "j"),
              run_row("c", "neutral", "k")],
             {"consecutive_harmful": 0, "consecutive_failures": 0}),
            ("harmful ended by helpful then one more",
             [run_row("a", "harmful", "i"), run_row("b", "helpful", "j"),
              run_row("c", "harmful", "k")],
             {"consecutive_harmful": 1, "consecutive_failures": 0}),
            ("harmful streak across review row",
             [run_row("a", "harmful", "i"), review_row("a", "reject"),
              run_row("b", "harmful", "j")],
             {"consecutive_harmful": 2, "consecutive_failures": 0}),
            ("harmful streak across pause transition",
             [run_row("a", "harmful", "i"),
              transition_row("pause", "idle", "paused"),
              run_row("b", "harmful", "j")],
             {"consecutive_harmful": 2, "consecutive_failures": 0}),
            ("two failures after a helpful run",
             [run_row("a", "helpful", "i"), run_row("b", "failed", "j"),
              run_row("c", "failed", "k")],
             {"consecutive_harmful": 0, "consecutive_failures": 2}),
            ("failures ended by a verified run",
             [run_row("a", "failed", "i"), run_row("b", "failed", "j"),
              run_row("c", "neutral", "k")],
             {"consecutive_harmful": 0, "consecutive_failures": 0}),
            ("failure after a verified run restarts the streak",
             [run_row("a", "failed", "i"), run_row("b", "failed", "j"),
              run_row("c", "helpful", "k"), run_row("d", "failed", "l")],
             {"consecutive_harmful": 0, "consecutive_failures": 1}),
            ("a throttled run is not a failure",
             [run_row("a", "throttled")],
             {"consecutive_harmful": 0, "consecutive_failures": 0}),
        ]
        for name, ledger, expected in rows:
            with self.subTest(name=name):
                got = self.counters(ledger)
                for key, value in expected.items():
                    self.assertEqual(got[key], value, key)

    def test_throttled_and_failed_runs_never_count_toward_no_help(self):
        """Adversarial where: a throttled or failed run is counted as a
        verified run without help, so a loop that was merely throttled halts
        for making no progress."""
        rows = [
            ("only throttled runs after a helpful one",
             [run_row("a", "helpful", "i"), run_row("b", "throttled"),
              run_row("c", "throttled"), run_row("d", "throttled")], 0),
            ("only failed runs after a helpful one",
             [run_row("a", "helpful", "i"), run_row("b", "failed", "j"),
              run_row("c", "failed", "k")], 0),
            ("mixed: only the verified runs count",
             [run_row("a", "helpful", "i"), run_row("b", "neutral", "j"),
              run_row("c", "failed", "k"), run_row("d", "throttled"),
              run_row("e", "harmful", "l"), run_row("f", "neutral", "m")], 3),
            ("no helpful run ever: every verified run counts",
             [run_row("a", "neutral", "i"), run_row("b", "harmful", "j")], 2),
            ("a helpful run resets the count",
             [run_row("a", "neutral", "i"), run_row("b", "helpful", "j")], 0),
            ("empty ledger", [], 0),
        ]
        for name, ledger, expected in rows:
            with self.subTest(name=name):
                self.assertEqual(self.counters(ledger)["runs_without_help"], expected)

    def test_resume_row_zeroes_the_consecutive_counters(self):
        """Adversarial where: a resume row does not reset a counter, a
        different transition row resets one, or rows before the resume leak
        into the count after it."""
        before = [
            run_row("a", "neutral", "i"),
            run_row("b", "harmful", "j"),
            run_row("c", "harmful", "k"),
            run_row("d", "failed", "l"),
            run_row("e", "failed", "m"),
            run_row("f", "failed", "n"),
        ]
        zero = {
            "consecutive_failures": 0,
            "consecutive_harmful": 0,
            "runs_without_help": 0,
        }
        rows = [
            ("counters are non-zero before the resume", before,
             {"consecutive_failures": 3, "runs_without_help": 3}),
            ("all zero immediately after the resume",
             before + [transition_row("resume")], zero),
            ("runs after the resume count from zero",
             before + [transition_row("resume"), run_row("g", "harmful", "o")],
             {"consecutive_failures": 0, "consecutive_harmful": 1,
              "runs_without_help": 1}),
            ("failure streak restarts at the resume",
             [run_row("a", "failed", "i"), transition_row("resume"),
              run_row("b", "failed", "j")],
             {"consecutive_failures": 1, "consecutive_harmful": 0,
              "runs_without_help": 0}),
            ("the latest resume wins",
             [run_row("a", "harmful", "i"), transition_row("resume"),
              run_row("b", "harmful", "j"), transition_row("resume")], zero),
            ("a reopen transition resets nothing",
             [run_row("a", "harmful", "i"), transition_row("reopen", "done", "idle"),
              run_row("b", "harmful", "j")],
             {"consecutive_failures": 0, "consecutive_harmful": 2,
              "runs_without_help": 2}),
        ]
        for name, ledger, expected in rows:
            with self.subTest(name=name):
                got = self.counters(ledger)
                for key, value in expected.items():
                    self.assertEqual(got[key], value, key)

    def test_reviews_release_held_items_and_wip(self):
        """Adversarial where: an accepted or rejected run still holds its item
        (so the controller never reselects it), a run that never reached
        verifying is counted as an increment, or an empty ledger reports a
        phantom WIP."""
        rows = [
            ("empty ledger", [], 0, []),
            ("one unreviewed increment", [run_row("a", "neutral", "z.py::q")],
             1, ["z.py::q"]),
            ("accepted releases the item",
             [run_row("a", "helpful", "z.py::q"), review_row("a", "accept")],
             0, []),
            ("rejected releases the item",
             [run_row("a", "harmful", "z.py::q"), review_row("a", "reject")],
             0, []),
            ("failed run leaves no increment", [run_row("a", "failed", "z.py::q")],
             0, []),
            ("throttled run leaves no increment", [run_row("a", "throttled")],
             0, []),
            ("held items are sorted",
             [run_row("a", "neutral", "m"), run_row("b", "neutral", "c"),
              run_row("c", "neutral", "x")],
             3, ["c", "m", "x"]),
            ("review of one of two releases only that one",
             [run_row("a", "neutral", "m"), run_row("b", "neutral", "c"),
              review_row("a")],
             1, ["c"]),
        ]
        for name, ledger, wip, held in rows:
            with self.subTest(name=name):
                got = self.counters(ledger)
                self.assertEqual(got["wip"], wip)
                self.assertEqual(got["held_items"], held)


class TestLock(LoopDirTestCase):
    def test_lock_file_records_pid_and_start_time(self):
        """Adversarial where: the lock file lacks the pid or start time that
        staleness and diagnosis depend on, or acquire fails when the lock's
        parent folder does not exist yet."""
        looplib.acquire_lock(self.lock_path, timeout_s=137, now=1000.0)
        data = json.loads(self.lock_path.read_text(encoding="utf-8"))
        self.assertEqual(data["pid"], os.getpid())
        self.assertEqual(data["started"], 1000.0)

    def test_second_acquire_fails_until_release(self):
        """Adversarial where: a second acquire succeeds while the lock is
        held (check-then-create race), or release leaves the lock behind."""
        looplib.acquire_lock(self.lock_path, timeout_s=137, now=1000.0)
        with self.assertRaises(looplib.LockHeld):
            looplib.acquire_lock(self.lock_path, timeout_s=137, now=1001.0)
        looplib.release_lock(self.lock_path)
        looplib.acquire_lock(self.lock_path, timeout_s=137, now=1002.0)

    def test_concurrent_acquire_has_exactly_one_winner(self):
        """Adversarial where: two runs that start together both believe they
        hold the lock because existence is checked before creation."""
        outcomes = []
        barrier = threading.Barrier(8)

        def attempt():
            barrier.wait()
            try:
                looplib.acquire_lock(self.lock_path, timeout_s=137, now=1000.0)
                outcomes.append("won")
            except looplib.LockHeld:
                outcomes.append("held")

        threads = [threading.Thread(target=attempt) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(outcomes), ["held"] * 7 + ["won"])

    def test_staleness_boundary_is_timeout_plus_600_seconds(self):
        """Adversarial where: the stale threshold is the timeout alone, a
        fixed constant, or off by a unit, so a long-running live run loses its
        lock or a crashed run's lock is never recovered. Exactly
        timeout+600 is not pinned; one second either side is."""
        looplib.acquire_lock(self.lock_path, timeout_s=137, now=1000.0)
        rows = [
            ("fresh", 1000.0, False),
            ("just past the timeout alone", 1000.0 + 137 + 1, False),
            ("one second inside the window", 1000.0 + 137 + 600 - 1, False),
            ("one second past the window", 1000.0 + 137 + 600 + 1, True),
            ("far past", 1000.0 + 100000, True),
        ]
        for name, now, stale in rows:
            with self.subTest(name=name):
                self.assertEqual(
                    looplib.is_stale(self.lock_path, timeout_s=137, now=now), stale
                )

    def test_staleness_uses_the_timeout_passed_in(self):
        """Adversarial where: the window ignores timeout_s (hard-coded
        constant), so a loop with a long timeout is judged by the wrong
        window."""
        looplib.acquire_lock(self.lock_path, timeout_s=29, now=1000.0)
        self.assertTrue(looplib.is_stale(self.lock_path, timeout_s=29, now=1000.0 + 631))
        self.assertFalse(looplib.is_stale(self.lock_path, timeout_s=3000, now=1000.0 + 631))


class TestRecover(LoopDirTestCase):
    def setUp(self):
        super().setUp()
        self.write_definition(BASE_DEFINITION)
        self.definition = looplib.load_definition(self.loop_dir)

    def test_stale_lock_with_working_state_recovers_to_idle(self):
        """Adversarial where: a crash in any working state leaves the loop
        stuck (no recovery), recovers without recording the crash, or charges
        a cost other than the full run budget. Each of the five working
        states is checked."""
        for state in WORKING:
            with self.subTest(state=state):
                loop_dir = self.root / f"loop-{state}"
                loop_dir.mkdir()
                lock = self.root / f"{state}.lock"
                looplib.write_state(loop_dir, {"state": state, "run_id": f"run-{state}"})
                looplib.acquire_lock(lock, timeout_s=523, now=1000.0)
                recovered = looplib.recover(
                    loop_dir, lock, self.definition, now=1000.0 + 523 + 600 + 1
                )
                self.assertTrue(recovered)
                self.assertEqual(looplib.read_state(loop_dir)["state"], "idle")
                rows, _skipped = looplib.read_ledger(loop_dir)
                crashed = [r for r in rows if r.get("outcome") == "crashed"]
                self.assertEqual(len(crashed), 1)
                self.assertEqual(crashed[0]["type"], "run")
                self.assertEqual(crashed[0]["run_id"], f"run-{state}")
                self.assertEqual(crashed[0]["cost_usd"], 0.37)
                moves = [
                    r for r in rows
                    if r.get("type") == "transition" and r.get("event") == "crash-recovered"
                ]
                self.assertEqual(len(moves), 1)
                self.assertEqual((moves[0]["from"], moves[0]["to"]), (state, "idle"))

    def test_recovery_clears_the_stale_lock(self):
        """Adversarial where: recovery leaves the stale lock file in place, so
        the very next run is refused by the lock it just recovered from."""
        looplib.write_state(self.loop_dir, {"state": "actuating", "run_id": "r1"})
        looplib.acquire_lock(self.lock_path, timeout_s=523, now=1000.0)
        looplib.recover(self.loop_dir, self.lock_path, self.definition,
                        now=1000.0 + 523 + 600 + 1)
        looplib.acquire_lock(self.lock_path, timeout_s=523, now=5000.0)
        held = json.loads(self.lock_path.read_text(encoding="utf-8"))
        self.assertEqual(held["started"], 5000.0)

    def test_working_state_with_no_lock_recovers(self):
        """Adversarial where: a crash that took the lock with it (file gone)
        is mistaken for a live run and the loop stays stuck in a working
        state forever."""
        looplib.write_state(self.loop_dir, {"state": "verifying", "run_id": "r2"})
        self.assertFalse(self.lock_path.exists())
        self.assertTrue(
            looplib.recover(self.loop_dir, self.lock_path, self.definition, now=2000.0)
        )
        self.assertEqual(looplib.read_state(self.loop_dir)["state"], "idle")

    def test_live_lock_refuses_and_changes_nothing(self):
        """Adversarial where: recovery steals the state from a run that is
        still going (one second inside the stale window), or half-applies
        before refusing."""
        looplib.write_state(self.loop_dir, {"state": "actuating", "run_id": "r3"})
        looplib.acquire_lock(self.lock_path, timeout_s=523, now=1000.0)
        before = (self.loop_dir / "state.json").read_bytes()
        with self.assertRaises(looplib.LockHeld):
            looplib.recover(self.loop_dir, self.lock_path, self.definition,
                            now=1000.0 + 523 + 600 - 1)
        self.assertEqual((self.loop_dir / "state.json").read_bytes(), before)
        self.assertFalse((self.loop_dir / "ledger.jsonl").exists())
        self.assertTrue(self.lock_path.exists())

    def test_resting_state_is_left_alone(self):
        """Adversarial where: recovery fires on a resting state (for example
        a paused loop) and records a crash that never happened. Each of the
        five resting states is checked, with a stale lock lying around."""
        for state in RESTING:
            with self.subTest(state=state):
                loop_dir = self.root / f"rest-{state}"
                loop_dir.mkdir()
                lock = self.root / f"rest-{state}.lock"
                looplib.write_state(loop_dir, {"state": state})
                looplib.acquire_lock(lock, timeout_s=523, now=1000.0)
                before = (loop_dir / "state.json").read_bytes()
                self.assertFalse(
                    looplib.recover(loop_dir, lock, self.definition,
                                    now=1000.0 + 523 + 600 + 1)
                )
                self.assertEqual((loop_dir / "state.json").read_bytes(), before)
                self.assertFalse((loop_dir / "ledger.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
