"""Tests for `sessionslib`, the read-only transcript reader and central-folder
resolver that the `sessions`, `clone` and `retention` commands share.

Public API under test (module `sessionslib`, importable from `plugin/cli`).
Every `transcript` argument is a path (str or Path) to a session's main
`<session-id>.jsonl`; `project_path` is an absolute project path (str or Path):

    project_key(project_path) -> str
        Absolute path with every non-alphanumeric character replaced by `-`.
    config_dir() -> Path
        `CLAUDE_CONFIG_DIR` when set and non-empty, else `~/.claude`.
    transcripts_dir(project_path) -> Path
        `<config_dir()>/projects/<project_key(project_path)>`.
    compass_home() -> Path
        `COMPASS_HOME` when set and non-empty, else `~/.compass`.
    run_dir(project_path, run_id) -> Path
        `<compass_home()>/sessions/<project_key(project_path)>/<run_id>`.
    subagent_transcripts(transcript) -> list[Path]
        The session's `<session-id>/subagents/agent-*.jsonl` files, sorted by
        name; [] when the side folder is absent.
    entrypoint(transcript) -> str | None
        The top-level `entrypoint` field of the transcript (`cli`, `sdk-cli`);
        None when no line carries one.
    model_id(transcript) -> str | None
        Latest model attachment's `modelId`, else the latest non-sidechain
        assistant message's `message.model`, else None; `[1m]` is appended to
        an id lacking it when used_tokens(transcript) is above 200,000.
    used_tokens(transcript) -> int | None
        input + cache_creation + cache_read tokens of the last non-sidechain
        assistant line carrying usage; None when there is none.
    commit_count(transcript) -> int
        Bash tool_use calls running `git commit` or `git -C <path> commit`,
        in the main transcript plus every subagent transcript of the session.
    plan_ids(transcript) -> list[str]
    task_ids(transcript) -> list[str]
        Distinct `PLAN-NNN` / `TASK-NNN` ids mentioned in user and assistant
        message text, sorted by number. Hook and other attachment lines do not
        count as mentions.
    is_active(transcript, now=None) -> bool
        True when the file's mtime lies within 10 minutes before `now`
        (epoch seconds, default the current time).

Every reader opens transcripts read-only, skips lines that do not parse as a
JSON object, and tolerates records whose fields have the wrong shape."""

import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maincli  # noqa: E402
import sessionslib  # noqa: E402


STANDARD_MODEL = "claude-sonnet-4-6"
NOW = 1_800_000_000.0


def model_line(model_id):
    return {"type": "attachment", "attachment": {"type": "model", "identity": {"modelId": model_id}}}


def assistant_line(input_tokens=0, cache_creation=0, cache_read=0, output=500, sidechain=False,
                   model=None, content=None):
    message = {"role": "assistant", "content": content if content is not None else [],
               "usage": {"input_tokens": input_tokens, "cache_creation_input_tokens": cache_creation,
                         "cache_read_input_tokens": cache_read, "output_tokens": output}}
    if model:
        message["model"] = model
    return {"type": "assistant", "isSidechain": sidechain, "message": message}


def tool_use_line(name, sidechain=False, **tool_input):
    block = {"type": "tool_use", "id": "toolu_x", "name": name, "input": tool_input}
    return assistant_line(content=[block], sidechain=sidechain)


def bash_line(command, sidechain=False):
    return tool_use_line("Bash", sidechain=sidechain, command=command)


def text_line(role, text):
    if role == "assistant":
        return assistant_line(content=[{"type": "text", "text": text}])
    return {"type": "user", "message": {"role": "user", "content": text}}


class SessionsFixture(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.env_backup = dict(os.environ)
        for name in ("CLAUDE_CONFIG_DIR", "COMPASS_HOME", "COMPASS_CONTEXT_WINDOW",
                     "CLAUDE_CODE_DISABLE_1M_CONTEXT", "CLAUDE_CODE_MAX_CONTEXT_TOKENS"):
            os.environ.pop(name, None)
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(self.root / "home")
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self.env_backup)))
        self.session_id = "aaaa1111"
        self.transcript = self.root / f"{self.session_id}.jsonl"

    def write(self, *records, raw=(), path=None):
        lines = [json.dumps(r).encode("utf-8") for r in records] + list(raw)
        target = path or self.transcript
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\n".join(lines) + b"\n")
        return target

    def write_subagent(self, name, *records, session_id=None):
        side = self.root / (session_id or self.session_id) / "subagents"
        return self.write(*records, path=side / name)


