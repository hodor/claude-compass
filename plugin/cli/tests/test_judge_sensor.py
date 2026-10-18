"""Tests for the judge sensor: an agent reads plain-language rules, reports
violations, and a vote across several fresh runs keeps the stable findings.
The reading is advisory: it rides on the run row and the next prompt and never
reaches the state machine, a transition or an exit code.

Names these tests pin, beyond the contracts already fixed in `test_looplib.py`,
`test_sensorlib.py` and `test_looprunner.py`:

    looplib.load_definition(loop_dir)   accepts an optional `judge` object
        {"rules_file", "model", "runs", "max_turns", "max_budget_usd",
         "timeout_s", "anchor_rule"}. `rules_file` is relative to the loop
        folder and defaults to `judge-rules.md`; `anchor_rule` is optional;
        every other key is required. The returned dict carries the object
        exactly as the file wrote it (no defaults injected). A DefinitionError
        message names both `judge` and the offending field for: a `judge`
        that is not an object, an unknown key, `runs` that is even, below 1 or
        not an integer, a zero cap (`max_turns`, `max_budget_usd`,
        `timeout_s`), a missing `runs` or cap, a non-string `rules_file` or
        `anchor_rule`, and a rules file that is missing or holds no rule. The
        rules file is read by `load_definition`; a rule is one bullet
        `- R<n>: text`, where n is one or more digits.

    sensorlib.parse_judge_lines(text, rule_ids) -> JudgeParse
        `text` is a judge's final answer, `rule_ids` the rule ids of the rules
        file. `.findings`: list of (rule, file, line) tuples in input order;
        `.discarded`: int count of discarded lines. A non-blank line is
        discarded and counted when it is not a JSON object, names a rule not
        in `rule_ids` (whole-string comparison), or carries a line that is not
        a JSON integer. A line missing `file` is also never kept. Never
        raises.

    sensorlib.vote_findings(runs, configured) -> list[dict]
        `runs`: one list of (rule, file, line) tuples per VALID judge run;
        `configured`: the configured number of runs, valid or not. Findings of
        one rule and one file cluster single-link when neighbouring lines sit
        within 2 of each other. A cluster is kept when MORE THAN HALF of
        `configured` distinct runs reported into it. A kept cluster is
        {"rule", "file", "line", "votes"}: `line` is the lowest line of the
        cluster, `votes` the number of distinct runs.

    The run row of a run whose judge ran carries
        row["judge"] = {"kept": [<kept cluster dicts>], "valid_runs": int,
                        "invalid_runs": int, "discarded": int,
                        "cost_usd": float, "anchor_delta": int}
    `anchor_delta` appears only when the definition names an `anchor_rule`. A
    run the judge never saw (failed actuator, controls changed, gate stop, dry
    run) has no `judge` record.

Fixtures: `fixtures/judge_events/run1.json` to `run5.json` are real judge
result events (`claude -p --output-format json`) whose answer is 40 JSON lines
over rules R1 to R5; every run reports the same 40 findings.
`fixtures/judge_events/no_judge_prompt.txt` is the assembled actuator prompt of
a loop with no `judge` key, built from the harness constants of
`test_looprunner.py`.

Adversarial themes: a reading that moves the state machine, budget arithmetic
that forgets the judge, a vote counted over findings instead of runs, a
denominator that shrinks with invalid runs, a judge handed tools that write,
a cap read from the actuator instead of the judge, a prompt that leaks counts,
a rules file the actuator may rewrite, and a hung judge that outlives its run.
"""

import contextlib
import importlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from collections import Counter
from pathlib import Path

CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CLI_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import looplib  # noqa: E402
import sensorlib  # noqa: E402
import test_looplib as looplib_tests  # noqa: E402
import test_looprunner as base  # noqa: E402

JUDGE_FIXTURES = Path(CLI_DIR) / "tests" / "fixtures" / "judge_events"
RUN_FIXTURES = [JUDGE_FIXTURES / f"run{n}.json" for n in range(1, 6)]
NO_JUDGE_PROMPT = JUDGE_FIXTURES / "no_judge_prompt.txt"

ITEMS = base.ITEMS
NOW = base.NOW
reading = base.reading
run_row = base.run_row
word_present = base.word_present
files_under = base.files_under

RULES_TEXT = (
    "# Review rules\n"
    "\n"
    "Read each file and report violations.\n"
    "\n"
    "- R2: functions must not swallow exceptions\n"
    "- R7: public names need a docstring, também em português\n"
    "- R12: no mutable default arguments\n"
)
RULE_IDS = ["R2", "R7", "R12"]
FIXTURE_RULES = "\n".join(f"- R{n}: fixture rule {chr(96 + n)}" for n in range(1, 6)) + "\n"

JUDGE = {
    "rules_file": "review-rules.md",
    "model": "claude-judge-model-z",
    "runs": 3,
    "max_turns": 53,
    "max_budget_usd": 0.5,
    "timeout_s": 77,
}
JUDGE_BUDGET = 0.5
ACTUATOR_BUDGET = 2.75
ACTUATOR_COST = 0.0463805
R3_COST = 0.0174133

GARBAGE = {"stdout_text": "not a result event", "exit": 0}
EMPTY = {"stdout_text": "", "exit": 1}
BUDGET_STOP = {"stdout_file": str(base.R3_BUDGET_STOP), "exit": 1}


def finding(rule, file, line):
    return json.dumps({"rule": rule, "file": file, "line": line})


def envelope(result_text, cost):
    event = json.loads(RUN_FIXTURES[0].read_text(encoding="utf-8"))
    event["result"] = result_text
    event["total_cost_usd"] = cost
    return json.dumps(event)


def reply(lines, cost=0.25, **extra):
    """Stub spec for a judge whose final answer is `lines` joined by newlines."""
    text = "\n".join(lines) if not isinstance(lines, str) else lines
    return {"stdout_text": envelope(text, cost), **extra}


