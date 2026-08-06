"""Tests for `lessonslib` (catalog row parsing and ranking) and the
`compass lessons` command that wraps it. Adversarial where the module
claims strictness: a row shape that does not match the writer's fixed
format must fail loud naming the row, never silently drop or guess."""

import builtins
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lessonslib  # noqa: E402
import maincli  # noqa: E402
from commands import lessons  # noqa: E402


def make_vault(test_case):
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    root = tmp / ".compass"
    (root / "meta").mkdir(parents=True)
    return root


def with_vault_env(test_case, project_dir):
    old = os.environ.get("CLAUDE_PROJECT_DIR")
    os.environ["CLAUDE_PROJECT_DIR"] = str(project_dir)

    def restore():
        if old is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = old

    test_case.addCleanup(restore)


def row(file, status="active", category="process", area="workflow",
        tags=(), score=5, summary="a summary", escalated=None):
    """One catalog row, in the exact shape `commands/sync.py:_catalog_row`
    writes, with an optional trailing `escalated:` line."""
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


class ParseCatalogTests(unittest.TestCase):
    def test_parses_every_field_of_a_well_formed_row(self):
        text = "lessons:\n" + row(
            "LESSON-a.md", tags=["hooks", "cli"], score=7, summary="hooks and cli"
        ) + "\n"
        rows = lessonslib.parse_catalog(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["file"], "LESSON-a.md")
        self.assertEqual(rows[0]["tags"], ["hooks", "cli"])
        self.assertEqual(rows[0]["score"], 7)
        self.assertEqual(rows[0]["summary"], "hooks and cli")
        self.assertFalse(rows[0]["escalated"])

    def test_escalated_field_read_when_present(self):
        text = "lessons:\n" + row("LESSON-e.md", escalated="2026-01-01") + "\n"
        rows = lessonslib.parse_catalog(text)
        self.assertTrue(rows[0]["escalated"])

    def test_empty_catalog_returns_no_rows(self):
        self.assertEqual(lessonslib.parse_catalog("lessons:\n"), [])
        self.assertEqual(lessonslib.parse_catalog(""), [])

    def test_missing_required_field_raises_with_row_number(self):
        text = "lessons:\n" + row("LESSON-a.md") + "\n" + (
            '  - file: "LESSON-b.md"\n'
            '    status: active\n'
            '    category: process\n'
            '    area: workflow\n'
            '    tags: [x]\n'
            '    summary: "missing score"\n'
        )
        with self.assertRaises(lessonslib.MalformedRow) as ctx:
            lessonslib.parse_catalog(text)
        self.assertEqual(ctx.exception.row_number, 2)

    def test_non_bracketed_tags_raises(self):
        text = (
            '  - file: "LESSON-a.md"\n'
            '    status: active\n'
            '    category: process\n'
            '    area: workflow\n'
            '    tags: hooks\n'
            '    score: 5\n'
            '    summary: "bad tags"\n'
        )
        with self.assertRaises(lessonslib.MalformedRow) as ctx:
            lessonslib.parse_catalog(text)
        self.assertEqual(ctx.exception.row_number, 1)

    def test_non_integer_score_raises(self):
        text = (
            '  - file: "LESSON-a.md"\n'
            '    status: active\n'
            '    category: process\n'
            '    area: workflow\n'
            '    tags: [x]\n'
            '    score: five\n'
            '    summary: "bad score"\n'
        )
        with self.assertRaises(lessonslib.MalformedRow) as ctx:
            lessonslib.parse_catalog(text)
        self.assertEqual(ctx.exception.row_number, 1)

    def test_row_number_counts_position_including_earlier_valid_rows(self):
        text = "lessons:\n" + row("LESSON-a.md") + "\n" + row("LESSON-b.md") + "\n" + (
            '  - file: "LESSON-c.md"\n'
            '    status: active\n'
        )
        with self.assertRaises(lessonslib.MalformedRow) as ctx:
            lessonslib.parse_catalog(text)
        self.assertEqual(ctx.exception.row_number, 3)


