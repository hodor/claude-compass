"""Tests for the idea schema, the `ideas.base` Bases view, and the lookup rule
text: the obsidian skill's properties block, the Spec/Plan/Decision templates,
the shipped base and its installer registration, the pipeline rules'
`## Ideas` section and its size budget, and the methodology capability index.

Adversarial themes: a base copied from `lessons.base` that still filters on a
lesson status and shows nothing; a base column the schema never defines; a
base file shipped but absent from `BASE_FILES`, so no project ever gets it;
an `ideas:` key added to a template that is not a Spec, Plan or Decision; a
rule section that grows past three lines or lands under another heading; a
rule that tells agents to ask whether to record an idea; a rule that forgets
that rejections and questions are never ideas; the always-loaded rules file
growing past its budget; em-dash or en-dash characters in shipped text."""

import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from review_surfaces import obsidian  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SKILL_DIR = REPO / "plugin" / "skills" / "obsidian"
SKILL = SKILL_DIR / "SKILL.md"
TEMPLATES = SKILL_DIR / "templates.md"
PIPELINE = REPO / "plugin" / "templates" / "rules" / "compass-pipeline.md"
METHODOLOGY = REPO / "plugin" / "skills" / "methodology" / "SKILL.md"
IDEAS_BASE = obsidian.shipped_bases_dir() / "ideas.base"

STATUSES = ["new", "exploring", "parked", "adopted", "done", "dropped"]
EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)
MAX_LINES = 141
MAX_BYTES = 12419
FILE_KEYS = {"file.name", "file.ext", "file.path", "file.folder"}


def read(path):
    return path.read_text(encoding="utf-8")


def squash(text):
    return re.sub(r"\s+", " ", text).lower()


def properties_block():
    """Lines of the first yaml fence after "## YAML frontmatter" in SKILL.md."""
    body = read(SKILL).split("## YAML frontmatter", 1)[1]
    fence = body.split("```yaml", 1)[1].split("```", 1)[0]
    return fence.splitlines()


def key_lines(lines, key):
    return [ln for ln in lines if re.match(rf"{key}:", ln)]


def template_frontmatter(heading):
    """The frontmatter inside the first markdown fence after `### <heading>`
    in templates.md."""
    text = read(TEMPLATES)
    after = text.split(f"\n### {heading}\n", 1)[1]
    fence = after.split("```markdown\n", 1)[1]
    opened = fence.split("---\n", 1)[1]
    return opened.split("\n---\n", 1)[0]


def pipeline_section(name):
    body = read(PIPELINE).split(f"\n## {name}\n", 1)[1]
    return body.split("\n## ", 1)[0]


def flatten_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from flatten_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from flatten_strings(value)


class IdeasBaseView(unittest.TestCase):
    def load(self):
        self.assertTrue(IDEAS_BASE.is_file(), f"{IDEAS_BASE} is not shipped")
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML is not installed")
        return yaml.safe_load(read(IDEAS_BASE))

    def test_base_filters_to_ideas_and_offers_the_named_table_views(self):
        """Adversarial where: a base copied from `lessons.base` keeps its
        `status == "active"` filter (no idea ever has that status, so the view
        is empty) or its `lesson` type; the category view must group by the
        folder, the status view by status, and the columns the plan names
        must all be shown."""
        data = self.load()
        filters = [squash(s).replace("'", '"') for s in flatten_strings(data.get("filters"))]
        self.assertIn('type == "idea"', filters)
        for text in filters:
            self.assertNotIn("status", text, "a status filter hides ideas")
            self.assertNotIn("lesson", text)
        views = {v["name"]: v for v in data["views"]}
        self.assertEqual(set(views), {"By category", "By status"})
        for name, view in views.items():
            self.assertEqual(view["type"], "table", name)
        self.assertEqual(views["By category"]["groupBy"]["property"], "file.folder")
        self.assertEqual(views["By status"]["groupBy"]["property"], "status")
        shown = {
            "By category": ["file.name", "status", "words", "led_to", "led_to_note"],
            "By status": ["file.name", "words", "led_to", "led_to_note"],
        }
        for name, columns in shown.items():
            for column in columns:
                self.assertIn(column, views[name]["order"], f"{name} lacks {column}")

    def test_base_text_carries_no_em_or_en_dash(self):
        """Adversarial where: a displayName or comment typed with a typographic
        dash ships a character the project bans from all output."""
        self.assertTrue(IDEAS_BASE.is_file(), f"{IDEAS_BASE} is not shipped")
        text = read(IDEAS_BASE)
        self.assertNotIn(EM_DASH, text)
        self.assertNotIn(EN_DASH, text)