def findings_reply(*triples, cost=0.25, **extra):
    return reply([finding(*t) for t in triples], cost, **extra)


def tools_after(argv, flag):
    """Tool names following `flag` up to the next option."""
    names = []
    for token in argv[argv.index(flag) + 1:]:
        if token.startswith("-"):
            break
        names += [t for t in token.replace(",", " ").split() if t]
    return names


class JudgeHarness(base.RunnerHarness):
    """The runner harness with helpers for a loop that carries a `judge`
    object: call 1 of a run is the actuator, every later call is a judge."""

    def judged_loop(self, judge=None, judge_replies=(), actuator=None, definition=None,
                    rules=RULES_TEXT, **kwargs):
        merged = {**JUDGE, **(judge or {})}
        self.judge = merged
        self.new_loop(
            definition={**(definition or {}), "judge": merged},
            stub_calls=[actuator or {}] + list(judge_replies),
            **kwargs,
        )
        rules_path = self.loop_dir / merged.get("rules_file", "judge-rules.md")
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        rules_path.write_bytes(rules.encode("utf-8"))

    def judge_calls(self):
        return self.calls()[1:]

    def judge_row(self):
        (row,) = self.new_run_rows()
        return row, row.get("judge")

    @staticmethod
    def kept_votes(record):
        return {(k["rule"], k["file"], k["line"]): k["votes"] for k in record["kept"]}


class ParseJudgeLinesTests(unittest.TestCase):
    def test_real_judge_events_parse_to_forty_findings_and_no_discards(self):
        """Adversarial where: the parser mishandles the real answer shape
        (trailing newline, ordering, every rule R1 to R5) and loses or
        invents findings or counts a clean line as discarded."""
        rules = [f"R{n}" for n in range(1, 6)]
        for path in RUN_FIXTURES:
            with self.subTest(path=path.name):
                event = sensorlib.parse_result(path.read_text(encoding="utf-8"))
                parsed = sensorlib.parse_judge_lines(event.result, rules)
                self.assertEqual(len(parsed.findings), 40)
                self.assertEqual(parsed.discarded, 0)
                self.assertEqual(
                    Counter(f[0] for f in parsed.findings),
                    Counter({"R1": 10, "R2": 10, "R3": 10, "R4": 5, "R5": 5}),
                )
                self.assertEqual(parsed.findings[0], ("R1", "api/handlers.py", 18))
                self.assertEqual(parsed.findings[-1], ("R5", "api.md", 56))

    def test_lines_failing_the_rule_list_or_the_shape_are_discarded_and_counted(self):
        """Adversarial where: a line naming an absent rule (including an id
        that is only a prefix of a real one), a non-integer line, prose, a
        code fence or a truncated object is kept as a finding, silently
        dropped without being counted, or one bad line takes the good lines
        around it down with it."""
        good_a = finding("R7", "a.py", 5)
        good_b = finding("R12", "dir/b.py", 9)
        rows = [
            ("rule absent from the list", [finding("R9", "a.py", 3)], 0, 1),
            ("rule that is a prefix of a listed id", [finding("R1", "a.py", 3)], 0, 1),
            ("rule that extends a listed id", [finding("R120", "a.py", 3)], 0, 1),
            ("line is a word", ['{"rule": "R7", "file": "a.py", "line": "x"}'], 0, 1),
            ("line is a fraction", ['{"rule": "R7", "file": "a.py", "line": 12.5}'], 0, 1),
            ("line is null", ['{"rule": "R7", "file": "a.py", "line": null}'], 0, 1),
            ("line is a boolean", ['{"rule": "R7", "file": "a.py", "line": true}'], 0, 1),
            ("line is missing", ['{"rule": "R7", "file": "a.py"}'], 0, 1),
            ("prose line", ["Here are the violations I found:"], 0, 1),
            ("code fence lines", ["```json", good_a, "```"], 1, 2),
            ("array line", ['[{"rule": "R7", "file": "a.py", "line": 5}]'], 0, 1),
            ("truncated object", ['{"rule": "R7", "file": "a.py", "li'], 0, 1),
            ("extra keys do not disqualify", [
                '{"rule": "R7", "file": "a.py", "line": 5, "why": "no docstring"}'], 1, 0),
            ("one good line among bad ones", [
                good_a, finding("R9", "a.py", 1), "prose", good_b,
                '{"rule": "R7", "file": "a.py", "line": "x"}'], 2, 3),
        ]
        for name, lines, kept, discarded in rows:
            with self.subTest(name=name):
                parsed = sensorlib.parse_judge_lines("\n".join(lines), RULE_IDS)
                self.assertEqual(len(parsed.findings), kept)
                self.assertEqual(parsed.discarded, discarded)
        with self.subTest(name="order and content of the kept lines"):
            parsed = sensorlib.parse_judge_lines(
                "\n".join([good_b, finding("R9", "x.py", 1), good_a]), RULE_IDS)
            self.assertEqual(
                list(parsed.findings), [("R12", "dir/b.py", 9), ("R7", "a.py", 5)])
        with self.subTest(name="a line without a file is never kept"):
            parsed = sensorlib.parse_judge_lines('{"rule": "R7", "line": 4}', RULE_IDS)
            self.assertEqual(len(parsed.findings) + parsed.discarded, 1)
            self.assertTrue(all(isinstance(f[1], str) for f in parsed.findings))


