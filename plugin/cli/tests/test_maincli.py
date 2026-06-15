"""Tests for CLI dispatch and the never-exit-2 policy."""

import io
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maincli  # noqa: E402

ALL_COMMANDS = [name for name, _ in maincli.COMMAND_SPECS]


class HelpTests(unittest.TestCase):
    def test_help_lists_all_subcommands(self):
        self.assertGreaterEqual(len(ALL_COMMANDS), 9)
        out = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, redirect_stdout(out):
            maincli.main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        text = out.getvalue()
        for name in ALL_COMMANDS:
            self.assertIn(name, text)

    def test_no_args_prints_help_and_returns_0(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = maincli.main([])
        self.assertEqual(code, 0)
        self.assertIn("compass", out.getvalue())


class ExitCodePolicyTests(unittest.TestCase):
    def test_unknown_command_returns_1_not_2(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = maincli.main(["no-such-command"])
        self.assertEqual(code, 1)
        self.assertIn("unknown command", err.getvalue())

    def test_subcommand_receives_flag_args(self):
        # `sync --hook` must pass --hook through to the command, not error on it.
        captured = {}
        original = maincli.dispatch
        maincli.dispatch = lambda name, args: (captured.update(name=name, args=args), 0)[1]
        try:
            code = maincli.main(["sync", "--hook"])
        finally:
            maincli.dispatch = original
        self.assertEqual(code, 0)
        self.assertEqual(captured, {"name": "sync", "args": ["--hook"]})

    def test_absent_command_module_returns_1(self):
        # dispatch() for a name with no module reports not-implemented rather
        # than crashing. Exercised directly so the test never touches a vault.
        err = io.StringIO()
        with redirect_stderr(err):
            code = maincli.dispatch("no-such-command", [])
        self.assertEqual(code, 1)
        self.assertIn("not implemented", err.getvalue())

    def test_cli_err_clamps_code_2_to_1(self):
        self.assertEqual(maincli.cli_err("boom", code=2), 1)

    def test_dispatch_exception_becomes_exit_1_and_captures(self):
        # A handler that raises must surface as exit 1 (never crash/exit 2) and
        # the crash is auto-captured for later GitHub-issue filing.
        import os
        import shutil
        import tempfile
        from pathlib import Path
        import bugs

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / ".compass").mkdir()
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(tmp)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
            else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )

        original = maincli.dispatch
        maincli.dispatch = lambda name, args: (_ for _ in ()).throw(RuntimeError("kaboom"))
        try:
            err = io.StringIO()
            with redirect_stderr(err):
                code = maincli.main(["validate"])
            self.assertEqual(code, 1)
            self.assertIn("kaboom", err.getvalue())
        finally:
            maincli.dispatch = original

        captured = bugs.load_all(tmp / ".compass")
        self.assertTrue(captured)
        self.assertIn("RuntimeError", captured[0]["signature"])


if __name__ == "__main__":
    unittest.main()
