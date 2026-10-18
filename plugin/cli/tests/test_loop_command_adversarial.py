"""Adversarial tests for `compass loop` aimed at the failure modes its own
code introduces: folder names the filesystem treats specially, two processes
creating loops at once, hand-damaged state files that `status` must report
rather than die on, free text that reaches `feedback.md`, an `index.md` in an
editor's line-ending dialect, a run lock held while the human acts, and the
template tree surviving an install copy.

These sit beside `test_loop_command.py`, which pins the public contract;
nothing here restates it.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CLI_DIR)

import looplib  # noqa: E402
import vaultlib  # noqa: E402
from commands import loop as loop_command  # noqa: E402
from commands import self_update  # noqa: E402
from commands import validate  # noqa: E402

COMPASS = os.path.join(CLI_DIR, "compass")

ROOT_INDEX = "# Index\n\n## Specs\n\n## Plans\n\n## Research\n\n## Decisions\n\n## Lessons\n\n## Handoffs\n"

WORKER = textwrap.dedent(
    """
    import os, sys, time
    sys.path.insert(0, sys.argv[1])
    go = sys.argv[2]
    deadline = time.time() + 60
    while not os.path.exists(go) and time.time() < deadline:
        pass
    from commands import loop
    sys.exit(loop.run(sys.argv[3:]))
    """
)


class VaultCase(unittest.TestCase):
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
        """Run `compass loop <args>` in-process: (code, stdout, stderr). An
        exception that escapes `run` propagates and fails the calling test."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = loop_command.run(list(args))
        code = 0 if code is None else code
        self.assertNotEqual(code, 2, f"loop {args} exited 2: {err.getvalue()}")
        return code, out.getvalue(), err.getvalue()

    def process(self, *args, env_extra=None, exe=COMPASS):
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.project)
        env.update(env_extra or {})
        return subprocess.run(
            [sys.executable, exe, "loop", *args],
            capture_output=True, env=env, cwd=str(self.project), timeout=120,
        )

    def new_loop(self, name="remove-bad"):
        code, _, err = self.loop("new", name)
        self.assertEqual(code, 0, err)
        found = sorted((self.root / "loops").glob(f"LOOP-[0-9]*-{name}"))
        self.assertEqual(len(found), 1, found)
        return found[0]

    def loops_dir_listing(self):
        loops = self.root / "loops"
        return sorted(p.name for p in loops.iterdir()) if loops.is_dir() else []

    def race(self, argv_lists):
        """Start one process per argv at once behind a barrier file and
        return their (returncode, stderr) in order."""
        script = self.project / "worker.py"
        script.write_text(WORKER, encoding="utf-8")
        go = self.project / "go.flag"
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project))
        procs = [
            subprocess.Popen(
                [sys.executable, str(script), CLI_DIR, str(go), *argv],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                cwd=str(self.project),
            )
            for argv in argv_lists
        ]
        time.sleep(1.5)
        go.write_text("go", encoding="utf-8")
        results = []
        for proc in procs:
            _out, err = proc.communicate(timeout=90)
            results.append((proc.returncode, err.decode("utf-8", "replace")))
        go.unlink()
        return results


