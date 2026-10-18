"""Tests for `compass retention`: report the effective `cleanupPeriodDays`
(local, then project, then user settings, the first that sets it) and, with
`--set N`, write it into the user's `settings.json` under `CLAUDE_CONFIG_DIR`.

Adversarial themes: the precedence chain (a file that exists but lacks the
key must fall through, not stop the search), the write path (every other key
and its order survives, only the user file is touched, a failed commit leaves
the original intact), and refusals (a value under 1, a settings file that does
not parse) that must change nothing and exit nonzero, never 2.

Assumed output contract: the first stdout line states the effective value,
either the number or the word "unset"; further lines may name the source layer.

Every test isolates CLAUDE_CONFIG_DIR, CLAUDE_PROJECT_DIR, HOME and
USERPROFILE in temp dirs, so no test reads or writes the real
~/.claude/settings.json.
"""

import importlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KEY = "cleanupPeriodDays"


def run_retention(args):
    """`(exit_code, stdout, stderr)`. Imports lazily so each test fails for
    its own reason. A `SystemExit` is captured as its code, so an argparse
    exit 2 shows up as 2 for the never-exit-2 assertions."""
    module = importlib.import_module("commands.retention")
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = module.run(list(args))
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    return (0 if code is None else code), out.getvalue(), err.getvalue()


def first_line(text):
    lines = text.strip().splitlines()
    return lines[0] if lines else ""


class RetentionCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.config = self.tmp / "cfg"
        self.project = self.tmp / "proj"
        for d in (self.home, self.config, self.project / ".compass", self.project / ".claude"):
            d.mkdir(parents=True)
        self._env("CLAUDE_CONFIG_DIR", str(self.config))
        self._env("CLAUDE_PROJECT_DIR", str(self.project))
        self._env("HOME", str(self.home))
        self._env("USERPROFILE", str(self.home))
        old_cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, old_cwd)

    def _env(self, name, value):
        old = os.environ.get(name)
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

        def restore():
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old

        self.addCleanup(restore)

    @property
    def user_file(self):
        return self.config / "settings.json"

    @property
    def project_file(self):
        return self.project / ".claude" / "settings.json"

    @property
    def local_file(self):
        return self.project / ".claude" / "settings.local.json"

    @staticmethod
    def write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        text = content if isinstance(content, str) else json.dumps(content, indent=2)
        path.write_bytes(text.encode("utf-8"))

    def snapshot(self):
        return {
            str(p.relative_to(self.tmp)): p.read_bytes()
            for p in sorted(self.tmp.rglob("*")) if p.is_file()
        }