class IdeasBaseInstall(unittest.TestCase):
    def test_base_is_registered_and_installed_into_a_vault(self):
        """Adversarial where: the file ships in `plugin/obsidian/bases/` but
        `BASE_FILES` omits it, so `install_bases` and the Obsidian install
        never copy it; or the new entry displaces an existing base."""
        self.assertEqual(obsidian.BASE_FILES.count("ideas.base"), 1)
        for kept in ("review-inbox.base", "lessons.base"):
            self.assertIn(kept, obsidian.BASE_FILES)
        shipped = obsidian.shipped_bases_dir() / "ideas.base"
        self.assertTrue(shipped.is_file(), f"{shipped} is not shipped")
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "compass"
            (vault / ".obsidian").mkdir(parents=True)
            written = obsidian.install_bases(vault)
            self.assertIn("ideas.base", written)
            self.assertEqual((vault / "ideas.base").read_bytes(), shipped.read_bytes())
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "compass"
            (vault / ".obsidian").mkdir(parents=True)
            message = obsidian.install_plugin(vault)
            self.assertIn("ideas.base", message)
            self.assertTrue((vault / "ideas.base").is_file())


class SchemaAndTemplates(unittest.TestCase):
    def test_skill_properties_block_defines_the_idea_schema(self):
        """Adversarial where: `idea` is missing from the `type` values, the
        status line drops or reorders a status, a key has no comment or two
        comments, `ideas` is described as belonging to the wrong document
        types, or a key the base shows (`words`, `led_to`, `led_to_note`) is
        undefined so a view silently goes empty."""
        lines = properties_block()
        (type_line,) = key_lines(lines, "type")
        tokens = [t.strip() for t in type_line.split("#", 1)[0].split(":", 1)[1].split("|")]
        self.assertIn("idea", tokens)
        for kept in ("spec", "research", "plan", "task", "lesson", "decision", "handoff"):
            self.assertIn(kept, tokens)
        joined = "\n".join(lines)
        self.assertIn(" | ".join(STATUSES), joined)
        self.assertIn("draft | review | approved | active | done | archived", joined)
        for key in ("words", "led_to", "led_to_note", "raw_status", "source", "ideas"):
            with self.subTest(key=key):
                found = key_lines(lines, key)
                self.assertEqual(len(found), 1, f"{key} is not defined once")
                self.assertEqual(found[0].count("#"), 1, f"{key} needs exactly one comment")
                comment = found[0].split("#", 1)[1].lower()
                self.assertIn("idea", comment)
        ideas_comment = key_lines(lines, "ideas")[0].split("#", 1)[1].lower()
        for doc in ("spec", "plan", "decision"):
            self.assertIn(doc, ideas_comment)
        self.assertTrue(IDEAS_BASE.is_file(), "ideas.base is not shipped")
        schema = "\n".join(read(p) for p in sorted(SKILL_DIR.glob("*.md")))
        defined = set(re.findall(r"^([a-z_]+):", schema, re.M))
        shown_keys = re.findall(r"^\s+-\s+([a-z_.]+)\s*$", read(IDEAS_BASE), re.M)
        self.assertIn("words", shown_keys)
        for shown in shown_keys:
            if shown not in FILE_KEYS:
                self.assertIn(shown, defined, f"ideas.base shows undefined key {shown}")

    def test_ideas_key_sits_in_spec_plan_decision_templates_only(self):
        """Adversarial where: the optional `ideas:` property is added to one
        or two of the three templates, or leaks into the Research, Lesson or
        Handoff templates that the plan does not give it to."""
        wanted = re.compile(r'^ideas: \["\[\[IDEA-NNN-slug\]\]"\]\s+# OPTIONAL', re.M)
        for heading in ("Spec", "Plan", "Decision (ADR)"):
            with self.subTest(template=heading):
                self.assertRegex(template_frontmatter(heading), wanted)
        for heading in ("Research", "Lesson", "Handoff"):
            with self.subTest(template=heading):
                self.assertNotRegex(template_frontmatter(heading), r"^ideas:")


