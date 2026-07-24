"""Shared vault library for the compass CLI.

Pure standard library. Every function here is deterministic and side-effect
free except `write_text_lf`, which is the single writer all commands route
through so line endings stay LF on every platform.
"""

import os
import re
from pathlib import Path

# Reserved infrastructure directories: never artifact type directories, never
# units, skipped by classification wherever they appear.
NON_TYPE_DIRS = {"meta", "tmp", "archive", ".annotations"}

# Reserved artifact type directories, scanned even when empty.
CORE_TYPE_DIRS = ["specs", "plans", "research", "decisions", "lessons", "handoffs", "prs"]

# Maps an artifact's `type` frontmatter value to its directory name. Used by
# numbering; artifact scanning discovers type directories from disk instead.
TYPE_TO_DIR = {
    "spec": "specs",
    "plan": "plans",
    "research": "research",
    "decision": "decisions",
    "lesson": "lessons",
    "handoff": "handoffs",
    "pr": "prs",
}


def _has_typed_artifact(directory):
    """True if the directory holds at least one markdown file with a `type:`
    frontmatter field - the signal that it is an artifact directory rather than
    an incidental folder (e.g. a stray `.compass/claude/` of agent files)."""
    candidates = list(directory.glob("*.md")) + list(directory.glob("*/index.md"))
    for path in candidates:
        data, error = parse_frontmatter(path)
        if not error and data.get("type"):
            return True
    return False


def _is_unit(directory):
    """True if the directory's own `index.md` declares `type: unit` in its
    frontmatter - the explicit marker that the folder is a unit of work
    (holding its own type subdirectories) rather than a type directory."""
    index = directory / "index.md"
    if not index.is_file():
        return False
    data, error = parse_frontmatter(index)
    return error is None and data.get("type") == "unit"


def classify_root_dirs(root):
    """Classify every subdirectory of `root` (the vault root, or a unit folder
    when scanning the unit's own type dirs).

    Returns `{"type_dirs": [...], "units": [...], "unclassified": [...]}`,
    each a name list in sorted order. Reserved infra dirs (NON_TYPE_DIRS and
    dot-dirs) are skipped outright. Reserved type names are always type dirs.
    A non-reserved dir is a unit iff its `index.md` carries the `type: unit`
    marker; failing that it is a custom type dir when it holds a typed
    artifact (the content signal that keeps e.g. `retro/` working); failing
    that, if it contains markdown at any depth it is unclassified - never
    scanned, surfaced by `validate` for the human to resolve. Directories
    with no markdown at all are silently ignored.
    """
    root = Path(root)
    result = {"type_dirs": [], "units": [], "unclassified": []}
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name in NON_TYPE_DIRS or child.name.startswith("."):
            continue
        if child.name in CORE_TYPE_DIRS:
            result["type_dirs"].append(child.name)
        elif _is_unit(child):
            result["units"].append(child.name)
        elif _has_typed_artifact(child):
            result["type_dirs"].append(child.name)
        elif any(child.rglob("*.md")):
            result["unclassified"].append(child.name)
    return result


def discover_type_dirs(vault_root):
    """Artifact type directories directly under `vault_root`: the reserved
    core dirs (always), plus any other subdirectory that actually contains
    typed artifacts. Unit folders are not type directories; `scan_artifacts`
    reaches their type dirs through `classify_root_dirs`.

    Always scanning the core dirs keeps numbering and sections stable even when
    a dir is empty. Requiring a typed artifact for extra dirs lets a vault add
    its own type (e.g. `retro/`) without code changes, while skipping incidental
    folders some projects drop in `.compass/` (`claude/`, `configs/`, ...).
    """
    return classify_root_dirs(vault_root)["type_dirs"]


def all_markdown_files(vault_root):
    """Every markdown file anywhere under the vault, for wikilink resolution.

    Includes type dirs, `archive/`, and any other subdir so a link to an
    archived or non-standard artifact still resolves. Excludes only `tmp/`,
    `meta/`, and `.annotations/` (generated or non-document content).
    """
    vault_root = Path(vault_root)
    skip = {"tmp", "meta", ".annotations"}
    files = []
    for path in sorted(vault_root.rglob("*.md")):
        rel_parts = path.relative_to(vault_root).parts
        if rel_parts and rel_parts[0] in skip:
            continue
        files.append(path)
    return files


