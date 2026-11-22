"""Tests for `compass reach --report <file> --diff <range> [--repo <dir>]`.

Each test builds a throwaway git repository with two commits, writes a
coverage report for the second commit's changes, and runs the command module
against the range `HEAD~1..HEAD`.

Adversarial themes: a measurement that did not happen reading as 0% or PASS,
one-line functions that never ran under full line coverage, Windows-shaped
paths and CRLF from the platforms that produce the reports, and exit codes
reserved for bad arguments.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import reach  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "reach"
RANGE = "HEAD~1..HEAD"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is required")


def git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    )


def commit(repo, files, message):
    for rel, content in files.items():
        target = Path(repo) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        data = content if isinstance(content, bytes) else content.encode("utf-8")
        target.write_bytes(data)
        git(repo, "add", rel)
    git(
        repo,
        "-c", "user.name=tester",
        "-c", "user.email=tester@example.invalid",
        "-c", "commit.gpgsign=false",
        "commit", "-q", "-m", message,
    )


def make_repo(tmp_path, first, second):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "core.autocrlf", "false")
    git(repo, "config", "core.safecrlf", "false")
    commit(repo, first, "first")
    commit(repo, second, "second")
    return repo


def lcov(records):
    """records: {path: [(line, hits), ...]} -> LCOV text."""
    out = []
    for path, lines in records.items():
        out.append(f"SF:{path}")
        out.extend(f"DA:{n},{hits}" for n, hits in lines)
        out.append("end_of_record")
    return "\n".join(out) + "\n"


def run_reach(capsys, report, repo, diff=RANGE):
    code = reach.run(["--report", str(report), "--diff", diff, "--repo", str(repo)])
    return code, capsys.readouterr().out


def verdict_line(out):
    lines = [line for line in out.splitlines() if line.startswith("REACH:")]
    assert len(lines) == 1, out
    return lines[0]


APP_BASE = {"README.md": "x\n", "src/app.py": "import os\n\n"}
APP_NEW = {
    "src/app.py": (
        "import os\n\n"
        "def used():\n"
        "    return 1\n\n"
        "def helper():\n"
        "    return 2\n"
    )
}


def test_reached_function_and_unreferenced_helper(tmp_path, capsys):
    """Adversarial where: the unreferenced helper's unrun lines must be named
    and the verdict must be a finding, even though the reached function in the
    same diff ran; the counts must be of executable changed lines."""
    repo = make_repo(tmp_path, APP_BASE, APP_NEW)
    report = FIXTURES / "coverage_py.xml"
    code, out = run_reach(capsys, report, repo)
    assert code == 0
    assert "src/app.py: 2 of 4 changed lines run" in out
    assert re.search(r"\b6\b", out) and re.search(r"\b7\b", out)
    assert verdict_line(out) == "REACH: FINDING"


def test_all_changed_lines_run_is_pass(tmp_path, capsys):
    """Adversarial where: a pass verdict printed while an unrun line exists, or
    a nonzero exit for a clean diff."""
    repo = make_repo(tmp_path, APP_BASE, APP_NEW)
    report = tmp_path / "cov.info"
    report.write_text(lcov({"src/app.py": [(3, 2), (4, 2), (6, 1), (7, 1)]}))
    code, out = run_reach(capsys, report, repo)
    assert code == 0
    assert "src/app.py: 4 of 4 changed lines run" in out
    assert verdict_line(out) == "REACH: PASS"


JS_BASE = {"README.md": "x\n"}
JS_NEW = {
    "src/route.js": (
        "exports.routeDead = (x) => x * 2;\n"
        "// routes\n"
        "exports.routeNew = (x) => {\n"
        "  return x + 1;\n"
        "};\n"
    )
}


def test_one_line_arrow_unreached_though_its_line_ran(tmp_path, capsys):
    """Adversarial where: line coverage alone calls this diff fully run; the
    function record FNDA:0 on a changed line must still be named and make the
    verdict a finding, while the reached function is not named."""
    repo = make_repo(tmp_path, JS_BASE, JS_NEW)
    report = FIXTURES / "lcov_c8.info"
    code, out = run_reach(capsys, report, repo)
    assert code == 0
    assert "src/route.js: 3 of 3 changed lines run" in out
    assert "exports.routeDead" in out
    assert "routeNew" not in out
    assert verdict_line(out) == "REACH: FINDING"


def test_no_report_file_is_skip_not_bad_arguments(tmp_path, capsys):
    """Adversarial where: a report path that does not exist is the killed-run
    case; it must be SKIP with exit 0 and never a percentage, not an
    argument error."""
    repo = make_repo(tmp_path, APP_BASE, APP_NEW)
    code, out = run_reach(capsys, tmp_path / "absent.info", repo)
    assert code == 0
    assert verdict_line(out).startswith("REACH: SKIP")
    assert "no measurement" in out
    assert "%" not in out
    assert " of " not in out


@pytest.mark.parametrize("content", ["", "\n\n", "TN:\n"])
def test_empty_report_is_skip_never_zero_percent(tmp_path, capsys, content):
    """Adversarial where: a report with no file records (a server killed before
    it wrote anything) must not be scored as every changed line unrun."""
    repo = make_repo(tmp_path, APP_BASE, APP_NEW)
    report = tmp_path / "empty.info"
    report.write_text(content)
    code, out = run_reach(capsys, report, repo)
    assert code == 0
    assert verdict_line(out).startswith("REACH: SKIP")
    assert "%" not in out
    assert " of " not in out


def test_truncated_xml_report_is_skip(tmp_path, capsys):
    """Adversarial where: a Cobertura file cut off mid-write raises a parse
    error that must surface as a SKIP verdict with exit 0, never a crash or a
    pass."""
    repo = make_repo(tmp_path, APP_BASE, APP_NEW)
    report = tmp_path / "cut.xml"
    report.write_text('<?xml version="1.0" ?>\n<coverage><packages><package><classes><class file')
    code, out = run_reach(capsys, report, repo)
    assert code == 0
    assert verdict_line(out).startswith("REACH: SKIP")
    assert "%" not in out


def test_report_naming_other_files_is_skip_missed(tmp_path, capsys):
    """Adversarial where: a report that measured only unrelated files reads as
    0% or PASS for the diff; it must say the measurement missed the changed
    files."""
    repo = make_repo(tmp_path, APP_BASE, APP_NEW)
    report = tmp_path / "other.info"
    report.write_text(lcov({"src/other.py": [(1, 1), (2, 1)]}))
    code, out = run_reach(capsys, report, repo)
    assert code == 0
    assert verdict_line(out).startswith("REACH: SKIP")
    assert "measurement missed the changed files" in out
    assert "%" not in out
    assert " of " not in out


def test_crlf_files_report_clean_paths_and_line_numbers(tmp_path, capsys):
    """Adversarial where: carriage returns from a CRLF-committed file leak into
    the diff text and corrupt the path or the hunk line numbers, so changed
    lines no longer match the report."""
    base = {"README.md": "x\r\n", "src/a.py": b"import os\r\n"}
    new = {"src/a.py": b"import os\r\ndef f():\r\n    return 1\r\n"}
    repo = make_repo(tmp_path, base, new)
    report = tmp_path / "cov.info"
    report.write_text(lcov({"src/a.py": [(2, 1), (3, 0)]}))
    code, out = run_reach(capsys, report, repo)
    assert code == 0
    assert "\r" not in out
    assert "src/a.py: 1 of 2 changed lines run" in out
    assert verdict_line(out) == "REACH: FINDING"


@pytest.mark.parametrize("style", ["backslash-relative", "absolute-native"])
def test_report_path_styles_match_the_diff(tmp_path, capsys, style):
    """Adversarial where: a Windows-style relative path, or an absolute path under
    the repo, left unmapped reads as a report naming none of the diff's files."""
    repo = make_repo(tmp_path, APP_BASE, APP_NEW)
    path = "src\\app.py" if style == "backslash-relative" else str(repo / "src" / "app.py")
    report = tmp_path / "cov.info"
    report.write_text(lcov({path: [(3, 1), (4, 1), (6, 0), (7, 0)]}))
    code, out = run_reach(capsys, report, repo)
    assert code == 0
    assert "src/app.py: 2 of 4 changed lines run" in out
    assert verdict_line(out) == "REACH: FINDING"


