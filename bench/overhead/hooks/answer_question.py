"""PreToolUse hook for a build session in a throwaway project.

It answers `AskUserQuestion` and fences the session into its project. Claude
Code runs it as a command with the event on stdin; the file named by the
environment variable `OVERHEAD_HOOK_CONFIG` holds

    {"project": "<project folder>", "answer_command": ["argv", ...]}

`AskUserQuestion` is allowed with `updatedInput` holding the questions and an
`answers` object keyed by question text. The answer command receives
`{"questions": [...]}` on stdin and prints `{"answers": {...}}`; a list answer
(multi-select) is joined with ", ", and a question the command skipped is
answered "decide yourself". A failing answer command ends in a denial that
names the failure.

Write, Edit, MultiEdit and NotebookEdit calls are denied when their path, with
links resolved, is not inside the project. Bash calls are denied when a command
word is `gh`, when a command is `git push`, or when an argument names a path
that leaves the project. Every other call, and every other hook event, gets no
opinion: nothing is printed.

The hook uses only the standard library and imports no sibling module.
"""

import json
import os
import posixpath
import re
import subprocess
import sys

CONFIG_VARIABLE = "OVERHEAD_HOOK_CONFIG"
DECIDE_YOURSELF = "decide yourself"

FILE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
FILE_KEYS = ("file_path", "notebook_path", "path")
COVERED_TOOLS = ("AskUserQuestion", "Bash") + FILE_TOOLS

# git options that take the next word as their value.
_GIT_VALUE_OPTIONS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"})
# Words that run the command following them.
_WRAPPERS = frozenset({
    "env", "command", "exec", "time", "nohup", "sudo", "builtin", "timeout", "nice", "xargs", "setsid", "stdbuf",
})
_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh"})
_POWERSHELLS = frozenset({"powershell", "pwsh"})
_POWERSHELL_COMMAND = re.compile(r"-c(?:o(?:m(?:m(?:a(?:n(?:d)?)?)?)?)?)?", re.IGNORECASE)
# Characters outside quotes that end a simple command.
_SEPARATORS = "&|;()<>\n`"
# Levels of command substitution and shell strings that are looked into.
_MAX_DEPTH = 5
_SUBSTITUTION = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
# Variables naming a folder outside the project.
_HOME_VARIABLE = re.compile(
    r"\$(?:env:)?\{?(?:HOME|USERPROFILE|HOMEDRIVE|HOMEPATH|APPDATA|LOCALAPPDATA|TEMP|TMP)\b"
    r"|%(?:HOME|USERPROFILE|HOMEDRIVE|HOMEPATH|APPDATA|LOCALAPPDATA|TEMP|TMP)%",
    re.IGNORECASE,
)
# Folders at the root of a POSIX or Git Bash filesystem.
_ROOT_FOLDERS = frozenset({
    "tmp", "etc", "home", "usr", "users", "mnt", "var", "root", "bin", "sbin", "opt", "proc", "sys", "dev",
    "lib", "lib64", "boot", "media", "srv", "private", "windows", "programdata",
})
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
_DRIVE_PATH = re.compile(r"[A-Za-z]:[\\/]")
_RAW_DRIVE_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s\"'|;&<>()]*")
_DEVICE_PATHS = frozenset({"/dev/null", "/dev/stdin", "/dev/stdout", "/dev/stderr", "/dev/tty"})


def _decision(kind, reason, updated_input=None):
    body = {
        "hookEventName": "PreToolUse",
        "permissionDecision": kind,
        "permissionDecisionReason": reason,
    }
    if updated_input is not None:
        body["updatedInput"] = updated_input
    return {"hookSpecificOutput": body}


def _deny(reason):
    return _decision("deny", reason)


def _real(path):
    return os.path.normcase(os.path.realpath(path))


def _inside(project, path):
    """True when `path` (relative paths resolve against `project`), with links
    resolved, is the project or below it."""
    root = _real(project)
    target = _real(os.path.join(root, path) if not os.path.isabs(path) else path)
    try:
        return os.path.commonpath([root, target]) == root
    except ValueError:
        return False