class PipelineRules(unittest.TestCase):
    def test_ideas_section_states_lookup_naming_and_capture_rules(self):
        """Adversarial where: the lookup sentence lands under another heading,
        names no `compass idea find` command, omits what to answer with (his
        words, status, where it led, history), forgets the `ideas:` property,
        tells agents to ask whether to record an idea, drops that rejections
        and questions are never logged, or grows past three lines."""
        section = pipeline_section("Ideas")
        body_lines = [ln for ln in section.splitlines() if ln.strip()]
        self.assertGreaterEqual(len(body_lines), 1)
        self.assertLessEqual(len(body_lines), 3, "the section is at most three lines")
        text = squash(section)
        self.assertIn("compass idea find", text)
        self.assertIn("idea-nnn", text)
        for part in ("his words", "status", "where it led", "history"):
            self.assertIn(part, text, f"answer must include {part}")
        self.assertIn("`ideas:`", section)
        for doc in ("spec", "plan", "adr"):
            self.assertIn(doc, text)
        sentences = re.split(r"(?<=[.!?])\s+", text)
        self.assertTrue(
            any("automatic" in s and re.search(r"\b(never|do not|don't) ask", s) for s in sentences),
            "capture is automatic, so agents never ask whether to record an idea",
        )
        self.assertTrue(
            any(re.search(r"reject|refut", s) and re.search(r"\b(never|not|no)\b", s) for s in sentences),
            "a rejection of an agent suggestion is never logged as an idea",
        )
        self.assertTrue(
            any("question" in s and re.search(r"\b(never|not|no)\b", s) for s in sentences),
            "his questions to the agent are not ideas",
        )

    def test_pipeline_rules_stay_within_budget_and_free_of_dashes(self):
        """Adversarial where: the always-loaded rules file grows past its
        141-line or 12,419-byte budget, or the new text carries an em-dash or
        en-dash character; both budgets are checked at the exact limit."""
        self.assertIn("## Ideas", read(PIPELINE), "no Ideas section to budget")
        text = read(PIPELINE)
        self.assertLessEqual(len(text.splitlines()), MAX_LINES)
        self.assertLessEqual(len(PIPELINE.read_bytes()), MAX_BYTES)
        self.assertNotIn(EM_DASH, text)
        self.assertNotIn(EN_DASH, text)


class MethodologyCapabilityIndex(unittest.TestCase):
    def test_capability_index_names_compass_idea_in_one_sentence(self):
        """Adversarial where: the capability index paragraph never names
        `compass idea` (agents conclude the capability is missing), names it
        in several sentences (the paragraph bloats), or loses its existing
        `compass tree` and `compass usage` sentences in the edit."""
        text = read(METHODOLOGY)
        paragraph = next(
            p for p in re.split(r"\n\s*\n", text) if p.startswith("The full capability index")
        )
        mentions = [s for s in re.split(r"(?<=[.!?])\s+", paragraph) if "compass idea" in s]
        self.assertEqual(len(mentions), 1, "exactly one sentence names `compass idea`")
        self.assertIn("`compass tree`", paragraph)
        self.assertIn("`compass usage`", paragraph)
        self.assertNotIn(EM_DASH, mentions[0])
        self.assertNotIn(EN_DASH, mentions[0])


if __name__ == "__main__":
    unittest.main()
