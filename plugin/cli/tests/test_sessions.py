"""Tests for `compass sessions list | show | record` (module `commands.sessions`).

Every test calls `commands.sessions.run(args)`; `args[0]` is the subcommand. The
command returns an int exit code and never exits 2: a bad argument, an unknown
subcommand and a missing file all return 1 with a message on stderr.

Adversarial themes: the feature-session line (10 commits qualifies, 9 does not,
subagent commits count, a worker entrypoint never qualifies), what `list`
treats as a session (only top-level `<id>.jsonl` of this project's key), the
per-session window behind headroom, the 10-minute active line, rendering
transcripts whose lines or fields are malformed, resolving a kept clone under
the central folder, and a vault record that never holds transcript or lesson
text.

Project root: the parent of the vault root, i.e. `CLAUDE_PROJECT_DIR` here.
Transcripts are read from `sessionslib.transcripts_dir(project_root)` and
opened read-only.

PINNED INTERFACE

`list [--json] [--min-commits N] [--all]`
    Rows are the top-level `*.jsonl` files of the transcript folder; the
    session id is the file stem. Subagent files under `<id>/subagents/` are not
    sessions. A session is a feature session when its entrypoint is `cli` and
    its commit count (`sessionslib.commit_count`, subagents included) is at
    least N (default 10, N >= 0). The default view shows only feature
    sessions; `--all` shows every session, qualifying or not. An `active`
    session is shown like any other and marked. Rows are ordered by last
    modified, newest first. A missing transcript folder is an empty list.
    `--min-commits` below 0 or not an integer, an unknown option and an
    unknown subcommand return 1.

    Table (no `--json`): a header line, then one row per session, columns
    separated by whitespace, in this order:

        SESSION ENTRYPOINT COMMITS PLANS TASKS MODEL USED HEADROOM MODIFIED ACTIVE FEATURE

    A value that is absent (no entrypoint, no plan ids, no model, no usage) is
    `-`. PLANS and TASKS are the ids joined by `,` without spaces
    (`PLAN-020,PLAN-021`). USED and HEADROOM are integers in tokens. MODIFIED is
    an ISO-8601 timestamp with a UTC offset and no spaces. ACTIVE and FEATURE
    are `yes` or `no`.

    `--json`: stdout is one JSON list of objects (`[]` when empty), each with
    exactly these keys:

        session_id  str         file stem
        entrypoint  str|null
        commits     int
        plans       list[str]   `sessionslib.plan_ids`
        tasks       list[str]   `sessionslib.task_ids`
        model       str|null    `sessionslib.model_id`
        used        int|null    `sessionslib.used_tokens`
        window      int|null    `context_check.window_for(model)`; null when model is null
        headroom    int|null    window - used; null when model or used is null
        modified    str         ISO-8601 with UTC offset
        active      bool        `sessionslib.is_active`
        feature     bool        qualifies under the line in force

`show <path | run-id/session-id>`
    An argument naming an existing file is read as a transcript, Claude Code
    jsonl or a clone's stream-json. Otherwise `<run-id>/<session-id>` resolves
    to `sessionslib.run_dir(project_root, run_id) / "<session-id>.jsonl"`.
    Output is plain text, in transcript order, from assistant records only:
    each text block verbatim, an assistant message whose content is a plain
    string verbatim, and each tool call as ONE line

        [tool] <Name> <input as compact one-line JSON>

    User records, tool results, system and result records print nothing. Lines
    that are not JSON objects are skipped; fields of the wrong shape print
    nothing and never raise. No argument, a missing file, a directory, and an
    unresolvable `run-id/session-id` return 1 with stderr text and empty stdout.

`record <run-id> [--written NAME...] [--merged NAME...] [--rejected N]`
    `--written` and `--merged` take zero or more lesson names (default none);
    `--rejected` takes an integer >= 0 (default 0). Appends exactly one
    JSON line to `<vault>/meta/clone-log.jsonl` with exactly these keys:

        event "run"  run_id  at (ISO-8601 UTC)  written (list)  merged (list)
        written_count  merged_count  rejected

    The row holds names and counts; nothing is read from the run folder. A
    missing `run-id`, a negative or non-integer `--rejected` and an unknown
    option return 1 and append nothing.

Every test isolates CLAUDE_CONFIG_DIR, COMPASS_HOME and CLAUDE_PROJECT_DIR in
temp dirs, so the real ~/.claude and ~/.compass are never read.
"""

