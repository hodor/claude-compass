"""Tests for the plan detail-region classifier.

Adversarial themes: region boundaries that must stop at the right heading and
not one line early or late, the commit-upfront override's start/stop rules
(field-begins-with vs token-appears-anywhere), fence stripping that must
preserve line numbers even when it blanks content, and documents so small
(empty, frontmatter-only) that a naive implementation forgets to handle them.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import planlib  # noqa: E402


def classify_lines(text):
    return planlib.classify_lines(text)


class NoLaterSectionTests(unittest.TestCase):
    def test_document_with_no_later_section_returns_empty_map(self):
        """Adversarial where: a plan written entirely in the old fully-detailed
        shape, with no '## Later' heading anywhere, must classify every line as
        detailed (absent from the map) so its coverage verdict is unchanged from
        before this classifier existed."""
        text = "# Plan\n\n## Risks\n\nSome risk detail.\n\n## Phases\n\nTask work.\n"
        regions, unterminated = classify_lines(text)
        self.assertEqual(regions, {})
        self.assertFalse(unterminated)


class LaterRegionBoundaryTests(unittest.TestCase):
    def test_later_region_scoped_lines_and_closes_at_next_heading(self):
        """Adversarial where: the region must swallow every line under the
        heading but release at the very next level-1-or-2 heading, not one line
        early (swallowing the heading's own first body line) or one line late
        (leaking into the next section)."""
        text = "\n".join(
            [
                "# Plan",  # 1
                "",  # 2
                "## Later (intent only)",  # 3
                "",  # 4
                "- [ ] TASK-100: first intent - files: []",  # 5
                "- [ ] TASK-101: second intent - files: []",  # 6
                "",  # 7
                "## Risks",  # 8
                "",  # 9
                "Risk detail line.",  # 10
            ]
        ) + "\n"
        regions, unterminated = classify_lines(text)
        self.assertEqual(regions.get(5), "scoped")
        self.assertEqual(regions.get(6), "scoped")
        self.assertNotIn(8, regions)
        self.assertFalse(unterminated)

    def test_sub_heading_inside_later_stays_scoped(self):
        """Adversarial where: only a level-1 or level-2 heading may close the
        region; a level-3-or-deeper heading is content, and a classifier that
        treats any '#'-prefixed line as a closer would wrongly end the region
        here."""
        text = "\n".join(
            [
                "# Plan",  # 1
                "",  # 2
                "## Later (intent only)",  # 3
                "",  # 4
                "### sub heading",  # 5
                "",  # 6
                "- [ ] TASK-200: intent - files: []",  # 7
            ]
        ) + "\n"
        regions, _ = classify_lines(text)
        self.assertEqual(regions.get(5), "scoped")
        self.assertEqual(regions.get(7), "scoped")

    def test_second_later_heading_opens_second_scoped_region(self):
        """Adversarial where: a classifier that only tracks a single open/close
        toggle for the whole document (rather than reopening on each new match)
        would fail to scope a second, later '## Later' section after an
        intervening detailed one."""
        text = "\n".join(
            [
                "# Plan",  # 1
                "",  # 2
                "## Later (intent only)",  # 3
                "- [ ] TASK-300: first - files: []",  # 4
                "",  # 5
                "## Middle",  # 6
                "Detailed content here.",  # 7
                "",  # 8
                "## Later",  # 9
                "- [ ] TASK-301: second - files: []",  # 10
            ]
        ) + "\n"
        regions, _ = classify_lines(text)
        self.assertEqual(regions.get(4), "scoped")
        self.assertNotIn(7, regions)
        self.assertEqual(regions.get(10), "scoped")

    def test_later_heading_case_insensitivity_and_word_boundary(self):
        """Adversarial where: matching must be case-insensitive ('## later')
        but still require a word boundary after 'Later', so a heading that
        merely starts with those letters ('## Latergrade') is a false match a
        naive prefix check would wrongly open a region on."""
        cases = [
            (
                "lowercase later matches",
                "## later\n- [ ] TASK-500: intent - files: []\n",
                True,
            ),
            (
                "latergrade does not match",
                "## Latergrade\n- [ ] TASK-501: intent - files: []\n",
                False,
            ),
        ]
        for name, text, should_open in cases:
            with self.subTest(name=name):
                regions, _ = classify_lines(text)
                if should_open:
                    self.assertEqual(regions.get(2), "scoped")
                else:
                    self.assertNotIn(2, regions)


class RecordRegionTests(unittest.TestCase):
    def test_wave_elaborated_before_later_maps_record_and_does_not_block_later(self):
        """Adversarial where: a record region occurring earlier in the document
        must not consume or otherwise prevent a genuine '## Later' heading
        appearing after it from opening its own scoped region - the two region
        kinds are independent, not mutually exclusive states of one toggle."""
        text = "\n".join(
            [
                "# Plan",  # 1
                "",  # 2
                "## Wave 1 elaborated",  # 3
                "Body line describing what changed.",  # 4
                "",  # 5
                "## Later (intent only)",  # 6
                "- [ ] TASK-400: intent - files: []",  # 7
            ]
        ) + "\n"
        regions, _ = classify_lines(text)
        self.assertEqual(regions.get(4), "record")
        self.assertEqual(regions.get(7), "scoped")

    def test_wave_elaborated_heading_variants(self):
        """Adversarial where: the record-heading pattern must accept the
        shapes an author actually writes ('Wave' or 'Waves', a dash before
        'elaborated', a trailing date) while a promoted '(detailed)' wave
        heading - which carries no 'elaborated' token - must not falsely match
        just because it also starts with '## Wave'."""
        cases = [
            (
                "dash-elaborated-with-date maps record",
                "## Wave 1 - elaborated (2026-08-12)\nBody text.\n",
                "record",
            ),
            (
                "detailed wave heading does not map record",
                "## Wave 2 (detailed)\nBody text.\n",
                None,
            ),
        ]
        for name, text, expected in cases:
            with self.subTest(name=name):
                regions, _ = classify_lines(text)
                if expected is None:
                    self.assertNotIn(2, regions)
                else:
                    self.assertEqual(regions.get(2), expected)


class CommitUpfrontOverrideTests(unittest.TestCase):
    def test_task076_verbatim_spans_bullets_and_blank_line_then_releases(self):
        """Adversarial where: the override's continuation must track TASK-076's
        actual shape from the plan - a head line followed by three indented
        bullets and a trailing blank line - staying detailed through all of it,
        and must release back to scoped on the very next plain intent line
        rather than leaking scope past the blank line or past the block."""
        task076_head = (
            "- [ ] TASK-076: install refresh and acceptance - complexity: M, depends_on: "
            "TASK-071, TASK-072, TASK-073, TASK-074, TASK-075, TASK-077, files: [.claude/], "
            "decisions: [SPEC-015-rolling-wave-planning/D-04, ADR-009-rolling-wave-mechanism/D-01], "
            "commit-upfront: the acceptance battery is the same shape every Compass plan runs and "
            "its detail does not depend on anything wave 1 or wave 2 produces"
        )
        bullet_copy = (
            "  - Copy `plugin/cli`, `plugin/skills/*` and `plugin/templates/agents/*` into "
            "`.claude/` (or run `/compass:update`), then run acceptance from the installed copy, "
            "which is the only way the refresh is proven."
        )
        bullet_automated = (
            "  - Automated verification: `python -m unittest discover -s plugin/cli/tests` green "
            "with the new tests included (507 at plan start, higher here), green meaning no failures "
            "outside `compass test-checkpoint open-ids`; `python .claude/cli/compass doctor` exits 0; "
            "`python .claude/cli/compass coverage PLAN-008-rolling-wave --strict` exits 0 - under "
            "`--strict` that is the same statement as zero scoped rows, and every decision this plan "
            "named must be built by the time it closes; `python .claude/cli/compass lesson-coverage "
            "PLAN-008-rolling-wave` exits 0; `compass coverage` and `compass lesson-coverage` still "
            "exit 0 on PLAN-006 and PLAN-007."
        )
        bullet_manual = (
            "  - Manual verification: count what this plan actually cost the human - one approval, "
            "plus one delta per elaboration, plus any mid-build amendment - against the one-approval "
            "baseline SPEC-015 success criterion 3 sets, and for each wave delta answer whether "
            "reading it cost less attention than the mid-build amendment it was supposed to replace. "
            "Nobody has measured that before, which is the point of measuring it here. Then answer "
            "the other two criteria from the document itself: did at least two elaboration steps run, "
            "and did a knowledge item from an earlier wave demonstrably change a later wave's detail "
            "in a way the wave sections show. A plan whose wave sections record nothing that changed "
            "is the falsification signal, not a clean run."
        )
        text = "\n".join(
            [
                "## Later (intent only)",  # 1
                "- [ ] TASK-070: earlier intent - files: []",  # 2
                task076_head,  # 3
                bullet_copy,  # 4
                bullet_automated,  # 5
                bullet_manual,  # 6
                "",  # 7 - blank line inside the continuation
                "- [ ] TASK-090: later plain intent - files: []",  # 8
            ]
        ) + "\n"

        regions, _ = classify_lines(text)

        self.assertEqual(regions.get(2), "scoped")
        for detailed_line in (3, 4, 5, 6, 7):
            self.assertNotIn(detailed_line, regions)
        self.assertEqual(regions.get(8), "scoped")

    def test_override_terminates_on_task_line_or_unindented_prose(self):
        """Adversarial where: the contract names two distinct terminator
        shapes for the override - a following task line, and a following
        non-blank unindented line that is not a task line - and both must end
        the block rather than only the first being implemented."""
        cases = [
            (
                "next task line ends override",
                "\n".join(
                    [
                        "## Later (intent only)",  # 1
                        "- [ ] TASK-500: intent - files: [], commit-upfront: reason text",  # 2
                        "  continuation detail line",  # 3
                        "- [ ] TASK-501: next intent - files: []",  # 4
                    ]
                )
                + "\n",
            ),
            (
                "unindented prose line ends override",
                "\n".join(
                    [
                        "## Later (intent only)",  # 1
                        "- [ ] TASK-500: intent - files: [], commit-upfront: reason text",  # 2
                        "  continuation detail line",  # 3
                        "Plain prose sentence, not a task line.",  # 4
                    ]
                )
                + "\n",
            ),
        ]
        for name, text in cases:
            with self.subTest(name=name):
                regions, _ = classify_lines(text)
                self.assertNotIn(2, regions)
                self.assertNotIn(3, regions)
                self.assertEqual(regions.get(4), "scoped")

    def test_bare_and_backticked_mid_sentence_mentions_do_not_trigger(self):
        """Adversarial where: 'commit-upfront:' appearing mid-sentence - as
        plain prose or wrapped in backticks - must not be read as the trailing
        field trigger just because the token string is present somewhere on
        the line. TASK-071's real intent line names the flag inside backticks
        directly after a comma, which a naive comma-split-and-startswith check
        could misfire on if it checks containment instead of the segment's
        start; only a field that BEGINS with the token, after inline-code
        stripping, may trigger the override."""
        task071_head = (
            "- [ ] TASK-071: planner brief flips from \"specify all tasks\" to \"specify the "
            "current wave fully - the frontier judgment, no caps, never one task alone - list "
            "the rest as intent, flag `commit-upfront:` exceptions\"; it also states that intent "
            "lines distribute to `backlog.md` and never to `active.md`, pins the canonical "
            "`## Wave N elaborated` heading, and requires an intent line quoted inside a "
            "detailed block to be fenced or backticked - files: [plugin/templates/agents/planner.md], "
            "decisions: [SPEC-015-rolling-wave-planning/D-03, SPEC-015-rolling-wave-planning/D-04, "
            "ADR-009-rolling-wave-mechanism/D-01, ADR-009-rolling-wave-mechanism/D-03], "
            "lessons: [LESSON-human-practice-rationing-assumes-human-scarcity]"
        )
        bare_mention_head = (
            "- [ ] TASK-600: some intent, flag commit-upfront: exceptions noted - files: []"
        )
        cases = [
            ("task071 verbatim, backticked mid-sentence mention", task071_head),
            ("bare mid-sentence mention, no backticks", bare_mention_head),
        ]
        for name, head_line in cases:
            with self.subTest(name=name):
                text = "\n".join(["## Later (intent only)", head_line]) + "\n"
                regions, _ = classify_lines(text)
                self.assertEqual(regions.get(2), "scoped")


class FenceHandlingTests(unittest.TestCase):
    def test_later_heading_inside_fenced_block_does_not_open_region(self):
        """Adversarial where: a '## Later' heading quoted inside a fenced code
        example (as documentation of the format itself) must not open a real
        region - the classifier reads the fence-stripped text, not the raw
        text, for heading and field matches."""
        text = "\n".join(
            [
                "# Plan",  # 1
                "",  # 2
                "```",  # 3
                "## Later (intent only)",  # 4
                "This is inside a fence.",  # 5
                "```",  # 6
                "",  # 7
                "Detailed content after fence.",  # 8
            ]
        ) + "\n"
        regions, unterminated = classify_lines(text)
        self.assertEqual(regions, {})
        self.assertFalse(unterminated)

    def test_line_numbers_stay_aligned_across_fenced_block(self):
        """Adversarial where: fence stripping is line-count preserving, so a
        heading located after a fenced block must be found at its position in
        the ORIGINAL text. An implementation that stripped fence lines out
        entirely (rather than blanking them in place) would shift every
        subsequent line number down and misreport where the region opens."""
        text = "\n".join(
            [
                "# Plan",  # 1
                "",  # 2
                "```",  # 3
                "example content",  # 4
                "```",  # 5
                "",  # 6
                "## Later (intent only)",  # 7
                "- [ ] TASK-700: intent - files: []",  # 8
            ]
        ) + "\n"
        regions, unterminated = classify_lines(text)
        self.assertFalse(unterminated)
        self.assertEqual(regions.get(8), "scoped")
        self.assertNotIn(3, regions)
        self.assertNotIn(4, regions)

    def test_unterminated_fence_returns_flag_true(self):
        """Adversarial where: a fence that never closes runs to EOF and blanks
        everything after it (per strip_fenced_code), so the classifier must
        surface unterminated_fence=True rather than silently reporting an
        empty, seemingly-valid map that looks identical to a document with no
        Later section at all."""
        text = "# Plan\n\n```\nunterminated content\n## Later (intent only)\nmore content\n"
        regions, unterminated = classify_lines(text)
        self.assertTrue(unterminated)
        self.assertEqual(regions, {})


class NormalizationAndEdgeDocumentTests(unittest.TestCase):
    def test_crlf_input_produces_same_map_as_lf(self):
        """Adversarial where: CRLF line endings must be normalized before
        region detection, so a document edited on Windows classifies
        identically to the same content saved with LF endings rather than
        embedding a trailing '\\r' into heading or field text and breaking the
        match."""
        lf_text = "## Later (intent only)\n- [ ] TASK-800: intent - files: []\n"
        crlf_text = lf_text.replace("\n", "\r\n")
        lf_regions, lf_fence = classify_lines(lf_text)
        crlf_regions, crlf_fence = classify_lines(crlf_text)
        self.assertEqual(lf_regions, crlf_regions)
        self.assertEqual(lf_fence, crlf_fence)
        self.assertEqual(lf_regions.get(2), "scoped")

    def test_empty_and_frontmatter_only_documents_return_empty_map_without_raising(self):
        """Adversarial where: an empty string and a document that is only YAML
        frontmatter carry no headings and no body at all, the two smallest
        documents the classifier can be handed - a naive implementation
        indexing into an empty line list or assuming a body exists past the
        frontmatter delimiter would raise here instead of returning cleanly."""
        cases = [
            ("empty document", ""),
            ("frontmatter only", "---\ntitle: Example\nstatus: draft\n---\n"),
        ]
        for name, text in cases:
            with self.subTest(name=name):
                regions, unterminated = classify_lines(text)
                self.assertEqual(regions, {})
                self.assertFalse(unterminated)


if __name__ == "__main__":
    unittest.main()
