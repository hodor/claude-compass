"""Tests for `compass sync` in both human and hook modes."""

import datetime
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import capturelib  # noqa: E402
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


class LogCleanupTests(SyncFixture):
    def test_old_logs_deleted_recent_kept(self):
        (self.root / "tmp").mkdir()
        old = self.root / "tmp" / "extraction-log-old.md"
        new = self.root / "tmp" / "extraction-log-new.md"
        old.write_text("x", encoding="utf-8")
        new.write_text("x", encoding="utf-8")
        old_time = time.time() - 40 * 86400
        os.utime(old, (old_time, old_time))
        deleted = sync_cmd.sync(self.root)["logs_deleted"]
        self.assertEqual(deleted, 1)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())


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
        self.assertEqual(rows[0]["id"], "OPP-new")

    def test_malformed_capture_log_line_pruned_without_crashing(self):
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
        self.assertIn("- [[unitx/lessons/LESSON-unit-fresh]] - summary of Unit Fresh", section)
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