class NewNameTests(VaultCase):
    def test_new_refuses_names_no_folder_segment_can_safely_carry(self):
        """Adversarial where: a name regex that lets a hostile or accidental
        name through - non-ASCII letters, spaces, a trailing dot, a trailing
        newline (a `$` anchor accepts `abc\\n`), upper-case reserved device
        names, path separators, an empty string - and then half-creates a
        folder or writes a name into the index frontmatter that breaks it."""
        refused = [
            ("hello world", "space"),
            ("héllo", "accented letter"),
            ("日本", "CJK"),
            ("аbc", "Cyrillic a"),
            ("abc.", "trailing dot"),
            ("abc ", "trailing space"),
            ("abc\n", "trailing newline"),
            ("a\nb", "embedded newline"),
            ("CON", "reserved device name"),
            ("NUL", "reserved device name"),
            ("AUX", "reserved device name"),
            ("con.txt", "device name with extension"),
            ("a/b", "forward slash"),
            ("a\\b", "backslash"),
            ("a:b", "colon"),
            ("..", "parent segment"),
            ("", "empty"),
        ]
        for name, why in refused:
            with self.subTest(why=why, name=name):
                before = self.loops_dir_listing()
                code, _out, err = self.loop("new", name)
                self.assertEqual(code, 1, f"{name!r} was accepted")
                self.assertTrue(err.strip(), "a refusal prints its reason")
                self.assertEqual(self.loops_dir_listing(), before)

    def test_new_accepts_lowercase_device_names_and_a_loop_that_works(self):
        """Adversarial where: refusing or mangling `con`, `nul`, `aux` in
        lower case, which become `LOOP-001-con` and are ordinary folders,
        or accepting them and producing a loop `status` cannot address."""
        for name in ("con", "nul", "aux", "com1", "lpt1"):
            with self.subTest(name=name):
                folder = self.new_loop(name)
                self.assertTrue((folder / "state.json").is_file())
                number = folder.name.split("-")[1]
                code, out, err = self.loop("status", f"LOOP-{number}")
                self.assertEqual(code, 0, err)
                self.assertIn(name, out)
        errors, _ = validate.check_vault(self.root)
        self.assertEqual(errors, [])

    def test_new_with_an_overlong_name_fails_clean_and_a_long_one_still_works(self):
        """Adversarial where: a name past the filesystem's 255-character
        segment limit crashing with a traceback or leaving the `.new-*.tmp`
        staging folder behind, and a long name inside the limit being refused
        or leaving a loop `status` cannot read."""
        with self.subTest("far over the limit"):
            code, _out, err = self.loop("new", "a" * 400)
            self.assertEqual(code, 1)
            self.assertTrue(err.strip())
            self.assertEqual(self.loops_dir_listing(), [])
        with self.subTest("long but legal"):
            name = "b" * 100
            folder = self.new_loop(name)
            code, out, err = self.loop("status", "LOOP-001")
            self.assertEqual(code, 0, err)
            self.assertIn(name, out)
            self.assertEqual(
                [n for n in self.loops_dir_listing() if n.startswith(".new-")], []
            )


class NewRaceTests(VaultCase):
    ROUNDS = 4

    def test_two_processes_creating_the_same_name_leave_exactly_one_intact_loop(self):
        """Adversarial where: both processes pass the name-exists check
        before either renames, so both report success or one overwrites the
        other, or a refused one leaves its staging folder behind."""
        for round_ in range(self.ROUNDS):
            with self.subTest(round=round_):
                name = f"same-{round_}"
                results = self.race([["new", name], ["new", name]])
                codes = sorted(code for code, _err in results)
                self.assertEqual(codes, [0, 1], results)
                folders = [n for n in self.loops_dir_listing() if n.endswith(f"-{name}")]
                self.assertEqual(len(folders), 1, folders)
                self.assertEqual(
                    [n for n in self.loops_dir_listing() if n.startswith(".new-")], []
                )
                folder = self.root / "loops" / folders[0]
                for rel in ("index.md", "loop.json", "actuator.md", "feedback.md",
                            "state.json", "golden/pattern-template.md"):
                    self.assertTrue((folder / rel).is_file(), f"{rel} missing from {folder.name}")
                self.assertEqual(looplib.read_state(folder)["state"], "idle")

    def test_two_processes_creating_different_names_get_distinct_numbers(self):
        """Adversarial where: both processes compute max+1 over the same
        directory listing and take the same number, leaving two folders that
        share `LOOP-001` and making every later `LOOP-001` command report
        'ambiguous'."""
        for round_ in range(self.ROUNDS):
            with self.subTest(round=round_):
                a, b = f"first-{round_}", f"second-{round_}"
                results = self.race([["new", a], ["new", b]])
                created = [
                    n for n in self.loops_dir_listing()
                    if n.endswith(f"-{a}") or n.endswith(f"-{b}")
                ]
                numbers = [n.split("-")[1] for n in created]
                self.assertEqual(len(set(numbers)), len(numbers), f"duplicate numbers: {created}")
                for code, err in results:
                    if code != 0:
                        self.assertTrue(err.strip(), "a refused create explains itself")
                for name in created:
                    number = name.split("-")[1]
                    code, _out, err = self.loop("status", f"LOOP-{number}")
                    self.assertEqual(code, 0, err)


