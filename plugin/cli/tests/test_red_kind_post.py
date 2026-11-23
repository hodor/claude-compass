"""Edge cases of the red-kind reader (`test_checkpoint._red_kinds`), the
`record --red-evidence` paths around it, ablate's `_collection_red_ids` and
the per-file rerun `_run_after_revert`: pattern shapes the run-output
regexes meet only on real consoles (Windows separators, bracketed
parameters, shared file-name prefixes, byte-order marks, CRLF), checkpoint
JSON shapes ablate must survive, and the rerun merge rule."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ablatelib  # noqa: E402
from commands import test_checkpoint  # noqa: E402
from tests.test_ablate_unproven import (  # noqa: E402
    checkpoint,
    collection_evidence,
    new_module_repo,
)
from tests.test_ablatelib import git  # noqa: E402

BACKSLASH = chr(92)


def file_record(path, *ids):
    return {"path": path, "ids": [i if isinstance(i, tuple) else (None, i) for i in ids]}


def kinds(text, *records):
    return test_checkpoint._red_kinds(text, list(records))


# --------------------------------------------------------------------------
# _red_kinds pattern edges
# --------------------------------------------------------------------------


def test_windows_backslash_paths_in_collection_heading_and_summary_mark_collection():
    """Adversarial where: pytest on Windows prints `ERROR collecting
    tests\\test_x.py` and `ERROR tests\\test_x.py`; a reader that compares
    separators literally leaves the file's tests `absent`, so a task's
    import-only reds read as defects on revert."""
    heading = f"_____ ERROR collecting tests{BACKSLASH}test_x.py _____\n"
    summary = f"ERROR tests{BACKSLASH}test_x.py\n"
    record = file_record("tests/test_x.py", "test_a")
    assert kinds(heading, record) == {"tests/test_x.py::test_a": "collection"}
    assert kinds(summary, record) == {"tests/test_x.py::test_a": "collection"}


def test_collection_summary_line_with_trailing_message_marks_collection():
    """Adversarial where: newer pytest appends ` - <message>` to the
    short-summary `ERROR <path>` line; a pattern anchored on the bare path
    misses it when the heading is absent (`-q` output), leaving `absent`."""
    text = "ERROR tests/test_x.py - ModuleNotFoundError: No module named 'newmod'\n"
    assert kinds(text, file_record("tests/test_x.py", "test_a")) == {
        "tests/test_x.py::test_a": "collection"}


def test_collection_error_in_a_file_with_a_longer_name_does_not_taint_its_prefix_sibling():
    """Adversarial where: `tests/test_ab.py` fails to import while the
    checkpointed `tests/test_a.py` holds a same-named test that was never in
    the run; a suffix or substring path comparison marks the sibling
    `collection`, hiding a defect as unproven."""
    text = "ERROR tests/test_ab.py\n"
    got = kinds(text, file_record("tests/test_a.py", "test_same"),
                file_record("tests/test_ab.py", "test_same"))
    assert got == {
        "tests/test_a.py::test_same": "absent",
        "tests/test_ab.py::test_same": "collection",
    }


def test_status_line_for_a_longer_file_name_is_not_credited_to_its_prefix_sibling():
    """Adversarial where: `tests/xtest_a.py::test_a PASSED` read as the
    result of `tests/test_a.py::test_a` because one path ends with the
    other; the checkpointed test would be called `passed` (never red) on
    another file's evidence."""
    text = "tests/xtest_a.py::test_a PASSED [100%]\n"
    assert kinds(text, file_record("tests/test_a.py", "test_a")) == {
        "tests/test_a.py::test_a": "absent"}


def test_collection_error_for_a_file_that_is_not_checkpointed_leaves_ids_absent():
    """Adversarial where: any `ERROR collecting` line in the run marks every
    checkpointed test `collection`; a broken unrelated file must not turn a
    test that simply never ran into an unproven one."""
    text = "ERROR tests/test_other.py\n"
    assert kinds(text, file_record("tests/test_a.py", "test_a")) == {
        "tests/test_a.py::test_a": "absent"}


