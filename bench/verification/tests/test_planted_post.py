"""Post-build tests for planted.py: defect classes the implementation introduced.

Adversarial themes: a failed build that strands a half-written folder the next
run refuses; line-ending rewrites of the seeded files under a user's global git
config; command strings that break on a path holding a space; a judge session
whose result event is missing or carries a non-string; requirement-line shapes
a regex reads differently from a person; a main() that raises a traceback, or
leaks or deletes the wrong scratch folder, instead of returning an exit code.
"""

import json
import os
import subprocess
import sys
import types
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
CORRECT_ROWS = {"O-3": "met", "K-1": "met", "C-1": "met", "C-2": "met", "C-3": "missing"}


def make_fake_uv(folder, *, fail_pip):
    """A `uv` stand-in: `venv` makes the folder, `pip` succeeds or exits 3."""
    script = folder / "fake_uv.py"
    script.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        f"FAIL_PIP = {fail_pip!r}\n"
        "args = sys.argv[1:]\n"
        "if args[0] == 'venv':\n"
        "    target = Path(args[-1])\n"
        "    target.mkdir(parents=True)\n"
        "    (target / 'pyvenv.cfg').write_text('home = x\\n')\n"
        "    sys.exit(0)\n"
        "if FAIL_PIP:\n"
        "    print('pip exploded', file=sys.stderr)\n"
        "    sys.exit(3)\n",
        encoding="utf-8",
    )
    if sys.platform == "win32":
        wrapper = folder / "fake_uv.cmd"
        wrapper.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        wrapper = folder / "fake_uv"
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        wrapper.chmod(0o755)
    return str(wrapper)


def git(cwd, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=env,
                          creationflags=NO_WINDOW)
    return done.stdout.strip()


# ------------------------------------------------------------------ build


def test_build_with_an_unrunnable_uv_raises_probe_error_and_writes_nothing(tmp_path):
    """Adversarial where: a missing uv escapes as a raw OSError, or the failed build leaves
    files behind that make the folder non-empty for the next attempt."""
    root = tmp_path / "project"
    with pytest.raises(planted.ProbeError):
        planted.build(root, repo_root=REPO_ROOT, uv=str(tmp_path / "no-such-uv"))
    assert not root.exists() or not any(root.iterdir())


def test_a_failed_pip_install_leaves_a_folder_a_second_build_accepts(tmp_path):
    """Adversarial where: the venv written before a failed install stays in the folder, so
    the retry is Refused as `not empty` and the person must delete by hand."""
    root = tmp_path / "project"
    uv = make_fake_uv(tmp_path, fail_pip=True)
    with pytest.raises(planted.ProbeError, match="pip"):
        planted.build(root, repo_root=REPO_ROOT, uv=uv)
    try:
        planted._check_target(root)
    except planted.Refused as error:
        pytest.fail(f"a retry in the same folder is refused after a failed build: {error}")


def test_build_refuses_a_file_as_the_target(tmp_path):
    """Adversarial where: a path naming a file passes the emptiness check and crashes later
    with a raw NotADirectoryError."""
    target = tmp_path / "afile"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(planted.Refused):
        planted.build(target, repo_root=REPO_ROOT, uv="unused")
    assert target.read_text(encoding="utf-8") == "x"


def test_build_under_a_work_tree_with_missing_parents_refuses_and_creates_nothing(tmp_path):
    """Adversarial where: the work-tree probe looks only at an existing folder, so a deep
    missing path inside a repository is created and written into."""
    git(tmp_path, "init", "-q")
    target = tmp_path / "a" / "b" / "c"
    with pytest.raises(planted.Refused):
        planted.build(target, repo_root=REPO_ROOT, uv="unused")
    assert not (tmp_path / "a").exists()


