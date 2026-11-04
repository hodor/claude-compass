"""Where a build's tokens go, read from its session transcripts.

`profile_project` reads every transcript Claude Code wrote for one project
under the sandbox config's `projects/` folder: the top-level sessions (setup,
build, capture workers) and the subagent sessions under `<session>/subagents/`.
It returns aggregates only: counts, model ids, tool names, skill names, agent
types, attachment kinds and Compass's own file names. No message text, project
path or session id reaches the result.

Requests. One API response can be written as several assistant records that
share a message id; the response is counted once, with the usage of its last
record. A response's tokens are its input, cache read and cache write tokens
(its context) and its output tokens; a weighted total uses the weights of
records.py.

Sessions. A top-level session is `setup` when its first message runs
`/compass:setup` and it was typed no other message, `capture-worker` when its first message
starts the extract-lessons skill, and `build` otherwise; a subagent session is
`subagent:<agent type>`.

Sources. A response's context holds the request prefix (the system prompt and
each tool definition, read from the request shape the transcript stores) and
every item the session added before it: messages, tool calls and results,
skill bodies (a meta message after a Skill call or a typed slash command, or
one carrying its own command tag, as a subagent's preloaded skills do; it is
`skill body:preloaded` when no name is known), other harness meta messages (`user:meta`), attachments and hook output.
A response streamed as several records is counted at its first record, so its
own blocks enter the context after it. Its cache-write and uncached input
tokens are split over the items added since the session's previous response,
its cache-read tokens over the items already there, each in proportion to the
item's characters (an image or document block counts MEDIA_CHARS); a response
with no cache read rewrote its whole context, so its cache write is split over
all of it; a split with no item on its side falls back to the whole context. A compaction boundary empties the context.

Phases. In a build or setup session the phase is the last skill the session
loaded (a skill body after a Skill tool call or a slash command, or a Read of a
skill's `SKILL.md` under `.claude/skills/`), `none` before the first; in a
subagent or capture-worker session it is the session kind. Every response's
weighted tokens also go to its phase, and its output tokens to `output:<phase>`.

Reconciliation. The counted tokens of each top-level session and its
subagents are compared with the `cost-state` totals the session wrote, when it
wrote them.

    python token_profile.py PROJECT [--private-root DIR] [--json]
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import launch
import records

CAPTURE_PROMPT = "Read the file .claude/skills/extract-lessons/SKILL.md"
SKILL_BODY_START = "Base directory for this skill"
# Characters counted for an image or document block, whose base64 data says
# nothing about its token count.
MEDIA_CHARS = 6000
SETUP_COMMAND = "<command-name>/compass:setup</command-name>"
_COMMAND_NAME = re.compile(r"<command-name>/?([^<\s]+)</command-name>")
_SKILL_NAME = re.compile(r"[A-Za-z0-9:_\-.]+")
_VAULT_FOLDER = re.compile(r"(?:^|[\\/])\.compass[\\/]([^\\/]+)([\\/][^\\/]+)?")
_CLAUDE_FILE = re.compile(r"(?:^|[\\/])\.claude[\\/](.+)$")
_SAFE_PART = re.compile(r"[A-Za-z0-9_\-.]+")
_SKILL_FILE = re.compile(r"(?:^|[\\/])\.claude[\\/]skills[\\/]([^\\/]+)[\\/]SKILL\.md$")
_VAULT_ROOT_FILES = ("index.md", "active.md", "backlog.md", "vision.md")


def transcript_folder(project, private_root=None):
    """The folder of `project`'s transcripts in the sandbox config."""
    root = Path(private_root) if private_root is not None else launch.default_private_root()
    return root / "claude-config" / "projects" / launch.encode_cwd(os.path.abspath(project))


def _read_lines(path):
    records_ = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return records_
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            records_.append(item)
    return records_


def _chars(value):
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        return sum(_chars(item) for item in value)
    if isinstance(value, dict):
        if value.get("type") in ("image", "document"):
            return MEDIA_CHARS
        if "text" in value and isinstance(value["text"], str):
            return len(value["text"])
        if "content" in value:
            return _chars(value["content"])
        return len(json.dumps(value))
    return 0


