"""Adversarial tests for `compass loop schedule`, `reconcile` and
`status --last-run`, written against the finished implementation.

Themes: values that cross a trust boundary into a YAML scalar, a scheduler
line or a shell script (cron text, project paths, the interpreter path, run
ids read back from the ledger); `.gitattributes` bytes the command did not
write; pull request lists and ledgers that are damaged in ways a well-formed
fixture never is; and the rendered workflow's shell steps executed against
real git repositories with a stubbed `gh`: the increment pull request, the
state commit racing another push, a protected default branch, a run that
produced no increment.
"""

import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CLI_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_loop_command import snapshot  # noqa: E402
from test_loop_schedule import (  # noqa: E402
    RECONCILED,
    RUN_CLOSED,
    RUN_MERGED,
    RUN_OPEN,
    TARGET,
    UNION_LINE,
    WORKFLOW_PATH,
    ReconcileCase,
    ScheduleCase,
    split_steps,
)

CLOSED_GUIDANCE = "closed without merge"
BASH = shutil.which("bash")
GIT = shutil.which("git")
PYTHON = shutil.which("python")


def msvc_argv(command_line):
    """Split `command_line` the way the Microsoft C runtime does: a quote
    toggles quoting, `2n` backslashes before a quote give `n` backslashes and
    toggle, `2n+1` give `n` backslashes and a literal quote."""
    args, current, in_quote, started, i = [], [], False, False, 0
    while i < len(command_line):
        ch = command_line[i]
        if ch == "\\":
            run = 0
            while i < len(command_line) and command_line[i] == "\\":
                run += 1
                i += 1
            if i < len(command_line) and command_line[i] == '"':
                current.append("\\" * (run // 2))
                if run % 2:
                    current.append('"')
                    i += 1
                # an even run leaves the quote for the next pass to toggle
            else:
                current.append("\\" * run)
            started = True
            continue
        if ch == '"':
            in_quote = not in_quote
            started = True
        elif ch in " \t" and not in_quote:
            if started:
                args.append("".join(current))
                current, started = [], False
        else:
            current.append(ch)
            started = True
        i += 1
    if started:
        args.append("".join(current))
    return args


def outside_quotes(text):
    """The characters of `text` that `cmd.exe` reads outside double quotes."""
    kept, in_quote = [], False
    for ch in text:
        if ch == '"':
            in_quote = not in_quote
        elif not in_quote:
            kept.append(ch)
    return "".join(kept)


class CronValueTests(ScheduleCase):
    def test_cron_values_github_cannot_run_are_refused_and_nothing_is_written(self):
        """Adversarial where: a cron expression made of five well-shaped tokens
        whose values lie outside the field's range (minute 60, hour 24, day 32,
        month 13, weekday 9) is rendered, so the workflow parses on disk and
        GitHub never runs it; a line break between fields is also accepted
        although only five space-separated fields are allowed."""
        before = snapshot(self.project)
        refused = {
            "minute 60": "60 6 * * *",
            "minute 99": "99 99 * * *",
            "hour 24": "0 24 * * *",
            "day of month 32": "0 6 32 * *",
            "month 13": "0 6 1 13 *",
            "weekday 9": "0 6 * * 9",
            "descending range past the limit": "0-60 6 * * *",
            "step past the limit": "*/99 6 * * *",
            "line break between fields": "0 6 * *\n*",
        }
        for label, expression in refused.items():
            with self.subTest(label):
                self.clear_github()
                (self.project / ".gitattributes").unlink(missing_ok=True)
                code, _out, err = self.schedule("--github", "--cron", expression)
                self.assertEqual(code, 1, f"{expression!r} was accepted")
                self.assertTrue(err.strip())
                self.assertEqual(snapshot(self.project), before)

    def test_an_accepted_cron_value_stays_on_one_line_of_the_workflow(self):
        """Adversarial where: hostile text in `--cron` (quotes, a comment, a
        newline plus a new YAML key, template placeholders, shell
        substitution, Unicode line separators) escapes the quoted scalar and
        adds a key or a step to the workflow."""
        baseline = self.render()
        self.clear_github()
        hostile = [
            '0 6 * * *"',
            "0 6 * * *'",
            "0 6 * * * # comment",
            "0 6 * * *\ninjected: true",
            "0 6 * * *\n  - run: echo pwned",
            "{{id}} 6 * * *",
            "$(id) 6 * * *",
            "${{ secrets.ANTHROPIC_API_KEY }} 6 * * *",
            "0 6 * * *\\",
            "0 6 * *\u2028*",
            "0 6 * *\u0085*",
            "0\u00a06 * * *",
        ]
        for expression in hostile:
            with self.subTest(expression=expression):
                self.clear_github()
                code, _out, _err = self.schedule("--github", "--cron", expression)
                self.assertIn(code, (0, 1))
                workflow = self.project / WORKFLOW_PATH
                if code == 1:
                    self.assertFalse(workflow.exists())
                    continue
                text = workflow.read_bytes().decode("utf-8")
                self.assertEqual(len(text.split("\n")), len(baseline.split("\n")))
                crons = re.findall(r"^\s*-\s*cron:\s*(.*)$", text, re.M)
                self.assertEqual(len(crons), 1)
                scalar = crons[0]
                self.assertRegex(scalar, r'^"[^"\\\n]*"$')
                self.assertEqual(len(scalar.strip('"').split(" ")), 5, scalar)


class LocalLineQuotingTests(ScheduleCase):
    def project_named(self, name):
        """A copy of the scratch vault under a project folder called `name`,
        made current through CLAUDE_PROJECT_DIR."""
        base = self.elsewhere / name
        shutil.copytree(self.root, base / ".compass")
        os.environ["CLAUDE_PROJECT_DIR"] = str(base)
        return base.resolve()

    def local(self, platform, executable=None):
        patches = [mock.patch.object(sys, "platform", platform)]
        if executable is not None:
            patches.append(mock.patch.object(sys, "executable", executable))
        with patches[0]:
            if executable is None:
                return self.loop("schedule", TARGET, "--local")
            with patches[1]:
                return self.loop("schedule", TARGET, "--local")

    def test_crontab_line_survives_a_shell_and_cron_for_hostile_project_paths(self):
        """Adversarial where: a project folder holding a space, an apostrophe,
        `$`, parentheses, an ampersand or a percent sign breaks the crontab
        line: an unquoted path splits, a `$HOME` expands, and a bare `%` is
        turned by cron into a newline that cuts the command in two."""
        names = ["it's a dir", "$HOME and (x) & y", "100% done", "semi;colon `tick`"]
        for name in names:
            with self.subTest(name=name):
                project = self.project_named(name)
                code, out, err = self.local("linux")
                self.assertEqual(code, 0, err)
                lines = [l for l in out.splitlines() if re.match(r"\s*[\d*/,\-]+(\s+[\d*/,\-]+){4}\s+\S", l)]
                self.assertEqual(len(lines), 1, out)
                body = lines[0].split(None, 5)[5]
                self.assertIsNone(re.search(r"(?<!\\)%", body), body)
                tokens = shlex.split(body.replace("\\%", "%"))
                self.assertEqual(tokens[:2], ["cd", project.as_posix()])
                self.assertEqual(tokens[2], "&&")
                self.assertEqual(tokens[3:5], ["mkdir", "-p"])
                log_dir = project / ".compass" / "tmp" / "loops" / TARGET
                self.assertEqual(tokens[5], log_dir.as_posix())
                redirect = tokens.index(">>")
                self.assertEqual(tokens[redirect + 1], (log_dir / "schedule.log").as_posix())
                self.assertEqual(tokens[redirect + 2], "2>&1")
                self.assertEqual(tokens[redirect - 3 : redirect], ["loop", "run", TARGET])

    def test_schtasks_line_keeps_the_task_action_in_one_cmd_command(self):
        """Adversarial where: the `/TR` action reaches `cmd.exe` with a path
        that holds `&` or `^` outside double quotes (only a space triggers
        quoting), so the task runs a truncated `cd` and treats the rest of the
        path as another command; or the quoting of a spaced path leaves the
        argument split into several arguments for `schtasks`."""
        for name in ("r&d work", "r&d", "a^b", "plain name", "with  two  spaces"):
            with self.subTest(name=name):
                self.project_named(name)
                code, out, err = self.local("win32")
                self.assertEqual(code, 0, err)
                line = next(l for l in out.splitlines() if l.lstrip().startswith("schtasks /Create"))
                args = msvc_argv(line)
                self.assertEqual(args[:2], ["schtasks", "/Create"])
                self.assertEqual(len(args), 10, args)
                self.assertEqual(args[8], "/TR")
                action = args[9]
                bare = outside_quotes(action)
                for allowed in ("&&", ">>", "2>&1"):
                    bare = bare.replace(allowed, "")
                self.assertIsNone(re.search(r"[&|<>^]", bare), f"unquoted metacharacter in {action!r}")

    def test_desktop_prompt_quotes_an_interpreter_path_that_holds_a_space(self):
        """Adversarial where: the Desktop phrasing pastes the interpreter path
        raw, so `C:\\Program Files\\Python 3\\python.exe compass loop run ...`
        names a program called `C:\\Program` when the sentence is run."""
        interpreter = "C:\\Program Files\\Python 3\\python.exe"
        for platform in ("win32", "linux"):
            with self.subTest(platform):
                code, out, err = self.local(platform, executable=interpreter)
                self.assertEqual(code, 0, err)
                prompt = next(l for l in out.splitlines() if l.strip().startswith("prompt:"))
                self.assertRegex(prompt, r"""(["'])[^"']*Program Files[^"']*\1""", prompt)


class GitattributesBytesTests(ScheduleCase):
    def test_existing_gitattributes_bytes_survive_and_the_line_is_added_once(self):
        """Adversarial where: a CRLF file gets an LF-terminated line (mixed
        endings), a file with no final newline gets the union line glued to its
        last line, a commented-out copy of the line counts as present, an
        existing line is rewritten or reordered, or a second run appends again."""
        union = UNION_LINE.encode()
        cases = {
            "crlf with final newline": (b"*.png binary\r\n*.md text\r\n", b"\r\n"),
            "crlf without final newline": (b"*.png binary\r\n*.md text", b"\r\n"),
            "lf without final newline": (b"*.png binary\n*.md text", b"\n"),
            "empty file": (b"", b"\n"),
            "single line without newline": (b"*.md text", b"\n"),
            "only a comment naming the line": (b"# " + union + b"\n", b"\n"),
            "same text inside a longer line": (b"# keep " + union + b" for ledgers\n", b"\n"),
            "different driver on the same path": (b".compass/loops/*/ledger.jsonl merge=binary\n", b"\n"),
            "blank lines and tabs": (b"\n\n*.sh\ttext eol=lf\n\n", b"\n"),
        }
        path = self.project / ".gitattributes"
        for label, (original, eol) in cases.items():
            with self.subTest(label):
                self.clear_github()
                path.write_bytes(original)
                code, _out, err = self.schedule("--github")
                self.assertEqual(code, 0, err)
                result = path.read_bytes()
                self.assertTrue(result.startswith(original), result)
                self.assertTrue(result.endswith(union + eol), result)
                added = result[len(original):]
                self.assertEqual(added.count(union), 1, added)
                self.assertEqual(result.count(b"\n"), original.count(b"\n") + (0 if original.endswith(b"\n") or not original else 1) + 1 - (0 if original else 0), result)
                code, _out, err = self.schedule("--github")
                self.assertEqual(code, 0, err)
                self.assertEqual(path.read_bytes(), result)

    def test_a_present_line_in_any_spelling_leaves_the_file_byte_identical(self):
        """Adversarial where: the line with a trailing carriage return, trailing
        blanks or leading blanks is not recognised and a duplicate is appended
        on every `schedule` call."""
        union = UNION_LINE.encode()
        variants = {
            "crlf": b"*.md text\r\n" + union + b"\r\n",
            "trailing blanks": union + b"   \n*.md text\n",
            "leading blanks": b"  " + union + b"\n",
            "last line without newline": b"*.md text\n" + union,
        }
        path = self.project / ".gitattributes"
        for label, original in variants.items():
            with self.subTest(label):
                self.clear_github()
                path.write_bytes(original)
                code, _out, err = self.schedule("--github")
                self.assertEqual(code, 0, err)
                self.assertEqual(path.read_bytes(), original)


class ReconcileDamagedInputTests(ReconcileCase):
    def branch(self, run_id):
        return f"compass-loop/{RECONCILED}/{run_id}"

    def pr(self, number, run_id, state, merged_at=None):
        return {"number": number, "headRefName": self.branch(run_id), "state": state, "mergedAt": merged_at}

    def test_unreadable_lists_are_refused_with_a_message_and_no_write(self):
        """Adversarial where: JSON that exhausts the parser's recursion limit
        (a RecursionError is not a ValueError and escapes as a traceback),
        bytes that are not UTF-8, the non-standard `NaN` literal, a truncated
        list, and a top-level `null` or string, each leave the ledger touched
        or the command dead without a message."""
        before = snapshot(self.folder)
        inputs = {
            "deeply nested arrays": b"[" * 200000 + b"]" * 200000,
            "latin-1 bytes": b'[{"headRefName": "caf\xe9"}]',
            "NaN as number": b'[{"number": NaN, "headRefName": "x", "state": "OPEN"}]',
            "truncated list": b'[{"number": 1, "headRefName": "x", "state": "OPEN"},',
            "null": b"null",
            "bare string": b'"compass-loop"',
            "bare number": b"7",
            "huge integer": b'[{"number": ' + b"9" * 6000 + b', "headRefName": "x", "state": "OPEN"}]',
        }
        for label, content in inputs.items():
            with self.subTest(label):
                code, _out, err = self.reconcile(self.write_prs(content))
                self.assertEqual(code, 1)
                self.assertTrue(err.strip())
                self.assertEqual(snapshot(self.folder), before)

    def test_runs_without_a_verified_increment_and_open_pull_requests_get_no_review(self):
        """Adversarial where: a merged pull request for a run that ended
        `crashed`, `halted` or without reaching verification is accepted, an
        open pull request next to a closed one on the same branch is rejected
        early, or a run with a pull request but no ledger row is invented."""
        for run_id, outcome in (("RUN-20261001T000000000001Z", "crashed"),
                                ("RUN-20261001T000000000002Z", "halted"),
                                ("RUN-20261001T000000000003Z", "throttled")):
            self.add_run(self.folder, run_id, outcome)
        before = snapshot(self.folder)
        payload = [
            self.pr(51, "RUN-20261001T000000000001Z", "MERGED", "2026-10-01T01:00:00Z"),
            self.pr(52, "RUN-20261001T000000000002Z", "CLOSED"),
            self.pr(53, "RUN-20261001T000000000003Z", "MERGED", "2026-10-01T01:00:00Z"),
            self.pr(54, "RUN-20261001T000000000004Z", "MERGED", "2026-10-01T01:00:00Z"),
            self.pr(55, RUN_OPEN, "CLOSED"),
            self.pr(56, RUN_OPEN, "OPEN"),
        ]
        code, out, err = self.reconcile(self.write_prs(payload))
        self.assertEqual(code, 0, err)
        self.assertEqual(snapshot(self.folder), before)
        for number in (51, 52, 53, 54, 55, 56):
            self.assertRegex(out, rf"skip #{number}\b")

    def test_a_second_reconcile_over_the_same_list_changes_nothing(self):
        """Adversarial where: the workflow runs reconcile every day over a list
        that still holds last week's merged pull requests; a second pass appends
        the same review rows or the same guidance line again."""
        code, _out, err = self.reconcile()
        self.assertEqual(code, 0, err)
        first = snapshot(self.folder)
        self.assertEqual(len(self.reviews()), 2)
        code, out, err = self.reconcile()
        self.assertEqual(code, 0, err)
        self.assertEqual(snapshot(self.folder), first)
        self.assertIn("already reviewed", out)

    def test_reconcile_appends_after_a_damaged_ledger_without_touching_its_bytes(self):
        """Adversarial where: the ledger ends without a newline (the review row
        glues onto the last run row and both are lost), holds a corrupt line
        in the middle (rewritten away) or CRLF endings, or `feedback.md` is
        missing (the reject path crashes instead of recreating it)."""
        ledger = self.folder / "ledger.jsonl"
        original = ledger.read_bytes().rstrip(b"\n").replace(b"\n", b"\r\n")
        damaged = original.split(b"\r\n")
        damaged.insert(1, b"{this line is not json")
        content = b"\r\n".join(damaged)
        ledger.write_bytes(content)
        (self.folder / "feedback.md").unlink()
        code, _out, err = self.reconcile()
        self.assertEqual(code, 0, err)
        after = ledger.read_bytes()
        self.assertTrue(after.startswith(content), after)
        rows = self.ledger(self.folder)
        self.assertEqual([r["run_id"] for r in rows if r.get("type") == "review"].count(RUN_MERGED), 1)
        self.assertEqual([r["run_id"] for r in rows if r.get("type") == "review"].count(RUN_CLOSED), 1)
        self.assertEqual(len([r for r in rows if r.get("type") == "run"]), 3)
        self.assertIn(CLOSED_GUIDANCE, (self.folder / "feedback.md").read_text(encoding="utf-8"))

    def test_a_list_of_tens_of_thousands_is_decided_correctly(self):
        """Adversarial where: per-entry rescans of the ledger or of the list
        make a repository with a long pull request history (`--limit 200`
        grows) quadratic, or the one real decision is lost among the skipped
        entries."""
        unknown = [self.pr(1000 + i, f"RUN-2025{i:08d}Z", "MERGED", "2026-01-01T00:00:00Z") for i in range(30000)]
        other = [
            {"number": 90000 + i, "headRefName": f"feature/{i}", "state": "OPEN", "mergedAt": None}
            for i in range(20000)
        ]
        payload = unknown + other + [
            self.pr(99001, RUN_MERGED, "MERGED", "2026-10-16T21:43:26Z"),
            self.pr(99002, RUN_CLOSED, "CLOSED"),
        ]
        started = time.monotonic()
        code, out, err = self.reconcile(self.write_prs(payload))
        elapsed = time.monotonic() - started
        self.assertEqual(code, 0, err)
        self.assertLess(elapsed, 60)
        reviews = {r["run_id"]: r["decision"] for r in self.reviews()}
        self.assertEqual(reviews, {RUN_MERGED: "accept", RUN_CLOSED: "reject"})
        self.assertGreaterEqual(len(out.splitlines()), 30000)


class LastRunDamagedLedgerTests(ScheduleCase):
    def last_run(self, content):
        (self.folder / "ledger.jsonl").write_bytes(content)
        return self.schedule_status()

    def schedule_status(self):
        return self.loop("status", TARGET, "--last-run")

    def test_last_run_prints_one_clean_token_pair_or_exits_1_whatever_the_ledger_holds(self):
        """Adversarial where: a run id that survives the one-token check but
        carries padding, a carriage return or a Unicode separator is printed
        verbatim, so `${last%% *}` in the workflow yields an empty or dirty run
        id that is then written to GITHUB_ENV and used as a git branch name; a
        ledger damaged by a torn write or by non-object lines makes the command
        crash or report a row that is not the last whole run row."""
        good = b'{"type": "run", "run_id": "RUN-good", "outcome": "helpful", "item": "a", "cost_usd": 0}\n'

        def run_row(run_id, outcome="helpful"):
            return (json.dumps({"type": "run", "run_id": run_id, "outcome": outcome}) + "\n").encode()

        cases = {
            "leading space in run id": good + run_row(" RUN-x"),
            "trailing space in run id": good + run_row("RUN-x "),
            "carriage return in run id": good + run_row("RUN-x\r"),
            "line separator in run id": good + run_row("RUN-x\u2028"),
            "next line character in run id": good + run_row("RUN-x\u0085"),
            "newline inside run id": good + run_row("RUN-x\nINJECT=1"),
            "padded outcome": good + run_row("RUN-x", " helpful"),
            "outcome with carriage return": good + run_row("RUN-x", "helpful\r"),
        }
        for label, content in cases.items():
            with self.subTest(label):
                code, out, _err = self.last_run(content)
                self.assertIn(code, (0, 1))
                if code == 0:
                    self.assertRegex(out, r"\A\S+ \S+\n\Z", repr(out))
                    self.assertNotEqual(out, "RUN-x helpful\n" if "x" not in label else "")
                else:
                    self.assertEqual(out, "")

    def test_last_run_skips_damaged_lines_and_reports_the_last_whole_run_row(self):
        """Adversarial where: a torn final line, non-object JSON lines, NUL
        bytes, a BOM and CRLF endings after the last run row make the command
        crash, print nothing, or report an earlier row than the last whole one."""
        old = b'{"type": "run", "run_id": "RUN-old", "outcome": "neutral"}\n'
        new = b'{"type": "run", "run_id": "RUN-new", "outcome": "harmful"}\n'
        cases = {
            "torn final line": (old + new + b'{"type": "run", "run_id": "RUN-torn", "outc', "RUN-new harmful\n"),
            "non-object lines after the row": (old + new + b'[1]\n"x"\nnull\n5\n', "RUN-new harmful\n"),
            "NUL and binary garbage": (old + b"\x00\x00\xff\xfe\n" + new + b"\x00\n", "RUN-new harmful\n"),
            "BOM and CRLF": (b"\xef\xbb\xbf" + old.replace(b"\n", b"\r\n") + new.replace(b"\n", b"\r\n"), "RUN-new harmful\n"),
            "review row last": (old + new + b'{"type": "review", "run_id": "RUN-new", "decision": "accept"}\n', "RUN-new harmful\n"),
            "no trailing newline": (old + new.rstrip(b"\n"), "RUN-new harmful\n"),
        }
        for label, (content, expected) in cases.items():
            with self.subTest(label):
                code, out, err = self.last_run(content)
                self.assertEqual(code, 0, err)
                self.assertEqual(out, expected)
        for label, content in {
            "only garbage": b"\x00\xff\n[1]\nnot json\n",
            "only review rows": b'{"type": "review", "run_id": "RUN-x", "decision": "accept"}\n',
            "run row without outcome": b'{"type": "run", "run_id": "RUN-x"}\n',
            "run row with a numeric run id": b'{"type": "run", "run_id": 7, "outcome": "helpful"}\n',
            "run row with a null run id": b'{"type": "run", "run_id": null, "outcome": "helpful"}\n',
        }.items():
            with self.subTest(label):
                code, out, err = self.last_run(content)
                self.assertEqual(code, 1)
                self.assertEqual(out, "")
                self.assertTrue(err.strip())


@unittest.skipUnless(BASH and GIT and PYTHON, "needs bash, git and python on PATH")
class WorkflowShellTests(ScheduleCase):
    """The rendered workflow's own `run:` scripts, executed with bash in a
    real clone whose `origin` is a bare repository, with `gh` replaced by a
    script that logs its arguments."""

    RUN = "RUN-20261018T060000123456Z"

    def setUp(self):
        super().setUp()
        self.workflow = self.render()
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        self.base = base
        self.origin = base / "origin.git"
        self.work = base / "work"
        self.other = base / "other"
        self.temp = base / "runner-temp"
        self.stubs = base / "stubs"
        for folder in (self.temp, self.stubs):
            folder.mkdir()
        self.gh_log = base / "gh.log"
        self.github_env = base / "github.env"
        self.github_env.write_bytes(b"")
        self.git(base, "init", "--bare", "-b", "main", str(self.origin))
        self.git(base, "clone", str(self.origin), str(self.work))
        self.git(self.work, "config", "user.name", "seed")
        self.git(self.work, "config", "user.email", "seed@example.invalid")
        loop = self.work / ".compass" / "loops" / self.folder.name
        loop.mkdir(parents=True)
        self.loop_dir = loop
        (loop / "state.json").write_text('{"state": "idle"}\n', encoding="utf-8", newline="\n")
        (loop / "feedback.md").write_text("# Feedback\n", encoding="utf-8", newline="\n")
        (loop / "ledger.jsonl").write_text('{"seed": 1}\n', encoding="utf-8", newline="\n")
        (self.work / ".gitattributes").write_text(UNION_LINE + "\n", encoding="utf-8", newline="\n")
        (self.work / ".compass" / "meta").mkdir(parents=True, exist_ok=True)
        (self.work / ".compass" / "meta" / "plugin.yaml").write_text("plugin:\n  version: 1\n", encoding="utf-8", newline="\n")
        src = self.work / "src"
        src.mkdir()
        for name in ("a b.py", "gone.txt", "keep.txt"):
            (src / name).write_text("original\n", encoding="utf-8", newline="\n")
        self.git(self.work, "add", "-A")
        self.git(self.work, "commit", "-m", "seed")
        self.git(self.work, "push", "origin", "main")
        self.git(base, "clone", str(self.origin), str(self.other))
        self.git(self.other, "config", "user.name", "other")
        self.git(self.other, "config", "user.email", "other@example.invalid")
        gh = self.stubs / "gh"
        gh.write_bytes(
            b'#!/bin/bash\nprintf "%s\\n" "$*" >> "$GH_LOG"\n'
            b'if [ "$1 $2" = "pr create" ] && [ -n "$GH_FAIL_PR" ]; then exit 1; fi\nexit 0\n'
        )
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)

    # -- helpers ---------------------------------------------------------

    def git(self, cwd, *args):
        done = subprocess.run(
            [GIT, *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", timeout=120
        )
        self.assertEqual(done.returncode, 0, f"git {args}: {done.stderr}")
        return done.stdout

    def step_script(self, marker):
        """The `run: |` body of the first step whose block holds `marker`."""
        for _first, _stop, _name, block in split_steps(self.workflow):
            if marker not in block:
                continue
            lines = block.split("\n")
            for index, line in enumerate(lines):
                if re.match(r"^\s*run:\s*\|\s*$", line):
                    body = lines[index + 1 :]
                    indent = len(body[0]) - len(body[0].lstrip())
                    return "\n".join(l[indent:] for l in body) + "\n"
        self.fail(f"no step holds {marker!r}")

    def bash(self, script, **extra):
        path = self.base / "step.sh"
        path.write_bytes(script.encode("utf-8"))
        env = dict(os.environ)
        env.update(
            PATH=f"{self.stubs.as_posix()}{os.pathsep}{env['PATH']}",
            DEFAULT_BRANCH="main",
            RUNNER_TEMP=self.temp.as_posix(),
            GITHUB_ENV=self.github_env.as_posix(),
            GITHUB_WORKSPACE=self.work.as_posix(),
            GITHUB_RUN_ID="9001",
            GH_LOG=self.gh_log.as_posix(),
            GH_TOKEN="x",
            GIT_TERMINAL_PROMPT="0",
        )
        for key in ("RUN_ID", "RUN_OUTCOME", "SINCE"):
            env.pop(key, None)
        env.update(extra)
        done = subprocess.run(
            [BASH, "--noprofile", "--norc", "-e", "-o", "pipefail", path.as_posix()],
            cwd=str(self.work), capture_output=True, env=env, timeout=180,
        )
        return done.returncode, done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace")

    def snapshot_step(self):
        code, out, err = self.bash(self.step_script("git status --porcelain"))
        self.assertEqual(code, 0, err)

    def pr_step(self, **extra):
        env = {"RUN_ID": self.RUN, "RUN_OUTCOME": "helpful"}
        env.update(extra)
        return self.bash(self.step_script("gh pr create"), **env)

    def state_step(self, **extra):
        return self.bash(self.step_script("state.json"), **extra)

    def gh_calls(self):
        return self.gh_log.read_text(encoding="utf-8").splitlines() if self.gh_log.exists() else []

    def origin_branches(self):
        return self.git(self.origin, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()

    def write(self, relative, text):
        path = self.work / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))

    def touch_state(self):
        (self.loop_dir / "state.json").write_text('{"state": "verifying"}\n', encoding="utf-8", newline="\n")
        with open(self.loop_dir / "ledger.jsonl", "ab") as handle:
            handle.write(b'{"local": 1}\n')

    # -- the increment pull request -----------------------------------------

    def test_increment_branch_holds_exactly_the_paths_the_iteration_changed(self):
        """Adversarial where: the pull request step stages a path with a space,
        an apostrophe, a non-ASCII letter or a leading dash wrongly, drops a
        deletion, sweeps in `.compass/`, `.claude/` or a file that was already
        dirty before the iteration, or leaves the checkout off the default
        branch for the state commit."""
        self.write("README-before.txt", "dirty before the iteration\n")
        (self.work / ".claude" / "cli").mkdir(parents=True)
        self.snapshot_step()
        self.write("src/a b.py", "changed\n")
        self.write("src/new'q \u00e9.py", "new\n")
        self.write("-dash.txt", "dash\n")
        self.write("deep/er/#hash.txt", "hash\n")
        (self.work / "src" / "gone.txt").unlink()
        self.write(".claude/cli/compass", "installed\n")
        self.touch_state()
        code, out, err = self.pr_step()
        self.assertEqual(code, 0, err)
        branch = f"compass-loop/{TARGET}/{self.RUN}"
        self.assertIn(branch, self.origin_branches())
        changed = self.git(self.origin, "diff", "--name-status", "-z", "main", branch).split("\0")
        pairs = sorted(zip(changed[0::2], changed[1::2]))
        self.assertEqual(
            pairs,
            sorted([("M", "src/a b.py"), ("A", "src/new'q \u00e9.py"), ("A", "-dash.txt"),
                    ("A", "deep/er/#hash.txt"), ("D", "src/gone.txt")]),
        )
        self.assertEqual(self.git(self.work, "rev-parse", "--abbrev-ref", "HEAD").strip(), "main")
        creates = [c for c in self.gh_calls() if c.startswith("pr create")]
        self.assertEqual(len(creates), 1, self.gh_calls())
        self.assertIn(f"--head {branch}", creates[0])
        self.assertIn("--base main", creates[0])
        status = self.git(self.work, "status", "--porcelain")
        self.assertIn("state.json", status)

    def test_no_increment_opens_no_branch_and_no_pull_request(self):
        """Adversarial where: an iteration that ended `crashed`, `halted` or
        `throttled`, left no ledger row, or changed only `.compass/`, still
        pushes an empty branch or calls `gh pr create`, or fails the job."""
        cases = {
            "crashed": ({"RUN_OUTCOME": "crashed"}, True),
            "halted": ({"RUN_OUTCOME": "halted"}, True),
            "throttled": ({"RUN_OUTCOME": "throttled"}, True),
            "no outcome at all": ({"RUN_OUTCOME": ""}, True),
            "helpful but only .compass changed": ({}, False),
        }
        for label, (extra, edits) in cases.items():
            with self.subTest(label):
                self.snapshot_step()
                self.touch_state()
                if edits:
                    self.write("src/a b.py", "changed\n")
                code, out, err = self.pr_step(**extra)
                self.assertEqual(code, 0, err)
                self.assertEqual(self.origin_branches(), ["main"])
                self.assertEqual([c for c in self.gh_calls() if c.startswith("pr create")], [])
                self.git(self.work, "checkout", "--", ".")
                self.git(self.work, "clean", "-fdq", "--", "src")

    def test_a_failed_pull_request_still_lets_the_state_commit_reach_the_default_branch(self):
        """Adversarial where: `gh pr create` fails (Actions may not create pull
        requests) after the branch was pushed and the checkout sits on the run
        branch; the state step, which runs even after a failure, then commits
        the state onto the run branch or dies on the dirty tree."""
        self.snapshot_step()
        self.write("src/a b.py", "changed\n")
        self.touch_state()
        code, _out, _err = self.pr_step(GH_FAIL_PR="1")
        self.assertNotEqual(code, 0)
        code, _out, err = self.state_step(RUN_ID=self.RUN)
        self.assertEqual(code, 0, err)
        self.git(self.other, "pull", "origin", "main")
        ledger = (self.other / ".compass" / "loops" / self.folder.name / "ledger.jsonl").read_text(encoding="utf-8")
        self.assertIn('{"local": 1}', ledger)
        self.assertFalse((self.other / "src" / "a b.py").read_text(encoding="utf-8").startswith("changed"))

    # -- the state commit ---------------------------------------------------

    def test_state_commit_rebases_over_a_push_and_unions_the_ledger(self):
        """Adversarial where: a human merged a pull request (or another loop
        pushed) during the iteration, so the default branch moved and the
        ledger gained a row at the same place; the push is refused, the
        rebase stops on a conflict, or a ledger row of either side is lost."""
        self.git(self.work, "config", "user.name", "compass-loop")
        self.git(self.work, "config", "user.email", "c@example.invalid")
        other_loop = self.other / ".compass" / "loops" / self.folder.name
        with open(other_loop / "ledger.jsonl", "ab") as handle:
            handle.write(b'{"remote": 1}\n')
        (self.other / "src" / "keep.txt").write_text("merged by a human\n", encoding="utf-8", newline="\n")
        self.git(self.other, "commit", "-am", "human merge")
        self.git(self.other, "push", "origin", "main")
        self.touch_state()
        self.write(".compass/meta/plugin.yaml", "plugin:\n  version: 2\n")
        code, out, err = self.state_step(RUN_ID=self.RUN)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.origin_branches(), ["main"])
        self.git(self.other, "pull", "origin", "main")
        ledger = (other_loop / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(sorted(ledger), sorted(['{"seed": 1}', '{"remote": 1}', '{"local": 1}']))
        self.assertEqual((self.other / "src" / "keep.txt").read_text(encoding="utf-8"), "merged by a human\n")
        self.assertIn("verifying", (other_loop / "state.json").read_text(encoding="utf-8"))
        self.assertFalse((self.work / ".git" / "rebase-merge").exists())
        self.assertIn("version: 2", (self.work / ".compass" / "meta" / "plugin.yaml").read_text(encoding="utf-8"))

    def test_protected_default_branch_keeps_the_state_on_a_fallback_branch_and_fails_red(self):
        """Adversarial where: a branch rule refuses the push of the state
        commit, so the state is lost with the runner, the job ends green, or
        the checkout is left in the middle of a rebase."""
        hook = self.origin / "hooks" / "pre-receive"
        hook.write_bytes(
            b'#!/bin/sh\nwhile read old new ref; do\n'
            b'  if [ "$ref" = refs/heads/main ]; then echo "protected branch" >&2; exit 1; fi\n'
            b"done\n"
        )
        hook.chmod(hook.stat().st_mode | stat.S_IEXEC)
        self.git(self.other, "pull", "origin", "main")
        (self.other / "src" / "keep.txt").write_text("moved on\n", encoding="utf-8", newline="\n")
        self.git(self.other, "commit", "-am", "moved on")
        hook.rename(hook.with_name("pre-receive.off"))
        self.git(self.other, "push", "origin", "main")
        hook.with_name("pre-receive.off").rename(hook)
        self.touch_state()
        code, _out, err = self.state_step(RUN_ID=self.RUN)
        self.assertNotEqual(code, 0)
        self.assertIn("::error::", _out + err)
        fallback = f"compass-loop/{TARGET}/state-{self.RUN}"
        self.assertIn(fallback, self.origin_branches())
        shown = self.git(self.origin, "show", f"{fallback}:.compass/loops/{self.folder.name}/ledger.jsonl")
        self.assertIn('{"local": 1}', shown)
        self.assertFalse((self.work / ".git" / "rebase-merge").exists())

    def test_state_step_without_a_new_run_or_without_changes_is_quiet_and_green(self):
        """Adversarial where: an iteration that left no run row (RUN_ID unset)
        or changed no state file makes `git commit` fail on an empty commit, or
        names the branch `state-` with an empty suffix; a loop folder without a
        `feedback.md` makes `git add` die on its pathspec."""
        code, out, err = self.state_step()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.git(self.work, "rev-list", "--count", "HEAD").strip(), "1")
        self.touch_state()
        code, out, err = self.state_step()
        self.assertEqual(code, 0, err)
        self.assertIn("iteration without a run", self.git(self.work, "log", "-1", "--format=%s"))
        (self.loop_dir / "feedback.md").unlink()
        self.git(self.work, "commit", "-am", "feedback.md removed by hand")
        self.git(self.work, "push", "origin", "main")
        with open(self.loop_dir / "ledger.jsonl", "ab") as handle:
            handle.write(b'{"after": 1}\n')
        code, out, err = self.state_step(RUN_ID=self.RUN)
        self.assertEqual(code, 0, err)

    # -- reading the outcome ---------------------------------------------------

    def test_outcome_step_adopts_only_a_row_newer_than_the_snapshot(self):
        """Adversarial where: the step adopts the previous day's last row when
        the new iteration wrote none (so yesterday's increment is proposed
        again), compares ids in a locale that sorts differently, or fails the
        job when `status --last-run` exits 1."""
        stub = self.work / ".claude" / "cli" / "compass"
        stub.parent.mkdir(parents=True)
        stub.write_text(
            "import os, sys\nline = os.environ.get('STUB_LAST')\n"
            "if line is None:\n    sys.exit(1)\nprint(line)\n",
            encoding="utf-8", newline="\n",
        )
        script = self.step_script("--last-run")
        since = "RUN-20261018T060000"
        cases = {
            "newer row, same second": (f"{since}000001Z helpful", True),
            "newer row, later day": ("RUN-20261019T000000000000Z neutral", True),
            "older row": ("RUN-20261017T235959999999Z helpful", False),
            "row of an earlier second": ("RUN-20261018T055959999999Z harmful", False),
            "no run row at all": (None, False),
        }
        for label, (last, adopted) in cases.items():
            with self.subTest(label):
                self.github_env.write_bytes(b"")
                extra = {"SINCE": since, "LC_ALL": "en_US.UTF-8"}
                if last is not None:
                    extra["STUB_LAST"] = last
                code, out, err = self.bash(script, **extra)
                self.assertEqual(code, 0, err)
                written = self.github_env.read_bytes().decode("utf-8")
                if adopted:
                    run_id, outcome = last.split(" ")
                    self.assertEqual(written.splitlines(), [f"RUN_ID={run_id}", f"RUN_OUTCOME={outcome}"])
                else:
                    self.assertEqual(written, "")


if __name__ == "__main__":
    unittest.main()
