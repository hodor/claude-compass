"""Tests for `compass loop`: new, status, activate, pause, resume and review,
and the dispatch of run, check and baseline.

Contract choices these tests pin:

* `new <name>` writes a *draft* loop the human completes: its `loop.json`
  carries safe defaults and no sensor command, so `looplib.load_definition`
  rejects it by naming `sensor_command` until the human adds one. `status`,
  `activate`, `pause`, `resume` and `review` need only the state file, the
  ledger and the index, so they work on that draft; every test here builds its
  loops through `new` and never gives them a sensor.
* `new <name>` refuses a name that already has a loop folder under any number;
  a fresh name takes max+1 over the existing `LOOP-NNN-*` folders. A refusal
  changes nothing in the vault.
* A loop is addressed as `LOOP-NNN`. An unknown id is exit 1, never a crash.
* `pause` and `resume` are legal exactly where `looplib.transition` allows
  them; an illegal request is exit 1 and leaves the loop folder byte-identical.
* `review` appends one ledger row and moves no state; `accept` and `reject`
  apply only to a run that reached `verifying` (outcome helpful, neutral or
  harmful). A reject reason becomes exactly one new line in `feedback.md`.
* The command never exits 2: exit 2 blocks the user's write when the command
  runs from a hook.

Adversarial themes: refusals that still half-write, identifiers that match by
prefix, a reason that smuggles a second line into the guidance file, and a
day boundary in the spend totals.
"""

import importlib
import io
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CLI_DIR)

import looplib  # noqa: E402
import maincli  # noqa: E402
import vaultlib  # noqa: E402
from commands import validate  # noqa: E402

COMPASS = os.path.join(CLI_DIR, "compass")

ROOT_INDEX = """# Index

## Specs

## Plans

## Research

## Decisions

## Lessons

## Handoffs
"""

SUBCOMMANDS = ["new", "status", "activate", "pause", "resume", "review",
               "run", "check", "baseline"]

ALL_STATES = sorted(looplib.STATES)


def snapshot(directory):
    """Map of relative path -> bytes for every file under `directory`, plus
    the set of directories, so a created or deleted entry shows in a compare."""
    directory = Path(directory)
    files = {}
    for path in sorted(directory.rglob("*")):
        rel = path.relative_to(directory).as_posix()
        files[rel] = path.read_bytes() if path.is_file() else None
    return files


def non_blank(text):
    return [line for line in text.splitlines() if line.strip()]


class LoopCommandCase(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.project = tmp
        self.root = tmp / ".compass"
        (self.root / "meta").mkdir(parents=True)
        (self.root / "index.md").write_text(ROOT_INDEX, encoding="utf-8")
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(tmp)

        def restore():
            if old is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = old

        self.addCleanup(restore)

    def loop(self, *args):
        """Run `compass loop <args>` in-process. Returns (code, stdout,
        stderr). A SystemExit from the command is its exit code; 2 is a
        failure of the never-exit-2 rule."""
        module = importlib.import_module("commands.loop")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = module.run(list(args))
            except SystemExit as exit_:
                code = exit_.code
        code = 0 if code is None else code
        self.assertNotEqual(code, 2, f"loop {args} exited 2: {err.getvalue()}")
        return code, out.getvalue(), err.getvalue()

    def cli(self, *args):
        """Run `python compass loop <args>` as a real process."""
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.project)
        env["COMPASS_CLAUDE_BIN"] = str(self.project / "no-such-claude")
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [sys.executable, COMPASS, "loop", *args],
            capture_output=True, text=True, encoding="utf-8", env=env,
            cwd=str(self.project), timeout=120,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def new_loop(self, name="remove-bad", **overrides):
        """Scaffold a loop with `new`. `overrides` replace keys of the
        template's loop.json; the draft keeps no sensor command."""
        code, _, err = self.loop("new", name)
        self.assertEqual(code, 0, err)
        folder = self.folder_for(name)
        if overrides:
            definition = json.loads((folder / "loop.json").read_text(encoding="utf-8"))
            definition.update(overrides)
            (folder / "loop.json").write_text(
                json.dumps(definition, indent=2) + "\n", encoding="utf-8", newline="\n"
            )
        return folder

    def folder_for(self, name):
        found = sorted((self.root / "loops").glob(f"LOOP-[0-9]*-{name}"))
        self.assertEqual(len(found), 1, f"loops for {name}: {found}")
        return found[0]

    def set_state(self, folder, state):
        looplib.write_state(folder, {"state": state})

    def state_of(self, folder):
        return looplib.read_state(folder)["state"]

    def ledger(self, folder):
        return looplib.read_ledger(folder)[0]

    def add_run(self, folder, run_id, outcome, cost=0.0, item="a.py:thing", **extra):
        row = {"type": "run", "run_id": run_id, "outcome": outcome,
               "item": item, "cost_usd": cost}
        row.update(extra)
        looplib.append_ledger(folder, row)


