"""Compares two sets of saved token profiles per launched agent type.

A set is a folder of `token_profile.py --json` outputs (one file per build).
For each agent type the report gives the number of launches and the mean
weighted tokens per launch in each set, the change, and a bootstrap 95%
interval of the change in the mean, resampling sessions with a fixed seed.
Agent types outside Compass's public names print as `(other)`; no folder or
file name of an input reaches the report.

Outcome folders hold one JSON file per build: the judge's verdict (its
`counts` of goals scored `met`, `partly met` and `not met`) and the build's
test result (`recorded.builder_tests`, or a top-level `tests`). When the two
sets' outcome counts differ, the report says "outcome differs" and prints no
token comparison, since a cheaper set that built less is not a saving.

    python compare.py BEFORE AFTER [--outcomes-before DIR --outcomes-after DIR] [--plugin-root DIR]
"""

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

import token_profile

SEED = 20261105
RESAMPLES = 2000
SCORES = ("met", "partly met", "not met")


def _json_files(folder):
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError("a folder of saved results does not exist")
    files = sorted(folder.glob("*.json"))
    if not files:
        raise ValueError("a folder of saved results holds no JSON file")
    return files


def _load(path):
    try:
        item = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("a saved result is not readable JSON") from None
    if not isinstance(item, dict):
        raise ValueError("a saved result is not a JSON object")
    return item


def load_profiles(folder):
    """{agent key: [weighted tokens of each session]} pooled over the profile
    files in `folder`. Raises ValueError for a missing or empty folder, an
    unreadable file, or a profile saved without `by_agent`."""
    pooled = {}
    for path in _json_files(folder):
        by_agent = _load(path).get("by_agent")
        if not isinstance(by_agent, dict):
            raise ValueError("a saved profile has no by_agent table; profile it again")
        for kind, entry in by_agent.items():
            sessions = entry.get("session_weighted") if isinstance(entry, dict) else None
            if not isinstance(sessions, list):
                raise ValueError("a saved profile has a by_agent entry without session_weighted")
            pooled.setdefault(kind, []).extend(float(value) for value in sessions)
    return pooled


def load_outcomes(folder):
    """{"goals": {score: count}, "tests": {result: count}} summed over the
    outcome files in `folder`. Raises ValueError when the folder holds no
    file or a file has no goal counts."""
    goals = dict.fromkeys(SCORES, 0)
    tests = {}
    for path in _json_files(folder):
        item = _load(path)
        counts = item.get("counts")
        if not isinstance(counts, dict):
            raise ValueError("an outcome file has no goal counts")
        for score in SCORES:
            goals[score] += int(counts.get(score) or 0)
        recorded = item.get("recorded")
        result = item.get("tests", recorded.get("builder_tests") if isinstance(recorded, dict) else None)
        key = str(result) if result is not None else "none"
        tests[key] = tests.get(key, 0) + 1
    return {"goals": goals, "tests": tests}


def bootstrap_interval(before, after, seed=SEED, resamples=RESAMPLES):
    """(low, high) of the 95% bootstrap interval of mean(after) - mean(before),
    resampling each side's sessions with replacement from a generator seeded
    with `seed`; None when either side has fewer than two sessions."""
    if len(before) < 2 or len(after) < 2:
        return None
    rng = random.Random(seed)
    changes = []
    for _ in range(resamples):
        resampled_before = rng.choices(before, k=len(before))
        resampled_after = rng.choices(after, k=len(after))
        changes.append(sum(resampled_after) / len(after) - sum(resampled_before) / len(before))
    changes.sort()
    low = changes[int(0.025 * (resamples - 1))]
    high = changes[int(round(0.975 * (resamples - 1)))]
    return float(low), float(high)


def _public(pooled, known):
    """{display name: [sessions]} with agent types outside the public names
    pooled as `(other)`."""
    table = {}
    for kind, sessions in pooled.items():
        name = token_profile.public_phase(kind, known)
        name = name[len("subagent:"):] if name.startswith("subagent:") else name
        table.setdefault(name, []).extend(sessions)
    return table


def _signed(value):
    return f"{value:+.0f}"


def _interval_text(interval):
    return "n/a" if interval is None else f"{interval[0]:+.0f} to {interval[1]:+.0f}"


def render_tokens(before, after, known):
    before, after = _public(before, known), _public(after, known)
    names = sorted(set(before) | set(after))
    lines = [
        "| Agent type | Launches before | Launches after | Mean before | Mean after | Change | Change % | 95% interval |",
        "|---|---|---|---|---|---|---|---|",
    ]
    shown = 0
    for name in names:
        old, new = before.get(name, []), after.get(name, [])
        if not old and not new:
            continue
        shown += 1
        mean_old = statistics.fmean(old) if old else None
        mean_new = statistics.fmean(new) if new else None
        if old and new:
            change = mean_new - mean_old
            percent = f"{change / mean_old:+.1%}" if mean_old else "n/a"
            cells = [_signed(change), percent, _interval_text(bootstrap_interval(old, new))]
        else:
            side = "before" if old else "after"
            cells = [f"only in {side}", "n/a", "n/a"]
        lines.append(
            f"| {name} | {len(old)} | {len(new)} | "
            f"{'n/a' if mean_old is None else f'{mean_old:.0f}'} | "
            f"{'n/a' if mean_new is None else f'{mean_new:.0f}'} | " + " | ".join(cells) + " |"
        )
    if not shown:
        return "No agent sessions in either set."
    return "\n".join(lines)


def _outcome_text(outcome):
    goals = ", ".join(f"{score} {outcome['goals'][score]}" for score in SCORES)
    tests = ", ".join(f"{result} {count}" for result, count in sorted(outcome["tests"].items()))
    return f"{goals}; tests {tests}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--outcomes-before")
    parser.add_argument("--outcomes-after")
    parser.add_argument("--plugin-root", default=str(Path(__file__).resolve().parents[2] / "plugin"))
    args = parser.parse_args(argv)
    if (args.outcomes_before is None) != (args.outcomes_after is None):
        sys.stderr.write("give both --outcomes-before and --outcomes-after, or neither\n")
        return 2
    try:
        before, after = load_profiles(args.before), load_profiles(args.after)
        outcomes = None
        if args.outcomes_before is not None:
            outcomes = load_outcomes(args.outcomes_before), load_outcomes(args.outcomes_after)
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        return 2
    lines = []
    if outcomes is not None:
        if outcomes[0] != outcomes[1]:
            sys.stdout.write(
                "outcome differs, so no token verdict.\n"
                f"- before: {_outcome_text(outcomes[0])}\n- after: {_outcome_text(outcomes[1])}\n"
            )
            return 0
        lines += [f"Outcomes match: {_outcome_text(outcomes[0])}.", ""]
    lines.append(render_tokens(before, after, token_profile.compass_names(args.plugin_root)))
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
