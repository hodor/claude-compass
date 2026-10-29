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
import subprocess
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
             "window", "headroom", "modified", "active", "feature",
             "est_cost_usd", "est_basis"}
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


class ListWorktreeTests(SessionsCase):
    def git(self, cwd, *args):
        subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)

    def make_worktree(self):
        """A git main checkout at `self.project` and a linked worktree under
        its `.claude/worktrees/`, each with a vault; returns the worktree."""
        (self.project / ".compass" / "meta" / ".keep").write_text("", encoding="utf-8")
        self.git(self.project, "init", "-q")
        self.git(self.project, "add", ".compass")
        self.git(self.project, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "vault")
        worktree = self.project / ".claude" / "worktrees" / "builder-1"
        self.git(self.project, "worktree", "add", "-q", str(worktree))
        return worktree

    def test_list_from_a_linked_worktree_reads_the_main_checkout_sessions(self):
        """Adversarial where: run inside `.claude/worktrees/<name>`, the
        project root is the worktree, whose own transcript folder is empty,
        so every session of the project is missing (GitHub #46)."""
        self.make_session("main10", commits=10)
        worktree = self.make_worktree()
        os.environ["CLAUDE_PROJECT_DIR"] = str(worktree)
        self.assertEqual(self.ids(), ["main10"])

    def test_list_from_a_worktree_of_a_submodule_reads_the_submodule_checkout(self):
        """Adversarial where: the shared git dir of a submodule is
        `<super>/.git/modules/<name>`, not a `.git` folder, so a path rule
        that takes the git dir's parent finds no checkout."""
        inner = self.tmp / "inner"
        inner.mkdir()
        self.git(inner, "init", "-q")
        self.git(inner, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "--allow-empty", "-qm", "x")
        outer = self.tmp / "outer"
        outer.mkdir()
        self.git(outer, "init", "-q")
        self.git(outer, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(inner), "sub")
        submodule = outer / "sub"
        (submodule / ".compass").mkdir()
        self.make_session("sub10", commits=10, folder=sessionslib.transcripts_dir(submodule.resolve()))
        worktree = self.tmp / "sub-wt"
        self.git(submodule, "worktree", "add", "-q", str(worktree))
        (worktree / ".compass").mkdir()
        os.environ["CLAUDE_PROJECT_DIR"] = str(worktree)
        self.assertEqual(self.ids(), ["sub10"])

    def test_list_from_a_worktree_of_a_separate_git_dir_repo_names_the_folder_it_read(self):
        """Adversarial where: git records no main checkout for a repo made
        with `--separate-git-dir` and lists the git dir itself, which a
        resolver must not take for a checkout."""
        gitdir = self.tmp / "store.git"
        self.git(self.tmp, "init", "-q", "--separate-git-dir", str(gitdir), str(self.project))
        (self.project / ".compass" / "meta" / ".keep").write_text("", encoding="utf-8")
        self.git(self.project, "add", ".compass")
        self.git(self.project, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "keep")
        worktree = self.project / ".claude" / "worktrees" / "builder-2"
        self.git(self.project, "worktree", "add", "-q", str(worktree))
        self.assertEqual(sessionslib.main_checkout(worktree), worktree)
        os.environ["CLAUDE_PROJECT_DIR"] = str(worktree)
        code, out, err = run_sessions(["list", "--json"])
        self.assertEqual((code, json.loads(out)), (0, []))
        self.assertIn(str(sessionslib.transcripts_dir(worktree)), err)

    def test_list_from_the_main_checkout_is_unchanged_by_its_worktrees(self):
        self.make_session("main10", commits=10)
        self.make_worktree()
        self.assertEqual(self.ids(), ["main10"])

    def test_empty_list_names_the_folder_it_searched(self):
        """Adversarial where: an empty result is indistinguishable from a
        lookup in the wrong folder, since `[]` names no folder."""
        for flags in ([], ["--json"]):
            with self.subTest(flags=flags):
                code, out, err = run_sessions(["list", *flags])
                self.assertEqual(code, 0, err)
                self.assertIn(str(self.folder), err)


