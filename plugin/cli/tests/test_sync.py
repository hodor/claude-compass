"""Tests for `compass sync` in both human and hook modes."""

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

import vaultlib  # noqa: E402
from commands import sync as sync_cmd  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