class ProjectKeyTests(SessionsFixture):
    def test_every_non_alphanumeric_character_becomes_a_dash(self):
        """Adversarial where: only path separators are replaced, so `:`, `.`,
        `_` or a space survive and the key names a folder Claude Code never
        wrote."""
        rows = {
            "windows drive path": ("F:\\claude\\plugins\\compass", "F--claude-plugins-compass"),
            "posix dots and underscores": ("/home/ana/my.proj_v2/sub", "-home-ana-my-proj-v2-sub"),
            "underscore directory": ("F:\\AI\\_Tools\\ai-songwriting", "F--AI--Tools-ai-songwriting"),
            "space in a directory": ("C:\\Users\\Jane Doe\\proj", "C--Users-Jane-Doe-proj"),
            "existing dash and digits kept": ("/srv/app-2/x9", "-srv-app-2-x9"),
        }
        for name, (path, expected) in rows.items():
            with self.subTest(name):
                self.assertEqual(sessionslib.project_key(path), expected)

    def test_accepts_a_path_object(self):
        """Adversarial where: a Path argument is rejected or keyed by its
        repr instead of its string form."""
        self.assertEqual(sessionslib.project_key(Path("/home/x/y.z")), "-home-x-y-z")


class FolderResolutionTests(SessionsFixture):
    PROJECT = "/home/ana/my.proj_v2"
    KEY = "-home-ana-my-proj-v2"

    def test_transcripts_dir_follows_claude_config_dir(self):
        """Adversarial where: the transcript folder is hard-wired to `~/.claude`
        so a relocated config dir is never read; an empty variable must count
        as unset."""
        custom = self.root / "elsewhere"
        os.environ["CLAUDE_CONFIG_DIR"] = str(custom)
        self.assertEqual(sessionslib.config_dir(), custom)
        self.assertEqual(sessionslib.transcripts_dir(self.PROJECT), custom / "projects" / self.KEY)

        default = self.root / "home" / ".claude"
        for label, value in (("unset", None), ("empty", "")):
            with self.subTest(label):
                os.environ.pop("CLAUDE_CONFIG_DIR", None)
                if value is not None:
                    os.environ["CLAUDE_CONFIG_DIR"] = value
                self.assertEqual(sessionslib.config_dir(), default)
                self.assertEqual(sessionslib.transcripts_dir(self.PROJECT), default / "projects" / self.KEY)

    def test_run_dir_follows_compass_home(self):
        """Adversarial where: the central run folder ignores `COMPASS_HOME`, or
        is not laid out as sessions/<project-key>/<run-id>."""
        custom = self.root / "central"
        os.environ["COMPASS_HOME"] = str(custom)
        self.assertEqual(sessionslib.compass_home(), custom)
        self.assertEqual(sessionslib.run_dir(self.PROJECT, "run-7"), custom / "sessions" / self.KEY / "run-7")

        default = self.root / "home" / ".compass"
        for label, value in (("unset", None), ("empty", "")):
            with self.subTest(label):
                os.environ.pop("COMPASS_HOME", None)
                if value is not None:
                    os.environ["COMPASS_HOME"] = value
                self.assertEqual(sessionslib.compass_home(), default)
                self.assertEqual(sessionslib.run_dir(self.PROJECT, "r"), default / "sessions" / self.KEY / "r")

    def test_claude_config_dir_does_not_move_the_run_folder(self):
        """Adversarial where: the two roots are crossed, so clones land inside
        Claude's own config directory."""
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.root / "cfg")
        os.environ["COMPASS_HOME"] = str(self.root / "ch")
        self.assertEqual(sessionslib.run_dir(self.PROJECT, "r"), self.root / "ch" / "sessions" / self.KEY / "r")
        self.assertEqual(sessionslib.transcripts_dir(self.PROJECT), self.root / "cfg" / "projects" / self.KEY)


class SubagentTranscriptTests(SessionsFixture):
    def test_lists_only_this_sessions_agent_jsonl_files(self):
        """Adversarial where: the glob picks up `.meta.json` siblings, another
        session's subagents, or non-`agent-` files in the side folder."""
        self.write(text_line("user", "hi"))
        b = self.write_subagent("agent-b.jsonl", text_line("user", "b"))
        a = self.write_subagent("agent-a.jsonl", text_line("user", "a"))
        self.write_subagent("agent-a.meta.json", {"x": 1})
        self.write_subagent("notes.jsonl", text_line("user", "n"))
        self.write_subagent("agent-z.jsonl", text_line("user", "z"), session_id="bbbb2222")
        self.assertEqual(sessionslib.subagent_transcripts(self.transcript), [a, b])

    def test_no_side_folder_gives_an_empty_list(self):
        """Adversarial where: a session that never spawned a subagent raises
        instead of returning []."""
        self.write(text_line("user", "hi"))
        self.assertEqual(sessionslib.subagent_transcripts(self.transcript), [])


