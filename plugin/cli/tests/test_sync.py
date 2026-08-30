"""Tests for `compass sync` in both human and hook modes."""

import datetime
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import capturelib  # noqa: E402
import lessonslib  # noqa: E402
import vaultlib  # noqa: E402
from commands import hot_path as hot_path_cmd  # noqa: E402
from commands import sync as sync_cmd  # noqa: E402
from commands import validate as validate_cmd  # noqa: E402

INDEX_TEMPLATE = """# Index

## Specs

- [[SPEC-001-existing]] - hand written description, do not touch

## Plans

## Research

## Decisions

## Lessons

## Handoffs
"""

CATALOG_TEMPLATE = """lessons:
  - file: "LESSON-known.md"
    status: active
    category: process
    area: workflow
    tags: [a, b]
    score: 5
    summary: "known lesson"
"""


def spec(name, tags="[x]", status="approved"):
    return (
        f"---\ntitle: {name}\ntype: spec\nstatus: {status}\narea: w\n"
        f"tags: {tags}\ncreated: 2026-06-14\nupdated: 2026-06-14\n---\n\nbody\n"
    )


def lesson(name, tags="[c]"):
    return (
        f"---\ntitle: {name}\ntype: lesson\nstatus: active\ncategory: process\n"
        f"area: workflow\ntags: {tags}\ncreated: 2026-06-14\nupdated: 2026-06-14\n"
        f"score: 5\nsummary: \"summary of {name}\"\n---\n\nbody\n"
    )


def research_doc(name, tags="[x]"):
    return (
        f"---\ntitle: {name}\ntype: research\nstatus: active\narea: w\n"
        f"tags: {tags}\ncreated: 2026-06-14\nupdated: 2026-06-14\n---\n\nbody\n"
    )


def folder_spec(name, summary):
    return (
        f"---\ntitle: {name}\ntype: spec\nstatus: approved\narea: w\ntags: [x]\n"
        f"children_count: 1\nsummary: \"{summary}\"\ncreated: 2026-06-14\n"
        f"updated: 2026-06-14\n---\n\nbody\n"
    )


UNIT_INDEX = """---
title: "Unit X"
type: unit
status: active
area: w
tags: [unitx]
created: 2026-07-24
updated: 2026-07-24
---

# Unit X
"""


