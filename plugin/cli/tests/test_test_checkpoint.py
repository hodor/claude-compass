"""Tests for `compass test-checkpoint`: `record`, `verify`, `open-ids`.

Every checkpoint fixture here is a real git repository - the module's whole
design rests on git being the authority over checkpointed content and
membership, so a mocked git would test nothing about tamper-evidence. Cases
are adversarial for the classifier: each one is a specific way a builder
could alter a checkpointed test file (or the fixtures around it) while
hoping `verify` calls it `unchanged` or `added-only` instead of `modified`.
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import test_checkpoint  # noqa: E402

INIT_SRC = "HELPER = 1\n"

BASELINE_SRC = (
    "import unittest\n"
    "\n"
    "\n"
    "CONST = 1\n"
    "\n"
    "\n"
    "class FooTests(unittest.TestCase):\n"
    "    def test_a(self):\n"
    "        \"\"\"Adversarial where CONST silently drifts from 1.\"\"\"\n"
    "        self.assertEqual(CONST, 1)\n"
    "\n"
    "    def test_b(self):\n"
    "        \"\"\"Adversarial where truthiness is inverted.\"\"\"\n"
    "        self.assertTrue(True)\n"
)


def write_file(repo_root, rel, content):
    path = repo_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    return path


def git_init(repo_root):
    subprocess.run(["git", "init", "-q"], cwd=str(repo_root), check=True)


def git_commit_all(repo_root, message):
    subprocess.run(["git", "add", "-A"], cwd=str(repo_root), check=True)
    subprocess.run(
        [
            "git", "-c", "user.email=test@example.com", "-c", "user.name=test",
            "commit", "-q", "-m", message,
        ],
        cwd=str(repo_root), check=True,
    )
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo_root),
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def make_repo_vault(test_case):
    """A fresh git repository with an empty `.compass/` at its root.
    `.compass/tmp/` is gitignored, matching production: a checkpoint commit
    must never accidentally include the checkpoint index it is about to be
    checkpointed under. The `.gitignore` lands in its own commit so every
    later checkpoint commit stays dedicated to just the test files being
    checkpointed - `verify` derives `.py` membership from the whole commit's
    diff regardless of what the index's `files` list says, so a commit
    mixed with unrelated `.py` files would otherwise surface them as
    spurious checkpointed entries."""
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    (tmp / ".compass").mkdir()
    git_init(tmp)
    write_file(tmp, ".gitignore", ".compass/tmp/\n")
    git_commit_all(tmp, "initial: gitignore")
    return tmp


def with_vault_env(test_case, repo_root):
    old = os.environ.get("CLAUDE_PROJECT_DIR")
    os.environ["CLAUDE_PROJECT_DIR"] = str(repo_root)

    def restore():
        if old is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = old

    test_case.addCleanup(restore)


def run_cli(argv):
    """Invoke `test_checkpoint.run` capturing stdout/stderr. Returns
    `(code, stdout, stderr)`."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = test_checkpoint.run(argv)
    return code, out.getvalue(), err.getvalue()


def checkpoint_path(repo_root, task):
    return repo_root / ".compass" / "tmp" / "test-checkpoints" / f"{task}.json"


def build_checkpoint(test_case, task="TASK-100"):
    """A repo+vault with `tests/__init__.py` and `tests/test_foo.py`
    (`BASELINE_SRC`) committed and checkpointed as `task`. Returns
    `(repo_root, sha)`."""
    repo_root = make_repo_vault(test_case)
    write_file(repo_root, "tests/__init__.py", INIT_SRC)
    write_file(repo_root, "tests/test_foo.py", BASELINE_SRC)
    sha = git_commit_all(repo_root, f"test({task}): failing tests before implementation")
    with_vault_env(test_case, repo_root)
    code, out, err = run_cli(["record", task, "tests/test_foo.py", "--commit", sha])
    test_case.assertEqual(code, 0, out + err)
    return repo_root, sha


class RecordTests(unittest.TestCase):
    def test_record_writes_index_through_write_text_lf(self):
        """Adversarial where the index is written with CRLF on a Windows
        host, so a later `git diff` on the vault sees every checkpoint as a
        full-file rewrite."""
        repo_root, sha = build_checkpoint(self, "TASK-101")
        raw = checkpoint_path(repo_root, "TASK-101").read_bytes()
        self.assertNotIn(b"\r\n", raw)
        self.assertNotIn(b"\r", raw)
        record = json.loads(raw.decode("utf-8"))
        self.assertEqual(record["commit"], sha)

    def test_record_without_commit_on_code_task_exits_1(self):
        """Adversarial where a task is 'checkpointed' with no commit at all,
        so `verify` would have nothing tamper-evident to re-read - the hole
        this whole mechanism exists to close."""
        repo_root = make_repo_vault(self)
        write_file(repo_root, "tests/test_foo.py", BASELINE_SRC)
        with_vault_env(self, repo_root)
        code, out, err = run_cli(["record", "TASK-102", "tests/test_foo.py"])
        self.assertEqual(code, 1)
        self.assertIn("--commit", err)

    def test_record_file_not_part_of_commit_exits_1(self):
        """Adversarial where a file path is checkpointed against a commit
        that never touched it, so the recorded SHA-256 would not match
        anything git can re-derive."""
        repo_root = make_repo_vault(self)
        write_file(repo_root, "tests/test_foo.py", BASELINE_SRC)
        sha = git_commit_all(repo_root, "unrelated commit")
        with_vault_env(self, repo_root)
        code, out, err = run_cli(["record", "TASK-103", "tests/other.py", "--commit", sha])
        self.assertEqual(code, 1)
        self.assertIn("not part of commit", err)

    def test_record_not_required_takes_no_files_exits_0(self):
        """Adversarial where a prose-only task is silently skipped rather
        than recording the explicit not-required state, making 'skipped
        correctly' indistinguishable from 'never ran'."""
        repo_root = make_repo_vault(self)
        with_vault_env(self, repo_root)
        code, out, err = run_cli(["record", "TASK-104", "--not-required"])
        self.assertEqual(code, 0)
        record = json.loads(checkpoint_path(repo_root, "TASK-104").read_text(encoding="utf-8"))
        self.assertTrue(record["not_required"])
        self.assertEqual(record["files"], [])

    def test_record_twice_without_supersede_exits_1(self):
        """Adversarial where a second `record` call silently overwrites the
        first checkpoint, letting a wrong pre-build test poison every later
        `verify` with no correction path."""
        repo_root, sha = build_checkpoint(self, "TASK-105")
        code, out, err = run_cli(["record", "TASK-105", "tests/test_foo.py", "--commit", sha])
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)


