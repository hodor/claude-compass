"""Tests for the session environment's provider and model variables, repository
variables, editor folders on PATH and the lookup of the claude executable.

Adversarial themes: one inherited provider or model variable moves a build off
the subscription without any visible change; a PATH filter that matches part of
a folder name drops tools the build needs; a missing executable must stop the
harness before it deletes or starts anything.
"""

import os

import pytest

import launch
import sandbox


@pytest.mark.parametrize(
    "name",
    [
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_PROFILE",
        "aws_region",
        "Anthropic_Base_Url",
    ],
)
def test_session_environment_drops_provider_and_model_selection(name, private_root):
    """Adversarial where: a provider switch, a custom endpoint, a model override
    or an AWS credential left in the child bills something other than the
    subscription, or changes the model, with no error; the name match is
    case-insensitive."""
    parent = {name: "inherited", "KEEP_ME": "kept"}

    env = launch.session_environment(parent, private_root)

    assert name not in env
    assert env["KEEP_ME"] == "kept"


def test_session_environment_keeps_variables_that_only_resemble_dropped_ones(private_root):
    """Adversarial where: matching the prefix `AWS` without its underscore, or any
    name containing `MODEL`, would drop unrelated variables."""
    parent = {"AWSOME_TOOL": "1", "MY_ANTHROPIC_MODEL": "x", "ANTHROPIC_LOG": "debug"}

    env = launch.session_environment(parent, private_root)

    assert {"AWSOME_TOOL", "MY_ANTHROPIC_MODEL", "ANTHROPIC_LOG"} <= set(env)


@pytest.mark.parametrize("name", ["GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "git_dir"])
def test_session_environment_drops_repository_location_variables(name, private_root):
    """Adversarial where: a hook-inherited GIT_DIR in the child makes the build's
    own git commands act on the hooked repository instead of the project."""
    env = launch.session_environment({name: "/elsewhere", "KEEP_ME": "kept"}, private_root)

    assert name not in env
    assert env["KEEP_ME"] == "kept"


def folder(*parts):
    return os.sep.join(["", *parts])


EDITOR_ENTRIES = [
    folder("opt", "Microsoft VS Code", "bin"),
    folder("opt", "cursor", "resources", "app", "bin"),
    "C:\\Users\\u\\AppData\\Local\\Programs\\Cursor\\resources\\app\\bin",
    folder("Applications", "Visual Studio Code.app", "Contents", "Resources", "app", "bin"),
    folder("Applications", "Visual Studio Code - Insiders.app", "Contents", "Resources", "app", "bin"),
]
OTHER_ENTRIES = [
    folder("opt", "cursor-tools", "bin"),
    folder("home", "u", "vscode-projects", "bin"),
    folder("opt", "barcursor", "bin"),
    folder("opt", "codecs"),
    folder("usr", "bin"),
]


def test_editor_folders_leave_path_by_whole_folder_name_only(private_root):
    """Adversarial where: matching a fragment of any folder name drops tools whose
    folder merely contains `cursor` or `vscode`; matching only the last folder
    misses the `bin` folder inside an editor install."""
    entries = [*EDITOR_ENTRIES[:2], *OTHER_ENTRIES[:3], *EDITOR_ENTRIES[2:], *OTHER_ENTRIES[3:]]

    env = launch.session_environment({"PATH": os.pathsep.join(entries)}, private_root)

    assert env["PATH"].split(os.pathsep) == OTHER_ENTRIES


def test_a_missing_claude_command_is_refused_with_a_plain_message(tmp_path, repo, project, private_root):
    """Adversarial where: a command that cannot be found must stop the harness
    with a message naming the command, not surface as a raw OSError from deep in
    the process launch."""
    missing = str(tmp_path / "no-such-claude")

    with pytest.raises(launch.Refused, match="no-such-claude"):
        launch.run_session(project, "go", repo_root=repo, private_root=private_root, claude_cmd=[missing])


def test_discard_with_a_missing_claude_command_keeps_the_project(tmp_path, projects_root):
    """Adversarial where: resolving the command after the delete leaves a project
    gone from disk but still known to Claude Code's state, with no way to run the
    purge."""
    project = sandbox.new_project(projects_root)

    with pytest.raises(launch.Refused):
        sandbox.discard_project(project, config_dir=tmp_path / "config", claude_cmd=[str(tmp_path / "no-such-claude")])

    assert project.is_dir()


def test_the_sandbox_command_line_reports_a_missing_claude_command_as_an_error_not_a_traceback(
    tmp_path, projects_root, monkeypatch, capsys
):
    """Adversarial where: the verbs a human types catch the harness's own
    refusals; an uncaught launch.Refused ends in a traceback and exit code 1."""
    project = sandbox.new_project(projects_root)
    monkeypatch.setenv("PATH", str(tmp_path))

    code = sandbox.main(["--projects-root", str(projects_root), "discard", str(project), "--config-dir", str(tmp_path)])

    assert code == 2
    assert "claude" in capsys.readouterr().err
    assert project.is_dir()