import hashlib
import importlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sessionslib  # noqa: E402

STANDARD_MODEL = "claude-sonnet-4-6"
EXTENDED_MODEL = "claude-opus-4-8"
TABLE_HEADER = ["SESSION", "ENTRYPOINT", "COMMITS", "PLANS", "TASKS", "MODEL", "USED",
                "HEADROOM", "MODIFIED", "ACTIVE", "FEATURE"]
JSON_KEYS = {"session_id", "entrypoint", "commits", "plans", "tasks", "model", "used",
             "window", "headroom", "modified", "active", "feature"}
RUN_ROW_KEYS = {"event", "run_id", "at", "written", "merged", "written_count",
                "merged_count", "rejected"}


def run_sessions(args):
    """`(exit_code, stdout, stderr)`. Imports lazily so each test fails for its
    own reason; a SystemExit is captured as its code so an argparse exit 2
    shows up as 2."""
    module = importlib.import_module("commands.sessions")
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = module.run(list(args))
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    return (0 if code is None else code), out.getvalue(), err.getvalue()


def bash_line(command, sidechain=False):
    block = {"type": "tool_use", "id": "toolu_x", "name": "Bash", "input": {"command": command}}
    return {"type": "assistant", "isSidechain": sidechain,
            "message": {"role": "assistant", "content": [block]}}


def usage_line(used):
    return {"type": "assistant", "isSidechain": False,
            "message": {"role": "assistant", "content": [],
                        "usage": {"input_tokens": used, "cache_creation_input_tokens": 0,
                                  "cache_read_input_tokens": 0, "output_tokens": 5}}}


def model_line(model_id):
    return {"type": "attachment", "attachment": {"type": "model", "identity": {"modelId": model_id}}}


def assistant(*blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


def text_block(text):
    return {"type": "text", "text": text}


def tool_block(name, **tool_input):
    return {"type": "tool_use", "id": "toolu_1", "name": name, "input": tool_input}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest(), os.stat(path).st_mtime_ns


class SessionsCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env_backup = dict(os.environ)
        for name in ("COMPASS_CONTEXT_WINDOW", "CLAUDE_CODE_DISABLE_1M_CONTEXT",
                     "CLAUDE_CODE_MAX_CONTEXT_TOKENS"):
            os.environ.pop(name, None)
        self.project = self.tmp / "my.proj_x"
        (self.project / ".compass" / "meta").mkdir(parents=True)
        self.config = self.tmp / "cfg"
        self.home = self.tmp / "chome"
        self.config.mkdir()
        self.home.mkdir()
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.config)
        os.environ["COMPASS_HOME"] = str(self.home)
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(self.tmp / "userhome")
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self.env_backup)))
        old_cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, old_cwd)
        self.folder = sessionslib.transcripts_dir(self.project)
        self.folder.mkdir(parents=True)
        self.log = self.project / ".compass" / "meta" / "clone-log.jsonl"

    def make_session(self, sid, entry="cli", commits=0, sub_commits=0, model=STANDARD_MODEL,
                     used=None, text="hello", age=7200, folder=None, extra=()):
        """Write `<sid>.jsonl` with the given commit count, optional subagent
        commits, model and usage; its mtime is `age` seconds ago."""
        folder = folder or self.folder
        first = {"type": "user", "message": {"role": "user", "content": text}}
        if entry:
            first["entrypoint"] = entry
        records = [first]
        if model:
            records.append(model_line(model))
        records.extend(bash_line("git commit -m 'c%d'" % i) for i in range(commits))
        records.extend(extra)
        if used is not None:
            records.append(usage_line(used))
        path = folder / f"{sid}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\n".join(json.dumps(r).encode("utf-8") for r in records) + b"\n")
        if sub_commits:
            side = folder / sid / "subagents" / "agent-a1.jsonl"
            side.parent.mkdir(parents=True, exist_ok=True)
            side.write_bytes(b"\n".join(
                json.dumps(bash_line("git commit -m s%d" % i, sidechain=True)).encode("utf-8")
                for i in range(sub_commits)) + b"\n")
        stamp = time.time() - age
        os.utime(path, (stamp, stamp))
        return path

    def list_json(self, *flags):
        code, out, err = run_sessions(["list", "--json", *flags])
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def ids(self, *flags):
        return [row["session_id"] for row in self.list_json(*flags)]

    def write_raw(self, path, *lines):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\n".join(lines) + b"\n")
        return path


