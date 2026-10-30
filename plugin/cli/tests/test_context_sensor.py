"""Tests for `compass loop sense-context`: the sensor that reads how much
context an install of `plugin/` adds to every session.

Public contract these tests pin (`compass loop sense-context [--plugin <dir>]`):

    stdout is one JSON object {"valid": bool, "value": number, "items": [str]}
    and the exit code is 0 on every path, so the loop runner judges validity.

    Sources: each file under `templates/rules/` whole, and the frontmatter
    fields `name`, `description` and `when_to_use` of each `skills/*/SKILL.md`
    and each `templates/agents/*.md`. The frontmatter keys `allowed-tools` and
    `version`, and a skill's body, are not sources.

    value: UTF-8 bytes of a source divided by 4, rounded up per source,
    summed over the sources.

    items: one source's plugin-relative path with forward slashes, each source
    once. A shrunk source keeps its identity; a new source is a new item.

    A missing plugin directory or an unreadable source is `valid: false` with
    a non-empty `reason`.

Scratch plugin trees hold only the sources a test names, so an exact value is
asserted only where nothing else in the tree contributes. The hook-injected
text and the setup skill's CLAUDE.md proposal are found in the real `plugin/`
tree and are not asserted here.

Adversarial themes: rounding applied to the sum instead of to each source,
characters counted in place of bytes, a body or a version line leaking into the
count, a path built with the platform separator, a shrunk file losing its
identity, and a failure that exits non-zero or prints no JSON.
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

COMPASS = os.path.join(CLI_DIR, "compass")
REAL_PLUGIN = Path(CLI_DIR).parent
SUBCOMMAND = "sense-context"


def frontmatter(fields, body):
    lines = ["---"]
    for key, value in fields.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body


SKILL_FIELDS = {
    "name": "alpha",
    "description": "a" * 40,
    "version": "1.0.0",
    "allowed-tools": "[Read, Write]",
    "when_to_use": "b" * 40,
}

AGENT_FIELDS = {
    "name": "beta",
    "description": "c" * 40,
    "when_to_use": "d" * 40,
}


class ContextSensorCase(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.tmp = tmp
        self.project = tmp / "project"
        self.project.mkdir()
        self.plugin = tmp / "plugin"
        self.plugin.mkdir()

    def write_rules(self, name, data):
        path = self.plugin / "templates" / "rules" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    def write_skill(self, name="alpha", fields=None, body="body\n"):
        merged = dict(SKILL_FIELDS, name=name)
        merged.update(fields or {})
        path = self.plugin / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(frontmatter(merged, body), encoding="utf-8", newline="\n")
        return path

    def write_agent(self, name="beta", fields=None, body="body\n"):
        merged = dict(AGENT_FIELDS, name=name)
        merged.update(fields or {})
        path = self.plugin / "templates" / "agents" / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(frontmatter(merged, body), encoding="utf-8", newline="\n")
        return path

    def sense(self, *args):
        """Run `python compass loop sense-context <args>` as a real process.
        Returns (exit code, parsed stdout, stderr)."""
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.project)
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [sys.executable, COMPASS, "loop", SUBCOMMAND, *args],
            capture_output=True, text=True, encoding="utf-8", env=env,
            cwd=str(self.project), timeout=120,
        )
        try:
            reading = json.loads(proc.stdout)
        except ValueError:
            reading = None
        return proc.returncode, reading, proc.stderr

    def read_plugin(self, plugin=None):
        code, reading, err = self.sense("--plugin", str(plugin or self.plugin))
        self.assertEqual(code, 0, f"exit {code}: {err}")
        self.assertIsInstance(reading, dict, "stdout is not one JSON object")
        return reading

    def value_of(self):
        reading = self.read_plugin()
        self.assertTrue(reading["valid"], reading)
        return reading["value"]

    def items_of(self):
        reading = self.read_plugin()
        self.assertTrue(reading["valid"], reading)
        return reading["items"]


class ValueTests(ContextSensorCase):
    def test_rules_file_bytes_divide_by_four_rounding_up(self):
        """Adversarial where: the divisor or the rounding is off by one at the
        quarter boundary: 399 bytes is 100 tokens, 400 is 100, 401 is 101, a
        single byte is 1 and an empty file is 0."""
        for size, expected in [(0, 0), (1, 1), (3, 1), (4, 1), (5, 2),
                               (399, 100), (400, 100), (401, 101)]:
            with self.subTest(size=size):
                self.write_rules("only.md", b"a" * size)
                self.assertEqual(self.value_of(), expected)

    def test_rounding_applies_per_source_before_summing(self):
        """Adversarial where: the bytes of all sources are summed and divided
        once, so two 1-byte files read 1 instead of 2, and 3 + 5 bytes read 2
        instead of 1 + 2 = 3."""
        for sizes, expected in [((1, 1), 2), ((3, 5), 3), ((400, 4), 101)]:
            with self.subTest(sizes=sizes):
                shutil.rmtree(self.plugin / "templates", ignore_errors=True)
                for index, size in enumerate(sizes):
                    self.write_rules(f"rule{index}.md", b"a" * size)
                self.assertEqual(self.value_of(), expected)

    def test_non_ascii_text_counts_bytes_not_characters(self):
        """Adversarial where: len(text) is used instead of the UTF-8 byte
        length, so 100 two-byte characters read 25 instead of 50 and 100
        three-byte characters read 25 instead of 75."""
        for char, count, expected in [("é", 100, 50), ("€", 100, 75),
                                      ("\U0001f600", 100, 100)]:
            with self.subTest(char=char):
                self.write_rules("only.md", char * count)
                self.assertEqual(self.value_of(), expected)

    def test_crlf_rules_file_counts_its_raw_bytes(self):
        """Adversarial where: the file is read in text mode, so each CRLF
        collapses to LF and 200 CRLF pairs (400 bytes) read 50 instead of 100."""
        self.write_rules("only.md", b"x\r\n" * 100 + b"y" * 100)
        self.assertEqual(self.value_of(), 100)


class FrontmatterFieldTests(ContextSensorCase):
    def test_skill_body_does_not_count_and_description_does(self):
        """Adversarial where: the whole SKILL.md is read, so a 4000-byte body
        moves the value, or the description is dropped so growing it by 400
        bytes moves nothing."""
        self.write_skill()
        base = self.value_of()
        self.write_skill(body="body text " * 400)
        self.assertEqual(self.value_of(), base, "body text changed the value")
        self.write_skill(fields={"description": "a" * 440})
        self.assertEqual(self.value_of(), base + 100)

    def test_each_counted_field_moves_the_value_in_skills_and_agents(self):
        """Adversarial where: one of name, description or when_to_use is left
        out of the sum, in skills or in agents, so growing it by 400 bytes
        changes nothing."""
        for kind, writer, base_fields in [("skill", self.write_skill, SKILL_FIELDS),
                                          ("agent", self.write_agent, AGENT_FIELDS)]:
            for field in ("name", "description", "when_to_use"):
                with self.subTest(kind=kind, field=field):
                    writer()
                    base = self.value_of()
                    grown = base_fields[field] + "z" * 400
                    writer(fields={field: grown})
                    self.assertEqual(self.value_of(), base + 100)
                    shutil.rmtree(self.plugin, ignore_errors=True)
                    self.plugin.mkdir()

    def test_allowed_tools_and_version_do_not_count(self):
        """Adversarial where: every frontmatter line is summed, so a long
        `allowed-tools` list or a `version` bump moves the value of a skill."""
        self.write_skill()
        base = self.value_of()
        self.write_skill(fields={"allowed-tools": "[" + ", ".join(["Read"] * 200) + "]"})
        self.assertEqual(self.value_of(), base, "allowed-tools changed the value")
        self.write_skill(fields={"version": "9" * 400})
        self.assertEqual(self.value_of(), base, "version changed the value")

    def test_sources_outside_the_named_set_do_not_count(self):
        """Adversarial where: a glob that is too wide counts a rules-like file
        outside `templates/rules/`, a non-markdown file inside it, or a
        sibling file beside a skill's SKILL.md."""
        self.write_rules("only.md", b"a" * 8)
        self.write_skill()
        base = self.value_of()
        (self.plugin / "templates" / "other").mkdir()
        (self.plugin / "templates" / "other" / "big.md").write_bytes(b"a" * 4000)
        (self.plugin / "templates" / "rules" / "notes.txt").write_bytes(b"a" * 4000)
        (self.plugin / "skills" / "alpha" / "reference.md").write_bytes(b"a" * 4000)
        self.assertEqual(self.value_of(), base)