class StatusDamageTests(VaultCase):
    def test_status_reports_a_damaged_state_file_instead_of_crashing(self):
        """Adversarial where: `state.json` truncated by a crash, emptied,
        holding a non-object, an unknown state or invalid UTF-8 makes
        `status` raise instead of printing the loop and saying what is
        wrong."""
        folder = self.new_loop("damaged")
        number = folder.name.split("-")[1]
        damaged = {
            "truncated": b'{"state": ',
            "empty": b"",
            "array": b"[1, 2]",
            "unknown state": b'{"state": "levitating"}',
            "state is a number": b'{"state": 7}',
            "invalid utf-8": b"\xff\xfe\x00{",
            "NUL bytes": b"\x00\x00\x00",
        }
        for label, data in damaged.items():
            with self.subTest(label):
                (folder / "state.json").write_bytes(data)
                code, out, err = self.loop("status", f"LOOP-{number}")
                self.assertEqual(code, 0, err)
                self.assertIn("damaged", out)
                self.assertIn("state.json", out + err)

    def test_status_survives_a_damaged_ledger_and_still_counts_the_good_rows(self):
        """Adversarial where: a ledger with a half-written last line, binary
        junk, a non-object row, and numeric fields past float range (an int
        with 400 digits, infinity, NaN, a string) crashing the spend or WIP
        fold, or dropping the readable rows around the damage."""
        folder = self.new_loop("ledgerdamage")
        number = folder.name.split("-")[1]
        today = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
        good = json.dumps({"ts": today, "type": "run", "run_id": "ok", "outcome": "helpful",
                           "item": "a:b", "cost_usd": 0.25})
        hostile_costs = [
            ("huge int", "1" + "0" * 400),
            ("infinity", "1e999"),
            ("nan", "NaN"),
            ("string", '"0.5"'),
            ("negative", "-3"),
            ("list", "[1]"),
        ]
        for label, cost in hostile_costs:
            with self.subTest(cost=label):
                text = "\n".join([
                    good,
                    "\x00\x00 binary \xff junk",
                    "[1, 2, 3]",
                    '{"type": "run", "run_id": "bad", "outcome": "helpful", "cost_usd": ' + cost + "}",
                    '{"type": "run", "run_id": "half", "outcome": "hel',
                ])
                (folder / "ledger.jsonl").write_bytes(text.encode("utf-8", "surrogateescape"))
                code, out, err = self.loop("status", f"LOOP-{number}")
                self.assertEqual(code, 0, err)
                self.assertIn("0.25", out, "the readable row's spend is lost")
                self.assertIn("unreadable", out)

    def test_status_survives_a_damaged_definition(self):
        """Adversarial where: `loop.json` that is not an object, is invalid
        UTF-8, or carries a budget as an int past float range (the budget
        formatter converts through float) crashes `status`, which must work
        on exactly the files the human is mid-way through editing."""
        folder = self.new_loop("defdamage")
        number = folder.name.split("-")[1]
        variants = {
            "array": b"[1]",
            "invalid utf-8": b"\xff\xfe\x00",
            "empty": b"",
            "null budgets": b'{"daily_budget_usd": null, "wip_limit": null}',
            "string budgets": b'{"daily_budget_usd": "3", "total_budget_usd": "x"}',
            "bool budget": b'{"daily_budget_usd": true}',
            "huge int budget": b'{"daily_budget_usd": 1' + b"0" * 400 + b', "total_budget_usd": 2}',
            "huge int wip": b'{"wip_limit": 1' + b"0" * 400 + b"}",
            "duplicate keys": b'{"wip_limit": 1, "wip_limit": 2}',
        }
        for label, data in variants.items():
            with self.subTest(label):
                (folder / "loop.json").write_bytes(data)
                code, _out, err = self.loop("status", f"LOOP-{number}")
                self.assertEqual(code, 0, err)

    def test_status_of_every_loop_prints_the_healthy_ones_beside_a_damaged_one(self):
        """Adversarial where: one loop's unreadable state aborting the
        all-loops listing, so a healthy neighbour is never shown."""
        first = self.new_loop("alpha")
        self.new_loop("omega")
        (first / "state.json").write_bytes(b"{")
        code, out, err = self.loop("status")
        self.assertEqual(code, 0, err)
        self.assertIn("alpha", out)
        self.assertIn("omega", out)

    def test_status_text_is_encodable_on_a_cp1252_console(self):
        """Adversarial where: a status line holding a character outside
        cp1252 (an arrow, a check mark, a box drawing) for ASCII data, or a
        halt reason with non-cp1252 text raising UnicodeEncodeError on a
        console whose encoding cannot represent it."""
        folder = self.new_loop("console")
        number = folder.name.split("-")[1]
        with self.subTest("fixed text is ASCII-safe"):
            code, out, err = self.loop("status", f"LOOP-{number}")
            self.assertEqual(code, 0, err)
            out.encode("cp1252")
        looplib.append_ledger(folder, {
            "type": "transition", "from": "gating", "event": "total-budget-spent",
            "to": "halted", "reason": "café → ✓ 中文 \U0001f600",
        })
        with self.subTest("non-cp1252 halt reason in a real cp1252 process"):
            result = self.process(
                "status", f"LOOP-{number}",
                env_extra={"PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"},
            )
            self.assertEqual(result.returncode, 0, result.stderr[-400:])
            self.assertNotIn(b"Traceback", result.stderr)
            self.assertNotIn(b"UnicodeEncodeError", result.stderr)
            self.assertTrue(result.stdout.strip())


