"""Tests for answering the documents of a several-file `compass review` one at a
time: the `<id>.verdict.<n>.json` answer a surface writes for some documents,
the waiter that ends on the first answer and names the documents still open,
`compass review --wait <id>` that takes up the next answer, the request
counting as answered once every document is covered, and a document the human
answered no longer being under review.

Adversarial themes: a row answered alone printing the lines of the rows still
open, the waiter ending only when every row is answered, `--wait` handing the
same answer twice or skipping one, a malformed or duplicate-index answer taken
as a verdict, the request vanishing from `--status` while rows are open, an
answered row still locking its file against the agent, and a newer request for
an answered row withdrawing the rows still open.

The fixture is the several-file project of `test_review_files.py`.
"""

import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reviewlib  # noqa: E402
from tests.test_review_files import MultiFileProject  # noqa: E402

PLAN = "plans/PLAN-001-z.md"
SPEC1 = "specs/SPEC-001-x.md"
SPEC2 = "specs/SPEC-002-y.md"
ORDER = [PLAN, SPEC1, SPEC2]


def partial_path(request_path, index):
    """The `<id>.verdict.<index>.json` file beside a request file."""
    name = request_path.name.replace(".request.json", f".verdict.{index}.json")
    return request_path.with_name(name)


def part(file, index, verdict="approved", read=True, note=None):
    out = {"file": file, "read": read, "verdict": verdict, "index": index}
    if note is not None:
        out["note"] = note
    return out


def answer_body(rid, entries, **extra):
    verdict = "approved" if all(e["verdict"] == "approved" for e in entries) else "changes"
    body = {"id": rid, "file": entries[0]["file"], "verdict": verdict, "notes": "", "comments": [],
            "edited": [], "files": entries, "at": "t"}
    body.update(extra)
    return body


class PerDocument(MultiFileProject):
    def write_partial(self, rid, entries, **extra):
        path = partial_path(reviewlib.review_dir(self.vault) / f"{rid}.request.json",
                            min(e["index"] for e in entries))
        path.write_text(json.dumps(answer_body(rid, entries, **extra)), encoding="utf-8")
        return path

    def partial_later(self, entries, delay=0.3, during=None, **extra):
        """Write a part answer for the first request that has no verdict."""
        directory = reviewlib.review_dir(self.vault)

        def write():
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                waiting = [p for p in sorted(directory.glob("*.request.json"))
                           if not reviewlib.is_answered(p, json.loads(p.read_text(encoding="utf-8")))] \
                    if directory.is_dir() else []
                if waiting:
                    time.sleep(delay)
                    rid = json.loads(waiting[0].read_text(encoding="utf-8"))["id"]
                    if during:
                        during()
                    self.write_partial(rid, entries, **extra)
                    return
                time.sleep(0.05)

        thread = threading.Thread(target=write, daemon=True)
        thread.start()
        return thread

    def file_lines(self, out):
        return [ln for ln in out.splitlines() if ln.startswith("file ")]

    def open_line(self, out):
        return [ln for ln in out.splitlines() if ln.startswith("still open ")]

    def request_path(self, rid):
        return reviewlib.review_dir(self.vault) / f"{rid}.request.json"


