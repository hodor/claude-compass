"""Deterministic capture trigger: turn counter, signal log, and due-check.

Durable tunables live at `.compass/meta/capture.json` (`enabled`, `interval`,
`max_reemits`), materialized with defaults on first read so a human can find
and retune them without reading code. Ephemeral per-session state lives at
`.compass/tmp/capture-state.json` (`turns_since_capture`, `signals`,
`open_opportunity`, `reemits`, `last_opportunity_at`). `due()` is the only
decision function and is pure arithmetic over already-loaded dicts - no I/O,
no model call - so the hook path can call it without a filesystem round trip.
Every other function here sits on that hook path and is best-effort: a
missing, corrupt, or unreadable file resets to defaults instead of raising,
and writes swallow I/O errors rather than breaking the turn that triggered
them.

Every opportunity's lifecycle is traced to the append-only
`.compass/tmp/capture-log.jsonl`, one JSON object per line: `opened` when
`open_opportunity` materializes a directory, `skipped` when `due_and_log`
finds nothing due (carrying the arithmetic reason `due()` returned), `fired`
when `close_opportunity` is given an outcome other than `abandoned` (an
extraction pass actually ran, whether or not it wrote anything - "reviewed
and found nothing" is a `fired` row with `written: 0`, distinct from a
`closed` row where extraction never ran at all), and `closed` when the
outcome is `abandoned` (the re-emit budget ran out with no extraction ever
run). Logging a row is best-effort like everything else on this module's
hook path: a write failure never raises out of the function that logs it.
"""

import datetime
import json
from pathlib import Path

import vaultlib

DEFAULT_CONFIG = {
    "enabled": True,
    "interval": 12,
    "max_reemits": 3,
}

DEFAULT_STATE = {
    "turns_since_capture": 0,
    "signals": [],
    "open_opportunity": None,
    "reemits": 0,
    "last_opportunity_at": None,
}

# Signal kinds that make an opportunity due on their own, independent of the
# turn interval.
STRONG_SIGNAL_KINDS = frozenset(
    {"handoff-written", "validator-finished", "debug-finished", "phase-summary"}
)

# Oldest signals are dropped past this count so a long-idle or long-disabled
# window cannot grow the state file without bound.
MAX_SIGNALS = 50


def _config_path(vault_root):
    return Path(vault_root) / "meta" / "capture.json"


def _state_path(vault_root):
    return Path(vault_root) / "tmp" / "capture-state.json"


def _opportunities_dir(vault_root):
    return Path(vault_root) / "tmp" / "capture-opportunities"


def _log_path(vault_root):
    return Path(vault_root) / "tmp" / "capture-log.jsonl"


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _write_json(path, data):
    """Serialize `data` and write it to `path` with LF endings. Serialization
    errors (bad types) raise; I/O errors (unwritable directory, out of disk)
    are swallowed, since every caller sits on the best-effort hook path."""
    text = json.dumps(data, indent=2) + "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        vaultlib.write_text_lf(path, text)
    except OSError:
        pass


def _log_event(vault_root, event, **fields):
    """Append one row to `.compass/tmp/capture-log.jsonl`: `{at, event,
    **fields}` with a UTC timestamp. Best-effort - a full disk or an
    unwritable tmp dir must never raise out of the opportunity lifecycle
    call that triggered the log, so I/O errors are swallowed here."""
    row = {"at": _iso(_now()), "event": event}
    row.update(fields)
    path = _log_path(vault_root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(row) + "\n")
    except OSError:
        pass


def load_config(vault_root):
    """Load `.compass/meta/capture.json`. A missing file is materialized with
    `DEFAULT_CONFIG` so a human can find and retune it; a partial file gets
    defaults filled in for the keys it omits, keeping the keys it sets; a
    corrupt or unreadable file falls back to `DEFAULT_CONFIG` in memory
    without touching the file on disk. Never raises."""
    path = _config_path(vault_root)
    if not path.is_file():
        config = dict(DEFAULT_CONFIG)
        _write_json(path, config)
        return config
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULT_CONFIG)
    if not isinstance(raw, dict):
        return dict(DEFAULT_CONFIG)
    config = dict(DEFAULT_CONFIG)
    config.update(raw)
    return config


def _default_state():
    """A fresh `DEFAULT_STATE` copy with its own `signals` list. `dict(...)`
    alone only shallow-copies: the nested `signals` list would stay the same
    object as `DEFAULT_STATE["signals"]`, so every caller that received a
    "fresh" state and appended to it in place (`record_signal` does) would
    corrupt every other vault's default for the life of the process."""
    state = dict(DEFAULT_STATE)
    state["signals"] = []
    return state


def load_state(vault_root):
    """Load `.compass/tmp/capture-state.json`. A missing, corrupt, or
    unreadable file resets to `DEFAULT_STATE` rather than raising. A `signals`
    value that is not a list (partial corruption of one field) is reset to an
    empty list while the rest of the state is kept."""
    path = _state_path(vault_root)
    if not path.is_file():
        return _default_state()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _default_state()
    if not isinstance(raw, dict):
        return _default_state()
    state = _default_state()
    state.update(raw)
    if not isinstance(state.get("signals"), list):
        state["signals"] = []
    if not isinstance(state.get("turns_since_capture"), int):
        state["turns_since_capture"] = 0
    return state


def save_state(vault_root, state):
    """Write `state` to `.compass/tmp/capture-state.json` with LF endings."""
    _write_json(_state_path(vault_root), state)


def record_signal(vault_root, kind, ref):
    """Append a `{kind, ref, at}` signal to the state and save it, bounding
    the list to `MAX_SIGNALS` by dropping the oldest entries. Returns the
    updated state."""
    state = load_state(vault_root)
    signals = state.get("signals", [])
    signals.append({"kind": kind, "ref": ref, "at": _iso(_now())})
    state["signals"] = signals[-MAX_SIGNALS:]
    save_state(vault_root, state)
    return state


