"""Tests for `compass loop sense-ast-grep`: the sensor adapter that turns an
ast-grep scan into a sensor reading.

Public contract these tests pin
(`compass loop sense-ast-grep --rule <file> [--bin <path>] [paths...]`):

    It runs `<bin> scan --rule <file> --json=stream [paths...]` from the
    project root and prints one JSON object `{"valid", "value", "items"}`
    (plus `reason` when invalid). The exit code is 0 on every path.

    An item is the match's `file` with forward slashes, a colon, and the
    match's `text` with every run of whitespace collapsed to one space; never
    a line number. `value` is the number of items.

    Scan exit 0, and exit 1 with matches (an error-severity rule matched), are
    valid. Lines not starting with `{` are skipped. A `{` line that does not
    parse, any other exit code, exit 1 with no match, or a missing binary is
    `valid: false` with a reason. Without `--bin` the binary is `ast-grep` on
    PATH, never `sg`.

    `sensorlib.parse_ast_grep_scan(stdout, returncode)` is the parser.

The fixtures under `fixtures/ast_grep/` are the raw `--json=stream` output of
the three rules the ast-grep experiment drafted (ast-grep 0.51.0 on Windows),
each holding ten matches with backslash paths and 0-based lines.

Adversarial themes: a line number leaking into the identity, a backslash
surviving on Windows paths, the trailing error block read as a match or as a
parse failure, exit 1 read as a failure, duplicate matches collapsed into one,
`sg` picked up from PATH, and a failure that exits non-zero or prints no JSON.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CLI_DIR)

import maincli  # noqa: E402
import sensorlib  # noqa: E402

COMPASS = os.path.join(CLI_DIR, "compass")
FIXTURES = Path(CLI_DIR) / "tests" / "fixtures" / "ast_grep"
SUBCOMMAND = "sense-ast-grep"
ERROR_BLOCK = (
    "\nError: 10 error(s) found in code.\n"
    "Help: Scan succeeded and found error level diagnostics in the codebase.\n"
)

# The stub replays the file named by STUB_OUT with the exit code STUB_EXIT and
# records its argv and working directory as JSON to STUB_LOG.
STUB_BODY = r'''
import json, os, sys
log = os.environ.get("STUB_LOG")
if log:
    with open(log, "w", encoding="utf-8") as fh:
        json.dump({"argv": sys.argv[1:], "cwd": os.getcwd()}, fh)
out = os.environ.get("STUB_OUT")
if out:
    with open(out, "rb") as fh:
        sys.stdout.buffer.write(fh.read())
    sys.stdout.flush()
sys.exit(int(os.environ.get("STUB_EXIT", "0")))
'''


def make_stub(folder, name):
    """An executable named `name` (plus .bat on Windows) in `folder` that runs
    the stub body."""
    folder.mkdir(parents=True, exist_ok=True)
    body = folder / "stub_body.py"
    body.write_text(STUB_BODY, encoding="utf-8")
    if sys.platform == "win32":
        launcher = folder / f"{name}.bat"
        launcher.write_text(
            '@echo off\r\n"' + sys.executable + '" "' + str(body) + '" %*\r\n',
            encoding="utf-8",
        )
    else:
        launcher = folder / name
        launcher.write_text(
            '#!/bin/sh\nexec "' + sys.executable + '" "' + str(body) + '" "$@"\n',
            encoding="utf-8",
        )
        launcher.chmod(0o755)
    return launcher


def match(file, text, line=0):
    """One `--json=stream` match line shaped like ast-grep 0.51.0's."""
    lines = text.count("\n")
    return json.dumps({
        "text": text,
        "range": {"start": {"line": line, "column": 4},
                  "end": {"line": line + lines, "column": 10}},
        "file": file,
        "lines": text,
        "ruleId": "r",
        "severity": "error",
        "message": "m",
    })


