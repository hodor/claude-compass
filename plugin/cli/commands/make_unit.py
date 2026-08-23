"""`compass make-unit <name> [artifact...]` - create a unit folder, optionally
moving artifacts into it.

Creates `<name>/` at the vault root with a `type: unit` `index.md` marker (the
classification signal `classify_root_dirs` looks for) and git-moves each named
artifact into the unit's matching type directory, derived from the artifact's
current location (`specs/SPEC-004-x.md` lands in `<name>/specs/`). Filenames,
numbers, and frontmatter are untouched, so bare-stem links to the moved files
keep resolving. With no artifacts named, the unit folder holds only its
`index.md` marker - no empty type subdirectories are created, since git does
not track them.

The moved artifacts' entries are removed from the root `index.md` - sync is
append-only and cannot heal them - then an in-process `sync` regenerates
derived state (the unit's index section, tag index, lessons catalog) and an
in-process `validate` reports the vault's health. A zero-artifact unit skips
sync: there is nothing for it to fold into a section, and the root index is
left untouched. Validate still runs, since the vault's health is independent
of whether this particular unit moved any artifacts.

Dry-run by default; `--apply` executes. The operation refuses outright - exit
1, zero changes - when the unit target already exists, is a reserved name, or
already resolves as a wikilink target; when an artifact name is ambiguous, an
artifact cannot be found, an artifact is not a root-level type-dir member, or
two arguments overlap.
"""

import datetime
import re
import sys

import vaultlib
from commands import sync as sync_command
from commands import validate as validate_command
from commands.promote import git_mv

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")

RESERVED_NAMES = set(vaultlib.CORE_TYPE_DIRS) | vaultlib.NON_TYPE_DIRS


def _check_target(vault_root, name, resolve):
    """Problems with the unit-folder name itself: malformed, reserved,
    already present on disk, or already resolving as a wikilink target. The
    last case matters because the moment this unit's `index.md` exists, a
    name that already maps to another file would map to two paths, turning
    every existing `[[name]]` wikilink into an ambiguous_wikilink."""
    if "/" in name or "\\" in name or name.startswith("."):
        return [f"invalid unit name: {name}"]
    if name in RESERVED_NAMES:
        return [f"reserved name: {name}"]
    if (vault_root / name).exists():
        return [f"target exists: {name}"]
    if name in resolve:
        return [f"already resolves: {name} -> " + ", ".join(sorted(resolve[name]))]
    return []


def _resolve_one(vault_root, arg, resolve):
    """Resolve one artifact argument to a file under the vault.

    Accepts a vault-relative path (a folder artifact may be named by its
    folder or its `index.md`) or any name in the resolution map. Returns
    `(path, error)` with exactly one side set.
    """
    norm = arg.replace("\\", "/").strip("/")
    direct = vault_root / norm
    if direct.is_file():
        return direct, None
    if direct.is_dir() and (direct / "index.md").is_file():
        return direct / "index.md", None
    name = norm[:-3] if norm.endswith(".md") else norm
    paths = resolve.get(name, [])
    if len(paths) > 1:
        return None, f"ambiguous: {arg} -> " + ", ".join(sorted(paths))
    if not paths:
        return None, f"not found: {arg}"
    return vault_root / paths[0], None


def _plan_moves(vault_root, name, artifacts, resolve):
    """Resolve every artifact argument into a move.

    Each move records the source node (the file, or the owning folder for a
    folder artifact), its destination inside the unit, the post-move
    path-qualified wikilink, the vault-relative markdown files the move
    carries, and the artifact's parsed frontmatter. Returns
    `(moves, problems)`; any problem means the whole operation is refused.
    """
    type_dirs = set(vaultlib.classify_root_dirs(vault_root)["type_dirs"])
    moves, problems, seen = [], [], set()
    for arg in artifacts:
        path, error = _resolve_one(vault_root, arg, resolve)
        if error:
            problems.append(error)
            continue
        parts = path.relative_to(vault_root).parts
        if len(parts) < 2 or parts[0] not in type_dirs:
            problems.append(f"not in a root type directory: {arg}")
            continue
        if path.name == "index.md":
            if len(parts) == 2:
                problems.append(f"not an artifact (type-dir index): {arg}")
                continue
            src = path.parent
            link = f"{name}/" + "/".join(parts[:-1])
        else:
            src = path
            link = f"{name}/" + "/".join(parts[:-1] + (path.stem,))
        if src in seen:
            problems.append(f"duplicate artifact: {arg}")
            continue
        seen.add(src)
        files = sorted(src.rglob("*.md")) if src.is_dir() else [src]
        data, _ = vaultlib.parse_frontmatter(path)
        moves.append({
            "src": src,
            "dest": vault_root / name / src.relative_to(vault_root),
            "link": link,
            "files": [f.relative_to(vault_root).as_posix() for f in files],
            "data": data,
        })

    dir_srcs = [m["src"] for m in moves if m["src"].is_dir()]
    for move in moves:
        for folder in dir_srcs:
            if move["src"] != folder and folder in move["src"].parents:
                problems.append(
                    "overlapping artifacts: "
                    f"{move['src'].relative_to(vault_root).as_posix()} is inside "
                    f"{folder.relative_to(vault_root).as_posix()}"
                )
    return moves, problems


