"""`compass session-state` - the session's state block, built with no model call.

The block lists what a model needs after a compaction and what a handoff
records mechanically: the human's last request, the open tasks of
`.compass/active.md`, the decisions taken (answers to questions put to the
human, and the D-NN decisions of every vault document the session read or
edited), the files edited and read, the uncommitted changes outside
`.compass/`, the last test run, and the branch with its short commit. Each
comes from the session transcript (and its subagent transcripts), the vault
or git, so a missing source leaves its section out and nothing else.

    compass session-state [--transcript PATH] [--format block|handoff]
                          [--until INDEX] [--at COMMIT]
    compass session-state --hook

`--until INDEX` reads the transcript sections only up to the compaction
boundary on line INDEX (0-based, counting every physical line of the file):
the main transcript's earlier lines and the subagent records stamped at or
before the boundary's own timestamp. `--at COMMIT` takes the open tasks and
the D-NN decisions from that commit, leaves out the uncommitted changes and
names the commit in the branch line. Each works alone, and both are refused
beside `--hook`.

`block` prints the sections under a title, in the order they survive when the
whole stays under the character budget: the last sections are dropped first.
`handoff` prints the four sections the handoff template carries, each
omitted when empty. `--hook` reads one event from stdin (and only under this
flag): SessionStart with source `compact` prints the block as additional
context; PreCompact prints the instructions the summary follows. Subagent
events and capture-worker sessions print nothing. Every path exits 0.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import decisionslib
import sessionslib
import vaultlib

USAGE = """\
compass session-state [--transcript PATH] [--format block|handoff] [--until INDEX] [--at COMMIT]
compass session-state --hook

Print the session's open tasks, files touched, decisions and git state, built
from the transcript, the vault and git. --hook reads a SessionStart or
PreCompact event on stdin. --until INDEX renders the transcript sections as
they stood at the compaction boundary on line INDEX; --at COMMIT takes the open
tasks, decisions and branch line from that commit. Both are refused beside --hook.
"""

BUDGET = 7900
REQUEST_CHARS = 500
TASK_LINE_CHARS = 240
ANSWER_LINE_CHARS = 200
DECISION_LINE_CHARS = 140
TEST_LINE_CHARS = 200
CAPS = {"tasks": 25, "answers": 8, "decisions": 20, "edited": 40, "read": 25, "dirty": 30}
GIT_TIMEOUT = 30
BLOCK_TITLE = "Compass session state"
_OPEN_TASK = re.compile(r"^- \[ \] ")
_EDIT_TOOLS = ("Edit", "Write", "MultiEdit")

PRE_COMPACT_INSTRUCTIONS = """\
When summarizing this conversation, keep these, in this order:
1. The human's intent: what they asked for, in their own words.
2. Every file changed, each with its full path.
3. Decisions taken, each with its reason.
4. Scope exclusions and rules the human stated, verbatim where short.
5. The next step.
Compass re-injects the open tasks, the file lists and the git state after the compaction, so spend the summary on these five.
"""


def _cut(text, limit):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def _capped(lines, cap):
    """The first `cap` lines, then `... and N more` when lines remain."""
    if len(lines) <= cap:
        return list(lines)
    return lines[:cap] + [f"... and {len(lines) - cap} more"]


def _project_root():
    try:
        return vaultlib.find_vault_root().parent
    except FileNotFoundError:
        return Path(os.getcwd())


def _relative(path, root):
    """`path` relative to `root` with forward slashes when it lies inside,
    else `path` with forward slashes."""
    text = path.replace("\\", "/")
    if not os.path.isabs(path):
        return text[2:] if text.startswith("./") else text
    for base in (root, root.resolve()):
        try:
            rel = os.path.relpath(path, base).replace("\\", "/")
        except (ValueError, OSError):
            continue
        if rel != ".." and not rel.startswith("../"):
            return rel
    return text


def _git(root, *args):
    """Stdout of a git command run in `root`, or None when git is missing,
    fails or times out."""
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args], cwd=str(root),
            capture_output=True, timeout=GIT_TIMEOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


class UsageError(Exception):
    """A request the command refuses; `run` prints it and exits 1."""


def _parse_args(args):
    options = {"hook": False, "transcript": None, "format": "block", "until": None, "at": None}
    valued = ("--transcript", "--format", "--until", "--at")
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--hook":
            options["hook"] = True
        elif arg in valued:
            if index + 1 < len(args):
                index += 1
                options[arg[2:]] = args[index]
            elif arg in ("--until", "--at"):
                raise UsageError(f"{arg} needs a value")
        elif arg.startswith(tuple(f"{flag}=" for flag in valued)):
            key, _, value = arg[2:].partition("=")
            options[key] = value
        index += 1
    if options["hook"] and (options["until"] is not None or options["at"] is not None):
        raise UsageError("--until and --at are not available with --hook")
    return options


def _resolve_transcript(explicit, root):
    """The `--transcript` path when it names a file, else the session's own
    transcript, else the newest transcript of the project's folder."""
    if explicit and Path(explicit).is_file():
        return Path(explicit)
    return _default_transcript(root)


