"""Tests for the internals of `compass reach --run` that its public contract
does not name: the coverage rc text, the coverage version gate, interpreter
selection order, cleanup of the startup file on every exit path, and the
environment the measured command receives.

Python runs reuse the virtual-environment helpers of `test_reach_run`.
"""

import configparser
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reachlib  # noqa: E402
from commands import reach  # noqa: E402
from test_reach_run import (  # noqa: E402,F401
    LIB_NEW_HELPER,
    PTH_NAME,
    RANGE,
    assert_no_pth,
    command_for,
    lib_repo,
    make_repo,
    make_venv,
    posix,
    run_reach,
    site_packages,
    venv_py,
    verdict_line,
    write_script,
)

CALL_NEW_HELPER = "import lib\nlib.new_helper()\n"
LIB_OLD = {"lib.py": "def old():\n    return 1\n"}


@pytest.mark.parametrize(
    "text, expected",
    [
        ("7.10.0", (7, 10)),
        ("7.9.2", (7, 9)),
        ("7.10", (7, 10)),
        ("7.10.0b1", (7, 10)),
        ("7.100.1", (7, 100)),
        ("10.0.0", (10, 0)),
        ("  7.11.3\n", (7, 11)),
        ("none", None),
        ("", None),
        (None, None),
        ("7", None),
        ("v7.10", None),
    ],
)
def test_coverage_version_reads_major_and_minor_numerically(text, expected):
    """Adversarial where: a version read as a string or float makes 7.9 newer
    than 7.10, and a pre-release suffix or the probe's `none` marker raises
    instead of returning None."""
    assert reachlib.coverage_version(text) == expected


def test_minimum_coverage_orders_nine_below_ten_and_ten_zero_above():
    """Adversarial where: tuple comparison against the minimum breaks at the
    two-digit minor boundary (7.9 vs 7.10, 8.0 vs 7.10)."""
    older = reachlib.coverage_version("7.9.99")
    exact = reachlib.coverage_version("7.10.0")
    newer = reachlib.coverage_version("8.0.0")
    assert older < reachlib.MIN_COVERAGE
    assert not exact < reachlib.MIN_COVERAGE
    assert not newer < reachlib.MIN_COVERAGE


def rc_parser(text):
    parser = configparser.RawConfigParser()
    parser.read_string(text)
    return parser


def test_coverage_rc_sets_every_run_option_the_measurement_needs():
    """Adversarial where: a missing `parallel`, `concurrency` or `data_file`
    key makes pool workers, threads or the combine step silently measure
    nothing."""
    text = reachlib.coverage_rc("/work/proj", "/work/proj/.compass/tmp/reach/X/.coverage")
    run = rc_parser(text)["run"]
    assert run["parallel"] == "true"
    assert [c.strip() for c in run["concurrency"].split(",")] == ["thread", "multiprocessing"]
    assert run["data_file"] == "/work/proj/.compass/tmp/reach/X/.coverage"
    assert run["include"] == "/work/proj/**"


def test_coverage_rc_omits_tests_and_installed_packages_one_per_line():
    """Adversarial where: tests or site-packages count as measured source, or
    the omit patterns share a line and coverage reads them as one."""
    run = rc_parser(reachlib.coverage_rc("/w", "/w/.coverage"))["run"]
    omit = [line.strip() for line in run["omit"].splitlines() if line.strip()]
    for expected in (
        "*/tests/*",
        "*/test_*",
        "*/*_test.*",
        "*/*.spec.*",
        "*/site-packages/*",
        "*/venv/*",
        "*/.venv/*",
        "*/node_modules/*",
    ):
        assert expected in omit


def test_coverage_rc_converts_windows_separators_in_every_path():
    """Adversarial where: a backslash in `include` or `data_file` is read as
    an escape by coverage's glob and nothing matches."""
    text = reachlib.coverage_rc("C:\\work\\proj", "C:\\work\\proj\\.compass\\tmp\\.coverage")
    assert "\\" not in text
    assert "include = C:/work/proj/**" in text
    assert "data_file = C:/work/proj/.compass/tmp/.coverage" in text