class ListTopicTests(SessionsCase):
    def test_grep_keeps_sessions_whose_transcript_mentions_the_topic(self):
        """Adversarial where: the topic is ignored (GitHub #46), matched
        case-sensitively, or only searched in the first record; a session
        whose subagents alone did the topic's work is dropped."""
        self.make_session("pod", commits=10, extra=[assistant(text_block("deploy to RunPod"))])
        self.make_session("pod_lower", commits=10, text="the runpod endpoint")
        self.make_session("side", commits=10)
        side = self.folder / "side" / "subagents" / "agent-a1.jsonl"
        self.write_raw(side, json.dumps(assistant(text_block("RUNPOD worker"))).encode("utf-8"))
        self.make_session("other", commits=10, text="unrelated work")
        self.assertEqual(sorted(self.ids("--grep", "runpod")), ["pod", "pod_lower", "side"])

    def test_grep_reads_conversation_text_not_record_metadata(self):
        """Adversarial where: the pattern runs over raw JSON lines, so a word
        in every record's `cwd` or `gitBranch` (the project's own name)
        matches every session, and `^` anchors to the JSON line."""
        quiet = {"type": "user", "cwd": "/work/runpod-tools", "gitBranch": "runpod",
                 "message": {"role": "user", "content": "unrelated work"}}
        self.make_session("meta_only", commits=10, text="unrelated work", extra=[quiet])
        self.make_session("said", commits=10, text="runpod at the start")
        result = {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t", "content": "pod 7 on RunPod"}]}}
        self.make_session("tool_said", commits=10, extra=[result])
        call = assistant(tool_block("Bash", command="runpodctl get pods"))
        self.make_session("call_said", commits=10, extra=[call])
        self.assertEqual(sorted(self.ids("--grep", "runpod")), ["call_said", "said", "tool_said"])
        self.assertEqual(self.ids("--grep", "^runpod"), ["said"])

    def test_grep_with_an_invalid_pattern_returns_one(self):
        self.make_session("c10", commits=10)
        code, _, err = run_sessions(["list", "--grep", "(unclosed"])
        self.assertEqual(code, 1)
        self.assertIn("--grep", err)

    def test_grep_without_a_pattern_returns_one(self):
        code, _, err = run_sessions(["list", "--grep"])
        self.assertEqual(code, 1)
        self.assertTrue(err.strip())


class ListCostEstimateTests(SessionsCase):
    def write_run(self, project_key, run_id, clones):
        folder = self.home / "sessions" / project_key / run_id
        folder.mkdir(parents=True)
        (folder / "run.json").write_text(json.dumps({"run_id": run_id, "clones": clones}),
                                         encoding="utf-8")

    def test_estimate_without_history_uses_the_default_rate(self):
        """Adversarial where: no past run exists and the estimate is zero or
        missing, so a costly run goes ahead unflagged (GitHub #46)."""
        self.make_session("c10", commits=10, used=800000)
        module = importlib.import_module("commands.sessions")
        row = self.list_json()[0]
        self.assertEqual(row["est_cost_usd"], round(800000 * module.DEFAULT_USD_PER_MTOK / 1e6, 2))
        self.assertEqual(row["est_basis"], "default")

    def test_estimate_calibrates_from_past_runs_of_every_project(self):
        """Adversarial where: past clones' cost per inherited token is
        ignored, rows without `used` or `cost_usd` skew the rate, or only
        this project's runs count."""
        self.write_run("other-project", "r1", [
            {"session_id": "a", "used": 1000000, "cost_usd": 100.0},
            {"session_id": "b", "used": 1000000, "cost_usd": 300.0},
            {"session_id": "c", "used": None, "cost_usd": 999.0},
            {"session_id": "d", "used": 500000, "cost_usd": None},
            {"session_id": "e", "used": 0, "cost_usd": 50.0},
        ])
        self.make_session("c10", commits=10, used=500000)
        row = self.list_json()[0]
        self.assertEqual(row["est_cost_usd"], 100.0)
        self.assertEqual(row["est_basis"], "2 past clones")

    def test_a_corrupt_run_record_falls_back_to_the_default(self):
        folder = self.home / "sessions" / "p" / "bad"
        folder.mkdir(parents=True)
        (folder / "run.json").write_bytes(b"\xff not json")
        self.make_session("c10", commits=10, used=1000)
        self.assertEqual(self.list_json()[0]["est_basis"], "default")

    def test_hostile_past_rows_never_skew_or_crash_the_estimate(self):
        """Adversarial where: a run.json carries NaN, Infinity, a negative
        or float-overflowing cost, a huge `used`, or nesting deep enough to
        exhaust the parser; any one of them crashes `list`, prints invalid
        JSON (NaN), or drags the rate below zero."""
        folder = self.home / "sessions" / "p" / "hostile"
        folder.mkdir(parents=True)
        (folder / "run.json").write_text(
            '{"clones": [{"used": 1000, "cost_usd": NaN},'
            ' {"used": 1000, "cost_usd": Infinity},'
            ' {"used": 1000, "cost_usd": -5},'
            ' {"used": 1000, "cost_usd": 1' + "0" * 400 + '},'
            ' {"used": 1' + "0" * 400 + ', "cost_usd": 1},'
            ' {"used": 1000000, "cost_usd": 200}]}', encoding="utf-8")
        deep = self.home / "sessions" / "p" / "deep"
        deep.mkdir(parents=True)
        (deep / "run.json").write_text('{"clones":' + "[" * 100000, encoding="utf-8")
        self.make_session("c10", commits=10, used=500000)
        code, out, err = run_sessions(["list", "--json"])
        self.assertEqual(code, 0, err)
        (row,) = json.loads(out, parse_constant=lambda name: self.fail(f"{name} in output"))
        self.assertEqual(row["est_cost_usd"], 100.0)
        self.assertEqual(row["est_basis"], "1 past clone")

    def test_unknown_usage_has_no_estimate(self):
        self.make_session("c10", commits=10)
        row = self.list_json()[0]
        self.assertIsNone(row["est_cost_usd"])


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


class StrictOutputCase(SessionsCase):
    """Runs a subcommand against a real encoding-strict text stream, the way a
    terminal or pipe behaves, instead of a StringIO that accepts anything."""

    def run_strict(self, args, encoding="utf-8"):
        """`(exit_code, stdout_bytes, stderr)`; an exception that escapes `run`
        propagates so the test shows the traceback."""
        module = importlib.import_module("commands.sessions")
        raw = io.BytesIO()
        wrapper = io.TextIOWrapper(raw, encoding=encoding, errors="strict", newline="\n")
        err = io.StringIO()
        with redirect_stdout(wrapper), redirect_stderr(err):
            code = module.run(list(args))
        wrapper.flush()
        return code, raw.getvalue(), err.getvalue()


class SessionsRobustnessTests(StrictOutputCase):
    def test_one_unreadable_transcript_does_not_kill_the_listing(self):
        """Adversarial where: a transcript that raises on read (locked by
        another process, permission denied) escapes the per-row guard and the
        whole `list` fails, or the bad session is listed with garbage fields."""
        self.make_session("good-a", commits=10, age=100)
        bad = self.make_session("locked", commits=10, age=200)
        self.make_session("good-b", commits=10, age=300)
        if os.name == "nt":
            import msvcrt
            holder = open(bad, "r+b")
            self.addCleanup(holder.close)
            msvcrt.locking(holder.fileno(), msvcrt.LK_NBLCK, 8)
            self.addCleanup(lambda: (holder.seek(0), msvcrt.locking(holder.fileno(), msvcrt.LK_UNLCK, 8)))
        else:
            if os.geteuid() == 0:
                self.skipTest("root reads any file")
            os.chmod(bad, 0)
            self.addCleanup(os.chmod, bad, 0o600)
        code, out, err = run_sessions(["list", "--json", "--all"])
        self.assertEqual(code, 0, err)
        shown = [row["session_id"] for row in json.loads(out)]
        self.assertIn("good-a", shown)
        self.assertIn("good-b", shown)
        self.assertNotIn("locked", shown)

    def test_a_deeply_nested_json_line_is_skipped_like_any_unparseable_line(self):
        """Adversarial where: a line of 100000 open brackets makes `json.loads`
        raise RecursionError (not ValueError), which the line parser does not
        catch, so one hostile line takes down `list` for every session and
        `show` for that transcript."""
        self.make_session("fine", commits=10, age=100)
        bad = self.folder / "nested.jsonl"
        self.write_raw(bad, b"[" * 100000,
                       json.dumps({"type": "user", "entrypoint": "cli"}).encode(),
                       json.dumps(assistant(text_block("AFTER-THE-NEST"))).encode())
        with self.subTest("list"):
            code, out, err = run_sessions(["list", "--json", "--all"])
            self.assertEqual(code, 0, err)
            self.assertEqual(sorted(r["session_id"] for r in json.loads(out)), ["fine", "nested"])
        with self.subTest("show"):
            code, out, err = run_sessions(["show", str(bad)])
            self.assertEqual(code, 0, err)
            self.assertIn("AFTER-THE-NEST", out)

    def test_show_does_not_crash_on_text_the_output_encoding_cannot_hold(self):
        """Adversarial where: a transcript text holding a lone surrogate
        (JSON `\\ud83d` is legal) reaches the strict UTF-8 stdout and raises
        UnicodeEncodeError instead of printing the rest of the transcript."""
        path = self.write_raw(self.tmp / "t.jsonl",
                              json.dumps(assistant(text_block("before \ud83d after"))).encode(),
                              json.dumps(assistant(text_block("LATER-LINE"))).encode())
        code, out, err = self.run_strict(["show", str(path)])
        self.assertEqual(code, 0, err)
        self.assertIn(b"LATER-LINE", out)

    def test_output_is_utf8_whatever_the_stream_default_encoding(self):
        """Adversarial where: stdout keeps a legacy codepage (cp1252) because
        the reconfigure step is skipped or wrong, so non-Latin transcript text
        and session ids raise or come out as mojibake."""
        self.make_session("sess-ação-日本", commits=10)
        path = self.write_raw(self.tmp / "t.jsonl",
                              json.dumps(assistant(text_block("日本語 ação"))).encode())
        code, out, err = self.run_strict(["show", str(path)], encoding="cp1252")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.decode("utf-8").strip(), "日本語 ação")
        code, out, err = self.run_strict(["list", "--all"], encoding="cp1252")
        self.assertEqual(code, 0, err)
        self.assertIn("sess-ação-日本", out.decode("utf-8"))

    def test_show_prints_a_twenty_megabyte_single_line_whole(self):
        """Adversarial where: a transcript line far larger than any read chunk
        is truncated, dropped, or makes the render quadratic."""
        big = "x" * (20 * 1024 * 1024)
        path = self.write_raw(self.tmp / "big.jsonl",
                              json.dumps(assistant(text_block(big))).encode(),
                              json.dumps(assistant(text_block("TAIL-MARK"))).encode())
        started = time.monotonic()
        code, out, err = run_sessions(["show", str(path)])
        elapsed = time.monotonic() - started
        self.assertEqual(code, 0, err)
        self.assertEqual(out, big + "\nTAIL-MARK\n")
        self.assertLess(elapsed, 30)

    def test_list_of_three_hundred_sessions_finishes_in_bounded_time(self):
        """Adversarial where: per-session work grows with the folder (a rescan
        of every transcript per row) so a long-lived project's `list` takes
        minutes."""
        for n in range(300):
            self.make_session("s%03d" % n, commits=10 + n % 3, sub_commits=n % 2, age=1000 + n)
        started = time.monotonic()
        rows = self.list_json()
        elapsed = time.monotonic() - started
        self.assertEqual(len(rows), 300)
        self.assertEqual(rows[0]["session_id"], "s000")
        self.assertLess(elapsed, 30)

    def test_a_session_with_an_unrepresentable_mtime_is_not_silently_dropped(self):
        """Adversarial where: a transcript whose mtime cannot be formatted
        (far future, clock skew, restored backup) hits the `except OSError`
        around the row and vanishes from `list --all` with no message."""
        self.make_session("normal", commits=10, age=100)
        odd = self.make_session("skewed", commits=10)
        os.utime(odd, (2 ** 36, 2 ** 36))
        code, out, err = run_sessions(["list", "--json", "--all"])
        self.assertEqual(code, 0, err)
        self.assertIn("skewed", [row["session_id"] for row in json.loads(out)])

    def test_min_commits_refuses_values_that_only_look_like_integers(self):
        """Adversarial where: `int()`-style leniency lets Unicode digits, a
        trailing newline, surrounding space, a decimal or an empty value
        through as a commit line instead of returning 1."""
        self.make_session("c10", commits=10)
        values = {"arabic-indic digit": "\u0663", "trailing newline": "5\n", "leading space": " 5",
                  "decimal": "1.0", "exponent": "1e1", "hex": "0x10", "empty": ""}
        for name, value in values.items():
            with self.subTest(name):
                code, out, err = run_sessions(["list", "--min-commits", value])
                self.assertEqual(code, 1)
                self.assertTrue(err.strip())
                self.assertEqual(out, "")
        with self.subTest("flag swallowed as the value"):
            code, _, err = run_sessions(["list", "--min-commits", "--all"])
            self.assertEqual(code, 1)
            self.assertTrue(err.strip())
        with self.subTest("zero is the boundary and valid"):
            self.make_session("c00", commits=0, age=10)
            self.assertIn("c00", self.ids("--min-commits", "0"))

    def test_show_refuses_targets_that_climb_out_of_the_run_folder(self):
        """Adversarial where: a `..` or separator in the run id or session id
        resolves a file outside `<central>/sessions/<key>/<run-id>/`, so `show`
        reads arbitrary jsonl through the clone shorthand."""
        run = sessionslib.run_dir(self.project, "run-1")
        run.mkdir(parents=True)
        (run / "inside.jsonl").write_text(json.dumps(assistant(text_block("INSIDE"))) + "\n", encoding="utf-8")
        decoy = run.parent / "loose.jsonl"
        decoy.write_text(json.dumps(assistant(text_block("DECOY-OUTSIDE"))) + "\n", encoding="utf-8")
        with self.subTest("control: the shorthand resolves"):
            code, out, err = run_sessions(["show", "run-1/inside"])
            self.assertEqual(code, 0, err)
            self.assertIn("INSIDE", out)
        targets = {
            "parent as run id": "../loose",
            "parent as session id": "run-1/..",
            "three segments": "run-1/../loose",
            "backslash climb": "run-1\\..\\loose",
            "backslash in session id": "run-1/..\\loose",
            "empty session id": "run-1/",
            "empty run id": "/inside",
            "dot run id": "./inside",
        }
        for name, target in targets.items():
            with self.subTest(name):
                code, out, err = run_sessions(["show", target])
                self.assertEqual(code, 1)
                self.assertNotIn("DECOY-OUTSIDE", out)
                self.assertTrue(err.strip())

    @unittest.skipUnless(os.name == "nt", "drive-relative paths exist only on Windows")
    def test_show_refuses_a_drive_letter_run_id(self):
        """Adversarial where: `C:/name` passes the `..`/separator screen, and
        `run_dir / "C:"` then re-roots the join at the drive's current
        directory, so `show` reads `<cwd>/name.jsonl` instead of a kept clone."""
        other = os.path.splitdrive(os.path.abspath(__file__))[0]
        if other.lower() == os.path.splitdrive(str(self.tmp))[0].lower():
            self.skipTest("the test file and the temp dir share a drive")
        elsewhere = Path(tempfile.mkdtemp(dir=os.path.dirname(os.path.abspath(__file__)))).resolve()
        self.addCleanup(shutil.rmtree, elsewhere, True)
        self.addCleanup(os.chdir, os.getcwd())
        (elsewhere / "name.jsonl").write_text(json.dumps(assistant(text_block("CWD-FILE"))) + "\n", encoding="utf-8")
        os.chdir(elsewhere)
        code, out, err = run_sessions(["show", f"{other}/name"])
        self.assertEqual(code, 1)
        self.assertNotIn("CWD-FILE", out)
        self.assertTrue(err.strip())