class NewScaffoldTests(LoopCommandCase):
    def test_new_scaffolds_every_part_of_the_loop(self):
        """Adversarial where: `new` omitting a part (golden pattern, state
        file, actuator), writing CRLF on Windows, leaving `state.json` out of
        the resting `idle` state, or producing a folder the vault validator
        rejects."""
        code, _, err = self.loop("new", "remove-bad")
        self.assertEqual(code, 0, err)
        folder = self.root / "loops" / "LOOP-001-remove-bad"
        for rel in ("index.md", "loop.json", "actuator.md", "feedback.md",
                    "golden/pattern-template.md", "state.json"):
            with self.subTest(rel):
                path = folder / rel
                self.assertTrue(path.is_file(), f"{rel} missing")
                data = path.read_bytes()
                self.assertTrue(data.strip(), f"{rel} is empty")
                self.assertNotIn(b"\r\n", data, f"{rel} has CRLF")
        self.assertEqual(self.state_of(folder), "idle")
        errors, _ = validate.check_vault(self.root)
        self.assertEqual(errors, [])

    def test_new_index_is_a_draft_loop_document_with_a_section_per_step(self):
        """Adversarial where: the index scaffolded as `status: active` (a draft
        would then run before the human completes it), missing a field the
        loop artifact type expects, or carrying fewer step sections than the
        loop's parts (end state, sensor, controller, actuator)."""
        self.loop("new", "remove-bad")
        index = self.root / "loops" / "LOOP-001-remove-bad" / "index.md"
        data, error = vaultlib.parse_frontmatter(index)
        self.assertIsNone(error)
        self.assertEqual(data.get("type"), "loop")
        self.assertNotEqual(data.get("status"), "active")
        for field in ("title", "area", "tags", "created", "updated", "summary"):
            with self.subTest(field):
                self.assertTrue(data.get(field), f"frontmatter lacks {field}")
        headings = [
            line.lstrip("#").strip().lower()
            for line in index.read_text(encoding="utf-8").splitlines()
            if line.startswith("## ")
        ]
        for step in ("end state", "sensor", "controller", "actuator"):
            with self.subTest(step):
                self.assertTrue(
                    any(step in h for h in headings), f"no section for {step}: {headings}"
                )

    def test_new_definition_is_a_draft_the_human_completes(self):
        """Adversarial where: a template `loop.json` that ships a sensor
        command (the loop would run an unreviewed command), that is invalid for
        a reason other than the missing sensor (adding a sensor still fails),
        or whose budgets are unsafe: a run budget above the daily budget
        throttles every run, a zero cap runs nothing."""
        self.loop("new", "remove-bad")
        folder = self.root / "loops" / "LOOP-001-remove-bad"
        path = folder / "loop.json"
        definition = json.loads(path.read_text(encoding="utf-8"))
        sensor = definition.get("sensor_command")
        self.assertFalse(isinstance(sensor, str) and sensor.strip())
        with self.assertRaises(looplib.DefinitionError) as ctx:
            looplib.load_definition(folder)
        self.assertIn("sensor_command", str(ctx.exception))

        definition["sensor_command"] = "python sense.py"
        path.write_text(json.dumps(definition), encoding="utf-8", newline="\n")
        loaded = looplib.load_definition(folder)
        for key in ("max_turns", "max_budget_usd", "timeout_s",
                    "daily_budget_usd", "total_budget_usd"):
            with self.subTest(key):
                self.assertGreater(loaded[key], 0)
        self.assertLessEqual(loaded["max_budget_usd"], loaded["daily_budget_usd"])
        self.assertLessEqual(loaded["daily_budget_usd"], loaded["total_budget_usd"])

    def test_new_feedback_is_a_title_one_paragraph_and_a_guidance_list(self):
        """Adversarial where: `feedback.md` scaffolded without the `## Guidance`
        heading (a reject reason then has no list to join), with the
        explanatory text split into several paragraphs or missing, or with the
        title absent."""
        self.loop("new", "remove-bad")
        text = (self.root / "loops" / "LOOP-001-remove-bad" / "feedback.md").read_text(
            encoding="utf-8"
        )
        lines = text.splitlines()
        first = non_blank(text)[0]
        self.assertTrue(first.startswith("# ") and not first.startswith("##"), first)
        self.assertEqual([l for l in lines if l.strip() == "## Guidance"], ["## Guidance"])
        before_guidance = text.split("## Guidance")[0]
        body = before_guidance.split(first, 1)[1]
        paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
        self.assertEqual(len(paragraphs), 1, paragraphs)
        self.assertIn("every run", paragraphs[0].lower())