class ItemTests(ContextSensorCase):
    def test_new_rules_file_is_a_new_item_and_a_removed_one_is_not(self):
        """Adversarial where: an added always-loaded file leaves the item set
        unchanged so the judge cannot see it as harmful, or a deleted file
        lingers in the items."""
        self.write_rules("keep.md", b"a" * 40)
        before = set(self.items_of())
        added = self.write_rules("extra.md", b"a" * 40)
        after_add = set(self.items_of())
        self.assertEqual(after_add - before, {"templates/rules/extra.md"})
        self.assertEqual(before - after_add, set())
        added.unlink()
        self.assertEqual(set(self.items_of()), before)

    def test_shrunk_source_keeps_its_identity(self):
        """Adversarial where: the item embeds the size or the value, so a
        source that shrinks from 400 to 8 bytes becomes a different item and
        reads as one removal plus one addition."""
        self.write_rules("keep.md", b"a" * 400)
        before = self.items_of()
        self.write_rules("keep.md", b"a" * 8)
        self.assertEqual(self.items_of(), before)

    def test_items_use_forward_slashes_and_plugin_relative_paths(self):
        """Adversarial where: the item is built with the platform separator or
        an absolute path, so a nested skill path carries a backslash on
        Windows."""
        self.write_rules("only.md", b"a" * 8)
        self.write_skill("alpha")
        self.write_agent("beta")
        items = self.items_of()
        self.assertEqual(
            sorted(items),
            ["skills/alpha/SKILL.md", "templates/agents/beta.md", "templates/rules/only.md"],
        )
        for item in items:
            self.assertNotIn("\\", item)

    def test_each_source_appears_once(self):
        """Adversarial where: a file matched by two source globs, or a skill's
        three counted fields, each add an item, so a source is listed more
        than once."""
        self.write_rules("only.md", b"a" * 8)
        self.write_skill("alpha")
        self.write_agent("beta")
        items = self.items_of()
        self.assertEqual(len(items), len(set(items)), items)