def fixture_text(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class ParserTests(unittest.TestCase):
    def test_each_fixture_yields_ten_items_with_forward_slashes(self):
        """Adversarial where: the Windows backslash paths ast-grep prints
        survive into the identity, or a line is dropped or double-counted."""
        for name in ("R1-scan.jsonl", "R2-scan.jsonl", "R3-scan.jsonl"):
            with self.subTest(fixture=name):
                reading = sensorlib.parse_ast_grep_scan(fixture_text(name), 0)
                self.assertTrue(reading.valid, reading.reason)
                self.assertEqual(reading.value, 10)
                self.assertEqual(len(reading.items), 10)
                for item in reading.items:
                    self.assertNotIn("\\", item)
                    self.assertIn("/", item.split(":", 1)[0])

    def test_item_is_file_colon_collapsed_text(self):
        """Adversarial where: the multi-line match text keeps its newline and
        indentation, so a reindent changes the identity."""
        reading = sensorlib.parse_ast_grep_scan(fixture_text("R1-scan.jsonl"), 0)
        self.assertIn("util/retry.py:except: return None", reading.items)

    def test_identity_holds_no_line_number(self):
        """Adversarial where: the item is built from the range, so a match
        moved down three lines by an unrelated edit becomes a new item."""
        before = sensorlib.parse_ast_grep_scan(match("a\\b.py", "print(x)", line=4) + "\n", 0)
        after = sensorlib.parse_ast_grep_scan(match("a\\b.py", "print(x)", line=7) + "\n", 0)
        self.assertTrue(before.valid and after.valid)
        self.assertEqual(before.items, after.items)
        self.assertEqual(before.items, ["a/b.py:print(x)"])

    def test_two_identical_matches_in_one_file_are_two_items(self):
        """Adversarial where: items are deduplicated, so a second copy of the
        same violation is invisible to the multiset judgment."""
        text = match("m.py", "print(x)", 1) + "\n" + match("m.py", "print(x)", 9) + "\n"
        reading = sensorlib.parse_ast_grep_scan(text, 0)
        self.assertTrue(reading.valid)
        self.assertEqual(reading.value, 2)
        self.assertEqual(reading.items, ["m.py:print(x)", "m.py:print(x)"])

    def test_exit_one_with_matches_is_valid(self):
        """Adversarial where: any non-zero exit is read as a failure, though
        ast-grep exits 1 whenever an error-severity rule matched."""
        reading = sensorlib.parse_ast_grep_scan(fixture_text("R2-scan.jsonl") + ERROR_BLOCK, 1)
        self.assertTrue(reading.valid, reading.reason)
        self.assertEqual(reading.value, 10)

    def test_trailing_error_block_is_skipped(self):
        reading = sensorlib.parse_ast_grep_scan(fixture_text("R3-scan.jsonl") + ERROR_BLOCK, 0)
        self.assertTrue(reading.valid, reading.reason)
        self.assertEqual(reading.value, 10)
        self.assertFalse(any(i.startswith("Error") or i.startswith("Help") for i in reading.items))

    def test_truncated_json_line_is_invalid_with_a_reason(self):
        text = fixture_text("R1-scan.jsonl") + '{"text":"print(x)","file":"a.py"\n'
        reading = sensorlib.parse_ast_grep_scan(text, 0)
        self.assertFalse(reading.valid)
        self.assertTrue(reading.reason)

    def test_json_line_missing_file_or_text_is_invalid(self):
        for line in ('{"text": "x"}', '{"file": "a.py"}', '{"file": 3, "text": "x"}', '[1]'):
            with self.subTest(line=line):
                reading = sensorlib.parse_ast_grep_scan(line + "\n", 0)
                if line.startswith("{"):
                    self.assertFalse(reading.valid, line)
                    self.assertTrue(reading.reason)

    def test_other_exit_codes_are_invalid_with_a_reason(self):
        for code in (2, 3, -1, 255):
            with self.subTest(code=code):
                reading = sensorlib.parse_ast_grep_scan(fixture_text("R1-scan.jsonl"), code)
                self.assertFalse(reading.valid)
                self.assertIn(str(code), reading.reason)

    def test_exit_one_with_no_match_is_invalid(self):
        """Adversarial where: a scan that failed before matching anything (a
        broken rule file) exits 1 and is read as a clean zero."""
        reading = sensorlib.parse_ast_grep_scan("Error: cannot parse rule\n", 1)
        self.assertFalse(reading.valid)
        self.assertTrue(reading.reason)

    def test_empty_stream_with_exit_zero_is_a_valid_zero(self):
        for text in ("", "\n", "\r\n"):
            with self.subTest(text=text):
                reading = sensorlib.parse_ast_grep_scan(text, 0)
                self.assertTrue(reading.valid, reading.reason)
                self.assertEqual(reading.value, 0)
                self.assertEqual(reading.items, [])

    def test_crlf_stream_parses(self):
        text = fixture_text("R1-scan.jsonl").replace("\n", "\r\n")
        reading = sensorlib.parse_ast_grep_scan(text, 0)
        self.assertTrue(reading.valid, reading.reason)
        self.assertEqual(reading.value, 10)


class CommandCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="astgrep-sensor-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.project = self.tmp / "project"
        (self.project / ".compass").mkdir(parents=True)
        (self.project / ".compass" / "index.md").write_text("# Index\n", encoding="utf-8")
        self.rule = self.project / "rule.yml"
        self.rule.write_text("id: r\nlanguage: python\nrule:\n  pattern: print($$$)\n",
                             encoding="utf-8")
        self.stub = make_stub(self.tmp / "bin", "ast-grep")
        self.log = self.tmp / "argv.json"
        self.out = self.tmp / "out.jsonl"
        self.out.write_text("", encoding="utf-8")

    def sense(self, *args, out_text=None, exit_code=0, env_extra=None, cwd=None):
        """Run `python compass loop sense-ast-grep <args>` as a real process.
        Returns (exit code, parsed stdout, stderr)."""
        if out_text is not None:
            self.out.write_bytes(out_text.encode("utf-8"))
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.project)
        env["PYTHONIOENCODING"] = "utf-8"
        env["STUB_LOG"] = str(self.log)
        env["STUB_OUT"] = str(self.out)
        env["STUB_EXIT"] = str(exit_code)
        env.update(env_extra or {})
        proc = subprocess.run(
            [sys.executable, COMPASS, "loop", SUBCOMMAND, *args],
            capture_output=True, text=True, encoding="utf-8", env=env,
            cwd=str(cwd or self.project), timeout=120,
        )
        try:
            reading = json.loads(proc.stdout)
        except ValueError:
            reading = None
        return proc.returncode, reading, proc.stderr


