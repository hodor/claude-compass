"""Tests for the sandbox home, the read roots and the plugin check of drive.py.

A build session runs with HOME, USERPROFILE, APPDATA, LOCALAPPDATA, TEMP and
TMP inside `<private_root>/homes/<project key>` (HOMEDRIVE and HOMEPATH
removed), the folder holds a `.gitconfig` with a build identity, and the hook
config names `home` and `read_roots` (the plugin folder in the Compass arm, none
in the baseline arm). After the build `plugin/` of the repository must be
unchanged, else the build ends "failed" with a reason.

Adversarial themes: a hook config that gives the baseline arm the plugin as a
read root, an environment that keeps the real home through a variable of
another case, a build that writes into the plugin and still reports done, and a
home shared by two projects.
"""

import json
import os
import subprocess
import sys

import pytest

import drive
import human
from test_drive import ScriptedHuman, build, read_records, start_entry


def hook_config(cmd):
    env = start_entry(cmd)["env"]
    return json.loads(open(env["OVERHEAD_HOOK_CONFIG"], encoding="utf-8").read())


def pushed_repo(repo, tmp_path, git):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "-q", "--bare")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "HEAD")


def test_the_session_environment_carries_the_sandbox_home(project, repo, private_root, tmp_path, monkeypatch):
    """Adversarial where: a variable left at the real home (HOMEDRIVE and
    HOMEPATH, or a lower-case spelling) lets a tool resolve the real home
    folder while HOME alone points into the sandbox."""
    monkeypatch.setenv("HOMEDRIVE", "C:")
    monkeypatch.setenv("HOMEPATH", "\\Users\\real")
    monkeypatch.setenv("APPDATA", str(tmp_path / "real-appdata"))
    who = ScriptedHuman([human.Reply(text="done", done=True)])

    _, cmd = build(project, repo, private_root, tmp_path, {"turns": [{}]}, who)

    env = start_entry(cmd)["env"]
    home = private_root / "homes" / drive.project_key(project)
    assert {k.upper(): v for k, v in env.items() if k.upper() in ("HOME", "USERPROFILE")} == {
        "HOME": str(home), "USERPROFILE": str(home),
    }
    keys = {key.upper(): value for key, value in env.items()}
    assert "HOMEDRIVE" not in keys and "HOMEPATH" not in keys
    for name in ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        assert os.path.commonpath([os.path.realpath(keys[name]), os.path.realpath(home)]) == os.path.realpath(home)
        assert os.path.isdir(keys[name])
    assert keys["CLAUDE_CONFIG_DIR"] == str(private_root / "claude-config")


def test_the_home_holds_a_gitconfig_that_lets_git_commit(project, repo, private_root, tmp_path):
    who = ScriptedHuman([human.Reply(text="done", done=True)])
    build(project, repo, private_root, tmp_path, {"turns": [{}]}, who)
    home = private_root / "homes" / drive.project_key(project)
    work = tmp_path / "commit-check"
    work.mkdir()
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME")}
    env.update(HOME=str(home), USERPROFILE=str(home), GIT_CONFIG_NOSYSTEM="1")
    env.pop("XDG_CONFIG_HOME", None)

    subprocess.run(["git", "init", "-q"], cwd=work, env=env, check=True)
    (work / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=work, env=env, check=True)
    done = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "x"], cwd=work, env=env,
        capture_output=True, text=True,
    )
    author = subprocess.run(
        ["git", "log", "-1", "--format=%an <%ae>"], cwd=work, env=env, capture_output=True, text=True,
    ).stdout.strip()

    assert done.returncode == 0, done.stderr
    assert author == "Overhead Build <build@example.invalid>"


def test_two_projects_get_two_homes(tmp_path, private_root):
    first, second = tmp_path / "a" / "app", tmp_path / "b" / "app"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    assert drive.sandbox_home(first, private_root) != drive.sandbox_home(second, private_root)


def test_the_baseline_arm_has_no_read_root_and_the_hook_config_names_the_home(
    project, repo, private_root, tmp_path
):
    """Adversarial where: a read root in the baseline arm lets the control
    session read the plugin it is meant not to have."""
    who = ScriptedHuman([human.Reply(text="done", done=True)])

    _, cmd = build(project, repo, private_root, tmp_path, {"turns": [{}]}, who)

    config = hook_config(cmd)
    assert config["read_roots"] == []
    assert config["home"] == str(private_root / "homes" / drive.project_key(project))