def test_seeded_files_stay_lf_in_index_and_tree_under_a_global_autocrlf_true(tmp_path, monkeypatch):
    """Adversarial where: a user's global core.autocrlf=true rewrites the seeded sources to
    CRLF, so the planted one-line replacement or the diff line numbers shift."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_text("[core]\n\tautocrlf = true\n", encoding="utf-8")
    for name in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(name, str(home))
    monkeypatch.delenv("GIT_CONFIG_GLOBAL", raising=False)
    if git(tmp_path, "config", "--global", "core.autocrlf") != "true":
        pytest.skip("this git does not read the redirected global config")
    uv = make_fake_uv(tmp_path, fail_pip=False)
    project = planted.build(tmp_path / "project", repo_root=REPO_ROOT, uv=uv)
    eol = git(project, "ls-files", "--eol").splitlines()
    assert eol and not [line for line in eol if "crlf" in line], eol
    assert git(project, "status", "--porcelain") == ""
    assert b"\r\n" not in (project / "tally" / "core.py").read_bytes()


# ------------------------------------------------------- command quoting


def test_reach_and_ablate_commands_quote_a_venv_python_path_holding_a_space(tmp_path):
    """Adversarial where: the venv interpreter is spliced into the shell command unquoted,
    so a folder like `my probe` splits the path at the space."""
    project = tmp_path / "my probe"
    python = planted.venv_python(project)
    reach = planted._check_command(project, Path("cli") / "compass", "reach", "TASK-001", "abc")
    run_command = reach[reach.index("--run") + 1]
    assert run_command.startswith(f'"{python}" -m tally count')
    assert run_command.endswith('"one two three"')
    assert str(reach[reach.index("--python") + 1]) == str(python)
    assert reach[reach.index("--diff") + 1] == "abc^1..abc"
    ablate = planted._check_command(project, Path("cli") / "compass", "ablate", "TASK-002", "abc")
    assert ablate[ablate.index("--cmd") + 1] == f'"{python}" -m pytest -v {{tests}}'


# ----------------------------------------------------------------- judge


def fake_session(monkeypatch, events, status=None):
    result = types.SimpleNamespace(status=status or planted.launch.DONE, events=events, returncode=0)
    monkeypatch.setattr(planted.launch, "run_session", lambda *a, **k: result)


REPLY = "\n".join(f"REQ {row}: {status}" for row, status in CORRECT_ROWS.items()) + "\n"


@pytest.mark.parametrize("result_field", [None, ["REQ C-3: missing"], 7, {"text": REPLY}])
def test_judge_raises_when_the_result_event_holds_no_string_reply(monkeypatch, tmp_path, result_field):
    """Adversarial where: a result event whose `result` is null, a list or a number is parsed
    as text, crashes with a TypeError, or scores as an empty reply."""
    fake_session(monkeypatch, [{"type": "result", "result": result_field, "num_turns": 2}])
    with pytest.raises(planted.JudgeError):
        planted.judge(tmp_path, repo_root=REPO_ROOT)


def test_judge_raises_when_the_session_has_no_result_event_even_if_the_assistant_wrote_rows(monkeypatch, tmp_path):
    """Adversarial where: rows are read from assistant messages of a session that never
    produced a result, scoring a cut-off run."""
    events = [{"type": "assistant", "message": {"content": [{"type": "text", "text": REPLY}]}}]
    fake_session(monkeypatch, events)
    with pytest.raises(planted.JudgeError):
        planted.judge(tmp_path, repo_root=REPO_ROOT)


def test_judge_reads_only_the_last_result_event(monkeypatch, tmp_path):
    """Adversarial where: the first result event of a resumed session is scored instead of
    the last, or rows from an earlier result mix into the final one."""
    events = [
        {"type": "result", "result": "REQ C-3: met\n", "num_turns": 1},
        {"type": "result", "result": "REQ C-3: partial\n", "num_turns": 4},
    ]
    fake_session(monkeypatch, events)
    got = planted.judge(tmp_path, repo_root=REPO_ROOT)
    assert got["statuses"] == {"C-3": "partial"}
    assert got["turns"] == 4


@pytest.mark.parametrize("turns", ["3", 3.5, None])
def test_judge_turns_is_none_unless_the_result_holds_an_integer(monkeypatch, tmp_path, turns):
    """Adversarial where: a string or float num_turns is passed through to the json record."""
    fake_session(monkeypatch, [{"type": "result", "result": REPLY, "num_turns": turns}])
    assert planted.judge(tmp_path, repo_root=REPO_ROOT)["turns"] is None


# ------------------------------------------------------------ parse_judge


@pytest.mark.parametrize("text, expected", [
    ("```\nREQ C-3: missing\n```\n", {"C-3": "missing"}),
    ("  REQ C-3: missing\n", {}),
    ("- REQ C-3: missing\n", {}),
    ("As shown, REQ C-3: missing holds.\n", {}),
    ("REQ C-3: missing\r\nREQ O-3: met\r\n", {"C-3": "missing", "O-3": "met"}),
    ("REQ C-3:\nmet\n", {}),
    ("REQ C-3: \n", {}),
    ("req c-3: missing\n", {}),
    ("REQ C-12: Partial.\n", {"C-12": "partial"}),
    ("REQ <id>: met|partial\n", {}),
])
def test_parse_judge_takes_only_a_line_that_starts_with_a_well_formed_row(text, expected):
    """Adversarial where: a row quoted inside prose, indented, bulleted or half-written is
    read as the judge's answer, or a CRLF reply loses its rows."""
    assert planted.parse_judge(text) == expected