def _skill(name):
    return name if isinstance(name, str) and _SKILL_NAME.fullmatch(name) else "unnamed"


def _path_source(path):
    """The category of a file path: a Compass vault folder, a file of the
    project's `.claude/` install, or the project's own files."""
    if not isinstance(path, str):
        return "project"
    vault = _VAULT_FOLDER.search(path)
    if vault:
        folder = vault.group(1)
        if folder in _VAULT_ROOT_FILES or (vault.group(2) is None and folder.endswith(".md")):
            return f".compass/{folder}" if folder in _VAULT_ROOT_FILES else ".compass/(file)"
        return f".compass/{folder}/" if _SAFE_PART.fullmatch(folder) else ".compass/(folder)/"
    install = _CLAUDE_FILE.search(path)
    if install:
        parts = re.split(r"[\\/]", install.group(1))
        if all(_SAFE_PART.fullmatch(part) for part in parts):
            return ".claude/" + "/".join(parts[:3])
        return ".claude/(file)"
    return "project"


def _first_user_text(lines):
    for item in lines:
        if item.get("type") != "user":
            continue
        content = (item.get("message") or {}).get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(block.get("text", "") for block in content if isinstance(block, dict))
    return ""


def _typed_messages(lines):
    """The number of user messages a person or the driver typed: not tool
    results, skill bodies, task notifications or reminders."""
    count = 0
    for item in lines:
        if item.get("type") != "user" or item.get("isMeta") is True or item.get("isCompactSummary"):
            continue
        content = (item.get("message") or {}).get("content")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content or []
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            text = (block.get("text") or "").lstrip()
            if text and not text.startswith(("<task-notification>", "<system-reminder>")):
                count += 1
                break
    return count


def session_kind(lines):
    """`setup`, `capture-worker` or `build` for a top-level session's lines."""
    first = _first_user_text(lines).strip()
    if first.startswith(CAPTURE_PROMPT):
        return "capture-worker"
    if SETUP_COMMAND in first and _typed_messages(lines) <= 1:
        return "setup"
    return "build"


class _Context:
    """The items a session's context holds, with their characters."""

    def __init__(self):
        self.items = []  # [source, chars, new]

    def add(self, source, chars):
        if chars > 0:
            self.items.append([source, chars, True])

    def clear(self):
        self.items = []


def _add(totals, key, kinds):
    entry = totals.setdefault(key, {"input": 0.0, "cache_read": 0.0, "cache_write": 0.0, "output": 0.0, "weighted": 0.0})
    for kind, value in kinds.items():
        entry[kind] += value


def _weight(model, kinds):
    read_weight = records.cache_read_weight(model)
    if read_weight is None:
        return 0.0
    return (
        kinds.get("input", 0.0)
        + records.OUTPUT_WEIGHT * kinds.get("output", 0.0)
        + read_weight * kinds.get("cache_read", 0.0)
        + records.CACHE_WRITE_WEIGHT * kinds.get("cache_write", 0.0)
    )


def _usage(message):
    usage = message.get("usage") if isinstance(message, dict) else None
    if not isinstance(usage, dict):
        return None
    get = lambda name: records._count(usage.get(name))  # noqa: E731
    return {
        "input": get("input_tokens"),
        "cache_read": get("cache_read_input_tokens"),
        "cache_write": get("cache_creation_input_tokens"),
        "output": get("output_tokens"),
    }


def _shape_items(shape):
    items = []
    if not isinstance(shape, dict):
        return items
    items.append(("prefix:system prompt", _chars(shape.get("system"))))
    for tool in shape.get("tools") or []:
        if isinstance(tool, dict):
            name = tool.get("name")
            name = name if isinstance(name, str) and _SKILL_NAME.fullmatch(name) else "unnamed"
            items.append((f"prefix:tool {name}", len(json.dumps(tool))))
    return items


def _split(tokens, items, key_of):
    """{source: tokens} of `tokens` split over `items` by characters."""
    total = sum(key_of(item) for item in items)
    if tokens <= 0 or total <= 0:
        return {}
    shares = {}
    for item in items:
        shares[item[0]] = shares.get(item[0], 0.0) + tokens * key_of(item) / total
    return shares


