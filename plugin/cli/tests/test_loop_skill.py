"""Tests for `plugin/skills/loop/SKILL.md`, the guided creation of a control
loop through steps 0 to 7.

Public contract these tests pin:

    Frontmatter `name: loop` and a non-empty `description`.

    Eight sections headed `## Step N: ...` for N = 0 to 7, in order, each
    holding a line that starts with `Done when:` (bold markers allowed).

    Every `compass loop <subcommand>` the skill names is a subcommand listed in
    `commands/loop.py`'s `USAGE`.

    The skill says "cap N allows N tool rounds" and that each iteration is a
    fresh session, and points to `loop_templates/loop.json` for the defaults
    instead of restating them: no numeric default of that template appears
    beside its key.

    The step 1 sensor section names `sense-ast-grep` and `/compass:research`;
    step 2 names `compass loop baseline` and `compass loop check`; step 5 names
    `compass loop schedule`; step 6 names `feedback.md` and `compass loop
    review`; step 7 names `wip_limit`, `daily_budget_usd` and
    `total_budget_usd`.

    The first `compass loop activate` comes after the standalone sensor run
    ("run the sensor command alone"), `compass loop baseline` and
    `compass loop run ... --dry-run`.

    Every paragraph that mentions a judge sensor calls it advisory and pairs it
    with a deterministic sensor.

Adversarial themes: a step missing its checkable criterion, a renamed or
invented subcommand, a template default copied into prose where it goes stale,
activation placed before the checks that should gate it, and a judge offered
as a sensor that can stop the loop on its own.
"""

import json
import os
import re
import sys
import unittest
from pathlib import Path

CLI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLI_DIR))

from commands import loop as loop_command  # noqa: E402

PLUGIN = CLI_DIR.parent
SKILL = PLUGIN / "skills" / "loop" / "SKILL.md"
LOOP_TEMPLATE = CLI_DIR / "loop_templates" / "loop.json"

STEP_HEADING = re.compile(r"^## Step (\d+)\b.*$", re.MULTILINE)
DONE_WHEN = re.compile(r"^\s*(?:[-*]\s+)?\**Done when:", re.MULTILINE)
LOOP_SUBCOMMAND = re.compile(r"\bcompass[ \t]+loop[ \t]+([a-z][a-z0-9-]*)")
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?!\w|\.\d)")


def read_skill():
    return SKILL.read_text(encoding="utf-8")


def frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip().strip('"')
    return {}


def step_sections(text):
    """Map step number -> section body, from each `## Step N` heading to the
    next level-2 heading."""
    sections = {}
    headings = list(re.finditer(r"^## .*$", text, re.MULTILINE))
    for index, heading in enumerate(headings):
        match = STEP_HEADING.match(heading.group(0))
        if not match:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        sections[int(match.group(1))] = text[heading.end():end]
    return sections


def usage_subcommands():
    return set(re.findall(r"compass loop ([a-z][a-z0-9-]*)", loop_command.USAGE))


class LoopSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read_skill()
        cls.steps = step_sections(cls.text)

    def test_frontmatter_names_loop_with_a_description(self):
        fields = frontmatter(self.text)
        self.assertEqual(fields.get("name"), "loop")
        self.assertTrue(fields.get("description"), "description is empty")

    def test_eight_steps_in_order_each_with_done_when(self):
        numbers = [int(m.group(1)) for m in STEP_HEADING.finditer(self.text)]
        self.assertEqual(numbers, list(range(8)))
        missing = [n for n, body in sorted(self.steps.items()) if not DONE_WHEN.search(body)]
        self.assertEqual(missing, [], "steps without a Done when: line")

    def test_every_loop_subcommand_named_is_in_usage(self):
        named = set(LOOP_SUBCOMMAND.findall(self.text))
        self.assertTrue(named, "the skill names no compass loop subcommand")
        unknown = sorted(named - usage_subcommands())
        self.assertEqual(unknown, [])

    def test_caps_wording_and_fresh_session(self):
        self.assertIn("cap N allows N tool rounds", self.text)
        self.assertRegex(self.text, r"(?i)fresh session")
        self.assertIn("loop_templates/loop.json", self.text)

    def test_no_template_default_beside_its_key(self):
        """Adversarial where: the prose restates `max_turns: 30` or a budget
        default, which goes stale the day the template changes."""
        template = json.loads(LOOP_TEMPLATE.read_text(encoding="utf-8"))
        offenders = []
        for key, default in template.items():
            if isinstance(default, bool) or not isinstance(default, (int, float)):
                continue
            for line in self.text.splitlines():
                for found in re.finditer(r"(?<![\w])" + re.escape(key) + r"(?![\w])", line):
                    window = line[max(0, found.start() - 15):found.end() + 30]
                    numbers = [float(n) for n in NUMBER.findall(window)]
                    if float(default) in numbers:
                        offenders.append(f"{key}={default}: {line.strip()}")
        self.assertEqual(offenders, [])

    def test_steps_name_their_commands_and_files(self):
        expected = {
            1: ("sense-ast-grep", "/compass:research"),
            2: ("compass loop baseline", "compass loop check"),
            5: ("compass loop schedule",),
            6: ("feedback.md", "compass loop review"),
            7: ("wip_limit", "daily_budget_usd", "total_budget_usd"),
        }
        missing = []
        for number, needles in expected.items():
            body = self.steps.get(number, "")
            missing.extend(f"step {number}: {n}" for n in needles if n not in body)
        self.assertEqual(missing, [])

    def test_activation_comes_after_the_standalone_checks(self):
        """Adversarial where: `activate` is reached before the sensor has been
        run alone, the baseline written and the dry run printed."""
        lower = self.text.lower()
        activate = self.text.find("compass loop activate")
        self.assertNotEqual(activate, -1, "the skill never activates the loop")
        alone = lower.find("run the sensor command alone")
        baseline = self.text.find("compass loop baseline")
        dry_run = re.search(r"compass loop run [^\n`]*--dry-run", self.text)
        self.assertNotEqual(alone, -1, "no standalone sensor run")
        self.assertNotEqual(baseline, -1, "no baseline")
        self.assertIsNotNone(dry_run, "no dry run")
        self.assertLess(alone, activate)
        self.assertLess(baseline, activate)
        self.assertLess(dry_run.start(), activate)

    def test_activate_warnings_count_as_unfinished_steps(self):
        after = self.text[self.text.find("compass loop activate"):]
        self.assertRegex(after, r"(?i)warning")

    def test_judge_is_advisory_and_paired_with_a_deterministic_sensor(self):
        """Adversarial where: a judge sensor is offered as the loop's sensor,
        which would let a plain-language reading stop the loop."""
        paragraphs = [p for p in re.split(r"\n\s*\n", self.text) if re.search(r"(?i)\bjudge\b", p)]
        self.assertTrue(paragraphs, "the skill never mentions a judge sensor")
        bad = [
            p.strip()[:80] for p in paragraphs
            if not re.search(r"(?i)advisory", p) or not re.search(r"(?i)deterministic", p)
        ]
        self.assertEqual(bad, [])

    def test_sensor_step_drafts_a_rule_and_shows_its_matches(self):
        body = self.steps.get(1, "")
        self.assertRegex(body, r"(?i)ast-grep")
        self.assertRegex(body, r"(?i)snippet")
        self.assertRegex(body, r"(?i)matches")


if __name__ == "__main__":
    unittest.main()
