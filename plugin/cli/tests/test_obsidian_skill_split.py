"""The obsidian skill is a short always-loaded `SKILL.md` plus top-level side
files. Sections moved whole and unedited, so nothing the skill taught was lost.

The unsplit original is read from BASE_COMMIT with `git show` and compared with
the skill folder as SPLIT_COMMIT committed it, so later edits to a moved
section (a pointer naming its new file, a reworded rule) leave the migration
checks green while the structural checks keep running against the live folder.
The migration checks skip when git or either commit is unavailable (a shallow
clone).

Adversarial themes: a heading dropped or duplicated across files, a section
moved with a word changed, a section sent to the wrong file, a side-file table
that names a file without saying what it holds, a SKILL.md that grew back over
its budget, a frontmatter key that only the old single file carried."""

import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FOLDER = REPO / "plugin" / "skills" / "obsidian"
BASE_COMMIT = "72f1c7c"
SPLIT_COMMIT = "1babf76"
SKILL_MAX_CHARS = 10_000

# The side file that holds each moved top-level `##` section.
DESTINATION = {
    "Document templates": "templates.md",
    "Decision bullets (the D-NN convention)": "documents.md",
    "Documents the human reads": "documents.md",
    "Math (LaTeX)": "vault-layout.md",
    "File naming": "vault-layout.md",
    "Hierarchical specs and plans (folders)": "vault-layout.md",
    "Unit folders (the hybrid root)": "vault-layout.md",
    "Facet tags (the multi-parent layer)": "vault-layout.md",
    "Vault search patterns": "vault-layout.md",
}
KEPT = ["The one linking rule", "YAML frontmatter", "Wikilinks"]
SIDE_FILES = ["templates.md", "documents.md", "vault-layout.md"]
HEADING = re.compile(r"^#{2,3} .+$", re.M)
DASHES = "\u2013\u2014"


def read(name):
    return (FOLDER / name).read_text(encoding="utf-8")


def committed(commit, name):
    """A skill-folder file as `commit` holds it, newline-normalized."""
    try:
        done = subprocess.run(
            ["git", "show", f"{commit}:plugin/skills/obsidian/{name}"],
            cwd=REPO, capture_output=True,
        )
    except OSError:
        raise unittest.SkipTest("git is not available")
    if done.returncode != 0:
        raise unittest.SkipTest(f"commit {commit} is not available to git")
    return done.stdout.decode("utf-8").replace("\r\n", "\n")


def original():
    """The unsplit SKILL.md at BASE_COMMIT."""
    return committed(BASE_COMMIT, "SKILL.md")


def split_files():
    """{file name: text} of the skill folder as SPLIT_COMMIT committed it."""
    return {name: committed(SPLIT_COMMIT, name) for name in ["SKILL.md"] + SIDE_FILES}


def top_sections(text):
    """`## ` sections of `text`, fence-aware: {heading text: whole section
    including its `###` children, trailing blank lines trimmed}."""
    sections, current, fenced = {}, None, False
    for line in text.split("\n"):
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            current = line[3:]
            sections[current] = []
        if current is not None:
            sections[current].append(line)
    return {k: "\n".join(v).rstrip() for k, v in sections.items()}


def schema_keys(text):
    return set(re.findall(r"^([a-z_]+):", text, re.M))


def folder_text():
    return "\n\n".join(read(p.name) for p in sorted(FOLDER.glob("*.md")))


def table_rows(text):
    return [line for line in text.splitlines() if line.startswith("|")]


class SideFilesExist(unittest.TestCase):
    def test_each_side_file_is_a_nonempty_top_level_markdown_file(self):
        """Adversarial where: a side file lands in a subfolder, which the
        installer (top-level `.md` files only) never copies, or is empty."""
        for name in SIDE_FILES:
            with self.subTest(file=name):
                path = FOLDER / name
                self.assertTrue(path.is_file(), f"{name} is not a top-level file of the skill")
                self.assertGreater(len(path.read_text(encoding="utf-8").strip()), 500)

    def test_side_files_do_not_start_with_skill_frontmatter(self):
        """Adversarial where: a side file opens with `---` frontmatter, so a
        skill loader could read it as a second skill definition."""
        for name in SIDE_FILES:
            with self.subTest(file=name):
                self.assertFalse(read(name).startswith("---"))


