"""`compass make-domain <type-dir>/<path>` - create a domain folder.

A domain is a topic folder inside a type dir (`specs/network`, at any
depth), holding the artifacts that share its subject. Its `index.md`
carries identity and a `## Scope` section only - the folder itself is the
listing. Creation demands the scope's first `Class here:` line up front
(`--class-here`), because a domain born without one greets every future
filer with a blank at the exact point of doubt.

Names are unique among siblings and may recur on other branches
(`specs/network/cache` and `specs/gpu-hardware/cache`); the path is the
identity. A parent must already exist - domains grow from real corpus, one
level at a time. Dry-run by default; `--apply` writes, requires `--reason`,
and records the decision in the sizing log with the id stamped into the
domain's own frontmatter. `--undo <path>` removes a domain that holds
nothing but its own index.md and logs the correction under the same id.
"""

import datetime
import shutil
import sys

import vaultlib
from commands import sizing


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


def _template(name, class_here, today):
    return (
        "---\n"
        f'title: "{name}"\n'
        "type: domain\n"
        "status: active\n"
        "tags: []\n"
        f'summary: "{class_here}"\n'
        f"created: {today}\n"
        f"updated: {today}\n"
        "---\n"
        "\n"
        f"# {name}\n"
        "\n"
        "## Scope\n"
        "\n"
        f"Class here: {class_here}\n"
    )


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
    if not apply:
        sys.stdout.write(
            f"compass make-domain: would remove empty domain {rel} "
            "(dry-run; pass --apply to write)\n"
        )
        return 0
    if reason is None:
        sys.stderr.write("compass make-domain: --reason is required on --apply, no changes made\n")
        return 1
    data, _ = vaultlib.parse_frontmatter(index)
    sizing_id = data.get("sizing_id") or sizing.mint_id(vault_root)
    shutil.rmtree(target)
    sizing.append_row(vault_root, {
        "id": sizing_id, "action": "correction", "shape": "domain",
        "subject": rel, "reason": reason, "by": by,
        "at": datetime.date.today().isoformat(), "volatile": volatile,
    })
    sys.stdout.write(f"compass make-domain: removed {rel}\n")
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
    apply = "--apply" in remaining
    undo = "--undo" in remaining
    positional = [a for a in remaining if not a.startswith("--")]
    vault_root = vaultlib.find_vault_root()

    if undo:
        return _run_undo(vault_root, positional, apply, reason, volatile, by)

    if not positional:
        sys.stderr.write(
            "usage: compass make-domain <type-dir>/<path> --class-here <line> "
            "[--reason <text>] [--apply]\n"
        )
        return 1
    rel = positional[0].strip("/")
    parts = rel.split("/")
    if len(parts) < 2:
        sys.stderr.write("compass make-domain: target must be <type-dir>/<path>\n")
        return 1

    type_dirs = set(vaultlib.classify_root_dirs(vault_root)["type_dirs"])
    if parts[0] not in type_dirs:
        sys.stderr.write(f"compass make-domain: {parts[0]} is not a type dir of this vault\n")
        return 1

    target = vault_root / rel
    if target.exists() or target.with_suffix(".md").exists():
        sys.stderr.write(f"compass make-domain: {rel} already exists, refused\n")
        return 1
    parent = target.parent
    parent_rel = "/".join(parts[:-1])
    if not parent.is_dir() or (len(parts) > 2 and not (parent / "index.md").is_file()):
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
    vaultlib.write_text_lf(index, _template(parts[-1], class_here, today))
    sizing_id = sizing.mint_id(vault_root)
    sizing.stamp_id(index, sizing_id)
    sizing.append_row(vault_root, {
        "id": sizing_id, "action": "decision", "shape": "domain",
        "subject": rel, "reason": reason, "by": by, "at": today,
        "volatile": volatile,
    })
    sys.stdout.write(f"compass make-domain: created {rel} ({sizing_id})\n")
    return 0
