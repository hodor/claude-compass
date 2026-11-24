"""Post-build tests for the Node mode of planted.py: defect classes the implementation introduced.

Adversarial themes: a Node command with no time bound that hangs the whole probe;
a missing or failing npm that raises a traceback or strands a half-built folder;
the npm prefix variable spelled in another case or leaking out of the Node
environment into the Python path; seeded files committed with CRLF; a server
that crashes on a request shape the driver never sends; a folder name holding
a space or non-ASCII text that breaks the npm or node command line.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
VERIFICATION_DIR = TESTS_DIR.parent
REPO_ROOT = VERIFICATION_DIR.parents[1]
OVERHEAD_DIR = REPO_ROOT / "bench" / "overhead"

for _path in (OVERHEAD_DIR, VERIFICATION_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import planted  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
HAS_NODE = shutil.which("node") is not None and shutil.which("npm") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node or npm is not on PATH")


def run_node(argv, cwd, *, stdin=None, timeout=60):
    return subprocess.run(
        argv, cwd=cwd, capture_output=True, input=stdin, timeout=timeout,
        creationflags=NO_WINDOW,
    )


def make_fake_npm(folder, *, body):
    """A launcher that stands in for npm: `body` is Python source run with npm's arguments."""
    script = folder / "fake_npm.py"
    script.write_text("import sys\nargs = sys.argv[1:]\n" + body, encoding="utf-8")
    if sys.platform == "win32":
        launcher = folder / "fake_npm.cmd"
        launcher.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        launcher = folder / "fake_npm"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        launcher.chmod(0o755)
    return str(launcher)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("tally node post project")
    if not HAS_NODE:
        pytest.skip("node or npm is not on PATH")
    try:
        return planted.build(root, repo_root=REPO_ROOT, lang="node")
    except planted.ProbeError as error:
        pytest.skip(f"c8 could not be installed: {error}")


# ------------------------------------------------------------- unbounded commands


