"""Edge tests for the delete and copy paths of sandbox.py found by reading its
code: links, `..` segments, forged markers, roots inside a repository and
inherited git environment.

Adversarial themes: a link standing in for a project, or sitting inside one,
must never carry a delete or a copy onto a folder outside the project; a marker
file alone does not make a folder a projects root when a root is named; a
project created while GIT_DIR is set must still be its own repository.
"""

import os
import subprocess
import sys

import pytest

import sandbox
from conftest import run_git

MARKER = sandbox.MARKER


def make_link(kind, link, target):
    """Make `link` a directory link to `target`, or skip when the kind is unavailable."""
    if kind == "junction":
        if sys.platform != "win32":
            pytest.skip("junctions exist on Windows only")
        done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
        if done.returncode != 0:
            pytest.skip("cannot create a junction")
        return
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("cannot create a symbolic link")


def make_root(base, name="projects"):
    root = base / name
    root.mkdir(parents=True)
    (root / MARKER).write_text("marker\n", encoding="utf-8")
    return root


def make_project(root, name="proj-aaaaaa"):
    folder = root / name
    folder.mkdir()
    (folder / "work.txt").write_text("work\n", encoding="utf-8")
    return folder


def purge_calls(log):
    return [call for call in log.calls() if call["argv"][:1] == ["purge"]]


@pytest.fixture(params=["symlink", "junction"])
def link_kind(request):
    return request.param


def test_discard_refuses_a_link_in_place_of_a_project_even_when_its_target_looks_like_one(
    link_kind, tmp_path, fake_cmd, use_scenario
):
    """Adversarial where: a link named like a project whose target sits in a folder
    carrying a marker passes the marker and name checks once resolved; only the
    link check stops a delete that follows the link onto a real project elsewhere."""
    log = use_scenario("clean")
    elsewhere = make_root(tmp_path, "elsewhere")
    victim = make_project(elsewhere, "proj-bbbbbb")
    root = make_root(tmp_path)
    make_link(link_kind, root / "proj-aaaaaa", victim)

    with pytest.raises(sandbox.Refused):
        sandbox.discard_project(root / "proj-aaaaaa", config_dir=tmp_path / "cfg", claude_cmd=fake_cmd)

    assert (victim / "work.txt").read_text(encoding="utf-8") == "work\n"
    assert purge_calls(log) == []


def test_discard_through_a_link_to_the_projects_root_removes_the_project(
    link_kind, tmp_path, fake_cmd, use_scenario
):
    """Adversarial where: refusing every path that crosses a link would also
    refuse a root reached through a link (a drive alias, a mapped folder); the
    project must resolve to the named root and be deleted."""
    log = use_scenario("clean")
    root = make_root(tmp_path)
    project = make_project(root)
    alias = tmp_path / "alias"
    make_link(link_kind, alias, root)

    sandbox.discard_project(alias / "proj-aaaaaa", config_dir=tmp_path / "cfg", claude_cmd=fake_cmd, projects_root=root)

    assert not project.exists()
    assert len(purge_calls(log)) == 1


def test_discard_removes_a_link_inside_the_project_and_leaves_what_it_points_to(
    link_kind, tmp_path, fake_cmd, use_scenario
):
    """Adversarial where: a project holding a link to a folder outside it (a
    shared cache, a vendored checkout) must lose the link only; a recursive delete
    that follows the link empties the outside folder."""
    use_scenario("clean")
    root = make_root(tmp_path)
    project = make_project(root)
    outside = tmp_path / "outside"
    (outside / "deep").mkdir(parents=True)
    (outside / "deep" / "precious.txt").write_text("precious\n", encoding="utf-8")
    make_link(link_kind, project / "external", outside)

    sandbox.discard_project(project, config_dir=tmp_path / "cfg", claude_cmd=fake_cmd, projects_root=root)

    assert not project.exists()
    assert (outside / "deep" / "precious.txt").read_text(encoding="utf-8") == "precious\n"


def test_discard_paths_with_dot_dot_segments_resolve_before_the_checks(tmp_path, fake_cmd, use_scenario):
    """Adversarial where: a `..` segment can make a path that ends in a project
    name point at a folder outside the root, or a path that starts inside a
    project point at the root; the checks must act on the normalised path and the
    delete must follow the same path."""
    log = use_scenario("clean")
    root = make_root(tmp_path)
    first = make_project(root, "proj-aaaaaa")
    second = make_project(root, "proj-bbbbbb")
    outside = make_project(tmp_path / "outside-parent", "proj-cccccc") if (tmp_path / "outside-parent").mkdir() is None else None
    (tmp_path / "outside-parent" / MARKER).write_text("forged\n", encoding="utf-8")
    cfg = tmp_path / "cfg"

    refused = [
        root / "proj-aaaaaa" / "..",
        root / ".." / "outside-parent" / "proj-cccccc",
        root / "proj-aaaaaa" / ".." / ".." / "outside-parent" / "proj-cccccc",
    ]
    for path in refused:
        with pytest.raises(sandbox.Refused):
            sandbox.discard_project(path, config_dir=cfg, claude_cmd=fake_cmd, projects_root=root)
    sandbox.discard_project(root / "proj-aaaaaa" / ".." / "proj-bbbbbb", config_dir=cfg, claude_cmd=fake_cmd,
                            projects_root=root)

    assert (first / "work.txt").is_file()
    assert (outside / "work.txt").is_file()
    assert not second.exists()
    assert len(purge_calls(log)) == 1


