"""Adversarial tests for the catalog-row refresh code paths that only the
implementation reveals: quoting round trips, row-block splitting around
comments and a missing final newline, unit-folder lessons, filename
collisions, and idempotence of the rewrite.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import test_sync_catalog_refresh as base  # noqa: E402

UNIT_INDEX = (
    "---\ntitle: Unit X\ntype: unit\nstatus: active\n"
    "created: 2026-08-30\nupdated: 2026-08-30\ntags: [unitx]\n---\n\n# Unit X\n"
)


class QuotingRoundTripTests(base.RefreshFixture):
    def test_summary_with_quotes_backslash_and_unicode_settles_after_one_sync(self):
        """Adversarial where: the row's summary is unquoted for comparison but
        the file's summary is compared raw, so a summary holding `"`, `\\` or
        non-ASCII never compares equal and the row is rewritten (or reported
        unpreserved) on every sync."""
        summary = 'Use "head" not C:\\tmp; caf\u00e9 note: a # b'
        self.write_lesson(
            "LESSON-q.md", base.lesson_file(summary=summary, body="old text\n")
        )
        self.write_catalog(base.row_text("LESSON-q.md", summary="old text"))
        self.sync_output()
        self.assertEqual(self.rows()["LESSON-q.md"]["summary"], summary)
        settled = self.catalog_bytes()
        second = self.sync_output()
        self.assertNotIn("catalog rows refreshed", second)
        self.assertNotIn("summary_unpreserved", second)
        self.assertEqual(self.catalog_bytes(), settled)

    def test_row_already_in_generated_form_with_special_summary_is_not_touched(self):
        """Adversarial where: a row written by the generator for a summary
        containing `"` and `\\` is judged different from its own file and
        rewritten, so a freshly appended row churns on the next sync."""
        summary = 'say "hi" \\ bye'
        self.write_lesson("LESSON-g.md", base.lesson_file(summary=summary))
        self.write_catalog()
        self.sync_output()
        generated = self.catalog_bytes()
        out = self.sync_output()
        self.assertNotIn("catalog rows refreshed", out)
        self.assertEqual(self.catalog_bytes(), generated)

    def test_score_with_leading_zero_does_not_refresh_on_every_sync(self):
        """Adversarial where: the row's score is parsed to an int and compared
        as text with the file's raw `007`, so equal values differ forever and
        every sync reports a refresh and rewrites the catalog."""
        self.write_lesson("LESSON-z.md", base.lesson_file(score="007"))
        self.write_catalog(base.row_text("LESSON-z.md", score=4))
        self.sync_output()
        settled = self.catalog_bytes()
        again = self.sync_output()
        self.assertNotIn("catalog rows refreshed", again)
        self.assertEqual(self.catalog_bytes(), settled)


class RowBlockBoundaryTests(base.RefreshFixture):
    def test_comment_and_blank_line_after_a_refreshed_row_survive_byte_identical(self):
        """Adversarial where: the row-block split treats the first non-field
        line as the row's end; a refresh that rewrites the whole block drops a
        hand-written comment sitting between two rows."""
        self.write_lesson("LESSON-a.md", base.lesson_file(score=9))
        self.write_lesson("LESSON-b.md", base.lesson_file(score=3))
        self.write_catalog(
            base.row_text("LESSON-a.md", score=1),
            "\n# note between rows\n",
            base.row_text("LESSON-b.md", score=3),
        )
        self.sync_output()
        text = self.catalog_path.read_text(encoding="utf-8")
        self.assertIn("\n\n# note between rows\n  - file: \"LESSON-b.md\"", text)
        self.assertEqual(self.rows()["LESSON-a.md"]["score"], 9)

    def test_last_row_without_trailing_newline_is_refreshed_and_stays_parseable(self):
        """Adversarial where: the rewrite appends a newline only when the old
        row ended with one; the final row of a catalog lacking its closing
        newline is mishandled and merges with the following append or fails to
        parse."""
        self.write_lesson("LESSON-a.md", base.lesson_file(score=9))
        self.write_catalog(base.row_text("LESSON-a.md", score=1).rstrip("\n"))
        self.sync_output()
        self.assertEqual(self.rows()["LESSON-a.md"]["score"], 9)
        self.write_lesson("LESSON-b.md", base.lesson_file(score=2))
        self.write_lesson("LESSON-a.md", base.lesson_file(score=4))
        self.sync_output()
        rows = self.rows()
        self.assertEqual(rows["LESSON-a.md"]["score"], 4)
        self.assertEqual(rows["LESSON-b.md"]["score"], 2)

    def test_tag_spacing_difference_alone_does_not_rewrite_the_row(self):
        """Adversarial where: tags compared as raw text instead of parsed
        lists, so `[t1,t2]` versus the file's `[t1, t2]` rewrites a row whose
        meaning is identical."""
        self.write_lesson("LESSON-a.md", base.lesson_file(tags=("t1", "t2")))
        self.write_catalog(base.row_text("LESSON-a.md", tags=("t1", "t2")).replace(
            "[t1, t2]", "[t1,t2]"
        ))
        before = self.catalog_bytes()
        out = self.sync_output()
        self.assertNotIn("catalog rows refreshed", out)
        self.assertEqual(self.catalog_bytes(), before)


class EscalatedStateTests(base.RefreshFixture):
    def test_row_escalated_survives_when_file_has_none_while_score_refreshes(self):
        """Adversarial where: rebuilding the row from the file's fields drops
        an `escalated` line the file never carried, erasing the stamp
        `lesson-write` put on the row."""
        self.write_lesson("LESSON-a.md", base.lesson_file(score=8))
        self.write_catalog(
            base.row_text("LESSON-a.md", score=2, escalated="2026-11-01")
        )
        self.sync_output()
        row = self.rows()["LESSON-a.md"]
        self.assertEqual(row["score"], 8)
        self.assertEqual(row["escalated"], "2026-11-01")

    def test_quoted_row_escalated_with_no_file_value_is_left_byte_identical(self):
        """Adversarial where: the parsed escalation keeps its quotes, so a
        quoted row value never equals the unquoted one rebuilt from it and the
        row is rewritten on every sync."""
        self.write_lesson("LESSON-a.md", base.lesson_file())
        self.write_catalog(
            base.row_text("LESSON-a.md").replace(
                '    summary: "file summary"\n',
                '    summary: "file summary"\n    escalated: "2026-11-01"\n',
            )
        )
        before = self.catalog_bytes()
        out = self.sync_output()
        self.assertNotIn("catalog rows refreshed", out)
        self.assertEqual(self.catalog_bytes(), before)


class LocationTests(base.RefreshFixture):
    def test_lesson_inside_a_unit_folder_refreshes_its_root_catalog_row(self):
        """Adversarial where: refresh looks rows up only among top-level
        lesson files, so a unit's lesson whose score changed stays stale in
        the aggregated root catalog."""
        unit = self.root / "unitx"
        (unit / "lessons").mkdir(parents=True)
        (unit / "index.md").write_text(UNIT_INDEX, encoding="utf-8")
        (unit / "lessons" / "LESSON-u.md").write_text(
            base.lesson_file(score=8), encoding="utf-8"
        )
        self.write_catalog(base.row_text("LESSON-u.md", score=2))
        self.sync_output()
        self.assertEqual(self.rows()["LESSON-u.md"]["score"], 8)

    def test_colliding_filenames_refresh_from_the_first_path_in_vault_order(self):
        """Adversarial where: with two files sharing a name the refresh source
        depends on discovery order, so the row flips between the two files'
        scores across runs."""
        for folder, score in (("b", 2), ("a", 9)):
            d = self.root / "lessons" / folder
            d.mkdir()
            (d / "LESSON-x.md").write_text(
                base.lesson_file(score=score), encoding="utf-8"
            )
        self.write_catalog(base.row_text("LESSON-x.md", score=4))
        self.sync_output()
        self.assertEqual(self.rows()["LESSON-x.md"]["score"], 9)
        settled = self.catalog_bytes()
        self.sync_output()
        self.assertEqual(self.catalog_bytes(), settled)


if __name__ == "__main__":
    unittest.main()