class NewNumberingTests(LoopCommandCase):
    def test_new_takes_max_plus_one_over_existing_loop_folders(self):
        """Adversarial where: numbering by folder count instead of max (a gap
        reuses a taken number), restarting at 001 beside an existing loop, or
        counting a numbered file nested inside a loop folder."""
        cases = {
            "empty vault": ([], "001"),
            "beside LOOP-002-x": (["LOOP-002-x/index.md"], "003"),
            "gap after 001 and 005": (["LOOP-001-a/index.md", "LOOP-005-b/index.md"], "006"),
            "nested numbered file": (
                ["LOOP-002-x/index.md", "LOOP-002-x/golden/LOOP-009-p.md"], "003",
            ),
        }
        for name, (files, expected) in cases.items():
            with self.subTest(name):
                shutil.rmtree(self.root / "loops", ignore_errors=True)
                for rel in files:
                    path = self.root / "loops" / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("---\ntype: loop\n---\n", encoding="utf-8")
                code, _, err = self.loop("new", "fresh-name")
                self.assertEqual(code, 0, err)
                self.assertTrue(
                    (self.root / "loops" / f"LOOP-{expected}-fresh-name" / "index.md").is_file()
                )


class NewRefusalTests(LoopCommandCase):
    def test_new_refuses_a_name_that_already_has_a_loop_and_changes_nothing(self):
        """Adversarial where: a second `new` of the same name overwriting or
        topping up the first folder (a hand-edited actuator.md lost), creating
        `LOOP-002-same` beside it, or half-writing before it notices."""
        folder = self.new_loop("same")
        (folder / "actuator.md").write_text("hand written instructions\n", encoding="utf-8")
        looplib.append_ledger(folder, {"type": "review", "run_id": "r", "decision": "accept"})
        before = snapshot(self.root)
        code, _, _ = self.loop("new", "same")
        self.assertEqual(code, 1)
        self.assertEqual(snapshot(self.root), before)

    def test_new_refuses_an_existing_name_held_under_a_different_number(self):
        """Adversarial where: the existing-name check comparing the full
        folder name (`LOOP-006-same`) instead of the name part, so the same
        name is created again under the next number."""
        (self.root / "loops" / "LOOP-005-same").mkdir(parents=True)
        (self.root / "loops" / "LOOP-005-same" / "index.md").write_text(
            "---\ntype: loop\n---\nmine\n", encoding="utf-8"
        )
        before = snapshot(self.root)
        code, _, _ = self.loop("new", "same")
        self.assertEqual(code, 1)
        self.assertEqual(snapshot(self.root), before)

    def test_new_refuses_names_that_are_not_one_folder_segment(self):
        """Adversarial where: a name with a path separator or a parent
        reference creating the loop outside `loops/` (or in a nested folder),
        or an empty name creating `LOOP-001-`."""
        names = {
            "parent reference": "../evil",
            "nested path": "a/b",
            "backslash path": "a\\b",
            "dot dot only": "..",
            "empty": "",
        }
        for label, name in names.items():
            with self.subTest(label):
                before = snapshot(self.project)
                code, _, _ = self.loop("new", name)
                self.assertEqual(code, 1)
                self.assertEqual(snapshot(self.project), before)


