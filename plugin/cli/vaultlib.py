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
CORE_TYPE_DIRS = ["specs", "plans", "research", "decisions", "lessons", "handoffs", "prs", "loops"]

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
    "loop": "loops",
}

# A loop folder is `loops/LOOP-NNN-name/`; only its `index.md` is an artifact.
LOOP_FOLDER = re.compile(r"^LOOP-\d+-")


def in_loops_dir(vault_root, path):
    """True when `path` sits at or below a `loops/` type dir, at the vault
    root or inside a unit folder."""
    parts = Path(path).relative_to(vault_root).parts
    return bool(parts) and (
        parts[0] == "loops"
        or (len(parts) > 1 and parts[1] == "loops" and parts[0] not in CORE_TYPE_DIRS)
    )


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


def attachment_names(vault_root):
    """The names a wikilink or embed reaches a non-markdown vault file by
    (an image, a `.canvas`, a `.base`): each file's name with its extension
    and its vault-relative POSIX path. Skips what `all_markdown_files` skips
    and every dot-directory, such as `.obsidian/`."""
    vault_root = Path(vault_root)
    skip = {"tmp", "meta", ".annotations"}
    names = set()
    for path in vault_root.rglob("*"):
        rel_parts = path.relative_to(vault_root).parts
        if (rel_parts[0] in skip or any(part.startswith(".") for part in rel_parts[:-1])
                or path.suffix == ".md" or not path.is_file()):
            continue
        names.add(path.name)
        names.add("/".join(rel_parts))
    return names


COMPASS_HOME_STORES = ("sessions", "private")


def _compass_homes():
    """The user's Compass home directories: `~/.compass` and, when set,
    `COMPASS_HOME`."""
    homes = [Path.home() / ".compass"]
    configured = os.environ.get("COMPASS_HOME")
    if configured:
        homes.append(Path(configured))
    return homes


def _is_compass_home(candidate, homes):
    """True for a configured Compass home, or for any `.compass` holding the
    Compass-home stores (`sessions/`, `private/`) and no `index.md`, which
    names the user's home store even when HOME points elsewhere."""
    if not (candidate / "index.md").exists() and any(
        (candidate / store).is_dir() for store in COMPASS_HOME_STORES
    ):
        return True
    for home in homes:
        try:
            if os.path.samefile(candidate, home):
                return True
        except OSError:
            continue
    return False


def find_vault_root(start=None, honor_env=True):
    """Return the `.compass` directory for the current project.

    Honors `CLAUDE_PROJECT_DIR` (set by the plugin hook runtime) first, unless
    `honor_env` is false, then walks up from `start` (or cwd) looking for a
    `.compass` directory. The
    user's Compass home (`COMPASS_HOME`, default `~/.compass`), which holds
    kept session clones and private stores, is never a project vault. The
    walk stops below a drive root: a `.compass` there is a vault only for a
    session started in the root itself, so a folder under it with no vault
    of its own finds none.
    Raises FileNotFoundError if none is found.
    """
    homes = _compass_homes()
    env = os.environ.get("CLAUDE_PROJECT_DIR") if honor_env else None
    if env:
        candidate = Path(env) / ".compass"
        if candidate.is_dir() and not _is_compass_home(candidate, homes):
            return candidate
    current = Path(start or os.getcwd()).resolve()
    for directory in [current, *current.parents]:
        if directory != current and directory.parent == directory:
            break
        candidate = directory / ".compass"
        if candidate.is_dir() and not _is_compass_home(candidate, homes):
            return candidate
    raise FileNotFoundError(f"no .compass vault found from {current}")


def _scalar(value):
    """Strip a matching quote layer and undo the YAML escapes that layer
    carries: a doubled apostrophe inside single quotes, a backslash-escaped
    quote or backslash inside double quotes. Other escape sequences pass
    through verbatim."""
    value = value.strip()
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        inner = value[1:-1]
        if value[0] == "'":
            return inner.replace("''", "'")
        return re.sub(r'\\(["\\])', r"\1", inner)
    return value


def yaml_double_quote(value):
    """Serialize a value as a YAML double-quoted scalar - backslash and
    quote escaped, everything else verbatim. The one form `_scalar` and a
    real YAML parser (Obsidian's included) read identically, so every
    writer of quoted frontmatter and catalog values routes through it."""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


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


