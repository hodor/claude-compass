"""A research run for a spec detects its own gap through the reviewer's spec
coverage table: one row per Need and per Decision of the spec, each naming at
least one finding that serves it, and a row with none is a gap that spawns
another research pass.

Guards four defects: the reviewer template losing the coverage step or its
report table, so a Need no finding serves (the source ledger of SPEC-023 was
one) reaches a plan unnoticed; the research entry point consolidating without
asking for the table, so the reviewer never builds it; the pipeline rules
dropping the invariant, so research run outside the entry point skips it; and
a shipped file pointing at the retired nugget scorer as the way a gap is found.
"""

import os
import re
import unittest

PLUGIN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REVIEWER = os.path.join(PLUGIN, "templates", "agents", "reviewer.md")
RESEARCH = os.path.join(PLUGIN, "skills", "research", "SKILL.md")
RULES = os.path.join(PLUGIN, "templates", "rules", "compass-pipeline.md")


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def section(text, heading, level):
    """The body under a heading line that starts with `heading` at the given
    level, up to the next heading of that level or higher."""
    hashes = "#" * level
    match = re.search(
        rf"^{hashes} {re.escape(heading)}[^\n]*$(.*?)(?=^#{{1,{level}}} |\Z)",
        text,
        re.S | re.M,
    )
    return match.group(1) if match else ""


class ReviewerCoverageStepTests(unittest.TestCase):
    def setUp(self):
        self.text = read(REVIEWER)
        protocol = section(self.text, "Protocol", 2)
        self.step = section(protocol, "5. Check spec coverage", 3)

    def test_protocol_has_a_spec_coverage_step(self):
        self.assertTrue(self.step.strip(), "reviewer protocol has no '### 5. Check spec coverage' step")

    def test_step_rows_are_every_need_and_every_decision(self):
        self.assertRegex(self.step, r"(?i)every Need")
        self.assertRegex(self.step, r"(?i)every Decision")

    def test_step_requires_at_least_one_finding_per_row(self):
        self.assertRegex(self.step, r"(?i)at least one finding")

    def test_step_reads_findings_across_every_document_of_the_run(self):
        # One consolidation under-reads a multi-document run: a sibling
        # document's finding counts.
        self.assertRegex(self.step, r"(?i)any (of the run's )?documents?|every document")

    def test_restating_a_decision_does_not_cover_it(self):
        self.assertRegex(self.step, r"(?i)restat")

    def test_an_uncovered_row_is_a_gap(self):
        self.assertRegex(self.step, r"(?i)no finding[^.]*\bgap\b")

    def test_a_deferred_decision_is_marked_not_counted_as_a_gap(self):
        self.assertIn("deferred", self.step)


class ReviewerReportFormatTests(unittest.TestCase):
    def setUp(self):
        self.report = section(read(REVIEWER), "Report format", 2)

    def test_report_template_carries_a_spec_coverage_table(self):
        block = re.search(r"```markdown\n(.*?)```", self.report, re.S)
        self.assertIsNotNone(block, "report format has no markdown template")
        template = block.group(1)
        self.assertIn("### Spec coverage", template)
        self.assertRegex(template, r"\|\s*Need or Decision\s*\|\s*Findings\s*\|")

    def test_coverage_table_comes_before_gaps(self):
        block = re.search(r"```markdown\n(.*?)```", self.report, re.S).group(1)
        self.assertLess(block.index("### Spec coverage"), block.index("### Gaps"))

    def test_gaps_section_takes_uncovered_rows(self):
        block = re.search(r"```markdown\n(.*?)```", self.report, re.S).group(1)
        gaps = block[block.index("### Gaps"):]
        self.assertRegex(gaps, r"(?i)need or decision with no finding")


class ResearchEntryPointTests(unittest.TestCase):
    def setUp(self):
        self.text = read(RESEARCH)

    def test_consolidation_step_asks_for_the_coverage_table(self):
        step = section(self.text, "9. Consolidate with the reviewer", 3)
        self.assertTrue(step.strip())
        self.assertRegex(step, r"(?i)spec coverage")

    def test_gap_step_names_an_uncovered_need_or_decision_as_a_gap(self):
        step = section(self.text, "10. A gap becomes another research pass", 3)
        self.assertTrue(step.strip())
        self.assertRegex(step, r"(?i)Need or Decision")
        self.assertIn("never goes to a plan", step)


class PipelineRuleTests(unittest.TestCase):
    def setUp(self):
        self.research = section(read(RULES), "Research", 2)

    def test_research_rules_carry_the_coverage_invariant(self):
        self.assertRegex(self.research, r"(?i)every Need and Decision")
        self.assertRegex(self.research, r"(?i)at least one finding")
        self.assertRegex(self.research, r"(?i)gap")

    def test_surviving_research_rules_stay(self):
        for line in (
            "Research traces to a spec.",
            "Every finding gets a confidence level.",
            "invite the human in",
            "evidence-rules.md",
        ):
            self.assertIn(line, self.research)


class RetiredScorerTests(unittest.TestCase):
    def test_no_shipped_research_surface_names_the_nugget_scorer(self):
        for path in (REVIEWER, RESEARCH, RULES):
            self.assertNotRegex(read(path), r"(?i)nugget", path)


if __name__ == "__main__":
    unittest.main()