def test_the_compass_arm_reads_the_plugin_folder_only(project, repo, private_root, tmp_path, git):
    pushed_repo(repo, tmp_path, git)
    who = ScriptedHuman([human.Reply(text="done", done=True)])

    _, cmd = build(project, repo, private_root, tmp_path, {"turns": [{}]}, who, arm="compass")

    config = hook_config(cmd)
    assert [os.path.realpath(root) for root in config["read_roots"]] == [os.path.realpath(repo / "plugin")]
    assert config["home"] == str(private_root / "homes" / drive.project_key(project))


def test_write_hook_config_writes_read_roots_and_home_when_given(tmp_path, private_root):
    project = tmp_path / "app"
    project.mkdir()

    path = drive.write_hook_config(project, private_root, ["h"])
    full = drive.write_hook_config(project, private_root, ["h"], read_roots=[tmp_path / "p"], home=tmp_path / "h")

    assert path == full
    assert json.loads(full.read_text(encoding="utf-8")) == {
        "project": str(project), "answer_command": ["h"], "read_roots": [str(tmp_path / "p")],
        "home": str(tmp_path / "h"),
    }


class WritesIntoPlugin(ScriptedHuman):
    def __init__(self, plugin, replies):
        super().__init__(replies)
        self.plugin = plugin

    def reply(self, text):
        (self.plugin / "stray.txt").write_text("written by the build\n", encoding="utf-8")
        return super().reply(text)


def test_a_build_that_changed_the_plugin_ends_failed_with_the_reason(project, repo, private_root, tmp_path):
    """Adversarial where: a build that wrote into the plugin under test and
    still ended done would score the next arm against a changed plugin."""
    who = WritesIntoPlugin(repo / "plugin", [human.Reply(text="done", done=True)])

    result, _ = build(project, repo, private_root, tmp_path, {"turns": [{}]}, who)

    assert result.end == "failed"
    assert "plugin/ changed" in result.reason
    assert "stray.txt" in result.reason
    row = [r for r in read_records(private_root) if r["role"] == "build"][0]
    assert row["outcome"] == "failed"


def test_a_modified_tracked_plugin_file_is_a_change_too(project, repo, private_root, tmp_path):
    class Edits(ScriptedHuman):
        def reply(self, text):
            (repo / "plugin" / "keep.txt").write_text("edited\n", encoding="utf-8")
            return super().reply(text)

    who = Edits([human.Reply(text="done", done=True)])

    result, _ = build(project, repo, private_root, tmp_path, {"turns": [{}]}, who)

    assert result.end == "failed"
    assert "keep.txt" in result.reason


def test_an_untouched_plugin_leaves_the_end_and_the_reason_alone(project, repo, private_root, tmp_path):
    who = ScriptedHuman([human.Reply(text="done", done=True)])

    result, _ = build(project, repo, private_root, tmp_path, {"turns": [{}]}, who)

    assert result.end == "human-done"
    assert result.reason == ""


def test_plugin_changes_lists_one_line_per_changed_path(repo):
    assert drive.plugin_changes(repo) == []
    (repo / "plugin" / "new.txt").write_text("n\n", encoding="utf-8")
    (repo / "README.md").write_text("outside plugin\n", encoding="utf-8")

    changes = drive.plugin_changes(repo)

    assert len(changes) == 1 and changes[0].endswith("plugin/new.txt")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows spells variable names in any case")
def test_apply_home_replaces_variables_whatever_their_case(tmp_path):
    env = drive.apply_home({"Userprofile": "C:\\real", "homedrive": "C:", "Temp": "C:\\real\\t", "KEEP": "1"}, tmp_path)

    assert env["KEEP"] == "1"
    assert [key for key in env if key.upper() == "USERPROFILE"] == ["USERPROFILE"]
    assert [key for key in env if key.upper() in ("HOMEDRIVE", "TEMP")] == ["TEMP"]
    assert env["TEMP"] == str(tmp_path / "AppData/Local/Temp")
