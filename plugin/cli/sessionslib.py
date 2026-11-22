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
import subprocess
import time
from pathlib import Path

from commands import context_check

ACTIVE_WINDOW_SECONDS = 600
EXTENDED_SUFFIX = "[1m]"
_ARG = r"(?:\"[^\"]*\"|'[^']*'|\S+)"
# `git commit` with any global options before the subcommand, the binary
# written as `git`, `git.exe`, or a path to either (quoted when it holds
# spaces), after a command boundary or a backtick. Options taking a value
# (`-C`, `-c`, `--git-dir`, `--work-tree`, `--namespace`) consume it in
# `=value` or separate form; every other `-x` / `--word[=value]` is a flag. A
# plain word before `commit` ends the match, so `git help commit` and
# `git -C a log commit` do not count, nor does `git commit-tree`.
_GIT_COMMAND = (
    r"(?:[\"'](?:[^\"'\n]*[/\\])?git(?:\.exe)?[\"']"
    r"|(?:^|[\s;&|(`])(?:[^\s;&|()`]*[/\\])?git(?:\.exe)?)"
)
_VALUE_OPTION = r"(?:-C|-c|--git-dir|--work-tree|--namespace)"
_GIT_GLOBAL_OPTION = (
    rf"\s+(?:{_VALUE_OPTION}(?:=|\s+){_ARG}"
    rf"|(?!{_VALUE_OPTION}(?![\w-]))--?[A-Za-z][\w-]*(?:={_ARG})?)"
)
_GIT_COMMIT = re.compile(rf"{_GIT_COMMAND}(?:{_GIT_GLOBAL_OPTION})*\s+commit(?![\w-])")
# A test runner at the start of a command, after any `cd <dir> &&` prefixes. A
# runner word later in the command (a commit message, a heredoc body, an
# argument) is not a test run.
_TEST_RUN = re.compile(
    rf"\s*(?:cd\s+{_ARG}\s*&&\s*)*"
    r"(?:pytest|python3?\s+-m\s+pytest|npm\s+test|npx\s+vitest|cargo\s+test|go\s+test)(?![\w-])"
)
TEST_TAIL_LINES = 8
_EDIT_TOOLS = ("Edit", "Write", "MultiEdit")
_PLAN_ID = re.compile(r"\bPLAN-(\d+)\b")
_TASK_ID = re.compile(r"\bTASK-(\d+)\b")


def project_key(project_path):
    """Claude Code builds the key with a JavaScript regex over UTF-16 code
    units, so a character outside the BMP yields two dashes."""
    return "".join(
        ch if ch.isascii() and ch.isalnum() else "-" * (2 if ord(ch) > 0xFFFF else 1)
        for ch in str(project_path)
    )


def _dir_from_env(name, default_name):
    value = os.environ.get(name, "").strip()
    return Path(value) if value else Path.home() / default_name


def config_dir():
    return _dir_from_env("CLAUDE_CONFIG_DIR", ".claude")


def main_checkout(project_path):
    """The main checkout of `project_path` when it is a linked git worktree,
    else `project_path` itself. A linked worktree's `.git` is a file naming
    its private git dir, which holds a `commondir` file leading to the shared
    git dir; a submodule's `.git` file names a git dir without one. The main
    checkout is the shared dir's `core.worktree` when set (a submodule's
    `.git/modules/<name>`), else the shared dir's parent when it is named
    `.git`. A repo made with `--separate-git-dir` records neither, and the
    worktree's own path is returned. Sessions started in the main checkout
    are kept under its key, so a worktree reads and clones them from there."""
    project_path = Path(project_path)
    try:
        pointer = (project_path / ".git").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return project_path
    if not pointer.startswith("gitdir:"):
        return project_path
    gitdir = project_path / pointer[len("gitdir:"):].strip()
    try:
        common = gitdir / (gitdir / "commondir").read_text(encoding="utf-8").strip()
        common = Path(os.path.normpath(common))
    except (OSError, UnicodeDecodeError, ValueError):
        return project_path
    configured = _core_worktree(common)
    if configured is not None:
        return configured
    if common.name == ".git" and common.is_dir():
        return common.parent
    return project_path


