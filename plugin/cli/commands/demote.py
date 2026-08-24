"""`compass demote <folder-spec>` - folder spec to flat file (inverse of
`promote`).

Moves `specs/SPEC-NNN-name/index.md` back to `specs/SPEC-NNN-name.md` via
`git mv` (history preserved) and drops the `children_count` frontmatter line
`promote` added, by deleting that one line rather than a YAML round trip - so
every other line survives byte for byte. Since the folder name equals the
flat file's stem, inbound `[[SPEC-NNN-name]]` wikilinks keep resolving
without a link rewrite.

Refuses outright - exit 1, zero changes - when the folder holds anything
besides its own `index.md`: demoting a folder with real children would
discard their content, and only an explicit, empty-children folder is ever
moved (LESSON-installer-removes-only-what-it-installed - act only on what is
named, never on an inferred complement). Also refuses when the restored flat
path already exists.

Dry-run by default; `--apply` executes, then regenerates derived vault state
(`compass sync`) and reports vault health, mirroring `make_unit.py`'s
contract.
"""

import sys

import vaultlib
from commands import sync as sync_command
from commands.make_unit import _report_vault_health
from commands.promote import git_mv


def _resolve(vault_root, target):
    """Resolve a folder-spec argument to its folder path.

    Accepts a vault-relative path (with or without a trailing `index.md` or
    `.md` suffix) or a bare stem searched across every root type directory -
    the same argument shapes `promote` accepts, adapted for a folder rather
    than a flat file. Returns the folder path, or None when it does not
    resolve to a folder spec (a directory carrying its own `index.md`).
    """
    norm = target.replace("\\", "/").strip("/")
    if norm.endswith("/index.md"):
        norm = norm[: -len("/index.md")]
    elif norm.endswith(".md"):
        norm = norm[:-3]
    if "/" in norm:
        candidate = vault_root / norm
        if candidate.is_dir() and (candidate / "index.md").is_file():
            return candidate
        return None
    for type_dir in vaultlib.discover_type_dirs(vault_root):
        candidate = vault_root / type_dir / norm
        if candidate.is_dir() and (candidate / "index.md").is_file():
            return candidate
    return None


def _drop_children_count(path):
    """Remove the `children_count:` frontmatter line, restoring the exact
    body `promote` started from. Line deletion, not a YAML round trip, so
    key order, quoting, and blank lines all survive byte for byte."""
    lines = path.read_text(encoding="utf-8").split("\n")
    closing = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if closing is not None:
        lines = [
            line for i, line in enumerate(lines)
            if not (i < closing and line.startswith("children_count:"))
        ]
    vaultlib.write_text_lf(path, "\n".join(lines))


def run(args):
    apply = "--apply" in args
    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        sys.stderr.write("usage: compass demote <folder-spec> [--apply]\n")
        return 1
    target = positional[0]
    vault_root = vaultlib.find_vault_root()
    folder = _resolve(vault_root, target)
    if folder is None:
        sys.stderr.write(f"compass demote: folder spec not found: {target}\n")
        return 1

    children = [p for p in folder.iterdir() if p.name != "index.md"]
    if children:
        sys.stderr.write(
            "compass demote: refused, no changes made\n"
            f"  {folder.relative_to(vault_root).as_posix()} has children, "
            "demote only a childless folder spec\n"
        )
        return 1

    dest = folder.parent / (folder.name + ".md")
    if dest.exists():
        sys.stderr.write(
            "compass demote: refused, no changes made\n"
            f"  target exists: {dest.relative_to(vault_root).as_posix()}\n"
        )
        return 1

    if not apply:
        sys.stdout.write(
            f"compass demote: would restore '{target}' to "
            f"{dest.relative_to(vault_root).as_posix()} "
            "(dry-run; pass --apply to write)\n"
        )
        return 0

    index_path = folder / "index.md"
    if not git_mv(vault_root.parent, index_path, dest):
        index_path.rename(dest)
    folder.rmdir()
    _drop_children_count(dest)

    sys.stdout.write(
        f"demoted: {dest.stem} (folder -> flat)\n"
        f"  {folder.relative_to(vault_root).as_posix()} -> "
        f"{dest.relative_to(vault_root).as_posix()}\n"
    )
    # sync's tag-index write assumes meta/ already exists; ensure it here so
    # a vault that has never had a shape-changing command run against it
    # does not crash on the very first one.
    (vault_root / "meta").mkdir(exist_ok=True)
    sync_command.sync(vault_root)
    _report_vault_health(vault_root)
    return 0
