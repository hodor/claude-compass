"""The suite-wide real-vault guard in `conftest.py`: a write the capture or
station code aims at the repository's own vault is blocked and recorded, so a
test that leaks into the real station log, capture files or capture state
fails instead of passing quietly.

The leak it closes: an event whose project directory holds no `.compass` makes
the vault lookup climb from the working directory, and inside this repository
that ends at the real vault.
"""

import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import capturelib  # noqa: E402
import stationlib  # noqa: E402
from commands import capture_signal  # noqa: E402

REAL_VAULT = Path(__file__).resolve().parents[3] / ".compass"
REPORT = "## Test Report\n\n### Mode\nPre-build\n\nTASK-346\n"


def test_writes_aimed_at_the_real_vault_are_blocked_and_recorded(real_vault_guard):
    stationlib.append_row(REAL_VAULT, {"station": "tester-pre", "task": "TASK-1"})
    capturelib.save_state(REAL_VAULT, {"signals": []})
    assert len(real_vault_guard) == 2
    real_vault_guard.clear()


def test_write_into_a_temp_vault_passes_through(real_vault_guard, tmp_path):
    stationlib.append_row(tmp_path / ".compass", {"station": "tester-pre", "task": "TASK-1"})
    lines = (tmp_path / ".compass" / "meta" / "station-log.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["task"] for x in lines] == ["TASK-1"]
    assert real_vault_guard == []


def test_event_with_a_bare_project_dir_and_cwd_in_the_repo_is_caught(
    real_vault_guard, monkeypatch, tmp_path
):
    """Adversarial where: the leak of a hook event whose project directory has
    no vault, run from a working directory inside this repository. The guard
    sees the capture state write it makes, and it never reaches the real
    vault."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("COMPASS_WORKER_SESSION", raising=False)
    monkeypatch.chdir(REAL_VAULT.parent / "plugin" / "cli")
    event = {"agent_type": "tester", "agent_id": "isolation-probe", "last_assistant_message": REPORT}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
    with redirect_stdout(io.StringIO()):
        assert capture_signal.run(["--hook"]) == 0
    assert any(item.startswith("save_state(") for item in real_vault_guard)
    real_vault_guard.clear()
