"""Read-only access to Claude Code session transcripts and the Compass folder
that holds kept session clones.

Claude Code keeps each session as `<config>/projects/<project-key>/<session-id>.jsonl`,
with the transcripts of the subagents it spawned in a side folder
`<session-id>/subagents/agent-*.jsonl`. The `sessions`, `clone` and
`retention` commands share this module for locating those files, reading the
facts they carry, and resolving the central run folder
`<compass-home>/sessions/<project-key>/<run-id>`.

The project key is the absolute project path with every non-alphanumeric
character replaced by `-`, the encoding Claude Code uses for its own project
folders. `CLAUDE_CONFIG_DIR` replaces `~/.claude` and `COMPASS_HOME` replaces
`~/.compass`; an empty value counts as unset.

Every reader opens transcripts in binary read mode, skips lines that do not
parse as a JSON object, and tolerates records whose fields have the wrong
shape. Transcript fields are undocumented, so a field a reader cannot make
sense of yields None or an empty result, never an exception.
"""

import os
import re
import time
from pathlib import Path

from commands import context_check

ACTIVE_WINDOW_SECONDS = 600
EXTENDED_SUFFIX = "[1m]"
_NON_ALNUM = re.compile(r"[^A-Za-z0-9]")
# `git commit` and `git -C <path> commit`, not `git commit-tree` or a word
# that merely ends in "git".
_GIT_COMMIT = re.compile(
    r"(?:^|[\s;&|(])git"
    r"(?:\s+-C\s+(?:\"[^\"]*\"|'[^']*'|\S+))?"
    r"\s+commit(?![\w-])"
)
_PLAN_ID = re.compile(r"\bPLAN-(\d+)\b")
_TASK_ID = re.compile(r"\bTASK-(\d+)\b")


def project_key(project_path):
    return _NON_ALNUM.sub("-", str(project_path))


def _dir_from_env(name, default_name):
    value = os.environ.get(name, "").strip()
    return Path(value) if value else Path.home() / default_name


def config_dir():
    return _dir_from_env("CLAUDE_CONFIG_DIR", ".claude")


def transcripts_dir(project_path):
    return config_dir() / "projects" / project_key(project_path)


def compass_home():
    return _dir_from_env("COMPASS_HOME", ".compass")


def run_dir(project_path, run_id):
    return compass_home() / "sessions" / project_key(project_path) / run_id


def subagent_transcripts(transcript):
    transcript = Path(transcript)
    side = transcript.with_suffix("") / "subagents"
    if not side.is_dir():
        return []
    return sorted(side.glob("agent-*.jsonl"), key=lambda p: p.name)


def _records(path):
    """Yield parsed transcript records from the first line to the last."""
    with open(path, "rb") as fh:
        for raw in fh:
            record = context_check._parse(raw)
            if record is not None:
                yield record


def _blocks(record, block_type):
    """The dict content blocks of a record's message that have `block_type`."""
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [b for b in content if isinstance(b, dict) and b.get("type") == block_type]


def _message_text(record):
    """The text a user or assistant record says: a string content, or the
    text blocks of a list content. Tool calls, tool results and every other
    record type are not message text."""
    if record.get("type") not in ("user", "assistant"):
        return ""
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    return "\n".join(b["text"] for b in _blocks(record, "text") if isinstance(b.get("text"), str))


def entrypoint(transcript):
    for record in _records(transcript):
        value = record.get("entrypoint")
        if isinstance(value, str) and value:
            return value
    return None


def used_tokens(transcript):
    for record in context_check._records_backward(transcript):
        used = context_check._used_of(record)
        if used is not None:
            return used
    return None


def _attachment_model(record):
    try:
        return context_check._model_of(record)
    except AttributeError:
        return None


def _assistant_model(record):
    if record.get("type") != "assistant" or record.get("isSidechain"):
        return None
    message = record.get("message")
    model = message.get("model") if isinstance(message, dict) else None
    return model if isinstance(model, str) and model else None


def model_id(transcript):
    fallback = None
    found = None
    for record in context_check._records_backward(transcript):
        found = _attachment_model(record)
        if found:
            break
        if fallback is None:
            fallback = _assistant_model(record)
    model = found or fallback
    if model is None:
        return None
    if not model.endswith(EXTENDED_SUFFIX):
        used = used_tokens(transcript)
        if used is not None and used > context_check.STANDARD_WINDOW:
            model += EXTENDED_SUFFIX
    return model


def _commits_in(path):
    count = 0
    for record in _records(path):
        for block in _blocks(record, "tool_use"):
            tool_input = block.get("input")
            command = tool_input.get("command") if isinstance(tool_input, dict) else None
            if block.get("name") == "Bash" and isinstance(command, str) and _GIT_COMMIT.search(command):
                count += 1
    return count


def commit_count(transcript):
    return sum(_commits_in(path) for path in [Path(transcript), *subagent_transcripts(transcript)])


def _ids(transcript, pattern, prefix):
    numbers = {}
    for record in _records(transcript):
        for digits in pattern.findall(_message_text(record)):
            numbers[f"{prefix}-{digits}"] = int(digits)
    return sorted(numbers, key=lambda name: (numbers[name], name))


def plan_ids(transcript):
    return _ids(transcript, _PLAN_ID, "PLAN")


def task_ids(transcript):
    return _ids(transcript, _TASK_ID, "TASK")


def is_active(transcript, now=None):
    now = time.time() if now is None else now
    return now - os.stat(transcript).st_mtime <= ACTIVE_WINDOW_SECONDS
