"""`compass move <artifact>... <dest-folder>` - link-preserving move.

Moves artifacts into a domain folder (or back to a type-dir root) with
`git mv`, then rewrites every inbound path-qualified wikilink vault-wide.
Bare-stem links keep resolving on their own, since filenames never change;
path-qualified links carry the path as identity, so a domain move without
the rewrite silently breaks each one. Mentions quoted in inline code or
fenced blocks are documentation, never rewritten. Dry-run by default;
`--apply` executes, then heals the root index: each moved artifact's
entry-line description lifts into its missing `summary:`, sync prunes the
lines now provably covered by the destination's folder pointer, and any
line whose description conflicts with the artifact's own fields is kept
and reported. Vault health is reported last.

The destination must already exist inside the same type dir as each
artifact: the type dir itself, or a domain folder (its own `index.md`
present) at any depth, at the vault root or inside a unit. The whole
operation is refused - exit 1, zero changes - on a missing or non-domain
destination, a name collision at the destination, an ambiguous or
unresolvable artifact, a cross-type-dir move, a folder moved into its own
subtree, or an artifact already sitting in the destination.
"""

import re
import sys

import vaultlib
from commands import sync as sync_command
from commands.make_unit import _report_vault_health, _resolve_one
from commands.promote import git_mv

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
INLINE_CODE_SPLIT = re.compile(r"(`[^`\n]*`)")


def _type_root(vault_root, parts, layout):
    """Number of leading segments of `parts` that form its type-dir root:
    1 for a root type dir, 2 for a type dir inside a unit, 0 when the path
    is not under a type dir at all."""
    if parts and parts[0] in layout["type_dirs"]:
        return 1
    if len(parts) >= 2 and parts[0] in layout["units"]:
        unit_layout = vaultlib.classify_root_dirs(vault_root / parts[0])
        if parts[1] in unit_layout["type_dirs"]:
            return 2
    return 0


def _check_dest(vault_root, dest_rel, layout):
    """Return (dest_path, type_dir_name, error) with the error side set
    exactly when the destination cannot receive artifacts."""
    parts = dest_rel.split("/")
    root_segments = _type_root(vault_root, parts, layout)
    if root_segments == 0:
        return None, None, f"destination {dest_rel} is not under a type dir"
    dest = vault_root / dest_rel
    if not dest.is_dir():
        return None, None, f"destination {dest_rel} does not exist"
    if len(parts) > root_segments and not (dest / "index.md").is_file():
        return None, None, (
            f"destination {dest_rel} has no index.md - not a domain "
            "(compass make-domain creates one)"
        )
    return dest, parts[root_segments - 1], None


def _plan_moves(vault_root, artifact_args, dest, dest_type, layout, resolve):
    """Resolve every artifact argument into a `(node, dest_node)` move.
    Returns (moves, problems); any problem refuses the whole operation."""
    moves, problems, seen = [], [], set()
    for arg in artifact_args:
        path, error = _resolve_one(vault_root, arg, resolve)
        if error:
            problems.append(error)
            continue
        node = path.parent if path.name == "index.md" else path
        parts = node.relative_to(vault_root).parts
        root_segments = _type_root(vault_root, parts, layout)
        if root_segments == 0 or len(parts) <= root_segments:
            problems.append(f"not an artifact under a type dir: {arg}")
            continue
        if parts[root_segments - 1] != dest_type:
            problems.append(
                f"type dir mismatch: {arg} is in {parts[root_segments - 1]}, "
                f"destination is in {dest_type}"
            )
            continue
        if node == dest or node in dest.parents:
            problems.append(f"cannot move {arg} into its own subtree")
            continue
        if node.parent == dest:
            problems.append(f"already in destination: {arg}")
            continue
        dest_node = dest / node.name
        if dest_node.exists():
            problems.append(
                f"target exists: {dest_node.relative_to(vault_root).as_posix()}"
            )
            continue
        if node in seen:
            problems.append(f"duplicate artifact: {arg}")
            continue
        seen.add(node)
        moves.append((node, dest_node))
    return moves, problems


