"""Tests for `evidencelib`, the library behind `compass evidence`.

Adversarial themes: a record that lies about the run (exit code, sha, dirty
paths, output hash), output truncated or reordered on its way to the `.out`
file, a slug or task id that escapes `.compass/evidence/`, a rerun that
compares the wrong thing (verdict lines not last, wrong prefix), a rerun that
mutates the record or leaves its scratch worktree behind.

Interface pinned here (all paths are `pathlib.Path`, `cwd` is the directory the
checked command runs in; the repo root is `git rev-parse --show-toplevel` of
`cwd`):

- `EvidenceError`: raised for every refused request (bad slug or task id, not
  inside a git repo, unreadable record).
- `validate_slug(slug)`: raises `EvidenceError` or returns None.
- `verdict_line(output_text)`: the last line when it starts `REACH:`,
  `ABLATE:` or `REQ:` (line ending removed), else None.
- `run_check(cwd, task, slug, argv)` -> `(record, record_path)`; writes
  `<root>/.compass/evidence/<task>/<slug>.json` and `<slug>.out`.
- `rerun(record_path)` -> dict with `verdict` ("match" or "mismatch"),
  `exit_code`, `recorded_exit_code`, `last_line`, `recorded_last_line` (the two
  verdict lines, None when absent) and `dirty_warning` (bool).
- `list_records(cwd, task)` -> list of record dicts sorted by `check`; an
  unreadable record file is `{"check": <slug>, "unreadable": True}`.

Record keys: task, check, argv, cwd, sha, tree ("clean" or "dirty"),
dirty_paths, exit_code, started, ended, python, git, output_sha256."""

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import evidencelib  # noqa: E402

PY = sys.executable


def git(repo, *args):
    done = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / ".compass").mkdir(parents=True)
    (root / "sub").mkdir()
    (root / ".compass" / "index.md").write_text("# index\n", encoding="utf-8")
    (root / "value.txt").write_text("3", encoding="utf-8")
    (root / "sub" / "f.txt").write_text("f", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "config", "core.autocrlf", "false")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "base")
    return root


def py(code, *rest):
    return [PY, "-c", code, *rest]


def record_files(root, task, slug):
    base = root / ".compass" / "evidence" / task
    return base / f"{slug}.json", base / f"{slug}.out"


def read_record(path):
    return json.loads(path.read_text(encoding="utf-8"))


def commit_value(root, text):
    (root / "value.txt").write_text(text, encoding="utf-8")
    git(root, "commit", "-q", "-am", "change value")


def test_run_check_record_states_what_ran(repo):
    """Adversarial where: a record that misreports the run (exit code 0
    instead of the real code, a stale sha, a missing field, an output hash
    over something other than the stored file) makes the evidence worthless."""
    cases = {"passing": 0, "failing": 7}
    for slug, code in cases.items():
        argv = py(f"import sys; print('hi'); sys.exit({code})")
        record, path = evidencelib.run_check(repo, "TASK-403", slug, argv)
        json_path, out_path = record_files(repo, "TASK-403", slug)
        assert path == json_path
        assert read_record(json_path) == record
        assert record["exit_code"] == code, slug
        assert record["argv"] == argv, slug
        assert record["task"] == "TASK-403" and record["check"] == slug
        assert record["sha"] == git(repo, "rev-parse", "HEAD")
        assert record["cwd"] == "."
        assert record["tree"] == "clean" and record["dirty_paths"] == []
        assert record["python"] == platform.python_version()
        assert record["git"] == git(repo, "--version")
        started = datetime.fromisoformat(record["started"])
        ended = datetime.fromisoformat(record["ended"])
        assert started <= ended
        out = out_path.read_bytes()
        assert out.replace(b"\r\n", b"\n") == b"hi\n"
        assert record["output_sha256"] == hashlib.sha256(out).hexdigest()


def test_run_check_keeps_combined_output_whole_and_in_order(repo):
    """Adversarial where: output truncated to a tail, stdout and stderr
    concatenated stream-after-stream instead of interleaved, non-UTF-8 bytes
    crashing the capture, or empty output leaving no .out file."""
    many = "for i in range(10000): print('row', i)"
    interleave = (
        "import sys\n"
        "print('out1'); sys.stdout.flush()\n"
        "print('err1', file=sys.stderr); sys.stderr.flush()\n"
        "print('out2'); sys.stdout.flush()\n"
    )
    raw = (
        "import sys; sys.stdout.buffer.write(bytes([255, 254, 0, 111, 107]));"
        " sys.stdout.flush()"
    )
    cases = {
        "ten-thousand": (many, [f"row {i}" for i in range(10000)]),
        "interleaved": (interleave, ["out1", "err1", "out2"]),
    }
    for slug, (code, expected) in cases.items():
        record, _ = evidencelib.run_check(repo, "TASK-403", slug, py(code))
        _, out_path = record_files(repo, "TASK-403", slug)
        stored = out_path.read_bytes()
        assert stored.decode("utf-8").splitlines() == expected, slug
        assert record["output_sha256"] == hashlib.sha256(stored).hexdigest(), slug
    evidencelib.run_check(repo, "TASK-403", "binary", py(raw))
    _, out_path = record_files(repo, "TASK-403", "binary")
    assert out_path.read_bytes() == bytes([255, 254, 0, 111, 107])
    record, _ = evidencelib.run_check(repo, "TASK-403", "silent", py("pass"))
    _, out_path = record_files(repo, "TASK-403", "silent")
    assert out_path.read_bytes() == b""
    assert record["output_sha256"] == hashlib.sha256(b"").hexdigest()


