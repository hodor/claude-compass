"""Tests for a `compass review` of several files: one request carrying the
files in the order given, `session` and `project`, a commit check on every
file, `--why` reasons, the pending listing, verdict validation of the optional
per-file marks, and the lines and reprints printed after the answer.

Adversarial themes: order lost or sorted, the first file standing in for all
of them, a dirty file hiding behind a clean first one, a reason attached to
the wrong file, a verdict that is half right (one good entry beside a bad
one), and a reprint that covers every file or only the first.

The fixture is the one `test_review.py` builds: a committed temp project, a
stubbed URI opener and focus probe, and no real Obsidian.
"""

import json
import os
import shutil
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reviewlib  # noqa: E402
from tests import test_review  # noqa: E402

REQUEST_KEYS = {"id", "surface", "file", "files", "session", "project", "title", "return", "commit"}


class MultiFileProject(test_review.ReviewProject):
    """The single-file fixture plus two more committed documents. The request
    order used throughout is plan, spec 1, spec 2, which is neither
    alphabetical by path nor the order the fixture created them in."""

    def setUp(self):
        super().setUp()
        (self.vault / "plans").mkdir()
        self.plan = self.vault / "plans" / "PLAN-001-z.md"
        self.plan.write_text("# Plan Z\nplan-body\n", encoding="utf-8")
        self.doc.write_text("# X\nspec-one-body\n", encoding="utf-8")
        self.spec2 = self.vault / "specs" / "SPEC-002-y.md"
        self.spec2.write_text("# Y\nspec-two-body\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "three documents")
        self.commit = self.git("rev-parse", "HEAD").stdout.strip()
        self.configure()
        self.trio = [self.plan, self.doc, self.spec2]
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def rel(self, path):
        return path.relative_to(self.vault).as_posix()

    def requests(self):
        directory = reviewlib.review_dir(self.vault)
        if not directory.is_dir():
            return []
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.request.json"))]

    def send(self, *args):
        code, out, err = self.review(*args, "--no-wait")
        self.assertEqual(code, 0, (out, err))
        rid = out.split()[1]
        path = reviewlib.review_dir(self.vault) / f"{rid}.request.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def answer(self, files, extra=None, during=None, delay=0.3):
        """Write an `approved` verdict carrying `files` (omitted when None) for
        the first request without one; `during` runs first, standing for the
        human's edits."""
        directory = reviewlib.review_dir(self.vault)

        def write():
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                waiting = [p for p in sorted(directory.glob("*.request.json"))
                           if not reviewlib.verdict_path(p).exists()] if directory.is_dir() else []
                if waiting:
                    time.sleep(delay)
                    req = json.loads(waiting[0].read_text(encoding="utf-8"))
                    if during:
                        during()
                    body = {"id": req["id"], "file": req["file"], "verdict": "approved", "notes": "n", "at": "t"}
                    if files is not None:
                        body["files"] = files
                    body.update(extra or {})
                    reviewlib.verdict_path(waiting[0]).write_text(json.dumps(body), encoding="utf-8")
                    return
                time.sleep(0.05)

        threading.Thread(target=write, daemon=True).start()


class MultiFileRequest(MultiFileProject):
    def test_request_keeps_the_given_order_and_file_is_the_first(self):
        """Adversarial where: the files are sorted, deduplicated against the
        vault listing, or only the first survives; `file` drifts from
        `files[0]` (the shipped plugin reads `file`); a flag between two
        paths ends the file list; an unlisted key appears or a listed one
        goes missing."""
        request = self.send(str(self.plan), "--title", "Three", str(self.doc), str(self.spec2))
        self.assertEqual(set(request), REQUEST_KEYS)
        self.assertEqual([f["file"] for f in request["files"]],
                         ["plans/PLAN-001-z.md", "specs/SPEC-001-x.md", "specs/SPEC-002-y.md"])
        self.assertEqual(request["file"], "plans/PLAN-001-z.md")
        self.assertEqual(request["file"], request["files"][0]["file"])
        self.assertEqual(request["title"], "Three")
        self.assertEqual(request["commit"], self.commit)
        self.assertEqual(len(self.opened), 1, "one review, one link")
        self.assertEqual(len(self.requests()), 1)

    def test_session_is_the_environment_value_or_empty_and_project_is_the_vault_folder(self):
        """Adversarial where: `session` is None or missing when the variable
        is unset (the spec says empty), is read from the wrong variable, or
        `project` follows CLAUDE_PROJECT_DIR instead of the folder that holds
        the vault the request lands in."""
        elsewhere = self.base / "elsewhere"
        (elsewhere / ".compass").mkdir(parents=True)
        rows = [
            ("session set", {"CLAUDE_CODE_SESSION_ID": "sess-7f3a"}, "sess-7f3a"),
            ("session unset", {}, ""),
            ("session empty", {"CLAUDE_CODE_SESSION_ID": ""}, ""),
            ("project dir names another project", {"CLAUDE_CODE_SESSION_ID": "s2", "CLAUDE_PROJECT_DIR": str(elsewhere)}, "s2"),
        ]
        for name, env, session in rows:
            with self.subTest(name), mock.patch.dict(os.environ, env):
                request = self.send(*map(str, self.trio))
                self.assertEqual(request["session"], session)
                self.assertEqual(request["project"], self.tmp.name)

    def test_why_reasons_attach_to_their_own_file_whatever_the_flag_order(self):
        """Adversarial where: reasons are applied by position instead of by
        path, a reason containing `=` is cut at the second `=`, a file with
        no reason gets a neighbour's, or the reasons reorder the files."""
        request = self.send(
            str(self.plan), str(self.doc), str(self.spec2),
            "--why", f"{self.spec2}=compare: a=b held",
            "--why", f"{self.plan}=the plan first",
        )
        self.assertEqual([f["file"] for f in request["files"]],
                         ["plans/PLAN-001-z.md", "specs/SPEC-001-x.md", "specs/SPEC-002-y.md"])
        whys = [f.get("why") for f in request["files"]]
        self.assertEqual(whys[0], "the plan first")
        self.assertIn(whys[1], (None, ""), "no reason was given for the middle file")
        self.assertEqual(whys[2], "compare: a=b held")

    def test_a_one_file_request_is_exactly_the_old_shape_even_with_a_session(self):
        """Adversarial where: a one-file review gains `files`, `session` or
        `project` (the one-file contract is unchanged), most likely when the
        session variable is set."""
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "sess-9"}):
            request = self.send(str(self.doc), "--title", "One")
        self.assertEqual(request, {"id": request["id"], "surface": "obsidian", "file": "specs/SPEC-001-x.md",
                                   "title": "One", "return": True, "commit": self.commit})

    def test_a_file_that_cannot_go_out_refuses_the_whole_review_and_names_it(self):
        """Adversarial where: only the first file is checked, a dirty file
        behind clean ones slips through, the second failure is named instead
        of the first, or a request is written (or a link opened) before the
        refusal."""
        missing = self.vault / "specs" / "nope.md"

        def dirty(path):
            path.write_text(path.read_text(encoding="utf-8") + "more\n", encoding="utf-8")

        def untracked():
            path = self.vault / "specs" / "SPEC-003-new.md"
            path.write_text("# new\n", encoding="utf-8")
            return path

        new = untracked()
        rows = [
            ("first is dirty", [self.plan, self.doc, self.spec2], self.plan, [self.doc, self.spec2], dirty),
            ("middle is dirty", [self.plan, self.doc, self.spec2], self.doc, [], dirty),
            ("last is dirty", [self.plan, self.doc, self.spec2], self.spec2, [], dirty),
            ("last is untracked", [self.plan, self.doc, new], new, [], lambda p: None),
            ("two dirty, first named", [self.plan, self.doc, self.spec2], self.doc, [self.spec2], dirty),
            ("last is missing", [self.plan, self.doc, missing], missing, [], lambda p: None),
        ]
        for name, given, culprit, also_dirty, break_it in rows:
            with self.subTest(name):
                self.git("checkout", "--", ".")
                break_it(culprit)
                for extra in also_dirty:
                    dirty(extra)
                code, out, _ = self.review(*map(str, given), "--timeout", "3")
                self.assertEqual(code, 1, out)
                first = out.splitlines()[0]
                self.assertTrue(first.startswith("not configured: "), first)
                self.assertIn(str(culprit), first)
                for other in also_dirty:
                    self.assertNotIn(str(other), first, "only the first failing file is named")
                self.assertEqual(self.requests(), [])
                self.assertEqual(self.opened, [])

    def test_status_names_the_first_file_and_how_many_more(self):
        """Adversarial where: `--status` lists only the first file with no
        hint of the rest, miscounts (counts the first file among the more),
        or adds a suffix to a one-file review."""
        for name, given, tail in [
            ("three files", self.trio, "plans/PLAN-001-z.md (+2 more)"),
            ("two files", [self.doc, self.spec2], "specs/SPEC-001-x.md (+1 more)"),
            ("one file", [self.plan], "plans/PLAN-001-z.md"),
        ]:
            with self.subTest(name):
                request = self.send(*map(str, given))
                code, out, _ = self.review("--status")
                self.assertEqual(code, 0)
                self.assertEqual(out.splitlines(), [f"pending {request['id']} {tail}"])
                self.assertEqual(self.review("--cancel", request["id"])[0], 0)

    def test_a_malformed_why_is_a_usage_error_and_sends_nothing(self):
        """Adversarial where: `--why` with no value raises IndexError or exits
        2, or a reason with no `<path>=` is accepted and attached to
        something."""
        for name, tail in [("no value", ["--why"]), ("no equals sign", ["--why", "just words"])]:
            with self.subTest(name):
                code, _, err = self.review(*map(str, self.trio), *tail, "--no-wait")
                self.assertEqual(code, 1)
                self.assertNotEqual(err.strip(), "")
                self.assertEqual(self.requests(), [])


