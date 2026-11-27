"""Tests for a verdict the human changes while a several-file review is open:
the `<id>.revision.<i>.<k>.json` files a surface writes, the close rule (a
review closes once every document is answered or it is withdrawn), and
`compass review --wait <id>` handing a revision on as a `revised <file>: <old>
-> <new>` line followed by the revision's own answer lines.

Adversarial themes: a malformed or misnamed revision taken as a verdict, a
revision of an unanswered document counted, a revision handed on twice or
lost behind an answer, several revisions reported one by one with stale
middle verdicts, a revision written as the review closes left behind because
the waiter exits, and the `still open` line forgetting a document whose
revision is not handed on yet.

The fixture is the several-file project of `test_review_files.py`.
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


class Revisions(PerDocument):
    def write_revision(self, rid, entry, number, **extra):
        path = reviewlib.revision_path(self.request_path(rid), entry["index"], number)
        path.write_text(json.dumps(answer_body(rid, [entry], revision=number, **extra)), encoding="utf-8")
        return path

    def start(self, entries=None):
        """Send the trio, answer SPEC1 as changes and hand that answer on;
        return the request id."""
        self.partial_later(entries or [part(SPEC1, 1, "changes", note="rework")])
        code, out, _ = self.review(*map(str, self.trio), "--timeout", str(ANSWER_WAIT_SECONDS))
        self.assertEqual(code, 0, out)
        return out.split()[1]

    def revised_lines(self, out):
        return [ln for ln in out.splitlines() if ln.startswith("revised ")]


class RevisionFiles(Revisions):
    def test_only_a_well_formed_revision_of_an_answered_document_counts(self):
        """Adversarial where: a revision whose name and entry disagree, number
        0, several entries, another request's id, a half-written file, or a
        revision of a document nobody answered is taken."""
        request = self.send(*map(str, self.trio))
        rid = request["id"]
        path = self.request_path(rid)
        self.write_partial(rid, [part(SPEC1, 1, "changes", note="x")])
        directory = path.parent
        bad = {
            f"{rid}.revision.1.0.json": answer_body(rid, [part(SPEC1, 1)]),
            f"{rid}.revision.2.1.json": answer_body(rid, [part(SPEC1, 1)]),
            f"{rid}.revision.0.1.json": answer_body(rid, [part(PLAN, 0)]),
            f"{rid}.revision.1.2.json": answer_body(rid, [part(SPEC1, 1), part(PLAN, 0)]),
            f"{rid}.revision.1.3.json": answer_body("someone-else", [part(SPEC1, 1)]),
            f"{rid}.revision.1.x.json": answer_body(rid, [part(SPEC1, 1)]),
        }
        for name, body in bad.items():
            (directory / name).write_text(json.dumps(body), encoding="utf-8")
        (directory / f"{rid}.revision.1.4.json").write_text('{"id": "', encoding="utf-8")
        self.assertEqual(reviewlib.revisions(path, request), [])
        self.assertEqual(reviewlib.current_verdicts(path, request), {1: "changes"})

    def test_the_current_verdict_is_the_highest_revision(self):
        """Adversarial where: revisions are ordered by name as text, so
        revision 10 sorts before 2, or the answer's verdict wins."""
        request = self.send(*map(str, self.trio))
        rid = request["id"]
        path = self.request_path(rid)
        self.write_partial(rid, [part(SPEC1, 1, "changes", note="x")])
        for number, word in ((1, "approved"), (2, "changes"), (10, "approved")):
            self.write_revision(rid, part(SPEC1, 1, word), number)
        self.assertEqual([n for _, n, _, _ in reviewlib.revisions(path, request)], [1, 2, 10])
        self.assertEqual(reviewlib.current_verdicts(path, request), {1: "approved"})
        self.assertEqual(reviewlib.answer_verdicts(path, request), {1: "changes"})


