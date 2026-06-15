"""Shared vault library for the compass CLI.

Pure standard library. Every function here is deterministic and side-effect
free except `write_text_lf`, which is the single writer all commands route
through so line endings stay LF on every platform.
"""

import os
import re
from pathlib import Path

# Artifact type directories under `.compass/`, in index display order.
TYPE_DIRS = ["specs", "plans", "research", "decisions", "lessons", "handoffs", "prs"]

# Maps an artifact's `type` frontmatter value to its directory name.
TYPE_TO_DIR = {
    "spec": "specs",
    "plan": "plans",
    "research": "research",
    "decision": "decisions",
    "lesson": "lessons",
    "handoff": "handoffs",
    "pr": "prs",
}


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


def scan_artifacts(vault_root):
    """Walk the type directories and classify every artifact markdown file.

    Each record is a dict with: `path`, `type_dir`, `kind`
    (`flat` | `folder-index` | `child`), `rel` (POSIX path within the type
    dir), `name` (wikilink identity), and `depth` (folder nesting level).
    """
    vault_root = Path(vault_root)
    records = []
    for type_dir in TYPE_DIRS:
        base = vault_root / type_dir
        if not base.is_dir():
            continue
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
            records.append({
                "path": path,
                "type_dir": type_dir,
                "kind": kind,
                "rel": str(rel).replace("\\", "/"),
                "name": name,
                "depth": depth,
            })
    return records


def count_tokens(text):
    """Approximate token count at ~4 characters per token.

    Used only for conservative hot-path cap checks, where the cap is itself a
    round number with headroom. Swap for a real tokenizer if exactness is ever
    required.
    """
    return len(text) // 4


def write_text_lf(path, text):
    """Write `text` to `path` with LF line endings on every platform.

    Normalizes any CRLF or lone CR to LF and disables newline translation so
    a Windows host cannot emit CRLF that later breaks Linux container scripts.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(normalized)
