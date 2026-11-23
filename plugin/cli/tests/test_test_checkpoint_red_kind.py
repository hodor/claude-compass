"""Tests for the red kind `compass test-checkpoint record --red-evidence`
stores: one entry per checkpointed test id in the record's `red_kinds`, each
`fail`, `error`, `collection`, `passed` or `absent`, read from the run output
the pre-build tester saved.

Interface pinned here: `red_kinds` is a mapping from a test id to its kind
string, where the id ends in the test's name (`name`, `Class.name` or any
`path::Class::name` form). Lookups below match on the trailing test name, so
every test name in the fixtures is unique. A record without evidence, or with
unreadable evidence, carries no `red_kinds` key at all.

Adversarial themes: a collection error that taints every test of a similarly
named file, a failing test filed as a collection error because its sibling
file failed to import, evidence saved by PowerShell (UTF-16) or a Windows
console (cp1252) read as nothing, a missing evidence file aborting the
record, and a record carrying the new key breaking `verify` or `open-ids`.
"""

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_test_checkpoint import (  # noqa: E402
    checkpoint_path, git_commit_all, make_repo_vault, run_cli, with_vault_env,
    write_file,
)

# `python -m pytest -v --continue-on-collection-errors tests/test_ok.py
# tests/test_errs.py tests/test_gone.py`, path lines shortened.
PYTEST_EVIDENCE = """\
============================= test session starts =============================
collecting ... collected 3 items / 1 error

tests/test_ok.py::test_passes PASSED                                     [ 33%]
tests/test_ok.py::test_fails FAILED                                      [ 66%]
tests/test_errs.py::test_setup_error ERROR                               [100%]

=================================== ERRORS ====================================
_____________________ ERROR collecting tests/test_gone.py _____________________
ImportError while importing test module '/repo/tests/test_gone.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
tests\\test_gone.py:1: in <module>
    from newmod import thing
E   ModuleNotFoundError: No module named 'newmod'
_____________________ ERROR at setup of test_setup_error ______________________

>       raise RuntimeError("boom")
E       RuntimeError: boom

tests\\test_errs.py:6: RuntimeError
=========================== short test summary info ===========================
FAILED tests/test_ok.py::test_fails - assert 1 == 2
ERROR tests/test_gone.py
ERROR tests/test_errs.py::test_setup_error - RuntimeError: boom
==================== 1 failed, 1 passed, 2 errors in 0.07s ====================
"""

# `python -m unittest -v tests.test_ut_gone tests.test_ut_ok`, path lines shortened.
UNITTEST_EVIDENCE = """\
test_ut_gone (unittest.loader._FailedTest.test_ut_gone) ... ERROR
test_bad (tests.test_ut_ok.OkTests.test_bad) ... FAIL
test_fine (tests.test_ut_ok.OkTests.test_fine) ... ok

======================================================================
ERROR: test_ut_gone (unittest.loader._FailedTest.test_ut_gone)
----------------------------------------------------------------------
ImportError: Failed to import test module: test_ut_gone
Traceback (most recent call last):
  File "unittest/loader.py", line 137, in loadTestsFromName
    module = __import__(module_name)
  File "/repo/tests/test_ut_gone.py", line 2, in <module>
    from newmod import thing
ModuleNotFoundError: No module named 'newmod'


======================================================================
FAIL: test_bad (tests.test_ut_ok.OkTests.test_bad)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/repo/tests/test_ut_ok.py", line 9, in test_bad
    self.assertTrue(False)
AssertionError: False is not true

----------------------------------------------------------------------
Ran 3 tests in 0.001s

FAILED (failures=1, errors=1)
"""