class ListSelectionTests(SessionsCase):
    def test_default_view_is_cli_sessions_at_or_above_ten_commits(self):
        """Adversarial where: the line is `> 10` instead of `>= 10`, subagent
        commits are ignored (6 main + 4 side = 10 must qualify), a worker
        entrypoint or a missing entrypoint slips in, a stray bad line hides a
        qualifying session, or files that are not this project's top-level
        sessions are listed."""
        self.make_session("c10", commits=10)
        self.make_session("c09", commits=9)
        self.make_session("split", commits=6, sub_commits=4)
        self.make_session("split-short", commits=6, sub_commits=3)
        self.make_session("worker", entry="sdk-cli", commits=12)
        self.make_session("noentry", entry=None, commits=12)
        self.make_session("noisy", commits=10, extra=())
        noisy = self.folder / "noisy.jsonl"
        body = noisy.read_bytes().split(b"\n")
        body.insert(3, b"{not json")
        noisy.write_bytes(b"\n".join(body))
        self.make_session("recent", commits=11, age=30)
        # decoys: another project's key, a text file, a side folder transcript
        other = sessionslib.transcripts_dir(self.tmp / "other-proj")
        self.make_session("elsewhere", commits=20, folder=other)
        (self.folder / "notes.txt").write_text("x", encoding="utf-8")
        shown = self.ids()
        self.assertEqual(sorted(shown), sorted(["c10", "split", "noisy", "recent"]))
        self.assertFalse(any(s.startswith("agent-") for s in shown))

    def test_min_commits_moves_the_line_to_exactly_n(self):
        """Adversarial where: `--min-commits` is ignored, off by one at the
        boundary, or 0 is treated as unset and falls back to 10."""
        self.make_session("c05", commits=5)
        self.make_session("c06", commits=6)
        self.make_session("c07", commits=7)
        self.make_session("c10", commits=10)
        self.make_session("zero", commits=0)
        self.make_session("worker", entry="sdk-cli", commits=30)
        rows = {
            "7": ["c07", "c10"],
            "11": [],
            "0": ["c05", "c06", "c07", "c10", "zero"],
        }
        for value, expected in rows.items():
            with self.subTest(min_commits=value):
                self.assertEqual(sorted(self.ids("--min-commits", value)), expected)

    def test_all_lists_every_session_and_flags_the_ones_below_the_line(self):
        """Adversarial where: `--all` drops the `feature` flag (everything
        reads true or false), or empty, all-garbage and metadata-free files
        crash the listing instead of appearing with zero commits."""
        self.make_session("big", commits=10)
        self.make_session("small", commits=3)
        self.make_session("worker", entry="sdk-cli", commits=15)
        (self.folder / "empty.jsonl").write_bytes(b"")
        self.write_raw(self.folder / "garbage.jsonl", b"{{{", b"\xff\xfe\x00", b"[1,2]")
        rows = {r["session_id"]: r for r in self.list_json("--all")}
        self.assertEqual(sorted(rows), ["big", "empty", "garbage", "small", "worker"])
        self.assertEqual({k: v["feature"] for k, v in rows.items()},
                         {"big": True, "small": False, "worker": False, "empty": False, "garbage": False})
        self.assertEqual((rows["empty"]["commits"], rows["empty"]["entrypoint"], rows["empty"]["used"]),
                         (0, None, None))
        self.assertEqual(rows["garbage"]["commits"], 0)

    def test_all_with_min_commits_applies_the_line_to_the_feature_flag(self):
        """Adversarial where: the feature flag is computed with the default
        10 even when `--min-commits` moved the line."""
        self.make_session("c07", commits=7)
        self.make_session("c06", commits=6)
        rows = {r["session_id"]: r["feature"] for r in self.list_json("--all", "--min-commits", "7")}
        self.assertEqual(rows, {"c07": True, "c06": False})

    def test_missing_transcript_folder_is_an_empty_list(self):
        """Adversarial where: a project with no Claude Code folder raises
        instead of reporting nothing."""
        shutil.rmtree(self.folder)
        code, out, _ = run_sessions(["list", "--json"])
        self.assertEqual((code, json.loads(out)), (0, []))
        code, out, _ = run_sessions(["list"])
        self.assertEqual(code, 0)

    def test_rows_are_ordered_newest_first(self):
        """Adversarial where: rows come in directory order or oldest first,
        so the session a human just finished is at the bottom."""
        self.make_session("old", commits=10, age=86400 * 3)
        self.make_session("newest", commits=10, age=3600)
        self.make_session("mid", commits=10, age=86400)
        self.assertEqual(self.ids(), ["newest", "mid", "old"])