class CloseRule(Revisions):
    def test_open_while_a_document_is_unanswered_closed_once_all_are_or_withdrawn(self):
        """Adversarial where: the review counts as closed after the first
        answer, stays open after the last, or a withdrawn one stays open."""
        request = self.send(*map(str, self.trio))
        path = self.request_path(request["id"])
        self.assertFalse(reviewlib.is_closed(path, request))
        self.write_partial(request["id"], [part(PLAN, 0), part(SPEC1, 1)])
        self.write_revision(request["id"], part(SPEC1, 1, "changes", note="no"), 1)
        self.assertFalse(reviewlib.is_closed(path, request), "a revision does not close it")
        self.write_partial(request["id"], [part(SPEC2, 2)])
        self.assertTrue(reviewlib.is_closed(path, request))
        other = self.send(str(self.plan))
        other_path = self.request_path(other["id"])
        reviewlib.cancel(self.vault, other["id"])
        self.assertTrue(reviewlib.is_closed(other_path, other))

    def test_a_taken_whole_answer_hands_on_every_position(self):
        """Adversarial where: a several-file whole answer handed on still
        leaves its documents waiting in the open line."""
        request = self.send(*map(str, self.trio))
        path = self.request_path(request["id"])
        entries = [{"file": p, "read": True, "verdict": "approved"} for p in (PLAN, SPEC1, SPEC2)]
        reviewlib.verdict_path(path).write_text(json.dumps(answer_body(request["id"], entries)), encoding="utf-8")
        self.assertEqual(reviewlib.handed_indexes(path, request), set())
        reviewlib.taken_path(path, None).write_bytes(b"")
        self.assertEqual(reviewlib.handed_indexes(path, request), {0, 1, 2})


