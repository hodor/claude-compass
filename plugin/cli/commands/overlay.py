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

A shipped file that was edited by hand is saved by update under
`meta/local/kept/<name>`, `<name>` being the addition's path
(`agents/researcher.md`). `compass overlay --extract <name>` reads that saved
copy against the installed shipped text: the lines it holds after the whole
shipped text become the local addition, applied at once. A reworded, removed,
or mid-file inserted shipped line has no form as an addition, so each is
printed on a line of its own and left in the saved copy.

`CLAUDE.md` is never read, written, or moved here or anywhere else in the
CLI (SPEC-014 D-02).
"""

import difflib
import os
import re
import sys
from pathlib import Path

import vaultlib

LOCAL_DIR = "meta/local"
KEPT_DIR = LOCAL_DIR + "/kept"
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


def addition_name(installed_rel):
    """The addition's path under `meta/local/` for an installed path under
    `.claude/`: `agents/builder.md` stays, `skills/lessons/SKILL.md` becomes
    `skills/lessons.md`. Any other file in a skill folder keeps its path."""
    parts = installed_rel.split("/")
    if len(parts) == 3 and parts[0] == "skills" and parts[2] == "SKILL.md":
        return f"skills/{parts[1]}.md"
    return installed_rel


def shipped_forms(rel, data):
    """Return the byte strings the installed file `data` can have been
    shipped as, once the block of its own addition `rel` is removed. A file
    with no such block can only be itself. Applying an addition rewrites the
    newlines between the shipped text and its marker, so the text above the
    marker comes back as it stands, with its trailing newlines trimmed, with
    one newline, and with one two-byte line ending."""
    try:
        raw = data.decode("utf-8")
    except UnicodeDecodeError:
        return [data]
    marker = MARKER.format(source=f"{LOCAL_DIR}/{rel}")
    index = _block_start(raw, marker, "")
    if index < 0:
        return [data]
    above = raw[:index]
    bare = above.rstrip("\r\n")
    forms = [above, bare, bare + "\n", bare + "\r\n"]
    return [form.encode("utf-8") for form in forms]


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


def _split_kept_name(vault_root, name):
    """Return (addition rel, target) for a saved copy's `name`. A later saved
    copy of one file carries a numeric suffix (`builder.2.md`); the suffix is
    dropped when no installed file answers to the full stem. Returns
    (None, None) for a name that is not `<agents|rules|skills>/<file>.md`."""
    parts = name.split("/")
    if (
        len(parts) != 2
        or parts[0] not in TARGETS
        or not parts[1].endswith(".md")
        or parts[1] == ".md"
        or ".." in parts
    ):
        return None, None
    target = _target_path(vault_root, name)
    stripped = re.sub(r"\.\d+\.md$", ".md", parts[1])
    if not target.is_file() and stripped != parts[1]:
        name = f"{parts[0]}/{stripped}"
        target = _target_path(vault_root, name)
    return name, target


def _above_block(rel, raw):
    """The text of `raw` above the block of addition `rel`, LF-normalized;
    all of it when the block is absent."""
    marker = MARKER.format(source=f"{LOCAL_DIR}/{rel}")
    index = _block_start(raw, marker, "")
    return _lf(raw if index < 0 else raw[:index])


def _resembles(a, b):
    """Whether line `a` reads as a rewording of line `b`."""
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.6


def _compare_lines(shipped, kept):
    """Return (added, changes): the lines `kept` holds after all of
    `shipped`, and a sentence for each change that has no form as an
    addition. When the last shipped lines were reworded or removed, the
    kept lines after the last one that resembles a shipped line are the
    appended ones."""
    s_lines = shipped.rstrip("\n").split("\n")
    k_lines = kept.rstrip("\n").split("\n")
    matcher = difflib.SequenceMatcher(None, s_lines, k_lines, autojunk=False)
    added, changes = [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("delete", "replace"):
            for n in range(i1, i2):
                changes.append(
                    f"shipped line {n + 1} is reworded or removed: {s_lines[n]}"
                )
            if tag == "replace" and i2 == len(s_lines):
                start = j1
                for j in range(j1, j2):
                    if any(_resembles(k_lines[j], line) for line in s_lines[i1:i2]):
                        start = j + 1
                added.extend(k_lines[start:j2])
        elif tag == "insert":
            if i1 == len(s_lines):
                added.extend(k_lines[j1:j2])
            else:
                for line in k_lines[j1:j2]:
                    changes.append(f"line inserted after shipped line {i1}: {line}")
    return added, changes


def _append_addition(vault_root, rel, text):
    """Add `text` to the local addition `rel`: a new file, or after the
    existing text. Text the file already holds as whole lines is not added
    again. Returns the path."""
    path = vault_root / LOCAL_DIR / rel
    existing = vaultlib.read_vault_text(path).strip() if path.is_file() else ""
    if f"\n{text}\n" in f"\n{_lf(existing)}\n":
        return path
    joined = f"{existing}\n\n{text}" if existing else text
    path.parent.mkdir(parents=True, exist_ok=True)
    vaultlib.write_text_lf(path, joined + "\n")
    return path


def extract(vault_root, name, out=None):
    """Turn the saved copy `name` into a local addition and apply it. Prints
    what was done and, one per line, each change that has no form as an
    addition. Creates nothing when there is no saved copy, no installed
    shipped file, or no appended line. Returns the exit code."""
    out = out or sys.stdout
    rel, target = _split_kept_name(vault_root, name)
    if rel is None:
        parts = name.split("/")
        if len(parts) == 3 and parts[0] == "skills" and ".." not in parts:
            out.write(
                f"{name}: a local addition extends a skill's SKILL.md only; "
                f"the saved copy stays under {KEPT_DIR}/\n"
            )
            return 0
        out.write(f"compass overlay: {name} is not <agents|rules|skills>/<file>.md\n")
        return 1
    kept_path = vault_root / KEPT_DIR / name
    if not kept_path.is_file():
        out.write(f"{name}: no saved copy under {KEPT_DIR}/\n")
        return 0
    if not target.is_file():
        out.write(f"{rel}: no shipped file to compare the saved copy with\n")
        return 0
    try:
        shipped = _above_block(rel, target.read_bytes().decode("utf-8"))
        kept = _above_block(rel, kept_path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        out.write(f"{name}: not read ({exc})\n")
        return 1
    added, changes = _compare_lines(shipped, kept)
    for change in changes:
        out.write(change.replace("\r", "\\r") + "\n")
    text = "\n".join(added).strip()
    if not text:
        if not changes:
            out.write(
                f"{name}: the saved copy matches the shipped text; nothing to extract\n"
            )
        return 0
    try:
        path = _append_addition(vault_root, rel, text)
        state, tgt, raw, index, block, empty = _classify(vault_root, rel, path)
        if state in (NOT_APPLIED, OUT_OF_DATE):
            _write_block(tgt, raw, index, block, empty)
    except (OSError, ValueError) as exc:
        out.write(f"{rel}: not written ({exc})\n")
        return 1
    out.write(f"{rel}: local addition written and applied\n")
    return 0


def run(args):
    apply = "--apply" in args
    vault_root = vaultlib.find_vault_root()
    if "--extract" in args:
        at = args.index("--extract")
        if at + 1 >= len(args):
            sys.stdout.write("compass overlay: --extract needs the saved file's name\n")
            return 1
        return extract(vault_root, args[at + 1])
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