class CommandTests(CommandCase):
    def test_fixture_through_the_command_reads_ten(self):
        code, reading, err = self.sense(
            "--rule", str(self.rule), "--bin", str(self.stub),
            out_text=fixture_text("R1-scan.jsonl") + ERROR_BLOCK, exit_code=1,
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(reading["valid"], True, reading)
        self.assertEqual(reading["value"], 10)
        self.assertFalse(any("\\" in item for item in reading["items"]))

    def test_scan_argv_and_working_directory(self):
        """Adversarial where: the rule or the paths are dropped, the stream
        flag is spelled differently, or the scan runs from the caller's
        folder instead of the project root."""
        sub = self.project / "src"
        sub.mkdir()
        code, reading, err = self.sense(
            "--rule", str(self.rule), "--bin", str(self.stub), "src", "lib",
            out_text="", cwd=sub,
        )
        self.assertEqual(code, 0, err)
        self.assertTrue(reading["valid"], reading)
        seen = json.loads(self.log.read_text(encoding="utf-8"))
        argv = seen["argv"]
        self.assertEqual(argv[0], "scan")
        self.assertIn("--json=stream", argv)
        rule_at = argv.index("--rule")
        self.assertEqual(Path(argv[rule_at + 1]).resolve(), self.rule.resolve())
        self.assertEqual(argv[-2:], ["src", "lib"])
        self.assertEqual(Path(seen["cwd"]).resolve(), self.project.resolve())

    def test_relative_rule_resolves_from_the_caller_folder(self):
        sub = self.project / "rules"
        sub.mkdir()
        rule = sub / "r.yml"
        rule.write_text("id: r\n", encoding="utf-8")
        code, reading, err = self.sense("--rule", "r.yml", "--bin", str(self.stub),
                                        out_text="", cwd=sub)
        self.assertEqual(code, 0, err)
        argv = json.loads(self.log.read_text(encoding="utf-8"))["argv"]
        self.assertEqual(Path(argv[argv.index("--rule") + 1]).resolve(), rule.resolve())

    def test_exit_two_is_invalid_and_the_command_exits_zero(self):
        code, reading, err = self.sense("--rule", str(self.rule), "--bin", str(self.stub),
                                        out_text=fixture_text("R1-scan.jsonl"), exit_code=2)
        self.assertEqual(code, 0, err)
        self.assertFalse(reading["valid"])
        self.assertTrue(reading["reason"])

    def test_missing_binary_is_invalid_with_a_reason(self):
        code, reading, err = self.sense("--rule", str(self.rule),
                                        "--bin", str(self.tmp / "nowhere" / "ast-grep"))
        self.assertEqual(code, 0, err)
        self.assertFalse(reading["valid"])
        self.assertTrue(reading["reason"])

    def test_without_bin_uses_ast_grep_on_path(self):
        env = {"PATH": str(self.stub.parent) + os.pathsep + os.environ.get("PATH", "")}
        code, reading, err = self.sense("--rule", str(self.rule),
                                        out_text=fixture_text("R2-scan.jsonl"), env_extra=env)
        self.assertEqual(code, 0, err)
        self.assertTrue(reading["valid"], reading)
        self.assertEqual(reading["value"], 10)

    def test_sg_on_path_is_never_used(self):
        """Adversarial where: the adapter falls back to `sg`, which on Linux is
        often the shadow-group tool rather than ast-grep."""
        only_sg = self.tmp / "sg-only"
        make_stub(only_sg, "sg")
        env = {"PATH": str(only_sg)}
        code, reading, err = self.sense("--rule", str(self.rule),
                                        out_text=fixture_text("R2-scan.jsonl"), env_extra=env)
        self.assertEqual(code, 0, err)
        self.assertFalse(reading["valid"], reading)
        self.assertIn("ast-grep", reading["reason"])
        self.assertFalse(self.log.exists(), "the sg stub ran")

    def test_missing_rule_argument_is_invalid_and_exits_zero(self):
        for args in ((), ("--bin", "x"), ("--rule",), ("--rule", "--bin", "x")):
            with self.subTest(args=args):
                code, reading, err = self.sense(*args)
                self.assertEqual(code, 0, err)
                self.assertIsInstance(reading, dict)
                self.assertFalse(reading["valid"])
                self.assertTrue(reading["reason"])

    def test_missing_rule_file_is_invalid(self):
        code, reading, err = self.sense("--rule", str(self.tmp / "absent.yml"),
                                        "--bin", str(self.stub), out_text="")
        self.assertEqual(code, 0, err)
        self.assertFalse(reading["valid"])
        self.assertIn("absent.yml", reading["reason"])

    def test_reading_satisfies_the_runner_parser(self):
        """The printed object is a reading `run_sensor` accepts as valid."""
        code, reading, err = self.sense("--rule", str(self.rule), "--bin", str(self.stub),
                                        out_text=fixture_text("R3-scan.jsonl"))
        self.assertEqual(code, 0, err)
        parsed = sensorlib._reading_from_stdout(json.dumps(reading), 0)
        self.assertTrue(parsed.valid, parsed.reason)
        self.assertEqual(parsed.value, 10)


class HelpLineTests(unittest.TestCase):
    def test_loop_help_line_and_usage_name_sense_ast_grep(self):
        """Adversarial where: the subcommand is wired in but its name is left
        off the `loop` line of `compass --help` or off the usage text that
        `compass loop` prints, so it is undiscoverable."""
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        shown = {}
        for label, args in (("help line", ["--help"]), ("usage", ["loop"])):
            proc = subprocess.run(
                [sys.executable, COMPASS, *args],
                capture_output=True, text=True, encoding="utf-8", env=env,
                timeout=120,
            )
            shown[label] = "".join((proc.stdout + proc.stderr).split())
        loop_help = "".join(maincli.build_parser().format_help().split())
        missing = [label for label, text in shown.items() if SUBCOMMAND not in text]
        if SUBCOMMAND not in loop_help:
            missing.append("parser help")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
