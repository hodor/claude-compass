"""`compass sessions list | show | record` - the project's past sessions.

`list` ranks the top-level `<session-id>.jsonl` files in the project's Claude
Code transcript folder. A session is a feature session when its entrypoint is
`cli` and its commit count (subagents included) reaches `--min-commits`
(default 10). The default view shows feature sessions only; `--all` shows
every session. Each row carries the facts a human needs to pick sessions to
clone: commits, plan and task ids, model, tokens used, headroom against the
model's window, last modified time, and whether the session is still active.
`--grep PATTERN` keeps only sessions whose conversation matches the regular
expression, case-insensitively: the text of user and assistant messages, tool
call inputs and tool results, in the session and its subagents. Record
metadata such as `cwd` and `gitBranch` is never searched, and `^` and `$`
anchor to one piece of text.

Each row estimates what cloning the session costs: `est_cost_usd` is `used`
times a dollar rate per million inherited tokens. A clone re-reads its whole
inherited context on every turn, so the rate is measured, never priced: it is
total cost over total inherited tokens across every past clone recorded in a
`run.json` under `<compass-home>/sessions/`, and `est_basis` names how many
clones it rests on. With no such clone the rate is `DEFAULT_USD_PER_MTOK` and
`est_basis` is `default`.

`--json` prints the rows as one JSON list. Run from a linked git worktree,
`list` reads the main checkout's folder, where the project's sessions live.
An empty result names the folder it read on stderr.

`show` prints a transcript as plain text: assistant words verbatim and each
tool call as one `[tool] <Name> <input>` line. It takes a file path, or
`<run-id>/<session-id>` for a kept clone under the central session folder.

`record` appends one row of lesson names and counts to
`<vault>/meta/clone-log.jsonl`.

Transcripts are only opened for reading. Every failure prints a message on
stderr and returns 1; the command never exits 2.
"""

import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

import sessionslib
import vaultlib
from commands import context_check

FEATURE_ENTRYPOINT = "cli"
DEFAULT_MIN_COMMITS = 10
# A count longer than this is refused before int() sees it, which raises on
# very long digit strings.
MAX_DIGITS = 9
CLONE_LOG = Path("meta") / "clone-log.jsonl"
# Dollars per million inherited tokens when no past clone is recorded. A
# ten-clone run of 0.7M to 0.9M-token sessions measured $378 per million
# overall and $167 to $656 per clone.
DEFAULT_USD_PER_MTOK = 400

TABLE_COLUMNS = ["SESSION", "ENTRYPOINT", "COMMITS", "PLANS", "TASKS", "MODEL", "USED",
                 "HEADROOM", "MODIFIED", "ACTIVE", "FEATURE"]

USAGE = (
    "usage: compass sessions list [--json] [--min-commits N] [--all] [--grep PATTERN]\n"
    "       compass sessions show <path | run-id/session-id>\n"
    "       compass sessions record <run-id> [--written NAME...] [--merged NAME...] [--rejected N]\n"
)


class UsageError(Exception):
    """A bad argument; the message goes to stderr and the exit code is 1."""


def _fail(message):
    sys.stderr.write(f"compass sessions: {message}\n")
    return 1


def _count(raw, option):
    """The integer of 0 or more in `raw`, or UsageError."""
    if raw is None or not re.fullmatch(r"[0-9]{1,%d}" % MAX_DIGITS, raw):
        shown = "missing" if raw is None else repr(raw[:40])
        raise UsageError(f"{option} needs an integer of 0 or more, got {shown}")
    return int(raw)


def _project_root():
    return sessionslib.main_checkout(vaultlib.find_vault_root().parent)


def _iso(epoch):
    """The ISO-8601 UTC time of `epoch`, or "-" when the platform cannot
    represent it."""
    try:
        return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")
    except (OSError, OverflowError, ValueError):
        return "-"


def _cell(value):
    return "-" if value is None or value == "" or value == [] else str(value)


# list ------------------------------------------------------------------

def _parse_list(args):
    options = {"json": False, "all": False, "min_commits": DEFAULT_MIN_COMMITS, "grep": None}
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--json":
            options["json"] = True
        elif arg == "--all":
            options["all"] = True
        elif arg == "--min-commits":
            index += 1
            options["min_commits"] = _count(args[index] if index < len(args) else None, "--min-commits")
        elif arg.startswith("--min-commits="):
            options["min_commits"] = _count(arg[len("--min-commits="):], "--min-commits")
        elif arg == "--grep":
            index += 1
            options["grep"] = _pattern(args[index] if index < len(args) else None)
        elif arg.startswith("--grep="):
            options["grep"] = _pattern(arg[len("--grep="):])
        else:
            raise UsageError(f"unknown argument {arg[:40]!r}")
        index += 1
    return options