def test_run_check_rerun_of_same_slug_replaces_the_record(repo):
    """Adversarial where: a second run of the same check appending to the old
    .out file or keeping the old exit code, so the record describes two runs."""
    evidencelib.run_check(
        repo, "TASK-403", "same",
        py("print('long long long'); import sys; sys.exit(4)"),
    )
    record, _ = evidencelib.run_check(repo, "TASK-403", "same", py("print('x')"))
    json_path, out_path = record_files(repo, "TASK-403", "same")
    assert read_record(json_path)["exit_code"] == 0 == record["exit_code"]
    assert out_path.read_bytes().replace(b"\r\n", b"\n") == b"x\n"


def test_run_check_records_subdirectory_cwd_and_runs_there(repo):
    """Adversarial where: the cwd recorded absolute or with backslashes, the
    command run from the repo root instead of the invoking directory, or the
    evidence written under the subdirectory instead of the repo root."""
    code = (
        "import os, sys; "
        "sys.exit(0 if os.path.basename(os.getcwd()) == 'sub' else 9)"
    )
    record, path = evidencelib.run_check(repo / "sub", "TASK-403", "insub", py(code))
    assert record["exit_code"] == 0
    assert record["cwd"] == "sub"
    assert path == repo / ".compass" / "evidence" / "TASK-403" / "insub.json"
    assert not (repo / "sub" / ".compass").exists()


def test_run_check_tree_state_lists_every_dirty_path(repo):
    """Adversarial where: dirty paths missed (untracked only, staged only),
    a path with a space quoted by git porcelain, evidence records of earlier
    checks making the next check look dirty, or a clean tree called dirty."""
    evidencelib.run_check(repo, "TASK-403", "first", py("pass"))
    record, _ = evidencelib.run_check(repo, "TASK-403", "second", py("pass"))
    assert record["tree"] == "clean" and record["dirty_paths"] == []

    (repo / "value.txt").write_text("9", encoding="utf-8")
    (repo / "new file.txt").write_text("u", encoding="utf-8")
    (repo / "sub" / "staged.txt").write_text("s", encoding="utf-8")
    git(repo, "add", "sub/staged.txt")
    record, _ = evidencelib.run_check(repo, "TASK-403", "third", py("pass"))
    assert record["tree"] == "dirty"
    assert sorted(record["dirty_paths"]) == [
        "new file.txt", "sub/staged.txt", "value.txt",
    ]


@pytest.mark.parametrize(
    "slug",
    ["a/b", "a\\b", "..", ".", "", "../escape", "x/../../y", "/abs"],
)
def test_run_check_rejects_slug_that_could_leave_the_evidence_folder(
    repo, tmp_path, slug
):
    """Adversarial where: a slug with a path separator or dot segment writing
    the record outside `.compass/evidence/<task>/`, or running the command
    before rejecting."""
    marker = tmp_path / "ran.txt"
    argv = py("import sys; open(sys.argv[1], 'w').write('x')", str(marker))
    with pytest.raises(evidencelib.EvidenceError):
        evidencelib.run_check(repo, "TASK-403", slug, argv)
    assert not marker.exists()
    assert not (repo / ".compass" / "evidence").exists()
    assert not (tmp_path / "escape.json").exists()
    assert not (repo / "escape.json").exists()


@pytest.mark.parametrize("slug", ["reach", "req-D-01", "ablate", "req-O-1.v2", "a_b"])
def test_validate_slug_accepts_the_check_names_the_validator_uses(slug):
    """Adversarial where: an over-strict slug rule refusing the names the
    validator passes (`reach`, `ablate`, `req-<id>`)."""
    assert evidencelib.validate_slug(slug) is None


