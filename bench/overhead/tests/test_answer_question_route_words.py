"""Words that begin with a slash in the Bash fence of hooks/answer_question.py.

The interface is described at the top of test_drive.py.

Adversarial themes: a route string, a quoted pattern or a URL path is a word
that begins with `/` yet names no folder, so a fence that denies every such word
blocks ordinary build work; a word whose first component is a folder at the
filesystem root (`/etc`, `/tmp`, a Git Bash drive `/c/`) is a real escape.
"""

import importlib.util

import pytest

from conftest import OVERHEAD_DIR

HOOK = OVERHEAD_DIR / "hooks" / "answer_question.py"


def verdict(command, project):
    spec = importlib.util.spec_from_file_location("answer_question_route_words", HOOK)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}}
    out = hook.decide(event, project=str(project), answer=lambda questions: {})
    return None if out is None else out["hookSpecificOutput"]["permissionDecision"]


@pytest.mark.parametrize(
    "command",
    [
        'grep -r "/api" .',
        'git commit -m "add /users route"',
        "curl http://localhost:3000/api",
        "grep -E '/v[0-9]+/items' src",
        "echo /zzz-no-such-folder-81",
    ],
    ids=lambda command: command,
)
def test_a_slash_word_that_names_no_root_folder_is_allowed(project, command):
    """Adversarial where: denying every word that starts with a slash refuses a
    grep for a route, a URL path and a regex, which a build does all the time."""
    assert verdict(command, project) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "cat /etc/hosts",
        "ls /c/Users",
        "cp x /tmp/y",
        "cat /api/../etc/passwd",
        "ls /",
    ],
    ids=lambda command: command,
)
def test_a_slash_word_under_a_root_folder_is_denied(project, command):
    """Adversarial where: relaxing the rule for route-like words must keep the
    real roots (`/etc`, a Git Bash drive letter, `/tmp`, the root itself) and a
    route-like prefix that climbs back to a root through `..`."""
    assert verdict(command, project) == "deny"
