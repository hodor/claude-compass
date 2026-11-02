"""Tests for the read roots and the sandbox home of hooks/answer_question.py.

The hook config may hold `read_roots` (folders Bash commands may name but
nothing may write into) and `home` (the sandbox home that `$HOME`, `~` and the
other home-like variables stand for). `decide(event, *, project, answer,
read_roots=(), home=None)` takes both.

Adversarial themes: the plugin path a setup command copies from, a sibling
folder that shares the read root's name as a prefix, `..` that climbs out of a
read root, the Git Bash `/f/...` form of a drive path, a Write tool call into a
read root, a home variable with no home configured, and a variable of unknown
value in front of a slash.
"""

import json
import os
import subprocess
import sys

import pytest

from test_answer_question import HOOK, bash, decision, event, load_hook


def never_asked(questions):
    raise AssertionError("no question expected")


@pytest.fixture
def places(tmp_path):
    project = tmp_path / "work" / "proj"
    plugin = tmp_path / "plugin-under-test"
    home = tmp_path / "sandbox-home"
    for folder in (project, plugin, home):
        folder.mkdir(parents=True)
    return {"project": project, "plugin": plugin, "home": home, "outside": tmp_path / "elsewhere"}


def run(command, places, **config):
    hook = load_hook()
    config.setdefault("read_roots", [str(places["plugin"])])
    config.setdefault("home", str(places["home"]))
    return decision(
        hook.decide(bash(command, places["project"]), project=str(places["project"]), answer=never_asked, **config)
    )


def setup_command(plugin):
    root = plugin.as_posix()
    return (
        f'for p in "{root}" "$HOME/.claude/plugins/compass/plugin"; do '
        '[ -f "$p/.claude-plugin/plugin.json" ] && PLUGIN_ROOT="$p" && break; done; '
        'echo "Plugin root: $PLUGIN_ROOT"; '
        'mkdir -p .claude/agents; cp "$PLUGIN_ROOT/templates/agents/"*.md .claude/agents/; '
        'for skill_dir in "$PLUGIN_ROOT/skills/"*/; do skill_name=$(basename "$skill_dir"); '
        'mkdir -p ".claude/skills/$skill_name"; cp "$skill_dir"*.md ".claude/skills/$skill_name/"; done; '
        'cp -r "$PLUGIN_ROOT/cli" .claude/cli; rm -rf .claude/obsidian; cp -r "$PLUGIN_ROOT/obsidian" .claude/obsidian'
    )


def test_the_setup_command_is_allowed_with_the_read_root_and_denied_without_it(places):
    """Adversarial where: setup copies from the plugin under test, so a fence
    that counts every path outside the project as leaving stops the build in its
    first turn; a read root that is not consulted, or consulted by a variable
    that the loop assigned, leaves the copy denied."""
    command = setup_command(places["plugin"])

    assert run(command, places) == "allow"
    assert run(command, places, read_roots=[]) == "deny"
    assert run(command, places, read_roots=[str(places["home"])]) == "deny"
    assert run(command, places, home=None) == "deny"


@pytest.mark.parametrize(
    "template",
    [
        "cp {plugin}/templates/agents/a.md .claude/agents/",
        "cat {plugin}/skills/x/SKILL.md",
        "ls {plugin_win}",
        "cp -r {plugin}/cli .claude/cli",
        "tar -C{plugin} -cf out.tar .",
        "cp --target-directory={plugin}/cli x",
    ],
)
def test_a_word_inside_a_read_root_does_not_leave_the_project(places, template):
    """Adversarial where: the root is matched by the whole word, so a path
    glued to a short option or to `--opt=` and the backslash drive form all
    slip past the check that only looks at plain words."""
    command = template.format(plugin=places["plugin"].as_posix(), plugin_win=str(places["plugin"]))

    assert run(command, places) == "allow"


@pytest.mark.parametrize(
    "template",
    [
        "cat {plugin}-evil/x",
        "cat {plugin}/../elsewhere/x",
        "cat {parent}",
        "cat {parent}/other/x",
        "cat {outside}/x",
    ],
)
def test_a_sibling_or_a_climb_out_of_a_read_root_is_still_outside(places, template):
    """Adversarial where: a prefix match lets `plugin-under-test-evil` through
    and an unresolved `..` lets a climb out of the root through."""
    command = template.format(
        plugin=places["plugin"].as_posix(), parent=places["plugin"].parent.as_posix(),
        outside=places["outside"].as_posix(),
    )

    assert run(command, places) == "deny"


