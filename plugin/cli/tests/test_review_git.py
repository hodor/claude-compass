"""Tests for the git side of `compass review`: a document with uncommitted
changes is refused, the request records the commit it was sent at, and after
the verdict the command prints the repository's changes since that commit
before the reviewed document's text.

Adversarial themes: a dirty check that looks at the wrong scope (the whole
repo instead of the file, or a name prefix instead of the exact path), a
commit recorded after instead of at request time, a diff taken against the
moving HEAD instead of the request's commit, untracked names that git quotes
or collapses into a directory, paths relative to the wrong directory when the
vault sits below the repository root, and git missing or the vault outside
any repository.

Every test builds a real temporary git repository holding a `.compass` vault,
runs `compass review` with the working directory outside it, and stubs the
Obsidian surface the way `test_review.py` does.
"""

import importlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reviewlib  # noqa: E402
from review_surfaces import obsidian as obsidian_surface  # noqa: E402

HEADER = re.compile(r"^--- changes since ([0-9a-f]{7,40}) ---$")
DOC_TEXT = "---\ntitle: x\n---\n\n# X\n"
DOC_REL = "specs/SPEC-001-x.md"
MARKER = f"--- {DOC_REL} as the human left it ---"


class GitReviewBase(unittest.TestCase):
    """A temp directory holding `repo/` (the git repository), `outside/` (the
    working directory and the Obsidian vault list, outside the repository)
    and, under `repo/<SUB>/`, the `.compass` vault when SUB is set."""

    SUB = ""
    INIT_REPO = True

    def setUp(self):
        self.base = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.root = self.base / "repo"
        self.outside = self.base / "outside"
        self.root.mkdir()
        self.outside.mkdir()
        self.project = self.root / self.SUB if self.SUB else self.root
        self.vault = self.project / ".compass"
        self.doc = self.vault / "specs" / "SPEC-001-x.md"
        (self.outside / "gitconfig").write_text("", encoding="utf-8")
        env = {
            "COMPASS_OBSIDIAN_CONFIG": str(self.outside / "obsidian.json"),
            "CLAUDE_PROJECT_DIR": str(self.project),
            "GIT_CEILING_DIRECTORIES": str(self.base),
            "GIT_CONFIG_GLOBAL": str(self.outside / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.opened = []
        for target, value in [("open_uri", self.opened.append), ("has_focus", lambda: False)]:
            p = mock.patch.object(obsidian_surface, target, value)
            p.start()
            self.addCleanup(p.stop)
        previous = os.getcwd()
        os.chdir(self.outside)
        self.addCleanup(os.chdir, previous)
        self.thread_errors = []

        self.put(self.root / ".gitignore", ".compass/tmp/\n*.tmp\n")
        self.put(self.root / "src" / "app.py", "print('app')\n")
        self.put(self.root / "README.md", "readme\n")
        self.configure_obsidian()
        if self.INIT_REPO:
            self.git("init", "-q")
            self.git("config", "user.name", "Tester")
            self.git("config", "user.email", "tester@example.invalid")
            self.git("config", "core.autocrlf", "false")
            self.git("add", "-A")
            self.git("commit", "-q", "-m", "first")
            self.first_commit = self.head()
            self.put(self.doc, DOC_TEXT)
            for name in ("SPEC-010-a.md", "SPEC-011-b.md", "SPEC-001-xy.md"):
                self.put(self.vault / "specs" / name, f"# {name}\n")
            self.commit_all("second")

    def configure_obsidian(self):
        obsidian = self.vault / ".obsidian"
        obsidian.mkdir(parents=True, exist_ok=True)
        (self.outside / "obsidian.json").write_text(
            json.dumps({"vaults": {"abc123": {"path": str(self.vault)}}}), encoding="utf-8")
        plugin = obsidian / "plugins" / obsidian_surface.PLUGIN_ID
        plugin.mkdir(parents=True, exist_ok=True)
        (plugin / "main.js").write_text("//", encoding="utf-8")
        (obsidian / "community-plugins.json").write_text(
            json.dumps([obsidian_surface.PLUGIN_ID]), encoding="utf-8")

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.root, capture_output=True,
                                text=True, encoding="utf-8")
        if result.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
        return result

    def head(self):
        return self.git("rev-parse", "HEAD").stdout.strip()

    def commit_all(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def diff_lines(self, sha):
        return self.git("-c", "color.ui=never", "diff", sha).stdout.splitlines()

    def rel(self, path):
        return Path(path).relative_to(self.root).as_posix()

    @staticmethod
    def put(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))

    def review(self, *args):
        module = importlib.import_module("commands.review")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = module.run(list(args))
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def requests(self):
        directory = reviewlib.review_dir(self.vault)
        return sorted(directory.glob("*.request.json")) if directory.is_dir() else []

    def run_review(self, during=None, extra=None, delay=0.3, files=None):
        """Review `files` (default: `self.doc`); a helper thread runs `during`
        (the human's edits) and then writes an approved verdict plus `extra`
        for the new request."""
        known = set(self.requests())

        def answer():
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    fresh = [p for p in self.requests() if p not in known]
                    if fresh:
                        time.sleep(delay)
                        request = json.loads(fresh[0].read_text(encoding="utf-8"))
                        if during:
                            during()
                        body = {"id": request["id"], "file": request["file"],
                                "verdict": "approved", "notes": "n", "at": "t"}
                        body.update(extra or {})
                        reviewlib.verdict_path(fresh[0]).write_text(json.dumps(body), encoding="utf-8")
                        return
                    time.sleep(0.05)
            except Exception as exc:
                self.thread_errors.append(repr(exc))

        thread = threading.Thread(target=answer, daemon=True)
        thread.start()
        result = self.review(*(str(f) for f in (files or [self.doc])), "--timeout", "20")
        thread.join(5)
        self.assertEqual(self.thread_errors, [])
        return result

    def vault_rel(self, path):
        """`path` as the Obsidian vault names it, the form `edited` entries take."""
        return Path(path).relative_to(self.vault).as_posix()

    def expected_report(self, commit, shown):
        """The report lines git yields for `commit`: the full diff of the repo
        paths in `shown`, then `changed <path>` for each other changed path in
        git's own order."""
        shown = [self.rel(p) for p in shown]
        diff = self.git("-c", "color.ui=never", "diff", "--no-ext-diff", commit, "--", *shown)
        names = self.git("-c", "core.quotepath=false", "diff", "--name-only", "-z", commit).stdout
        others = [n for n in names.split("\0") if n and n not in shown]
        return diff.stdout.splitlines() + [f"changed {n}" for n in others]

    def report(self, out):
        """The change report of a several-file review: the lines after the
        header up to the first document text, or the end of the output."""
        lines = out.splitlines()
        headers = [i for i, line in enumerate(lines) if HEADER.match(line)]
        self.assertEqual(len(headers), 1, out)
        rest = lines[headers[0] + 1:]
        stops = [i for i, line in enumerate(rest) if line.startswith("--- ") and line.endswith(" as the human left it ---")]
        return rest[:stops[0]] if stops else rest

    def sections(self, out):
        """`(lines, header_index, marker_index, short_sha)` of a finished review."""
        lines = out.splitlines()
        headers = [i for i, line in enumerate(lines) if HEADER.match(line)]
        self.assertEqual(len(headers), 1, out)
        self.assertIn(MARKER, lines, out)
        marker = lines.index(MARKER)
        self.assertLess(headers[0], marker, out)
        return lines, headers[0], marker, HEADER.match(lines[headers[0]]).group(1)


class GitReview(GitReviewBase):
    def test_a_document_with_uncommitted_changes_is_refused_and_no_request_is_written(self):
        """Adversarial where: staged-only edits, a staged new file, an untracked
        file or a worktree edit slip past the dirty check, the command writes a
        request (or waits) before refusing, or the first line deviates."""
        specs = self.vault / "specs"

        def modified():
            path = specs / "SPEC-010-a.md"
            self.put(path, "# SPEC-010-a.md\nmore\n")
            return path

        def staged_edit():
            path = specs / "SPEC-011-b.md"
            self.put(path, "# SPEC-011-b.md\nstaged\n")
            self.git("add", self.rel(path))
            return path

        def untracked():
            path = specs / "SPEC-012-c.md"
            self.put(path, "# c\n")
            return path

        def staged_new():
            path = specs / "SPEC-013-d.md"
            self.put(path, "# d\n")
            self.git("add", self.rel(path))
            return path

        for name, prepare in [("modified in the worktree", modified), ("staged edit", staged_edit),
                              ("untracked", untracked), ("staged new file", staged_new)]:
            with self.subTest(name):
                path = prepare()
                code, out, _ = self.review(str(path), "--timeout", "3")
                self.assertEqual(code, 1, out)
                self.assertEqual(out.splitlines()[0],
                                 f"not configured: {path} has uncommitted changes; commit first")
                self.assertEqual(self.requests(), [])
                self.assertEqual(self.opened, [])

    def test_git_missing_from_the_path_refuses_without_a_request(self):
        """Adversarial where: an absent git executable raises FileNotFoundError
        out of the command (exit 2 or a traceback) instead of refusing."""
        with mock.patch.dict(os.environ, {"PATH": str(self.outside)}):
            code, out, _ = self.review(str(self.doc), "--timeout", "3")
        self.assertEqual(code, 1, out)
        self.assertTrue(out.splitlines()[0].startswith("not configured: "), out)
        self.assertEqual(self.requests(), [])

    def test_request_carries_the_full_head_sha_and_other_dirty_files_do_not_block_it(self):
        """Adversarial where: `commit` is missing, abbreviated, the repo's first
        commit rather than HEAD, or the dirty check matches by name prefix or by
        whole repository so a dirty sibling, a `.bak` copy or another directory
        blocks a clean document."""
        self.put(self.vault / "specs" / "SPEC-001-x.md.bak", "bak\n")
        self.put(self.vault / "specs" / "SPEC-001-xy.md", "# dirty sibling\n")
        self.put(self.root / "src" / "app.py", "print('changed')\n")
        self.put(self.root / "stray.txt", "stray\n")
        head = self.head()
        self.assertNotEqual(head, self.first_commit)
        code, out, _ = self.review(str(self.doc), "--title", "Spec one", "--no-wait")
        self.assertEqual(code, 0, out)
        first = out.splitlines()[0].split()
        self.assertEqual(first[0], "requested")
        request = json.loads((reviewlib.review_dir(self.vault) / f"{first[1]}.request.json").read_text())
        self.assertRegex(request["commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(request["commit"], head)
        rest = {k: v for k, v in request.items() if k != "commit"}
        self.assertEqual(rest, {"id": first[1], "surface": "obsidian", "file": DOC_REL,
                                "title": "Spec one", "return": True})

    def test_changes_section_sits_between_the_carried_lines_and_the_document_text(self):
        """Adversarial where: the section is printed after the document text,
        before the verdict JSON, ahead of the comment/edited lines, with the
        diff of a different commit, or the human's text is cut off after it."""
        extra = {"comments": [{"file": "specs/SPEC-002-y.md", "note": "why: unclear"}],
                 "edited": ["specs/SPEC-003-w.md"]}
        before = self.head()

        def edit():
            self.put(self.doc, DOC_TEXT + "\nhuman edit\n")

        code, out, _ = self.run_review(during=edit, extra=extra)
        self.assertEqual(code, 0, out)
        lines, header, marker, short = self.sections(out)
        self.assertTrue(before.startswith(short), (before, short))
        self.assertEqual(lines[header - 2:header],
                         ["comment specs/SPEC-002-y.md: why: unclear", "edited specs/SPEC-003-w.md"])
        self.assertEqual(lines[header - 3], "}")
        expected = self.diff_lines(before)
        self.assertIn("+human edit", expected)
        self.assertEqual(lines[header + 1:marker], expected)
        self.assertEqual("\n".join(lines[marker + 1:]), (DOC_TEXT + "\nhuman edit\n").rstrip("\n"))

    def test_diff_is_taken_against_the_request_commit_and_an_unlisted_file_is_only_named(self):
        """Adversarial where: the diff is taken against the moving HEAD so a
        commit made during the review hides everything the human changed, or a
        change outside the review's files still prints its diff lines instead
        of the single `changed <path>` line."""
        original = DOC_TEXT

        def edit_outside_the_vault():
            self.put(self.root / "src" / "app.py", "print('edited during review')\n")

        def edit_and_commit_during_the_wait():
            self.put(self.doc, original + "\ncommitted while reviewing\n")
            self.commit_all("committed during the review")

        for name, during in [("edit outside the vault", edit_outside_the_vault),
                             ("edit committed during the wait", edit_and_commit_during_the_wait)]:
            with self.subTest(name):
                before = self.head()
                code, out, _ = self.run_review(during=during)
                self.assertEqual(code, 0, out)
                lines, header, marker, short = self.sections(out)
                self.assertTrue(before.startswith(short), (name, before, short))
                if name == "edit outside the vault":
                    self.assertEqual(lines[header + 1:marker], ["changed src/app.py"])
                    self.commit_all("clean up after the row")
                else:
                    expected = self.diff_lines(before)
                    self.assertTrue(expected, name)
                    self.assertEqual(lines[header + 1:marker], expected)
                    self.assertNotEqual(self.head(), before)

    def test_full_diff_covers_reviewed_and_edited_files_and_every_other_change_is_one_line(self):
        """Adversarial where: a changed file outside the request's files and
        the answer's `edited` list (a name-prefix sibling, a deleted file, a
        non-ASCII path git would quote) leaks diff lines or loses its
        `changed` line, or a reviewed file after the first, or an edited one,
        gets no diff."""
        spec = self.vault / "specs"
        listed = spec / "SPEC-010-a.md"
        edited = spec / "SPEC-011-b.md"
        sibling = spec / "SPEC-001-xy.md"
        accented = self.root / "notes" / "na\u00efve file.md"
        self.put(accented, "a\n")
        self.commit_all("add a non-ASCII path")
        before = self.head()

        def change():
            self.put(self.doc, DOC_TEXT + "\nREVIEWED-MARK\n")
            self.put(listed, "# listed\nLISTED-MARK\n")
            self.put(edited, "# edited\nEDITED-MARK\n")
            self.put(sibling, "# sibling\nOTHER-MARK\n")
            self.put(self.root / "src" / "app.py", "OTHER-MARK\n")
            self.put(accented, "OTHER-MARK\n")
            os.remove(self.root / "README.md")

        code, out, _ = self.run_review(during=change, files=[self.doc, listed],
                                       extra={"edited": [self.vault_rel(edited)]})
        self.assertEqual(code, 0, out)
        section = self.report(out)
        self.assertEqual(section, self.expected_report(before, [self.doc, listed, edited]))
        self.assertEqual(sorted(line for line in section if line.startswith("changed ")), sorted([
            f"changed {self.rel(sibling)}", "changed src/app.py", "changed README.md",
            "changed notes/na\u00efve file.md"]))
        self.assertFalse([line for line in section if "OTHER-MARK" in line], section)
        for mark in ("REVIEWED-MARK", "LISTED-MARK", "EDITED-MARK"):
            self.assertIn(f"+{mark}", section)

    def test_an_edited_file_with_no_change_prints_nothing_and_an_untracked_one_is_only_named(self):
        """Adversarial where: an `edited` entry that did not change prints a
        `changed` line or an empty diff header, an entry git never saw makes
        the diff fail with an ambiguous-path error, or an untracked edited
        file is listed as both untracked and changed."""
        listed = self.vault / "specs" / "SPEC-010-a.md"
        fresh = self.vault / "specs" / "SPEC-099-new.md"
        rows = [
            ("edited but unchanged", [self.vault_rel(listed)], None, []),
            ("edited path git never saw", ["specs/SPEC-404-gone.md"], None, []),
            ("edited and untracked", [self.vault_rel(fresh)],
             lambda: self.put(fresh, "new\n"), [f"untracked {self.rel(fresh)}"]),
        ]
        for name, edited, during, expected in rows:
            with self.subTest(name):
                code, out, _ = self.run_review(during=during, extra={"edited": edited})
                self.assertEqual(code, 0, out)
                lines, header, marker, _ = self.sections(out)
                self.assertEqual(lines[header + 1:marker], expected, out)
                if fresh.exists():
                    os.remove(fresh)

    def test_the_line_cap_bounds_the_diff_and_the_changed_and_untracked_lines_still_follow(self):
        """Adversarial where: a reviewed file changed by thousands of lines
        floods the report, or the cap line swallows the `changed` and
        `untracked` lines that come after the diff."""
        def change():
            self.put(self.doc, "".join(f"line {n}\n" for n in range(reviewlib.MAX_DIFF_LINES * 2)))
            self.put(self.root / "src" / "app.py", "print('other')\n")
            self.put(self.root / "stray.txt", "s\n")

        code, out, _ = self.run_review(during=change)
        self.assertEqual(code, 0, out)
        lines, header, marker, _ = self.sections(out)
        section = lines[header + 1:marker]
        cap = reviewlib.MAX_DIFF_LINES
        self.assertRegex(section[cap], r"^\(\d+ more diff lines: git diff .*\)$")
        self.assertEqual(section[cap + 1:], ["changed src/app.py", "untracked stray.txt"])

    def test_every_untracked_file_is_named_repo_relative_after_the_diff(self):
        """Adversarial where: untracked files in a new directory are collapsed
        to `dir/`, names with a space or non-ASCII letters come back quoted or
        mis-decoded, an ignored file is listed, a tracked edit is listed as
        untracked, or a name is printed twice."""
        def create():
            self.put(self.root / "notes" / "deep" / "two words.md", "a\n")
            self.put(self.vault / "specs" / "naïve.md", "b\n")
            self.put(self.root / "drafts" / "a.md", "c\n")
            self.put(self.root / "drafts" / "b.md", "d\n")
            self.put(self.vault / "specs" / "SPEC-099-new.md", "e\n")
            self.put(self.root / "scratch.tmp", "ignored\n")
            self.put(self.doc, DOC_TEXT + "\ntracked edit\n")

        before = self.head()
        code, out, _ = self.run_review(during=create)
        self.assertEqual(code, 0, out)
        lines, header, marker, _ = self.sections(out)
        section = lines[header + 1:marker]
        expected_diff = self.diff_lines(before)
        self.assertEqual(section[:len(expected_diff)], expected_diff)
        tail = section[len(expected_diff):]
        expected_names = [
            "notes/deep/two words.md",
            self.rel(self.vault / "specs" / "naïve.md"),
            "drafts/a.md",
            "drafts/b.md",
            self.rel(self.vault / "specs" / "SPEC-099-new.md"),
        ]
        self.assertEqual(sorted(tail), sorted(f"untracked {name}" for name in expected_names))

    def test_no_changes_prints_the_header_with_nothing_under_it(self):
        """Adversarial where: an empty change set drops the header, prints a
        placeholder line under it, or leaves the marker glued to the header."""
        before = self.head()
        code, out, _ = self.run_review()
        self.assertEqual(code, 0, out)
        lines, header, marker, short = self.sections(out)
        self.assertTrue(before.startswith(short), (before, short))
        self.assertEqual(marker, header + 1, lines)
        self.assertEqual(lines[0].split()[0], "requested")
        self.assertEqual("\n".join(lines[marker + 1:]), DOC_TEXT.rstrip("\n"))


class NestedVault(GitReviewBase):
    SUB = "proj"

    def test_edited_paths_and_report_names_are_repo_relative_when_the_vault_is_below_the_repo_root(self):
        """Adversarial where: an `edited` path relative to the vault is handed
        to git unchanged (so it matches nothing and the diff vanishes), or
        untracked and changed names are listed relative to the vault or the
        working directory, so files outside the project folder go missing."""
        edited = self.vault / "specs" / "SPEC-010-a.md"

        def create():
            self.put(self.root / "stray.txt", "s\n")
            self.put(self.vault / "specs" / "SPEC-099-new.md", "n\n")
            self.put(self.root / "README.md", "readme edited\n")
            self.put(edited, "# edited below the repo root\n")
            self.put(self.doc, DOC_TEXT + "\nreviewed edit\n")

        before = self.head()
        code, out, _ = self.run_review(during=create, extra={"edited": [self.vault_rel(edited)]})
        self.assertEqual(code, 0, out)
        lines, header, marker, _ = self.sections(out)
        section = lines[header + 1:marker]
        expected = self.expected_report(before, [self.doc, edited])
        self.assertIn(f"diff --git a/{self.rel(edited)} b/{self.rel(edited)}", expected)
        self.assertIn("changed README.md", expected)
        self.assertEqual(section[:len(expected)], expected)
        self.assertEqual(sorted(section[len(expected):]), sorted([
            "untracked stray.txt",
            "untracked proj/.compass/specs/SPEC-099-new.md",
        ]))


class EmptyRepository(GitReviewBase):
    INIT_REPO = False

    def test_a_file_in_a_repository_with_no_commits_is_refused_as_uncommitted(self):
        """Adversarial where: in a repository whose HEAD does not exist yet the
        command crashes resolving HEAD instead of refusing the untracked file."""
        self.put(self.doc, DOC_TEXT)
        self.git("init", "-q")
        code, out, _ = self.review(str(self.doc), "--timeout", "3")
        self.assertEqual(code, 1, out)
        self.assertEqual(out.splitlines()[0],
                         f"not configured: {self.doc} has uncommitted changes; commit first")
        self.assertEqual(self.requests(), [])


class OutsideRepository(GitReviewBase):
    INIT_REPO = False

    def test_a_vault_outside_any_repository_is_refused_with_its_own_message(self):
        """Adversarial where: the command crashes on git's "not a git
        repository" failure, reports it as uncommitted changes, or writes a
        request it cannot later diff."""
        self.put(self.doc, DOC_TEXT)
        code, out, _ = self.review(str(self.doc), "--timeout", "3")
        self.assertEqual(code, 1, out)
        self.assertEqual(out.splitlines()[0], f"not configured: {self.doc} is not in a git repository")
        self.assertEqual(self.requests(), [])
        self.assertEqual(self.opened, [])


if __name__ == "__main__":
    unittest.main()
