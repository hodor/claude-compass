"""Tests for `compass lesson-check` and the `lesson_body_over_cap` finding of
`compass validate`.

Adversarial themes: a body that grows past five lines by one; displaced text
that is dropped or only nearly kept while the edit still looks like a tidy
move into the Record section; frontmatter lists and counters that shrink
while the edit appends elsewhere; a lesson with no committed version being
judged against a revision that does not hold it; a failure that exits 1 for
the wrong reason (an unimplemented command also exits 1) so each failing row
also pins the text that names its cause; a validate warning that fires on
the Record section, or that stays jargon when printed.
"""

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maincli  # noqa: E402
from commands import lesson_check, validate  # noqa: E402

LESSON_REL = ".compass/lessons/LESSON-probe.md"
RECORD = "## Record (preserved)"

GIT_IDENTITY = [
    "-c", "user.name=probe", "-c", "user.email=probe@example.invalid",
    "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false",
]


def lesson(body_lines, record_lines=(), seen=(), tags=("alpha", "beta"),
           score=7, created="2026-03-01"):
    """A lesson file shaped like the real ones: frontmatter, one blank line,
    the body lines, then an optional Record section."""
    front = [
        "---",
        "title: Probe lesson",
        "type: lesson",
        "status: active",
        "category: process",
        "area: methodology",
        f"tags: [{', '.join(tags)}]",
        f"created: {created}",
        "updated: 2026-03-01",
        f"score: {score}",
        'summary: "probe summary"',
        'source: "probe"',
        f"seen: [{', '.join(seen)}]",
        "---",
        "",
    ]
    text = "\n".join(front + list(body_lines)) + "\n"
    if record_lines:
        text += "\n" + RECORD + "\n\n" + "\n".join(record_lines) + "\n"
    return text


def numbered(count, stem="rule"):
    return [f"{stem} line {i} states one distinct instruction" for i in range(1, count + 1)]


