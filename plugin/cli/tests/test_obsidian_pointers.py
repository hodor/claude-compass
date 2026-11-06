"""Every pointer into the `obsidian` skill names the file and the heading that
hold the text it points at.

A pointer reads: the `obsidian` skill, file `documents.md`, section "Decision
bullets". Inside the skill folder the shorter form `file `x.md`, section "Y"`
names a sibling file. The scan covers the shipped markdown (skills, templates,
loop templates) and resolves each pointer to a heading outside code fences in
the named file; a heading matches by its full text or by its text before a
trailing parenthetical.

Adversarial themes: a pointer to a heading that moved to another file, a
heading that exists only inside a code fence, a section named with no file, a
legacy `obsidian/SKILL.md` path, a quoted title with no file, a heading matched
by a prefix of its words, and an agent that writes vault documents without the
templates pointer."""

import re
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PLUGIN = REPO / "plugin"
SKILL_DIR = PLUGIN / "skills" / "obsidian"
SCANNED = [PLUGIN / "skills", PLUGIN / "templates", PLUGIN / "cli" / "loop_templates"]
AGENTS_WITH_TEMPLATES_LINE = ["planner", "researcher", "reviewer", "pr-describe"]
TEMPLATES_LINE = "Before writing a vault document, read the `obsidian` skill, file `templates.md`."

SKILL_MENTION = re.compile(r"`?obsidian`? skill(?:'s)?")
FILE_POINTER = re.compile(r"file `([^`]+)`(?:, section \"([^\"]+)\")?")
LEGACY_PATH = re.compile(r"obsidian/SKILL\.md")
BARE_TITLE_SEE = re.compile(r"\b[Ss]ee (?:the )?\"[A-Z][^\"]*\"")
HEADING_LINE = re.compile(r"^#{2,4} (.+?)\s*$")


def markdown_files():
    for root in SCANNED:
        yield from sorted(root.rglob("*.md"))


def headings(path):
    """Heading texts of `path` outside code fences."""
    found, fenced = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        match = None if fenced else HEADING_LINE.match(line)
        if match:
            found.append(match.group(1))
    return found


def heading_matches(heading, title):
    return heading == title or heading.startswith(title + " (")


def sentence_after(text, start):
    """Text from `start` to the end of its sentence (a period before
    whitespace) or paragraph."""
    paragraph = text[start:].split("\n\n", 1)[0]
    return re.split(r"\.(?:\s|$)", paragraph, maxsplit=1)[0]


def resolve(skill_dir, name, title):
    """A problem string when pointer (`name`, `title`) does not resolve in
    `skill_dir`, else None."""
    path = skill_dir / name
    if not path.is_file():
        return f"file `{name}` is not in the skill folder"
    if title is not None and not any(heading_matches(h, title) for h in headings(path)):
        return f"section \"{title}\" is not a heading of `{name}`"
    return None


def pointers_in(text, in_skill_folder):
    """(file, section or None) pairs for every pointer in `text`, plus the
    problems of pointers that cannot be resolved by name at all."""
    pairs, problems = [], []
    for mention in SKILL_MENTION.finditer(text):
        tail = sentence_after(text, mention.end())
        for found in FILE_POINTER.finditer(tail):
            pairs.append((found.group(1), found.group(2)))
        rest = FILE_POINTER.sub("", tail)
        if 'section "' in rest:
            problems.append(f"names a section but no file: ...{tail[:80]}")
        elif re.search(r"\"[A-Z][^\"]*\"", rest):
            problems.append(f"quotes a title but names no file: ...{tail[:80]}")
    if in_skill_folder:
        for found in FILE_POINTER.finditer(text):
            pairs.append((found.group(1), found.group(2)))
    return sorted(set(pairs), key=lambda pair: (pair[0], pair[1] or "")), problems


def problems_in(text, skill_dir, in_skill_folder=False):
    pairs, problems = pointers_in(text, in_skill_folder)
    for name, title in pairs:
        problem = resolve(skill_dir, name, title)
        if problem:
            problems.append(problem)
    if LEGACY_PATH.search(text):
        problems.append("names the skill by its old path obsidian/SKILL.md")
    for bare in BARE_TITLE_SEE.finditer(text):
        problems.append(f"points at a bare title with no file: {bare.group(0)}")
    return problems


class ShippedPointersResolve(unittest.TestCase):
    def test_every_pointer_resolves_to_a_heading_in_the_named_file(self):
        """Adversarial where: a section moves between side files, or a heading
        is renamed, while a pointer elsewhere still names the old home."""
        files = list(markdown_files())
        self.assertGreater(len(files), 50)
        total = 0
        for path in files:
            text = path.read_text(encoding="utf-8")
            in_skill = path.parent == SKILL_DIR
            total += len(pointers_in(text, in_skill)[0])
            with self.subTest(file=str(path.relative_to(REPO))):
                self.assertEqual(problems_in(text, SKILL_DIR, in_skill), [])
        self.assertGreater(total, 12, "the scan found too few pointers to be checking anything")

    def test_the_pointers_the_pipeline_rules_carry_are_found(self):
        """Adversarial where: the scanner's grammar drifts from the wording in
        the always-loaded rules, so those pointers go unchecked."""
        text = (PLUGIN / "templates" / "rules" / "compass-pipeline.md").read_text(encoding="utf-8")
        pairs, _ = pointers_in(text, False)
        self.assertIn(("documents.md", "Documents the human reads"), pairs)
        self.assertIn(("writing-principles.md", "Scope of the reader test"), pairs)
        self.assertIn(("writing-principles.md", "Indexing a new vault document"), pairs)

    def test_the_agents_that_write_vault_documents_point_to_the_templates(self):
        """Adversarial where: an agent preloads the skill but never learns that
        the templates sit in a side file it must read before writing."""
        for name in AGENTS_WITH_TEMPLATES_LINE:
            with self.subTest(agent=name):
                text = (PLUGIN / "templates" / "agents" / f"{name}.md").read_text(encoding="utf-8")
                self.assertIn(TEMPLATES_LINE, text)
                self.assertEqual(problems_in(text, SKILL_DIR), [])

    def test_no_shipped_text_names_the_skill_by_its_file_path(self):
        """Adversarial where: a pointer says `obsidian/SKILL.md` for a section
        that now lives in a side file."""
        for path in markdown_files():
            with self.subTest(file=str(path.relative_to(REPO))):
                self.assertIsNone(LEGACY_PATH.search(path.read_text(encoding="utf-8")))


