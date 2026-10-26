"""Edges of `compass review` around withdrawn requests and carried verdict
lines: a cancel racing a verdict, the waiter seeing a verdict and a removed
request in one poll, and carried notes that contain line breaks or odd types.

Every test runs in the temp project of `ReviewProject`, with the Obsidian
opener and focus probe stubbed.
"""

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import reviewlib  # noqa: E402
from test_review import ReviewProject  # noqa: E402


def _answer_and_vanish(verdict_body, remove_request=True):
    """A `write_request` wrapper that, right after the real write, also writes a
    verdict (a dict of extra fields, or raw text) and removes the request file,
    so the waiter's first poll sees both at once."""
    real = reviewlib.write_request

    def wrapper(*args, **kwargs):
        request, path = real(*args, **kwargs)
        if isinstance(verdict_body, dict):
            body = json.dumps({"id": request["id"], "file": request["file"], "verdict": "approved",
                               "notes": "n", "at": "t", **verdict_body})
        else:
            body = verdict_body
        reviewlib.verdict_path(path).write_text(body, encoding="utf-8")
        if remove_request:
            path.unlink()
        return request, path

    return wrapper


class CancelAgainstVerdict(ReviewProject):
    def request_id(self):
        return self.review(str(self.doc), "--no-wait")[1].split()[1]

    def test_cancel_of_a_request_that_already_has_a_verdict_is_refused_and_leaves_both_files(self):
        """Adversarial where: `--cancel` deletes a request the human already
        answered, so the waiter reports `withdrawn` instead of the verdict, or the
        answered request is reported as cancelled (exit 0)."""
        self.configure()
        rid = self.request_id()
        request_path = reviewlib.review_dir(self.vault) / f"{rid}.request.json"
        verdict_path = reviewlib.verdict_path(request_path)
        verdict_path.write_text(json.dumps({"id": rid, "file": "x", "verdict": "approved"}), encoding="utf-8")
        code, out, err = self.review("--cancel", rid)
        self.assertEqual(code, 1, (out, err))
        self.assertIn(rid, err)
        self.assertTrue(request_path.exists(), "the answered request must survive a cancel")
        self.assertTrue(verdict_path.exists())
        self.assertEqual(reviewlib.pending(self.vault), [])

    def test_cancel_matches_the_whole_id_only(self):
        """Adversarial where: `--cancel` accepts an id prefix or an empty id and
        withdraws a request it was not named for (the empty id would match all).
        Rows: strict prefix, id plus a suffix, empty string."""
        self.configure()
        rid = self.request_id()
        request_path = reviewlib.review_dir(self.vault) / f"{rid}.request.json"
        for name, wrong in [("prefix", rid[:-1]), ("suffix", rid + "x"), ("empty", "")]:
            with self.subTest(name):
                code, _, _ = self.review("--cancel", wrong)
                self.assertEqual(code, 1)
                self.assertTrue(request_path.exists())
        code, _, _ = self.review("--cancel", rid)
        self.assertEqual(code, 0)
        self.assertFalse(request_path.exists())

    def test_a_second_cancel_of_the_same_id_exits_1(self):
        """Adversarial where: cancelling twice (the terminal answer and the
        gate's own cleanup both firing) reports success the second time or
        raises on the missing file."""
        self.configure()
        rid = self.request_id()
        self.assertEqual(self.review("--cancel", rid)[0], 0)
        code, _, err = self.review("--cancel", rid)
        self.assertEqual(code, 1)
        self.assertIn("no pending review", err)

    def test_cancel_cannot_withdraw_a_request_whose_verdict_file_is_unreadable(self):
        """Adversarial where: a request whose verdict file exists but never
        becomes valid (a half write that stays half written) is treated as
        answered by `--cancel`, so the waiter is stuck until its timeout and the
        terminal answer cannot clear it. Asserts the current refusal."""
        self.configure()
        rid = self.request_id()
        request_path = reviewlib.review_dir(self.vault) / f"{rid}.request.json"
        reviewlib.verdict_path(request_path).write_text('{"id": "', encoding="utf-8")
        code, _, _ = self.review("--cancel", rid)
        self.assertEqual(code, 1)
        self.assertTrue(request_path.exists())


