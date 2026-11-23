"""Tests for `compass reach --run "<command>" --lang python|node --diff <range>`.

Each test builds a throwaway git repository whose second commit adds a
function to `lib.py`, writes a driver script outside the repository that
reaches (or fails to reach) that function in a particular way, and runs the
command module with `--run` against the range `HEAD~1..HEAD`. Python runs use
a virtual environment created in a temporary folder with
`--system-site-packages`; everything is skipped when that environment cannot
import coverage 7.10 or newer.

Adversarial themes: a measurement that did not happen reading as 0% or PASS,
code that runs only in a child process, a pool worker or a shell-wrapped hook,
the startup file written into an interpreter's site-packages outliving the run
or overwriting a file that was already there, and interpreters the startup file
must never be written into.
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

RANGE = "HEAD~1..HEAD"
PTH_NAME = "compass_reach_cov.pth"
MIN_COVERAGE = (7, 10)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is required")


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def commit(repo, files, message):
    for rel, content in files.items():
        target = Path(repo) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))
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


LIB_FIRST = "def old():\n    return 1\n"
# Changed lines of the second commit are 5, 6 and 7.
LIB_NEW_HELPER = LIB_FIRST + "\n\ndef new_helper():\n    value = 2\n    return value\n"
LIB_WORK = LIB_FIRST + "\n\ndef work(n):\n    doubled = n * 2\n    return doubled\n"


def lib_repo(tmp_path, second=LIB_NEW_HELPER):
    return make_repo(tmp_path, {"lib.py": LIB_FIRST}, {"lib.py": second})


def venv_python(venv):
    sub = "Scripts" if os.name == "nt" else "bin"
    exe = "python.exe" if os.name == "nt" else "python"
    return Path(venv) / sub / exe


def coverage_version(py):
    """Return the (major, minor) coverage version importable by `py`, or None."""
    proc = subprocess.run(
        [str(py), "-c", "import coverage; print(coverage.__version__)"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    match = re.match(r"(\d+)\.(\d+)", proc.stdout.strip())
    return (int(match.group(1)), int(match.group(2))) if match else None


def make_venv(path, *flags):
    subprocess.run(
        [sys.executable, "-m", "venv", *flags, str(path)],
        check=True,
        capture_output=True,
    )
    return venv_python(path)


def site_packages(py):
    proc = subprocess.run(
        [str(py), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(proc.stdout.strip())


@pytest.fixture(scope="module")
def venv_py(tmp_path_factory):
    py = make_venv(tmp_path_factory.mktemp("reach_venv"), "--system-site-packages")
    version = coverage_version(py)
    if version is None or version < MIN_COVERAGE:
        pytest.skip("coverage >= 7.10 is not importable in the test venv")
    pth = site_packages(py) / PTH_NAME
    assert not pth.exists()
    return py


def posix(path):
    return str(path).replace("\\", "/")


def write_script(tmp_path, name, body, repo):
    """Write a driver outside the repository that puts the repository on
    sys.path first."""
    folder = tmp_path / "drivers"
    folder.mkdir(exist_ok=True)
    script = folder / name
    prefix = f"import sys\nsys.path.insert(0, {posix(repo)!r})\n"
    script.write_text(prefix + body, encoding="utf-8")
    return script


def command_for(py, script):
    return f'"{posix(py)}" "{posix(script)}"'


def run_reach(capsys, repo, command, py=None, lang="python"):
    args = ["--run", command, "--lang", lang, "--diff", RANGE, "--repo", str(repo)]
    if py is not None:
        args += ["--python", str(py)]
    code = reach.run(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def verdict_line(out):
    lines = [line for line in out.splitlines() if line.startswith("REACH:")]
    assert len(lines) == 1, out
    return lines[0]


def assert_no_pth(py):
    assert not (site_packages(py) / PTH_NAME).exists()


def test_cli_script_calling_new_function_is_pass(tmp_path, capsys, venv_py):
    """Adversarial where: a run that executed the new function reads as a
    finding or a skip because the command's own process was not measured, or
    the command's exit code is not printed."""
    repo = lib_repo(tmp_path)
    script = write_script(tmp_path, "cli.py", "import lib\nlib.new_helper()\n", repo)
    code, out, _ = run_reach(capsys, repo, command_for(venv_py, script), venv_py)
    assert code == 0
    assert re.search(r"lib\.py: 3 of 3 changed lines run", out), out
    assert verdict_line(out) == "REACH: PASS"
    assert re.search(r"^run exit: 0$", out, re.M), out
    assert_no_pth(venv_py)