def bump_turn(vault_root):
    """Increment `turns_since_capture` by one and save the state. Returns the
    updated state."""
    state = load_state(vault_root)
    state["turns_since_capture"] = state.get("turns_since_capture", 0) + 1
    save_state(vault_root, state)
    return state


def due(state, config):
    """Whether a capture opportunity should open, decided by pure arithmetic
    over `state` and `config` - no I/O, no model call. Returns `(bool, reason)`.

    A strong signal (`STRONG_SIGNAL_KINDS`) is due on its own regardless of
    the turn count. Otherwise due requires the turn interval reached AND at
    least one recorded signal in the window; reaching the interval with zero
    signals is not due, since an idle session with no vault write and no
    subagent must never open an opportunity. `enabled: false` suppresses
    both paths."""
    if not config.get("enabled", True):
        return False, "capture disabled"

    signals = state.get("signals") or []
    for signal in signals:
        kind = signal.get("kind") if isinstance(signal, dict) else None
        if kind in STRONG_SIGNAL_KINDS:
            return True, f"strong signal: {kind}"

    interval = config.get("interval", DEFAULT_CONFIG["interval"])
    turns = state.get("turns_since_capture", 0)
    if not isinstance(turns, int):
        turns = 0
    if turns < interval:
        return False, f"below interval ({turns}/{interval})"
    if not signals:
        return False, f"interval reached ({turns}/{interval}) with no signals"
    return True, f"interval reached ({turns}/{interval}) with {len(signals)} signal(s)"


def due_and_log(vault_root, state, config):
    """`due()`, plus a `skipped` trace row carrying the arithmetic reason
    when the result is not due. `due()` itself stays the pure, I/O-free
    decision function `due()`'s own docstring and SPEC-012 D-03 require;
    this wrapper is the one caller on the hook path that needs the outcome
    traced, so the log write sits beside `due()` rather than inside it.
    Returns the same `(bool, reason)` pair `due()` returns."""
    is_due, reason = due(state, config)
    if not is_due:
        _log_event(vault_root, "skipped", reason=reason)
    return is_due, reason


def open_opportunity(vault_root, kind, triggers, evidence):
    """Materialize a capture opportunity at
    `.compass/tmp/capture-opportunities/OPP-<UTC>/opportunity.json`, holding
    `kind`, the fired `triggers`, and `evidence`. Marks the state's
    `open_opportunity` with the new id, resets `reemits` to 0, clears
    `turns_since_capture` and `signals` (the window that produced this
    opportunity is spent; the next one starts counting fresh), and stamps
    `last_opportunity_at`. Returns the opportunity directory path."""
    now = _now()
    opened_at = _iso(now)
    opp_id = "OPP-" + now.strftime("%Y%m%dT%H%M%S") + f"{now.microsecond:06d}Z"
    directory = _opportunities_dir(vault_root) / opp_id
    record = {
        "id": opp_id,
        "kind": kind,
        "triggers": triggers,
        "evidence": evidence,
        "opened_at": opened_at,
        "closed_at": None,
        "outcome": None,
    }
    _write_json(directory / "opportunity.json", record)

    state = load_state(vault_root)
    state["open_opportunity"] = opp_id
    state["reemits"] = 0
    state["turns_since_capture"] = 0
    state["signals"] = []
    state["last_opportunity_at"] = opened_at
    save_state(vault_root, state)
    _log_event(vault_root, "opened", id=opp_id, kind=kind, triggers=triggers)
    return directory


def close_opportunity(
    vault_root, opportunity_id, outcome,
    candidate=None, written=None, recurrence=None, rejected=None, error=None,
    revised=None, archived=None,
):
    """Close `opportunity_id` with `outcome` (e.g. `fired`, `abandoned`).
    Clears the state's `open_opportunity` and `reemits` when `opportunity_id`
    is the one currently open; records `outcome` and `closed_at` on the
    opportunity's own `opportunity.json` when that file is still present,
    independent of whether it was the current mutex holder.

    `outcome` is an open string, not an enum - the extraction pass supplies
    whatever value describes what happened. `abandoned` is the one outcome
    this module itself uses (the re-emit budget ran out with no extraction
    ever run) and logs as a `closed` trace row. Any other outcome logs as
    `fired` - an extraction pass actually ran, whether or not it wrote
    anything - carrying whichever of `candidate`, `written`, `recurrence`,
    `rejected`, `error`, `revised`, `archived` were passed, so "reviewed and
    found nothing" and "never ran" are always distinguishable rows, never the
    same absence. `revised` and `archived` count an existing lesson corrected
    or retired through the contradiction branch, kept apart from `written`
    and `recurrence` since neither is a fresh candidate outcome.
    """
    state = load_state(vault_root)
    if state.get("open_opportunity") == opportunity_id:
        state["open_opportunity"] = None
        state["reemits"] = 0
        save_state(vault_root, state)

    path = _opportunities_dir(vault_root) / opportunity_id / "opportunity.json"
    if path.is_file():
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            record = {}
        if not isinstance(record, dict):
            record = {}
        record.setdefault("id", opportunity_id)
        record["outcome"] = outcome
        record["closed_at"] = _iso(_now())
        _write_json(path, record)

    counts = {
        name: value
        for name, value in (
            ("candidate", candidate), ("written", written),
            ("recurrence", recurrence), ("rejected", rejected), ("error", error),
            ("revised", revised), ("archived", archived),
        )
        if value is not None
    }
    event = "closed" if outcome == "abandoned" else "fired"
    _log_event(vault_root, event, id=opportunity_id, outcome=outcome, **counts)
