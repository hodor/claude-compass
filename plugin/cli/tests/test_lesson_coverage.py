"""Tests for `compass lesson-coverage <plan>`, the advisory lesson-citation
audit that mirrors `commands/coverage.py`'s decision-citation gate one field
over. Adversarial where the module claims strictness (an unresolvable
citation must fail loud naming it) and where it claims never to gate
(surfaced-but-uncited and citation-free plans must always exit 0)."""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maincli  # noqa: E402
from commands import lesson_coverage  # noqa: E402

# tests/ -> cli/ -> plugin/ -> repo root, the directory holding .compass.
REPO_ROOT = Path(__file__).resolve().parents[3]
CLI_DIR = Path(__file__).resolve().parents[1]


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

    # -- TASK-069: three-state region read (scoped joins cited) --------

    def test_scoped_lesson_cited_only_from_later_region_reports_scoped(self):
        """Adversarial where: a lesson cited only from a `## Later`
        intent line must not silently read as `cited` (already built)
        or fall to `surfaced-but-uncited` (never named) - it needs its
        own status naming work that is promised but not yet elaborated,
        and the summary line must count it."""
        write_catalog(self.root, [row("LESSON-hooks.md", tags=["hooks"])])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x]",
            "",
            "## Later (intent only)",
            "",
            "- [ ] TASK-002: b - files: [y], lessons: [LESSON-hooks]",
        ]))
        code, out, _ = self.run_command(["PLAN-001-p"])
        self.assertEqual(code, 0)
        line = next(l for l in out.splitlines() if "LESSON-hooks.md" in l)
        self.assertIn("scoped", line)
        self.assertNotIn("cited", line)
        self.assertIn("TASK-002", line)
        self.assertIn("1 scoped", out)
        self.assertIn("PASS", out)

    def test_lesson_cited_from_detailed_task_before_later_reports_cited(self):
        """Adversarial where: wiring in region-awareness must not
        misclassify a citation on a detailed task line as scoped merely
        because a `## Later` region exists later in the same document -
        position of the *region*, not position in the file, decides."""
        write_catalog(self.root, [row("LESSON-hooks.md", tags=["hooks"])])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x], "
            "lessons: [LESSON-hooks]",
            "",
            "## Later (intent only)",
            "",
            "- [ ] TASK-002: b - files: [y]",
        ]))
        code, out, _ = self.run_command(["PLAN-001-p"])
        self.assertEqual(code, 0)
        line = next(l for l in out.splitlines() if "LESSON-hooks.md" in l)
        self.assertIn("cited", line)
        self.assertNotIn("scoped", line)
        self.assertIn("TASK-001", line)

    def test_lesson_cited_from_both_regions_counted_once_as_cited(self):
        """Adversarial where: a lesson claimed by both a detailed task
        and a Later intent line must collapse to one `cited` row, not
        two rows and not a `scoped` row that loses the detailed claim."""
        write_catalog(self.root, [row("LESSON-hooks.md", tags=["hooks"])])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x], "
            "lessons: [LESSON-hooks]",
            "",
            "## Later (intent only)",
            "",
            "- [ ] TASK-002: b - files: [y], lessons: [LESSON-hooks]",
        ]))
        code, out, _ = self.run_command(["PLAN-001-p"])
        self.assertEqual(code, 0)
        rows = [l for l in out.splitlines() if l.startswith("LESSON-hooks.md")]
        self.assertEqual(len(rows), 1)
        self.assertIn("cited", rows[0])
        self.assertIn("TASK-001", rows[0])

    def test_unresolvable_citation_from_later_region_still_exits_1(self):
        """Adversarial where: an unresolvable citation sitting on a
        Later intent line, alongside one perfectly valid citation
        elsewhere in the plan, must still fail loud - the advisory
        treatment of `scoped` must not be read as advisory for typos,
        because a typo is a typo in either region."""
        write_catalog(self.root, [row("LESSON-hooks.md", tags=["hooks"])])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x], "
            "lessons: [LESSON-hooks]",
            "",
            "## Later (intent only)",
            "",
            "- [ ] TASK-002: b - files: [y], lessons: [LESSON-typo]",
        ]))
        code, out, _ = self.run_command(["PLAN-001-p"])
        self.assertEqual(code, 1)
        line = next(l for l in out.splitlines() if "LESSON-typo" in l)
        self.assertIn("unresolvable", line)
        self.assertIn("TASK-002", line)
        self.assertIn("FAIL", out)

    def test_json_scoped_entry_carries_citing_tasks(self):
        """Adversarial where: the `--json` payload must expose the
        scoped status as its own list beside `cited`, not fold a
        Later-only citation into `cited` and not drop it from the
        payload entirely."""
        write_catalog(self.root, [row("LESSON-hooks.md", tags=["hooks"])])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x]",
            "",
            "## Later (intent only)",
            "",
            "- [ ] TASK-002: b - files: [y], lessons: [LESSON-hooks]",
        ]))
        code, out, _ = self.run_command(["PLAN-001-p", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["cited"], [])
        self.assertEqual(payload["scoped"][0]["lesson"], "LESSON-hooks.md")
        self.assertIn("TASK-002", payload["scoped"][0]["cited_by"])

    def test_surfaced_but_uncited_untouched_when_plan_has_later_region(self):
        """Adversarial where: introducing the scoped status must not
        reclassify a lesson nobody cites at all - `surfaced-but-uncited`
        has to survive the three-state change unchanged even once the
        plan being read carries a `## Later` region."""
        write_catalog(self.root, [
            row("LESSON-hooks.md", tags=["hooks"]),
            row("LESSON-other.md", tags=["hooks"]),
        ])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x], "
            "lessons: [LESSON-hooks]",
            "",
            "## Later (intent only)",
            "",
            "- [ ] TASK-002: b - files: [y]",
        ]))
        code, out, _ = self.run_command(["PLAN-001-p"])
        self.assertEqual(code, 0)
        line = next(l for l in out.splitlines() if "LESSON-other.md" in l)
        self.assertIn("surfaced-but-uncited", line)

    def test_unterminated_fence_prints_note_and_exits_0(self):
        """Adversarial where: a fence that never closes blanks the rest
        of the document, including the `## Later` heading and its
        citation - the command must not pass silently as if that
        citation never existed. It has to print the same unreadable-
        regions note TASK-068 defines and must never crash to exit 2."""
        write_catalog(self.root, [row("LESSON-hooks.md", tags=["hooks"])])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "```",
            "unterminated fence, never closes",
            "",
            "## Later (intent only)",
            "",
            "- [ ] TASK-002: b - files: [y], lessons: [LESSON-hooks]",
        ]))
        code, out, err = self.run_command(["PLAN-001-p"])
        self.assertEqual(code, 0)
        self.assertIn("note", (out + err).lower())

    def test_no_later_section_summary_stays_byte_identical(self):
        """Adversarial where: a plan with no `## Later` heading anywhere
        must produce the exact previous summary wording, with no
        `scoped` count appended, not merely the same verdict - TASK-069
        promises "the previous output," not "the same PASS/FAIL"."""
        write_catalog(self.root, [row("LESSON-hooks.md", tags=["hooks"])])
        write(self.root, "plans/PLAN-001-p.md", plan([
            "- [ ] TASK-001: a - complexity: S, depends_on: none, files: [x], "
            "lessons: [LESSON-hooks]",
        ]))
        code, out, _ = self.run_command(["PLAN-001-p"])
        self.assertEqual(code, 0)
        self.assertIn("1 cited, 0 unresolvable", out)
        self.assertNotIn("scoped", out)


