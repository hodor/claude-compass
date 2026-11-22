"""Post-build tests for `compass reach`: classes only the implementation reveals.

Adversarial themes: changed files that hold no executable code, git
configuration that changes the diff header shape, hit counts that cannot be
converted to integers, and path or record shapes a platform's tools emit
(spaces and non-ASCII in names, function names holding commas, a directory
given as the report).
"""

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reachlib  # noqa: E402
from commands import reach  # noqa: E402

RANGE = "HEAD~1..HEAD"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is required")


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _make_repo(tmp_path, first, second, config=()):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "core.autocrlf", "false")
    for key, value in config:
        _git(repo, "config", key, value)
    for files in (first, second):
        for rel, content in files.items():
            target = repo / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content.encode("utf-8"))
            _git(repo, "add", rel)
        _git(
            repo,
            "-c", "user.name=tester",
            "-c", "user.email=tester@example.invalid",
            "-c", "commit.gpgsign=false",
            "commit", "-q", "-m", "commit",
        )
    return repo


def _run(capsys, tmp_path, repo, report_text):
    report = tmp_path / "report.info"
    report.write_text(report_text, encoding="utf-8")
    code = reach.run(["--report", str(report), "--diff", RANGE, "--repo", str(repo)])
    out = capsys.readouterr().out
    verdicts = [line for line in out.splitlines() if line.startswith("REACH:")]
    assert len(verdicts) == 1, out
    return code, verdicts[0], out


CODE_REPORT = "SF:a.py\nDA:1,1\nDA:2,1\nend_of_record\n"

NON_CODE_ROWS = {
    "doc-only-report-names-other-code": (
        {"a.py": "x = 1\n"},
        {"a.py": "x = 1\n", "README.md": "hello\n"},
        "SF:other.py\nDA:1,1\nend_of_record\n",
        "REACH: N/A",
    ),
    "yaml-only-report-names-other-code": (
        {"a.py": "x = 1\n"},
        {"a.py": "x = 1\n", "ci.yaml": "a: 1\n"},
        "SF:a.py\nDA:1,1\nend_of_record\n",
        "REACH: N/A",
    ),
    "doc-only-empty-report": (
        {"a.py": "x = 1\n"},
        {"a.py": "x = 1\n", "README.md": "hello\n"},
        "",
        "REACH: N/A",
    ),
    "run-code-plus-doc-line": (
        {"a.py": "x = 1\n"},
        {"a.py": "x = 1\ny = 2\n", "README.md": "hello\n"},
        CODE_REPORT,
        "REACH: PASS",
    ),
}


@pytest.mark.parametrize("row", list(NON_CODE_ROWS), ids=list(NON_CODE_ROWS))
def test_changes_to_non_code_files_never_make_the_verdict_a_finding_or_skip(
    tmp_path, capsys, row
):
    """Adversarial where: a README or YAML line has no executable content, so
    a diff whose only changes are such files is N/A and a documentation file
    next to fully-run code does not turn PASS into FINDING."""
    first, second, report_text, expected = NON_CODE_ROWS[row]
    repo = _make_repo(tmp_path, first, second)
    code, verdict, out = _run(capsys, tmp_path, repo, report_text)
    assert code == 0
    assert verdict == expected, out


def test_diff_prefix_config_does_not_strip_a_real_leading_b_directory(
    tmp_path, capsys
):
    """Adversarial where: with `diff.noprefix` the header path has no `b/`
    prefix, so a source directory literally named `b` must keep its name and
    match the report path `b/a.py`."""
    repo = _make_repo(
        tmp_path,
        {"b/a.py": "x = 1\n"},
        {"b/a.py": "x = 1\ny = 2\n"},
        config=[("diff.noprefix", "true")],
    )
    report = "SF:b/a.py\nDA:1,1\nDA:2,0\nend_of_record\n"
    _, verdict, out = _run(capsys, tmp_path, repo, report)
    assert verdict == "REACH: FINDING", out
    assert "unrun lines: 2" in out


@pytest.mark.parametrize("hits", ["inf", "-inf", "nan", "1e999"])
def test_unconvertible_hit_count_gives_a_verdict_not_a_traceback(
    tmp_path, capsys, hits
):
    """Adversarial where: a hit count float() accepts but int() cannot
    convert (`inf`, `nan`) must end as a verdict line, never an uncaught
    exception out of the command."""
    repo = _make_repo(tmp_path, {"a.py": "x = 1\n"}, {"a.py": "x = 1\ny = 2\n"})
    report = f"SF:a.py\nDA:1,1\nDA:2,{hits}\nend_of_record\n"
    code, verdict, _ = _run(capsys, tmp_path, repo, report)
    assert code == 0
    assert verdict.startswith("REACH: ")


@pytest.mark.parametrize(
    "name", ["my app.py", "café.py"], ids=["space", "non-ascii"]
)
def test_filenames_with_spaces_or_non_ascii_match_the_report(tmp_path, capsys, name):
    """Adversarial where: git appends a tab to header paths holding spaces
    and quotes non-ASCII ones unless quoting is off; the diff path must still
    equal the report's path so the unrun line is named."""
    repo = _make_repo(tmp_path, {name: "x = 1\n"}, {name: "x = 1\ny = 2\n"})
    report = f"SF:{name}\nDA:1,1\nDA:2,0\nend_of_record\n"
    _, verdict, out = _run(capsys, tmp_path, repo, report)
    assert verdict == "REACH: FINDING", out
    assert f"{name}: 0 of 1 changed lines run" in out


def test_report_path_that_is_a_directory_is_no_measurement(tmp_path, capsys):
    """Adversarial where: a directory handed as the report is an unreadable
    measurement (SKIP), not bad arguments and not a traceback."""
    repo = _make_repo(tmp_path, {"a.py": "x = 1\n"}, {"a.py": "x = 1\ny = 2\n"})
    folder = tmp_path / "reportdir"
    folder.mkdir()
    code = reach.run(["--report", str(folder), "--diff", RANGE, "--repo", str(repo)])
    out = capsys.readouterr().out
    assert code == 0
    assert out.strip().splitlines()[-1] == "REACH: SKIP: no measurement"


def test_lcov_function_records_in_every_shape():
    """Adversarial where: function names holding commas, a FNDA record that
    precedes its FN record, an FN with no FNDA, and the line,end,name range
    form must each yield the right (name, line, hits) triple."""
    text = (
        "SF:a.cpp\n"
        "FNDA:0,tmpl<int,long>\n"
        "FN:3,tmpl<int,long>\n"
        "FN:10,12,ranged\n"
        "FNDA:4,ranged\n"
        "FN:20,never_recorded\n"
        "end_of_record\n"
    )
    functions = sorted(reachlib.parse_lcov(text)["a.cpp"]["functions"])
    assert functions == [
        ("never_recorded", 20, 0),
        ("ranged", 10, 4),
        ("tmpl<int,long>", 3, 0),
    ]