class ReviewTextTests(VaultCase):
    def make_run(self, folder, run_id="r1", outcome="harmful"):
        looplib.append_ledger(folder, {"type": "run", "run_id": run_id, "outcome": outcome,
                                       "item": "a.py:x", "cost_usd": 0.1})

    def test_a_reject_reason_cannot_become_structure_in_feedback_md(self):
        """Adversarial where: a reason that is itself markdown structure (a
        heading, a frontmatter fence, a rule, a block quote, a task box, an
        embedded line separator) lands at column 0 of `feedback.md` and turns
        the guidance file into something other than a list under
        `## Guidance`, or spans more than one line."""
        reasons = {
            "heading": "## Heading",
            "frontmatter block": "---\ntitle: x\n---\nbody",
            "bare fence": "---",
            "h1": "# New title",
            "quote": "> quoted",
            "task box": "[ ] do it",
            "unicode line separator": "one ## two ---\u0085three",
            "crlf": "one\r\n## two\r\n",
            "tab and form feed": "a\t\x0c## b",
            "nul": "a\x00b",
            "leading dash": "- already a bullet",
        }
        for label, reason in reasons.items():
            with self.subTest(label):
                folder = self.new_loop(f"rv-{label.replace(' ', '-')}")
                number = folder.name.split("-")[1]
                self.make_run(folder)
                before = (folder / "feedback.md").read_bytes()
                code, _out, err = self.loop("review", f"LOOP-{number}", "r1", "reject",
                                            "--reason", reason)
                self.assertEqual(code, 0, err)
                after = (folder / "feedback.md").read_bytes()
                self.assertTrue(after.startswith(before))
                added = after[len(before):].decode("utf-8")
                self.assertEqual(len(added.splitlines()), 1, repr(added))
                self.assertTrue(added.startswith("- "), repr(added))
                self.assertNotIn(b"\r", after)
                text = after.decode("utf-8")
                headings = [ln for ln in text.splitlines() if ln.startswith("#")]
                self.assertEqual(headings, ["# Feedback", "## Guidance"])
                self.assertFalse(any(ln.strip() == "---" for ln in text.splitlines()))
                rows, skipped = looplib.read_ledger(folder)
                self.assertEqual(skipped, [])
                self.assertEqual(sum(1 for r in rows if r.get("type") == "review"), 1)

    def test_a_reject_appends_to_a_feedback_file_in_any_state_a_human_left_it(self):
        """Adversarial where: appending to a `feedback.md` that lacks a final
        newline, has CRLF endings or a BOM, or is gone, fuses the new bullet
        onto the last line, leaves mixed endings, or raises instead of
        recreating the file."""
        base = "# Feedback\n\nIntro.\n\n## Guidance\n- keep names short"
        variants = {
            "no final newline": base.encode("utf-8"),
            "crlf": base.replace("\n", "\r\n").encode("utf-8"),
            "bom": b"\xef\xbb\xbf" + base.encode("utf-8"),
        }
        for label, data in variants.items():
            with self.subTest(label):
                folder = self.new_loop(f"fb-{label.replace(' ', '-')}")
                number = folder.name.split("-")[1]
                self.make_run(folder)
                (folder / "feedback.md").write_bytes(data)
                code, _out, err = self.loop("review", f"LOOP-{number}", "r1", "reject",
                                            "--reason", "too broad")
                self.assertEqual(code, 0, err)
                lines = (folder / "feedback.md").read_bytes().decode("utf-8-sig").split("\n")
                self.assertEqual(lines[-2:], ["- too broad", ""])
                self.assertIn("- keep names short", lines)
                self.assertNotIn(b"\r", (folder / "feedback.md").read_bytes())
        with self.subTest("file missing"):
            folder = self.new_loop("fb-missing")
            number = folder.name.split("-")[1]
            self.make_run(folder)
            (folder / "feedback.md").unlink()
            code, _out, err = self.loop("review", f"LOOP-{number}", "r1", "reject",
                                        "--reason", "again")
            self.assertEqual(code, 0, err)
            self.assertIn("- again", (folder / "feedback.md").read_text(encoding="utf-8"))

    def test_a_failed_feedback_write_leaves_no_review_row_behind(self):
        """Adversarial where: the ledger row is appended before the
        `feedback.md` write fails, so the command exits 1 yet the run now
        counts as reviewed and every retry is refused with 'already
        reviewed' - a refusal that half-writes."""
        folder = self.new_loop("fb-blocked")
        number = folder.name.split("-")[1]
        self.make_run(folder)
        (folder / "feedback.md").unlink()
        (folder / "feedback.md").mkdir()
        code, _out, _err = self.loop("review", f"LOOP-{number}", "r1", "reject",
                                     "--reason", "nope")
        self.assertEqual(code, 1)
        rows, _ = looplib.read_ledger(folder)
        self.assertEqual([r for r in rows if r.get("type") == "review"], [],
                         "a failed review left a review row")

    def test_a_second_review_of_a_run_is_refused_whatever_the_decisions(self):
        """Adversarial where: the `already reviewed` check compares decisions
        or reasons rather than the run, so accept-then-reject,
        reject-then-accept or a repeat with a new reason is let through and
        the run is counted twice (WIP drops below zero, guidance doubles)."""
        pairs = [("accept", "accept"), ("accept", "reject"),
                 ("reject", "accept"), ("reject", "reject")]
        for index, (first, second) in enumerate(pairs):
            with self.subTest(first=first, second=second):
                folder = self.new_loop(f"twice-{index}")
                number = folder.name.split("-")[1]
                self.make_run(folder)
                self.assertEqual(
                    self.loop("review", f"LOOP-{number}", "r1", first, "--reason", "first")[0], 0)
                snap = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
                code, _out, err = self.loop("review", f"LOOP-{number}", "r1", second,
                                            "--reason", "second")
                self.assertEqual(code, 1)
                self.assertIn("already reviewed", err)
                after = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
                self.assertEqual(after, snap)
        with self.subTest("a different run is still reviewable"):
            folder = self.new_loop("twice-other")
            number = folder.name.split("-")[1]
            self.make_run(folder, "r1")
            self.make_run(folder, "r2")
            self.assertEqual(self.loop("review", f"LOOP-{number}", "r1", "accept")[0], 0)
            self.assertEqual(self.loop("review", f"LOOP-{number}", "r2", "accept")[0], 0)

    def test_two_processes_reviewing_the_same_run_record_one_review(self):
        """Adversarial where: the already-reviewed check and the ledger
        append are separate steps, so two simultaneous reviews both pass the
        check and both append, doubling the review row and the guidance
        line."""
        for round_ in range(3):
            with self.subTest(round=round_):
                folder = self.new_loop(f"racing-{round_}")
                number = folder.name.split("-")[1]
                self.make_run(folder)
                results = self.race([
                    ["review", f"LOOP-{number}", "r1", "reject", "--reason", "from-a"],
                    ["review", f"LOOP-{number}", "r1", "reject", "--reason", "from-b"],
                ])
                rows, _ = looplib.read_ledger(folder)
                reviews = [r for r in rows if r.get("type") == "review"]
                self.assertEqual(len(reviews), 1, results)
                guidance = [ln for ln in (folder / "feedback.md").read_text(
                    encoding="utf-8").splitlines() if ln.startswith("- ")]
                self.assertEqual(len(guidance), 1, guidance)
                self.assertEqual(sorted(code for code, _ in results), [0, 1])