class SyncFixture(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = tmp / ".compass"
        (self.root / "meta").mkdir(parents=True)
        (self.root / "specs").mkdir()
        (self.root / "lessons").mkdir()
        (self.root / "index.md").write_text(INDEX_TEMPLATE, encoding="utf-8")
        (self.root / "meta" / "lessons-catalog.yaml").write_text(CATALOG_TEMPLATE, encoding="utf-8")
        (self.root / "specs" / "SPEC-001-existing.md").write_text(spec("Existing"), encoding="utf-8")

    def write(self, rel, body):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def index_text(self):
        return (self.root / "index.md").read_text(encoding="utf-8")


class IndexSyncTests(SyncFixture):
    def test_orphan_spec_appended(self):
        self.write("specs/SPEC-002-new.md", spec("New"))
        sync_cmd.sync(self.root)
        self.assertIn("[[SPEC-002-new]]", self.index_text())

    def test_archived_spec_not_appended(self):
        self.write("specs/SPEC-003-old.md", spec("Old", status="archived"))
        sync_cmd.sync(self.root)
        self.assertNotIn("[[SPEC-003-old]]", self.index_text())

    def test_human_description_preserved(self):
        self.write("specs/SPEC-002-new.md", spec("New"))
        sync_cmd.sync(self.root)
        self.assertIn("hand written description, do not touch", self.index_text())
        # existing entry appears exactly once
        self.assertEqual(self.index_text().count("[[SPEC-001-existing]]"), 1)


class CatalogSyncTests(SyncFixture):
    def test_new_lesson_row_appended(self):
        self.write("lessons/LESSON-fresh.md", lesson("Fresh"))
        added = sync_cmd.sync(self.root)["catalog_added"]
        self.assertEqual(added, 1)
        self.assertIn("LESSON-fresh.md", (self.root / "meta" / "lessons-catalog.yaml").read_text(encoding="utf-8"))

    def test_known_lesson_not_duplicated(self):
        self.write("lessons/LESSON-known.md", lesson("Known"))
        added = sync_cmd.sync(self.root)["catalog_added"]
        self.assertEqual(added, 0)


class CatalogEmptyMarkerTests(SyncFixture):
    """`meta/lessons-catalog.yaml` starts life as `lessons: []` (the
    /compass:setup skeleton). The marker is valid YAML only while the
    catalog holds zero rows; appending a row under it without first
    replacing it produces an unparseable file (issue #5)."""

    def setUp(self):
        super().setUp()
        (self.root / "meta" / "lessons-catalog.yaml").write_text("lessons: []\n", encoding="utf-8")

    def _catalog_text(self):
        return (self.root / "meta" / "lessons-catalog.yaml").read_text(encoding="utf-8")

    def test_first_row_replaces_the_empty_marker(self):
        self.write("lessons/LESSON-fresh.md", lesson("Fresh"))
        added = sync_cmd.sync(self.root)["catalog_added"]
        self.assertEqual(added, 1)
        text = self._catalog_text()
        self.assertNotIn("lessons: []", text)
        self.assertTrue(text.startswith("lessons:\n"))
        self.assertIn('file: "LESSON-fresh.md"', text)

    def test_first_row_catalog_parses_cleanly(self):
        self.write("lessons/LESSON-fresh.md", lesson("Fresh"))
        sync_cmd.sync(self.root)
        text = self._catalog_text()
        # lessonslib's row scanner never inspects the header line, so it
        # would tolerate a row wrongly left under `lessons: []`; assert the
        # header itself is the plain block-sequence form.
        self.assertEqual(text.splitlines()[0], "lessons:")
        rows = lessonslib.parse_catalog(text)
        self.assertEqual([r["file"] for r in rows], ["LESSON-fresh.md"])

    def test_sync_with_no_lessons_leaves_the_empty_marker_untouched(self):
        sync_cmd.sync(self.root)
        self.assertEqual(self._catalog_text(), "lessons: []\n")


class CatalogCorruptedHealTests(SyncFixture):
    """A catalog already in the corrupted shape - a row nested under the
    `lessons: []` marker, from a version of the writer carrying issue #5 -
    heals to valid YAML on the next sync, even when no new row is being
    appended in that run."""

    CORRUPTED = (
        'lessons: []\n'
        '  - file: "LESSON-known.md"\n'
        '    status: active\n'
        '    category: process\n'
        '    area: workflow\n'
        '    tags: [a, b]\n'
        '    score: 5\n'
        '    summary: "known lesson"\n'
    )

    def setUp(self):
        super().setUp()
        (self.root / "meta" / "lessons-catalog.yaml").write_text(self.CORRUPTED, encoding="utf-8")

    def test_marker_is_replaced_with_no_new_rows_pending(self):
        added = sync_cmd.sync(self.root)["catalog_added"]
        self.assertEqual(added, 0)
        text = (self.root / "meta" / "lessons-catalog.yaml").read_text(encoding="utf-8")
        self.assertNotIn("lessons: []", text)
        self.assertTrue(text.startswith("lessons:\n"))
        self.assertEqual(text.count('file: "LESSON-known.md"'), 1)

    def test_lessonslib_already_tolerates_the_corrupted_shape(self):
        # The row scanner matches on the row lines only and never inspects
        # the header, so the corrupted shape was already readable before the
        # writer-side heal - confirms no parser change is needed here.
        rows = lessonslib.parse_catalog(self.CORRUPTED)
        self.assertEqual(rows[0]["file"], "LESSON-known.md")


class TagIndexTests(SyncFixture):
    def test_tag_index_format_and_content(self):
        self.write("specs/SPEC-002-new.md", spec("New", tags="[rendering, tile-editor]"))
        sync_cmd.sync(self.root)
        text = (self.root / "meta" / "tag-index.yaml").read_text(encoding="utf-8")
        self.assertIn("tags:\n", text)
        self.assertIn("  rendering:\n  - specs/SPEC-002-new.md\n", text)
        self.assertIn("  tile-editor:\n", text)


class IdempotencyTests(SyncFixture):
    def _snapshot(self):
        return {
            p.relative_to(self.root).as_posix(): p.read_bytes()
            for p in self.root.rglob("*") if p.is_file()
        }

    def test_second_sync_is_a_noop(self):
        self.write("specs/SPEC-002-new.md", spec("New", tags="[rendering]"))
        self.write("lessons/LESSON-fresh.md", lesson("Fresh"))
        sync_cmd.sync(self.root)
        first = self._snapshot()
        sync_cmd.sync(self.root)
        self.assertEqual(self._snapshot(), first)


class CapTests(SyncFixture):
    def test_index_line_cap_warning(self):
        big = INDEX_TEMPLATE + "\n".join(f"- filler {i}" for i in range(300))
        (self.root / "index.md").write_text(big, encoding="utf-8")
        warnings = sync_cmd.sync(self.root)["caps"]
        self.assertIn("index.md", warnings)
        self.assertIn(sync_cmd.INDEX_WARNING, self.index_text())


class MissingIndexFileTests(SyncFixture):
    """A vault whose `index.md` does not exist (issue #4, the hook's
    never-crash contract): sync creates the same minimal skeleton
    /compass:setup writes instead of raising FileNotFoundError."""

    def setUp(self):
        super().setUp()
        (self.root / "index.md").unlink()

    def test_sync_creates_index_instead_of_crashing(self):
        report = sync_cmd.sync(self.root)  # must not raise
        self.assertIn("[[SPEC-001-existing]]", self.index_text())
        self.assertEqual(report["index_added"], {"specs": 1})

    def test_created_index_carries_title_frontmatter(self):
        sync_cmd.sync(self.root)
        text = self.index_text()
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("type: index", text)

    def test_empty_vault_missing_index_still_gets_created(self):
        # No artifacts at all: the per-section loop adds nothing to `added`,
        # but the file must still be written so later steps (and validate)
        # don't hit the same missing-file hole this run.
        (self.root / "specs" / "SPEC-001-existing.md").unlink()
        sync_cmd.sync(self.root)
        self.assertTrue((self.root / "index.md").is_file())

    def test_hook_mode_does_not_crash_and_still_suppresses_output(self):
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.root.parent)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
            else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )
        self.write("specs/SPEC-002-new.md", spec("New"))
        self.addCleanup(setattr, sys, "stdin", sys.stdin)
        sys.stdin = io.StringIO(json.dumps({
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.root / "specs" / "SPEC-002-new.md")},
        }))
        out = io.StringIO()
        from contextlib import redirect_stdout
        with redirect_stdout(out):
            code = sync_cmd.run(["--hook"])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), json.dumps({"suppressOutput": True}))
        self.assertTrue((self.root / "index.md").is_file())


