"""Tests for `compass drift --apply`: git-proven rewrites of stale vault text.

The command is dispatched through `maincli.main`, as a user runs it. Every
test builds its own temporary git repository holding a `.compass/` vault and
points `CLAUDE_PROJECT_DIR` at it; nothing reads a live vault.

Contract under test
-------------------
`--apply` rewrites, inside the backtick code span on the citing line only:

* a `shifted` reference to its proposed line span (the cited text is
  byte-identical there);
* a `moved` reference whose rename has similarity 100 to the new path;
* the description of an `index-drift` line whose `newer` side is the target
  to the target's `summary`.

A comma list rewrites only its stale items. `changed`, `missing` and `moved`
below similarity 100 stay as written. A citing file with uncommitted changes
is skipped and named in the report. Files keep their line endings and every
byte outside the rewritten span. Each applied change is a row under
`## Applied` in that run's report carrying the old and the new text;
report-only classes keep their rows under `## Findings`. A run without
`--apply` rewrites nothing, and a second `--apply` after committing the
first one's edits applies nothing.

Adversarial themes: textual replace hitting a prefix twin (`:1` inside
`:10`), character offsets used as byte offsets, line endings normalised on
write, a skipped file's edits lost, rewrites on a prose copy of the
reference, an applied row that drops the old text, and a rewrite that is
itself read as drift on the next run.
"""

import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maincli  # noqa: E402

DOC = ".compass/specs/s.md"
INDEX = ".compass/index.md"
DRIFT_DIR = ".compass/archive/drift"
EPOCH = 1_700_000_000


def git(repo, *args, env=None):
    done = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True, encoding="utf-8",
        env=dict(os.environ, **(env or {})),
    )
    return done.stdout.strip()


def write(repo, rel, lines):
    path = Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def write_bytes(repo, rel, data):
    path = Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def read_bytes(repo, rel):
    return (Path(repo) / rel).read_bytes()


def commit(repo, message, *paths, at=None):
    git(repo, "add", "-A", "--", *(paths or (".",)))
    env = None
    if at is not None:
        stamp = f"{at} +0000"
        env = {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    git(repo, "commit", "-q", "--allow-empty", "-m", message, env=env)


def new_repo(case, autocrlf="false"):
    repo = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, repo, True)
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Tester")
    git(repo, "config", "user.email", "tester@example.invalid")
    git(repo, "config", "core.autocrlf", autocrlf)
    git(repo, "config", "commit.gpgsign", "false")
    return repo


def source(prefix, count=30):
    return [f"{prefix}{n} token" for n in range(1, count + 1)]


def run_drift(repo, *args):
    """Dispatch `compass drift` against `repo`; return (code, stdout, stderr)."""
    saved = os.environ.get("CLAUDE_PROJECT_DIR")
    os.environ["CLAUDE_PROJECT_DIR"] = str(repo)
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = maincli.main(["drift", *args])
    finally:
        if saved is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = saved
    return code, out.getvalue(), err.getvalue()


def reports(repo):
    folder = Path(repo) / DRIFT_DIR
    return sorted(folder.glob("DRIFT-*.md")) if folder.is_dir() else []


def newest_report(case, repo):
    found = reports(repo)
    case.assertTrue(found, "the run wrote no report")
    return found[-1].read_text(encoding="utf-8")


def section(text, title):
    """The lines under the `## <title>` heading, up to the next `## ` heading."""
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line.startswith(f"## {title}")
            continue
        if inside:
            out.append(line)
    return out


def applied_rows(text, needle=""):
    return [l for l in section(text, "Applied") if l.startswith("|") and needle in l]


def lines_of(path_bytes):
    return path_bytes.decode("utf-8").split("\n")


def shifted_repo(case, doc_lines, a_edit, doc_path=DOC):
    """Repo whose `src/a.py` (30 lines) is edited after `doc_lines` cites it.

    Returns the repo with the doc and the edit committed."""
    repo = new_repo(case)
    write(repo, "src/a.py", source("A"))
    write(repo, "src/c.py", source("C", 10))
    write(repo, doc_path, doc_lines)
    commit(repo, "base")
    write(repo, "src/a.py", a_edit(source("A")))
    commit(repo, "edit a")
    return repo


def insert_after(lines, n, *new):
    return lines[:n] + list(new) + lines[n:]