def _default_transcript(root):
    """`<transcripts_dir>/<CLAUDE_CODE_SESSION_ID>.jsonl`, else the newest
    transcript of that folder; the folder is the project's, or its main
    checkout's when the project is a linked worktree."""
    folders = []
    for project in (root, sessionslib.main_checkout(root)):
        folder = sessionslib.transcripts_dir(project)
        if folder not in folders:
            folders.append(folder)
    session = os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
    if session and not re.search(r"[\\/]|\.\.", session):
        for folder in folders:
            candidate = folder / f"{session}.jsonl"
            if candidate.is_file():
                return candidate
    for folder in folders:
        try:
            found = [(p.stat().st_mtime, p) for p in folder.glob("*.jsonl") if p.is_file()]
        except OSError:
            continue
        if found:
            return max(found, key=lambda item: item[0])[1]
    return None


def _blocks(record, block_type):
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [b for b in content if isinstance(b, dict) and b.get("type") == block_type]


def _leading_context(lines):
    """The number of unchanged context lines (` `-prefixed) that open a
    `structuredPatch` hunk before its first `-` or `+` line; 0 when the hunk
    holds no changed line or `lines` is not a list of strings."""
    if not isinstance(lines, list):
        return 0
    count = 0
    for text in lines:
        if not isinstance(text, str):
            return 0
        if text.startswith(("-", "+")):
            return count
        count += 1
    return 0


def _edit_start_lines(transcript, root):
    """`{display_path: line}` of the first changed line of each edited path's
    last Edit result, keyed like the file lists (the path relative to `root`):
    the first hunk's `newStart` in its `structuredPatch` plus the context
    lines that open the hunk. A Write or an empty patch has none."""
    starts = {}
    for path in [Path(transcript), *sessionslib.subagent_transcripts(transcript)]:
        calls = {}
        try:
            for record in sessionslib.records(path):
                for block in _blocks(record, "tool_use"):
                    target = (block.get("input") or {}).get("file_path") if isinstance(block.get("input"), dict) else None
                    if block.get("name") in _EDIT_TOOLS and isinstance(target, str) and isinstance(block.get("id"), str):
                        calls[block["id"]] = target
                result = record.get("toolUseResult")
                patch = result.get("structuredPatch") if isinstance(result, dict) else None
                if not isinstance(patch, list) or not patch or not isinstance(patch[0], dict):
                    continue
                line = patch[0].get("newStart") or patch[0].get("oldStart")
                if isinstance(line, bool) or not isinstance(line, int) or line < 1:
                    continue
                line += _leading_context(patch[0].get("lines"))
                for block in _blocks(record, "tool_result"):
                    target = calls.get(block.get("tool_use_id"))
                    if target:
                        starts[_relative(target, root)] = line
        except OSError:
            continue
    return starts


def _safe(default, function, *args):
    try:
        return function(*args)
    except Exception:
        return default


def _touched(transcript, root):
    """`[(display_path, kind, raw_path)]` oldest first, one entry per file."""
    merged = {}
    for raw, kind, _ in sessionslib.touched_files(transcript):
        display = _relative(raw, root)
        previous = merged.pop(display, None)
        if previous is not None and previous[0] == "edited":
            kind = "edited"
        merged[display] = (kind, raw)
    return [(display, kind, raw) for display, (kind, raw) in merged.items()]


def _open_tasks(root, at=None):
    if at:
        text = _git(root, "show", f"{at}:.compass/active.md") or ""
    else:
        try:
            text = (root / ".compass" / "active.md").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
    return [_cut(line, TASK_LINE_CHARS) for line in text.splitlines() if _OPEN_TASK.match(line)]


def _doc_stem(path):
    return path.parent.name if path.stem == "index" else path.stem