class NestedRepoTests(unittest.TestCase):
    """A workspace whose code lives in a nested repository the workspace's
    own repo ignores (`addons/toolkit/`): the checkpoint commit exists only
    in the nested repo."""

    def make_nested(self, task="TASK-120"):
        workspace = make_repo_vault(self)
        write_file(workspace, ".gitignore", ".compass/tmp/\naddons/\n")
        git_commit_all(workspace, "ignore nested repos")
        nested = workspace / "addons" / "toolkit"
        nested.mkdir(parents=True)
        git_init(nested)
        write_file(nested, "README.md", "toolkit\n")
        git_commit_all(nested, "initial")
        write_file(nested, "tests/__init__.py", INIT_SRC)
        write_file(nested, "tests/test_foo.py", BASELINE_SRC)
        sha = git_commit_all(nested, f"test({task}): failing tests")
        with_vault_env(self, workspace)
        return workspace, nested, sha

    def test_record_and_verify_against_a_commit_in_a_nested_repo(self):
        """Adversarial where the checkpoint commit lives only in the nested
        repo and the workspace repo is asked for it - 'commit not found'."""
        workspace, nested, sha = self.make_nested()
        code, out, err = run_cli(["record", "TASK-120", "addons/toolkit/tests/test_foo.py", "--commit", sha])
        self.assertEqual(code, 0, out + err)
        record = json.loads(checkpoint_path(workspace, "TASK-120").read_text(encoding="utf-8"))
        self.assertEqual(record["repo"], "addons/toolkit")
        self.assertEqual(record["files"][0]["path"], "tests/test_foo.py")
        self.assertEqual([s["path"] for s in record["support_surface"]], ["tests/__init__.py"])
        code, out, err = run_cli(["verify", "TASK-120"])
        self.assertEqual(code, 0, out + err)
        self.assertIn("unchanged", out)

    def test_verify_catches_a_modification_in_the_nested_repo(self):
        """Adversarial where verify reads the workspace tree instead of the
        nested one and reports the edited file as missing or unchanged."""
        workspace, nested, sha = self.make_nested("TASK-121")
        run_cli(["record", "TASK-121", "addons/toolkit/tests/test_foo.py", "--commit", sha])
        write_file(nested, "tests/test_foo.py", BASELINE_SRC.replace("assertEqual(CONST, 1)", "assertEqual(CONST, CONST)"))
        code, out, err = run_cli(["verify", "TASK-121"])
        self.assertEqual(code, 1)
        self.assertIn("modified", out)
        self.assertIn("tests/test_foo.py", out)

    def test_absolute_file_path_in_a_nested_repo_is_accepted(self):
        workspace, nested, sha = self.make_nested("TASK-122")
        code, out, err = run_cli(["record", "TASK-122", str(nested / "tests" / "test_foo.py"), "--commit", sha])
        self.assertEqual(code, 0, out + err)

    def test_file_path_relative_to_the_cwd_inside_the_nested_repo(self):
        """Adversarial where a builder working inside the nested repo passes
        a cwd-relative path and it is resolved against the workspace."""
        workspace, nested, sha = self.make_nested("TASK-125")
        cwd = os.getcwd()
        os.chdir(nested)
        self.addCleanup(os.chdir, cwd)
        code, out, err = run_cli(["record", "TASK-125", "tests/test_foo.py", "--commit", sha])
        self.assertEqual(code, 0, out + err)
        record = json.loads(checkpoint_path(workspace, "TASK-125").read_text(encoding="utf-8"))
        self.assertEqual(record["repo"], "addons/toolkit")

    def test_files_spanning_two_repos_are_refused(self):
        """Adversarial where one checkpoint mixes repos, so one of its files
        can never be re-read at the recorded commit."""
        workspace, nested, sha = self.make_nested("TASK-123")
        write_file(workspace, "tests/test_top.py", BASELINE_SRC)
        git_commit_all(workspace, "top-level test")
        code, out, err = run_cli(["record", "TASK-123", "addons/toolkit/tests/test_foo.py",
                                  "tests/test_top.py", "--commit", sha])
        self.assertEqual(code, 1)
        self.assertIn("more than one git repository", err)
        self.assertFalse(checkpoint_path(workspace, "TASK-123").exists())

    def test_workspace_repo_checkpoint_records_dot_and_old_index_without_repo_still_verifies(self):
        """Adversarial where an index written before `repo` existed is read
        as pointing nowhere."""
        repo_root, sha = build_checkpoint(self, "TASK-124")
        path = checkpoint_path(repo_root, "TASK-124")
        record = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(record["repo"], ".")
        del record["repo"]
        path.write_text(json.dumps(record), encoding="utf-8")
        code, out, err = run_cli(["verify", "TASK-124"])
        self.assertEqual(code, 0, out + err)


