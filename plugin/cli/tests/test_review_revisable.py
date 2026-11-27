"""Tests for revisable reviews: the `"revisable": true` every new request
carries, the review staying open after every document is answered, and its
close by `compass review --close <id>` (the `<id>.closed` marker), by a later
request for one of its documents, or 24 hours after its newest answer or
revision; `compass review --wait <id>` on an answered revisable review waiting
for the next revision and ending with `closed <id>`.

Adversarial themes: a one-document or last-document answer that still closes
the review, an old request without the flag reopened, the 24 hours counted
from the request or the first answer instead of the newest one, a close that
removes a file, a newer request that leaves the older answered one open, a
running wait that never ends at close, and a closed review still locking or
listing its documents.
"""

import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reviewlib  # noqa: E402
from tests.test_review import ANSWER_WAIT_SECONDS  # noqa: E402
from tests.test_review_per_document_verdict import PLAN, SPEC1, SPEC2, PerDocument, answer_body, part  # noqa: E402


def one_answer(rid, verdict="approved", notes="", at="t"):
    return {"id": rid, "file": SPEC1, "verdict": verdict, "notes": notes, "comments": [], "edited": [], "at": at}


class Revisable(PerDocument):
    def write_revision(self, rid, entry, number, **extra):
        path = reviewlib.revision_path(self.request_path(rid), entry["index"], number)
        path.write_text(json.dumps(answer_body(rid, [entry], revision=number, **extra)), encoding="utf-8")
        return path

    def answer_one(self, rid, **body):
        path = reviewlib.verdict_path(self.request_path(rid))
        path.write_text(json.dumps(one_answer(rid, **body)), encoding="utf-8")
        return path

    def first_answer(self, **body):
        """Send SPEC1 alone, answer it and hand the answer on; return the id."""
        self.answer_later(body.get("verdict", "approved"))
        code, out, _ = self.review(str(self.doc), "--timeout", str(ANSWER_WAIT_SECONDS))
        self.assertEqual(code, 0, out)
        return out.split()[1]

    def request(self, rid):
        return json.loads(self.request_path(rid).read_text(encoding="utf-8"))

    def names(self):
        return sorted(p.name for p in reviewlib.review_dir(self.vault).iterdir())

    def revised_lines(self, out):
        return [ln for ln in out.splitlines() if ln.startswith("revised ")]


class NewRequestsAreRevisable(Revisable):
    def test_a_one_file_and_a_several_file_request_both_carry_the_flag(self):
        """Adversarial where: only several-file requests carry the flag, or it
        is written as a string."""
        self.assertIs(self.send(str(self.doc)).get("revisable"), True)
        self.assertIs(self.send(*map(str, self.trio)).get("revisable"), True)

    def test_a_one_file_answer_prints_as_before_and_is_marked_handed_on(self):
        """Adversarial where: the first answer's output changes, or a later
        wait prints the one answer again instead of waiting for a revision."""
        rid = self.first_answer()
        self.assertTrue(reviewlib.taken_path(self.request_path(rid), None).exists())
        code, out, _ = self.review("--wait", rid, "--timeout", "1")
        self.assertEqual((code, out.strip()), (1, f"timeout {rid}"))


class OneDocumentRevision(Revisable):
    def test_a_one_file_revision_wakes_the_wait_and_close_ends_it(self):
        """Adversarial where: a one-document review cannot be revised, its
        revision is printed without the document, or a running wait does not
        end at close."""
        rid = self.first_answer()
        threading.Timer(0.6, self.write_revision, args=(rid, part(SPEC1, 0, "changes", note="narrow it"), 1),
                        kwargs={"notes": "narrow it"}).start()
        code, out, _ = self.review("--wait", rid, "--timeout", str(ANSWER_WAIT_SECONDS))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.revised_lines(out), [f"revised {SPEC1}: approved -> changes"])
        self.assertIn('"notes": "narrow it"', out)
        self.assertIn(f"--- {SPEC1} as the human left it ---", out)
        self.assertEqual([ln for ln in out.splitlines() if ln.startswith("still open")], [])
        threading.Timer(0.6, self.review, args=("--close", rid)).start()
        code, out, _ = self.review("--wait", rid, "--timeout", str(ANSWER_WAIT_SECONDS))
        self.assertEqual((code, out.strip()), (0, f"closed {rid}"))