class ShiftRewriteTests(unittest.TestCase):
    def test_shifted_refs_are_rewritten_inside_their_span_and_nothing_else_changes(self):
        """Adversarial where: a textual replace of `src/a.py:1` also hits the
        prefix twin `src/a.py:10`; the prose copy of the reference beside the
        code span is rewritten with it; a width change (9 to 11, 1 to 3) eats
        or leaves a character of the tail; character offsets are used as byte
        offsets after a multibyte character; or the run edits a file other
        than the citing document."""
        doc = [
            "# Spec", "",
            "Before `src/a.py:5` after, plain src/a.py:5 stays.",
            "Range `src/a.py:5-7` end.",
            "Wide `src/a.py:9` end.",
            "Café ☕ `src/a.py:12` tail.",
            "Collide `src/a.py:1` and `src/a.py:10`.",
            "Not code: src/a.py:5 prose only.",
        ]
        repo = shifted_repo(self, doc, lambda a: ["new one", "new two"] + a)
        before = git(repo, "rev-parse", "HEAD")
        code, _, _ = run_drift(repo, "--apply")
        self.assertEqual(code, 0)
        expected = [
            "# Spec", "",
            "Before `src/a.py:7` after, plain src/a.py:5 stays.",
            "Range `src/a.py:7-9` end.",
            "Wide `src/a.py:11` end.",
            "Café ☕ `src/a.py:14` tail.",
            "Collide `src/a.py:3` and `src/a.py:12`.",
            "Not code: src/a.py:5 prose only.",
        ]
        self.assertEqual(lines_of(read_bytes(repo, DOC)), expected + [""])
        changed = set(git(repo, "diff", "--name-only").splitlines())
        self.assertEqual(changed, {DOC})
        self.assertEqual(git(repo, "rev-parse", "HEAD"), before)

    def test_edits_above_that_net_to_zero_are_not_touched(self):
        """Adversarial where: an insert and a delete above the range leave
        its text on the cited line, yet the ref is rewritten to the line it
        already cites (or churned to a different line). The genuinely
        shifted ref `src/a.py:3` (net +1: it sits between the two edits)
        proves the run still rewrites what moved."""
        doc = [
            "# Spec", "",
            "Same `src/a.py:20` line.",
            "Same range `src/a.py:5-7` lines.",
            "Between the edits `src/a.py:3` line.",
        ]

        def edit(a):
            grown = insert_after(a, 1, "NEW")
            return grown[:4] + grown[5:]

        repo = shifted_repo(self, doc, edit)
        run_drift(repo, "--apply")
        expected = list(doc)
        expected[4] = "Between the edits `src/a.py:4` line."
        self.assertEqual(lines_of(read_bytes(repo, DOC)), expected + [""])

    def test_a_comma_list_and_a_line_with_two_refs_change_only_their_stale_items(self):
        """Adversarial where: one stale item rewrites the whole span or the
        whole line (a fresh `src/c.py:5` beside it, or `10` beside `20`)
        and the stale item in the first, middle or last position is missed
        or its neighbours renumbered. `11-14` straddles the insert, so it
        is `changed` and stays."""
        doc = [
            "# Spec", "",
            "Mixed `src/a.py:20` and `src/c.py:5` end.",
            "Reverse `src/c.py:5` and `src/a.py:20`.",
            "List `src/a.py:10,20` end.",
            "List2 `src/a.py:20,10` end.",
            "Middle `src/a.py:5,20,8-9` end.",
            "Straddle `src/a.py:11-14` end.",
        ]
        repo = shifted_repo(self, doc, lambda a: insert_after(a, 12, "n1", "n2"))
        run_drift(repo, "--apply")
        expected = [
            "# Spec", "",
            "Mixed `src/a.py:22` and `src/c.py:5` end.",
            "Reverse `src/c.py:5` and `src/a.py:22`.",
            "List `src/a.py:10,22` end.",
            "List2 `src/a.py:22,10` end.",
            "Middle `src/a.py:5,22,8-9` end.",
            "Straddle `src/a.py:11-14` end.",
        ]
        self.assertEqual(lines_of(read_bytes(repo, DOC)), expected + [""])

    def test_research_and_handoff_documents_are_rewritten_like_any_other(self):
        """Adversarial where: documents of `type: research` or `handoff`
        are treated as read-only history and left stale, or only the first
        document of the run is rewritten."""
        repo = new_repo(self)
        write(repo, "src/a.py", source("A"))
        docs = {}
        for kind in ("research", "handoff", "spec"):
            rel = f".compass/{kind}/d.md"
            docs[rel] = ["---", f"title: D", f"type: {kind}", "---", "",
                         "Cites `src/a.py:5` here."]
            write(repo, rel, docs[rel])
        commit(repo, "base")
        write(repo, "src/a.py", ["new"] + source("A"))
        commit(repo, "edit a")
        run_drift(repo, "--apply")
        for rel, lines in docs.items():
            with self.subTest(rel):
                want = lines[:-1] + ["Cites `src/a.py:6` here."]
                self.assertEqual(lines_of(read_bytes(repo, rel)), want + [""])

    def test_a_run_without_apply_rewrites_nothing(self):
        """Adversarial where: the rewrite is the default and `--apply` only
        changes the report, so a plain scan edits the vault."""
        doc = ["# Spec", "", "Cites `src/a.py:5` here."]
        repo = shifted_repo(self, doc, lambda a: ["new"] + a)
        original = read_bytes(repo, DOC)
        code, _, _ = run_drift(repo)
        self.assertEqual(code, 0)
        self.assertEqual(read_bytes(repo, DOC), original)
        self.assertEqual(applied_rows(newest_report(self, repo)), [])


