"""Tests for the branches and helpers `compass lesson-check` carries beyond its
public contract: byte and line-ending handling of the working file versus the
committed text, argument parsing, frontmatter shapes the comparison must not
choke on, and the body measure shared with `compass validate`.
"""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import lesson_check, validate  # noqa: E402
from test_lesson_check import (  # noqa: E402
    GitCase, LESSON_REL, RECORD, lesson, numbered,
)


class ByteAndLineEndingTests(GitCase):
    def test_crlf_and_bom_working_copies_of_an_unedited_lesson_pass(self):
        """Adversarial where: the committed text and the working file are
        decoded by different paths (git bytes versus the vault reader), so an
        editor that only re-saves with CRLF endings or a BOM makes every line
        look changed. Rows rewrite the identical text with each encoding."""
        text = lesson(numbered(4), numbered(2, "kept"), seen=("2026-01-01",))
        rows = [
            ("CRLF endings", text.replace("\n", "\r\n").encode("utf-8")),
            ("UTF-8 BOM", b"\xef\xbb\xbf" + text.encode("utf-8")),
            ("BOM and CRLF", b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")),
            ("lone CR endings", text.replace("\n", "\r").encode("utf-8")),
        ]
        for name, raw in rows:
            with self.subTest(row=name):
                repo = self.make_repo()
                self.commit(repo, text)
                (repo / LESSON_REL).write_bytes(raw)
                code, output = self.check(repo)
                self.assert_passes(code, output)

    def test_committed_crlf_lesson_checked_against_its_lf_working_copy_passes(self):
        """Adversarial where: the base side of the comparison keeps its CR
        bytes, so a repository that committed CRLF text reports every line
        gone once an editor saves LF endings."""
        text = lesson(numbered(3), seen=("2026-01-01",))
        repo = self.make_repo()
        (repo / LESSON_REL).write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
        self.commit(repo)
        self.edit(repo, text)
        code, output = self.check(repo)
        self.assert_passes(code, output)

    def test_a_lesson_holding_bytes_that_are_not_utf8_exits_one_without_a_traceback(self):
        """Adversarial where: a latin-1 byte reaches the strict vault reader
        and the exception escapes the command, which promises to exit 1 with
        a cause for any file it cannot check."""
        text = lesson(numbered(2)).encode("utf-8") + b"caf\xe9 stray latin-1 line\n"
        repo = self.make_repo()
        (repo / LESSON_REL).write_bytes(text)
        self.commit(repo)
        code, output = self.check(repo)
        self.assertEqual(code, 1, output)
        self.assertIn("LESSON-probe", output)
        self.assertNotIn("Traceback", output)


class ArgumentTests(GitCase):
    def test_malformed_arguments_exit_one_with_usage_and_never_raise(self):
        """Adversarial where: each argument-parsing branch (missing path,
        second path, unknown option, `--base` with no value, empty
        `--base=`, an option-shaped revision) ends in an exception or in git
        reading the revision as one of its own options."""
        repo = self.make_repo()
        self.commit(repo, lesson(numbered(2)))
        target = str(repo / LESSON_REL)
        rows = [
            ("no path", [], "missing lesson path"),
            ("two paths", [target, target], "unexpected argument"),
            ("unknown option", [target, "--force"], "unknown option"),
            ("--base without value", [target, "--base"], "--base needs a revision"),
            ("empty --base=", [target, "--base="], "--base needs a revision"),
            ("empty --base value", [target, "--base", ""], "--base needs a revision"),
            ("option-shaped revision", [target, "--base", "--output=leak.txt"], "does not name a commit"),
            ("revision that is no commit", [target, "--base", "no-such-rev"], "does not name a commit"),
        ]
        os.chdir(repo)
        for name, argv, cause in rows:
            with self.subTest(row=name):
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    code = lesson_check.run(argv)
                self.assertEqual(code, 1, err.getvalue())
                self.assertIn(cause, err.getvalue())
        self.assertFalse((repo / "leak.txt").exists())

    def test_base_given_as_branch_tag_and_abbreviated_sha_all_resolve(self):
        """Adversarial where: the explicit-base branch only recognises a
        full SHA or `HEAD`; a body line dropped since each spelling of the
        same commit must fail in all of them."""
        repo = self.make_repo()
        sha = self.commit(repo, lesson(numbered(3)))
        self.git(repo, "tag", "probe-tag")
        self.git(repo, "branch", "probe-branch")
        self.edit(repo, lesson(numbered(2)))
        for spelling in ("probe-tag", "probe-branch", sha[:8], "HEAD~0", sha):
            with self.subTest(base=spelling):
                code, output = self.check(repo, ["--base", spelling])
                self.assert_fails_naming(code, output, "rule line 3")

    def test_base_naming_a_blob_or_tree_is_not_taken_for_a_commit(self):
        """Adversarial where: `rev-parse --verify` accepts a tree id; the
        `^{commit}` peel must reject it so the check does not silently fall
        back to the cap-only branch and pass a lesson that lost text."""
        repo = self.make_repo()
        self.commit(repo, lesson(numbered(3)))
        tree = self.git(repo, "rev-parse", "HEAD^{tree}")
        self.edit(repo, lesson(numbered(2)))
        code, output = self.check(repo, ["--base", tree])
        self.assert_fails_naming(code, output, "does not name a commit")

    def test_relative_path_from_another_directory_and_a_path_with_spaces(self):
        """Adversarial where: the base lookup runs `git show REV:./name` from
        the lesson's own folder; a relative path, a different cwd or a space
        in a folder name breaks the lookup and the edit passes unchecked."""
        repo = self.make_repo()
        rel = ".compass/lessons/two words/LESSON-probe.md"
        path = repo / rel
        path.parent.mkdir(parents=True)
        path.write_text(lesson(numbered(3)), encoding="utf-8", newline="")
        self.commit(repo)
        path.write_text(lesson(numbered(2)), encoding="utf-8", newline="")
        elsewhere = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, elsewhere, True)
        for name, cwd, target in (
            ("relative from repo root", repo, rel),
            ("relative from the lesson folder", path.parent, "LESSON-probe.md"),
            ("absolute from an unrelated cwd", elsewhere, str(path)),
        ):
            with self.subTest(row=name):
                os.chdir(cwd)
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    code = lesson_check.run([target])
                self.assertEqual(code, 1, err.getvalue())
                self.assertIn("rule line 3", err.getvalue())

    def test_a_directory_or_missing_path_names_the_cause(self):
        """Adversarial where: `os.path.isfile` guards the missing-file branch
        but a directory argument falls to the reader and raises."""
        repo = self.make_repo()
        self.commit(repo, lesson(numbered(2)))
        for target in (str(repo / ".compass" / "lessons"), str(repo / "absent.md")):
            with self.subTest(target=Path(target).name):
                code, output = self.check(repo, path=target)
                self.assert_fails_naming(code, output, "file not found")

    def test_a_lesson_outside_any_repository_gets_the_cap_check_only(self):
        """Adversarial where: git failing with 'not a repository' must read
        as no base version, not as a crash or a pass on a six-line body."""
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        env_keys = {"GIT_CEILING_DIRECTORIES": str(folder.parent)}
        os.environ.update(env_keys)
        for count, expected in ((5, 0), (6, 1)):
            with self.subTest(body_lines=count):
                (folder / "LESSON-x.md").write_text(lesson(numbered(count)), encoding="utf-8")
                os.chdir(folder)
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    code = lesson_check.run(["LESSON-x.md"])
                self.assertEqual(code, expected, err.getvalue())


