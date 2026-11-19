"""`compass make-domain <type-dir>/<path>` - create a domain folder.

A domain is a topic folder inside a type dir (`specs/network`, at any
depth), holding the artifacts that share its subject. The type dir may
itself sit inside a unit (`<unit>/specs/analytics`); unit-internal domain
members scan and link like root ones. Its `index.md`
carries identity and a `## Scope` section only - the folder itself is the
listing. Creation demands the scope's first `Class here:` line up front
(`--class-here`), because a domain born without one greets every future
filer with a blank at the exact point of doubt.

Names are unique among siblings and may recur on other branches
(`specs/network/cache` and `specs/gpu-hardware/cache`); the path is the
identity. A parent must already exist - domains grow from real corpus, one
level at a time. Dry-run by default; `--apply` writes, requires `--reason`,
and records the decision in the sizing log with the id stamped into the
domain's own frontmatter. `--title "<text>"` sets the created index's
title; the folder name stays the path's last segment and seeds the tag.

`--undo <path>` removes a domain that holds nothing but its own index.md and
logs the correction under the same id. The index.md, whose Scope text is the
domain's only record of what belonged in it, moves to
`archive/domains/<path>/index.md` first (`<path>-2`, `-3`, ... when that
folder is taken), so no scope text is lost.

`--rename <old> <new>` renames a domain folder within its own parent: the
folder moves (`git mv` when tracked), path-qualified wikilinks to it and to
everything under it are rewritten vault-wide, and the index's `title` and
first tag become the new name. Everything outside those frontmatter lines,
the Scope text included, is written back byte for byte. Refused with zero
changes: a missing source, an existing target, a target in another type dir
or not a sibling of the source, and a name that is not a valid folder name.
The sizing log records the rename under the domain's `sizing_id`.
"""

import datetime
import re
import shutil
import sys

import vaultlib
from commands import move, sizing
from commands.promote import git_mv

FOLDER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
FIRST_INLINE_TAG = re.compile(
    r"""^(tags:\s*\[\s*)("(?:[^"\\]|\\.)*"|'[^']*'|[^,\]]*)"""
)
BLOCK_TAG_ITEM = re.compile(r"^(\s*-\s+).*$")


def _take_value_flag(args, flag):
    """Remove `flag <value>` from args; return (remaining, value, error)."""
    remaining = []
    value = None
    error = None
    i = 0
    while i < len(args):
        if args[i] == flag:
            if i + 1 >= len(args):
                error = f"{flag} requires a value"
                i += 1
                continue
            value = args[i + 1]
            i += 2
            continue
        remaining.append(args[i])
        i += 1
    if value is not None and not value.strip():
        error = f"{flag} must not be blank"
    return remaining, value, error


def _template(name, class_here, today, title=None):
    # The folder name is the domain's own topic and seeds its tag list, so
    # a freshly generated index never draws validate's missing-tags warning.
    title = name if title is None else title
    return (
        "---\n"
        f"title: {vaultlib.yaml_double_quote(title)}\n"
        "type: domain\n"
        "status: active\n"
        f"tags: [{name}]\n"
        f"summary: {vaultlib.yaml_double_quote(class_here)}\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        "---\n"
        "\n"
        f"# {title}\n"
        "\n"
        "## Scope\n"
        "\n"
        f"Class here: {class_here}\n"
    )


def _archive_index_path(vault_root, rel):
    """`archive/domains/<rel>/index.md`, the folder taking a `-2`, `-3`, ...
    suffix while an earlier archived domain already holds the name."""
    base = vault_root / "archive" / "domains" / rel
    candidate = base
    n = 2
    while candidate.exists():
        candidate = base.with_name(f"{base.name}-{n}")
        n += 1
    return candidate / "index.md"