@pytest.mark.parametrize("task", ["TASK-403/../x", "..", "", "../TASK-1", "TASK-1\\x"])
def test_run_check_rejects_task_that_could_leave_the_evidence_folder(repo, task):
    """Adversarial where: the task id used as a path component without the
    same separator check as the slug."""
    with pytest.raises(evidencelib.EvidenceError):
        evidencelib.run_check(repo, task, "ok", py("pass"))
    assert not (repo / ".compass" / "evidence").exists()


def test_run_check_outside_a_git_repo_is_refused_without_running(tmp_path):
    """Adversarial where: running the command and writing a record that has no
    sha to rerun at."""
    outside = tmp_path / "plain"
    outside.mkdir()
    marker = tmp_path / "ran.txt"
    argv = py("import sys; open(sys.argv[1], 'w').write('x')", str(marker))
    with pytest.raises(evidencelib.EvidenceError):
        evidencelib.run_check(outside, "TASK-403", "x", argv)
    assert not marker.exists()


@pytest.mark.parametrize(
    "text,expected",
    [
        ("x\nREACH: PASS\n", "REACH: PASS"),
        ("ABLATE: FINDING", "ABLATE: FINDING"),
        ("REQ: met\r\n", "REQ: met"),
        ("REACH:", "REACH:"),
        ("REACH: PASS\nmore\n", None),
        ("reach: pass\n", None),
        (" REACH: PASS\n", None),
        ("XREACH: PASS\n", None),
        ("REACHED: yes\n", None),
        ("PASS\n", None),
        ("", None),
    ],
)
def test_verdict_line_is_the_last_line_with_a_known_prefix(text, expected):
    """Adversarial where: a verdict line found anywhere but last, matched
    case-insensitively or by substring, or CRLF left on the line so two equal
    verdicts compare unequal."""
    assert evidencelib.verdict_line(text) == expected


def test_rerun_runs_at_the_recorded_sha_not_the_current_tree(repo):
    """Adversarial where: a rerun in the live working tree, so upstream change
    after the record turns a true match into a mismatch (or hides one)."""
    argv = py("import sys; sys.exit(int(open('value.txt').read()))")
    record, path = evidencelib.run_check(repo, "TASK-403", "atsha", argv)
    assert record["exit_code"] == 3
    commit_value(repo, "0")
    result = evidencelib.rerun(path)
    assert result["verdict"] == "match"
    assert result["exit_code"] == 3 == result["recorded_exit_code"]


def test_rerun_runs_in_the_recorded_subdirectory_of_the_worktree(repo):
    """Adversarial where: the rerun starting at the worktree root instead of
    the recorded cwd, or at the live repo's subdirectory."""
    code = (
        "import os, sys; sys.exit(0 if os.path.basename(os.getcwd()) == 'sub'"
        " and os.path.exists('f.txt') else 9)"
    )
    _, path = evidencelib.run_check(repo / "sub", "TASK-403", "insub", py(code))
    result = evidencelib.rerun(path)
    assert result["verdict"] == "match" and result["exit_code"] == 0


def test_rerun_leaves_record_untouched_and_worktree_removed(repo):
    """Adversarial where: a rerun rewriting the record or its output, or
    leaving `.claude/worktrees/evidence-<slug>` registered or on disk, on both
    a matching and a failing command."""
    for slug, code in {"clean": "pass", "failing": "import sys; sys.exit(5)"}.items():
        _, path = evidencelib.run_check(repo, "TASK-403", slug, py(code))
        _, out_path = record_files(repo, "TASK-403", slug)
        before = (path.read_bytes(), out_path.read_bytes())
        evidencelib.rerun(path)
        assert (path.read_bytes(), out_path.read_bytes()) == before, slug
        assert not (repo / ".claude" / "worktrees" / f"evidence-{slug}").exists(), slug
    listing = git(repo, "worktree", "list", "--porcelain")
    assert listing.count("worktree ") == 1


@pytest.mark.parametrize(
    "prefix,recorded,rerun_value,expected",
    [
        ("REACH", "PASS", "FINDING", "mismatch"),
        ("ABLATE", "PASS", "FINDING", "mismatch"),
        ("REQ", "met", "missing", "mismatch"),
        ("REACH", "PASS", "PASS", "match"),
    ],
)
def test_rerun_compares_a_trailing_verdict_line(
    repo, tmp_path, prefix, recorded, rerun_value, expected
):
    """Adversarial where: the verdict line ignored (match reported though it
    changed), or compared as different when the text is equal."""
    flag = tmp_path / "flag.txt"
    flag.write_text(recorded, encoding="utf-8")
    code = (
        f"import sys; print('noise'); "
        f"print('{prefix}: ' + open(sys.argv[1]).read())"
    )
    _, path = evidencelib.run_check(repo, "TASK-403", "verdict", py(code, str(flag)))
    flag.write_text(rerun_value, encoding="utf-8")
    result = evidencelib.rerun(path)
    assert result["verdict"] == expected
    assert result["recorded_last_line"] == f"{prefix}: {recorded}"
    assert result["last_line"] == f"{prefix}: {rerun_value}"


