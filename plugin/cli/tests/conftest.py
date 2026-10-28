"""Suite-wide fixtures.

No test starts or queries a real VS Code or Cursor: `code` and `cursor` are
hidden from `shutil.which` unless a test installs its own lookup (as
`test_review_vscode.py` does), so the VS Code family review surfaces read as
not set up on every machine.
"""

import shutil
from pathlib import Path

import pytest

HIDDEN_EDITORS = {"code", "cursor"}


@pytest.fixture(autouse=True)
def no_real_editors(monkeypatch):
    real_which = shutil.which

    def which(cmd, *args, **kwargs):
        if Path(str(cmd)).stem.lower() in HIDDEN_EDITORS:
            return None
        return real_which(cmd, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", which)
