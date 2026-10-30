"""Tests for the parts of the context sensor (`sensorlib.sense_context` and
`compass loop sense-context`) that exist because of how it is written: the
setup skill's CLAUDE.md proposal item, the frontmatter value forms the parser
yields, the error reasons it builds, the ordering of its items, and the
default plugin folder.

Estimates are `ceil(bytes / 4)` per source. Scratch trees hold only the sources
a test names, so every value is asserted exactly.

Adversarial themes: a regex that reaches past the setup skill's own section,
quotes and block scalars read as raw text, carriage returns inflating a
count, a failure reason that does not name the file, and an ordering that
depends on the creation order of the files.
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

import sensorlib  # noqa: E402

COMPASS = os.path.join(CLI_DIR, "compass")
SETUP = "skills/setup/SKILL.md"
CLAUDE_MD_ITEM = SETUP + "#claude-md-addition"


def ceil_quarter(byte_count):
    return -(-byte_count // 4)


class TreeCase(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.tmp = tmp
        self.plugin = tmp / "plugin"
        self.plugin.mkdir()

    def put(self, rel, data):
        path = self.plugin / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    def sense(self):
        return sensorlib.sense_context(self.plugin)


class ClaudeMdAdditionTests(TreeCase):
    def setup_text(self, block_body, newline="\n"):
        text = (
            "---\nname: setup\n---\n"
            "# Setup\n\n"
            "### 4. Propose CLAUDE.md addition\n\n"
            "Draft a short section:\n\n"
            "```markdown\n" + block_body + "```\n\n"
            "### 5. Report\n\nDone.\n"
        )
        return text.replace("\n", newline)

    def test_block_bytes_are_added_once_and_move_with_the_block(self):
        """Adversarial where: the proposal is left out of the value, counted
        by characters, counted with its fence lines, or counted twice, so the
        reading does not move by the block's exact quarter-byte estimate."""
        name_estimate = ceil_quarter(len("setup"))
        rows = [
            ("40 bytes", "x" * 39 + "\n", 40),
            ("41 bytes crosses a quarter", "x" * 40 + "\n", 41),
            ("multibyte counts bytes", "é" * 20 + "\n", 41),
        ]
        for name, body, byte_count in rows:
            with self.subTest(case=name):
                self.assertEqual(len(body.encode("utf-8")), byte_count)
                self.put(SETUP, self.setup_text(body))
                reading = self.sense()
                self.assertTrue(reading.valid, reading.reason)
                self.assertEqual(reading.value, name_estimate + ceil_quarter(byte_count))
                self.assertEqual(reading.items.count(CLAUDE_MD_ITEM), 1)
                self.assertEqual(reading.items.count(SETUP), 1)

    def test_crlf_setup_skill_reads_as_its_lf_form(self):
        """Adversarial where: a setup skill checked out with CRLF line endings
        counts one extra byte per line of the proposal and of the frontmatter,
        so the reading differs between platforms for the same content."""
        body = "line one\nline two\nline three\n"
        self.put(SETUP, self.setup_text(body))
        lf = self.sense()
        self.put(SETUP, self.setup_text(body, newline="\r\n"))
        crlf = self.sense()
        self.assertTrue(crlf.valid, crlf.reason)
        self.assertEqual((crlf.value, crlf.items), (lf.value, lf.items))

    def test_no_item_when_the_setup_skill_has_no_proposal(self):
        """Adversarial where: the item is emitted for any setup skill, or for a
        heading that only mentions the proposal, so the reading names a source
        that is not in the file."""
        rows = {
            "no heading": "---\nname: setup\n---\n```markdown\nstray\n```\n",
            "heading without a fence": (
                "---\nname: setup\n---\n### Propose CLAUDE.md addition\n\ntext only\n"
            ),
            "heading with an unclosed fence": (
                "---\nname: setup\n---\n### Propose CLAUDE.md addition\n"
                "```markdown\nnever closed\n"
            ),
            "mention in prose only": (
                "---\nname: setup\n---\nApprove the CLAUDE.md addition.\n"
                "```markdown\nstray\n```\n"
            ),
        }
        for name, text in rows.items():
            with self.subTest(case=name):
                self.put(SETUP, text)
                reading = self.sense()
                self.assertTrue(reading.valid, reading.reason)
                self.assertNotIn(CLAUDE_MD_ITEM, reading.items)
                self.assertEqual(reading.items, [SETUP])
                self.assertEqual(reading.value, ceil_quarter(len("setup")))

    def test_fence_of_a_later_section_is_not_the_proposal(self):
        """Adversarial where: the proposal heading has no fenced block of its
        own, so the match runs on into a later section's markdown fence and
        counts that section as the CLAUDE.md addition."""
        self.put(
            SETUP,
            "---\nname: setup\n---\n"
            "### 4. Propose CLAUDE.md addition\n\nNothing is proposed.\n\n"
            "### 5. Report\n\n```markdown\n## Next Steps\n1. Open the vault\n```\n",
        )
        reading = self.sense()
        self.assertTrue(reading.valid, reading.reason)
        self.assertNotIn(CLAUDE_MD_ITEM, reading.items)

    def test_other_skill_with_the_same_heading_has_no_item(self):
        """Adversarial where: any skill whose text holds the heading and a
        fence is credited with the proposal, not only the setup skill."""
        self.put(
            "skills/other/SKILL.md",
            "---\nname: other\n---\n### CLAUDE.md addition\n```markdown\nabcd\n```\n",
        )
        reading = self.sense()
        self.assertTrue(reading.valid, reading.reason)
        self.assertEqual(reading.items, ["skills/other/SKILL.md"])


