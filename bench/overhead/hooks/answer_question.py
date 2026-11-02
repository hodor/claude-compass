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
import re
import shlex
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
_SHELLS = frozenset({"bash", "sh", "zsh", "dash"})
_OPERATORS = frozenset({"&&", "||", "&", ";", ";;", "|", "|&", "(", ")", "&>", ">", ">>", "<", "<<", ">&", "<&"})
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
_DRIVE_PATH = re.compile(r"[A-Za-z]:[\\/]")
_RAW_DRIVE_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s\"'|;&<>()]*")
_RAW_PARENT = re.compile(r"(?:^|[\s\"'=])\.\.\\")
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


def _split_unquoted_newlines(command):
    """`command` with each newline and backtick outside quotes turned into ';'."""
    out, quote = [], None
    for char in command:
        if quote:
            if char == quote:
                quote = None
            out.append(char)
        elif char in "'\"":
            quote = char
            out.append(char)
        elif char in "\n`":
            out.append(";")
        else:
            out.append(char)
    return "".join(out)


def _tokens(command):
    prepared = _split_unquoted_newlines(command)
    try:
        lexer = shlex.shlex(prepared, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return prepared.split()


def _segments(tokens):
    segment = []
    for token in tokens:
        if token == "$":
            continue
        if token in _OPERATORS:
            if segment:
                yield segment
            segment = []
        else:
            segment.append(token)
    if segment:
        yield segment


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


def _forbidden_command(command, depth=0):
    """The reason `command` may not run, or None."""
    for segment in _segments(_tokens(command)):
        words = _command_words(segment)
        if not words:
            continue
        program = _program(words[0])
        if program == "gh":
            return "the gh command is not available in this build"
        if program == "git" and _git_subcommand(words) == "push":
            return "git push is not available in this build"
        flags = [i for i, word in enumerate(words[1:], 1) if re.fullmatch(r"-[a-z]*c[a-z]*", word)]
        if program in _SHELLS and depth < 3 and flags:
            position = flags[0] + 1
            if position < len(words):
                reason = _forbidden_command(words[position], depth + 1)
                if reason:
                    return reason
    return None


def _looks_like_path(word):
    return (
        word.startswith(("/", "~", "./", "../", ".\\", "..\\", "$"))
        or word in (".", "..")
        or word.endswith(("/..", "\\.."))
        or "/../" in word
        or _DRIVE_PATH.match(word) is not None
    )


def _leaves_project(project, word):
    if word in _DEVICE_PATHS:
        return False
    if word.startswith("$"):
        return "/" in word or "\\" in word
    if word.startswith("~"):
        expanded = os.path.expanduser(word)
        return expanded == word or not _inside(project, expanded)
    return not _inside(project, word)


def _path_escape(command, project):
    """A path in `command` that leaves the project, or None."""
    for match in _RAW_DRIVE_PATH.finditer(command):
        if _leaves_project(project, match.group(0)):
            return match.group(0)
    if _RAW_PARENT.search(command):
        return ".."
    for segment in _segments(_tokens(command)):
        for word in segment:
            candidates = [word]
            if word.startswith("-") and "=" in word:
                candidates.append(word.split("=", 1)[1])
            for candidate in candidates:
                if _looks_like_path(candidate) and _leaves_project(project, candidate):
                    return candidate
    return None


def _check_bash(tool_input, project):
    command = tool_input.get("command")
    if not isinstance(command, str):
        return _deny("the Bash call carried no command")
    reason = _forbidden_command(command)
    if reason:
        return _deny(reason)
    escape = _path_escape(command, project)
    if escape is not None:
        return _deny(f"the path {escape!r} leaves the project")
    return None


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