class ClassificationTests(unittest.TestCase):
    """Every case rewrites `tests/test_foo.py` on disk without committing -
    `verify` reads the current state straight off the working tree - then
    checks the reported status against the baseline recorded by
    `build_checkpoint`."""

    def _verify(self, task="TASK-100", extra=None):
        return run_cli(["verify", task, *(extra or [])])

    def test_verify_untouched_reports_unchanged_exits_0(self):
        """Adversarial where the classifier reports every unmodified
        checkpoint as tampered, which would make the guard fail every green
        run on its own baseline."""
        build_checkpoint(self, "TASK-100")
        code, out, err = self._verify()
        self.assertEqual(code, 0, out + err)
        self.assertIn("unchanged", out)

    def test_verify_new_test_function_reports_added_only_exits_0(self):
        """Adversarial where a builder appends a legitimate implementation-
        visible test and the classifier flags it as tampering, which would
        make post-build testing itself impossible under the checkpoint."""
        repo_root, _ = build_checkpoint(self, "TASK-100")
        added = BASELINE_SRC + (
            "\n"
            "    def test_c(self):\n"
            "        \"\"\"Adversarial where a third case is silently dropped.\"\"\"\n"
            "        self.assertFalse(False)\n"
        )
        write_file(repo_root, "tests/test_foo.py", added)
        code, out, err = self._verify()
        self.assertEqual(code, 0, out + err)
        self.assertIn("added-only", out)

    def test_verify_changed_assertion_reports_modified_naming_function_exits_1(self):
        """Adversarial where a builder loosens a checkpointed assertion to
        make the implementation pass instead of fixing the implementation,
        and the change is not attributed to the function it altered."""
        repo_root, _ = build_checkpoint(self, "TASK-100")
        modified = BASELINE_SRC.replace("self.assertEqual(CONST, 1)", "self.assertEqual(CONST, 2)")
        write_file(repo_root, "tests/test_foo.py", modified)
        code, out, err = self._verify()
        self.assertEqual(code, 1)
        self.assertIn("modified", out)
        self.assertIn("test_a", out)

    def test_verify_appended_skip_decorator_reports_modified_exits_1(self):
        """Adversarial where a builder neutralizes a checkpointed test with
        `@unittest.skip` instead of editing its body - byte-identical
        function text with a changed decorator list must still be caught."""
        repo_root, _ = build_checkpoint(self, "TASK-100")
        skipped = BASELINE_SRC.replace(
            "    def test_a(self):", "    @unittest.skip(\"flaky\")\n    def test_a(self):"
        )
        write_file(repo_root, "tests/test_foo.py", skipped)
        code, out, err = self._verify()
        self.assertEqual(code, 1)
        self.assertIn("modified", out)
        self.assertIn("test_a", out)

    def test_verify_duplicate_def_shadows_checkpointed_name_reports_modified_exits_1(self):
        """Adversarial where a builder appends a second `def test_a` that
        wins at runtime, leaving the checkpointed one byte-identical and
        therefore invisible to a comparison that only checks each name once."""
        repo_root, _ = build_checkpoint(self, "TASK-100")
        shadowed = BASELINE_SRC + (
            "\n"
            "    def test_a(self):\n"
            "        \"\"\"Adversarial where a shadow definition silently wins.\"\"\"\n"
            "        pass\n"
        )
        write_file(repo_root, "tests/test_foo.py", shadowed)
        code, out, err = self._verify()
        self.assertEqual(code, 1)
        self.assertIn("modified", out)
        self.assertIn("test_a", out)
        self.assertIn("shadow", out.lower())

    def test_verify_added_class_level_assignment_reports_modified_exits_1(self):
        """Adversarial where a builder adds class-level state to change test
        behavior, which is not a `FunctionDef`/`ClassDef` addition and so
        must not be tolerated as `added-only`."""
        repo_root, _ = build_checkpoint(self, "TASK-100")
        extra_assign = BASELINE_SRC + "\n    EXTRA = 2\n"
        write_file(repo_root, "tests/test_foo.py", extra_assign)
        code, out, err = self._verify()
        self.assertEqual(code, 1)
        self.assertIn("modified", out)

    def test_verify_rebound_module_level_name_reports_modified_naming_symbol_exits_1(self):
        """Adversarial where a builder appends a second module-level
        `CONST = 2` after the checkpointed content, changing what every test
        in the file asserts against without editing a single test body."""
        repo_root, _ = build_checkpoint(self, "TASK-100")
        rebound = BASELINE_SRC + "\nCONST = 2\n"
        write_file(repo_root, "tests/test_foo.py", rebound)
        code, out, err = self._verify()
        self.assertEqual(code, 1)
        self.assertIn("modified", out)
        self.assertIn("CONST", out)

    def test_verify_deleted_file_reports_missing_exits_1(self):
        """Adversarial where a checkpointed file is deleted outright rather
        than edited, which a text-diff-only check might treat as having
        nothing left to compare rather than as a finding."""
        repo_root, _ = build_checkpoint(self, "TASK-100")
        (repo_root / "tests" / "test_foo.py").unlink()
        code, out, err = self._verify()
        self.assertEqual(code, 1)
        self.assertIn("missing", out)

    def test_verify_modified_fixture_reports_modified_exits_1(self):
        """Adversarial where a builder edits a shared fixture instead of the
        test file itself, changing what the checkpointed tests assert while
        every checkpointed test file stays byte-identical."""
        repo_root, _ = build_checkpoint(self, "TASK-100")
        write_file(repo_root, "tests/__init__.py", "HELPER = 2\n")
        code, out, err = self._verify()
        self.assertEqual(code, 1)
        self.assertIn("modified", out)
        self.assertIn("__init__.py", out)

    def test_verify_recorded_non_python_file_compares_bytes_not_ast(self):
        """GitHub #7: a recorded .js harness is not Python; AST-parsing it
        folds a tokenizer error into 'modified' even when the file is
        byte-identical to its checkpoint. Recorded non-.py files compare
        byte-wise: identical is clean, an edit is modified."""
        js = 'const s = "harness";\nmodule.exports = s;\n'
        repo_root = make_repo_vault(self)
        write_file(repo_root, "tests/__init__.py", INIT_SRC)
        write_file(repo_root, "tests/test_foo.py", BASELINE_SRC)
        write_file(repo_root, "scripts/_test_node_harness.js", js)
        sha = git_commit_all(repo_root, "test(TASK-111): checkpoint with js harness")
        with_vault_env(self, repo_root)
        code, out, err = run_cli(
            ["record", "TASK-111", "tests/test_foo.py",
             "scripts/_test_node_harness.js", "--commit", sha]
        )
        self.assertEqual(code, 0, out + err)

        code, out, err = self._verify(task="TASK-111")
        self.assertEqual(code, 0, out + err)

        write_file(repo_root, "scripts/_test_node_harness.js", js + "// edited\n")
        code, out, err = self._verify(task="TASK-111")
        self.assertEqual(code, 1)
        self.assertIn("_test_node_harness.js", out)

    def test_verify_unrelated_non_python_file_in_commit_reports_clean_exits_0(self):
        """Adversarial where a checkpoint commit also carries a bundled
        markdown file - a plan updated in the same commit as the tests it
        plans - whose prose happens to be invalid Python; a classifier that
        AST-parses every file the commit touched would report that file
        `modified` on a tokenizer error and fail a checkpoint nothing
        actually tampered with."""
        repo_root = make_repo_vault(self)
        write_file(repo_root, "tests/__init__.py", INIT_SRC)
        write_file(repo_root, "tests/test_foo.py", BASELINE_SRC)
        write_file(
            repo_root, "notes/plan.md",
            "# Plan\n\nWave 1 shipped TASK-078 and TASK-083.\n",
        )
        sha = git_commit_all(repo_root, "test(TASK-110): checkpoint plus unrelated markdown")
        with_vault_env(self, repo_root)
        code, out, err = run_cli(["record", "TASK-110", "tests/test_foo.py", "--commit", sha])
        self.assertEqual(code, 0, out + err)

        code, out, err = self._verify(task="TASK-110")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("plan.md", out)
        self.assertIn("unchanged", out)

    def test_verify_json_file_list_edit_does_not_change_verdict(self):
        """Adversarial where a builder edits the untracked JSON index to
        drop the modified file from its `files` list, hoping `verify` trusts
        the index instead of re-deriving membership from git."""
        repo_root, _ = build_checkpoint(self, "TASK-100")
        modified = BASELINE_SRC.replace("self.assertEqual(CONST, 1)", "self.assertEqual(CONST, 2)")
        write_file(repo_root, "tests/test_foo.py", modified)

        path = checkpoint_path(repo_root, "TASK-100")
        record = json.loads(path.read_text(encoding="utf-8"))
        record["files"] = []
        path.write_text(json.dumps(record), encoding="utf-8")

        code, out, err = self._verify()
        self.assertEqual(code, 1)
        self.assertIn("modified", out)
        self.assertIn("test_a", out)

    def test_verify_commit_sha_absent_from_log_exits_1(self):
        """Adversarial where the JSON's `commit` field is edited to a SHA
        that was never committed, which would let a tamperer fabricate a
        clean baseline out of thin air if `verify` did not check the log."""
        repo_root, _ = build_checkpoint(self, "TASK-100")
        path = checkpoint_path(repo_root, "TASK-100")
        record = json.loads(path.read_text(encoding="utf-8"))
        record["commit"] = "f" * 40
        path.write_text(json.dumps(record), encoding="utf-8")
        code, out, err = self._verify()
        self.assertEqual(code, 1)
        self.assertIn("not found in git log", err)

    def test_verify_tree_flag_classifies_supplied_tree_not_current_checkout(self):
        """Adversarial where a fix-loop check reads the orchestrator's own
        checkout instead of the worktree that is actually changing, making
        the per-cycle guard inert for an entire loop of tampering."""
        repo_root, _ = build_checkpoint(self, "TASK-100")

        alt_tree = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, alt_tree, True)
        write_file(alt_tree, "tests/__init__.py", INIT_SRC)
        write_file(
            alt_tree, "tests/test_foo.py",
            BASELINE_SRC.replace("self.assertEqual(CONST, 1)", "self.assertEqual(CONST, 2)"),
        )

        code_default, out_default, _ = self._verify()
        self.assertEqual(code_default, 0, out_default)
        self.assertIn("unchanged", out_default)

        code_tree, out_tree, _ = self._verify(extra=["--tree", str(alt_tree)])
        self.assertEqual(code_tree, 1)
        self.assertIn("modified", out_tree)

    def test_verify_against_run_skipped_id_exits_1(self):
        """Adversarial where a checkpointed test still exists byte-identical
        but was skipped or errored in the actual run, which neutralizes it
        just as effectively as editing it - and a check that only compares
        file content would miss it entirely."""
        repo_root, _ = build_checkpoint(self, "TASK-100")
        evidence = repo_root / "evidence.txt"
        evidence.write_text(
            "test_a (tests.test_foo.FooTests) ... skipped 'flaky'\n"
            "test_b (tests.test_foo.FooTests) ... ok\n",
            encoding="utf-8",
        )
        code, out, err = self._verify(extra=["--against-run", str(evidence)])
        self.assertEqual(code, 1)
        self.assertIn("not-passed", out)
        self.assertIn("test_a", out)

    def test_verify_against_run_all_passed_marks_landed(self):
        """Adversarial where a checkpoint never gets marked landed even
        after a clean post-build run, so `open-ids` keeps reporting its
        tests as part of the open set forever and 'suite green' can never
        be satisfied again."""
        repo_root, _ = build_checkpoint(self, "TASK-106")
        evidence = repo_root / "evidence.txt"
        evidence.write_text(
            "test_a (tests.test_foo.FooTests) ... ok\n"
            "test_b (tests.test_foo.FooTests) ... ok\n",
            encoding="utf-8",
        )
        code, out, err = self._verify(task="TASK-106", extra=["--against-run", str(evidence)])
        self.assertEqual(code, 0, out + err)
        record = json.loads(checkpoint_path(repo_root, "TASK-106").read_text(encoding="utf-8"))
        self.assertTrue(record["landed"])

    def test_verify_against_run_accepts_modern_unittest_path_format(self):
        """Adversarial where: newer unittest -v repeats the test name inside
        the parenthesized path (`test_a (tests.test_foo.FooTests.test_a)`);
        a parser taking the path's last segment as the class would match
        nothing, and every genuinely passing test would read not-passed."""
        repo_root, _ = build_checkpoint(self, "TASK-107")
        evidence = repo_root / "evidence.txt"
        evidence.write_text(
            "test_a (tests.test_foo.FooTests.test_a) ... ok\n"
            "test_b (tests.test_foo.FooTests.test_b) ... ok\n",
            encoding="utf-8",
        )
        code, out, err = self._verify(task="TASK-107", extra=["--against-run", str(evidence)])
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("not-passed", out)

    def test_verify_against_run_accepts_two_line_docstring_format(self):
        """Adversarial where: a test WITH a docstring prints across two -v
        lines (header `name (path)` alone, then the docstring first line
        carrying `... ok`); a single-line parser reads none of them, so
        precisely the docstring-bearing tests the test-design bar requires
        would all report not-passed."""
        repo_root, _ = build_checkpoint(self, "TASK-108")
        evidence = repo_root / "evidence.txt"
        evidence.write_text(
            "test_a (tests.test_foo.FooTests.test_a)\n"
            "Adversarial where: something breaks. ... ok\n"
            "test_b (tests.test_foo.FooTests)\n"
            "Another docstring line ... ok\n",
            encoding="utf-8",
        )
        code, out, err = self._verify(task="TASK-108", extra=["--against-run", str(evidence)])
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("not-passed", out)

    def test_verify_against_run_accepts_interleaved_stderr_output(self):
        """Adversarial where: a test that writes to stderr during its run
        interleaves that output after `... ` and its bare status token lands
        alone on a later line; a parser requiring status on the header line
        reads such tests as absent, so precisely the tests exercising error
        paths (which print) become unverifiable."""
        repo_root, _ = build_checkpoint(self, "TASK-109")
        evidence = repo_root / "evidence.txt"
        evidence.write_text(
            "test_a (tests.test_foo.FooTests.test_a) ... compass next-num: scope rejected\n"
            "another interleaved line\n"
            "ok\n"
            "test_b (tests.test_foo.FooTests) ... ok\n",
            encoding="utf-8",
        )
        code, out, err = self._verify(task="TASK-109", extra=["--against-run", str(evidence)])
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("not-passed", out)

    def test_verify_against_run_accepts_pytest_verbose_format(self):
        """Adversarial where: the run evidence is a pytest -v transcript
        (`path.py::Class::test PASSED [ 50%]`); a unittest-only parser reads
        every checkpointed test as absent, so a pytest-based project's
        checkpoints can never land (GitHub #33)."""
        repo_root, _ = build_checkpoint(self, "TASK-110")
        evidence = repo_root / "evidence.txt"
        evidence.write_text(
            "tests/test_foo.py::FooTests::test_a PASSED                 [ 50%]\n"
            "tests/test_foo.py::FooTests::test_b PASSED                 [100%]\n",
            encoding="utf-8",
        )
        code, out, err = self._verify(task="TASK-110", extra=["--against-run", str(evidence)])
        self.assertEqual(code, 0, out + err)
        record = json.loads(checkpoint_path(repo_root, "TASK-110").read_text(encoding="utf-8"))
        self.assertTrue(record["landed"])

    def test_verify_against_run_pytest_failed_id_exits_1(self):
        """Adversarial where: a pytest transcript that parses at all could
        map every recognized line to `ok`; a genuinely FAILED checkpointed
        test must still surface as not-passed."""
        repo_root, _ = build_checkpoint(self, "TASK-111")
        evidence = repo_root / "evidence.txt"
        evidence.write_text(
            "tests/test_foo.py::FooTests::test_a FAILED                 [ 50%]\n"
            "tests/test_foo.py::FooTests::test_b PASSED                 [100%]\n",
            encoding="utf-8",
        )
        code, out, err = self._verify(task="TASK-111", extra=["--against-run", str(evidence)])
        self.assertEqual(code, 1)
        self.assertIn("not-passed", out)
        self.assertIn("test_a", out)

    def test_verify_against_run_pytest_param_failure_not_laundered_by_later_pass(self):
        """Adversarial where: a parametrized test prints one line per case
        under the same bare name; a parser that lets the last occurrence win
        would launder `test_a[mid] FAILED` behind `test_a[late] PASSED`."""
        repo_root, _ = build_checkpoint(self, "TASK-112")
        evidence = repo_root / "evidence.txt"
        evidence.write_text(
            "tests/test_foo.py::FooTests::test_a[early] PASSED          [ 25%]\n"
            "tests/test_foo.py::FooTests::test_a[mid] FAILED            [ 50%]\n"
            "tests/test_foo.py::FooTests::test_a[late] PASSED           [ 75%]\n"
            "tests/test_foo.py::FooTests::test_b PASSED                 [100%]\n",
            encoding="utf-8",
        )
        code, out, err = self._verify(task="TASK-112", extra=["--against-run", str(evidence)])
        self.assertEqual(code, 1)
        self.assertIn("not-passed", out)
        self.assertIn("test_a", out)

    def test_verify_against_run_accepts_pytest_status_first_summary_lines(self):
        """Adversarial where: `-rA` short-summary evidence puts the status
        before the node id (`PASSED path.py::Class::test`); a parser bound
        to the -v column order reads such evidence as empty."""
        repo_root, _ = build_checkpoint(self, "TASK-113")
        evidence = repo_root / "evidence.txt"
        evidence.write_text(
            "PASSED tests/test_foo.py::FooTests::test_a\n"
            "PASSED tests/test_foo.py::FooTests::test_b\n",
            encoding="utf-8",
        )
        code, out, err = self._verify(task="TASK-113", extra=["--against-run", str(evidence)])
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("not-passed", out)

    def test_verify_against_run_param_id_holding_double_colon_reads_the_test_name(self):
        """Adversarial where: a parametrize id carries `::` inside its
        brackets; splitting the node id before stripping the bracket names
        the test after the id's tail, so every passing case reads as
        not-passed (GitHub #42)."""
        repo_root, _ = build_checkpoint(self, "TASK-116")
        evidence = repo_root / "evidence.txt"
        evidence.write_text(
            "tests/test_foo.py::FooTests::test_a[mod::_entry] PASSED   [ 50%]\n"
            "tests/test_foo.py::FooTests::test_b[a::b::c] PASSED       [100%]\n",
            encoding="utf-8",
        )
        code, out, err = self._verify(task="TASK-116", extra=["--against-run", str(evidence)])
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("not-passed", out)

    def test_verify_against_run_param_id_holding_brackets_reads_the_test_name(self):
        """Adversarial where: `ids=str` on a list parameter prints the id as
        `test_a[['--material']]`; a param pattern that ends at the first `]`
        leaves the trailing `]` unmatched, so the line is skipped and every
        passing case reads as not-passed (GitHub #49). The `-v` and the `-rA`
        summary forms are each read on their own, since either one alone
        proves every case."""
        forms = {
            "-v": ("tests/test_foo.py::FooTests::test_a[['--material']] PASSED   [ 50%]\n"
                   "tests/test_foo.py::FooTests::test_b[['a b', 'c']] PASSED     [100%]\n"),
            "-rA": ("PASSED tests/test_foo.py::FooTests::test_a[['--material']]\n"
                    "PASSED tests/test_foo.py::FooTests::test_b[['a b', 'c']]\n"),
        }
        for n, (form, lines) in enumerate(forms.items()):
            task = f"TASK-11{7 + n}"
            repo_root, _ = build_checkpoint(self, task)
            evidence = repo_root / "evidence.txt"
            evidence.write_text(lines, encoding="utf-8")
            code, out, err = self._verify(task=task, extra=["--against-run", str(evidence)])
            self.assertEqual(code, 0, f"{form}: {out}{err}")
            self.assertNotIn("not-passed", out)

    def test_verify_against_run_failed_case_with_bracketed_param_id_reads_not_passed(self):
        """Adversarial where: a parser that drops bracketed-id lines it cannot
        read would also drop a failing case, and a passing sibling would then
        stand for the whole test."""
        repo_root, _ = build_checkpoint(self, "TASK-119")
        evidence = repo_root / "evidence.txt"
        evidence.write_text(
            "tests/test_foo.py::FooTests::test_a[['x']] PASSED   [ 25%]\n"
            "tests/test_foo.py::FooTests::test_a[['y']] FAILED   [ 50%]\n"
            "tests/test_foo.py::FooTests::test_b[['x']] PASSED   [100%]\n",
            encoding="utf-8",
        )
        code, out, err = self._verify(task="TASK-119", extra=["--against-run", str(evidence)])
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("not-passed", out)

    def test_verify_against_run_reads_evidence_in_a_windows_encoding(self):
        """Adversarial where: a Windows shell saves the run as cp1252 (a
        dash printed by a test is byte 0x97) or, from a PowerShell `>`
        redirect, as UTF-16; a strict UTF-8 read crashes on the first and
        finds no test lines in the second (GitHub #39)."""
        lines = ("tests/test_foo.py::FooTests::test_a PASSED  — note [ 50%]\n"
                 "tests/test_foo.py::FooTests::test_b PASSED               [100%]\n")
        for n, encoding in enumerate(("cp1252", "utf-16")):
            task = f"TASK-12{n}"
            repo_root, _ = build_checkpoint(self, task)
            evidence = repo_root / "evidence.txt"
            evidence.write_bytes(lines.encode(encoding))
            code, out, err = self._verify(task=task, extra=["--against-run", str(evidence)])
            self.assertEqual(code, 0, f"{encoding}: {out}{err}")
            self.assertNotIn("not-passed", out)

    def test_verify_supersede_retains_prior_and_names_it(self):
        """Adversarial where a legitimately-corrected pre-build test
        silently replaces the original checkpoint with no trace, so a human
        auditing `verify`'s output cannot tell a correction from tampering."""
        repo_root, sha1 = build_checkpoint(self, "TASK-107")
        corrected = BASELINE_SRC.replace("self.assertTrue(True)", "self.assertFalse(False)")
        write_file(repo_root, "tests/test_foo.py", corrected)
        sha2 = git_commit_all(repo_root, "test(TASK-107): correct inverted assertion")
        code, out, err = run_cli([
            "record", "TASK-107", "tests/test_foo.py", "--commit", sha2,
            "--supersede", "TASK-107", "--reason", "test_b assertion was inverted",
        ])
        self.assertEqual(code, 0, out + err)

        record = json.loads(checkpoint_path(repo_root, "TASK-107").read_text(encoding="utf-8"))
        self.assertEqual(record["version"], 2)
        self.assertEqual(record["supersedes"]["prior_version"], 1)
        self.assertEqual(record["supersedes"]["prior_commit"], sha1)

        code, out, err = self._verify(task="TASK-107")
        self.assertEqual(code, 0, out + err)
        self.assertIn("supersedes v1", out)
        self.assertIn("test_b assertion was inverted", out)

    def test_verify_not_required_exits_0(self):
        """Adversarial where a prose-only task's recorded skip is treated as
        a missing checkpoint by `verify`, forcing a station on a task with
        no executable files to check."""
        repo_root = make_repo_vault(self)
        with_vault_env(self, repo_root)
        run_cli(["record", "TASK-108", "--not-required"])
        code, out, err = self._verify(task="TASK-108")
        self.assertEqual(code, 0, out + err)
        self.assertIn("not-required", out)

    def test_verify_no_checkpoint_on_code_task_exits_1(self):
        """Adversarial where a code task with executable files simply never
        called `record`, and `verify` treats silence as success - the exact
        failure mode this mechanism exists to make loud."""
        repo_root = make_repo_vault(self)
        with_vault_env(self, repo_root)
        code, out, err = self._verify(task="TASK-999")
        self.assertEqual(code, 1)
        self.assertIn("no checkpoint recorded", err)

    def test_verify_corrupt_json_exits_1_with_message_no_traceback(self):
        """Adversarial where the checkpoint index is corrupted (partial
        write, disk fault) and `verify` raises instead of reporting - which
        on the hook-adjacent build path would surface as an uncaught crash
        rather than a clean exit-1 finding."""
        repo_root = make_repo_vault(self)
        with_vault_env(self, repo_root)
        path = checkpoint_path(repo_root, "TASK-109")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        code, out, err = self._verify(task="TASK-109")
        self.assertEqual(code, 1)
        self.assertTrue(err.strip())


