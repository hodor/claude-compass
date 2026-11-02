"""Tests for hooks/answer_question.py: the PreToolUse hook that answers
AskUserQuestion and fences the build into its project.

The interface is described at the top of test_drive.py.

Adversarial themes: a path check by string prefix (a sibling folder sharing the
project's name), `..` that escapes after looking inside, a `gh` or `git push`
hiding behind `&&` or a git option, a quoted message that merely mentions
them, and a failing answerer that silently allows the call.
"""

import importlib.util
import json
import os
import subprocess
import sys

import pytest

from conftest import OVERHEAD_DIR

HOOK = OVERHEAD_DIR / "hooks" / "answer_question.py"


def load_hook():
    spec = importlib.util.spec_from_file_location("answer_question", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def event(tool, tool_input, project):
    return {
        "hook_event_name": "PreToolUse",
        "session_id": "session-1",
        "cwd": str(project),
        "tool_name": tool,
        "tool_input": tool_input,
        "tool_use_id": "toolu_1",
    }


def decision(output):
    if output is None:
        return None
    return output["hookSpecificOutput"]["permissionDecision"]


def bash(command, project):
    return event("Bash", {"command": command}, project)


def never_asked(questions):
    raise AssertionError("the answerer must not be called")


QUESTIONS = [
    {"question": "Which database?", "header": "DB", "multiSelect": False,
     "options": [{"label": "sqlite", "description": "file"}, {"label": "postgres", "description": "server"}]},
    {"question": "Which extras?", "header": "Extras", "multiSelect": True,
     "options": [{"label": "auth", "description": "a"}, {"label": "logs", "description": "b"},
                 {"label": "docs", "description": "c"}]},
    {"question": "Anything else?", "header": "Else", "multiSelect": False,
     "options": [{"label": "no", "description": "x"}, {"label": "yes", "description": "y"}]},
]


def test_ask_user_question_becomes_an_allow_with_answers_keyed_by_question_text(project):
    """Adversarial where: answers keyed by header or index instead of question
    text, a multi-select list not joined into the string the picker reads, a
    free-text answer rejected for not being an option, a question the answerer
    skipped left unanswered (the run would block), or the questions themselves
    dropped from updatedInput."""
    hook = load_hook()
    seen = []

    def answer(questions):
        seen.append(questions)
        return {"Which database?": "sqlite", "Which extras?": ["auth", "docs"], "Anything else?": "only the CSV, please"}

    skipped = [dict(QUESTIONS[0]), {"question": "Unanswered one?", "multiSelect": False, "options": []}]
    out = hook.decide(event("AskUserQuestion", {"questions": QUESTIONS}, project), project=project, answer=answer)
    out_skipped = hook.decide(
        event("AskUserQuestion", {"questions": skipped}, project), project=project,
        answer=lambda questions: {"Which database?": "postgres"},
    )

    assert decision(out) == "allow"
    body = out["hookSpecificOutput"]
    assert body["hookEventName"] == "PreToolUse"
    assert seen == [QUESTIONS]
    assert body["updatedInput"]["questions"] == QUESTIONS
    assert body["updatedInput"]["answers"] == {
        "Which database?": "sqlite",
        "Which extras?": "auth, docs",
        "Anything else?": "only the CSV, please",
    }
    assert out_skipped["hookSpecificOutput"]["updatedInput"]["answers"] == {
        "Which database?": "postgres",
        "Unanswered one?": "decide yourself",
    }


def test_a_failing_answerer_denies_with_a_reason_instead_of_allowing_or_raising(project):
    """Adversarial where: an answerer that raises makes the hook crash with a
    traceback the harness reads as 'no opinion', so the question goes unanswered
    in silence; the denial must name the failure."""
    hook = load_hook()

    def broken(questions):
        raise RuntimeError("human session failed")

    out = hook.decide(event("AskUserQuestion", {"questions": QUESTIONS}, project), project=project, answer=broken)

    assert decision(out) == "deny"
    assert "human session failed" in out["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize("tool", ["Write", "Edit"])
@pytest.mark.parametrize(
    "where, allowed",
    [
        ("src/app.py", True),
        ("src/../ok.txt", True),
        ("INSIDE/abs.txt", True),
        ("../outside.txt", False),
        ("src/../../outside.txt", False),
        ("OUTSIDE/abs.txt", False),
        ("SIBLING/x.txt", False),
        ("", False),
    ],
    ids=["relative", "dotdot-stays-inside", "absolute-inside", "dotdot-escapes", "deep-dotdot-escapes",
         "absolute-outside", "sibling-sharing-prefix", "empty-path"],
)
def test_write_and_edit_are_fenced_to_the_project(project, tool, where, allowed):
    """Adversarial where: a startswith check on the raw string lets a sibling
    folder named like the project (proj-zq81xk-evil) through; `..` segments
    that look inside but resolve outside; an empty path read as the project
    root; relative paths resolved against the wrong base."""
    hook = load_hook()
    substitutions = {
        "INSIDE": project.as_posix(),
        "OUTSIDE": project.parent.as_posix() + "/elsewhere",
        "SIBLING": project.parent.as_posix() + "/" + project.name + "-evil",
    }
    for key, value in substitutions.items():
        where = where.replace(key, value)

    out = hook.decide(event(tool, {"file_path": where, "content": "x"}, project), project=project, answer=never_asked)

    assert (decision(out) != "deny") is allowed


def test_a_symlink_inside_the_project_that_points_outside_is_refused(project, tmp_path):
    """Adversarial where: a path check on the unresolved string trusts a link
    named like a project file that leads out of the project."""
    outside = tmp_path / "outside-target"
    outside.mkdir()
    link = project / "link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available")
    hook = load_hook()

    out = hook.decide(
        event("Write", {"file_path": str(link / "f.txt"), "content": "x"}, project),
        project=project, answer=never_asked,
    )

    assert decision(out) == "deny"


@pytest.mark.parametrize(
    "command, denied",
    [
        ("gh pr create --fill", True),
        ("cd sub && gh issue list", True),
        ("FOO=1 gh api /user", True),
        ("echo hi | gh auth login", True),
        ("git push origin main", True),
        ("git push", True),
        ("git -C . push --force", True),
        ("git status && git push origin HEAD", True),
        ("git status", False),
        ("git commit -m 'gh and git push are blocked'", False),
        ("ghc --version", False),
        ("git pull origin main", False),
        ("echo gh", False),
        ("python -m pytest -q", False),
    ],
)
def test_bash_denies_gh_and_git_push_at_command_position_only(project, command, denied):
    """Adversarial where: matching the substring `gh` or `push` anywhere denies
    ordinary commits and `ghc`; matching only the start of the line misses a
    `gh` after `&&`, `|` or an env assignment, and a `push` behind `git -C`."""
    hook = load_hook()

    out = hook.decide(bash(command, project), project=project, answer=never_asked)

    assert (decision(out) == "deny") is denied


@pytest.mark.parametrize(
    "command, denied",
    [
        ("cat src/a.py", False),
        ("python -m venv .venv && ./.venv/bin/pip install -q requests", False),
        ("ls INSIDE/src", False),
        ("cat /dev/null", False),
        ("ls ..", True),
        ("cat ../secret.txt", True),
        ("cd .. && ls", True),
        ("rm -rf OUTSIDE/data", True),
        ("cat ~/.ssh/id_rsa", True),
        ("cp a.txt SIBLING/a.txt", True),
    ],
)
def test_bash_denies_a_path_that_leaves_the_project(project, command, denied):
    """Adversarial where: only Write and Edit being fenced leaves `rm -rf` and
    `cat ../` free to leave the project; the sibling-prefix and home-folder
    forms are the escapes a prefix check or a missing `~` expansion lets by."""
    hook = load_hook()
    for key, value in {
        "INSIDE": project.as_posix(),
        "OUTSIDE": project.parent.as_posix() + "/elsewhere",
        "SIBLING": project.parent.as_posix() + "/" + project.name + "-evil",
    }.items():
        command = command.replace(key, value)

    out = hook.decide(bash(command, project), project=project, answer=never_asked)

    assert (decision(out) == "deny") is denied


@pytest.mark.parametrize(
    "ev",
    [
        {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}},
        {"hook_event_name": "PreToolUse", "tool_name": "Grep", "tool_input": {"pattern": "x", "path": ".."}},
        {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "gh pr list"}},
    ],
    ids=["read", "grep", "other-hook-event"],
)
def test_calls_the_hook_does_not_cover_are_left_alone(project, ev):
    """Adversarial where: a hook that denies every tool or every event would
    stop the build at the first Read; the fence covers Bash, Write and Edit on
    PreToolUse only."""
    hook = load_hook()

    out = hook.decide(ev, project=project, answer=never_asked)

    assert decision(out) != "deny"


