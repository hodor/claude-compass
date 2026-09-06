"""`compass hot-path` - report both hot-path surfaces against the cap.

Two distinct surfaces load at fixed points, and each is measured on its
own (conflating them would hide which one grew):

- The agent surface, what every spawned agent's `initialPrompt` loads:
  the root index, the active-tasks file, and the lessons surface
  `lessons/index.md` - the high-level index whose domain indexes agents
  grep and descend into. The full catalog stays the machine index behind
  `compass lessons`, off the hot path. This is the surface the 5,000-token
  cap binds; `validate` fails on a breach.
- The session-start surface, what the session-start rule tells the main
  session to read: the root index, the active-tasks file, `vision.md`,
  and the most recent handoff. Measured and reported so its cost is never
  invisible; no cap binds it yet.

Read-only; `validate` is what fails on a breach.
"""

import sys

import vaultlib

HOT_PATH_FILES = ["index.md", "active.md", "lessons/index.md"]
SESSION_START_FILES = ["index.md", "active.md", "vision.md"]
HOT_PATH_CAP = 5000


def _newest_handoff(vault_root):
    """The most recently modified handoff document, or None. Handoffs may
    sit flat in `handoffs/` or grouped in per-plan subdirectories."""
    handoffs = sorted(
        (vault_root / "handoffs").rglob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ) if (vault_root / "handoffs").is_dir() else []
    return handoffs[0] if handoffs else None


def measure(vault_root):
    """Token total of the agent surface - the set every spawned agent's
    `initialPrompt` loads, and the set the cap binds."""
    total = 0
    for rel in HOT_PATH_FILES:
        path = vault_root / rel
        if path.is_file():
            total += vaultlib.count_tokens(path.read_text(encoding="utf-8"))
    return total


def measure_session_start(vault_root):
    """`(total, files)` for the session-start surface - what the
    session-start rule has the main session read. `files` names the
    vault-relative paths that existed and were counted."""
    total = 0
    files = []
    for rel in SESSION_START_FILES:
        path = vault_root / rel
        if path.is_file():
            total += vaultlib.count_tokens(path.read_text(encoding="utf-8"))
            files.append(rel)
    handoff = _newest_handoff(vault_root)
    if handoff is not None:
        total += vaultlib.count_tokens(handoff.read_text(encoding="utf-8"))
        files.append(handoff.relative_to(vault_root).as_posix())
    return total, files


def run(args):
    vault_root = vaultlib.find_vault_root()
    total = measure(vault_root)
    sys.stdout.write(f"{total} / {HOT_PATH_CAP}\n")
    session_total, files = measure_session_start(vault_root)
    sys.stdout.write(
        f"session-start: {session_total} tokens ({', '.join(files)})\n"
    )
    return 0