class ActivateFormatTests(VaultCase):
    def test_activate_handles_the_index_dialects_editors_write(self):
        """Adversarial where: the frontmatter regex assumes LF and a body
        after the closing fence, so a CRLF index, a BOM, an index whose
        closing `---` ends the file without a newline, or one holding a
        `status:` line in the body before the real field is refused or edits
        the wrong line."""
        head = '---\ntitle: "T"\ntype: loop\nstatus: draft\narea: workflow\n'
        tail = "tags: [loop]\ncreated: 2026-01-01\nupdated: 2026-01-01\nsummary: \"s\"\n---\n"
        body = "\n# T\n\nstatus: draft\n"
        cases = {
            "lf": (head + tail + body).encode("utf-8"),
            "crlf": (head + tail + body).replace("\n", "\r\n").encode("utf-8"),
            "bom": b"\xef\xbb\xbf" + (head + tail + body).encode("utf-8"),
            "closing fence ends the file": (head + tail.rstrip("\n")).encode("utf-8"),
            "closing fence then crlf only": (head + tail).replace("\n", "\r\n").encode("utf-8"),
            "status with trailing comment": (head.replace("status: draft", "status: draft  # wip")
                                             + tail + body).encode("utf-8"),
            "status quoted": (head.replace("status: draft", 'status: "draft"') + tail + body).encode("utf-8"),
        }
        for label, data in cases.items():
            with self.subTest(label):
                folder = self.new_loop("dialect-" + label.replace(" ", "-"))
                number = folder.name.split("-")[1]
                (folder / "index.md").write_bytes(data)
                code, _out, err = self.loop("activate", f"LOOP-{number}")
                self.assertEqual(code, 0, err)
                parsed, error = vaultlib.parse_frontmatter(folder / "index.md")
                self.assertIsNone(error)
                self.assertEqual(parsed.get("status"), "active")
                self.assertEqual(parsed.get("title"), "T")
                if b"# T" in data and b"# wip" not in data:
                    text = (folder / "index.md").read_text(encoding="utf-8-sig")
                    self.assertIn("\nstatus: draft", text.split("---", 2)[2],
                                  "the body line must be untouched")

    def test_activate_refuses_an_index_without_usable_frontmatter_and_leaves_it_alone(self):
        """Adversarial where: an index with no frontmatter, a frontmatter
        without `status`, or an unterminated fence is silently rewritten, or
        raises, rather than refused with exit 1 and the bytes untouched."""
        cases = {
            "no frontmatter": b"# Just a title\n\nstatus: draft\n",
            "no status field": b"---\ntitle: T\ntype: loop\n---\n\nbody\n",
            "unterminated fence": b"---\ntitle: T\nstatus: draft\n\nbody\n",
            "empty file": b"",
            "indented status only": b"---\ntitle: T\nmeta:\n  status: draft\n---\nbody\n",
        }
        for label, data in cases.items():
            with self.subTest(label):
                folder = self.new_loop("refuse-" + label.replace(" ", "-"))
                number = folder.name.split("-")[1]
                (folder / "index.md").write_bytes(data)
                code, _out, err = self.loop("activate", f"LOOP-{number}")
                self.assertEqual(code, 1, "accepted an index it cannot activate")
                self.assertTrue(err.strip())
                self.assertEqual((folder / "index.md").read_bytes(), data)


