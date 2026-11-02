"""Private per-session records of token use.

`record_session` counts a session's tokens from its `stream-json` events, adds
list-price weights and appends one allowlisted row to
`<private root>/records/<machine id>.jsonl`. A row holds counts, enums, model
ids, a Claude Code version, a commit id, a timestamp and a hashed machine id;
nothing of a session's content reaches it. Writing inside a git work tree is
refused.

Counting. A session's `result` events carry running totals per model in
`modelUsage`. Within one stretch of a session the last totals are the stretch's
usage; a new stretch starts at a `system/init` event with another session id
(what `/clear` produces), or when a model's totals fall below their earlier
values. The session's tokens are the sum over stretches. A stretch with no
`result` event counts nothing. Usage of subagents is inside `modelUsage`;
assistant events are not added on top.

Weights. A token weighs what it lists at relative to a fresh input token of the
same model: output 5, cache write 1.25, cache read 0.1 (0.05 for the Opus 5.5
and Sonnet 5.5 families, 0.025 for the Fable 5.1 and Mythos 5.1 families). A
model id outside the table adds no weight; its tokens are still counted and the
row names it under `unpriced_models`.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_CLI_DIR = Path(__file__).resolve().parents[2] / "plugin" / "cli"
if str(_CLI_DIR) not in sys.path:
    sys.path.insert(0, str(_CLI_DIR))

import sensorlib  # noqa: E402
from launch import default_private_root  # noqa: E402

ROLES = ("build", "human", "topic", "goal", "judge")
OUTCOMES = ("done", "failed", "usage-limit")
ARMS = ("compass", "baseline")

KINDS = ("input", "output", "cache_read", "cache_write")
_USAGE_FIELDS = {
    "input": "inputTokens",
    "output": "outputTokens",
    "cache_read": "cacheReadInputTokens",
    "cache_write": "cacheCreationInputTokens",
}

OUTPUT_WEIGHT = 5.0
CACHE_WRITE_WEIGHT = 1.25
# (model id prefix, cache-read weight); the first matching prefix wins.
PRICED_MODELS = (
    ("claude-opus-5-5", 0.05),
    ("claude-sonnet-5-5", 0.05),
    ("claude-fable-5-1", 0.025),
    ("claude-mythos-5-1", 0.025),
    ("claude-opus-4", 0.1),
    ("claude-sonnet-4", 0.1),
    ("claude-haiku-4", 0.1),
)

UNKNOWN_MODEL = "unknown-model"
_MODEL_ID = re.compile(r"claude-[a-z0-9.\-]+(\[[a-z0-9]+\])?")
_COMMIT_ID = re.compile(r"[0-9a-f]{7,64}")
_VERSION = re.compile(r"\d+\.\d+\.\d+")


class Refused(Exception):
    """The records folder would sit inside a git work tree."""


def _model_key(model):
    return model if isinstance(model, str) and _MODEL_ID.fullmatch(model) else UNKNOWN_MODEL


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _result_usage(event):
    """{model key: {kind: count}} from one result event's `modelUsage`."""
    usage = event.get("modelUsage")
    if not isinstance(usage, dict):
        return {}
    parsed = {}
    for model, entry in usage.items():
        if not isinstance(entry, dict):
            continue
        counts = parsed.setdefault(_model_key(model), dict.fromkeys(KINDS, 0))
        for kind, source in _USAGE_FIELDS.items():
            counts[kind] += _count(entry.get(source))
    return parsed


def _fell_below(latest, usage):
    return any(
        counts[kind] < latest[model][kind]
        for model, counts in usage.items() if model in latest
        for kind in KINDS
    )


def count_tokens(events):
    """{model id: {kind: tokens}} summed over the stretches of a session."""
    stretches, latest, session = [], {}, None
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            if latest and event.get("session_id") != session:
                stretches.append(latest)
                latest = {}
            session = event.get("session_id")
        elif event.get("type") == "result":
            usage = _result_usage(event)
            if _fell_below(latest, usage):
                stretches.append(latest)
                latest = {}
            latest.update(usage)
    if latest:
        stretches.append(latest)
    totals = {}
    for stretch in stretches:
        for model, counts in stretch.items():
            total = totals.setdefault(model, dict.fromkeys(KINDS, 0))
            for kind in KINDS:
                total[kind] += counts[kind]
    return totals


def cache_read_weight(model):
    """The cache-read weight of `model`, or None when the model is unpriced."""
    for prefix, weight in PRICED_MODELS:
        if model.startswith(prefix):
            return weight
    return None


def weigh(totals):
    """(weighted total, sorted ids of unpriced models) for `count_tokens` output."""
    weighted, unpriced = 0.0, []
    for model, counts in totals.items():
        read_weight = cache_read_weight(model)
        if read_weight is None:
            unpriced.append(model)
            continue
        weighted += (
            counts["input"]
            + OUTPUT_WEIGHT * counts["output"]
            + read_weight * counts["cache_read"]
            + CACHE_WRITE_WEIGHT * counts["cache_write"]
        )
    return round(weighted, 3), sorted(unpriced)


def _first_version(events):
    for event in events:
        if isinstance(event, dict) and event.get("type") == "system" and event.get("subtype") == "init":
            version = event.get("claude_code_version")
            return version if isinstance(version, str) and _VERSION.fullmatch(version) else None
    return None


def _sum_durations(events):
    return sum(
        _count(event.get("duration_ms"))
        for event in events if isinstance(event, dict) and event.get("type") == "result"
    )


def _count_results(events):
    return sum(1 for event in events if isinstance(event, dict) and event.get("type") == "result")


def _inside_work_tree(folder):
    """True when `folder` or any folder above it holds a `.git` entry (a folder,
    or a file for a linked worktree). `folder` need not exist."""
    here = Path(os.path.realpath(folder))
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            return True
    return False


def _check_choice(name, value, allowed, optional=False):
    if value is None and optional:
        return
    if value not in allowed:
        raise ValueError(f"{name} is not one of {', '.join(allowed)}")


def record_session(events, *, role, outcome, arm=None, plugin_sha=None, private_root=None):
    """Append one record row for the session that produced `events`; return it.

    Raises ValueError for a role, outcome, arm or commit id outside its allowed
    shape, and Refused when the records folder would sit inside a git work tree.
    Nothing is written in either case.
    """
    events = list(events)
    _check_choice("role", role, ROLES)
    _check_choice("outcome", outcome, OUTCOMES)
    _check_choice("arm", arm, ARMS, optional=True)
    if plugin_sha is not None:
        if not isinstance(plugin_sha, str) or not _COMMIT_ID.fullmatch(plugin_sha.lower()):
            raise ValueError("plugin_sha is not a hexadecimal commit id")
        plugin_sha = plugin_sha.lower()

    root = Path(private_root) if private_root is not None else default_private_root()
    folder = root / "records"
    if _inside_work_tree(folder):
        raise Refused("records stay outside git work trees")

    totals = count_tokens(events)
    weighted, unpriced = weigh(totals)
    row = {
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "machine": sensorlib.machine_id(),
        "role": role,
        "outcome": outcome,
        "arm": arm,
        "plugin_sha": plugin_sha,
        "claude_code_version": _first_version(events),
        "results": _count_results(events),
        "duration_ms": _sum_durations(events),
        "models": totals,
        "weighted": weighted,
        "unpriced_models": unpriced,
    }
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / f"{row['machine']}.jsonl", "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row) + "\n")
    return row