class FirstAnswerEndsTheWait(PerDocument):
    def test_a_row_answered_alone_ends_the_wait_with_that_row_only_and_names_the_rest(self):
        """Adversarial where: the waiter holds on for the other rows, prints a
        `file` line for rows the human has not answered, or leaves out the
        line naming them."""
        self.partial_later([part(SPEC1, 1, "changes", note="rework the intro")])
        code, out, _ = self.review(*map(str, self.trio), "--timeout", "10")
        self.assertEqual(code, 0, out)
        rid = out.split()[1]
        self.assertEqual(self.file_lines(out), [f"file {SPEC1} changes read note: rework the intro"])
        self.assertEqual(self.open_line(out), [f"still open {rid}: {PLAN}, {SPEC2}"])
        self.assertIn('"verdict": "changes"', out)
        self.assertIn(f"--- {SPEC1} as the human left it ---", out)
        self.assertNotIn(f"--- {PLAN} as the human left it ---", out)

    def test_the_answered_row_is_marked_handed_on_and_the_request_stays_pending(self):
        """Adversarial where: the request leaves `--status` while rows are
        open, or the answer is not marked handed on so the next wait prints it
        again."""
        self.partial_later([part(PLAN, 0)])
        code, out, _ = self.review(*map(str, self.trio), "--timeout", "10")
        rid = out.split()[1]
        request_path = self.request_path(rid)
        self.assertTrue(reviewlib.taken_path(request_path, 0).exists())
        self.assertFalse(reviewlib.taken_path(request_path, 1).exists())
        self.assertFalse(reviewlib.verdict_path(request_path).exists())
        _, status, _ = self.review("--status")
        self.assertIn(f"pending {rid} {PLAN} (+2 more)", status)

    def test_an_answer_covering_two_rows_prints_both_and_names_the_third(self):
        """Adversarial where: only the first covered row prints, the covered
        rows are matched by position in the answer instead of by their index,
        or the open line names a covered row."""
        self.partial_later([part(PLAN, 0), part(SPEC2, 2, note="late")])
        code, out, _ = self.review(*map(str, self.trio), "--timeout", "10")
        rid = out.split()[1]
        self.assertEqual(self.file_lines(out), [f"file {PLAN} approved read", f"file {SPEC2} approved read note: late"])
        self.assertEqual(self.open_line(out), [f"still open {rid}: {SPEC1}"])

    def test_a_one_file_review_ends_on_its_one_answer_and_prints_no_open_line(self):
        """Adversarial where: the open line or a `file` line leaks into a
        one-file review."""
        self.answer(None, extra={"verdict": "approved"})
        code, out, _ = self.review(str(self.doc), "--timeout", "5")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.file_lines(out) + self.open_line(out), [])

    def test_an_answer_for_every_row_at_once_is_the_whole_verdict_and_names_nothing_open(self):
        """Adversarial where: the whole `<id>.verdict.json` of a several-file
        review prints an open line, or is handed on without a marker so
        `--wait` hands it again."""
        self.answer([{"file": p, "read": True, "verdict": "approved"} for p in ORDER], extra={"verdict": "approved"})
        code, out, _ = self.review(*map(str, self.trio), "--timeout", "10")
        self.assertEqual(code, 0, out)
        rid = out.split()[1]
        self.assertEqual(len(self.file_lines(out)), 3)
        self.assertEqual(self.open_line(out), [])
        code, _, err = self.review("--wait", rid)
        self.assertEqual(code, 1)
        self.assertIn("already answered", err)


class WaitTakesTheNextAnswer(PerDocument):
    def start(self):
        """Send the request, answer row 2 and take that answer; return the id."""
        self.partial_later([part(SPEC1, 1, "changes", note="rework")])
        _, out, _ = self.review(*map(str, self.trio), "--timeout", "10")
        return out.split()[1]

    def test_wait_prints_the_next_row_and_never_the_one_already_handed_on(self):
        """Adversarial where: `--wait` hands the first answer again, skips the
        new one, or prints the lines of rows other than the one answered."""
        rid = self.start()
        self.write_partial(rid, [part(PLAN, 0)])
        code, out, _ = self.review("--wait", rid, "--timeout", "10")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.file_lines(out), [f"file {PLAN} approved read"])
        self.assertEqual(self.open_line(out), [f"still open {rid}: {SPEC2}"])
        self.assertNotIn(SPEC1, "\n".join(self.file_lines(out)))

    def test_wait_blocks_until_the_next_row_is_answered(self):
        """Adversarial where: `--wait` returns at once with nothing, or times
        out although an answer arrives while it waits."""
        rid = self.start()
        threading.Timer(0.6, self.write_partial, args=(rid, [part(SPEC2, 2)])).start()
        started = time.monotonic()
        code, out, _ = self.review("--wait", rid, "--timeout", "10")
        self.assertEqual(code, 0, out)
        self.assertGreaterEqual(time.monotonic() - started, 0.5)
        self.assertEqual(self.file_lines(out), [f"file {SPEC2} approved read"])

    def test_the_last_row_completes_the_request_and_ends_the_waits(self):
        """Adversarial where: the last answer still prints an open line, the
        completed request stays in `--status`, or a further `--wait` waits for
        ever instead of exiting 1."""
        rid = self.start()
        self.write_partial(rid, [part(PLAN, 0), part(SPEC2, 2)])
        code, out, _ = self.review("--wait", rid, "--timeout", "10")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.open_line(out), [])
        self.assertEqual(self.review("--status")[1], "")
        code, out, err = self.review("--wait", rid, "--timeout", "2")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("already answered and handed on", err)

    def test_two_rows_answered_while_nobody_waits_come_one_wait_at_a_time(self):
        """Adversarial where: two waiting answers are printed together, or the
        second is lost behind the first."""
        rid = self.start()
        self.write_partial(rid, [part(SPEC2, 2)])
        self.write_partial(rid, [part(PLAN, 0)])
        first = self.review("--wait", rid, "--timeout", "5")
        second = self.review("--wait", rid, "--timeout", "5")
        self.assertEqual(self.file_lines(first[1]), [f"file {PLAN} approved read"])
        self.assertEqual(self.open_line(first[1]), [f"still open {rid}: {SPEC2}"])
        self.assertEqual(self.file_lines(second[1]), [f"file {SPEC2} approved read"])
        self.assertEqual(self.open_line(second[1]), [])

    def test_wait_ends_with_withdrawn_when_the_request_is_cancelled(self):
        """Adversarial where: `--wait` on a cancelled request times out
        instead of reporting the withdrawal."""
        rid = self.start()
        threading.Timer(0.5, reviewlib.cancel, args=(self.vault, rid)).start()
        code, out, _ = self.review("--wait", rid, "--timeout", "10")
        self.assertEqual((code, out.strip()), (1, f"withdrawn {rid}"))

    def test_wait_times_out_with_the_request_id(self):
        """Adversarial where: `--timeout` is ignored by `--wait`."""
        rid = self.start()
        code, out, _ = self.review("--wait", rid, "--timeout", "1")
        self.assertEqual((code, out.strip()), (1, f"timeout {rid}"))