def test_interpreter_prefers_given_then_venv_then_dot_venv_then_path(tmp_path, monkeypatch):
    """Adversarial where: the lookup order inverts (PATH python beating a repo
    environment, `.venv` beating `venv`, `--python` ignored), so a different
    interpreter than the project's is measured."""
    folder, name = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    monkeypatch.setattr(reach.shutil, "which", lambda _: "PATH-PYTHON")
    repo = str(tmp_path)
    assert reach._interpreter(repo, None) == "PATH-PYTHON"
    dot_venv = tmp_path / ".venv" / folder / name
    dot_venv.parent.mkdir(parents=True)
    dot_venv.write_text("")
    assert reach._interpreter(repo, None) == str(dot_venv)
    plain = tmp_path / "venv" / folder / name
    plain.parent.mkdir(parents=True)
    plain.write_text("")
    assert reach._interpreter(repo, None) == str(plain)
    assert reach._interpreter(repo, "given-python") == "given-python"


def test_interpreter_is_none_when_nothing_exists(tmp_path, monkeypatch):
    """Adversarial where: an empty `venv/` directory without an executable
    counts as an interpreter, or the absence of any python raises."""
    (tmp_path / "venv").mkdir()
    monkeypatch.setattr(reach.shutil, "which", lambda _: None)
    assert reach._interpreter(str(tmp_path), None) is None


def test_no_interpreter_anywhere_is_skip_and_runs_nothing(tmp_path, capsys, monkeypatch):
    """Adversarial where: the absence of an interpreter crashes with a
    traceback or runs the command unmeasured."""
    repo = lib_repo(tmp_path)
    marker = tmp_path / "ran.marker"
    monkeypatch.setattr(reach.shutil, "which", lambda _: None)
    code, out, _ = run_reach(capsys, repo, f'echo x > "{posix(marker)}"')
    assert code == 0
    assert verdict_line(out).startswith("REACH: SKIP"), out
    assert not marker.exists()


def test_unrunnable_interpreter_is_skip_without_traceback(tmp_path, capsys):
    """Adversarial where: a `--python` path that does not exist raises
    FileNotFoundError out of the probe instead of becoming a SKIP."""
    repo = lib_repo(tmp_path)
    missing = tmp_path / "nowhere" / "python"
    code, out, _ = run_reach(capsys, repo, "echo hi", missing)
    assert code == 0
    assert verdict_line(out).startswith("REACH: SKIP"), out


def fake_coverage_venv(tmp_path, version):
    """A venv whose `coverage` module reports `version` and does nothing."""
    py = make_venv(tmp_path / f"fake_{version}", "--without-pip")
    (site_packages(py) / "coverage.py").write_text(
        f"__version__ = {version!r}\ndef process_startup():\n    return None\n",
        encoding="utf-8",
    )
    return py


def test_coverage_older_than_minimum_is_skip_and_never_runs_the_command(tmp_path, capsys):
    """Adversarial where: coverage 7.9 is accepted because the version is
    compared as text or a boundary is off, so the command runs and a thin
    measurement reads as a finding."""
    py = fake_coverage_venv(tmp_path, "7.9.2")
    repo = lib_repo(tmp_path)
    marker = tmp_path / "ran.marker"
    script = write_script(tmp_path, "cli.py", f"open({posix(marker)!r}, 'w').close()\n", repo)
    code, out, _ = run_reach(capsys, repo, command_for(py, script), py)
    assert code == 0
    assert verdict_line(out).startswith("REACH: SKIP"), out
    assert "7.9.2" in out and "7.10" in out
    assert not marker.exists()
    assert_no_pth(py)


@pytest.mark.parametrize("version", ["7.10.0", "10.1.0"])
def test_minimum_coverage_and_newer_pass_the_gate_and_run_the_command(tmp_path, capsys, version):
    """Adversarial where: the gate rejects exactly 7.10 (off-by-one on the
    minor) or a two-digit major, so the run never starts. The fake module
    writes no data, so the verdict is the no-data SKIP, not the version one."""
    py = fake_coverage_venv(tmp_path, version)
    repo = lib_repo(tmp_path)
    marker = tmp_path / "ran.marker"
    script = write_script(tmp_path, "cli.py", f"open({posix(marker)!r}, 'w').close()\n", repo)
    code, out, _ = run_reach(capsys, repo, command_for(py, script), py)
    assert code == 0
    assert marker.exists()
    assert "older than" not in out
    assert re.search(r"^run exit: 0$", out, re.M), out
    assert "no coverage data" in out
    assert_no_pth(py)


def reach_args(repo, venv, command="x"):
    return ["--run", command, "--lang", "python", "--diff", RANGE, "--repo", str(repo), "--python", str(venv)]