class LessonCoverageCorpusPinTests(unittest.TestCase):
    """Real-vault regression pins for TASK-069: PLAN-006 and PLAN-007 carry
    no `## Later` section, so wiring in the three-state region read must
    leave their row sets exactly as they were. Runs the installed `compass`
    CLI as a subprocess against this repo's own `.compass` vault, with
    `CLAUDE_PROJECT_DIR` pinned explicitly so no fixture vault used by the
    other tests in this module can leak in through inherited environment.
    The pinned plans exist only in the Compass repo's own vault, so a
    vendored copy of this suite running in another project skips them."""

    def setUp(self):
        plans = REPO_ROOT / ".compass" / "plans"
        if not (plans / "PLAN-006-learning-loop.md").is_file() \
                or not (plans / "PLAN-007-test-quality.md").is_file():
            self.skipTest("corpus plans absent: not running in the Compass repo")

    def run_real(self, plan_id):
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(REPO_ROOT)
        result = subprocess.run(
            [sys.executable, "compass", "lesson-coverage", plan_id],
            cwd=str(CLI_DIR), env=env, capture_output=True, text=True,
        )
        return result.returncode, result.stdout, result.stderr

    def test_corpus_pin_plan_006_row_set_unchanged(self):
        code, out, _ = self.run_real("PLAN-006-learning-loop")
        self.assertEqual(code, 0)
        lines = out.splitlines()

        def status_of(lesson):
            return next(l for l in lines if l.startswith(lesson))

        self.assertIn("cited", status_of("LESSON-hook-cli-gate-stdin-on-flag.md"))
        self.assertIn("TASK-037", status_of("LESSON-hook-cli-gate-stdin-on-flag.md"))
        self.assertIn("cited", status_of("LESSON-no-agent-bookkeeping.md"))
        self.assertIn("TASK-036", status_of("LESSON-no-agent-bookkeeping.md"))
        self.assertIn(
            "surfaced-but-uncited",
            status_of("LESSON-hooks-load-only-from-settings.md"),
        )
        self.assertIn(
            "surfaced-but-uncited",
            status_of("LESSON-scratch-vaults-need-compass-dir.md"),
        )
        self.assertIn(
            "surfaced-but-uncited",
            status_of("LESSON-tag-index-trades-cost-for-directed-retrieval.md"),
        )
        # The cited count and the unresolvable count are what this pin
        # guards. The surfaced-but-uncited total tracks how many catalog
        # rows rank against the plan, which grows whenever any lesson is
        # written, so asserting it would couple this pin to unrelated
        # vault growth.
        self.assertIn("summary: 2 cited, 0 unresolvable, ", out)
        self.assertIn("(advisory) -> PASS", out)

    def test_corpus_pin_plan_007_row_set_unchanged(self):
        code, out, _ = self.run_real("PLAN-007-test-quality")
        self.assertEqual(code, 0)
        lines = out.splitlines()

        def status_of(lesson):
            return next(l for l in lines if l.startswith(lesson))

        self.assertIn("cited", status_of("LESSON-no-agent-bookkeeping.md"))
        self.assertIn("TASK-052", status_of("LESSON-no-agent-bookkeeping.md"))
        self.assertIn("TASK-057", status_of("LESSON-no-agent-bookkeeping.md"))
        self.assertIn("cited", status_of("LESSON-scratch-vaults-need-compass-dir.md"))
        self.assertIn(
            "TASK-052", status_of("LESSON-scratch-vaults-need-compass-dir.md")
        )
        self.assertIn("cited", status_of("LESSON-subagent-worktrees-fork-stale.md"))
        self.assertIn(
            "TASK-055", status_of("LESSON-subagent-worktrees-fork-stale.md")
        )
        self.assertIn(
            "cited", status_of("LESSON-test-driven-tasks-dont-discriminate.md")
        )
        self.assertIn(
            "TASK-055", status_of("LESSON-test-driven-tasks-dont-discriminate.md")
        )
        self.assertIn(
            "cited",
            status_of("LESSON-type-dir-discovery-needs-content-signal.md"),
        )
        self.assertIn(
            "TASK-057",
            status_of("LESSON-type-dir-discovery-needs-content-signal.md"),
        )
        self.assertIn(
            "surfaced-but-uncited",
            status_of("LESSON-revert-to-prove-a-regression-test.md"),
        )
        self.assertIn(
            "surfaced-but-uncited", status_of("LESSON-suite-size-is-not-coverage.md")
        )
        self.assertIn(
            "surfaced-but-uncited",
            status_of("LESSON-hook-cli-gate-stdin-on-flag.md"),
        )
        self.assertIn("summary: 5 cited, 0 unresolvable, ", out)
        self.assertIn("(advisory) -> PASS", out)


if __name__ == "__main__":
    unittest.main()