class CheckCapsMissingIndexTests(unittest.TestCase):
    """`_check_caps` re-reads index.md independently of `_sync_index`; it
    must not crash either when called on a vault with no index.md yet."""

    def test_check_caps_does_not_crash_when_index_missing(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        root = tmp / ".compass"
        (root / "meta").mkdir(parents=True)
        warnings = sync_cmd._check_caps(root, [])
        self.assertEqual(warnings, [])


class LogCleanupTests(SyncFixture):
    def test_old_logs_move_to_archive_recent_stay(self):
        (self.root / "tmp").mkdir()
        old = self.root / "tmp" / "extraction-log-old.md"
        new = self.root / "tmp" / "extraction-log-new.md"
        old.write_text("the audit trail", encoding="utf-8")
        new.write_text("x", encoding="utf-8")
        old_time = time.time() - 40 * 86400
        os.utime(old, (old_time, old_time))
        moved = sync_cmd.sync(self.root)["logs_deleted"]
        self.assertEqual(moved, 1)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())
        archived = self.root / "archive" / "logs" / "extraction-log-old.md"
        self.assertEqual(archived.read_text(encoding="utf-8"), "the audit trail")

    def test_archive_name_collision_keeps_both(self):
        (self.root / "tmp").mkdir()
        (self.root / "archive" / "logs").mkdir(parents=True)
        (self.root / "archive" / "logs" / "extraction-log-old.md").write_text(
            "earlier archive", encoding="utf-8"
        )
        old = self.root / "tmp" / "extraction-log-old.md"
        old.write_text("later archive", encoding="utf-8")
        old_time = time.time() - 40 * 86400
        os.utime(old, (old_time, old_time))
        sync_cmd.sync(self.root)
        logs = sorted((self.root / "archive" / "logs").glob("extraction-log-old*.md"))
        self.assertEqual(len(logs), 2)
        contents = {p.read_text(encoding="utf-8") for p in logs}
        self.assertEqual(contents, {"earlier archive", "later archive"})


class CaptureLogRetentionTests(SyncFixture):
    """`_clean_logs` prunes `capture-log.jsonl` row-level at 365 days, on a
    horizon independent of the 30-day `extraction-log-*.md` file pruning
    above - a fleet fire-rate measurement needs to look back further than a
    month even while extraction logs age out on their own shorter clock."""

    def _row(self, days_old, event="opened", **fields):
        at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_old)
        row = {"at": at.isoformat().replace("+00:00", "Z"), "event": event}
        row.update(fields)
        return row

    def _write_capture_log(self, rows):
        (self.root / "tmp").mkdir(exist_ok=True)
        path = self.root / "tmp" / "capture-log.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        return path

    def test_31_day_old_extraction_log_pruned_31_day_old_capture_row_kept(self):
        (self.root / "tmp").mkdir(exist_ok=True)
        old_extraction = self.root / "tmp" / "extraction-log-old.md"
        old_extraction.write_text("x", encoding="utf-8")
        old_time = time.time() - 31 * 86400
        os.utime(old_extraction, (old_time, old_time))

        path = self._write_capture_log([self._row(31, id="OPP-1", kind="interval", triggers=[])])

        report = sync_cmd.sync(self.root)
        self.assertEqual(report["logs_deleted"], 1)
        self.assertFalse(old_extraction.exists())
        self.assertEqual(report["capture_log_pruned"], 0)
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(rows), 1)

    def test_366_day_old_capture_row_pruned(self):
        path = self._write_capture_log([
            self._row(366, id="OPP-old", kind="interval", triggers=[]),
            self._row(1, id="OPP-new", kind="interval", triggers=[]),
        ])
        report = sync_cmd.sync(self.root)
        self.assertEqual(report["capture_log_pruned"], 1)
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(rows), 1)
        archive = self.root / "archive" / "logs" / "capture-log-archive.jsonl"
        aged = [json.loads(l) for l in archive.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(aged), 1)
        self.assertEqual(aged[0]["id"], "OPP-old")
        self.assertEqual(rows[0]["id"], "OPP-new")

    def test_malformed_capture_log_line_ages_out_preserved_raw(self):
        (self.root / "tmp").mkdir(exist_ok=True)
        path = self.root / "tmp" / "capture-log.jsonl"
        path.write_text(
            "{not valid json\n" + json.dumps(self._row(1, id="OPP-new", kind="interval", triggers=[])) + "\n",
            encoding="utf-8",
        )
        report = sync_cmd.sync(self.root)
        self.assertEqual(report["capture_log_pruned"], 1)
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "OPP-new")
        # The unjudgeable line is archived verbatim, not destroyed.
        archive = self.root / "archive" / "logs" / "capture-log-archive.jsonl"
        self.assertIn("{not valid json", archive.read_text(encoding="utf-8"))

    def test_no_capture_log_is_a_noop(self):
        report = sync_cmd.sync(self.root)
        self.assertEqual(report["capture_log_pruned"], 0)

    def test_pruned_capture_log_is_lf_only(self):
        self._write_capture_log([
            self._row(366, id="OPP-old", kind="interval", triggers=[]),
            self._row(1, id="OPP-new", kind="interval", triggers=[]),
        ])
        sync_cmd.sync(self.root)
        raw = (self.root / "tmp" / "capture-log.jsonl").read_bytes()
        self.assertNotIn(b"\r\n", raw)


class WorkerLogRetentionTests(SyncFixture):
    """TASK-092: sync additionally sweeps `.compass/tmp/worker-logs/*.log` on
    the same 30-day horizon as `extraction-log-*.md` (ADR-013 D-07's pruning
    clause, "previously unowned" per PLAN-010's own task bullet). The plan
    ties this to "the existing 30-day extraction-log retention" but gives no
    literal report-key shape for the deleted count, so these assertions read
    disk state directly rather than a specific `report[...]` key - the
    unambiguous half of the claim."""

    def test_31_day_old_worker_log_deleted_recent_kept(self):
        logs_dir = self.root / "tmp" / "worker-logs"
        logs_dir.mkdir(parents=True)
        old = logs_dir / "OPP-old.log"
        new = logs_dir / "OPP-new.log"
        old.write_text("x", encoding="utf-8")
        new.write_text("x", encoding="utf-8")
        old_time = time.time() - 31 * 86400
        os.utime(old, (old_time, old_time))
        sync_cmd.sync(self.root)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())

    def test_29_day_old_worker_log_kept(self):
        """Adversarial where: a worker-log sweep reusing a stricter cutoff
        than extraction logs by mistake would delete this file one day
        early; 29 days sits inside the 30-day horizon and must survive -
        the boundary the 31-day case above brackets from the other side."""
        logs_dir = self.root / "tmp" / "worker-logs"
        logs_dir.mkdir(parents=True)
        recent = logs_dir / "OPP-recent.log"
        recent.write_text("x", encoding="utf-8")
        recent_time = time.time() - 29 * 86400
        os.utime(recent, (recent_time, recent_time))
        sync_cmd.sync(self.root)
        self.assertTrue(recent.exists())