class WaitArguments(PerDocument):
    def test_an_unknown_id_exits_1_with_a_message_on_stderr(self):
        """Adversarial where: an id that names no review waits for ever or
        exits 0."""
        code, out, err = self.review("--wait", "nope")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("no review with id 'nope'", err)

    def test_wait_is_a_separate_run_from_files_and_other_modes(self):
        """Adversarial where: `--wait` combined with files, `--status`,
        `--cancel` or a missing id is accepted, or exits 2."""
        for args in (["--wait"], ["--wait", "x", str(self.doc)], ["--wait", "x", "--status"],
                     ["--wait", "x", "--cancel", "y"], ["--wait", "x", "--no-wait"], ["--wait", "x", "--title", "T"]):
            with self.subTest(args):
                code, out, err = self.review(*args)
                self.assertEqual((code, out), (1, ""))
                self.assertIn("usage: compass review", err)

    def test_the_usage_and_docstring_name_wait_and_the_open_line(self):
        """Adversarial where: the contract other agents read omits the new
        flag, the part answer file or the open line."""
        from commands import review as module
        self.assertIn("compass review --wait <id>", module.__doc__)
        self.assertIn("still open <id>:", module.__doc__)
        self.assertIn("<id>.verdict.<n>.json", module.__doc__)
        self.assertIn("<id>.verdict.<n>.json", reviewlib.__doc__)


class MalformedAnswers(PerDocument):
    def test_a_part_answer_that_is_not_well_formed_is_not_taken(self):
        """Adversarial where: an entry with no index, an index outside the
        request, a repeated index, a non-integer index or an unknown verdict
        word is taken as a verdict."""
        rows = [
            ("no index", [{"file": SPEC1, "read": True, "verdict": "approved"}]),
            ("index outside", [part(SPEC1, 3)]),
            ("negative index", [part(SPEC1, -1)]),
            ("repeated index", [part(SPEC1, 1), part(PLAN, 1)]),
            ("boolean index", [{"file": SPEC1, "read": True, "verdict": "approved", "index": True}]),
            ("string index", [{"file": SPEC1, "read": True, "verdict": "approved", "index": "1"}]),
            ("unknown verdict word", [part(SPEC1, 1, "maybe")]),
            ("no entries", []),
        ]
        for name, entries in rows:
            with self.subTest(name):
                request = self.send(*map(str, self.trio))
                path = self.request_path(request["id"])
                body = answer_body(request["id"], entries or [part(SPEC1, 1)])
                body["files"] = entries
                partial_path(path, 1).write_text(json.dumps(body), encoding="utf-8")
                self.assertEqual(reviewlib.partial_verdicts(path, request), [])
                self.assertFalse(reviewlib.is_answered(path, request))
                reviewlib.cancel(self.vault, request["id"])

    def test_a_half_written_part_answer_is_not_taken(self):
        """Adversarial where: a file that is not yet whole JSON ends the wait
        or crashes it."""
        request = self.send(*map(str, self.trio))
        path = self.request_path(request["id"])
        partial_path(path, 1).write_text('{"id": "', encoding="utf-8")
        self.assertEqual(reviewlib.partial_verdicts(path, request), [])
        code, out, _ = self.review("--wait", request["id"], "--timeout", "1")
        self.assertEqual((code, out.strip()), (1, f"timeout {request['id']}"))

    def test_an_answer_file_of_another_request_is_not_this_requests_answer(self):
        """Adversarial where: files are matched by id prefix only, so an id
        that starts with another's picks up its answers."""
        request = self.send(*map(str, self.trio))
        path = self.request_path(request["id"])
        body = answer_body("someone-else", [part(SPEC1, 1)])
        partial_path(path, 1).write_text(json.dumps(body), encoding="utf-8")
        self.assertEqual(reviewlib.partial_verdicts(path, request), [])


