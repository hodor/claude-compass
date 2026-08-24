"""`compass make-unit <name> [artifact...]` - create a unit folder, optionally
moving artifacts into it. `compass make-unit --undo <name>` reverses it.

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

`--undo <name>` is the inverse: every artifact under the unit's own type
directories moves back to the matching root type directory it came from, and
the unit folder - marker included - is removed. It refuses all-or-nothing,
zero changes, when any restored artifact would collide with an existing file
at the root, naming the colliding path, and when the unit folder holds
anything besides its own `index.md` and recognized type directories - never
inferring that unclassified content is safe to discard along with the folder
(LESSON-installer-removes-only-what-it-installed - act only on the named
artifacts, never assume the rest of the folder is clear to remove). Dry-run
by default, `--apply` executes, then regenerates derived state and reports
vault health the same way the forward direction does.

Every `--apply` that creates or removes a unit is a sizing decision and
requires `--reason <text>`; `--volatile <text>` (repeatable) and `--by
human|agent` are optional. A create mints a `sizing_id` and stamps it into
the new unit's own `index.md`; `--undo` writes a correction row carrying
the SAME id the unit's `index.md` already carried, joining the two rows for
`compass sizing stats` (see `commands/sizing.py`). Dry-run never requires
`--reason` - nothing is recorded because nothing changed.
"""

import datetime
import re
import shutil
import sys

import vaultlib
from commands import sizing
from commands import sync as sync_command
from commands import validate as validate_command
from commands.promote import git_mv

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")

RESERVED_NAMES = set(vaultlib.CORE_TYPE_DIRS) | vaultlib.NON_TYPE_DIRS


def _report_vault_health(vault_root):
    """Print the vault's validate findings under a created unit.

    Every path that creates a unit reports through here, so the report a
    human sees does not depend on which path created it."""
    errors, warnings = validate_command.check_vault(vault_root)
    if not errors and not warnings:
        sys.stdout.write("  validate: clean\n")
        return
    sys.stdout.write(f"  validate: {len(errors)} error(s), {len(warnings)} warning(s)\n")
    for finding in errors:
        sys.stdout.write(f"    ERROR   {finding}\n")
    for finding in warnings:
        sys.stdout.write(f"    warning {finding}\n")


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


def _plan_undo_moves(vault_root, unit_dir, type_dirs):
    """Every artifact currently under one of the unit's own type directories,
    paired with the root type-dir path it moved from. Mirrors the forward
    direction's `<name>/<type_dir>/<rel>` layout in reverse.

    The move unit is each top-level entry of `<unit>/<type_dir>/` - a file or
    a whole subdirectory. An artifact that was moved in as a single file
    nested inside a subdirectory (a loose nested doc, see
    `vaultlib.is_loose_nested`) restores its whole containing subdirectory,
    which only round-trips cleanly when nothing else was left behind at the
    root under that same subdirectory name."""
    moves = []
    for type_dir in type_dirs:
        base = unit_dir / type_dir
        for child in sorted(base.iterdir()):
            moves.append({"src": child, "dest": vault_root / type_dir / child.name})
    return moves