def _core_worktree(common):
    """The checkout named by `core.worktree` in the git dir `common`,
    resolved against that dir, when it holds a `.git` entry; else None,
    also when git is absent or fails."""
    try:
        result = subprocess.run(
            ["git", "--git-dir", str(common), "config", "--get", "core.worktree"],
            capture_output=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.decode("utf-8", errors="replace").strip()
    if result.returncode != 0 or not value:
        return None
    try:
        checkout = Path(os.path.normpath(common / value))
    except ValueError:
        return None
    return checkout if (checkout / ".git").exists() else None


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
    return sorted((p for p in side.glob("agent-*.jsonl") if p.is_file()), key=lambda p: p.name)


def records(path):
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
    for record in records(transcript):
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
    for record in records(path):
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
    for record in records(transcript):
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


def _numbered_records(path):
    """Yield `(index, record)` for each parseable line of `path`, the index
    being the 0-based position of the line in the file. An unreadable file
    yields what was read before the failure."""
    try:
        with open(path, "rb") as fh:
            for index, raw in enumerate(fh):
                record = context_check._parse(raw)
                if record is not None:
                    yield index, record
    except (OSError, ValueError):
        return


def _tool_calls(record):
    """The `(id, name, input)` of each tool call of a record, `input` always a dict."""
    calls = []
    for block in _blocks(record, "tool_use"):
        name = block.get("name")
        tool_input = block.get("input")
        if isinstance(name, str):
            calls.append((block.get("id"), name, tool_input if isinstance(tool_input, dict) else {}))
    return calls


def _side_transcripts(transcript):
    try:
        return subagent_transcripts(transcript)
    except OSError:
        return []


def touched_files(transcript):
    """`(path, kind, last_index)` for each file the session read or changed.

    `path` is the tool call's `file_path` verbatim. `kind` is `edited` for
    Edit, Write and MultiEdit and `read` for Read; a path with both is
    `edited`. `last_index` is the index of the last record of the main
    transcript that touched the path. Subagent transcripts count toward
    `kind`; a path only they touched takes the index of its last record in
    the subagent file and follows the main transcript's paths. Entries come
    in ascending `last_index`."""
    found = {}
    for rank, path in enumerate([Path(transcript), *_side_transcripts(transcript)]):
        for index, record in _numbered_records(path):
            for _, name, tool_input in _tool_calls(record):
                target = tool_input.get("file_path")
                if not isinstance(target, str) or not target:
                    continue
                if name in _EDIT_TOOLS:
                    kind = "edited"
                elif name == "Read":
                    kind = "read"
                else:
                    continue
                entry = found.get(target)
                if entry is None:
                    found[target] = [kind, index, rank]
                    continue
                if kind == "edited":
                    entry[0] = "edited"
                if entry[2] == rank:
                    entry[1] = index
    ordered = sorted(found.items(), key=lambda item: (item[1][2], item[1][1]))
    return [(target, kind, index) for target, (kind, index, _) in ordered]


def last_human_request(transcript):
    """The text of the last user record the human typed: string content,
    `origin.kind == "human"`, neither `isMeta` nor `isCompactSummary`. Task
    notifications, peer messages, summaries and tool results never qualify."""
    request = None
    for _, record in _numbered_records(transcript):
        if record.get("type") != "user" or record.get("isMeta") or record.get("isCompactSummary"):
            continue
        origin = record.get("origin")
        if not isinstance(origin, dict) or origin.get("kind") != "human":
            continue
        message = record.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            request = content
    return request


def question_answers(transcript):
    """`(question, answer)` for each answered AskUserQuestion entry, in file
    order, read from the call result's `toolUseResult`."""
    pairs = []
    for _, record in _numbered_records(transcript):
        result = record.get("toolUseResult")
        if not isinstance(result, dict):
            continue
        questions = result.get("questions")
        answers = result.get("answers")
        if not isinstance(questions, list) or not isinstance(answers, dict):
            continue
        for entry in questions:
            question = entry.get("question") if isinstance(entry, dict) else None
            if isinstance(question, str) and isinstance(answers.get(question), str):
                pairs.append((question, answers[question]))
    return pairs


def _result_text(record):
    """`{tool_use_id: stdout}` of the tool results of a record; the stdout is
    `toolUseResult.stdout` when it is text, else the result block's content."""
    result = record.get("toolUseResult")
    stdout = result.get("stdout") if isinstance(result, dict) else None
    texts = {}
    for block in _blocks(record, "tool_result"):
        text = stdout if isinstance(stdout, str) else block.get("content")
        if isinstance(block.get("tool_use_id"), str) and isinstance(text, str):
            texts[block["tool_use_id"]] = text
    return texts


def last_test_run(transcript):
    """`(command, tail_lines)` of the last Bash call that runs a test runner
    (see `_TEST_RUN`), with the last `TEST_TAIL_LINES` lines of its stdout, or
    None when the session ran no tests. A result pairs to its call by
    tool-use id."""
    last_id = None
    last_command = None
    outputs = {}
    for _, record in _numbered_records(transcript):
        for call_id, name, tool_input in _tool_calls(record):
            command = tool_input.get("command")
            if name == "Bash" and isinstance(command, str) and _TEST_RUN.match(command):
                last_id, last_command = call_id, command
        if record.get("type") == "user":
            outputs.update(_result_text(record))
    if last_command is None:
        return None
    return last_command, outputs.get(last_id, "").splitlines()[-TEST_TAIL_LINES:]


def compact_boundaries(transcript):
    """`(index, trigger)` for each `compact_boundary` record, in file order;
    `trigger` is None when the record carries no readable one."""
    found = []
    for index, record in _numbered_records(transcript):
        if record.get("type") != "system" or record.get("subtype") != "compact_boundary":
            continue
        metadata = record.get("compactMetadata")
        trigger = metadata.get("trigger") if isinstance(metadata, dict) else None
        found.append((index, trigger if isinstance(trigger, str) else None))
    return found