class GitCase(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self.addCleanup(os.chdir, self._cwd)
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)

    def git(self, repo, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        done = subprocess.run(
            ["git", *GIT_IDENTITY, *args], cwd=repo, env=env,
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def make_repo(self):
        repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, repo, True)
        self.git(repo, "init", "-q")
        (repo / ".compass" / "lessons").mkdir(parents=True)
        (repo / ".compass" / "index.md").write_text("# Index\n", encoding="utf-8")
        os.environ["CLAUDE_PROJECT_DIR"] = str(repo)
        return repo

    def commit(self, repo, text=None, message="base"):
        """Write the probe lesson (when `text` is given) and commit all."""
        if text is not None:
            (repo / LESSON_REL).write_text(text, encoding="utf-8", newline="")
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", message)
        return self.git(repo, "rev-parse", "HEAD")

    def edit(self, repo, text):
        (repo / LESSON_REL).write_text(text, encoding="utf-8", newline="")

    def check(self, repo, args=None, path=None):
        """Run the command from the repo root; return (exit code, all output)."""
        os.chdir(repo)
        target = path if path is not None else str(repo / LESSON_REL)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lesson_check.run([target, *(args or [])])
        return code, out.getvalue() + err.getvalue()

    def assert_passes(self, code, output):
        self.assertEqual(code, 0, output)

    def assert_fails_naming(self, code, output, *needles):
        self.assertEqual(code, 1, output)
        self.assertNotIn("not implemented", output)
        for needle in needles:
            self.assertIn(needle, output)


class BodyCapTests(GitCase):
    def test_body_over_five_lines_fails_and_the_record_section_is_not_counted(self):
        """Adversarial where: an off-by-one at the cap (5 passes, 6 fails),
        or a count that includes the Record section, which is exempt from the
        cap and would make every preserved lesson fail. Each row commits the
        same text as base and as working file, so only the cap can speak."""
        rows = [
            ("exactly five body lines", numbered(5), (), True),
            ("six body lines", numbered(6), (), False),
            ("one body line", numbered(1), (), True),
            ("five body lines under a twelve line record", numbered(5),
             numbered(12, "kept"), True),
            ("six body lines even with a record", numbered(6), numbered(2, "kept"), False),
        ]
        for name, body, record, ok in rows:
            with self.subTest(row=name):
                repo = self.make_repo()
                text = lesson(body, record)
                self.commit(repo, text)
                code, output = self.check(repo)
                if ok:
                    self.assert_passes(code, output)
                else:
                    self.assert_fails_naming(code, output, "LESSON-probe")

    def test_a_lesson_with_no_committed_version_is_checked_for_the_cap_only(self):
        """Adversarial where: a brand-new lesson judged against a base that
        does not hold it, so every body line looks dropped and every counter
        looks shrunk. Rows: an untracked file in a repo that has commits, a
        file in a repo with no commit at all, and a base revision that
        predates the file. Five lines pass in each, six fail."""
        for name, make_base in (
            ("untracked file, repo has commits", "commit"),
            ("repo has no commits", "none"),
            ("explicit base predating the file", "explicit"),
        ):
            for count, ok in ((5, True), (6, False)):
                with self.subTest(row=name, body_lines=count):
                    repo = self.make_repo()
                    args = None
                    if make_base != "none":
                        (repo / "note.txt").write_text("x\n", encoding="utf-8")
                        base = self.commit(repo)
                        if make_base == "explicit":
                            args = ["--base", base]
                    self.edit(repo, lesson(numbered(count), seen=("2026-01-01",), score=1))
                    code, output = self.check(repo, args)
                    if ok:
                        self.assert_passes(code, output)
                    else:
                        self.assert_fails_naming(code, output, "LESSON-probe")


class BodyLossTests(GitCase):
    def test_displaced_body_text_must_survive_verbatim_in_the_file(self):
        """Adversarial where: an edit that shrinks the body to fit the cap by
        dropping text, or by moving it into the Record section with one
        character changed, passes as a tidy compaction. Base holds five lines
        plus one more being displaced; the row decides where the displaced
        line goes. The failing rows must print the lost line."""
        base_body = numbered(6)
        lost = base_body[5]
        near_miss = lost.replace("distinct", "distinKt")
        self.assertNotEqual(lost, near_miss)
        kept = base_body[:5]
        rows = [
            ("moved verbatim into a new record", kept, [lost], True),
            ("moved with one character changed", kept, [near_miss], False),
            ("dropped with no record", kept, [], False),
            ("record holds a different line", kept, ["unrelated preserved text"], False),
        ]
        for name, body, record, ok in rows:
            with self.subTest(row=name):
                repo = self.make_repo()
                # six line base is already over the cap; the check on the
                # edit must still judge only what the edit lost
                self.commit(repo, lesson(base_body))
                self.edit(repo, lesson(body, record))
                code, output = self.check(repo)
                if ok:
                    self.assert_passes(code, output)
                else:
                    self.assert_fails_naming(code, output, lost)

    def test_record_text_present_at_base_must_still_be_present(self):
        """Adversarial where: a consolidation that rewrites the Record
        section and silently drops an older preserved line, while the body is
        untouched. Rows: the record keeps both lines (passes, new line
        appended), loses one of two (fails and names it), is removed
        entirely (fails and names its line)."""
        old = ["preserved line one stays", "preserved line two stays"]
        rows = [
            ("record grows by one line", old + ["a third preserved line"], True, None),
            ("one of two record lines removed", old[:1], False, old[1]),
            ("record section removed", [], False, old[0]),
        ]
        for name, record, ok, lost in rows:
            with self.subTest(row=name):
                repo = self.make_repo()
                self.commit(repo, lesson(numbered(3), old))
                self.edit(repo, lesson(numbered(3), record))
                code, output = self.check(repo)
                if ok:
                    self.assert_passes(code, output)
                else:
                    self.assert_fails_naming(code, output, lost)

    def test_an_unedited_lesson_and_an_explicit_base_are_both_honoured(self):
        """Adversarial where: the base revision ignored, so a check against
        HEAD and a check against an older commit give the same answer. The
        second commit drops a line the first held; against HEAD the working
        file equals base (passes), against the first commit it lost a line
        (fails, naming it). Also pins that the default base is HEAD."""
        repo = self.make_repo()
        first = self.commit(repo, lesson(numbered(5)))
        lost = numbered(5)[4]
        self.commit(repo, lesson(numbered(4)), "drop a line")
        code, output = self.check(repo)
        self.assert_passes(code, output)
        code, output = self.check(repo, ["--base", "HEAD"])
        self.assert_passes(code, output)
        code, output = self.check(repo, ["--base", first])
        self.assert_fails_naming(code, output, lost)

    def test_the_default_base_compares_the_working_file_not_the_staged_one(self):
        """Adversarial where: the comparison reads the index instead of the
        working tree, so an edit that was staged and then reverted or one not
        staged at all is judged on the wrong text. The edit drops a line and
        stays unstaged; it must fail, and a relative path from the repo root
        must reach the same file as the absolute one."""
        repo = self.make_repo()
        self.commit(repo, lesson(numbered(5)))
        lost = numbered(5)[2]
        body = [line for line in numbered(5) if line != lost]
        self.edit(repo, lesson(body))
        code, output = self.check(repo, path=LESSON_REL)
        self.assert_fails_naming(code, output, lost)


class FrontmatterGrowthTests(GitCase):
    def test_seen_tags_score_and_created_may_grow_but_never_shrink(self):
        """Adversarial where: an edit that appends a seen date but also drops
        an older one, replaces a tag instead of adding one, lowers a score by
        one, or rewrites `created`, while another field legitimately grows.
        Base: two seen dates, tags alpha and beta, score 7. The score row at
        7 (equal) is the boundary: unchanged must pass."""
        two = ("2026-01-01", "2026-01-02")
        rows = [
            ("seen gains a date", dict(seen=two + ("2026-02-01",)), True, None),
            ("seen loses one date", dict(seen=two[:1]), False, "seen"),
            ("seen emptied", dict(seen=()), False, "seen"),
            ("seen swaps a date", dict(seen=(two[0], "2026-02-09")), False, "seen"),
            ("tags unioned", dict(tags=("alpha", "beta", "gamma")), True, None),
            ("tag removed", dict(tags=("alpha",)), False, "tags"),
            ("tag replaced", dict(tags=("alpha", "gamma")), False, "tags"),
            ("score raised by one", dict(score=8), True, None),
            ("score equal", dict(score=7), True, None),
            ("score lowered by one", dict(score=6), False, "score"),
            ("created changed", dict(created="2026-03-02"), False, "created"),
        ]
        for name, change, ok, field in rows:
            with self.subTest(row=name):
                repo = self.make_repo()
                base_fields = dict(seen=two)
                self.commit(repo, lesson(numbered(3), **base_fields))
                self.edit(repo, lesson(numbered(3), **{**base_fields, **change}))
                code, output = self.check(repo)
                if ok:
                    self.assert_passes(code, output)
                else:
                    self.assert_fails_naming(code, output, field)

    def test_several_losses_in_one_edit_are_all_reported(self):
        """Adversarial where: the check stops at its first finding, so an edit
        that drops a body line and lowers the score reports only one and the
        fix loop needs two rounds. Both causes must appear in one run."""
        repo = self.make_repo()
        self.commit(repo, lesson(numbered(4), score=7))
        self.edit(repo, lesson(numbered(3), score=3))
        code, output = self.check(repo)
        self.assert_fails_naming(code, output, numbered(4)[3], "score")


class MalformedInputTests(GitCase):
    def test_unreadable_lessons_exit_one_and_name_the_cause(self):
        """Adversarial where: a file with no frontmatter, an unterminated
        frontmatter, or a path that does not exist raises a traceback or
        passes silently because no field could be compared. Each must exit 1
        through the real entry point (never 2), print the file name or path,
        and say what is wrong."""
        rows = [
            ("no frontmatter", "just a body line\nanother body line\n", r"front|propert|header"),
            ("unterminated frontmatter", "---\ntitle: x\ntype: lesson\nbody\n",
             r"front|propert|header|unterminated"),
        ]
        for name, text, cause in rows:
            with self.subTest(row=name):
                repo = self.make_repo()
                self.commit(repo, lesson(numbered(2)))
                self.edit(repo, text)
                os.chdir(repo)
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    code = maincli.main(["lesson-check", str(repo / LESSON_REL)])
                output = out.getvalue() + err.getvalue()
                self.assert_fails_naming(code, output, "LESSON-probe")
                self.assertRegex(output.lower(), cause)
                self.assertNotIn("Traceback", output)
        with self.subTest(row="missing file"):
            repo = self.make_repo()
            self.commit(repo, lesson(numbered(2)))
            os.chdir(repo)
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = maincli.main(["lesson-check", str(repo / ".compass/lessons/LESSON-absent.md")])
            output = out.getvalue() + err.getvalue()
            self.assert_fails_naming(code, output, "LESSON-absent")
            self.assertNotIn("Traceback", output)

    def test_main_dispatches_to_the_command_and_an_unedited_lesson_exits_zero(self):
        """Adversarial where: the command registered in maincli but never
        wired, so dispatch reports it as not implemented. An unedited lesson
        checked against HEAD through `maincli.main` must exit 0 with no
        failure output."""
        repo = self.make_repo()
        self.commit(repo, lesson(numbered(5), numbered(2, "kept"), seen=("2026-01-01",)))
        os.chdir(repo)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = maincli.main(["lesson-check", str(repo / LESSON_REL), "--base", "HEAD"])
        output = out.getvalue() + err.getvalue()
        self.assertEqual(code, 0, output)
        self.assertNotIn("not implemented", output)


class ValidateLessonCapTests(GitCase):
    def make_vault(self, lessons):
        repo = self.make_repo()
        for rel, text in lessons.items():
            path = repo / ".compass" / "lessons" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="")
        return repo / ".compass"

    def cap_warnings(self, vault):
        _, warnings = validate.check_vault(vault)
        return [w for w in warnings if w.startswith("lesson_body_over_cap:")]

    def test_validate_warns_once_per_lesson_whose_body_is_over_five_lines(self):
        """Adversarial where: the warning fires at five lines (off by one),
        counts the exempt Record section, misses a lesson one folder down, or
        reports a lesson more than once. Vault holds a five-line lesson, a
        five-line lesson with a long Record, a six-line lesson at the top and
        a six-line lesson in a subfolder; exactly the last two are named."""
        vault = self.make_vault({
            "LESSON-five.md": lesson(numbered(5)),
            "LESSON-five-with-record.md": lesson(numbered(5), numbered(12, "kept")),
            "LESSON-six.md": lesson(numbered(6)),
            "hooks/LESSON-six-nested.md": lesson(numbered(6)),
        })
        found = self.cap_warnings(vault)
        self.assertEqual(len(found), 2, found)
        self.assertTrue(any("LESSON-six.md" in w for w in found), found)
        self.assertTrue(any("LESSON-six-nested.md" in w for w in found), found)
        self.assertFalse(any("LESSON-five" in w for w in found), found)

    def test_validate_prints_the_cap_warning_as_a_sentence_ending_in_its_code(self):
        """Adversarial where: the new code added to `check_vault` but not to
        the word list, so a person reads `lesson_body_over_cap: path` as
        jargon, or the rewriting hides the lesson's path. `plain_finding`
        must lead with the details, end with the bracketed code, and carry a
        sentence; the real report must show the same line."""
        code = "lesson_body_over_cap"
        rendered = validate.plain_finding(f"{code}: probe/path.md")
        self.assertNotEqual(rendered, f"{code}: probe/path.md")
        self.assertFalse(rendered.startswith(code), rendered)
        self.assertTrue(rendered.endswith(f"({code})"), rendered)
        self.assertIn("probe/path.md", rendered)
        sentence = rendered[: -len(f"({code})")].replace("probe/path.md", " ")
        self.assertGreaterEqual(len(sentence.split()), 4, rendered)
        self.assertNotIn("frontmatter", sentence.lower())
        vault = self.make_vault({"LESSON-six.md": lesson(numbered(6))})
        self.assertEqual(len(self.cap_warnings(vault)), 1)
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            validate.run([])
        lines = [ln for ln in err.getvalue().splitlines() if f"({code})" in ln]
        self.assertEqual(len(lines), 1, err.getvalue())
        self.assertIn("LESSON-six.md", lines[0])
        self.assertFalse(re.search(rf"\b{code}:", lines[0]), lines[0])


if __name__ == "__main__":
    unittest.main()
