"""Tests for `compass session-state`, the state block printed around a
compaction and the handoff's mechanical sections.

Interface assumed (the builder implements exactly this):

    commands/session_state.py: `run(args) -> int`, prints to stdout, registered
    in `maincli.COMMAND_SPECS` as "session-state". Always returns 0.

    The project root is `CLAUDE_PROJECT_DIR`'s folder (the folder holding the
    `.compass` vault); git runs there. Paths print relative to it, with
    forward slashes.

    `--format block` (default). First line holds "Compass session state".
    Every section is a `## <name>` heading followed by its lines, in this
    order, a section with nothing in it left out:
        ## Last human request      the text, cut at 500 characters
        ## Open tasks              `- [ ]` lines of .compass/active.md, 25
        ## Decisions               question answers "Q: A" (8) then
                                   `<doc-stem>/D-NN: <text>` lines (20, each
                                   at most 140 characters after the "- ")
        ## Files edited            40, most recent first
        ## Files read              files read and not edited, 25
        ## Uncommitted changes     `git status --short` outside .compass/, 30
        ## Last test run           the command and the last 8 stdout lines
        ## Branch                  branch name and short commit hash
    A list over its cap ends with `... and N more`. Over the 8,000-character
    budget the last sections are dropped first, so a present section always
    has every earlier non-empty section present.

    `--format handoff` prints only `## Tasks`, `## Recent Changes`,
    `## Decisions` and `## Uncommitted Changes`; each edited file is
    `` `path` `` or `` `path:line` `` when its Edit result carries a
    structuredPatch start line.

    `--transcript PATH`, else `<transcripts_dir>/<CLAUDE_CODE_SESSION_ID>.jsonl`,
    else the newest `*.jsonl` of `transcripts_dir`.

    `--hook` reads one JSON event from stdin (and only then). SessionStart
    with source `compact` prints one JSON object
    `{"hookSpecificOutput": {"hookEventName": "SessionStart",
    "additionalContext": <block>}}`; PreCompact prints plain text under 1,500
    characters. Anything else prints nothing.

Adversarial themes: budget drops that cut the wrong end, caps off by one,
read-versus-edited spec attribution, stdin read without the flag, hook
modes leaking into agents, and every degraded input exiting 0.
"""

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

CLI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLI_DIR))

import maincli  # noqa: E402
import sessionslib  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "transcripts"
STATE_FIXTURE = FIXTURES / "state-session.jsonl"
SESSION_ID = "11111111-2222-3333-4444-555555555555"

ORDER = [
    "Last human request", "Open tasks", "Decisions", "Files edited", "Files read",
    "Uncommitted changes", "Last test run", "Branch",
]
HANDOFF_HEADINGS = ["Tasks", "Recent Changes", "Decisions", "Uncommitted Changes"]

SPEC_TEXT = """---
title: Foo
---

# Foo

## Decisions

- **D-01:** The first decision of foo.
- **D-02:** The second decision of foo.
"""


def user_human(text):
    return {"type": "user", "message": {"role": "user", "content": text}, "origin": {"kind": "human"}}


def tool_call(call_id, name, tool_input):
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": call_id, "name": name, "input": tool_input}]}}


def tool_result(call_id, tool_use_result=None, content="ok"):
    record = {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": call_id, "content": content}]}}
    if tool_use_result is not None:
        record["toolUseResult"] = tool_use_result
    return record


def read_of(call_id, path):
    return [tool_call(call_id, "Read", {"file_path": path}), tool_result(call_id)]


def edit_of(call_id, path, start=None):
    patch = [{"oldStart": start, "oldLines": 1, "newStart": start, "newLines": 1, "lines": ["-a", "+b"]}] if start else []
    return [tool_call(call_id, "Edit", {"file_path": path, "old_string": "a", "new_string": "b"}),
            tool_result(call_id, {"filePath": path, "structuredPatch": patch})]


def answer_of(call_id, question, answer):
    return [tool_call(call_id, "AskUserQuestion", {"questions": [{"question": question}]}),
            tool_result(call_id, {"questions": [{"question": question}], "answers": {question: answer}})]


def bash_test_run(call_id, command, stdout):
    return [tool_call(call_id, "Bash", {"command": command}),
            tool_result(call_id, {"stdout": stdout, "stderr": ""})]


def sections(text):
    """`{heading: [lines]}` of a `## ` sectioned text, in order of appearance."""
    found = {}
    current = None
    for line in text.splitlines():
        match = re.match(r"^##\s+(.*?)\s*$", line)
        if match:
            current = match.group(1)
            found[current] = []
        elif current is not None:
            found[current].append(line)
    return found


def items(lines):
    return [ln for ln in lines if ln.strip()]


class StateFixture(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.project = self.root / "proj"
        self.project.mkdir()
        (self.project / ".compass").mkdir()
        self.config = self.root / "config"
        self.config.mkdir()
        self.outside = self.root / "outside"
        self.outside.mkdir()
        self.transcript = self.outside / "session.jsonl"
        self.env_backup = dict(os.environ)
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.config)
        os.environ["CLAUDE_CODE_SESSION_ID"] = SESSION_ID
        os.environ.pop("COMPASS_WORKER_SESSION", None)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self.env_backup)))
        self.cwd_backup = os.getcwd()
        os.chdir(self.project)
        self.addCleanup(os.chdir, self.cwd_backup)

    def git(self, *args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                       cwd=self.project, check=True, capture_output=True)

    def init_repo(self, commit=True):
        self.git("init", "-q", "-b", "trunk")
        if commit:
            (self.project / "seed.txt").write_text("seed\n", encoding="utf-8")
            self.git("add", "seed.txt")
            self.git("commit", "-q", "-m", "seed")

    def write_active(self, *lines):
        (self.project / ".compass" / "active.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def write_transcript(self, *groups, path=None, raw_tail=""):
        records = []
        for group in groups:
            records.extend(group if isinstance(group, list) else [group])
        target = Path(path or self.transcript)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("".join(json.dumps(r) + "\n" for r in records) + raw_tail, encoding="utf-8")
        return target

    def add_spec(self, name, text=SPEC_TEXT, folder="specs"):
        path = self.project / ".compass" / folder / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def transcripts_folder(self):
        return sessionslib.transcripts_dir(self.project)

    def run_cmd(self, *args, stdin=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), unittest.mock.patch("sys.stdin", io.StringIO(stdin or "")):
            from commands import session_state
            code = session_state.run(list(args))
        return code, out.getvalue()

    def block(self, *args):
        code, text = self.run_cmd("--transcript", str(self.transcript), *args)
        self.assertEqual(code, 0)
        return text


class RegistrationTests(unittest.TestCase):
    def test_command_is_registered_with_its_one_line_description(self):
        """Adversarial where: the command module exists but `maincli` never lists it."""
        self.assertIn("session-state", maincli.VALID_COMMANDS)
        args = maincli.build_parser().parse_args(["session-state"])
        self.assertEqual(args.command, "session-state")
        description = dict(maincli.COMMAND_SPECS)["session-state"]
        self.assertIn("compaction", description)
        self.assertIn("no model call", description)

    def test_cli_launcher_prints_the_block_for_the_fixture_transcript(self):
        """Adversarial where: registration resolves in the dispatcher but the launcher path
        (`compass session-state --transcript ...`) never reaches the module."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / ".compass").mkdir()
            env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project), CLAUDE_CONFIG_DIR=tmp)
            proc = subprocess.run(
                [sys.executable, str(CLI_DIR / "compass"), "session-state", "--transcript", str(STATE_FIXTURE)],
                cwd=project, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Compass session state", proc.stdout)
        self.assertIn("Now also update gamma", proc.stdout)


class FixtureSessionTests(StateFixture):
    def setUp(self):
        super().setUp()
        self.init_repo()
        self.write_active("# Active", "- [ ] TASK-1: first open", "- [x] TASK-2: done", "- [ ] TASK-3: second open",
                          "  - [ ] nested note")
        shutil.copy(STATE_FIXTURE, self.transcript)
        shutil.copytree(STATE_FIXTURE.with_suffix("") / "subagents", self.transcript.with_suffix("") / "subagents")
        (self.project / "dirty.txt").write_text("x", encoding="utf-8")

    def test_every_section_renders_in_the_pinned_order(self):
        """Adversarial where: sections emitted in an order that survives budget cuts wrongly."""
        text = self.block()
        self.assertIn("Compass session state", text.splitlines()[0])
        found = list(sections(text))
        self.assertEqual(found, ORDER)

    def test_last_human_request_is_the_human_prompt_not_the_later_notification(self):
        """Adversarial where: a task-notification or peer record after the prompt replaces it."""
        body = sections(self.block())["Last human request"]
        joined = "\n".join(body)
        self.assertIn("Now also update gamma", joined)
        self.assertNotIn("task-notification", joined)
        self.assertNotIn("Peer relay text", joined)

    def test_open_tasks_list_unchecked_lines_only(self):
        """Adversarial where: a checked task or an indented note counted as an open task."""
        body = "\n".join(sections(self.block())["Open tasks"])
        self.assertIn("TASK-1: first open", body)
        self.assertIn("TASK-3: second open", body)
        self.assertNotIn("TASK-2", body)
        self.assertNotIn("nested note", body)

    def test_question_answers_appear_under_decisions(self):
        """Adversarial where: answers read from the question's options rather than `answers`."""
        body = "\n".join(sections(self.block())["Decisions"])
        for needle in ("Which layout?", "Flat (Recommended)", "Which checks run?", "Unit, Lint"):
            self.assertIn(needle, body)
        self.assertNotIn("Ship it?", body)

    def test_edited_files_list_most_recent_first_and_include_subagent_edits(self):
        """Adversarial where: ascending order kept from the reader, or subagent edits dropped."""
        body = [ln for ln in sections(self.block())["Files edited"]]
        text = "\n".join(body)
        paths = ["src/side.py", "src/delta.py", "src/gamma.py", "src/alpha.py"]
        positions = [text.index(p) for p in paths]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("src/sub_only.py", text)
        self.assertNotIn("src/beta.py", text)

    def test_files_read_excludes_files_also_edited(self):
        """Adversarial where: a file read then edited listed in both sections."""
        read_body = "\n".join(sections(self.block())["Files read"])
        self.assertIn("src/beta.py", read_body)
        self.assertIn("src/theta.py", read_body)
        self.assertNotIn("src/alpha.py", read_body)
        self.assertNotIn("src/eta.py", read_body)

    def test_last_test_run_keeps_the_last_eight_lines_only(self):
        """Adversarial where: the whole stdout or the first lines kept instead of the tail."""
        body = "\n".join(sections(self.block())["Last test run"])
        self.assertIn("1 failed, 6 passed", body)
        self.assertIn("line3", body)
        self.assertNotIn("line1", body)
        self.assertNotIn("line2", body)

    def test_uncommitted_changes_list_git_status_and_leave_out_the_vault(self):
        """Adversarial where: `.compass/` churn listed as uncommitted work."""
        body = "\n".join(sections(self.block())["Uncommitted changes"])
        self.assertIn("dirty.txt", body)
        self.assertNotIn(".compass", body)

    def test_branch_section_names_the_branch_and_short_commit(self):
        """Adversarial where: the branch read from the transcript's `gitBranch` ("main") not git."""
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.project,
                              capture_output=True, text=True, check=True).stdout.strip()
        body = "\n".join(sections(self.block())["Branch"])
        self.assertIn("trunk", body)
        self.assertIn(head, body)

    def test_absolute_paths_inside_the_project_print_relative(self):
        """Adversarial where: absolute transcript paths leak into the block, wasting budget."""
        target = str(self.project / "src" / "deep" / "mod.py")
        self.write_transcript(user_human("go"), edit_of("e1", target))
        text = self.block()
        self.assertIn("src/deep/mod.py", text)
        self.assertNotIn(str(self.project), text)
        self.assertNotIn(str(self.project).replace("\\", "/"), text)