class VerdictFiles(MultiFileProject):
    def test_valid_verdict_checks_the_files_list_entry_by_entry(self):
        """Adversarial where: a malformed `files` is accepted, only the first
        entry is checked (one good entry excuses a bad one), `read` is
        coerced from a string or a number, or the old verdict with no `files`
        is rejected."""
        request = {"id": "r1", "file": "a.md", "files": [{"file": "a.md"}, {"file": "b.md"}]}
        base = {"id": "r1", "verdict": "changes"}
        good = {"file": "a.md", "read": True, "note": "n"}
        rows = [
            ("old shape, no files", {}, True),
            ("empty list", {"files": []}, True),
            ("note absent", {"files": [{"file": "a.md", "read": False}]}, True),
            ("two good entries", {"files": [good, {"file": "b.md", "read": False}]}, True),
            ("files is a string", {"files": "a.md"}, False),
            ("files is an object", {"files": good}, False),
            ("entry is a string", {"files": ["a.md"]}, False),
            ("entry has no file", {"files": [{"read": True}]}, False),
            ("file is a number", {"files": [{"file": 3, "read": True}]}, False),
            ("read is the string true", {"files": [{"file": "a.md", "read": "true"}]}, False),
            ("read is the number one", {"files": [{"file": "a.md", "read": 1}]}, False),
            ("read is missing", {"files": [{"file": "a.md"}]}, False),
            ("note is a number", {"files": [{"file": "a.md", "read": True, "note": 5}]}, False),
            ("note is a list", {"files": [{"file": "a.md", "read": True, "note": ["x"]}]}, False),
            ("first good, second bad", {"files": [good, {"file": "b.md", "read": "yes"}]}, False),
            ("first bad, second good", {"files": [{"file": "a.md", "read": "yes"}, good]}, False),
        ]
        for name, extra, ok in rows:
            with self.subTest(name):
                self.assertIs(bool(reviewlib.valid_verdict({**base, **extra}, request)), ok)

    def test_the_waiter_does_not_take_a_verdict_with_a_malformed_files_list(self):
        """Adversarial where: the waiter prints marks built from a `files`
        value that is not a list of entries, or crashes on it, instead of
        waiting on."""
        self.answer("not a list")
        code, out, _ = self.review(*map(str, self.trio), "--timeout", "1.5")
        self.assertEqual(code, 1)
        self.assertTrue(out.splitlines()[-1].startswith("timeout "), out)
        self.assertNotIn("as the human left it", out)

    def test_an_old_verdict_without_files_is_taken_for_a_several_file_review(self):
        """Adversarial where: a verdict from a surface that does not know
        about `files` leaves the waiter waiting until its timeout."""
        self.answer(None)
        code, out, _ = self.review(*map(str, self.trio), "--timeout", "5")
        self.assertEqual(code, 0, out)
        self.assertIn('"verdict": "approved"', out)