def _block_scalar(style, block_lines):
    """Value of a `>` folded or `|` literal block scalar. Continuation
    lines drop the first content line's indentation; `|` keeps line breaks,
    `>` folds them to spaces and keeps a blank line as a paragraph break.
    Chomping indicators only govern trailing newlines, which these stripped
    values never keep."""
    contents, indent = [], None
    for line in block_lines:
        if not line.strip():
            contents.append("")
            continue
        if indent is None:
            indent = len(line) - len(line.lstrip())
        if not line[:indent].strip():
            contents.append(line[indent:].rstrip())
        else:
            contents.append(line.strip())
    while contents and contents[0] == "":
        contents.pop(0)
    while contents and contents[-1] == "":
        contents.pop()
    if style == "|":
        return "\n".join(contents)
    paragraphs, current = [], []
    for line in contents:
        if line:
            current.append(line)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n".join(paragraphs)


def parse_frontmatter_text(text):
    """Parse a YAML frontmatter block from `text`.

    Returns `(data, error)`. `error` is None on success, or a short string
    when the block is missing or unterminated. Handles the frontmatter subset
    the vault uses: scalar `key: value`, inline `key: [a, b]`, block lists
    of `- item` under a key, and `key: >` / `key: |` block scalars (with
    chomping indicators), whose indented continuation lines fold into the
    value. Never raises on malformed content; unparseable lines are skipped.
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
    i = 1
    while i < end:
        raw = lines[i]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if stripped.startswith("- ") and key is not None:
            if not isinstance(data.get(key), list):
                data[key] = []
            data[key].append(_scalar(stripped[2:].strip()))
            i += 1
            continue
        match = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", raw)
        if not match:
            i += 1
            continue
        key, value = match.group(1), match.group(2).strip()
        if re.fullmatch(r"[>|][+-]?", value):
            block = []
            i += 1
            while i < end and (not lines[i].strip() or lines[i][0] in " \t"):
                block.append(lines[i])
                i += 1
            data[key] = _block_scalar(value[0], block)
            continue
        if value == "":
            data[key] = ""
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            data[key] = _split_inline_list(inner) if inner else []
        else:
            data[key] = _scalar(value)
        i += 1
    return data, None


def parse_frontmatter(path):
    """Read `path` and parse its frontmatter. See `parse_frontmatter_text`."""
    text = read_vault_text(path)
    return parse_frontmatter_text(text)


def is_loose_nested(path, kind):
    """True for a `"child"` record whose immediate parent folder carries no
    `index.md` of its own - a plain grouping subfolder rather than a
    folder-spec. A folder-spec's own children stay scoped to that folder's
    name (unique within it by filesystem constraint); a loose nested doc has
    nothing scoping its subfolder, so two of them in different subfolders
    can share a filename, and only the full vault-relative name tells them
    apart. Always False for `"flat"` and `"folder-index"` records.
    """
    return kind == "child" and not (path.parent / "index.md").is_file()


def _scan_type_dir(base, type_dir, unit):
    """Classify every artifact markdown file under one type directory.

    `base` is the directory on disk; `unit` is the owning unit folder name,
    or None when the type dir sits at the vault root. A unit artifact's
    `name` is its vault-relative path without extension, so links to it are
    path-qualified and unambiguous across units. A loose nested root
    artifact (see `is_loose_nested`) gets the same vault-relative form even
    though it has no unit, for the same uniqueness reason.
    """
    records = []
    for path in sorted(base.rglob("*.md")):
        rel = path.relative_to(base)
        parts = rel.parts
        if type_dir == "loops":
            # A loop's feedback, golden patterns and other parts are not
            # artifacts; its `index.md` is one flat artifact named for the
            # folder, never a folder spec with children.
            if not (len(parts) == 2 and parts[1] == "index.md"
                    and LOOP_FOLDER.match(parts[0])):
                continue
            records.append({
                "path": path,
                "type_dir": type_dir,
                "kind": "loop-index",
                "rel": str(rel).replace("\\", "/"),
                "name": parts[0] if unit is None else f"{unit}/{type_dir}/{parts[0]}",
                "depth": 0,
                "unit": unit,
            })
            continue
        if path.name == "index.md":
            if len(parts) == 1:
                # A bare `<type>/index.md` is not an artifact; skip it.
                continue
            kind = "folder-index"
            core = "/".join(parts[:-1])
            # A folder spec renders at the depth of its folder, which sits
            # one level above its own `index.md` file.
            depth = len(parts) - 2
        elif len(parts) == 1:
            kind = "flat"
            core = path.stem
            depth = 0
        else:
            kind = "child"
            core = "/".join(list(parts[:-1]) + [path.stem])
            depth = len(parts) - 1
        # A record's name is its vault-relative path without extension for
        # everything except a root flat artifact, whose bare stem is unique
        # by construction. Same-named folders on different branches
        # (specs/dup, research/dup) therefore never share a name.
        if unit is not None:
            name = f"{unit}/{type_dir}/{core}"
        elif kind == "flat":
            name = core
        else:
            name = f"{type_dir}/{core}"
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
    `specs` even inside a unit), `kind` (`flat` | `folder-index` | `child` | `loop-index`),
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


def resolve_link(mapping, target):
    """Resolve one wikilink target against `resolvable_names_map` output.

    An exact name match wins outright. Failing that, the target is treated
    as the abbreviated stem `rules/wikilinks.md` resolves by hand with the
    glob `<linkname>*.md`: every slash-free name extending the target is a
    candidate, so `[[R-NAV-1]]` reaches the unique
    `R-NAV-1-uassetuserdata-....md`. Returns the sorted list of matching
    vault-relative paths - empty for a broken link, several for an
    ambiguous one (`R-NAV-1` against both `R-NAV-1-*` and `R-NAV-10-*`).
    """
    paths = mapping.get(target)
    if paths:
        return paths
    if "/" in target:
        return []
    matches = set()
    for name, name_paths in mapping.items():
        if "/" not in name and name.startswith(target):
            matches.update(name_paths)
    return sorted(matches)


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


def split_link(raw):
    """`(target, suffix)` for the text inside a wikilink's brackets: the
    target before any `#heading` or `|alias`, and the rest verbatim. Inside
    a markdown table the alias pipe is written `\\|`; its backslash belongs
    to the suffix."""
    split_at = next((i for i, c in enumerate(raw) if c in "#|"), len(raw))
    if raw[split_at:split_at + 1] == "|" and raw[:split_at].endswith("\\"):
        split_at -= 1
    return raw[:split_at].strip(), raw[split_at:]


def fence_mask(lines):
    """`(mask, unterminated_fence)` for a list of lines: `mask[i]` is True
    when line `i` belongs to a fenced code block, delimiters included. Both
    backtick and tilde fences count; a closing fence uses the opener's
    character and is at least as long, so a shorter or other-character
    fence inside a block is content. A fence that never closes runs to the
    end (CommonMark) and the flag is True."""
    mask = [False] * len(lines)
    open_marker = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if open_marker is None:
            match = _FENCE_OPEN.match(stripped)
            if match:
                open_marker = match.group(1)
                mask[i] = True
            continue
        mask[i] = True
        match = _FENCE_CLOSE.match(stripped)
        if (
            match
            and match.group(1)[0] == open_marker[0]
            and len(match.group(1)) >= len(open_marker)
        ):
            open_marker = None
    return mask, open_marker is not None


def strip_fenced_code(text):
    """Blank out fenced code blocks, preserving the line count.

    Returns `(stripped_text, unterminated_fence)`. Every line `fence_mask`
    marks becomes an empty line, so line numbers computed on the stripped
    text still point at the original. The flag is how callers tell "content
    absent" from "content swallowed by a broken fence" - they must fail loud
    instead of passing silently.
    """
    lines = text.split("\n")
    mask, unterminated = fence_mask(lines)
    out = ["" if fenced else line for line, fenced in zip(lines, mask)]
    return "\n".join(out), unterminated


def strip_inline_code(text):
    """Remove single-backtick inline code spans.

    Spans never cross a line break, so the line count is preserved. Example
    wikilinks or decision tokens quoted in inline code are documentation, not
    live references; validators and parsers strip them before matching.
    """
    return _INLINE_CODE_SPAN.sub("", text)


def read_vault_text(path):
    """Read `path` as vault text: BOM stripped, line endings normalized.

    `utf-8-sig` drops a leading byte-order mark and is otherwise identical to
    `utf-8`. A BOM survives a plain `utf-8` read as `\\ufeff`, which is not
    whitespace, so it defeats every pattern anchored at the start of the text:
    `^lessons:` stops matching and a `---` frontmatter fence stops being
    recognized, leaving the file parsed as having no frontmatter at all.
    Windows tools write BOMs by default, `PowerShell`'s `Out-File` among them.
    """
    text = Path(path).read_text(encoding="utf-8-sig")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def write_text_lf(path, text):
    """Write `text` to `path` with LF line endings on every platform.

    Normalizes any CRLF or lone CR to LF and disables newline translation so
    a Windows host cannot emit CRLF that later breaks Linux container
    scripts. The text lands through a temp file in the same directory and an
    atomic replace, so a concurrent reader never sees a half-written file.
    A filesystem that refuses the replace (a cloud-synced or placeholder
    file can answer EINVAL) gets the same text written straight to `path`.
    When both refuse, the error names `path` and carries both reasons.
    """
    path = Path(path)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    replace_error = None
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as handle:
            handle.write(normalized)
        os.replace(tmp, path)
        return
    except OSError as exc:
        replace_error = exc
        try:
            tmp.unlink()
        except OSError:
            pass
    try:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(normalized)
    except OSError as exc:
        raise OSError(
            exc.errno,
            f"{exc.strerror} writing {path} "
            f"(atomic replace failed first: {replace_error.strerror})",
        ) from exc
