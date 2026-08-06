"""Tests for the capture-family commands (`capture-signal` today; `capture-check`
and `capture-stats` land in later tasks and append here). Adversarial: the
SubagentStop hook path must never fail the turn that triggered it, so most
cases assert "exits 0, records nothing" under a malformed or absent input
rather than a happy path."""

import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import capturelib  # noqa: E402
from commands import capture_signal  # noqa: E402


def make_vault(test_case):
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    root = tmp / ".compass"
    root.mkdir(parents=True)
    return root


def with_vault_env(test_case, vault_root):
    """Point find_vault_root at this vault (or, when `vault_root` is a bare
    project dir with no .compass, at nowhere) for the duration of the test."""
    old = os.environ.get("CLAUDE_PROJECT_DIR")
    os.environ["CLAUDE_PROJECT_DIR"] = str(vault_root)

    def restore():
        if old is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = old

    test_case.addCleanup(restore)


def feed_stdin(test_case, payload):
    """Pipe `payload` (a dict, serialized as JSON, or a raw string for
    malformed-input cases) as the process's stdin for the duration of the
    test."""
    test_case.addCleanup(setattr, sys, "stdin", sys.stdin)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    sys.stdin = io.StringIO(text)


def captures_dir(vault_root):
    return vault_root / "tmp" / "subagent-captures"


class CaptureSignalTests(unittest.TestCase):
    def _run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = capture_signal.run(["--hook"])
        return code, out.getvalue()

    def test_validator_writes_capture_and_records_validator_finished(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {
            "agent_type": "validator",
            "agent_id": "agent-1",
            "last_assistant_message": "PASS: all checks green",
        })
        code, _ = self._run()
        self.assertEqual(code, 0)

        files = list(captures_dir(root).glob("*_validator.md"))
        self.assertEqual(len(files), 1)
        text = files[0].read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("type: subagent_capture\n", text)
        self.assertIn("agent_type: validator\n", text)
        self.assertIn("agent_id: agent-1\n", text)
        self.assertIn("captured_at: ", text)
        # Body is the message verbatim - byte-identical past the frontmatter.
        body = text.split("---\n", 2)[2].lstrip("\n")
        self.assertEqual(body, "PASS: all checks green")

        state = capturelib.load_state(root)
        self.assertEqual(len(state["signals"]), 1)
        self.assertEqual(state["signals"][0]["kind"], "validator-finished")

    def test_debug_records_debug_finished(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"agent_type": "debug", "last_assistant_message": "found it"})
        self._run()
        state = capturelib.load_state(root)
        self.assertEqual(state["signals"][0]["kind"], "debug-finished")

    def test_builder_records_builder_finished(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"agent_type": "builder", "last_assistant_message": "done"})
        self._run()
        state = capturelib.load_state(root)
        self.assertEqual(state["signals"][0]["kind"], "builder-finished")

    def test_other_agent_type_records_subagent_finished(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"agent_type": "researcher", "last_assistant_message": "notes"})
        self._run()
        state = capturelib.load_state(root)
        self.assertEqual(state["signals"][0]["kind"], "subagent-finished")

    def test_malformed_json_exits_0_and_records_nothing(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, "{not json at all")
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertFalse(captures_dir(root).is_dir())
        state = capturelib.load_state(root)
        self.assertEqual(state["signals"], [])

    def test_empty_stdin_exits_0_and_records_nothing(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, "")
        code, _ = self._run()
        self.assertEqual(code, 0)
        self.assertFalse(captures_dir(root).is_dir())

    def test_missing_vault_exits_0(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        # find_vault_root falls back to walking up from cwd when
        # CLAUDE_PROJECT_DIR has no .compass/, so cwd must also sit outside
        # this repo's own vault - otherwise the fallback would find it.
        old_cwd = os.getcwd()
        os.chdir(tmp)
        self.addCleanup(os.chdir, old_cwd)
        with_vault_env(self, tmp)  # no .compass/ under this dir either
        feed_stdin(self, {"agent_type": "builder", "last_assistant_message": "x"})
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_agent_type_absent_still_writes_and_records_default_signal(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"last_assistant_message": "no agent_type on this event"})
        code, _ = self._run()
        self.assertEqual(code, 0)
        files = list(captures_dir(root).glob("*_unknown.md"))
        self.assertEqual(len(files), 1)
        state = capturelib.load_state(root)
        self.assertEqual(state["signals"][0]["kind"], "subagent-finished")

    def test_empty_last_assistant_message_still_writes_capture(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"agent_type": "builder", "last_assistant_message": ""})
        code, _ = self._run()
        self.assertEqual(code, 0)
        files = list(captures_dir(root).glob("*_builder.md"))
        self.assertEqual(len(files), 1)
        body = files[0].read_text(encoding="utf-8").split("---\n", 2)[2].lstrip("\n")
        self.assertEqual(body, "")

    def test_huge_message_is_not_truncated(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        huge = "x" * 500_000
        feed_stdin(self, {"agent_type": "builder", "last_assistant_message": huge})
        code, _ = self._run()
        self.assertEqual(code, 0)
        files = list(captures_dir(root).glob("*_builder.md"))
        body = files[0].read_text(encoding="utf-8").split("---\n", 2)[2].lstrip("\n")
        self.assertEqual(len(body), 500_000)

    def test_same_second_collision_does_not_overwrite(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"agent_type": "builder", "last_assistant_message": "first"})
        self._run()
        feed_stdin(self, {"agent_type": "builder", "last_assistant_message": "second"})
        self._run()

        files = sorted(captures_dir(root).glob("*_builder*.md"))
        self.assertEqual(len(files), 2)
        bodies = {
            f.read_text(encoding="utf-8").split("---\n", 2)[2].lstrip("\n") for f in files
        }
        self.assertEqual(bodies, {"first", "second"})

    def test_filenames_match_expected_timestamp_shape(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"agent_type": "builder", "last_assistant_message": "x"})
        self._run()
        files = list(captures_dir(root).glob("*.md"))
        self.assertEqual(len(files), 1)
        self.assertRegex(
            files[0].name, r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}_builder\.md$"
        )

    def test_no_hook_flag_never_reads_stdin(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)

        class _Boom:
            def read(self_inner):
                raise AssertionError("no --hook flag: stdin must never be read")

        self.addCleanup(setattr, sys, "stdin", sys.stdin)
        sys.stdin = _Boom()
        code = capture_signal.run([])
        self.assertEqual(code, 0)
        self.assertFalse(captures_dir(root).is_dir())

    def test_internal_error_after_stdin_parse_still_exits_0(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        feed_stdin(self, {"agent_type": "builder", "last_assistant_message": "x"})
        original = capturelib.record_signal
        capturelib.record_signal = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            code, out = self._run()
        finally:
            capturelib.record_signal = original
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