def _answer_questions(tool_input, answer):
    questions = tool_input.get("questions")
    if not isinstance(questions, list):
        raise ValueError("AskUserQuestion carried no questions")
    given = answer(questions)
    answers = {}
    for question in questions:
        text = question.get("question") if isinstance(question, dict) else None
        if not isinstance(text, str):
            continue
        value = given.get(text) if isinstance(given, dict) else None
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(part) for part in value)
        answers[text] = str(value) if value not in (None, "") else DECIDE_YOURSELF
    return {**tool_input, "questions": questions, "answers": answers}


def _parse(command, depth=0):
    """The simple commands of `command` as lists of words.

    Quotes are removed and backslashes kept as written, so Windows paths reach
    the checks intact. A word holding a command substitution also adds the
    commands inside it as segments of their own.
    """
    segments, segment, chars = [], [], []
    started, quote = False, None

    def flush_word():
        nonlocal started
        if not started:
            return
        word = "".join(chars)
        chars.clear()
        started = False
        segment.append(word)
        if depth < _MAX_DEPTH and ("$(" in word or "`" in word):
            for inner in _SUBSTITUTION.findall(word):
                segments.extend(_parse(inner[0] or inner[1], depth + 1))
            segments.append([piece for piece in re.split(r"\$\(|[\s`()]+", word) if piece])

    def end_segment():
        nonlocal segment
        flush_word()
        if segment:
            segments.append(segment)
        segment = []

    index = 0
    while index < len(command):
        char = command[index]
        index += 1
        if quote == "'":
            if char == "'":
                quote = None
            else:
                chars.append(char)
        elif quote == '"':
            if char == '"':
                quote = None
            elif char == "\\" and command[index:index + 1] == '"':
                chars.append('"')
                index += 1
            else:
                chars.append(char)
        elif char in "'\"":
            quote, started = char, True
        elif char in " \t\r":
            flush_word()
        elif char in _SEPARATORS:
            end_segment()
        else:
            chars.append(char)
            started = True
    end_segment()
    return segments


def _command_words(segment):
    """The segment from its command word on: env assignments, wrappers and the
    options of a wrapper dropped."""
    index, after_wrapper = 0, False
    while index < len(segment):
        word = segment[index]
        if word in _WRAPPERS:
            after_wrapper = True
        elif _ASSIGNMENT.match(word) or (after_wrapper and word.startswith("-")):
            pass
        else:
            break
        index += 1
    return segment[index:]


def _program(word):
    name = re.split(r"[\\/]", word)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _git_subcommand(words):
    index = 1
    while index < len(words):
        word = words[index]
        if word in _GIT_VALUE_OPTIONS:
            index += 2
        elif word.startswith("-"):
            index += 1
        else:
            return word
    return None


def _shell_payload(program, words):
    """The command string a shell is asked to run, or None."""
    rest = words[1:]
    if program in _SHELLS:
        for position, word in enumerate(rest):
            if re.fullmatch(r"-[a-z]*c[a-z]*", word):
                return rest[position + 1] if position + 1 < len(rest) else None
    elif program in _POWERSHELLS:
        for position, word in enumerate(rest):
            if _POWERSHELL_COMMAND.fullmatch(word):
                return " ".join(rest[position + 1:])
    elif program == "cmd":
        for position, word in enumerate(rest):
            if word.lower() in ("/c", "/k"):
                return " ".join(rest[position + 1:])
    return None


def _looks_like_path(word):
    return (
        word.startswith(("/", "./", "../"))
        or word in (".", "..")
        or word.endswith("/..")
        or "/../" in word
        or _DRIVE_PATH.match(word) is not None
    )


def _names_filesystem_root_folder(path):
    """True when the first component of the absolute `path` is a folder the
    shell sees at the filesystem root: a well-known one, a Git Bash drive letter
    (`/c/`), or one that exists. A word like `/api` is a route or a pattern."""
    parts = posixpath.normpath(path).split("/")
    first = parts[1] if len(parts) > 1 else ""
    return (
        first == ""
        or first.lower() in _ROOT_FOLDERS
        or (len(first) == 1 and first.isalpha())
        or os.path.exists("/" + first)
    )