class LastDocumentRevision(Revisable):
    def test_the_document_answered_last_can_be_revised_and_the_review_stays_open(self):
        """Adversarial where: answering every document closes a revisable
        review, so the last answer can never change."""
        self.partial_later([part(SPEC1, 1)])
        _, out, _ = self.review(*map(str, self.trio), "--timeout", str(ANSWER_WAIT_SECONDS))
        rid = out.split()[1]
        self.write_partial(rid, [part(PLAN, 0), part(SPEC2, 2)])
        code, out, _ = self.review("--wait", rid, "--timeout", str(ANSWER_WAIT_SECONDS))
        self.assertEqual(code, 0, out)
        self.assertFalse(reviewlib.is_closed(self.request_path(rid), self.request(rid)))
        self.write_revision(rid, part(SPEC2, 2, "changes", note="one more case"), 1)
        code, out, _ = self.review("--wait", rid, "--timeout", str(ANSWER_WAIT_SECONDS))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.revised_lines(out), [f"revised {SPEC2}: approved -> changes"])
        self.assertEqual(self.file_lines(out), [f"file {SPEC2} changes read note: one more case"])


class OldRequestsStayClosed(Revisable):
    def test_an_unflagged_answered_request_is_closed_and_waits_end_as_before(self):
        """Adversarial where: a request written before the flag existed stays
        open once answered, so old reviews come back, or a one-file wait on it
        stops printing the answer."""
        request = self.send(str(self.doc))
        self.unflag(request["id"])
        self.answer_one(request["id"])
        path = self.request_path(request["id"])
        self.assertTrue(reviewlib.is_closed(path, self.request(request["id"])))
        for _ in range(2):
            code, out, _ = self.review("--wait", request["id"], "--timeout", "2")
            self.assertEqual(code, 0, out)
            self.assertIn('"verdict": "approved"', out)
        self.assertFalse(reviewlib.taken_path(path, None).exists())
        several = self.send(*map(str, self.trio))
        self.unflag(several["id"])
        self.write_partial(several["id"], [part(PLAN, 0), part(SPEC1, 1), part(SPEC2, 2)])
        self.review("--wait", several["id"], "--timeout", str(ANSWER_WAIT_SECONDS))
        code, out, err = self.review("--wait", several["id"], "--timeout", "2")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("already answered and handed on", err)


class Expiry(Revisable):
    def answered(self):
        request = self.send(str(self.doc))
        return request, self.request_path(request["id"])

    def test_it_closes_24_hours_after_the_newest_answer_or_revision(self):
        """Adversarial where: the clock starts at the first answer, so a
        revision does not extend it, or it closes a moment early."""
        request, path = self.answered()
        self.answer_one(request["id"], at="2026-11-01T10:00:00+00:00")
        first = reviewlib.last_answered_at(path, request)
        self.assertFalse(reviewlib.is_closed(path, request, now=first + reviewlib.REVISE_SECONDS - 1))
        self.assertTrue(reviewlib.is_closed(path, request, now=first + reviewlib.REVISE_SECONDS))
        self.write_revision(request["id"], part(SPEC1, 0, "changes", note="x"), 1, at="2026-11-01T20:00:00Z")
        self.assertEqual(reviewlib.last_answered_at(path, request), first + 10 * 3600)
        self.assertFalse(reviewlib.is_closed(path, request, now=first + reviewlib.REVISE_SECONDS))

    def test_an_answer_with_no_zoned_at_is_timed_by_its_file(self):
        """Adversarial where: an `at` that is not a time with a zone crashes
        the check or never expires."""
        request, path = self.answered()
        answer = self.answer_one(request["id"], at="t")
        stamp = time.time() - reviewlib.REVISE_SECONDS - 60
        os.utime(answer, (stamp, stamp))
        self.assertTrue(reviewlib.is_closed(path, request))
        self.answer_one(request["id"], at="2026-11-01T10:00:00")
        os.utime(answer, (stamp, stamp))
        self.assertTrue(reviewlib.is_closed(path, request), "a time without a zone falls back to the file")

    def test_an_unanswered_revisable_request_never_expires(self):
        """Adversarial where: the expiry runs before any answer, closing a
        review the human has not seen yet."""
        request, path = self.answered()
        self.assertFalse(reviewlib.is_closed(path, request, now=time.time() + 10 * reviewlib.REVISE_SECONDS))

    def test_a_partly_answered_revisable_request_does_not_expire(self):
        """Adversarial where: the open documents of a part-answered review
        are dropped after 24 hours."""
        request = self.send(*map(str, self.trio))
        path = self.request_path(request["id"])
        self.write_partial(request["id"], [part(PLAN, 0)])
        self.assertFalse(reviewlib.is_closed(path, request, now=time.time() + 10 * reviewlib.REVISE_SECONDS))


