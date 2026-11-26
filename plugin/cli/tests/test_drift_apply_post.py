"""Adversarial tests for `compass drift --apply` aimed at the branches its
implementation introduced.

Themes: the whole-line guard (a citing line that also carries a correction
git does not prove is left alone, and the unproven finding survives the next
scan), repeated and punctuated references inside one span, fenced lines,
the index-entry pattern `driftlib` owns (`(3 children)` as well as
`(folder, N children)`), byte fidelity beyond ASCII (invalid UTF-8, a BOM, a
lone CR, a non-ASCII file name), the report of a run that applies nothing or
applies everything, and the net-zero shift boundary.
"""

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import driftlib  # noqa: E402
from test_drift_apply import (  # noqa: E402
    DOC, DRIFT_DIR, EPOCH, INDEX, applied_rows, commit, git, lines_of,
    new_repo, newest_report, read_bytes, reports, run_drift, section,
    shifted_repo, source, write, write_bytes,
)


def class_of(repo, cite, line=None):
    """The class `--print` reports for `cite` (on citing line `line`)."""
    text = run_drift(repo, "--print")[1]
    found = []
    for row in text.splitlines():
        if not row.startswith("|") or cite not in row:
            continue
        cells = [c.strip() for c in row.strip("|").split("|")]
        if line is None or cells[2] == str(line):
            found.append(cells[0])
    return found


def finding_rows(text, needle):
    return [l for l in section(text, "Findings") if l.startswith("|") and needle in l]


class LineGuardTests(unittest.TestCase):
    def test_a_line_holding_an_unproven_correction_is_left_whole_and_the_finding_survives(self):
        """Adversarial where: rewriting the shifted ref on a line that also
        carries a `changed` / `missing` / sub-100 `moved` ref re-anchors the
        line's blame base at the apply commit, so the next scan reads the
        unproven ref as `unchanged` and the finding is lost; or the guard is
        keyed on the file instead of the (file, line) pair and a clean line
        beside it, or the same line of another document, is held back too."""
        rows = {
            "changed": ("`src/a.py:12` and `src/a.py:5-7`", "src/a.py:5-7", "changed"),
            "missing": ("`src/a.py:12` and `src/gone.py:2`", "src/gone.py:2", "missing"),
            "partial-rename": ("`src/a.py:12` and `src/b.py:5-7`", "src/b.py:5-7", "moved"),
        }
        for name, (guarded, cite, cls) in rows.items():
            with self.subTest(name):
                doc = ["# Spec", "", f"Guarded {guarded} end.",
                       "Free `src/a.py:12` end."]
                repo = new_repo(self)
                write(repo, "src/a.py", source("A"))
                write(repo, "src/b.py", source("B", 10))
                write(repo, "src/gone.py", source("G", 10))
                write(repo, DOC, doc)
                write(repo, ".compass/specs/other.md",
                      ["# Other", "", f"Guarded {guarded} end."])
                commit(repo, "base")
                edited = ["top"] + source("A")
                edited[5] = "A5 rewritten"
                write(repo, "src/a.py", edited)
                git(repo, "mv", "src/b.py", "src/lib_b.py")
                renamed = source("B", 10)
                renamed[5] = "B6 rewritten"
                write(repo, "src/lib_b.py", renamed)
                git(repo, "rm", "-q", "src/gone.py")
                commit(repo, "edit, rename, delete")
                self.assertIn(cls, class_of(repo, cite, 3))
                code, _, _ = run_drift(repo, "--apply")
                self.assertEqual(code, 0)
                after = lines_of(read_bytes(repo, DOC))
                self.assertEqual(after[2], f"Guarded {guarded} end.")
                self.assertEqual(after[3], "Free `src/a.py:13` end.")
                text = newest_report(self, repo)
                self.assertEqual(applied_rows(text, ".compass/specs/other.md"), [])
                self.assertEqual(len(finding_rows(text, "src/a.py:12")), 2)
                self.assertTrue(finding_rows(text, cite))
                commit(repo, "apply drift fixes")
                self.assertIn(cls, class_of(repo, cite, 3))
                self.assertIn("shifted", class_of(repo, "src/a.py:12", 3))

    def test_a_ref_repeated_on_one_line_and_inside_one_span_is_rewritten_each_time(self):
        """Adversarial where: the per-key record queue is popped once, so the
        second occurrence of the same reference on a line stays stale (or is
        counted as an open finding), or a double-backtick span is not
        recognised by the rewriter though the scanner reads it."""
        doc = [
            "# Spec", "",
            "Twice `src/a.py:5` then `src/a.py:5` end.",
            "Same span `src/a.py:5 src/a.py:5` end.",
            "Double ``src/a.py:5`` end.",
            "Wrapped `(src/a.py:5), src/a.py:8.` end.",
        ]
        repo = shifted_repo(self, doc, lambda a: ["new one", "new two"] + a)
        run_drift(repo, "--apply")
        expected = [
            "# Spec", "",
            "Twice `src/a.py:7` then `src/a.py:7` end.",
            "Same span `src/a.py:7 src/a.py:7` end.",
            "Double ``src/a.py:7`` end.",
            "Wrapped `(src/a.py:7), src/a.py:10.` end.",
        ]
        self.assertEqual(lines_of(read_bytes(repo, DOC)), expected + [""])
        text = newest_report(self, repo)
        self.assertEqual(finding_rows(text, "src/a.py"), [])
        self.assertEqual(len(applied_rows(text, "src/a.py:5")), 6)

    def test_fenced_and_dot_slash_references(self):
        """Adversarial where: a reference inside a fenced block is rewritten
        (the fence holds a quotation of old text), a rewritten fenced row
        also leaves the finding open, or a `./` prefix is dropped when the
        path moves or the line shifts."""
        doc = [
            "# Spec", "",
            "Dot `./src/a.py:5` end.",
            "```", "src/a.py:5", "```",
            "Moved `./src/b.py:2` end.",
        ]
        repo = new_repo(self)
        write(repo, "src/a.py", source("A"))
        write(repo, "src/b.py", source("B", 10))
        write(repo, DOC, doc)
        commit(repo, "base")
        write(repo, "src/a.py", ["new"] + source("A"))
        git(repo, "mv", "src/b.py", "src/lib_b.py")
        commit(repo, "edit and rename")
        run_drift(repo, "--apply")
        expected = list(doc)
        expected[2] = "Dot `./src/a.py:6` end."
        expected[6] = "Moved `./src/lib_b.py:2` end."
        self.assertEqual(lines_of(read_bytes(repo, DOC)), expected + [""])
        text = newest_report(self, repo)
        fenced = [l for l in finding_rows(text, "src/a.py:5") if "| 5 |" in l]
        self.assertEqual(len(fenced), 1, "the fenced reference stays an open finding")