class ReportTests(RetentionCase):
    def test_report_states_the_effective_value(self):
        """Adversarial where: the reported value must be the one in the user
        settings, with 30 (the setting's own small boundary) distinct from
        unset and from 3650. A reader that falls back to a default for an
        unset key, or treats a present 30 as unset, reports the wrong state;
        a user file holding only other keys must read as unset, not error."""
        rows = [
            ("no settings file anywhere", None, "unset"),
            ("user file without the key", {"model": "opus", "env": {"A": "1"}}, "unset"),
            ("exactly 30", {KEY: 30}, "30"),
            ("exactly 1", {KEY: 1}, "1"),
            ("3650", {KEY: 3650}, "3650"),
        ]
        for name, content, expected in rows:
            with self.subTest(name=name):
                if self.user_file.exists():
                    self.user_file.unlink()
                if content is not None:
                    self.write(self.user_file, content)
                code, out, _err = run_retention([])
                self.assertEqual(code, 0)
                line = first_line(out).lower()
                if expected == "unset":
                    self.assertIn("unset", line)
                else:
                    self.assertRegex(line, r"(?<!\d)" + expected + r"(?!\d)")
                    self.assertNotIn("unset", line)

    def test_project_and_local_settings_outrank_user_in_order(self):
        """Adversarial where: precedence is local, then project, then user,
        and a layer whose file exists but does not set the key must fall
        through to the next layer rather than end the search as 'unset'. Three
        distinct values (111, 222, 333) make a wrong layer visible; a
        first-line reader that returned the user value or the last-found
        value would show 333."""
        rows = [
            ("local beats project and user", {KEY: 111}, {KEY: 222}, {KEY: 333}, "111"),
            ("project beats user", None, {KEY: 222}, {KEY: 333}, "222"),
            ("local file without the key falls to project", {"model": "x"}, {KEY: 222}, {KEY: 333}, "222"),
            ("project file without the key falls to user", None, {"model": "x"}, {KEY: 333}, "333"),
            ("local and project without the key fall to user", {"a": 1}, {"b": 2}, {KEY: 333}, "333"),
            ("local alone with user and project unset", {KEY: 111}, None, None, "111"),
            ("project alone, user file missing", None, {KEY: 222}, None, "222"),
            ("small local value beats big user value", {KEY: 1}, None, {KEY: 3650}, "1"),
        ]
        for name, local, project, user, expected in rows:
            with self.subTest(name=name):
                for f in (self.local_file, self.project_file, self.user_file):
                    if f.exists():
                        f.unlink()
                for f, content in ((self.local_file, local), (self.project_file, project),
                                   (self.user_file, user)):
                    if content is not None:
                        self.write(f, content)
                code, out, _err = run_retention([])
                self.assertEqual(code, 0)
                line = first_line(out)
                self.assertRegex(line, r"(?<!\d)" + expected + r"(?!\d)")
                for wrong in {"111", "222", "333"} - {expected}:
                    self.assertNotRegex(line, r"(?<!\d)" + wrong + r"(?!\d)")

    def test_project_root_found_from_vault_when_env_is_unset(self):
        """Adversarial where: with CLAUDE_PROJECT_DIR unset, the project root
        is the vault root's parent found by walking up from the working
        directory. A reader that looks for `.claude/settings.json` relative to
        the cwd instead of the project root misses the project setting when
        run from a subdirectory."""
        self._env("CLAUDE_PROJECT_DIR", None)
        sub = self.project / "deep" / "er"
        sub.mkdir(parents=True)
        os.chdir(sub)
        self.write(self.project_file, {KEY: 222})
        self.write(self.user_file, {KEY: 333})
        code, out, _err = run_retention([])
        self.assertEqual(code, 0)
        self.assertRegex(first_line(out), r"(?<!\d)222(?!\d)")

    def test_default_config_dir_is_dot_claude_under_home(self):
        """Adversarial where: with CLAUDE_CONFIG_DIR unset the user settings
        live at ~/.claude/settings.json, for both reading and writing. A
        reader that requires the env var, or a writer that creates a `.claude`
        beside the project, would miss the file."""
        self._env("CLAUDE_CONFIG_DIR", None)
        default_file = self.home / ".claude" / "settings.json"
        self.write(default_file, {KEY: 555, "model": "m"})
        code, out, _err = run_retention([])
        self.assertEqual(code, 0)
        self.assertRegex(first_line(out), r"(?<!\d)555(?!\d)")
        code, _out, _err = run_retention(["--set", "777"])
        self.assertEqual(code, 0)
        data = json.loads(default_file.read_text(encoding="utf-8"))
        self.assertEqual(data, {KEY: 777, "model": "m"})
        self.assertFalse(self.user_file.exists())

    def test_report_writes_nothing(self):
        """Adversarial where: the report path must be read-only. Creating an
        empty settings.json or the config dir while reporting 'unset' would
        silently materialize a user file the human never asked for."""
        shutil.rmtree(self.config)
        self.write(self.project_file, {"model": "x"})
        before = self.snapshot()
        code, _out, _err = run_retention([])
        self.assertEqual(code, 0)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.config.exists())