class ResolverRejectsBadPointers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        (cls.dir / "a.md").write_text(
            "# A\n\n## Alpha\n\n### Beta\n\n```markdown\n## Gamma\n```\n", encoding="utf-8")
        (cls.dir / "b.md").write_text("# B\n\n## Delta (extra words)\n\n## Epsilon\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check(self, sentence):
        return problems_in(sentence, self.dir)

    def test_a_pointer_to_the_right_file_and_heading_passes(self):
        self.assertEqual(self.check('See the `obsidian` skill, file `a.md`, section "Alpha".'), [])
        self.assertEqual(self.check('See the `obsidian` skill, file `a.md`, section "Beta".'), [])
        self.assertEqual(self.check("See the `obsidian` skill, file `b.md`."), [])

    def test_a_heading_matches_by_its_text_before_a_parenthetical(self):
        self.assertEqual(self.check('The `obsidian` skill, file `b.md`, section "Delta".'), [])
        self.assertEqual(self.check('The `obsidian` skill, file `b.md`, section "Delta (extra words)".'), [])

    def test_a_pointer_to_a_heading_that_moved_to_another_file_fails(self):
        found = self.check('The `obsidian` skill, file `b.md`, section "Alpha".')
        self.assertEqual(len(found), 1)
        self.assertIn("not a heading of `b.md`", found[0])

    def test_a_missing_file_fails(self):
        found = self.check('The `obsidian` skill, file `gone.md`, section "Alpha".')
        self.assertEqual(len(found), 1)
        self.assertIn("is not in the skill folder", found[0])

    def test_a_heading_that_appears_only_inside_a_code_fence_fails(self):
        self.assertEqual(len(self.check('The `obsidian` skill, file `a.md`, section "Gamma".')), 1)

    def test_a_prefix_of_a_heading_fails(self):
        self.assertEqual(len(self.check('The `obsidian` skill, file `b.md`, section "Del".')), 1)
        self.assertEqual(len(self.check('The `obsidian` skill, file `b.md`, section "Delta (extra".')), 1)
        self.assertEqual(len(self.check('The `obsidian` skill, file `b.md`, section "Epsilo".')), 1)

    def test_a_section_with_no_file_fails(self):
        found = self.check('Follow the `obsidian` skill, section "Alpha".')
        self.assertTrue(any("names a section but no file" in p for p in found), found)

    def test_a_quoted_title_with_no_file_fails(self):
        found = self.check('Resolve it per the `obsidian` skill\'s "Alpha" rule: the root.')
        self.assertTrue(any("quotes a title but names no file" in p for p in found), found)

    def test_the_old_file_path_fails(self):
        found = self.check("See the Lesson template in `obsidian/SKILL.md` for the schema.")
        self.assertTrue(any("old path" in p for p in found), found)

    def test_a_bare_quoted_title_pointer_fails(self):
        found = self.check('See "Unit folders" below for when a link must be path-qualified.')
        self.assertTrue(any("bare title" in p for p in found), found)

    def test_a_file_named_in_a_later_sentence_is_not_attributed_to_the_mention(self):
        text = 'The `obsidian` skill holds the forms. Another note says file `zzz.md`, section "Q".'
        self.assertEqual(self.check(text), [])

    def test_inside_the_skill_folder_a_sibling_pointer_resolves_without_the_mention(self):
        text = 'See file `b.md`, section "Alpha" for it.'
        self.assertEqual(len(problems_in(text, self.dir, in_skill_folder=True)), 1)
        self.assertEqual(problems_in('See file `b.md`, section "Epsilon" for it.', self.dir, in_skill_folder=True), [])


class MovedHeadingsAreCaughtInTheRealSkill(unittest.TestCase):
    def test_a_pointer_to_the_decision_bullets_heading_in_templates_fails(self):
        """The heading lives in documents.md; naming templates.md must fail."""
        found = problems_in('The `obsidian` skill, file `templates.md`, section "Decision bullets".', SKILL_DIR)
        self.assertEqual(len(found), 1)
        self.assertEqual(problems_in('The `obsidian` skill, file `documents.md`, section "Decision bullets".', SKILL_DIR), [])

    def test_a_pointer_to_unit_folders_in_skill_md_fails(self):
        found = problems_in('The `obsidian` skill, file `SKILL.md`, section "Unit folders".', SKILL_DIR)
        self.assertEqual(len(found), 1)
        self.assertEqual(problems_in('The `obsidian` skill, file `vault-layout.md`, section "Unit folders".', SKILL_DIR), [])


if __name__ == "__main__":
    unittest.main()
