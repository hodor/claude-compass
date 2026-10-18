"""Adversarial tests for `compass test-checkpoint verify --accept-skip`.

Each case probes a way an acceptance could reach further than the one named
skipped test: a failure folded into a skip, a name matching the wrong class,
a reason that forges report lines, or a tampered index entry crashing verify.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_test_checkpoint import (  # noqa: E402
    INIT_SRC, build_checkpoint, checkpoint_path, git_commit_all,
    make_repo_vault, run_cli, with_vault_env, write_file,
)

REASON = "POSIX-only, skipped on Windows"

TWO_CLASS_SRC = (
    "import unittest\n"
    "\n"
    "\n"
    "class AlphaTests(unittest.TestCase):\n"
    "    def test_x(self):\n"
    "        self.assertEqual(1, 1)\n"
    "\n"
    "\n"
    "class BetaTests(unittest.TestCase):\n"
    "    def test_x(self):\n"
    "        self.assertEqual(2, 2)\n"
)


class AcceptSkipAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.repo_root, _ = build_checkpoint(self, "TASK-310")
        self.evidence = self.repo_root / "evidence.txt"

    def write_evidence(self, a, b):
        self.evidence.write_text(
            f"test_a (tests.test_foo.FooTests) ... {a}\n"
            f"test_b (tests.test_foo.FooTests) ... {b}\n",
            encoding="utf-8",
        )

    def verify(self, *extra):
        return run_cli(["verify", "TASK-310", "--against-run", str(self.evidence), *extra])

    def record_path(self):
        return checkpoint_path(self.repo_root, "TASK-310")

    def record(self):
        return json.loads(self.record_path().read_text(encoding="utf-8"))

    def test_accept_skip_on_a_passed_test_records_no_acceptance(self):
        """Adversarial where naming a test that actually passed writes a
        bogus accepted-skip audit entry."""
        self.write_evidence("ok", "ok")
        code, out, err = self.verify("--accept-skip", "FooTests.test_a", "--reason", REASON)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(self.record()["landed"])
        self.assertNotIn("accepted_skips", self.record())
        self.assertNotIn("accepted-skip", out)

    def test_parametrized_id_is_not_a_checkpointed_name(self):
        """Adversarial where `Class.test[param]` is accepted as a name for
        a bare checkpoint id, or crashes the lookup."""
        self.write_evidence("skipped 'x'", "ok")
        code, out, _ = self.verify("--accept-skip", "FooTests.test_a[1]", "--reason", REASON)
        self.assertEqual(code, 1)
        self.assertIn("test_a[1]", out)
        self.assertFalse(self.record()["landed"])

    def test_bare_name_does_not_match_a_class_qualified_checkpoint(self):
        """Adversarial where the unqualified `test_a` accepts the skip of
        `FooTests.test_a`."""
        self.write_evidence("skipped 'x'", "ok")
        code, out, _ = self.verify("--accept-skip", "test_a", "--reason", REASON)
        self.assertEqual(code, 1)
        self.assertFalse(self.record()["landed"])

    def test_failed_param_case_after_a_skipped_case_is_not_laundered(self):
        """Adversarial where one skipped case plus one FAILED case of a
        parametrized test fold to 'skipped' and --accept-skip lands it."""
        self.evidence.write_text(
            "tests/test_foo.py::FooTests::test_a[1] SKIPPED (x) [ 25%]\n"
            "tests/test_foo.py::FooTests::test_a[2] FAILED [ 50%]\n"
            "tests/test_foo.py::FooTests::test_b PASSED [100%]\n",
            encoding="utf-8",
        )
        code, out, _ = self.verify("--accept-skip", "FooTests.test_a", "--reason", REASON)
        self.assertEqual(code, 1, out)
        self.assertFalse(self.record()["landed"])

    def test_failed_param_case_before_a_skipped_case_is_not_laundered(self):
        """Adversarial where the same fold depends on case order, FAILED
        first then SKIPPED."""
        self.evidence.write_text(
            "tests/test_foo.py::FooTests::test_a[1] FAILED [ 25%]\n"
            "tests/test_foo.py::FooTests::test_a[2] SKIPPED (x) [ 50%]\n"
            "tests/test_foo.py::FooTests::test_b PASSED [100%]\n",
            encoding="utf-8",
        )
        code, out, _ = self.verify("--accept-skip", "FooTests.test_a", "--reason", REASON)
        self.assertEqual(code, 1, out)
        self.assertFalse(self.record()["landed"])

    def test_accepted_test_that_later_fails_is_reported_not_passed(self):
        """Adversarial where a stored acceptance keeps counting after fresh
        evidence shows the test FAILED."""
        self.write_evidence("skipped 'x'", "ok")
        self.verify("--accept-skip", "FooTests.test_a", "--reason", REASON)
        self.write_evidence("FAIL", "ok")
        code, out, _ = self.verify()
        self.assertEqual(code, 1)
        self.assertIn("not-passed", out)
        self.assertIn("FooTests.test_a", out)

    def test_acceptance_is_not_reused_for_a_skip_in_new_evidence(self):
        """Adversarial where a stored acceptance of test_a also excuses
        test_a skipping in later evidence that names no --accept-skip."""
        self.write_evidence("skipped 'x'", "ok")
        self.verify("--accept-skip", "FooTests.test_a", "--reason", REASON)
        code, out, _ = self.verify()
        self.assertEqual(code, 1, out)
        self.assertIn("not-passed", out)

    def test_failure_beside_an_accepted_skip_keeps_the_failed_test_open(self):
        """Adversarial where --accept-skip plus a FAIL elsewhere lands the
        checkpoint, hiding the failed test from open-ids."""
        self.write_evidence("skipped 'x'", "FAIL")
        self.verify("--accept-skip", "FooTests.test_a", "--reason", REASON)
        self.assertFalse(self.record()["landed"])
        _, open_out, _ = run_cli(["open-ids"])
        self.assertIn("test_b", open_out)

    def test_reason_with_newline_cannot_forge_report_lines(self):
        """Adversarial where a newline in --reason injects a fabricated
        `unchanged` finding line into the verify report."""
        self.write_evidence("skipped 'x'", "ok")
        reason = "why\n  unchanged    tests/test_foo.py"
        code, out, err = self.verify("--accept-skip", "FooTests.test_a", "--reason", reason)
        self.assertEqual(code, 0, out + err)
        forged = [
            line for line in out.splitlines()
            if line.strip().startswith("unchanged    tests/test_foo.py")
        ]
        self.assertEqual(len(forged), 1, forged)
        self.assertEqual(self.record()["accepted_skips"][0]["reason"], reason)

    def test_reason_with_quotes_round_trips_through_the_index(self):
        """Adversarial where quotes and backslashes in --reason corrupt the
        JSON index so the next verify cannot load it."""
        self.write_evidence("skipped 'x'", "ok")
        reason = 'say "hi" \\ it\'s'
        self.verify("--accept-skip", "FooTests.test_a", "--reason", reason)
        self.assertEqual(self.record()["accepted_skips"][0]["reason"], reason)
        code, out, err = run_cli(["verify", "TASK-310"])
        self.assertEqual(code, 0, out + err)
        self.assertIn(reason, out)

    def test_index_entry_missing_fields_does_not_crash_verify(self):
        """Adversarial where a hand-edited accepted_skips entry lacking
        `reason`/`evidence` raises KeyError while printing the report."""
        self.write_evidence("ok", "ok")
        self.verify()
        record = self.record()
        record["accepted_skips"] = [{"id": "FooTests.test_a"}]
        self.record_path().write_text(json.dumps(record), encoding="utf-8")
        try:
            code, _, _ = run_cli(["verify", "TASK-310"])
        except Exception as exc:  # noqa: BLE001
            self.fail(f"verify raised {type(exc).__name__}: {exc}")
        self.assertIn(code, (0, 1))

    def test_non_list_accepted_skips_in_index_does_not_crash_verify(self):
        """Adversarial where `accepted_skips` edited to a string or object
        breaks iteration."""
        self.write_evidence("ok", "ok")
        self.verify()
        for bad in ("oops", {"id": "x"}, 7, None):
            with self.subTest(bad=bad):
                record = self.record()
                record["accepted_skips"] = bad
                self.record_path().write_text(json.dumps(record), encoding="utf-8")
                try:
                    code, _, _ = run_cli(["verify", "TASK-310"])
                except Exception as exc:  # noqa: BLE001
                    self.fail(f"verify raised {type(exc).__name__}: {exc}")
                self.assertIn(code, (0, 1))

    def test_forged_acceptance_in_index_does_not_excuse_a_skip(self):
        """Adversarial where a hand-written accepted_skips entry makes a
        skipped test count as passed without any --accept-skip flag."""
        self.write_evidence("skipped 'x'", "ok")
        record = self.record()
        record["accepted_skips"] = [{
            "id": "FooTests.test_a", "reason": "forged",
            "evidence": "x", "accepted_at": "2026-01-01T00:00:00Z",
        }]
        self.record_path().write_text(json.dumps(record), encoding="utf-8")
        code, out, _ = self.verify()
        self.assertEqual(code, 1, out)
        self.assertIn("not-passed", out)


class SharedNameAcrossClassesTests(unittest.TestCase):
    def checkpoint_two_classes(self, task):
        repo_root = make_repo_vault(self)
        write_file(repo_root, "tests/__init__.py", INIT_SRC)
        write_file(repo_root, "tests/test_two.py", TWO_CLASS_SRC)
        sha = git_commit_all(repo_root, f"test({task}): two classes")
        with_vault_env(self, repo_root)
        code, out, err = run_cli(["record", task, "tests/test_two.py", "--commit", sha])
        self.assertEqual(code, 0, out + err)
        evidence = repo_root / "evidence.txt"
        evidence.write_text(
            "test_x (tests.test_two.AlphaTests) ... skipped 'a'\n"
            "test_x (tests.test_two.BetaTests) ... skipped 'b'\n",
            encoding="utf-8",
        )
        return evidence

    def test_accepting_one_class_does_not_accept_the_same_name_in_another(self):
        """Adversarial where `AlphaTests.test_x` skipped and accepted also
        excuses `BetaTests.test_x` skipping, via the shared bare name."""
        evidence = self.checkpoint_two_classes("TASK-311")
        code, out, _ = run_cli([
            "verify", "TASK-311", "--against-run", str(evidence),
            "--accept-skip", "AlphaTests.test_x", "--reason", REASON,
        ])
        self.assertEqual(code, 1, out)
        self.assertIn("BetaTests.test_x", out)
        self.assertIn("not-passed", out)

    def test_bare_shared_name_is_not_accepted_for_either_class(self):
        """Adversarial where the ambiguous bare `test_x` accepts both
        classes' skips."""
        evidence = self.checkpoint_two_classes("TASK-312")
        code, out, _ = run_cli([
            "verify", "TASK-312", "--against-run", str(evidence),
            "--accept-skip", "test_x", "--reason", REASON,
        ])
        self.assertEqual(code, 1, out)


if __name__ == "__main__":
    unittest.main()