@pytest.mark.skipif(os.name != "nt", reason="the /x/ drive form exists only in Git Bash on Windows")
def test_the_git_bash_form_of_a_read_root_is_inside_it(places):
    drive_letter = places["plugin"].drive[0].lower()
    rest = places["plugin"].as_posix().split(":", 1)[1]
    inside = f"/{drive_letter}{rest}/templates/a.md"
    sibling = f"/{drive_letter}{rest}-evil/a.md"

    assert run(f"cp {inside} x", places) == "allow"
    assert run(f"cp {sibling} x", places) == "deny"


@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit", "NotebookEdit"])
def test_file_tools_may_not_write_into_a_read_root_or_the_home(places, tool):
    """Adversarial where: sharing one inside-check between Bash words and file
    tools turns the read access into write access on the plugin under test."""
    hook = load_hook()
    for target in (places["plugin"] / "y.md", places["home"] / ".gitconfig"):
        out = hook.decide(
            event(tool, {"file_path": str(target), "content": "x"}, places["project"]),
            project=str(places["project"]), answer=never_asked,
            read_roots=[str(places["plugin"])], home=str(places["home"]),
        )
        assert decision(out) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "cat $HOME/.gitconfig",
        "cat ${HOME}/.gitconfig",
        "cat ~/.gitconfig",
        "cat ~",
        "ls $HOME",
        "cat $USERPROFILE/.gitconfig",
        "cat %USERPROFILE%/.gitconfig",
        "cat $env:USERPROFILE/.gitconfig",
        "cat $APPDATA/x",
        "cat $LOCALAPPDATA/x",
        "cat $TEMP/x",
        "ls $TMP",
    ],
)
def test_home_forms_are_allowed_only_when_a_home_is_set(places, command):
    """Adversarial where: a home variable that is always allowed, or one that
    is never allowed, breaks git or lets a build read the real home when the
    configuration lacks a home."""
    assert run(command, places) == "allow"
    assert run(command, places, home=None) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "cat $HOME/../x",
        "cat ~/../x",
        "cat ~other/x",
        "cat $HOMEDRIVE$HOMEPATH/x",
        "cat $HOME/../../x",
        "cat x$HOME/y",
        "cat $UNSET_VARIABLE/x",
    ],
)
def test_expansions_that_climb_out_of_the_home_or_name_unknown_places_are_denied(places, command):
    assert run(command, places) == "deny"


def test_a_variable_the_command_assigns_is_judged_by_its_values(places):
    """Adversarial where: a variable assigned an outside folder in one branch
    and an inside folder in another is judged by the first value only."""
    inside = places["plugin"].as_posix()
    outside = places["outside"].as_posix()

    assert run(f'R={inside}; cat "$R/x"', places) == "allow"
    assert run(f'R={outside}; cat "$R/x"', places) == "deny"
    assert run(f'for r in {inside} {outside}; do cat "$r/x"; done', places) == "deny"
    assert run(f'R=$(pwd); cat "$R/x"', places) == "deny"
    assert run(f'R={inside}; R={outside}; cat "$R/x"', places) == "deny"


def test_main_reads_read_roots_and_home_from_the_config_file(places, tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "project": str(places["project"]), "answer_command": [sys.executable, "-c", "pass"],
        "read_roots": [str(places["plugin"])], "home": str(places["home"]),
    }), encoding="utf-8")
    payload = json.dumps(bash(f"cat {places['plugin'].as_posix()}/a $HOME/b", places["project"]))
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps({
        "project": str(places["project"]), "answer_command": [sys.executable, "-c", "pass"],
    }), encoding="utf-8")
    hook = load_hook()

    _, allowed = hook.main([], payload, {hook.CONFIG_VARIABLE: str(config)})
    _, denied = hook.main([], payload, {hook.CONFIG_VARIABLE: str(bare)})

    assert json.loads(allowed)["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert json.loads(denied)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_the_hook_script_run_as_a_process_honours_the_config(places, tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "project": str(places["project"]), "answer_command": [sys.executable, "-c", "pass"],
        "read_roots": [str(places["plugin"])], "home": str(places["home"]),
    }), encoding="utf-8")
    payload = json.dumps(bash(setup_command(places["plugin"]), places["project"]))

    done = subprocess.run(
        [sys.executable, str(HOOK)], input=payload, capture_output=True, text=True,
        env={**os.environ, "OVERHEAD_HOOK_CONFIG": str(config)},
    )

    assert done.returncode == 0
    assert json.loads(done.stdout)["hookSpecificOutput"]["permissionDecision"] == "allow"