def test_cobertura_with_encoding_declaration_and_backslash_filenames(tmp_path, capsys):
    """Adversarial where: an XML declaration naming an encoding crashes a str
    parse, and backslash filenames fail to match; the report must be read, not
    skipped."""
    base = {"README.md": "x\n"}
    lines = [f"// line {n}\n" for n in range(1, 22)]
    new = {"src/front.ts": "".join(lines)}
    repo = make_repo(tmp_path, base, new)
    code, out = run_reach(capsys, FIXTURES / "coverage_decl.xml", repo)
    assert code == 0
    assert "src/front.ts: 2 of 4 changed lines run" in out
    assert verdict_line(out) == "REACH: FINDING"


def test_diff_of_only_test_files_is_not_applicable(tmp_path, capsys):
    """Adversarial where: test files counted as changed source, or a report that
    names only other files turning a tests-only diff into SKIP or a
    finding."""
    base = {"README.md": "x\n", "tests/test_a.py": "x = 1\n", "web/a.spec.ts": "a\n"}
    new = {"tests/test_a.py": "x = 1\ny = 2\n", "web/a.spec.ts": "a\nb\n"}
    repo = make_repo(tmp_path, base, new)
    report = tmp_path / "cov.info"
    report.write_text(
        lcov({"tests/test_a.py": [(2, 0)], "web/a.spec.ts": [(2, 0)], "src/x.py": [(1, 1)]})
    )
    code, out = run_reach(capsys, report, repo)
    assert code == 0
    assert verdict_line(out) == "REACH: N/A"
    assert "%" not in out