class IndexEntryPatternTests(unittest.TestCase):
    def test_entry_forms_are_scanned_and_non_entries_are_not(self):
        """Adversarial where: driftlib's own entry pattern rejects the
        `(3 children)` form (so those lines are never checked), accepts
        `(folder, N children)` only, or is loose enough to pick up a line with
        no bullet, a second wikilink before the dash, a malformed child
        annotation, or a bare-text bullet."""
        names = ["SPEC-001-a", "SPEC-002-b", "SPEC-003-c", "SPEC-004-d",
                 "SPEC-005-e", "SPEC-006-f", "SPEC-007-g", "SPEC-008-h",
                 "SPEC-009-i"]
        repo = new_repo(self)
        for name in names:
            write(repo, f".compass/specs/{name}.md",
                  ["---", f"title: {name}", "summary: Real summary", "---", "", "x"])
        lines = [
            "# Index", "",
            "- [[SPEC-001-a]] - stale plain",
            "- [[SPEC-002-b]] (3 children) - stale count",
            "- [[SPEC-003-c]] (folder, 3 children) - stale folder",
            "- [[SPEC-004-d]] (folder, 12 children) \u2014 stale em dash",
            "  - [[SPEC-005-e]] \u2013 stale nested en dash",
            "[[SPEC-006-f]] - stale no bullet",
            "- [[SPEC-007-g]] [[SPEC-001-a]] - stale two links",
            "- [[SPEC-008-h]] (three children) - stale word count",
            "- plain text bullet - stale text",
            "- [[SPEC-009-i]] (3 children)",
        ]
        write(repo, INDEX, lines)
        commit(repo, "seed")
        records = driftlib.scan_index_lines(repo, Path(repo) / ".compass")
        flagged = {r["line"]: r["class"] for r in records}
        self.assertEqual(flagged, {
            3: "index-drift", 4: "index-drift", 5: "index-drift",
            6: "index-drift", 7: "index-drift",
        })

    def test_apply_keeps_link_annotation_separator_trailing_space_and_crlf_of_an_index_line(self):
        """Adversarial where: replacing the description eats the child count,
        swaps an en/em dash separator for a hyphen, drops trailing blanks
        after the description, or strips the `\\r` of a CRLF index."""
        names = ("SPEC-001-a", "SPEC-002-b", "SPEC-003-c")
        repo = new_repo(self)
        data = (b"# Index\r\n\r\n"
                b"- [[SPEC-001-a]] (3 children) - old a\r\n"
                b"- [[SPEC-002-b]] (folder, 2 children) \xe2\x80\x94 old b  \r\n"
                b"  - [[SPEC-003-c]] \xe2\x80\x93 old c\r\n")
        write_bytes(repo, INDEX, data)
        for name in names:
            write(repo, f".compass/specs/{name}.md",
                  ["---", f"title: {name}", "summary: seeded", "---", "", "x"])
        commit(repo, "seed", at=EPOCH)
        for name, summary in zip(names, ("new a", "new b", "new c")):
            write(repo, f".compass/specs/{name}.md",
                  ["---", f"title: {name}", f"summary: {summary}", "---", "", "x"])
        commit(repo, "summaries", at=EPOCH + 100)
        run_drift(repo, "--apply")
        self.assertEqual(
            read_bytes(repo, INDEX),
            b"# Index\r\n\r\n"
            b"- [[SPEC-001-a]] (3 children) - new a\r\n"
            b"- [[SPEC-002-b]] (folder, 2 children) \xe2\x80\x94 new b  \r\n"
            b"  - [[SPEC-003-c]] \xe2\x80\x93 new c\r\n")

    def test_a_lone_cr_above_an_index_line_never_corrupts_another_line(self):
        """Adversarial where: the scan normalises a lone CR to a line break
        while the rewrite splits on LF only, so a record's line number points
        at a different line and the rewrite edits the wrong line or drops
        bytes. Either the entry is rewritten or the file is left as it was."""
        repo = new_repo(self)
        old = (b"# Index\rstray\n\n- [[SPEC-001-a]] - old a\n"
               b"- [[SPEC-002-b]] - old a\n")
        write_bytes(repo, INDEX, old)
        for name in ("SPEC-001-a", "SPEC-002-b"):
            write(repo, f".compass/specs/{name}.md",
                  ["---", f"title: {name}", "summary: old a", "---", "", "x"])
        commit(repo, "seed", at=EPOCH)
        write(repo, ".compass/specs/SPEC-001-a.md",
              ["---", "title: a", "summary: new a", "---", "", "x"])
        commit(repo, "summary", at=EPOCH + 100)
        run_drift(repo, "--apply")
        after = read_bytes(repo, INDEX)
        good = old.replace(b"[[SPEC-001-a]] - old a", b"[[SPEC-001-a]] - new a")
        self.assertIn(after, (old, good))