class SetTests(RetentionCase):
    def test_set_adds_key_and_keeps_every_other_key_in_order(self):
        """Adversarial where: the rewrite must keep every other key, nested
        values, non-ASCII text, and key order, with the new key appended and
        stored as an integer. A writer that rebuilds the file from only the
        parsed fields, sorts keys, or stringifies the number would reorder or
        corrupt the human's settings."""
        original = {
            "zeta": [1, 2, {"deep": True}],
            "alpha": {"nested": {"x": None}, "hooks": ["a", "b"]},
            "model": "claude-ünï-☃",
            "mid": 0,
        }
        self.write(self.user_file, original)
        code, _out, _err = run_retention(["--set", "3650"])
        self.assertEqual(code, 0)
        data = json.loads(self.user_file.read_text(encoding="utf-8"))
        self.assertEqual(list(data), ["zeta", "alpha", "model", "mid", KEY])
        self.assertEqual({k: v for k, v in data.items() if k != KEY}, original)
        self.assertIs(type(data[KEY]), int)
        self.assertEqual(data[KEY], 3650)

    def test_set_replaces_existing_value_and_keeps_other_keys(self):
        """Adversarial where: when the key is already present, the new value
        replaces it exactly once (no duplicate key, old value gone) and the
        remaining keys keep their order. A writer that appends without
        removing leaves 30 as the value a parser keeps for a duplicate."""
        self.write(self.user_file, {"first": 1, KEY: 30, "last": 2})
        code, _out, _err = run_retention(["--set", "3650"])
        self.assertEqual(code, 0)
        text = self.user_file.read_text(encoding="utf-8")
        self.assertEqual(text.count(KEY), 1)
        data = json.loads(text)
        self.assertEqual(data[KEY], 3650)
        self.assertEqual([k for k in data if k != KEY], ["first", "last"])
        self.assertEqual((data["first"], data["last"]), (1, 2))

    def test_set_creates_missing_file_and_missing_directory(self):
        """Adversarial where: a fresh machine has no settings.json and may not
        have the config dir. The write must create both and produce a file
        holding exactly the one key. A writer that opens the existing file
        first, or the temp file in a directory that is not there, fails."""
        rows = [
            ("config dir exists, file missing", self.config),
            ("config dir missing too", self.tmp / "fresh" / "nested" / "cfg"),
        ]
        for name, config_dir in rows:
            with self.subTest(name=name):
                self._env("CLAUDE_CONFIG_DIR", str(config_dir))
                target = config_dir / "settings.json"
                self.assertFalse(target.exists())
                code, _out, _err = run_retention(["--set", "3650"])
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {KEY: 3650})

    def test_set_accepts_the_lower_boundary_of_one(self):
        """Adversarial where: 1 is the smallest accepted value. A refusal
        written as `<= 1` instead of `< 1` rejects the boundary itself."""
        code, _out, _err = run_retention(["--set", "1"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.user_file.read_text(encoding="utf-8")), {KEY: 1})

    def test_set_then_report_round_trips_to_the_user_layer(self):
        """Adversarial where: the written value must be the one the report
        reads back (round-trip), e.g. 4321 differing from the 30 and 3650 the
        suite uses elsewhere so a fallback to a default cannot pass."""
        code, _out, _err = run_retention(["--set", "4321"])
        self.assertEqual(code, 0)
        code, out, _err = run_retention([])
        self.assertEqual(code, 0)
        self.assertRegex(first_line(out), r"(?<!\d)4321(?!\d)")

    def test_set_touches_only_the_user_file(self):
        """Adversarial where: `--set` writes the user's settings.json even
        when a project or local setting currently outranks it, and leaves
        those project files byte-identical. A writer that updates the
        effective layer, or the project file, edits the repository's settings
        instead of the user's."""
        self.write(self.project_file, {KEY: 7, "model": "p"})
        self.write(self.local_file, {KEY: 9})
        self.write(self.user_file, {"model": "u"})
        project_bytes = self.project_file.read_bytes()
        local_bytes = self.local_file.read_bytes()
        code, _out, _err = run_retention(["--set", "3650"])
        self.assertEqual(code, 0)
        self.assertEqual(self.project_file.read_bytes(), project_bytes)
        self.assertEqual(self.local_file.read_bytes(), local_bytes)
        self.assertEqual(json.loads(self.user_file.read_text(encoding="utf-8")),
                         {"model": "u", KEY: 3650})

    def test_set_leaves_no_temp_file_behind(self):
        """Adversarial where: writing through a temp file and a rename must
        leave the config dir holding only settings.json after success. A
        leaked `.tmp` sibling accumulates in the user's ~/.claude."""
        self.write(self.user_file, {"model": "u"})
        code, _out, _err = run_retention(["--set", "3650"])
        self.assertEqual(code, 0)
        self.assertEqual(sorted(p.name for p in self.config.iterdir()), ["settings.json"])

    def test_failed_commit_leaves_original_untouched(self):
        """Adversarial where: the write goes through a temp file and a rename,
        so when the rename fails the original file keeps its exact bytes and
        the command does not report success. A writer that truncates and
        rewrites settings.json in place has already lost the file when the
        failure comes."""
        self.write(self.user_file, {"model": "u", "keep": [1, 2, 3]})
        original = self.user_file.read_bytes()
        boom = OSError("simulated rename failure")
        code = None
        with mock.patch("os.replace", side_effect=boom), mock.patch("os.rename", side_effect=boom):
            try:
                code, _out, _err = run_retention(["--set", "3650"])
            except OSError:
                code = 1
        self.assertNotEqual(code, 0)
        self.assertNotEqual(code, 2)
        self.assertEqual(self.user_file.read_bytes(), original)