class OpenIdsTests(unittest.TestCase):
    def test_open_ids_prints_only_unlanded_tasks(self):
        """Adversarial where `open-ids` keeps listing a task's tests after
        `verify --against-run` has already confirmed them passing, which
        would make 'no failures outside the open checkpoint set' permanently
        unsatisfiable even on an otherwise-green suite."""
        repo_root = make_repo_vault(self)
        with_vault_env(self, repo_root)

        write_file(repo_root, "tests/test_open.py", BASELINE_SRC)
        sha_open = git_commit_all(repo_root, "test(TASK-201): checkpoint")
        code, out, err = run_cli(["record", "TASK-201", "tests/test_open.py", "--commit", sha_open])
        self.assertEqual(code, 0, out + err)

        write_file(repo_root, "tests/test_landed.py", BASELINE_SRC)
        sha_landed = git_commit_all(repo_root, "test(TASK-202): checkpoint")
        code, out, err = run_cli(["record", "TASK-202", "tests/test_landed.py", "--commit", sha_landed])
        self.assertEqual(code, 0, out + err)
        evidence = repo_root / "evidence.txt"
        evidence.write_text(
            "test_a (tests.test_landed.FooTests) ... ok\n"
            "test_b (tests.test_landed.FooTests) ... ok\n",
            encoding="utf-8",
        )
        code, out, err = run_cli(["verify", "TASK-202", "--against-run", str(evidence)])
        self.assertEqual(code, 0, out + err)

        code, out, err = run_cli(["record", "TASK-203", "--not-required"])
        self.assertEqual(code, 0, out + err)

        code, out, err = run_cli(["open-ids"])
        self.assertEqual(code, 0, out + err)
        self.assertIn("tests.test_open.FooTests.test_a", out)
        self.assertIn("tests.test_open.FooTests.test_b", out)
        self.assertNotIn("test_landed", out)