class ResolutionMatchingTests(SyncFixture):
    def test_stem_entry_for_folder_child_not_reappended(self):
        self.write("specs/SPEC-004-pack/index.md", folder_spec("Pack", "the pack folder"))
        self.write("specs/SPEC-004-pack/SPEC-001-inner.md", spec("Inner"))
        seeded = INDEX_TEMPLATE.replace(
            "## Plans", "- [[SPEC-001-inner]] - noted by hand\n\n## Plans"
        )
        (self.root / "index.md").write_text(seeded, encoding="utf-8")
        sync_cmd.sync(self.root)
        self.assertEqual(self.index_text().count("[[SPEC-001-inner]]"), 1)
        self.assertIn("noted by hand", self.index_text())

    def test_root_folder_children_get_bare_stem_links(self):
        self.write("specs/SPEC-004-pack/index.md", folder_spec("Pack", "the pack folder"))
        self.write("specs/SPEC-004-pack/SPEC-001-inner.md", spec("Inner"))
        sync_cmd.sync(self.root)
        text = self.index_text()
        self.assertIn("  - [[SPEC-001-inner]] - Inner", text)
        self.assertIn("- [[SPEC-004-pack]] (folder, 1 children) - the pack folder", text)
        self.assertNotIn("[[SPEC-004-pack/SPEC-001-inner]]", text)


class NestedDocWikilinkTests(SyncFixture):
    """A root-level doc nested under a subfolder with no folder-spec
    `index.md` sibling (issue #1): sync and validate must resolve the same
    link form, and re-running sync must not duplicate the entry."""

    def setUp(self):
        super().setUp()
        (self.root / "research").mkdir()

    def test_loose_nested_doc_gets_full_vault_relative_link(self):
        self.write("research/sub/note.md", research_doc("Note"))
        sync_cmd.sync(self.root)
        text = self.index_text()
        self.assertIn("[[research/sub/note]]", text)
        self.assertNotIn("[[sub/note]]", text)
        self.assertNotIn("[[note]] -", text)

    def test_loose_nested_doc_link_resolves_clean_in_validate(self):
        self.write("research/sub/note.md", research_doc("Note"))
        sync_cmd.sync(self.root)
        _, warnings = validate_cmd.check_vault(self.root)
        broken = [w for w in warnings if w.startswith("broken_wikilink")]
        self.assertEqual(broken, [])

    def test_second_sync_does_not_duplicate_the_entry(self):
        self.write("research/sub/note.md", research_doc("Note"))
        sync_cmd.sync(self.root)
        sync_cmd.sync(self.root)
        self.assertEqual(self.index_text().count("[[research/sub/note]]"), 1)

    def test_two_loose_nested_docs_sharing_a_stem_both_link_uniquely(self):
        # Two different subfolders under the same type dir, neither a
        # folder-spec, can reuse a filename without conflicting on disk -
        # the exact collision the type-dir-omitted bare stem could not tell
        # apart.
        self.write("research/sub-a/note.md", research_doc("Note A"))
        self.write("research/sub-b/note.md", research_doc("Note B"))
        sync_cmd.sync(self.root)
        text = self.index_text()
        self.assertIn("[[research/sub-a/note]]", text)
        self.assertIn("[[research/sub-b/note]]", text)
        _, warnings = validate_cmd.check_vault(self.root)
        self.assertEqual([w for w in warnings if "ambiguous" in w or "broken" in w], [])

    def test_existing_type_dir_omitted_link_is_rewritten_not_duplicated(self):
        self.write("research/sub/note.md", research_doc("Note"))
        seeded = self.index_text().replace(
            "## Research", "## Research\n\n- [[sub/note]] - hand written description, do not touch"
        )
        (self.root / "index.md").write_text(seeded, encoding="utf-8")
        sync_cmd.sync(self.root)
        text = self.index_text()
        self.assertEqual(text.count("[[research/sub/note]]"), 1)
        self.assertNotIn("[[sub/note]]", text)
        self.assertIn("hand written description, do not touch", text)

    def test_existing_link_with_alias_suffix_is_rewritten_preserving_the_alias(self):
        self.write("research/sub/note.md", research_doc("Note"))
        seeded = self.index_text().replace(
            "## Research", "## Research\n\n- [[sub/note|My Note]] - hand written"
        )
        (self.root / "index.md").write_text(seeded, encoding="utf-8")
        sync_cmd.sync(self.root)
        text = self.index_text()
        self.assertIn("[[research/sub/note|My Note]]", text)
        self.assertNotIn("[[sub/note", text)
        _, warnings = validate_cmd.check_vault(self.root)
        self.assertEqual([w for w in warnings if w.startswith("broken_wikilink")], [])

    def test_existing_link_with_heading_suffix_is_rewritten_preserving_the_heading(self):
        self.write("research/sub/note.md", research_doc("Note"))
        seeded = self.index_text().replace(
            "## Research", "## Research\n\n- [[sub/note#Details]] - hand written"
        )
        (self.root / "index.md").write_text(seeded, encoding="utf-8")
        sync_cmd.sync(self.root)
        text = self.index_text()
        self.assertIn("[[research/sub/note#Details]]", text)
        self.assertNotIn("[[sub/note", text)
        _, warnings = validate_cmd.check_vault(self.root)
        self.assertEqual([w for w in warnings if w.startswith("broken_wikilink")], [])

    def test_folder_spec_child_still_gets_bare_stem_link(self):
        # A subfolder that IS a folder-spec (carries its own index.md) keeps
        # the existing bare-stem convention for its children, unaffected by
        # the loose-nested-doc fix.
        self.write("research/pack/index.md", folder_spec("Pack", "the pack folder"))
        self.write("research/pack/RESEARCH-inner.md", research_doc("Inner"))
        sync_cmd.sync(self.root)
        text = self.index_text()
        self.assertIn("[[RESEARCH-inner]]", text)
        self.assertNotIn("[[research/pack/RESEARCH-inner]]", text)