class ListFieldTests(SessionsCase):
    def test_json_row_carries_exactly_the_pinned_fields(self):
        """Adversarial where: a field is renamed, missing or mistyped
        (plans as a string, modified as epoch seconds, active as 0/1), or the
        row exposes keys the consumer never asked for."""
        self.make_session("full", commits=10, used=61_234,
                          text="Finished PLAN-020 and PLAN-007 with TASK-142 and TASK-9",
                          age=7200)
        (row,) = self.list_json()
        self.assertEqual(set(row), JSON_KEYS)
        self.assertEqual(row["session_id"], "full")
        self.assertEqual(row["entrypoint"], "cli")
        self.assertEqual(row["commits"], 10)
        self.assertEqual(row["plans"], ["PLAN-007", "PLAN-020"])
        self.assertEqual(row["tasks"], ["TASK-9", "TASK-142"])
        self.assertEqual(row["model"], STANDARD_MODEL)
        self.assertEqual((row["used"], row["window"], row["headroom"]), (61_234, 200_000, 138_766))
        self.assertIs(row["active"], False)
        self.assertIs(row["feature"], True)
        stamp = datetime.fromisoformat(row["modified"].replace("Z", "+00:00"))
        self.assertIsNotNone(stamp.utcoffset())
        self.assertAlmostEqual(stamp.timestamp(), time.time() - 7200, delta=30)

    def test_headroom_uses_the_window_of_the_sessions_own_model(self):
        """Adversarial where: headroom is computed against one fixed window
        (200K or 1M) instead of the session's, an extended-window session that
        crossed 200K is measured against 200K, or an unknown usage yields a
        number."""
        self.make_session("std", commits=10, model=STANDARD_MODEL, used=150_000)
        self.make_session("ext-model", commits=10, model=EXTENDED_MODEL, used=150_000)
        self.make_session("crossed", commits=10, model=STANDARD_MODEL, used=300_000)
        self.make_session("tagged", commits=10, model=STANDARD_MODEL + "[1m]", used=120_000)
        self.make_session("no-usage", commits=10, model=STANDARD_MODEL, used=None)
        self.make_session("no-model", commits=10, model=None, used=None)
        rows = {r["session_id"]: r for r in self.list_json()}
        got = {k: (r["window"], r["headroom"]) for k, r in rows.items()}
        self.assertEqual(got, {
            "std": (200_000, 50_000),
            "ext-model": (1_000_000, 850_000),
            "crossed": (1_000_000, 700_000),
            "tagged": (1_000_000, 880_000),
            "no-usage": (200_000, None),
            "no-model": (None, None),
        })

    def test_session_is_marked_active_only_within_ten_minutes_of_its_last_write(self):
        """Adversarial where: the active flag is missing, inverted, or an
        open session is dropped from the list instead of marked (clone
        refuses it; list must still show it)."""
        self.make_session("live", commits=10, age=570)
        self.make_session("idle", commits=10, age=630)
        rows = {r["session_id"]: r["active"] for r in self.list_json()}
        self.assertEqual(rows, {"live": True, "idle": False})

    def test_table_has_the_pinned_header_and_one_row_per_session(self):
        """Adversarial where: columns are reordered or renamed, absent values
        print as empty cells (shifting every later column), or plan ids print
        space-separated."""
        self.make_session("withids", commits=10, used=40_000, text="PLAN-020 PLAN-021 TASK-142", age=900)
        self.make_session("bare", entry=None, commits=2, model=None, used=None, text="hi", age=100)
        code, out, err = run_sessions(["list", "--all"])
        self.assertEqual(code, 0, err)
        lines = [ln for ln in out.splitlines() if ln.strip()]
        self.assertEqual(lines[0].split(), TABLE_HEADER)
        rows = {ln.split()[0]: ln.split() for ln in lines[1:]}
        self.assertEqual(set(rows), {"withids", "bare"})
        first = rows["withids"]
        self.assertEqual(len(first), len(TABLE_HEADER))
        self.assertEqual(first[1:8], ["cli", "10", "PLAN-020,PLAN-021", "TASK-142",
                                      STANDARD_MODEL, "40000", "160000"])
        self.assertEqual(first[9:], ["no", "yes"])
        datetime.fromisoformat(first[8].replace("Z", "+00:00"))
        bare = rows["bare"]
        self.assertEqual(len(bare), len(TABLE_HEADER))
        self.assertEqual(bare[1:8], ["-", "2", "-", "-", "-", "-", "-"])
        self.assertEqual(bare[9:], ["yes", "no"])

    def test_list_leaves_every_transcript_untouched(self):
        """Adversarial where: the reader opens a transcript for writing or
        touches it, so listing changes a session's hash or modification time
        (and would mark it active)."""
        a = self.make_session("a", commits=10, sub_commits=2, used=1_000)
        b = self.make_session("b", commits=1)
        before = {p: digest(p) for p in (a, b)}
        for flags in ([], ["--all"], ["--json"], ["--all", "--json"]):
            run_sessions(["list", *flags])
        self.assertEqual({p: digest(p) for p in (a, b)}, before)


