"""The autopilot skill's research step runs through the research entry point,
and its plan-approval checkpoint carries the grading the entry point's gate
settled.

Guards three defects: step 2 spawning the `researcher` agent directly, which
skips the axis derivation, the axis gate and the grading disclosure; the
checkpoint block omitting the `grading:` field, so the human approves a plan
without seeing whether graded evidence shaped it; and the field spelled
differently from the research entry point's, so the gate's answer never
reaches the checkpoint by name.
"""

import os
import re
import unittest

PLUGIN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AUTOPILOT = os.path.join(PLUGIN, "skills", "autopilot", "SKILL.md")
RESEARCH = os.path.join(PLUGIN, "skills", "research", "SKILL.md")


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def section(text, heading):
    """The body under a `### <heading>` line, up to the next heading of
    level 3 or higher."""
    match = re.search(
        rf"^### {re.escape(heading)}\s*$(.*?)(?=^#{{1,3}} )", text, re.S | re.M
    )
    return match.group(1) if match else ""


class AutopilotResearchStepTests(unittest.TestCase):
    def setUp(self):
        self.text = read(AUTOPILOT)
        self.step2 = section(self.text, "2. Research")

    def test_step_two_exists(self):
        self.assertTrue(self.step2.strip(), "autopilot has no '### 2. Research' step")

    def test_step_two_calls_the_research_entry_point(self):
        self.assertRegex(self.step2, r"`/compass:research`|`research` skill")

    def test_step_two_does_not_spawn_the_researcher_directly(self):
        self.assertNotRegex(self.step2, r"(?i)spawn the `researcher` agent")

    def test_step_two_names_the_gate_and_the_grading_disclosure(self):
        self.assertIn("gate", self.step2)
        self.assertIn("grading", self.step2)

    def test_checkpoint_block_carries_the_grading_field(self):
        step3 = section(self.text, "3. Plan")
        block = re.search(r"```\n(.*?)```", step3, re.S)
        self.assertIsNotNone(block, "step 3 has no checkpoint block")
        self.assertIn("grading:", block.group(1))

    def test_grading_field_is_spelled_as_the_research_entry_point_spells_it(self):
        research = read(RESEARCH)
        for state in ("grading: allowed", "grading: refused"):
            with self.subTest(state=state):
                self.assertIn(state, research)
                self.assertIn(state, self.text)

    def test_checkpoint_asks_no_second_grading_question(self):
        step3 = section(self.text, "3. Plan")
        options = re.findall(r"^- \*\*(.+?):\*\*", step3, re.M)
        self.assertTrue(options, "step 3 lists no checkpoint options")
        for option in options:
            with self.subTest(option=option):
                self.assertNotIn("grading", option.lower())

    def test_autopilot_holds_every_tool_the_research_entry_point_declares(self):
        def tools(text):
            match = re.search(r"^allowed-tools:\s*\[(.*?)\]", text, re.M)
            self.assertIsNotNone(match)
            return {t.strip() for t in match.group(1).split(",")}

        missing = tools(read(RESEARCH)) - tools(self.text)
        self.assertEqual(missing, set())

    def test_failure_modes_name_bypassing_the_entry_point(self):
        failures = self.text.split("## Failure modes worth naming", 1)
        self.assertEqual(len(failures), 2)
        self.assertIn("research entry point", failures[1])


if __name__ == "__main__":
    unittest.main()