class NeverExitsTwoTests(unittest.TestCase):
    def test_malformed_invocations_never_exit_2(self):
        """Adversarial where a malformed invocation of a CLI command reaches
        argparse's default exit(2), which on the hook path would block the
        user's write instead of degrading to a reported error."""
        repo_root = make_repo_vault(self)
        with_vault_env(self, repo_root)
        malformed = [
            [],
            ["bogus-subcommand"],
            ["record"],
            ["record", "TASK-1"],
            ["record", "TASK-1", "--not-required", "tests/test_foo.py"],
            ["verify"],
            ["verify", "TASK-1", "--tree"],
            ["verify", "TASK-1", "--unknown-flag"],
            ["open-ids", "unexpected-arg"],
        ]
        for argv in malformed:
            with self.subTest(argv=argv):
                code, out, err = run_cli(argv)
                self.assertIn(code, (0, 1))



CYCLE_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cycle_evidence"
CYCLE_LINE = re.compile(r"^cycle (\d+): (\w+)", re.MULTILINE)
ESCALATE_LINE = re.compile(r"^escalate: (yes|no)\s*$", re.MULTILINE)
CYCLE_FORMAT = re.compile(
    r"^cycle \d+: (helpful|neutral|harmful) - fixed .*, new .*, still failing .*$",
    re.MULTILINE,
)


