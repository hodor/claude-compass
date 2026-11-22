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
    compass session-state --hook

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
from pathlib import Path

import decisionslib
import sessionslib
import vaultlib

USAGE = """\
compass session-state [--transcript PATH] [--format block|handoff]
compass session-state --hook

Print the session's open tasks, files touched, decisions and git state, built
from the transcript, the vault and git. --hook reads a SessionStart or
PreCompact event on stdin.
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


def _parse_args(args):
    options = {"hook": False, "transcript": None, "format": "block"}
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--hook":
            options["hook"] = True
        elif arg in ("--transcript", "--format"):
            if index + 1 < len(args):
                index += 1
                options[arg[2:]] = args[index]
        elif arg.startswith("--transcript=") or arg.startswith("--format="):
            key, _, value = arg[2:].partition("=")
            options[key] = value
        index += 1
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


def _edit_start_lines(transcript):
    """`{path: line}` of the start line each edited path's last Edit result
    reports in its `structuredPatch`; a Write or an empty patch has none."""
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
                for block in _blocks(record, "tool_result"):
                    target = calls.get(block.get("tool_use_id"))
                    if target:
                        starts[target] = line
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


def _open_tasks(root):
    try:
        text = (root / ".compass" / "active.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [_cut(line, TASK_LINE_CHARS) for line in text.splitlines() if _OPEN_TASK.match(line)]


def _doc_stem(path):
    return path.parent.name if path.stem == "index" else path.stem


def _document_decisions(touched, root):
    """`<doc-stem>/D-NN: <text>` lines for each vault document the session
    read or edited, the most recently touched document first."""
    try:
        vault = (root / ".compass").resolve()
    except OSError:
        return []
    lines = []
    for _, _, raw in reversed(touched):
        path = Path(raw) if os.path.isabs(raw) else root / raw
        try:
            path = path.resolve()
            path.relative_to(vault)
            if path.suffix.lower() != ".md" or not path.is_file():
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


def gather(root, transcript):
    """Every section's raw material as one dict; each source that is absent
    or unreadable contributes an empty value."""
    transcript = Path(transcript) if transcript else None
    has_transcript = transcript is not None and transcript.is_file()
    touched = _safe([], _touched, transcript, root) if has_transcript else []
    answers = _safe([], sessionslib.question_answers, transcript) if has_transcript else []
    dirty, branch = _git_sections(root)
    test_run = _safe(None, sessionslib.last_test_run, transcript) if has_transcript else None
    return {
        "request": _safe(None, sessionslib.last_human_request, transcript) if has_transcript else None,
        "tasks": _open_tasks(root),
        "answers": answers,
        "documents": _safe([], _document_decisions, touched, root),
        "edited": [t for t in reversed(touched) if t[1] == "edited"],
        "read": [t for t in reversed(touched) if t[1] == "read"],
        "starts": _safe({}, _edit_start_lines, transcript) if has_transcript else {},
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
    for display, _, raw in state["edited"]:
        line = starts.get(raw)
        changes.append(f"- `{display}:{line}`" if line else f"- `{display}`")
    sections = [
        ("Tasks", _capped(state["tasks"], CAPS["tasks"])),
        ("Recent Changes", _capped(changes, CAPS["edited"])),
        ("Decisions", _decision_lines(state["answers"], state["documents"])),
        ("Uncommitted Changes", _capped([f"- {line}" for line in state["dirty"]], CAPS["dirty"])),
    ]
    return "\n".join(f"## {name}\n" + "\n".join(lines) + "\n" for name, lines in sections if lines)


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


def run(args):
    try:
        options = _parse_args(args)
        root = _project_root()
        if options["hook"]:
            text = _hook(options, root)
        else:
            transcript = _resolve_transcript(options["transcript"], root)
            state = gather(root, transcript)
            text = render_handoff(state) if options["format"] == "handoff" else render_block(state)
        if text:
            sys.stdout.write(text if text.endswith("\n") else text + "\n")
    except Exception as exc:  # a failing state block must never block a compaction
        try:
            import bugs
            bugs.capture_exception(_project_root().joinpath(".compass"), "session-state", exc)
        except Exception:
            pass
    return 0
