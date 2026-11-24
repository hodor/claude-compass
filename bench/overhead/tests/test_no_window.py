"""Every process the bench starts opens no console window on Windows.

The bench runs headless builds for hours from a process that may have no
console of its own; a console program started from such a process without
CREATE_NO_WINDOW opens a window on the desktop. This test reads the source of
every bench module and the hook script, finds each `subprocess.run`,
`subprocess.Popen`, `subprocess.call`, `subprocess.check_call` and
`subprocess.check_output` call, and requires it to pass either a
`creationflags` keyword or a `**` mapping (`launch.NO_WINDOW` or
`launch._group_options()`).
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

import launch

HERE = Path(__file__).resolve().parents[1]
STARTERS = {"run", "Popen", "call", "check_call", "check_output"}


def _sources():
    return sorted([*HERE.glob("*.py"), *(HERE / "hooks").glob("*.py")])


def _unflagged_calls(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    missing = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in STARTERS):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "subprocess"):
            continue
        keywords = node.keywords
        if any(k.arg == "creationflags" for k in keywords) or any(k.arg is None for k in keywords):
            continue
        missing.append("%s:%d" % (path.name, node.lineno))
    return missing


def test_every_process_start_in_the_bench_passes_window_flags():
    """Adversarial where: one git, purge or answer-command call starts a
    console program bare, so a long pilot run flashes a window per call."""
    missing = [where for path in _sources() for where in _unflagged_calls(path)]
    assert missing == []


def test_the_scan_sees_a_bare_call(tmp_path):
    """Adversarial where: the scan above passes because it matches nothing."""
    sample = tmp_path / "sample.py"
    sample.write_text("import subprocess\nsubprocess.run(['git', 'status'])\n", encoding="utf-8")
    assert _unflagged_calls(sample) == ["sample.py:2"]


def test_no_window_mapping_carries_the_flag_on_windows(monkeypatch):
    if sys.platform != "win32":
        assert launch.NO_WINDOW == {}
        return
    assert launch.NO_WINDOW["creationflags"] & subprocess.CREATE_NO_WINDOW
