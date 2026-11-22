"""Tests the five session-state readers in `sessionslib`.

Adversarial themes: classification by prefix (a word inside another command is
not a test run), kind precedence (`edited` beats `read`), record-shape drift
(string where a list belongs, string `toolUseResult`), and the never-raise
contract (truncated, binary, non-object and absent input).

Public API under test. `transcript` is a str or Path to a session's main
`<session-id>.jsonl`. Subagent transcripts sit beside it at
`<session-id>/subagents/agent-*.jsonl`. Each record's index is the 0-based
position of its line in the file. No reader raises: an unreadable path or an
unreadable line yields what the readable remainder holds.

    touched_files(transcript) -> iterable of (path, kind, last_index)
        path: `input.file_path` verbatim. kind: "edited" for Edit, Write and
        MultiEdit, "read" for Read; "edited" wins when a path has both.
        One entry per path. last_index: index of the last main-transcript
        record that touched the path. Entries come in ascending last_index.
        Sidechain records in the main file and every subagent file count.
    last_human_request(transcript) -> str | None
        Content of the last record with string content and
        `origin.kind == "human"`, not `isMeta`, not `isCompactSummary`.
        Main transcript only.
    question_answers(transcript) -> iterable of (question, answer)
        From each AskUserQuestion result's `toolUseResult`: one pair per
        entry of `questions`, in order, answer taken from `answers[question]`.
        Main transcript only; results come in file order.
    last_test_run(transcript) -> (command, tail_lines) | None
        The last Bash tool call whose command starts with a test runner
        (pytest, python -m pytest, npm test, npx vitest, cargo test, go test)
        after any `cd ... &&` prefix. tail_lines is a list of the last 8
        lines (str.splitlines) of the paired result's `toolUseResult.stdout`.
        The result is paired to its call by tool_use_id. Main transcript only.
    compact_boundaries(transcript) -> iterable of (index, trigger)
        One pair per `system` record with subtype `compact_boundary`, trigger
        from `compactMetadata.trigger`, in file order. Main transcript only.
"""

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sessionslib as sl  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "transcripts"
STATE = FIXTURES / "state-session.jsonl"

# Record indices in state-session.jsonl.
IDX = {
    "alpha_edit": 5,
    "gamma_write": 7,
    "delta_multi": 9,
    "beta_last_read": 11,
    "side_edit": 37,
    "boundary_auto": 24,
    "boundary_manual": 32,
}


def use(tid, name, inp):
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}],
        },
    }


def bash_result(tid, stdout):
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tid, "content": stdout}],
        },
        "toolUseResult": {"stdout": stdout, "stderr": ""},
    }


def human(text):
    return {
        "type": "user",
        "message": {"role": "user", "content": text},
        "origin": {"kind": "human"},
    }


def bash_pair(tid, command, stdout="ok\n"):
    return [use(tid, "Bash", {"command": command}), bash_result(tid, stdout)]


def write_lines(path, lines):
    """Writes dicts as JSON lines and strs verbatim, one per line."""
    text = "\n".join(l if isinstance(l, str) else json.dumps(l) for l in lines)
    Path(path).write_text(text + "\n", encoding="utf-8", newline="\n")
    return Path(path)


def fixture_lines():
    return STATE.read_text(encoding="utf-8").splitlines()



def _copy_side_folder(target):
    """Copy the fixture's subagents side folder beside a transcript copy, so
    the copy reads the same subagent records as the fixture."""
    import shutil

    shutil.copytree(STATE.with_suffix("") / "subagents", target.with_suffix("") / "subagents")

class TouchedFilesTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_fixture_lists_each_path_once_with_winning_kind_in_index_order(self):
        """Adversarial where: a path read then edited, or read twice, is listed
        twice or as `read`; Grep and Bash mentions are listed as touches."""
        got = list(sl.touched_files(STATE))
        by_path = {p: (k, i) for p, k, i in got}
        self.assertEqual(len(got), len(by_path), "one entry per path")
        self.assertEqual(
            {p: k for p, (k, _) in by_path.items()},
            {
                "src/alpha.py": "edited",
                "src/beta.py": "read",
                "src/gamma.py": "edited",
                "src/delta.py": "edited",
                "src/side.py": "edited",
                "src/theta.py": "read",
                "src/sub_only.py": "edited",
            },
        )
        self.assertEqual(by_path["src/alpha.py"][1], IDX["alpha_edit"])
        self.assertEqual(by_path["src/gamma.py"][1], IDX["gamma_write"])
        self.assertEqual(by_path["src/delta.py"][1], IDX["delta_multi"])
        self.assertEqual(by_path["src/beta.py"][1], IDX["beta_last_read"])
        self.assertEqual(by_path["src/side.py"][1], IDX["side_edit"])
        main_indices = [
            i for p, k, i in got if p not in ("src/theta.py", "src/sub_only.py")
        ]
        self.assertEqual(main_indices, sorted(main_indices))

    def test_edit_then_later_read_stays_edited_and_listed_once(self):
        """Adversarial where: a later Read overwrites the earlier `edited`
        kind, so a file the session changed shows as only read."""
        t = write_lines(
            self.tmp / "s.jsonl",
            [
                use("a", "Edit", {"file_path": "src/one.py"}),
                use("b", "Read", {"file_path": "src/one.py"}),
                use("c", "Write", {"file_path": "src/two.py"}),
                use("d", "Read", {"file_path": "src/two.py"}),
            ],
        )
        got = {p: k for p, k, _ in sl.touched_files(t)}
        self.assertEqual(got, {"src/one.py": "edited", "src/two.py": "edited"})
        self.assertEqual(len(list(sl.touched_files(t))), 2)

    def test_subagent_file_edit_is_listed_and_edit_there_beats_main_read(self):
        """Adversarial where: only the main transcript is scanned, so a path a
        subagent edited is missing, or kind precedence ignores the subagent."""
        main = write_lines(
            self.tmp / "s9.jsonl", [use("a", "Read", {"file_path": "src/shared.py"})]
        )
        sub = self.tmp / "s9" / "subagents"
        sub.mkdir(parents=True)
        write_lines(
            sub / "agent-x1.jsonl",
            [
                use("b", "Edit", {"file_path": "src/shared.py"}),
                use("c", "Write", {"file_path": "src/fresh.py"}),
            ],
        )
        got = {p: k for p, k, _ in sl.touched_files(main)}
        self.assertEqual(got, {"src/shared.py": "edited", "src/fresh.py": "edited"})

    def test_str_and_path_arguments_agree(self):
        """Adversarial where: a reader that joins or opens a str argument
        differently from a Path argument."""
        self.assertEqual(
            list(sl.touched_files(str(STATE))), list(sl.touched_files(STATE))
        )
        self.assertTrue(list(sl.touched_files(str(STATE))))


class LastHumanRequestTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_fixture_skips_meta_notification_and_summary_after_prompt(self):
        """Adversarial where: a task notification, a peer isMeta record or a
        compact summary arriving after the human's prompt replaces it."""
        self.assertEqual(sl.last_human_request(STATE), "Now also update gamma")

    def test_non_qualifying_user_records_never_replace_the_request(self):
        """Adversarial where: any of these shapes passes the qualifier and
        replaces the human's prompt: tool result, list content, no origin,
        origin human but isMeta, origin human but isCompactSummary."""
        rows = {
            "tool_result": bash_result("t", "output"),
            "list_content": {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "later"}],
                },
                "origin": {"kind": "human"},
            },
            "no_origin": {
                "type": "user",
                "message": {"role": "user", "content": "later"},
            },
            "peer_origin": {
                "type": "user",
                "message": {"role": "user", "content": "later"},
                "origin": {"kind": "peer"},
            },
            "meta_human": dict(human("later"), isMeta=True),
            "summary_human": dict(human("later"), isCompactSummary=True),
        }
        for name, row in rows.items():
            with self.subTest(name=name):
                t = write_lines(self.tmp / f"{name}.jsonl", [human("the request"), row])
                self.assertEqual(sl.last_human_request(t), "the request")

    def test_last_qualifying_record_wins_and_none_when_absent(self):
        """Adversarial where: the first human record is returned instead of
        the last, or a session with no human record raises instead of None."""
        t = write_lines(self.tmp / "two.jsonl", [human("first"), human("second")])
        self.assertEqual(sl.last_human_request(t), "second")
        none = write_lines(self.tmp / "none.jsonl", [bash_result("t", "x")])
        self.assertIsNone(sl.last_human_request(none))

    def test_subagent_prompt_does_not_replace_the_request(self):
        """Adversarial where: a subagent file's opening prompt (string content,
        sidechain) is read as the human's request."""
        main = write_lines(self.tmp / "s7.jsonl", [human("the request")])
        sub = self.tmp / "s7" / "subagents"
        sub.mkdir(parents=True)
        write_lines(
            sub / "agent-a.jsonl", [dict(human("subagent prompt"), isSidechain=True)]
        )
        self.assertEqual(sl.last_human_request(main), "the request")