class RankTests(unittest.TestCase):
    def test_tag_overlap_outranks_area_only_match(self):
        rows = lessonslib.parse_catalog("lessons:\n" + "\n".join([
            row("LESSON-tagmatch.md", area="workflow", tags=["hooks"], score=1,
                summary="hooks lesson"),
            row("LESSON-areaonly.md", area="workflow", tags=["unrelated"], score=9,
                summary="area only lesson"),
        ]) + "\n")
        ranked = lessonslib.rank(rows, area="workflow", tags=["hooks"])
        self.assertEqual(ranked[0]["file"], "LESSON-tagmatch.md")
        self.assertEqual(ranked[0]["tag_overlap"], 1)
        self.assertEqual(ranked[1]["file"], "LESSON-areaonly.md")

    def test_area_contributes_when_tags_tie(self):
        rows = lessonslib.parse_catalog("lessons:\n" + "\n".join([
            row("LESSON-sameArea.md", area="workflow", tags=["t"], score=1),
            row("LESSON-otherArea.md", area="methodology", tags=["t"], score=9),
        ]) + "\n")
        ranked = lessonslib.rank(rows, area="workflow", tags=["t"])
        self.assertEqual(ranked[0]["file"], "LESSON-sameArea.md")
        self.assertEqual(ranked[0]["area_match"], 1)
        self.assertEqual(ranked[1]["area_match"], 0)

    def test_text_token_overlap_ranks(self):
        rows = lessonslib.parse_catalog("lessons:\n" + "\n".join([
            row("LESSON-match.md", tags=[], score=1,
                summary="windows crlf breaks container scripts"),
            row("LESSON-partial.md", tags=[], score=9,
                summary="windows service restarts on schedule"),
        ]) + "\n")
        ranked = lessonslib.rank(rows, text="windows crlf")
        self.assertEqual(ranked[0]["file"], "LESSON-match.md")
        self.assertEqual(ranked[0]["text_overlap"], 2)
        self.assertEqual(ranked[1]["text_overlap"], 1)

    def test_zero_relevance_rows_excluded_when_query_has_criteria(self):
        rows = lessonslib.parse_catalog("lessons:\n" + "\n".join([
            row("LESSON-relevant.md", area="workflow", tags=["hooks"], score=1),
            row("LESSON-unrelated.md", area="methodology", tags=["other"], score=9),
        ]) + "\n")
        ranked = lessonslib.rank(rows, tags=["hooks"])
        self.assertEqual([r["file"] for r in ranked], ["LESSON-relevant.md"])

    def test_no_criteria_is_a_browse_returning_every_active_row(self):
        rows = lessonslib.parse_catalog("lessons:\n" + "\n".join([
            row("LESSON-a.md", area="workflow", tags=["x"], score=1),
            row("LESSON-b.md", area="methodology", tags=["y"], score=9),
        ]) + "\n")
        ranked = lessonslib.rank(rows)
        self.assertEqual(len(ranked), 2)

    def test_escalated_row_survives_the_zero_relevance_exclusion(self):
        rows = lessonslib.parse_catalog("lessons:\n" + "\n".join([
            row("LESSON-relevant.md", area="workflow", tags=["hooks"], score=1),
            row("LESSON-escalated.md", area="methodology", tags=["other"], score=1,
                escalated="2026-08-06"),
        ]) + "\n")
        ranked = lessonslib.rank(rows, tags=["hooks"])
        self.assertEqual(ranked[0]["file"], "LESSON-escalated.md")
        self.assertEqual(len(ranked), 2)

    def test_score_is_the_final_tiebreak(self):
        rows = lessonslib.parse_catalog("lessons:\n" + "\n".join([
            row("LESSON-low.md", area="workflow", tags=[], score=2),
            row("LESSON-high.md", area="workflow", tags=[], score=8),
        ]) + "\n")
        ranked = lessonslib.rank(rows)  # no query: everything ties except score
        self.assertEqual(ranked[0]["file"], "LESSON-high.md")

    def test_archived_rows_excluded(self):
        rows = lessonslib.parse_catalog("lessons:\n" + "\n".join([
            row("LESSON-active.md", status="active", tags=["hooks"]),
            row("LESSON-archived.md", status="archived", tags=["hooks"]),
        ]) + "\n")
        ranked = lessonslib.rank(rows, tags=["hooks"])
        files = [r["file"] for r in ranked]
        self.assertIn("LESSON-active.md", files)
        self.assertNotIn("LESSON-archived.md", files)

    def test_escalated_row_surfaces_first_regardless_of_other_scores(self):
        rows = lessonslib.parse_catalog("lessons:\n" + "\n".join([
            row("LESSON-perfectmatch.md", area="workflow", tags=["hooks"], score=10),
            row("LESSON-escalated.md", area="other", tags=[], score=1,
                escalated="2026-01-01"),
        ]) + "\n")
        ranked = lessonslib.rank(rows, area="workflow", tags=["hooks"])
        self.assertEqual(ranked[0]["file"], "LESSON-escalated.md")
        self.assertTrue(ranked[0]["escalated"])

    def test_tag_matching_is_case_insensitive_both_directions(self):
        rows = lessonslib.parse_catalog(
            "lessons:\n" + row("LESSON-a.md", tags=["hooks"]) + "\n"
        )
        ranked = lessonslib.rank(rows, tags=["Hooks"])
        self.assertEqual(ranked[0]["tag_overlap"], 1)

    def test_area_matching_is_case_insensitive(self):
        rows = lessonslib.parse_catalog(
            "lessons:\n" + row("LESSON-a.md", area="workflow") + "\n"
        )
        ranked = lessonslib.rank(rows, area="Workflow")
        self.assertEqual(ranked[0]["area_match"], 1)

    def test_rank_field_is_1_based_and_sequential(self):
        rows = lessonslib.parse_catalog("lessons:\n" + "\n".join([
            row("LESSON-a.md", score=9),
            row("LESSON-b.md", score=5),
            row("LESSON-c.md", score=1),
        ]) + "\n")
        ranked = lessonslib.rank(rows)
        self.assertEqual([r["rank"] for r in ranked], [1, 2, 3])