class UnitSyncTests(SyncFixture):
    def make_unit(self):
        self.write("unitx/index.md", UNIT_INDEX)
        self.write("unitx/specs/SPEC-001-alpha.md", spec("Alpha", tags="[alpha]"))
        self.write("unitx/lessons/LESSON-unit-fresh.md", lesson("Unit Fresh"))

    def _snapshot(self):
        return {
            p.relative_to(self.root).as_posix(): p.read_bytes()
            for p in self.root.rglob("*") if p.is_file()
        }

    def test_unit_entries_path_qualified_under_unit_section(self):
        self.make_unit()
        sync_cmd.sync(self.root)
        text = self.index_text()
        self.assertIn("## Unit X", text)
        section = text.split("## Unit X", 1)[1]
        # Unit lessons aggregate into the root catalog like every lesson;
        # the catalog is their index, so no per-lesson line appears here.
        self.assertNotIn("LESSON-unit-fresh", section)
        self.assertIn("- [[unitx/specs/SPEC-001-alpha]] - Alpha", section)
        self.assertNotIn("[[SPEC-001-alpha]] -", text.split("## Unit X", 1)[0])

    def test_unit_folder_spec_links_by_folder_path(self):
        self.make_unit()
        self.write("unitx/specs/SPEC-002-sub/index.md", folder_spec("Sub", "the sub folder"))
        self.write("unitx/specs/SPEC-002-sub/SPEC-001-leaf.md", spec("Leaf"))
        sync_cmd.sync(self.root)
        text = self.index_text()
        self.assertIn("- [[unitx/specs/SPEC-002-sub]] (folder, 1 children) - the sub folder", text)
        self.assertIn("  - [[unitx/specs/SPEC-002-sub/SPEC-001-leaf]] - Leaf", text)

    def test_sync_written_links_validate_clean(self):
        self.make_unit()
        self.write("unitx/specs/SPEC-002-sub/index.md", folder_spec("Sub", "the sub folder"))
        self.write("unitx/specs/SPEC-002-sub/SPEC-001-leaf.md", spec("Leaf"))
        sync_cmd.sync(self.root)
        _, warnings = validate_cmd.check_vault(self.root)
        index_broken = [w for w in warnings if w.startswith("broken_wikilink: index.md")]
        self.assertEqual(index_broken, [])

    def test_unit_lesson_reaches_catalog(self):
        self.make_unit()
        report = sync_cmd.sync(self.root)
        self.assertEqual(report["catalog_added"], 1)
        self.assertEqual(report["catalog_collisions"], [])
        catalog = (self.root / "meta" / "lessons-catalog.yaml").read_text(encoding="utf-8")
        self.assertIn('file: "LESSON-unit-fresh.md"', catalog)

    def test_duplicate_lesson_filename_reported_not_overwritten(self):
        self.make_unit()
        self.write("lessons/LESSON-unit-fresh.md", lesson("Root Twin"))
        report = sync_cmd.sync(self.root)
        self.assertEqual(
            report["catalog_collisions"],
            ["LESSON-unit-fresh.md: lessons/LESSON-unit-fresh.md, unitx/lessons/LESSON-unit-fresh.md"],
        )
        catalog = (self.root / "meta" / "lessons-catalog.yaml").read_text(encoding="utf-8")
        self.assertEqual(catalog.count('file: "LESSON-unit-fresh.md"'), 1)
        self.assertIn("summary of Root Twin", catalog)

    def test_unit_tags_vault_relative_in_tag_index(self):
        self.make_unit()
        sync_cmd.sync(self.root)
        text = (self.root / "meta" / "tag-index.yaml").read_text(encoding="utf-8")
        self.assertIn("  alpha:\n  - unitx/specs/SPEC-001-alpha.md\n", text)

    def test_second_sync_with_unit_is_a_noop(self):
        self.make_unit()
        sync_cmd.sync(self.root)
        first = self._snapshot()
        sync_cmd.sync(self.root)
        self.assertEqual(self._snapshot(), first)

    def test_lesson_cap_counts_unit_lessons(self):
        self.make_unit()
        self.write("lessons/LESSON-rootie.md", lesson("Rootie"))
        old_cap = sync_cmd.LESSON_COUNT_CAP
        sync_cmd.LESSON_COUNT_CAP = 1
        self.addCleanup(setattr, sync_cmd, "LESSON_COUNT_CAP", old_cap)
        warnings = sync_cmd.sync(self.root)["caps"]
        self.assertIn("lessons-catalog.yaml", warnings)