def pytest_evidence(*rows):
    """pytest `-v` text for `(class, test, passed)` rows."""
    lines = []
    for class_name, test, passed in rows:
        status = "PASSED" if passed else "FAILED"
        lines.append(f"tests/test_widget.py::{class_name}::{test} {status} [ 50%]")
    return "\n".join(lines) + "\n"


def cycle_log(repo_root, task):
    path = repo_root / ".compass" / "tmp" / "test-checkpoints" / f"{task}.cycles.jsonl"
    if not path.is_file():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class CycleTests(unittest.TestCase):
    def setUp(self):
        self.repo_root = make_repo_vault(self)
        with_vault_env(self, self.repo_root)
        self.counter = 0

    def evidence_file(self, text):
        self.counter += 1
        rel = f"ev/run{self.counter}.txt"
        return write_file(self.repo_root, rel, text)

    def cycle(self, task, text):
        """Run `cycle` against `text` as evidence. Returns
        `(code, number, verdict, escalate, stdout)`."""
        code, out, err = run_cli(["cycle", task, "--evidence", str(self.evidence_file(text))])
        self.assertEqual(code, 0, out + err)
        found = CYCLE_LINE.search(out)
        self.assertIsNotNone(found, f"no 'cycle N:' line in {out!r}")
        esc = ESCALATE_LINE.search(out)
        self.assertIsNotNone(esc, f"no 'escalate:' line in {out!r}")
        return code, int(found.group(1)), found.group(2), esc.group(1), out

    def run_pair(self, task, before, after):
        """Cycle 0 on `before`, cycle 1 on `after`; returns the cycle 1 result."""
        number0 = self.cycle(task, before)[1]
        self.assertEqual(number0, 0)
        result = self.cycle(task, after)
        self.assertEqual(result[1], 1)
        return result

    def test_verdict_classifies_the_change_between_two_cycles(self):
        """Adversarial where: the verdict keys tests by bare name instead of
        class plus name, treats a failing test that vanished from the next
        run as fixed, or counts a fix that is paid for by a new break as
        helpful."""
        rows = [
            ("fixes two breaks none",
             [("A", "t1", False), ("A", "t2", False)],
             [("A", "t1", True), ("A", "t2", True)], "helpful", "no"),
            ("fixes one breaks one",
             [("A", "t1", False), ("A", "t2", True)],
             [("A", "t1", True), ("A", "t2", False)], "harmful", "yes"),
            ("fixes one, a test absent before now fails",
             [("A", "t1", False)],
             [("A", "t1", True), ("A", "t3", False)], "harmful", "yes"),
            ("failing test missing from next run among others still failing",
             [("A", "t1", False), ("A", "t2", False)],
             [("A", "t2", False)], "harmful", "yes"),
            ("failing test missing, everything present passes",
             [("A", "t1", False)],
             [("A", "t9", True)], "harmful", "yes"),
            ("name shared by two classes, one of the two fixed",
             [("A", "t", False), ("B", "t", False)],
             [("A", "t", True), ("B", "t", False)], "helpful", "no"),
            ("name shared by two classes, one fixed while the twin breaks",
             [("A", "t", False)],
             [("A", "t", True), ("B", "t", False)], "harmful", "yes"),
            ("same failing set, passing set grew",
             [("A", "t1", False), ("A", "t2", True)],
             [("A", "t1", False), ("A", "t2", True), ("A", "t3", True)], "neutral", "no"),
            ("nothing failing in either run",
             [("A", "t1", True)],
             [("A", "t1", True)], "neutral", "no"),
        ]
        for index, (label, before, after, verdict, escalate) in enumerate(rows):
            with self.subTest(row=label):
                result = self.run_pair(
                    f"TASK-{300 + index}", pytest_evidence(*before), pytest_evidence(*after)
                )
                _, _, got, esc, out = result
                self.assertEqual((got, esc), (verdict, escalate), out)
                self.assertRegex(out, CYCLE_FORMAT)

    def test_each_cycle_is_compared_with_the_one_before_it_and_logged_once(self):
        """Adversarial where: the comparison anchors on cycle 0 instead of
        the previous cycle (a test fixed in cycle 1 and broken again in
        cycle 2 reads as unchanged), or an appended cycle line is lost or
        doubled."""
        task = "TASK-320"
        runs = [
            [("A", "x", False)],
            [("A", "x", True)],
            [("A", "x", False)],
        ]
        verdicts = []
        for expected_number, rows in enumerate(runs):
            _, number, verdict, _, out = self.cycle(task, pytest_evidence(*rows))
            self.assertEqual(number, expected_number, out)
            verdicts.append(verdict)
            self.assertEqual(len(cycle_log(self.repo_root, task)), expected_number + 1)
        self.assertEqual(verdicts[1:], ["helpful", "harmful"])

    def test_cycle_three_escalates_and_cycle_two_does_not(self):
        """Adversarial where: the escalation threshold is off by one, firing
        at cycle 2 or never firing at cycle 3, or fires only when the third
        cycle is harmful."""
        failing = [("A", name, False) for name in "abcd"]
        helpful = [
            failing,
            [("A", "a", True)] + failing[1:],
            [("A", "a", True), ("A", "b", True)] + failing[2:],
            [("A", "a", True), ("A", "b", True), ("A", "c", True), ("A", "d", False)],
        ]
        neutral_third = helpful[:3] + [helpful[2]]
        for label, run, task in (
            ("helpful third cycle", helpful, "TASK-330"),
            ("neutral third cycle", neutral_third, "TASK-331"),
        ):
            with self.subTest(run=label):
                escalations = [self.cycle(task, pytest_evidence(*rows))[3] for rows in run]
                self.assertEqual(escalations, ["no", "no", "no", "yes"])

    def test_checkpointed_tests_of_unlanded_tasks_are_not_failures(self):
        """Adversarial where: an expected red from an open pre-build
        checkpoint is counted as a break (or as vanishing coverage), or
        the ignore matches on the bare test name so a same-named test in
        another class slips through, or a landed checkpoint keeps hiding
        its tests."""
        checkpoint_root, _ = build_checkpoint(self, "TASK-200")
        rows = [
            ("open-checkpoint test starts failing",
             [("WidgetTests", "t", False)],
             [("WidgetTests", "t", False), ("FooTests", "test_a", False)], "neutral"),
            ("open-checkpoint test disappears from the run",
             [("FooTests", "test_a", False), ("WidgetTests", "t", True)],
             [("WidgetTests", "t", True)], "neutral"),
            ("same test name in a class the checkpoint does not name",
             [("WidgetTests", "t", True)],
             [("OtherTests", "test_a", False)], "harmful"),
        ]
        for index, (label, before, after, verdict) in enumerate(rows):
            with self.subTest(row=label):
                got = self.run_pair(
                    f"TASK-{340 + index}", pytest_evidence(*before), pytest_evidence(*after)
                )[2]
                self.assertEqual(got, verdict)

        index_path = checkpoint_path(checkpoint_root, "TASK-200")
        record = json.loads(index_path.read_text(encoding="utf-8"))
        record["landed"] = True
        index_path.write_text(json.dumps(record), encoding="utf-8")
        with self.subTest(row="landed checkpoint no longer hides its tests"):
            got = self.run_pair(
                "TASK-350",
                pytest_evidence(("WidgetTests", "t", True)),
                pytest_evidence(("WidgetTests", "t", True), ("FooTests", "test_a", False)),
            )[2]
            self.assertEqual(got, "harmful")

    def test_real_pytest_and_unittest_evidence_both_parse(self):
        """Adversarial where: the parser only handles synthetic one-line
        evidence and misses a failure in real `-v` output, whose unittest
        form splits a docstring test across two lines, so the flipped test
        reads as absent or unchanged."""
        pytest_real = (CYCLE_FIXTURES / "pytest_v_test_bom.txt").read_text(encoding="utf-8")
        unittest_real = (CYCLE_FIXTURES / "unittest_v_test_bom.txt").read_text(encoding="utf-8")

        def flip(text, old, new):
            self.assertIn(old, text)
            return text.replace(old, new)

        py_single = flip(
            pytest_real,
            "BomFrontmatterTests::test_plain_artifact_is_unaffected PASSED",
            "BomFrontmatterTests::test_plain_artifact_is_unaffected FAILED",
        )
        py_doc = flip(
            pytest_real,
            "BomFrontmatterTests::test_bom_artifact_still_parses_its_frontmatter PASSED",
            "BomFrontmatterTests::test_bom_artifact_still_parses_its_frontmatter FAILED",
        )
        single_line = (
            "test_plain_artifact_is_unaffected "
            "(tests.test_bom.BomFrontmatterTests.test_plain_artifact_is_unaffected) ... "
        )
        ut_single = flip(unittest_real, single_line + "ok", single_line + "FAIL")
        split_line = "Adversarial where: the file is byte-identical to a good artifact ... "
        ut_doc = flip(unittest_real, split_line + "ok", split_line + "FAIL")
        rows = [
            ("pytest, test newly fails", pytest_real, py_single, "harmful"),
            ("pytest, failure repaired", py_single, pytest_real, "helpful"),
            ("pytest, unchanged real run", pytest_real, pytest_real, "neutral"),
            ("unittest single-line, test newly fails", unittest_real, ut_single, "harmful"),
            ("unittest single-line, failure repaired", ut_single, unittest_real, "helpful"),
            ("unittest docstring-split, test newly fails", unittest_real, ut_doc, "harmful"),
            ("unittest docstring-split, failure repaired", ut_doc, unittest_real, "helpful"),
            ("failure in pytest run repaired in unittest run", py_doc, unittest_real, "helpful"),
            ("failure in unittest run repaired in pytest run", ut_single, pytest_real, "helpful"),
        ]
        for index, (label, before, after, verdict) in enumerate(rows):
            with self.subTest(row=label):
                got = self.run_pair(f"TASK-{360 + index}", before, after)[2]
                self.assertEqual(got, verdict)

    def test_missing_evidence_file_exits_1_and_appends_nothing(self):
        """Adversarial where: a typo in the evidence path records an empty
        cycle (all failures read as vanished, or the cycle counter advances
        with no data), or the failing call still leaves a log line behind."""
        task = "TASK-380"
        self.cycle(task, pytest_evidence(("A", "t", False)))
        missing = self.repo_root / "ev" / "does-not-exist.txt"
        code, out, err = run_cli(["cycle", task, "--evidence", str(missing)])
        self.assertEqual(code, 1, out + err)
        self.assertNotRegex(out, CYCLE_LINE)
        self.assertEqual(len(cycle_log(self.repo_root, task)), 1)
        number = self.cycle(task, pytest_evidence(("A", "t", False)))[1]
        self.assertEqual(number, 1)

        untouched = "TASK-381"
        code, out, err = run_cli(["cycle", untouched, "--evidence", str(missing)])
        self.assertEqual(code, 1, out + err)
        self.assertEqual(cycle_log(self.repo_root, untouched), [])

    def test_malformed_cycle_arguments_exit_1_and_append_nothing(self):
        """Adversarial where: a cycle call missing its task id, its
        `--evidence` flag, or the flag's value raises or exits 2 instead of
        reporting a usage error naming the `cycle` form."""
        evidence = str(self.evidence_file(pytest_evidence(("A", "t", False))))
        for argv in (
            ["cycle"],
            ["cycle", "TASK-390"],
            ["cycle", "TASK-390", "--evidence"],
            ["cycle", "--evidence", evidence],
        ):
            with self.subTest(argv=argv):
                code, _, err = run_cli(argv)
                self.assertEqual(code, 1)
                self.assertIn("cycle TASK-NNN --evidence", err)
        self.assertEqual(cycle_log(self.repo_root, "TASK-390"), [])

    def test_cycle_logs_are_kept_per_task(self):
        """Adversarial where: cycles of two tasks share one log, so the
        second task's first call is compared against the first task's
        failures instead of starting at cycle 0."""
        self.cycle("TASK-395", pytest_evidence(("A", "t", False)))
        number = self.cycle("TASK-396", pytest_evidence(("A", "t", False)))[1]
        self.assertEqual(number, 0)
        self.assertEqual(len(cycle_log(self.repo_root, "TASK-395")), 1)
        self.assertEqual(len(cycle_log(self.repo_root, "TASK-396")), 1)


