"""`compass sizing stats` - report the sizing decision log, and the shared
plumbing `make-unit`, `promote`, and `demote` use to write to it.

A sizing decision is made whenever one of those three commands changes a
vault artifact's shape under `--apply`: `make-unit` (flat/folder artifacts
into a unit), `promote` (a flat spec into a folder spec), or their inverses,
`make-unit --undo` and `demote`. Each records itself - the harness owns the
trigger and the write, never an agent's memory (ADR-011 D-03, D-08).

Every row lives in `.compass/meta/sizing-log.yaml` under a `log:` block
list, one entry per decision or correction:

    log:
      - id: sz-2026-08-23-1
        action: decision
        shape: unit
        subject: core
        reason: "reserve the workspace"
        by: agent
        at: 2026-08-23
        volatile: []

`id` is `sz-<date>-<n>`, minted once at decision time and written into the
subject artifact's own frontmatter (`sizing_id:`), so it survives every
`git mv` the three commands perform - a path or a bare stem does not, since
`promote` changes the path and bare stems are ambiguous across units. A
`demote` or `--undo` correction row carries the SAME id and the SAME
`shape` as the decision it reverses (a demote correcting a folder decision
is itself `shape: folder`, even though the artifact ends up flat again),
joining the pair for an audit. `action` is `decision` for `make-unit` and
`promote`, `correction` for their inverses. `shape` is `unit` for
`make-unit`, `folder` for `promote`/`demote`; `spec` is reserved for a
"stays flat" decision no command in this module writes yet.

The log is read-modify-write via `vaultlib.read_vault_text` (BOM-tolerant,
CRLF-normalizing) then `vaultlib.write_text_lf` - an append-mode open would
emit CRLF on Windows, and `write_text_lf` truncates, so the existing text
must be read first. A corrupt row is reported and skipped, never raised: a
bad row must not take down a shape-changing command's own write.
"""

import datetime
import re
import sys

import vaultlib

ROW_START = re.compile(r"^  - id:\s*(.+)$")
FIELD = re.compile(r"^    ([A-Za-z0-9_]+):\s*(.*)$")
LIST_ITEM = re.compile(r"^      - (.*)$")

REQUIRED_FIELDS = ("action", "shape", "subject", "reason", "by", "at")


def log_path(vault_root):
    return vault_root / "meta" / "sizing-log.yaml"


def _quote(value):
    """Wrap free text in double quotes, escaping any embedded quote. The
    sizing log has no YAML parser behind it beyond this module's own
    regexes, so this is a minimal, self-consistent quoting scheme rather
    than a general YAML emitter."""
    text = "" if value is None else str(value)
    return '"' + text.replace('"', '\\"') + '"'


def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1].replace('\\"', '"')
    return value


def parse_flags(args):
    """Hand-parse the sizing flags shared by `make-unit`, `promote`, and
    `demote`: `--reason <text>` (single value, last wins, never blank),
    `--volatile <text>` (repeatable), `--by human|agent` (defaults to
    `agent`). Hand-parsed rather than via `argparse`, so a malformed
    invocation reports through this function's own `error` return instead
    of `argparse`'s `SystemExit(2)`.

    Returns `(remaining, reason, volatile, by, error)`. `remaining` is
    `args` with every consumed flag and its value removed, in order, so a
    caller's own `--apply`/positional handling is unaffected. `error` is a
    short string when a flag is missing its value, `--reason` is blank or
    all-whitespace, or `--by` names anything but human or agent; every
    other field still holds its default so a caller need not special-case
    the error path before reporting it.
    """
    remaining = []
    reason = None
    volatile = []
    by = "agent"
    error = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--reason", "--volatile", "--by"):
            if i + 1 >= len(args):
                if error is None:
                    error = f"{arg} requires a value"
                i += 1
                continue
            value = args[i + 1]
            if arg == "--reason":
                if not value.strip():
                    if error is None:
                        error = "--reason must not be blank"
                else:
                    reason = value
            elif arg == "--volatile":
                volatile.append(value)
            else:
                if value not in ("human", "agent"):
                    if error is None:
                        error = f"--by must be human or agent, got: {value}"
                else:
                    by = value
            i += 2
            continue
        remaining.append(arg)
        i += 1
    return remaining, reason, volatile, by, error


MINTED_ID = re.compile(r"^  - id:\s*sz-(\d{4}-\d{2}-\d{2})-(\d+)\s*$")


def mint_id(vault_root):
    """Mint the next `sz-<date>-<n>` id for today, `<n>` being one past the
    highest existing suffix already recorded for today's date. Scans only
    `  - id: sz-...` lines (`MINTED_ID`, the exact shape `_format_row`
    writes), not `parse_log`'s full row parser and not the row's other
    fields - a `reason` or `subject` value that happens to mention another
    id as free text can never inflate the count, and a malformed
    neighboring row can never suppress or collide with a fresh one."""
    today = datetime.date.today().isoformat()
    path = log_path(vault_root)
    existing = []
    if path.is_file():
        text = vaultlib.read_vault_text(path)
        for line in text.splitlines():
            match = MINTED_ID.match(line)
            if match and match.group(1) == today:
                existing.append(int(match.group(2)))
    n = max(existing, default=0) + 1
    return f"sz-{today}-{n}"