class AnsweredRowsAreFree(PerDocument):
    def test_an_answered_row_is_no_longer_under_review_but_an_open_one_is(self):
        """Adversarial where: the agent stays locked out of a document the
        human has already answered (so it cannot revise it while the other
        rows are open), or an open row is released with it."""
        request = self.send(*map(str, self.trio))
        self.assertIsNotNone(reviewlib.under_review(self.vault, self.doc))
        self.write_partial(request["id"], [part(SPEC1, 1, "changes", note="x")])
        self.assertIsNone(reviewlib.under_review(self.vault, self.doc))
        self.assertIsNotNone(reviewlib.under_review(self.vault, self.plan))
        self.assertIsNotNone(reviewlib.under_review(self.vault, self.spec2))

    def test_a_request_with_every_row_covered_is_not_pending(self):
        """Adversarial where: coverage is counted by files rather than by
        distinct positions, so one answer repeating a row completes the
        request."""
        request = self.send(*map(str, self.trio))
        path = self.request_path(request["id"])
        self.write_partial(request["id"], [part(PLAN, 0), part(SPEC1, 1)])
        self.assertTrue(reviewlib.pending(self.vault))
        self.write_partial(request["id"], [part(SPEC2, 2)])
        self.assertTrue(reviewlib.is_answered(path, request))
        self.assertEqual(reviewlib.pending(self.vault), [])

    def test_a_newer_request_for_an_answered_row_leaves_the_older_request_open(self):
        """Adversarial where: sending the revised document again withdraws the
        older request, dropping the rows the human has not answered."""
        old = self.send(*map(str, self.trio))
        self.write_partial(old["id"], [part(SPEC1, 1, "changes", note="x")])
        self.git("commit", "--allow-empty", "-q", "-m", "revised")
        newer = self.send(str(self.doc))
        self.assertTrue(self.request_path(old["id"]).exists(), "the older request stays")
        self.assertTrue(self.request_path(newer["id"]).exists())

    def test_a_newer_request_for_an_open_row_withdraws_the_older_request(self):
        """Adversarial where: the withdrawal rule for a row still open is
        lost along with the answered-row exception."""
        old = self.send(*map(str, self.trio))
        self.write_partial(old["id"], [part(SPEC1, 1)])
        newer = self.send(str(self.plan))
        self.assertFalse(self.request_path(old["id"]).exists())
        self.assertTrue(self.request_path(newer["id"]).exists())


class RenamedRow(PerDocument):
    def test_a_row_renamed_during_the_review_prints_under_its_new_path(self):
        """Adversarial where: the part answer's entry is matched by position
        in the answer, so a renamed row loses its name or its mark."""
        renamed = self.spec2.with_name("SPEC-002-renamed.md")
        self.partial_later([part("specs/SPEC-002-renamed.md", 2, "changes", note="moved")],
                           during=lambda: self.spec2.rename(renamed))
        code, out, _ = self.review(*map(str, self.trio), "--timeout", "10")
        renamed.rename(self.spec2)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.file_lines(out),
                         [f"file specs/SPEC-002-renamed.md changes read note: moved (renamed from {SPEC2})"])


if __name__ == "__main__":
    import unittest
    unittest.main()