def test_discard_with_a_named_root_ignores_a_marker_forged_elsewhere(tmp_path, fake_cmd, use_scenario):
    """Adversarial where: any folder can hold a marker file; when the root is
    named, a project-named folder under another marker folder, under a
    grandparent-only marker, under a marker that is a directory, or nested inside
    a project must be refused and left whole."""
    log = use_scenario("clean")
    root = make_root(tmp_path)
    real = make_project(root)
    forged_parent = tmp_path / "docs"
    forged_parent.mkdir()
    (forged_parent / MARKER).write_text("forged\n", encoding="utf-8")
    forged = make_project(forged_parent)
    (root / "sub").mkdir()
    deep = make_project(root / "sub")
    dir_marker_root = tmp_path / "dir-marker"
    (dir_marker_root / MARKER).mkdir(parents=True)
    dir_marked = make_project(dir_marker_root)
    nested = make_project(real, "proj-dddddd")

    for path in (forged, deep, dir_marked, nested):
        with pytest.raises(sandbox.Refused):
            sandbox.discard_project(path, config_dir=tmp_path / "cfg", claude_cmd=fake_cmd, projects_root=root)

    for folder in (real, forged, deep, dir_marked, nested):
        assert (folder / "work.txt").is_file()
    assert purge_calls(log) == []


def test_a_projects_root_inside_a_repository_gives_projects_that_are_their_own_repositories_and_discard_spares_the_rest(
    tmp_path, repo, git, fake_cmd, use_scenario
):
    """Adversarial where: a root under a checkout makes the checkout the enclosing
    repository of every project; the project must still be its own repository, and
    discarding it must leave the checkout's tracked files and history untouched."""
    use_scenario("clean")
    root = repo / "scratch" / "projects"
    tracked_before = git(repo, "ls-files")
    head_before = git(repo, "rev-parse", "HEAD")

    project = sandbox.new_project(root)
    own_top = git(project, "rev-parse", "--show-toplevel")
    sandbox.discard_project(project, config_dir=tmp_path / "cfg", claude_cmd=fake_cmd, projects_root=root)

    assert os.path.normcase(os.path.realpath(own_top)) == os.path.normcase(os.path.realpath(project))
    assert not project.exists()
    assert git(repo, "ls-files") == tracked_before
    assert git(repo, "rev-parse", "HEAD") == head_before
    assert git(repo, "ls-files", "--deleted") == ""
    assert (repo / "plugin" / "keep.txt").is_file()


def test_new_project_is_its_own_repository_when_git_dir_is_inherited_from_a_hook(tmp_path, projects_root, monkeypatch):
    """Adversarial where: under a git hook GIT_DIR names the hooked repository, so
    `git init` in the new folder reinitialises that repository and leaves the
    project without a `.git` of its own, sharing history with the hooked repo."""
    other = tmp_path / "hooked"
    other.mkdir()
    run_git(other, "init", "-q")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))

    project = sandbox.new_project(projects_root)

    assert (project / ".git").exists()


def test_new_project_leaves_no_half_made_folder_when_git_is_not_runnable(projects_root, monkeypatch):
    """Adversarial where: git missing from PATH fails after the folder exists; the
    folder must not stay behind looking like a finished project."""
    monkeypatch.setenv("PATH", os.devnull)

    with pytest.raises(RuntimeError):
        sandbox.new_project(projects_root)

    assert sandbox.list_projects(projects_root) == []


@pytest.mark.parametrize("through", ["dotdot", "symlink", "junction"])
def test_keep_refuses_a_destination_that_reaches_the_inside_of_the_project_by_dots_or_a_link(
    through, tmp_path
):
    """Adversarial where: copying a project into itself recurses without end; a
    destination that is lexically outside the project but resolves inside it
    through `..` or through a link must be refused and create nothing."""
    root = make_root(tmp_path)
    project = make_project(root)
    (project / "sub").mkdir()
    if through == "dotdot":
        destination = root / "proj-zzzzzz" / ".." / "proj-aaaaaa" / "sub" / "copy"
    else:
        make_link(through, tmp_path / "shortcut", project / "sub")
        destination = tmp_path / "shortcut" / "copy"

    with pytest.raises(sandbox.Refused):
        sandbox.keep_project(project, destination, projects_root=root)

    assert sorted(path.name for path in (project / "sub").iterdir()) == []
    assert sorted(path.name for path in project.iterdir()) == ["sub", "work.txt"]