class DecisionAttributionTests(StateFixture):
    def test_spec_read_this_session_contributes_its_decisions_and_unread_spec_does_not(self):
        """Adversarial where: every vault spec's decisions dumped, or a read spec's skipped."""
        read_spec = self.add_spec("SPEC-900-foo")
        self.add_spec("SPEC-901-bar", SPEC_TEXT.replace("first decision of foo", "first decision of bar"))
        self.write_transcript(user_human("go"), read_of("r1", str(read_spec)))
        body = "\n".join(sections(self.block())["Decisions"])
        self.assertIn("SPEC-900-foo/D-01: The first decision of foo.", body)
        self.assertIn("SPEC-900-foo/D-02: The second decision of foo.", body)
        self.assertNotIn("SPEC-901-bar", body)

    def test_spec_edited_this_session_contributes_its_decisions(self):
        """Adversarial where: only Read counted as `touched`, an Edit-only spec missed."""
        spec = self.add_spec("SPEC-902-baz")
        self.write_transcript(user_human("go"), edit_of("e1", str(spec)))
        body = "\n".join(sections(self.block())["Decisions"])
        self.assertIn("SPEC-902-baz/D-01:", body)

    def test_decision_in_an_adr_under_the_vault_is_included(self):
        """Adversarial where: only `specs/` scanned though the plan says any doc under `.compass/`."""
        adr = self.add_spec("ADR-050-choice", SPEC_TEXT.replace("foo", "adr"), folder="decisions")
        self.write_transcript(user_human("go"), read_of("r1", str(adr)))
        body = "\n".join(sections(self.block())["Decisions"])
        self.assertIn("ADR-050-choice/D-01:", body)

    def test_decision_lines_outside_the_vault_are_not_scanned(self):
        """Adversarial where: any markdown file read this session mined for D-NN lines."""
        outside = self.project / "notes.md"
        outside.write_text(SPEC_TEXT, encoding="utf-8")
        self.write_transcript(user_human("go"), read_of("r1", str(outside)))
        self.assertNotIn("Decisions", sections(self.block()))

    def test_decision_line_is_cut_at_140_characters(self):
        """Adversarial where: a long decision pushes one line past the cap (off-by-one at 140/141)."""
        long_text = "word " * 80
        spec = self.add_spec("SPEC-903-long", SPEC_TEXT.replace("The first decision of foo.", long_text.strip()))
        self.write_transcript(user_human("go"), read_of("r1", str(spec)))
        lines = items(sections(self.block())["Decisions"])
        long_lines = [ln for ln in lines if "SPEC-903-long/D-01" in ln]
        self.assertEqual(len(long_lines), 1)
        self.assertLessEqual(len(re.sub(r"^\s*-\s+", "", long_lines[0])), 140)
        self.assertGreater(len(re.sub(r"^\s*-\s+", "", long_lines[0])), 100)

    def test_decision_lines_over_twenty_end_with_a_more_marker(self):
        """Adversarial where: the 20-line cap off by one or the overflow marker missing."""
        body = "## Decisions\n\n" + "\n".join(f"- **D-{n:02d}:** decision number {n}." for n in range(1, 24)) + "\n"
        spec = self.add_spec("SPEC-904-many", body)
        self.write_transcript(user_human("go"), read_of("r1", str(spec)))
        lines = items(sections(self.block())["Decisions"])
        listed = [ln for ln in lines if "SPEC-904-many/D-" in ln]
        self.assertEqual(len(listed), 20)
        self.assertTrue(any(re.search(r"\.\.\. and 3 more", ln) for ln in lines), lines)

    def test_question_answers_over_eight_end_with_a_more_marker(self):
        """Adversarial where: the 8-answer cap off by one or answers beyond it silently lost."""
        groups = [answer_of(f"q{n}", f"Question {n}?", f"Answer {n}") for n in range(10)]
        self.write_transcript(user_human("go"), *groups)
        lines = items(sections(self.block())["Decisions"])
        listed = [ln for ln in lines if re.search(r"Question \d", ln)]
        self.assertEqual(len(listed), 8)
        self.assertTrue(any(re.search(r"\.\.\. and 2 more", ln) for ln in lines), lines)


class CapTests(StateFixture):
    def test_edited_files_over_forty_keep_the_most_recent_and_count_the_rest(self):
        """Adversarial where: the oldest edits kept instead of the newest, or the cap off by one."""
        groups = [edit_of(f"e{n}", f"src/f{n:03d}.py") for n in range(45)]
        self.write_transcript(user_human("go"), *groups)
        lines = items(sections(self.block())["Files edited"])
        listed = [ln for ln in lines if "src/f" in ln]
        self.assertEqual(len(listed), 40)
        text = "\n".join(lines)
        self.assertIn("src/f044.py", text)
        self.assertNotIn("src/f000.py", text)
        self.assertIn("... and 5 more", text)

    def test_exactly_forty_edited_files_carry_no_more_marker(self):
        """Adversarial where: boundary of the cap prints `... and 0 more`."""
        self.write_transcript(user_human("go"), *[edit_of(f"e{n}", f"src/f{n:03d}.py") for n in range(40)])
        text = "\n".join(sections(self.block())["Files edited"])
        self.assertNotIn("more", text)

    def test_read_files_over_twenty_five_end_with_a_more_marker(self):
        """Adversarial where: the read cap taken as the edited cap (40) or no marker."""
        self.write_transcript(user_human("go"), *[read_of(f"r{n}", f"src/r{n:03d}.py") for n in range(30)])
        lines = items(sections(self.block())["Files read"])
        self.assertEqual(len([ln for ln in lines if "src/r" in ln]), 25)
        self.assertIn("... and 5 more", "\n".join(lines))

    def test_open_tasks_over_twenty_five_end_with_a_more_marker(self):
        """Adversarial where: tasks over the cap dropped without a count."""
        self.write_active(*[f"- [ ] TASK-{n}: open work item {n}" for n in range(1, 31)])
        self.write_transcript(user_human("go"))
        lines = items(sections(self.block())["Open tasks"])
        self.assertEqual(len([ln for ln in lines if "TASK-" in ln]), 25)
        self.assertIn("... and 5 more", "\n".join(lines))

    def test_uncommitted_changes_over_thirty_end_with_a_more_marker(self):
        """Adversarial where: the status list uncapped, flooding the block with dirty paths."""
        self.init_repo()
        for n in range(35):
            (self.project / f"dirty{n:02d}.txt").write_text("x", encoding="utf-8")
        self.write_transcript(user_human("go"))
        lines = items(sections(self.block())["Uncommitted changes"])
        self.assertEqual(len([ln for ln in lines if "dirty" in ln]), 30)
        self.assertIn("... and 5 more", "\n".join(lines))

    def test_request_over_five_hundred_characters_is_cut(self):
        """Adversarial where: a pasted multi-thousand-character prompt printed whole."""
        request = "".join(f"w{n:04d} " for n in range(1000))
        self.write_transcript(user_human(request))
        body = "\n".join(sections(self.block())["Last human request"])
        self.assertIn(request[:400], body)
        self.assertNotIn(request[:1500], body)
        self.assertLess(len(body), 600)

    def test_a_section_with_nothing_in_it_is_left_out(self):
        """Adversarial where: empty sections printed as bare headings, wasting budget."""
        self.write_transcript(user_human("only a prompt"))
        self.assertEqual(list(sections(self.block())), ["Last human request"])


class BudgetTests(StateFixture):
    def build_worst_case(self):
        self.init_repo()
        self.write_active(*[f"- [ ] TASK-{n:03d}: an open task with some length to it, number {n}" for n in range(60)])
        specs = []
        for index in range(3):
            body = "## Decisions\n\n" + "\n".join(
                f"- **D-{n:02d}:** " + ("decision text " * 14) for n in range(1, 21)) + "\n"
            specs.append(self.add_spec(f"SPEC-95{index}-bulk", body))
        groups = [user_human("R" * 5000)]
        groups += [read_of(f"s{i}", str(p)) for i, p in enumerate(specs)]
        groups += [edit_of(f"e{n}", f"src/package/subpackage/module_{n:04d}_with_long_name.py") for n in range(500)]
        groups += [read_of(f"r{n}", f"src/package/subpackage/reader_{n:04d}_with_long_name.py") for n in range(200)]
        groups += [answer_of(f"q{n}", f"Question number {n} about the layout?", f"Answer {n} " * 5) for n in range(30)]
        groups += [bash_test_run("t1", "python -m pytest -q", "\n".join(f"line {n} " + "x" * 80 for n in range(30)))]
        self.write_transcript(*groups)
        for n in range(300):
            (self.project / f"dirty_path_{n:04d}_with_a_long_name.txt").write_text("x", encoding="utf-8")

    def test_worst_case_session_fits_the_budget_and_keeps_request_and_tasks_whole(self):
        """Adversarial where: the block grows past 8,000 characters, or the budget cut eats the
        request or the open tasks before the later sections."""
        self.build_worst_case()
        text = self.block()
        self.assertLess(len(text), 8000)
        found = sections(text)
        request = "\n".join(found["Last human request"])
        self.assertIn("R" * 400, request)
        tasks = items(found["Open tasks"])
        self.assertEqual(len([ln for ln in tasks if "TASK-" in ln]), 25)
        self.assertIn("... and 35 more", "\n".join(tasks))

    def test_dropped_sections_are_always_the_last_ones(self):
        """Adversarial where: the budget cut removes a middle section and keeps a later one."""
        self.build_worst_case()
        found = list(sections(self.block()))
        self.assertEqual(found, ORDER[:len(found)])
        self.assertLess(len(found), len(ORDER), "the worst case must actually exceed the budget")

    def test_a_session_under_the_budget_loses_no_section(self):
        """Adversarial where: the budget logic drops sections even when everything fits."""
        self.init_repo()
        self.write_active("- [ ] TASK-1: one")
        self.write_transcript(user_human("small"), read_of("r1", "a.py"), edit_of("e1", "b.py"),
                              answer_of("q1", "Q?", "A"), bash_test_run("t1", "pytest", "1 passed"))
        (self.project / "dirty.txt").write_text("x", encoding="utf-8")
        self.assertEqual(list(sections(self.block())), ORDER)


class HandoffFormatTests(StateFixture):
    def setUp(self):
        super().setUp()
        self.init_repo()
        self.write_active("- [ ] TASK-1: first open")
        shutil.copy(STATE_FIXTURE, self.transcript)
        shutil.copytree(STATE_FIXTURE.with_suffix("") / "subagents", self.transcript.with_suffix("") / "subagents")
        (self.project / "dirty.txt").write_text("x", encoding="utf-8")

    def test_handoff_prints_the_four_headings_and_no_others(self):
        """Adversarial where: the block's title or extra sections leak into the handoff paste."""
        text = self.block("--format", "handoff")
        headings = re.findall(r"^#+\s+(.*?)\s*$", text, re.M)
        self.assertEqual(headings, HANDOFF_HEADINGS)

    def test_handoff_edited_file_carries_the_edit_start_line_when_known(self):
        """Adversarial where: the structuredPatch start line ignored, or invented for a Write
        whose patch is empty."""
        text = self.block("--format", "handoff")
        self.assertIn("`src/alpha.py:12`", text)
        self.assertIn("`src/gamma.py`", text)
        self.assertNotIn("src/gamma.py:", text)

    def test_handoff_lists_open_tasks_answers_and_dirty_files(self):
        """Adversarial where: a handoff section filled from the wrong source."""
        found = sections(self.block("--format", "handoff"))
        self.assertIn("TASK-1: first open", "\n".join(found["Tasks"]))
        self.assertIn("Flat (Recommended)", "\n".join(found["Decisions"]))
        self.assertIn("dirty.txt", "\n".join(found["Uncommitted Changes"]))

    def test_handoff_leaves_out_a_section_with_nothing_in_it(self):
        """Adversarial where: empty headings pasted into a handoff, which the skill forbids."""
        os.remove(self.project / "dirty.txt")
        (self.project / ".compass" / "active.md").unlink()
        self.write_transcript(user_human("go"), edit_of("e1", "src/a.py", start=3))
        found = list(sections(self.block("--format", "handoff")))
        self.assertEqual(found, ["Recent Changes"])

    def test_explicit_block_format_matches_the_default(self):
        """Adversarial where: `--format block` routed differently from the default."""
        self.assertEqual(self.block("--format", "block"), self.block())


