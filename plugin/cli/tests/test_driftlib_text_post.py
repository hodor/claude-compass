"""Adversarial tests for `driftlib.scan_index_lines` and `driftlib.scan_catalog`
aimed at branches of the implementation: link and line-shape parsing, summary
span detection for blame, blame line mapping with uncommitted edits, and
catalog row splitting and field comparison.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import driftlib  # noqa: E402
from test_driftlib_text import (  # noqa: E402
    CATALOG, EPOCH, INDEX, LESSON_A, SPEC, catalog_row, catalog_vault, commit,
    doc, entry, index_doc, lesson_file, new_repo, scan_catalog, scan_index,
    vault, write,
)


def raw_write(repo, rel, text):
    path = Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


class IndexLineShapeTests(unittest.TestCase):
    def test_link_forms_and_trailing_whitespace_resolve_to_the_same_target(self):
        """Adversarial where: resolving the raw link text instead of the
        name before `|` and `#`, or letting trailing blanks leak into the
        description, reports a faithful line as unresolved or drifted."""
        rows = {
            "alias": "- [[SPEC-001-alpha|Alpha]] - Alpha does X",
            "heading": "- [[SPEC-001-alpha#Goals]] - Alpha does X",
            "heading and alias": "- [[SPEC-001-alpha#Goals|Alpha]] - Alpha does X",
            "trailing spaces": "- [[SPEC-001-alpha]] - Alpha does X   ",
            "trailing tab": "- [[SPEC-001-alpha]] - Alpha does X\t",
            "indented bullet": "    - [[SPEC-001-alpha]] - Alpha does X",
            "extra spaces around dash": "- [[SPEC-001-alpha]]   -   Alpha does X",
        }
        for name, line in rows.items():
            with self.subTest(name):
                repo = vault(self, index_doc(line),
                             {SPEC: doc("summary: Alpha does X")})
                self.assertEqual(scan_index(repo), [])

    def test_crlf_index_and_target_files_compare_equal(self):
        """Adversarial where: splitting on "\\n" without normalising leaves
        a trailing carriage return on the description or on the summary
        fence, which reports drift on every line of a Windows-written vault."""
        repo = new_repo(self)
        raw_write(repo, INDEX, "# Index\r\n\r\n- [[SPEC-001-alpha]] - Alpha does X\r\n")
        raw_write(repo, SPEC,
                  "---\r\ntitle: Alpha\r\nsummary: Alpha does X\r\n---\r\n\r\nBody\r\n")
        commit(repo, "seed", ".compass")
        self.assertEqual(scan_index(repo), [])

    def test_summary_with_colons_quotes_and_unicode_matches_a_faithful_line(self):
        """Adversarial where: an unquoting or splitting bug on `: `, doubled
        apostrophes or non-ASCII text reports a line sync wrote as drift."""
        rows = {
            "colon inside double quotes": (
                'summary: "Plan: ship it"', "Plan: ship it"),
            "doubled apostrophe": (
                "summary: 'It''s fine'", "It's fine"),
            "escaped quote": (
                'summary: "Say \\"go\\" now"', 'Say "go" now'),
            "unquoted colon without space": (
                "summary: ratio 3:1 holds", "ratio 3:1 holds"),
            "non-ascii": (
                "summary: Café and über", "Café and über"),
            "dash inside description": (
                "summary: Alpha - beta - gamma", "Alpha - beta - gamma"),
            "em dash inside description": (
                "summary: Alpha — beta", "Alpha — beta"),
        }
        for name, (summary, desc) in rows.items():
            with self.subTest(name):
                repo = vault(self, index_doc(entry("SPEC-001-alpha", desc)),
                             {SPEC: doc(summary)})
                self.assertEqual(scan_index(repo), [])

    def test_block_scalar_summaries_fold_to_one_comparable_line(self):
        """Adversarial where: reading a block-scalar summary as its `>-`
        indicator or as only its first line reports every folded summary as
        drift; the reverse (ignoring a changed continuation) hides one."""
        folded = [
            "---", "title: Alpha", "summary: >-", "  Alpha does", "  X", "---", "",
        ]
        repo = vault(self, index_doc(entry("SPEC-001-alpha", "Alpha does X")),
                     {SPEC: folded})
        self.assertEqual(scan_index(repo), [])
        repo = vault(self, index_doc(entry("SPEC-001-alpha", "Alpha does Y")),
                     {SPEC: folded})
        found = scan_index(repo)
        self.assertEqual([r["class"] for r in found], ["index-drift"])
        self.assertEqual(found[0]["current_text"], "Alpha does X")

    def test_fenced_entry_lines_are_skipped_and_unfenced_ones_after_are_checked(self):
        """Adversarial where: a fence tracker that never closes, or that
        ignores tilde fences, either flags documentation examples or stops
        checking the rest of the index."""
        lines = index_doc(
            "```", entry("SPEC-001-alpha", "Wrong in backticks"), "```",
            "~~~", entry("SPEC-001-alpha", "Wrong in tildes"), "~~~",
            entry("SPEC-001-alpha", "Wrong outside"),
        )
        repo = vault(self, lines, {SPEC: doc("summary: Alpha does X")})
        found = scan_index(repo)
        self.assertEqual([(r["class"], r["old_text"]) for r in found],
                         [("index-drift", "Wrong outside")])

    def test_only_vault_root_archive_and_tmp_are_skipped(self):
        """Adversarial where: skipping every directory named `archive` or
        `tmp` at any depth, or skipping hidden directories only by name
        prefix mistakes, hides a real index below a domain folder."""
        stale = index_doc(entry("SPEC-001-alpha", "Stale"))
        docs = {
            SPEC: doc("summary: Real"),
            ".compass/specs/archive/index.md": stale,
            ".compass/tmp/index.md": stale,
            ".compass/archive/index.md": stale,
        }
        found = scan_index(vault(self, ["# Index"], docs))
        self.assertEqual([r["file"] for r in found],
                         [".compass/specs/archive/index.md"])

    def test_link_to_a_folder_index_artifact_is_resolved_and_blamed(self):
        """Adversarial where: treating a folder spec's `index.md` target as
        the ambiguous bare stem `index`, or blaming the wrong path, loses
        the target or its commit time."""
        folder_spec = ".compass/specs/SPEC-002-beta/index.md"
        repo = new_repo(self)
        write(repo, folder_spec, doc("summary: Beta real"))
        commit(repo, "target", ".compass", at=EPOCH + 50)
        write(repo, INDEX, index_doc(
            entry("specs/SPEC-002-beta/index", "Beta stale")))
        commit(repo, "index", ".compass", at=EPOCH)
        found = scan_index(repo)
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["target"], folder_spec)
        self.assertEqual(found[0]["newer"], "target")


class IndexLineBlameMappingTests(unittest.TestCase):
    def test_uncommitted_insertions_above_do_not_shift_commit_times(self):
        """Adversarial where: mapping blame lines through HEAD line numbers
        while the scan reads working-tree line numbers attributes the wrong
        commit to the index line and the summary after unrelated uncommitted
        edits."""
        repo = new_repo(self)
        write(repo, SPEC, doc("summary: Target text"))
        commit(repo, "target", ".compass", at=EPOCH + 100)
        write(repo, INDEX, index_doc(entry("SPEC-001-alpha", "Index text")))
        commit(repo, "index", ".compass", at=EPOCH)
        raw_write(repo, INDEX, "Uncommitted a\nUncommitted b\n"
                  + (Path(repo) / INDEX).read_text(encoding="utf-8"))
        raw_write(repo, SPEC, "---\nextra: 1\nextra2: 2\n"
                  + (Path(repo) / SPEC).read_text(encoding="utf-8")[4:])
        found = scan_index(repo)
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["line"], 7)
        self.assertEqual(found[0]["newer"], "target")

    def test_uncommitted_summary_edit_leaves_newer_undecided(self):
        """Adversarial where: treating the zero-hash blame commit as a real
        (epoch 0 or now) time decides `newer` from a time that no commit
        carries."""
        repo = new_repo(self)
        write(repo, SPEC, doc("summary: Target text"))
        write(repo, INDEX, index_doc(entry("SPEC-001-alpha", "Index text")))
        commit(repo, "seed", ".compass", at=EPOCH)
        write(repo, SPEC, doc("summary: Target text edited"))
        found = scan_index(repo)
        self.assertEqual(len(found), 1, found)
        self.assertIsNone(found[0]["newer"])

    def test_untracked_target_leaves_newer_undecided(self):
        """Adversarial where: a blame failure on an untracked target that
        raises, or that is swallowed into a time of 0, breaks the whole scan
        or reports `newer: index`."""
        repo = new_repo(self)
        write(repo, INDEX, index_doc(entry("SPEC-001-alpha", "Index text")))
        commit(repo, "index", ".compass", at=EPOCH)
        write(repo, SPEC, doc("summary: Target text"))
        found = scan_index(repo)
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["class"], "index-drift")
        self.assertIsNone(found[0]["newer"])

    def test_last_continuation_line_of_a_block_summary_decides_target_time(self):
        """Adversarial where: blaming only the `summary:` key line misses an
        edit to a continuation line, so a freshly reworded summary looks
        older than the index line."""
        repo = new_repo(self)
        write(repo, SPEC, ["---", "title: Alpha", "summary: >-", "  Alpha does", "  X",
                           "---", "", "Body"])
        commit(repo, "target", ".compass", at=EPOCH)
        write(repo, INDEX, index_doc(entry("SPEC-001-alpha", "Alpha does Y")))
        commit(repo, "index", ".compass", at=EPOCH + 10)
        write(repo, SPEC, ["---", "title: Alpha", "summary: >-", "  Alpha does", "  Z",
                           "---", "", "Body"])
        commit(repo, "reword", ".compass", at=EPOCH + 20)
        found = scan_index(repo)
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["current_text"], "Alpha does Z")
        self.assertEqual(found[0]["newer"], "target")

    def test_more_scattered_drift_lines_than_the_blame_range_cap_still_resolve(self):
        """Adversarial where: past the cap on `-L` ranges the implementation
        blames the whole file, and a mapping bug there (offsets, header
        parsing across commit groups) assigns times to the wrong lines."""
        count = driftlib._MAX_BLAME_RANGES + 20
        repo = new_repo(self)
        docs = {}
        entries = []
        for n in range(count):
            rel = f".compass/specs/SPEC-{n + 1:03d}-gen.md"
            docs[rel] = doc(f"summary: Real {n}")
            entries.append(entry(f"SPEC-{n + 1:03d}-gen", f"Stale {n}"))
            entries.append("")
        for rel, lines in docs.items():
            write(repo, rel, lines)
        commit(repo, "targets", ".compass", at=EPOCH + 100)
        write(repo, INDEX, index_doc(*entries))
        commit(repo, "index", ".compass", at=EPOCH)
        found = scan_index(repo)
        self.assertEqual(len(found), count)
        self.assertEqual({r["newer"] for r in found}, {"target"})
        self.assertEqual([r["line"] for r in found],
                         [5 + 2 * n for n in range(count)])


class CatalogRowTests(unittest.TestCase):
    def test_tags_list_forms_compare_by_content_not_syntax(self):
        """Adversarial where: comparing the raw tag text, or a scalar `a`
        against the list `[a]`, mis-states drift; a row whose tags are a
        block list must equal the same list written inline."""
        block_row = [
            '  - file: "LESSON-a.md"', "    status: active", "    category: process",
            "    area: testing", "    tags:", "      - a", "      - b",
            "    score: 6", '    summary: "Plain summary"',
        ]
        repo = catalog_vault(self, [block_row], {LESSON_A: lesson_file()})
        self.assertEqual(scan_catalog(repo), [])
        for name, row_tags, file_tags, drifts in (
            ("scalar row, one-item list file", "a", "[a]", True),
            ("one-item list row, scalar file", "[a]", "a", True),
            ("empty list row, no tags in file", "[]", "", False),
            ("quoted items inline", '["a", "b"]', "[a, b]", False),
        ):
            with self.subTest(name):
                repo = catalog_vault(
                    self, [catalog_row("LESSON-a.md", tags=row_tags)],
                    {LESSON_A: lesson_file(tags=file_tags)})
                found = scan_catalog(repo)
                self.assertEqual([r["field"] for r in found],
                                 ["tags"] if drifts else [])

    def test_score_padding_equal_but_non_numeric_or_decimal_scores_compared_as_text(self):
        """Adversarial where: int() coercion applied to every score raises on
        text like `high`; text coercion only misses zero padding."""
        for name, row_score, file_score, drifts in (
            ("zero padded", "06", "6", False),
            ("same non-numeric text", "high", "high", False),
            ("different non-numeric text", "high", "low", True),
            ("number versus word", "6", "high", True),
            ("negative", "-1", "-1", False),
        ):
            with self.subTest(name):
                repo = catalog_vault(
                    self, [catalog_row("LESSON-a.md", score=row_score)],
                    {LESSON_A: lesson_file(score=file_score)})
                found = scan_catalog(repo)
                self.assertEqual([r["field"] for r in found],
                                 ["score"] if drifts else [])

    def test_lesson_escalated_missing_from_the_row_is_drift_with_no_old_text(self):
        """Adversarial where: skipping `escalated` whenever either side is
        empty hides a lesson escalated after the catalog row was written."""
        repo = catalog_vault(self, [catalog_row("LESSON-a.md")],
                             {LESSON_A: lesson_file(escalated="2026-01-02")})
        found = scan_catalog(repo)
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["field"], "escalated")
        self.assertIsNone(found[0]["old_text"])
        self.assertEqual(found[0]["current_text"], "2026-01-02")
        self.assertEqual(found[0]["line"], 2)

    def test_row_with_comment_blank_lines_and_unquoted_file_is_split_correctly(self):
        """Adversarial where: a row splitter that ends a row at a blank or
        comment line, or that requires a quoted `file:`, drops every field
        after it and reports them as drift or loses the row."""
        row = [
            "  - file: LESSON-a.md", "    status: active", "    # kept note", "",
            "    category: process", "    area: testing", "    tags: [a, b]",
            "    score: 6", '    summary: "Plain summary"',
        ]
        second = catalog_row("LESSON-missing.md")
        repo = catalog_vault(self, [row, second], {LESSON_A: lesson_file()})
        found = scan_catalog(repo)
        self.assertEqual([(r["class"], r["line"]) for r in found],
                         [("missing", 11)])

    def test_summary_with_hash_colon_and_quotes_compares_equal_on_both_sides(self):
        """Adversarial where: comment stripping or `: ` splitting applied on
        one side only (row parse versus lesson frontmatter parse) turns a
        faithful row into drift."""
        for name, summary in (
            ("hash", '"Fix #12: ship it"'),
            ("unquoted hash", "Fix #12 now"),
            ("embedded double quotes", '"Say \\"go\\": now"'),
            ("single quotes", "'It''s: fine'"),
        ):
            with self.subTest(name):
                repo = catalog_vault(
                    self, [catalog_row("LESSON-a.md", summary=summary)],
                    {LESSON_A: lesson_file(summary=summary)})
                self.assertEqual(scan_catalog(repo), [])

    def test_crlf_catalog_and_lesson_compare_equal(self):
        """Adversarial where: a carriage return left on row values or on the
        row-splitting regexes reports every field of a Windows-written
        catalog as drift."""
        repo = new_repo(self)
        rows = "\r\n".join(["lessons:"] + catalog_row("LESSON-a.md")) + "\r\n"
        raw_write(repo, CATALOG, rows)
        raw_write(repo, LESSON_A, "\r\n".join(lesson_file()) + "\r\n")
        commit(repo, "seed", ".compass")
        self.assertEqual(scan_catalog(repo), [])

    def test_stale_field_reports_its_own_line_in_a_later_row(self):
        """Adversarial where: a field line number computed relative to the
        row, not the file, points the human at the wrong catalog line."""
        repo = catalog_vault(
            self,
            [catalog_row("LESSON-a.md"),
             catalog_row("LESSON-b.md", score=9)],
            {LESSON_A: lesson_file(),
             ".compass/lessons/LESSON-b.md": lesson_file(score=3)})
        found = scan_catalog(repo)
        self.assertEqual([(r["field"], r["line"]) for r in found], [("score", 14)])


if __name__ == "__main__":
    unittest.main()