class LockedLoopTests(VaultCase):
    def lock_path(self, folder):
        number = folder.name.split("-")[1]
        return self.root / "tmp" / "loops" / f"LOOP-{number}.lock"

    def test_pause_and_resume_while_a_run_holds_the_lock(self):
        """Adversarial where: pause or resume succeeding in the middle of a
        run (a working state with a live lock), moving the state out from
        under the runner, or leaving state.json and the ledger disagreeing
        about whether a transition happened."""
        working = sorted(looplib.WORKING)
        for state in working:
            with self.subTest(state=state):
                folder = self.new_loop(f"mid-{state}")
                number = folder.name.split("-")[1]
                looplib.write_state(folder, {"state": state})
                lock = self.lock_path(folder)
                looplib.acquire_lock(lock, 60)
                held = lock.read_bytes()
                before_ledger = looplib.read_ledger(folder)[0]
                for command in ("pause", "resume"):
                    code, _out, err = self.loop(command, f"LOOP-{number}")
                    self.assertEqual(code, 1, f"{command} allowed during {state}")
                    self.assertTrue(err.strip())
                self.assertEqual(looplib.read_state(folder)["state"], state)
                self.assertEqual(looplib.read_ledger(folder)[0], before_ledger)
                self.assertEqual(lock.read_bytes(), held, "the lock was touched")

    def test_pause_with_a_lock_file_present_keeps_state_and_ledger_in_step(self):
        """Adversarial where: a resting loop with a lock file present (the
        window before the runner writes `sensing`) lets `pause` write the
        state but not the ledger row, or the reverse."""
        folder = self.new_loop("window")
        number = folder.name.split("-")[1]
        lock = self.lock_path(folder)
        looplib.acquire_lock(lock, 60)
        held = lock.read_bytes()
        code, _out, _err = self.loop("pause", f"LOOP-{number}")
        state = looplib.read_state(folder)["state"]
        rows, _ = looplib.read_ledger(folder)
        moved = [r for r in rows if r.get("type") == "transition" and r.get("event") == "pause"]
        if code == 0:
            self.assertEqual((state, len(moved)), ("paused", 1))
        else:
            self.assertEqual((state, len(moved)), ("idle", 0))
        self.assertEqual(lock.read_bytes(), held)

    def test_pause_and_resume_on_a_damaged_state_file_exit_1_and_write_nothing(self):
        """Adversarial where: a transition command on an unreadable
        `state.json` overwrites it with a fresh idle state (destroying the
        evidence of what the loop was doing) or crashes."""
        folder = self.new_loop("pausedamage")
        number = folder.name.split("-")[1]
        for label, data in {"truncated": b'{"state": ', "unknown": b'{"state": "x"}'}.items():
            with self.subTest(label):
                (folder / "state.json").write_bytes(data)
                for command in ("pause", "resume"):
                    code, _out, err = self.loop(command, f"LOOP-{number}")
                    self.assertEqual(code, 1)
                    self.assertTrue(err.strip())
                    self.assertEqual((folder / "state.json").read_bytes(), data)
                self.assertEqual(looplib.read_ledger(folder)[0], [])


