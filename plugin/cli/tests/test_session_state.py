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


if __name__ == "__main__":
    unittest.main()
