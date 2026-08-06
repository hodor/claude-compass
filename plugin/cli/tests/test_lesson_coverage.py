"""Tests for `compass lesson-coverage <plan>`, the advisory lesson-citation
audit that mirrors `commands/coverage.py`'s decision-citation gate one field
over. Adversarial where the module claims strictness (an unresolvable
citation must fail loud naming it) and where it claims never to gate
(surfaced-but-uncited and citation-free plans must always exit 0)."""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maincli  # noqa: E402
from commands import lesson_coverage  # noqa: E402


def make_vault(test_case):
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    (tmp / ".compass" / "meta").mkdir(parents=True)
    return tmp / ".compass"


def with_vault_env(test_case, vault_root):
    old = os.environ.get("CLAUDE_PROJECT_DIR")
    os.environ["CLAUDE_PROJECT_DIR"] = str(vault_root.parent)

    def restore():
        if old is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = old

    test_case.addCleanup(restore)


def write(root, rel, body):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def row(file, status="active", category="process", area="workflow",
        tags=(), score=5, summary="a summary", escalated=None):
    """One catalog row, in the exact shape `commands/sync.py:_catalog_row`
    writes."""
    lines = [
        f'  - file: "{file}"',
        f'    status: {status}',
        f'    category: {category}',
        f'    area: {area}',
        f'    tags: [{", ".join(tags)}]',
        f'    score: {score}',
        f'    summary: "{summary}"',
    ]
    if escalated:
        lines.append(f'    escalated: {escalated}')
    return "\n".join(lines)


def write_catalog(root, rows):
    text = "lessons:\n" + ("\n".join(rows) + "\n" if rows else "")
    (root / "meta" / "lessons-catalog.yaml").write_text(text, encoding="utf-8")


def plan(body_lines, area="workflow", tags=("hooks",)):
    tag_items = ", ".join(tags)
    return (
        "---\ntitle: P\ntype: plan\nstatus: approved\n"
        f"area: {area}\ntags: [{tag_items}]\n---\n\n## Phases\n\n"
        + "\n".join(body_lines) + "\n"
    )


