"""The setup skill offers longer session retention through `compass retention`.

Guards two defects: the offer step disappearing from the skill, and the skill
naming a `compass` subcommand that is not registered in `COMMAND_SPECS`.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maincli  # noqa: E402

SKILL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "skills", "setup", "SKILL.md",
)

# `compass <word>` where word is a lowercase kebab-case command token.
# Slash commands (`/compass:vision`) have a colon right after `compass`
# and never match; capitalised prose ("Compass is", "compass CLI") neither.
COMMAND_REF = re.compile(r"\bcompass[ \t]+([a-z][a-z0-9-]*)\b")
INLINE_CODE = re.compile(r"`([^`\n]+)`")


def read_skill():
    with open(SKILL, encoding="utf-8") as handle:
        return handle.read()


def command_references(text):
    """Subcommand names the skill invokes: tokens inside inline code spans
    and non-comment lines of fenced code blocks. Plain prose is ignored."""
    names = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            if line.lstrip().startswith("#"):
                continue
            segments = [line]
        else:
            segments = INLINE_CODE.findall(line)
        for segment in segments:
            names.extend(COMMAND_REF.findall(segment))
    return names


class SetupRetentionTests(unittest.TestCase):
    def test_skill_names_retention_set(self):
        self.assertIn("compass retention --set", read_skill())

    def test_skill_offers_the_ten_year_value(self):
        self.assertIn("compass retention --set 3650", read_skill())

    def test_every_named_command_is_registered(self):
        registered = {name for name, _ in maincli.COMMAND_SPECS}
        names = command_references(read_skill())
        self.assertIn("retention", names)
        unknown = sorted({n for n in names if n not in registered})
        self.assertEqual(unknown, [], "setup skill names unregistered commands")

    def test_reference_parser_skips_slash_commands_and_prose(self):
        sample = (
            "Run `/compass:vision` then `compass doctor`.\n"
            "The compass CLI and Compass is prose, compass vault too.\n"
            "```bash\n"
            "# the compass binary comment\n"
            "python .claude/cli/compass sync\n"
            "```\n"
        )
        self.assertEqual(command_references(sample), ["doctor", "sync"])


if __name__ == "__main__":
    unittest.main()