def test_parametrized_ids_with_brackets_and_spaces_fold_to_fail_when_any_case_failed():
    """Adversarial where: a parameter id such as `[x y]` or `[a]b]` splits the
    node id wrongly or drops the line, so a failing case is lost and the test
    reads `passed` or `absent`."""
    text = (
        "tests/test_a.py::test_a[x y] PASSED [ 33%]\n"
        "tests/test_a.py::test_a[a]b] FAILED [ 66%]\n"
        "tests/test_a.py::test_a[ok] PASSED [100%]\n"
    )
    assert kinds(text, file_record("tests/test_a.py", "test_a")) == {
        "tests/test_a.py::test_a": "fail"}


def test_parametrized_ids_that_all_passed_are_passed_not_collection():
    """Adversarial where: a parametrized test printed several times folds to
    its first status instead of the all-cases result."""
    text = ("tests/test_a.py::test_a[1] PASSED [ 50%]\n"
            "tests/test_a.py::test_a[2] PASSED [100%]\n"
            "ERROR tests/test_a.py\n")
    assert kinds(text, file_record("tests/test_a.py", "test_a")) == {
        "tests/test_a.py::test_a": "passed"}


def test_failing_status_outranks_a_collection_error_and_a_pass_for_the_same_id():
    """Adversarial where: the precedence between `fail`, `passed` and
    `collection` is order-dependent; a test that both failed and was later
    seen under a broken file must stay `fail` (its red was its own)."""
    text = ("tests/test_a.py::test_a FAILED [ 50%]\n"
            "tests/test_a.py::test_a PASSED [100%]\n"
            "ERROR tests/test_a.py\n")
    assert kinds(text, file_record("tests/test_a.py", "test_a")) == {
        "tests/test_a.py::test_a": "fail"}


def test_setup_error_summary_line_is_error_not_collection():
    """Adversarial where: the collection summary pattern (`ERROR <path>`)
    also fires on `ERROR tests/test_a.py::test_a - boom`, relabelling a test's
    own setup error as an import failure."""
    text = "ERROR tests/test_a.py::test_a - RuntimeError: boom\n"
    assert kinds(text, file_record("tests/test_a.py", "test_a")) == {
        "tests/test_a.py::test_a": "error"}


def test_same_test_name_in_class_and_at_module_level_gets_separate_kinds():
    """Adversarial where: the class segment is dropped while matching, so a
    failing `TestC.test_a` also marks the module-level `test_a` as failed."""
    text = "tests/test_a.py::TestC::test_a FAILED [100%]\n"
    got = kinds(text, file_record("tests/test_a.py", "test_a", ("TestC", "test_a")))
    assert got == {
        "tests/test_a.py::test_a": "absent",
        "tests/test_a.py::TestC::test_a": "fail",
    }


def test_skipped_and_xfail_lines_are_absent_not_passed():
    """Adversarial where: any printed status is read as green, so a skipped
    or xfail test counts as `passed` and is never red evidence."""
    text = ("tests/test_a.py::test_s SKIPPED (why) [ 50%]\n"
            "tests/test_a.py::test_x XFAIL [100%]\n")
    assert kinds(text, file_record("tests/test_a.py", "test_s", "test_x")) == {
        "tests/test_a.py::test_s": "absent",
        "tests/test_a.py::test_x": "absent",
    }


def test_paths_printed_relative_to_a_different_root_still_match_the_recorded_file():
    """Adversarial where: pytest run from `cli/` prints `tests/test_a.py`
    while the checkpoint records `cli/tests/test_a.py` (and the reverse);
    an exact comparison leaves every id `absent`."""
    text = "tests/test_a.py::test_a FAILED [100%]\n"
    assert kinds(text, file_record("cli/tests/test_a.py", "test_a")) == {
        "cli/tests/test_a.py::test_a": "fail"}
    text = "cli/tests/test_a.py::test_a FAILED [100%]\n"
    assert kinds(text, file_record("tests/test_a.py", "test_a")) == {
        "tests/test_a.py::test_a": "fail"}