def _run_undo(vault_root, positional, apply, reason, volatile, by):
    if not positional:
        sys.stderr.write("usage: compass make-domain --undo <type-dir>/<path> [--apply]\n")
        return 1
    rel = positional[0].strip("/")
    target = vault_root / rel
    index = target / "index.md"
    if not index.is_file():
        sys.stderr.write(f"compass make-domain: no domain at {rel}\n")
        return 1
    members = [p for p in target.iterdir() if p != index]
    if members:
        sys.stderr.write(
            f"compass make-domain: refused, {rel} holds {len(members)} member(s); "
            "move them out first\n"
        )
        return 1
    archived = _archive_index_path(vault_root, rel)
    archived_rel = archived.relative_to(vault_root).as_posix()
    if not apply:
        sys.stdout.write(
            f"compass make-domain: would archive the scope text to {archived_rel} "
            f"and remove empty domain {rel} (dry-run; pass --apply to write)\n"
        )
        return 0
    if reason is None:
        sys.stderr.write("compass make-domain: --reason is required on --apply, no changes made\n")
        return 1
    data, _ = vaultlib.parse_frontmatter(index)
    sizing_id = data.get("sizing_id") or sizing.mint_id(vault_root)
    archived.parent.mkdir(parents=True)
    if not git_mv(vault_root.parent, index, archived):
        shutil.move(str(index), str(archived))
    target.rmdir()
    sizing.append_row(vault_root, {
        "id": sizing_id, "action": "correction", "shape": "domain",
        "subject": rel, "reason": reason, "by": by,
        "at": datetime.date.today().isoformat(), "volatile": volatile,
    })
    sys.stdout.write(
        f"compass make-domain: removed {rel}; scope text kept at {archived_rel}\n"
    )
    return 0


def _eol(line):
    return "\r" if line.endswith("\r") else ""


