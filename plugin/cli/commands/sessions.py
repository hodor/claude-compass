"""`compass sessions list | show | record` - the project's past sessions.

`list` ranks the top-level `<session-id>.jsonl` files in the project's Claude
Code transcript folder. A session is a feature session when its entrypoint is
`cli` and its commit count (subagents included) reaches `--min-commits`
(default 10). The default view shows feature sessions only; `--all` shows
every session. Each row carries the facts a human needs to pick sessions to
clone: commits, plan and task ids, model, tokens used, headroom against the
model's window, last modified time, and whether the session is still active.
`--json` prints the rows as one JSON list.

`show` prints a transcript as plain text: assistant words verbatim and each
tool call as one `[tool] <Name> <input>` line. It takes a file path, or
`<run-id>/<session-id>` for a kept clone under the central session folder.

`record` appends one row of lesson names and counts to
`<vault>/meta/clone-log.jsonl`.

Transcripts are only opened for reading. Every failure prints a message on
stderr and returns 1; the command never exits 2.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import sessionslib
import vaultlib
from commands import context_check

FEATURE_ENTRYPOINT = "cli"
DEFAULT_MIN_COMMITS = 10
# A count longer than this is refused before int() sees it, which raises on
# very long digit strings.
MAX_DIGITS = 9
CLONE_LOG = Path("meta") / "clone-log.jsonl"

TABLE_COLUMNS = ["SESSION", "ENTRYPOINT", "COMMITS", "PLANS", "TASKS", "MODEL", "USED",
                 "HEADROOM", "MODIFIED", "ACTIVE", "FEATURE"]

USAGE = (
    "usage: compass sessions list [--json] [--min-commits N] [--all]\n"
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
    return vaultlib.find_vault_root().parent


def _iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def _cell(value):
    return "-" if value is None or value == "" or value == [] else str(value)


# list ------------------------------------------------------------------

def _parse_list(args):
    options = {"json": False, "all": False, "min_commits": DEFAULT_MIN_COMMITS}
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
        else:
            raise UsageError(f"unknown argument {arg[:40]!r}")
        index += 1
    return options


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
        if options["all"] or row["feature"]:
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
    if options["json"]:
        sys.stdout.write(json.dumps(rows, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(_table(rows))
    return 0


# show ------------------------------------------------------------------

def _resolve_transcript(target):
    """The transcript path named by `target`: an existing file, else
    `<run-id>/<session-id>` under the central run folder."""
    direct = Path(target)
    if direct.is_file():
        return direct
    if direct.exists():
        raise UsageError(f"{target} is not a file")
    parts = target.split("/")
    if len(parts) != 2 or any(p in ("", ".", "..") or "\\" in p for p in parts):
        raise UsageError(f"{target} is neither a file nor a <run-id>/<session-id>")
    run_id, session_id = parts
    path = sessionslib.run_dir(_project_root(), run_id) / f"{session_id}.jsonl"
    if not path.is_file():
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
        lines = [line for record in sessionslib._records(path) for line in _render_record(record)]
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
    try:
        _append_line(vaultlib.find_vault_root() / CLONE_LOG, json.dumps(row, ensure_ascii=False))
    except OSError as exc:
        raise UsageError(f"could not write the clone log: {exc}") from exc
    return 0


COMMANDS = {"list": _list, "show": _show, "record": _record}


def run(args):
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")
    if not args or args[0] not in COMMANDS:
        sys.stderr.write(USAGE)
        return 1
    try:
        return COMMANDS[args[0]](args[1:])
    except UsageError as exc:
        return _fail(str(exc))
    except FileNotFoundError as exc:
        return _fail(str(exc))
