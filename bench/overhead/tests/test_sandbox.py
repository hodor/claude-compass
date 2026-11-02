"""Tests for sandbox.py: throwaway projects, kept copies and discards.

Adversarial themes: a project that is not its own git repository would inherit
the surrounding one; a CLAUDE.md above the projects root would load the human's
rules into a measured build; Windows refuses to delete read-only git objects;
a discard that skips the sandbox config leaves the project in the human's real
Claude state.
"""

import os
import stat
from pathlib import Path

import pytest

import sandbox


def same(left, right):
    return os.path.normcase(os.path.realpath(str(left))) == os.path.normcase(os.path.realpath(str(right)))


def tree(root):
    """Relative path -> bytes for every file under `root`."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(Path(root).rglob("*"))
        if p.is_file()
    }


def commit_a_file(git, folder):
    (folder / "src").mkdir(exist_ok=True)
    (folder / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    git(folder, "add", ".")
    git(folder, "commit", "-q", "-m", "first")


def test_new_project_is_its_own_git_repository_under_the_root(projects_root, git):
    """Adversarial where: a project created without its own `git init` resolves
    git commands to an enclosing repository, and two calls that return the same
    folder would make two builds share one project."""
    first = sandbox.new_project(projects_root)
    second = sandbox.new_project(projects_root)

    assert not same(first, second)
    for project in (first, second):
        assert same(project.parent, projects_root)
        assert same(git(project, "rev-parse", "--show-toplevel"), project)
        assert not (project / "CLAUDE.md").exists()


@pytest.mark.parametrize("holder", ["the root itself", "its parent", "two levels up", "the temporary base"])
def test_new_project_refuses_a_root_with_a_claude_md_above_it(projects_root, tmp_path, holder):
    """Adversarial where: a CLAUDE.md in the root or any ancestor loads into every
    session started below it; the check must cover the nearest and the farthest
    ancestor, not only the immediate parent."""
    root = projects_root / "x" / "y"
    root.mkdir(parents=True)
    folder = {
        "the root itself": root,
        "its parent": root.parent,
        "two levels up": projects_root,
        "the temporary base": tmp_path,
    }[holder]
    (folder / "CLAUDE.md").write_text("global rules\n", encoding="utf-8")

    with pytest.raises(sandbox.Refused):
        sandbox.new_project(root)

    assert [p for p in root.iterdir() if p.is_dir()] == []


def test_list_projects_returns_the_project_folders_sorted_and_nothing_else(projects_root):
    """Adversarial where: a missing root should read as no projects rather than
    raise, and a stray file in the root must not be listed as a project."""
    assert sandbox.list_projects(projects_root) == []

    created = [sandbox.new_project(projects_root) for _ in range(3)]
    (projects_root / "notes.txt").write_text("stray\n", encoding="utf-8")

    listed = sandbox.list_projects(projects_root)
    assert [os.path.normcase(os.path.realpath(p)) for p in listed] == sorted(
        os.path.normcase(os.path.realpath(p)) for p in created
    )


def test_keep_project_copies_the_whole_project_and_leaves_the_original(projects_root, tmp_path, git):
    """Adversarial where: a copy that skips dot-folders loses `.git`, and one that
    moves instead of copies leaves the later discard nothing to delete."""
    project = sandbox.new_project(projects_root)
    commit_a_file(git, project)
    destination = tmp_path / "kept" / "copy"

    result = sandbox.keep_project(project, destination)

    assert same(result, destination)
    assert tree(destination) == tree(project)
    assert (destination / ".git" / "HEAD").is_file()
    assert git(destination, "log", "--oneline") != ""
    assert (project / "src" / "app.py").is_file()


def test_discard_project_deletes_a_committed_project_and_purges_with_the_sandbox_config(
    projects_root, tmp_path, git, fake_cmd, use_scenario
):
    """Adversarial where: git object files are read-only on Windows and a plain
    recursive delete stops on them; the purge must name the project path, pass
    --yes, and run under the sandbox config rather than the human's; sibling
    projects and kept copies must survive."""
    log = use_scenario("clean")
    project = sandbox.new_project(projects_root)
    sibling = sandbox.new_project(projects_root)
    commit_a_file(git, project)
    readonly = project / "src" / "locked.txt"
    readonly.write_text("locked\n", encoding="utf-8")
    os.chmod(readonly, stat.S_IREAD)
    kept = sandbox.keep_project(project, tmp_path / "kept")
    config_dir = tmp_path / "sandbox-config-marker"

    sandbox.discard_project(project, config_dir=config_dir, claude_cmd=fake_cmd)

    assert not project.exists()
    assert sibling.is_dir()
    assert kept.is_dir()
    calls = log.calls()
    assert len(calls) == 1
    assert calls[0]["argv"][0] == "purge"
    assert same(calls[0]["argv"][1], project)
    assert calls[0]["argv"][2:] == ["--yes"]
    assert same(calls[0]["env"]["CLAUDE_CONFIG_DIR"], config_dir)


def test_command_line_verbs_new_list_and_keep(projects_root, tmp_path, capsys):
    """Adversarial where: the verbs a human types must print the paths they act
    on, since `keep` and `discard` take that path as their argument."""
    root = str(projects_root)

    assert sandbox.main(["--projects-root", root, "new"]) == 0
    created = capsys.readouterr().out.strip().splitlines()[-1]
    assert Path(created).is_dir()
    assert same(Path(created).parent, projects_root)

    assert sandbox.main(["--projects-root", root, "list"]) == 0
    listed = capsys.readouterr().out.strip().splitlines()
    assert len(listed) == 1 and same(listed[0], created)

    destination = tmp_path / "kept-by-cli"
    assert sandbox.main(["--projects-root", root, "keep", created, "--to", str(destination)]) == 0
    assert (destination / ".git").is_dir()