def profile_session(lines, kind, skip_ids=frozenset()):
    """Aggregates of one session's lines (see the module docstring). Responses
    whose message id is in `skip_ids` (counted in a parent session already, as
    a forked subagent repeats them) add their content but no tokens."""
    shapes, requests_ = {}, {}
    for item in lines:
        if item.get("type") == "api-request-shape" and isinstance(item.get("shapeHash"), str):
            shapes[item["shapeHash"]] = item.get("shape")
        elif item.get("type") == "api-request" and isinstance(item.get("id"), str):
            requests_[item["id"]] = item.get("shapeHash")

    first, last = {}, {}
    for index, item in enumerate(lines):
        if item.get("type") == "assistant":
            message = item.get("message") or {}
            key = message.get("id") or f"line-{index}"
            first.setdefault(key, index)
            last[key] = index

    context = _Context()
    by_source, by_phase, models = {}, {}, {}
    tool_names = {}
    fixed = kind if kind not in ("build", "setup") else None
    active = fixed or "none"
    pending_skill = None
    counted = set()
    prefix = []
    request_count = 0

    for index, item in enumerate(lines):
        kind_ = item.get("type")
        if kind_ == "system" and item.get("subtype") == "compact_boundary":
            context.clear()
            continue
        if kind_ == "attachment":
            attachment = item.get("attachment") or {}
            name = attachment.get("type") if isinstance(attachment.get("type"), str) else "unknown"
            context.add(f"attachment:{name}", _chars(item.get("rendered")))
            continue
        if kind_ == "user":
            message = item.get("message") or {}
            content = message.get("content")
            meta = item.get("isMeta") is True
            if item.get("isCompactSummary"):
                context.add("compaction summary", _chars(content))
                continue
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content or []
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result":
                    tool, path = tool_names.get(block.get("tool_use_id"), ("unknown", None))
                    source = f"tool result:{tool}"
                    if tool in ("Read", "Write", "Edit", "MultiEdit"):
                        source += f" {_path_source(path)}"
                    context.add(source, _chars(block.get("content")))
                    continue
                text = block.get("text") if isinstance(block.get("text"), str) else ""
                command = _COMMAND_NAME.search(text)
                if command and meta:
                    name = _skill(command.group(1))
                    if fixed is None:
                        active = name
                    context.add(f"skill body:{name}", len(text))
                    pending_skill = None
                elif command:
                    pending_skill = _skill(command.group(1))
                    context.add("user:slash command", len(text))
                elif meta and (pending_skill or text.lstrip().startswith(SKILL_BODY_START)):
                    name = pending_skill or (active if fixed is None else "preloaded")
                    if fixed is None and pending_skill:
                        active = pending_skill
                    context.add(f"skill body:{name}", len(text))
                    pending_skill = None
                elif meta:
                    context.add("user:meta", len(text))
                elif text.lstrip().startswith("<task-notification>"):
                    context.add("user:task notification", len(text))
                elif "<system-reminder>" in text:
                    context.add("user:system reminder", len(text))
                else:
                    context.add("user:message", len(text))
            continue
        if kind_ != "assistant":
            continue

        message = item.get("message") or {}
        key = message.get("id") or f"line-{index}"
        if first.get(key) == index:
            pending_skill = None
        if first.get(key) == index and key not in counted and key not in skip_ids:
            counted.add(key)
            usage = _usage(lines[last[key]].get("message") or {})
            if usage is not None:
                request_count += 1
                model = records._model_key(message.get("model"))
                shape = shapes.get(requests_.get(item.get("requestRef")))
                if shape is not None:
                    new_prefix = _shape_items(shape)
                    if new_prefix != [tuple(p[:2]) for p in prefix]:
                        prefix = [[source, chars, True] for source, chars in new_prefix]
                whole = prefix + context.items
                fresh = [entry for entry in whole if entry[2]] or whole
                if usage["cache_read"] == 0:
                    fresh = whole
                kept = [entry for entry in whole if not entry[2]] or whole
                parts = {}
                for kind_name, items, in (("cache_write", fresh), ("input", fresh), ("cache_read", kept)):
                    for source, tokens in _split(usage[kind_name], items, lambda entry: entry[1]).items():
                        parts.setdefault(source, {})[kind_name] = parts.get(source, {}).get(kind_name, 0.0) + tokens
                parts.setdefault(f"output:{active}", {})["output"] = float(usage["output"])
                for source, kinds in parts.items():
                    kinds = {name: kinds.get(name, 0.0) for name in ("input", "cache_read", "cache_write", "output")}
                    kinds["weighted"] = _weight(model, kinds)
                    _add(by_source, source, kinds)
                phase = {name: float(usage[name]) for name in ("input", "cache_read", "cache_write", "output")}
                phase["weighted"] = _weight(model, phase)
                _add(by_phase, active, phase)
                _add(models, model, phase)
                for entry in whole:
                    entry[2] = False

        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                context.add("assistant:text", len(block.get("text") or ""))
            elif block.get("type") == "thinking":
                context.add("assistant:thinking", len(block.get("thinking") or ""))
            elif block.get("type") == "tool_use":
                name = block.get("name") if isinstance(block.get("name"), str) else "unknown"
                name = name if _SKILL_NAME.fullmatch(name) else "unknown"
                tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
                tool_names[block.get("id")] = (name, tool_input.get("file_path") or tool_input.get("path"))
                if name == "Skill":
                    pending_skill = _skill(tool_input.get("skill"))
                elif name == "Read" and fixed is None:
                    read_skill = _SKILL_FILE.search(str(tool_input.get("file_path") or ""))
                    if read_skill:
                        active = _skill(read_skill.group(1))
                context.add(f"tool call:{name}", len(json.dumps(tool_input)))

    reported = None
    for item in lines:
        if item.get("type") == "cost-state" and isinstance(item.get("modelUsage"), dict):
            reported = item["modelUsage"]
    return {
        "kind": kind,
        "counted_ids": counted,
        "requests": request_count,
        "models": models,
        "by_source": by_source,
        "by_phase": by_phase,
        "reported": _reported_totals(reported),
    }