class VoteFindingsTests(unittest.TestCase):
    def vote(self, runs, configured):
        kept = sensorlib.vote_findings(runs, configured)
        return sorted((k["rule"], k["file"], k["line"], k["votes"]) for k in kept)

    def test_vote_rows(self):
        """Adversarial where: the vote counts findings instead of runs, the
        denominator shrinks with the runs that came back, the threshold is
        at-least-half instead of more-than-half, the 2-line neighbour rule is
        off by one or compares end to end instead of neighbour to neighbour,
        or clusters merge across rules or files."""
        a, b = "a.py", "b.py"
        rows = [
            ("2 of 3 stays", 3, [[("R1", a, 10)], [("R1", a, 10)], []], [("R1", a, 10, 2)]),
            ("1 of 3 drops", 3, [[("R1", a, 10)], [], []], []),
            ("1 of 1 stays", 1, [[("R1", a, 10)]], [("R1", a, 10, 1)]),
            ("2 of 5 is not more than half", 5,
             [[("R1", a, 10)], [("R1", a, 10)], [], [], []], []),
            ("3 of 5 stays", 5,
             [[("R1", a, 10)], [("R1", a, 10)], [("R1", a, 10)], [], []], [("R1", a, 10, 3)]),
            ("denominator is the configured count, not the runs that came back", 5,
             [[("R1", a, 10)], [("R1", a, 10)], []], []),
            ("1 of 2 valid runs of 3 drops", 3, [[("R1", a, 10)], []], []),
            ("2 of 2 valid runs of 3 stays", 3,
             [[("R1", a, 10)], [("R1", a, 10)]], [("R1", a, 10, 2)]),
            ("lines 10 and 12 cluster", 3,
             [[("R1", a, 10)], [("R1", a, 12)], []], [("R1", a, 10, 2)]),
            ("lines 10 and 13 do not", 3, [[("R1", a, 10)], [("R1", a, 13)], []], []),
            ("a chain of neighbours is one cluster", 3,
             [[("R1", a, 10)], [("R1", a, 12)], [("R1", a, 14)]], [("R1", a, 10, 3)]),
            ("one run repeating a cluster is one vote", 3,
             [[("R1", a, 10), ("R1", a, 11), ("R1", a, 12)], [], []], []),
            ("a repeat inside a cluster adds no vote", 3,
             [[("R1", a, 10), ("R1", a, 10)], [("R1", a, 11)], []], [("R1", a, 10, 2)]),
            ("another rule on the same line is another cluster", 3,
             [[("R1", a, 10)], [("R2", a, 10)], []], []),
            ("another file on the same line is another cluster", 3,
             [[("R1", a, 10)], [("R1", b, 10)], []], []),
            ("two far clusters of one file are both kept", 3,
             [[("R1", a, 10), ("R1", a, 40)], [("R1", a, 10), ("R1", a, 41)], []],
             [("R1", a, 10, 2), ("R1", a, 40, 2)]),
        ]
        for name, configured, runs, expected in rows:
            with self.subTest(name=name):
                self.assertEqual(self.vote(runs, configured), sorted(expected))

    def test_five_real_judge_runs_vote_to_the_forty_findings(self):
        """Adversarial where: voting over real parsed answers drops or
        duplicates findings that all five runs agree on, at either the full
        configured count or a three-run prefix."""
        rules = [f"R{n}" for n in range(1, 6)]
        runs = []
        for path in RUN_FIXTURES:
            event = sensorlib.parse_result(path.read_text(encoding="utf-8"))
            runs.append(list(sensorlib.parse_judge_lines(event.result, rules).findings))
        for configured, used in ((5, runs), (3, runs[:3])):
            with self.subTest(configured=configured):
                kept = sensorlib.vote_findings(used, configured)
                self.assertEqual(len(kept), 40)
                self.assertEqual({k["votes"] for k in kept}, {configured})
                self.assertEqual({(k["rule"], k["file"], k["line"]) for k in kept}, set(runs[0]))


class JudgeDefinitionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.loop_dir = Path(tmp.name)

    def write(self, judge, rules=RULES_TEXT, rules_name="review-rules.md"):
        mapping = dict(looplib_tests.BASE_DEFINITION)
        mapping["judge"] = judge
        (self.loop_dir / "loop.json").write_text(json.dumps(mapping), encoding="utf-8")
        if rules is not None:
            (self.loop_dir / rules_name).write_text(rules, encoding="utf-8")
        return mapping

    def test_valid_judge_objects_load_unchanged(self):
        """Adversarial where: validation rejects a good object (smallest odd
        runs, a larger odd runs, a subfolder rules path, an anchor rule, the
        default rules file name), or rewrites it by injecting defaults."""
        minimal = {k: v for k, v in JUDGE.items() if k != "rules_file"}
        rows = [
            ("full object", dict(JUDGE, anchor_rule="R7"), "review-rules.md"),
            ("default rules file name", minimal, "judge-rules.md"),
            ("one run", dict(JUDGE, runs=1), "review-rules.md"),
            ("five runs", dict(JUDGE, runs=5), "review-rules.md"),
            ("rules file in a subfolder", dict(JUDGE, rules_file="rubric/rules.md"),
             "rubric/rules.md"),
        ]
        for name, judge, rules_name in rows:
            with self.subTest(name=name):
                (self.loop_dir / Path(rules_name).parent).mkdir(parents=True, exist_ok=True)
                mapping = self.write(judge, rules_name=rules_name)
                self.assertEqual(looplib.load_definition(self.loop_dir), mapping)

    def test_malformed_judge_object_names_the_field(self):
        """Adversarial where: an unknown key, an even or zero runs, a zero
        cap, a missing cap, a wrong type, or a rules file with no rule passes
        silently or fails with a message that does not say which judge field
        to fix (the actuator has keys of the same names)."""
        no_judge_rule_bodies = [
            ("empty rules file", ""),
            ("blank rules file", "  \n\n"),
            ("prose only", "Check that every function has a docstring.\n"),
            ("bullets without an R id", "- first: a rule\n- A1: another\n"),
            ("rule id without a number", "- R: a rule\n"),
        ]
        rows = [
            ("judge is a string", "judge", "yes", RULES_TEXT),
            ("judge is a list", "judge", [], RULES_TEXT),
            ("unknown key", "temperature", dict(JUDGE, temperature=0), RULES_TEXT),
            ("even runs", "runs", dict(JUDGE, runs=2), RULES_TEXT),
            ("larger even runs", "runs", dict(JUDGE, runs=4), RULES_TEXT),
            ("zero runs", "runs", dict(JUDGE, runs=0), RULES_TEXT),
            ("negative runs", "runs", dict(JUDGE, runs=-1), RULES_TEXT),
            ("runs as text", "runs", dict(JUDGE, runs="3"), RULES_TEXT),
            ("zero max_turns", "max_turns", dict(JUDGE, max_turns=0), RULES_TEXT),
            ("zero max_budget_usd", "max_budget_usd", dict(JUDGE, max_budget_usd=0),
             RULES_TEXT),
            ("zero timeout_s", "timeout_s", dict(JUDGE, timeout_s=0), RULES_TEXT),
            ("rules_file as a number", "rules_file", dict(JUDGE, rules_file=7), RULES_TEXT),
            ("anchor_rule as a number", "anchor_rule", dict(JUDGE, anchor_rule=7),
             RULES_TEXT),
        ]
        for key in ("runs", "max_turns", "max_budget_usd", "timeout_s"):
            rows.append((f"missing {key}", key,
                         {k: v for k, v in JUDGE.items() if k != key}, RULES_TEXT))
        for name, body in no_judge_rule_bodies:
            rows.append((name, "rules_file", dict(JUDGE), body))
        rows.append(("rules file missing", "rules_file", dict(JUDGE), None))
        for name, field, judge, rules in rows:
            with self.subTest(name=name):
                self.write(judge, rules=rules)
                if rules is None:
                    (self.loop_dir / "review-rules.md").unlink(missing_ok=True)
                with self.assertRaises(looplib.DefinitionError) as ctx:
                    looplib.load_definition(self.loop_dir)
                self.assertIn(field, str(ctx.exception))
                self.assertIn("judge", str(ctx.exception))
                if field == "judge":
                    self.assertNotIn("unknown key", str(ctx.exception))


