"""`compass capture-note "<observation>"` - an agent's in-flight lesson candidate.

The main agent notices something worth remembering while it works: a test that
destroyed shared state, a tool that behaves differently than documented, a
plan step that turned out to be wrong. This command hands that observation to
the invisible capture worker and nothing else happens on the human's screen.
The note is written to `.compass/tmp/subagent-captures/<UTC>_note.md`, the
same evidence location the extract-lessons pass already reads, and recorded
as an `agent-noted` signal, which `capturelib.due()` treats as strong: the
worker fires at the next Stop instead of waiting for the turn interval.

The note is evidence, never a lesson. The worker runs it through the anti-list
and dedup the same way it treats a subagent's captured report, so a note that
does not survive the filter costs one file in tmp and nothing in the vault.

Text comes from the arguments only; stdin is never read, per
LESSON-hook-cli-gate-stdin-on-flag. `COMPASS_WORKER_SESSION` (ADR-013 D-11)
gates the command: a note recorded from inside the worker's own session would
manufacture the strong signal that reopens the loop it was spawned to close.
"""

import datetime
import os
import sys

import capturelib
import vaultlib
from commands import capture_signal

SIGNAL_KIND = "agent-noted"
NOTE_STEM = "note"

USAGE = 'usage: compass capture-note "<one observation, its own sentence>"'


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _write_note(vault_root, text):
    """Write `text` as the body of a note file under subagent-captures,
    frontmatter first. Returns the vault-relative POSIX path, used as the
    recorded signal's `ref`."""
    directory = vault_root / "tmp" / capture_signal.CAPTURES_DIR
    directory.mkdir(parents=True, exist_ok=True)
    now = _now()
    timestamp = now.strftime("%Y-%m-%dT%H-%M-%S")
    path = capture_signal._unique_path(directory, f"{timestamp}_{NOTE_STEM}", ".md")
    frontmatter = (
        "---\n"
        "type: agent_note\n"
        f"agent_type: {NOTE_STEM}\n"
        f"captured_at: {_iso(now)}\n"
        "---\n"
    )
    vaultlib.write_text_lf(path, frontmatter + "\n" + text.strip() + "\n")
    return path.relative_to(vault_root).as_posix()


def run(args):
    if os.environ.get("COMPASS_WORKER_SESSION"):
        return 0
    text = " ".join(a for a in args if not a.startswith("--")).strip()
    if not text:
        print(USAGE, file=sys.stderr)
        return 1
    try:
        vault_root = vaultlib.find_vault_root()
        ref = _write_note(vault_root, text)
        capturelib.record_signal(vault_root, SIGNAL_KIND, ref)
    except Exception as exc:
        print(f"capture-note: {exc}", file=sys.stderr)
        return 1
    return 0