def _document_decisions(touched, root, at=None):
    """`<doc-stem>/D-NN: <text>` lines for each vault document the session
    read or edited, the most recently touched document first. With `at`, each
    document's text is its content at that commit and a document absent there
    contributes nothing."""
    try:
        vault = (root / ".compass").resolve()
    except OSError:
        return []
    lines = []
    for _, _, raw in reversed(touched):
        path = Path(raw) if os.path.isabs(raw) else root / raw
        try:
            path = path.resolve()
            inside = path.relative_to(vault)
            if path.suffix.lower() != ".md":
                continue
            if at:
                text = _git(root, "show", f"{at}:.compass/{inside.as_posix()}")
                if text is None:
                    continue
            else:
                if not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        decisions, _ = decisionslib.extract_decisions(text)
        stem = _doc_stem(path)
        for decision in decisions:
            lines.append(_cut(f"{stem}/{decision['id']}: {decision['text']}", DECISION_LINE_CHARS))
    return lines


def _decision_lines(answers, documents):
    lines = []
    if answers:
        kept = answers[-CAPS["answers"]:]
        lines += [f"- {_cut(f'{q}: {a}', ANSWER_LINE_CHARS)}" for q, a in kept]
        if len(answers) > len(kept):
            lines.append(f"... and {len(answers) - len(kept)} more")
    lines += _capped([f"- {line}" for line in documents], CAPS["decisions"])
    return lines


def _git_sections(root):
    """`(dirty_lines, branch_lines)`, each empty when git cannot say."""
    dirty = []
    status = _git(root, "status", "--short", "--", ".", ":(exclude).compass")
    if status:
        dirty = [line.rstrip() for line in status.splitlines() if line.strip()]
    branch = (_git(root, "symbolic-ref", "--short", "-q", "HEAD") or "").strip()
    commit = (_git(root, "rev-parse", "--short", "HEAD") or "").strip()
    if branch and commit:
        return dirty, [f"{branch} @ {commit}"]
    if branch or commit:
        return dirty, [branch or f"(detached) @ {commit}"]
    return dirty, []


def gather(root, transcript, at=None):
    """Every section's raw material as one dict; each source that is absent
    or unreadable contributes an empty value. With `at` (a full commit hash),
    the open tasks and vault decisions come from that commit, the uncommitted
    changes are left out and the branch line reads `at <short commit>`."""
    transcript = Path(transcript) if transcript else None
    has_transcript = transcript is not None and transcript.is_file()
    touched = _safe([], _touched, transcript, root) if has_transcript else []
    answers = _safe([], sessionslib.question_answers, transcript) if has_transcript else []
    if at:
        short = (_git(root, "rev-parse", "--short", at) or "").strip()
        dirty, branch = [], [f"at {short or at}"]
    else:
        dirty, branch = _git_sections(root)
    test_run = _safe(None, sessionslib.last_test_run, transcript) if has_transcript else None
    return {
        "request": _safe(None, sessionslib.last_human_request, transcript) if has_transcript else None,
        "tasks": _open_tasks(root, at),
        "answers": answers,
        "documents": _safe([], _document_decisions, touched, root, at),
        "edited": [t for t in reversed(touched) if t[1] == "edited"],
        "read": [t for t in reversed(touched) if t[1] == "read"],
        "starts": _safe({}, _edit_start_lines, transcript, root) if has_transcript else {},
        "dirty": dirty,
        "test_run": test_run,
        "branch": branch,
    }


def _request_lines(request):
    if not request or not request.strip():
        return []
    text = request.strip()
    cut = text[:REQUEST_CHARS].rstrip()
    if len(text) > REQUEST_CHARS:
        cut += "..."
    return [f"> {line}" for line in cut.splitlines()]


def _test_lines(test_run):
    if not test_run:
        return []
    command, tail = test_run
    first = (command.strip().splitlines() or [""])[0]
    lines = [f"- `{_cut(first, TEST_LINE_CHARS)}`"]
    lines += [f"    {_cut(line, TEST_LINE_CHARS)}" for line in tail if line.strip()]
    return lines


def block_sections(state):
    """`[(name, lines)]` in survival order, empty sections left out."""
    sections = [
        ("Last human request", _request_lines(state["request"])),
        ("Open tasks", _capped(state["tasks"], CAPS["tasks"])),
        ("Decisions", _decision_lines(state["answers"], state["documents"])),
        ("Files edited", _capped([f"- {d}" for d, _, _ in state["edited"]], CAPS["edited"])),
        ("Files read", _capped([f"- {d}" for d, _, _ in state["read"]], CAPS["read"])),
        ("Uncommitted changes", _capped(state["dirty"], CAPS["dirty"])),
        ("Last test run", _test_lines(state["test_run"])),
        ("Branch", state["branch"]),
    ]
    return [(name, lines) for name, lines in sections if lines]


def render_block(state):
    """The title and as many leading sections as fit the budget; a section
    that does not fit ends the block, so no later section appears without an
    earlier one."""
    text = BLOCK_TITLE + "\n"
    for name, lines in block_sections(state):
        section = "\n## " + name + "\n" + "\n".join(lines) + "\n"
        if len(text) + len(section) > BUDGET:
            break
        text += section
    return text