class NodeTapEvidenceTests(unittest.TestCase):
    """`node --test` prints TAP: `ok N - name` and `not ok N - name` at the
    top level, subtests indented beneath their parent."""

    def test_top_level_tap_lines_parse_as_bare_names(self):
        """Adversarial where: an indented subtest line is read as a test of
        its own, `not ok` is read as a pass because it contains `ok`, or a
        `# SKIP` directive is read as a pass."""
        text = "\n".join([
            "TAP version 13",
            "# Subtest: a board draws",
            "    ok 1 - inner step",
            "ok 1 - a board draws",
            "    not ok 1 - inner failing step",
            "not ok 2 - Needs changes never sends an empty verdict",
            "ok 3 - a skipped probe # SKIP no node fs",
            "ok 4 - a name with a \\# hash",
            "1..4",
            "# pass 2",
        ])
        statuses = test_checkpoint._parse_run_evidence(text)
        self.assertEqual(statuses[(None, "a board draws")], "ok")
        self.assertEqual(statuses[(None, "Needs changes never sends an empty verdict")], "fail")
        self.assertEqual(statuses[(None, "a skipped probe")], "skipped")
        self.assertEqual(statuses[(None, "a name with a # hash")], "ok")
        self.assertNotIn((None, "inner step"), statuses)
        self.assertNotIn((None, "inner failing step"), statuses)

    def test_cycle_accepts_node_tap_evidence(self):
        """Adversarial where: `cycle` still refuses evidence holding only
        TAP lines, so a fix loop on plugin tests records nothing."""
        repo_root = make_repo_vault(self)
        with_vault_env(self, repo_root)
        evidence = write_file(repo_root, "ev/tap.txt", "TAP version 13\nnot ok 1 - board\n1..1\n")
        code, out, err = run_cli(["cycle", "TASK-901", "--evidence", str(evidence)])
        self.assertEqual(code, 0, out + err)
        self.assertRegex(out, r"cycle 0:")


if __name__ == "__main__":
    unittest.main()
