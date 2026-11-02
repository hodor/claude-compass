"""Throwaway projects for the overhead measurement.

A project is a folder directly under the projects root, with its own git
repository, named `proj-` and six hexadecimal digits. The root holds a marker
file written by `new_project`; `keep` and `discard` act only on a project folder
that is a direct child of a folder carrying that marker (and, when a root is
named, only inside that root), and refuse anything else before they touch the
disk.

    python sandbox.py [--projects-root DIR] new
    python sandbox.py [--projects-root DIR] list
    python sandbox.py [--projects-root DIR] keep PROJECT --to DIR
    python sandbox.py [--projects-root DIR] discard PROJECT [--config-dir DIR]

`new` refuses a root with a `CLAUDE.md` in it or in any folder above it (such a
file loads into every session started below) and a root that already holds
entries but no marker.
"""

import argparse
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import launch

MARKER = ".compass-overhead-projects"
PROJECT_NAME = re.compile(r"proj-[0-9a-f]{6}")
MEMORY_FILES = ("CLAUDE.md", "CLAUDE.local.md")
DEFAULT_PROJECTS_ROOT = (
    Path("C:/compass-overhead/projects") if sys.platform == "win32" else Path("/var/tmp/compass-overhead/projects")
)


class Refused(Exception):
    """The operation was not carried out."""


def _same(left, right):
    return os.path.normcase(os.path.realpath(str(left))) == os.path.normcase(os.path.realpath(str(right)))


def _memory_file_above(root):
    """The first `CLAUDE.md` in `root` or any folder above it, or None."""
    here = Path(os.path.abspath(root))
    for folder in (here, *here.parents):
        for name in MEMORY_FILES:
            if (folder / name).exists():
                return folder / name
    return None


def new_project(projects_root):
    """Create a project folder under `projects_root`, its own git repository."""
    root = Path(os.path.abspath(projects_root))
    found = _memory_file_above(root)
    if found is not None:
        raise Refused(f"{found} would load into every session below {root}")
    if root.is_dir() and not (root / MARKER).is_file() and any(root.iterdir()):
        raise Refused(f"{root} holds entries but is not a projects root")
    root.mkdir(parents=True, exist_ok=True)
    (root / MARKER).write_text("Folders in this directory are throwaway overhead-measurement projects.\n", encoding="utf-8")
    while True:
        project = root / f"proj-{secrets.token_hex(3)}"
        try:
            project.mkdir()
            break
        except FileExistsError:
            continue
    try:
        done = subprocess.run(
            ["git", "init", "-q"], cwd=project, capture_output=True, text=True, env=launch.git_environment(),
        )
    except OSError as error:
        project.rmdir()
        raise RuntimeError(f"git cannot be run: {error}") from error
    if done.returncode != 0:
        _remove_tree(project)
        raise RuntimeError(f"git init failed: {done.stderr.strip()}")
    return project


def list_projects(projects_root):
    """The project folders under `projects_root`, sorted by name."""
    root = Path(projects_root)
    if not root.is_dir():
        return []
    return sorted(
        (p for p in root.iterdir() if PROJECT_NAME.fullmatch(p.name) and p.is_dir() and not _is_link(p)),
        key=lambda p: p.name,
    )


def _is_link(path):
    return os.path.islink(path) or (hasattr(os.path, "isjunction") and os.path.isjunction(path))


def check_project(project, projects_root=None):
    """The absolute path of `project` once it is shown to be a project folder.

    A project is a real folder (not a link) named like the folders `new_project`
    makes, and a direct child of a folder carrying the projects marker. When `projects_root` is given the parent must
    be that folder, compared after resolving both. Raises Refused otherwise.
    """
    path = Path(os.path.abspath(project))
    if not PROJECT_NAME.fullmatch(path.name):
        raise Refused(f"{path} is not named like a project folder")
    if _is_link(path):
        raise Refused(f"{path} is a link, not a project folder")
    resolved = Path(os.path.realpath(path))
    parent = resolved.parent
    if projects_root is not None and not _same(parent, projects_root):
        raise Refused(f"{path} is not directly inside the projects root")
    if not (parent / MARKER).is_file():
        raise Refused(f"{path} is not inside a projects root")
    return path


def keep_project(project, to, *, projects_root=None):
    """Copy the whole project, `.git` included, to `to`; the original stays."""
    source = check_project(project, projects_root)
    if not source.is_dir():
        raise Refused(f"{source} does not exist")
    destination = Path(os.path.abspath(to))
    if _same(destination, source) or Path(os.path.realpath(source)) in Path(os.path.realpath(destination)).parents:
        raise Refused("the destination is inside the project")
    shutil.copytree(source, destination, symlinks=True)
    return destination


def _make_writable_and_retry(function, path, _error):
    os.chmod(path, stat.S_IRWXU if os.path.isdir(path) else stat.S_IWRITE)
    function(path)


def _remove_tree(path):
    """Delete a folder, including read-only files such as git objects.

    Junctions inside the tree are removed as links, never followed (Python 3.12
    and later).
    """
    shutil.rmtree(path, onexc=_make_writable_and_retry)


def discard_project(project, *, config_dir, claude_cmd=None, projects_root=None):
    """Delete the project folder, then run `claude purge <path> --yes` under `config_dir`.

    Refuses, before deleting anything, a path that is not a project folder of a
    projects root.
    """
    path = check_project(project, projects_root)
    command = launch.resolve_command(claude_cmd, os.environ) + ["purge", str(path), "--yes"]
    env = {key: value for key, value in os.environ.items() if not launch.drops_variable(key)}
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    if path.exists():
        _remove_tree(path)
    done = subprocess.run(command, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        raise RuntimeError(f"claude purge exited {done.returncode}: {done.stderr.strip()}")


def _build_parser():
    parser = argparse.ArgumentParser(prog="sandbox.py", description="Throwaway overhead-measurement projects.")
    parser.add_argument("--projects-root", default=str(DEFAULT_PROJECTS_ROOT), help="folder holding the projects")
    verbs = parser.add_subparsers(dest="verb", required=True)
    verbs.add_parser("new", help="create a project and print its path")
    verbs.add_parser("list", help="print the project paths")
    keep = verbs.add_parser("keep", help="copy a project to a folder")
    keep.add_argument("project")
    keep.add_argument("--to", required=True, help="folder to create")
    discard = verbs.add_parser("discard", help="delete a project and purge its Claude state")
    discard.add_argument("project")
    discard.add_argument("--config-dir", default=None, help="sandbox Claude config (default: the private root's)")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    root = args.projects_root
    try:
        if args.verb == "new":
            print(new_project(root))
        elif args.verb == "list":
            for project in list_projects(root):
                print(project)
        elif args.verb == "keep":
            print(keep_project(args.project, args.to, projects_root=root))
        else:
            config_dir = args.config_dir or str(launch.default_private_root() / "claude-config")
            discard_project(args.project, config_dir=config_dir, projects_root=root)
            print(f"discarded {args.project}")
    except (Refused, launch.Refused, OSError, RuntimeError) as error:
        print(f"sandbox: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