def _leaves_project(project, candidate):
    """True when `candidate`, a word or the value glued into one, names a place
    outside the project."""
    if _HOME_VARIABLE.search(candidate):
        return True
    path = candidate.replace("\\", "/")
    if path.startswith("~") or path.startswith("//"):
        return True
    if path in _DEVICE_PATHS:
        return False
    if path.startswith("$"):
        return "/" in path
    if path.startswith("/"):
        return not _inside(project, path) and _names_filesystem_root_folder(path)
    return _looks_like_path(path) and not _inside(project, path)


def _candidates(word):
    """The word, the value after an `=`, and the value glued to a short option."""
    found = [word]
    if "=" in word:
        found.append(word.split("=", 1)[1])
    if len(word) > 2 and word[0] == "-" and word[1].isalpha():
        found.append(word[2:])
    return found


def _inspect(command, project, depth=0):
    """The reason `command` may not run, or None."""
    if depth > _MAX_DEPTH:
        return "shell commands nest too deeply"
    for match in _RAW_DRIVE_PATH.finditer(command):
        if _leaves_project(project, match.group(0)):
            return f"the path {match.group(0)!r} leaves the project"
    for segment in _parse(command):
        words = _command_words(segment)
        if words:
            program = _program(words[0])
            if program == "gh":
                return "the gh command is not available in this build"
            if program == "git" and _git_subcommand(words) == "push":
                return "git push is not available in this build"
            if program in ("cd", "pushd") and len(words) == 1:
                return "a bare cd leaves the project"
            payload = _shell_payload(program, words)
            if payload is not None:
                reason = _inspect(payload, project, depth + 1)
                if reason:
                    return reason
        for word in segment:
            for candidate in _candidates(word):
                if _leaves_project(project, candidate):
                    return f"the path {candidate!r} leaves the project"
    return None


def _check_bash(tool_input, project):
    command = tool_input.get("command")
    if not isinstance(command, str):
        return _deny("the Bash call carried no command")
    reason = _inspect(command, project)
    return _deny(reason) if reason else None


def _check_file_call(tool_input, project):
    path = next((tool_input[key] for key in FILE_KEYS if isinstance(tool_input.get(key), str)), "")
    if not path.strip():
        return _deny("the call named no file inside the project")
    if not _inside(project, path):
        return _deny(f"the path {path!r} leaves the project")
    return None


def decide(event, *, project, answer):
    """The hook output for a PreToolUse `event`, or None for no opinion."""
    if event.get("hook_event_name") != "PreToolUse":
        return None
    tool = event.get("tool_name")
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    if tool == "AskUserQuestion":
        try:
            updated = _answer_questions(tool_input, answer)
        except Exception as error:
            return _deny(f"the question could not be answered: {error}")
        return _decision("allow", "answered by the simulated human", updated)
    try:
        if tool == "Bash":
            return _check_bash(tool_input, project)
        if tool in FILE_TOOLS:
            return _check_file_call(tool_input, project)
    except Exception as error:
        return _deny(f"the call could not be checked: {error}")
    return None


def _command_answerer(argv):
    def answer(questions):
        done = subprocess.run(
            argv, input=json.dumps({"questions": questions}), capture_output=True, text=True, encoding="utf-8",
        )
        if done.returncode != 0:
            detail = (done.stderr or "").strip()[-300:]
            raise RuntimeError(f"the answer command exited {done.returncode}: {detail}")
        return json.loads(done.stdout)["answers"]

    return answer


def main(argv, stdin_text, env):
    """(exit code, stdout text) for one hook call."""
    try:
        event = json.loads(stdin_text)
    except ValueError:
        return 0, ""
    if not isinstance(event, dict):
        return 0, ""
    try:
        with open(env[CONFIG_VARIABLE], encoding="utf-8") as handle:
            config = json.load(handle)
        project, answer_command = config["project"], config["answer_command"]
    except (KeyError, OSError, ValueError, TypeError):
        if event.get("hook_event_name") == "PreToolUse" and event.get("tool_name") in COVERED_TOOLS:
            return 0, json.dumps(_deny("the hook's configuration could not be read")) + "\n"
        return 0, ""
    out = decide(event, project=project, answer=_command_answerer(answer_command))
    return 0, (json.dumps(out) + "\n" if out is not None else "")


if __name__ == "__main__":
    code, text = main(sys.argv[1:], sys.stdin.read(), os.environ)
    sys.stdout.write(text)
    sys.exit(code)