class InvalidReadingTests(ContextSensorCase):
    def assert_invalid_exit_zero(self, *args):
        code, reading, err = self.sense(*args)
        self.assertEqual(code, 0, f"exit {code}: {err}")
        self.assertIsInstance(reading, dict, "stdout is not one JSON object")
        self.assertIs(reading["valid"], False)
        self.assertIsInstance(reading.get("reason"), str)
        self.assertTrue(reading["reason"].strip(), "empty reason")

    def test_missing_or_non_directory_plugin_is_invalid_with_a_reason(self):
        """Adversarial where: a plugin path that does not exist, or names a
        regular file, reads as a valid zero (an empty install) or raises."""
        regular = self.tmp / "afile"
        regular.write_text("x", encoding="utf-8")
        for name, target in [("missing", self.tmp / "no-such-plugin"), ("regular file", regular)]:
            with self.subTest(case=name):
                self.assert_invalid_exit_zero("--plugin", str(target))

    def test_unreadable_source_is_invalid_even_beside_good_sources(self):
        """Adversarial where: one source that cannot be read is skipped and the
        remaining sources report a valid, understated total. The source is a
        directory named like a rules file, so no permission bits are needed."""
        self.write_rules("good.md", b"a" * 40)
        self.write_skill()
        (self.plugin / "templates" / "rules" / "broken.md").mkdir()
        self.assert_invalid_exit_zero("--plugin", str(self.plugin))


class ExitCodeTests(ContextSensorCase):
    def test_exit_is_zero_and_stdout_is_a_reading_on_every_path(self):
        """Adversarial where: a bad argument, a missing value or an absent
        plugin exits non-zero or prints a usage text, so the loop runner sees
        a crashed sensor instead of an invalid reading."""
        self.write_rules("only.md", b"a" * 8)
        paths = [
            ("valid", ["--plugin", str(self.plugin)]),
            ("missing dir", ["--plugin", str(self.tmp / "absent")]),
            ("flag without value", ["--plugin"]),
            ("unknown flag", ["--no-such-flag"]),
        ]
        for name, args in paths:
            with self.subTest(case=name):
                code, reading, err = self.sense(*args)
                self.assertEqual(code, 0, f"exit {code}: {err}")
                self.assertIsInstance(reading, dict, "stdout is not one JSON object")
                self.assertTrue({"valid", "value", "items"} <= set(reading), reading)
                self.assertIsInstance(reading["valid"], bool)


class RealPluginTests(ContextSensorCase):
    def test_reading_of_this_repositorys_plugin_is_valid_and_nonzero(self):
        """Adversarial where: the real tree breaks an assumption the scratch
        trees share (a quoted value, a folded field, a file without
        frontmatter) so the reading is invalid, zero, or misses a source."""
        reading = self.read_plugin(REAL_PLUGIN)
        self.assertIs(reading["valid"], True, reading)
        self.assertGreater(reading["value"], 0)
        items = reading["items"]
        self.assertEqual(len(items), len(set(items)))
        for item in items:
            self.assertNotIn("\\", item)
        expected = {p.relative_to(REAL_PLUGIN).as_posix()
                    for pattern in ("templates/rules/*.md", "skills/*/SKILL.md",
                                    "templates/agents/*.md")
                    for p in REAL_PLUGIN.glob(pattern)}
        self.assertTrue(expected, "no sources found in the real plugin")
        self.assertLessEqual(expected, set(items), "a named source is missing")


class HelpLineTests(unittest.TestCase):
    def test_loop_help_line_and_usage_name_sense_context(self):
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