def run_cli(event_json, config_path, extra_env=None):
    env = {**os.environ, "OVERHEAD_HOOK_CONFIG": str(config_path), **(extra_env or {})}
    return subprocess.run(
        [sys.executable, str(HOOK)], input=json.dumps(event_json), capture_output=True, text=True, env=env, timeout=60,
    )


def write_answerer(tmp_path, body):
    script = tmp_path / "answerer.py"
    script.write_text(body, encoding="utf-8")
    return script


def test_cli_runs_the_answer_command_and_prints_the_decision(project, tmp_path):
    """Adversarial where: the script entry point is what Claude Code runs; the
    questions must reach the answer command as {"questions": [...]} on stdin,
    its {"answers": {...}} must come back into updatedInput, and a command that
    fails must end as a printed denial with exit code 0, not a crash."""
    captured = tmp_path / "captured.json"
    good = write_answerer(
        tmp_path,
        "import json, sys\n"
        f"data = json.load(sys.stdin)\nopen({str(captured)!r}, 'w').write(json.dumps(data))\n"
        "print(json.dumps({'answers': {q['question']: 'from-command' for q in data['questions']}}))\n",
    )
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"project": str(project), "answer_command": [sys.executable, str(good)]}), encoding="utf-8")

    done = run_cli(event("AskUserQuestion", {"questions": QUESTIONS}, project), config)

    assert done.returncode == 0
    out = json.loads(done.stdout)
    assert decision(out) == "allow"
    assert out["hookSpecificOutput"]["updatedInput"]["answers"]["Which database?"] == "from-command"
    assert json.loads(captured.read_text(encoding="utf-8")) == {"questions": QUESTIONS}

    bad = write_answerer(tmp_path, "import sys\nsys.stderr.write('boom')\nsys.exit(4)\n")
    config.write_text(json.dumps({"project": str(project), "answer_command": [sys.executable, str(bad)]}), encoding="utf-8")
    failed = run_cli(event("AskUserQuestion", {"questions": QUESTIONS}, project), config)
    assert failed.returncode == 0
    assert decision(json.loads(failed.stdout)) == "deny"


def test_cli_prints_nothing_for_a_safe_call_and_a_denial_for_an_unsafe_one(project, tmp_path):
    """Adversarial where: a safe Bash call that prints a decision payload
    would override the harness's own permission flow; an unsafe one that prints
    nothing lets it through."""
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"project": str(project), "answer_command": [sys.executable, "-c", "pass"]}), encoding="utf-8")

    safe = run_cli(bash("git status", project), config)
    unsafe = run_cli(bash("git push origin main", project), config)

    assert safe.returncode == 0
    assert decision(json.loads(safe.stdout) if safe.stdout.strip() else None) != "deny"
    assert unsafe.returncode == 0
    assert decision(json.loads(unsafe.stdout)) == "deny"