class EntrypointTests(SessionsFixture):
    def test_entrypoint_is_the_top_level_field(self):
        """Adversarial where: an `entrypoint` key nested in a tool input, seen
        before the real top-level one, is returned; a transcript with no field
        must give None, not a default."""
        nested = tool_use_line("Write", entrypoint="cli", content="x")
        rows = {
            "sdk-cli after lines without it": ([{"type": "permission-mode"}, nested,
                                                 dict(text_line("user", "go"), entrypoint="sdk-cli")], "sdk-cli"),
            "cli": ([dict(text_line("user", "go"), entrypoint="cli")], "cli"),
            "absent": ([{"type": "permission-mode"}, nested], None),
        }
        for name, (records, expected) in rows.items():
            with self.subTest(name):
                self.write(*records)
                self.assertEqual(sessionslib.entrypoint(self.transcript), expected)


class ModelTests(SessionsFixture):
    def check(self, records, expected):
        self.write(*records)
        self.assertEqual(sessionslib.model_id(self.transcript), expected)

    def test_model_source_precedence(self):
        """Adversarial where: the model comes from the wrong source. The
        attachment keeps its `[1m]`, the latest attachment wins, the
        assistant message only backs it up, sidechain assistants never
        count, and a `"model"` key inside a tool input is not the session's
        model."""
        rows = {
            "attachment keeps [1m] while assistant message drops it": (
                [model_line("claude-opus-4-6[1m]"), assistant_line(input_tokens=10, model="claude-opus-4-6")],
                "claude-opus-4-6[1m]"),
            "latest attachment wins": (
                [model_line("claude-opus-4-6"), assistant_line(input_tokens=10),
                 model_line("claude-haiku-4-5"), assistant_line(input_tokens=10)],
                "claude-haiku-4-5"),
            "attachment beats a later assistant message": (
                [model_line("claude-opus-4-6"), assistant_line(input_tokens=10, model="claude-haiku-4-5")],
                "claude-opus-4-6"),
            "assistant message is the fallback": (
                [assistant_line(input_tokens=10, model="claude-sonnet-4-5")], "claude-sonnet-4-5"),
            "latest assistant message wins the fallback": (
                [assistant_line(input_tokens=10, model="claude-sonnet-4-5"),
                 assistant_line(input_tokens=10, model="claude-opus-4-6")], "claude-opus-4-6"),
            "sidechain assistant is skipped": (
                [assistant_line(input_tokens=10, model="claude-opus-4-6"),
                 assistant_line(input_tokens=10, model="claude-haiku-4-5", sidechain=True)], "claude-opus-4-6"),
            "model key in a later tool input is ignored": (
                [assistant_line(input_tokens=10, model="claude-opus-4-6"),
                 tool_use_line("Task", prompt="x", model="haiku")], "claude-opus-4-6"),
            "model text in a user line is ignored": (
                [assistant_line(input_tokens=10, model="claude-opus-4-6"),
                 text_line("user", 'the config has "model":"haiku" in it')], "claude-opus-4-6"),
            "no model anywhere": ([text_line("user", "hi"), assistant_line(input_tokens=10)], None),
        }
        for name, (records, expected) in rows.items():
            with self.subTest(name):
                self.check(records, expected)

    def test_extended_suffix_is_added_only_past_200k_used(self):
        """Adversarial where: the `[1m]` rule is off by one at 200,000, counts
        output tokens, drops a usage component, double-appends, or skips the
        assistant-message fallback."""
        rows = {
            "exactly 200000 used": (120_000 - 1, 80_000, 1, STANDARD_MODEL),
            "200001 used": (120_000, 80_000, 1, STANDARD_MODEL + "[1m]"),
            "cache read alone carries it past": (0, 0, 250_000, STANDARD_MODEL + "[1m]"),
            "cache creation alone carries it past": (0, 250_000, 0, STANDARD_MODEL + "[1m]"),
            "input alone carries it past": (250_000, 0, 0, STANDARD_MODEL + "[1m]"),
        }
        for name, (read, creation, inp, expected) in rows.items():
            with self.subTest(name):
                self.check([model_line(STANDARD_MODEL),
                            assistant_line(input_tokens=inp, cache_creation=creation, cache_read=read, output=500)],
                           expected)
        with self.subTest("id already ends in [1m] is not doubled"):
            self.check([model_line(STANDARD_MODEL + "[1m]"), assistant_line(cache_read=250_000)],
                       STANDARD_MODEL + "[1m]")
        with self.subTest("fallback model id also gets the suffix"):
            self.check([assistant_line(cache_read=250_000, model=STANDARD_MODEL)], STANDARD_MODEL + "[1m]")
        with self.subTest("a sidechain line's size does not trigger it"):
            self.check([model_line(STANDARD_MODEL), assistant_line(cache_read=1_000),
                        assistant_line(cache_read=900_000, sidechain=True)], STANDARD_MODEL)


