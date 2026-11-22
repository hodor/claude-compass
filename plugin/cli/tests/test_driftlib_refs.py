"""Tests for the code-reference classifier in `driftlib`.

Public API under test
---------------------

``driftlib.scan_refs(repo_root, vault_dir, base_from="blame")``

* ``repo_root``: ``pathlib.Path`` of a git repository.
* ``vault_dir``: ``pathlib.Path`` of the vault directory inside it.
* ``base_from``: ``"blame"`` (base = commit that last changed the citing
  line, by ``git blame --porcelain``) or ``"add"`` (base = commit that added
  the citing document).
* Returns a list of dict records, sorted by ``(file, line, ref_start)``,
  one per cited range. Every record has exactly these keys:

  - ``file``: citing document, repo-relative with ``/`` separators.
  - ``line``: 1-based line number of the citation inside that document.
  - ``ref_path``: cited path as written.
  - ``ref_start`` / ``ref_end``: 1-based inclusive cited range
    (``path:N`` gives ``N, N``; ``path:2,5-7`` gives two records).
  - ``base``: full 40-hex sha of the base commit, ``None`` when unknown.
  - ``class``: one of ``unchanged``, ``changed-elsewhere``, ``shifted``,
    ``changed``, ``moved``, ``missing``, ``unclassifiable``, ``malformed``.
  - ``old_text``: the cited lines at ``base`` joined with ``"\\n"``
    (no trailing newline); ``None`` when there is no base.
  - ``current_text``: the cited lines at ``HEAD`` joined with ``"\\n"``.
    For ``unchanged`` / ``changed-elsewhere`` / ``changed`` these are the
    lines at the same line numbers; for ``shifted`` the same lines at their
    new position; for ``moved`` the same line numbers in the new path;
    ``None`` for ``missing`` and ``unclassifiable``.
  - ``proposal``: ``None`` except for ``shifted``
    (``{"new_line": <new start line>}``) and ``moved``
    (``{"new_path", "rename_commit" (full sha), "similarity" (int percent)}``).

Scan rules: markdown files under ``vault_dir`` except its top-level
``archive/`` and ``tmp/`` subtrees; a reference is ``path:N``, ``path:N-M``
or a comma list of those inside an inline code span or a fenced code block
(never plain prose); ``path`` must equal or sit below a top-level entry of
``git ls-files``. Out-of-range, zero, reversed or non-numeric line numbers
are either not reported or reported with class ``malformed``; they never
raise. Classification diffs ``base..HEAD`` for the cited path only; the
working tree is not consulted.

Adversarial themes: diff-hunk boundary arithmetic for pure insertions and
deletions, blame-versus-add base selection, rename detection thresholds,
and extraction false positives.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import driftlib  # noqa: E402

KEYS = {
    "file", "line", "ref_path", "ref_start", "ref_end", "base", "class",
    "old_text", "current_text", "proposal",
}
A_LINES = [f"line {n}" for n in range(1, 11)]
DOC_PATH = ".compass/specs/s.md"


def git(repo, *args):
    done = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    return done.stdout.strip()


def write(repo, rel, lines):
    path = Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def commit(repo, message, *paths):
    if paths:
        git(repo, "add", "-A", "--", *paths)
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def new_repo(case):
    repo = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, repo, True)
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Tester")
    git(repo, "config", "user.email", "tester@example.invalid")
    git(repo, "config", "core.autocrlf", "false")
    git(repo, "config", "commit.gpgsign", "false")
    return repo


def doc_with(*cited):
    """A document whose line 3 carries each reference in `cited` as a code span."""
    spans = " and ".join(f"`{c}`" for c in cited)
    return ["# Spec", "", f"See {spans} for details."]


def seeded_repo(case, doc_lines, a_lines=A_LINES):
    """Repo with src/a.py, src/b.py, README.md and one vault doc, one commit."""
    repo = new_repo(case)
    write(repo, "src/a.py", a_lines)
    write(repo, "src/b.py", ["b"])
    write(repo, "README.md", ["readme"])
    write(repo, DOC_PATH, doc_lines)
    base = commit(repo, "seed", "src", "README.md", ".compass")
    return repo, base


def scan(repo, base_from="blame"):
    return driftlib.scan_refs(repo, Path(repo) / ".compass", base_from=base_from)


def only(case, records):
    case.assertEqual(len(records), 1, records)
    return records[0]


def insert_after(lines, n, *new):
    return lines[:n] + list(new) + lines[n:]


def replace_line(lines, n, text):
    return lines[: n - 1] + [text] + lines[n:]


def delete_line(lines, n):
    return lines[: n - 1] + lines[n:]


class ExtractionTests(unittest.TestCase):
    def test_only_code_span_references_under_known_top_level_entries_are_found(self):
        """Adversarial where: extraction treats plain prose, URLs, a path that
        merely shares a prefix with a top-level entry (`srcfoo` vs `src`), or
        an unknown top-level directory as a reference, or misses a fenced
        block, a comma list, a bare top-level file, or a second span on one line."""
        doc = [
            "# T",
            "Inline `src/a.py:5` ok.",
            "Range `src/a.py:5-7` ok.",
            "List `src/a.py:2,5-7` ok.",
            "Prose src/a.py:6 without backticks.",
            "```",
            "src/a.py:3",
            "```",
            "Url `http://localhost:8080` no.",
            "Prefix `srcfoo/a.py:3` no.",
            "Unknown `nothere/x.py:3` no.",
            "Root `README.md:1` ok.",
            "Two `src/a.py:1` and `src/b.py:1` ok.",
        ]
        repo, _ = seeded_repo(self, doc)
        recs = scan(repo)
        got = sorted((r["line"], r["ref_path"], r["ref_start"], r["ref_end"]) for r in recs)
        want = sorted([
            (2, "src/a.py", 5, 5),
            (3, "src/a.py", 5, 7),
            (4, "src/a.py", 2, 2),
            (4, "src/a.py", 5, 7),
            (7, "src/a.py", 3, 3),
            (12, "README.md", 1, 1),
            (13, "src/a.py", 1, 1),
            (13, "src/b.py", 1, 1),
        ])
        self.assertEqual(got, want)
        for rec in recs:
            self.assertEqual(set(rec), KEYS)
            self.assertEqual(rec["file"], DOC_PATH)

    def test_malformed_line_numbers_never_crash_and_never_classify(self):
        """Adversarial where: `path:0`, `path:abc`, a reversed range, and
        numbers one past the end of a 10-line file (a trailing newline
        counted as an extra line) crash the scan, get a real drift class,
        or swallow the valid reference beside them."""
        bad = ["src/a.py:0", "src/a.py:abc", "src/a.py:7-5",
               "src/a.py:11", "src/a.py:9-11", "src/a.py:5-99"]
        good = ["src/a.py:10", "src/a.py:9-10"]
        doc = ["# T"] + [f"Ref `{c}` here." for c in bad + good]
        repo, _ = seeded_repo(self, doc)
        recs = scan(repo)
        by_ref = {(r["ref_start"], r["ref_end"]): r for r in recs
                  if r["class"] != "malformed"}
        self.assertEqual(sorted(by_ref), [(9, 10), (10, 10)])
        self.assertEqual({r["class"] for r in by_ref.values()}, {"unchanged"})
        self.assertEqual(by_ref[(9, 10)]["old_text"], "line 9\nline 10")
        for rec in recs:
            if rec["class"] == "malformed":
                self.assertIn(rec["ref_path"], {"src/a.py"})

    def test_scan_skips_vault_archive_and_tmp_but_reads_nested_and_prefixed_dirs(self):
        """Adversarial where: the exclusion is a prefix match (`archived/`
        skipped like `archive/`), or it misses `tmp/`, or nested spec
        folders are not walked."""
        repo = new_repo(self)
        write(repo, "src/a.py", A_LINES)
        for rel in ("specs/x.md", "specs/sub/y.md", "archived/q.md",
                    "archive/z.md", "tmp/t.md"):
            write(repo, f".compass/{rel}", ["# D", "Ref `src/a.py:5` x."])
        commit(repo, "seed", "src", ".compass")
        files = {r["file"] for r in scan(repo)}
        self.assertEqual(files, {
            ".compass/specs/x.md", ".compass/specs/sub/y.md",
            ".compass/archived/q.md",
        })


class ClassificationTests(unittest.TestCase):
    def test_diff_boundaries_classify_each_edit_position(self):
        """Adversarial where: pure-insertion and pure-deletion hunks
        (`-N,0` / `+N,0`) are read as touching line N, so an insertion
        directly below the range reads `changed`, one directly above reads
        `changed-elsewhere`, or an edit of the first or last range line
        reads as outside the range."""
        rng, single = "src/a.py:5-7", "src/a.py:5"
        old_rng = "line 5\nline 6\nline 7"
        rows = [
            ("unrelated-file-edit", rng, None, "unchanged", None, old_rng),
            ("insert-directly-below", rng, lambda s: insert_after(s, 7, "NEW"), "changed-elsewhere", None, old_rng),
            ("edit-line-below", rng, lambda s: replace_line(s, 8, "NEW"), "changed-elsewhere", None, old_rng),
            ("append-at-eof", rng, lambda s: s + ["NEW"], "changed-elsewhere", None, old_rng),
            ("delete-line-below", rng, lambda s: delete_line(s, 8), "changed-elsewhere", None, old_rng),
            ("insert-directly-above", rng, lambda s: insert_after(s, 4, "NEW"), "shifted", 6, old_rng),
            ("delete-directly-above", rng, lambda s: delete_line(s, 4), "shifted", 4, old_rng),
            ("edit-above-same-count", rng, lambda s: replace_line(s, 4, "NEW"), "shifted", 5, old_rng),
            ("insert-at-top", rng, lambda s: ["NEW"] + s, "shifted", 6, old_rng),
            ("above-and-below", rng, lambda s: replace_line(insert_after(s, 2, "NEW"), 10, "TAIL"), "shifted", 6, old_rng),
            ("edit-first-line", rng, lambda s: replace_line(s, 5, "NEW"), "changed", None, "NEW\nline 6\nline 7"),
            ("edit-last-line", rng, lambda s: replace_line(s, 7, "NEW"), "changed", None, "line 5\nline 6\nNEW"),
            ("insert-inside", rng, lambda s: insert_after(s, 5, "NEW"), "changed", None, None),
            ("delete-inside", rng, lambda s: delete_line(s, 6), "changed", None, None),
            ("above-and-inside", rng, lambda s: replace_line(insert_after(s, 2, "NEW"), 7, "MID"), "changed", None, None),
            ("single-insert-after", single, lambda s: insert_after(s, 5, "NEW"), "changed-elsewhere", None, "line 5"),
            ("single-insert-before", single, lambda s: insert_after(s, 4, "NEW"), "shifted", 6, "line 5"),
            ("single-edit", single, lambda s: replace_line(s, 5, "NEW"), "changed", None, "NEW"),
        ]
        for name, ref, mutate, want_class, want_line, want_current in rows:
            with self.subTest(name):
                repo, base = seeded_repo(self, doc_with(ref))
                if mutate is None:
                    write(repo, "src/b.py", ["b2"])
                    commit(repo, "touch b", "src/b.py")
                else:
                    write(repo, "src/a.py", mutate(A_LINES))
                    commit(repo, "edit a", "src/a.py")
                rec = only(self, scan(repo))
                self.assertEqual(rec["class"], want_class)
                self.assertEqual(rec["base"], base)
                self.assertEqual(rec["line"], 3)
                if want_line is not None:
                    self.assertEqual(rec["proposal"], {"new_line": want_line})
                if want_current is not None:
                    self.assertEqual(rec["current_text"], want_current)
                self.assertEqual(rec["old_text"], "line 5" if ref == single else old_rng)

    def test_shifted_new_line_follows_position_not_first_text_match(self):
        """Adversarial where: the new line is found by searching the file for
        the cited text, so a duplicate of that text earlier in the file
        (line 2) is reported instead of the shifted original (line 6)."""
        lines = replace_line(replace_line(A_LINES, 2, "dup"), 5, "dup")
        repo, _ = seeded_repo(self, doc_with("src/a.py:5"), a_lines=lines)
        write(repo, "src/a.py", insert_after(lines, 4, "NEW"))
        commit(repo, "edit a", "src/a.py")
        rec = only(self, scan(repo))
        self.assertEqual(rec["class"], "shifted")
        self.assertEqual(rec["proposal"], {"new_line": 6})
        self.assertEqual(rec["current_text"], "dup")

    def test_blame_base_reanchors_on_citing_line_edit_but_add_base_does_not(self):
        """Adversarial where: the base is taken per document instead of per
        line (a later edit to a different doc line re-anchors this one), or
        `--base-from add` follows blame, or blame mode ignores that editing
        the citing line re-anchors it."""
        doc = ["# T", "One `src/a.py:5` here.", "", "Two `src/a.py:8` here."]
        repo, add_sha = seeded_repo(self, doc)
        write(repo, "src/a.py", replace_line(A_LINES, 5, "NEW"))
        commit(repo, "edit a", "src/a.py")
        write(repo, DOC_PATH, replace_line(doc, 2, "One `src/a.py:5` re-anchored."))
        edit_sha = commit(repo, "edit citing line", DOC_PATH)

        blame = {r["line"]: r for r in scan(repo, "blame")}
        self.assertEqual(blame[2]["base"], edit_sha)
        self.assertEqual(blame[2]["class"], "unchanged")
        self.assertEqual(blame[4]["base"], add_sha)
        self.assertEqual(blame[4]["class"], "shifted")
        self.assertEqual(blame[4]["proposal"], {"new_line": 8})

        added = {r["line"]: r for r in scan(repo, "add")}
        self.assertEqual(added[2]["base"], add_sha)
        self.assertEqual(added[2]["class"], "changed")
        self.assertEqual(added[2]["old_text"], "line 5")
        self.assertEqual(added[4]["base"], add_sha)
        self.assertEqual(added[4]["class"], "shifted")


class FileFateTests(unittest.TestCase):
    def test_renamed_file_is_moved_with_rename_commit_and_similarity(self):
        """Adversarial where: a rename is reported `missing`, the proposed
        commit is HEAD instead of the rename commit, similarity is not 100
        for a pure rename or not below 100 for a rename with edits."""
        rows = [("pure-rename", None), ("rename-with-edits", [3, 8])]
        for name, edited in rows:
            with self.subTest(name):
                repo, base = seeded_repo(self, doc_with("src/a.py:5-7"))
                git(repo, "mv", "src/a.py", "lib_a.py")
                lines = list(A_LINES)
                for n in edited or []:
                    lines = replace_line(lines, n, f"changed {n}")
                write(repo, "lib_a.py", lines)
                rename_sha = commit(repo, "rename", "lib_a.py", "src")
                write(repo, "src/b.py", ["b2"])
                head_sha = commit(repo, "later", "src/b.py")
                self.assertNotEqual(rename_sha, head_sha)
                rec = only(self, scan(repo))
                self.assertEqual(rec["class"], "moved")
                self.assertEqual(rec["base"], base)
                prop = rec["proposal"]
                self.assertEqual(prop["new_path"], "lib_a.py")
                self.assertEqual(prop["rename_commit"], rename_sha)
                if edited is None:
                    self.assertEqual(prop["similarity"], 100)
                    self.assertEqual(rec["current_text"], rec["old_text"])
                else:
                    self.assertGreaterEqual(prop["similarity"], 50)
                    self.assertLess(prop["similarity"], 100)

    def test_deleted_file_is_missing_even_when_an_unrelated_file_is_added(self):
        """Adversarial where: a deletion paired with an unrelated new file in
        the same commit is read as a rename (below git's similarity
        threshold), or a deleted file loses its base-time text."""
        for name, extra in (("plain-delete", None), ("delete-and-unrelated-add", ["zzzz"] * 3)):
            with self.subTest(name):
                repo, base = seeded_repo(self, doc_with("src/a.py:5-7"))
                git(repo, "rm", "-q", "src/a.py")
                if extra:
                    write(repo, "src/z.py", extra)
                commit(repo, "delete a", "src")
                rec = only(self, scan(repo))
                self.assertEqual(rec["class"], "missing")
                self.assertEqual(rec["base"], base)
                self.assertEqual(rec["old_text"], "line 5\nline 6\nline 7")
                self.assertIsNone(rec["current_text"])
                self.assertIsNone(rec["proposal"])

    def test_uncommitted_citing_line_is_unclassifiable_with_no_base(self):
        """Adversarial where: an uncommitted citing line (untracked document,
        or a working-tree edit blamed to the all-zero commit) is given a
        bogus base or a drift class instead of `unclassifiable`, or the
        committed reference in the same modified document is lost."""
        repo, base = seeded_repo(self, doc_with("src/a.py:5"))
        write(repo, ".compass/specs/untracked.md", doc_with("src/a.py:6"))
        write(repo, DOC_PATH, doc_with("src/a.py:5") + ["Late `src/a.py:7` here."])
        recs = scan(repo)
        by_file_line = {(r["file"], r["line"]): r for r in recs}
        self.assertEqual(len(recs), 3, recs)
        for key in ((".compass/specs/untracked.md", 3), (DOC_PATH, 4)):
            rec = by_file_line[key]
            self.assertEqual(rec["class"], "unclassifiable")
            self.assertIsNone(rec["base"])
            self.assertIsNone(rec["old_text"])
        committed = by_file_line[(DOC_PATH, 3)]
        self.assertEqual(committed["class"], "unchanged")
        self.assertEqual(committed["base"], base)
        untracked_add = {(r["file"], r["line"]): r for r in scan(repo, "add")}
        self.assertEqual(
            untracked_add[(".compass/specs/untracked.md", 3)]["class"], "unclassifiable")


if __name__ == "__main__":
    unittest.main()