class ListArgumentTests(SessionsCase):
    def test_bad_arguments_return_one_with_a_message_never_two(self):
        """Adversarial where: argparse's exit 2 escapes for a non-integer or
        negative `--min-commits`, an unknown option or subcommand, or no
        subcommand at all; or the failure prints nothing."""
        rows = {
            "non-integer": ["list", "--min-commits", "many"],
            "negative": ["list", "--min-commits", "-1"],
            "missing value": ["list", "--min-commits"],
            "unknown option": ["list", "--bogus"],
            "unknown subcommand": ["frobnicate"],
            "no subcommand": [],
        }
        self.make_session("c10", commits=10)
        for name, args in rows.items():
            with self.subTest(name):
                code, out, err = run_sessions(args)
                self.assertEqual(code, 1)
                self.assertTrue(err.strip())


class ShowTests(SessionsCase):
    def stream(self):
        """A clone's stream-json: init, assistant text and tool calls, a tool
        result, a final result line, and three unparseable lines."""
        multiline_cmd = "echo first\necho second"
        records = [
            json.dumps({"type": "system", "subtype": "init", "session_id": "x"}).encode(),
            json.dumps(assistant(text_block("I will read the file."),
                                 tool_block("Read", file_path="/p/a.py"))).encode(),
            b"this is not json {{{",
            json.dumps({"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "FILEBODY-TEXT"}]}}).encode(),
            b'[1, 2, 3]',
            b'"just a string"',
            json.dumps(assistant(tool_block("Bash", command=multiline_cmd))).encode(),
            json.dumps(assistant(text_block("Lesson one:\nsecond line of it."))).encode(),
            json.dumps({"type": "user", "message": {"role": "user", "content": "USER-PROMPT-TEXT"}}).encode(),
            json.dumps({"type": "result", "subtype": "success", "result": "FINAL-RESULT-TEXT"}).encode(),
        ]
        return records

    def test_stream_json_prints_assistant_words_and_one_line_per_tool_call(self):
        """Adversarial where: an unparseable or non-object line aborts the
        render or leaks into it, a multi-line tool input spills over several
        lines, tool results / prompts / the result line are echoed, or output
        order differs from transcript order."""
        path = self.write_raw(self.tmp / "clone.jsonl", *self.stream())
        code, out, err = run_sessions(["show", str(path)])
        self.assertEqual(code, 0, err)
        self.assertIn("I will read the file.", out)
        self.assertIn("Lesson one:\nsecond line of it.", out)
        tool_lines = [ln for ln in out.splitlines() if ln.startswith("[tool] ")]
        self.assertEqual(len(tool_lines), 2)
        self.assertTrue(tool_lines[0].startswith("[tool] Read ") and "/p/a.py" in tool_lines[0])
        self.assertTrue(tool_lines[1].startswith("[tool] Bash "))
        self.assertIn("echo first", tool_lines[1])
        self.assertIn("echo second", tool_lines[1])
        for leaked in ("FILEBODY-TEXT", "USER-PROMPT-TEXT", "FINAL-RESULT-TEXT", "not json", "just a string"):
            self.assertNotIn(leaked, out)
        self.assertLess(out.index("I will read the file."), out.index("[tool] Read"))
        self.assertLess(out.index("[tool] Read"), out.index("[tool] Bash"))
        self.assertLess(out.index("[tool] Bash"), out.index("Lesson one:"))

    def test_malformed_bytes_and_fields_are_skipped_not_raised(self):
        """Adversarial where: one line with invalid UTF-8, a BOM on the first
        line, an empty file, or records whose fields have the wrong shape
        (content as a number, message as a list, a tool input that is not an
        object, a text block whose text is a number) crash the render or
        hide the good lines around them."""
        good = json.dumps(assistant(text_block("valid words here"))).encode("utf-8")
        lines = [
            b"\xef\xbb\xbf" + good,
            b"\xff\xfe\x00\x01 broken bytes",
            json.dumps({"type": "assistant", "message": {"content": "plain string reply"}}).encode(),
            json.dumps({"type": "assistant", "message": {"content": 5}}).encode(),
            json.dumps({"type": "assistant", "message": [1, 2]}).encode(),
            json.dumps({"type": "assistant", "message": {"content": [text_block(123), "bare", None]}}).encode(),
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Grep", "input": ["not", "an", "object"]}]}}).encode(),
            json.dumps(assistant(text_block("last words"))).encode(),
        ]
        path = self.write_raw(self.tmp / "odd.jsonl", *lines)
        code, out, err = run_sessions(["show", str(path)])
        self.assertEqual(code, 0, err)
        for expected in ("valid words here", "plain string reply", "last words"):
            self.assertIn(expected, out)
        grep_lines = [ln for ln in out.splitlines() if ln.startswith("[tool] Grep")]
        self.assertEqual(len(grep_lines), 1)
        empty = self.tmp / "empty.jsonl"
        empty.write_bytes(b"")
        self.assertEqual(run_sessions(["show", str(empty)]), (0, "", ""))

    def test_non_ascii_text_survives_the_render(self):
        """Adversarial where: the renderer escapes or mangles non-ASCII
        assistant words and tool inputs (cp1252 or `\\uXXXX` output)."""
        words = "ação concluída ✓ 日本語"
        path = self.write_raw(
            self.tmp / "u.jsonl",
            json.dumps(assistant(text_block(words), tool_block("Write", file_path="/p/é.md")),
                       ensure_ascii=False).encode("utf-8"))
        code, out, _ = run_sessions(["show", str(path)])
        self.assertEqual(code, 0)
        self.assertIn(words, out)
        self.assertIn("/p/é.md", out)

    def test_run_id_slash_session_id_resolves_under_the_central_folder(self):
        """Adversarial where: the central folder is resolved without the run
        id (another run's same-named session is shown), is read from
        `~/.claude/projects`, or a missing run still exits 0."""
        mine = sessionslib.run_dir(self.project, "run-7")
        theirs = sessionslib.run_dir(self.project, "run-8")
        self.write_raw(mine / "abcd1234.jsonl",
                       json.dumps(assistant(text_block("FROM-RUN-SEVEN"))).encode())
        self.write_raw(theirs / "abcd1234.jsonl",
                       json.dumps(assistant(text_block("FROM-RUN-EIGHT"))).encode())
        self.write_raw(self.folder / "run-7" / "abcd1234.jsonl",
                       json.dumps(assistant(text_block("FROM-CLAUDE-FOLDER"))).encode())
        code, out, err = run_sessions(["show", "run-7/abcd1234"])
        self.assertEqual(code, 0, err)
        self.assertIn("FROM-RUN-SEVEN", out)
        self.assertNotIn("FROM-RUN-EIGHT", out)
        self.assertNotIn("FROM-CLAUDE-FOLDER", out)

    def test_unreadable_targets_return_one_with_stderr_and_no_stdout(self):
        """Adversarial where: a missing file, a directory, an unknown run, an
        unknown session in a known run, or no argument raises a traceback or
        exits 2 or 0."""
        self.write_raw(sessionslib.run_dir(self.project, "run-7") / "known.jsonl",
                       json.dumps(assistant(text_block("x"))).encode())
        rows = {
            "no argument": ["show"],
            "missing file": ["show", str(self.tmp / "nope.jsonl")],
            "directory": ["show", str(self.tmp)],
            "unknown run": ["show", "run-404/known"],
            "unknown session": ["show", "run-7/unknown"],
        }
        for name, args in rows.items():
            with self.subTest(name):
                code, out, err = run_sessions(args)
                self.assertEqual(code, 1)
                self.assertEqual(out, "")
                self.assertTrue(err.strip())

    def test_show_leaves_the_transcript_untouched(self):
        """Adversarial where: rendering rewrites or touches the transcript
        it reads."""
        path = self.write_raw(self.tmp / "clone.jsonl", *self.stream())
        os.utime(path, (1_700_000_000, 1_700_000_000))
        before = digest(path)
        run_sessions(["show", str(path)])
        self.assertEqual(digest(path), before)


class RecordTests(SessionsCase):
    def rows(self):
        text = self.log.read_text(encoding="utf-8")
        return [json.loads(ln) for ln in text.splitlines() if ln.strip()]

    def test_record_appends_one_row_of_names_and_counts(self):
        """Adversarial where: the row is missing a field, counts are
        derived off by one (a `--rejected 0` boundary read as unset), names are
        mangled (non-ASCII), or `--merged` values land under `written`."""
        code, _, err = run_sessions(["record", "run-9", "--written", "LESSON-aa", "LESSON-ação",
                                     "LESSON-cc", "--merged", "LESSON-dd", "--rejected", "4"])
        self.assertEqual(code, 0, err)
        (row,) = self.rows()
        self.assertEqual(set(row), RUN_ROW_KEYS)
        self.assertEqual(row["event"], "run")
        self.assertEqual(row["run_id"], "run-9")
        self.assertEqual(row["written"], ["LESSON-aa", "LESSON-ação", "LESSON-cc"])
        self.assertEqual(row["merged"], ["LESSON-dd"])
        self.assertEqual((row["written_count"], row["merged_count"], row["rejected"]), (3, 1, 4))
        datetime.fromisoformat(row["at"].replace("Z", "+00:00"))
        run_sessions(["record", "run-10"])
        empty = self.rows()[-1]
        self.assertEqual((empty["run_id"], empty["written"], empty["merged"], empty["rejected"]),
                         ("run-10", [], [], 0))
        self.assertEqual((empty["written_count"], empty["merged_count"]), (0, 0))

    def test_record_appends_after_existing_rows_even_without_a_trailing_newline(self):
        """Adversarial where: the log is overwritten rather than appended, or
        a final row with no newline gets the new row glued onto its line,
        corrupting both."""
        first = b'{"event":"clone","run_id":"r1","session_id":"s1","status":"done"}'
        self.log.write_bytes(first)
        run_sessions(["record", "r1", "--written", "LESSON-x"])
        run_sessions(["record", "r2", "--rejected", "1"])
        data = self.log.read_bytes()
        self.assertTrue(data.startswith(first + b"\n"))
        rows = self.rows()
        self.assertEqual([r.get("run_id") for r in rows], ["r1", "r1", "r2"])
        self.assertEqual([r["event"] for r in rows], ["clone", "run", "run"])
        self.assertEqual(len(data.splitlines()), 3)

    def test_record_never_copies_transcript_or_lesson_text(self):
        """Adversarial where: the command reads the run folder's lesson file
        or transcript and puts their text into the vault's log."""
        run = sessionslib.run_dir(self.project, "run-5")
        run.mkdir(parents=True)
        (run / "sess1.md").write_text("LESSON-BODY-SECRET always mock the db", encoding="utf-8")
        (run / "sess1.jsonl").write_text(
            json.dumps(assistant(text_block("TRANSCRIPT-SECRET words"))) + "\n", encoding="utf-8")
        (run / "run.json").write_text(json.dumps({"note": "RUNJSON-SECRET"}), encoding="utf-8")
        code, _, err = run_sessions(["record", "run-5", "--written", "LESSON-one", "--rejected", "1"])
        self.assertEqual(code, 0, err)
        logged = self.log.read_text(encoding="utf-8")
        for secret in ("LESSON-BODY-SECRET", "TRANSCRIPT-SECRET", "RUNJSON-SECRET", "always mock"):
            self.assertNotIn(secret, logged)

    def test_invalid_record_arguments_return_one_and_append_nothing(self):
        """Adversarial where: a negative or non-integer `--rejected`, a
        missing run id, a dangling option or an unknown option exits 2 (the
        argparse default) or still appends a row."""
        self.log.write_bytes(b'{"event":"clone"}\n')
        before = self.log.read_bytes()
        rows = {
            "no run id": ["record"],
            "negative rejected": ["record", "r", "--rejected", "-1"],
            "non-integer rejected": ["record", "r", "--rejected", "some"],
            "dangling rejected": ["record", "r", "--rejected"],
            "unknown option": ["record", "r", "--bogus", "1"],
        }
        for name, args in rows.items():
            with self.subTest(name):
                code, _, err = run_sessions(args)
                self.assertEqual(code, 1)
                self.assertTrue(err.strip())
                self.assertEqual(self.log.read_bytes(), before)

    def test_record_creates_the_log_when_it_does_not_exist(self):
        """Adversarial where: the first run of a project (no log yet) fails
        with FileNotFoundError, or lands the file somewhere other than
        `<vault>/meta/clone-log.jsonl`."""
        self.assertFalse(self.log.exists())
        code, _, err = run_sessions(["record", "first-run", "--merged", "LESSON-m"])
        self.assertEqual(code, 0, err)
        self.assertEqual([r["run_id"] for r in self.rows()], ["first-run"])
        self.assertEqual(self.rows()[0]["merged_count"], 1)


if __name__ == "__main__":
    unittest.main()