def test_test_file_lines_never_count_against_source(tmp_path, capsys):
    """Adversarial where: unrun lines in a changed test file dragging a fully
    run source change into FINDING."""
    base = {"README.md": "x\n", "tests/test_a.py": "x = 1\n"}
    new = {
        "tests/test_a.py": "x = 1\ny = 2\n",
        "src/app.py": "def f():\n    return 1\n",
    }
    repo = make_repo(tmp_path, base, new)
    report = tmp_path / "cov.info"
    report.write_text(
        lcov({"tests/test_a.py": [(2, 0)], "src/app.py": [(1, 1), (2, 1)]})
    )
    code, out = run_reach(capsys, report, repo)
    assert code == 0
    assert "src/app.py: 2 of 2 changed lines run" in out
    assert "test_a.py" not in out
    assert verdict_line(out) == "REACH: PASS"


def test_deletion_only_diff_is_not_applicable(tmp_path, capsys):
    """Adversarial where: removed lines have no new-side line numbers; a diff
    that only deletes must be N/A, not a finding built from stale numbers."""
    base = {"README.md": "x\n", "src/app.py": "a = 1\nb = 2\nc = 3\n"}
    new = {"src/app.py": "a = 1\n"}
    repo = make_repo(tmp_path, base, new)
    report = tmp_path / "cov.info"
    report.write_text(lcov({"src/app.py": [(1, 1)]}))
    code, out = run_reach(capsys, report, repo)
    assert code == 0
    assert verdict_line(out) == "REACH: N/A"


def test_repo_defaults_to_working_directory(tmp_path, capsys, monkeypatch):
    """Adversarial where: omitting --repo must diff the current directory's
    repository, not the directory holding the plugin."""
    repo = make_repo(tmp_path, APP_BASE, APP_NEW)
    report = tmp_path / "cov.info"
    report.write_text(lcov({"src/app.py": [(3, 1), (4, 1), (6, 1), (7, 1)]}))
    monkeypatch.chdir(repo)
    code = reach.run(["--report", str(report), "--diff", RANGE])
    out = capsys.readouterr().out
    assert code == 0
    assert verdict_line(out) == "REACH: PASS"


def test_bad_arguments_exit_one(tmp_path, capsys):
    """Adversarial where: exit 1 is reserved for bad arguments and must not be
    skipped for a missing flag, a flag without its value, an unknown flag, an
    unresolvable range or a missing repository directory."""
    repo = make_repo(tmp_path, APP_BASE, APP_NEW)
    report = tmp_path / "cov.info"
    report.write_text(lcov({"src/app.py": [(3, 1)]}))
    rows = {
        "no arguments": [],
        "missing --report": ["--diff", RANGE, "--repo", str(repo)],
        "missing --diff": ["--report", str(report), "--repo", str(repo)],
        "--report without value": ["--diff", RANGE, "--repo", str(repo), "--report"],
        "--diff without value": ["--report", str(report), "--repo", str(repo), "--diff"],
        "unknown flag": ["--report", str(report), "--diff", RANGE, "--repo", str(repo), "--bogus"],
        "unresolvable range": ["--report", str(report), "--diff", "nosuchref..HEAD", "--repo", str(repo)],
        "repo is not a directory": ["--report", str(report), "--diff", RANGE, "--repo", str(tmp_path / "nope")],
    }
    for name, args in rows.items():
        code = reach.run(args)
        out = capsys.readouterr().out
        assert code == 1, name
        assert "REACH: PASS" not in out, name