class ActivateTests(LoopCommandCase):
    def test_activate_changes_only_the_frontmatter_status(self):
        """Adversarial where: `activate` replacing every `status:` line (a
        lookalike line in the index body is rewritten too), dropping other
        frontmatter fields, or touching a file other than `index.md`."""
        folder = self.new_loop("remove-bad")
        index = folder / "index.md"
        original_status = vaultlib.parse_frontmatter(index)[0]["status"]
        self.assertNotEqual(original_status, "active")
        lookalike = f"status: {original_status}"
        index.write_text(
            index.read_text(encoding="utf-8") + f"\n```\n{lookalike}\n```\n",
            encoding="utf-8", newline="\n",
        )
        before_text = index.read_text(encoding="utf-8")
        before_data = vaultlib.parse_frontmatter(index)[0]
        others = {k: v for k, v in snapshot(folder).items() if k != "index.md"}

        code, _, err = self.loop("activate", "LOOP-001")
        self.assertEqual(code, 0, err)

        after_text = index.read_text(encoding="utf-8")
        after_data = vaultlib.parse_frontmatter(index)[0]
        self.assertEqual(after_data["status"], "active")
        self.assertEqual(
            {k: v for k, v in after_data.items() if k != "status"},
            {k: v for k, v in before_data.items() if k != "status"},
        )
        self.assertEqual(after_text.split("\n---\n", 1)[1], before_text.split("\n---\n", 1)[1])
        self.assertIn(lookalike, after_text.split("\n---\n", 1)[1])
        self.assertEqual({k: v for k, v in snapshot(folder).items() if k != "index.md"}, others)


class UnknownLoopTests(LoopCommandCase):
    def test_every_command_on_an_unknown_loop_id_exits_1_and_changes_nothing(self):
        """Adversarial where: a command given a loop id that matches no folder
        (here the id one above the last) creating a folder, raising, or
        exiting 0 after doing nothing."""
        self.new_loop("remove-bad")
        invocations = {
            "status": ["status", "LOOP-002"],
            "activate": ["activate", "LOOP-002"],
            "pause": ["pause", "LOOP-002"],
            "resume": ["resume", "LOOP-002"],
            "review": ["review", "LOOP-002", "run-1", "accept"],
        }
        before = snapshot(self.root)
        for label, args in invocations.items():
            with self.subTest(label):
                code, _, _ = self.loop(*args)
                self.assertEqual(code, 1)
                self.assertEqual(snapshot(self.root), before)


class PauseResumeTests(LoopCommandCase):
    def test_pause_and_resume_follow_the_transition_table_over_every_state(self):
        """Adversarial where: pause or resume applied from a state the table
        forbids (`pause` from `halted`, `resume` from `done` or a working
        state) or a legal one landing in the wrong state; every state is
        tried for both commands, an illegal request must leave the folder
        byte-identical, and a legal one writes exactly one transition row."""
        legal = {
            ("pause", "idle"): "paused",
            ("pause", "throttled"): "paused",
            ("resume", "paused"): "idle",
            ("resume", "halted"): "idle",
        }
        folder = self.new_loop("remove-bad")
        for command, state in itertools.product(("pause", "resume"), ALL_STATES):
            with self.subTest(command=command, state=state):
                self.set_state(folder, state)
                before = snapshot(folder)
                rows_before = len(self.ledger(folder))
                code, _, _ = self.loop(command, "LOOP-001")
                if (command, state) in legal:
                    self.assertEqual(code, 0)
                    self.assertEqual(self.state_of(folder), legal[(command, state)])
                    rows = self.ledger(folder)
                    self.assertEqual(len(rows), rows_before + 1)
                    last = rows[-1]
                    self.assertEqual(
                        (last["type"], last["from"], last["event"], last["to"]),
                        ("transition", state, command, legal[(command, state)]),
                    )
                else:
                    self.assertEqual(code, 1)
                    self.assertEqual(snapshot(folder), before)


