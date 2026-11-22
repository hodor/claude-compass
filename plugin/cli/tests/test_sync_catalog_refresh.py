"""Adversarial tests for sync refreshing existing lesson-catalog rows.

Themes: a row must follow its lesson file field by field; `summary` follows
only when the row's old text still lives in the file (the Data rule); rows
with no usable file are left alone; and a sync with nothing to change does
not touch the catalog at all.
"""

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lessonslib  # noqa: E402
from commands import sync as sync_cmd  # noqa: E402

HEADER = "# hand note above the rows\n"


def lesson_file(
    status="active",
    category="process",
    area="workflow",
    tags=("t1",),
    score=5,
    summary="file summary",
    escalated=None,
    body="body\n",
    drop=(),
):
    fields = {
        "title": "T",
        "type": "lesson",
        "status": status,
        "category": category,
        "area": area,
        "tags": "[" + ", ".join(tags) + "]",
        "score": str(score),
        "summary": '"' + summary.replace('"', '\\"') + '"',
    }
    for name in drop:
        del fields[name]
    lines = [f"{k}: {v}" for k, v in fields.items()]
    if escalated:
        lines.append(f"escalated: {escalated}")
    lines += ["created: 2026-08-30", "updated: 2026-08-30"]
    return "---\n" + "\n".join(lines) + "\n---\n\n" + body


def row_text(
    file,
    status="active",
    category="process",
    area="workflow",
    tags=("t1",),
    score=5,
    summary="file summary",
    escalated=None,
):
    lines = [
        f'  - file: "{file}"',
        f"    status: {status}",
        f"    category: {category}",
        f"    area: {area}",
        f'    tags: [{", ".join(tags)}]',
        f"    score: {score}",
        f'    summary: "{summary}"',
    ]
    if escalated:
        lines.append(f"    escalated: {escalated}")
    return "\n".join(lines) + "\n"


