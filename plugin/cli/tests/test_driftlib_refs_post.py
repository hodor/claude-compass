"""Adversarial tests for `driftlib.scan_refs` aimed at implementation branches.

Covers fence tracking, pathspec handling in batched diffs, batching limits
(blame range cap, argument chunking), CRLF content, unicode and space paths,
and one document citing a path at two base commits.
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

DOC_PATH = ".compass/specs/s.md"
A_LINES = [f"line {n}" for n in range(1, 11)]


def git(repo, *args):
    done = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    return done.stdout.strip()


def write_bytes(repo, rel, data):
    path = Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def write(repo, rel, lines):
    write_bytes(repo, rel, ("\n".join(lines) + "\n").encode("utf-8"))


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


def scan(repo, base_from="blame"):
    return driftlib.scan_refs(repo, Path(repo) / ".compass", base_from=base_from)


def by_line(records):
    return {(r["file"], r["line"], r["ref_start"], r["ref_end"]): r for r in records}


class FenceTrackingTests(unittest.TestCase):
    def test_mixed_fence_markers_do_not_turn_later_prose_into_a_fenced_block(self):
        """Adversarial where: a `~~~` line inside a backtick fence is toggled as
        a fence by the scanner, flipping its state; the real closing fence then
        reopens it and a plain-prose citation after the block is reported."""
        repo = new_repo(self)
        write(repo, "src/a.py", [f"line {n}" for n in range(1, 11)])
        write(repo, DOC_PATH, [
            "# Doc",
            "```text",
            "~~~",
            "```",
            "Prose src/a.py:6 outside any block.",
        ])
        commit(repo, "seed", "src", ".compass")
        self.assertEqual(scan(repo), [])

    def test_longer_outer_fence_keeps_inner_shorter_fence_lines_as_content(self):
        """Adversarial where: a four-backtick fence containing a three-backtick
        line is closed early by the inner line, so a citation later inside the
        outer block is missed."""
        repo = new_repo(self)
        write(repo, "src/a.py", [f"line {n}" for n in range(1, 11)])
        write(repo, DOC_PATH, [
            "# Doc",
            "````md",
            "```",
            "src/a.py:6",
            "````",
        ])
        commit(repo, "seed", "src", ".compass")
        found = scan(repo)
        self.assertEqual([(r["line"], r["ref_start"]) for r in found], [(4, 6)])


class PathspecTests(unittest.TestCase):
    def test_one_unresolvable_cited_path_does_not_poison_other_refs_at_same_base(self):
        """Adversarial where: all cited paths for a base commit go in one
        `git diff` call; a pathspec git rejects (`..` escaping the repo or
        pointing nowhere) fails the call and every sibling reference at that
        base is demoted to unclassifiable."""
        repo = new_repo(self)
        write(repo, "src/a.py", A_LINES)
        write(repo, "README.md", ["readme"])
        write(repo, DOC_PATH, [
            "# Doc", "",
            "Cites `src/../../x.py:1` and `src/a.py:5` together.",
        ])
        commit(repo, "seed", "src", "README.md", ".compass")
        write(repo, "src/a.py", A_LINES[:4] + ["edited"] + A_LINES[5:])
        commit(repo, "edit", "src")
        classes = {r["ref_path"]: r["class"] for r in scan(repo)}
        self.assertEqual(classes.get("src/a.py"), "changed")

    def test_dot_segments_in_a_cited_path_still_classify_the_real_file(self):
        """Adversarial where: `src/./a.py` normalises to `src/a.py` in git but
        the scanner keys diff results by the literal string, so the lookup
        misses and a changed range is reported as unchanged."""
        repo = new_repo(self)
        write(repo, "src/a.py", A_LINES)
        write(repo, DOC_PATH, ["# Doc", "", "See `src/./a.py:5` here."])
        commit(repo, "seed", "src", ".compass")
        write(repo, "src/a.py", A_LINES[:4] + ["edited"] + A_LINES[5:])
        commit(repo, "edit", "src")
        for rec in scan(repo):
            self.assertNotEqual(rec["class"], "unchanged", rec)


class BatchingLimitTests(unittest.TestCase):
    def test_more_blame_ranges_than_the_range_cap_still_resolve_each_base(self):
        """Adversarial where: above the cap the scanner drops `-L` ranges and
        blames the whole file; line-number mapping from the porcelain output
        must still pick the right commit per citing line."""
        repo = new_repo(self)
        write(repo, "src/a.py", A_LINES)
        lines = ["# Doc"]
        for _ in range(170):
            lines += ["`src/a.py:5`", "filler"]
        write(repo, DOC_PATH, lines)
        commit(repo, "seed", "src", ".compass")
        write(repo, "src/a.py", A_LINES[:4] + ["edited"] + A_LINES[5:])
        commit(repo, "edit", "src")
        lines[1] = "`src/a.py:6`"
        write(repo, DOC_PATH, lines)
        reanchor = commit(repo, "reanchor", ".compass")
        found = scan(repo)
        self.assertEqual(len(found), 170)
        first = [r for r in found if r["line"] == 2][0]
        second = [r for r in found if r["line"] == 4][0]
        self.assertEqual(first["base"], reanchor)
        self.assertEqual(first["class"], "unchanged")
        self.assertEqual(second["class"], "changed")

    def test_cited_paths_spanning_several_diff_chunks_all_classify(self):
        """Adversarial where: path arguments are split into chunks per `git
        diff` call; results of later chunks must merge into the table, so an
        edit to a file in the last chunk is still seen."""
        repo = new_repo(self)
        names = [f"src/{'x' * 70}{n:04d}.py" for n in range(600)]
        for name in names:
            write(repo, name, A_LINES)
        cites = [f"`{name}:5`" for name in names]
        write(repo, DOC_PATH, ["# Doc"] + cites)
        commit(repo, "seed", "src", ".compass")
        write(repo, names[-1], A_LINES[:4] + ["edited"] + A_LINES[5:])
        write(repo, names[0], A_LINES[:4] + ["edited"] + A_LINES[5:])
        commit(repo, "edit", "src")
        classes = {r["ref_path"]: r["class"] for r in scan(repo)}
        self.assertEqual(len(classes), 600)
        self.assertEqual(classes[names[0]], "changed")
        self.assertEqual(classes[names[-1]], "changed")
        self.assertEqual(classes[names[300]], "unchanged")


class ContentEncodingTests(unittest.TestCase):
    def test_crlf_cited_file_yields_texts_without_carriage_returns(self):
        """Adversarial where: a CRLF-terminated blob keeps `\\r` on every line
        when split on `\\n`, so old_text and current_text carry stray carriage
        returns and never equal the same text from an LF file."""
        repo = new_repo(self)
        crlf = "".join(f"line {n}\r\n" for n in range(1, 11)).encode()
        write_bytes(repo, "src/a.py", crlf)
        write(repo, DOC_PATH, ["# Doc", "", "See `src/a.py:5-6`."])
        commit(repo, "seed", "src", ".compass")
        write_bytes(repo, "src/a.py", b"new top\r\n" + crlf)
        commit(repo, "insert", "src")
        (rec,) = scan(repo)
        self.assertEqual(rec["class"], "shifted")
        self.assertEqual(rec["old_text"], "line 5\nline 6")
        self.assertEqual(rec["current_text"], "line 5\nline 6")
        self.assertEqual(rec["proposal"], {"new_line": 6})

    def test_crlf_citing_document_finds_spans_and_fenced_references(self):
        """Adversarial where: a CRLF vault document leaves `\\r` on fence lines
        and tokens, which can defeat fence detection or token matching."""
        repo = new_repo(self)
        write(repo, "src/a.py", A_LINES)
        doc = "# Doc\r\n\r\nSpan `src/a.py:3` here.\r\n```\r\nsrc/a.py:4\r\n```\r\nProse src/a.py:5 end.\r\n"
        write_bytes(repo, DOC_PATH, doc.encode())
        commit(repo, "seed", "src", ".compass")
        found = scan(repo)
        self.assertEqual([(r["line"], r["ref_start"]) for r in found], [(3, 3), (5, 4)])
        self.assertTrue(all(r["class"] == "unchanged" for r in found))

    def test_file_without_trailing_newline_cites_its_last_line(self):
        """Adversarial where: splitting a blob that lacks a final newline
        drops or double-counts the last line, turning the last-line citation
        malformed or empty."""
        repo = new_repo(self)
        write_bytes(repo, "src/a.py", b"one\ntwo\nthree")
        write(repo, DOC_PATH, ["# Doc", "", "See `src/a.py:3` and `src/a.py:4`."])
        commit(repo, "seed", "src", ".compass")
        records = {r["ref_start"]: r for r in scan(repo)}
        self.assertEqual(records[3]["class"], "unchanged")
        self.assertEqual(records[3]["old_text"], "three")
        self.assertEqual(records[4]["class"], "malformed")

    def test_blob_larger_than_a_pipe_buffer_is_read_completely(self):
        """Adversarial where: the persistent `cat-file --batch` reader returns
        a short read on a large blob and desynchronises later reads."""
        repo = new_repo(self)
        big = [f"line {n} " + "y" * 80 for n in range(1, 4001)]
        write(repo, "src/big.py", big)
        write(repo, "src/a.py", A_LINES)
        write(repo, DOC_PATH, ["# Doc", "", "`src/big.py:4000` then `src/a.py:5`."])
        commit(repo, "seed", "src", ".compass")
        records = {r["ref_path"]: r for r in scan(repo)}
        self.assertEqual(records["src/big.py"]["old_text"], big[-1])
        self.assertEqual(records["src/a.py"]["old_text"], "line 5")

    def test_unicode_and_spaced_vault_document_names_are_blamed(self):
        """Adversarial where: a citing document whose name has spaces or
        non-ASCII characters is mis-quoted in git output and yields an
        unclassifiable base or a wrong `file` value."""
        repo = new_repo(self)
        write(repo, "src/a.py", A_LINES)
        rel = ".compass/specs/não spec é.md"
        write(repo, rel, ["# Doc", "", "See `src/a.py:5`."])
        base = commit(repo, "seed", "src", ".compass")
        for mode in ("blame", "add"):
            (rec,) = scan(repo, mode)
            self.assertEqual(rec["file"], rel)
            self.assertEqual(rec["base"], base)
            self.assertEqual(rec["class"], "unchanged")

    def test_unicode_cited_path_and_directory_classify(self):
        """Adversarial where: a non-ASCII top-level directory or file name is
        unquoted in the diff header only when quoting is disabled, and its
        byte length differs from its character length."""
        repo = new_repo(self)
        rel = "dados/café ü.py"
        plain = "dados/café.py"
        write(repo, rel, A_LINES)
        write(repo, plain, A_LINES)
        write(repo, DOC_PATH, ["# Doc", "", f"See `{plain}:5`."])
        commit(repo, "seed", "dados", ".compass")
        write(repo, plain, A_LINES[:4] + ["edited"] + A_LINES[5:])
        commit(repo, "edit", "dados")
        (rec,) = scan(repo)
        self.assertEqual(rec["class"], "changed")
        self.assertEqual(rec["current_text"], "edited")


class BaseSelectionTests(unittest.TestCase):
    def test_path_added_after_the_base_commit_is_unclassifiable_without_crash(self):
        """Adversarial where: the cited path does not exist at the base commit
        (citation written before the file); reading the base blob fails and
        must produce a record, not an exception or a bogus unchanged."""
        repo = new_repo(self)
        write(repo, "README.md", ["readme"])
        write(repo, DOC_PATH, ["# Doc", "", "See `src/late.py:2`."])
        base = commit(repo, "seed", "README.md", ".compass")
        write(repo, "src/late.py", A_LINES)
        commit(repo, "add late", "src")
        (rec,) = scan(repo)
        self.assertEqual(rec["class"], "unclassifiable")
        self.assertEqual(rec["base"], base)
        self.assertIsNone(rec["current_text"])

    def test_same_path_cited_at_two_base_commits_classifies_each_separately(self):
        """Adversarial where: refs to one path from lines with different base
        commits share a per-path cache, so the second base reuses the first
        base's diff and both lines get the same class."""
        repo = new_repo(self)
        write(repo, "src/a.py", A_LINES)
        write(repo, DOC_PATH, ["# Doc", "", "Old `src/a.py:5`.", "Other `src/a.py:5`."])
        commit(repo, "seed", "src", ".compass")
        write(repo, "src/a.py", ["new top"] + A_LINES)
        commit(repo, "insert", "src")
        write(repo, DOC_PATH, ["# Doc", "", "Old `src/a.py:5`.", "Other `src/a.py:6`."])
        reanchor = commit(repo, "reanchor", ".compass")
        records = {r["line"]: r for r in scan(repo)}
        self.assertEqual(records[3]["class"], "shifted")
        self.assertEqual(records[3]["proposal"], {"new_line": 6})
        self.assertEqual(records[4]["class"], "unchanged")
        self.assertEqual(records[4]["base"], reanchor)
        self.assertEqual(records[4]["current_text"], "line 5")

    def test_comma_list_ranges_classify_independently_around_one_hunk(self):
        """Adversarial where: one hunk lies inside one range of a comma list
        and between two others; sharing hunk state across list elements would
        give every element the same class."""
        repo = new_repo(self)
        write(repo, "src/a.py", A_LINES)
        write(repo, DOC_PATH, ["# Doc", "", "See `src/a.py:2,5-7,9`."])
        commit(repo, "seed", "src", ".compass")
        write(repo, "src/a.py", A_LINES[:5] + ["edited", "extra"] + A_LINES[6:])
        commit(repo, "edit", "src")
        classes = {(r["ref_start"], r["ref_end"]): r["class"] for r in scan(repo)}
        self.assertEqual(classes, {
            (2, 2): "changed-elsewhere",
            (5, 7): "changed",
            (9, 9): "shifted",
        })

    def test_range_whose_last_line_is_deleted_is_changed_not_shifted(self):
        """Adversarial where: a deletion of the cited range's final line has
        its old-side extent ending exactly at the range end, an off-by-one
        that would class it as above or below the range."""
        repo = new_repo(self)
        write(repo, "src/a.py", A_LINES)
        write(repo, DOC_PATH, ["# Doc", "", "See `src/a.py:5-7`."])
        commit(repo, "seed", "src", ".compass")
        write(repo, "src/a.py", A_LINES[:6] + A_LINES[7:])
        commit(repo, "delete last", "src")
        (rec,) = scan(repo)
        self.assertEqual(rec["class"], "changed")

    def test_range_whose_first_line_is_edited_alongside_an_insertion_above_is_changed(self):
        """Adversarial where: an edit at the range start combined with an
        insertion above must not be reduced to `shifted`."""
        repo = new_repo(self)
        write(repo, "src/a.py", A_LINES)
        write(repo, DOC_PATH, ["# Doc", "", "See `src/a.py:5-7`."])
        commit(repo, "seed", "src", ".compass")
        edited = ["top"] + A_LINES[:4] + ["edited"] + A_LINES[5:]
        write(repo, "src/a.py", edited)
        commit(repo, "edit", "src")
        (rec,) = scan(repo)
        self.assertEqual(rec["class"], "changed")


