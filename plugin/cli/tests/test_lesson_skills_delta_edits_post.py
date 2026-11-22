"""Post-implementation structural checks over the consolidate and lesson-write skills."""

import re
import sys
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parents[1]
SKILLS = CLI.parent / "skills"
SKILL_FILES = [SKILLS / "consolidate" / "SKILL.md", SKILLS / "lesson-write" / "SKILL.md"]

sys.path.insert(0, str(CLI))
import maincli  # noqa: E402

COMPASS_CMD = re.compile(r"`compass ([a-z][a-z-]*)")
TIMELINE = re.compile(
    r"\b(TASK-\d+|PLAN-\d+|Tier[- ]\d|for now|first pass|Phase \d)\b", re.IGNORECASE
)


class SkillCommandReferenceTests(unittest.TestCase):
    def test_every_compass_command_named_in_the_skills_is_registered(self):
        """Adversarial where: a skill tells an agent to run a `compass <cmd>`
        that maincli does not register (typo or renamed command), so the
        agent's check step fails with an unknown-command error."""
        for path in SKILL_FILES:
            for name in set(COMPASS_CMD.findall(path.read_text(encoding="utf-8"))):
                with self.subTest(skill=path.parent.name, command=name):
                    self.assertIn(name, maincli.VALID_COMMANDS)


class SkillProseHygieneTests(unittest.TestCase):
    def test_no_plan_timeline_markers_in_skill_text(self):
        """Adversarial where: skill prose carries a task id or roadmap phrase
        that only makes sense to a reader who saw the plan."""
        for path in SKILL_FILES:
            hits = TIMELINE.findall(path.read_text(encoding="utf-8"))
            with self.subTest(skill=path.parent.name):
                self.assertEqual(hits, [])

    def test_no_absolute_local_paths_in_skill_text(self):
        """Adversarial where: an absolute drive or home path leaks from the
        authoring machine into shipped skill text."""
        pattern = re.compile(r"[A-Za-z]:[\/]|/Users/|/home/")
        for path in SKILL_FILES:
            with self.subTest(skill=path.parent.name):
                self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")))


class ProposalGateTests(unittest.TestCase):
    def test_consolidate_proposal_directory_is_the_gitignored_tmp_tree(self):
        """Adversarial where: the proposal file is directed outside
        `.compass/tmp/`, so a pending proposal would be committed."""
        text = (SKILLS / "consolidate" / "SKILL.md").read_text(encoding="utf-8")
        paths = re.findall(r"`(\.compass/[^`]*proposal[^`]*)`", text)
        self.assertTrue(paths)
        for p in paths:
            self.assertTrue(p.startswith(".compass/tmp/"), p)

    def test_lesson_write_refinement_never_tells_the_agent_to_edit_a_catalog_row(self):
        """Adversarial where: the refinement step still instructs a hand edit
        of a catalog row, which sync now owns."""
        text = SKILL_FILES[1].read_text(encoding="utf-8")
        block = text[text.index("### 4b.") : text.index("### 4c.")]
        hand_edit = re.compile(r"(?i)edit[^.]*catalog row|catalog row[^.]*in place")
        self.assertIsNone(hand_edit.search(block))


if __name__ == "__main__":
    unittest.main()