def _pattern(raw):
    """`raw` compiled as a case-insensitive regular expression, or UsageError."""
    if not raw:
        raise UsageError("--grep needs a pattern")
    try:
        return re.compile(raw, re.IGNORECASE)
    except re.error as exc:
        raise UsageError(f"--grep pattern {raw[:40]!r} is invalid: {exc}") from exc


def _texts(content):
    """Every piece of conversation text in a message's `content`: plain
    strings, text blocks, tool call inputs as compact JSON, and tool
    results, which nest content of their own."""
    if isinstance(content, str):
        yield content
        return
    if not isinstance(content, list):
        return
    for block in content:
        if isinstance(block, str):
            yield block
        elif not isinstance(block, dict):
            continue
        elif block.get("type") == "text" and isinstance(block.get("text"), str):
            yield block["text"]
        elif block.get("type") == "tool_use":
            yield _compact(block.get("input", {}))
        elif block.get("type") == "tool_result":
            yield from _texts(block.get("content"))


def _mentions(path, pattern):
    """True when any message text of the transcript at `path`, or of one of
    its subagent transcripts, matches `pattern`."""
    for transcript in (path, *sessionslib.subagent_transcripts(path)):
        for record in sessionslib.records(transcript):
            if record.get("type") not in ("user", "assistant"):
                continue
            message = record.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if any(pattern.search(text) for text in _texts(content)):
                return True
    return False


