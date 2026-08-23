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


if __name__ == "__main__":
    unittest.main()