def _reported_totals(model_usage):
    if not isinstance(model_usage, dict):
        return None
    totals = {}
    for model, entry in model_usage.items():
        if isinstance(entry, dict):
            totals[records._model_key(model)] = {
                kind: records._count(entry.get(field)) for kind, field in records._USAGE_FIELDS.items()
            }
    return totals


def _agent_type(meta_path):
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "unknown"
    agent = meta.get("agentType") if isinstance(meta, dict) else None
    return agent if isinstance(agent, str) and _SKILL_NAME.fullmatch(agent) else "unknown"


def profile_folder(folder):
    """Aggregates over every session in a project's transcript `folder`.
    Raises ValueError when the folder holds no session."""
    folder = Path(folder)
    if not any(folder.glob("*.jsonl")):
        raise ValueError("the folder holds no session transcript")
    sessions = []
    for path in sorted(folder.glob("*.jsonl")):
        lines = _read_lines(path)
        family = [profile_session(lines, session_kind(lines))]
        parent_ids = frozenset(family[0]["counted_ids"])
        for agent_path in sorted((folder / path.stem / "subagents").glob("*.jsonl")):
            agent = _agent_type(agent_path.with_name(agent_path.stem + ".meta.json"))
            family.append(profile_session(_read_lines(agent_path), f"subagent:{agent}", skip_ids=parent_ids))
        family[0]["family_models"] = _family_models(family)
        sessions.extend(family)
    return summarize(sessions)


def _family_models(family):
    """{model: kinds} over a top-level session and its subagents, whose sum the
    session's own `cost-state` reports."""
    models = {}
    for session in family:
        for model, kinds in session["models"].items():
            _add(models, model, kinds)
    return models