class ByteFidelityTests(unittest.TestCase):
    def test_invalid_utf8_bom_and_nonascii_names_survive_a_rewrite(self):
        """Adversarial where: a document holding an invalid UTF-8 byte is
        decoded with replacement and written back with U+FFFD in place of the
        byte, a leading BOM is dropped, a non-breaking space beside the span
        is read as a token break and shifts the offsets, or a citing document
        with a non-ASCII file name is wrongly reported dirty and skipped."""
        ref, want = b"`src/a.py:5`", b"`src/a.py:7`"
        name = ".compass/specs/caf\xe9 notes.md"
        rows = {
            "invalid-byte": (DOC, b"# S\n\nBad \xff\xfe byte " + ref + b" end.\n"),
            "bom": (DOC, b"\xef\xbb\xbf# S\n\nLead " + ref + b" end.\n"),
            "nbsp-and-cjk": (DOC, "# S\n\n日本 ".encode()
                             + ref + " 終\n".encode()),
            "unicode-file-name": (name, b"# S\n\nCites " + ref + b" end.\n"),
        }
        for label, (rel, data) in rows.items():
            with self.subTest(label):
                repo = new_repo(self)
                write(repo, "src/a.py", source("A"))
                write_bytes(repo, rel, data)
                commit(repo, "base")
                write(repo, "src/a.py", ["new one", "new two"] + source("A"))
                commit(repo, "edit a")
                run_drift(repo, "--apply")
                self.assertEqual(read_bytes(repo, rel), data.replace(ref, want))