class WaitHandsRevisionsOn(Revisions):
    def test_a_revision_prints_its_revised_line_new_note_and_open_line_once(self):
        """Adversarial where: the revision is not reported, the old verdict is
        the newest one, the new note is missing, the open line is dropped, or a
        later wait hands the same revision again."""
        rid = self.start()
        self.write_revision(rid, part(SPEC1, 1, "approved", note="fine as it is"), 1)
        code, out, _ = self.review("--wait", rid, "--timeout", str(ANSWER_WAIT_SECONDS))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.revised_lines(out), [f"revised {SPEC1}: changes -> approved"])
        self.assertEqual(self.file_lines(out), [f"file {SPEC1} approved read note: fine as it is"])
        self.assertEqual(self.open_line(out), [f"still open {rid}: {PLAN}, {SPEC2}"])
        self.assertIn('"revision": 1', out)
        self.assertTrue(reviewlib.marker_of(reviewlib.revision_path(self.request_path(rid), 1, 1)).exists())
        code, out, _ = self.review("--wait", rid, "--timeout", "1")
        self.assertEqual((code, out.strip()), (1, f"timeout {rid}"))

    def test_a_wait_wakes_on_a_revision_written_while_it_waits(self):
        """Adversarial where: a running wait only wakes for new answers."""
        rid = self.start()
        threading.Timer(0.6, self.write_revision, args=(rid, part(SPEC1, 1, "approved"), 1)).start()
        started = time.monotonic()
        code, out, _ = self.review("--wait", rid, "--timeout", str(ANSWER_WAIT_SECONDS))
        self.assertEqual(code, 0, out)
        self.assertGreaterEqual(time.monotonic() - started, 0.5)
        self.assertEqual(self.revised_lines(out), [f"revised {SPEC1}: changes -> approved"])

    def test_revisions_not_yet_handed_on_print_as_one_from_the_last_handed_verdict(self):
        """Adversarial where: each revision prints on its own wait, so the
        agent acts on a middle verdict, or `old` is the answer's verdict when a
        revision was already handed on."""
        rid = self.start()
        self.write_revision(rid, part(SPEC1, 1, "approved"), 1)
        self.review("--wait", rid, "--timeout", str(ANSWER_WAIT_SECONDS))
        self.write_revision(rid, part(SPEC1, 1, "changes", note="second thoughts"), 2)
        self.write_revision(rid, part(SPEC1, 1, "approved", note="third thoughts"), 3)
        code, out, _ = self.review("--wait", rid, "--timeout", str(ANSWER_WAIT_SECONDS))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.revised_lines(out), [f"revised {SPEC1}: approved -> approved"])
        self.assertEqual(self.file_lines(out), [f"file {SPEC1} approved read note: third thoughts"])
        path = self.request_path(rid)
        self.assertTrue(all(reviewlib.marker_of(reviewlib.revision_path(path, 1, n)).exists() for n in (2, 3)))

    def test_an_answer_and_a_revision_waiting_together_come_in_one_wait(self):
        """Adversarial where: the revision is lost behind the new answer, or
        printed before it."""
        rid = self.start()
        self.write_revision(rid, part(SPEC1, 1, "approved"), 1)
        self.write_partial(rid, [part(PLAN, 0, "changes", note="split it")])
        code, out, _ = self.review("--wait", rid, "--timeout", str(ANSWER_WAIT_SECONDS))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.file_lines(out), [f"file {PLAN} changes read note: split it", f"file {SPEC1} approved read"])
        self.assertEqual(self.revised_lines(out), [f"revised {SPEC1}: changes -> approved"])
        self.assertLess(out.index(f"file {PLAN}"), out.index("revised "))
        self.assertEqual(self.open_line(out), [f"still open {rid}: {SPEC2}"])

    def test_a_revision_written_as_the_review_closes_is_still_handed_on(self):
        """Adversarial where: the last answer closes the review and the
        revision written just before it is never reported, or `--wait` on the
        closed review exits 1 with a revision still to hand on."""
        rid = self.start()
        self.write_partial(rid, [part(PLAN, 0), part(SPEC2, 2)])
        request_path = self.request_path(rid)
        reviewlib.taken_path(request_path, 0).write_bytes(b"")
        self.write_revision(rid, part(SPEC1, 1, "approved"), 1)
        request = json.loads(request_path.read_text(encoding="utf-8"))
        self.assertTrue(reviewlib.is_closed(request_path, request))
        code, out, _ = self.review("--wait", rid, "--timeout", str(ANSWER_WAIT_SECONDS))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.revised_lines(out), [f"revised {SPEC1}: changes -> approved"])
        self.assertEqual(self.open_line(out), [])
        code, out, err = self.review("--wait", rid, "--timeout", "2")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("already answered and handed on", err)

    def test_the_open_line_names_a_document_whose_revision_came_after_this_wait_took_its_answers(self):
        """Adversarial where: the open line counts a document as handed on
        while a revision of it waits, so the agent stops waiting once the
        other documents are answered."""
        import contextlib
        import io
        from commands import review as module
        rid = self.start()
        path = self.request_path(rid)
        request = json.loads(path.read_text(encoding="utf-8"))
        self.write_partial(rid, [part(PLAN, 0), part(SPEC2, 2)])
        reviewlib.taken_path(path, 0).write_bytes(b"")
        self.write_revision(rid, part(SPEC1, 1, "approved"), 1)
        documents = [(rel, self.vault / rel) for rel in (PLAN, SPEC1, SPEC2)]
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            module._print_open(request, path, documents)
        self.assertEqual(printed.getvalue().strip(), f"still open {rid}: {SPEC1}")

    def test_a_revision_with_an_edit_prints_the_document_and_its_edited_line(self):
        """Adversarial where: a revision to changes drops the edit or the
        document text the agent needs to revise it."""
        rid = self.start([part(SPEC1, 1, "approved")])
        self.doc.write_text("# X\nspec-one-body\nhuman line\n", encoding="utf-8")
        self.write_revision(rid, part(SPEC1, 1, "changes"), 1, edited=[SPEC1])
        code, out, _ = self.review("--wait", rid, "--timeout", str(ANSWER_WAIT_SECONDS))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.revised_lines(out), [f"revised {SPEC1}: approved -> changes"])
        self.assertIn(f"edited {SPEC1}", out.splitlines())
        self.assertIn("+human line", out.splitlines())
        self.assertIn(f"--- {SPEC1} as the human left it ---", out)

    def test_the_docstrings_name_the_revision_file_and_the_revised_line(self):
        """Adversarial where: the contract other agents and surfaces read
        omits the revision file, its marker, the close rule or the line."""
        from commands import review as module
        self.assertIn("<id>.revision.<i>.<k>.json", reviewlib.__doc__)
        self.assertIn("<id>.revision.<i>.<k>.taken", reviewlib.__doc__)
        self.assertIn("closes when every", reviewlib.__doc__)
        self.assertIn("revised <path>: <old> -> <new>", module.__doc__)


class RuleText(Revisions):
    def test_the_pipeline_rule_keeps_a_wait_running_and_handles_a_revised_line_both_ways(self):
        """Adversarial where: the review rule an agent follows lets it stop
        waiting before the review closes, or says nothing of what a reversal
        in either direction asks of it."""
        from pathlib import Path
        rule = (Path(__file__).resolve().parents[2] / "templates" / "rules" / "compass-pipeline.md").read_text(
            encoding="utf-8")
        paragraph = next(line for line in rule.splitlines() if line.startswith("**Review in a visual surface.**"))
        self.assertIn("a wait stays running on it", paragraph)
        self.assertIn("`revised <file>: <old> -> <new>`", paragraph)
        self.assertIn("reversed to changes", paragraph)
        self.assertIn("reversed to approved, it is handled as approved and a revision under way for it is dropped",
                      paragraph)


if __name__ == "__main__":
    import unittest
    unittest.main()
