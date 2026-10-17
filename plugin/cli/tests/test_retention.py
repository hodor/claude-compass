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


if __name__ == "__main__":
    unittest.main()