class CloseMarker(Revisable):
    def test_close_writes_the_marker_and_removes_nothing(self):
        """Adversarial where: closing deletes the request or an answer, or an
        unknown id is accepted."""
        rid = self.first_answer()
        before = self.names()
        code, out, err = self.review("--close", rid)
        self.assertEqual((code, out, err), (0, "", ""))
        self.assertEqual(sorted(set(self.names()) - set(before)), [f"{rid}.closed"])
        self.assertTrue(set(before) <= set(self.names()))
        self.assertTrue(reviewlib.is_closed(self.request_path(rid), self.request(rid)))
        code, out, _ = self.review("--wait", rid, "--timeout", "2")
        self.assertEqual((code, out.strip()), (0, f"closed {rid}"))
        code, out, err = self.review("--close", "nope")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("no review with id 'nope'", err)

    def test_a_closed_unanswered_review_leaves_status_and_frees_its_documents(self):
        """Adversarial where: a closed review still locks its documents
        against the agent or stays in `--status`."""
        request = self.send(*map(str, self.trio))
        self.review("--close", request["id"])
        self.assertEqual(self.review("--status")[1], "")
        self.assertIsNone(reviewlib.under_review(self.vault, self.doc))

    def test_close_is_a_separate_run(self):
        """Adversarial where: `--close` combined with another mode or without
        an id is accepted."""
        for args in (["--close"], ["--close", "x", "--status"], ["--close", "x", "--wait", "y"]):
            with self.subTest(args):
                code, out, err = self.review(*args)
                self.assertEqual((code, out), (1, ""))
                self.assertIn("usage: compass review", err)


class NewerRequest(Revisable):
    def test_a_newer_request_for_the_document_closes_the_older_answered_review(self):
        """Adversarial where: the older answered review stays open beside the
        new one, so the document is answered in two places."""
        rid = self.first_answer()
        newer = self.send(str(self.doc))
        self.assertTrue(reviewlib.closed_path(self.request_path(rid)).exists())
        self.assertFalse(reviewlib.closed_path(self.request_path(newer["id"])).exists())
        code, out, _ = self.review("--wait", rid, "--timeout", "2")
        self.assertEqual((code, out.strip()), (0, f"closed {rid}"))

    def test_a_later_request_on_disk_closes_it_without_the_marker(self):
        """Adversarial where: the rule depends on the marker only, or an
        earlier request closes a later one."""
        rid = self.first_answer()
        path = self.request_path(rid)
        later = path.with_name("29991231T235959-ffffff.request.json")
        later.write_text(json.dumps({**self.request(rid), "id": "29991231T235959-ffffff"}), encoding="utf-8")
        self.assertTrue(reviewlib.is_closed(path, self.request(rid)))
        earlier = path.with_name("19990101T000000-000000.request.json")
        later.rename(earlier)
        self.assertFalse(reviewlib.is_closed(path, self.request(rid)))

    def test_a_newer_request_leaves_a_part_answered_older_review_open(self):
        """Adversarial where: sending the revised document closes the older
        review while other documents are still unanswered."""
        old = self.send(*map(str, self.trio))
        self.write_partial(old["id"], [part(SPEC1, 1, "changes", note="x")])
        self.git("commit", "--allow-empty", "-q", "-m", "revised")
        self.send(str(self.doc))
        self.assertFalse(reviewlib.closed_path(self.request_path(old["id"])).exists())
        self.assertFalse(reviewlib.is_closed(self.request_path(old["id"]), old))


class Docs(Revisable):
    def test_the_contract_and_the_rule_name_the_close(self):
        """Adversarial where: the protocol omits the flag, the marker or the
        24 hours, or the rule never tells the agent to wait for `closed` and
        to close the review."""
        from pathlib import Path
        from commands import review as module
        for text in ('"revisable": true', "<id>.closed", "24 hours"):
            self.assertIn(text, reviewlib.__doc__)
        self.assertIn("compass review --close <id>", module.__doc__)
        self.assertIn("closed <id>", module.__doc__)
        rule = (Path(__file__).resolve().parents[2] / "templates" / "rules" / "compass-pipeline.md").read_text(
            encoding="utf-8")
        paragraph = next(line for line in rule.splitlines() if line.startswith("**Review in a visual surface.**"))
        self.assertIn("until `closed <id>`", paragraph)
        self.assertIn("compass review --close <id>", paragraph)


if __name__ == "__main__":
    import unittest
    unittest.main()