def render_handoff(state):
    starts = state["starts"]
    changes = []
    for display, _, _ in state["edited"]:
        line = starts.get(display)
        changes.append(f"- `{display}:{line}`" if line else f"- `{display}`")
    sections = [
        ("Tasks", _capped(state["tasks"], CAPS["tasks"])),
        ("Recent Changes", _capped(changes, CAPS["edited"])),
        ("Decisions", _decision_lines(state["answers"], state["documents"])),
        ("Uncommitted Changes", _capped([f"- {line}" for line in state["dirty"]], CAPS["dirty"])),
    ]
    return "\n".join(f"## {name}\n" + "\n".join(lines) + "\n" for name, lines in sections if lines)


def _resolve_commit(root, ref):
    """The full hash of commit `ref`, or a UsageError naming it."""
    full = None if ref.startswith("-") else _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if not full or not full.strip():
        raise UsageError(f"unknown commit: {ref}")
    return full.strip()


def _parse_line(raw):
    try:
        record = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def _stamp(record):
    """The record's `timestamp` as an aware datetime, or None."""
    value = record.get("timestamp") if isinstance(record, dict) else None
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _cut_transcript(transcript, until, folder):
    """Write into `folder` a copy of `transcript` holding the lines before
    line `until`, with a `subagents/` side holding each subagent record
    stamped at or before the boundary record's timestamp; return the copy's
    path. A UsageError when line `until` is not a compact_boundary record."""
    transcript = Path(transcript)
    if re.fullmatch(r"\d+", until or "") is None:
        raise UsageError(f"not a compaction boundary: --until needs a line number, got {until}")
    index = int(until)
    with open(transcript, "rb") as handle:
        lines = handle.readlines()
    boundary = _parse_line(lines[index]) if index < len(lines) else None
    if not boundary or boundary.get("type") != "system" or boundary.get("subtype") != "compact_boundary":
        raise UsageError(f"not a compaction boundary: line {until}")
    cut = Path(folder) / transcript.name
    cut.write_bytes(b"".join(lines[:index]))
    limit = _stamp(boundary)
    side = cut.with_suffix("") / "subagents"
    for path in sessionslib.subagent_transcripts(transcript):
        kept = []
        with open(path, "rb") as handle:
            for raw in handle:
                moment = _stamp(_parse_line(raw))
                if limit is not None and moment is not None and moment <= limit:
                    kept.append(raw if raw.endswith(b"\n") else raw + b"\n")
        side.mkdir(parents=True, exist_ok=True)
        (side / path.name).write_bytes(b"".join(kept))
    return cut


def _hook(options, root):
    """The hook's stdout text for the event on stdin, empty when the event is
    not one this command answers."""
    if os.environ.get("COMPASS_WORKER_SESSION"):
        return ""
    raw = sys.stdin.read().strip()
    event = json.loads(raw) if raw else None
    if not isinstance(event, dict) or event.get("agent_id") or event.get("agent_type"):
        return ""
    name = event.get("hook_event_name")
    if name == "PreCompact":
        return PRE_COMPACT_INSTRUCTIONS
    if name != "SessionStart" or event.get("source") != "compact":
        return ""
    transcript = options["transcript"]
    if not transcript and isinstance(event.get("transcript_path"), str):
        transcript = event["transcript_path"]
    transcript = _resolve_transcript(transcript, root)
    context = render_block(gather(root, transcript))
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}})


def _state_text(options, root):
    at = _resolve_commit(root, options["at"]) if options["at"] is not None else None
    transcript = _resolve_transcript(options["transcript"], root)
    if options["until"] is not None:
        if transcript is None:
            raise UsageError("not a compaction boundary: no transcript")
        with tempfile.TemporaryDirectory(prefix="compass-state-") as folder:
            state = gather(root, _cut_transcript(transcript, options["until"], folder), at)
    else:
        state = gather(root, transcript, at)
    return render_handoff(state) if options["format"] == "handoff" else render_block(state)


def run(args):
    try:
        options = _parse_args(args)
        root = _project_root()
        text = _hook(options, root) if options["hook"] else _state_text(options, root)
        if text:
            sys.stdout.write(text if text.endswith("\n") else text + "\n")
    except UsageError as exc:
        sys.stderr.write(f"{exc}\n{USAGE}")
        return 1
    except Exception as exc:  # a failing state block must never block a compaction
        try:
            import bugs
            bugs.capture_exception(_project_root().joinpath(".compass"), "session-state", exc)
        except Exception:
            pass
    return 0