class LessonsCommandTests(unittest.TestCase):
    def _run(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lessons.run(args)
        return code, out.getvalue(), err.getvalue()

    def test_missing_catalog_exits_1(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        code, _, err = self._run([])
        self.assertEqual(code, 1)
        self.assertIn("vault malformed", err)

    def test_empty_catalog_exits_0_with_explicit_line(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_catalog(root, [])
        code, out, _ = self._run([])
        self.assertEqual(code, 0)
        self.assertIn("no lessons", out)

    def test_malformed_row_exits_1_naming_row_number(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        (root / "meta" / "lessons-catalog.yaml").write_text(
            "lessons:\n" + row("LESSON-ok.md") + "\n"
            '  - file: "LESSON-bad.md"\n'
            '    status: active\n',
            encoding="utf-8",
        )
        code, _, err = self._run([])
        self.assertEqual(code, 1)
        self.assertIn("row 2", err)

    def test_unknown_flag_exits_1_not_2(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_catalog(root, [row("LESSON-a.md")])
        code, _, err = self._run(["--bogus"])
        self.assertEqual(code, 1)
        self.assertIn("unknown flag", err)

    def test_top_bounds_output(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_catalog(root, [row(f"LESSON-{i}.md", score=i) for i in range(8)])
        code, out, _ = self._run(["--top", "3", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(len(payload), 3)

    def test_json_output_parses_and_carries_rank_fields(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_catalog(root, [row("LESSON-a.md", tags=["hooks"])])
        code, out, _ = self._run(["--tags", "hooks", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload[0]["file"], "LESSON-a.md")
        for field in ("tag_overlap", "area_match", "text_overlap", "rank", "escalated"):
            self.assertIn(field, payload[0])

    def test_escalated_row_carries_visible_marker_in_report(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_catalog(root, [row("LESSON-e.md", escalated="2026-01-01")])
        code, out, _ = self._run([])
        self.assertEqual(code, 0)
        self.assertIn("ESCALATED", out)
        self.assertIn("LESSON-e.md", out)

    def _write_doc(self, root, rel, area=None, tags=None):
        lines = ["---"]
        if area is not None:
            lines.append(f"area: {area}")
        if tags is not None:
            lines.append(f"tags: [{', '.join(tags)}]")
        lines += ["---", "", "# doc", ""]
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")

    def test_for_resolves_bare_name_and_path_the_same_way(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        (root / "specs").mkdir()
        self._write_doc(root, "specs/SPEC-001-foo.md", area="workflow", tags=["hooks"])
        write_catalog(root, [
            row("LESSON-hooks.md", area="workflow", tags=["hooks"], score=1),
            row("LESSON-other.md", area="methodology", tags=["unrelated"], score=9),
        ])
        code_bare, out_bare, _ = self._run(["--for", "SPEC-001-foo", "--json"])
        code_path, out_path, _ = self._run(["--for", "specs/SPEC-001-foo.md", "--json"])
        self.assertEqual(code_bare, 0)
        self.assertEqual(code_path, 0)
        self.assertEqual(json.loads(out_bare)[0]["file"], "LESSON-hooks.md")
        self.assertEqual(json.loads(out_path)[0]["file"], "LESSON-hooks.md")

    def test_for_doc_with_no_tags_still_uses_area(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        (root / "specs").mkdir()
        self._write_doc(root, "specs/SPEC-002-bar.md", area="methodology")
        write_catalog(root, [
            row("LESSON-samearea.md", area="methodology", tags=[], score=1),
            row("LESSON-otherarea.md", area="workflow", tags=[], score=9),
        ])
        code, out, _ = self._run(["--for", "SPEC-002-bar", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)[0]["file"], "LESSON-samearea.md")

    def test_for_unresolvable_doc_exits_1(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_catalog(root, [row("LESSON-a.md")])
        code, _, err = self._run(["--for", "SPEC-does-not-exist"])
        self.assertEqual(code, 1)
        self.assertIn("not found", err)

    def test_missing_vault_exits_1_not_2_through_main(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        # find_vault_root falls back to walking up from cwd when
        # CLAUDE_PROJECT_DIR has no .compass/, so cwd must also sit outside
        # this repo's own vault - otherwise the fallback would find it.
        old_cwd = os.getcwd()
        os.chdir(tmp)
        self.addCleanup(os.chdir, old_cwd)
        with_vault_env(self, tmp)
        err = io.StringIO()
        with redirect_stderr(err):
            code = maincli.main(["lessons"])
        self.assertEqual(code, 1)


class RetrievalLogTests(unittest.TestCase):
    """`compass lessons` traces every run to
    `.compass/tmp/retrieval-log.jsonl`. Adversarial where the tracing
    claims best-effort: a log write failure must never touch the command's
    exit code or output."""

    def _run(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lessons.run(args)
        return code, out.getvalue(), err.getvalue()

    def _log_path(self, root):
        return root / "tmp" / "retrieval-log.jsonl"

    def _rows(self, root):
        path = self._log_path(root)
        if not path.is_file():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_run_with_criteria_appends_one_row_with_at_and_query(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_catalog(root, [
            row("LESSON-a.md", area="workflow", tags=["hooks"], score=5),
            row("LESSON-b.md", area="methodology", tags=["other"], score=9),
        ])
        code, _, _ = self._run(["--tags", "hooks", "--area", "workflow"])
        self.assertEqual(code, 0)
        rows = self._rows(root)
        self.assertEqual(len(rows), 1)
        self.assertRegex(rows[0]["at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        self.assertEqual(rows[0]["query"]["tags"], ["hooks"])
        self.assertEqual(rows[0]["query"]["area"], "workflow")

    def test_json_run_surfaced_list_matches_stdout_payload(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_catalog(root, [
            row("LESSON-a.md", area="workflow", tags=["hooks"], score=5),
            row("LESSON-b.md", area="methodology", tags=["other"], score=9),
        ])
        code, out, _ = self._run(["--tags", "hooks", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        rows = self._rows(root)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["surfaced"], [r["file"] for r in payload])
        self.assertEqual(rows[0]["surfaced"], ["LESSON-a.md"])

    def test_context_flag_lands_in_row(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_catalog(root, [row("LESSON-a.md")])
        self._run(["--context", "builder"])
        rows = self._rows(root)
        self.assertEqual(rows[0]["context"], "builder")

    def test_no_context_flag_omits_context_field(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_catalog(root, [row("LESSON-a.md")])
        self._run([])
        rows = self._rows(root)
        self.assertNotIn("context", rows[0])

    def test_repeated_runs_append_one_row_each(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_catalog(root, [row("LESSON-a.md")])
        self._run([])
        self._run(["--context", "planner"])
        self._run(["--tags", "hooks"])
        rows = self._rows(root)
        self.assertEqual(len(rows), 3)

    def test_browse_with_no_criteria_logs_empty_query_and_full_surface(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_catalog(root, [row("LESSON-a.md"), row("LESSON-b.md")])
        code, _, _ = self._run([])
        self.assertEqual(code, 0)
        rows = self._rows(root)
        self.assertEqual(len(rows), 1)
        query = rows[0]["query"]
        self.assertIsNone(query["area"])
        self.assertEqual(query["tags"], [])
        self.assertIsNone(query["text"])
        self.assertIsNone(query["for"])
        self.assertEqual(sorted(rows[0]["surfaced"]), ["LESSON-a.md", "LESSON-b.md"])

    def test_empty_catalog_still_logs_a_row_with_empty_surfaced(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_catalog(root, [])
        code, _, _ = self._run([])
        self.assertEqual(code, 0)
        rows = self._rows(root)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["surfaced"], [])

    def test_unwritable_tmp_dir_preserves_exit_code_and_output(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_catalog(root, [row("LESSON-a.md", tags=["hooks"])])
        baseline_code, baseline_out, baseline_err = self._run(["--tags", "hooks"])

        real_open = builtins.open

        def boom(file, *args, **kwargs):
            if str(file).endswith("retrieval-log.jsonl"):
                raise OSError("unwritable")
            return real_open(file, *args, **kwargs)

        with mock.patch("builtins.open", boom):
            code, out, err = self._run(["--tags", "hooks"])

        self.assertEqual(code, baseline_code)
        self.assertEqual(out, baseline_out)
        self.assertEqual(err, baseline_err)
        # The write failure itself is swallowed: only the baseline run's row
        # exists, nothing added for the run made under the unwritable mock.
        self.assertEqual(len(self._rows(root)), 1)

    def test_retrieval_log_is_lf_only(self):
        root = make_vault(self)
        with_vault_env(self, root.parent)
        write_catalog(root, [row("LESSON-a.md")])
        self._run([])
        self._run(["--context", "builder"])
        raw = self._log_path(root).read_bytes()
        self.assertNotIn(b"\r\n", raw)
        self.assertIn(b"\n", raw)


if __name__ == "__main__":
    unittest.main()