FILES = {
    "tests/__init__.py": "",
    "tests/test_ok.py": "def test_passes():\n    pass\n\n\ndef test_fails():\n    pass\n",
    "tests/test_errs.py": "def test_setup_error():\n    pass\n",
    "tests/test_gone.py": (
        "def test_uses_thing():\n    pass\n\n\n"
        "class TestGone:\n    def test_method(self):\n        pass\n"
    ),
    "tests/test_gone_more.py": "def test_sibling():\n    pass\n",
    "tests/test_not_run.py": "def test_never_ran():\n    pass\n",
    "tests/test_ut_gone.py": (
        "import unittest\n\n\nclass GoneTests(unittest.TestCase):\n"
        "    def test_ut_gone(self):\n        pass\n"
    ),
    "tests/test_ut_gone_extra.py": "def test_ut_sibling():\n    pass\n",
    "tests/test_ut_ok.py": (
        "import unittest\n\n\nclass OkTests(unittest.TestCase):\n"
        "    def test_fine(self):\n        pass\n\n"
        "    def test_bad(self):\n        pass\n"
    ),
}
PYTEST_FILES = [
    "tests/test_ok.py", "tests/test_errs.py", "tests/test_gone.py",
    "tests/test_gone_more.py", "tests/test_not_run.py",
]
UNITTEST_FILES = ["tests/test_ut_gone.py", "tests/test_ut_gone_extra.py", "tests/test_ut_ok.py"]

PYTEST_KINDS = {
    "test_passes": "passed", "test_fails": "fail", "test_setup_error": "error",
    "test_uses_thing": "collection", "test_method": "collection",
    "test_sibling": "absent", "test_never_ran": "absent",
}
UNITTEST_KINDS = {
    "test_fine": "passed", "test_bad": "fail", "test_ut_gone": "collection",
    "test_ut_sibling": "absent",
}


def kinds_by_name(record):
    """`{test name: kind}` from the record's `red_kinds`, keyed on the
    trailing segment of each id."""
    return {re.split(r"::|\.", key)[-1]: value for key, value in record["red_kinds"].items()}


def read_record(repo, task):
    return json.loads(checkpoint_path(repo, task).read_text(encoding="utf-8"))