# ---------------------------------------------------- record and rerun lines


@pytest.mark.parametrize("stdout, expected", [
    ("record: a.json\r\nrecord: b.json\r\n", "b.json"),
    ("no record here\n", None),
    ("  record: indented.json\n", None),
    ("tail\nrecord: .compass/tmp/evidence/TASK-001/reach.json\n", ".compass/tmp/evidence/TASK-001/reach.json"),
])
def test_record_line_is_the_last_line_starting_record(stdout, expected):
    """Adversarial where: CRLF output keeps a carriage return in the path, or a quoted
    indented line is taken as the record."""
    assert planted._record_line(stdout) == expected


@pytest.mark.parametrize("stdout, expected", [
    ("match\nrecorded exit code: 0\n", "match"),
    ("mismatch\nrecorded exit code: 0\n", "mismatch"),
    ("", "error"),
    ("matched\n", "error"),
    ("compass evidence: no such record\n", "error"),
])
def test_rerun_status_is_the_first_word_only_when_it_is_match_or_mismatch(monkeypatch, tmp_path, stdout, expected):
    """Adversarial where: an error message that contains `match` is read as a match, or
    empty output is read as one."""
    done = types.SimpleNamespace(stdout=stdout, stderr="", returncode=0)
    monkeypatch.setattr(planted, "_run", lambda *a, **k: done)
    assert planted._rerun(tmp_path, Path("cli"), "r.json") == expected


# ------------------------------------------------------------------- main


def stub_main(monkeypatch, *, green=True, rows=None, build=None, judge=None):
    def default_build(root, **kwargs):
        Path(root).mkdir(parents=True, exist_ok=True)
        (Path(root) / "marker.txt").write_text("x", encoding="utf-8")
        return Path(root)

    def checks(project, *, cli):
        out = []
        for letter, task in planted.TASKS:
            for check in ("reach", "ablate"):
                out.append({"letter": letter, "task": task, "check": check,
                            "verdict": planted.EXPECTED[check][letter],
                            "expected": planted.EXPECTED[check][letter],
                            "record": f"r/{task}-{check}.json", "rerun": "match"})
        return rows(out) if rows else out

    monkeypatch.setattr(planted, "build", build or default_build)
    monkeypatch.setattr(planted, "run_suite", lambda project: (green, "1 passed"))
    monkeypatch.setattr(planted, "run_checks", checks)
    if judge:
        monkeypatch.setattr(planted, "judge", judge)


def use_temp_folder(monkeypatch, tmp_path):
    scratch = tmp_path / "tally-probe-fixed"
    scratch.mkdir()
    monkeypatch.setattr(planted.tempfile, "mkdtemp", lambda prefix="": str(scratch))
    return scratch


def test_main_removes_its_own_temp_folder_only_when_every_check_passes(monkeypatch, tmp_path, capsys):
    """Adversarial where: a failing run deletes the folder holding the evidence, or a
    passing run leaves a read-only git folder behind."""
    scratch = use_temp_folder(monkeypatch, tmp_path)
    stub_main(monkeypatch)
    assert planted.main([]) == 0
    assert not scratch.exists()

    scratch = use_temp_folder(monkeypatch, tmp_path)
    stub_main(monkeypatch, green=False)
    assert planted.main([]) == 1
    assert scratch.exists()
    assert str(scratch) in capsys.readouterr().err


def test_main_never_removes_a_folder_given_with_root(monkeypatch, tmp_path):
    """Adversarial where: a passing run deletes the person's own --root folder."""
    root = tmp_path / "mine"
    stub_main(monkeypatch)
    assert planted.main(["--root", str(root)]) == 0
    assert (root / "marker.txt").exists()