def test_keyboard_interrupt_during_the_command_still_removes_the_startup_file(
    tmp_path, venv_py, monkeypatch
):
    """Adversarial where: Ctrl-C during the measured command skips cleanup, so
    the startup file stays in site-packages and loads coverage into every
    later process of that interpreter."""
    repo = lib_repo(tmp_path)
    pth = site_packages(venv_py) / PTH_NAME
    seen = []

    def interrupted(command, repo_dir, env):
        seen.append(pth.exists())
        raise KeyboardInterrupt

    monkeypatch.setattr(reach, "_run_command", interrupted)
    with pytest.raises(KeyboardInterrupt):
        reach.run(reach_args(repo, venv_py))
    assert seen == [True]
    assert not pth.exists()


def test_unexpected_exception_during_the_command_still_removes_the_startup_file(
    tmp_path, venv_py, monkeypatch
):
    """Adversarial where: a non-OSError failure out of the command runner
    (only OSError is caught) leaves the startup file behind."""
    repo = lib_repo(tmp_path)
    pth = site_packages(venv_py) / PTH_NAME
    seen = []

    def broken(command, repo_dir, env):
        seen.append(pth.exists())
        raise RuntimeError("runner failed")

    monkeypatch.setattr(reach, "_run_command", broken)
    with pytest.raises(RuntimeError):
        reach.run(reach_args(repo, venv_py))
    assert seen == [True]
    assert not pth.exists()


def test_command_that_deletes_the_startup_file_itself_does_not_crash_cleanup(
    tmp_path, capsys, venv_py
):
    """Adversarial where: cleanup removes the startup file unconditionally and
    raises FileNotFoundError when the command already deleted it."""
    repo = lib_repo(tmp_path)
    pth = site_packages(venv_py) / PTH_NAME
    script = write_script(tmp_path, "cli.py", f"import os\nos.remove({posix(pth)!r})\n", repo)
    code, out, _ = run_reach(capsys, repo, command_for(venv_py, script), venv_py)
    assert code == 0
    assert verdict_line(out).startswith("REACH:")
    assert not pth.exists()


def test_existing_startup_file_survives_a_skipped_run_byte_for_byte(tmp_path, capsys, venv_py):
    """Adversarial where: the exclusive-create guard is followed by a cleanup
    that deletes a file the run never wrote, destroying another run's startup
    file (checked on bytes a text round trip would alter)."""
    repo = lib_repo(tmp_path)
    pth = site_packages(venv_py) / PTH_NAME
    original = b"# \xff\xfe odd bytes\r\nimport sys\r\n"
    pth.write_bytes(original)
    try:
        code, out, _ = run_reach(capsys, repo, "echo hi", venv_py)
        after = pth.read_bytes()
    finally:
        pth.unlink()
    assert code == 0
    assert verdict_line(out).startswith("REACH: SKIP")
    assert after == original


def test_command_receives_an_absolute_rc_path_and_runs_in_the_repository(
    tmp_path, capsys, venv_py, monkeypatch
):
    """Adversarial where: a relative `--repo` yields a relative
    COVERAGE_PROCESS_START, which breaks as soon as the command or a child
    changes directory; the command must also start in the repository."""
    repo = lib_repo(tmp_path)
    record = tmp_path / "env.json"
    script = write_script(
        tmp_path,
        "cli.py",
        "import json, os\n"
        "json.dump({'rc': os.environ.get('COVERAGE_PROCESS_START'), 'cwd': os.getcwd()},"
        f" open({posix(record)!r}, 'w'))\n",
        repo,
    )
    monkeypatch.chdir(tmp_path)
    args = reach_args("repo", venv_py, command_for(venv_py, script))
    code = reach.run(args)
    capsys.readouterr()
    assert code == 0
    seen = json.loads(record.read_text())
    assert os.path.isabs(seen["rc"])
    rc_files = list((repo / ".compass" / "tmp" / "reach").glob("*/coveragerc"))
    assert len(rc_files) == 1
    assert os.path.samefile(seen["rc"], rc_files[0])
    assert os.path.samefile(seen["cwd"], repo)


def test_command_output_never_reaches_stdout_as_a_verdict_line(tmp_path, capsys, venv_py):
    """Adversarial where: the command's own stdout is forwarded to stdout, so
    a command printing `REACH: PASS` (or undecodable bytes) forges or corrupts
    the verdict the caller parses."""
    repo = lib_repo(tmp_path)
    script = write_script(
        tmp_path,
        "cli.py",
        "import sys\n"
        "print('REACH: PASS')\n"
        "sys.stdout.flush()\n"
        "sys.stdout.buffer.write(bytes([255, 254, 10]))\n",
        repo,
    )
    code, out, err = run_reach(capsys, repo, command_for(venv_py, script), venv_py)
    assert code == 0
    assert "REACH: PASS" in err
    assert verdict_line(out) != "REACH: PASS"