def _renames_for(vault_root, moves):
    """Old link target -> new link target for every markdown file the moves
    carry: its path-qualified name, plus the folder path for an index.md."""
    renames = {}
    for node, dest_node in moves:
        files = sorted(node.rglob("*.md")) if node.is_dir() else [node]
        for f in files:
            old_rel = f.relative_to(vault_root).as_posix()
            if node.is_dir():
                new_rel = (dest_node / f.relative_to(node)).relative_to(
                    vault_root).as_posix()
            else:
                new_rel = dest_node.relative_to(vault_root).as_posix()
            renames[old_rel[:-3]] = new_rel[:-3]
            if f.name == "index.md":
                renames[old_rel.rsplit("/", 1)[0]] = new_rel.rsplit("/", 1)[0]
    return renames


def _rewrite_links(text, renames):
    """Rewrite renamed wikilink targets in `text`, preserving `#heading` and
    `|alias` suffixes and leaving fenced blocks and inline code spans
    untouched. Returns (new_text, links_rewritten)."""
    changed = 0

    def repl(match):
        nonlocal changed
        raw = match.group(1)
        split_at = next((i for i, c in enumerate(raw) if c in "#|"), len(raw))
        new = renames.get(raw[:split_at].strip())
        if new is None:
            return match.group(0)
        changed += 1
        return f"[[{new}{raw[split_at:]}]]"

    out = []
    in_fence = False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        parts = INLINE_CODE_SPLIT.split(line)
        for i, part in enumerate(parts):
            if not part.startswith("`"):
                parts[i] = WIKILINK.sub(repl, part)
        out.append("".join(parts))
    return "\n".join(out), changed


def _lift_summary(path, desc):
    """Copy `desc` into the artifact's missing `summary:`. False when the
    frontmatter cannot take it or already carries one - an existing summary
    is never overwritten."""
    text = vaultlib.read_vault_text(path)
    data, error = vaultlib.parse_frontmatter_text(text)
    if error or data.get("summary"):
        return False
    lines = text.split("\n")
    closing = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if closing is None:
        return False
    lines.insert(closing, f"summary: {vaultlib.yaml_double_quote(desc)}")
    vaultlib.write_text_lf(path, "\n".join(lines))
    return True


def _index_descriptions_of(vault_root, moved_rel):
    """(path, description) for each root-index entry line whose subject
    link resolves to a moved file. Fenced lines are skipped."""
    index_path = vault_root / "index.md"
    if not index_path.is_file():
        return []
    resolve = vaultlib.resolvable_names_map(vault_root)
    found = []
    in_fence = False
    for line in index_path.read_text(encoding="utf-8").split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        entry = sync_command.ENTRY_PATTERN.match(line)
        raws = WIKILINK.findall(line)
        if not entry or not raws:
            continue
        split_at = next((i for i, c in enumerate(raws[0]) if c in "#|"), len(raws[0]))
        paths = vaultlib.resolve_link(resolve, raws[0][:split_at].strip())
        if len(paths) == 1 and paths[0] in moved_rel:
            found.append((paths[0], entry.group("desc")))
    return found