def test_rerun_ignores_output_that_is_not_a_trailing_verdict(repo, tmp_path):
    """Adversarial where: whole-output or any-last-line comparison, so a
    timestamp-like last line, or a REACH line that is not last, turns a match
    into a mismatch."""
    flag = tmp_path / "flag.txt"
    cases = {
        "last-line-noise": "import sys; print('stamp ' + open(sys.argv[1]).read())",
        "verdict-not-last": (
            "import sys; print('REACH: ' + open(sys.argv[1]).read()); print('done')"
        ),
        "wrong-case": "import sys; print('reach: ' + open(sys.argv[1]).read())",
    }
    for slug, code in cases.items():
        flag.write_text("one", encoding="utf-8")
        _, path = evidencelib.run_check(repo, "TASK-403", slug, py(code, str(flag)))
        flag.write_text("two", encoding="utf-8")
        result = evidencelib.rerun(path)
        assert result["verdict"] == "match", slug


@pytest.mark.parametrize(
    "recorded,rerun_code,expected",
    [("0", 3, "mismatch"), ("3", 0, "mismatch"), ("3", 3, "match"), ("3", 4, "mismatch")],
)
def test_rerun_compares_exit_codes(repo, tmp_path, recorded, rerun_code, expected):
    """Adversarial where: zero versus nonzero treated as the only distinction,
    so 3 versus 4 (both failing) reads as a match."""
    flag = tmp_path / "flag.txt"
    flag.write_text(recorded, encoding="utf-8")
    code = "import sys; sys.exit(int(open(sys.argv[1]).read()))"
    _, path = evidencelib.run_check(repo, "TASK-403", "codes", py(code, str(flag)))
    flag.write_text(str(rerun_code), encoding="utf-8")
    result = evidencelib.rerun(path)
    assert result["verdict"] == expected
    assert result["recorded_exit_code"] == int(recorded)
    assert result["exit_code"] == rerun_code


def test_rerun_of_dirty_tree_record_warns_and_runs_the_committed_sha(repo):
    """Adversarial where: a dirty record rerun silently (no warning), or rerun
    on the dirty contents instead of the recorded sha, or a clean record
    warned about."""
    argv = py("import sys; sys.exit(int(open('value.txt').read()))")
    (repo / "value.txt").write_text("5", encoding="utf-8")
    dirty_record, dirty_path = evidencelib.run_check(repo, "TASK-403", "dirty", argv)
    git(repo, "checkout", "--", "value.txt")
    clean_record, clean_path = evidencelib.run_check(repo, "TASK-403", "clean", argv)
    assert dirty_record["exit_code"] == 5 and clean_record["exit_code"] == 3
    dirty = evidencelib.rerun(dirty_path)
    assert dirty["dirty_warning"] is True
    assert dirty["exit_code"] == 3 and dirty["verdict"] == "mismatch"
    assert evidencelib.rerun(clean_path)["dirty_warning"] is False


@pytest.mark.parametrize("damage", ["missing", "not-json"])
def test_rerun_of_unreadable_record_is_refused_without_a_worktree(repo, damage):
    """Adversarial where: a crash with a traceback, or a scratch worktree
    created before the record was known to be readable."""
    path = repo / ".compass" / "evidence" / "TASK-403" / "bad.json"
    if damage == "not-json":
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
    with pytest.raises(evidencelib.EvidenceError):
        evidencelib.rerun(path)
    assert not (repo / ".claude" / "worktrees").exists()


def test_list_records_filters_by_exact_task_and_survives_a_damaged_record(repo):
    """Adversarial where: TASK-40 listing TASK-403's records by prefix, `.out`
    files listed as records, one damaged record hiding the others, or an
    unsorted result."""
    evidencelib.run_check(repo, "TASK-403", "zeta", py("pass"))
    evidencelib.run_check(repo, "TASK-403", "alpha", py("import sys; sys.exit(2)"))
    evidencelib.run_check(repo, "TASK-40", "other", py("pass"))
    broken = repo / ".compass" / "evidence" / "TASK-403" / "broken.json"
    broken.write_text("{", encoding="utf-8")
    rows = evidencelib.list_records(repo, "TASK-403")
    assert [row["check"] for row in rows] == ["alpha", "broken", "zeta"]
    assert rows[0]["exit_code"] == 2
    assert rows[1].get("unreadable") is True
    assert [row["check"] for row in evidencelib.list_records(repo, "TASK-40")] == ["other"]
    assert evidencelib.list_records(repo, "TASK-999") == []