class MoveRewriteTests(unittest.TestCase):
    def test_a_pure_rename_rewrites_the_path_once_per_span_and_keeps_the_lines(self):
        """Adversarial where: the line numbers are dropped or shifted along
        with the path, a comma list gets the path written once per item, or
        a ref to an untouched file beside it is rewritten too."""
        doc = [
            "# Spec", "",
            "One `src/a.py:5` end.",
            "Range `src/a.py:5-7` end.",
            "List `src/a.py:5,8` end.",
            "Pair `src/a.py:5` and `src/c.py:2` end.",
        ]
        repo = new_repo(self)
        write(repo, "src/a.py", source("A"))
        write(repo, "src/c.py", source("C", 10))
        write(repo, DOC, doc)
        commit(repo, "base")
        git(repo, "mv", "src/a.py", "src/lib_a.py")
        commit(repo, "rename")
        run_drift(repo, "--apply")
        expected = [l.replace("src/a.py", "src/lib_a.py") for l in doc]
        self.assertEqual(lines_of(read_bytes(repo, DOC)), expected + [""])


class ReportOnlyTests(unittest.TestCase):
    def test_changed_missing_and_partial_renames_stay_as_written_and_in_findings(self):
        """Adversarial where: a `changed` ref is rewritten to wherever the
        old text went, a rename with one edited line (similarity below 100)
        is treated as a pure rename, a deleted file's ref is rewritten, or
        the rows of these classes move from `## Findings` to `## Applied`."""
        doc = [
            "# Spec", "",
            "Edited `src/a.py:5-7` end.",
            "Renamed with an edit `src/b.py:5-7` end.",
            "Deleted `src/gone.py:2` end.",
        ]
        repo = new_repo(self)
        write(repo, "src/a.py", source("A"))
        write(repo, "src/b.py", source("B", 10))
        write(repo, "src/gone.py", source("G", 10))
        write(repo, DOC, doc)
        commit(repo, "base")
        edited = source("A")
        edited[5] = "A6 rewritten"
        write(repo, "src/a.py", edited)
        git(repo, "mv", "src/b.py", "src/lib_b.py")
        renamed = source("B", 10)
        renamed[2] = "B3 rewritten"
        write(repo, "src/lib_b.py", renamed)
        git(repo, "rm", "-q", "src/gone.py")
        commit(repo, "edit, rename, delete")
        original = read_bytes(repo, DOC)
        code, _, _ = run_drift(repo, "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(read_bytes(repo, DOC), original)
        text = newest_report(self, repo)
        self.assertEqual(applied_rows(text), [])
        findings = [l for l in section(text, "Findings") if l.startswith("|")]
        for cite, cls in (("src/a.py:5-7", "changed"), ("src/b.py:5-7", "moved"),
                          ("src/gone.py:2", "missing")):
            with self.subTest(cite):
                rows = [l for l in findings if cite in l]
                self.assertEqual(len(rows), 1, rows)
                self.assertRegex(rows[0], rf"(?<![\w-]){cls}(?![\w-])")


class IndexResyncTests(unittest.TestCase):
    def test_target_newer_lines_take_the_summary_and_index_newer_lines_stay(self):
        """Adversarial where: every drifting index line is overwritten, so a
        hand edit newer than the summary is lost; the description is
        replaced through a regex template so `\\1` or `\\g<0>` in a summary
        is expanded; or the link and the `(3 children)` annotation before the
        description are eaten with it."""
        repo = new_repo(self)
        write(repo, INDEX, [
            "# Index", "", "## Specs", "",
            "- [[SPEC-001-alpha]] - Alpha does Y",
            "- [[SPEC-002-beta]] - Beta stale",
            "- [[SPEC-003-gamma]] (3 children) - Gamma old",
        ])
        for name, summary in (("SPEC-001-alpha", "Alpha does Y"),
                              ("SPEC-002-beta", "Beta summary"),
                              ("SPEC-003-gamma", "Gamma old")):
            write(repo, f".compass/specs/{name}.md",
                  ["---", f"title: {name}", f"summary: {summary}", "---", "", "Body."])
        commit(repo, "seed", at=EPOCH)
        write(repo, ".compass/specs/SPEC-001-alpha.md",
              ["---", "title: a", "summary: Alpha does X", "---", "", "Body."])
        write(repo, ".compass/specs/SPEC-003-gamma.md",
              ["---", "title: g", "summary: Gamma \\1 and \\g<0> costs", "---", "", "Body."])
        commit(repo, "summaries", at=EPOCH + 100)
        write(repo, INDEX, [
            "# Index", "", "## Specs", "",
            "- [[SPEC-001-alpha]] - Alpha does Y",
            "- [[SPEC-002-beta]] - Beta hand edit",
            "- [[SPEC-003-gamma]] (3 children) - Gamma old",
        ])
        commit(repo, "hand edit", at=EPOCH + 200)
        code, _, _ = run_drift(repo, "--apply")
        self.assertEqual(code, 0)
        expected = [
            "# Index", "", "## Specs", "",
            "- [[SPEC-001-alpha]] - Alpha does X",
            "- [[SPEC-002-beta]] - Beta hand edit",
            "- [[SPEC-003-gamma]] (3 children) - Gamma \\1 and \\g<0> costs",
        ]
        self.assertEqual(lines_of(read_bytes(repo, INDEX)), expected + [""])
        text = newest_report(self, repo)
        self.assertEqual(len(applied_rows(text, "Alpha does Y")), 1)
        self.assertEqual(applied_rows(text, "Beta"), [])
        beta = [l for l in section(text, "Findings") if "Beta hand edit" in l]
        self.assertEqual(len(beta), 1, "the index-newer line stays a finding")


class SkipAndEncodingTests(unittest.TestCase):
    def test_a_citing_file_with_uncommitted_changes_is_skipped_and_named(self):
        """Adversarial where: the rewrite lands in a file whose working text
        is not its blame base (and the next scan reads it as
        unclassifiable), the skip is per run instead of per file so the clean
        document is skipped too, the uncommitted edit is lost, or the skip
        is silent. A staged-only edit counts as uncommitted."""
        dirty = ".compass/specs/dirty.md"
        clean = ".compass/specs/clean.md"
        for how in ("unstaged", "staged"):
            with self.subTest(how):
                repo = new_repo(self)
                write(repo, "src/a.py", source("A"))
                for rel in (dirty, clean):
                    write(repo, rel, ["# Spec", "", "Cites `src/a.py:5` here."])
                commit(repo, "base")
                write(repo, "src/a.py", ["new"] + source("A"))
                commit(repo, "edit a")
                edited = ["# Spec", "", "Cites `src/a.py:5` here.", "Uncommitted tail."]
                write(repo, dirty, edited)
                if how == "staged":
                    git(repo, "add", "--", dirty)
                before = read_bytes(repo, dirty)
                code, _, _ = run_drift(repo, "--apply")
                self.assertEqual(code, 0)
                self.assertEqual(read_bytes(repo, dirty), before)
                self.assertEqual(
                    lines_of(read_bytes(repo, clean)),
                    ["# Spec", "", "Cites `src/a.py:6` here.", ""])
                text = newest_report(self, repo)
                skipped = [l for l in text.splitlines()
                           if dirty in l and "skip" in l.lower()]
                self.assertTrue(skipped, "the skipped file is not named as skipped")
                self.assertEqual(applied_rows(text, dirty), [])

    def test_line_endings_and_every_byte_outside_the_span_survive(self):
        """Adversarial where: the file is read in text mode and written back
        LF (a CRLF document churned on every run, which an `autocrlf=true`
        checkout turns into a whole-file diff), a mixed-ending file is
        normalised, a missing final newline is added, or a UTF-8 byte
        sequence is re-encoded."""
        ref = b"`src/a.py:5`"
        want_ref = b"`src/a.py:7`"
        rows = {
            "all-crlf": (b"# Spec\r\n\r\nCites " + ref + b" here.\r\nEnd.\r\n", "false"),
            "mixed": (b"# Spec\r\nCaf\xc3\xa9 " + ref + b" a.\nMore.\r\nEnd.\n", "false"),
            "no-final-newline": (b"# Spec\r\n\r\nCites " + ref + b" here.", "false"),
            "autocrlf-true": (b"# Spec\r\n\r\nCites " + ref + b" here.\r\nEnd.\r\n", "true"),
        }
        for name, (data, autocrlf) in rows.items():
            with self.subTest(name):
                repo = new_repo(self, autocrlf)
                write(repo, "src/a.py", source("A"))
                write_bytes(repo, DOC, data)
                commit(repo, "base")
                write(repo, "src/a.py", ["new one", "new two"] + source("A"))
                commit(repo, "edit a")
                self.assertRegex(run_drift(repo, "--print")[1], r"(?<![\w-])shifted(?![\w-])")
                run_drift(repo, "--apply")
                self.assertEqual(read_bytes(repo, DOC), data.replace(ref, want_ref))
                if autocrlf == "true":
                    stat = git(repo, "diff", "--numstat", "--", DOC)
                    self.assertEqual(stat.split()[:2], ["1", "1"], stat)


class ReportTests(unittest.TestCase):
    def test_applied_rows_carry_old_and_new_and_a_second_apply_applies_nothing(self):
        """Adversarial where: an applied row keeps only the new text (the old
        reference is gone from the vault, breaking the Data rule), a row
        omits the citing file, an applied class is also left as an open
        finding of the same run, or the committed rewrite is read as drift
        on the next run so a second `--apply` rewrites again."""
        repo = new_repo(self)
        write(repo, "src/a.py", source("A"))
        write(repo, "src/b.py", source("B", 10))
        write(repo, DOC, ["# Spec", "", "Shift `src/a.py:5` and move `src/b.py:2`."])
        write(repo, INDEX, ["# Index", "", "## Specs", "",
                            "- [[SPEC-001-alpha]] - Alpha does Y"])
        write(repo, ".compass/specs/SPEC-001-alpha.md",
              ["---", "title: a", "summary: Alpha does Y", "---", "", "Body."])
        commit(repo, "base", at=EPOCH)
        write(repo, "src/a.py", ["new"] + source("A"))
        git(repo, "mv", "src/b.py", "src/lib_b.py")
        write(repo, ".compass/specs/SPEC-001-alpha.md",
              ["---", "title: a", "summary: Alpha does X", "---", "", "Body."])
        commit(repo, "edits", at=EPOCH + 100)
        code, _, _ = run_drift(repo, "--apply")
        self.assertEqual(code, 0)
        text = newest_report(self, repo)
        for path, old, new in ((DOC, "src/a.py:5", "src/a.py:6"),
                               (DOC, "src/b.py:2", "src/lib_b.py:2"),
                               (INDEX, "Alpha does Y", "Alpha does X")):
            with self.subTest(old):
                rows = [l for l in applied_rows(text, path) if old in l]
                self.assertEqual(len(rows), 1, rows)
                self.assertIn(new, rows[0])
        for old in ("src/a.py:5", "src/b.py:2", "Alpha does Y"):
            with self.subTest(f"{old} is not an open finding"):
                open_rows = [l for l in section(text, "Findings")
                             if l.startswith("|") and old in l]
                self.assertEqual(open_rows, [])

        commit(repo, "apply drift fixes")
        committed = {rel: read_bytes(repo, rel) for rel in (DOC, INDEX)}
        reports_before = len(reports(repo))
        code, _, _ = run_drift(repo, "--apply")
        self.assertEqual(code, 0)
        for rel, data in committed.items():
            with self.subTest(f"second run leaves {rel}"):
                self.assertEqual(read_bytes(repo, rel), data)
        for report in reports(repo)[reports_before:]:
            self.assertEqual(applied_rows(report.read_text(encoding="utf-8")), [])


if __name__ == "__main__":
    unittest.main()
