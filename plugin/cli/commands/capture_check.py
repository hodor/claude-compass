"""`compass capture-check --hook` - the Stop-hook trigger.

Bumps the main-agent turn counter, evaluates `capturelib.due_and_log()` (which
traces a `skipped` row to the capture log when not due), and on due
materializes a capture opportunity under
`.compass/tmp/capture-opportunities/OPP-<UTC>/opportunity.json` holding the
fired triggers and the evidence gathered from the turn window (the `ref` of
every signal recorded since the last opportunity - subagent-capture files, a
handoff path when a handoff-written signal is present). It then spawns a
detached headless worker (`compass capture-worker <opp-id>`) to run the
extraction pass and prints nothing: the conversation carries zero capture
scaffolding on the common path (ADR-013 D-01).

An unprocessed `.compass/tmp/phase-reports/*/phase-summary.yaml` (no sibling
`.processed` marker) opens a `phase` opportunity on its own, independent of
the turn/signal arithmetic, since a completed phase is detectable directly
from the file it leaves on disk rather than from a recorded signal. It takes
priority over the turn-based check: when both are true in the same call, the
phase opportunity opens and the pending turn/signal window carries into
whatever opportunity opens next. It spawns the worker the same way the
turn-based path does.

While an opportunity is already open, subsequent checks walk a fallback
ladder instead of the pure turn-based reemit spacing this module used before
the detached worker existed (ADR-013 D-04/D-05, mechanism decisions in
[[PLAN-010-invisible-capture]]): a live worker (a started row inside
`worker_grace_seconds`) is left alone; a dead worker, a spawn error, or an
open opportunity with no worker rows at all past the grace spends one of two
attempts and respawns; lock contention respawns without spending an attempt;
a `no-headless` failure latches the host and goes quiet immediately,
bypassing the attempt budget entirely, since it is a host-level fact, not a
transient death. Past two spent attempts, the ladder goes quiet
(`hookSpecificOutput.additionalContext`, never rendered) instead of
respawning a third time, and stays quiet until another full grace window
passes with the opportunity still open - at which point it falls back to
today's rendered block, entered exactly once, after which the pre-worker
turn-spaced reemit/abandon logic takes over unchanged. `enabled: false`
silences the whole command after the turn bump: no new opportunity opens or
spawns, and one already open stays frozen rather than progressing the
ladder.

`COMPASS_WORKER_SESSION` (ADR-013 D-11) gates this module's entire hook path:
when set, `run` returns 0 before doing anything else. The worker's own
headless session inherits this project's hooks, so without this gate it
would process the very opportunity it was spawned to close and manufacture
the signals that make the next one due - a loop, not a pass.

Every step past the `--hook` gate is best-effort: a missing vault, a corrupt
state or config file, or any internal error prints nothing and exits 0
rather than failing the turn that triggered it. The full JSON payload (block
or quiet) is assembled before the single stdout write, so an error partway
through resolving an opportunity can never leave partial output on stdout,
and exactly one of the two shapes is ever written in one run.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import capturelib
import vaultlib

OPPORTUNITIES_DIR = ("tmp", "capture-opportunities")

# Turns of silence between re-announcements of an open opportunity once the
# block last resort has been reached. `_enter_block_state` zeroes
# `turns_since_capture`, so from that point this counter measures turns
# since the block was last announced - identical to the pre-worker mechanism.
REEMIT_SPACING_TURNS = 5
PHASE_REPORTS_DIR = ("tmp", "phase-reports")

# Ledger events a worker (or capture-check spawning one) can leave against an
# opportunity id, oldest first in the log - the latest one is this
# opportunity's current worker status. `worker-spawn-error` is capture-check's
# own row (a Popen failure, never the wrapper's), and must be recognized here
# alongside the wrapper's own worker-started/finished/failed rows or a spawn
# error becomes invisible to the ladder and ages off the opportunity's own
# opened_at instead of retrying promptly.
WORKER_EVENTS = frozenset(
    {"worker-started", "worker-finished", "worker-failed", "worker-spawn-error"}
)

# The two-attempt budget D-04 sizes: a dead worker, a spawn error, or a
# zero-rows-past-grace opportunity may each be retried twice before the
# ladder gives up and goes quiet.
MAX_WORKER_ATTEMPTS = 2

# The `compass` launcher script sits beside this file's own package root
# (`plugin/cli/`), so the worker is spawned via the same entry point a human
# or a hook invokes directly - never a hardcoded install path.
COMPASS_SCRIPT = Path(__file__).resolve().parent.parent / "compass"


def _opportunity_dir(vault_root, opp_id):
    return Path(vault_root).joinpath(*OPPORTUNITIES_DIR) / opp_id


def _reason(directory, vault_root, reemit=False):
    rel = directory.relative_to(Path(vault_root)).as_posix()
    state_word = "still open" if reemit else "ready"
    return (
        f"Capture opportunity {state_word} at {rel} - "
        "spawn a subagent whose prompt tells it to read "
        ".claude/skills/extract-lessons/SKILL.md and follow its steps "
        "against that directory (a Skill-tool invocation hangs inside a "
        "subagent - the file is read and followed, never invoked; never "
        "run the pass in the main context), then relay only its one-line "
        "extracted: summary."
    )


def _quiet_context(directory, vault_root):
    rel = directory.relative_to(Path(vault_root)).as_posix()
    return (
        f"The detached capture worker for {rel} could not complete. Spawn a "
        "subagent whose prompt tells it to read "
        ".claude/skills/extract-lessons/SKILL.md and follow its steps "
        "against that directory (a Skill-tool invocation hangs inside a "
        "subagent - read and follow the file; never run the pass in the "
        "main context) - the skill's full contract, closed via `compass "
        "capture-close`. Tell the human nothing: the ledger holds the result. "
        "Speak only if the pass itself fails, in one line."
    )


def _emit(reason):
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}) + "\n")


def _emit_quiet(context):
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": context,
        }
    }
    sys.stdout.write(json.dumps(payload) + "\n")


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


def _worker_grace(config):
    return config.get(
        "worker_grace_seconds", capturelib.DEFAULT_CONFIG["worker_grace_seconds"]
    )


def _spend_attempt(vault_root, state):
    attempts = state.get("worker_attempts", 0)
    if not isinstance(attempts, int):
        attempts = 0
    state["worker_attempts"] = attempts + 1
    capturelib.save_state(vault_root, state)


def _spawn_worker(vault_root, opp_id):
    """Popen the detached worker for `opp_id`. On success, logs
    `worker-started` carrying the child's pid - the row that announces the
    attempt, per TASK-091's own division of labor (the worker writes only
    its end row). On a `Popen` failure, logs `worker-spawn-error` and spends
    no attempt itself: capture-check cannot see a child's stderr, so a spawn
    failure here is never classified `no-headless` - only the wrapper, which
    can see it, produces that reason (mechanism decisions, PLAN-010). The
    attempt is spent once, by whichever ladder step decided to call this
    function (`run`'s fresh-due path spends none - a brand-new opportunity
    has nothing to spend yet; `_respawn_or_quiet` already spent one before
    calling this). Spending here too would double-count a respawn's own
    failure against the same two-attempt budget in one call."""
    argv = [sys.executable, str(COMPASS_SCRIPT), "capture-worker", opp_id]
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(argv, **kwargs)
    except OSError:
        capturelib.log_event(vault_root, "worker-spawn-error", id=opp_id)
        return False
    capturelib.log_event(vault_root, "worker-started", id=opp_id, pid=proc.pid)
    return True


def _go_quiet(vault_root, opp_id, directory, state):
    """The quiet fallback (ADR-013 D-05): `additionalContext` wakes the
    model without rendering anything, replacing the two-strike respawn ladder
    or a host-level `no-headless` fact. Never spends an attempt itself -
    exhaustion or the latch already decided that."""
    capturelib.log_event(vault_root, "fallback-fired", id=opp_id, channel="quiet")
    state["worker_quiet_at"] = capturelib._iso(capturelib._now())
    capturelib.save_state(vault_root, state)
    _emit_quiet(_quiet_context(directory, vault_root))


def _respawn_or_quiet(vault_root, opp_id, directory, state, spend_attempt):
    """A death (dead worker, zero rows past grace, or any worker failure
    other than `lock-held`/`no-headless`) was detected: retry while under
    the two-attempt budget, otherwise fall through to the quiet channel
    instead of a third respawn. `spend_attempt=False` is `lock-held`'s own
    path - contention is not a death, so it must never burn the budget."""
    attempts = state.get("worker_attempts", 0)
    if not isinstance(attempts, int):
        attempts = 0
    if attempts >= MAX_WORKER_ATTEMPTS:
        _go_quiet(vault_root, opp_id, directory, state)
        return
    if spend_attempt:
        _spend_attempt(vault_root, state)
    _spawn_worker(vault_root, opp_id)


def _enter_block_state(vault_root, opp_id, directory, state):
    """The last resort (ADR-013 D-05): quiet has already fired and aged past
    another full grace with the opportunity still open. Fires the rendered
    block for the first time, logs the transition, and resets the turn/
    reemit bookkeeping so the pre-worker spacing logic that takes over from
    here (`_handle_block_reemit_and_abandon`) starts counting fresh, exactly
    as it did from a plain `open_opportunity` call before this mechanism
    existed."""
    capturelib.log_event(vault_root, "fallback-fired", id=opp_id, channel="block")
    state["turns_since_capture"] = 0
    state["reemits"] = 0
    capturelib.save_state(vault_root, state)
    _emit(_reason(directory, vault_root, reemit=False))


def _block_state_entered(vault_root, opp_id):
    return any(
        row.get("event") == "fallback-fired"
        and row.get("id") == opp_id
        and row.get("channel") == "block"
        for row in capturelib.read_log(vault_root)
    )


def _latest_worker_row(vault_root, opp_id):
    rows = [
        row for row in capturelib.read_log(vault_root)
        if row.get("id") == opp_id and row.get("event") in WORKER_EVENTS
    ]
    return rows[-1] if rows else None


def _handle_block_reemit_and_abandon(vault_root, opp_id, directory, opp_path, state, config):
    """Once the block last resort has been reached for this opportunity, the
    mechanism behaves exactly as it did before the detached worker existed:
    turn-spaced re-emits of the rendered block up to `max_reemits`, then an
    age-gated abandon. The spacing exists because every block reason is
    rendered into the human's conversation: the announcement is for the
    model, and an extraction pass usually completes within a few turns, so
    per-turn re-nagging costs the human attention while buying nothing. The
    age requirement on abandon keeps a burst of quick turns from abandoning
    an opportunity whose extraction pass is still running - a re-emit budget
    alone measures turn count, not elapsed time, and an in-flight pass needs
    time."""
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


def _handle_open_opportunity(vault_root, state, config):
    """An opportunity is already open. Routes to whichever rung of the
    fallback ladder its current ledger state and grace/attempt bookkeeping
    put it on - see the module docstring for the ladder's shape. Exactly one
    JSON payload (block, quiet, or nothing) is ever emitted per call: once
    `worker_quiet_at` is set, the row-based death/lock-held/no-headless
    ladder below is never consulted again for this opportunity - it has
    already been exhausted by the time quiet fired."""
    opp_id = state.get("open_opportunity")
    directory = _opportunity_dir(vault_root, opp_id)
    opp_path = directory / "opportunity.json"
    if not opp_path.is_file():
        # The mutex points at an opportunity no longer on disk: stale, not held.
        state["open_opportunity"] = None
        state["reemits"] = 0
        capturelib.save_state(vault_root, state)
        return

    if _block_state_entered(vault_root, opp_id):
        _handle_block_reemit_and_abandon(vault_root, opp_id, directory, opp_path, state, config)
        return

    grace = _worker_grace(config)
    quiet_at = capturelib.parse_iso(state.get("worker_quiet_at"))
    if quiet_at is not None:
        age = (capturelib._now() - quiet_at).total_seconds()
        if age < grace:
            return  # already quiet, still inside the next grace: stay silent
        _enter_block_state(vault_root, opp_id, directory, state)
        return

    row = _latest_worker_row(vault_root, opp_id)
    event = row.get("event") if row else None
    reason = row.get("reason") if row else None

    if event == "worker-failed" and reason == "no-headless":
        _go_quiet(vault_root, opp_id, directory, state)
        return

    if event == "worker-failed" and reason == "lock-held":
        _respawn_or_quiet(vault_root, opp_id, directory, state, spend_attempt=False)
        return

    if event == "worker-started":
        started_at = capturelib.parse_iso(row.get("at"))
        age = (capturelib._now() - started_at).total_seconds() if started_at else None
        if age is None or age < grace:
            return  # presumed still running, within its grace
        _respawn_or_quiet(vault_root, opp_id, directory, state, spend_attempt=True)
        return

    if event in ("worker-failed", "worker-spawn-error"):
        # A timeout, any other worker-reported failure reason, or a Popen
        # failure capture-check recorded itself: a death, same as a dead
        # started row - retried on the very next check, no grace wait,
        # since a spawn error is already an unambiguous, immediate fact.
        _respawn_or_quiet(vault_root, opp_id, directory, state, spend_attempt=True)
        return

    # No worker rows at all for this opportunity - the spawn-that-never-was
    # branch: age it off the opportunity's own opened_at instead of a row.
    opened_at = None
    try:
        opened_at = capturelib.parse_iso(
            json.loads(opp_path.read_text(encoding="utf-8")).get("opened_at")
        )
    except (OSError, ValueError):
        pass
    age = (capturelib._now() - opened_at).total_seconds() if opened_at else None
    if age is None or age < grace:
        return
    _respawn_or_quiet(vault_root, opp_id, directory, state, spend_attempt=True)


def run(args):
    if "--hook" not in args:
        return 0
    if os.environ.get("COMPASS_WORKER_SESSION"):
        # ADR-013 D-11: the worker's own headless session inherits this
        # project's hooks. Without this gate it would process the very
        # opportunity it was spawned to close and manufacture the signals
        # that make the next one due - a loop, not a pass.
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

        no_headless_at = capturelib.parse_iso(state.get("no_headless_at"))
        if no_headless_at is not None:
            retry_seconds = config.get(
                "no_headless_retry_seconds",
                capturelib.DEFAULT_CONFIG["no_headless_retry_seconds"],
            )
            if (capturelib._now() - no_headless_at).total_seconds() < retry_seconds:
                # This host could not run a headless child last time and has
                # not proven otherwise since: no new opportunity is even
                # considered until the latch expires.
                return 0

        phase_dir = _pending_phase_summary(vault_root)
        if phase_dir is not None:
            rel = phase_dir.relative_to(Path(vault_root)).as_posix()
            directory = capturelib.open_opportunity(
                vault_root, "phase", ["phase-summary"], [rel]
            )
            _spawn_worker(vault_root, directory.name)
            return 0

        is_due, reason = capturelib.due_and_log(vault_root, state, config)
        if is_due:
            kind = "signal" if reason.startswith("strong signal") else "interval"
            triggers, evidence = _window_evidence(state.get("signals") or [])
            directory = capturelib.open_opportunity(vault_root, kind, triggers, evidence)
            _spawn_worker(vault_root, directory.name)
    except Exception:
        pass  # best-effort: capture bookkeeping must never fail the turn
    finally:
        if locked:
            capturelib.release_run_lock(vault_root)
    return 0