class ReviewTests(LoopCommandCase):
    VERIFIED = ("helpful", "neutral", "harmful")
    UNVERIFIED = ("failed", "throttled", "crashed")

    def seeded_loop(self):
        folder = self.new_loop("remove-bad")
        for outcome in self.VERIFIED + self.UNVERIFIED:
            for decision in ("accept", "reject"):
                for state in ("idle", "halted"):
                    self.add_run(folder, f"{outcome}-{decision}-{state}", outcome)
        return folder

    def test_review_unknown_run_id_exits_1_and_changes_nothing(self):
        """Adversarial where: a run id that is only a prefix of a real id, or
        an id never recorded, being accepted (substring matching) or creating
        a review row for a run that does not exist; a reject reason must not
        reach `feedback.md` either."""
        folder = self.seeded_loop()
        before = snapshot(folder)
        for label, run_id in {"never recorded": "no-such-run",
                              "prefix of a real id": "helpful-accept-idl",
                              "empty": ""}.items():
            for decision in ("accept", "reject"):
                with self.subTest(label, decision=decision):
                    args = ["review", "LOOP-001", run_id, decision]
                    if decision == "reject":
                        args += ["--reason", "must not land"]
                    code, _, _ = self.loop(*args)
                    self.assertEqual(code, 1)
                    self.assertEqual(snapshot(folder), before)

    def test_review_applies_only_to_a_run_that_reached_verifying(self):
        """Adversarial where: accepting or rejecting a failed, throttled or
        crashed run (it left no increment), a refused review still appending
        its reason to `feedback.md`, or an accepted one moving state or
        writing anything but a single review row."""
        folder = self.seeded_loop()
        for state in ("idle", "halted"):
            self.set_state(folder, state)
            for outcome in self.UNVERIFIED + self.VERIFIED:
                for decision in ("accept", "reject"):
                    with self.subTest(state=state, outcome=outcome, decision=decision):
                        run_id = f"{outcome}-{decision}-{state}"
                        args = ["review", "LOOP-001", run_id, decision]
                        if decision == "reject":
                            args += ["--reason", f"reason {state} {outcome}"]
                        before = snapshot(folder)
                        rows_before = self.ledger(folder)
                        code, _, _ = self.loop(*args)
                        after = snapshot(folder)
                        if outcome in self.UNVERIFIED:
                            self.assertEqual(code, 1)
                            self.assertEqual(after, before)
                            continue
                        self.assertEqual(code, 0)
                        self.assertEqual(after["state.json"], before["state.json"])
                        rows = self.ledger(folder)
                        self.assertEqual(len(rows), len(rows_before) + 1)
                        row = rows[-1]
                        self.assertEqual(
                            (row["type"], row["run_id"], row["decision"]),
                            ("review", run_id, decision),
                        )

    def test_reject_reason_becomes_exactly_one_feedback_line_and_one_ledger_row(self):
        """Adversarial where: a reason with an embedded newline writing two
        lines (or a blank line) into the guidance list, a non-ASCII reason
        mangled or written in the console's encoding, the reason replacing
        earlier guidance instead of appending, or the reject writing the
        ledger row twice."""
        reasons = {
            "plain": ("do not touch generated files", ["do not touch generated files"]),
            "embedded newline": ("first idea\nsecond idea", ["first idea", "second idea"]),
            "non-ascii": ("não use eval, é perigoso ✓", ["não use eval, é perigoso ✓"]),
        }
        folder = self.new_loop("remove-bad")
        for index, (label, (reason, expected_parts)) in enumerate(reasons.items()):
            with self.subTest(label):
                run_id = f"rejected-{index}"
                self.add_run(folder, run_id, "helpful")
                old_bytes = (folder / "feedback.md").read_bytes()
                old_lines = old_bytes.decode("utf-8").splitlines()
                rows_before = len(self.ledger(folder))

                code, _, err = self.loop(
                    "review", "LOOP-001", run_id, "reject", "--reason", reason
                )
                self.assertEqual(code, 0, err)

                new_bytes = (folder / "feedback.md").read_bytes()
                self.assertNotIn(b"\r\n", new_bytes)
                new_lines = new_bytes.decode("utf-8").splitlines()
                self.assertEqual(new_lines[:-1], old_lines)
                self.assertEqual(len(new_lines), len(old_lines) + 1)
                self.assertTrue(new_lines[-1].startswith("- "), new_lines[-1])
                for part in expected_parts:
                    self.assertIn(part, new_lines[-1])
                rows = self.ledger(folder)
                self.assertEqual(len(rows), rows_before + 1)
                self.assertEqual(rows[-1]["decision"], "reject")

    def test_reject_without_a_reason_adds_no_feedback_line(self):
        """Adversarial where: a reject with no reason appending an empty or
        placeholder bullet to the guidance list, or refusing the review; the
        ledger row is still written."""
        folder = self.new_loop("remove-bad")
        self.add_run(folder, "r-bare", "helpful")
        feedback_before = (folder / "feedback.md").read_bytes()
        rows_before = len(self.ledger(folder))
        code, _, err = self.loop("review", "LOOP-001", "r-bare", "reject")
        self.assertEqual(code, 0, err)
        self.assertEqual((folder / "feedback.md").read_bytes(), feedback_before)
        self.assertEqual(len(self.ledger(folder)), rows_before + 1)

    def test_review_with_a_malformed_invocation_exits_1_and_changes_nothing(self):
        """Adversarial where: a missing run id, a missing decision or a
        decision outside accept|reject treated as a default (accept) or
        surfacing argparse's exit 2."""
        folder = self.seeded_loop()
        before = snapshot(folder)
        cases = {
            "no run id or decision": ["review", "LOOP-001"],
            "no decision": ["review", "LOOP-001", "helpful-accept-idle"],
            "decision outside the pair": ["review", "LOOP-001", "helpful-accept-idle", "maybe"],
            "decision is a near miss": ["review", "LOOP-001", "helpful-accept-idle", "accepted"],
        }
        for label, args in cases.items():
            with self.subTest(label):
                code, _, _ = self.loop(*args)
                self.assertEqual(code, 1)
                self.assertEqual(snapshot(folder), before)