def _amount(value):
    """`value` as a finite float of 0 or more, else None. JSON booleans,
    NaN, Infinity and integers too large for a float are refused."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
    except OverflowError:
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _cost_rate():
    """`(usd_per_million_tokens, basis)` measured from every past clone row
    holding both a positive `used` and a `cost_usd` of 0 or more, each a
    finite number."""
    cost = used = clones = 0
    root = sessionslib.compass_home() / "sessions"
    for record in sorted(root.glob("*/*/run.json")) if root.is_dir() else ():
        try:
            rows = json.loads(record.read_bytes()).get("clones")
        except (OSError, ValueError, AttributeError, RecursionError):
            continue
        for row in rows if isinstance(rows, list) else ():
            if not isinstance(row, dict):
                continue
            row_used, row_cost = _amount(row.get("used")), _amount(row.get("cost_usd"))
            if row_used and row_cost is not None and math.isfinite(used + row_used):
                cost += row_cost
                used += row_used
                clones += 1
    if not clones:
        return DEFAULT_USD_PER_MTOK, "default"
    return cost / used * 1_000_000, f"{clones} past clone{'s' if clones != 1 else ''}"


def _session_row(path, mtime, min_commits):
    model = sessionslib.model_id(path)
    used = sessionslib.used_tokens(path)
    window = context_check.window_for(model) if model is not None else None
    headroom = window - used if window is not None and used is not None else None
    entry = sessionslib.entrypoint(path)
    commits = sessionslib.commit_count(path)
    return {
        "session_id": path.stem,
        "entrypoint": entry,
        "commits": commits,
        "plans": sessionslib.plan_ids(path),
        "tasks": sessionslib.task_ids(path),
        "model": model,
        "used": used,
        "window": window,
        "headroom": headroom,
        "modified": _iso(mtime),
        "active": sessionslib.is_active(path),
        "feature": entry == FEATURE_ENTRYPOINT and commits >= min_commits,
    }


def _session_rows(options):
    folder = sessionslib.transcripts_dir(_project_root())
    if not folder.is_dir():
        return []
    rate, basis = _cost_rate()
    found = []
    for path in folder.glob("*.jsonl"):
        try:
            if path.is_file():
                found.append((path.stat().st_mtime, path))
        except OSError:
            continue
    found.sort(key=lambda item: (-item[0], item[1].name))
    rows = []
    for mtime, path in found:
        try:
            row = _session_row(path, mtime, options["min_commits"])
        except OSError:
            continue
        if not (options["all"] or row["feature"]):
            continue
        if options["grep"] is not None:
            try:
                if not _mentions(path, options["grep"]):
                    continue
            except OSError:
                continue
        row["est_cost_usd"] = None if row["used"] is None else round(row["used"] * rate / 1_000_000, 2)
        row["est_basis"] = basis
        rows.append(row)
    return rows


def _table(rows):
    lines = [" ".join(TABLE_COLUMNS)]
    for row in rows:
        cells = [
            row["session_id"],
            row["entrypoint"],
            row["commits"],
            ",".join(row["plans"]),
            ",".join(row["tasks"]),
            row["model"],
            row["used"],
            row["headroom"],
            row["modified"],
            "yes" if row["active"] else "no",
            "yes" if row["feature"] else "no",
        ]
        lines.append(" ".join(_cell(c) for c in cells))
    return "\n".join(lines) + "\n"


def _list(args):
    options = _parse_list(args)
    rows = _session_rows(options)
    if not rows:
        folder = sessionslib.transcripts_dir(_project_root())
        sys.stderr.write(f"compass sessions: no sessions listed from {folder}\n")
    if options["json"]:
        sys.stdout.write(json.dumps(rows, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(_table(rows))
    return 0


# show ------------------------------------------------------------------

def _unsafe_component(part):
    """True for a run or session id that is empty, climbs, holds a path
    separator, or carries a drive (a `:` re-roots a Windows join)."""
    return (part in ("", ".", "..") or "\\" in part or ":" in part
            or bool(PureWindowsPath(part).drive))


def _resolve_transcript(target):
    """The transcript path named by `target`: an existing file, else
    `<run-id>/<session-id>` under the central run folder."""
    direct = Path(target)
    if direct.is_file():
        return direct
    if direct.exists():
        raise UsageError(f"{target} is not a file")
    parts = target.split("/")
    if len(parts) != 2 or any(_unsafe_component(p) for p in parts):
        raise UsageError(f"{target} is neither a file nor a <run-id>/<session-id>")
    run_id, session_id = parts
    folder = sessionslib.run_dir(_project_root(), run_id)
    path = folder / f"{session_id}.jsonl"
    try:
        inside = path.resolve().is_relative_to(folder.resolve())
    except (OSError, ValueError):
        inside = False
    if not inside or not path.is_file():
        raise UsageError(f"no kept clone transcript at {path}")
    return path


def _compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _render_record(record):
    """The text lines an assistant record contributes, in block order."""
    if record.get("type") != "assistant":
        return []
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return [content] if content else []
    if not isinstance(content, list):
        return []
    lines = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                lines.append(text)
        elif kind == "tool_use" and isinstance(block.get("name"), str):
            lines.append(f"[tool] {block['name']} {_compact(block.get('input', {}))}")
    return lines


def _show(args):
    if len(args) != 1:
        raise UsageError("show needs exactly one <path | run-id/session-id>")
    path = _resolve_transcript(args[0])
    try:
        lines = [line for record in sessionslib.records(path) for line in _render_record(record)]
    except OSError as exc:
        raise UsageError(f"could not read {path}: {exc}") from exc
    if lines:
        sys.stdout.write("\n".join(lines) + "\n")
    return 0


# record ----------------------------------------------------------------

def _parse_record(args):
    run_id = None
    names = {"--written": [], "--merged": []}
    rejected = 0
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in names:
            index += 1
            while index < len(args) and not args[index].startswith("--"):
                names[arg].append(args[index])
                index += 1
            continue
        if arg == "--rejected":
            index += 1
            rejected = _count(args[index] if index < len(args) else None, "--rejected")
        elif arg.startswith("--rejected="):
            rejected = _count(arg[len("--rejected="):], "--rejected")
        elif arg.startswith("--"):
            raise UsageError(f"unknown argument {arg[:40]!r}")
        elif run_id is None:
            run_id = arg
        else:
            raise UsageError(f"unexpected argument {arg[:40]!r}")
        index += 1
    if not run_id:
        raise UsageError("record needs a <run-id>")
    return run_id, names["--written"], names["--merged"], rejected


def _append_line(path, line):
    """Append `line` plus a newline, first ending an unterminated last row."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as fh:
        fh.seek(0, 2)
        needs_break = False
        if fh.tell() > 0:
            fh.seek(-1, 2)
            needs_break = fh.read(1) != b"\n"
        fh.seek(0, 2)
        fh.write((b"\n" if needs_break else b"") + line.encode("utf-8") + b"\n")


def _record(args):
    run_id, written, merged, rejected = _parse_record(args)
    row = {
        "event": "run",
        "run_id": run_id,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "written": written,
        "merged": merged,
        "written_count": len(written),
        "merged_count": len(merged),
        "rejected": rejected,
    }
    for text in [run_id, *written, *merged]:
        try:
            text.encode("utf-8")
        except UnicodeEncodeError:
            raise UsageError("record names must be valid text (an argument holds an undecodable byte)")
    try:
        _append_line(vaultlib.find_vault_root() / CLONE_LOG, json.dumps(row))
    except OSError as exc:
        raise UsageError(f"could not write the clone log: {exc}") from exc
    return 0


COMMANDS = {"list": _list, "show": _show, "record": _record}


def run(args):
    for stream, errors in ((sys.stdout, "replace"), (sys.stderr, "backslashreplace")):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors=errors)
    if not args or args[0] not in COMMANDS:
        sys.stderr.write(USAGE)
        return 1
    try:
        return COMMANDS[args[0]](args[1:])
    except UsageError as exc:
        return _fail(str(exc))
    except FileNotFoundError as exc:
        return _fail(str(exc))
