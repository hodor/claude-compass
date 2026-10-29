"""`compass overlay` - project-local additions to shipped agents, rules, and
skills, re-applied after every update (ADR-020).

Update replaces `.claude/agents`, `rules`, and `skills` wholesale and now
fires at every session start, so an edit made directly to a shipped file
dies silently. An overlay is the addition by itself, kept in
`.compass/meta/local/` - inside the vault, which update never touches, and
version-controlled wherever the project tracks `.compass/`:

    .compass/meta/local/agents/researcher.md  -> .claude/agents/researcher.md
    .compass/meta/local/rules/<name>.md       -> .claude/rules/<name>.md
    .compass/meta/local/skills/<name>.md      -> .claude/skills/<name>/SKILL.md

Application is append-after-refresh: update copies the shipped file pristine,
then this appends the addendum under a provenance comment. The provenance
line is also the addition's marker. The block runs from the first occurrence
of the marker to the end of the target, so a hand-run `--apply` finds its own
block, leaves it alone when it matches the local file, and replaces it from
the marker to the end when the local file has changed. Text above the marker
is never rewritten.

Each addition is in one of four states:

    not applied      the target has no block for it
    current          the target's block matches the local file
    out of date      the target's block differs from the local file
    no shipped file  the target does not exist

Shipped content comes first and the addendum last, so a local instruction
that contradicts shipped prose wins by position - the same rule Claude Code's
own CLAUDE.md concatenation uses.

`CLAUDE.md` is never read, written, or moved here or anywhere else in the
CLI (SPEC-014 D-02).
"""

import sys

import vaultlib

LOCAL_DIR = "meta/local"
MARKER = "<!-- project-local overlay: {source} -->"

NOT_APPLIED = "not applied"
CURRENT = "current"
OUT_OF_DATE = "out of date"
NO_SHIPPED_FILE = "no shipped file"

# Overlay subdirectory -> how its name maps onto an installed path.
TARGETS = {
    "agents": lambda claude, stem: claude / "agents" / f"{stem}.md",
    "rules": lambda claude, stem: claude / "rules" / f"{stem}.md",
    "skills": lambda claude, stem: claude / "skills" / stem / "SKILL.md",
}


def find_overlays(vault_root):
    """Return [(rel, path)] for every overlay file, sorted. `rel` is the
    path under `meta/local/`, e.g. `agents/researcher.md`."""
    root = vault_root / LOCAL_DIR
    if not root.is_dir():
        return []
    found = []
    for kind in sorted(TARGETS):
        kind_dir = root / kind
        if not kind_dir.is_dir():
            continue
        for path in sorted(kind_dir.glob("*.md")):
            found.append((f"{kind}/{path.name}", path))
    return found


def _target_path(vault_root, rel):
    kind, name = rel.split("/", 1)
    return TARGETS[kind](vault_root.parent / ".claude", name[: -len(".md")])


def _classify(vault_root, rel, source_path):
    """Return (state, target, current_text, marker_index, block) for one
    addition. `block` is the marker line plus the addition, the text an
    applied addition occupies from its marker to the end of the target;
    `marker_index` is where the target's block starts, or -1."""
    target = _target_path(vault_root, rel)
    if not target.is_file():
        return NO_SHIPPED_FILE, target, "", -1, ""
    marker = MARKER.format(source=f"{LOCAL_DIR}/{rel}")
    addition = vaultlib.read_vault_text(source_path).strip()
    block = f"{marker}\n\n{addition}"
    current = vaultlib.read_vault_text(target)
    index = current.find(marker)
    if index < 0:
        return NOT_APPLIED, target, current, -1, block
    if current[index:].rstrip() == block.rstrip():
        return CURRENT, target, current, index, block
    return OUT_OF_DATE, target, current, index, block


def addition_states(vault_root):
    """Return [(rel, state)] for every addition, sorted by path. Reads only."""
    return [
        (rel, _classify(vault_root, rel, path)[0])
        for rel, path in find_overlays(vault_root)
    ]


def apply_overlays(vault_root, apply=True):
    """Bring every addition's block in its installed target up to date.
    Returns {"applied", "skipped", "orphans"} of overlay-relative paths:
    applied is written this run (a new block, or an out-of-date block
    replaced from its marker to the end of the target), skipped is already
    current, and orphans name a target that does not exist. With
    `apply=False` nothing is written and applied lists what would be. Never
    raises."""
    report = {"applied": [], "skipped": [], "orphans": []}
    for rel, path in find_overlays(vault_root):
        state, target, current, index, block = _classify(vault_root, rel, path)
        if state == NO_SHIPPED_FILE:
            report["orphans"].append(rel)
        elif state == CURRENT:
            report["skipped"].append(rel)
        else:
            if apply:
                if index >= 0:
                    above = current[:index]
                else:
                    above = current.rstrip("\n") + "\n\n"
                vaultlib.write_text_lf(target, f"{above}{block}\n")
            report["applied"].append(rel)
    return report


def run(args):
    apply = "--apply" in args
    vault_root = vaultlib.find_vault_root()
    states = addition_states(vault_root)
    if not states:
        sys.stdout.write(
            "compass overlay: no project-local overlays "
            f"({LOCAL_DIR}/ is empty or absent)\n"
        )
        return 0
    if apply:
        apply_overlays(vault_root, apply=True)
        written = {NOT_APPLIED: "applied", OUT_OF_DATE: "updated"}
        for rel, state in states:
            sys.stdout.write(f"{rel}: {written.get(state, state)}\n")
        return 0
    for rel, state in states:
        sys.stdout.write(f"{rel}: {state}\n")
    if any(state in (NOT_APPLIED, OUT_OF_DATE) for _, state in states):
        sys.stdout.write("run `compass overlay --apply` to write them\n")
    return 0