class StatusTests(LoopCommandCase):
    ZERO = re.compile(r"(?<![\d.])0(?:\.0+)?(?!\.?\d)")

    def lines_with(self, text, *words):
        return [l for l in text.splitlines() if any(w in l.lower() for w in words)]

    def test_status_of_a_fresh_draft_loop_shows_state_zero_spend_and_budgets(self):
        """Adversarial where: status failing on a draft loop with no sensor
        command, no reading and an empty ledger, omitting a budget, or
        reporting a non-zero figure for a loop that never ran."""
        self.new_loop("remove-bad", daily_budget_usd=3.5, total_budget_usd=11.5)
        code, out, err = self.loop("status", "LOOP-001")
        self.assertEqual(code, 0, err)
        self.assertIn("idle", out)
        for budget in ("3.5", "11.5"):
            self.assertIn(budget, out)
        today = self.lines_with(out, "today")
        lifetime = self.lines_with(out, "lifetime", "total")
        self.assertTrue(today, out)
        self.assertTrue(lifetime, out)
        self.assertTrue(any(self.ZERO.search(l) for l in today), today)
        self.assertTrue(any(self.ZERO.search(l) for l in lifetime), lifetime)

    def test_status_splits_spend_at_the_utc_day_boundary(self):
        """Adversarial where: spend a second before UTC midnight counted into
        today (or the first second of today dropped), or lifetime spend
        excluding the older days; amounts are chosen so the wrong sums
        (0.33, 0.66) differ from the right ones (0.11, 0.77)."""
        folder = self.new_loop("remove-bad", daily_budget_usd=3.5, total_budget_usd=11.5)
        midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        rows = [
            (midnight + timedelta(seconds=0), 0.11),
            (midnight - timedelta(seconds=1), 0.22),
            (midnight - timedelta(days=3), 0.44),
        ]
        for index, (when, cost) in enumerate(rows):
            self.add_run(folder, f"r{index}", "failed", cost=cost, ts=when.isoformat())
        code, out, err = self.loop("status", "LOOP-001")
        self.assertEqual(code, 0, err)
        self.assertIn("0.11", out)
        self.assertIn("0.77", out)
        self.assertNotIn("0.33", out)

    def test_status_reports_the_most_recent_halt_reason(self):
        """Adversarial where: status showing the first halt reason of a loop
        halted twice, or no reason at all for a halted loop."""
        folder = self.new_loop("remove-bad")
        self.set_state(folder, "halted")
        for reason in ("sensor printed garbage", "budget ran dry"):
            looplib.append_ledger(folder, {
                "type": "transition", "from": "sensing", "event": "invalid-reading",
                "to": "halted", "reason": reason,
            })
        code, out, err = self.loop("status", "LOOP-001")
        self.assertEqual(code, 0, err)
        self.assertIn("halted", out)
        self.assertIn("budget ran dry", out)
        self.assertNotIn("sensor printed garbage", out)

    def test_status_counts_unreviewed_increments_as_wip_and_review_lowers_it(self):
        """Adversarial where: failed runs counted as WIP, a reviewed run still
        counted, or status reading a stale count instead of the ledger; the
        limit (7) is chosen to differ from both counts shown."""
        folder = self.new_loop("remove-bad", wip_limit=7)
        self.add_run(folder, "r-help", "helpful", item="a.py:one")
        self.add_run(folder, "r-neutral", "neutral", item="b.py:two")
        self.add_run(folder, "r-failed", "failed", item="c.py:three")

        def wip_line():
            code, out, err = self.loop("status", "LOOP-001")
            self.assertEqual(code, 0, err)
            lines = self.lines_with(out, "wip")
            self.assertTrue(lines, out)
            return " ".join(lines)

        first = wip_line()
        self.assertRegex(first, r"\b2\b")
        code, _, err = self.loop("review", "LOOP-001", "r-help", "accept")
        self.assertEqual(code, 0, err)
        second = wip_line()
        self.assertRegex(second, r"\b1\b")
        self.assertNotRegex(second, r"\b2\b")

    def test_status_without_an_id_covers_every_loop(self):
        """Adversarial where: bare `status` reporting only the first loop, or
        refusing because no id was given."""
        self.new_loop("alpha")
        self.new_loop("beta")
        code, out, err = self.loop("status")
        self.assertEqual(code, 0, err)
        self.assertIn("LOOP-001", out)
        self.assertIn("LOOP-002", out)