def test_summary_only_run_output_with_status_first_lines_is_read():
    """Adversarial where: `-rA` short-summary lines put the status first;
    a reader of `-v` lines only returns `absent` for a run saved that way."""
    text = ("FAILED tests/test_a.py::test_f - assert 1 == 2\n"
            "PASSED tests/test_a.py::test_p\n")
    assert kinds(text, file_record("tests/test_a.py", "test_f", "test_p")) == {
        "tests/test_a.py::test_f": "fail",
        "tests/test_a.py::test_p": "passed",
    }


def test_unittest_import_failure_names_the_dotted_module_and_only_that_module():
    """Adversarial where: the unittest import-failure module (`tests.test_ut`)
    is matched against file paths by substring; a same-named module in
    another package, or a longer module name, must stay `absent`."""
    text = "ImportError: Failed to import test module: other.test_ut\n"
    assert kinds(text, file_record("tests/test_ut.py", ("G", "test_m"))) == {
        "tests/test_ut.py::G::test_m": "absent"}
    text = "ImportError: Failed to import test module: tests.test_ut\n"
    got = kinds(text, file_record("tests/test_ut.py", ("G", "test_m")),
                file_record("tests/test_ut2.py", ("G", "test_m")))
    assert got == {
        "tests/test_ut.py::G::test_m": "collection",
        "tests/test_ut2.py::G::test_m": "absent",
    }


def test_unittest_fail_line_for_a_test_in_a_broken_looking_module_is_fail():
    """Adversarial where: a unittest FAIL line is outranked by an import
    failure line naming the same module elsewhere in the output."""
    text = ("test_m (tests.test_ut.G.test_m) ... FAIL\n"
            "ImportError: Failed to import test module: tests.test_ut\n")
    assert kinds(text, file_record("tests/test_ut.py", ("G", "test_m"))) == {
        "tests/test_ut.py::G::test_m": "fail"}


def test_empty_evidence_marks_every_id_absent():
    """Adversarial where: an empty saved run raises or marks ids `collection`."""
    assert kinds("", file_record("tests/test_a.py", "test_a")) == {
        "tests/test_a.py::test_a": "absent"}


@pytest.mark.xfail(strict=True, reason=(
    "_red_kinds reads pytest and unittest lines only; `not ok` TAP lines that "
    "_parse_run_evidence accepts leave the failing test `absent`"))
def test_tap_failure_line_is_a_fail_kind():
    """Adversarial where: `record --red-evidence` accepts `node --test` TAP
    output everywhere else, but a TAP `not ok` line is dropped here, so a
    genuinely failing test is stored as `absent`."""
    text = "not ok 1 - test_a\nok 2 - test_b\n"
    assert kinds(text, file_record("t.test.js", "test_a", "test_b")) == {
        "t.test.js::test_a": "fail", "t.test.js::test_b": "passed"}


# --------------------------------------------------------------------------
# record --red-evidence end to end
# --------------------------------------------------------------------------


def stored_kinds(repo, task="TASK-402"):
    path = repo / ".compass" / "tmp" / "test-checkpoints" / f"{task}.json"
    return json.loads(path.read_text(encoding="utf-8")).get("red_kinds")


