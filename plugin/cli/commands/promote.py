"""`compass promote <spec>` - flat spec to folder spec (mechanical half).

Moves `specs/SPEC-NNN-name.md` to `specs/SPEC-NNN-name/index.md` via `git mv`
(history preserved) and marks it a folder spec with `children_count: 0`.
Inbound `[[SPEC-NNN-name]]` wikilinks keep resolving because the folder name
equals the old stem, so no link rewrite is needed. Deciding to promote and
authoring child specs stay with the agent.

Dry-run by default; `--apply` executes, mirroring `make_unit.py`'s and
`demote.py`'s contract. A promotion is a sizing decision and `--apply`
requires `--reason <text>`; `--volatile <text>` (repeatable) and `--by
human|agent` are optional. `--apply` mints a `sizing_id` and stamps it into
the new folder's `index.md`, so `compass demote` can later write a
correction row carrying the same id (see `commands/sizing.py`).
"""

import datetime
import subprocess
import sys

import vaultlib
from commands import sizing


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
    remaining, reason, volatile, by, flag_error = sizing.parse_flags(args)
    if flag_error:
        sys.stderr.write(f"compass promote: {flag_error}\n")
        return 1
    apply = "--apply" in remaining
    positional = [a for a in remaining if not a.startswith("--")]
    if not positional:
        sys.stderr.write("usage: compass promote <spec-id|path> [--reason <text>] [--apply]\n")
        return 1
    if apply and reason is None:
        sys.stderr.write(
            "compass promote: --reason is required on --apply, no changes made\n"
        )
        return 1

    vault_root = vaultlib.find_vault_root()
    path = _resolve(vault_root, positional[0])
    if path is None:
        sys.stderr.write(f"compass promote: spec not found: {positional[0]}\n")
        return 1
    if path.name == "index.md":
        sys.stderr.write("compass promote: already a folder spec\n")
        return 1

    folder = path.with_suffix("")
    dest = folder / "index.md"

    if not apply:
        sys.stdout.write(
            f"compass promote: would move {path.stem} (flat -> folder) "
            "(dry-run; pass --apply to write)\n"
            f"  {path.relative_to(vault_root)} -> {dest.relative_to(vault_root)}\n"
        )
        return 0

    folder.mkdir(parents=True, exist_ok=True)
    if not git_mv(vault_root.parent, path, dest):
        path.rename(dest)
    _add_children_count(dest)

    sizing_id = sizing.mint_id(vault_root)
    sizing.stamp_id(dest, sizing_id)
    sizing.append_row(vault_root, {
        "id": sizing_id,
        "action": "decision",
        "shape": "folder",
        "subject": dest.relative_to(vault_root).as_posix(),
        "reason": reason,
        "volatile": volatile,
        "by": by,
        "at": datetime.date.today().isoformat(),
    })

    sys.stdout.write(
        f"promoted: {path.stem} (flat -> folder)\n"
        f"  {path.relative_to(vault_root)} -> {dest.relative_to(vault_root)}\n"
        f"  children_count: 0\n"
    )
    return 0