class DispatchTests(LoopCommandCase):
    def test_bare_loop_prints_usage_with_exit_1_never_2(self):
        """Adversarial where: `compass loop` with no subcommand, an unknown
        subcommand or `new` with no name surfacing argparse's exit 2 (which
        blocks a hook's write) or crashing; usage must name every subcommand."""
        code, out, err = self.cli()
        self.assertEqual(code, 1, err)
        for name in SUBCOMMANDS:
            with self.subTest(name):
                self.assertIn(name, out + err)
        for args in (["bogus"], ["new"], ["review"], ["pause"]):
            with self.subTest(args=args):
                code, _, err = self.cli(*args)
                self.assertEqual(code, 1, err)
                self.assertNotIn("Traceback", err)
        self.assertFalse((self.root / "loops").exists())

    def test_run_check_and_baseline_never_exit_2_or_crash(self):
        """Adversarial where: the runner commands on a draft loop (no sensor
        command, not active) or with no loop id exiting 2, raising a
        traceback, or starting a real session instead of refusing."""
        self.new_loop("remove-bad")
        invocations = [
            ["run", "LOOP-001"],
            ["run", "LOOP-001", "--dry-run"],
            ["run"],
            ["check", "LOOP-001"],
            ["check"],
            ["baseline", "LOOP-001"],
            ["baseline"],
        ]
        for args in invocations:
            with self.subTest(args=args):
                code, _, err = self.cli(*args)
                self.assertIn(code, (0, 1), err)
                self.assertNotIn("Traceback", err)

    def test_real_process_round_trip_new_pause_resume_status(self):
        """Adversarial where: the in-process command working but the launcher
        path (argument vector, vault discovery from the environment, console
        encoding) failing; one full lifecycle through `python compass loop`."""
        steps = [
            (["new", "remove-bad"], 0),
            (["pause", "LOOP-001"], 0),
            (["pause", "LOOP-001"], 1),
            (["resume", "LOOP-001"], 0),
            (["status", "LOOP-001"], 0),
        ]
        for args, expected in steps:
            with self.subTest(args=args):
                code, _, err = self.cli(*args)
                self.assertEqual(code, expected, err)
        folder = self.root / "loops" / "LOOP-001-remove-bad"
        self.assertEqual(self.state_of(folder), "idle")


class MainCliRegistrationTests(unittest.TestCase):
    def test_loop_is_registered_and_listed_in_help(self):
        """Adversarial where: the `loop` entry missing from COMMAND_SPECS (the
        command is then unknown and exits 1 as unknown), registered with an
        empty help line, or absent from `compass --help`."""
        specs = dict(maincli.COMMAND_SPECS)
        self.assertIn("loop", specs)
        self.assertTrue(specs["loop"].strip())
        self.assertIn("loop", maincli.VALID_COMMANDS)
        out = io.StringIO()
        with self.assertRaises(SystemExit), redirect_stdout(out):
            maincli.main(["--help"])
        self.assertIn("loop", out.getvalue())

    def test_test_checkpoint_help_line_lists_cycle_beside_the_existing_modes(self):
        """Adversarial where: `cycle` added by replacing an existing mode in
        the `test-checkpoint` help line instead of joining record, verify and
        open-ids."""
        line = dict(maincli.COMMAND_SPECS)["test-checkpoint"]
        for mode in ("record", "verify", "open-ids", "cycle"):
            with self.subTest(mode):
                self.assertIn(mode, line)


if __name__ == "__main__":
    unittest.main()