class FrontmatterShapeTests(GitCase):
    def rewrite(self, repo, old_text, new_text):
        self.commit(repo, old_text)
        self.edit(repo, new_text)
        return self.check(repo)

    def test_unterminated_or_missing_frontmatter_exits_one_naming_the_cause(self):
        """Adversarial where: the helper that locates the closing fence
        assumes the parser already vouched for it; an empty file, a fence
        never closed or no fence at all must report, not raise."""
        rows = [
            ("empty file", ""),
            ("fence never closed", "---\ntitle: x\nscore: 3\nbody line\n"),
            ("no frontmatter", "just a body\n"),
            ("BOM only", "﻿"),
        ]
        for name, content in rows:
            with self.subTest(row=name):
                repo = self.make_repo()
                self.commit(repo, lesson(numbered(2)))
                self.edit(repo, content)
                code, output = self.check(repo)
                self.assert_fails_naming(code, output, "LESSON-probe")
                self.assertNotIn("Traceback", output)

    def test_a_base_without_readable_frontmatter_falls_back_to_the_cap_check(self):
        """Adversarial where: the committed version is an old-format note;
        comparing against it would flag every field as lost."""
        repo = self.make_repo()
        self.commit(repo, "an old format note without a fence\n")
        self.edit(repo, lesson(numbered(5)))
        code, output = self.check(repo)
        self.assert_passes(code, output)
        self.edit(repo, lesson(numbered(6)))
        code, output = self.check(repo)
        self.assert_fails_naming(code, output, "6 lines")

    def test_list_fields_survive_a_change_of_yaml_spelling(self):
        """Adversarial where: the entry-by-entry comparison treats a flow
        list, a block list, a reordering and a scalar as different values.
        Same entries in a different spelling or order pass; one dropped
        entry among reordered ones fails."""
        flow_old = lesson(numbered(2), tags=("alpha", "beta"), seen=("2026-01-01", "2026-02-02"))
        block_new = flow_old.replace(
            "tags: [alpha, beta]", "tags:\n  - beta\n  - alpha").replace(
            "seen: [2026-01-01, 2026-02-02]", "seen:\n  - 2026-02-02\n  - 2026-01-01")
        repo = self.make_repo()
        code, output = self.rewrite(repo, flow_old, block_new)
        self.assert_passes(code, output)

        repo = self.make_repo()
        code, output = self.rewrite(
            repo, flow_old, block_new.replace("  - alpha\n", ""))
        self.assert_fails_naming(code, output, "tags lost alpha")

        repo = self.make_repo()
        scalar_old = lesson(numbered(2), tags=("alpha",)).replace("seen: []", "seen: 2026-01-01")
        scalar_new = scalar_old.replace("seen: 2026-01-01", "seen: [2026-01-01, 2026-03-03]")
        code, output = self.rewrite(repo, scalar_old, scalar_new)
        self.assert_passes(code, output)

    def test_score_edge_values(self):
        """Adversarial where: the integer parse and its None branches. A
        score that becomes non-numeric or disappears is a shrink; a base
        score that was never numeric cannot be compared and must not fail
        the edit; a drop to zero or below is a fall."""
        rows = [
            ("equal", 7, 7, 0),
            ("raised", 7, 8, 0),
            ("fell to zero", 7, 0, 1),
            ("fell below zero", 7, -1, 1),
            ("became text", 7, "high", 1),
            ("removed", 7, None, 1),
            ("base was text", "high", 3, 0),
            ("base was text and removed", "high", None, 0),
        ]
        for name, old, new, expected in rows:
            with self.subTest(row=name):
                repo = self.make_repo()
                old_text = lesson(numbered(2), score=old)
                new_text = lesson(numbered(2), score=new)
                if new is None:
                    new_text = new_text.replace("score: None\n", "")
                self.commit(repo, old_text)
                self.edit(repo, new_text)
                code, output = self.check(repo)
                self.assertEqual(code, expected, output)
                if expected:
                    self.assertIn("score", output)

    def test_created_compared_as_text_not_as_a_parsed_date(self):
        """Adversarial where: quoting a date changes how the parser reads it
        but not its value; a different date, a removed field and a field
        newly added where the base had none are three distinct branches."""
        base = lesson(numbered(2), created="2026-03-01")
        rows = [
            ("quoted same date", base.replace("created: 2026-03-01", 'created: "2026-03-01"'), 0),
            ("different date", base.replace("2026-03-01\nupdated", "2026-03-02\nupdated"), 1),
            ("removed", base.replace("created: 2026-03-01\n", ""), 1),
        ]
        for name, new_text, expected in rows:
            with self.subTest(row=name):
                repo = self.make_repo()
                code, output = self.rewrite(repo, base, new_text)
                self.assertEqual(code, expected, output)
                if expected:
                    self.assertIn("created", output)
        repo = self.make_repo()
        no_created = base.replace("created: 2026-03-01\n", "")
        code, output = self.rewrite(repo, no_created, base)
        self.assert_passes(code, output)