class JudgeLaunchTests(JudgeHarness):
    def test_judge_argv_environment_and_count(self):
        """Adversarial where: a judge is launched with a tool that writes
        (Edit, Write, Bash), without --strict-mcp-config, resumed from an
        earlier session, with the actuator's caps or model instead of its own,
        in a scrubbed environment, or launched fewer or more times than
        `runs`; or the judge's settings leak into the actuator's launch."""
        self.judged_loop(judge={"runs": 5}, judge_replies=[reply("")] * 5)
        self.assertEqual(self.iterate()[0], 0)
        calls = self.calls()
        self.assertEqual(len(calls), 6)
        actuator = calls[0]["argv"]
        self.assertEqual(actuator[actuator.index("--model") + 1], "claude-test-model-x")
        self.assertEqual(actuator[actuator.index("--max-turns") + 1], "37")
        self.assertEqual(float(actuator[actuator.index("--max-budget-usd") + 1]), 2.75)
        self.assertEqual(sorted(tools_after(actuator, "--allowedTools")),
                         ["Edit", "Glob", "Read"])
        for call in self.judge_calls():
            argv = call["argv"]
            self.assertIn("-p", argv)
            self.assertIn("--strict-mcp-config", argv)
            self.assertEqual(argv[argv.index("--output-format") + 1], "json")
            self.assertEqual(argv[argv.index("--model") + 1], "claude-judge-model-z")
            self.assertEqual(argv[argv.index("--max-turns") + 1], "53")
            self.assertEqual(float(argv[argv.index("--max-budget-usd") + 1]), 0.5)
            self.assertEqual(sorted(tools_after(argv, "--allowedTools")),
                             ["Glob", "Grep", "Read"])
            for token in argv:
                for banned in ("Edit", "Write", "Bash"):
                    self.assertNotIn(banned, token)
            for banned in ("--resume", "--continue", "-c", "-r"):
                self.assertNotIn(banned, argv)
            env = call["env"]
            self.assertEqual(env.get("COMPASS_WORKER_SESSION"), "1")
            self.assertEqual(Path(env["CLAUDE_PROJECT_DIR"]).resolve(), self.project)
            self.assertEqual(env.get("XTEST_INHERITED"), "kept-through-the-runner")
            self.assertEqual(Path(call["cwd"]).resolve(), self.project)
            self.assertTrue(call["lock_exists"])

    def test_judge_prompt_is_the_rules_and_a_checklist_and_states_no_count(self):
        """Adversarial where: the judge is handed the actuator's prompt, the
        rules are paraphrased or cut, non-ASCII text is mangled or gets CRLF,
        the answer shape is not asked for, or the prompt states how many rules
        there are, how many runs vote, or a cap, inviting the judge to stop
        early or to pad."""
        self.judged_loop(judge={"runs": 5}, judge_replies=[reply("")] * 5)
        self.assertEqual(self.iterate()[0], 0)
        for call in self.judge_calls():
            raw = self.stdin_of(call)
            self.assertNotIn(b"\r", raw)
            prompt = raw.decode("utf-8")
            self.assertIn(RULES_TEXT.strip(), prompt)
            for key in ('"rule"', '"file"', '"line"'):
                self.assertIn(key, prompt)
            for marker in ("ACTUATOR-MARKER", "GOLDEN-MARKER", "FEEDBACK-MARKER",
                           "## Selected work"):
                self.assertNotIn(marker, prompt)
            for number in ("5", "3", "53", "0.5", "77", "37", "2.75"):
                self.assertFalse(word_present(number, prompt), f"{number} leaked")
            for spelled in ("three", "five"):
                self.assertNotIn(spelled, prompt.lower())

    def test_default_rules_file_name_is_read_when_the_key_is_omitted(self):
        """Adversarial where: the default `judge-rules.md` is never read, so
        a loop that relies on the default sends the judge an empty rules
        section; every other test names its own file."""
        judge = {k: v for k, v in JUDGE.items() if k != "rules_file"}
        self.new_loop(definition={"judge": judge},
                      stub_calls=[{}, reply(""), reply(""), reply("")])
        (self.loop_dir / "judge-rules.md").write_bytes(RULES_TEXT.encode("utf-8"))
        self.assertEqual(self.iterate()[0], 0)
        self.assertEqual(len(self.judge_calls()), 3)
        for call in self.judge_calls():
            self.assertIn(RULES_TEXT.strip(), self.stdin_of(call).decode("utf-8"))

    def test_judge_runs_after_the_deterministic_re_sense(self):
        """Adversarial where: the judge runs before the re-sense, so whatever
        it touches is read into the run's `reading_after`; the stub's judge
        rewrites the sensor reading to 2 and the row must still say 8."""
        shifted = reading(2, ITEMS)
        self.judged_loop(
            actuator={"set_reading": reading(8, ITEMS[1:])},
            judge_replies=[reply("", set_reading=shifted)] * 3,
        )
        self.assertEqual(self.iterate()[0], 0)
        (row,) = self.run_rows()
        self.assertEqual(row["reading_after"], {"value": 8, "items_count": 2})
        self.assertEqual(row["outcome"], "helpful")

    def test_hung_judge_is_killed_at_its_own_timeout_with_its_children(self):
        """Adversarial where: the judge's wait is unbounded or uses the
        actuator's 91 second timeout instead of the judge's 3, or the kill
        reaches only the launcher so a descendant outlives the run; the hung
        judge counts as an invalid run and the iteration completes."""
        heartbeat = self.base / "tools" / "judge-heartbeat.bin"
        self.judged_loop(
            judge={"timeout_s": 3},
            judge_replies=[
                {"hang": True, "heartbeat": str(heartbeat)},
                reply([finding("R7", "a.py", 5)]),
                reply([finding("R7", "a.py", 5)]),
            ],
        )
        started = time.monotonic()
        code = self.iterate()[0]
        self.assertLess(time.monotonic() - started, 20)
        self.assertEqual(code, 0)
        size = heartbeat.stat().st_size
        self.assertGreater(size, 0, "the stub's child never started")
        time.sleep(1.2)
        self.assertEqual(heartbeat.stat().st_size, size, "the child outlived the run")
        row, record = self.judge_row()
        self.assertEqual((record["valid_runs"], record["invalid_runs"]), (2, 1))
        self.assertEqual(self.state(), "idle")
        self.assert_no_lock()

    def test_dry_run_launches_no_judge_and_writes_nothing(self):
        """Adversarial where: a dry run spends on the judge, or records a
        judge reading, preview being the one mode that must cost nothing."""
        self.judged_loop(status="draft", seeds=[run_row("failed", "RUN-1", 0.01)],
                         judge_replies=[reply("")] * 3)
        before = files_under(self.root)
        code, out, _err = self.iterate(dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("ACTUATOR-MARKER-ONE", out)
        self.assert_nothing_launched()
        self.assertEqual(files_under(self.root), before)


class PromptStabilityTests(JudgeHarness):
    def test_loop_without_a_judge_key_sends_the_unchanged_prompt(self):
        """Adversarial where: judge support alters the actuator prompt of a
        loop that never asked for it (a stray heading, a changed separator, a
        rules file left in the folder being read); compared byte for byte
        against the prompt a loop with no judge sent before judge support."""
        self.new_loop()
        (self.loop_dir / "judge-rules.md").write_bytes(RULES_TEXT.encode("utf-8"))
        self.assertEqual(self.iterate()[0], 0)
        (call,) = self.calls()
        self.assertEqual(self.stdin_of(call), NO_JUDGE_PROMPT.read_bytes())
        (row,) = self.run_rows()
        self.assertFalse(row.get("judge"))

    def test_next_prompt_carries_only_the_last_judged_runs_kept_findings(self):
        """Adversarial where: the findings are missing from the next prompt,
        sit before the controller's pick or past the Feedback section, a
        finding only one of three runs reported is carried, the judge's own
        caps leak into the actuator prompt, or findings from an older judged
        run are still carried after a later judged run kept none."""
        kept = ("R7", "judged/alpha_kept.py", 4417)
        dropped = ("R7", "judged/beta_dropped.py", 4423)
        first = [findings_reply(kept, dropped), findings_reply(kept), findings_reply(kept)]
        silent = [reply("")] * 3
        calls = (
            [{"set_reading": reading(8, ITEMS[1:])}] + first
            + [{"set_reading": reading(6, ITEMS[2:])}] + silent
            + [{"set_reading": reading(4, [])}] + silent
        )
        self.judged_loop(judge_replies=[])
        self.set_stub(None, calls)
        prompts = []
        for _ in range(3):
            self.assertEqual(self.iterate()[0], 0)
            prompts.append(self.stdin_of(self.calls()[len(prompts) * 4]).decode("utf-8"))
        self.assertEqual(len(self.calls()), 12)

        def selected(prompt):
            start = prompt.index("## Selected work (controller output)")
            return prompt[start:prompt.index("## Feedback")]

        second = selected(prompts[1])
        self.assertIn(ITEMS[1], second)
        for text in ("judged/alpha_kept.py", "R7", "4417"):
            self.assertIn(text, second)
        self.assertLess(second.index(ITEMS[1]), second.index("judged/alpha_kept.py"))
        self.assertNotIn("beta_dropped", prompts[1])
        for number in ("53", "77"):
            self.assertFalse(word_present(number, prompts[1]), f"{number} leaked")
        self.assertNotIn("alpha_kept", prompts[2])


class JudgeRecordTests(JudgeHarness):
    def test_row_records_the_voted_findings_of_the_real_events(self):
        """Adversarial where: replaying the five real judge events through
        the runner loses a field of the run's `judge` record, miscounts valid
        runs, discards or kept findings, or computes the anchor delta from
        the item count instead of the sensor's value."""
        self.judged_loop(
            judge={"runs": 5, "anchor_rule": "R1"},
            rules=FIXTURE_RULES,
            actuator={"set_reading": reading(4, ITEMS[1:])},
            judge_replies=[{"stdout_file": str(p)} for p in RUN_FIXTURES],
        )
        self.assertEqual(self.iterate()[0], 0)
        row, record = self.judge_row()
        self.assertEqual(record["valid_runs"], 5)
        self.assertEqual(record["invalid_runs"], 0)
        self.assertEqual(record["discarded"], 0)
        self.assertEqual(len(record["kept"]), 40)
        self.assertEqual({k["votes"] for k in record["kept"]}, {5})
        self.assertEqual(self.kept_votes(record)[("R1", "api/handlers.py", 18)], 5)
        self.assertEqual(record["anchor_delta"], 10 - 4)
        fixture_costs = sum(
            json.loads(p.read_text(encoding="utf-8"))["total_cost_usd"] for p in RUN_FIXTURES)
        self.assertAlmostEqual(record["cost_usd"], fixture_costs, places=9)
        self.assertAlmostEqual(row["cost_usd"], ACTUATOR_COST + fixture_costs, places=9)
        self.assertEqual(row["outcome"], "helpful")

    def test_anchor_delta_rows(self):
        """Adversarial where: the delta is the item count minus the kept
        count, uses the wrong sign, ignores an anchor rule with no kept
        findings, or is written when no anchor rule is configured."""
        four = [("R7", f"p/f{i}.py", 10) for i in range(4)]
        rows = [
            ("anchor above the reading", "R7", 1, 4 - 1),
            ("anchor below the reading", "R7", 9, 4 - 9),
            ("anchor rule with no kept finding", "R12", 9, 0 - 9),
            ("no anchor rule", None, 9, None),
        ]
        for name, anchor, value, expected in rows:
            with self.subTest(name=name):
                judge = {"anchor_rule": anchor} if anchor else {}
                self.judged_loop(
                    judge=judge,
                    actuator={"set_reading": reading(value, ITEMS)},
                    judge_replies=[findings_reply(*four)] * 3,
                )
                self.assertEqual(self.iterate()[0], 0)
                _row, record = self.judge_row()
                self.assertEqual(len(record["kept"]), 4)
                if expected is None:
                    self.assertIsNone(record.get("anchor_delta"))
                else:
                    self.assertEqual(record["anchor_delta"], expected)

    def test_discards_are_summed_over_the_valid_runs(self):
        """Adversarial where: discarded lines are counted for one run only,
        reset per run, or dropped from the record, so a judge that talks
        around its answer looks clean."""
        ok = finding("R7", "a.py", 5)
        self.judged_loop(judge_replies=[
            reply(["Here is what I found:", ok, finding("R9", "a.py", 5)]),
            reply([ok, '{"rule": "R7", "file": "a.py", "line": "x"}']),
            reply([ok]),
        ])
        self.assertEqual(self.iterate()[0], 0)
        _row, record = self.judge_row()
        self.assertEqual(record["discarded"], 3)
        self.assertEqual(self.kept_votes(record), {("R7", "a.py", 5): 3})

    def test_voting_keeps_what_most_runs_report_and_clusters_neighbours(self):
        """Adversarial where: the runner keeps the union of the runs, votes
        over the findings of a single run, or clusters lines 3 apart; a
        finding two of three runs report stays, one run alone drops, lines 10
        and 12 across runs cluster, lines 30 and 33 do not."""
        run_a = findings_reply(("R7", "k.py", 20), ("R7", "d.py", 40),
                              ("R2", "cl.py", 10), ("R2", "z.py", 30))
        run_b = findings_reply(("R7", "k.py", 20), ("R2", "cl.py", 12), ("R2", "z.py", 33))
        self.judged_loop(judge_replies=[run_a, run_b, reply("")])
        self.assertEqual(self.iterate()[0], 0)
        _row, record = self.judge_row()
        self.assertEqual(self.kept_votes(record),
                         {("R7", "k.py", 20): 2, ("R2", "cl.py", 10): 2})
        self.assertEqual((record["valid_runs"], record["invalid_runs"]), (3, 0))

    def test_invalid_runs_are_recorded_and_the_iteration_completes(self):
        """Adversarial where: a judge with garbage output, no output or a
        budget-stop event (no answer text) is counted valid with no findings,
        aborts the iteration, or lets the remaining runs vote against a
        shrunken denominator; its cost, when an event arrived, is the event's
        real cost."""
        ok = [("R7", "a.py", 5)]
        rows = [
            ("garbage output", [findings_reply(*ok), findings_reply(*ok), GARBAGE],
             (2, 1), {("R7", "a.py", 5): 2}, 0.0, 1),
            ("empty output and a failing exit", [findings_reply(*ok), findings_reply(*ok), EMPTY],
             (2, 1), {("R7", "a.py", 5): 2}, 0.0, 1),
            ("budget stop event without an answer",
             [findings_reply(*ok), findings_reply(*ok), BUDGET_STOP],
             (2, 1), {("R7", "a.py", 5): 2}, R3_COST, 0),
            ("two invalid of three leave no majority",
             [findings_reply(*ok), GARBAGE, EMPTY], (1, 2), {}, 0.0, 2),
            ("all invalid", [GARBAGE, EMPTY, BUDGET_STOP], (0, 3), {}, R3_COST, 2),
        ]
        for name, replies, counts, kept, known_cost, unknown_runs in rows:
            with self.subTest(name=name):
                self.judged_loop(judge_replies=replies,
                                 actuator={"set_reading": reading(8, ITEMS[1:])})
                code, _out, _err = self.iterate()
                self.assertEqual(code, 0)
                self.assertEqual(self.events(), base.SUCCESS_EVENTS)
                self.assertEqual(self.state(), "idle")
                row, record = self.judge_row()
                self.assertEqual((record["valid_runs"], record["invalid_runs"]), counts)
                self.assertEqual(self.kept_votes(record), kept)
                valid_cost = 0.25 * counts[0]
                lower = valid_cost + known_cost
                upper = lower + unknown_runs * JUDGE_BUDGET
                self.assertGreaterEqual(record["cost_usd"], lower - 1e-9)
                self.assertLessEqual(record["cost_usd"], upper + 1e-9)
                self.assertAlmostEqual(row["cost_usd"], ACTUATOR_COST + record["cost_usd"],
                                       places=9)
                self.assert_no_lock()

    def test_run_that_never_reached_the_judge_has_no_judge_record(self):
        """Adversarial where: the judge is launched and charged after an
        actuator that failed or that rewrote the controls, spending on a run
        that was never verified; the failed run's cost stays the actuator's
        alone."""
        rows = [
            ("budget stop", {"stdout_file": str(base.R3_BUDGET_STOP), "exit": 1}, R3_COST),
            ("garbage output", {"stdout_text": "not a result event", "exit": 0},
             ACTUATOR_BUDGET),
        ]
        for name, actuator, cost in rows:
            with self.subTest(name=name):
                self.judged_loop(actuator=actuator, judge_replies=[reply("")] * 3)
                self.assertEqual(self.iterate()[0], 0)
                self.assertEqual(len(self.calls()), 1)
                (row,) = self.run_rows()
                self.assertEqual(row["outcome"], "failed")
                self.assertEqual(row["cost_usd"], cost)
                self.assertFalse(row.get("judge"))
                self.assertEqual(self.events()[-1], "failed")


class JudgeSpendTests(JudgeHarness):
    def test_row_cost_sums_the_actuator_and_every_judge_run(self):
        """Adversarial where: the row records the actuator's cost alone, the
        largest or last judge run instead of the sum, or a separate row, so
        `spend_lifetime` and `compass loop status` miss the judge's spend;
        costs are 1.25 + 0.25 + 0.5 + 0.25 = 2.25."""
        event = json.loads(base.R2_SUCCESS.read_text(encoding="utf-8"))
        event["total_cost_usd"] = 1.25
        actuator_event = self.base / "tools" / "actuator_event.json"
        actuator_event.write_text(json.dumps(event), encoding="utf-8")
        self.judged_loop(
            actuator={"stdout_file": str(actuator_event)},
            judge_replies=[reply("", cost=0.25), reply("", cost=0.5), reply("", cost=0.25)],
        )
        self.assertEqual(self.iterate(now=None)[0], 0)
        row, record = self.judge_row()
        self.assertAlmostEqual(record["cost_usd"], 1.0, places=9)
        self.assertAlmostEqual(row["cost_usd"], 2.25, places=9)
        rows = self.ledger()
        self.assertEqual({r["type"] for r in rows}, {"run", "transition"})
        self.assertAlmostEqual(sensorlib.spend_lifetime(rows), 2.25, places=9)
        module = importlib.import_module("commands.loop")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = module.run(["status", "LOOP-001"])
        self.assertEqual(0 if code is None else code, 0)
        text = out.getvalue().lower()
        lifetime = [l for l in text.splitlines() if "lifetime" in l or "total" in l]
        today = [l for l in text.splitlines() if "today" in l]
        self.assertTrue(any("2.25" in l for l in lifetime), lifetime)
        self.assertTrue(any("2.25" in l for l in today), today)

    def test_gate_budget_is_the_actuator_budget_plus_runs_times_the_judge_budget(self):
        """Adversarial where: the gate checks the actuator budget alone, adds
        the judge budget once instead of `runs` times, or is off by one at the
        exact fit; the actuator budget is 2.75 and the judge budget 0.5, so a
        run needs 2.75 + runs * 0.5, and every amount here is exact in binary."""
        old = "2026-09-01T08:00:00+00:00"
        today = "2026-10-18T09:30:00+00:00"
        rows = [
            ("daily: 3 runs, exact fit", 3, 10.0, 100.0, today, 5.75, "runs"),
            ("daily: 3 runs, over by a cent", 3, 10.0, 100.0, today, 5.76, "daily-budget-spent"),
            ("daily: room for the actuator alone", 3, 10.0, 100.0, today, 6.0,
             "daily-budget-spent"),
            ("daily: 1 run, exact fit", 1, 10.0, 100.0, today, 6.75, "runs"),
            ("daily: 1 run, over by a cent", 1, 10.0, 100.0, today, 6.76, "daily-budget-spent"),
            ("daily: 5 runs, exact fit", 5, 10.0, 100.0, today, 4.75, "runs"),
            ("daily: 5 runs, over by a cent", 5, 10.0, 100.0, today, 4.76, "daily-budget-spent"),
            ("lifetime: 3 runs, exact fit", 3, 100.0, 20.0, old, 15.75, "runs"),
            ("lifetime: 3 runs, over by a cent", 3, 100.0, 20.0, old, 15.76,
             "total-budget-spent"),
        ]
        for name, runs, daily, total, ts, spent, ending in rows:
            with self.subTest(name=name):
                self.judged_loop(
                    judge={"runs": runs},
                    definition={"daily_budget_usd": daily, "total_budget_usd": total},
                    seeds=[run_row("failed", "RUN-SPENT", spent, ts=ts)],
                    judge_replies=[reply("")] * runs,
                )
                self.iterate(now=NOW)
                if ending == "runs":
                    self.assertEqual(len(self.calls()), 1 + runs)
                    self.assertEqual(self.state(), "idle")
                    continue
                self.assert_nothing_launched()
                self.assertEqual(self.state(), "halted" if ending.startswith("total") else "throttled")
                self.assertEqual(self.events(), ["start", "off-set-point", ending])
                (row,) = self.new_run_rows()
                self.assertEqual(row["outcome"], "halted" if ending.startswith("total") else "throttled")
                self.assertEqual(row.get("cost_usd", 0), 0)
                self.assert_no_lock()

    def test_crashed_run_is_charged_the_actuator_and_the_whole_judge_budget(self):
        """Adversarial where: crash recovery charges the actuator budget only,
        so a run killed while the judge was working is undercounted by the
        judge's whole allowance; a loop with no judge keeps the actuator
        charge."""
        rows = [
            ("killed during actuation", "actuating", True, ACTUATOR_BUDGET + 3 * JUDGE_BUDGET),
            ("killed during the judge", "verifying", True, ACTUATOR_BUDGET + 3 * JUDGE_BUDGET),
            ("no judge configured", "actuating", False, ACTUATOR_BUDGET),
        ]
        for name, state, judged, charge in rows:
            with self.subTest(name=name):
                working = {"state": state, "run_id": "RUN-OLD", "item": ITEMS[0]}
                if judged:
                    self.judged_loop(state=working, judge_replies=[reply("")] * 3)
                else:
                    self.new_loop(state=working)
                self.assertEqual(self.iterate()[0], 0)
                crashed = self.run_rows()[0]
                self.assertEqual((crashed["run_id"], crashed["outcome"]), ("RUN-OLD", "crashed"))
                self.assertAlmostEqual(crashed["cost_usd"], charge, places=9)
                self.assertIn("crash-recovered", self.events())
                self.assert_no_lock()


class AdvisoryTests(JudgeHarness):
    OUTCOMES = [
        ("helpful", reading(8, ITEMS[1:]), [], "helpful", "idle"),
        ("neutral", reading(10), [], "neutral", "idle"),
        ("harmful", reading(12), [], "harmful", "idle"),
        ("harmful limit", reading(12), [run_row("harmful", "RUN-H1", item="old-h")],
         "harmful-limit", "halted"),
    ]
    FILES = ["alpha.py", "bravo.py", "charlie.py", "actuator.md"]

    def snapshot(self, code):
        transitions = [(r["from"], r["event"], r["to"])
                       for r in self.ledger() if r["type"] == "transition"]
        (row,) = self.new_run_rows()
        return {
            "code": code,
            "transitions": transitions,
            "state": self.state(),
            "outcome": row["outcome"],
            "item": row["item"],
            "before": row["reading_before"],
            "after": row["reading_after"],
        }

    def test_judge_behaviour_never_moves_transitions_outcome_or_exit_code(self):
        """Adversarial where: a judge reading reaches the state machine, so
        the same deterministic outcome ends in a different transition, outcome
        or exit code when the judge reports nothing or flags every file; all
        twelve combinations of four outcomes and three judge behaviours,
        checked against absolute expectations and against the no-judge run."""
        everything = [finding(rule, name, 3) for rule in RULE_IDS for name in self.FILES]
        behaviours = [
            ("no judge", None),
            ("zero findings", [reply("")] * 3),
            ("every file", [reply(everything)] * 3),
        ]
        for outcome, after, seeds, final_event, final_state in self.OUTCOMES:
            baseline = None
            for behaviour, replies in behaviours:
                with self.subTest(outcome=outcome, judge=behaviour):
                    stub_actuator = {"set_reading": after}
                    if replies is None:
                        self.new_loop(seeds=seeds, stub_calls=[stub_actuator])
                    else:
                        self.judged_loop(seeds=seeds, actuator=stub_actuator,
                                         judge_replies=replies)
                    code, _out, _err = self.iterate()
                    snap = self.snapshot(code)
                    expected_events = base.SUCCESS_EVENTS[:-1] + [final_event]
                    self.assertEqual([t[1] for t in snap["transitions"]], expected_events)
                    self.assertEqual(snap["state"], final_state)
                    self.assertEqual(snap["outcome"], final_event.split("-")[0])
                    if final_state == "idle":
                        self.assertEqual(code, 0)
                    if replies is None:
                        baseline = snap
                        self.assertEqual(len(self.calls()), 1)
                    else:
                        self.assertEqual(len(self.calls()), 4)
                        row, record = self.judge_row()
                        self.assertEqual(len(record["kept"]),
                                         0 if behaviour == "zero findings" else len(everything))
                    self.assertEqual(snap, baseline)

    def test_actuator_that_edits_a_rules_file_halts_with_controls_changed(self):
        """Adversarial where: the rules file is not among the fingerprinted
        controls, so an actuator that softens the rules it will be judged by
        goes unnoticed, or the judge is still launched and charged after the
        tamper; checked for a rewrite and an append, a rules file in a
        subfolder, and the default file name."""
        rows = [
            ("rewrite", {"rules_file": "rubric/review-rules.md"},
             "rubric/review-rules.md", "- R2: nothing is ever a violation\n", False),
            ("append", {"rules_file": "rubric/review-rules.md"},
             "rubric/review-rules.md", "- R99: one more\n", True),
            ("default name", {"rules_file": None}, "judge-rules.md", "- R2: softened\n", False),
        ]
        for name, judge, filename, text, append in rows:
            with self.subTest(name=name):
                judge = {k: v for k, v in {**JUDGE, **judge}.items() if v is not None}
                self.new_loop(
                    definition={"judge": judge},
                    stub_calls=[{"tamper": [{"path": str(self.loop_dir / filename),
                                             "text": text, "append": append}]},
                                reply(""), reply(""), reply("")],
                )
                target = self.loop_dir / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(RULES_TEXT.encode("utf-8"))
                self.iterate()
                self.assertEqual(self.state(), "halted")
                events = self.events()
                self.assertEqual(events[-1], "controls-changed")
                self.assertNotIn("finished", events)
                self.assertEqual(len(self.calls()), 1)
                (row,) = self.run_rows()
                self.assertEqual(row["cost_usd"], ACTUATOR_COST)
                self.assertFalse(row.get("judge"))
                self.assert_no_lock()


if __name__ == "__main__":
    unittest.main()
