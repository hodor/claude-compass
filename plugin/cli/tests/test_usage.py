"""Tests for `compass usage` - the per-command invocation record (ADR-017).

Adversarial classes: recording must never raise (outside a vault, corrupt
record file, unwritable path), the never-used group must list zero-count
commands explicitly, and retirement must actually remove the two commands
from the dispatch surface.
"""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maincli  # noqa: E402
from commands import usage as usage_cmd  # noqa: E402


class UsageFixture(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.project = tmp / "project"
        self.vault = self.project / ".compass"
        (self.vault / "meta").mkdir(parents=True)
        self._cwd = os.getcwd()
        os.chdir(self.project)
        self.addCleanup(os.chdir, self._cwd)

    def record_file(self):
        return self.vault / "meta" / "usage.yaml"


class RecordTests(UsageFixture):
    def test_first_record_creates_file_with_since_and_count_one(self):
        usage_cmd.record("sync")
        text = self.record_file().read_text(encoding="utf-8")
        self.assertIn("since:", text)
        self.assertIn("sync:", text)
        self.assertIn("count: 1", text)

    def test_second_record_increments_and_keeps_one_since(self):
        usage_cmd.record("sync")
        usage_cmd.record("sync")
        text = self.record_file().read_text(encoding="utf-8")
        self.assertIn("count: 2", text)
        self.assertEqual(text.count("since:"), 1)

    def test_outside_a_vault_is_a_silent_noop(self):
        os.chdir(self._cwd)
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        os.chdir(outside)
        usage_cmd.record("sync")  # must not raise
        self.assertFalse((outside / ".compass").exists())

    def test_corrupt_record_file_is_rewritten_not_fatal(self):
        self.record_file().write_text("{{{ not yaml", encoding="utf-8")
        usage_cmd.record("sync")
        text = self.record_file().read_text(encoding="utf-8")
        self.assertIn("sync:", text)
        self.assertIn("count: 1", text)

    def test_dispatch_records(self):
        maincli.main(["next-num", "spec"])
        self.assertIn("next-num:", self.record_file().read_text(encoding="utf-8"))


class ReportTests(UsageFixture):
    def run_report(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = usage_cmd.run([])
        return code, buf.getvalue()

    def test_never_used_commands_listed_explicitly(self):
        usage_cmd.record("sync")
        code, out = self.run_report()
        self.assertEqual(code, 0)
        self.assertIn("NEVER USED", out)
        self.assertIn("admit-check", out)  # zero-count row is visible

    def test_hook_commands_grouped_separately(self):
        usage_cmd.record("sync")
        usage_cmd.record("validate")
        _, out = self.run_report()
        hook_pos = out.index("hook-fired")
        self.assertIn("sync", out[hook_pos:])
        self.assertLess(out.index("validate"), hook_pos)

    def test_missing_record_file_reports_all_never_used_exit_zero(self):
        code, out = self.run_report()
        self.assertEqual(code, 0)
        self.assertIn("NEVER USED", out)


class RetirementTests(unittest.TestCase):
    def test_tree_and_clean_tmp_are_gone_from_dispatch(self):
        self.assertNotIn("tree", maincli.VALID_COMMANDS)
        self.assertNotIn("clean-tmp", maincli.VALID_COMMANDS)

    def test_usage_is_dispatchable(self):
        self.assertIn("usage", maincli.VALID_COMMANDS)

    def test_retired_modules_are_deleted(self):
        commands_dir = Path(maincli.__file__).parent / "commands"
        self.assertFalse((commands_dir / "tree.py").exists())
        self.assertFalse((commands_dir / "clean_tmp.py").exists())


class DoctorUsageRowTests(UsageFixture):
    def _doctor_output(self):
        from commands import doctor

        buf = io.StringIO()
        with redirect_stdout(buf):
            doctor.run([])
        return buf.getvalue()

    def test_row_present_when_record_missing(self):
        self.assertIn("capability usage", self._doctor_output())

    def test_young_record_stays_ok_with_state_named(self):
        usage_cmd.record("sync")
        out = self._doctor_output()
        self.assertIn("unused so far", out)
        self.assertNotIn("never used in", out)

    def test_dead_commands_warn_once_record_is_old(self):
        usage_cmd.record("sync")
        path = self.record_file()
        text = path.read_text(encoding="utf-8")
        import re
        path.write_text(
            re.sub(r"since: \S+", "since: 2026-01-01", text), encoding="utf-8"
        )
        self.assertIn("never used in", self._doctor_output())


if __name__ == "__main__":
    unittest.main()