class QuestionAnswersTests(unittest.TestCase):
    def test_fixture_pairs_follow_question_order_and_skip_string_result(self):
        """Adversarial where: a declined question (string toolUseResult) raises
        or yields a pair, or a multi-select answer is split or re-keyed."""
        self.assertEqual(
            list(sl.question_answers(STATE)),
            [
                ("Which layout?", "Flat (Recommended)"),
                ("Which checks run?", "Unit, Lint"),
            ],
        )

    def test_answers_from_separate_calls_come_in_file_order(self):
        """Adversarial where: pairs are grouped by dict hash order or reversed
        across calls rather than following the transcript."""
        import tempfile

        def ask(q, a):
            return {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": q}],
                },
                "toolUseResult": {"questions": [{"question": q}], "answers": {q: a}},
            }

        with tempfile.TemporaryDirectory() as d:
            t = write_lines(
                Path(d) / "s.jsonl", [ask("zeta?", "z"), ask("alpha?", "a")]
            )
            self.assertEqual(
                list(sl.question_answers(t)), [("zeta?", "z"), ("alpha?", "a")]
            )


class LastTestRunTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def run_of(self, name, command, stdout="ok\n"):
        t = write_lines(self.tmp / f"{name}.jsonl", bash_pair("t1", command, stdout))
        return sl.last_test_run(t)

    def test_fixture_returns_the_runner_call_not_the_commit_or_heredoc(self):
        """Adversarial where: `git commit -m "fix pytest"` or a heredoc whose
        body holds `pytest` later in the file is taken as the last test run,
        or the subagent file's pytest replaces the main transcript's."""
        command, tail = sl.last_test_run(STATE)
        self.assertEqual(
            command, "cd plugin/cli && python -m pytest -q tests/test_alpha.py"
        )
        self.assertEqual(
            tail,
            [
                "tests/test_alpha.py line3",
                "tests/test_alpha.py line4",
                "tests/test_alpha.py line5",
                "tests/test_alpha.py line6",
                "tests/test_alpha.py line7",
                "",
                "FAILED tests/test_alpha.py::test_one - assert 1 == 2",
                "1 failed, 6 passed in 0.10s",
            ],
        )

    def test_runner_prefix_classification(self):
        """Adversarial where: the runner word anywhere in the command, not
        only at its start after a `cd ... &&` prefix, counts as a test run."""
        runs = [
            "pytest",
            "pytest -q tests/x.py",
            "python -m pytest -q 2>&1 | tail -3",
            "npm test",
            "npx vitest run",
            "cargo test --release",
            "go test ./...",
            "cd plugin/cli && pytest -q",
            "cd a && cd b && python -m pytest",
        ]
        not_runs = [
            'git commit -m "fix pytest"',
            "echo pytest",
            "grep -rn pytest tests",
            "pip install pytest",
            "cat > t.sh <<'END'\npytest -q\nEND",
            "cat > t.sh <<'END'\ncd x && pytest\nEND",
            "git status && pytest",
            "python script.py --runner pytest",
            "ls",
        ]
        for i, cmd in enumerate(runs):
            with self.subTest(run=cmd):
                got = self.run_of(f"run{i}", cmd)
                self.assertIsNotNone(got)
                self.assertEqual(got[0], cmd)
        for i, cmd in enumerate(not_runs):
            with self.subTest(not_run=cmd):
                self.assertIsNone(self.run_of(f"no{i}", cmd))

    def test_tail_is_the_last_eight_lines_at_the_boundary(self):
        """Adversarial where: an off-by-one in the tail (7 or 9 lines), a
        short output padded or raising, or an empty stdout raising."""
        rows = {
            "nine": ([f"l{i}" for i in range(1, 10)], [f"l{i}" for i in range(2, 10)]),
            "eight": ([f"l{i}" for i in range(1, 9)], [f"l{i}" for i in range(1, 9)]),
            "seven": ([f"l{i}" for i in range(1, 8)], [f"l{i}" for i in range(1, 8)]),
            "empty": ([], []),
        }
        for name, (lines, expected) in rows.items():
            with self.subTest(name=name):
                got = self.run_of(
                    name, "pytest", "\n".join(lines) + ("\n" if lines else "")
                )
                self.assertEqual(got, ("pytest", expected))

    def test_result_is_paired_to_its_call_by_id_not_by_position(self):
        """Adversarial where: results arriving out of order hand the last
        run the other run's stdout; a later non-test call replaces the run."""
        t = write_lines(
            self.tmp / "ooo.jsonl",
            [
                use("a", "Bash", {"command": "pytest first"}),
                use("b", "Bash", {"command": "go test ./..."}),
                bash_result("b", "from-go"),
                bash_result("a", "from-pytest"),
                *bash_pair("c", "ls -la", "listing"),
            ],
        )
        self.assertEqual(sl.last_test_run(t), ("go test ./...", ["from-go"]))

    def test_session_without_a_test_run_is_none(self):
        """Adversarial where: a session with only non-test Bash calls raises
        or returns an empty tuple instead of None."""
        t = write_lines(self.tmp / "none.jsonl", bash_pair("a", "ls"))
        self.assertIsNone(sl.last_test_run(t))


