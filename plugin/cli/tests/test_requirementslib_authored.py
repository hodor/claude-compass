"""Tests for authored requirement ids in `requirementslib` and `compass requirements`.

A bullet under `## Desired Outcome`, `## Success Criteria` or `## Constraints`
may open with an authored id in the decision-bullet shape: `- **O-01:** text`,
`- **S-01:** text`, `- **C-01:** text`, or `- [ ] **S-01:** text` for a
checkbox bullet. The row keeps the authored id as written, and its text is
the bullet text with the id removed, so the hash covers only the words.
Authored and derived ids compare by prefix and number (`O-3` equals `O-03`);
a derived id skips every number an authored id of its prefix already holds
in the spec; the `KPI:` line stays `K-1`. Two rows holding the same id make
`compass requirements` exit 1 naming both line numbers. An authored id inside
a fenced block, or anywhere but the start of a bullet, is plain text.

Adversarial themes: an insertion above an authored bullet must leave its id
and hash alone while derived ids below shift; numeric comparison must not
depend on zero padding; fences and untracked sections must not reserve ids;
authored ids must not disturb decision rows or the decision coverage gate;
a spec with no authored ids must read exactly as before.
"""

import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requirementslib  # noqa: E402
from commands import coverage, requirements  # noqa: E402

REAL_SPEC = (
    Path(__file__).resolve().parents[3]
    / ".compass"
    / "specs"
    / "pipeline"
    / "SPEC-034-verification-beyond-test-pass.md"
)

# The rows `extract_requirements` returns for SPEC-034 before authored ids
# exist: (id, section, hash).
REAL_SPEC_ROWS = [
    ("O-1", "Desired Outcome", "9d5347610e50"),
    ("K-1", "Desired Outcome", "3515b1cf401c"),
    ("C-1", "Constraints", "ec4e419200fe"),
]


def make_spec(outcome="", success="", constraints="", decisions=""):
    parts = ["---\ntitle: Sample\ntype: spec\nstatus: approved\n---\n\n# Sample\n"]
    parts.append("## Problem\n\n- A problem bullet.\n")
    if outcome:
        parts.append("## Desired Outcome\n\n" + outcome)
    if success:
        parts.append("## Success Criteria\n\n" + success)
    if constraints:
        parts.append("## Constraints\n\n" + constraints)
    if decisions:
        parts.append("## Decisions\n\n" + decisions)
    return "\n".join(parts)


def by_text(rows):
    return {row["text"]: row for row in rows}


def normalized_hash(text):
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:12]


def line_of(text, needle):
    for number, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return number
    raise AssertionError(f"{needle!r} not in text")