def record_bytes(repo, tmp_path, monkeypatch, capsys, data, extra=None, files=None):
    (repo / ".compass").mkdir(exist_ok=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    evidence = tmp_path / "ev.bin"
    evidence.write_bytes(data)
    argv = ["record", "TASK-402", *(files or ["tests/test_newmod.py"]),
            "--commit", git(repo, "rev-parse", "HEAD^2"),
            "--red-evidence", str(evidence), *(extra or [])]
    code = test_checkpoint.run(argv)
    out = capsys.readouterr()
    return code, out


def test_utf8_bom_and_crlf_evidence_is_read_like_plain_evidence(tmp_path, monkeypatch, capsys):
    """Adversarial where: a console-redirected evidence file starts with a
    UTF-8 byte-order mark and ends lines with CRLF; the BOM glued to the
    first line or a trailing CR defeats the anchored status patterns and
    every id is stored `absent`."""
    repo = new_module_repo(tmp_path)
    text = collection_evidence("tests/test_newmod.py").replace("\n", "\r\n")
    code, out = record_bytes(repo, tmp_path, monkeypatch, capsys,
                             b"\xef\xbb\xbf" + text.encode("utf-8"))
    assert code == 0, out.err
    assert stored_kinds(repo) == {
        "tests/test_newmod.py::test_thing": "collection",
        "tests/test_newmod.py::TestNew::test_in_class": "collection",
    }


def test_utf16_evidence_with_bom_is_read(tmp_path, monkeypatch, capsys):
    """Adversarial where: a PowerShell `>` redirect writes UTF-16LE; decoded
    as bytes-as-text no pattern matches and the record stores `absent`."""
    repo = new_module_repo(tmp_path)
    data = collection_evidence("tests/test_newmod.py").encode("utf-16")
    code, out = record_bytes(repo, tmp_path, monkeypatch, capsys, data)
    assert code == 0, out.err
    assert set(stored_kinds(repo).values()) == {"collection"}


def test_empty_evidence_file_records_with_every_kind_absent(tmp_path, monkeypatch, capsys):
    """Adversarial where: a zero-byte evidence file aborts the record or is
    treated as unreadable (no `red_kinds` key at all)."""
    repo = new_module_repo(tmp_path)
    code, out = record_bytes(repo, tmp_path, monkeypatch, capsys, b"")
    assert code == 0, out.err
    assert set(stored_kinds(repo).values()) == {"absent"}


def test_missing_evidence_file_warns_and_still_records_without_kinds(tmp_path, monkeypatch, capsys):
    """Adversarial where: a mistyped `--red-evidence` path fails the whole
    record instead of warning, losing the checkpoint."""
    repo = new_module_repo(tmp_path)
    (repo / ".compass").mkdir(exist_ok=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    code = test_checkpoint.run([
        "record", "TASK-402", "tests/test_newmod.py",
        "--commit", git(repo, "rev-parse", "HEAD^2"),
        "--red-evidence", str(tmp_path / "no-such-file.txt")])
    out = capsys.readouterr()
    assert code == 0, out.err
    assert "unreadable" in out.err
    assert stored_kinds(repo) is None


def test_not_required_record_ignores_red_evidence_and_stores_no_kinds(tmp_path, monkeypatch, capsys):
    """Adversarial where: the red-kind step runs on the `--not-required`
    path and crashes on its empty file list, or writes kinds onto a record
    that checkpoints nothing."""
    repo = new_module_repo(tmp_path)
    (repo / ".compass").mkdir(exist_ok=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    evidence = tmp_path / "ev.txt"
    evidence.write_text(collection_evidence("tests/test_newmod.py"), encoding="utf-8")
    code = test_checkpoint.run(["record", "TASK-402", "--not-required",
                                "--red-evidence", str(evidence)])
    out = capsys.readouterr()
    assert code == 0, out.err
    assert stored_kinds(repo) is None


def test_superseding_record_replaces_kinds_with_its_own_evidence(tmp_path, monkeypatch, capsys):
    """Adversarial where: a `--supersede` record keeps the prior version's
    `red_kinds` (stale unproven labels) or drops them when new evidence is
    given."""
    repo = new_module_repo(tmp_path)
    checkpoint(repo, tmp_path, monkeypatch, capsys, ["tests/test_newmod.py"],
               collection_evidence("tests/test_newmod.py"))
    assert set(stored_kinds(repo).values()) == {"collection"}
    evidence = tmp_path / "second.txt"
    evidence.write_text(
        "tests/test_newmod.py::test_thing FAILED [ 50%]\n"
        "tests/test_newmod.py::TestNew::test_in_class FAILED [100%]\n", encoding="utf-8")
    code = test_checkpoint.run([
        "record", "TASK-402", "tests/test_newmod.py",
        "--commit", git(repo, "rev-parse", "HEAD^2"),
        "--supersede", "TASK-402", "--reason", "rerun",
        "--red-evidence", str(evidence)])
    out = capsys.readouterr()
    assert code == 0, out.err
    assert set(stored_kinds(repo).values()) == {"fail"}


def test_superseding_record_without_evidence_does_not_inherit_prior_kinds(tmp_path, monkeypatch, capsys):
    """Adversarial where: a superseding record that names no evidence carries
    the previous version's `collection` kinds, so ablate keeps calling tests
    unproven on evidence the new version never had."""
    repo = new_module_repo(tmp_path)
    checkpoint(repo, tmp_path, monkeypatch, capsys, ["tests/test_newmod.py"],
               collection_evidence("tests/test_newmod.py"))
    code = test_checkpoint.run([
        "record", "TASK-402", "tests/test_newmod.py",
        "--commit", git(repo, "rev-parse", "HEAD^2"),
        "--supersede", "TASK-402", "--reason", "rerun"])
    out = capsys.readouterr()
    assert code == 0, out.err
    assert stored_kinds(repo) is None


# --------------------------------------------------------------------------
# ablatelib helpers
# --------------------------------------------------------------------------


def write_checkpoint(repo, payload, task="TASK-402"):
    folder = repo / ".compass" / "tmp" / "test-checkpoints"
    folder.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    (folder / f"{task}.json").write_text(text, encoding="utf-8")


def test_collection_red_ids_skips_ids_missing_from_red_kinds(tmp_path):
    """Adversarial where: an id absent from `red_kinds` (a test added to the
    file after the evidence was saved) is treated as collection-red, hiding
    a real unflipped test."""
    write_checkpoint(tmp_path, {"red_kinds": {
        "tests/test_a.py::test_listed": "collection"}})
    got = ablatelib._collection_red_ids(tmp_path, "TASK-402")
    assert got == {"test_listed"}
    assert "test_unlisted" not in got


def test_collection_red_ids_requires_every_file_holding_the_name_to_be_collection(tmp_path):
    """Adversarial where: one test name in two checkpointed files, collection
    in one and `fail` in the other; counting the name as collection-red
    would excuse the file whose red was genuine."""
    write_checkpoint(tmp_path, {"red_kinds": {
        "tests/test_a.py::test_dup": "collection",
        "tests/test_b.py::test_dup": "fail",
        "tests/test_a.py::TestC::test_m": "collection",
        "tests/test_b.py::TestC::test_m": "collection",
    }})
    assert ablatelib._collection_red_ids(tmp_path, "TASK-402") == {"TestC.test_m"}


def test_collection_red_ids_ids_use_the_class_and_name_of_the_last_two_segments(tmp_path):
    """Adversarial where: a module-level key `path::name` and a class key
    `path::Class::name` yield the wrong id shape, so ablate's `Class.name`
    ids never match."""
    write_checkpoint(tmp_path, {"red_kinds": {
        "tests/test_a.py::test_mod": "collection",
        "tests/test_a.py::TestC::test_m": "collection",
    }})
    assert ablatelib._collection_red_ids(tmp_path, "TASK-402") == {"test_mod", "TestC.test_m"}


@pytest.mark.parametrize("payload", [
    "{not json",
    "[]",
    {"red_kinds": []},
    {"red_kinds": "collection"},
    {"red_kinds": None},
    {"red_kinds": {"tests/test_a.py::test_a": ["collection"]}},
])
def test_collection_red_ids_survives_malformed_checkpoint_shapes(tmp_path, payload):
    """Adversarial where: a hand-edited or damaged checkpoint raises out of
    ablate (AttributeError on a list, TypeError on an unhashable kind)
    instead of reporting no unproven tests."""
    write_checkpoint(tmp_path, payload)
    assert ablatelib._collection_red_ids(tmp_path, "TASK-402") == set()


def test_collection_red_ids_without_a_checkpoint_file_is_empty(tmp_path):
    """Adversarial where: a task with no checkpoint raises FileNotFoundError."""
    assert ablatelib._collection_red_ids(tmp_path, "TASK-999") == set()


class FakeRuns:
    """Stands in for `ablatelib._run_tests`, answering by the selected files."""

    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = []

    def __call__(self, worktree, cmd, selected):
        self.calls.append(tuple(selected))
        return self.outputs[tuple(selected)]


def line(path, name, status="PASSED"):
    return f"{path}::{name} {status} [100%]\n"


def test_rerun_with_one_selected_file_runs_once_even_when_ids_are_missing(monkeypatch):
    """Adversarial where: the per-file fallback loops over a single file and
    reruns it, doubling the revert run for a plain collection error."""
    fake = FakeRuns({("tests/a.py",): line("tests/a.py", "test_x")})
    monkeypatch.setattr(ablatelib, "_run_tests", fake)
    got = ablatelib._run_after_revert("wt", "cmd", ["tests/a.py"], {"test_x", "test_gone"})
    assert got == {"test_x": "ok"}
    assert fake.calls == [("tests/a.py",)]


def test_rerun_is_skipped_when_the_combined_run_reports_every_expected_id(monkeypatch):
    """Adversarial where: the fallback fires on a complete combined run and
    costs one run per file on every ablation."""
    both = ("tests/a.py", "tests/b.py")
    fake = FakeRuns({both: line("tests/a.py", "test_a") + line("tests/b.py", "test_b", "FAILED")})
    monkeypatch.setattr(ablatelib, "_run_tests", fake)
    got = ablatelib._run_after_revert("wt", "cmd", list(both), {"test_a", "test_b"})
    assert got == {"test_a": "ok", "test_b": "fail"}
    assert fake.calls == [both]


@pytest.mark.parametrize("order", [("tests/a.py", "tests/b.py"), ("tests/b.py", "tests/a.py")])
def test_per_file_rerun_merge_lets_a_failing_status_outrank_ok_in_either_order(monkeypatch, order):
    """Adversarial where: the merge keeps the first-seen status for a test
    name defined in two files, so a failing `test_dup` is masked by (or
    masks) the other file's pass depending on selection order."""
    both = order
    outputs = {
        both: "ERROR collecting tests/c.py\n",
        ("tests/a.py",): line("tests/a.py", "test_dup") + line("tests/a.py", "test_a"),
        ("tests/b.py",): line("tests/b.py", "test_dup", "FAILED"),
    }
    fake = FakeRuns(outputs)
    monkeypatch.setattr(ablatelib, "_run_tests", fake)
    got = ablatelib._run_after_revert("wt", "cmd", list(both), {"test_dup", "test_a"})
    assert got == {"test_dup": "fail", "test_a": "ok"}
    assert sorted(fake.calls[1:]) == [("tests/a.py",), ("tests/b.py",)]


def test_per_file_rerun_leaves_a_still_broken_file_ids_missing(monkeypatch):
    """Adversarial where: the fallback invents a status for ids of a file
    that still cannot be imported, so ablate stops reporting its tests as
    collection errors."""
    both = ("tests/a.py", "tests/b.py")
    fake = FakeRuns({
        both: "ERROR collecting tests/b.py\n",
        ("tests/a.py",): line("tests/a.py", "test_a"),
        ("tests/b.py",): "ERROR collecting tests/b.py\n",
    })
    monkeypatch.setattr(ablatelib, "_run_tests", fake)
    got = ablatelib._run_after_revert("wt", "cmd", list(both), {"test_a", "test_b"})
    assert got == {"test_a": "ok"}