class RefusalTests(RetentionCase):
    def assert_refused(self, args, before, message_context):
        code, out, err = run_retention(args)
        self.assertNotEqual(code, 0, message_context)
        self.assertNotEqual(code, 2, message_context)
        self.assertTrue((out + err).strip(), f"no message printed: {message_context}")
        self.assertEqual(self.snapshot(), before, f"files changed: {message_context}")

    def test_set_refuses_values_under_one_and_non_integers(self):
        """Adversarial where: 0 and negatives would tell Claude Code to
        delete every session at once; each must be refused with a message,
        exit nonzero (never 2), and leave an existing file and a missing file
        unchanged. A non-numeric or fractional value, or `--set` with no
        value, must be refused the same way instead of raising or exiting 2
        through the argument parser."""
        rows = [
            ("zero", ["--set", "0"]),
            ("minus one", ["--set", "-1"]),
            ("large negative", ["--set", "-3650"]),
            ("non-numeric", ["--set", "abc"]),
            ("fraction", ["--set", "1.5"]),
            ("empty value", ["--set", ""]),
            ("no value", ["--set"]),
        ]
        for name, args in rows:
            for state in ("existing file", "missing file"):
                with self.subTest(name=f"{name} / {state}"):
                    if self.user_file.exists():
                        self.user_file.unlink()
                    if state == "existing file":
                        self.write(self.user_file, {"model": "u", KEY: 30})
                    self.assert_refused(args, self.snapshot(), f"{name} / {state}")
                    if state == "missing file":
                        self.assertFalse(self.user_file.exists())

    def test_set_refuses_a_settings_file_that_does_not_parse(self):
        """Adversarial where: a settings file that is not a JSON object must
        be left alone, never overwritten with just the new key (which would
        destroy the human's other settings). The rows are asymmetric: broken
        from the start, truncated mid-value, a valid object followed by
        trailing junk, and valid JSON that is an array and so cannot take a
        key."""
        rows = [
            ("not json", "{not valid json"),
            ("truncated", '{"model": "u", "env": {"A": '),
            ("object then trailing junk", '{"model": "u"} trailing'),
            ("array instead of object", '[1, 2, 3]'),
            ("bare string", '"just a string"'),
        ]
        for name, content in rows:
            with self.subTest(name=name):
                self.write(self.user_file, content)
                self.assert_refused(["--set", "3650"], self.snapshot(), name)