class HookModeTests(SyncFixture):
    def _set_env(self):
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.root.parent)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
            else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )

    def _feed_stdin(self, payload):
        self.addCleanup(setattr, sys, "stdin", sys.stdin)
        sys.stdin = io.StringIO(json.dumps(payload))

    def test_normal_write_runs_sync_and_suppresses_output(self):
        self._set_env()
        self.write("specs/SPEC-002-new.md", spec("New"))
        self._feed_stdin({
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.root / "specs" / "SPEC-002-new.md")},
        })
        out = io.StringIO()
        from contextlib import redirect_stdout
        with redirect_stdout(out):
            code = sync_cmd.run(["--hook"])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), json.dumps({"suppressOutput": True}))
        self.assertIn("[[SPEC-002-new]]", self.index_text())

    def test_non_vault_write_is_noop(self):
        self._set_env()
        self.write("specs/SPEC-002-new.md", spec("New"))
        self._feed_stdin({
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "/some/other/project/main.py"},
        })
        code = sync_cmd.run(["--hook"])
        self.assertEqual(code, 0)
        self.assertNotIn("[[SPEC-002-new]]", self.index_text())

    def test_own_output_write_is_noop(self):
        self._set_env()
        self.write("specs/SPEC-002-new.md", spec("New"))
        self._feed_stdin({
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.root / "index.md")},
        })
        code = sync_cmd.run(["--hook"])
        self.assertEqual(code, 0)
        # loop guard: sync did not run, so the orphan was NOT linked
        self.assertNotIn("[[SPEC-002-new]]", self.index_text())

    def test_exception_returns_1_not_2(self):
        self._set_env()
        self._feed_stdin({
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.root / "specs" / "SPEC-002-new.md")},
        })
        original = sync_cmd.sync
        sync_cmd.sync = lambda root: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            code = sync_cmd.run(["--hook"])
        finally:
            sync_cmd.sync = original
        self.assertEqual(code, 1)


class SignalRecordingTests(SyncFixture):
    """Hook-mode sync records a capture signal for the artifact it just
    synced, after the self-filter, wrapped so any capturelib failure never
    touches sync's own exit code or report."""

    def _set_env(self):
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.root.parent)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
            else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )

    def _feed_stdin(self, payload):
        self.addCleanup(setattr, sys, "stdin", sys.stdin)
        sys.stdin = io.StringIO(json.dumps(payload))

    def _state(self):
        path = self.root / "tmp" / "capture-state.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_handoff_write_records_handoff_written_signal(self):
        self._set_env()
        self.write("handoffs/2026-08-05-session.md", spec("Handoff"))
        self._feed_stdin({
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.root / "handoffs" / "2026-08-05-session.md")},
        })
        code = sync_cmd.run(["--hook"])
        self.assertEqual(code, 0)
        signals = self._state()["signals"]
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["kind"], "handoff-written")
        self.assertEqual(signals[0]["ref"], "handoffs/2026-08-05-session.md")

    def test_spec_write_records_vault_write_signal(self):
        self._set_env()
        self.write("specs/SPEC-002-new.md", spec("New"))
        self._feed_stdin({
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.root / "specs" / "SPEC-002-new.md")},
        })
        code = sync_cmd.run(["--hook"])
        self.assertEqual(code, 0)
        signals = self._state()["signals"]
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["kind"], "vault-write")
        self.assertEqual(signals[0]["ref"], "specs/SPEC-002-new.md")

    def test_generated_output_records_nothing(self):
        self._set_env()
        self.write("specs/SPEC-002-new.md", spec("New"))
        self._feed_stdin({
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.root / "index.md")},
        })
        code = sync_cmd.run(["--hook"])
        self.assertEqual(code, 0)
        self.assertFalse((self.root / "tmp" / "capture-state.json").exists())

    def test_tag_index_write_records_nothing(self):
        self._set_env()
        (self.root / "tmp").mkdir(exist_ok=True)
        self._feed_stdin({
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.root / "meta" / "tag-index.yaml")},
        })
        code = sync_cmd.run(["--hook"])
        self.assertEqual(code, 0)
        self.assertFalse((self.root / "tmp" / "capture-state.json").exists())

    def test_capturelib_exception_leaves_report_and_exit_code_untouched(self):
        self._set_env()
        self.write("specs/SPEC-002-new.md", spec("New"))
        self._feed_stdin({
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.root / "specs" / "SPEC-002-new.md")},
        })
        original = sync_cmd.capturelib.record_signal
        sync_cmd.capturelib.record_signal = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            out = io.StringIO()
            from contextlib import redirect_stdout
            with redirect_stdout(out):
                code = sync_cmd.run(["--hook"])
        finally:
            sync_cmd.capturelib.record_signal = original
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), json.dumps({"suppressOutput": True}))
        self.assertIn("[[SPEC-002-new]]", self.index_text())

    def test_non_hook_sync_records_nothing(self):
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.root.parent)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
            else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )
        self.write("specs/SPEC-002-new.md", spec("New"))
        out = io.StringIO()
        from contextlib import redirect_stdout
        with redirect_stdout(out):
            code = sync_cmd.run([])
        self.assertEqual(code, 0)
        self.assertFalse((self.root / "tmp" / "capture-state.json").exists())

    def test_signal_readable_by_capturelib_load_state(self):
        self._set_env()
        self.write("specs/SPEC-002-new.md", spec("New"))
        self._feed_stdin({
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.root / "specs" / "SPEC-002-new.md")},
        })
        code = sync_cmd.run(["--hook"])
        self.assertEqual(code, 0)
        state = capturelib.load_state(self.root)
        self.assertEqual(len(state["signals"]), 1)
        self.assertEqual(state["signals"][0]["kind"], "vault-write")
        self.assertEqual(state["signals"][0]["ref"], "specs/SPEC-002-new.md")


