"""`compass capture-stats [--json] [--since YYYY-MM-DD]` - fire and write
rates from the capture trace log.

Reads `.compass/tmp/capture-log.jsonl` (append-only, one JSON object per
line, written by `capturelib.open_opportunity`, `capturelib.close_opportunity`,
and `capturelib.due_and_log`) and reports how many opportunities opened, what
fraction fired (an extraction pass actually ran, whether or not it wrote
anything), what fraction wrote at least one lesson, and a per-trigger
breakdown of what caused an opportunity to open. A line that fails to parse,
is not a JSON object, or names an event outside the known set is skipped
rather than raising, since the log accumulates across many sessions and one
bad line must never sink the whole report.
"""

import datetime
import json
import sys

import vaultlib

KNOWN_EVENTS = {"opened", "skipped", "fired", "closed"}


def _log_path(vault_root):
    return vault_root / "tmp" / "capture-log.jsonl"


def _valid_since(value):
    """`True` when `value` parses as `YYYY-MM-DD`."""
    try:
        datetime.datetime.strptime(value, "%Y-%m-%d")
    except (ValueError, TypeError):
        return False
    return True


def load_rows(vault_root, since=None):
    """Every well-formed row from the capture log, oldest first. `since` (a
    `YYYY-MM-DD` string) drops rows whose `at` timestamp sorts before that
    date. A missing log is an empty list, not an error - "never ran" is a
    valid state for a vault that has not reached a capture opportunity yet.
    """
    path = _log_path(vault_root)
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or row.get("event") not in KNOWN_EVENTS:
            continue
        at = row.get("at")
        if since and not (isinstance(at, str) and at[:10] >= since):
            continue
        rows.append(row)
    return rows


def compute_stats(rows):
    """Aggregate trace rows into opened/fired/written counts, the fire and
    write rates against opened opportunities, and a per-trigger breakdown of
    the `opened` rows' `triggers` lists (a row with more than one trigger
    counts once per trigger, since each named a reason the opportunity was
    due)."""
    opened = [r for r in rows if r.get("event") == "opened"]
    fired = [r for r in rows if r.get("event") == "fired"]
    written = [
        r for r in fired
        if isinstance(r.get("written"), (int, float)) and r["written"] > 0
    ]

    triggers = {}
    for row in opened:
        for trigger in row.get("triggers") or []:
            triggers[trigger] = triggers.get(trigger, 0) + 1

    opened_n, fired_n, written_n = len(opened), len(fired), len(written)
    return {
        "opened": opened_n,
        "fired": fired_n,
        "fire_rate": (fired_n / opened_n) if opened_n else 0.0,
        "written": written_n,
        "write_rate": (written_n / opened_n) if opened_n else 0.0,
        "triggers": dict(sorted(triggers.items())),
    }


def format_report(stats):
    lines = [
        f"opportunities opened: {stats['opened']}",
        f"fired: {stats['fired']} ({stats['fire_rate'] * 100:.1f}%)",
        f"written: {stats['written']} ({stats['write_rate'] * 100:.1f}%)",
    ]
    if stats["triggers"]:
        lines.append("per-trigger:")
        for trigger, count in stats["triggers"].items():
            lines.append(f"  {trigger}: {count}")
    else:
        lines.append("per-trigger: none")
    return "\n".join(lines)


def run(args):
    as_json = "--json" in args
    since = None
    if "--since" in args:
        idx = args.index("--since")
        if idx + 1 >= len(args) or not _valid_since(args[idx + 1]):
            sys.stderr.write("compass capture-stats: --since expects a YYYY-MM-DD value\n")
            return 1
        since = args[idx + 1]

    vault_root = vaultlib.find_vault_root()
    stats = compute_stats(load_rows(vault_root, since=since))

    if as_json:
        sys.stdout.write(json.dumps(stats) + "\n")
    else:
        sys.stdout.write(format_report(stats) + "\n")
    return 0