class NothingAppliedTests(unittest.TestCase):
    def _log_rows(self, repo):
        path = Path(repo) / DRIFT_DIR / "log.jsonl"
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]

    def test_apply_on_a_clean_vault_writes_no_report_and_logs_zero_applied(self):
        """Adversarial where: an `--apply` run with nothing to rewrite writes
        an empty report, or omits the run from the log so a run that fixed
        nothing looks like a run that never happened."""
        repo = new_repo(self)
        write(repo, "src/a.py", source("A"))
        write(repo, DOC, ["# S", "", "Cites `src/a.py:5` end."])
        commit(repo, "base")
        code, out, _ = run_drift(repo, "--apply")
        self.assertEqual(code, 0)
        self.assertIn("clean", out)
        self.assertEqual(reports(repo), [])
        (row,) = self._log_rows(repo)
        self.assertEqual(row["report"], "clean")
        self.assertEqual(row["applied"], 0)

    def test_apply_with_only_unproven_findings_has_no_applied_or_skipped_section(self):
        """Adversarial where: an empty `## Applied (0)` or `## Skipped (0)`
        heading is emitted, or a file with only `changed` findings is
        rewritten or reported as skipped."""
        repo = new_repo(self)
        write(repo, "src/a.py", source("A"))
        write(repo, DOC, ["# S", "", "Cites `src/a.py:5-7` end."])
        commit(repo, "base")
        edited = source("A")
        edited[5] = "A6 rewritten"
        write(repo, "src/a.py", edited)
        commit(repo, "edit a")
        before = read_bytes(repo, DOC)
        run_drift(repo, "--apply")
        self.assertEqual(read_bytes(repo, DOC), before)
        text = newest_report(self, repo)
        headings = [l for l in text.splitlines() if l.startswith("## ")]
        self.assertEqual([h for h in headings if h.startswith(("## Applied", "## Skipped"))], [])
        self.assertIn("## Findings", headings)
        self.assertEqual(self._log_rows(repo)[-1]["applied"], 0)

    def test_a_run_that_applies_everything_still_writes_its_report_and_the_next_run_is_clean(self):
        """Adversarial where: a run whose every finding was applied counts as
        `clean` and writes no report, so the old text is nowhere (the Data
        rule), or the log row of that run reads as an open report with
        findings, or the following run is not clean."""
        repo = shifted_repo(self, ["# S", "", "Cites `src/a.py:5` end."],
                            lambda a: ["new one"] + a)
        code, out, _ = run_drift(repo, "--apply")
        self.assertEqual(code, 0)
        text = newest_report(self, repo)
        self.assertEqual(len(applied_rows(text, "src/a.py:5")), 1)
        self.assertEqual(finding_rows(text, "src/"), [])
        row = self._log_rows(repo)[-1]
        self.assertNotEqual(row["report"], "clean")
        self.assertEqual(row["applied"], 1)
        self.assertEqual(sum(row["counts"].values()), 0)
        from commands import drift
        self.assertIsNone(drift.latest_open_report(str(Path(repo) / ".compass")))
        commit(repo, "apply drift fixes")
        _, out, _ = run_drift(repo, "--apply")
        self.assertIn("clean", out)
        self.assertEqual(self._log_rows(repo)[-1]["applied"], 0)

    def test_apply_and_print_together_are_refused_before_anything_is_written(self):
        """Adversarial where: `--apply --print` rewrites files while claiming
        to write none, or exits 0, or leaves a report behind."""
        repo = shifted_repo(self, ["# S", "", "Cites `src/a.py:5` end."],
                            lambda a: ["new one"] + a)
        before = read_bytes(repo, DOC)
        for args in (("--apply", "--print"), ("--print", "--apply")):
            with self.subTest(args):
                code, out, err = run_drift(repo, *args)
                self.assertEqual(code, 1)
                self.assertEqual(out, "")
                self.assertIn("--apply", err)
                self.assertEqual(read_bytes(repo, DOC), before)
                self.assertEqual(reports(repo), [])


class NetZeroShiftBoundaryTests(unittest.TestCase):
    def test_net_zero_above_is_unchanged_but_still_changed_elsewhere_with_an_edit_below(self):
        """Adversarial where: the `shift == 0` guard added to the `above`
        branch also swallows the `below` branch, so a net-zero edit above
        plus an edit below reads `unchanged` instead of `changed-elsewhere`;
        or hunks above that sum to a nonzero shift (+3, -1) are read as
        net-zero."""
        cite = "`src/a.py:12-13`"
        doc = ["# S", "", f"Cites {cite} end."]
        base = source("A", 30)

        def edit(lines):
            lines = list(lines)
            lines[2] = "A3 edited"          # same-count edit above
            return lines

        def edit_below(lines):
            lines = edit(lines)
            lines[24] = "A25 edited"        # edit below the range
            return lines

        def plus3_minus1(lines):
            return lines[:2] + ["x", "y", "z"] + lines[2:6] + lines[7:]

        rows = (
            ("same-count-above", edit, "unchanged"),
            ("same-count-above-and-edit-below", edit_below, "changed-elsewhere"),
            ("plus3-minus1-above", plus3_minus1, "shifted"),
        )
        for name, change, want in rows:
            with self.subTest(name):
                repo = new_repo(self)
                write(repo, "src/a.py", base)
                write(repo, DOC, doc)
                commit(repo, "base")
                write(repo, "src/a.py", change(base))
                commit(repo, "edit a")
                records = driftlib.scan_refs(repo, Path(repo) / ".compass")
                self.assertEqual([r["class"] for r in records], [want])
                if want == "shifted":
                    self.assertEqual(records[0]["proposal"], {"new_line": 14})


if __name__ == "__main__":
    unittest.main()
