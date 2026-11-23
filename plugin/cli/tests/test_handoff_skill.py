"""The handoff skill's template yields a handoff `compass validate` accepts,
and the skill says how to run the `compass` it calls.

Guards two defects: a template frontmatter missing a property validate
expects of a handoff (every handoff written as instructed then warns), and a
bare `compass` call with no resolvable form (the CLI is not on the Bash
PATH of a session, so the first call fails).
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import validate  # noqa: E402

PLUGIN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(PLUGIN, "skills", "handoff", "SKILL.md")


def read_skill():
    with open(SKILL, encoding="utf-8") as handle:
        return handle.read()


def template_frontmatter(text):
    """The property names of the handoff template's frontmatter: the
    `---` block inside the markdown fence of the Create protocol."""
    fence = re.search(r"```markdown\n(.*?)```", text, re.S)
    if not fence:
        return []
    lines = [line.strip() for line in fence.group(1).splitlines()]
    if not lines or lines[0] != "---":
        return []
    names = []
    for line in lines[1:]:
        if line == "---":
            return names
        match = re.match(r"([a-z_]+):", line)
        if match:
            names.append(match.group(1))
    return []


class HandoffTemplateTests(unittest.TestCase):
    def test_template_carries_every_property_validate_expects_of_a_handoff(self):
        names = template_frontmatter(read_skill())
        self.assertIn("type", names)
        missing = [field for field in validate.EXPECTED_FIELDS["handoff"] if field not in names]
        self.assertEqual(missing, [])

    def test_template_parser_rejects_a_frontmatter_without_a_closing_line(self):
        self.assertEqual(template_frontmatter("```markdown\n---\ntitle: x\n```"), [])

    def test_skill_names_the_installed_cli_path_for_compass(self):
        text = read_skill()
        self.assertIn("compass session-state --format handoff", text)
        self.assertIn("python3 .claude/cli/compass", text)
        self.assertIn("python .claude/cli/compass", text)


if __name__ == "__main__":
    unittest.main()