class UsedTokensTests(SessionsFixture):
    def test_used_is_the_last_main_line_sum_without_output(self):
        """Adversarial where: output tokens are added, a component is dropped,
        a sidechain line or a subagent file supplies the figure, or the first
        line is read instead of the last."""
        self.write(
            assistant_line(input_tokens=1, cache_creation=2, cache_read=3, output=9_999),
            assistant_line(input_tokens=11, cache_creation=2_200, cache_read=33_000, output=999),
            assistant_line(input_tokens=500_000, sidechain=True),
            text_line("user", "next"),
        )
        self.write_subagent("agent-a.jsonl", assistant_line(input_tokens=700_000, sidechain=True))
        self.assertEqual(sessionslib.used_tokens(self.transcript), 35_211)

    def test_no_usage_gives_none(self):
        """Adversarial where: a transcript with no assistant usage reports 0
        or raises; an empty file must behave the same."""
        with self.subTest("only user text"):
            self.write(text_line("user", "hi"))
            self.assertIsNone(sessionslib.used_tokens(self.transcript))
        with self.subTest("only sidechain usage"):
            self.write(assistant_line(input_tokens=5, sidechain=True))
            self.assertIsNone(sessionslib.used_tokens(self.transcript))
        with self.subTest("empty file"):
            self.transcript.write_bytes(b"")
            self.assertIsNone(sessionslib.used_tokens(self.transcript))
            self.assertIsNone(sessionslib.model_id(self.transcript))
            self.assertIsNone(sessionslib.entrypoint(self.transcript))
            self.assertEqual(sessionslib.commit_count(self.transcript), 0)
            self.assertEqual(sessionslib.plan_ids(self.transcript), [])
            self.assertEqual(sessionslib.task_ids(self.transcript), [])