class FrontmatterValueTests(TreeCase):
    def skill_value(self, frontmatter_lines, body="body\n", newline="\n"):
        text = "---\n" + "".join(line + "\n" for line in frontmatter_lines) + "---\n" + body
        self.put("skills/a/SKILL.md", text.replace("\n", newline))
        reading = self.sense()
        self.assertTrue(reading.valid, reading.reason)
        return reading.value

    def test_each_value_form_counts_the_text_the_parser_yields(self):
        """Adversarial where: quote characters, escape backslashes, block
        scalar indentation or line breaks, or CRLF endings are counted as part
        of the value, or a form is skipped, so the estimate drifts from the
        text the session shows."""
        # name is "ab" (2 bytes) in every row; expected is bytes of the other values.
        rows = [
            ("plain", ['description: abcdefghij'], 10),
            ("double quoted with escaped quotes", [r'description: "say \"hi\" now"'], 12),
            ("single quoted with doubled apostrophe", ["description: 'it''s fine'"], 9),
            ("folded block", ["description: >", "  aaaaa", "  bbbbb", "  ccccc"], 17),
            ("folded block with strip indicator", ["description: >-", "  aaaaa", "  bbbbb"], 11),
            ("literal block keeps line breaks", ["description: |", "  aaaaa", "  bbbbb", "  ccccc"], 17),
            ("multibyte is bytes", ["description: ééé"], 6),
            ("empty value", ["description:"], 0),
            ("when_to_use folded", ["when_to_use: >", "  aaaa", "  bbbb"], 9),
            ("both fields", ["description: abcd", "when_to_use: efgh"], 8),
        ]
        for name, lines, value_bytes in rows:
            with self.subTest(case=name):
                got = self.skill_value(["name: ab", *lines])
                self.assertEqual(got, ceil_quarter(2 + value_bytes))

    def test_crlf_frontmatter_counts_like_lf(self):
        """Adversarial where: a carriage return left on a value or on the
        lines of a block scalar adds bytes, so a CRLF checkout of a skill reads
        larger than the same skill with LF endings."""
        lines = ["name: ab", "description: >", "  aaaaa", "  bbbbb", "when_to_use: efgh"]
        lf = self.skill_value(lines)
        crlf = self.skill_value(lines, newline="\r\n")
        self.assertEqual(crlf, lf)
        self.assertEqual(lf, ceil_quarter(2 + 11 + 4))

    def test_description_in_the_body_is_not_a_source(self):
        """Adversarial where: a `description:` or `name:` line below the
        closing fence, or a `---` rule in the body, is read as frontmatter, so
        body text changes the reading."""
        base = self.skill_value(["name: ab", "description: abcd"])
        self.assertEqual(base, ceil_quarter(6))
        body = (
            "# Title\n\ndescription: " + "z" * 200 + "\n"
            "---\nwhen_to_use: " + "y" * 200 + "\n---\nname: " + "x" * 200 + "\n"
        )
        self.assertEqual(self.skill_value(["name: ab", "description: abcd"], body=body), base)

    def test_description_only_in_the_body_adds_nothing(self):
        """Adversarial where: a skill whose frontmatter lacks `description`
        borrows the first `description:` line of its body."""
        value = self.skill_value(["name: ab"], body="description: " + "z" * 200 + "\n")
        self.assertEqual(value, ceil_quarter(2))


class InvalidReasonTests(TreeCase):
    def test_a_source_without_valid_frontmatter_names_its_file(self):
        """Adversarial where: a skill or agent file without a frontmatter
        block reads as a source of zero bytes, or the reason names no file, so
        the loop cannot tell which source broke."""
        rows = [
            ("skill without frontmatter", "skills/bare/SKILL.md", "# Bare\n\nno fence\n"),
            ("skill with unterminated frontmatter", "skills/open/SKILL.md", "---\nname: open\n"),
            ("agent without frontmatter", "templates/agents/bare.md", "just text\n"),
            ("empty skill file", "skills/empty/SKILL.md", ""),
        ]
        for name, rel, text in rows:
            with self.subTest(case=name):
                self.put("templates/rules/good.md", "a" * 40)
                self.put("skills/good/SKILL.md", "---\nname: good\n---\n")
                self.put(rel, text)
                reading = self.sense()
                self.assertFalse(reading.valid)
                self.assertIn(rel, reading.reason)
                (self.plugin / rel).unlink()

    def test_undecodable_skill_is_invalid_and_names_its_file(self):
        """Adversarial where: a skill file that is not valid UTF-8 raises out
        of the sensor, or gives an invalid reading whose reason carries only
        the codec message and no file."""
        rel = "skills/latin/SKILL.md"
        self.put(rel, b"---\nname: caf\xe9\n---\nbody\n")
        reading = self.sense()
        self.assertFalse(reading.valid)
        self.assertIn(rel, reading.reason)

    def test_rules_file_that_is_not_utf8_still_counts_its_bytes(self):
        """Adversarial where: a rules file is decoded as text before it is
        measured, so bytes that are not UTF-8 make the whole reading invalid
        instead of counting the file's size."""
        self.put("templates/rules/odd.md", b"\xff\xfe" * 20)
        reading = self.sense()
        self.assertTrue(reading.valid, reading.reason)
        self.assertEqual(reading.value, 10)
        self.assertEqual(reading.items, ["templates/rules/odd.md"])


