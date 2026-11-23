"""Suite-wide fixtures.

No test starts or queries a real VS Code or Cursor: `code` and `cursor` are
hidden from `shutil.which` unless a test installs its own lookup (as
`test_review_vscode.py` does), so the VS Code family review surfaces read as
not set up on every machine.

No test writes into the repository's own vault: the station log, the subagent
capture files and the capture state are write-guarded, and a test that reaches
one fails at teardown. A project directory with no `.compass` makes the vault
lookup climb from the working directory, which inside this repository ends at
the real vault.
"""

import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import capturelib  # noqa: E402
import stationlib  # noqa: E402
from commands import capture_signal  # noqa: E402

HIDDEN_EDITORS = {"code", "cursor"}
REAL_VAULT = Path(__file__).resolve().parents[3] / ".compass"


@pytest.fixture(autouse=True)
def no_real_editors(monkeypatch):
    real_which = shutil.which

    def which(cmd, *args, **kwargs):
        if Path(str(cmd)).stem.lower() in HIDDEN_EDITORS:
            return None
        return real_which(cmd, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", which)


def _in_real_vault(vault_root):
    try:
        return Path(vault_root).resolve().is_relative_to(REAL_VAULT)
    except (OSError, ValueError):
        return False


@pytest.fixture(autouse=True)
def real_vault_guard(monkeypatch):
    """Block and record every write the capture and station code aims at the
    repository's own vault. Yields the list of blocked writes; a test that
    expects some clears it, any entry left fails the test at teardown."""
    blocked = []

    def guarded(name, real, vault_arg):
        def wrapper(*args, **kwargs):
            if _in_real_vault(args[vault_arg]):
                blocked.append(f"{name}({args[vault_arg]})")
                return None
            return real(*args, **kwargs)
        return wrapper

    monkeypatch.setattr(stationlib, "append_row", guarded("append_row", stationlib.append_row, 0))
    monkeypatch.setattr(capturelib, "save_state", guarded("save_state", capturelib.save_state, 0))
    monkeypatch.setattr(
        capture_signal, "_write_capture", guarded("_write_capture", capture_signal._write_capture, 0)
    )
    yield blocked
    if blocked:
        pytest.fail("test wrote into the repository's real vault: " + "; ".join(blocked))
