"""Tests that the vault conventions shipped in `plugin/` know about loops, and
that the local install carries the loop commands and skill.

Public contract these tests pin:

    The obsidian skill lists `loop` among the frontmatter `type:` values; its
    vault layout names `LOOP-NNN-descriptive-name/` in the file naming table
    and `compass next-num loop` in the next-number table.

    The vault trees in the methodology skill, the setup skill and the
    vault-locator agent each name `loops/`.

    The local install under the repository's `.claude/` lists `schedule`,
    `sense-ast-grep` and `sense-context` in `cli/maincli.py`, and holds
    `skills/loop/SKILL.md` and `skills/loop/maya-recipe.md`. The install is
    generated, so these cases skip where no `.claude/cli/` exists (a fresh
    clone or CI checkout).

Adversarial themes: a type list updated in one copy and missed in another, a
naming row that names the folder without its numbering command, and a release
whose local install never received the new commands.
"""

import os
import re
import unittest
from pathlib import Path

CLI_DIR = Path(__file__).resolve().parent.parent
PLUGIN = CLI_DIR.parent
REPO = PLUGIN.parent
INSTALL = REPO / ".claude"

OBSIDIAN = PLUGIN / "skills" / "obsidian"
TREES = {
    "methodology": PLUGIN / "skills" / "methodology" / "SKILL.md",
    "setup": PLUGIN / "skills" / "setup" / "SKILL.md",
    "vault-locator": PLUGIN / "templates" / "agents" / "vault-locator.md",
}


def read(path):
    return Path(path).read_text(encoding="utf-8")


def fenced_blocks(text):
    return re.findall(r"^```[^\n]*\n(.*?)^```", text, re.MULTILINE | re.DOTALL)


class ConventionTests(unittest.TestCase):
    def test_obsidian_type_list_names_loop(self):
        text = read(OBSIDIAN / "SKILL.md")
        type_line = next((l for l in text.splitlines() if re.match(r"^type:\s", l)), None)
        self.assertIsNotNone(type_line, "no type: line in the obsidian skill")
        values = [v.strip() for v in type_line.split("#", 1)[0][len("type:"):].split("|")]
        self.assertIn("loop", values)

    def test_obsidian_naming_table_names_loop_folders(self):
        text = read(OBSIDIAN / "vault-layout.md")
        rows = [l for l in text.splitlines() if l.startswith("|") and "LOOP-NNN" in l]
        self.assertTrue(any("LOOP-NNN-descriptive-name/" in r for r in rows), rows)

    def test_obsidian_next_number_table_names_next_num_loop(self):
        text = read(OBSIDIAN / "vault-layout.md")
        rows = [l for l in text.splitlines() if l.startswith("| LOOP")]
        self.assertTrue(any("compass next-num loop" in r for r in rows), rows)

    def test_vault_trees_name_loops(self):
        missing = []
        for name, path in TREES.items():
            blocks = [b for b in fenced_blocks(read(path)) if ".compass/" in b]
            if not any(re.search(r"(?<![\w/])loops/", b) for b in blocks):
                missing.append(name)
        self.assertEqual(missing, [])


@unittest.skipUnless((INSTALL / "cli").is_dir(), "no local install under .claude/")
class LocalInstallTests(unittest.TestCase):
    def test_installed_cli_lists_the_loop_subcommands(self):
        text = read(INSTALL / "cli" / "maincli.py")
        loop_line = next((l for l in text.splitlines() if '("loop",' in l), "")
        missing = [s for s in ("schedule", "sense-ast-grep", "sense-context") if s not in loop_line]
        self.assertEqual(missing, [])

    def test_installed_loop_skill_and_recipe_exist(self):
        for name in ("SKILL.md", "maya-recipe.md"):
            with self.subTest(file=name):
                self.assertTrue((INSTALL / "skills" / "loop" / name).is_file())


if __name__ == "__main__":
    unittest.main()