class SkillMdIsShort(unittest.TestCase):
    def test_skill_md_is_under_the_character_budget(self):
        """Adversarial where: SKILL.md keeps a heavy section or the side-file
        table swells until the always-loaded part is long again."""
        self.assertLess(len(read("SKILL.md")), SKILL_MAX_CHARS)

    def test_skill_md_names_every_side_file(self):
        text = read("SKILL.md")
        for name in SIDE_FILES:
            with self.subTest(file=name):
                self.assertIn(name, text)

    def test_each_side_file_row_says_what_it_holds_and_when_to_read_it(self):
        """Adversarial where: the table lists a file name without the sections
        it holds, or a row has no third column telling when to read it, so an
        agent cannot tell which file answers its question."""
        text = read("SKILL.md")
        for name in SIDE_FILES:
            with self.subTest(file=name):
                rows = [r for r in table_rows(text) if name in r]
                self.assertEqual(len(rows), 1, f"{name} must sit in exactly one table row")
                cells = [c.strip() for c in rows[0].strip().strip("|").split("|")]
                self.assertGreaterEqual(len(cells), 3, "row needs file, holds, when to read")
                self.assertTrue(all(cells[:3]), "row has an empty cell")
                for title, dest in DESTINATION.items():
                    if dest == name:
                        short = title.split(" (")[0]
                        self.assertIn(short, rows[0], f"{name} row does not name '{short}'")

    def test_the_one_linking_rule_heading_appears_once(self):
        """Exactly one line is the `## The one linking rule` heading."""
        count = len(re.findall(r"^## The one linking rule", read("SKILL.md"), re.M))
        self.assertEqual(count, 1)

    def test_kept_sections_stay_in_skill_md(self):
        text = read("SKILL.md")
        for title in KEPT:
            with self.subTest(section=title):
                self.assertIn(f"\n## {title}\n", text)

    def test_skill_md_carries_no_moved_section_heading(self):
        """Adversarial where: a moved section is copied back into SKILL.md,
        so the same text is loaded twice."""
        headings = set(top_sections(read("SKILL.md")))
        self.assertEqual(headings & set(DESTINATION), set())

    def test_new_skill_md_lines_carry_no_em_or_en_dash(self):
        """Adversarial where: the added table and wording use a dash the
        project forbids; moved sections keep their original text."""
        old = set(original().split("\n"))
        for line in read("SKILL.md").split("\n"):
            if line not in old:
                with self.subTest(line=line[:60]):
                    self.assertFalse(any(d in line for d in DASHES))


class MigrationKeepsEverything(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = original()
        cls.split = split_files()

    def test_every_original_heading_is_in_exactly_one_file(self):
        """Adversarial where: a `##` or `###` heading is dropped, or sits in
        two files, at the split or in the live folder. The scan counts heading
        lines inside code fences too (the template headings and the
        `## Children` example)."""
        headings = HEADING.findall(self.old)
        self.assertGreater(len(headings), 60)
        live = {p.name: p.read_text(encoding="utf-8") for p in FOLDER.glob("*.md")}
        for label, texts in (("split", self.split), ("live", live)):
            for heading in sorted(set(headings)):
                with self.subTest(folder=label, heading=heading):
                    holders = [n for n, t in texts.items() if re.search(f"^{re.escape(heading)}$", t, re.M)]
                    self.assertEqual(len(holders), 1, f"'{heading}' is in {holders}")

    def test_every_original_section_moved_whole_and_unedited_to_its_file(self):
        """Adversarial where: one word of a section changes in the move, a
        subsection is left behind, or a section goes to the wrong file."""
        sections = top_sections(self.old)
        for title, dest in DESTINATION.items():
            with self.subTest(section=title):
                self.assertIn(title, sections)
                self.assertIn(sections[title], self.split[dest], f"'{title}' differs in {dest}")
                for other in SIDE_FILES + ["SKILL.md"]:
                    if other != dest:
                        self.assertNotIn(sections[title], self.split[other])

    def test_kept_sections_are_unedited(self):
        sections = top_sections(self.old)
        text = self.split["SKILL.md"]
        for title in KEPT:
            with self.subTest(section=title):
                self.assertIn(sections[title], text)

    def test_skill_md_keeps_its_title_and_front_matter(self):
        old_head = self.old.split("\n## ", 1)[0]
        new_head = self.split["SKILL.md"].split("\n## ", 1)[0]
        self.assertEqual(new_head, old_head)

    def test_no_original_line_is_lost(self):
        """Adversarial where: a line vanishes between sections (the Data rule:
        nothing is lost). Counts every non-blank original line against the
        folder at the split, so a repeated line must still be repeated."""
        folder = "\n\n".join(self.split[n] for n in ["SKILL.md"] + SIDE_FILES).split("\n")
        for line in sorted({l for l in self.old.split("\n") if l.strip()}):
            with self.subTest(line=line[:70]):
                self.assertGreaterEqual(folder.count(line), self.old.split("\n").count(line))

    def test_frontmatter_keys_are_the_same_set_as_before(self):
        """Adversarial where: a `key:` the Bases test finds in the schema
        lives in no file of the folder after the split."""
        self.assertEqual(schema_keys(folder_text()), schema_keys(self.old))

    def test_frontmatter_schema_keys_stay_in_skill_md(self):
        """Adversarial where: the properties table moves to a side file, so
        the always-loaded part no longer names the keys every document needs."""
        frontmatter_section = top_sections(self.old)["YAML frontmatter"]
        keys = schema_keys(frontmatter_section.split("```yaml", 1)[1].split("```", 1)[0])
        self.assertGreater(len(keys), 15)
        self.assertLessEqual(keys, schema_keys(read("SKILL.md")))


if __name__ == "__main__":
    unittest.main()
