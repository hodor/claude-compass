"""PreToolUse hook for a build session in a throwaway project.

It answers `AskUserQuestion` and fences the session into its project. Claude
Code runs it as a command with the event on stdin; the file named by the
environment variable `OVERHEAD_HOOK_CONFIG` holds

    {"project": "<project folder>", "answer_command": ["argv", ...],
     "read_roots": ["<folder>", ...], "home": "<sandbox home folder>"}

`read_roots` and `home` are optional.

`AskUserQuestion` is allowed with `updatedInput` holding the questions and an
`answers` object keyed by question text. The answer command receives
`{"questions": [...]}` on stdin and prints `{"answers": {...}}`; a list answer
(multi-select) is joined with ", ", and a question the command skipped is
answered "decide yourself". A failing answer command ends in a denial that
names the failure.

Write, Edit, MultiEdit and NotebookEdit calls are denied when their path, with
links resolved, is not inside the project. Bash calls are denied when a command
word is `gh`, when a command is `git push`, or when an argument names a path
that leaves the project. A Bash argument may also name a place inside a read
root (a folder the session copies from, such as the plugin under test) or
inside the sandbox home. Within a command, `$HOME`, `${HOME}`, `%USERPROFILE%`,
`$env:USERPROFILE` and a leading `~` stand for the sandbox home; `APPDATA`,
`LOCALAPPDATA`, `TEMP` and `TMP` stand for the folders below it that
`HOME_SUBFOLDERS` names, and a variable the command itself assigns (an
assignment or a `for` list) stands for its values. Each expansion is judged
like any other path; a variable of unknown value followed by a slash, and every
home variable when no home is configured, leaves the project. Write and Edit
calls never reach into a read root or the home.
Every other call, and every other hook event, gets no opinion: nothing is
printed.

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
COVERED_TOOLS = ("AskUserQuestion", "Bash", "PowerShell") + FILE_TOOLS

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
# Where each home-like variable points, relative to the sandbox home.
HOME_SUBFOLDERS = {
    "HOME": "",
    "USERPROFILE": "",
    "APPDATA": "AppData/Roaming",
    "LOCALAPPDATA": "AppData/Local",
    "TEMP": "AppData/Local/Temp",
    "TMP": "AppData/Local/Temp",
}
# A variable reference at the start of a word: `$X`, `${X}`, `$env:X`, `%X%`.
_VARIABLE_START = re.compile(r"\$(?:env:)?(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))|%([A-Za-z_]\w*)%")
# Words that may precede an assignment or a `for` in a simple command.
_KEYWORDS = frozenset({"do", "then", "else", "{", "!", "if", "while", "until", "export", "declare", "local",
                       "readonly", "typeset"})
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


def _allow():
    """Permission for a call inside the fence. A headless build has no one to
    grant a prompt, so a call without an allow would be refused."""
    return _decision("allow", "inside the build's fence")


def _real(path):
    return os.path.normcase(os.path.realpath(path))


def _is_absolute(path):
    """True for a POSIX absolute path or a Windows drive path."""
    return path.startswith("/") or (len(path) > 2 and path[1] == ":" and path[2] in "/\\")


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


class _Fence:
    """What a Bash command may name: the project, the read roots, the sandbox
    home, and the variables the command itself assigns."""

    def __init__(self, project, read_roots=(), home=None, variables=None):
        self.project = project
        self.home = home.replace("\\", "/").rstrip("/") if isinstance(home, str) and home.strip() else None
        self.roots = [root for root in read_roots if isinstance(root, str) and root.strip()]
        if self.home:
            self.roots.append(self.home)
        self.variables = variables or {}

    def with_variables(self, variables):
        fence = _Fence(self.project)
        fence.home, fence.roots, fence.variables = self.home, self.roots, variables
        return fence


def _native(path):
    """`path` with a Git Bash drive prefix (`/f/x`) written as a drive path."""
    if os.name == "nt" and re.match(r"/[A-Za-z](?:/|$)", path):
        return path[1].upper() + ":" + (path[2:] or "/")
    return path


def _in_roots(fence, path):
    """True when the absolute `path` is a read root, the sandbox home, or below one."""
    path = _native(path)
    return _is_absolute(path) and any(_inside(root, path) for root in fence.roots)


def _variable_values(name, fence, depth):
    """The values the variable `name` may hold, or None when unknown."""
    if fence.home is not None and name.upper() in HOME_SUBFOLDERS:
        sub = HOME_SUBFOLDERS[name.upper()]
        return [fence.home + ("/" + sub if sub else "")]
    if name in fence.variables and depth < _MAX_DEPTH:
        values = []
        for raw in fence.variables[name]:
            expanded = _expand(raw, fence, depth + 1)
            if expanded is None:
                return None
            values.extend(expanded)
        return values
    return None


def _expand(text, fence, depth=0):
    """The values of `text` with a leading `~` or variable expanded: the text
    itself when it starts with neither, None when the expansion is unknown or
    leaves a substitution or variable behind."""
    text = text.replace("\\", "/")
    values = [text]
    if text == "~" or text.startswith("~/"):
        if fence.home is None:
            return None
        values = [fence.home + text[1:]]
    else:
        match = _VARIABLE_START.match(text)
        if match:
            found = _variable_values(match.group(1) or match.group(2) or match.group(3), fence, depth)
            if found is None:
                return None
            values = [value + text[match.end():] for value in found]
    if any("$" in value or "`" in value or _HOME_VARIABLE.search(value) for value in values):
        return None
    return values


def _leaves_path(fence, path):
    """True when `path`, which holds no variable, names a place outside the
    project, the read roots and the sandbox home."""
    if path.startswith("//"):
        return True
    if _in_roots(fence, path):
        return False
    if path.startswith("~"):
        return True
    if path in _DEVICE_PATHS:
        return False
    if path.startswith("/"):
        return not _inside(fence.project, _native(path)) and _names_filesystem_root_folder(path)
    return _looks_like_path(path) and not _inside(fence.project, path)


def _leaves_project(fence, candidate):
    """True when `candidate`, a word or the value glued into one, names a place
    outside the project, the read roots and the sandbox home."""
    path = candidate.replace("\\", "/")
    if path.startswith("~") or _VARIABLE_START.match(path):
        values = _expand(path, fence)
        if values is not None:
            return any(_leaves_path(fence, value) for value in values)
        if _HOME_VARIABLE.search(candidate) or path.startswith("~"):
            return True
        return "/" in path
    if _HOME_VARIABLE.search(candidate):
        return True
    return _leaves_path(fence, path)


def _candidates(word):
    """The word, the value after an `=`, and the value glued to a short option."""
    found = [word]
    if "=" in word:
        found.append(word.split("=", 1)[1])
    if len(word) > 2 and word[0] == "-" and word[1].isalpha():
        found.append(word[2:])
    return found


def _assigned_variables(segments):
    """{name: [raw values]} for the variables `segments` assign: leading
    `NAME=value` words and the lists of `for NAME in ...`."""
    found = {}
    for segment in segments:
        start = 0
        while start < len(segment) and segment[start] in _KEYWORDS:
            start += 1
        if start + 2 < len(segment) and segment[start] == "for" and segment[start + 2] == "in":
            found.setdefault(segment[start + 1], []).extend(segment[start + 3:])
        for word in segment:
            if _ASSIGNMENT.match(word):
                name, value = word.split("=", 1)
                found.setdefault(name, []).append(value)
            elif word not in _KEYWORDS:
                break
    return found


def _inspect(command, fence, depth=0):
    """The reason `command` may not run, or None."""
    if depth > _MAX_DEPTH:
        return "shell commands nest too deeply"
    segments = _parse(command)
    fence = fence.with_variables(_assigned_variables(segments))
    for match in _RAW_DRIVE_PATH.finditer(command):
        if _leaves_project(fence, match.group(0)):
            return f"the path {match.group(0)!r} leaves the project"
    for segment in segments:
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
                reason = _inspect(payload, fence, depth + 1)
                if reason:
                    return reason
        for word in segment:
            for candidate in _candidates(word):
                if _leaves_project(fence, candidate):
                    return f"the path {candidate!r} leaves the project"
    return None


def _check_bash(tool_input, fence):
    command = tool_input.get("command")
    if not isinstance(command, str):
        return _deny("the Bash call carried no command")
    reason = _inspect(command, fence)
    return _deny(reason) if reason else _allow()


def _check_file_call(tool_input, project):
    path = next((tool_input[key] for key in FILE_KEYS if isinstance(tool_input.get(key), str)), "")
    if not path.strip():
        return _deny("the call named no file inside the project")
    if not _inside(project, path):
        return _deny(f"the path {path!r} leaves the project")
    return _allow()


def decide(event, *, project, answer, read_roots=(), home=None):
    """The hook output for a PreToolUse `event`, or None for no opinion.

    Bash, Write and Edit calls are allowed or denied: Bash commands may also
    name paths inside `read_roots` and the sandbox `home`; Write and Edit calls
    stay inside the project."""
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
        if tool == "PowerShell":
            return _deny("PowerShell is not available in this build; use the Bash tool")
        if tool == "Bash":
            return _check_bash(tool_input, _Fence(project, read_roots, home))
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
        read_roots = [str(root) for root in config.get("read_roots") or []]
        home = config.get("home")
    except (KeyError, OSError, ValueError, TypeError):
        if event.get("hook_event_name") == "PreToolUse" and event.get("tool_name") in COVERED_TOOLS:
            return 0, json.dumps(_deny("the hook's configuration could not be read")) + "\n"
        return 0, ""
    out = decide(
        event, project=project, answer=_command_answerer(answer_command),
        read_roots=read_roots, home=home if isinstance(home, str) else None,
    )
    return 0, (json.dumps(out) + "\n" if out is not None else "")


if __name__ == "__main__":
    code, text = main(sys.argv[1:], sys.stdin.read(), os.environ)
    sys.stdout.write(text)
    sys.exit(code)