def _unquote_scalar(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _retarget_index(raw, old_name, new_name, sizing_id, today):
    """The index.md bytes `raw` with its frontmatter `title` and first tag
    set to `new_name`, `updated` set to `today` and `sizing_id` present, and
    a first body heading that repeated the old title or folder name renamed.
    Every other byte, line endings and the Scope text included, is kept.
    Returns None when `raw` has no frontmatter or is not UTF-8."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    lines = text.split("\n")
    if lines[0].lstrip("﻿").rstrip("\r") != "---":
        return None
    close = next(
        (i for i in range(1, len(lines)) if lines[i].rstrip("\r").strip() == "---"),
        None,
    )
    if close is None:
        return None

    old_title = old_name
    seen = {"title": False, "tags": False, "sizing_id": False}
    in_block_tags = False
    for i in range(1, close):
        line, eol = lines[i].rstrip("\r"), _eol(lines[i])
        if line.startswith("title:"):
            old_title = _unquote_scalar(line[len("title:"):])
            lines[i] = f"title: {vaultlib.yaml_double_quote(new_name)}{eol}"
            seen["title"] = True
        elif line.startswith("tags:"):
            seen["tags"] = True
            if FIRST_INLINE_TAG.match(line):
                lines[i] = FIRST_INLINE_TAG.sub(
                    lambda m: m.group(1) + new_name, line, count=1) + eol
            elif not line[len("tags:"):].strip():
                in_block_tags = True
        elif in_block_tags and BLOCK_TAG_ITEM.match(line):
            lines[i] = BLOCK_TAG_ITEM.sub(
                lambda m: m.group(1) + new_name, line) + eol
            in_block_tags = False
        elif line.startswith("updated:"):
            lines[i] = f"updated: {today}{eol}"
        elif line.startswith("sizing_id:"):
            seen["sizing_id"] = True
    eol = _eol(lines[close])
    for key, value in (
        ("title", vaultlib.yaml_double_quote(new_name)),
        ("tags", f"[{new_name}]"),
        ("sizing_id", sizing_id),
    ):
        if not seen[key]:
            lines.insert(close, f"{key}: {value}{eol}")
            close += 1

    for i in range(close + 1, len(lines)):
        line = lines[i].rstrip("\r")
        if line.startswith("## "):
            break
        if line.startswith("# ") and line[2:].strip() in (old_name, old_title):
            lines[i] = f"# {new_name}{_eol(lines[i])}"
            break
    return "\n".join(lines).encode("utf-8")


def _sweep_links(vault_root, renames, apply):
    """Rewrite (or, when `apply` is false, count) the path-qualified links
    named in `renames` across every markdown file, writing each file back
    byte for byte apart from the rewritten links. Returns (links, files)."""
    links = files = 0
    for path in vaultlib.all_markdown_files(vault_root):
        try:
            text = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        new_text, changed = move._rewrite_links(text, renames)
        if changed:
            links += changed
            files += 1
            if apply:
                path.write_bytes(new_text.encode("utf-8"))
    return links, files


def _rename_problem(vault_root, old_rel, new_rel):
    """The reason `old_rel` cannot be renamed to `new_rel`, or None."""
    layout = vaultlib.classify_root_dirs(vault_root)
    old_parts, new_parts = old_rel.split("/"), new_rel.split("/")
    old_root = move._type_root(vault_root, old_parts, layout)
    if old_root == 0 or len(old_parts) <= old_root:
        return f"{old_rel} is not a domain folder inside a type dir"
    if not (vault_root / old_rel / "index.md").is_file():
        return f"no domain at {old_rel}"
    new_root = move._type_root(vault_root, new_parts, layout)
    if new_root == 0 or len(new_parts) <= new_root:
        return f"{new_rel} is not a folder inside a type dir"
    if new_parts[:old_root] != old_parts[:old_root]:
        return f"{new_rel} is in another type dir than {old_rel}"
    if new_parts[:-1] != old_parts[:-1]:
        return f"{new_rel} is not a sibling of {old_rel}; rename keeps the parent folder"
    if not FOLDER_NAME.match(new_parts[-1]):
        return (
            f"invalid folder name {new_parts[-1]!r}: letters, digits, "
            "'-' and '_' only, starting with a letter or digit"
        )
    new_path = vault_root / new_rel
    if new_path.exists() or new_path.with_suffix(".md").exists():
        return f"{new_rel} already exists"
    return None


def _run_rename(vault_root, positional, apply, reason, volatile, by):
    if len(positional) != 2:
        sys.stderr.write(
            "usage: compass make-domain --rename <old-path> <new-path> "
            "[--reason <text>] [--apply]\n"
        )
        return 1
    old_rel, new_rel = (p.replace("\\", "/").strip("/") for p in positional)
    problem = _rename_problem(vault_root, old_rel, new_rel)
    if problem:
        sys.stderr.write(f"compass make-domain: refused, {problem}\n")
        return 1
    old_name, new_name = old_rel.split("/")[-1], new_rel.split("/")[-1]
    old_path, new_path = vault_root / old_rel, vault_root / new_rel
    index = old_path / "index.md"
    data, _ = vaultlib.parse_frontmatter(index)
    sizing_id = data.get("sizing_id") or sizing.mint_id(vault_root)
    today = datetime.date.today().isoformat()
    retargeted = _retarget_index(index.read_bytes(), old_name, new_name, sizing_id, today)
    if retargeted is None:
        sys.stderr.write(
            f"compass make-domain: refused, {old_rel}/index.md has no readable "
            "frontmatter\n"
        )
        return 1

    moves = [(old_path, new_path)]
    renames = move._renames_for(vault_root, moves)
    file_renames = move._file_renames_for(vault_root, moves)
    if not apply:
        links, files = _sweep_links(vault_root, renames, apply=False)
        sys.stdout.write(
            f"compass make-domain: would rename {old_rel} -> {new_rel} "
            "(dry-run; pass --apply to write)\n"
            f"  wikilinks to rewrite: {links} across {files} file(s)\n"
        )
        return 0
    if reason is None:
        sys.stderr.write("compass make-domain: --reason is required on --apply, no changes made\n")
        return 1

    if not git_mv(vault_root.parent, old_path, new_path):
        old_path.rename(new_path)
    (new_path / "index.md").write_bytes(retargeted)
    links, files = _sweep_links(vault_root, renames, apply=True)
    cards = move._sweep_canvas(vault_root, file_renames, apply=True)
    sizing.append_row(vault_root, {
        "id": sizing_id, "action": "rename", "shape": "domain",
        "subject": f"{old_rel} -> {new_rel}", "reason": reason, "by": by,
        "at": today, "volatile": volatile,
    })
    sys.stdout.write(
        f"compass make-domain: renamed {old_rel} -> {new_rel} ({sizing_id})\n"
        f"  wikilinks rewritten: {links} across {files} file(s)\n"
    )
    if cards:
        sys.stdout.write(f"  canvas cards rewritten: {cards}\n")
    return 0


def run(args):
    remaining, reason, volatile, by, flag_error = sizing.parse_flags(args)
    if flag_error:
        sys.stderr.write(f"compass make-domain: {flag_error}\n")
        return 1
    remaining, class_here, ch_error = _take_value_flag(remaining, "--class-here")
    if ch_error:
        sys.stderr.write(f"compass make-domain: {ch_error}\n")
        return 1
    remaining, title, title_error = _take_value_flag(remaining, "--title")
    if title_error:
        sys.stderr.write(f"compass make-domain: {title_error}\n")
        return 1
    if title is not None and ("\n" in title or "\r" in title):
        sys.stderr.write("compass make-domain: --title must be a single line\n")
        return 1
    apply = "--apply" in remaining
    undo = "--undo" in remaining
    rename = "--rename" in remaining
    positional = [a for a in remaining if not a.startswith("--")]
    vault_root = vaultlib.find_vault_root()

    if undo and rename:
        sys.stderr.write("compass make-domain: --undo and --rename cannot be combined\n")
        return 1
    if (undo or rename) and title is not None:
        sys.stderr.write("compass make-domain: --title applies to creating a domain only\n")
        return 1
    if undo:
        return _run_undo(vault_root, positional, apply, reason, volatile, by)
    if rename:
        return _run_rename(vault_root, positional, apply, reason, volatile, by)

    if not positional:
        sys.stderr.write(
            "usage: compass make-domain <[unit/]type-dir/path> --class-here <line> "
            "[--title <text>] [--reason <text>] [--apply]\n"
        )
        return 1
    rel = positional[0].strip("/")
    parts = rel.split("/")
    if len(parts) < 2:
        sys.stderr.write(
            "compass make-domain: target must be <type-dir>/<path> or "
            "<unit>/<type-dir>/<path>\n"
        )
        return 1

    # The path segments that form the domain's type-dir root: one for a root
    # type dir, two for a type dir inside a unit. Everything below the root
    # is domain territory and grows one level at a time.
    layout = vaultlib.classify_root_dirs(vault_root)
    if parts[0] in layout["type_dirs"]:
        root_segments = 1
    elif parts[0] in layout["units"]:
        unit_type_dirs = vaultlib.classify_root_dirs(vault_root / parts[0])["type_dirs"]
        if len(parts) < 3 or parts[1] not in unit_type_dirs:
            sys.stderr.write(
                f"compass make-domain: target inside unit {parts[0]} must be "
                f"{parts[0]}/<type-dir>/<path>\n"
            )
            return 1
        root_segments = 2
    else:
        sys.stderr.write(
            f"compass make-domain: {parts[0]} is not a type dir or unit of this vault\n"
        )
        return 1

    if parts[root_segments - 1] == "loops":
        sys.stderr.write(
            "compass make-domain: refused, loops are never domain-grouped\n"
        )
        return 1

    target = vault_root / rel
    if target.exists() or target.with_suffix(".md").exists():
        sys.stderr.write(f"compass make-domain: {rel} already exists, refused\n")
        return 1
    parent = target.parent
    parent_rel = "/".join(parts[:-1])
    if not parent.is_dir() or (
        len(parts) > root_segments + 1 and not (parent / "index.md").is_file()
    ):
        sys.stderr.write(
            f"compass make-domain: parent {parent_rel} does not exist as a domain; "
            "domains grow one level at a time\n"
        )
        return 1

    if not apply:
        sys.stdout.write(
            f"compass make-domain: would create domain {rel} with its index.md "
            "(dry-run; pass --apply to write)\n"
        )
        return 0
    if reason is None:
        sys.stderr.write("compass make-domain: --reason is required on --apply, no changes made\n")
        return 1
    if class_here is None:
        sys.stderr.write(
            "compass make-domain: --class-here is required on --apply - a domain "
            "is never born with a blank Scope\n"
        )
        return 1

    today = datetime.date.today().isoformat()
    target.mkdir(parents=True)
    index = target / "index.md"
    vaultlib.write_text_lf(index, _template(parts[-1], class_here, today, title))
    sizing_id = sizing.mint_id(vault_root)
    sizing.stamp_id(index, sizing_id)
    sizing.append_row(vault_root, {
        "id": sizing_id, "action": "decision", "shape": "domain",
        "subject": rel, "reason": reason, "by": by, "at": today,
        "volatile": volatile,
    })
    sys.stdout.write(f"compass make-domain: created {rel} ({sizing_id})\n")
    return 0