class WorkerSessionRecursionGateTests(SyncFixture):
    """TASK-092: sync's hook mode under `COMPASS_WORKER_SESSION` (ADR-013
    D-11). The worker's own vault writes must still update the index - that
    part is wanted, since the worker really does write vault content (new
    lessons) that the next session needs to find - but must record no
    capture signal, or the worker would manufacture the very due() evidence
    that reopens the capture loop on itself."""

    def _set_env(self):
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.root.parent)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
            else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )

    def _set_worker_session(self):
        old = os.environ.get("COMPASS_WORKER_SESSION")
        os.environ["COMPASS_WORKER_SESSION"] = "1"
        self.addCleanup(
            lambda: os.environ.__setitem__("COMPASS_WORKER_SESSION", old) if old
            else os.environ.pop("COMPASS_WORKER_SESSION", None)
        )

    def _feed_stdin(self, payload):
        self.addCleanup(setattr, sys, "stdin", sys.stdin)
        sys.stdin = io.StringIO(json.dumps(payload))

    def test_worker_session_write_syncs_index_but_records_no_signal(self):
        self._set_env()
        self._set_worker_session()
        self.write("specs/SPEC-002-new.md", spec("New"))
        self._feed_stdin({
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.root / "specs" / "SPEC-002-new.md")},
        })
        out = io.StringIO()
        from contextlib import redirect_stdout
        with redirect_stdout(out):
            code = sync_cmd.run(["--hook"])
        self.assertEqual(code, 0)
        self.assertIn("[[SPEC-002-new]]", self.index_text(), "the worker's own write must still sync")
        self.assertFalse(
            (self.root / "tmp" / "capture-state.json").exists(),
            "a worker-session write must record no capture signal",
        )


class HumanModeTests(SyncFixture):
    def test_run_without_hook_flag_never_reads_stdin(self):
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.root.parent)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
            else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )
        self.write("specs/SPEC-002-new.md", spec("New"))

        # A stdin whose read() raises proves human mode never touches it - the
        # regression guard for the no-input hang in a non-interactive shell.
        class _Boom:
            def read(self_inner):
                raise AssertionError("human mode must not read stdin")

        self.addCleanup(setattr, sys, "stdin", sys.stdin)
        sys.stdin = _Boom()
        out = io.StringIO()
        from contextlib import redirect_stdout
        with redirect_stdout(out):
            code = sync_cmd.run([])
        self.assertEqual(code, 0)
        self.assertIn("[[SPEC-002-new]]", self.index_text())


class CatalogRowEscalatedTests(unittest.TestCase):
    _data = {
        "status": "active",
        "category": "process",
        "area": "workflow",
        "tags": ["a", "b"],
        "score": 6,
        "summary": "a rule",
    }

    def test_escalated_frontmatter_lands_in_the_row(self):
        row = sync_cmd._catalog_row(
            "LESSON-x.md", {**self._data, "escalated": "2026-08-06"}
        )
        self.assertIn("    escalated: 2026-08-06", row)

    def test_row_without_escalated_omits_the_field(self):
        row = sync_cmd._catalog_row("LESSON-x.md", dict(self._data))
        self.assertNotIn("escalated", row)


if __name__ == "__main__":
    unittest.main()


class HotPathCapTests(SyncFixture):
    """The aggregate hot-path cap: index.md, active.md and the lessons catalog
    together against `hot_path.HOT_PATH_CAP`, independent of the per-file caps."""

    def _fill_over_cap(self, rel):
        """Write `rel` with enough filler to carry the hot path over the cap
        on its own. `active.md` has no component cap, so filling it isolates
        the aggregate breach from every per-file check."""
        words = []
        while True:
            words.extend(f"filler{i}" for i in range(len(words), len(words) + 400))
            text = " ".join(words)
            if vaultlib.count_tokens(text) > hot_path_cmd.HOT_PATH_CAP:
                self.write(rel, text)
                return

    def marker_line(self):
        for line in self.index_text().split("\n"):
            if line.startswith(sync_cmd.HOT_PATH_WARNING_PREFIX):
                return line
        return None

    def test_marker_written_when_only_the_aggregate_is_over(self):
        """Adversarial where: every component cap passes and the total does
        not. The defect this catches is the aggregate breach going unmarked
        because only per-file caps were checked, which leaves the one cap
        actually violated with nothing attached to it."""
        self._fill_over_cap("active.md")
        report = sync_cmd.sync(self.root)
        index_text = self.index_text()
        # The per-file caps that would otherwise have fired: all clear.
        self.assertLessEqual(len(index_text.splitlines()), sync_cmd.INDEX_LINE_CAP)
        self.assertNotIn(sync_cmd.INDEX_WARNING, index_text)
        self.assertNotIn(sync_cmd.CATALOG_WARNING,
                         (self.root / "meta" / "lessons-catalog.yaml").read_text(encoding="utf-8"))
        self.assertIn("hot path", report["caps"])
        self.assertIsNotNone(self.marker_line())

    def test_marker_names_every_hot_path_file_and_the_cap(self):
        self._fill_over_cap("active.md")
        sync_cmd.sync(self.root)
        line = self.marker_line()
        for rel in hot_path_cmd.HOT_PATH_FILES:
            self.assertIn(rel, line)
        self.assertIn(f"/ {hot_path_cmd.HOT_PATH_CAP} tokens", line)

    def test_marker_total_excludes_the_marker_itself(self):
        """Adversarial where: the marker is prepended to the very file it
        measures. Counting it would inflate the total by its own length and,
        for a vault near the boundary, keep the marker alive forever. The
        reported total must equal the count of the three files with no
        marker present."""
        self._fill_over_cap("active.md")
        sync_cmd.sync(self.root)
        reported = int(self.marker_line().split(sync_cmd.HOT_PATH_WARNING_PREFIX)[1].split(" /")[0])
        stripped = "\n".join(
            line for line in self.index_text().split("\n")
            if not line.startswith(sync_cmd.HOT_PATH_WARNING_PREFIX)
        )
        expected = vaultlib.count_tokens(stripped)
        for rel in ("active.md", "meta/lessons-catalog.yaml"):
            expected += vaultlib.count_tokens((self.root / rel).read_text(encoding="utf-8"))
        self.assertEqual(reported, expected)

    def test_no_marker_and_no_warning_when_under_cap(self):
        report = sync_cmd.sync(self.root)
        self.assertNotIn("hot path", report["caps"])
        self.assertIsNone(self.marker_line())

    def test_marker_cleared_once_the_total_drops_back_under(self):
        """Adversarial where: the breach is fixed. A marker that is written
        but never withdrawn tells every later session to consolidate a vault
        that is already inside its budget."""
        self._fill_over_cap("active.md")
        sync_cmd.sync(self.root)
        self.assertIsNotNone(self.marker_line())
        self.write("active.md", "trimmed")
        self.write("meta/lessons-catalog.yaml", CATALOG_TEMPLATE)
        report = sync_cmd.sync(self.root)
        self.assertNotIn("hot path", report["caps"])
        self.assertIsNone(self.marker_line())

    def test_repeat_sync_over_cap_leaves_exactly_one_marker(self):
        """Adversarial where: sync runs on every vault write. A marker
        prepended per run stacks duplicates into the hot path it is
        complaining about."""
        self._fill_over_cap("active.md")
        sync_cmd.sync(self.root)
        first = self.index_text()
        sync_cmd.sync(self.root)
        second = self.index_text()
        markers = [line for line in second.split("\n")
                   if line.startswith(sync_cmd.HOT_PATH_WARNING_PREFIX)]
        self.assertEqual(len(markers), 1)
        self.assertEqual(first, second)

    def test_missing_index_does_not_crash_the_hot_path_check(self):
        (self.root / "index.md").unlink()
        sync_cmd._check_hot_path_cap(self.root, self.root / "index.md")  # must not raise


