"""Tests for bug capture, dedup, and GitHub-issue filing."""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bugs  # noqa: E402
from commands import capture_bug, file_bugs  # noqa: E402

PLUGIN_YAML = (
    "plugin:\n  name: compass\n  version: 0.3.1\n"
    "  repository: https://github.com/hodor/claude-compass\n"
)


def make_vault(test_case):
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    root = tmp / ".compass"
    (root / "meta").mkdir(parents=True)
    (root / "meta" / "plugin.yaml").write_text(PLUGIN_YAML, encoding="utf-8")
    old = os.environ.get("CLAUDE_PROJECT_DIR")
    os.environ["CLAUDE_PROJECT_DIR"] = str(root.parent)
    test_case.addCleanup(
        lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
        else os.environ.pop("CLAUDE_PROJECT_DIR", None)
    )
    return root


class CaptureTests(unittest.TestCase):
    def test_same_bug_dedups_with_count(self):
        root = make_vault(self)
        fp1 = bugs.capture(root, "sync", "KeyError at sync.py:10", "tb", "0.3.1")
        fp2 = bugs.capture(root, "sync", "KeyError at sync.py:10", "tb", "0.3.1")
        self.assertEqual(fp1, fp2)
        records = bugs.load_all(root)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["count"], 2)
        self.assertFalse(records[0]["filed"])

    def test_distinct_bugs_distinct_records(self):
        root = make_vault(self)
        bugs.capture(root, "sync", "A", "x")
        bugs.capture(root, "validate", "B", "y")
        self.assertEqual(len(bugs.load_all(root)), 2)

    def test_capture_exception_records_type(self):
        root = make_vault(self)
        try:
            raise ValueError("boom")
        except ValueError as exc:
            bugs.capture_exception(root, "sync", exc)
        self.assertIn("ValueError", bugs.load_all(root)[0]["signature"])

    def test_mark_filed(self):
        root = make_vault(self)
        fp = bugs.capture(root, "sync", "A", "x")
        bugs.mark_filed(root, fp, "https://example/issues/1")
        record = bugs.load_all(root)[0]
        self.assertTrue(record["filed"])
        self.assertEqual(record["issue_url"], "https://example/issues/1")


class CaptureBugCommandTests(unittest.TestCase):
    def test_manual_capture(self):
        root = make_vault(self)
        with redirect_stdout(io.StringIO()):
            code = capture_bug.run(["validate", "false", "positive", "on", "retro"])
        self.assertEqual(code, 0)
        records = bugs.load_all(root)
        self.assertEqual(len(records), 1)
        self.assertIn("retro", records[0]["detail"])

    def test_empty_message_errors(self):
        make_vault(self)
        self.assertEqual(capture_bug.run([]), 1)


class FileBugsTests(unittest.TestCase):
    def _mock_gh(self, fn):
        original = file_bugs._gh
        self.addCleanup(setattr, file_bugs, "_gh", original)
        file_bugs._gh = fn

    def test_repo_slug_parsed(self):
        root = make_vault(self)
        self.assertEqual(file_bugs._repo_slug(root), "hodor/claude-compass")

    def test_dry_run_lists_but_does_not_file(self):
        root = make_vault(self)
        bugs.capture(root, "sync", "A", "x")
        self._mock_gh(lambda a: (0, "[]", ""))
        out = io.StringIO()
        with redirect_stdout(out):
            code = file_bugs.run([])
        self.assertEqual(code, 0)
        self.assertIn("would file", out.getvalue())
        self.assertFalse(bugs.load_all(root)[0]["filed"])

    def test_dedup_existing_issue_not_recreated(self):
        root = make_vault(self)
        fp = bugs.capture(root, "sync", "A", "x")

        def fake_gh(args):
            if args[1] == "list":
                return (0, json.dumps([{
                    "url": "https://github.com/hodor/claude-compass/issues/9",
                    "title": f"[compass-bug {fp}] sync: A",
                }]), "")
            raise AssertionError("must not create an issue that already exists")

        self._mock_gh(fake_gh)
        out = io.StringIO()
        with redirect_stdout(out):
            code = file_bugs.run(["--apply"])
        self.assertEqual(code, 0)
        self.assertIn("already open", out.getvalue())
        self.assertTrue(bugs.load_all(root)[0]["filed"])

    def test_apply_creates_when_new(self):
        root = make_vault(self)
        bugs.capture(root, "sync", "A", "x")

        def fake_gh(args):
            if args[1] == "list":
                return (0, "[]", "")
            if args[1] == "create":
                return (0, "https://github.com/hodor/claude-compass/issues/10", "")
            return (1, "", "?")

        self._mock_gh(fake_gh)
        out = io.StringIO()
        with redirect_stdout(out):
            file_bugs.run(["--apply"])
        record = bugs.load_all(root)[0]
        self.assertTrue(record["filed"])
        self.assertEqual(record["issue_url"], "https://github.com/hodor/claude-compass/issues/10")


if __name__ == "__main__":
    unittest.main()
