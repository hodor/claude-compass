"""Escape probes for the Bash fence of hooks/answer_question.py.

The interface is described at the top of test_drive.py.

Adversarial themes: a path that reaches outside the project through a shell
variable that expands to a bare folder (no slash to look for), through the
payload of a shell or PowerShell `-c`/`-Command` string, through a Windows
UNC or backslash-parent spelling, or through a short option whose value is
glued to the flag. Each denied row names a path outside the project; each
allowed row is a path that stays inside and must not be refused.
"""

import importlib.util

import pytest

from conftest import OVERHEAD_DIR

HOOK = OVERHEAD_DIR / "hooks" / "answer_question.py"


def load_hook():
    spec = importlib.util.spec_from_file_location("answer_question_escapes", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verdict(command, project):
    hook = load_hook()
    event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}}
    out = hook.decide(event, project=str(project), answer=lambda questions: {})
    return None if out is None else out["hookSpecificOutput"]["permissionDecision"]


BARE_VARIABLES = [
    "ls $HOME",
    "cat $HOME",
    "cat ${HOME}",
    'cat "$HOME"',
    "cat $USERPROFILE",
    "echo hi > $HOME",
    "(ls $HOME)",
    "echo $(ls $HOME)",
    'echo "$(cat ~)"',
    "cat ~",
]


@pytest.mark.parametrize("command", BARE_VARIABLES, ids=lambda command: command)
def test_a_variable_or_tilde_naming_the_home_folder_is_denied(project, command):
    """Adversarial where: `$HOME` with no slash after it, a braced or quoted
    form, a command substitution, and a lone `~` all name the home folder, which
    is outside the project; a fence that only denies variables followed by a
    slash lets `ls $HOME` read the whole home folder."""
    assert verdict(command, project) == "deny"


SHELL_PAYLOADS = [
    "sh -c 'cat /etc/passwd'",
    "bash -c 'cat ../secret'",
    "sh -lc 'ls ~/notes'",
    'powershell -Command "Get-Content ../secret"',
    'pwsh -c "Get-Content /etc/hosts"',
]


@pytest.mark.parametrize("command", SHELL_PAYLOADS, ids=lambda command: command)
def test_a_path_inside_a_shell_command_string_is_denied_like_a_bare_path(project, command):
    """Adversarial where: the string handed to `sh -c` or a PowerShell
    `-Command` is one word to the tokenizer, so a fence that checks only
    whole words for a path prefix never sees `/etc/passwd` or `../secret`
    inside it, while the same path written directly is denied."""
    assert verdict(command, project) == "deny"


WINDOWS_PATHS = [
    r"type \\server\share\notes.txt",
    r"cat \\server\share",
    r"cat .\..\secret",
    r"dir ..\..",
]


@pytest.mark.parametrize("command", WINDOWS_PATHS, ids=lambda command: command)
def test_windows_unc_and_backslash_parent_paths_are_denied(project, command):
    """Adversarial where: a UNC path names another machine's share and a
    `.\\..\\` spelling climbs out of the project, yet neither starts with a
    forward slash or a drive letter, so a check built on `/` and `X:\\` prefixes
    waves them through."""
    assert verdict(command, project) == "deny"


GLUED_OPTION_VALUES = [
    "tar xf archive.tar -C/tmp",
    "gcc main.c -o/tmp/out",
    "cp -t/tmp notes.txt",
    "tar xf archive.tar --directory=/tmp",
]


@pytest.mark.parametrize("command", GLUED_OPTION_VALUES, ids=lambda command: command)
def test_an_option_value_glued_to_its_flag_is_checked_as_a_path(project, command):
    """Adversarial where: `-C/tmp` is one word that starts with a dash, not a
    slash, so only the `--name=value` form is split; a fence that checks the
    value of `--directory=/tmp` but not of `-C/tmp` has two spellings for the
    same escape."""
    assert verdict(command, project) == "deny"


INSIDE_COMMANDS = [
    "echo hi > out.txt",
    "git -C . status",
    "cat src/../README.md",
    'git commit -m "see ../docs later"',
    "mkdir -p a/b && cd a/b && ls",
]


@pytest.mark.parametrize("command", INSIDE_COMMANDS, ids=lambda command: command)
def test_paths_that_stay_inside_the_project_are_not_refused(project, command):
    """Adversarial where: the stricter checks above (variables, shell
    strings, glued options) must not turn into a blanket refusal; a `..` that
    resolves back inside the project, `-C .`, and a quoted sentence that merely
    mentions `../` are ordinary work."""
    assert verdict(command, project) is None