def _unit_index_text(name, moves, today):
    """The unit's `index.md`: the `type: unit` marker frontmatter plus a
    one-line-per-member children listing with path-qualified wikilinks."""
    lines = [
        "---",
        f"title: {name}",
        "type: unit",
        "status: active",
        f"created: {today}",
        f"updated: {today}",
        "---",
        "",
        f"# {name}",
        "",
        "## Children",
        "",
    ]
    for move in sorted(moves, key=lambda m: m["link"]):
        data = move["data"]
        summary = data.get("summary") or data.get("title") or move["link"].rsplit("/", 1)[-1]
        lines.append(f"- [[{move['link']}]] - {summary}")
    lines.append("")
    return "\n".join(lines)


def _removable_lines(index_text, resolve, moved_files):
    """Indices of root-index lines whose wikilinks all point into the moved
    set, resolved through the pre-move name map. A line that also references
    an unmoved file is kept; fenced code lines are never touched."""
    moved = set(moved_files)
    removable, in_fence = [], False
    for i, line in enumerate(index_text.split("\n")):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        targets = [
            raw.split("#")[0].split("|")[0].strip()
            for raw in WIKILINK.findall(line)
        ]
        resolved = [p for target in targets for p in resolve.get(target, [])]
        if resolved and all(p in moved for p in resolved):
            removable.append(i)
    return removable


def run(args):
    apply = "--apply" in args
    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        sys.stderr.write("usage: compass make-unit <name> [artifact...] [--apply]\n")
        return 1
    name, artifacts = positional[0], positional[1:]
    vault_root = vaultlib.find_vault_root()
    resolve = vaultlib.resolvable_names_map(vault_root)

    problems = _check_target(vault_root, name, resolve)
    moves, move_problems = _plan_moves(vault_root, name, artifacts, resolve)
    problems += move_problems
    if problems:
        sys.stderr.write("compass make-unit: refused, no changes made\n")
        for problem in problems:
            sys.stderr.write(f"  {problem}\n")
        return 1

    if not artifacts:
        unit_dir = vault_root / name
        if not apply:
            sys.stdout.write(
                f"compass make-unit: would create unit '{name}' at "
                f"{name}/index.md with no artifacts "
                "(dry-run; pass --apply to write)\n"
            )
            return 0
        unit_dir.mkdir(parents=True)
        today = datetime.date.today().isoformat()
        vaultlib.write_text_lf(
            unit_dir / "index.md", _unit_index_text(name, [], today)
        )
        sys.stdout.write(
            f"compass make-unit: created unit '{name}' at {name}/index.md "
            "with no artifacts\n"
        )
        errors, warnings = validate_command.check_vault(vault_root)
        if not errors and not warnings:
            sys.stdout.write("  validate: clean\n")
        else:
            sys.stdout.write(
                f"  validate: {len(errors)} error(s), {len(warnings)} warning(s)\n"
            )
            for finding in errors:
                sys.stdout.write(f"    ERROR   {finding}\n")
            for finding in warnings:
                sys.stdout.write(f"    warning {finding}\n")
        return 0

    moved_files = [f for move in moves for f in move["files"]]
    index_path = vault_root / "index.md"
    index_text = index_path.read_text(encoding="utf-8") if index_path.is_file() else ""
    removable = _removable_lines(index_text, resolve, moved_files)
    move_lines = [
        f"  {m['src'].relative_to(vault_root).as_posix()}"
        f" -> {m['dest'].relative_to(vault_root).as_posix()}"
        for m in moves
    ]

    if not apply:
        sys.stdout.write(
            f"compass make-unit: would create unit '{name}' with {len(moves)} "
            "artifact(s) (dry-run; pass --apply to write)\n"
        )
        for line in move_lines:
            sys.stdout.write(line + "\n")
        sys.stdout.write(f"  index.md: would remove {len(removable)} entry line(s)\n")
        return 0

    for move in moves:
        move["dest"].parent.mkdir(parents=True, exist_ok=True)
        if not git_mv(vault_root.parent, move["src"], move["dest"]):
            move["src"].rename(move["dest"])
    today = datetime.date.today().isoformat()
    vaultlib.write_text_lf(
        vault_root / name / "index.md", _unit_index_text(name, moves, today)
    )
    if removable and index_text:
        drop = set(removable)
        lines = index_text.split("\n")
        kept = [line for i, line in enumerate(lines) if i not in drop]
        vaultlib.write_text_lf(index_path, "\n".join(kept))
    if index_path.is_file():
        sync_command.sync(vault_root)

    sys.stdout.write(
        f"compass make-unit: created unit '{name}' with {len(moves)} artifact(s)\n"
    )
    for line in move_lines:
        sys.stdout.write(line + "\n")
    sys.stdout.write(f"  index.md: removed {len(removable)} entry line(s)\n")
    errors, warnings = validate_command.check_vault(vault_root)
    if not errors and not warnings:
        sys.stdout.write("  validate: clean\n")
    else:
        sys.stdout.write(
            f"  validate: {len(errors)} error(s), {len(warnings)} warning(s)\n"
        )
        for finding in errors:
            sys.stdout.write(f"    ERROR   {finding}\n")
        for finding in warnings:
            sys.stdout.write(f"    warning {finding}\n")
    return 0
