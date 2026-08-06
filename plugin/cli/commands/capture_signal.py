"""`compass capture-signal --hook` - the SubagentStop hook.

Captures a finishing subagent's final report to
`.compass/tmp/subagent-captures/<UTC>_<agent_type>.md` with frontmatter
(`type`, `agent_type`, `agent_id`, `captured_at`), then records a capture
signal keyed on the agent type via `capturelib`. Reads the event JSON from stdin, gated
behind `--hook` per LESSON-hook-cli-gate-stdin-on-flag: the human/no-flag
path never touches stdin, so it cannot block on a shell with nothing piped
in. A subagent finishing must never fail the turn that triggered it, so every
step past argument parsing is best-effort - malformed JSON, an absent vault,
or any internal error records nothing and exits 0.
"""

import datetime
import json
import sys

import capturelib
import vaultlib

# Maps an event's agent_type to the signal kind capture-check's due() reads.
# Any agent_type outside this map (including one absent from the event) gets
# the default kind.
SIGNAL_KINDS = {
    "validator": "validator-finished",
    "debug": "debug-finished",
    "builder": "builder-finished",
}
DEFAULT_SIGNAL_KIND = "subagent-finished"
DEFAULT_AGENT_TYPE = "unknown"

CAPTURES_DIR = "subagent-captures"


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _parse_hook_stdin():
    """Parse the SubagentStop event JSON the hook runtime pipes on stdin.
    Returns `None` for empty stdin, unparseable JSON, or a non-object
    payload - no event was actually received, so `run` must record nothing -
    distinct from a valid but incomplete event (e.g. missing `agent_type`),
    which still gets captured under the default kind."""
    data = sys.stdin.read().strip()
    if not data:
        return None
    try:
        obj = json.loads(data)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _unique_path(directory, stem, suffix):
    """`directory / f"{stem}{suffix}"`, or the first `-N` variant that does
    not already exist, so two subagents of the same type finishing within
    the same UTC second never overwrite each other's capture."""
    candidate = directory / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    n = 1
    while True:
        candidate = directory / f"{stem}-{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def _write_capture(vault_root, agent_type, agent_id, message):
    """Write `message` verbatim as the body of a subagent-captures file,
    frontmatter first. Returns the vault-relative POSIX path of the file
    written, used as the recorded signal's `ref`."""
    directory = vault_root / "tmp" / CAPTURES_DIR
    directory.mkdir(parents=True, exist_ok=True)
    now = _now()
    timestamp = now.strftime("%Y-%m-%dT%H-%M-%S")
    path = _unique_path(directory, f"{timestamp}_{agent_type}", ".md")
    frontmatter = (
        "---\n"
        "type: subagent_capture\n"
        f"agent_type: {agent_type}\n"
        f"agent_id: {agent_id}\n"
        f"captured_at: {_iso(now)}\n"
        "---\n"
    )
    vaultlib.write_text_lf(path, frontmatter + "\n" + message)
    return path.relative_to(vault_root).as_posix()


def run(args):
    if "--hook" not in args:
        # Nothing to do outside the hook path, and stdin is never touched,
        # per LESSON-hook-cli-gate-stdin-on-flag.
        return 0

    try:
        event = _parse_hook_stdin()
        if event is None:
            return 0  # no event received: nothing to capture or record
        agent_type = event.get("agent_type") or DEFAULT_AGENT_TYPE
        agent_id = event.get("agent_id", "")
        message = event.get("last_assistant_message", "")

        vault_root = vaultlib.find_vault_root()
        ref = _write_capture(vault_root, agent_type, agent_id, message)
        capturelib.record_signal(
            vault_root, SIGNAL_KINDS.get(agent_type, DEFAULT_SIGNAL_KIND), ref
        )
    except Exception:
        pass  # best-effort: capture bookkeeping must never fail the turn
    return 0
