"""`compass decisions <doc>` - list a document's D-NN decisions.

Resolves `<doc>` the way a wikilink resolves: a vault-relative path (with or
without `.md`) or any name in the vault's resolution map, bare stem or
path-qualified. Prints the parse outcome and one aligned row per decision:
ID, trackable flag, tags, and the first line of the decision text.

Exit 0 on `parsed` and on `none-present`; exit 1 on `could-not-parse` - a
document holding decision-shaped content the D-NN grammars cannot read is a
format mismatch that must fail loud, never pass as "nothing to check".
Never exits 2.
"""

import sys

import decisionslib
import vaultlib


def resolve_doc(vault_root, arg, resolve):
    """Resolve one document argument to a file under the vault.

    Accepts a vault-relative path (a folder artifact may be named by its
    folder or its `index.md`) or any name in the resolution map. Returns
    `(path, error)` with exactly one side set; an ambiguous name reports
    every candidate.
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


def format_table(decisions):
    """Aligned rows for a decision list: id, trackable flag, tags, and the
    first line of the decision text."""
    rows = [("id", "trackable", "tags", "text")]
    for decision in decisions:
        rows.append((
            decision["id"],
            "yes" if decision["trackable"] else "no",
            ",".join(decision["tags"]) or "-",
            decision["text"].split("\n")[0],
        ))
    widths = [max(len(row[col]) for row in rows) for col in range(4)]
    return [
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip()
        for row in rows
    ]


def run(args):
    for arg in args:
        if arg.startswith("--"):
            sys.stderr.write(f"compass decisions: unknown flag {arg}\n")
            return 1
    if len(args) != 1:
        sys.stderr.write("usage: compass decisions <doc>\n")
        return 1

    vault_root = vaultlib.find_vault_root()
    resolve = vaultlib.resolvable_names_map(vault_root)
    path, error = resolve_doc(vault_root, args[0], resolve)
    if error:
        sys.stderr.write(f"compass decisions: {error}\n")
        return 1

    rel = path.relative_to(vault_root).as_posix()
    decisions, outcome = decisionslib.extract_decisions(
        path.read_text(encoding="utf-8")
    )

    if outcome == "could-not-parse":
        sys.stderr.write(
            f"compass decisions: could not parse decisions in {rel} - "
            "decision-shaped content does not match the '- **D-NN:** text' "
            "convention\n"
        )
        return 1
    if outcome == "none-present":
        sys.stdout.write(f"compass decisions: {rel} - no decisions present\n")
        return 0
    sys.stdout.write(f"compass decisions: {rel} - {len(decisions)} decision(s)\n")
    for line in format_table(decisions):
        sys.stdout.write(line + "\n")
    return 0
