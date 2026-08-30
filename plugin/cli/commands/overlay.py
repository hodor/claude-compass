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
then this appends the addendum under a provenance comment. The base is
regenerated every time, so there is never a previous block to locate - the
orphaned-block failure mode of marker splicing cannot occur here, and no
anchor can drift. The provenance line doubles as an idempotence guard for a
hand-run `--apply` outside the update path.

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


def apply_overlays(vault_root, apply=True):
    """Append every overlay to its installed target. Returns
    {"applied", "skipped", "orphans"} of overlay-relative paths: applied is
    written this run, skipped is already present (idempotence guard), and
    orphans name a target that does not exist. Never raises."""
    report = {"applied": [], "skipped": [], "orphans": []}
    claude = vault_root.parent / ".claude"
    for rel, path in find_overlays(vault_root):
        kind, name = rel.split("/", 1)
        target = TARGETS[kind](claude, name[: -len(".md")])
        if not target.is_file():
            report["orphans"].append(rel)
            continue
        marker = MARKER.format(source=f"{LOCAL_DIR}/{rel}")
        current = vaultlib.read_vault_text(target)
        if marker in current:
            report["skipped"].append(rel)
            continue
        if not apply:
            report["applied"].append(rel)
            continue
        addition = vaultlib.read_vault_text(path).strip()
        vaultlib.write_text_lf(
            target, current.rstrip("\n") + f"\n\n{marker}\n\n{addition}\n"
        )
        report["applied"].append(rel)
    return report


def run(args):
    apply = "--apply" in args
    vault_root = vaultlib.find_vault_root()
    report = apply_overlays(vault_root, apply=apply)
    total = sum(len(v) for v in report.values())
    if not total:
        sys.stdout.write(
            "compass overlay: no project-local overlays "
            f"({LOCAL_DIR}/ is empty or absent)\n"
        )
        return 0
    verb = "applied" if apply else "would apply"
    for rel in report["applied"]:
        sys.stdout.write(f"{verb}: {rel}\n")
    for rel in report["skipped"]:
        sys.stdout.write(f"already present: {rel}\n")
    for rel in report["orphans"]:
        sys.stdout.write(f"ORPHAN (target not installed): {rel}\n")
    return 0