def _run_undo(vault_root, positional, apply, reason, volatile, by):
    if not positional:
        sys.stderr.write("usage: compass make-unit --undo <unit> [--reason <text>] [--apply]\n")
        return 1
    if apply and reason is None:
        sys.stderr.write(
            "compass make-unit --undo: --reason is required on --apply, no changes made\n"
        )
        return 1
    name = positional[0]
    units = vaultlib.classify_root_dirs(vault_root)["units"]
    if name not in units:
        sys.stderr.write(f"compass make-unit --undo: not a unit: {name}\n")
        return 1

    unit_dir = vault_root / name
    type_dirs = vaultlib.classify_root_dirs(unit_dir)["type_dirs"]
    unexpected = sorted(
        p.name for p in unit_dir.iterdir()
        if p.name != "index.md" and p.name not in type_dirs
    )
    if unexpected:
        sys.stderr.write(
            "compass make-unit --undo: refused, no changes made\n"
            f"  unexpected content in '{name}', not a recognized type "
            f"directory: {', '.join(unexpected)}\n"
        )
        return 1

    moves = _plan_undo_moves(vault_root, unit_dir, type_dirs)
    collisions = [m for m in moves if m["dest"].exists()]
    if collisions:
        sys.stderr.write("compass make-unit --undo: refused, no changes made\n")
        for move in collisions:
            sys.stderr.write(
                f"  target exists: {move['dest'].relative_to(vault_root).as_posix()}\n"
            )
        return 1

    if not apply:
        sys.stdout.write(
            f"compass make-unit: would restore {len(moves)} artifact(s) from "
            f"'{name}' and remove the unit folder (dry-run; pass --apply to write)\n"
        )
        for move in moves:
            sys.stdout.write(
                f"  {move['src'].relative_to(vault_root).as_posix()}"
                f" -> {move['dest'].relative_to(vault_root).as_posix()}\n"
            )
        return 0

    # The unit's own sizing_id, read before the folder is removed - the
    # correction row must carry the SAME id as the decision it reverses
    # (ADR-011 D-08), not a freshly minted one. A unit that predates the
    # sizing log (no id ever stamped) falls back to a fresh id: there is no
    # earlier decision row to join against.
    original_id = None
    unit_index = unit_dir / "index.md"
    if unit_index.is_file():
        data, frontmatter_error = vaultlib.parse_frontmatter(unit_index)
        if frontmatter_error is None:
            original_id = data.get("sizing_id")

    for move in moves:
        move["dest"].parent.mkdir(parents=True, exist_ok=True)
        if not git_mv(vault_root.parent, move["src"], move["dest"]):
            move["src"].rename(move["dest"])
    shutil.rmtree(unit_dir)

    correction_id = original_id or sizing.mint_id(vault_root)
    sizing.append_row(vault_root, {
        "id": correction_id,
        "action": "correction",
        "shape": "unit",
        "subject": name,
        "reason": reason,
        "volatile": volatile,
        "by": by,
        "at": datetime.date.today().isoformat(),
    })

    sys.stdout.write(
        f"compass make-unit: restored {len(moves)} artifact(s) from '{name}' "
        "and removed the unit folder\n"
    )
    # sync's tag-index write assumes meta/ already exists; ensure it here so
    # a vault that has never had a shape-changing command run against it
    # does not crash on the very first one.
    (vault_root / "meta").mkdir(exist_ok=True)
    if (vault_root / "index.md").is_file():
        sync_command.sync(vault_root)
    _report_vault_health(vault_root)
    return 0


def run(args):
    remaining, reason, volatile, by, flag_error = sizing.parse_flags(args)
    if flag_error:
        sys.stderr.write(f"compass make-unit: {flag_error}\n")
        return 1
    apply = "--apply" in remaining
    positional = [a for a in remaining if not a.startswith("--")]
    if "--undo" in remaining:
        return _run_undo(vaultlib.find_vault_root(), positional, apply, reason, volatile, by)
    if not positional:
        sys.stderr.write("usage: compass make-unit <name> [artifact...] [--reason <text>] [--apply]\n")
        return 1
    if apply and reason is None:
        sys.stderr.write(
            "compass make-unit: --reason is required on --apply, no changes made\n"
        )
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
        sizing_id = sizing.mint_id(vault_root)
        sizing.stamp_id(unit_dir / "index.md", sizing_id)
        sizing.append_row(vault_root, {
            "id": sizing_id,
            "action": "decision",
            "shape": "unit",
            "subject": name,
            "reason": reason,
            "volatile": volatile,
            "by": by,
            "at": today,
        })
        sys.stdout.write(
            f"compass make-unit: created unit '{name}' at {name}/index.md "
            "with no artifacts\n"
        )
        _report_vault_health(vault_root)
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
    unit_index_path = vault_root / name / "index.md"
    vaultlib.write_text_lf(unit_index_path, _unit_index_text(name, moves, today))
    sizing_id = sizing.mint_id(vault_root)
    sizing.stamp_id(unit_index_path, sizing_id)
    sizing.append_row(vault_root, {
        "id": sizing_id,
        "action": "decision",
        "shape": "unit",
        "subject": name,
        "reason": reason,
        "volatile": volatile,
        "by": by,
        "at": today,
    })
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
    _report_vault_health(vault_root)
    return 0