def summarize(sessions):
    by_kind, by_source, by_phase, models = {}, {}, {}, {}
    counts = {}
    mismatches = []
    for session in sessions:
        session.pop("counted_ids", None)
        counts[session["kind"]] = counts.get(session["kind"], 0) + 1
        for model, kinds in session["models"].items():
            _add(models, model, kinds)
            _add(by_kind, session["kind"], kinds)
        for source, kinds in session["by_source"].items():
            _add(by_source, source, kinds)
        for phase, kinds in session["by_phase"].items():
            _add(by_phase, phase, kinds)
        if session["reported"] and "family_models" in session:
            counted = sum(
                k["input"] + k["cache_read"] + k["cache_write"] + k["output"] for k in session["family_models"].values()
            )
            reported = sum(sum(k.values()) for k in session["reported"].values())
            if reported:
                mismatches.append(abs(counted - reported) / reported)
    weighted = sum(kinds["weighted"] for kinds in models.values())
    return {
        "weighted": round(weighted, 1),
        "sessions": counts,
        "by_kind": _rounded(by_kind),
        "by_source": _rounded(by_source),
        "by_phase": _rounded(by_phase),
        "models": _rounded(models),
        "reconciliation": {
            "sessions_checked": len(mismatches),
            "largest_gap": round(max(mismatches), 4) if mismatches else None,
        },
    }


def _rounded(table):
    return {key: {kind: round(value, 1) for kind, value in kinds.items()} for key, kinds in table.items()}


def wait_until_quiet(folder, quiet_seconds=120, limit_seconds=900, clock=time.time, sleep=time.sleep):
    """Wait until no transcript under `folder` changed for `quiet_seconds`
    (capture workers a build started can outlive it), at most `limit_seconds`;
    True when the folder went quiet."""
    deadline = clock() + limit_seconds
    while True:
        newest = max((path.stat().st_mtime for path in Path(folder).rglob("*.jsonl")), default=0.0)
        if clock() - newest >= quiet_seconds:
            return True
        if clock() >= deadline:
            return False
        sleep(min(15, max(1, quiet_seconds - (clock() - newest))))


def profile_project(project, private_root=None, wait=True):
    folder = transcript_folder(project, private_root)
    if wait:
        wait_until_quiet(folder)
    return profile_folder(folder)


VAULT_FOLDERS = frozenset({
    "specs", "research", "plans", "decisions", "lessons", "handoffs", "prs", "archive", "meta", "tmp",
    "loops", ".annotations", "(folder)",
})
BUILT_IN_TOOLS = frozenset({
    "Agent", "Bash", "DeferredToolPlaceholder", "Edit", "Glob", "Grep", "ListAgents", "Monitor", "MultiEdit",
    "NotebookEdit", "PowerShell", "Read", "ReportFindings", "ScheduleWakeup", "SendMessage", "Skill", "Task",
    "TaskStop", "TodoWrite", "ToolSearch", "WebFetch", "WebSearch", "Workflow", "Write", "AskUserQuestion",
    "advisor",
})
_ATTACHMENT_KIND = re.compile(r"[a-z][a-z_]+")
_FIXED_SOURCES = frozenset({
    "compaction summary", "assistant:text", "assistant:thinking", "user:message", "user:slash command",
    "user:task notification", "user:system reminder", "user:meta", "prefix:system prompt",
})


def compass_names(plugin_root):
    """The skill, agent and rule names the plugin at `plugin_root` ships."""
    root = Path(plugin_root)
    names = {path.name for path in (root / "skills").glob("*") if path.is_dir()}
    for folder in (root / "agents", root / "templates" / "agents", root / "templates" / "rules"):
        names |= {path.stem for path in folder.glob("*.md")}
    return frozenset(names)


def _public_name(name, known):
    """`name` when it is a Compass skill or agent (with or without the
    `compass:` prefix) or a fixed label, else `(other)`."""
    bare = name[len("compass:"):] if name.startswith("compass:") else name
    if bare in known or name in ("none", "preloaded", "unnamed", "build", "setup", "capture-worker"):
        return name
    if name.startswith("subagent:") and (name[len("subagent:"):] in known or name == "subagent:general-purpose"):
        return name
    return "(other)"