class TemplateTests(VaultCase):
    SENSOR = "python sense.py"

    def scaffolded_definition(self):
        folder = self.new_loop("tmpl")
        path = folder / "loop.json"
        return folder, path, json.loads(path.read_text(encoding="utf-8"))

    def test_scaffolded_definition_loads_once_a_sensor_is_set_and_orders_its_budgets(self):
        """Adversarial where: a template whose only gap is the sensor command
        still fails to load (a stray key, a wrong type, a missing field), or
        whose per-run budget exceeds the daily budget or the daily budget
        exceeds the lifetime budget, so the first run is throttled forever or
        the cap `max_turns` drifts from the documented 30."""
        folder, path, data = self.scaffolded_definition()
        with self.subTest("draft is refused by naming the sensor"):
            with self.assertRaises(looplib.DefinitionError) as caught:
                looplib.load_definition(folder)
            self.assertIn("sensor_command", str(caught.exception))
        data["sensor_command"] = self.SENSOR
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
        definition = looplib.load_definition(folder)
        with self.subTest("caps"):
            self.assertEqual(definition["max_turns"], 30)
            self.assertGreater(definition["max_budget_usd"], 0)
            self.assertLessEqual(definition["max_budget_usd"], definition["daily_budget_usd"])
            self.assertLessEqual(definition["daily_budget_usd"], definition["total_budget_usd"])
        with self.subTest("every cap and limit is positive"):
            for key in ("timeout_s", "sensor_timeout_s", "wip_limit", "max_actuator_failures",
                        "max_harmful_runs", "max_runs_without_help"):
                self.assertGreater(definition[key], 0, key)
        with self.subTest("a run fits in a day with room for a second"):
            self.assertGreaterEqual(
                definition["daily_budget_usd"], 2 * definition["max_budget_usd"]
            )

    def test_scaffolded_files_survive_a_second_scaffold_and_hold_no_placeholders(self):
        """Adversarial where: a `{{placeholder}}` the renderer does not know
        reaches the user's files, or the id/name/date substitutions land in
        the wrong file so two loops share content that must differ."""
        first = self.new_loop("one")
        second = self.new_loop("two")
        for folder in (first, second):
            for path in folder.rglob("*"):
                if path.is_file():
                    with self.subTest(path=path.relative_to(folder).as_posix(), loop=folder.name):
                        self.assertNotIn("{{", path.read_text(encoding="utf-8"))
        self.assertIn("LOOP-001", (first / "index.md").read_text(encoding="utf-8"))
        self.assertIn("LOOP-002", (second / "index.md").read_text(encoding="utf-8"))
        self.assertNotIn("LOOP-002", (first / "index.md").read_text(encoding="utf-8"))

    def test_templates_ship_through_the_self_update_copy_and_still_scaffold(self):
        """Adversarial where: the installed CLI copy (`.claude/cli`, made by
        self-update) lacks `loop_templates` or its nested `golden/` folder
        because the copier or a packaging rule skips non-Python data, so
        `compass loop new` works from the repo and fails after an install."""
        source = Path(CLI_DIR)
        installed = self.project / ".claude" / "cli"
        self_update._copy_tree_best_effort(source, installed)
        shipped = sorted(
            p.relative_to(source / "loop_templates").as_posix()
            for p in (source / "loop_templates").rglob("*") if p.is_file()
        )
        self.assertIn("golden/pattern-template.md", shipped)
        for rel in shipped:
            with self.subTest(rel):
                self.assertEqual(
                    (installed / "loop_templates" / rel).read_bytes(),
                    (source / "loop_templates" / rel).read_bytes(),
                )
        result = self.process("new", "from-install", exe=str(installed / "compass"))
        self.assertEqual(result.returncode, 0, result.stderr[-400:])
        created = self.root / "loops" / "LOOP-001-from-install"
        self.assertTrue((created / "golden" / "pattern-template.md").is_file())
        self.assertEqual(looplib.read_state(created)["state"], "idle")


if __name__ == "__main__":
    unittest.main()