class BodyMeasureTests(GitCase):
    def test_superseded_lines_do_not_count_but_still_cannot_be_dropped(self):
        """Adversarial where: the cap measure drops `Superseded:` lines, and
        the lost-line scan must still protect them; a measure shared with
        the comparison would let an edit erase the retirement notice."""
        body = numbered(5) + ["Superseded: by LESSON-newer on 2026-05-01"]
        repo = self.make_repo()
        text = lesson(body)
        self.commit(repo, text)
        code, output = self.check(repo)
        self.assert_passes(code, output)
        self.edit(repo, lesson(numbered(5)))
        code, output = self.check(repo)
        self.assert_fails_naming(code, output, "Superseded: by LESSON-newer")

    def test_superseded_line_between_body_lines_is_excluded_from_the_count(self):
        """Adversarial where: only a trailing Superseded line is skipped, so
        one in the middle pushes a five-line body to six."""
        body = numbered(2) + ["Superseded: older note"] + numbered(3, "tail")
        repo = self.make_repo()
        self.commit(repo, lesson(body))
        code, output = self.check(repo)
        self.assert_passes(code, output)

    def test_blank_lines_inside_the_body_are_physical_lines(self):
        """Adversarial where: the cap counts physical lines, so blank
        separators between five paragraphs push the body past the cap; the
        leading and trailing blanks do not."""
        padded = [""] + numbered(5) + ["", ""]
        spaced = [line for pair in zip(numbered(5), [""] * 5) for line in pair][:-1]
        repo = self.make_repo()
        self.commit(repo, lesson(padded))
        code, output = self.check(repo)
        self.assert_passes(code, output)
        repo = self.make_repo()
        self.commit(repo, lesson(spaced))
        code, output = self.check(repo)
        self.assert_fails_naming(code, output, "9 lines")

    def test_record_heading_variants(self):
        """Adversarial where: the heading match is exact after strip. Trailing
        spaces still end the body; a different case or a missing heading
        leaves the Record text inside the body and trips the cap."""
        body = numbered(5)
        record = numbered(3, "kept")
        rows = [
            ("trailing spaces", RECORD + "   ", 0),
            ("lower case", "## record (preserved)", 1),
            ("one hash fewer", "# Record (preserved)", 1),
        ]
        for name, heading, expected in rows:
            with self.subTest(row=name):
                text = lesson(body) + "\n" + heading + "\n\n" + "\n".join(record) + "\n"
                repo = self.make_repo()
                self.commit(repo, text)
                code, output = self.check(repo)
                self.assertEqual(code, expected, output)

    def test_moving_a_line_into_the_record_requires_the_exact_text(self):
        """Adversarial where: trailing whitespace is forgiven, leading
        indentation and inner spacing are not."""
        body = numbered(5)
        old = lesson(body)
        for name, moved, expected in (
            ("trailing space added", body[0] + "   ", 0),
            ("trailing tab added", body[0] + "\t", 0),
            ("indented", "  " + body[0], 1),
            ("inner space doubled", body[0].replace(" states", "  states"), 1),
        ):
            with self.subTest(row=name):
                repo = self.make_repo()
                self.commit(repo, old)
                self.edit(repo, lesson(body[1:], [moved]))
                code, output = self.check(repo)
                self.assertEqual(code, expected, output)

    def test_a_record_line_moved_up_into_the_body_still_counts_as_kept(self):
        """Adversarial where: the kept-text scan covers both sections;
        promoting a Record line into a body with room for it loses nothing."""
        repo = self.make_repo()
        self.commit(repo, lesson(numbered(3), ["kept earlier detail"]))
        self.edit(repo, lesson(numbered(3) + ["kept earlier detail"]))
        code, output = self.check(repo)
        self.assert_passes(code, output)

    def test_every_lost_line_is_reported_once_and_a_repeated_one_only_once(self):
        """Adversarial where: the loop adds each reported line to the kept
        set to avoid repeats; two different lost lines produce two findings,
        a line lost twice in the base produces one."""
        repo = self.make_repo()
        base_body = numbered(3) + [numbered(3)[0]]
        self.commit(repo, lesson(base_body))
        self.edit(repo, lesson([numbered(3)[2]]))
        code, output = self.check(repo)
        self.assertEqual(code, 1, output)
        self.assertEqual(output.count("rule line 1 states"), 1, output)
        self.assertEqual(output.count("rule line 2 states"), 1, output)