class PostBuildReadTests(RetentionCase):
    def test_report_reads_settings_written_with_bom_crlf_and_tabs(self):
        """Adversarial where: settings files saved by Windows editors carry a
        UTF-8 BOM and CRLF line endings. A reader that decodes as plain
        `utf-8` rejects the BOM as invalid JSON and reports `unset` (or a
        skip) for a file that does set the key."""
        raw = b'\xef\xbb\xbf{\r\n\t"model": "\xc3\xa9",\r\n\t"cleanupPeriodDays": 4321\r\n}\r\n'
        rows = [
            ("user file with BOM and CRLF", self.user_file),
            ("project file with BOM and CRLF", self.project_file),
        ]
        for name, path in rows:
            with self.subTest(name=name):
                for f in (self.user_file, self.project_file):
                    if f.exists():
                        f.unlink()
                path.write_bytes(raw)
                code, out, _err = run_retention([])
                self.assertEqual(code, 0)
                self.assertRegex(first_line(out), r"(?<!\d)4321(?!\d)")
                self.assertNotIn("skipped", out)

    def test_report_ignores_values_that_are_not_integers(self):
        """Adversarial where: `cleanupPeriodDays` holding a string, a bool, a
        float or null is not a day count. A reader using `isinstance(v, int)`
        alone reports `True` as 1 day; one that echoes the raw value prints
        `"3650"` or `None` as the effective setting. The layer must fall
        through to the next one (here the user's 333) with exit 0."""
        rows = [
            ("string", '"3650"'),
            ("bool true", "true"),
            ("bool false", "false"),
            ("float", "3650.5"),
            ("null", "null"),
            ("list", "[30]"),
        ]
        self.write(self.user_file, {KEY: 333})
        for name, value in rows:
            with self.subTest(name=name):
                self.write(self.local_file, '{"%s": %s}' % (KEY, value))
                code, out, _err = run_retention([])
                self.assertEqual(code, 0)
                self.assertRegex(first_line(out), r"(?<!\d)333(?!\d)")

    def test_non_integer_only_value_reports_unset(self):
        """Adversarial where: when the only value present is a bool or a
        string, the report must say `unset`, never `True`/`1`; a bool is an
        int subclass in Python, so the wrong check turns `true` into a 1-day
        setting."""
        for name, value in (("true", "true"), ("string", '"30"')):
            with self.subTest(name=name):
                self.write(self.user_file, '{"%s": %s}' % (KEY, value))
                code, out, _err = run_retention([])
                self.assertEqual(code, 0)
                self.assertIn("unset", first_line(out).lower())

    def test_malformed_layer_does_not_hide_a_valid_layer(self):
        """Adversarial where: one broken settings file among three layers
        (asymmetric malformation) must not abort the report: the valid layer
        is still reported, the exit code is 0, and the broken file is named.
        A reader that raises, or that treats the broken file as 'unset' and
        stops, loses the user's real setting."""
        broken = {
            "local is not JSON": (self.local_file, "{oops"),
            "project is an array": (self.project_file, "[1]"),
            "local is empty": (self.local_file, ""),
            "project is truncated": (self.project_file, '{"cleanupPeriodDays": '),
        }
        self.write(self.user_file, {KEY: 4321})
        for name, (path, content) in broken.items():
            with self.subTest(name=name):
                for f in (self.local_file, self.project_file):
                    if f.exists():
                        f.unlink()
                self.write(path, content)
                code, out, _err = run_retention([])
                self.assertEqual(code, 0)
                self.assertRegex(first_line(out), r"(?<!\d)4321(?!\d)")
                self.assertIn(path.name, out)

    def test_directory_at_settings_path_or_missing_project_dir_falls_through(self):
        """Adversarial where: a settings path that is a directory, or a
        CLAUDE_PROJECT_DIR that does not exist, are odd but not errors. The
        report must still exit 0 and fall to the user layer instead of
        raising IsADirectoryError / FileNotFoundError."""
        self.write(self.user_file, {KEY: 4321})
        self.local_file.mkdir()
        code, out, _err = run_retention([])
        self.assertEqual(code, 0)
        self.assertRegex(first_line(out), r"(?<!\d)4321(?!\d)")
        self._env("CLAUDE_PROJECT_DIR", str(self.tmp / "no" / "such" / "dir"))
        code, out, _err = run_retention([])
        self.assertEqual(code, 0)
        self.assertRegex(first_line(out), r"(?<!\d)4321(?!\d)")


