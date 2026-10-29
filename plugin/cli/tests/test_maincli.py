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

    def test_output_a_console_cannot_encode_is_escaped_not_a_crash(self):
        # A cp1252 console has no box-drawing glyph; a command printing one
        # raised UnicodeEncodeError and lost its whole report (GitHub #45).
        import subprocess
        cli_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
        script = ("import sys; sys.path.insert(0, sys.argv[1]); import maincli;"
                  "maincli.dispatch = lambda name, args: maincli.cli_ok('report \u2500 end');"
                  "sys.exit(maincli.main(['sync']))")
        proc = subprocess.run([sys.executable, "-c", script, cli_dir], env=env, capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("cp1252"))
        self.assertEqual(proc.stdout.decode("cp1252").strip(), "report \\u2500 end")

    def test_output_to_a_reader_that_closes_early_is_not_a_crash(self):
        # `compass test-checkpoint open-ids | head -1` closes the pipe while
        # the command still writes; the write raised BrokenPipeError, which
        # printed a traceback and was captured as a Compass bug (GitHub #48).
        import shutil
        import subprocess
        import tempfile
        from pathlib import Path
        import bugs

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / ".compass").mkdir()
        cli_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(tmp))
        script = ("import sys; sys.path.insert(0, sys.argv[1]); import maincli;"
                  "maincli.dispatch = lambda name, args: sys.stdout.write('line\\n' * 2000000) and 0;"
                  "sys.exit(maincli.main(['sync']))")
        proc = subprocess.Popen([sys.executable, "-c", script, cli_dir], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.stdout.readline()
        proc.stdout.close()
        err = proc.stderr.read()
        proc.stderr.close()
        proc.wait(timeout=60)
        self.assertNotIn(b"Traceback", err)
        self.assertNotIn(b"Broken pipe", err)
        self.assertNotIn(b"BrokenPipeError", err)
        self.assertEqual(bugs.load_all(tmp / ".compass"), [])

    def test_help_flag_prints_the_command_usage_and_returns_0(self):
        # `compass sessions --help` and `compass clone --help` answered
        # "unknown argument" instead of usage (GitHub #46). The flag reads
        # in any position, so `sessions list --help` answers too.
        from commands import clone, sessions
        for argv, usage in ((["sessions", "--help"], sessions.USAGE),
                            (["sessions", "list", "--help"], sessions.USAGE),
                            (["clone", "-h"], clone.USAGE)):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = maincli.main(argv)
            self.assertEqual(code, 0, f"{argv}: {err.getvalue()}")
            self.assertEqual(out.getvalue().strip(), usage.strip(), argv)
            self.assertEqual(err.getvalue(), "", argv)

    def test_help_flag_on_a_command_without_usage_reaches_the_command(self):
        # A command with no USAGE text owns its arguments; the flag passes
        # through to it unchanged.
        seen = []
        original = maincli.dispatch
        maincli.dispatch = lambda name, args: seen.append((name, args)) or 0
        try:
            code = maincli.main(["sync", "--help"])
        finally:
            maincli.dispatch = original
        self.assertEqual(code, 0)
        self.assertEqual(seen, [("sync", ["--help"])])

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