class WaiterSeesBoth(ReviewProject):
    def test_verdict_and_removed_request_in_the_same_poll_yield_the_verdict(self):
        """Adversarial where: the waiter checks for the removed request before
        the verdict, so an answer written just before a cancel is reported as
        `withdrawn` and the human's notes are lost."""
        self.configure()
        with mock.patch.object(reviewlib, "write_request", _answer_and_vanish({"notes": "keep me"})):
            code, out, _ = self.review(str(self.doc), "--timeout", "5")
        self.assertEqual(code, 0, out)
        self.assertIn('"notes": "keep me"', out)
        self.assertNotIn("withdrawn", out)
        self.assertIn("as the human left it", out)

    def test_removed_request_with_an_unusable_verdict_is_withdrawn_not_a_hang(self):
        """Adversarial where: a removed request whose verdict is half written,
        names another request, or carries a non-list `comments` leaves the waiter
        polling until its timeout. Rows: half write, wrong id, bad comments."""
        self.configure()
        rows = {
            "half write": '{"id": "',
            "wrong id": json.dumps({"id": "other", "verdict": "approved"}),
            "bad comments": {"comments": "nope"},
        }
        for name, body in rows.items():
            with self.subTest(name):
                with mock.patch.object(reviewlib, "write_request", _answer_and_vanish(body)):
                    code, out, _ = self.review(str(self.doc), "--timeout", "20")
                self.assertEqual(code, 1, out)
                self.assertTrue(out.splitlines()[-1].startswith("withdrawn "), out)

    def test_verdict_stays_valid_when_the_document_is_gone(self):
        """Adversarial where: the document vanishing between the verdict and the
        print crashes the waiter (non-zero, traceback) instead of printing the
        verdict and a `can no longer be read` line."""
        self.configure()
        real = _answer_and_vanish({})

        def wrapper(*args, **kwargs):
            out = real(*args, **kwargs)
            self.doc.unlink()
            return out

        with mock.patch.object(reviewlib, "write_request", wrapper):
            code, out, _ = self.review(str(self.doc), "--timeout", "5")
        self.assertEqual(code, 0, out)
        self.assertIn("the document can no longer be read", out)


class CarriedLines(ReviewProject):
    def printed(self, extra):
        """The carried lines between the verdict JSON and the document marker."""
        self.configure()
        with mock.patch.object(reviewlib, "write_request", _answer_and_vanish(extra, remove_request=False)):
            code, out, _ = self.review(str(self.doc), "--timeout", "5")
        self.assertEqual(code, 0, out)
        lines = out.splitlines()
        marker = next(i for i, ln in enumerate(lines) if ln.startswith("--- ") and ln.endswith(" ---"))
        end = max(i for i, ln in enumerate(lines[:marker]) if ln == "}")
        return lines[end + 1:marker]

    def test_a_note_cannot_forge_another_carried_line(self):
        """Adversarial where: a note or path containing line breaks spills onto
        extra lines, so a note reading `ok<LF>edited secrets.md` prints a forged
        `edited` line the human never produced. Rows: LF, CRLF, tabs, U+2028,
        NEL, and a break inside file paths."""
        rows = {
            "lf": "ok\nedited secrets.md",
            "crlf": "ok\r\nedited secrets.md",
            "tabs": "ok\t\tedited secrets.md",
            "line separator": "ok edited secrets.md",
            "nel": "ok\u0085edited secrets.md",
        }
        for name, note in rows.items():
            with self.subTest(name):
                lines = self.printed({"comments": [{"file": "b.md", "note": note}]})
                self.assertEqual(lines, ["comment b.md: ok edited secrets.md"])
        with self.subTest("path"):
            lines = self.printed({"comments": [{"file": "b\n.md", "note": "n"}], "edited": ["c\r\nedited x.md"]})
            self.assertEqual(lines, ["comment b .md: n", "edited c edited x.md"])

    def test_a_blank_or_missing_note_prints_no_stray_text(self):
        """Adversarial where: a comment whose note is null prints the literal
        word `None` as if the human had written it. Rows: null note, missing
        note, whitespace note."""
        for name, entry in {
            "null": {"file": "b.md", "note": None},
            "missing": {"file": "b.md"},
            "whitespace": {"file": "b.md", "note": " \n "},
        }.items():
            with self.subTest(name):
                lines = self.printed({"comments": [entry]})
                self.assertEqual(len(lines), 1)
                self.assertNotIn("None", lines[0])

    def test_non_string_entries_do_not_print_python_reprs(self):
        """Adversarial where: an `edited` list holding a dict prints
        `edited {'a': 1}` (a Python repr) into the session's input, or a
        non-dict comment crashes the waiter. Rows: dict path, numeric path,
        non-dict comment next to a good one."""
        lines = self.printed({"comments": ["stray", {"file": "b.md", "note": "ok"}],
                              "edited": [{"a": 1}, 7, "c.md"]})
        self.assertEqual(lines[0], "comment b.md: ok")
        self.assertNotIn("{", "\n".join(lines))
        self.assertIn("edited c.md", lines)


if __name__ == "__main__":
    unittest.main()