class AfterTheAnswer(MultiFileProject):
    FILES = [
        {"file": "plans/PLAN-001-z.md", "read": True},
        {"file": "specs/SPEC-001-x.md", "read": False, "note": "needs:\n  work"},
        {"file": "specs/SPEC-002-y.md", "read": True},
    ]

    def lines_of(self, out):
        lines = out.splitlines()
        header = next(i for i, ln in enumerate(lines) if ln.startswith("--- changes since "))
        return lines, header

    def test_one_line_per_file_with_its_mark_and_note_before_the_changes(self):
        """Adversarial where: a file with no note is skipped, the unread mark
        reads as read, a multi-line note breaks the one-line format, the
        lines come out in another order than the request, or they land after
        the change report."""
        self.answer(self.FILES)
        code, out, _ = self.review(*map(str, self.trio), "--timeout", "5")
        self.assertEqual(code, 0, out)
        lines, header = self.lines_of(out)
        expected = [
            "file plans/PLAN-001-z.md read",
            "file specs/SPEC-001-x.md unread note: needs: work",
            "file specs/SPEC-002-y.md read",
        ]
        start = lines.index(expected[0])
        self.assertEqual(lines[start:start + 3], expected)
        self.assertLess(start + 2, header)
        self.assertGreater(start, lines.index("}"), "the verdict JSON comes first")

    def test_only_files_with_a_note_or_an_edit_are_reprinted_after_the_changes(self):
        """Adversarial where: every file is reprinted, only the first file is
        (as a one-file review does), a file with a note is not, a file the
        human edited but did not annotate is not, or the reprint carries the
        committed text instead of what the human left."""
        edited = self.spec2

        def human_edit():
            edited.write_text("# Y\nhuman edit of two\n", encoding="utf-8")

        self.answer(self.FILES, extra={"edited": ["specs/SPEC-002-y.md"]}, during=human_edit)
        code, out, _ = self.review(*map(str, self.trio), "--timeout", "5")
        self.assertEqual(code, 0, out)
        lines, header = self.lines_of(out)
        marker = "--- {} as the human left it ---"
        self.assertNotIn(marker.format("plans/PLAN-001-z.md"), lines, "no note, no edit")
        noted = lines.index(marker.format("specs/SPEC-001-x.md"))
        changed = lines.index(marker.format("specs/SPEC-002-y.md"))
        self.assertGreater(noted, header)
        self.assertGreater(changed, noted, "reprints follow the request order")
        self.assertEqual(lines[noted + 1:noted + 3], ["# X", "spec-one-body"])
        self.assertEqual(lines[changed + 1:changed + 3], ["# Y", "human edit of two"])
        self.assertEqual(sum(ln.endswith("as the human left it ---") for ln in lines), 2)

    def test_with_no_notes_and_no_edits_nothing_is_reprinted(self):
        """Adversarial where: the first file is reprinted by habit when no
        file has a note or an edit, or the per-file lines go missing along
        with the reprints."""
        self.answer([{"file": self.rel(p), "read": True} for p in self.trio])
        code, out, _ = self.review(*map(str, self.trio), "--timeout", "5")
        self.assertEqual(code, 0, out)
        lines, header = self.lines_of(out)
        self.assertNotIn("as the human left it", out)
        self.assertEqual([ln for ln in lines if ln.startswith("file ")],
                         [f"file {self.rel(p)} read" for p in self.trio])
        self.assertEqual(lines[header], self.changes_header)


if __name__ == "__main__":
    unittest.main()
