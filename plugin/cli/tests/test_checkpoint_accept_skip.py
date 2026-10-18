"""Tests for `compass test-checkpoint verify --accept-skip`.

A test skipped by design on the machine that produced the run evidence would
keep its whole checkpoint unlanded. `--accept-skip Class.test_name --reason`
accepts exactly the named skips. Each case here is a way the acceptance could
reach further than it names: a failed or absent test accepted by mistake, an
unnamed skip riding along, a reason that goes missing, or an acceptance that
is not kept in the record.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_test_checkpoint import build_checkpoint, checkpoint_path, run_cli  # noqa: E402

REASON = "POSIX-only, skipped on Windows"


class AcceptSkipTests(unittest.TestCase):
    def setUp(self):
        self.repo_root, _ = build_checkpoint(self, "TASK-300")
        self.evidence = self.repo_root / "evidence.txt"

    def write_evidence(self, a, b):
        self.evidence.write_text(
            f"test_a (tests.test_foo.FooTests) ... {a}\n"
            f"test_b (tests.test_foo.FooTests) ... {b}\n",
            encoding="utf-8",
        )

    def verify(self, *extra):
        return run_cli(["verify", "TASK-300", "--against-run", str(self.evidence), *extra])

    def record(self):
        return json.loads(checkpoint_path(self.repo_root, "TASK-300").read_text(encoding="utf-8"))

    def test_named_skip_lands_the_checkpoint_and_records_the_acceptance(self):
        """Adversarial where a by-design skip keeps the checkpoint unlanded
        or lands it without leaving an audit entry."""
        self.write_evidence("skipped 'posix only'", "ok")
        code, out, err = self.verify("--accept-skip", "FooTests.test_a", "--reason", REASON)
        self.assertEqual(code, 0, out + err)
        self.assertIn("accepted-skip", out)
        record = self.record()
        self.assertTrue(record["landed"])
        [entry] = record["accepted_skips"]
        self.assertEqual(entry["id"], "FooTests.test_a")
        self.assertEqual(entry["reason"], REASON)
        self.assertEqual(entry["evidence"], str(self.evidence))
        self.assertTrue(entry["accepted_at"].endswith("Z"))

    def test_later_verify_prints_the_stored_acceptance(self):
        """Adversarial where the acceptance is stored but invisible to anyone
        verifying afterwards."""
        self.write_evidence("skipped 'posix only'", "ok")
        self.verify("--accept-skip", "FooTests.test_a", "--reason", REASON)
        code, out, err = run_cli(["verify", "TASK-300"])
        self.assertEqual(code, 0, out + err)
        self.assertIn("accepted-skip", out)
        self.assertIn("FooTests.test_a", out)
        self.assertIn(REASON, out)

    def test_reason_before_its_flag_and_repeated_flags_are_accepted(self):
        """Adversarial where two named skips collapse to one acceptance or
        share the wrong reason."""
        self.write_evidence("skipped 'x'", "skipped 'y'")
        code, out, err = self.verify(
            "--accept-skip", "FooTests.test_a", "--reason", "first",
            "--reason", "second", "--accept-skip", "FooTests.test_b",
        )
        self.assertEqual(code, 0, out + err)
        reasons = {e["id"]: e["reason"] for e in self.record()["accepted_skips"]}
        self.assertEqual(
            reasons, {"FooTests.test_a": "first", "FooTests.test_b": "second"}
        )

    def test_unnamed_skip_is_still_a_finding(self):
        """Adversarial where naming one skip accepts every skip."""
        self.write_evidence("skipped 'x'", "skipped 'y'")
        code, out, _ = self.verify("--accept-skip", "FooTests.test_a", "--reason", REASON)
        self.assertEqual(code, 1)
        self.assertIn("not-passed", out)
        self.assertIn("FooTests.test_b", out)
        self.assertFalse(self.record()["landed"])

    def test_failed_test_is_never_accepted(self):
        """Adversarial where --accept-skip launders a FAIL."""
        self.write_evidence("FAIL", "ok")
        code, out, _ = self.verify("--accept-skip", "FooTests.test_a", "--reason", REASON)
        self.assertEqual(code, 1)
        self.assertIn("not-passed", out)
        self.assertNotIn("accepted_skips", self.record())

    def test_errored_test_is_never_accepted(self):
        """Adversarial where --accept-skip launders an ERROR."""
        self.write_evidence("ERROR", "ok")
        code, out, _ = self.verify("--accept-skip", "FooTests.test_a", "--reason", REASON)
        self.assertEqual(code, 1)
        self.assertIn("not-passed", out)

    def test_absent_test_is_never_accepted(self):
        """Adversarial where a test missing from the evidence counts as a
        skip."""
        self.evidence.write_text(
            "test_b (tests.test_foo.FooTests) ... ok\n", encoding="utf-8"
        )
        code, out, _ = self.verify("--accept-skip", "FooTests.test_a", "--reason", REASON)
        self.assertEqual(code, 1)
        self.assertIn("not present in run evidence", out)

    def test_name_outside_the_checkpoint_is_rejected_even_when_all_else_passes(self):
        """Adversarial where a typo in the accepted name silently does
        nothing and the checkpoint lands anyway."""
        self.write_evidence("ok", "ok")
        code, out, _ = self.verify("--accept-skip", "FooTests.test_zzz", "--reason", REASON)
        self.assertEqual(code, 1)
        self.assertIn("test_zzz", out)
        self.assertFalse(self.record()["landed"])

    def test_accepted_skip_does_not_land_when_another_test_failed(self):
        """Adversarial where an acceptance is recorded for a checkpoint that
        did not land."""
        self.write_evidence("skipped 'x'", "FAIL")
        code, _, _ = self.verify("--accept-skip", "FooTests.test_a", "--reason", REASON)
        self.assertEqual(code, 1)
        record = self.record()
        self.assertFalse(record["landed"])
        self.assertNotIn("accepted_skips", record)

    def test_malformed_invocations_exit_1_never_2(self):
        """Adversarial where a missing or blank value, or an orphan flag,
        raises or exits 2 instead of reporting."""
        self.write_evidence("skipped 'x'", "ok")
        cases = [
            ["--accept-skip", "FooTests.test_a"],
            ["--accept-skip", "FooTests.test_a", "--reason", "   "],
            ["--accept-skip"],
            ["--reason", REASON],
            ["--accept-skip", "", "--reason", REASON],
            ["--accept-skip", "FooTests.test_a", "--reason", "a", "--reason", "b"],
        ]
        for extra in cases:
            with self.subTest(extra=extra):
                code, _, err = self.verify(*extra)
                self.assertEqual(code, 1)
                self.assertIn("usage", err)

    def test_accept_skip_without_against_run_exits_1(self):
        """Adversarial where the flag is silently ignored when there is no
        evidence to accept against."""
        code, _, err = run_cli(
            ["verify", "TASK-300", "--accept-skip", "FooTests.test_a", "--reason", REASON]
        )
        self.assertEqual(code, 1)
        self.assertIn("--against-run", err)

    def test_usage_line_names_the_flag(self):
        code, _, err = run_cli(["verify"])
        self.assertEqual(code, 1)
        self.assertIn("--accept-skip", err)


if __name__ == "__main__":
    unittest.main()