class CompactBoundariesTests(unittest.TestCase):
    def test_fixture_yields_index_and_trigger_in_file_order(self):
        """Adversarial where: the summary record after a boundary is counted as
        a boundary, or the manual and auto triggers are conflated."""
        self.assertEqual(
            list(sl.compact_boundaries(STATE)),
            [(IDX["boundary_auto"], "auto"), (IDX["boundary_manual"], "manual")],
        )


class NeverRaiseTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def call_all(self, t):
        return (
            list(sl.touched_files(t)),
            sl.last_human_request(t),
            list(sl.question_answers(t)),
            sl.last_test_run(t),
            list(sl.compact_boundaries(t)),
        )

    def test_absent_empty_and_directory_paths_yield_nothing(self):
        """Adversarial where: a missing transcript, an empty file or a
        directory path raises instead of yielding empty results."""
        empty = self.tmp / "empty.jsonl"
        empty.write_bytes(b"")
        folder = self.tmp / "folder"
        folder.mkdir()
        for name, p in {
            "absent": self.tmp / "absent.jsonl",
            "empty": empty,
            "directory": folder,
        }.items():
            with self.subTest(name=name):
                self.assertEqual(self.call_all(p), ([], None, [], None, []))

    def test_truncated_last_line_leaves_every_reader_result_unchanged(self):
        """Adversarial where: a half-written final line, as left by a crashed
        session, aborts the scan and drops the records before it."""
        whole = self.call_all(STATE)
        cut = self.tmp / "cut.jsonl"
        _copy_side_folder(cut)
        cut.write_bytes(
            STATE.read_bytes()
            + b'{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_pa'
        )
        self.assertEqual(self.call_all(cut), whole)

    def test_crlf_line_endings_leave_results_unchanged(self):
        """Adversarial where: a transcript saved with CRLF endings leaves a
        trailing carriage return that breaks line-level parsing."""
        whole = self.call_all(STATE)
        crlf = self.tmp / "crlf.jsonl"
        _copy_side_folder(crlf)
        crlf.write_bytes(STATE.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(self.call_all(crlf), whole)

    def test_hostile_records_around_good_ones_yield_the_good_ones(self):
        """Adversarial where: one malformed record among valid ones (non-object
        JSON, string message, string toolUseResult, non-dict tool input, null
        content items, boundary without metadata, bad bytes) aborts a reader
        or hides the valid records."""
        hostile = [
            "null",
            "[1, 2]",
            '"a bare string"',
            "5",
            {"type": "assistant", "message": "message as a string"},
            {"type": "assistant", "message": None},
            {"type": "assistant", "message": {"content": "content as a string"}},
            {
                "type": "assistant",
                "message": {
                    "content": [
                        None,
                        "x",
                        5,
                        {"type": "tool_use", "name": "Edit", "input": "not a dict"},
                        {"type": "tool_use", "name": "Edit", "input": {"file_path": 5}},
                        {"type": "tool_use", "name": "Edit"},
                        {"type": "tool_use", "name": "Bash", "input": {"command": 7}},
                    ]
                },
            },
            {
                "type": "user",
                "message": {"content": [{"type": "tool_result", "tool_use_id": "x"}]},
                "toolUseResult": "a string result",
            },
            {
                "type": "user",
                "message": {"content": [{"type": "tool_result", "tool_use_id": "x"}]},
                "toolUseResult": {"questions": "not a list", "answers": [1]},
            },
            {
                "type": "user",
                "message": {"content": [{"type": "tool_result", "tool_use_id": "x"}]},
                "toolUseResult": {
                    "questions": [1, {"question": 5}],
                    "answers": {"a": 1},
                },
            },
            {"type": "system", "subtype": "compact_boundary"},
            {
                "type": "system",
                "subtype": "compact_boundary",
                "compactMetadata": "text",
            },
        ]
        good_start = len(hostile)
        good = [
            human("good request"),
            use("g1", "Edit", {"file_path": "src/good.py"}),
            *bash_pair("g2", "pytest -q", "1 passed\n"),
            use("g3", "AskUserQuestion", {"questions": []}),
            {
                "type": "user",
                "message": {"content": [{"type": "tool_result", "tool_use_id": "g3"}]},
                "toolUseResult": {
                    "questions": [{"question": "Q?"}],
                    "answers": {"Q?": "A"},
                },
            },
            {
                "type": "system",
                "subtype": "compact_boundary",
                "compactMetadata": {"trigger": "manual"},
            },
        ]
        t = write_lines(self.tmp / "hostile.jsonl", hostile + good)
        with open(t, "ab") as f:
            f.write(b"{not json\n\xff\xfe\x00garbage bytes\n")
        files, request, answers, run, boundaries = self.call_all(t)
        self.assertIn(("src/good.py", "edited", good_start + 1), files)
        self.assertEqual(request, "good request")
        self.assertIn(("Q?", "A"), answers)
        self.assertEqual(run, ("pytest -q", ["1 passed"]))
        self.assertIn((good_start + 6, "manual"), boundaries)


class ImplementationBranchTests(unittest.TestCase):
    """Branches and helpers of the readers that the public contract does not name."""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def sub(self, main, name, lines):
        folder = main.with_suffix("") / "subagents"
        folder.mkdir(parents=True, exist_ok=True)
        return write_lines(folder / name, lines)

    def test_subagent_only_paths_follow_main_paths_in_file_name_order(self):
        """Adversarial where: entries sort by raw index across files, so a
        subagent path with a small index lands before a main-transcript path,
        or subagent files are visited in directory order not by name."""
        main = write_lines(
            self.tmp / "s.jsonl",
            [
                use("a", "Read", {"file_path": "m1"}),
                "",
                "",
                "",
                "",
                use("b", "Read", {"file_path": "m2"}),
            ],
        )
        self.sub(main, "agent-b.jsonl", [use("c", "Edit", {"file_path": "sB"})])
        self.sub(
            main,
            "agent-a.jsonl",
            ["", "", "", "", "", "", use("d", "Edit", {"file_path": "sA"})],
        )
        self.assertEqual(
            [p for p, _, _ in sl.touched_files(main)], ["m1", "m2", "sA", "sB"]
        )

    def test_subagent_touch_changes_kind_but_not_the_main_last_index(self):
        """Adversarial where: a subagent record's index overwrites the index of
        a path the main transcript also touched."""
        main = write_lines(
            self.tmp / "s.jsonl",
            [
                use("a", "Read", {"file_path": "shared"}),
                "",
                "",
                use("b", "Read", {"file_path": "other"}),
            ],
        )
        self.sub(
            main,
            "agent-a.jsonl",
            [""] * 9 + [use("c", "Edit", {"file_path": "shared"})],
        )
        got = {p: (k, i) for p, k, i in sl.touched_files(main)}
        self.assertEqual(got["shared"], ("edited", 0))

    def test_side_folder_ignores_files_that_are_not_agent_transcripts(self):
        """Adversarial where: the side-folder glob admits `other.jsonl`, a
        `.meta.json` sibling, or a directory named like a transcript."""
        main = write_lines(self.tmp / "s.jsonl", [use("a", "Read", {"file_path": "m"})])
        self.sub(main, "other.jsonl", [use("b", "Edit", {"file_path": "other"})])
        self.sub(main, "agent-z.meta.json", [use("b", "Edit", {"file_path": "meta"})])
        (main.with_suffix("") / "subagents" / "agent-dir.jsonl").mkdir()
        self.assertEqual([p for p, _, _ in sl.touched_files(main)], ["m"])

    def test_untracked_tool_names_and_empty_paths_are_not_touches(self):
        """Adversarial where: any tool carrying `file_path` (Grep, NotebookEdit)
        counts, or an empty `file_path` is listed as a path."""
        t = write_lines(
            self.tmp / "s.jsonl",
            [
                use("a", "Grep", {"file_path": "g.py"}),
                use("b", "NotebookEdit", {"file_path": "n.ipynb"}),
                use("c", "Edit", {"file_path": ""}),
                use("d", "Edit", {"file_path": "real.py"}),
            ],
        )
        self.assertEqual(list(sl.touched_files(t)), [("real.py", "edited", 3)])

    def test_record_index_counts_blank_garbage_and_unicode_separator_lines(self):
        """Adversarial where: indexing counts only parsed records, or a raw
        U+2028 / U+0085 inside a record splits it into two lines."""
        raw = json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "a b\u0085c"}]},
            },
            ensure_ascii=False,
        )
        t = write_lines(
            self.tmp / "s.jsonl",
            ["", "   ", "{bad", raw, use("a", "Edit", {"file_path": "x.py"})],
        )
        self.assertEqual(list(sl.touched_files(t)), [("x.py", "edited", 4)])

    def test_cd_prefix_forms_and_non_prefix_separators(self):
        """Adversarial where: the `cd <dir> &&` prefix fails on quoted or
        spaced directories, on `&&` without spaces or followed by a newline, or
        a `;` separator or a name longer than the runner counts as a run."""
        runs = [
            'cd "dir with space" && pytest',
            "cd 'dir with space'&&pytest",
            "cd a&&cd b&&pytest -q",
            "cd a &&\npytest",
            "  pytest",
            "python3 -m pytest",
        ]
        not_runs = [
            "cd a; pytest",
            "pytest-xdist",
            "pytestx",
            "cd a && echo pytest",
            "cd a ||pytest",
        ]
        for i, cmd in enumerate(runs):
            with self.subTest(run=cmd):
                t = write_lines(self.tmp / f"r{i}.jsonl", bash_pair("t", cmd))
                self.assertEqual(sl.last_test_run(t)[0], cmd)
        for i, cmd in enumerate(not_runs):
            with self.subTest(not_run=cmd):
                t = write_lines(self.tmp / f"n{i}.jsonl", bash_pair("t", cmd))
                self.assertIsNone(sl.last_test_run(t))

    def test_long_cd_chains_classify_quickly(self):
        """Adversarial where: the `cd` prefix pattern backtracks without bound
        on a long chain that never reaches a runner."""
        import time

        for cmd in [
            "cd a&&" * 4000 + "ls",
            "cd a && " * 4000 + "ls",
            "cd " + "&&" * 5000 + "x",
        ]:
            t = write_lines(self.tmp / "long.jsonl", bash_pair("t", cmd))
            started = time.monotonic()
            self.assertIsNone(sl.last_test_run(t))
            self.assertLess(time.monotonic() - started, 2.0)

    def test_runner_in_a_non_bash_tool_call_is_not_a_run(self):
        """Adversarial where: any tool call with a `command` input counts."""
        t = write_lines(self.tmp / "s.jsonl", [use("a", "Task", {"command": "pytest"})])
        self.assertIsNone(sl.last_test_run(t))

    def test_stdout_falls_back_to_result_content_and_handles_crlf(self):
        """Adversarial where: a non-text `toolUseResult.stdout` yields an empty
        tail instead of the block content, or CRLF output leaves a carriage
        return on lines."""

        def result(tool_use_result, content="c1\nc2"):
            return {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "a", "content": content}
                    ]
                },
                "toolUseResult": tool_use_result,
            }

        rows = {
            "stdout_none": (result({"stdout": None}), ["c1", "c2"]),
            "string_result": (result("plain string"), ["c1", "c2"]),
            "crlf": (result({"stdout": "l1\r\nl2\r\n"}), ["l1", "l2"]),
        }
        for name, (record, tail) in rows.items():
            with self.subTest(name=name):
                t = write_lines(
                    self.tmp / f"{name}.jsonl",
                    [use("a", "Bash", {"command": "pytest"}), record],
                )
                self.assertEqual(sl.last_test_run(t), ("pytest", tail))

    def test_run_without_a_result_yet_has_an_empty_tail_not_an_earlier_one(self):
        """Adversarial where: a later run that has no result inherits the
        output of the earlier run."""
        t = write_lines(
            self.tmp / "s.jsonl",
            [
                *bash_pair("a", "pytest first", "old\n"),
                use("b", "Bash", {"command": "pytest second"}),
            ],
        )
        self.assertEqual(sl.last_test_run(t), ("pytest second", []))

    def test_unanswered_and_non_text_answers_are_skipped_individually(self):
        """Adversarial where: one unanswered or non-text answer drops the
        whole call's pairs, or an answer key absent from `questions` is listed."""
        t = write_lines(
            self.tmp / "s.jsonl",
            [
                {
                    "type": "user",
                    "toolUseResult": {
                        "questions": [
                            {"question": "Q1"},
                            {"question": "Q2"},
                            {"question": "Q3"},
                        ],
                        "answers": {"Q1": "a", "Q3": 5, "Extra": "x"},
                    },
                }
            ],
        )
        self.assertEqual(list(sl.question_answers(t)), [("Q1", "a")])

    def test_boundary_trigger_shapes_and_record_type(self):
        """Adversarial where: a non-text trigger is passed through, a record of
        another type carrying the subtype counts, or a subagent file's
        boundary is merged into the main transcript's list."""
        main = write_lines(
            self.tmp / "s.jsonl",
            [
                {
                    "type": "system",
                    "subtype": "compact_boundary",
                    "compactMetadata": {"trigger": 5},
                },
                {"type": "user", "subtype": "compact_boundary"},
                {"type": "system", "subtype": "other"},
                {
                    "type": "system",
                    "subtype": "compact_boundary",
                    "compactMetadata": {},
                },
            ],
        )
        self.sub(
            main,
            "agent-a.jsonl",
            [
                {
                    "type": "system",
                    "subtype": "compact_boundary",
                    "compactMetadata": {"trigger": "auto"},
                }
            ],
        )
        self.assertEqual(list(sl.compact_boundaries(main)), [(0, None), (3, None)])

    def test_origin_that_is_not_an_object_never_qualifies(self):
        """Adversarial where: `origin` written as the bare string "human" is
        accepted by a truthiness or substring check."""
        t = write_lines(
            self.tmp / "s.jsonl",
            [
                human("the request"),
                {"type": "user", "message": {"content": "later"}, "origin": "human"},
            ],
        )
        self.assertEqual(sl.last_human_request(t), "the request")


if __name__ == "__main__":
    unittest.main()
