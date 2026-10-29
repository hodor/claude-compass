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
line is also the addition's marker. The block runs from the marker line to
the end of the target, so a hand-run `--apply` finds its own block, leaves it
alone when it matches the local file, and replaces it from the marker to the
end when the local file has changed. Text above the marker is never
rewritten: a target with CRLF line endings keeps its bytes above the marker
and receives the block in its own line ending.

Each addition is in one of four states:

    not applied      the target has no block for it
    current          the target's block matches the local file
    out of date      the target's block differs from the local file
    no shipped file  the target does not exist

An emptied local file leaves a block in the target out of date; applying it
removes the block and leaves the shipped text as it was.

Shipped content comes first and the addendum last, so a local instruction
that contradicts shipped prose wins by position - the same rule Claude Code's
own CLAUDE.md concatenation uses.

`CLAUDE.md` is never read, written, or moved here or anywhere else in the
CLI (SPEC-014 D-02).
"""

import os
import re
import sys
from pathlib import Path

import vaultlib

LOCAL_DIR = "meta/local"
MARKER = "<!-- project-local overlay: {source} -->"

NOT_APPLIED = "not applied"
CURRENT = "current"
OUT_OF_DATE = "out of date"
NO_SHIPPED_FILE = "no shipped file"
UNREADABLE = "unreadable"

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


def _lf(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _block_start(raw, marker, block):
    """Return the index where the addition's block starts in `raw`, or -1.

    A block start is a line holding the marker alone, set off by blank lines
    from the text before and after it, which is how an addition is appended.
    A marker quoted inside shipped prose or inside the addition itself does
    not have that shape. Among several candidates the one whose text to the
    end of the target equals the block wins; otherwise the last, since the
    block is always the final thing in the target."""
    candidates = []
    for match in re.finditer(rf"(?m)^{re.escape(marker)}\r?$", raw):
        head = _lf(raw[: match.start()])
        tail = _lf(raw[match.end():])
        if (head == "" or head.endswith("\n\n")) and (
            tail.strip() == "" or tail.startswith("\n\n")
        ):
            candidates.append(match.start())
    for start in candidates:
        if _lf(raw[start:]).rstrip() == block.rstrip():
            return start
    return candidates[-1] if candidates else -1


def _addition_block(rel, source_path):
    """Return (block, empty) for one addition: the marker line plus the
    addition's stripped text (the marker alone for an addition with no
    text), and whether the addition has no text. Raises OSError or
    ValueError when the local file cannot be read."""
    marker = MARKER.format(source=f"{LOCAL_DIR}/{rel}")
    addition = vaultlib.read_vault_text(source_path).strip()
    if not addition:
        return marker, True
    return f"{marker}\n\n{addition}", False


def addition_blocks(vault_root):
    """Return {rel: block} for every addition that has text and can be read,
    `rel` being the path under `meta/local/` (`skills/lessons.md`). The
    block is the marker line plus the addition, LF-normalized, which is what
    an applied addition occupies in its target. An empty or unreadable
    addition has no entry. Never raises. A builder that writes shipped
    content somewhere other than `.claude/` appends these blocks itself."""
    blocks = {}
    for rel, path in find_overlays(vault_root):
        try:
            block, empty = _addition_block(rel, path)
        except (OSError, ValueError):
            continue
        if not empty:
            blocks[rel] = block
    return blocks


def _classify(vault_root, rel, source_path):
    """Return (state, target, raw, index, block, empty) for one addition.
    `raw` is the target's text with its own line endings; `block` is the
    marker line plus the addition, LF-normalized, the text an applied
    addition occupies from its marker to the end of the target; `index` is
    where the target's block starts in `raw`, or -1; `empty` is true for an
    addition with no text. Raises OSError or ValueError when the local file
    or the target cannot be read."""
    target = _target_path(vault_root, rel)
    if not target.is_file():
        return NO_SHIPPED_FILE, target, "", -1, "", False
    marker = MARKER.format(source=f"{LOCAL_DIR}/{rel}")
    block, empty = _addition_block(rel, source_path)
    raw = target.read_bytes().decode("utf-8")
    index = _block_start(raw, marker, block)
    if index < 0:
        return (CURRENT if empty else NOT_APPLIED), target, raw, -1, block, empty
    if _lf(raw[index:]).rstrip() == block.rstrip():
        return CURRENT, target, raw, index, block, empty
    return OUT_OF_DATE, target, raw, index, block, empty


def addition_states(vault_root):
    """Return [(rel, state)] for every addition, sorted by path. Reads only;
    an addition or target that cannot be read reports as unreadable."""
    states = []
    for rel, path in find_overlays(vault_root):
        try:
            state = _classify(vault_root, rel, path)[0]
        except (OSError, ValueError):
            state = UNREADABLE
        states.append((rel, state))
    return states


def _write_text(target, text):
    """Write `text` as UTF-8 to the file `target` resolves to, so a symlinked
    target keeps its link and the file behind it changes. The text lands
    through a temp file and an atomic replace; a filesystem that refuses the
    replace gets the text written straight to the file."""
    real = Path(os.path.realpath(target))
    data = text.encode("utf-8")
    tmp = real.with_name(f".{real.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, real)
    except OSError:
        tmp.unlink(missing_ok=True)
        real.write_bytes(data)


def _write_block(target, raw, index, block, empty):
    """Write the addition's block into `target`. Text above the block keeps
    its bytes; the block is written in the target's own line ending. An
    empty addition removes the block and leaves the shipped text."""
    eol = "\r\n" if "\r\n" in raw else "\n"
    above = raw[:index] if index >= 0 else raw.rstrip("\r\n") + eol + eol
    if empty:
        above = above.rstrip("\r\n")
        text = above + eol if above else ""
    else:
        text = above + block.replace("\n", eol) + eol
    _write_text(target, text)


def apply_overlays(vault_root, apply=True):
    """Bring every addition's block in its installed target up to date.
    Returns {"applied", "skipped", "orphans"} of overlay-relative paths:
    applied is written this run (a new block, an out-of-date block replaced
    from its marker to the end of the target, or a block removed because the
    local file is empty), skipped is already current, and orphans name a
    target that does not exist. An addition whose local file or target
    cannot be read or written goes into a "failed" key, a dict of path to
    reason present only when something failed; the other additions still
    apply. With `apply=False` nothing is written and applied lists what
    would be. Never raises."""
    report = {"applied": [], "skipped": [], "orphans": []}
    for rel, path in find_overlays(vault_root):
        try:
            state, target, raw, index, block, empty = _classify(
                vault_root, rel, path
            )
            if state == NO_SHIPPED_FILE:
                report["orphans"].append(rel)
            elif state == CURRENT:
                report["skipped"].append(rel)
            else:
                if apply:
                    _write_block(target, raw, index, block, empty)
                report["applied"].append(rel)
        except (OSError, ValueError) as exc:
            report.setdefault("failed", {})[rel] = str(exc) or type(exc).__name__
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
        report = apply_overlays(vault_root, apply=True)
        written = {NOT_APPLIED: "applied", OUT_OF_DATE: "updated"}
        failed = report.get("failed", {})
        for rel, state in states:
            if rel in failed:
                sys.stdout.write(f"{rel}: not written ({failed[rel]})\n")
            else:
                sys.stdout.write(f"{rel}: {written.get(state, state)}\n")
        return 0
    for rel, state in states:
        sys.stdout.write(f"{rel}: {state}\n")
    if any(state in (NOT_APPLIED, OUT_OF_DATE) for _, state in states):
        sys.stdout.write("run `compass overlay --apply` to write them\n")
    return 0