class ConsolidateTriggerLiteralTests(unittest.TestCase):
    """Every marker the consolidate skill waits for must be one sync can
    actually write. A literal that drifted on either side gates the only
    cleanup instrument shut with no error anywhere."""

    def skill_markers(self):
        path = Path(__file__).resolve().parents[2] / "skills" / "consolidate" / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        pre_check = text.split("## Pre-check", 1)[1].split("If none present", 1)[0]
        return re.findall(r"^- `([^`]+)`", pre_check, re.MULTILINE)

    def test_pre_check_lists_markers(self):
        self.assertTrue(self.skill_markers())

    def test_every_skill_marker_is_one_sync_writes(self):
        writable = [
            sync_cmd.INDEX_WARNING,
            sync_cmd.CATALOG_WARNING,
            sync_cmd._hot_path_marker([("index.md", 1)], 1),
        ]
        for marker in self.skill_markers():
            with self.subTest(marker=marker):
                self.assertTrue(
                    any(w.startswith(marker) for w in writable),
                    f"consolidate waits for {marker!r}, which no sync marker starts with",
                )


class CatalogDuplicateRowTests(SyncFixture):
    """A second writer (a model editing the catalog by hand) can insert a
    row the hook already appended. The catalog is append-only by design, so
    without a collapse the duplicate survives every later sync, validate and
    doctor silently."""

    def _row_block(self, filename):
        text = (self.root / "meta" / "lessons-catalog.yaml").read_text(encoding="utf-8")
        blocks = re.split(r"(?m)^(?=  - file: )", text)
        return next(b for b in blocks if f'file: "{filename}"' in b)

    def test_byte_identical_duplicate_row_collapses_to_one_and_is_reported(self):
        """Adversarial where: the duplicate is byte-identical and sits at a
        different position, exactly the worker's Edit. Appending-side dedup
        (the `existing` set) cannot see it; only a collapse over the file can."""
        self.write("lessons/LESSON-dup.md", lesson("Dup"))
        sync_cmd.sync(self.root)
        block = self._row_block("LESSON-dup.md")
        path = self.root / "meta" / "lessons-catalog.yaml"
        text = path.read_text(encoding="utf-8")
        head, sep, rest = text.partition("  - file:")
        path.write_text(head + block + sep + rest, encoding="utf-8")
        self.assertEqual(path.read_text(encoding="utf-8").count('file: "LESSON-dup.md"'), 2)
        report = sync_cmd.sync(self.root)
        after = path.read_text(encoding="utf-8")
        self.assertEqual(after.count('file: "LESSON-dup.md"'), 1)
        self.assertIn('summary: "summary of Dup"', after)
        self.assertTrue(lessonslib.load_catalog(self.root))
        self.assertEqual(report.get("catalog_duplicates_removed"), 1)
        self.assertIn("duplicate", sync_cmd.format_report(report).lower())

    def test_two_distinct_adjacent_rows_are_untouched(self):
        self.write("lessons/LESSON-a.md", lesson("A"))
        self.write("lessons/LESSON-b.md", lesson("B"))
        sync_cmd.sync(self.root)
        report = sync_cmd.sync(self.root)
        text = (self.root / "meta" / "lessons-catalog.yaml").read_text(encoding="utf-8")
        self.assertEqual(text.count('file: "LESSON-a.md"'), 1)
        self.assertEqual(text.count('file: "LESSON-b.md"'), 1)
        self.assertEqual(report.get("catalog_duplicates_removed", 0), 0)

    def test_summary_containing_the_word_file_is_not_a_block_boundary(self):
        """Adversarial where: a naive split on `file:` would cut a row whose
        summary text contains that token. The block boundary is the row
        start, not the substring."""
        self.write("lessons/LESSON-c.md", lesson("C").replace(
            'summary: "summary of C"', 'summary: "the file: field is the key"'))
        sync_cmd.sync(self.root)
        report = sync_cmd.sync(self.root)
        text = (self.root / "meta" / "lessons-catalog.yaml").read_text(encoding="utf-8")
        self.assertEqual(text.count('file: "LESSON-c.md"'), 1)
        self.assertIn('summary: "the file: field is the key"', text)
        self.assertEqual(report.get("catalog_duplicates_removed", 0), 0)