class AuthoredIdsTest(unittest.TestCase):
    def test_insert_above_authored_bullet_keeps_its_id_and_hash_and_shifts_derived(self):
        """Adversarial where: a bullet inserted above an authored `O-02` must
        leave that row's id and hash untouched while the derived rows below
        move to later numbers (skipping 2); an id tied to position instead
        of the authored token would renumber the authored row too."""
        before = make_spec(
            outcome="- **O-02:** Authored outcome.\n- Derived one.\n- Derived two.\n"
        )
        after = make_spec(
            outcome="- Inserted outcome.\n- **O-02:** Authored outcome.\n"
            "- Derived one.\n- Derived two.\n"
        )
        rows_before = by_text(requirementslib.extract_requirements(before))
        rows_after = by_text(requirementslib.extract_requirements(after))
        self.assertEqual(rows_before["Authored outcome."]["id"], "O-02")
        self.assertEqual(rows_after["Authored outcome."]["id"], "O-02")
        self.assertEqual(
            rows_before["Authored outcome."]["hash"], rows_after["Authored outcome."]["hash"]
        )
        self.assertEqual(rows_before["Derived one."]["id"], "O-1")
        self.assertEqual(rows_before["Derived two."]["id"], "O-3")
        self.assertEqual(rows_after["Inserted outcome."]["id"], "O-1")
        self.assertEqual(rows_after["Derived one."]["id"], "O-3")
        self.assertEqual(rows_after["Derived two."]["id"], "O-4")

    def test_authored_constraint_beside_two_unauthored_bullets(self):
        """Adversarial where: with `C-01` authored first and two bullets
        carrying no id, the derived rows must be `C-2` and `C-3`; counting
        from 1 again would collide with the authored `C-01`."""
        spec = make_spec(
            constraints="- **C-01:** Authored constraint.\n- Plain one.\n- Plain two.\n"
        )
        rows = requirementslib.extract_requirements(spec)
        self.assertEqual(
            [(r["id"], r["text"]) for r in rows],
            [
                ("C-01", "Authored constraint."),
                ("C-2", "Plain one."),
                ("C-3", "Plain two."),
            ],
        )

    def test_derived_id_skips_only_the_numbers_authored_ids_hold(self):
        """Adversarial where: an authored `O-10` reserves 10 and nothing
        below it; the unauthored bullets must still start at `O-1`, `O-2`.
        A skip-everything-below rule would start them at `O-11`."""
        spec = make_spec(outcome="- **O-10:** Far authored.\n- First plain.\n- Second plain.\n")
        rows = requirementslib.extract_requirements(spec)
        self.assertEqual([r["id"] for r in rows], ["O-10", "O-1", "O-2"])

    def test_authored_and_derived_ids_compare_by_number_not_spelling(self):
        """Adversarial where: an authored `O-1` and an authored `O-001` both
        reserve number 1, so the unauthored bullet after them must be `O-2`
        in each spec; string comparison would let it take `O-1` and
        collide."""
        for authored in ("O-1", "O-01", "O-001"):
            with self.subTest(authored=authored):
                spec = make_spec(outcome=f"- **{authored}:** Held.\n- Plain.\n")
                rows = requirementslib.extract_requirements(spec)
                self.assertEqual([r["id"] for r in rows], [authored, "O-2"])

    def test_checkbox_bullet_carries_an_authored_id(self):
        """Adversarial where: `- [ ] **S-01:** text` must read as authored
        `S-01` with the checkbox marker and id both off the text; a bullet
        parser that sees `[ ]` as text would hash `[ ] text` or derive
        `S-1`."""
        spec = make_spec(success="- [ ] **S-01:** Box one.\n- [x] **S-02:** Box two.\n")
        rows = requirementslib.extract_requirements(spec)
        self.assertEqual([r["id"] for r in rows], ["S-01", "S-02"])
        self.assertEqual(rows[0]["text"], "Box one.")
        self.assertEqual(rows[1]["text"], "Box two.")
        self.assertEqual(rows[0]["hash"], normalized_hash("Box one."))
        self.assertEqual(rows[0]["section"], "Success Criteria")

    def test_text_is_stripped_of_the_id_before_hashing(self):
        """Adversarial where: the same words with and without an authored id
        must hash alike, with extra spaces after the id and a wrapped
        continuation line also leaving the text clean; hashing the id into
        the text would make adding an id read as an edit."""
        authored = make_spec(
            outcome="- **O-01:**   Wrapped words\n  continue here.\n- **O-02:** Same words.\n"
        )
        plain = make_spec(outcome="- Wrapped words continue here.\n- Same words.\n")
        a_rows = requirementslib.extract_requirements(authored)
        p_rows = requirementslib.extract_requirements(plain)
        self.assertEqual([r["text"] for r in a_rows], ["Wrapped words continue here.", "Same words."])
        self.assertEqual([r["hash"] for r in a_rows], [r["hash"] for r in p_rows])
        self.assertEqual(a_rows[1]["hash"], normalized_hash("Same words."))

    def test_authored_id_inside_a_fence_is_text_and_reserves_nothing(self):
        """Adversarial where: a fenced `- **C-01:** quoted` must yield no row
        and must not reserve number 1, so the unauthored bullet after it is
        `C-1`; a scan that ignores fences would give `C-2`, or report a
        duplicate against a real `C-01` outside the fence."""
        fenced = "```\n- **C-01:** quoted example\n```\n\n- Plain bullet.\n"
        rows = requirementslib.extract_requirements(make_spec(constraints=fenced))
        self.assertEqual([(r["id"], r["text"]) for r in rows], [("C-1", "Plain bullet.")])

        with_real = "```\n- **C-01:** quoted example\n```\n\n- **C-01:** Real one.\n"
        rows = requirementslib.extract_requirements(make_spec(constraints=with_real))
        self.assertEqual([(r["id"], r["text"]) for r in rows], [("C-01", "Real one.")])

    def test_id_not_at_the_start_of_a_bullet_is_plain_text(self):
        """Adversarial where: `**C-01:**` in the middle of a bullet is prose;
        the row must derive `C-1` and keep the whole sentence as its text,
        not be claimed as authored."""
        spec = make_spec(constraints="- Write ids as **C-01:** at the start.\n")
        rows = requirementslib.extract_requirements(spec)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "C-1")
        self.assertEqual(rows[0]["text"], "Write ids as **C-01:** at the start.")

    def test_authored_id_in_an_untracked_section_makes_no_row_and_reserves_nothing(self):
        """Adversarial where: an `O-01` bullet under `## Problem` is not a
        requirement; it must yield no row and must not push the real
        outcome bullet from `O-1` to `O-2`."""
        spec = (
            "# T\n\n## Problem\n\n- **O-01:** problem prose.\n\n"
            "## Desired Outcome\n\n- Real outcome.\n"
        )
        rows = requirementslib.extract_requirements(spec)
        self.assertEqual([(r["id"], r["text"]) for r in rows], [("O-1", "Real outcome.")])

    def test_kpi_line_stays_k1_beside_an_authored_outcome(self):
        """Adversarial where: an authored `O-01` and the `KPI:` line share a
        section; the KPI row must stay `K-1` with its unchanged text and
        hash, and the authored row must not absorb the KPI line."""
        kpi = "KPI: every planted instance is flagged."
        with_id = make_spec(outcome=f"- **O-01:** Outcome.\n\n{kpi}\n")
        without = make_spec(outcome=f"- Outcome.\n\n{kpi}\n")
        a = {r["id"]: r for r in requirementslib.extract_requirements(with_id)}
        p = {r["id"]: r for r in requirementslib.extract_requirements(without)}
        self.assertEqual(list(a), ["O-01", "K-1"])
        self.assertEqual(a["K-1"], p["K-1"])
        self.assertEqual(a["O-01"]["text"], "Outcome.")

    def test_decision_rows_beside_authored_outcomes_keep_ids_text_and_tags(self):
        """Adversarial where: `- **O-01:**` and `- **D-01:**` share the same
        bullet shape; the D rows must still carry `D-NN`, their text and
        tags, and the O row must not turn into a decision."""
        spec = make_spec(
            outcome="- **O-01:** Outcome.\n",
            decisions="- **D-01:** Live.\n- **D-02 [deferred]:** Later.\n",
        )
        rows = {r["id"]: r for r in requirementslib.extract_requirements(spec)}
        self.assertEqual(list(rows), ["O-01", "D-01", "D-02"])
        self.assertEqual(rows["D-01"]["text"], "Live.")
        self.assertEqual(rows["D-02"]["tags"], ["deferred"])
        self.assertNotIn("tags", rows["O-01"])

    def test_authored_rows_are_non_decision_rows_for_a_task(self):
        """Adversarial where: `rows_for_task` keeps every non-decision row;
        an authored `O-01` must be kept for a task citing no decision while
        the uncited `D-01` is dropped."""
        spec = make_spec(
            outcome="- **O-01:** Outcome.\n", decisions="- **D-01:** Live.\n"
        )
        rows = requirementslib.extract_requirements(spec)
        plan = "- [ ] TASK-1: one - complexity: S, depends_on: none, files: [a.py]\n"
        kept = requirementslib.rows_for_task(rows, plan, "TASK-1", "SPEC-099-sample")
        self.assertEqual([r["id"] for r in kept], ["O-01"])

    def test_crlf_spec_with_authored_ids_gives_the_same_rows(self):
        """Adversarial where: CRLF endings must not leave a `\\r` in an
        authored row's text or break id detection."""
        spec = make_spec(
            outcome="- **O-01:** Outcome.\n- Plain.\n", success="- [ ] **S-01:** Box.\n"
        )
        lf = requirementslib.extract_requirements(spec)
        crlf = requirementslib.extract_requirements(spec.replace("\n", "\r\n"))
        self.assertEqual(lf, crlf)
        self.assertEqual([r["id"] for r in lf], ["O-01", "O-2", "S-01"])

    def test_real_spec_rows_are_unchanged(self):
        """Adversarial where: SPEC-034 carries no authored ids, so the rows
        must equal the pre-authored-id output exactly (ids, sections,
        hashes); a changed strip or hash rule would show up as a moved
        hash on every existing spec."""
        rows = requirementslib.extract_requirements(REAL_SPEC.read_text(encoding="utf-8"))
        self.assertEqual([(r["id"], r["section"], r["hash"]) for r in rows], REAL_SPEC_ROWS)


class AuthoredIdsCommandTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        (self.root / ".compass" / "specs").mkdir(parents=True)
        (self.root / ".compass" / "plans").mkdir(parents=True)
        previous_cwd = os.getcwd()
        previous_env = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.root)
        os.chdir(self.root)

        def restore():
            os.chdir(previous_cwd)
            if previous_env is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = previous_env

        self.addCleanup(restore)

    def write_spec(self, name, body):
        path = self.root / ".compass" / "specs" / name
        path.write_text(body, encoding="utf-8")
        return path

    def call(self, module, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = module.run([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def test_json_listing_prints_the_authored_ids(self):
        """Adversarial where: the command must print authored ids as
        written beside derived ones, in document order, with the id off the
        text."""
        spec = self.write_spec(
            "SPEC-050-authored.md",
            make_spec(
                outcome="- **O-01:** Outcome.\n- Plain.\n",
                constraints="- **C-07:** Constraint.\n",
            ),
        )
        code, out, _ = self.call(requirements, spec, "--json")
        self.assertEqual(code, 0)
        rows = json.loads(out)
        self.assertEqual([r["id"] for r in rows], ["O-01", "O-2", "C-07"])
        self.assertEqual(rows[0]["text"], "Outcome.")

    def test_same_number_in_two_spellings_exits_one_naming_both_lines(self):
        """Adversarial where: `O-3` beside `O-03` is one id twice; the
        command must exit 1 and name both line numbers on stderr; exiting 0
        would let a citation of `O-3` point at two requirements."""
        body = make_spec(outcome="- **O-03:** First holder.\n- **O-3:** Second holder.\n")
        spec = self.write_spec("SPEC-051-dup.md", body)
        first, second = line_of(body, "First holder"), line_of(body, "Second holder")
        code, _, err = self.call(requirements, spec)
        self.assertEqual(code, 1)
        for number in (first, second):
            self.assertRegex(err, rf"(?<!\d){number}(?!\d)")

    def test_identical_authored_ids_exit_one_naming_both_lines(self):
        """Adversarial where: the same `S-01` spelled identically twice,
        once as a checkbox bullet, must also exit 1 naming both lines."""
        body = make_spec(success="- **S-01:** One.\n- [ ] **S-01:** Two.\n")
        spec = self.write_spec("SPEC-052-dup.md", body)
        first, second = line_of(body, "One."), line_of(body, "Two.")
        code, _, err = self.call(requirements, spec, "--json")
        self.assertEqual(code, 1)
        for number in (first, second):
            self.assertRegex(err, rf"(?<!\d){number}(?!\d)")

    def test_same_number_under_different_prefixes_is_not_a_duplicate(self):
        """Adversarial where: `O-01`, `S-01` and `C-01` are three ids; a
        duplicate check on the number alone would exit 1."""
        spec = self.write_spec(
            "SPEC-053-prefixes.md",
            make_spec(
                outcome="- **O-01:** Outcome.\n",
                success="- **S-01:** Success.\n",
                constraints="- **C-01:** Constraint.\n",
            ),
        )
        code, out, _ = self.call(requirements, spec, "--json")
        self.assertEqual(code, 0)
        self.assertEqual([r["id"] for r in json.loads(out)], ["O-01", "S-01", "C-01"])

    def test_authored_id_quoted_in_a_fence_is_not_a_duplicate(self):
        """Adversarial where: a real `C-01` plus a fenced quote of the same
        id must exit 0; a fence-blind duplicate check would exit 1."""
        body = make_spec(
            constraints="- **C-01:** Real.\n\n```\n- **C-01:** quoted\n```\n"
        )
        spec = self.write_spec("SPEC-054-fence.md", body)
        code, out, _ = self.call(requirements, spec, "--json")
        self.assertEqual(code, 0)
        self.assertEqual([r["id"] for r in json.loads(out)], ["C-01"])

    def test_real_spec_command_rows_are_unchanged(self):
        """Adversarial where: `compass requirements --json` on SPEC-034 must
        print today's ids, sections and hashes and exit 0."""
        code, out, _ = self.call(requirements, REAL_SPEC, "--json")
        self.assertEqual(code, 0)
        rows = json.loads(out)
        self.assertEqual([(r["id"], r["section"], r["hash"]) for r in rows], REAL_SPEC_ROWS)

    def coverage_summary(self, spec_body):
        self.write_spec("SPEC-001-src.md", spec_body)
        plan = (
            "---\ntitle: P\ntype: plan\nstatus: approved\n"
            'depends_on: ["[[SPEC-001-src]]"]\n---\n\n## Phases\n\n'
            "- [ ] TASK-001: a - decisions: [SPEC-001-src/D-01]\n"
        )
        (self.root / ".compass" / "plans" / "PLAN-001-p.md").write_text(plan, encoding="utf-8")
        code, out, _ = self.call(coverage, "PLAN-001-p")
        summaries = [line for line in out.splitlines() if line.startswith("summary:")]
        self.assertEqual(len(summaries), 1, out)
        return code, summaries[0]

    def test_coverage_summary_ignores_authored_outcome_ids(self):
        """Adversarial where: `- **O-01:**` bullets beside `- **D-NN:**`
        decisions must not read as malformed or extra decisions; `compass
        coverage` must print the same summary line and exit code as on the
        spec without them."""
        decisions = "- **D-01:** Live.\n- **D-02 [deferred]:** Later.\n"
        plain = make_spec(outcome="- Outcome.\n", decisions=decisions)
        authored = make_spec(
            outcome="- **O-01:** Outcome.\n- **O-02:** Another.\n",
            success="- **S-01:** Success.\n",
            constraints="- **C-01:** Constraint.\n",
            decisions=decisions,
        )
        plain_code, plain_summary = self.coverage_summary(plain)
        authored_code, authored_summary = self.coverage_summary(authored)
        self.assertEqual(authored_summary, plain_summary)
        self.assertEqual(authored_code, plain_code)
        self.assertNotIn("could not be parsed", authored_summary)


if __name__ == "__main__":
    unittest.main()
