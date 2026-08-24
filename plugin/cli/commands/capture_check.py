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
hook stays silent for `REEMIT_SPACING_TURNS` turns at a time, re-emitting the
block JSON only when that many turns have passed since the last announcement,
up to `max_reemits` times; past that the opportunity is closed `abandoned`
and nothing more is printed. The spacing exists because every block reason is
rendered into the human's conversation: the announcement is for the model,
and an extraction pass usually completes within a few turns, so per-turn
re-nagging costs the human attention while buying nothing. `enabled:
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

# Turns of silence between re-announcements of an open opportunity.
# `open_opportunity` zeroes `turns_since_capture`, so while an opportunity is
# open that counter measures turns since it was announced.
REEMIT_SPACING_TURNS = 5
PHASE_REPORTS_DIR = ("tmp", "phase-reports")


def _opportunity_dir(vault_root, opp_id):
    return Path(vault_root).joinpath(*OPPORTUNITIES_DIR) / opp_id


def _reason(directory, vault_root, reemit=False):
    rel = directory.relative_to(Path(vault_root)).as_posix()
    state_word = "still open" if reemit else "ready"
    return (
        f"Capture opportunity {state_word} at {rel} - "
        "spawn a subagent to run the extract-lessons skill against it "
        "(never run the pass in the main context), then relay only its "
        "one-line extracted: summary."
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
    """An opportunity is already open. Stay silent until
    `REEMIT_SPACING_TURNS` turns have passed since the last announcement,
    then re-emit the block JSON, while under `max_reemits`; past that budget,
    go silent, and close it `abandoned` only once it is also older than
    `abandon_after_seconds`. The age requirement is what keeps a burst of
    quick turns from abandoning an opportunity whose extraction pass is
    still running - a re-emit budget alone measures turn count, not elapsed
    time, and an in-flight pass needs time."""
    opp_id = state.get("open_opportunity")
    directory = _opportunity_dir(vault_root, opp_id)
    opp_path = directory / "opportunity.json"
    if not opp_path.is_file():
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
        turns_open = state.get("turns_since_capture", 0)
        if not isinstance(turns_open, int):
            turns_open = 0
        if turns_open < (reemits + 1) * REEMIT_SPACING_TURNS:
            return
        state["reemits"] = reemits + 1
        capturelib.save_state(vault_root, state)
        _emit(_reason(directory, vault_root, reemit=True))
        return

    grace = config.get(
        "abandon_after_seconds", capturelib.DEFAULT_CONFIG["abandon_after_seconds"]
    )
    opened_at = None
    try:
        opened_at = capturelib.parse_iso(
            json.loads(opp_path.read_text(encoding="utf-8")).get("opened_at")
        )
    except (OSError, ValueError):
        pass
    if opened_at is not None:
        age = (capturelib._now() - opened_at).total_seconds()
        if age < grace:
            return  # budget spent but still young: an extraction may be in flight
    capturelib.close_opportunity(vault_root, opp_id, "abandoned")


def run(args):
    if "--hook" not in args:
        return 0
    locked = False
    vault_root = None
    try:
        sys.stdin.read()  # drain the Stop event JSON; content is unused

        vault_root = vaultlib.find_vault_root()
        if not capturelib.acquire_run_lock(vault_root):
            return 0  # a concurrent capture-check holds the window
        locked = True
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
    finally:
        if locked:
            capturelib.release_run_lock(vault_root)
    return 0
