"""Tests for `compass sweep` - the active.md done-task sweep (ADR-014).

Adversarial by design: fenced fake tasks, unchecked descendants under a
checked parent, CRLF input, idempotence, day-heading reuse, and the
dry-run/apply split are each a class of defect the sweep must survive.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vaultlib  # noqa: E402
from commands import sweep as sweep_cmd  # noqa: E402
from commands import sync as sync_cmd  # noqa: E402


FRONT = "---\ntitle: Active Tasks\nupdated: 2026-08-24\n---\n"

ACTIVE = FRONT + """
# Active Tasks

Preamble prose stays.

- [x] preamble done item with a [[WIKI-link]]
- [ ] preamble open item

## Shipped

- [x] [[PLAN-001]] - first
- [x] [[PLAN-002]] - second

## Mixed initiative

Context prose for the initiative.

- [x] done leaf
- [ ] open leaf
- [x] done parent with open child
  - [ ] the open child
- [x] done parent with done child
  - [x] the done child
  continuation prose of the done parent

## Prose only

No tasks here, just words.

## Fenced

- [ ] real open task

```markdown
- [x] fake task inside a fence
## fake heading inside a fence
```
"""


class SweepFixture(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = tmp / ".compass"
        self.root.mkdir(parents=True)
        (self.root / "active.md").write_text(ACTIVE, encoding="utf-8")

    def sweep(self, apply=True, today="2026-08-28"):
        return sweep_cmd.sweep_active(self.root, apply=apply, today=today)

    def active(self):
        return (self.root / "active.md").read_text(encoding="utf-8")

    def done(self):
        return (self.root / "archive" / "done.md").read_text(encoding="utf-8")


class SweepEngineTests(SweepFixture):
    def test_done_items_leave_active_and_land_verbatim_in_done(self):
        self.sweep()
        self.assertNotIn("- [x] done leaf", self.active())
        self.assertIn("- [x] done leaf", self.done())
        self.assertIn("- [x] preamble done item with a [[WIKI-link]]", self.done())

    def test_open_items_and_preamble_prose_stay(self):
        self.sweep()
        text = self.active()
        self.assertIn("- [ ] preamble open item", text)
        self.assertIn("- [ ] open leaf", text)
        self.assertIn("Preamble prose stays.", text)
        self.assertIn("# Active Tasks", text)

    def test_checked_parent_with_unchecked_child_is_not_done(self):
        self.sweep()
        text = self.active()
        self.assertIn("- [x] done parent with open child", text)
        self.assertIn("- [ ] the open child", text)
        self.assertNotIn("done parent with open child", self.done())

    def test_done_parent_block_moves_with_children_and_continuation(self):
        self.sweep()
        self.assertNotIn("done parent with done child", self.active())
        done = self.done()
        self.assertIn("- [x] done parent with done child", done)
        self.assertIn("  - [x] the done child", done)
        self.assertIn("  continuation prose of the done parent", done)

    def test_all_done_section_moves_wholesale_with_heading_demoted(self):
        self.sweep()
        text = self.active()
        self.assertNotIn("## Shipped", text)
        self.assertNotIn("[[PLAN-001]]", text)
        done = self.done()
        self.assertIn("### Shipped", done)
        self.assertIn("- [x] [[PLAN-001]] - first", done)
        self.assertIn("- [x] [[PLAN-002]] - second", done)

    def test_mixed_section_keeps_heading_and_prose(self):
        self.sweep()
        text = self.active()
        self.assertIn("## Mixed initiative", text)
        self.assertIn("Context prose for the initiative.", text)

    def test_prose_only_section_untouched(self):
        self.sweep()
        self.assertIn("## Prose only", self.active())
        self.assertIn("No tasks here, just words.", self.active())
        self.assertNotIn("Prose only", self.done())

    def test_fenced_fake_tasks_and_headings_never_swept(self):
        self.sweep()
        text = self.active()
        self.assertIn("- [x] fake task inside a fence", text)
        self.assertIn("## fake heading inside a fence", text)
        self.assertIn("- [ ] real open task", text)
        self.assertNotIn("fake task", self.done())

    def test_frontmatter_preserved(self):
        self.sweep()
        self.assertTrue(self.active().startswith(FRONT))

    def test_report_counts(self):
        report = self.sweep()
        # items: preamble done, done leaf, done parent with done child = 3
        # sections wholesale: Shipped = 1
        self.assertEqual(report["sections"], 1)
        self.assertEqual(report["items"], 3)

    def test_idempotent_second_run_is_a_noop(self):
        self.sweep()
        after_first = self.active()
        done_first = self.done()
        report = self.sweep()
        self.assertEqual((report["items"], report["sections"]), (0, 0))
        self.assertEqual(self.active(), after_first)
        self.assertEqual(self.done(), done_first)

    def test_dry_run_touches_nothing(self):
        report = self.sweep(apply=False)
        self.assertEqual(report["items"], 3)
        self.assertEqual(report["sections"], 1)
        self.assertEqual(self.active(), ACTIVE)
        self.assertFalse((self.root / "archive" / "done.md").exists())

    def test_missing_active_is_a_noop(self):
        (self.root / "active.md").unlink()
        report = self.sweep()
        self.assertEqual((report["items"], report["sections"]), (0, 0))

    def test_crlf_input_survives(self):
        crlf = ACTIVE.replace("\n", "\r\n")
        (self.root / "active.md").write_bytes(crlf.encode("utf-8"))
        self.sweep()
        self.assertIn("- [ ] open leaf", self.active())
        self.assertIn("- [x] done leaf", self.done())

    def test_uppercase_x_counts_as_done(self):
        (self.root / "active.md").write_text(
            FRONT + "\n## S\n\n- [X] shouted done\n- [ ] open\n", encoding="utf-8"
        )
        self.sweep()
        self.assertNotIn("shouted done", self.active())
        self.assertIn("- [X] shouted done", self.done())

    def test_day_heading_reused_within_a_day_and_new_on_a_new_day(self):
        (self.root / "active.md").write_text(
            FRONT + "\n## A\n\n- [x] one\n- [ ] keep\n", encoding="utf-8"
        )
        self.sweep(today="2026-08-28")
        (self.root / "active.md").write_text(
            FRONT + "\n## A\n\n- [x] two\n- [ ] keep\n", encoding="utf-8"
        )
        self.sweep(today="2026-08-28")
        self.assertEqual(self.done().count("## 2026-08-28"), 1)
        (self.root / "active.md").write_text(
            FRONT + "\n## A\n\n- [x] three\n- [ ] keep\n", encoding="utf-8"
        )
        self.sweep(today="2026-08-29")
        self.assertEqual(self.done().count("## 2026-08-29"), 1)


class SweepCliTests(SweepFixture):
    def run_cli(self, args):
        import contextlib
        import io

        cwd = os.getcwd()
        os.chdir(self.root.parent)
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                code = sweep_cmd.run(args)
        finally:
            os.chdir(cwd)
        return code, buf.getvalue()

    def test_default_is_dry_run(self):
        code, out = self.run_cli([])
        self.assertEqual(code, 0)
        self.assertIn("would sweep", out)
        self.assertEqual(self.active(), ACTIVE)

    def test_apply_sweeps(self):
        code, out = self.run_cli(["--apply"])
        self.assertEqual(code, 0)
        self.assertIn("swept", out)
        self.assertNotIn("- [x] done leaf", self.active())


class SweepSyncIntegrationTests(SweepFixture):
    def setUp(self):
        super().setUp()
        (self.root / "meta").mkdir()
        (self.root / "index.md").write_text(
            "# Index\n\n## Specs\n\n## Lessons\n", encoding="utf-8"
        )
        (self.root / "meta" / "lessons-catalog.yaml").write_text(
            "lessons:\n", encoding="utf-8"
        )

    def test_sync_runs_the_sweep(self):
        report = sync_cmd.sync(self.root)
        self.assertEqual(report["active_swept"]["items"], 3)
        self.assertEqual(report["active_swept"]["sections"], 1)
        self.assertNotIn("- [x] done leaf", self.active())

    def test_sync_report_names_the_sweep_only_when_it_moved_something(self):
        text = sync_cmd.format_report(sync_cmd.sync(self.root))
        self.assertIn("active.md swept", text)
        text = sync_cmd.format_report(sync_cmd.sync(self.root))
        self.assertNotIn("active.md swept", text)


class ValidateDriftWarningTests(SweepFixture):
    def test_validate_warns_on_lingering_done_items(self):
        from commands import validate as validate_cmd

        (self.root / "meta").mkdir()
        (self.root / "index.md").write_text("# Index\n", encoding="utf-8")
        errors, warnings = validate_cmd.check_vault(self.root)
        self.assertTrue(any(w.startswith("active_done:") for w in warnings))

    def test_no_warning_when_clean(self):
        from commands import validate as validate_cmd

        self.sweep()
        (self.root / "meta").mkdir()
        (self.root / "index.md").write_text("# Index\n", encoding="utf-8")
        errors, warnings = validate_cmd.check_vault(self.root)
        self.assertFalse(any(w.startswith("active_done:") for w in warnings))


if __name__ == "__main__":
    unittest.main()