class RecordHostileInputTests(StrictOutputCase):
    def rows_by_lines(self):
        """Parse the log the way a line-oriented reader does: every line of
        `str.splitlines()` must itself be one JSON object."""
        text = self.log.read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def test_names_with_line_breaking_characters_stay_on_one_parseable_line(self):
        """Adversarial where: a lesson name or run id holding a newline, quote,
        backslash or a Unicode line separator (U+2028, U+0085) splits the
        appended row across lines, so a reader using `splitlines()` meets
        fragments that are not JSON."""
        names = {
            "newline": "LESSON-a\nb",
            "carriage return": "LESSON-a\rb",
            "double quote": 'LESSON-"q"',
            "backslash": "LESSON-a\\nb",
            "tab": "LESSON-a\tb",
            "line separator U+2028": "LESSON-a\u2028b",
            "paragraph separator U+2029": "LESSON-a\u2029b",
            "next line U+0085": "LESSON-a\u0085b",
        }
        for label, name in names.items():
            with self.subTest(label):
                self.log.write_bytes(b"")
                code, _, err = run_sessions(["record", "run-" + name, "--written", name, "--merged", name])
                self.assertEqual(code, 0, err)
                self.assertEqual(len(self.log.read_bytes().split(b"\n")), 2)
                (row,) = self.rows_by_lines()
                self.assertEqual((row["run_id"], row["written"], row["merged"]),
                                 ("run-" + name, [name], [name]))

    def test_unencodable_argument_returns_one_instead_of_a_traceback(self):
        """Adversarial where: an argument holding a lone surrogate (what POSIX
        argv yields for invalid UTF-8 bytes) makes the append raise
        UnicodeEncodeError, which the command does not turn into exit 1."""
        before = self.log.exists()
        code, _, err = run_sessions(["record", "run-1", "--written", "LESSON-\udcff"])
        self.assertEqual(code, 1)
        self.assertTrue(err.strip())
        self.assertEqual(self.log.exists(), before)

    def test_record_and_list_report_a_missing_vault_or_blocked_log_with_exit_one(self):
        """Adversarial where: no `.compass` above the project, or the log path
        occupied by a directory, escapes as a traceback or exit 2 instead of a
        stderr message and exit 1; a blocked log must also leave no row."""
        self.log.mkdir()
        with self.subTest("log path is a directory"):
            code, _, err = run_sessions(["record", "run-1"])
            self.assertEqual(code, 1)
            self.assertTrue(err.strip())
        bare = self.tmp / "no-vault"
        bare.mkdir()
        os.environ["CLAUDE_PROJECT_DIR"] = str(bare)
        os.chdir(bare)
        for args in (["record", "run-1"], ["list"], ["show", "run-1/s"]):
            with self.subTest("no vault: " + args[0]):
                code, out, err = run_sessions(args)
                self.assertEqual(code, 1)
                self.assertTrue(err.strip())
                self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