class RedKindTests(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo_vault(self)
        for rel, content in FILES.items():
            write_file(self.repo, rel, content)
        self.sha = git_commit_all(self.repo, "test(TASK-900): failing tests before implementation")
        with_vault_env(self, self.repo)
        self.scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.scratch, True)

    def record(self, task, files, evidence=None):
        argv = ["record", task, *files, "--commit", self.sha]
        if evidence is not None:
            argv += ["--red-evidence", str(evidence)]
        return run_cli(argv)

    def evidence_file(self, name, data):
        path = self.scratch / name
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    def test_pytest_evidence_yields_one_kind_per_checkpointed_test(self):
        """Adversarial where: a FAILED, an ERROR and a collection error in a
        second file collapse into one kind, a passed test is filed as red, or
        a file whose name merely starts like the broken file's (`test_gone`
        vs `test_gone_more`) is tainted by its collection error instead of
        reading `absent`."""
        evidence = self.evidence_file("pytest.txt", PYTEST_EVIDENCE)
        code, out, err = self.record("TASK-901", PYTEST_FILES, evidence)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(kinds_by_name(read_record(self.repo, "TASK-901")), PYTEST_KINDS)

    def test_red_kinds_cover_exactly_the_checkpointed_ids(self):
        """Adversarial where: evidence lines for a test outside the
        checkpointed files (the broken `_FailedTest` stub, the summary's file
        line) leak in as extra ids, or a checkpointed id is dropped."""
        evidence = self.evidence_file("pytest.txt", PYTEST_EVIDENCE)
        self.record("TASK-902", PYTEST_FILES, evidence)
        self.assertEqual(
            sorted(kinds_by_name(read_record(self.repo, "TASK-902"))), sorted(PYTEST_KINDS))

    def test_unittest_evidence_reads_the_import_failure_form(self):
        """Adversarial where: unittest's `Failed to import test module:
        <module>` is not recognized, so the import failure reads as a plain
        `error` or `absent`, or the sibling `test_ut_gone_extra` is claimed by
        the module name `test_ut_gone`."""
        evidence = self.evidence_file("unittest.txt", UNITTEST_EVIDENCE)
        code, out, err = self.record("TASK-903", UNITTEST_FILES, evidence)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(kinds_by_name(read_record(self.repo, "TASK-903")), UNITTEST_KINDS)

    def test_a_test_green_in_the_red_run_is_passed_not_red(self):
        """Adversarial where: a test that passed before the build, so it
        proves nothing, is stored as `fail` because the run it came from was
        red overall."""
        evidence = self.evidence_file("pytest.txt", PYTEST_EVIDENCE)
        self.record("TASK-904", ["tests/test_ok.py"], evidence)
        self.assertEqual(kinds_by_name(read_record(self.repo, "TASK-904"))["test_passes"], "passed")

    def test_evidence_saved_as_utf16_or_cp1252_yields_the_same_kinds(self):
        """Adversarial where: a PowerShell redirect (UTF-16 with a BOM) or a
        Windows console (cp1252 bytes that are not valid UTF-8) is read as
        empty, so every test stores `absent` and the record hides that the
        tests failed."""
        cp1252_text = PYTEST_EVIDENCE.replace(
            "E       RuntimeError: boom", "E       RuntimeError: café boom")
        rows = {
            "TASK-905": self.evidence_file("u16.txt", PYTEST_EVIDENCE.encode("utf-16")),
            "TASK-906": self.evidence_file("c1252.txt", cp1252_text.encode("cp1252")),
        }
        with self.assertRaises(UnicodeDecodeError):
            rows["TASK-906"].read_bytes().decode("utf-8")
        for task, evidence in rows.items():
            code, out, err = self.record(task, PYTEST_FILES, evidence)
            self.assertEqual(code, 0, out + err)
            self.assertEqual(kinds_by_name(read_record(self.repo, task)), PYTEST_KINDS, task)

    def test_missing_or_unreadable_evidence_still_records_without_kinds_and_warns(self):
        """Adversarial where: a red-evidence path that does not exist, or is
        a folder, aborts the record (no checkpoint at all), or is accepted
        silently with an empty `red_kinds` that reads as all-`absent`."""
        rows = {
            "TASK-907": self.scratch / "never-written.txt",
            "TASK-908": self.scratch,
        }
        for task, evidence in rows.items():
            code, out, err = self.record(task, ["tests/test_ok.py"], evidence)
            self.assertEqual(code, 0, task + out + err)
            record = read_record(self.repo, task)
            self.assertNotIn("red_kinds", record, task)
            self.assertEqual(record["red_evidence"], str(evidence), task)
            self.assertIn("evidence", err.lower(), task)

    def test_record_without_evidence_carries_no_red_kinds_and_no_warning(self):
        """Adversarial where: a record made without `--red-evidence` gains an
        empty `red_kinds` or a stderr warning, changing what every existing
        caller of `record` sees."""
        code, out, err = self.record("TASK-909", ["tests/test_ok.py"])
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("red_kinds", read_record(self.repo, "TASK-909"))
        self.assertEqual(err, "")

    def test_verify_and_open_ids_read_a_record_with_and_without_the_key_alike(self):
        """Adversarial where: `verify` or `open-ids` treats the new key as an
        unknown field (a `malformed` finding), or a record written before the
        key existed stops verifying, so the same task reads differently by
        when it was recorded."""
        evidence = self.evidence_file("pytest.txt", PYTEST_EVIDENCE)
        self.record("TASK-910", PYTEST_FILES, evidence)
        with_key = (run_cli(["verify", "TASK-910"]), run_cli(["open-ids"]))
        path = checkpoint_path(self.repo, "TASK-910")
        record = json.loads(path.read_text(encoding="utf-8"))
        del record["red_kinds"]
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
        without_key = (run_cli(["verify", "TASK-910"]), run_cli(["open-ids"]))
        self.assertEqual(with_key[0][0], 0, with_key[0][1] + with_key[0][2])
        self.assertIn("unchanged", with_key[0][1])
        self.assertEqual(with_key, without_key)


if __name__ == "__main__":
    unittest.main()
