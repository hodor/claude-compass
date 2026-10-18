"""The clone-old skill names real `compass` commands and ships from version 0.27.0 on.

Guards two defects: the skill naming a `compass` subcommand that is not
registered in `COMMAND_SPECS` (a renamed command would otherwise break the
skill silently), and the plugin version falling below 0.27.0, the first release
that ships the skill.
"""

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maincli  # noqa: E402

PLUGIN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(PLUGIN, "skills", "clone-old", "SKILL.md")
PLUGIN_JSON = os.path.join(PLUGIN, ".claude-plugin", "plugin.json")

# `compass <word>` where word is a lowercase kebab-case command token.
# Slash commands (`/compass:vision`) have a colon right after `compass`
# and never match; capitalised prose ("Compass is") neither.
COMMAND_REF = re.compile(r"\bcompass[ \t]+([a-z][a-z0-9-]*)\b")
INLINE_CODE = re.compile(r"`([^`\n]+)`")


def read_skill():
    with open(SKILL, encoding="utf-8") as handle:
        return handle.read()


def frontmatter_name(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            return None
        match = re.match(r"name:\s*(\S+)\s*$", line)
        if match:
            return match.group(1)
    return None


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


class CloneOldSkillTests(unittest.TestCase):
    def test_frontmatter_name_is_clone_old(self):
        self.assertEqual(frontmatter_name(read_skill()), "clone-old")

    def test_every_named_command_is_registered(self):
        registered = {name for name, _ in maincli.COMMAND_SPECS}
        names = command_references(read_skill())
        for expected in ("sessions", "clone"):
            self.assertIn(expected, names)
        unknown = sorted({n for n in names if n not in registered})
        self.assertEqual(unknown, [], "clone-old skill names unregistered commands")

    def test_plugin_version_is_at_least_0_27_0(self):
        with open(PLUGIN_JSON, encoding="utf-8") as handle:
            version = json.load(handle)["version"]
        parts = tuple(int(part) for part in version.split("."))
        self.assertGreaterEqual(parts, (0, 27, 0), f"plugin version {version}")

    def test_reference_parser_skips_slash_commands_and_prose(self):
        sample = (
            "Run `/compass:clone-old` then `compass sessions list --json`.\n"
            "The compass CLI and Compass is prose, compass vault too.\n"
            "```bash\n"
            "# the compass binary comment\n"
            "python .claude/cli/compass clone abc\n"
            "```\n"
        )
        self.assertEqual(command_references(sample), ["sessions", "clone"])


if __name__ == "__main__":
    unittest.main()