def test_nonzero_exit_after_reaching_the_lines_does_not_change_the_verdict(
    tmp_path, capsys, venv_py
):
    """Adversarial where: the command's failing exit code is folded into the
    verdict, turning a fully reached change into a finding or a skip."""
    repo = lib_repo(tmp_path)
    script = write_script(tmp_path, "cli.py", CALL_NEW_HELPER + "raise SystemExit(7)\n", repo)
    code, out, _ = run_reach(capsys, repo, command_for(venv_py, script), venv_py)
    assert code == 0
    assert re.search(r"^run exit: 7$", out, re.M), out
    assert verdict_line(out) == "REACH: PASS"


def test_command_with_no_python_process_prints_its_exit_and_is_skip(tmp_path, capsys, venv_py):
    """Adversarial where: a command that starts no Python process leaves no
    data and the empty measurement reads as 0% (a finding) or loses the
    command's exit code."""
    repo = lib_repo(tmp_path)
    code, out, _ = run_reach(capsys, repo, "echo hello", venv_py)
    assert code == 0
    assert re.search(r"^run exit: 0$", out, re.M), out
    assert verdict_line(out).startswith("REACH: SKIP"), out
    assert_no_pth(venv_py)


def test_empty_command_is_skip_not_pass(tmp_path, capsys, venv_py):
    """Adversarial where: an empty `--run` string runs nothing and the empty
    report is accepted as a passing measurement."""
    repo = lib_repo(tmp_path)
    code, out, _ = run_reach(capsys, repo, "", venv_py)
    assert code == 0
    assert verdict_line(out).startswith("REACH: SKIP"), out
    assert_no_pth(venv_py)


def measured_under(tmp_path, capsys, venv_py, folder_name):
    base = tmp_path / folder_name
    base.mkdir()
    repo = make_repo(base, LIB_OLD, {"lib.py": LIB_NEW_HELPER})
    script = write_script(tmp_path, "cli.py", CALL_NEW_HELPER, repo)
    return run_reach(capsys, repo, command_for(venv_py, script), venv_py)


@pytest.mark.parametrize("folder_name", ["my projects", "tests", "venv", "site-packages"])
def test_repository_under_an_ancestor_folder_is_measured(tmp_path, capsys, venv_py, folder_name):
    """Adversarial where: spaces in the repository path break the rc `include`
    pattern or the shell command, or an omit pattern for test folders,
    environments or installed packages matches the checkout's own ancestor
    folder and drops every file of the repository from the measurement."""
    code, out, _ = measured_under(tmp_path, capsys, venv_py, folder_name)
    assert code == 0
    assert re.search(r"lib\.py: 3 of 3 changed lines run", out), out
    assert verdict_line(out) == "REACH: PASS"


@pytest.mark.parametrize(
    "args, needle",
    [
        (["--report", "r.info", "--lang", "python", "--diff", "HEAD~1..HEAD"], "--lang"),
        (["--report", "r.info", "--python", "p", "--diff", "HEAD~1..HEAD"], "--python"),
        (["--run", "x", "--diff", "HEAD~1..HEAD"], "--lang"),
        (["--run", "x", "--lang", "ruby", "--diff", "HEAD~1..HEAD"], "--lang"),
        (["--run", "x", "--lang", "node", "--python", "p", "--diff", "HEAD~1..HEAD"], "--python"),
        (["--run", "x", "--lang", "python"], "--diff"),
        (["--lang", "python", "--diff", "HEAD~1..HEAD"], "--report or --run"),
        (["--runx", "x", "--diff", "HEAD~1..HEAD"], "unknown argument"),
        (["--run"], "requires a value"),
    ],
)
def test_invalid_flag_combinations_exit_1_naming_the_problem_without_running(
    tmp_path, capsys, args, needle
):
    """Adversarial where: a flag valid on its own (`--lang`, `--python`) is
    accepted beside `--report`, `--run` is accepted without `--lang`, or a
    near-miss flag name is accepted by prefix, so the command runs or the
    wrong source is silently chosen."""
    repo = lib_repo(tmp_path)
    code = reach.run(["--repo", str(repo), *args])
    captured = capsys.readouterr()
    assert code == 1
    assert needle in captured.err
    assert "REACH:" not in captured.out
    assert not (repo / ".compass" / "tmp" / "reach").exists()