def test_new_helper_never_called_is_finding_naming_its_lines(tmp_path, capsys, venv_py):
    """Adversarial where: an unreferenced helper in the diff reads as run
    because the module's def line executed on import; its body lines must be
    named and the verdict must be a finding."""
    repo = lib_repo(tmp_path)
    script = write_script(tmp_path, "cli.py", "import lib\nlib.old()\n", repo)
    code, out, _ = run_reach(capsys, repo, command_for(venv_py, script), venv_py)
    assert code == 0
    assert re.search(r"lib\.py: 1 of 3 changed lines run", out), out
    assert "unrun lines: 6, 7" in out
    assert verdict_line(out) == "REACH: FINDING"


def test_python_child_process_lines_are_reached(tmp_path, capsys, venv_py):
    """Adversarial where: code that runs only in a Python child of the command
    reads as unreached because only the parent process was measured."""
    repo = lib_repo(tmp_path)
    child = write_script(tmp_path, "child.py", "import lib\nlib.new_helper()\n", repo)
    script = write_script(
        tmp_path,
        "parent.py",
        "import subprocess, sys\n"
        f"subprocess.run([sys.executable, {posix(child)!r}], check=True)\n",
        repo,
    )
    code, out, _ = run_reach(capsys, repo, command_for(venv_py, script), venv_py)
    assert code == 0
    assert re.search(r"lib\.py: 3 of 3 changed lines run", out), out
    assert verdict_line(out) == "REACH: PASS"
    assert_no_pth(venv_py)


def test_multiprocessing_pool_worker_lines_are_reached(tmp_path, capsys, venv_py):
    """Adversarial where: a function body that runs only inside a Pool worker
    reads as unreached because worker processes were not measured."""
    repo = lib_repo(tmp_path, LIB_WORK)
    script = write_script(
        tmp_path,
        "pool.py",
        "import lib\n"
        "from multiprocessing import Pool\n"
        "if __name__ == '__main__':\n"
        "    pool = Pool(2)\n"
        "    print(pool.map(lib.work, [1, 2]))\n"
        "    pool.close()\n"
        "    pool.join()\n",
        repo,
    )
    code, out, _ = run_reach(capsys, repo, command_for(venv_py, script), venv_py)
    assert code == 0
    assert re.search(r"lib\.py: 3 of 3 changed lines run", out), out
    assert verdict_line(out) == "REACH: PASS"
    assert_no_pth(venv_py)


@pytest.mark.skipif(shutil.which("sh") is None, reason="sh is required")
def test_shell_wrapper_launching_python_as_a_hook_is_reached(tmp_path, capsys, venv_py):
    """Adversarial where: a hook fired through a shell wrapper has no measured
    Python parent, so code it runs reads as unreached unless every Python
    process the command starts measures itself."""
    repo = lib_repo(tmp_path)
    child = write_script(tmp_path, "hook_body.py", "import lib\nlib.new_helper()\n", repo)
    wrapper = tmp_path / "drivers" / "hookwrap.sh"
    wrapper.write_text(
        f"echo '{{}}' | \"{posix(venv_py)}\" \"{posix(child)}\"\n", encoding="utf-8"
    )
    code, out, _ = run_reach(capsys, repo, f'sh "{posix(wrapper)}"', venv_py)
    assert code == 0
    assert re.search(r"lib\.py: 3 of 3 changed lines run", out), out
    assert verdict_line(out) == "REACH: PASS"
    assert_no_pth(venv_py)


def test_hard_killed_server_child_is_skip_not_zero_percent(tmp_path, capsys, venv_py):
    """Adversarial where: a server the driver kills without a graceful stop
    saves no data, and the missing measurement must read as a SKIP rather than
    a finding or a zero percentage."""
    repo = lib_repo(tmp_path)
    server = write_script(
        tmp_path,
        "server.py",
        "import lib, sys, time\n"
        "lib.new_helper()\n"
        "print('ready', flush=True)\n"
        "time.sleep(60)\n",
        repo,
    )
    script = write_script(
        tmp_path,
        "driver.py",
        "import subprocess, sys\n"
        f"proc = subprocess.Popen([sys.executable, {posix(server)!r}],"
        " stdout=subprocess.PIPE, text=True)\n"
        "proc.stdout.readline()\n"
        "proc.kill()\n"
        "proc.wait()\n",
        repo,
    )
    code, out, _ = run_reach(capsys, repo, command_for(venv_py, script), venv_py)
    assert code == 0
    assert verdict_line(out).startswith("REACH: SKIP"), out
    assert "changed lines run" not in out
    assert_no_pth(venv_py)


