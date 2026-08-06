"""`compass capture-check --hook` - the Stop-hook trigger.

Bumps the main-agent turn counter, evaluates `capturelib.due_and_log()` (which
traces a `skipped` row to the capture log when not due), and on due
materializes a capture opportunity under
`.compass/tmp/capture-opportunities/OPP-<UTC>/opportunity.json` holding the
fired triggers and the evidence gathered from the turn window (the `ref` of
every signal recorded since the last opportunity - subagent-capture files, a
handoff path when a handoff-written signal is present). It then prints the
Claude Code stop-hook contract `{"decision": "block", "reason": ...}` naming
the opportunity directory and the extract-lessons skill, so the capture pass
runs as a real turn instead of prose the model can skip.

An unprocessed `.compass/tmp/phase-reports/*/phase-summary.yaml` (no sibling
`.processed` marker) opens a `phase` opportunity on its own, independent of
the turn/signal arithmetic, since a completed phase is detectable directly
from the file it leaves on disk rather than from a recorded signal. It takes
priority over the turn-based check: when both are true in the same call, the
phase opportunity opens and the pending turn/signal window carries into
whatever opportunity opens next.

While an opportunity is already open (the state's mutex marker is set), the
block JSON re-emits once per turn up to `max_reemits` times; past that the
opportunity is closed `abandoned` and nothing more is printed. `enabled:
false` silences the whole command after the turn bump: no new opportunity
opens, and one already open stays frozen rather than re-emitting or being
abandoned while capture is turned off.

Every step past the `--hook` gate is best-effort: a missing vault, a corrupt
state or config file, or any internal error prints nothing and exits 0
rather than failing the turn that triggered it. The full JSON payload is
assembled before the single stdout write, so an error partway through
resolving an opportunity can never leave partial output on stdout.
"""

import json
import sys
from pathlib import Path

import capturelib
import vaultlib

OPPORTUNITIES_DIR = ("tmp", "capture-opportunities")
PHASE_REPORTS_DIR = ("tmp", "phase-reports")


def _opportunity_dir(vault_root, opp_id):
    return Path(vault_root).joinpath(*OPPORTUNITIES_DIR) / opp_id


def _reason(directory, vault_root, reemit=False):
    rel = directory.relative_to(Path(vault_root)).as_posix()
    state_word = "still open" if reemit else "ready"
    return (
        f"Capture opportunity {state_word} at {rel} - "
        "run the extract-lessons skill against it."
    )


def _emit(reason):
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}) + "\n")


def _pending_phase_summary(vault_root):
    """The most recently modified `.compass/tmp/phase-reports/*/` directory
    holding a `phase-summary.yaml` with no sibling `.processed` marker, or
    `None`. Phase completion is detectable directly from the file it leaves
    on disk, independent of whether a signal was ever recorded for it."""
    reports_dir = Path(vault_root).joinpath(*PHASE_REPORTS_DIR)
    if not reports_dir.is_dir():
        return None
    candidates = []
    for entry in reports_dir.iterdir():
        if not entry.is_dir():
            continue
        summary = entry / "phase-summary.yaml"
        if not summary.is_file() or (entry / ".processed").exists():
            continue
        candidates.append((summary.stat().st_mtime, entry))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[0][1]


def _window_evidence(signals):
    """Distinct, order-preserving signal kinds and refs recorded in the
    window that made an opportunity due: the subagent-capture and handoff
    paths a strong or interval signal points the extractor at."""
    triggers, evidence = [], []
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        kind = signal.get("kind")
        if kind and kind not in triggers:
            triggers.append(kind)
        ref = signal.get("ref")
        if ref and ref not in evidence:
            evidence.append(ref)
    return triggers, evidence


def _handle_open_opportunity(vault_root, state, config):
    """An opportunity is already open. Re-emit the block JSON while under
    `max_reemits`; past that, close it `abandoned` and go silent."""
    opp_id = state.get("open_opportunity")
    directory = _opportunity_dir(vault_root, opp_id)
    if not (directory / "opportunity.json").is_file():
        # The mutex points at an opportunity no longer on disk: stale, not held.
        state["open_opportunity"] = None
        state["reemits"] = 0
        capturelib.save_state(vault_root, state)
        return

    reemits = state.get("reemits", 0)
    if not isinstance(reemits, int):
        reemits = 0
    max_reemits = config.get("max_reemits", capturelib.DEFAULT_CONFIG["max_reemits"])
    if reemits < max_reemits:
        state["reemits"] = reemits + 1
        capturelib.save_state(vault_root, state)
        _emit(_reason(directory, vault_root, reemit=True))
    else:
        capturelib.close_opportunity(vault_root, opp_id, "abandoned")


def run(args):
    if "--hook" not in args:
        return 0
    try:
        sys.stdin.read()  # drain the Stop event JSON; content is unused

        vault_root = vaultlib.find_vault_root()
        state = capturelib.bump_turn(vault_root)
        config = capturelib.load_config(vault_root)
        if not config.get("enabled", True):
            return 0

        if state.get("open_opportunity"):
            _handle_open_opportunity(vault_root, state, config)
            return 0

        phase_dir = _pending_phase_summary(vault_root)
        if phase_dir is not None:
            rel = phase_dir.relative_to(Path(vault_root)).as_posix()
            directory = capturelib.open_opportunity(
                vault_root, "phase", ["phase-summary"], [rel]
            )
            _emit(_reason(directory, vault_root))
            return 0

        is_due, reason = capturelib.due_and_log(vault_root, state, config)
        if is_due:
            kind = "signal" if reason.startswith("strong signal") else "interval"
            triggers, evidence = _window_evidence(state.get("signals") or [])
            directory = capturelib.open_opportunity(vault_root, kind, triggers, evidence)
            _emit(_reason(directory, vault_root))
    except Exception:
        pass  # best-effort: capture bookkeeping must never fail the turn
    return 0
