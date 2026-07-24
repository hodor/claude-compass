"""`compass promote <spec>` - flat spec to folder spec (mechanical half).

Moves `specs/SPEC-NNN-name.md` to `specs/SPEC-NNN-name/index.md` via `git mv`
(history preserved) and marks it a folder spec with `children_count: 0`.
Inbound `[[SPEC-NNN-name]]` wikilinks keep resolving because the folder name
equals the old stem, so no link rewrite is needed. Deciding to promote and
authoring child specs stay with the agent.
"""

import subprocess
import sys

import vaultlib


def _resolve(vault_root, target):
    if target.endswith(".md") or "/" in target:
        candidate = vault_root / target
        return candidate if candidate.is_file() else None
    for type_dir in vaultlib.discover_type_dirs(vault_root):
        candidate = vault_root / type_dir / f"{target}.md"
        if candidate.is_file():
            return candidate
    return None


def git_mv(repo, src, dest):
    """Move `src` to `dest` with `git mv` inside `repo`, preserving history.

    Returns True on success, False when git is unavailable or refuses the
    move (e.g. the path is untracked or `repo` is not a repository); callers
    fall back to a plain filesystem rename. Shared by `promote` and
    `make-unit`.
    """
    try:
        result = subprocess.run(
            ["git", "mv", str(src), str(dest)],
            cwd=str(repo), capture_output=True, text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def _add_children_count(path):
    lines = path.read_text(encoding="utf-8").split("\n")
    closing = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if closing is not None and not any(l.startswith("children_count:") for l in lines[:closing]):
        lines.insert(closing, "children_count: 0")
    vaultlib.write_text_lf(path, "\n".join(lines))


def run(args):
    if not args:
        sys.stderr.write("usage: compass promote <spec-id|path>\n")
        return 1
    vault_root = vaultlib.find_vault_root()
    path = _resolve(vault_root, args[0])
    if path is None:
        sys.stderr.write(f"compass promote: spec not found: {args[0]}\n")
        return 1
    if path.name == "index.md":
        sys.stderr.write("compass promote: already a folder spec\n")
        return 1

    folder = path.with_suffix("")
    dest = folder / "index.md"
    folder.mkdir(parents=True, exist_ok=True)
    if not git_mv(vault_root.parent, path, dest):
        path.rename(dest)
    _add_children_count(dest)

    sys.stdout.write(
        f"promoted: {path.stem} (flat -> folder)\n"
        f"  {path.relative_to(vault_root)} -> {dest.relative_to(vault_root)}\n"
        f"  children_count: 0\n"
    )
    return 0