def test_interpreter_outside_a_virtual_environment_is_skip(tmp_path, capsys):
    """Adversarial where: the startup file written into a system interpreter's
    site-packages would measure every Python process on the machine; the run
    must refuse, write nothing there, and report a SKIP."""
    base = getattr(sys, "_base_executable", sys.executable)
    probe = subprocess.run(
        [base, "-c", "import sys; print(sys.prefix == sys.base_prefix)"],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "True":
        pytest.skip("no interpreter outside a virtual environment is available")
    version = coverage_version(base)
    if version is None or version < MIN_COVERAGE:
        pytest.skip("coverage >= 7.10 is not importable by the system interpreter")
    pth = site_packages(base) / PTH_NAME
    if pth.exists():
        pytest.skip(f"{pth} already exists")
    repo = lib_repo(tmp_path)
    script = write_script(tmp_path, "cli.py", "import lib\nlib.new_helper()\n", repo)
    try:
        code, out, _ = run_reach(capsys, repo, command_for(base, script), base)
        assert not pth.exists()
    finally:
        if pth.exists():
            pth.unlink()
    assert code == 0
    assert verdict_line(out).startswith("REACH: SKIP"), out
    assert re.search(r"virtual|venv", out, re.I), out


def test_existing_startup_file_is_a_skip_and_left_as_it_was(tmp_path, capsys, venv_py):
    """Adversarial where: a leftover startup file of the same name from a
    killed run is overwritten or deleted by the next run; it must stay
    byte-identical, the command must not run, and the verdict is a SKIP."""
    repo = lib_repo(tmp_path)
    marker = tmp_path / "ran.marker"
    script = write_script(
        tmp_path,
        "cli.py",
        f"import lib\nlib.new_helper()\nopen({posix(marker)!r}, 'w').close()\n",
        repo,
    )
    pth = site_packages(venv_py) / PTH_NAME
    original = b"# pre-existing sentinel\n"
    pth.write_bytes(original)
    try:
        code, out, _ = run_reach(capsys, repo, command_for(venv_py, script), venv_py)
        assert pth.read_bytes() == original
    finally:
        if pth.exists():
            pth.unlink()
    assert code == 0
    assert verdict_line(out).startswith("REACH: SKIP"), out
    assert not marker.exists()


def test_failing_command_prints_exit_and_leaves_no_startup_file(tmp_path, capsys, venv_py):
    """Adversarial where: a command that exits nonzero skips the cleanup of
    the startup file, or its exit code is swallowed instead of printed."""
    repo = lib_repo(tmp_path)
    command = f'"{posix(venv_py)}" -c "import sys; sys.exit(3)"'
    code, out, _ = run_reach(capsys, repo, command, venv_py)
    assert code == 0
    assert re.search(r"^run exit: 3$", out, re.M), out
    assert verdict_line(out).startswith("REACH:")
    assert_no_pth(venv_py)


def test_command_that_raises_leaves_no_startup_file(tmp_path, capsys, venv_py):
    """Adversarial where: an exception inside the measured command leaves the
    startup file in site-packages, where it would load coverage into every
    later process of that interpreter."""
    repo = lib_repo(tmp_path)
    script = write_script(
        tmp_path, "cli.py", "import lib\nlib.new_helper()\nraise RuntimeError('boom')\n", repo
    )
    code, out, _ = run_reach(capsys, repo, command_for(venv_py, script), venv_py)
    assert code == 0
    assert re.search(r"^run exit: [1-9]\d*$", out, re.M), out
    assert re.search(r"lib\.py: 3 of 3 changed lines run", out), out
    assert_no_pth(venv_py)


def test_run_writes_its_rc_file_under_the_repo_tmp_reach_folder(tmp_path, capsys, venv_py):
    """Adversarial where: the coverage configuration and data are written
    outside the vault scratch folder (or into the working tree), leaving
    artifacts the commit rules forbid."""
    repo = lib_repo(tmp_path)
    script = write_script(tmp_path, "cli.py", "import lib\nlib.new_helper()\n", repo)
    run_reach(capsys, repo, command_for(venv_py, script), venv_py)
    folders = [p for p in (repo / ".compass" / "tmp" / "reach").glob("*") if p.is_dir()]
    assert len(folders) == 1
    assert any(p.is_file() for p in folders[0].iterdir())


def test_interpreter_found_in_repo_dot_venv_when_python_not_given(tmp_path, capsys):
    """Adversarial where: without `--python` the run falls back to the PATH
    interpreter, which has no startup file route into the repository's own
    environment and is outside a virtual environment, instead of using the
    `.venv` folder in the repo."""
    repo = lib_repo(tmp_path)
    py = make_venv(repo / ".venv", "--system-site-packages")
    version = coverage_version(py)
    if version is None or version < MIN_COVERAGE:
        pytest.skip("coverage >= 7.10 is not importable in the test venv")
    script = write_script(tmp_path, "cli.py", "import lib\nlib.new_helper()\n", repo)
    code, out, _ = run_reach(capsys, repo, command_for(py, script))
    assert code == 0
    assert re.search(r"lib\.py: 3 of 3 changed lines run", out), out
    assert verdict_line(out) == "REACH: PASS"
    assert_no_pth(py)


def test_coverage_missing_in_interpreter_is_skip(tmp_path, capsys):
    """Adversarial where: an environment without coverage runs the command
    unmeasured and the empty measurement reads as a finding or a pass."""
    py = make_venv(tmp_path / "bare_venv", "--without-pip")
    repo = lib_repo(tmp_path)
    marker = tmp_path / "ran.marker"
    script = write_script(
        tmp_path, "cli.py", f"open({posix(marker)!r}, 'w').close()\n", repo
    )
    code, out, _ = run_reach(capsys, repo, command_for(py, script), py)
    assert code == 0
    assert verdict_line(out).startswith("REACH: SKIP"), out
    assert_no_pth(py)


def test_run_and_report_together_exit_1(tmp_path, capsys):
    """Adversarial where: both a command to run and a finished report are
    accepted and one silently wins; they are exclusive and a bad argument
    exits 1."""
    repo = lib_repo(tmp_path)
    report = tmp_path / "cov.info"
    report.write_text("SF:lib.py\nDA:5,1\nend_of_record\n")
    code = reach.run(
        ["--run", "echo hi", "--report", str(report), "--diff", RANGE, "--repo", str(repo)]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "--run" in captured.err and "--report" in captured.err
    assert "unknown argument" not in captured.err
    assert "REACH:" not in captured.out


def test_unknown_lang_exits_1(tmp_path, capsys):
    """Adversarial where: a language other than python or node falls through to
    one of the routes instead of being rejected as a bad argument."""
    repo = lib_repo(tmp_path)
    code = reach.run(
        ["--run", "echo hi", "--lang", "cobol", "--diff", RANGE, "--repo", str(repo)]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "--lang" in captured.err
    assert "unknown argument" not in captured.err
    assert "REACH:" not in captured.out


def _node_tool(args):
    if shutil.which("npx") is None:
        return None
    return subprocess.run(
        ["npx", "--no-install", "c8", *args],
        capture_output=True,
        text=True,
        shell=(os.name == "nt"),
    )


def _c8_available():
    try:
        proc = _node_tool(["--version"])
    except OSError:
        return False
    return proc is not None and proc.returncode == 0


C8 = _c8_available()
JS_FIRST = "exports.old = () => 1;\n"
JS_SECOND = (
    JS_FIRST
    + "exports.used = () => {\n"
    + "  return 2;\n"
    + "};\n"
    + "exports.dead = () => {\n"
    + "  return 3;\n"
    + "};\n"
)


@pytest.mark.skipif(not C8, reason="npx --no-install c8 is not available")
def test_node_run_names_the_uncalled_function(tmp_path, capsys):
    """Adversarial where: the Node route reads the LCOV report c8 wrote but
    misses the dead function, or treats a run with a never-called export as
    a pass."""
    repo = make_repo(tmp_path, {"lib.js": JS_FIRST}, {"lib.js": JS_SECOND})
    (repo / "cli.js").write_text("require('./lib').used();\n", encoding="utf-8")
    code, out, _ = run_reach(capsys, repo, "node cli.js", lang="node")
    assert code == 0
    assert verdict_line(out) == "REACH: FINDING"
    assert re.search(r"lib\.js: \d of \d changed lines run", out), out
    assert re.search(r"^run exit: 0$", out, re.M), out


@pytest.mark.skipif(
    shutil.which("npx") is None or shutil.which("node") is None or C8,
    reason="needs node and npx with c8 absent",
)
def test_node_run_without_c8_installed_is_skip(tmp_path, capsys):
    """Adversarial where: a missing c8 makes the command run unmeasured and the
    empty measurement read as a finding or a pass."""
    repo = make_repo(tmp_path, {"lib.js": JS_FIRST}, {"lib.js": JS_SECOND})
    (repo / "cli.js").write_text("require('./lib').used();\n", encoding="utf-8")
    code, out, _ = run_reach(capsys, repo, "node cli.js", lang="node")
    assert code == 0
    assert verdict_line(out).startswith("REACH: SKIP"), out