class PostBuildSetTests(RetentionCase):
    def test_set_rewrites_a_bom_crlf_tab_indented_file_without_loss(self):
        """Adversarial where: a settings file with a BOM, CRLF endings, tab
        indentation and non-BMP text (an emoji) must survive `--set` with
        every key, value and key order intact, no BOM re-emitted inside the
        JSON, and the emoji kept as text. A writer that reads as plain utf-8
        refuses the file; one that escapes with ensure_ascii rewrites the
        user's text as \\u escapes."""
        raw = (b'\xef\xbb\xbf{\r\n\t"zz": "\xf0\x9f\x98\x80 caf\xc3\xa9",\r\n'
               b'\t"aa": {"k": [1, 2]},\r\n\t"cleanupPeriodDays": 30\r\n}\r\n')
        self.user_file.write_bytes(raw)
        code, _out, err = run_retention(["--set", "3650"])
        self.assertEqual(code, 0, err)
        text = self.user_file.read_bytes().decode("utf-8")
        self.assertFalse(text.startswith("﻿"))
        data = json.loads(text)
        self.assertEqual(list(data), ["zz", "aa", KEY])
        self.assertEqual(data["zz"], "\U0001F600 café")
        self.assertEqual(data["aa"], {"k": [1, 2]})
        self.assertEqual(data[KEY], 3650)
        self.assertIn("\U0001F600", text)
        self.assertIn('\n\t"zz"', text)

    def test_set_replaces_an_existing_non_integer_value_in_place(self):
        """Adversarial where: a pre-existing `cleanupPeriodDays` of a string,
        bool, null, zero or negative is replaced by the integer, once, at the
        key's original position. A writer that only appends when the existing
        value is not an int leaves two keys or moves the key to the end."""
        for name, value in (("string", '"30"'), ("bool", "true"), ("null", "null"),
                            ("zero", "0"), ("negative", "-5")):
            with self.subTest(name=name):
                self.user_file.write_text(
                    '{"first": 1, "%s": %s, "last": 2}' % (KEY, value), encoding="utf-8")
                code, _out, err = run_retention(["--set", "3650"])
                self.assertEqual(code, 0, err)
                text = self.user_file.read_text(encoding="utf-8")
                self.assertEqual(text.count(KEY), 1)
                data = json.loads(text)
                self.assertEqual(list(data), ["first", KEY, "last"])
                self.assertIs(type(data[KEY]), int)
                self.assertEqual(data[KEY], 3650)

    def test_set_ignores_a_malformed_project_file_and_notes_a_winning_layer(self):
        """Adversarial where: the post-write note about a higher-priority
        layer scans every layer. A broken project file must not turn a
        successful write into a failure or traceback, and a valid local
        value that outranks the user file is named in the output."""
        self.write(self.project_file, "{oops")
        code, _out, err = run_retention(["--set", "3650"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(self.user_file.read_text(encoding="utf-8")), {KEY: 3650})
        self.write(self.local_file, {KEY: 9})
        code, out, err = run_retention(["--set", "3651"])
        self.assertEqual(code, 0, err)
        self.assertIn("local", out)

    def test_set_argument_shapes(self):
        """Adversarial where: the argument grammar is `--set N` or `--set=N`
        and nothing else. Extra positional args, an unknown flag, `--set=`
        with no value, and a value with whitespace, a plus sign, or non-ASCII
        digits must be refused with exit 1 and no write; `--set=7` must write
        7. A parser that ignores trailing args, or accepts `+7`/` 7` via
        int(), writes on malformed input."""
        refused = [
            ("extra positional", ["--set", "7", "extra"]),
            ("unknown flag", ["--bogus"]),
            ("bare positional", ["7"]),
            ("equals with no value", ["--set="]),
            ("leading plus", ["--set", "+7"]),
            ("leading space", ["--set", " 7"]),
            ("trailing newline", ["--set", "7\n"]),
            ("hex", ["--set", "0x10"]),
            ("underscore", ["--set", "1_0"]),
            ("fullwidth digit", ["--set", "７"]),
        ]
        for name, args in refused:
            with self.subTest(name=name):
                before = self.snapshot()
                code, out, err = run_retention(args)
                self.assertEqual(code, 1, (out, err))
                self.assertEqual(self.snapshot(), before)
        code, _out, err = run_retention(["--set=7"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(self.user_file.read_text(encoding="utf-8")), {KEY: 7})

    def test_set_refuses_an_absurdly_long_number_without_a_traceback(self):
        """Adversarial where: a digit string past Python's 4300-digit int
        conversion limit makes `int()` raise ValueError. The command promises
        exit 1 with a message on any refusal, so the error must be a refusal,
        not an uncaught exception, and nothing may be written."""
        before = self.snapshot()
        code, out, err = run_retention(["--set", "9" * 5000])
        self.assertEqual(code, 1)
        self.assertTrue((out + err).strip())
        self.assertEqual(self.snapshot(), before)

    def test_failed_write_leaves_no_temp_file_behind(self):
        """Adversarial where: when the commit cannot replace a read-only
        target, the command must exit 1 with the original bytes intact, and
        the temp file written beside it must be gone. A cleanup that cannot
        delete the temp because it inherited the read-only mode leaks a
        `.settings-*.tmp` into the user's ~/.claude on every attempt."""
        import stat

        def restore_mode(path):
            if path.exists() and path.is_file():
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD)

        self.user_file.write_text('{"model": "u"}', encoding="utf-8")
        os.chmod(self.user_file, stat.S_IREAD)
        self.addCleanup(restore_mode, self.user_file)
        self.addCleanup(
            lambda: [restore_mode(p) for p in self.config.iterdir()])
        code, _out, _err = run_retention(["--set", "3650"])
        self.assertIn(code, (0, 1))
        leaked = [p.name for p in self.config.iterdir() if p.name != "settings.json"]
        self.assertEqual(leaked, [])
        if code == 1:
            self.assertEqual(self.user_file.read_text(encoding="utf-8"), '{"model": "u"}')

    def test_set_with_a_directory_at_the_target_path_fails_cleanly(self):
        """Adversarial where: `settings.json` being a directory is a write
        failure, not a crash: exit 1 with a message and no temp file leaked."""
        self.user_file.mkdir()
        code, out, err = run_retention(["--set", "3650"])
        self.assertEqual(code, 1)
        self.assertTrue((out + err).strip())
        self.assertEqual([p.name for p in self.config.iterdir()], ["settings.json"])
        self.assertTrue(self.user_file.is_dir())


if __name__ == "__main__":
    unittest.main()


class LeadingZeroTests(RetentionCase):
    def test_leading_zeros_do_not_count_toward_the_digit_limit(self):
        """Adversarial where: `0000000005` is the integer 5 and must be
        accepted, while an all-zero string is still under 1 and refused, and
        a long run of zeros before a value past the limit is still refused.
        A cap on raw string length refuses the padded 5."""
        code, _out, err = run_retention(["--set", "0000000005"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(self.user_file.read_text(encoding="utf-8")), {KEY: 5})
        for value in ("0000000000000", "0" * 5000, "0" * 20 + "9" * 12):
            with self.subTest(value=value[:30]):
                before = self.snapshot()
                code, out, err = run_retention(["--set", value])
                self.assertEqual(code, 1)
                self.assertTrue((out + err).strip())
                self.assertEqual(self.snapshot(), before)