class UntrackedDocumentTests(unittest.TestCase):
    def test_untracked_document_is_unclassifiable_in_both_modes(self):
        """Adversarial where: blame and add-commit lookup both fail for a file
        git has never seen; failure must degrade to unclassifiable."""
        repo = new_repo(self)
        write(repo, "src/a.py", A_LINES)
        write(repo, "README.md", ["r"])
        commit(repo, "seed", "src", "README.md")
        write(repo, DOC_PATH, ["# Doc", "", "See `src/a.py:5`."])
        for mode in ("blame", "add"):
            (rec,) = scan(repo, mode)
            self.assertEqual(rec["class"], "unclassifiable")
            self.assertIsNone(rec["base"])

    def test_add_base_survives_document_rename(self):
        """Adversarial where: `--follow` log output for a renamed document
        lists commits for old paths; the add base must be the original add."""
        repo = new_repo(self)
        write(repo, "src/a.py", A_LINES)
        write(repo, DOC_PATH, ["# Doc", "", "See `src/a.py:5`."])
        base = commit(repo, "seed", "src", ".compass")
        git(repo, "mv", DOC_PATH, ".compass/specs/renamed.md")
        commit(repo, "rename")
        (rec,) = scan(repo, "add")
        self.assertEqual(rec["base"], base)


if __name__ == "__main__":
    unittest.main()