class ValidateAgreementTests(GitCase):
    def make_vault(self, lessons):
        repo = self.make_repo()
        for rel, text in lessons.items():
            path = repo / ".compass" / "lessons" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
        return repo / ".compass"

    def cap_warnings(self, vault):
        _, warnings = validate.check_vault(vault)
        return [w for w in warnings if w.startswith("lesson_body_over_cap:")]

    def test_validate_counts_exactly_as_lesson_check_for_every_body_shape(self):
        """Adversarial where: validate and lesson-check each read the file;
        a CRLF or BOM file, a Superseded line and a Record section must give
        the same verdict in both or the warning and the command disagree."""
        shapes = {
            "five-crlf.md": lesson(numbered(5), numbered(4, "kept")).replace("\n", "\r\n"),
            "five-bom.md": b"\xef\xbb\xbf" + lesson(numbered(5)).encode("utf-8"),
            "five-superseded.md": lesson(numbered(5) + ["Superseded: by another"]),
            "six-crlf.md": lesson(numbered(6)).replace("\n", "\r\n"),
            "six-bom.md": b"\xef\xbb\xbf" + lesson(numbered(6)).encode("utf-8"),
        }
        vault = self.make_vault(shapes)
        flagged = {w.split(":")[1].strip().split("/")[-1] for w in self.cap_warnings(vault)}
        self.assertEqual(flagged, {"six-crlf.md", "six-bom.md"})
        for name in shapes:
            with self.subTest(file=name):
                path = vault / "lessons" / name
                lesson_check_says = lesson_check.check(str(path), "HEAD")
                self.assertEqual(bool(lesson_check_says), name in flagged, lesson_check_says)

    def test_validate_skips_an_over_long_lesson_whose_frontmatter_is_unreadable(self):
        """Adversarial where: the helper returns early on a parse error; a
        fence-less file under lessons/ must not crash the vault check or
        double-report as a cap warning."""
        vault = self.make_vault({"LESSON-bad.md": "no fence\n" + "\n".join(numbered(9)) + "\n"})
        _, warnings = validate.check_vault(vault)
        self.assertEqual([w for w in warnings if "lesson_body_over_cap" in w], [])


if __name__ == "__main__":
    unittest.main()
