"""Tests for the build skill's fix-loop text: step 5 runs
`compass test-checkpoint cycle` after each post-build tester confirmation and
the phase summary's `fix_loop_cycles` is read from that command."""

import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / "skills" / "build" / "SKILL.md"


def step_five(text):
    """The body of numbered step 5 (the fix loop), up to step 6."""
    match = re.search(r"^5\. \*\*Fix loop\.\*\*.*?(?=^6\. \*\*)", text, re.MULTILINE | re.DOTALL)
    assert match, "build SKILL.md has no step 5 'Fix loop'"
    return match.group(0)


class BuildSkillCycleTests(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")

    def test_step_five_runs_the_cycle_command_with_the_verified_evidence(self):
        """Adversarial where: the fix loop still decides helpful versus
        harmful by hand because step 5 never names the command, names it
        without the evidence flag, or leaves a harmful cycle unshown to the
        human."""
        step = step_five(self.text)
        self.assertIn("compass test-checkpoint cycle", step)
        self.assertIn("--evidence", step)
        self.assertIn("harmful", step)

    def test_fix_loop_cycles_is_read_from_the_cycle_command(self):
        """Adversarial where: the phase summary's `fix_loop_cycles` stays a
        hand-tallied count because the skill never ties it to the command's
        output."""
        tied = [
            line for line in self.text.splitlines()
            if "fix_loop_cycles" in line and "compass test-checkpoint cycle" in line
        ]
        self.assertTrue(tied, "no line ties fix_loop_cycles to `compass test-checkpoint cycle`")
        self.assertTrue(
            any(re.search(r"\b(read|reads|from)\b", line) for line in tied),
            "fix_loop_cycles is mentioned beside the command but not as read from it",
        )


if __name__ == "__main__":
    unittest.main()