class LessonCoverageTests(unittest.TestCase):
    def setUp(self):
        self.root = make_vault(self)
        with_vault_env(self, self.root)

    def run_command(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lesson_coverage.run(args)
        return code, out.getvalue(), err.getvalue()

    def test_cited_lesson_shows_cited(self):
        write_catalog(self.root, [row("LESSON-hooks.md", tags=["hooks"])])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x], "
            "lessons: [LESSON-hooks]",
        ]))
        code, out, _ = self.run_command(["PLAN-001-p"])
        self.assertEqual(code, 0)
        line = next(l for l in out.splitlines() if "LESSON-hooks.md" in l)
        self.assertIn("cited", line)
        self.assertIn("TASK-001", line)
        self.assertIn("1 cited, 0 unresolvable", out)
        self.assertIn("PASS", out)

    def test_high_ranking_uncited_lesson_is_advisory_and_exits_0(self):
        write_catalog(self.root, [row("LESSON-hooks.md", tags=["hooks"])])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x]",
        ]))
        code, out, _ = self.run_command(["PLAN-001-p"])
        self.assertEqual(code, 0)
        line = next(l for l in out.splitlines() if "LESSON-hooks.md" in l)
        self.assertIn("surfaced-but-uncited", line)
        self.assertIn("PASS", out)

    def test_unresolvable_citation_exits_1_naming_it(self):
        write_catalog(self.root, [row("LESSON-hooks.md", tags=["hooks"])])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x], "
            "lessons: [LESSON-typo]",
        ]))
        code, out, _ = self.run_command(["PLAN-001-p"])
        self.assertEqual(code, 1)
        line = next(l for l in out.splitlines() if "LESSON-typo" in l)
        self.assertIn("unresolvable", line)
        self.assertIn("TASK-001", line)
        self.assertIn("FAIL", out)

    def test_citation_with_and_without_md_both_resolve_to_one_row(self):
        write_catalog(self.root, [row("LESSON-hooks.md", tags=["hooks"])])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x], "
            "lessons: [LESSON-hooks]",
            "- [ ] TASK-002: b - complexity: S, depends_on: none, files: [y], "
            "lessons: [LESSON-hooks.md]",
        ]))
        code, out, _ = self.run_command(["PLAN-001-p"])
        self.assertEqual(code, 0)
        cited_lines = [l for l in out.splitlines() if l.startswith("LESSON-hooks.md")]
        self.assertEqual(len(cited_lines), 1)
        self.assertIn("TASK-001", cited_lines[0])
        self.assertIn("TASK-002", cited_lines[0])

    def test_no_lessons_fields_exits_0_with_explicit_summary(self):
        write_catalog(self.root, [])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x]",
        ]))
        code, out, _ = self.run_command(["PLAN-001-p"])
        self.assertEqual(code, 0)
        self.assertIn("no citations", out)
        self.assertIn("PASS", out)

    def test_fenced_and_inline_code_never_claim(self):
        write_catalog(self.root, [row("LESSON-hooks.md", tags=["hooks"])])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "Fenced example:",
            "```",
            "- [ ] TASK-001: a - lessons: [LESSON-hooks]",
            "```",
            "Inline example: `lessons: [LESSON-hooks]`.",
            "- [ ] TASK-002: b - complexity: S, depends_on: none, files: [x]",
        ]))
        code, out, _ = self.run_command(["PLAN-001-p"])
        self.assertEqual(code, 0)
        self.assertIn("no citations", out)

    def test_archived_lesson_cited_resolves_as_cited_not_unresolvable(self):
        write_catalog(self.root, [
            row("LESSON-old.md", status="archived", tags=["hooks"]),
        ])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x], "
            "lessons: [LESSON-old]",
        ]))
        code, out, _ = self.run_command(["PLAN-001-p"])
        self.assertEqual(code, 0)
        line = next(l for l in out.splitlines() if "LESSON-old.md" in l)
        self.assertIn("cited", line)
        self.assertNotIn("unresolvable", line)
        # Archived rows never rank, so it must not also show as surfaced.
        self.assertEqual(
            len([l for l in out.splitlines() if "LESSON-old.md" in l]), 1
        )

    def test_json_output_parses(self):
        write_catalog(self.root, [row("LESSON-hooks.md", tags=["hooks"])])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x], "
            "lessons: [LESSON-hooks]",
        ]))
        code, out, _ = self.run_command(["PLAN-001-p", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["cited"][0]["lesson"], "LESSON-hooks.md")
        self.assertIn("TASK-001", payload["cited"][0]["cited_by"])
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["has_citations"])

    def test_json_output_reports_unresolvable_and_exits_1(self):
        write_catalog(self.root, [row("LESSON-hooks.md", tags=["hooks"])])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x], "
            "lessons: [LESSON-typo]",
        ]))
        code, out, _ = self.run_command(["PLAN-001-p", "--json"])
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["unresolvable"][0]["citation"], "LESSON-typo")

    def test_plan_not_found_exits_1(self):
        code, _, err = self.run_command(["NoSuchPlan"])
        self.assertEqual(code, 1)
        self.assertIn("not found", err)

    def test_missing_catalog_exits_1(self):
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x]",
        ]))
        code, _, err = self.run_command(["PLAN-001-p"])
        self.assertEqual(code, 1)
        self.assertIn("vault malformed", err)

    def test_malformed_catalog_row_exits_1(self):
        (self.root / "meta" / "lessons-catalog.yaml").write_text(
            'lessons:\n  - file: "LESSON-bad.md"\n    status: active\n',
            encoding="utf-8",
        )
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x]",
        ]))
        code, _, err = self.run_command(["PLAN-001-p"])
        self.assertEqual(code, 1)
        self.assertIn("malformed catalog", err)

    def test_usage_error_exits_1_not_2(self):
        code, _, err = self.run_command([])
        self.assertEqual(code, 1)
        self.assertIn("usage", err)

    def test_unknown_flag_exits_1_not_2(self):
        write_catalog(self.root, [])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x]",
        ]))
        code, _, err = self.run_command(["PLAN-001-p", "--bogus"])
        self.assertEqual(code, 1)
        self.assertIn("unknown flag", err)

    def test_registered_in_command_specs_and_dispatches(self):
        self.assertIn("lesson-coverage", maincli.VALID_COMMANDS)
        write_catalog(self.root, [])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x]",
        ]))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = maincli.main(["lesson-coverage", "PLAN-001-p"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
