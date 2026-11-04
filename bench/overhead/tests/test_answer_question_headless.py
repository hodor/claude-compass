"""The fence of hooks/answer_question.py in a headless build.

A headless build has no one to grant a permission prompt, so the hook's word
is final: a call inside the fence is allowed outright, a call outside it is
denied with a reason, web search and fetch are allowed, and the PowerShell
tool is denied with a pointer to Bash.

Adversarial themes: the project named in its Git Bash spelling (`/c/...`),
which the shell reports for the working folder, must count as the project; a
sibling folder spelled the same way must still leave it.
"""

import importlib.util
import os

import pytest

from conftest import OVERHEAD_DIR

HOOK = OVERHEAD_DIR / "hooks" / "answer_question.py"


def load_hook():
    spec = importlib.util.spec_from_file_location("answer_question_headless", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def never_asked(questions):
    raise AssertionError("no question expected")


def call(tool, tool_input, project):
    out = load_hook().decide(
        {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input},
        project=str(project), answer=never_asked,
    )
    return out["hookSpecificOutput"] if out is not None else None


def git_bash(path):
    text = path.as_posix()
    return "/" + text[0].lower() + text[2:]


@pytest.fixture
def project(tmp_path):
    folder = tmp_path / "projects" / "proj-a1"
    folder.mkdir(parents=True)
    return folder


def test_a_write_inside_the_project_is_allowed_outright(project):
    out = call("Write", {"file_path": str(project / "src" / "main.py"), "content": "x"}, project)
    assert out["permissionDecision"] == "allow"


def test_a_bash_command_inside_the_project_is_allowed_outright(project):
    out = call("Bash", {"command": "python -m pytest -q > out.txt"}, project)
    assert out["permissionDecision"] == "allow"


def test_a_write_outside_the_project_is_still_denied(project):
    out = call("Write", {"file_path": str(project.parent / "other" / "x.py"), "content": "x"}, project)
    assert out["permissionDecision"] == "deny"


@pytest.mark.skipif(os.name != "nt", reason="Git Bash drive paths exist on Windows only")
def test_the_project_in_its_git_bash_spelling_is_the_project(project):
    out = call("Bash", {"command": f"cd {git_bash(project)}; ls -la {git_bash(project)}/.claude"}, project)
    assert out["permissionDecision"] == "allow"


@pytest.mark.skipif(os.name != "nt", reason="Git Bash drive paths exist on Windows only")
def test_a_sibling_in_git_bash_spelling_still_leaves_the_project(project):
    sibling = project.parent / "proj-b2"
    sibling.mkdir()
    out = call("Bash", {"command": f"ls {git_bash(sibling)}"}, project)
    assert out["permissionDecision"] == "deny"


def test_powershell_is_denied_with_a_pointer_to_bash(project):
    out = call("PowerShell", {"command": "Get-ChildItem"}, project)
    assert out["permissionDecision"] == "deny"
    assert "Bash" in out["permissionDecisionReason"]


@pytest.mark.parametrize("tool, tool_input", [
    ("WebSearch", {"query": "json lines spec"}),
    ("WebFetch", {"url": "https://jsonlines.org/", "prompt": "summarize"}),
])
def test_web_tools_are_allowed_since_no_one_can_grant_their_prompt(project, tool, tool_input):
    """Adversarial where: a web call falls through to the permission prompt,
    which a headless session refuses, and researchers fall back to curl."""
    out = call(tool, tool_input, project)
    assert out["permissionDecision"] == "allow"