def test_main_refuses_a_non_empty_root_with_exit_two_and_touches_nothing(monkeypatch, tmp_path, capsys):
    """Adversarial where: a refused build still runs the suite or checks, or exits 0 or 1."""
    root = tmp_path / "full"
    root.mkdir()
    (root / "keep.txt").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(planted, "run_suite", lambda project: pytest.fail("suite ran after a refusal"))
    assert planted.main(["--root", str(root)]) == 2
    assert "refused:" in capsys.readouterr().err
    assert [p.name for p in root.iterdir()] == ["keep.txt"]


def test_main_exits_one_when_a_check_printed_no_verdict(monkeypatch, tmp_path, capsys):
    """Adversarial where: a check whose output has no verdict line (None) compares equal to
    nothing but still ends in exit 0, or crashes the report."""
    def drop_verdict(rows):
        rows[0]["verdict"] = None
        rows[0]["record"] = ""
        rows[0]["rerun"] = "error"
        return rows

    stub_main(monkeypatch, rows=drop_verdict)
    assert planted.main(["--root", str(tmp_path / "p")]) == 1
    assert "reach A:" in capsys.readouterr().out


def test_main_reports_a_failed_judge_as_a_line_and_exit_one_with_null_judge_json(monkeypatch, tmp_path, capsys):
    """Adversarial where: a JudgeError escapes as a traceback after minutes of work, or the
    run exits 0 although the judge never answered."""
    def failing_judge(project, **kwargs):
        raise planted.JudgeError("no REQ line")

    stub_main(monkeypatch, judge=failing_judge)
    target = tmp_path / "out.json"
    assert planted.main(["--root", str(tmp_path / "p"), "--judge", "--json", str(target)]) == 1
    assert "4j: failed: no REQ line" in capsys.readouterr().out
    assert json.loads(target.read_text(encoding="utf-8"))["judge"] is None


def test_main_json_from_a_real_judge_holds_neither_reply_prose_nor_the_project_folder(monkeypatch, tmp_path):
    """Adversarial where: the json file carries the judge's answer text or the machine's
    folder, so a committed result page leaks them."""
    events = [{"type": "result", "result": "SECRETPROSE long analysis\n" + REPLY, "num_turns": 2}]
    fake_session(monkeypatch, events)
    stub_main(monkeypatch)
    root = tmp_path / "uniquefolder-xyz"
    target = tmp_path / "out.json"
    assert planted.main(["--root", str(root), "--judge", "--json", str(target)]) == 0
    text = target.read_text(encoding="utf-8")
    assert "SECRETPROSE" not in text
    assert "uniquefolder-xyz" not in text
    assert json.loads(text)["judge"]["statuses"]["C-3"] == "missing"


def test_main_returns_nonzero_instead_of_raising_when_the_build_fails(monkeypatch, tmp_path):
    """Adversarial where: a uv or git failure inside build surfaces as an uncaught ProbeError
    traceback, and the new temp folder is abandoned without a word."""
    def broken_build(root, **kwargs):
        raise planted.ProbeError("uv venv failed (exit 1): boom")

    scratch = use_temp_folder(monkeypatch, tmp_path)
    stub_main(monkeypatch, build=broken_build)
    code = planted.main([])
    assert isinstance(code, int) and code != 0
    assert scratch.exists()


def test_main_returns_nonzero_instead_of_raising_when_the_json_folder_is_missing(monkeypatch, tmp_path):
    """Adversarial where: --json into a folder that does not exist is found only after the
    whole run, as a FileNotFoundError that also skips the scratch-folder handling."""
    use_temp_folder(monkeypatch, tmp_path)
    stub_main(monkeypatch)
    code = planted.main(["--json", str(tmp_path / "nope" / "out.json")])
    assert isinstance(code, int) and code != 0


def test_remove_tree_deletes_a_folder_holding_read_only_files(tmp_path):
    """Adversarial where: the read-only flag git sets on object files makes the temp folder
    removal fail on Windows."""
    folder = tmp_path / "objects" / "ab"
    folder.mkdir(parents=True)
    frozen = folder / "cdef"
    frozen.write_text("x", encoding="utf-8")
    os.chmod(frozen, 0o444)
    planted._remove_tree(tmp_path / "objects")
    assert not (tmp_path / "objects").exists()