class TranscriptResolutionTests(StateFixture):
    def place(self, name, request, mtime):
        path = self.write_transcript(user_human(request), path=self.transcripts_folder() / f"{name}.jsonl")
        os.utime(path, (mtime, mtime))
        return path

    def test_session_id_transcript_wins_over_a_newer_one(self):
        """Adversarial where: newest-file fallback used even when the session id names a file."""
        self.place(SESSION_ID, "mine", 1_000)
        self.place("other", "newer but not mine", 2_000)
        code, text = self.run_cmd()
        self.assertEqual(code, 0)
        self.assertIn("mine", text)
        self.assertNotIn("newer but not mine", text)

    def test_newest_transcript_is_used_when_the_session_id_has_no_file(self):
        """Adversarial where: a missing id file yields an empty block instead of the newest."""
        self.place("older", "older request", 1_000)
        self.place("newest", "newest request", 2_000)
        code, text = self.run_cmd()
        self.assertEqual(code, 0)
        self.assertIn("newest request", text)
        self.assertNotIn("older request", text)

    def test_newest_transcript_is_used_when_no_session_id_is_set(self):
        """Adversarial where: an unset id crashes the path join instead of falling back."""
        os.environ.pop("CLAUDE_CODE_SESSION_ID")
        self.place("older", "older request", 1_000)
        self.place("newest", "newest request", 2_000)
        code, text = self.run_cmd()
        self.assertEqual(code, 0)
        self.assertIn("newest request", text)

    def test_explicit_transcript_flag_beats_the_session_id_file(self):
        """Adversarial where: the flag ignored when a default transcript exists."""
        self.place(SESSION_ID, "default one", 1_000)
        flagged = self.write_transcript(user_human("flagged one"))
        code, text = self.run_cmd("--transcript", str(flagged))
        self.assertEqual(code, 0)
        self.assertIn("flagged one", text)
        self.assertNotIn("default one", text)


class DegradedInputTests(StateFixture):
    def test_missing_transcript_still_prints_the_vault_and_git_sections(self):
        """Adversarial where: a nonexistent transcript path aborts the whole block."""
        self.init_repo()
        self.write_active("- [ ] TASK-1: still shown")
        code, text = self.run_cmd("--transcript", str(self.outside / "nope.jsonl"))
        self.assertEqual(code, 0)
        found = sections(text)
        self.assertIn("TASK-1: still shown", "\n".join(found["Open tasks"]))
        self.assertIn("Branch", found)
        self.assertNotIn("Last human request", found)

    def test_no_transcript_anywhere_exits_zero(self):
        """Adversarial where: the newest-file fallback raises on a missing transcripts folder."""
        code, _ = self.run_cmd()
        self.assertEqual(code, 0)

    def test_transcript_path_that_is_a_directory_exits_zero(self):
        """Adversarial where: an IsADirectoryError escapes the reader."""
        code, _ = self.run_cmd("--transcript", str(self.outside))
        self.assertEqual(code, 0)

    def test_vault_without_active_md_leaves_out_open_tasks(self):
        """Adversarial where: a missing active.md raises or prints an empty Open tasks heading."""
        self.init_repo()
        self.write_transcript(user_human("go"))
        found = sections(self.block())
        self.assertNotIn("Open tasks", found)
        self.assertIn("Last human request", found)

    def test_folder_that_is_not_a_git_repository_leaves_out_git_sections(self):
        """Adversarial where: `git status` failure (exit 128) raised or printed as an error line."""
        self.write_active("- [ ] TASK-1: one")
        self.write_transcript(user_human("go"), edit_of("e1", "a.py"))
        code, text = self.run_cmd("--transcript", str(self.transcript))
        self.assertEqual(code, 0)
        found = sections(text)
        self.assertNotIn("Branch", found)
        self.assertNotIn("Uncommitted changes", found)
        self.assertNotIn("fatal", text.lower())
        self.assertIn("Files edited", found)

    def test_git_that_cannot_run_still_exits_zero_with_the_other_sections(self):
        """Adversarial where: an OSError launching git (not installed) escapes."""
        self.write_active("- [ ] TASK-1: one")
        self.write_transcript(user_human("go"))
        empty = self.root / "empty-path"
        empty.mkdir()
        with unittest.mock.patch.dict(os.environ, {"PATH": str(empty)}):
            with unittest.mock.patch("shutil.which", return_value=None):
                code, text = self.run_cmd("--transcript", str(self.transcript))
        self.assertEqual(code, 0)
        self.assertIn("Open tasks", sections(text))

    def test_truncated_last_line_and_binary_noise_keep_the_readable_remainder(self):
        """Adversarial where: one unreadable trailing line discards the whole transcript."""
        self.write_transcript(user_human("kept request"), edit_of("e1", "kept.py"),
                              raw_tail='{"type": "user", "message": {"role": "us')
        with open(self.transcript, "ab") as fh:
            fh.write(b"\n\xff\xfe\x00garbage\n")
        text = self.block()
        self.assertIn("kept request", text)
        self.assertIn("kept.py", text)

    def test_unknown_format_value_never_exits_two(self):
        """Adversarial where: an argparse-style SystemExit(2) would block a PreCompact run."""
        self.write_transcript(user_human("go"))
        try:
            code, _ = self.run_cmd("--transcript", str(self.transcript), "--format", "nonsense")
        except SystemExit as exc:
            code = exc.code
        self.assertNotEqual(code, 2)

    def test_command_reading_a_vault_in_a_worktree_style_cwd_uses_the_project_dir(self):
        """Adversarial where: the root taken from the cwd rather than CLAUDE_PROJECT_DIR."""
        self.write_active("- [ ] TASK-1: from project dir")
        self.write_transcript(user_human("go"))
        os.chdir(self.outside)
        found = sections(self.block())
        self.assertIn("TASK-1: from project dir", "\n".join(found["Open tasks"]))