def find_vault_root(start=None):
    """Return the `.compass` directory for the current project.

    Honors `CLAUDE_PROJECT_DIR` (set by the plugin hook runtime) first, then
    walks up from `start` (or cwd) looking for a `.compass` directory.
    Raises FileNotFoundError if none is found.
    """
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        candidate = Path(env) / ".compass"
        if candidate.is_dir():
            return candidate
    current = Path(start or os.getcwd()).resolve()
    for directory in [current, *current.parents]:
        candidate = directory / ".compass"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(f"no .compass vault found from {current}")


def _scalar(value):
    """Strip a single layer of matching quotes from a scalar value."""
    value = value.strip()
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        return value[1:-1]
    return value


def _split_inline_list(inner):
    """Split the inside of an inline `[a, b, c]` list, respecting quotes."""
    items, current, quote = [], "", None
    for char in inner:
        if quote:
            current += char
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            current += char
        elif char == ",":
            items.append(current)
            current = ""
        else:
            current += char
    if current.strip():
        items.append(current)
    return [_scalar(item) for item in items]


def parse_frontmatter_text(text):
    """Parse a YAML frontmatter block from `text`.

    Returns `(data, error)`. `error` is None on success, or a short string
    when the block is missing or unterminated. Handles the frontmatter subset
    the vault uses: scalar `key: value`, inline `key: [a, b]`, and block lists
    of `- item` under a key. Never raises on malformed content; unparseable
    lines are skipped.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, "no frontmatter"
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, "unterminated frontmatter"

    data = {}
    key = None
    for raw in lines[1:end]:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and key is not None:
            if not isinstance(data.get(key), list):
                data[key] = []
            data[key].append(_scalar(stripped[2:].strip()))
            continue
        match = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", raw)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if value == "":
            data[key] = ""
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            data[key] = _split_inline_list(inner) if inner else []
        else:
            data[key] = _scalar(value)
    return data, None


def parse_frontmatter(path):
    """Read `path` and parse its frontmatter. See `parse_frontmatter_text`."""
    text = Path(path).read_text(encoding="utf-8")
    return parse_frontmatter_text(text)


def _scan_type_dir(base, type_dir, unit):
    """Classify every artifact markdown file under one type directory.

    `base` is the directory on disk; `unit` is the owning unit folder name,
    or None when the type dir sits at the vault root. A unit artifact's
    `name` is its vault-relative path without extension, so links to it are
    path-qualified and unambiguous across units.
    """
    records = []
    for path in sorted(base.rglob("*.md")):
        rel = path.relative_to(base)
        parts = rel.parts
        if path.name == "index.md":
            if len(parts) == 1:
                # A bare `<type>/index.md` is not an artifact; skip it.
                continue
            kind = "folder-index"
            name = "/".join(parts[:-1])
            # A folder spec renders at the depth of its folder, which sits
            # one level above its own `index.md` file.
            depth = len(parts) - 2
        elif len(parts) == 1:
            kind = "flat"
            name = path.stem
            depth = 0
        else:
            kind = "child"
            name = "/".join(list(parts[:-1]) + [path.stem])
            depth = len(parts) - 1
        if unit is not None:
            name = f"{unit}/{type_dir}/{name}"
        records.append({
            "path": path,
            "type_dir": type_dir,
            "kind": kind,
            "rel": str(rel).replace("\\", "/"),
            "name": name,
            "depth": depth,
            "unit": unit,
        })
    return records


def scan_artifacts(vault_root):
    """Walk the type directories - at the vault root and inside each marked
    unit folder - and classify every artifact markdown file.

    Each record is a dict with: `path`, `type_dir` (bare type dir name, e.g.
    `specs` even inside a unit), `kind` (`flat` | `folder-index` | `child`),
    `rel` (POSIX path within the type dir), `name` (wikilink identity;
    vault-relative for unit artifacts), `depth` (folder nesting level), and
    `unit` (owning unit folder name, None for root artifacts). A unit's own
    `index.md` is the unit's marker, not an artifact, and is not scanned.
    """
    vault_root = Path(vault_root)
    layout = classify_root_dirs(vault_root)
    records = []
    for type_dir in layout["type_dirs"]:
        records.extend(_scan_type_dir(vault_root / type_dir, type_dir, None))
    for unit in layout["units"]:
        unit_dir = vault_root / unit
        for type_dir in classify_root_dirs(unit_dir)["type_dirs"]:
            records.extend(_scan_type_dir(unit_dir / type_dir, type_dir, unit))
    return records


def resolvable_names_map(vault_root):
    """Every name a wikilink may resolve to, mapped to the vault-relative
    POSIX paths (extension kept) of the files bearing that name.

    Names per file: its bare stem, its path-qualified name (vault-relative,
    no extension), and - when the file is a folder `index.md` - the folder's
    name and the folder's vault-relative path. Drawn from every markdown
    file in the vault, so archive/ and custom type dirs are covered. A name
    mapping to more than one path is an ambiguous wikilink.
    """
    vault_root = Path(vault_root)
    mapping = {}
    for path in all_markdown_files(vault_root):
        rel = path.relative_to(vault_root)
        names = {path.stem, str(rel.with_suffix("")).replace("\\", "/")}
        if path.name == "index.md":
            names.add(path.parent.name)
            folder_rel = rel.parent.as_posix()
            if folder_rel != ".":
                names.add(folder_rel)
        for name in names:
            mapping.setdefault(name, []).append(str(rel).replace("\\", "/"))
    return mapping


def count_tokens(text):
    """Approximate token count at ~4 characters per token.

    Used only for conservative hot-path cap checks, where the cap is itself a
    round number with headroom. Swap for a real tokenizer if exactness is ever
    required.
    """
    return len(text) // 4


# Fence delimiters: an opening fence may carry an info string (```python);
# a closing fence is bare, same character, at least as long as the opener.
_FENCE_OPEN = re.compile(r"^(`{3,}|~{3,})")
_FENCE_CLOSE = re.compile(r"^(`{3,}|~{3,})\s*$")

# A single-backtick inline code span, never crossing a line break.
_INLINE_CODE_SPAN = re.compile(r"`[^`\n]+`")


def strip_fenced_code(text):
    """Blank out fenced code blocks, preserving the line count.

    Returns `(stripped_text, unterminated_fence)`. Every line of a fenced
    block - delimiters included - becomes an empty line, so line numbers
    computed on the stripped text still point at the original. Both backtick
    and tilde fences are handled; a closing fence must use the opener's
    character and be at least as long.

    A fence that never closes runs to the end of the text (CommonMark), so
    everything from the opener onward is blanked and the flag is True. The
    flag is how callers tell "content absent" from "content swallowed by a
    broken fence" - they must fail loud instead of passing silently.
    """
    lines = text.split("\n")
    out = list(lines)
    open_marker = None
    open_index = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if open_marker is None:
            match = _FENCE_OPEN.match(stripped)
            if match:
                open_marker = match.group(1)
                open_index = i
        else:
            match = _FENCE_CLOSE.match(stripped)
            if (
                match
                and match.group(1)[0] == open_marker[0]
                and len(match.group(1)) >= len(open_marker)
            ):
                for j in range(open_index, i + 1):
                    out[j] = ""
                open_marker = None
                open_index = None
    unterminated = open_marker is not None
    if unterminated:
        for j in range(open_index, len(out)):
            out[j] = ""
    return "\n".join(out), unterminated


def strip_inline_code(text):
    """Remove single-backtick inline code spans.

    Spans never cross a line break, so the line count is preserved. Example
    wikilinks or decision tokens quoted in inline code are documentation, not
    live references; validators and parsers strip them before matching.
    """
    return _INLINE_CODE_SPAN.sub("", text)


def write_text_lf(path, text):
    """Write `text` to `path` with LF line endings on every platform.

    Normalizes any CRLF or lone CR to LF and disables newline translation so
    a Windows host cannot emit CRLF that later breaks Linux container scripts.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(normalized)
