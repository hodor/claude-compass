"""Tests for `compass guard`, the PreToolUse hook that denies a tool call
which would destroy information: deleting or discarding files from Bash,
emptying or gutting a vault file with Write, or blanking a vault passage
with Edit. Scratch areas (the session scratchpad, `.compass/tmp/`, agent
worktrees) stay open so cleanup keeps working."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import guard  # noqa: E402


class GuardFixture(unittest.TestCase):
    def setUp(self):
        self.project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.project, True)
        self.vault = self.project / ".compass"
        (self.vault / "specs").mkdir(parents=True)
        (self.vault / "tmp").mkdir()
        (self.project / "src").mkdir()
        self.env_backup = dict(os.environ)
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self.env_backup)))

    def decide(self, tool_name, tool_input):
        return guard.decide(tool_name, tool_input, self.project)

    def bash(self, command):
        return self.decide("Bash", {"command": command})

    def assert_denied(self, verdict, *needles):
        denied, reason = verdict
        self.assertTrue(denied, f"expected a denial, got allow: {reason!r}")
        for needle in needles:
            self.assertIn(needle, reason)

    def assert_allowed(self, verdict):
        denied, reason = verdict
        self.assertFalse(denied, f"expected allow, got denial: {reason!r}")


class BashDeletionTests(GuardFixture):
    def test_rm_of_a_project_file_is_denied_naming_the_rule(self):
        # Defect class: a subagent under bypassPermissions removes files
        # with no prompt and no rule standing in front of it.
        self.assert_denied(self.bash("rm -rf src/old"), "rm", "archive")

    def test_each_deleting_command_is_denied(self):
        # Defect class: only `rm` is guarded and every sibling spelling of
        # delete walks through.
        cases = {
            "rmdir src/old": "rmdir",
            "del src\\old.py": "del",
            "Remove-Item -Recurse src/old": "Remove-Item",
            "rd /s /q src\\old": "rd",
            "git rm -r src/old": "git rm",
            "git clean -fd": "git clean",
            "git checkout -- src/main.py": "git checkout --",
            "git restore src/main.py": "git restore",
            "git reset --hard HEAD~1": "git reset --hard",
            "git branch -D feature": "git branch -D",
            "find src -name '*.bak' -delete": "find -delete",
            "find src -name '*.bak' -exec rm {} \\;": "rm",
            "ls src | xargs rm": "rm",
            "python -c \"import shutil; shutil.rmtree('src/old')\"": "rmtree",
            "python -c \"import os; os.unlink('src/a.py')\"": "unlink",
            "trash src/old": "trash",
        }
        for command, token in cases.items():
            with self.subTest(command=command):
                self.assert_denied(self.bash(command), token)

    def test_delete_hidden_behind_a_chain_is_still_denied(self):
        # Defect class: the guard reads only the first command of a line.
        for command in (
            "ls && rm -rf src/old",
            "echo ok; rm src/a.py",
            "true || rm src/a.py",
            "cd src && rm a.py",
            "ls\nrm src/a.py",
            "sudo rm -rf src/old",
            "FOO=1 rm src/a.py",
        ):
            with self.subTest(command=command):
                self.assert_denied(self.bash(command), "rm")

    def test_word_rm_inside_another_token_is_not_a_delete(self):
        # Defect class: a substring match denies `grep rm`, `format`, `rmdir`
        # mentioned in text, or a path containing rm.
        for command in (
            "grep -rn 'rm -rf' docs/",
            "python -m pytest tests/ -q",
            "echo 'do not rm this'",
            "cat src/firmware.c",
            "git log --format=%s",
            "ls storm/",
            "git status --short",
            "git checkout feature-branch",
            "git reset --soft HEAD~1",
            "git branch -d merged-branch",
            "git stash",
            "mv src/a.py src/b.py",
            "git mv src/a.py src/b.py",
        ):
            with self.subTest(command=command):
                self.assert_allowed(self.bash(command))

    def test_scratch_paths_stay_deletable(self):
        # Defect class: the guard blocks cleanup of the session scratchpad,
        # the vault tmp dir, and agent worktrees, breaking every builder.
        scratch = Path(tempfile.gettempdir()) / "claude" / "x" / "scratchpad"
        for command in (
            f"rm -rf {scratch}/clone",
            f"rm -rf \"{scratch}/clone\"",
            "rm -rf .compass/tmp/phase-reports/old",
            f"rm -rf {self.vault / 'tmp' / 'x'}",
            "rm -rf .claude/worktrees/agent-abc",
            "rm -rf __pycache__ src/__pycache__",
            "rm src/a.pyc",
            "rm -rf /tmp/build-123",
        ):
            with self.subTest(command=command):
                self.assert_allowed(self.bash(command))

    def test_one_project_path_among_scratch_paths_denies_the_whole_command(self):
        # Defect class: a deleted project file rides along with scratch
        # cleanup and the guard only checks the first path.
        self.assert_denied(self.bash("rm -rf .compass/tmp/x src/a.py"), "rm")

    def test_delete_with_no_path_argument_is_denied(self):
        # Defect class: `git clean -fd` names no path so the path filter
        # finds nothing to object to and allows it.
        self.assert_denied(self.bash("git clean -fdx"), "git clean")

    def test_truncating_an_existing_vault_file_is_denied(self):
        # Defect class: `: > file` empties a vault document without any
        # delete verb appearing in the command.
        target = self.vault / "specs" / "SPEC-001-a.md"
        target.write_text("---\ntitle: a\n---\nbody\n", encoding="utf-8")
        self.assert_denied(self.bash(": > .compass/specs/SPEC-001-a.md"), "truncat")
        self.assert_allowed(self.bash("echo hi > .compass/tmp/log.txt"))
        self.assert_allowed(self.bash("echo hi >> .compass/specs/SPEC-001-a.md"))


class WriteTests(GuardFixture):
    def _spec(self, body):
        path = self.vault / "specs" / "SPEC-001-a.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_emptying_an_existing_file_is_denied_anywhere(self):
        # Defect class: a Write of empty content is a delete in disguise.
        src = self.project / "src" / "a.py"
        src.write_text("print(1)\n", encoding="utf-8")
        self.assert_denied(self.decide("Write", {"file_path": str(src), "content": ""}), "empt")
        self.assert_denied(self.decide("Write", {"file_path": str(src), "content": "  \n"}), "empt")

    def test_gutting_a_vault_file_is_denied_with_the_archive_route(self):
        # Defect class: a Write that keeps a third of a spec destroys the
        # rest, which the Data rule forbids; the reason names where the
        # text should go instead.
        path = self._spec("---\ntitle: a\n---\n" + "line of spec text\n" * 60)
        verdict = self.decide("Write", {"file_path": str(path), "content": "---\ntitle: a\n---\nshort\n"})
        self.assert_denied(verdict, "archive")

    def test_rewriting_a_vault_file_with_most_text_kept_is_allowed(self):
        # Defect class: the shrink threshold blocks ordinary editing.
        body = "---\ntitle: a\n---\n" + "line of spec text\n" * 60
        path = self._spec(body)
        trimmed = body.replace("line of spec text\n" * 10, "", 1)
        self.assert_allowed(self.decide("Write", {"file_path": str(path), "content": trimmed}))

    def test_source_file_rewrite_that_shrinks_is_allowed(self):
        # Defect class: the vault shrink rule leaks onto source code, where
        # a rewrite that removes dead code is normal work.
        src = self.project / "src" / "a.py"
        src.write_text("x = 1\n" * 100, encoding="utf-8")
        self.assert_allowed(self.decide("Write", {"file_path": str(src), "content": "x = 1\n"}))

    def test_new_file_and_scratch_writes_are_allowed(self):
        # Defect class: the guard compares against a file that does not
        # exist and denies creation.
        self.assert_allowed(self.decide("Write", {"file_path": str(self.vault / "specs" / "new.md"), "content": ""}))
        tmp = self.vault / "tmp" / "x.md"
        tmp.write_text("a\n" * 50, encoding="utf-8")
        self.assert_allowed(self.decide("Write", {"file_path": str(tmp), "content": ""}))

    def test_archive_and_done_files_may_be_rewritten_by_the_sweep(self):
        # Defect class: the sync sweep's own rewrite of active.md, which
        # moves sections to archive/done.md, is denied as a gut.
        active = self.vault / "active.md"
        active.write_text("# Active\n\n" + "- [x] TASK-001: done\n" * 40, encoding="utf-8")
        self.assert_allowed(self.decide("Write", {"file_path": str(active), "content": "# Active\n"}))


class EditTests(GuardFixture):
    def test_blanking_a_long_vault_passage_is_denied(self):
        # Defect class: an Edit with an empty replacement removes a section
        # of a spec with no delete verb anywhere.
        path = self.vault / "specs" / "SPEC-001-a.md"
        passage = "\n".join(f"line {i}" for i in range(12))
        path.write_text("---\ntitle: a\n---\n" + passage + "\n", encoding="utf-8")
        verdict = self.decide("Edit", {"file_path": str(path), "old_string": passage, "new_string": ""})
        self.assert_denied(verdict, "archive")

    def test_short_blanking_and_replacements_are_allowed(self):
        # Defect class: every Edit that shortens text is denied, which is
        # every edit that fixes prose.
        path = self.vault / "specs" / "SPEC-001-a.md"
        path.write_text("---\ntitle: a\n---\nsome text here\n", encoding="utf-8")
        self.assert_allowed(self.decide("Edit", {"file_path": str(path), "old_string": "some text here", "new_string": ""}))
        self.assert_allowed(self.decide("Edit", {"file_path": str(path), "old_string": "some text here", "new_string": "other"}))

    def test_source_edits_are_never_judged(self):
        # Defect class: the vault passage rule leaks onto source code.
        src = self.project / "src" / "a.py"
        passage = "\n".join(f"x{i} = {i}" for i in range(30))
        src.write_text(passage + "\n", encoding="utf-8")
        self.assert_allowed(self.decide("Edit", {"file_path": str(src), "old_string": passage, "new_string": ""}))


class HookContractTests(GuardFixture):
    def _run(self, payload):
        sys.stdin = io.StringIO(json.dumps(payload))
        self.addCleanup(setattr, sys, "stdin", sys.__stdin__)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = guard.run(["--hook"])
        return code, out.getvalue(), err.getvalue()

    def test_denial_is_a_json_deny_decision_on_exit_zero(self):
        # Defect class: the CLI clamps exit 2 to 1, so a denial by exit
        # code never reaches the runtime; the JSON contract must carry it.
        code, out, _ = self._run({
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "agent_id": "abc", "agent_type": "builder",
            "tool_input": {"command": "rm -rf src"},
        })
        self.assertEqual(code, 0)
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(decision["hookEventName"], "PreToolUse")
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("rm", decision["permissionDecisionReason"])

    def test_allow_prints_nothing_and_exits_zero(self):
        # Defect class: an allow that prints JSON changes the runtime's
        # default permission flow.
        code, out, err = self._run({
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": "ls"},
        })
        self.assertEqual((code, out, err), (0, "", ""))

    def test_malformed_stdin_allows(self):
        # Defect class: a guard that fails closed on a parse error blocks
        # every tool call in the session.
        sys.stdin = io.StringIO("not json")
        self.addCleanup(setattr, sys, "stdin", sys.__stdin__)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = guard.run(["--hook"])
        self.assertEqual((code, out.getvalue()), (0, ""))

    def test_main_agent_calls_are_never_judged(self):
        # Defect class: the guard fences the human's own session, so the
        # main agent cannot clean up a project file the human asked about.
        code, out, err = self._run({
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": "rm -rf src"},
        })
        self.assertEqual((code, out, err), (0, "", ""))

    def test_subagent_calls_are_judged_the_same(self):
        # Defect class: a subagent under bypassPermissions is treated as trusted.
        code, out, _ = self._run({
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "agent_id": "abc", "agent_type": "builder", "permission_mode": "bypassPermissions",
            "tool_input": {"command": "git clean -fd"},
        })
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")


if __name__ == "__main__":
    unittest.main()