class HookTests(StateFixture):
    def setUp(self):
        super().setUp()
        self.init_repo()
        self.write_active("- [ ] TASK-1: hook task")
        self.session_file = self.write_transcript(
            user_human("hook request"), edit_of("e1", "src/hooked.py"),
            path=self.transcripts_folder() / f"{SESSION_ID}.jsonl")

    def event(self, name="SessionStart", **extra):
        base = {"hook_event_name": name, "session_id": SESSION_ID, "transcript_path": str(self.session_file)}
        base.update(extra)
        return json.dumps(base)

    def hook(self, payload):
        return self.run_cmd("--hook", stdin=payload)

    def test_session_start_compact_prints_json_whose_context_is_the_block(self):
        """Adversarial where: plain text or a wrong envelope key, which Claude Code would ignore."""
        code, text = self.hook(self.event(source="compact"))
        self.assertEqual(code, 0)
        data = json.loads(text)
        self.assertEqual(list(data), ["hookSpecificOutput"])
        output = data["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "SessionStart")
        self.assertEqual(list(output), ["hookEventName", "additionalContext"])
        self.assertIn("Compass session state", output["additionalContext"])
        self.assertIn("hook request", output["additionalContext"])
        self.assertIn("src/hooked.py", output["additionalContext"])
        self.assertEqual(output["additionalContext"].strip(), self.block().strip())

    def test_session_start_other_sources_print_nothing(self):
        """Adversarial where: the block injected at every session start, not just after a compaction."""
        for source in ("startup", "resume", "clear", ""):
            with self.subTest(source=source):
                code, text = self.hook(self.event(source=source))
                self.assertEqual((code, text), (0, ""))

    def test_session_start_without_a_source_prints_nothing(self):
        """Adversarial where: a missing `source` key treated as compact."""
        code, text = self.hook(self.event())
        self.assertEqual((code, text), (0, ""))

    def test_pre_compact_prints_short_instructions_naming_all_five_things(self):
        """Adversarial where: the instructions exceed 1,500 characters or omit one of the five
        kept items, or come in a different order."""
        for trigger in ("auto", "manual"):
            with self.subTest(trigger=trigger):
                code, text = self.hook(self.event("PreCompact", trigger=trigger))
                self.assertEqual(code, 0)
                self.assertTrue(text.strip())
                self.assertLess(len(text), 1500)
                with self.assertRaises(ValueError):
                    json.loads(text)
                lowered = text.lower()
                keys = ["intent", "path", "reason", "exclusion", "next step"]
                positions = [lowered.find(k) for k in keys]
                self.assertNotIn(-1, positions, positions)
                self.assertEqual(positions, sorted(positions))
                self.assertIn("rule", lowered)

    def test_events_from_agents_print_nothing(self):
        """Adversarial where: a subagent's compaction injects the main session's state."""
        for name, extra in (("SessionStart", {"source": "compact"}), ("PreCompact", {})):
            for key in ("agent_id", "agent_type"):
                with self.subTest(event=name, key=key):
                    code, text = self.hook(self.event(name, **extra, **{key: "worker-1"}))
                    self.assertEqual((code, text), (0, ""))

    def test_worker_session_env_prints_nothing(self):
        """Adversarial where: capture-worker headless sessions receive a state block."""
        os.environ["COMPASS_WORKER_SESSION"] = "1"
        for name, extra in (("SessionStart", {"source": "compact"}), ("PreCompact", {})):
            with self.subTest(event=name):
                code, text = self.hook(self.event(name, **extra))
                self.assertEqual((code, text), (0, ""))

    def test_other_events_print_nothing(self):
        """Adversarial where: the hook answers events it was never registered for."""
        for name in ("PostToolUse", "Stop", "UserPromptSubmit", "Nonsense"):
            with self.subTest(event=name):
                code, text = self.hook(self.event(name, source="compact"))
                self.assertEqual((code, text), (0, ""))

    def test_empty_malformed_or_non_object_stdin_exits_zero_silently(self):
        """Adversarial where: a JSON decode error or a list payload becomes a crash or exit 2,
        which would block a compaction."""
        for payload in ("", "   \n", "{not json", "[1, 2]", "null", '"text"'):
            with self.subTest(payload=payload):
                code, text = self.hook(payload)
                self.assertEqual((code, text), (0, ""))

    def test_hook_without_any_transcript_still_exits_zero(self):
        """Adversarial where: a compaction in a session whose transcript is gone raises."""
        self.session_file.unlink()
        code, text = self.hook(self.event(source="compact"))
        self.assertEqual(code, 0)
        if text:
            self.assertIn("Compass session state", json.loads(text)["hookSpecificOutput"]["additionalContext"])


class StdinDisciplineTests(StateFixture):
    class ExplodingStdin:
        def read(self, *a, **k):
            raise AssertionError("stdin was read without --hook")

        readline = readlines = __iter__ = __next__ = read

    def test_in_process_run_without_hook_never_touches_stdin(self):
        """Adversarial where: the command reads stdin unconditionally, blocking an interactive run."""
        self.write_transcript(user_human("go"))
        out = io.StringIO()
        from commands import session_state
        with contextlib.redirect_stdout(out), unittest.mock.patch("sys.stdin", self.ExplodingStdin()):
            code = session_state.run(["--transcript", str(self.transcript)])
        self.assertEqual(code, 0)
        self.assertIn("go", out.getvalue())

    def test_process_with_an_open_idle_stdin_returns_without_the_flag(self):
        """Adversarial where: a real process blocks forever on a stdin pipe that never closes."""
        self.write_transcript(user_human("go"))
        proc = subprocess.Popen(
            [sys.executable, str(CLI_DIR / "compass"), "session-state", "--transcript", str(self.transcript)],
            cwd=self.project, env=dict(os.environ), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            self.fail("session-state without --hook blocked on stdin")
        finally:
            out = proc.stdout.read()
            proc.stdout.close()
            proc.stderr.close()
            proc.stdin.close()
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Compass session state", out)

    def test_hook_flag_reads_the_event_from_a_real_stdin_pipe(self):
        """Adversarial where: the in-process stdin patch hides a failure to read `sys.stdin` in a
        real process."""
        folder = self.transcripts_folder()
        self.write_transcript(user_human("piped request"), path=folder / f"{SESSION_ID}.jsonl")
        event = json.dumps({"hook_event_name": "SessionStart", "source": "compact", "session_id": SESSION_ID})
        proc = subprocess.run([sys.executable, str(CLI_DIR / "compass"), "session-state", "--hook"],
                              cwd=self.project, env=dict(os.environ), input=event,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("piped request", json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"])


class MultibyteBudgetTests(StateFixture):
    def test_request_cut_counts_characters_not_bytes(self):
        """Adversarial where: the 500-character request cap measured in bytes, halving or
        splitting a multibyte request."""
        self.write_transcript(user_human("\u754c" * 600))
        body = "\n".join(sections(self.block())["Last human request"])
        self.assertIn("\u754c" * 500, body)
        self.assertNotIn("\u754c" * 501, body)

    def test_worst_case_block_of_wide_characters_stays_under_8000_characters(self):
        """Adversarial where: a budget measured in encoded bytes or JSON-escaped length lets
        wide-character text through, or a cut lands mid-section and breaks the order."""
        self.init_repo()
        self.write_active(*[f"- [ ] TASK-{n}: " + "\u4efb" * 300 for n in range(60)])
        groups = [user_human("\u754c" * 5000)]
        groups += [edit_of(f"e{n}", f"src/\u6a21\u5757_{n:04d}_" + "\u540d" * 40 + ".py") for n in range(100)]
        groups += [answer_of(f"q{n}", "\u554f" * 120, "\u7b54" * 120) for n in range(30)]
        self.write_transcript(*groups)
        text = self.block()
        self.assertLess(len(text), 8000)
        found = list(sections(text))
        self.assertEqual(found, ORDER[:len(found)])
        self.assertEqual(found[:2], ORDER[:2])

    def test_hook_payload_is_valid_single_line_json_for_quotes_backslashes_and_control_text(self):
        """Adversarial where: the request carries quotes, backslashes, emoji, tabs and U+2028
        into the hook's JSON, breaking the envelope or splitting it over lines."""
        nasty = 'say "hi" C:\\Users\\x\\n tab\there \U0001F600 sep\u2028end \x1b[0m'
        folder = self.transcripts_folder()
        session = self.write_transcript(user_human(nasty), path=folder / f"{SESSION_ID}.jsonl")
        event = json.dumps({"hook_event_name": "SessionStart", "source": "compact",
                            "transcript_path": str(session)})
        code, text = self.run_cmd("--hook", stdin=event)
        self.assertEqual(code, 0)
        self.assertEqual(len(text.strip().splitlines()), 1)
        context = json.loads(text)["hookSpecificOutput"]["additionalContext"]
        self.assertIn('say "hi" C:\\Users\\x\\n', context)
        self.assertIn("\U0001F600", context)


class RenderBlockSweepTests(unittest.TestCase):
    def state(self, **over):
        base = {"request": None, "tasks": [], "answers": [], "documents": [], "edited": [], "read": [],
                "starts": {}, "dirty": [], "test_run": None, "branch": []}
        base.update(over)
        return base

    def test_block_stays_under_8000_characters_and_keeps_a_section_prefix_for_every_load(self):
        """Adversarial where: a budget boundary off by one lets a section land just past the
        cap, or lets a later section appear after an earlier one was dropped."""
        from commands import session_state
        for width in range(1, 240, 7):
            for count in (0, 1, 7, 8, 9, 24, 25, 26, 60):
                state = self.state(
                    request="r" * 700,
                    tasks=["- [ ] " + "t" * width] * count,
                    answers=[("q" * width, "a" * width)] * (count % 12),
                    documents=["d" * width] * count,
                    edited=[("e" * width, "edited", "e" * width)] * count,
                    read=[("r" * width, "read", "r" * width)] * count,
                    dirty=[" M " + "x" * width] * count,
                    test_run=("pytest", ["l" * width] * 8),
                    branch=["main @ abc1234"])
                text = session_state.render_block(state)
                self.assertLessEqual(len(text), 8000, (width, count))
                found = list(sections(text))
                nonempty = [name for name, _ in session_state.block_sections(state)]
                self.assertEqual(found, nonempty[:len(found)], (width, count))

    def test_many_short_request_lines_and_long_tasks_both_survive_whole(self):
        """Adversarial where: a 500-character request made of 250 one-letter lines expands with
        its `> ` prefixes past what the budget leaves for the 25 open tasks."""
        from commands import session_state
        state = self.state(request="a\n" * 300, tasks=[("- [ ] TASK: " + "w " * 200)[:240]] * 60)
        found = sections(session_state.render_block(state))
        self.assertIn("Open tasks", found)
        tasks = items(found["Open tasks"])
        self.assertEqual(len(tasks), 26)
        self.assertEqual(tasks[-1], "... and 35 more")
        self.assertTrue(all(len(t) <= 240 for t in tasks))


class PathRenderingTests(StateFixture):
    def test_backslash_relative_paths_print_with_forward_slashes_and_merge_with_slash_spelling(self):
        """Adversarial where: a Windows-spelled path (`src\\a.py`) listed twice beside its
        `src/a.py` spelling, or printed with backslashes."""
        self.write_transcript(user_human("go"), read_of("r1", "src\\a.py"), edit_of("e1", "src/a.py"))
        found = sections(self.block())
        self.assertEqual(items(found["Files edited"]), ["- src/a.py"])
        self.assertNotIn("Files read", found)

    def test_dot_slash_prefix_is_dropped_and_merges_with_the_bare_spelling(self):
        """Adversarial where: `./x.py` and `x.py` counted as two files."""
        self.write_transcript(user_human("go"), read_of("r1", "./x.py"), read_of("r2", "x.py"))
        self.assertEqual(items(sections(self.block())["Files read"]), ["- x.py"])

    def test_absolute_path_outside_the_project_prints_whole_with_forward_slashes(self):
        """Adversarial where: a path outside the project rendered as a `../..` chain or left
        with backslashes."""
        target = str(self.outside / "elsewhere" / "f.py")
        self.write_transcript(user_human("go"), edit_of("e1", target))
        lines = items(sections(self.block())["Files edited"])
        self.assertEqual(lines, ["- " + target.replace("\\", "/")])

    def test_sibling_folder_sharing_the_project_name_prefix_is_not_inside_the_project(self):
        """Adversarial where: a prefix comparison treats `proj-other/f.py` as inside `proj`."""
        target = str(self.root / "proj-other" / "f.py")
        self.write_transcript(user_human("go"), edit_of("e1", target))
        lines = items(sections(self.block())["Files edited"])
        self.assertEqual(lines, ["- " + target.replace("\\", "/")])

    @unittest.skipUnless(os.name == "nt", "drive-letter spelling only exists on Windows")
    def test_lowercase_drive_letter_spelling_still_prints_relative(self):
        """Adversarial where: a path spelled with a different drive-letter case is treated as
        outside the project."""
        target = str(self.project / "src" / "m.py")
        target = target[0].lower() + target[1:]
        self.write_transcript(user_human("go"), edit_of("e1", target))
        self.assertEqual(items(sections(self.block())["Files edited"]), ["- src/m.py"])


class HandoffStartLineTests(StateFixture):
    def test_start_line_survives_a_later_read_spelled_differently(self):
        """Adversarial where: the merged display entry keeps the later Read's spelling, so the
        absolute-path Edit's `path:line` is lost."""
        target = str(self.project / "src" / "a.py")
        self.write_transcript(user_human("go"), edit_of("e1", target, start=12), read_of("r1", "src/a.py"))
        body = "\n".join(sections(self.block("--format", "handoff"))["Recent Changes"])
        self.assertIn("`src/a.py:12`", body)

    def test_two_edits_of_one_path_show_one_entry_with_a_line(self):
        """Adversarial where: one file edited twice listed twice in Recent Changes."""
        self.write_transcript(user_human("go"), edit_of("e1", "a.py", start=3), edit_of("e2", "a.py", start=40))
        lines = items(sections(self.block("--format", "handoff"))["Recent Changes"])
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"^- `a\.py:\d+`$")

    def test_edit_with_an_empty_patch_has_no_line_suffix(self):
        """Adversarial where: a missing start line rendered as `path:None` or `path:0`."""
        self.write_transcript(user_human("go"), edit_of("e1", "a.py"))
        lines = items(sections(self.block("--format", "handoff"))["Recent Changes"])
        self.assertEqual(lines, ["- `a.py`"])

    def test_patch_start_of_zero_or_a_non_integer_gives_no_line_suffix(self):
        """Adversarial where: a zero or non-integer `newStart` (a malformed record) printed as
        `path:0`, `path:7` from a string or `path:2.5`."""
        def odd(call_id, start):
            patch = [{"oldStart": start, "newStart": start, "lines": []}]
            return [tool_call(call_id, "Edit", {"file_path": f"{call_id}.py"}),
                    tool_result(call_id, {"structuredPatch": patch})]
        self.write_transcript(user_human("go"), odd("z", 0), odd("s", "7"), odd("f", 2.5))
        lines = items(sections(self.block("--format", "handoff"))["Recent Changes"])
        self.assertEqual(sorted(lines), ["- `f.py`", "- `s.py`", "- `z.py`"])

    def test_edit_line_skips_the_hunks_leading_context_lines(self):
        """Adversarial where: the hunk start printed, which the host sets up to three
        context lines above the change (observed live: `scratch.md:1` for a change on line 3),
        or context lines after the change counted too."""
        def hunk(call_id, start, lines):
            patch = [{"oldStart": start, "newStart": start, "lines": lines}]
            return [tool_call(call_id, "Edit", {"file_path": f"{call_id}.md"}),
                    tool_result(call_id, {"structuredPatch": patch})]
        self.write_transcript(user_human("go"),
                              hunk("ctx", 1, [" # title", " ", "-status: draft", "+status: edited", " codeword"]),
                              hunk("add", 40, [" a", " b", " c", "+new", " d"]),
                              hunk("none", 7, [" only context"]),
                              hunk("odd", 5, [" a", 3, "-b"]))
        lines = items(sections(self.block("--format", "handoff"))["Recent Changes"])
        self.assertEqual(sorted(lines), ["- `add.md:43`", "- `ctx.md:3`", "- `none.md:7`", "- `odd.md:5`"])

    def test_subagent_edit_start_line_is_reported(self):
        """Adversarial where: start lines read from the main transcript only, so a subagent's
        Edit prints without its line."""
        self.write_transcript(user_human("go"))
        side = self.transcript.with_suffix("") / "subagents"
        side.mkdir(parents=True)
        (side / "agent-x1.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in edit_of("s1", "sub.py", start=9)), encoding="utf-8")
        body = "\n".join(sections(self.block("--format", "handoff"))["Recent Changes"])
        self.assertIn("`sub.py:9`", body)


class DocumentDecisionTests(StateFixture):
    def test_folder_spec_index_uses_the_folder_name_as_the_stem(self):
        """Adversarial where: a folder spec's `index.md` stem prefixes every decision with
        `index/`."""
        path = self.project / ".compass" / "specs" / "SPEC-910-folder" / "index.md"
        path.parent.mkdir(parents=True)
        path.write_text(SPEC_TEXT, encoding="utf-8")
        self.write_transcript(user_human("go"), read_of("r1", str(path)))
        body = "\n".join(sections(self.block())["Decisions"])
        self.assertIn("- SPEC-910-folder/D-01:", body)
        self.assertNotIn("index/D-", body)

    def test_spec_read_only_by_a_subagent_contributes_its_decisions(self):
        """Adversarial where: documents scanned from the main transcript's paths only."""
        spec = self.add_spec("SPEC-911-sub")
        self.write_transcript(user_human("go"))
        side = self.transcript.with_suffix("") / "subagents"
        side.mkdir(parents=True)
        (side / "agent-x2.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in read_of("s1", str(spec))), encoding="utf-8")
        self.assertIn("SPEC-911-sub/D-01:", "\n".join(sections(self.block())["Decisions"]))

    def test_spec_read_by_a_project_relative_path_is_found(self):
        """Adversarial where: a relative `file_path` resolved against the current directory
        instead of the project root."""
        self.add_spec("SPEC-912-rel")
        self.write_transcript(user_human("go"), read_of("r1", ".compass/specs/SPEC-912-rel.md"))
        os.chdir(self.outside)
        self.assertIn("SPEC-912-rel/D-01:", "\n".join(sections(self.block())["Decisions"]))

    @unittest.skipUnless(os.name == "nt", "backslash separators only exist on Windows")
    def test_spec_read_by_a_backslash_path_is_found(self):
        """Adversarial where: a Windows-separator vault path misses the vault containment test."""
        self.add_spec("SPEC-913-bs")
        self.write_transcript(user_human("go"), read_of("r1", ".compass\\specs\\SPEC-913-bs.md"))
        self.assertIn("SPEC-913-bs/D-01:", "\n".join(sections(self.block())["Decisions"]))

    def test_spec_read_through_a_dotdot_spelling_is_listed_once(self):
        """Adversarial where: the same spec read as `specs/x.md` and `specs/../specs/x.md` yields
        its decisions twice, spending the 20-line cap."""
        spec = self.add_spec("SPEC-914-dup")
        alias = str(spec.parent / ".." / "specs" / spec.name)
        self.write_transcript(user_human("go"), read_of("r1", str(spec)), read_of("r2", alias))
        body = "\n".join(sections(self.block())["Decisions"])
        self.assertEqual(body.count("SPEC-914-dup/D-01:"), 1)

    def test_spec_deleted_after_being_read_does_not_break_the_block(self):
        """Adversarial where: a read of a missing file or of a directory raises instead of being
        skipped."""
        vault = self.project / ".compass"
        (vault / "specs").mkdir()
        self.write_transcript(user_human("go"), read_of("r1", str(vault / "specs" / "gone.md")),
                              read_of("r2", str(vault / "specs")))
        self.assertNotIn("Decisions", sections(self.block()))

    def test_decision_line_of_wide_characters_is_cut_at_140_characters(self):
        """Adversarial where: the 140 cut counts bytes, or leaves the `...` beyond the cap."""
        spec = self.add_spec("SPEC-915-wide", SPEC_TEXT.replace(
            "The first decision of foo.", "\u6c7a" * 300))
        self.write_transcript(user_human("go"), read_of("r1", str(spec)))
        lines = [ln for ln in sections(self.block())["Decisions"] if "SPEC-915-wide/D-01" in ln]
        self.assertEqual(len(lines), 1)
        self.assertLessEqual(len(lines[0]) - 2, 140)
        self.assertTrue(lines[0].endswith("..."))


class GitStateTests(StateFixture):
    def test_detached_head_names_the_commit_with_a_detached_marker(self):
        """Adversarial where: a detached HEAD yields no branch section, or an empty branch name
        before the `@`."""
        self.init_repo()
        self.git("checkout", "-q", "--detach")
        self.write_transcript(user_human("go"))
        body = "\n".join(sections(self.block())["Branch"]).strip()
        self.assertRegex(body, r"^\(detached\) @ [0-9a-f]{7,}$")

    def test_repository_without_a_commit_names_the_branch_only(self):
        """Adversarial where: a fresh repository prints `trunk @ ` with an empty hash, or drops
        the section."""
        self.init_repo(commit=False)
        self.write_transcript(user_human("go"))
        body = "\n".join(sections(self.block())["Branch"]).strip()
        self.assertEqual(body, "trunk")

    def test_unicode_and_spaced_file_names_print_unescaped(self):
        """Adversarial where: git's quoted-octal path escapes reach the block."""
        self.init_repo()
        (self.project / "a\u00e7\u00e3o final.txt").write_text("x", encoding="utf-8")
        self.write_transcript(user_human("go"))
        body = "\n".join(sections(self.block())["Uncommitted changes"])
        self.assertNotIn("\\303", body)
        self.assertIn("a\u00e7\u00e3o final.txt", body)

    def test_compass_changes_alone_leave_the_uncommitted_section_out(self):
        """Adversarial where: a vault-only change still creates an empty section header."""
        self.init_repo()
        (self.project / ".compass" / "active.md").write_text("- [ ] T\n", encoding="utf-8")
        self.write_transcript(user_human("go"))
        self.assertNotIn("Uncommitted changes", sections(self.block()))

    def test_git_timeout_leaves_out_the_git_sections_and_exits_zero(self):
        """Adversarial where: a hung git raises `TimeoutExpired` through the command, taking the
        whole block with it."""
        self.write_active("- [ ] TASK-1: kept")
        self.write_transcript(user_human("go"))
        with unittest.mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            found = sections(self.block())
        self.assertIn("Open tasks", found)
        self.assertNotIn("Branch", found)
        self.assertNotIn("Uncommitted changes", found)

    def test_git_output_in_a_foreign_encoding_is_decoded_with_replacement(self):
        """Adversarial where: undecodable bytes in a file name raise `UnicodeDecodeError`."""
        self.write_transcript(user_human("go"))
        done = subprocess.CompletedProcess(["git"], 0, stdout=b"?? caf\xe9.txt\n", stderr=b"")
        with unittest.mock.patch("subprocess.run", return_value=done):
            text = self.block()
        self.assertIn("caf", sections(text)["Uncommitted changes"][0])

    def test_nonzero_git_exit_is_treated_as_no_output(self):
        """Adversarial where: stdout of a failed git (partial text before the error) is used."""
        self.write_transcript(user_human("go"))
        failed = subprocess.CompletedProcess(["git"], 128, stdout=b"?? half.txt\n", stderr=b"fatal")
        with unittest.mock.patch("subprocess.run", return_value=failed):
            found = sections(self.block())
        self.assertNotIn("Uncommitted changes", found)
        self.assertNotIn("Branch", found)


class OptionAndResolutionTests(StateFixture):
    def test_equals_spelling_of_both_options_is_honoured(self):
        """Adversarial where: `--format=handoff` and `--transcript=PATH` ignored, printing the
        block for the wrong transcript."""
        self.write_active("- [ ] TASK-1: one")
        self.write_transcript(user_human("go"), edit_of("e1", "a.py", start=4))
        code, text = self.run_cmd(f"--transcript={self.transcript}", "--format=handoff")
        self.assertEqual(code, 0)
        self.assertEqual(list(sections(text)), ["Tasks", "Recent Changes"])
        self.assertIn("`a.py:4`", text)

    def test_option_without_a_value_at_the_end_exits_zero_with_the_default(self):
        """Adversarial where: a trailing `--transcript` indexes past the arguments."""
        self.write_active("- [ ] TASK-1: one")
        for flag in ("--transcript", "--format"):
            code, text = self.run_cmd(flag)
            self.assertEqual(code, 0)
            self.assertIn("Open tasks", sections(text))

    def test_session_id_with_a_path_separator_cannot_reach_a_file_outside_the_folder(self):
        """Adversarial where: `CLAUDE_CODE_SESSION_ID=../evil` joins to a transcript above the
        project's transcript folder."""
        folder = self.transcripts_folder()
        folder.mkdir(parents=True, exist_ok=True)
        self.write_transcript(user_human("LEAKED request"), path=folder.parent / "evil.jsonl")
        for value in ("../evil", "..\\evil"):
            os.environ["CLAUDE_CODE_SESSION_ID"] = value
            self.assertNotIn("LEAKED", self.run_cmd()[1])

    def test_hook_event_transcript_path_beats_a_newer_transcript_in_the_folder(self):
        """Adversarial where: the hook ignores the event's `transcript_path` and prints the
        newest transcript of the folder."""
        folder = self.transcripts_folder()
        mine = self.write_transcript(user_human("MINE"), path=self.outside / "mine.jsonl")
        self.write_transcript(user_human("NEWER"), path=folder / "other.jsonl")
        event = json.dumps({"hook_event_name": "SessionStart", "source": "compact",
                            "transcript_path": str(mine)})
        context = json.loads(self.run_cmd("--hook", stdin=event)[1])["hookSpecificOutput"]["additionalContext"]
        self.assertIn("MINE", context)
        self.assertNotIn("NEWER", context)

    def test_hook_event_with_a_missing_transcript_path_falls_back_to_the_folder(self):
        """Adversarial where: a non-existent `transcript_path` yields an empty block instead of
        the session's own transcript."""
        folder = self.transcripts_folder()
        self.write_transcript(user_human("FALLBACK"), path=folder / f"{SESSION_ID}.jsonl")
        event = json.dumps({"hook_event_name": "SessionStart", "source": "compact",
                            "transcript_path": str(self.outside / "nope.jsonl")})
        context = json.loads(self.run_cmd("--hook", stdin=event)[1])["hookSpecificOutput"]["additionalContext"]
        self.assertIn("FALLBACK", context)

    def test_active_md_with_crlf_line_endings_lists_its_open_tasks(self):
        """Adversarial where: CRLF files leave a trailing carriage return in task lines or hide
        the lines from the matcher."""
        (self.project / ".compass" / "active.md").write_bytes(
            b"# Active\r\n- [ ] TASK-1: one\r\n- [x] TASK-2: done\r\n- [ ] TASK-3: two\r\n")
        self.write_transcript(user_human("go"))
        lines = items(sections(self.block())["Open tasks"])
        self.assertEqual(lines, ["- [ ] TASK-1: one", "- [ ] TASK-3: two"])

    def test_task_line_over_240_characters_is_cut_with_an_ellipsis(self):
        """Adversarial where: one very long task line is kept whole, spending the budget."""
        self.write_active("- [ ] TASK-1: " + "x" * 600)
        self.write_transcript(user_human("go"))
        line = items(sections(self.block())["Open tasks"])[0]
        self.assertLessEqual(len(line), 240)
        self.assertTrue(line.endswith("..."))



TWO_FIXTURE = FIXTURES / "state-two-boundaries.jsonl"
FIRST_BOUNDARY = 9
SECOND_BOUNDARY = 24
LAST_LINE = 38
LINE_COUNT = 39

GOLDEN_BLOCK = """\
Compass session state

## Last human request
> Now also update gamma

## Open tasks
- [ ] TASK-1: first open
- [ ] TASK-3: second open

## Decisions
- Which layout?: Flat (Recommended)
- Which checks run?: Unit, Lint

## Files edited
- src/sub_only.py
- src/side.py
- src/delta.py
- src/gamma.py
- src/alpha.py

## Files read
- src/theta.py
- src/beta.py

## Uncommitted changes
?? dirty.txt

## Last test run
- `cd plugin/cli && python -m pytest -q tests/test_alpha.py`
    tests/test_alpha.py line3
    tests/test_alpha.py line4
    tests/test_alpha.py line5
    tests/test_alpha.py line6
    tests/test_alpha.py line7
    FAILED tests/test_alpha.py::test_one - assert 1 == 2
    1 failed, 6 passed in 0.10s

## Branch
trunk @ <SHA>
"""

GOLDEN_HANDOFF = """\
## Tasks
- [ ] TASK-1: first open
- [ ] TASK-3: second open

## Recent Changes
- `src/sub_only.py:4`
- `src/side.py:3`
- `src/delta.py`
- `src/gamma.py`
- `src/alpha.py:12`

## Decisions
- Which layout?: Flat (Recommended)
- Which checks run?: Unit, Lint

## Uncommitted Changes
- ?? dirty.txt
"""

AT_SPEC_FIRST = SPEC_TEXT
AT_SPEC_SECOND = """---
title: Foo
---

# Foo

## Decisions

- **D-01:** The first decision of foo, reworded in the second commit.
- **D-03:** A third decision that only the second commit holds.
"""
AT_ADR_TEXT = """---
title: Bar
---

# Bar

## Decisions

- **D-01:** The only decision of bar.
"""
AT_LATE_TEXT = """---
title: Late
---

# Late

## Decisions

- **D-01:** A decision of a spec that the first commit does not hold.
"""


class BoundaryFixture(StateFixture):
    """A project holding a copy of the two-boundary transcript and its subagent files."""

    def setUp(self):
        super().setUp()
        self.install_two_boundaries()

    def install_two_boundaries(self, prefix=""):
        text = TWO_FIXTURE.read_text(encoding="utf-8")
        self.transcript.write_text(prefix + text, encoding="utf-8")
        side = self.transcript.with_suffix("") / "subagents"
        if side.parent.exists():
            shutil.rmtree(side.parent)
        shutil.copytree(TWO_FIXTURE.with_suffix("") / "subagents", side)

    def run_split(self, *args, stdin=None):
        """`(code, stdout, stderr)` of the command run in-process."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                unittest.mock.patch("sys.stdin", io.StringIO(stdin or "")):
            from commands import session_state
            code = session_state.run(list(args))
        return code, out.getvalue(), err.getvalue()

    def state(self, *args):
        code, out, err = self.run_split("--transcript", str(self.transcript), *args)
        self.assertEqual(code, 0, err)
        return out


class UntilBoundaryTests(BoundaryFixture):
    def test_until_second_boundary_renders_only_what_came_before_it(self):
        """Adversarial where: `--until` filters the main transcript but still reads the
        prompt, the answer, the test run or the file lists from lines after the boundary,
        or keeps the subagent records of the wrong side of the boundary."""
        found = sections(self.state("--until", str(SECOND_BOUNDARY)))
        request = "\n".join(found["Last human request"])
        self.assertIn("Middle request about the gadget", request)
        self.assertNotIn("Final request", request)
        answers = "\n".join(found["Decisions"])
        for kept in ("Which early layout?: Early flat", "Which middle checks?: Middle unit"):
            self.assertIn(kept, answers)
        self.assertNotIn("Final target", answers)
        edited = items(found["Files edited"])
        for path in ("src/edit_early.py", "src/edit_mid.py", "src/shared.py", "src/sub_before.py", "src/sub_at.py"):
            self.assertIn(f"- {path}", edited)
        for path in ("src/edit_final.py", "src/sub_after.py", "src/sub_late_edit.py"):
            self.assertNotIn(f"- {path}", edited)
        read = items(found["Files read"])
        for path in ("src/read_early.py", "src/read_mid.py", "src/sub_read_early.py"):
            self.assertIn(f"- {path}", read)
        for path in ("src/read_final.py", "src/sub_late_read.py"):
            self.assertNotIn(f"- {path}", read)
        test_run = "\n".join(found["Last test run"])
        self.assertIn("1 failed middle", test_run)
        self.assertNotIn("final run", test_run)

    def test_a_file_edited_only_after_the_boundary_is_read_not_edited_at_it(self):
        """Adversarial where: a path's `edited` kind is taken from the whole transcript, so a
        file read before the boundary and edited after it lists as edited at the boundary."""
        found = sections(self.state("--until", str(SECOND_BOUNDARY)))
        self.assertIn("- src/flip.py", items(found["Files read"]))
        self.assertNotIn("- src/flip.py", items(found["Files edited"]))
        whole = sections(self.state())
        self.assertIn("- src/flip.py", items(whole["Files edited"]))
        self.assertNotIn("- src/flip.py", items(whole["Files read"]))

    def test_until_first_boundary_keeps_only_the_records_before_the_first_one(self):
        """Adversarial where: the cut is always taken at the last boundary, or the subagent
        records are cut at the last boundary's stamp instead of the named one."""
        found = sections(self.state("--until", str(FIRST_BOUNDARY)))
        self.assertIn("Initial request about the widget", "\n".join(found["Last human request"]))
        self.assertEqual(items(found["Files edited"]), ["- src/edit_early.py"])
        self.assertEqual(items(found["Files read"]), ["- src/sub_read_early.py", "- src/read_early.py"])
        self.assertIn("early run", "\n".join(found["Last test run"]))
        decisions = "\n".join(found["Decisions"])
        self.assertIn("Early flat", decisions)
        self.assertNotIn("Middle unit", decisions)

    def test_subagent_record_stamped_exactly_at_the_boundary_is_kept_one_later_is_not(self):
        """Adversarial where: the subagent filter uses a strict `<` against the boundary's
        timestamp, dropping the record stamped at the same instant."""
        edited = items(sections(self.state("--until", str(SECOND_BOUNDARY)))["Files edited"])
        self.assertIn("- src/sub_at.py", edited)
        self.assertNotIn("- src/sub_after.py", edited)

    def test_handoff_format_under_until_reports_the_edit_start_lines_of_that_moment(self):
        """Adversarial where: the edit start line comes from the whole transcript, so a later
        edit of the same file moves the line the boundary state names."""
        at_boundary = self.state("--until", str(SECOND_BOUNDARY), "--format", "handoff")
        self.assertIn("`src/shared.py:7`", at_boundary)
        self.assertIn("`src/sub_before.py:11`", at_boundary)
        self.assertNotIn("src/edit_final.py", at_boundary)
        self.assertNotIn("src/sub_after.py", at_boundary)
        self.assertIn("`src/shared.py:40`", self.state("--format", "handoff"))

    def test_index_counts_physical_lines_including_unparseable_ones(self):
        """Adversarial where: the index is the position among parseable records, so one noise
        line before the boundary moves which line `--until` accepts."""
        self.install_two_boundaries(prefix="not json at all\n")
        found = sections(self.state("--until", str(SECOND_BOUNDARY + 1)))
        self.assertIn("Middle request about the gadget", "\n".join(found["Last human request"]))
        code, out, err = self.run_split("--transcript", str(self.transcript), "--until", str(SECOND_BOUNDARY))
        self.assertEqual(code, 1)
        self.assertIn("not a compaction boundary", err)

    def test_until_refuses_every_line_that_is_not_a_boundary_and_any_index_past_the_end(self):
        """Adversarial where: an off-by-one index lands on the record beside the boundary (the
        summary after it, the line before it), the last line, or past the end and is accepted or
        crashes instead of exiting 1 with `not a compaction boundary`."""
        rows = {
            "first line": 0,
            "line before the second boundary": SECOND_BOUNDARY - 1,
            "summary record after the second boundary": SECOND_BOUNDARY + 1,
            "last line of the file": LAST_LINE,
            "one past the last line": LINE_COUNT,
            "far past the end": 100000,
        }
        for name, index in rows.items():
            with self.subTest(name):
                code, out, err = self.run_split("--transcript", str(self.transcript), "--until", str(index))
                self.assertEqual(code, 1)
                self.assertIn("not a compaction boundary", err)
                self.assertEqual(out, "")

    def test_equals_spelling_of_until_is_honoured(self):
        """Adversarial where: `--until=N` is ignored the way an unknown flag is, printing the
        whole transcript's state with exit 0."""
        found = sections(self.state(f"--until={SECOND_BOUNDARY}"))
        self.assertIn("Middle request about the gadget", "\n".join(found["Last human request"]))
        self.assertNotIn("- src/edit_final.py", items(found["Files edited"]))

    def test_until_keeps_the_branch_and_uncommitted_sections_of_the_present(self):
        """Adversarial where: `--until` also switches the git sections or the open tasks to a
        past state, though only `--at` moves them."""
        self.init_repo()
        self.write_active("- [ ] TASK-1: present task")
        (self.project / "dirty.txt").write_text("x", encoding="utf-8")
        found = sections(self.state("--until", str(SECOND_BOUNDARY)))
        self.assertIn("Middle request about the gadget", "\n".join(found["Last human request"]))
        self.assertIn("present task", "\n".join(found["Open tasks"]))
        self.assertIn("dirty.txt", "\n".join(found["Uncommitted changes"]))
        self.assertRegex("\n".join(found["Branch"]), r"trunk @ [0-9a-f]{7,}")


class AtCommitTests(BoundaryFixture):
    def setUp(self):
        super().setUp()
        self.git("init", "-q", "-b", "trunk")
        compass = self.project / ".compass"
        (compass / "specs").mkdir()
        (compass / "decisions").mkdir()
        self.write_active("# Active", "- [ ] TASK-1: first commit task", "- [ ] TASK-2: shared task",
                          "- [x] TASK-3: finished")
        (compass / "specs" / "SPEC-001-foo.md").write_text(AT_SPEC_FIRST, encoding="utf-8")
        (compass / "decisions" / "ADR-001-bar.md").write_text(AT_ADR_TEXT, encoding="utf-8")
        self.git("add", ".compass")
        self.git("commit", "-q", "-m", "first")
        self.first = self.rev("HEAD")
        self.write_active("# Active", "- [ ] TASK-2: shared task", "- [ ] TASK-9: second commit task")
        (compass / "specs" / "SPEC-001-foo.md").write_text(AT_SPEC_SECOND, encoding="utf-8")
        (compass / "specs" / "SPEC-002-late.md").write_text(AT_LATE_TEXT, encoding="utf-8")
        self.git("rm", "-q", ".compass/decisions/ADR-001-bar.md")
        self.git("add", ".compass")
        self.git("commit", "-q", "-m", "second")
        self.second = self.rev("HEAD")
        self.write_active("- [ ] TASK-2: shared task", "- [ ] TASK-77: uncommitted task")
        (self.project / "dirty.txt").write_text("x", encoding="utf-8")
        touched = [str(compass / "specs" / "SPEC-001-foo.md"), str(compass / "specs" / "SPEC-002-late.md"),
                   str(compass / "decisions" / "ADR-001-bar.md")]
        self.touching = self.write_transcript(
            user_human("go"), *[read_of(f"r{n}", path) for n, path in enumerate(touched)],
            edit_of("e1", "src/at_edit.py"), path=self.outside / "touching.jsonl")

    def rev(self, ref):
        return subprocess.run(["git", "rev-parse", ref], cwd=self.project, capture_output=True,
                              text=True, check=True).stdout.strip()

    def at(self, ref, *extra, transcript=None):
        code, out, err = self.run_split("--transcript", str(transcript or self.touching), "--at", ref, *extra)
        self.assertEqual(code, 0, err)
        return out

    def test_at_prints_the_open_tasks_of_that_commit_not_the_work_tree(self):
        """Adversarial where: the tasks are read from the working copy or from HEAD, so the
        commit named by `--at` is never consulted."""
        tasks = items(sections(self.at(self.first))["Open tasks"])
        self.assertEqual(tasks, ["- [ ] TASK-1: first commit task", "- [ ] TASK-2: shared task"])

    def test_at_reads_decisions_from_the_commit_including_a_file_since_deleted(self):
        """Adversarial where: D-NN lines come from the working copy, so a spec reworded later
        shows its new text, a spec deleted since shows nothing, and a spec that did not exist
        yet shows up anyway."""
        body = "\n".join(sections(self.at(self.first))["Decisions"])
        self.assertIn("SPEC-001-foo/D-01: The first decision of foo.", body)
        self.assertIn("SPEC-001-foo/D-02: The second decision of foo.", body)
        self.assertNotIn("reworded", body)
        self.assertNotIn("D-03", body)
        self.assertIn("ADR-001-bar/D-01: The only decision of bar.", body)
        self.assertNotIn("SPEC-002-late", body)

    def test_at_the_later_commit_swaps_the_tasks_and_decisions_to_that_commits(self):
        """Adversarial where: `--at` always shows the first state it ever parsed, or ignores
        the commit argument and uses a fixed ancestor."""
        found = sections(self.at(self.second))
        self.assertEqual(items(found["Open tasks"]),
                         ["- [ ] TASK-2: shared task", "- [ ] TASK-9: second commit task"])
        body = "\n".join(found["Decisions"])
        self.assertIn("SPEC-001-foo/D-03:", body)
        self.assertIn("SPEC-002-late/D-01:", body)
        self.assertNotIn("ADR-001-bar", body)

    def test_at_leaves_out_uncommitted_changes_and_names_the_commit_in_the_branch_line(self):
        """Adversarial where: the dirty work tree still prints under `--at`, or the branch line
        keeps `trunk @ <head>` or echoes the ref text instead of the resolved short commit."""
        for ref in (self.first, "HEAD~1"):
            with self.subTest(ref):
                found = sections(self.at(ref))
                self.assertNotIn("Uncommitted changes", found)
                branch = "\n".join(found["Branch"]).strip()
                match = re.fullmatch(r"at ([0-9a-f]{7,40})", branch)
                self.assertIsNotNone(match, branch)
                self.assertTrue(self.first.startswith(match.group(1)), branch)

    def test_at_alone_keeps_every_transcript_section_whole(self):
        """Adversarial where: `--at` also cuts the transcript sections, so each flag does not
        work alone."""
        found = sections(self.at(self.first, transcript=self.transcript))
        self.assertIn("Final request about the sprocket", "\n".join(found["Last human request"]))
        self.assertIn("- src/edit_final.py", items(found["Files edited"]))
        self.assertIn("2 failed final", "\n".join(found["Last test run"]))
        self.assertIn("- [ ] TASK-1: first commit task", items(found["Open tasks"]))

    def test_at_with_a_file_absent_at_the_commit_contributes_nothing_and_exits_zero(self):
        """Adversarial where: a spec or the active list missing at the commit falls back to the
        working copy or crashes the block."""
        self.git("rm", "-q", "--cached", ".compass/active.md")
        self.git("commit", "-q", "-m", "drop active")
        self.write_transcript(user_human("go"), path=self.outside / "empty.jsonl")
        found = sections(self.at("HEAD", transcript=self.outside / "empty.jsonl"))
        self.assertNotIn("Open tasks", found)
        self.assertNotIn("Decisions", found)

    def test_unknown_commit_exits_one_naming_it(self):
        """Adversarial where: an unresolvable commit yields an empty state with exit 0, or an
        error that does not name the commit."""
        for ref in ("no-such-commit", "0123456789abcdef0123456789abcdef01234567"):
            with self.subTest(ref):
                code, out, err = self.run_split("--transcript", str(self.touching), "--at", ref)
                self.assertEqual(code, 1)
                self.assertIn(ref, err)
                self.assertEqual(out, "")

    def test_until_and_at_together_cut_the_transcript_and_move_the_vault(self):
        """Adversarial where: the two flags exclude each other, or one overrides the other's
        section."""
        found = sections(self.at(self.first, "--until", str(SECOND_BOUNDARY), transcript=self.transcript))
        self.assertIn("Middle request about the gadget", "\n".join(found["Last human request"]))
        self.assertNotIn("- src/edit_final.py", items(found["Files edited"]))
        self.assertIn("- [ ] TASK-1: first commit task", items(found["Open tasks"]))
        self.assertNotIn("Uncommitted changes", found)


class FlagRefusalAndCompatibilityTests(BoundaryFixture):
    def hook_event(self):
        return json.dumps({"hook_event_name": "SessionStart", "source": "compact",
                           "transcript_path": str(self.transcript)})

    def test_hook_beside_either_flag_exits_one_with_the_usage_and_no_json(self):
        """Adversarial where: the hook path reads `--until` or `--at` (or ignores them and
        prints the block as JSON), instead of refusing with the usage line."""
        rows = {
            "until after hook": ["--hook", "--until", "3"],
            "until before hook": ["--until", "3", "--hook"],
            "at after hook": ["--hook", "--at", "HEAD"],
            "equals spelling": ["--hook", "--until=3"],
        }
        for name, args in rows.items():
            with self.subTest(name):
                code, out, err = self.run_split(*args, stdin=self.hook_event())
                self.assertEqual(code, 1)
                self.assertNotIn("hookSpecificOutput", out)
                self.assertNotIn("additionalContext", out)
                usage = [ln for ln in (out + err).splitlines() if ln.startswith("compass session-state")]
                self.assertTrue(any("--until" in ln for ln in usage), out + err)
                self.assertTrue(any("--at" in ln for ln in usage), out + err)

    def test_without_either_flag_the_output_is_byte_identical_to_the_prior_command(self):
        """Adversarial where: adding the flags changes the default rendering (ordering, a new
        section, trailing text) of the block or the handoff on the existing fixture."""
        self.init_repo()
        self.write_active("# Active", "- [ ] TASK-1: first open", "- [x] TASK-2: done", "- [ ] TASK-3: second open")
        shutil.copy(STATE_FIXTURE, self.transcript)
        shutil.rmtree(self.transcript.with_suffix("") / "subagents")
        shutil.copytree(STATE_FIXTURE.with_suffix("") / "subagents", self.transcript.with_suffix("") / "subagents")
        (self.project / "dirty.txt").write_text("x", encoding="utf-8")
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.project,
                             capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(self.state().replace(sha, "<SHA>"), GOLDEN_BLOCK)
        self.assertEqual(self.state("--format", "handoff").replace(sha, "<SHA>"), GOLDEN_HANDOFF)



def boundary_record(timestamp=None):
    record = {"type": "system", "subtype": "compact_boundary", "content": "Conversation compacted"}
    if timestamp is not None:
        record["timestamp"] = timestamp
    return record


MISSING = object()


def head_of(project):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=project, capture_output=True,
                          text=True, check=True).stdout.strip()


class SubagentStampTests(StateFixture):
    """Subagent records are kept by comparing their `timestamp` with the boundary's."""

    BOUNDARY_STAMP = "2026-01-01T09:00:00Z"
    BOUNDARY_INDEX = 1

    def setUp(self):
        super().setUp()
        self.side = self.outside / "session" / "subagents"
        self.side.mkdir(parents=True)

    def main_with_boundary(self, stamp=BOUNDARY_STAMP):
        self.write_transcript(user_human("before"), boundary_record(stamp), user_human("after"))

    def sub_edit(self, tag, timestamp=MISSING):
        records = edit_of(f"c-{tag}", f"src/{tag}.py")
        if timestamp is not MISSING:
            for record in records:
                record["timestamp"] = timestamp
        (self.side / f"agent-{tag}.jsonl").write_bytes(b"".join(json.dumps(r).encode() + b"\n" for r in records))

    def edited_at_boundary(self):
        code, out = self.run_cmd("--transcript", str(self.transcript), "--until", str(self.BOUNDARY_INDEX))
        self.assertEqual(code, 0)
        return {line[2:] for line in items(sections(out).get("Files edited", []))}

    def test_subagent_stamps_are_compared_as_instants_and_unreadable_stamps_are_dropped(self):
        """Adversarial where: stamps are compared as strings or with their offset ignored, a
        naive stamp or one with microseconds lands on the wrong side, or a record whose stamp
        is missing, null, numeric or unparseable is kept (or crashes the cut)."""
        self.main_with_boundary()
        rows = {
            "offset stamp earlier in UTC but later as text": ("plus2", "2026-01-01T10:30:00+02:00", True),
            "offset stamp later in UTC but earlier as text": ("minus2", "2026-01-01T08:30:00-02:00", False),
            "naive stamp one second before": ("naive_in", "2026-01-01T08:59:59", True),
            "naive stamp one second after": ("naive_out", "2026-01-01T09:00:01", False),
            "one microsecond before": ("us_in", "2026-01-01T08:59:59.999999Z", True),
            "one microsecond after": ("us_out", "2026-01-01T09:00:00.000001Z", False),
            "nanosecond fraction before": ("ns_in", "2026-01-01T08:59:59.999999999Z", True),
            "missing stamp": ("none", MISSING, False),
            "null stamp": ("null", None, False),
            "epoch number as stamp": ("epoch", 1767258000, False),
            "words as stamp": ("words", "yesterday", False),
            "empty stamp": ("empty", "", False),
        }
        for tag, stamp, _ in rows.values():
            self.sub_edit(tag, stamp)
        kept = self.edited_at_boundary()
        for name, (tag, _, expected) in rows.items():
            with self.subTest(name):
                self.assertEqual(f"src/{tag}.py" in kept, expected, sorted(kept))

    def test_a_boundary_without_a_readable_stamp_keeps_no_subagent_record(self):
        """Adversarial where: a boundary with no readable timestamp compares every subagent
        record against nothing and keeps all of them, or crashes the cut."""
        for name, stamp in {"absent": None, "words": "later", "empty": ""}.items():
            with self.subTest(name):
                self.main_with_boundary(stamp)
                self.sub_edit("only", "2026-01-01T08:00:00Z")
                self.assertEqual(self.edited_at_boundary(), set())

    def test_a_subagent_file_with_some_bad_lines_keeps_exactly_its_good_early_lines(self):
        """Adversarial where: one unparseable, non-object, binary or unstamped line in a
        subagent file drops the whole file, or the last line without a newline fuses with
        the line before it."""
        self.main_with_boundary()

        def encoded(records, stamp):
            return [json.dumps(dict(r, timestamp=stamp) if stamp else r).encode() for r in records]

        lines = [raw + b"\n" for raw in encoded(edit_of("g1", "src/good_early.py"), "2026-01-01T08:00:00Z")]
        lines += [b"{not json\n", b"[1, 2, 3]\n", b"42\n", b"\n", b"\xff\xfe binary noise\n"]
        lines += [raw + b"\n" for raw in encoded(edit_of("g3", "src/late.py"), "2026-01-01T09:30:00Z")]
        lines += [raw + b"\n" for raw in encoded(edit_of("g4", "src/unstamped.py"), None)]
        last = encoded(edit_of("g2", "src/good_last_no_newline.py"), "2026-01-01T08:30:00Z")
        lines += [last[0] + b"\n", last[1]]
        (self.side / "agent-mixed.jsonl").write_bytes(b"".join(lines))
        self.assertEqual(self.edited_at_boundary(), {"src/good_early.py", "src/good_last_no_newline.py"})


class UntilIndexSpellingTests(BoundaryFixture):
    def test_until_accepts_only_a_plain_run_of_digits_and_a_flag_without_a_value_exits_one(self):
        """Adversarial where: a negative, signed, spaced, fractional, hex or empty index is
        coerced into a line number (a negative one counting from the end of the file) instead
        of exiting 1, or a trailing `--until` / `--at` with no value is silently ignored."""
        refused = ["-1", "+24", " 24", "24 ", "24.0", "0x18", "1e1", "24abc", "abc", "", "-0"]
        for value in refused:
            with self.subTest(f"--until {value!r}"):
                code, out, err = self.run_split("--transcript", str(self.transcript), "--until", value)
                self.assertEqual(code, 1)
                self.assertIn("not a compaction boundary", err)
                self.assertEqual(out, "")
        with self.subTest("empty equals spelling"):
            code, out, err = self.run_split("--transcript", str(self.transcript), "--until=")
            self.assertEqual((code, out), (1, ""))
        for flag in ("--until", "--at"):
            with self.subTest(f"trailing {flag}"):
                code, out, err = self.run_split("--transcript", str(self.transcript), flag)
                self.assertEqual((code, out), (1, ""))
                self.assertIn(f"{flag} needs a value", err)
        with self.subTest("another flag as the value"):
            code, out, err = self.run_split("--transcript", str(self.transcript), "--until", "--format", "handoff")
            self.assertEqual((code, out), (1, ""))

    def test_until_with_leading_zeros_names_the_same_line(self):
        """Adversarial where: `--until 0024` is refused or read as octal, so it names a
        different line than `--until 24`."""
        plain = self.state("--until", str(SECOND_BOUNDARY))
        self.assertEqual(self.state("--until", "00" + str(SECOND_BOUNDARY)), plain)

    def test_until_on_files_with_no_line_zero_or_no_final_newline(self):
        """Adversarial where: an empty transcript (no line 0) raises an IndexError that the
        catch-all turns into exit 0, or a boundary on a last line with no newline is not
        recognised."""
        self.transcript.write_bytes(b"")
        code, out, err = self.run_split("--transcript", str(self.transcript), "--until", "0")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("not a compaction boundary", err)
        self.transcript.write_bytes(json.dumps(boundary_record()).encode())
        code, out, err = self.run_split("--transcript", str(self.transcript), "--until", "0")
        self.assertEqual(code, 0, err)

    def test_until_with_no_readable_transcript_exits_one(self):
        """Adversarial where: `--until` with a transcript that cannot be found falls through
        to an empty block and exit 0, as a missing transcript does without the flag."""
        self.transcript.unlink()
        code, out, err = self.run_split("--transcript", str(self.transcript), "--until", "3")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("not a compaction boundary", err)


class AtRefTests(StateFixture):
    def setUp(self):
        super().setUp()
        self.git("init", "-q", "-b", "trunk")
        self.write_active("- [ ] TASK-1: first")
        self.git("add", ".compass")
        self.git("commit", "-q", "-m", "first")
        self.first = head_of(self.project)
        self.git("tag", "-a", "-m", "annotated", "v1")
        self.git("branch", "feature/topic")
        self.write_active("- [ ] TASK-2: second")
        self.git("add", ".compass")
        self.git("commit", "-q", "-m", "second")
        self.write_transcript(user_human("go"))

    def at(self, ref):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            from commands import session_state
            code = session_state.run(["--transcript", str(self.transcript), f"--at={ref}"])
        return code, out.getvalue(), err.getvalue()

    def test_at_resolves_branches_annotated_tags_abbreviations_and_ancestors_to_the_commit(self):
        """Adversarial where: an annotated tag's own object id, a slash-bearing branch name, an
        abbreviated hash or `HEAD~1` is not peeled to its commit, so the tasks or the branch
        line come from the wrong object or the ref is called unknown."""
        for ref in ("v1", "feature/topic", self.first[:8], "HEAD~1", "trunk~1", "v1^{commit}"):
            with self.subTest(ref):
                code, out, err = self.at(ref)
                self.assertEqual(code, 0, err)
                found = sections(out)
                self.assertEqual(items(found["Open tasks"]), ["- [ ] TASK-1: first"])
                match = re.fullmatch(r"at ([0-9a-f]{7,40})", "\n".join(found["Branch"]).strip())
                self.assertIsNotNone(match)
                self.assertTrue(self.first.startswith(match.group(1)))

    def test_at_refuses_refs_that_are_not_commits_or_would_read_as_git_options(self):
        """Adversarial where: a blob or tree rev, an empty ref, a range, or a ref starting with
        a dash is passed to git (option injection) or accepted instead of exiting 1 naming
        it."""
        for ref in ("HEAD:.compass/active.md", "HEAD^{tree}", "", "-q", "--all", "--output=x", "HEAD..HEAD~1"):
            with self.subTest(ref):
                code, out, err = self.at(ref)
                self.assertEqual((code, out), (1, ""))
                self.assertIn(f"unknown commit: {ref}", err)

    def test_at_outside_any_git_repository_exits_one_naming_the_commit(self):
        """Adversarial where: a folder with no git history turns `--at` into an empty state
        with exit 0, as git failing does without the flag."""
        bare = self.root / "nogit"
        (bare / ".compass").mkdir(parents=True)
        os.environ["CLAUDE_PROJECT_DIR"] = str(bare)
        os.chdir(bare)
        code, out, err = self.at("HEAD")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("unknown commit: HEAD", err)


class AtVaultPathTests(StateFixture):
    def test_decisions_come_from_the_commit_for_unicode_spaced_folder_and_relative_spellings(self):
        """Adversarial where: the commit-relative path is built wrong for a spec whose name
        holds spaces or non-ASCII characters, for a folder spec's `index.md`, or for a spec
        the transcript reached by a project-relative path, so the commit's text is not read
        and the working copy (reworded after the commit) shows instead."""
        self.git("init", "-q", "-b", "trunk")
        compass = self.project / ".compass"
        names = {"SPEC 7 éü": "SPEC 7 éü", "SPEC-008-grp/index": "SPEC-008-grp",
                 "SPEC-009-rel": "SPEC-009-rel"}
        for name in names:
            self.add_spec(name)
        self.git("add", ".compass")
        self.git("commit", "-q", "-m", "first")
        commit = head_of(self.project)
        for name in names:
            (compass / "specs" / f"{name}.md").write_text(
                SPEC_TEXT.replace("The first decision", "REWORDED decision"), encoding="utf-8")
        self.write_transcript(
            user_human("go"), read_of("r0", str(compass / "specs" / "SPEC 7 éü.md")),
            read_of("r1", str(compass / "specs" / "SPEC-008-grp" / "index.md")),
            read_of("r2", ".compass/specs/SPEC-009-rel.md"))
        code, out = self.run_cmd("--transcript", str(self.transcript), "--at", commit)
        self.assertEqual(code, 0)
        body = "\n".join(sections(out)["Decisions"])
        for stem in names.values():
            with self.subTest(stem):
                self.assertIn(f"{stem}/D-01: The first decision of foo.", body)
        self.assertNotIn("REWORDED", body)

    def test_spec_renamed_between_commits_contributes_only_under_the_name_it_had_at_the_commit(self):
        """Adversarial where: a path touched under a name the commit does not hold falls back
        to the working copy, or the old name's text leaks into the new name's section."""
        self.git("init", "-q", "-b", "trunk")
        self.add_spec("SPEC-001-old")
        self.git("add", ".compass")
        self.git("commit", "-q", "-m", "first")
        first = head_of(self.project)
        self.git("mv", ".compass/specs/SPEC-001-old.md", ".compass/specs/SPEC-001-new.md")
        self.git("commit", "-q", "-m", "rename")
        base = self.project / ".compass" / "specs"
        self.write_transcript(user_human("go"), read_of("r0", str(base / "SPEC-001-old.md")),
                              read_of("r1", str(base / "SPEC-001-new.md")))
        body = "\n".join(sections(self.block("--at", first))["Decisions"])
        self.assertIn("SPEC-001-old/D-01:", body)
        self.assertNotIn("SPEC-001-new", body)
        body_now = "\n".join(sections(self.block("--at", head_of(self.project)))["Decisions"])
        self.assertIn("SPEC-001-new/D-01:", body_now)
        self.assertNotIn("SPEC-001-old", body_now)

    def test_a_vault_in_a_subfolder_of_the_repository_still_reads_the_commits_files(self):
        """Adversarial where: `git show <commit>:<path>` resolves the path from the repository
        root, so a project whose `.compass` sits one folder below the root finds no active.md
        or spec at the commit and prints no tasks or decisions."""
        repo = self.root / "mono"
        project = repo / "app"
        (project / ".compass" / "specs").mkdir(parents=True)
        (project / ".compass" / "active.md").write_text("- [ ] TASK-1: nested task\n", encoding="utf-8")
        spec = project / ".compass" / "specs" / "SPEC-001-foo.md"
        spec.write_text(SPEC_TEXT, encoding="utf-8")
        for args in (["init", "-q", "-b", "trunk"], ["add", "."], ["commit", "-q", "-m", "first"]):
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                           cwd=repo, check=True, capture_output=True)
        os.environ["CLAUDE_PROJECT_DIR"] = str(project)
        os.chdir(project)
        self.write_transcript(user_human("go"), read_of("r0", str(spec)))
        code, out = self.run_cmd("--transcript", str(self.transcript), "--at", "HEAD")
        self.assertEqual(code, 0)
        found = sections(out)
        self.assertEqual(items(found.get("Open tasks", [])), ["- [ ] TASK-1: nested task"])
        self.assertIn("SPEC-001-foo/D-01:", "\n".join(found.get("Decisions", [])))


class ProjectRootResolutionTests(BoundaryFixture):
    def make_history(self):
        self.git("init", "-q", "-b", "trunk")
        self.write_active("- [ ] TASK-1: committed task")
        self.git("add", ".compass")
        self.git("commit", "-q", "-m", "first")
        self.write_active("- [ ] TASK-9: later task")
        return head_of(self.project)

    def test_flags_work_from_a_cwd_outside_the_repository_when_the_project_dir_is_set(self):
        """Adversarial where: git or the vault read runs in the cwd instead of the project
        root, so `--at` from an unrelated folder reports an unknown commit or reads no tasks."""
        commit = self.make_history()
        os.chdir(self.outside)
        found = sections(self.state("--at", commit, "--until", str(SECOND_BOUNDARY)))
        self.assertEqual(items(found["Open tasks"]), ["- [ ] TASK-1: committed task"])
        self.assertIn("Middle request about the gadget", "\n".join(found["Last human request"]))
        self.assertNotIn("Uncommitted changes", found)

    def test_flags_work_from_a_subfolder_of_the_project_without_the_project_dir_variable(self):
        """Adversarial where: without `CLAUDE_PROJECT_DIR` the root is the cwd, so `--at` run
        from a subfolder resolves the commit and `.compass/active.md` against the subfolder."""
        commit = self.make_history()
        sub = self.project / "deep" / "er"
        sub.mkdir(parents=True)
        os.environ.pop("CLAUDE_PROJECT_DIR")
        os.chdir(sub)
        found = sections(self.state("--at", commit))
        self.assertEqual(items(found["Open tasks"]), ["- [ ] TASK-1: committed task"])


class CapUnderFlagsTests(StateFixture):
    def test_the_eight_thousand_character_cap_and_the_list_caps_hold_under_until_and_at(self):
        """Adversarial where: the commit's active.md or specs, or a cut transcript, reach the
        renderer through a path that skips the list caps and the budget, so a large past state
        prints over 8,000 characters or with every task."""
        self.git("init", "-q", "-b", "trunk")
        tasks = [f"- [ ] TASK-{n:03d}: " + "t" * 200 for n in range(80)]
        self.write_active("# Active", *tasks)
        decisions = "\n".join(f"- **D-{n:02d}:** " + "d" * 300 for n in range(1, 41))
        self.add_spec("SPEC-001-big", text=f"---\ntitle: Big\n---\n\n## Decisions\n\n{decisions}\n")
        self.git("add", ".compass")
        self.git("commit", "-q", "-m", "big")
        commit = head_of(self.project)
        self.write_active("- [ ] TASK-999: present")
        spec = str(self.project / ".compass" / "specs" / "SPEC-001-big.md")
        groups = [user_human("w" * 900), read_of("rs", spec)]
        groups += [edit_of(f"e{n}", "src/" + "p" * 120 + f"_{n}.py", start=n + 1) for n in range(70)]
        groups += [read_of(f"r{n}", "docs/" + "q" * 120 + f"_{n}.md") for n in range(40)]
        groups += [answer_of(f"a{n}", f"Question {n}?", "x" * 200) for n in range(12)]
        groups += [bash_test_run("t1", "python -m pytest -q", "\n".join("o" * 300 for _ in range(10)))]
        groups += [boundary_record("2026-01-01T09:00:00Z"), user_human("after")]
        self.write_transcript(*groups)
        index = len(self.transcript.read_text(encoding="utf-8").splitlines()) - 2
        for args in (["--at", commit], ["--until", str(index)], ["--at", commit, "--until", str(index)]):
            with self.subTest(" ".join(args)):
                out = self.block(*args)
                self.assertLessEqual(len(out), 8000)
                found = sections(out)
                self.assertEqual(list(found), [h for h in ORDER if h in found])
                self.assertIn("Last human request", found)
                self.assertIn("Open tasks", found)
                if "--at" in args:
                    self.assertIn("... and 55 more", "\n".join(found["Open tasks"]))
                    self.assertNotIn("TASK-999", out)
        with self.subTest("handoff format"):
            out = self.block("--at", commit, "--until", str(index), "--format", "handoff")
            self.assertIn("... and 55 more", "\n".join(sections(out)["Tasks"]))


class UntilAtInteractionTests(StateFixture):
    def test_a_spec_touched_only_after_the_boundary_adds_no_decisions_at_the_commit(self):
        """Adversarial where: `--at` collects touched documents from the whole transcript
        instead of the cut one, so decisions of a spec first read after the boundary appear
        in the state of that earlier moment."""
        self.git("init", "-q", "-b", "trunk")
        self.add_spec("SPEC-001-early")
        self.add_spec("SPEC-002-late", text=SPEC_TEXT.replace("first decision of foo", "decision of the late spec"))
        self.git("add", ".compass")
        self.git("commit", "-q", "-m", "first")
        base = self.project / ".compass" / "specs"
        self.write_transcript(user_human("one"), read_of("r0", str(base / "SPEC-001-early.md")),
                              boundary_record("2026-01-01T09:00:00Z"),
                              read_of("r1", str(base / "SPEC-002-late.md")))
        boundary_index = 3
        body = "\n".join(sections(self.block("--at", "HEAD", "--until", str(boundary_index)))["Decisions"])
        self.assertIn("SPEC-001-early/D-01:", body)
        self.assertNotIn("SPEC-002-late", body)
        whole = "\n".join(sections(self.block("--at", "HEAD"))["Decisions"])
        self.assertIn("SPEC-002-late/D-01:", whole)


if __name__ == "__main__":
    unittest.main()