def _public_path(path_source, known):
    if path_source == "project":
        return path_source
    if path_source.startswith(".compass/"):
        rest = path_source[len(".compass/"):]
        folder = rest.rstrip("/")
        if rest.endswith("/") and folder in VAULT_FOLDERS:
            return path_source
        if folder in _VAULT_ROOT_FILES or folder == "(file)":
            return path_source
        return ".compass/(other)"
    parts = path_source[len(".claude/"):].split("/")
    if len(parts) >= 2 and parts[0] in ("skills", "agents", "rules"):
        name = parts[1][:-3] if parts[1].endswith(".md") else parts[1]
        if name in known:
            return path_source
    if parts and parts[0] in ("cli", "hooks"):
        return f".claude/{parts[0]}/"
    return ".claude/(other)"


def public_source(source, known):
    """`source` with any name outside the public vocabulary replaced by
    `(other)`: Compass skill and agent names from `known`, built-in tool
    names, attachment kinds, vault folders and the fixed labels pass; a skill,
    tool or path someone else named does not."""
    if source in _FIXED_SOURCES:
        return source
    head, _, rest = source.partition(":")
    if head in ("skill body", "output"):
        return f"{head}:{_public_name(rest, known)}"
    if head == "attachment":
        return source if _ATTACHMENT_KIND.fullmatch(rest) else "attachment:(other)"
    if head == "prefix" and rest.startswith("tool "):
        return source if rest[5:] in BUILT_IN_TOOLS else "prefix:tool (other)"
    if head in ("tool result", "tool call"):
        tool, _, path = rest.partition(" ")
        if tool not in BUILT_IN_TOOLS:
            return f"{head}:(other)"
        return f"{head}:{tool}" + (f" {_public_path(path, known)}" if path else "")
    return "(other)"


def public_phase(phase, known):
    return _public_name(phase, known)


def group(source):
    """The family of a source: `tool result`, `skill body`, `prefix` and so on."""
    head = source.split(":", 1)[0]
    if head == "prefix" and source.startswith("prefix:tool "):
        return "prefix:tool definitions"
    return head


def render(summary, top=25):
    total = summary["weighted"] or 1.0
    lines = [f"Weighted tokens: {summary['weighted']:.0f}", ""]
    lines += ["| Session kind | Sessions | Weighted | Share |", "|---|---|---|---|"]
    for kind, kinds in sorted(summary["by_kind"].items(), key=lambda pair: -pair[1]["weighted"]):
        lines.append(f"| {kind} | {summary['sessions'].get(kind, 0)} | {kinds['weighted']:.0f} | {kinds['weighted'] / total:.1%} |")
    families = {}
    for source, kinds in summary["by_source"].items():
        families[group(source)] = families.get(group(source), 0.0) + kinds["weighted"]
    lines += ["", "| Source family | Weighted | Share |", "|---|---|---|"]
    for family, value in sorted(families.items(), key=lambda pair: -pair[1]):
        lines.append(f"| {family} | {value:.0f} | {value / total:.1%} |")
    lines += ["", "| Source | Weighted | Share |", "|---|---|---|"]
    for source, kinds in sorted(summary["by_source"].items(), key=lambda pair: -pair[1]["weighted"])[:top]:
        lines.append(f"| {source} | {kinds['weighted']:.0f} | {kinds['weighted'] / total:.1%} |")
    lines += ["", "| Active skill | Weighted | Share |", "|---|---|---|"]
    for phase, kinds in sorted(summary["by_phase"].items(), key=lambda pair: -pair[1]["weighted"])[:top]:
        lines.append(f"| {phase} | {kinds['weighted']:.0f} | {kinds['weighted'] / total:.1%} |")
    gap = summary["reconciliation"]["largest_gap"]
    lines += ["", f"Largest gap to the sessions' own totals: {'none checked' if gap is None else f'{gap:.1%}'}"]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("project")
    parser.add_argument("--private-root")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--top", type=int, default=25)
    args = parser.parse_args(argv)
    summary = profile_project(args.project, args.private_root)
    sys.stdout.write((json.dumps(summary, indent=1) if args.json else render(summary, args.top)) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