def test_run_command_has_a_time_bound_or_turns_a_timeout_into_a_probe_error(monkeypatch, tmp_path):
    """Adversarial where: a node child that never exits (a driver whose server errors and
    leaves a request open) blocks the probe forever, because the subprocess call has no
    timeout, or its TimeoutExpired escapes as a traceback instead of a ProbeError."""
    seen = {}

    def hang(argv, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout") or 0)

    monkeypatch.setattr(planted.subprocess, "run", hang)
    with pytest.raises(planted.ProbeError):
        planted._run(["node", "scripts/drive.js"], tmp_path, what="driver", check=False)
    assert seen["timeout"] is not None


# --------------------------------------------------------------- npm availability


def test_build_without_npm_on_path_refuses_cleanly_and_leaves_the_folder_missing(
    monkeypatch, tmp_path
):
    """Adversarial where: npm missing from PATH raises a bare OSError/TypeError traceback, or
    leaves a half-written project folder the next run refuses as non-empty."""
    monkeypatch.setattr(planted.shutil, "which", lambda name, *a, **k: None)
    root = tmp_path / "fresh"
    with pytest.raises(planted.ProbeError, match="npm"):
        planted.build(root, repo_root=REPO_ROOT, lang="node")
    assert not root.exists()


def test_build_without_npm_restores_an_existing_empty_folder(monkeypatch, tmp_path):
    """Adversarial where: the cleanup after a failed Node build removes the empty folder the
    caller passed in, so a second run into the same --root fails on a missing path."""
    monkeypatch.setattr(planted.shutil, "which", lambda name, *a, **k: None)
    root = tmp_path / "given"
    root.mkdir()
    with pytest.raises(planted.ProbeError):
        planted.build(root, repo_root=REPO_ROOT, lang="node")
    assert root.is_dir() and list(root.iterdir()) == []


def test_main_without_npm_exits_one_with_a_message_and_no_traceback(monkeypatch, tmp_path, capsys):
    """Adversarial where: main() lets the ProbeError from a missing npm propagate as a
    traceback instead of returning the build-failed exit code."""
    monkeypatch.setattr(planted.shutil, "which", lambda name, *a, **k: None)
    code = planted.main(["--lang", "node", "--root", str(tmp_path / "p")])
    err = capsys.readouterr().err
    assert code == 1
    assert "npm" in err and "Traceback" not in err


# --------------------------------------------------------------- c8 install failing


def test_failed_c8_install_raises_probe_error_and_strands_nothing(monkeypatch, tmp_path):
    """Adversarial where: npm exits non-zero after creating part of the .tools folder, and the
    half-built folder (with the partial install and no seed) stays behind for the next run
    to refuse as non-empty."""
    fake = make_fake_npm(
        tmp_path,
        body=(
            "from pathlib import Path\n"
            "prefix = Path(args[args.index('--prefix') + 1])\n"
            "(prefix / 'lib').mkdir(parents=True)\n"
            "print('registry unreachable', file=sys.stderr)\n"
            "sys.exit(3)\n"
        ),
    )
    monkeypatch.setattr(planted, "_npm", lambda: fake)
    root = tmp_path / "proj"
    with pytest.raises(planted.ProbeError, match="registry unreachable"):
        planted.build(root, repo_root=REPO_ROOT, lang="node")
    assert not root.exists()


def test_failed_c8_install_into_a_given_empty_folder_leaves_it_empty(monkeypatch, tmp_path):
    """Adversarial where: the failed install leaves `.tools` inside the caller's --root, so the
    retry is refused as `not empty`."""
    fake = make_fake_npm(
        tmp_path,
        body=(
            "from pathlib import Path\n"
            "prefix = Path(args[args.index('--prefix') + 1])\n"
            "(prefix / 'lib').mkdir(parents=True)\n"
            "sys.exit(1)\n"
        ),
    )
    monkeypatch.setattr(planted, "_npm", lambda: fake)
    root = tmp_path / "given"
    root.mkdir()
    with pytest.raises(planted.ProbeError):
        planted.build(root, repo_root=REPO_ROOT, lang="node")
    assert list(root.iterdir()) == []


def test_main_reports_a_failed_c8_install_as_build_failed(monkeypatch, tmp_path, capsys):
    """Adversarial where: a failing install exits through a traceback, or exits 0 or 2 (the
    refusal code) instead of the build-failed code 1."""
    fake = make_fake_npm(tmp_path, body="print('boom', file=sys.stderr)\nsys.exit(4)\n")
    monkeypatch.setattr(planted, "_npm", lambda: fake)
    code = planted.main(["--lang", "node", "--root", str(tmp_path / "p")])
    err = capsys.readouterr().err
    assert code == 1
    assert "build failed" in err and "Traceback" not in err


# ------------------------------------------------------------ environment handling


def test_node_env_removes_every_casing_of_the_prefix_variable(monkeypatch, tmp_path):
    """Adversarial where: a caller's `NPM_CONFIG_PREFIX` (or mixed-case spelling) survives next
    to the lower-case one the probe sets, so npm and c8 resolve a different global folder
    depending on the platform's case rules."""
    parent = {"PATH": "x", "NPM_CONFIG_PREFIX": "/elsewhere", "Npm_Config_Prefix": "/also"}
    monkeypatch.setattr(planted, "_clean_env", lambda: dict(parent))
    env = planted._node_env(tmp_path)
    spellings = [key for key in env if key.upper() == "NPM_CONFIG_PREFIX"]
    assert spellings == ["npm_config_prefix"]
    assert env["npm_config_prefix"] == str(tmp_path / ".tools")


def test_node_env_does_not_leak_the_prefix_into_the_process_or_the_python_path(
    monkeypatch, tmp_path
):
    """Adversarial where: building the Node environment mutates os.environ, so the Python
    probe that runs afterwards in the same process installs and tests under the c8 prefix."""
    monkeypatch.delenv("npm_config_prefix", raising=False)
    monkeypatch.delenv("NPM_CONFIG_PREFIX", raising=False)
    planted._node_env(tmp_path)
    assert not any(key.upper() == "NPM_CONFIG_PREFIX" for key in os.environ)
    assert not any(key.upper() == "NPM_CONFIG_PREFIX" for key in planted._clean_env())


def test_python_suite_run_after_a_node_run_carries_no_npm_prefix(monkeypatch, tmp_path):
    """Adversarial where: run_suite(lang="python") reuses the Node environment object, so the
    pytest child sees npm_config_prefix pointing into another project."""
    monkeypatch.delenv("npm_config_prefix", raising=False)
    monkeypatch.delenv("NPM_CONFIG_PREFIX", raising=False)
    seen = []

    def capture(argv, cwd, *, what, check=True, env=None):
        seen.append(env)
        return subprocess.CompletedProcess(argv, 0, stdout="1 passed\n", stderr="")

    monkeypatch.setattr(planted, "_run", capture)
    planted.run_suite(tmp_path, lang="node")
    planted.run_suite(tmp_path)
    node_env, python_env = seen
    assert node_env is not None and "npm_config_prefix" in node_env
    effective = python_env if python_env is not None else planted._clean_env()
    assert not any(key.upper() == "NPM_CONFIG_PREFIX" for key in effective)


@pytest.mark.parametrize("function", ["build", "run_suite", "run_checks"])
@pytest.mark.parametrize("bad", ["Node", "ruby", "", None])
def test_entry_points_reject_an_unknown_language_before_any_work(function, bad, tmp_path):
    """Adversarial where: a misspelt language ("Node", None) falls into the Python branch and
    builds or runs the wrong project, or writes into the folder before failing."""
    target = tmp_path / "t"
    if function == "build":
        call = lambda: planted.build(target, repo_root=REPO_ROOT, lang=bad)  # noqa: E731
    elif function == "run_suite":
        call = lambda: planted.run_suite(target, lang=bad)  # noqa: E731
    else:
        call = lambda: planted.run_checks(target, cli=target / "cli", lang=bad)  # noqa: E731
    with pytest.raises(ValueError):
        call()
    assert not target.exists()


def test_cli_rejects_judge_with_node_and_a_wrong_case_language(monkeypatch, tmp_path):
    """Adversarial where: --judge on the Node project starts a paid headless session against a
    project the judge was never written for, or `--lang Node` is accepted by case folding."""
    built_roots = []
    monkeypatch.setattr(planted, "build", lambda root, **kw: built_roots.append(root))
    for argv in (["--lang", "node", "--judge"], ["--lang", "Node"], ["--lang", ""]):
        with pytest.raises(SystemExit) as stopped:
            planted.main([*argv, "--root", str(tmp_path / "p")])
        assert stopped.value.code == 2
    assert built_roots == []


# ------------------------------------------------------------------- built project


@needs_node
def test_every_committed_node_file_has_lf_line_endings(built):
    """Adversarial where: a seeded Node file is committed with CRLF (the writer converts
    newlines, or git's autocrlf rewrites it), so the changed-line numbers the reach report
    counts differ from the diff's and the planted failure moves."""
    names = subprocess.run(
        ["git", "-C", str(built), "ls-files"], capture_output=True, text=True, check=True,
        creationflags=NO_WINDOW,
    ).stdout.split()
    crlf = []
    for name in names:
        blob = subprocess.run(
            ["git", "-C", str(built), "show", f"HEAD:{name}"], capture_output=True, check=True,
            creationflags=NO_WINDOW,
        ).stdout
        if b"\r" in blob:
            crlf.append(name)
    assert names and crlf == []


@needs_node
def test_working_tree_node_files_equal_their_committed_blobs(built):
    """Adversarial where: the files on disk differ from the committed blobs (a text-mode write
    on Windows adds CR), so a command run from the working tree sees different line numbers
    than the diff the reach report reads."""
    files = [
        path
        for pattern in ("src/*.js", "bin/*.js", "scripts/*.js", "tests/*.js")
        for path in built.glob(pattern)
    ]
    assert len(files) >= 5
    for path in files:
        name = path.relative_to(built).as_posix()
        blob = subprocess.run(
            ["git", "-C", str(built), "show", f"HEAD:{name}"], capture_output=True, check=True,
            creationflags=NO_WINDOW,
        ).stdout
        assert path.read_bytes() == blob, name


@needs_node
def test_build_in_a_folder_with_a_space_installs_c8_and_runs_the_suite(built):
    """Adversarial where: the folder holding a space is split by the npm launcher (a .cmd file
    on Windows), so c8 lands in the wrong folder and every later check cannot find it."""
    assert " " in str(built)
    assert any((built / ".tools").rglob("c8*"))
    green, line = planted.run_suite(built, lang="node")
    assert green, line


@needs_node
def test_server_answers_a_missing_text_parameter_with_an_empty_ok_body(built):
    """Adversarial where: `/top` with no `text` throws inside the route (null passed to
    toLowerCase) and the answer is a dropped connection instead of an empty 200."""
    script = (
        "const http=require('node:http');"
        "const {createServer}=require('./src/server.js');"
        "const s=createServer();"
        "s.listen(0,'127.0.0.1',()=>{"
        "const p=s.address().port;"
        "http.get(`http://127.0.0.1:${p}/top`,{agent:false},(r)=>{"
        "let b='';r.on('data',c=>b+=c);"
        "r.on('end',()=>{console.log(r.statusCode+'|'+b);s.close();});});});"
    )
    done = run_node(["node", "-e", script], built)
    assert done.returncode == 0, done.stderr
    assert done.stdout.decode().strip() == "200|"


@needs_node
def test_server_answers_an_unknown_path_with_404_and_keeps_running(built):
    """Adversarial where: an unknown route falls through to a handler that throws or answers
    200 with the top word of nothing."""
    script = (
        "const http=require('node:http');"
        "const {createServer}=require('./src/server.js');"
        "const s=createServer();"
        "s.listen(0,'127.0.0.1',()=>{"
        "const p=s.address().port;"
        "http.get(`http://127.0.0.1:${p}/nope?text=a`,{agent:false},(r)=>{"
        "r.resume();r.on('end',()=>{console.log(r.statusCode);s.close();});});});"
    )
    done = run_node(["node", "-e", script], built)
    assert done.returncode == 0, done.stderr
    assert done.stdout.decode().strip() == "404"


@needs_node
def test_server_survives_a_request_target_that_is_not_a_valid_url(built):
    """Adversarial where: the handler builds `new URL(req.url, base)` outside any guard, so a
    request line such as `GET // HTTP/1.1` throws in the handler and kills the process
    instead of answering."""
    script = (
        "const net=require('node:net');"
        "const {createServer}=require('./src/server.js');"
        "const s=createServer();"
        "s.on('error',()=>{});"
        "s.listen(0,'127.0.0.1',()=>{"
        "const p=s.address().port;"
        "const c=net.connect(p,'127.0.0.1',()=>c.write('GET // HTTP/1.1\\r\\nHost: x\\r\\n"
        "Connection: close\\r\\n\\r\\n'));"
        "let b='';c.on('data',d=>b+=d);"
        "c.on('close',()=>{console.log(b.split(' ')[1]);s.close();});"
        "c.on('error',()=>{s.close();});});"
    )
    done = run_node(["node", "-e", script], built)
    assert done.returncode == 0, done.stderr.decode()[-300:]
    assert done.stdout.decode().strip() in {"200", "400", "404"}


@needs_node
def test_command_line_keeps_non_ascii_words_and_lowercases_them(built):
    """Adversarial where: argv or stdout is decoded as a legacy code page on Windows, so an
    accented word prints as mojibake or is not lower-cased by `top`."""
    done = run_node(["node", "bin/tally.js", "top", "ÉCOLE école x"], built)
    assert done.returncode == 0, done.stderr
    assert done.stdout.decode("utf-8").strip() == "école"


@needs_node
@pytest.mark.parametrize("args", [[], ["nonsense"], ["constructor", "a b"], ["__proto__"]])
def test_command_line_refuses_a_non_command_with_usage_and_exit_two(built, args):
    """Adversarial where: a name that exists on the core module's prototype (`constructor`,
    `__proto__`) or no argument at all is dispatched as a command and throws or exits 0."""
    done = run_node(["node", "bin/tally.js", *args], built)
    assert done.returncode == 2
    assert b"usage" in done.stderr and done.stdout == b""


@needs_node
def test_driver_exits_nonzero_within_a_bound_when_the_route_throws(built, tmp_path):
    """Adversarial where: a server route that throws leaves the driver's request open forever,
    so the probe waits on a child that never exits instead of seeing a failing exit code."""
    copy = tmp_path / "copy"
    shutil.copytree(built, copy, ignore=shutil.ignore_patterns(".tools", ".git", ".claude"))
    core = copy / "src" / "core.js"
    core.write_bytes(
        core.read_bytes() + b'\nexports.top = () => { throw new Error("planted failure"); };\n'
    )
    try:
        done = run_node(["node", "scripts/drive.js"], copy, timeout=30)
    except subprocess.TimeoutExpired:
        pytest.fail("scripts/drive.js hung when the route threw")
    assert done.returncode != 0