class DeterminismTests(TreeCase):
    def populate(self, order):
        files = {
            "templates/rules/zeta.md": "z" * 12,
            "templates/rules/Alpha.md": "a" * 12,
            "skills/mid/SKILL.md": "---\nname: mid\n---\n",
            "skills/Abc/SKILL.md": "---\nname: abc\n---\n",
            "templates/agents/zed.md": "---\nname: zed\n---\n",
            "templates/agents/ann.md": "---\nname: ann\n---\n",
        }
        for rel in order(sorted(files)):
            self.put(rel, files[rel])

    def fields(self, reading):
        return (reading.valid, reading.value, reading.items, reading.reason)

    def sources_of(self, reading):
        return [item for item in reading.items if "#" not in item]

    def test_reading_is_identical_across_runs_and_creation_order(self):
        """Adversarial where: items come out in directory-listing or
        creation order, so two runs, or two checkouts of one tree, produce
        different readings and the loop's baseline comparison flips."""
        self.populate(lambda names: names)
        first = self.sense()
        second = self.sense()
        self.assertEqual(self.fields(first), self.fields(second))
        self.assertEqual(self.sources_of(first), sorted(self.sources_of(first)))
        self.assertEqual(len(first.items), 6)

        shutil.rmtree(self.plugin)
        self.plugin.mkdir()
        self.populate(lambda names: list(reversed(names)))
        reversed_build = self.sense()
        self.assertEqual(self.fields(reversed_build), self.fields(first))

    def test_each_cli_run_prints_the_same_bytes(self):
        """Adversarial where: the JSON printed by the command varies between
        runs of one tree, through key order or item order."""
        self.populate(lambda names: names)
        outputs = []
        for _ in range(2):
            proc = subprocess.run(
                [sys.executable, COMPASS, "loop", "sense-context", "--plugin", str(self.plugin)],
                capture_output=True, text=True, encoding="utf-8", timeout=120,
                env=dict(os.environ, PYTHONIOENCODING="utf-8"),
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            outputs.append(proc.stdout)
        self.assertEqual(outputs[0], outputs[1])
        body = json.loads(outputs[0])
        self.assertEqual(body["items"], self.sources_of(sensorlib.sense_context(self.plugin)))


class DefaultPluginTests(TreeCase):
    def run_cli(self, project, cwd, *args):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        env["CLAUDE_PROJECT_DIR"] = str(project)
        proc = subprocess.run(
            [sys.executable, COMPASS, "loop", "sense-context", *args],
            capture_output=True, text=True, encoding="utf-8", env=env,
            cwd=str(cwd), timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_no_argument_reads_the_plugin_folder_of_the_project_root(self):
        """Adversarial where: the default folder is the working directory or
        the vault folder instead of `plugin/` beside `.compass/`, so the
        command reads the wrong tree whenever it is run from a subfolder."""
        project = self.tmp / "proj"
        (project / ".compass").mkdir(parents=True)
        (project / "plugin" / "templates" / "rules").mkdir(parents=True)
        (project / "plugin" / "templates" / "rules" / "r.md").write_bytes(b"a" * 36)
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        reading = self.run_cli(project, elsewhere)
        self.assertEqual(reading["valid"], True, reading)
        self.assertEqual(reading["value"], 9)
        self.assertEqual(reading["items"], ["templates/rules/r.md"])

    def test_project_without_a_plugin_folder_is_invalid(self):
        """Adversarial where: a project root with no `plugin/` folder reads as
        a valid zero, which a loop minimizing the value would call an
        improvement."""
        project = self.tmp / "proj"
        (project / ".compass").mkdir(parents=True)
        reading = self.run_cli(project, project)
        self.assertIs(reading["valid"], False)
        self.assertTrue(reading["reason"].strip())

    def test_extra_arguments_are_an_invalid_reading_naming_them(self):
        """Adversarial where: a second positional argument is ignored, so a
        misspelled command line reads the default folder as valid."""
        project = self.tmp / "proj"
        (project / ".compass").mkdir(parents=True)
        reading = self.run_cli(project, project, "--plugin", str(self.plugin), "stray")
        self.assertIs(reading["valid"], False)
        self.assertIn("stray", reading["reason"])


if __name__ == "__main__":
    unittest.main()