class CommitCountTests(SessionsFixture):
    def test_only_bash_calls_running_git_commit_count(self):
        """Adversarial where: the counter matches `git commit` in prose or in a
        non-Bash tool, misses the `-C <path>` form (quoted path with spaces
        included), matches `git commit-tree` or a word ending in `git`, or
        counts a call once per line instead of per call."""
        rows = {
            "plain commit": ([bash_line('git commit -m "x"')], 1),
            "amend": ([bash_line("git commit --amend --no-edit")], 1),
            "-C path": ([bash_line("git -C plugins/cli commit -m y")], 1),
            "-C quoted path with spaces": ([bash_line('git -C "F:\\my dir\\repo" commit -m y')], 1),
            "after add in one command": ([bash_line('git add a.py && git commit -m "z"')], 1),
            "two separate calls": ([bash_line("git commit -m a"), bash_line("git commit -m b")], 2),
            "status is not a commit": ([bash_line("git status --short")], 0),
            "log is not a commit": ([bash_line("git log --oneline -3")], 0),
            "commit-tree is not git commit": ([bash_line("git commit-tree HEAD^{tree} -m x")], 0),
            "word ending in git": ([bash_line("cat digit commit.txt")], 0),
            "assistant prose": ([text_line("assistant", "Next I will run git commit -m x")], 0),
            "user prose": ([text_line("user", "please git commit this")], 0),
            "non-Bash tool carrying the text": (
                [tool_use_line("Write", file_path="notes.md", content="run git commit"),
                 tool_use_line("Task", prompt="then git -C x commit")], 0),
            "tool result echoing the text": (
                [{"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "t", "content": "hint: git commit -m"}]}}], 0),
        }
        for name, (records, expected) in rows.items():
            with self.subTest(name):
                self.write(*records)
                self.assertEqual(sessionslib.commit_count(self.transcript), expected)

    def test_commits_in_subagent_transcripts_are_added(self):
        """Adversarial where: only the main transcript is read, so commits made
        by builder subagents vanish; or another session's subagents leak in."""
        self.write(bash_line("git commit -m main"))
        self.write_subagent("agent-a.jsonl", bash_line("git commit -m sub1", sidechain=True),
                            bash_line("git -C x commit -m sub2", sidechain=True))
        self.write_subagent("agent-b.jsonl", text_line("user", "git commit in prose"), bash_line("ls", sidechain=True))
        self.write_subagent("agent-c.jsonl", bash_line("git commit -m other", sidechain=True), session_id="bbbb2222")
        self.assertEqual(sessionslib.commit_count(self.transcript), 3)

    def test_subagent_only_commit_counts_when_main_has_none(self):
        """Adversarial where: the count short-circuits to 0 when the main
        transcript has no commit."""
        self.write(text_line("user", "hi"))
        self.write_subagent("agent-a.jsonl", bash_line("git commit -m sub", sidechain=True))
        self.assertEqual(sessionslib.commit_count(self.transcript), 1)


class IdMentionTests(SessionsFixture):
    def test_plan_and_task_ids_are_whole_distinct_sorted_mentions(self):
        """Adversarial where: `TASK-1400` is read as `TASK-140`, a file name
        like `PLAN-020-clone-old-sessions.md` is missed, repeats are not
        collapsed, order follows first mention, plan and task ids bleed into
        each other, or ids injected by hook attachments count as mentions."""
        rows = {
            "user string and list content, assistant text": (
                [text_line("user", "Build TASK-141 first"),
                 {"type": "user", "message": {"role": "user",
                                              "content": [{"type": "text", "text": "then TASK-140 per PLAN-021"}]}},
                 text_line("assistant", "see .compass/plans/PLAN-020-clone-old-sessions.md")],
                ["PLAN-020", "PLAN-021"], ["TASK-140", "TASK-141"]),
            "four digit id is not truncated": (
                [text_line("user", "TASK-1400 and PLAN-0201")], ["PLAN-0201"], ["TASK-1400"]),
            "repeats collapse": (
                [text_line("user", "TASK-140 TASK-140"), text_line("assistant", "done TASK-140 PLAN-020 PLAN-020")],
                ["PLAN-020"], ["TASK-140"]),
            "attachment text is not a mention": (
                [{"type": "attachment", "attachment": {"type": "hook_success", "content": "TASK-999 PLAN-099"}},
                 text_line("user", "hi")], [], []),
            "no mention": ([text_line("user", "hello TASKS and PLAN B")], [], []),
        }
        for name, (records, plans, tasks) in rows.items():
            with self.subTest(name):
                self.write(*records)
                self.assertEqual(sessionslib.plan_ids(self.transcript), plans)
                self.assertEqual(sessionslib.task_ids(self.transcript), tasks)


class IsActiveTests(SessionsFixture):
    def test_active_means_modified_within_ten_minutes(self):
        """Adversarial where: the window is not 10 minutes (off by a unit) or
        is measured from the wrong end, so a recent file reads as idle or an
        old one as live."""
        self.write(text_line("user", "hi"))
        rows = {
            "five minutes ago": (300, True),
            "just inside the window": (599, True),
            "just outside the window": (601, False),
            "an hour ago": (3_600, False),
        }
        for name, (age, expected) in rows.items():
            with self.subTest(name):
                os.utime(self.transcript, (NOW - age, NOW - age))
                self.assertIs(sessionslib.is_active(self.transcript, now=NOW), expected)

    def test_default_now_is_the_current_time(self):
        """Adversarial where: omitting `now` compares against a fixed value, so
        a file written a moment ago reads as idle."""
        self.write(text_line("user", "hi"))
        self.assertIs(sessionslib.is_active(self.transcript), True)
        os.utime(self.transcript, (1_000_000_000, 1_000_000_000))
        self.assertIs(sessionslib.is_active(self.transcript), False)


class MalformedLineTests(SessionsFixture):
    def test_unparseable_and_misshapen_lines_are_skipped(self):
        """Adversarial where: one bad line among good ones aborts the read or
        zeroes the result. Covers invalid JSON, non-object JSON, invalid
        UTF-8, blank lines, records with wrong-typed fields, and a final
        line cut off mid-write that would otherwise be a commit."""
        good_before = [dict(text_line("user", "Work on TASK-140 in PLAN-020"), entrypoint="sdk-cli"),
                       model_line(STANDARD_MODEL), bash_line("git commit -m a")]
        good_after = [assistant_line(input_tokens=4, cache_creation=5, cache_read=6), bash_line("git commit -m b")]
        bad = [
            b"{not json at all",
            b"[1, 2, 3]", b"null", b"42", b'"just a string"',
            b"",
            b"\xff\xfe\x00 garbage \x80",
            json.dumps({"type": "assistant", "message": "oops"}).encode(),
            json.dumps({"type": "assistant", "message": {"content": "text", "usage": None}}).encode(),
            json.dumps({"type": "assistant", "message": {"content": [None, 5, "x",
                        {"type": "tool_use", "name": "Bash", "input": "not-a-dict"},
                        {"type": "tool_use", "name": "Bash", "input": {"command": None}}]}}).encode(),
            json.dumps({"type": "attachment", "attachment": "flat"}).encode(),
            json.dumps({"type": "attachment", "attachment": {"type": "model", "identity": None}}).encode(),
        ]
        truncated = b'{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"git comm'
        with open(self.transcript, "wb") as fh:
            for rec in good_before:
                fh.write(json.dumps(rec).encode() + b"\n")
            for line in bad:
                fh.write(line + b"\n")
            for rec in good_after:
                fh.write(json.dumps(rec).encode() + b"\n")
            fh.write(truncated)
        self.assertEqual(sessionslib.model_id(self.transcript), STANDARD_MODEL)
        self.assertEqual(sessionslib.used_tokens(self.transcript), 15)
        self.assertEqual(sessionslib.commit_count(self.transcript), 2)
        self.assertEqual(sessionslib.entrypoint(self.transcript), "sdk-cli")
        self.assertEqual(sessionslib.plan_ids(self.transcript), ["PLAN-020"])
        self.assertEqual(sessionslib.task_ids(self.transcript), ["TASK-140"])

    def test_a_bad_line_inside_a_subagent_transcript_does_not_hide_its_commit(self):
        """Adversarial where: a subagent file with one garbage line is dropped
        whole, losing the commit on the next line."""
        self.write(text_line("user", "hi"))
        side =self.root / self.session_id / "subagents" / "agent-a.jsonl"
        side.parent.mkdir(parents=True)
        side.write_bytes(b"{broken\n" + json.dumps(bash_line("git commit -m ok", sidechain=True)).encode() + b"\n")
        self.assertEqual(sessionslib.commit_count(self.transcript), 1)


class ReadOnlyTests(SessionsFixture):
    def test_reading_never_changes_a_transcript_or_its_folder(self):
        """Adversarial where: a reader opens a transcript for write or append,
        touches its mtime, or drops lock or cache files beside it. The files
        are marked read-only so a write-mode open fails outright."""
        self.write(dict(text_line("user", "TASK-140 PLAN-020"), entrypoint="cli"), model_line(STANDARD_MODEL),
                   assistant_line(input_tokens=1, cache_read=300_000), bash_line("git commit -m a"))
        sub = self.write_subagent("agent-a.jsonl", bash_line("git commit -m b", sidechain=True))
        paths = [self.transcript, sub]
        old = NOW - 100_000
        for path in paths:
            os.utime(path, (old, old))
            os.chmod(path, stat.S_IREAD)
            self.addCleanup(os.chmod, path, stat.S_IWRITE | stat.S_IREAD)

        def snapshot():
            return ({p: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in paths},
                    sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")))

        before = snapshot()
        sessionslib.entrypoint(self.transcript)
        sessionslib.model_id(self.transcript)
        sessionslib.used_tokens(self.transcript)
        sessionslib.commit_count(self.transcript)
        sessionslib.plan_ids(self.transcript)
        sessionslib.task_ids(self.transcript)
        sessionslib.subagent_transcripts(self.transcript)
        sessionslib.is_active(self.transcript, now=NOW)
        self.assertEqual(snapshot(), before)


class CommandRegistrationTests(unittest.TestCase):
    def test_sessions_clone_and_retention_are_registered(self):
        """Adversarial where: a new command is missing from COMMAND_SPECS, so
        `compass <name>` answers 'unknown command' instead of dispatching, or
        is registered with an empty help line."""
        specs = dict(maincli.COMMAND_SPECS)
        for name in ("sessions", "clone", "retention"):
            with self.subTest(name):
                self.assertIn(name, specs)
                self.assertTrue(specs[name].strip())
                self.assertIn(name, maincli.VALID_COMMANDS)


if __name__ == "__main__":
    unittest.main()