def stamp_id(path, sizing_id):
    """Insert `sizing_id: <id>` into `path`'s frontmatter, just before the
    closing `---`, unless the key is already present. Mirrors
    `promote._add_children_count`'s insert-before-close technique so every
    other line survives untouched."""
    lines = vaultlib.read_vault_text(path).split("\n")
    closing = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if closing is not None and not any(l.startswith("sizing_id:") for l in lines[:closing]):
        lines.insert(closing, f"sizing_id: {sizing_id}")
    vaultlib.write_text_lf(path, "\n".join(lines))


def _format_row(row):
    lines = [
        f"  - id: {row['id']}",
        f"    action: {row['action']}",
        f"    shape: {row['shape']}",
        f"    subject: {_quote(row['subject'])}",
        f"    reason: {_quote(row['reason'])}",
        f"    by: {row['by']}",
        f"    at: {row['at']}",
    ]
    volatile = row.get("volatile") or []
    if volatile:
        lines.append("    volatile:")
        for item in volatile:
            lines.append(f"      - {_quote(item)}")
    else:
        lines.append("    volatile: []")
    return "\n".join(lines) + "\n"


def append_row(vault_root, row):
    """Append one row to `.compass/meta/sizing-log.yaml`, read-modify-write.

    Reads the existing text through `vaultlib.read_vault_text` (BOM and
    CRLF tolerant) and writes the result through `vaultlib.write_text_lf`
    (LF-only, truncating) - a plain append-mode open would emit CRLF on
    Windows, and `write_text_lf` truncates, so the prior content has to be
    read first rather than assumed away.
    """
    path = log_path(vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        text = vaultlib.read_vault_text(path)
    else:
        text = ""
    if not text.strip():
        text = "log:\n"
    text = text.rstrip("\n") + "\n" + _format_row(row)
    vaultlib.write_text_lf(path, text)


def parse_log(text):
    """Parse every row in sizing-log `text`. Returns `(rows, skipped)`.

    Never raises. A line starting `  - id: ` opens a row; a `  - ` line
    that does not match that shape is itself a malformed row and is
    counted in `skipped` without disturbing whatever row came before or
    after it. A row missing any of `REQUIRED_FIELDS` is dropped and
    counted in `skipped` too, so one corrupt row can never take down a
    `sizing stats` read.
    """
    rows = []
    skipped = 0
    current = None

    def finalize():
        nonlocal skipped
        if current is None:
            return
        row_id = current.get("id", "").strip()
        missing = not row_id or any(not current.get(f, "").strip() for f in REQUIRED_FIELDS)
        if missing:
            skipped += 1
            return
        rows.append({
            "id": row_id,
            "action": _unquote(current["action"]),
            "shape": _unquote(current["shape"]),
            "subject": _unquote(current["subject"]),
            "reason": _unquote(current["reason"]),
            "volatile": [_unquote(v) for v in current.get("volatile", [])],
            "by": _unquote(current["by"]),
            "at": _unquote(current["at"]),
        })

    for line in text.splitlines():
        start = ROW_START.match(line)
        if start:
            finalize()
            current = {"id": start.group(1).strip(), "volatile": [], "_last_field": None}
            continue
        if line.startswith("  - "):
            # A `- ` list item at row-start indent that is not `- id: ...`
            # is itself a malformed row - close out whatever came before
            # and count this line as its own skip.
            finalize()
            current = None
            skipped += 1
            continue
        field = FIELD.match(line) if current is not None else None
        if field:
            key, value = field.group(1), field.group(2).strip()
            if key == "volatile":
                if value not in ("", "[]"):
                    current["volatile"] = [value]
                    current["_last_field"] = None
                else:
                    current["volatile"] = []
                    current["_last_field"] = "volatile"
            else:
                current[key] = value
                current["_last_field"] = key
            continue
        item = LIST_ITEM.match(line) if current is not None else None
        if item and current.get("_last_field") == "volatile":
            current["volatile"].append(item.group(1))
            continue
    finalize()
    return rows, skipped


def _run_stats(args):
    vault_root = vaultlib.find_vault_root()
    path = log_path(vault_root)
    text = vaultlib.read_vault_text(path) if path.is_file() else ""
    rows, skipped = parse_log(text)

    decisions = [r for r in rows if r["action"] == "decision"]
    corrections = [r for r in rows if r["action"] == "correction"]
    by_shape = {}
    for row in decisions:
        by_shape[row["shape"]] = by_shape.get(row["shape"], 0) + 1
    by_provenance = {}
    for row in rows:
        by_provenance[row["by"]] = by_provenance.get(row["by"], 0) + 1

    lines = [
        f"compass sizing stats: {len(decisions)} decision(s), "
        f"{len(corrections)} correction(s)",
    ]
    for shape in sorted(by_shape):
        lines.append(f"  decisions by shape: {shape}: {by_shape[shape]}")
    for who in sorted(by_provenance):
        lines.append(f"  provenance: {who}: {by_provenance[who]}")
    if skipped:
        lines.append(f"  {skipped} malformed row(s) skipped")
    if not corrections:
        lines.append(
            "  0 corrections is uninterpretable without the audit denominator "
            "(the blind re-audit of mis-sized decisions is not built yet) - "
            "it is not, on its own, a clean bill of health"
        )
    else:
        rate = len(corrections) / len(decisions) if decisions else 0.0
        lines.append(f"  correction rate: {rate:.0%} of {len(decisions)} decision(s)")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def run(args):
    if not args:
        sys.stderr.write("usage: compass sizing stats\n")
        return 1
    sub, rest = args[0], args[1:]
    if sub == "stats":
        return _run_stats(rest)
    sys.stderr.write(f"compass sizing: unknown subcommand: {sub}\n")
    return 1