class RefreshFixture(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.project = tmp
        self.root = tmp / ".compass"
        for d in ("meta", "specs", "lessons"):
            (self.root / d).mkdir(parents=True)
        (self.root / "index.md").write_text("# Index\n", encoding="utf-8")
        (self.root / "active.md").write_text("# Active\n", encoding="utf-8")
        self.catalog_path = self.root / "meta" / "lessons-catalog.yaml"
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        if old is None:
            self.addCleanup(os.environ.pop, "CLAUDE_PROJECT_DIR", None)
        else:
            self.addCleanup(os.environ.__setitem__, "CLAUDE_PROJECT_DIR", old)

    def write_lesson(self, name, text):
        (self.root / "lessons" / name).write_text(text, encoding="utf-8")

    def write_catalog(self, *rows):
        self.catalog_path.write_text(
            HEADER + "lessons:\n" + "".join(rows), encoding="utf-8"
        )

    def catalog_bytes(self):
        return self.catalog_path.read_bytes()

    def rows(self):
        text = self.catalog_path.read_text(encoding="utf-8")
        return {r["file"]: r for r in lessonslib.parse_catalog(text)}

    def sync_output(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = sync_cmd.run([])
        self.assertEqual(code, 0)
        return out.getvalue()


class ScalarFieldRefreshTests(RefreshFixture):
    def test_each_field_that_differs_reaches_the_row_and_nothing_else_moves(self):
        """Adversarial where: sync skips filenames already in the catalog, so
        an edit to status, category, area, tags or score on the lesson file
        never reaches the row; or one field's rewrite clobbers a sibling."""
        base = dict(
            status="active",
            category="process",
            area="workflow",
            tags=("t1", "t2"),
            score=5,
        )
        cases = {
            "status": ("superseded", "status"),
            "category": ("domain", "category"),
            "area": ("methodology", "area"),
            "tags": (("t1", "t2", "t9"), "tags"),
            "score": (9, "score"),
            "score_one_step": (6, "score"),
        }
        for name, (new, field) in cases.items():
            with self.subTest(field=name):
                shutil.rmtree(self.root / "lessons")
                (self.root / "lessons").mkdir()
                edited = dict(base, **{field: new})
                self.write_lesson("LESSON-x.md", lesson_file(**edited))
                self.write_catalog(row_text("LESSON-x.md", **base))
                sync_cmd.sync(self.root)
                got = self.rows()["LESSON-x.md"]
                expect_tags = list(edited["tags"])
                self.assertEqual(got["status"], edited["status"])
                self.assertEqual(got["category"], edited["category"])
                self.assertEqual(got["area"], edited["area"])
                self.assertEqual(got["tags"], expect_tags)
                self.assertEqual(got["score"], edited["score"])
                self.assertEqual(got["summary"], "file summary")
                self.assertEqual(len(self.rows()), 1)

    def test_untouched_rows_and_hand_header_stay_byte_identical(self):
        """Adversarial where: refreshing one row by regenerating the whole
        catalog reorders rows or drops the hand-written header comment."""
        a = row_text("LESSON-a.md", score=3, summary="a sum")
        b_old = row_text("LESSON-b.md", score=4, summary="b sum")
        c = row_text("LESSON-c.md", tags=("x", "y"), score=7, summary="c sum")
        self.write_lesson("LESSON-a.md", lesson_file(score=3, summary="a sum"))
        self.write_lesson("LESSON-b.md", lesson_file(score=8, summary="b sum"))
        self.write_lesson(
            "LESSON-c.md", lesson_file(tags=("x", "y"), score=7, summary="c sum")
        )
        self.write_catalog(a, b_old, c)
        sync_cmd.sync(self.root)
        text = self.catalog_path.read_text(encoding="utf-8")
        self.assertEqual(
            text,
            HEADER + "lessons:\n" + a + row_text("LESSON-b.md", score=8, summary="b sum") + c,
        )


class EscalatedTests(RefreshFixture):
    def test_escalated_reaches_row_and_survives_a_second_sync(self):
        """Adversarial where: `escalated` is written once and then dropped by
        the next sync (the row rewrite forgets the optional field), or it
        never reaches an existing row at all."""
        self.write_lesson("LESSON-e.md", lesson_file(escalated="2026-09-02"))
        self.write_catalog(row_text("LESSON-e.md"))
        sync_cmd.sync(self.root)
        self.assertEqual(self.rows()["LESSON-e.md"]["escalated"], "2026-09-02")
        first = self.catalog_bytes()
        sync_cmd.sync(self.root)
        self.assertEqual(self.catalog_bytes(), first)

    def test_escalated_value_that_differs_is_rewritten(self):
        """Adversarial where: sync only adds `escalated` when the row has
        none, leaving a stale date when the file carries a different one."""
        self.write_lesson("LESSON-e.md", lesson_file(escalated="2026-10-11"))
        self.write_catalog(row_text("LESSON-e.md", escalated="2026-09-02"))
        sync_cmd.sync(self.root)
        self.assertEqual(self.rows()["LESSON-e.md"]["escalated"], "2026-10-11")


class SummaryRefreshTests(RefreshFixture):
    def test_summary_follows_file_only_when_old_text_survives_in_file(self):
        """Adversarial where: a summary edit that destroys the old text is
        copied into the row, losing the old wording (Data rule); or the
        preserved-text check looks only at the frontmatter and refuses edits
        whose old text moved into the body or `## Record (preserved)`."""
        record = "## Record (preserved)\n\n- the original wording lives here\n"
        cases = {
            "old text in record section": dict(
                old="the original wording lives here",
                new="reworded summary",
                body="line one\n\n" + record,
                updated=True,
            ),
            "old text in body": dict(
                old="wording kept in the body",
                new="reworded summary",
                body="wording kept in the body, verbatim\n",
                updated=True,
            ),
            "old text inside the new summary": dict(
                old="hooks fire",
                new="hooks fire from settings",
                body="body\n",
                updated=True,
            ),
            "old text nowhere in file": dict(
                old="vanished wording",
                new="reworded summary",
                body="body\n",
                updated=False,
            ),
            "old text is a near miss of body text": dict(
                old="wording kept in the body.",
                new="reworded summary",
                body="wording kept in the body\n",
                updated=False,
            ),
        }
        for name, c in cases.items():
            with self.subTest(case=name):
                self.write_lesson(
                    "LESSON-s.md", lesson_file(summary=c["new"], body=c["body"])
                )
                self.write_catalog(row_text("LESSON-s.md", summary=c["old"]))
                sync_cmd.sync(self.root)
                want = c["new"] if c["updated"] else c["old"]
                self.assertEqual(self.rows()["LESSON-s.md"]["summary"], want)

    def test_unpreserved_summary_is_reported_but_other_fields_still_refresh(self):
        """Adversarial where: a blocked summary silently aborts the whole row
        refresh (score stays stale), or is blocked without any report so the
        drift stays invisible."""
        self.write_lesson(
            "LESSON-u.md", lesson_file(score=9, area="methodology", summary="new words")
        )
        self.write_catalog(row_text("LESSON-u.md", score=5, summary="lost words"))
        out = self.sync_output()
        self.assertIn("summary_unpreserved: LESSON-u.md", out)
        got = self.rows()["LESSON-u.md"]
        self.assertEqual(got["summary"], "lost words")
        self.assertEqual(got["score"], 9)
        self.assertEqual(got["area"], "methodology")

    def test_report_is_silent_when_summaries_are_preserved_or_equal(self):
        """Adversarial where: `summary_unpreserved` is printed for every row
        or for rows whose summary already matches the file."""
        self.write_lesson("LESSON-same.md", lesson_file(summary="same words"))
        self.write_lesson(
            "LESSON-moved.md",
            lesson_file(summary="new words", body="## Record (preserved)\n\n- old words\n"),
        )
        self.write_catalog(
            row_text("LESSON-same.md", summary="same words"),
            row_text("LESSON-moved.md", summary="old words"),
        )
        self.assertNotIn("summary_unpreserved", self.sync_output())

    def test_summary_with_quotes_round_trips_into_the_row(self):
        """Adversarial where: the refreshed summary is written without
        YAML escaping, so a double quote in the lesson's summary corrupts the
        row or reads back as different text."""
        new = 'he said "stop" and it\'s done'
        self.write_lesson(
            "LESSON-q.md",
            lesson_file(summary=new, body="## Record (preserved)\n\n- plain old\n"),
        )
        self.write_catalog(row_text("LESSON-q.md", summary="plain old"))
        sync_cmd.sync(self.root)
        self.assertEqual(self.rows()["LESSON-q.md"]["summary"], new)


class UnrefreshableRowTests(RefreshFixture):
    def test_row_for_a_deleted_file_is_left_byte_identical(self):
        """Adversarial where: a row whose lesson file is gone is pruned or
        zeroed by the refresh, destroying catalog data (Data rule)."""
        orphan = row_text("LESSON-gone.md", score=4, tags=("o", "p"), summary="orphan")
        live_old = row_text("LESSON-live.md", score=2)
        self.write_lesson("LESSON-live.md", lesson_file(score=6))
        self.write_catalog(orphan, live_old)
        sync_cmd.sync(self.root)
        text = self.catalog_path.read_text(encoding="utf-8")
        self.assertIn(orphan, text)
        self.assertEqual(self.rows()["LESSON-live.md"]["score"], 6)

    def test_lesson_missing_any_required_field_leaves_its_row_untouched(self):
        """Adversarial where: a lesson whose frontmatter lacks one required
        field is refreshed with a blank or default value, overwriting a good
        row. One field is missing while the rest differ from the row."""
        for field in ("status", "category", "area", "tags", "score", "summary"):
            with self.subTest(missing=field):
                old = row_text("LESSON-m.md", score=2, summary="old words")
                self.write_lesson(
                    "LESSON-m.md",
                    lesson_file(
                        status="superseded",
                        category="domain",
                        area="elsewhere",
                        tags=("z",),
                        score=9,
                        summary="old words",
                        drop=(field,),
                    ),
                )
                self.write_catalog(old)
                sync_cmd.sync(self.root)
                self.assertEqual(
                    self.catalog_path.read_text(encoding="utf-8"),
                    HEADER + "lessons:\n" + old,
                )


class NoOpWriteTests(RefreshFixture):
    def _age(self):
        past = 1_500_000_000
        os.utime(self.catalog_path, (past, past))
        return self.catalog_path.stat().st_mtime_ns

    def test_second_sync_with_no_edits_leaves_bytes_and_mtime_unchanged(self):
        """Adversarial where: the catalog is rewritten on every sync even
        when no row differs, touching mtime and churning version control and
        file watchers."""
        self.write_lesson("LESSON-n.md", lesson_file(score=9, escalated="2026-09-02"))
        self.write_lesson("LESSON-o.md", lesson_file(summary="o sum"))
        self.write_catalog(
            row_text("LESSON-n.md", score=2), row_text("LESSON-o.md", summary="o sum")
        )
        sync_cmd.sync(self.root)
        settled = self.catalog_bytes()
        stamp = self._age()
        sync_cmd.sync(self.root)
        self.assertEqual(self.catalog_bytes(), settled)
        self.assertEqual(self.catalog_path.stat().st_mtime_ns, stamp)

    def test_catalog_with_only_unrefreshable_rows_is_not_rewritten(self):
        """Adversarial where: a blocked summary or a deleted-file row counts
        as a change and forces a write on every sync."""
        self.write_lesson("LESSON-u.md", lesson_file(summary="new words"))
        self.write_catalog(
            row_text("LESSON-u.md", summary="lost words"),
            row_text("LESSON-gone.md"),
        )
        before = self.catalog_bytes()
        stamp = self._age()
        sync_cmd.sync(self.root)
        self.assertEqual(self.catalog_bytes(), before)
        self.assertEqual(self.catalog_path.stat().st_mtime_ns, stamp)


class DuplicateRowTests(RefreshFixture):
    def test_duplicate_rows_collapse_and_the_survivor_is_refreshed(self):
        """Adversarial where: refreshing rows by filename breaks duplicate
        collapse, leaving two rows for one file or refreshing only one."""
        self.write_lesson("LESSON-d.md", lesson_file(score=8))
        self.write_catalog(
            row_text("LESSON-d.md", score=3),
            row_text("LESSON-other.md", score=1),
            row_text("LESSON-d.md", score=3),
        )
        report = sync_cmd.sync(self.root)
        text = self.catalog_path.read_text(encoding="utf-8")
        self.assertEqual(text.count('file: "LESSON-d.md"'), 1)
        self.assertEqual(self.rows()["LESSON-d.md"]["score"], 8)
        self.assertEqual(report["catalog_duplicates_removed"], 1)
        self.assertIn('file: "LESSON-other.md"', text)


if __name__ == "__main__":
    unittest.main()