def _heal_index(vault_root, moves):
    """The moved artifacts' index residue: lift each entry line's
    description into its artifact's missing `summary:` (so sync's
    covered-line prune can prove the text survives), run sync, and count
    the lines whose description still conflicts with the artifact's own
    fields. Returns (lifted, pruned, kept)."""
    moved_rel = set()
    for _, dest_node in moves:
        files = sorted(dest_node.rglob("*.md")) if dest_node.is_dir() else [dest_node]
        moved_rel.update(f.relative_to(vault_root).as_posix() for f in files)
    lifted = 0
    for rel, desc in _index_descriptions_of(vault_root, moved_rel):
        if desc and _lift_summary(vault_root / rel, desc):
            lifted += 1
    # sync's tag-index write assumes meta/ already exists; ensure it here so
    # a vault that has never had a shape-changing command run against it
    # does not crash on the very first one.
    (vault_root / "meta").mkdir(exist_ok=True)
    pruned = 0
    if (vault_root / "index.md").is_file():
        pruned = sync_command.sync(vault_root).get("index_pruned", 0)
    kept = 0
    for rel, desc in _index_descriptions_of(vault_root, moved_rel):
        data, error = vaultlib.parse_frontmatter(vault_root / rel)
        if not error and desc is not None and desc not in (
            data.get("summary"), data.get("title")
        ):
            kept += 1
    return lifted, pruned, kept


def _sweep_rewrites(vault_root, renames, apply):
    """Apply (or count, when `apply` is false) the link rewrites across
    every markdown file in the vault. Returns (links, files_touched)."""
    links = files = 0
    for path in vaultlib.all_markdown_files(vault_root):
        text = vaultlib.read_vault_text(path)
        new_text, changed = _rewrite_links(text, renames)
        if changed:
            links += changed
            files += 1
            if apply:
                vaultlib.write_text_lf(path, new_text)
    return links, files


def run(args):
    apply = "--apply" in args
    positional = [a for a in args if not a.startswith("--")]
    if len(positional) < 2:
        sys.stderr.write(
            "usage: compass move <artifact>... <dest-folder> [--apply]\n"
        )
        return 1
    *artifact_args, dest_rel = positional
    dest_rel = dest_rel.replace("\\", "/").strip("/")
    vault_root = vaultlib.find_vault_root()
    layout = vaultlib.classify_root_dirs(vault_root)
    resolve = vaultlib.resolvable_names_map(vault_root)

    dest, dest_type, problem = _check_dest(vault_root, dest_rel, layout)
    if problem:
        moves, problems = [], [problem]
    else:
        moves, problems = _plan_moves(
            vault_root, artifact_args, dest, dest_type, layout, resolve
        )
    if problems:
        sys.stderr.write("compass move: refused, no changes made\n")
        for entry in problems:
            sys.stderr.write(f"  {entry}\n")
        return 1

    renames = _renames_for(vault_root, moves)
    move_lines = [
        f"  {node.relative_to(vault_root).as_posix()}"
        f" -> {dest_node.relative_to(vault_root).as_posix()}"
        for node, dest_node in moves
    ]

    if not apply:
        links, files = _sweep_rewrites(vault_root, renames, apply=False)
        sys.stdout.write(
            f"compass move: would move {len(moves)} artifact(s) into {dest_rel} "
            "(dry-run; pass --apply to write)\n"
        )
        for line in move_lines:
            sys.stdout.write(line + "\n")
        sys.stdout.write(
            f"  wikilinks to rewrite: {links} across {files} file(s)\n"
        )
        return 0

    for node, dest_node in moves:
        if not git_mv(vault_root.parent, node, dest_node):
            node.rename(dest_node)
    links, files = _sweep_rewrites(vault_root, renames, apply=True)

    sys.stdout.write(
        f"compass move: moved {len(moves)} artifact(s) into {dest_rel}\n"
    )
    for line in move_lines:
        sys.stdout.write(line + "\n")
    sys.stdout.write(
        f"  wikilinks rewritten: {links} across {files} file(s)\n"
    )
    lifted, pruned, kept = _heal_index(vault_root, moves)
    if lifted:
        sys.stdout.write(
            f"  summaries lifted from index descriptions: {lifted}\n"
        )
    sys.stdout.write(f"  index.md: {pruned} entry line(s) pruned\n")
    if kept:
        sys.stdout.write(
            f"  index.md: {kept} line(s) kept - description differs from "
            "the artifact's own summary\n"
        )
    _report_vault_health(vault_root)
    return 0
