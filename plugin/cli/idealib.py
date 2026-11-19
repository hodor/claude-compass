"""The idea record: reading, rendering and editing `ideas/<category>/IDEA-NNN-<slug>.md`.

An idea file holds his words, a status, `led_to` links and a dated history:

    ---
    title: "IDEA-007: what if the map remembers where you died"
    type: idea
    status: new
    words: "what if the map remembers where you died"
    led_to: []
    led_to_note: ""
    raw_status: ""
    source: "compass idea add"
    tags: [idea, world-building]
    created: 2026-11-19
    updated: 2026-11-19
    ---

    > what if the map remembers where you died

    ## History

    - 2026-11-19: new (filed)

`words` is a double-quoted scalar on one line, or a `|-` block scalar when it
holds a newline; both forms read back identically through `vaultlib` and a
real YAML parser. The body blockquote repeats the words, each line prefixed
`> `. Edits touch only the lines the record owns (`status`, `updated`,
`led_to`, and one appended `## History` line); every other line, whatever a
human added, is written back unchanged.

Pure standard library. Callers write through `vaultlib.write_text_lf`.
"""

import json
import re
import unicodedata
from pathlib import Path

import vaultlib

STATUSES = ("new", "exploring", "parked", "adopted", "done", "dropped")
FOLDER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
ID_PATTERN = re.compile(r"^IDEA-(\d+)$", re.IGNORECASE)
FILE_PATTERN = re.compile(r"^IDEA-(\d+)-.*\.md$")
HISTORY_HEADING = re.compile(r"^##\s+History\s*$")
HEADING = re.compile(r"^##\s")
SLUG_WORDS = 5
TITLE_LENGTH = 60
PROMPT_LOG = Path("tmp") / "prompt-log.jsonl"

# Unicode categories a real YAML parser would fold, drop or reject inside a
# quoted or block scalar: control characters (tab and newline aside), lone
# surrogates, and the line and paragraph separators.
_UNSTORABLE_CATEGORIES = {"Cc", "Cs", "Zl", "Zp"}
_NONCHARACTERS = {0xFFFE, 0xFFFF}


def verbatim(words, source_text):
    """True only when `words` is a non-empty exact substring of `source_text`.
    No normalization of case, whitespace, quotes or Unicode form."""
    return bool(words) and words in source_text


def prompt_text(vault_root, prompt_id):
    """The prompt text of the log row whose id is exactly `prompt_id`, or
    None when the log or the row is absent. Lines that are not JSON objects
    (a torn write) are skipped."""
    path = Path(vault_root) / PROMPT_LOG
    if not path.is_file():
        return None
    text = path.read_bytes().decode("utf-8", errors="replace")
    found = None
    for line in text.split("\n"):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("id") == prompt_id:
            prompt = row.get("prompt")
            if isinstance(prompt, str):
                found = prompt
    return found


def storable_error(words):
    """A short reason `words` cannot be stored faithfully, or None."""
    if not words.strip():
        return "words are empty"
    if "\r" in words:
        return "words hold a carriage return, which the vault's LF writer would change"
    for char in words:
        if char in "\n\t":
            continue
        if unicodedata.category(char) in _UNSTORABLE_CATEGORIES or ord(char) in _NONCHARACTERS:
            return f"words hold U+{ord(char):04X}, a character a YAML reader alters"
    return None


def single_line_error(value):
    """A short reason `value` cannot sit on one frontmatter or history line,
    or None."""
    for char in value:
        if unicodedata.category(char) in _UNSTORABLE_CATEGORIES:
            return f"value holds U+{ord(char):04X}, which cannot sit on one line"
    return None


def slug(words):
    """File-name slug from the first five words: ASCII lowercase, accents
    folded, one hyphen between words. `idea` when nothing survives."""
    parts = []
    for token in words.split()[:SLUG_WORDS]:
        folded = unicodedata.normalize("NFKD", token)
        folded = "".join(c for c in folded if not unicodedata.combining(c))
        cleaned = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
        if cleaned:
            parts.append(cleaned)
    return "-".join(parts)[:TITLE_LENGTH].strip("-") or "idea"


def title_for(number, words):
    first = words.split("\n", 1)[0].strip()[:TITLE_LENGTH].rstrip()
    label = f"IDEA-{number:03d}"
    return f"{label}: {first}" if first else label


def words_property(words):
    """The frontmatter lines holding `words`."""
    if "\n" not in words:
        return ["words: " + vaultlib.yaml_double_quote(words)]
    return ["words: |-"] + [("  " + line) if line else "" for line in words.split("\n")]


def led_to_line(links):
    return "led_to: [" + ", ".join(vaultlib.yaml_double_quote(x) for x in links) + "]"


def render(number, words, status, category, source, today, history_line):
    """The full text of a new idea file."""
    tag = category.rsplit("/", 1)[-1]
    lines = [
        "---",
        "title: " + vaultlib.yaml_double_quote(title_for(number, words)),
        "type: idea",
        f"status: {status}",
        *words_property(words),
        "led_to: []",
        'led_to_note: ""',
        'raw_status: ""',
        "source: " + vaultlib.yaml_double_quote(source),
        f"tags: [idea, {tag}]",
        f"created: {today}",
        f"updated: {today}",
        "---",
        "",
        *["> " + line for line in words.split("\n")],
        "",
        "## History",
        "",
        history_line,
        "",
    ]
    return "\n".join(lines)


def round_trips(text, words):
    """True when the vault reader reads `words` back from `text` unchanged."""
    data, error = vaultlib.parse_frontmatter_text(text)
    return error is None and data.get("words") == words


def _closing_fence(lines):
    """Index of the closing unindented `---` line, or None."""
    if not lines or lines[0].rstrip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return i
    return None


def _property_extent(lines, close, key):
    """(start, end) of the `key:` property inside the frontmatter, covering
    its block-scalar or block-list continuation lines; None when absent."""
    pattern = re.compile(rf"^{re.escape(key)}:(\s|$)")
    for i in range(1, close):
        if pattern.match(lines[i]):
            j = i + 1
            while j < close and lines[j] and (lines[j][0] in " \t" or lines[j].startswith("- ")):
                j += 1
            return i, j
    return None


def _set_property(lines, close, key, new_lines):
    """Replace the property's lines, or add them before the closing fence;
    returns the closing fence's new index."""
    extent = _property_extent(lines, close, key)
    if extent is None:
        lines[close:close] = new_lines
        return close + len(new_lines)
    start, end = extent
    lines[start:end] = new_lines
    return close + len(new_lines) - (end - start)


def _append_history(lines, close, entry):
    start = None
    for i in range(close + 1, len(lines)):
        if HISTORY_HEADING.match(lines[i]):
            start = i
            break
    if start is None:
        while lines and lines[-1] == "":
            lines.pop()
        lines.extend(["", "## History", "", entry, ""])
        return
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if HEADING.match(lines[i]):
            end = i
            break
    last = start
    for i in range(start + 1, end):
        if lines[i].strip():
            last = i
    if last == start:
        lines[start + 1:start + 1] = ["", entry]
    else:
        lines.insert(last + 1, entry)


def change(text, old_status, new_status, links, history_entry, today):
    """`text` (LF line endings) with the status set, `links` appended to
    `led_to` (earlier links kept, in order, no duplicates), `updated` stamped
    and one history line appended. Returns the new text, or None when `text`
    has no frontmatter."""
    lines = text.split("\n")
    close = _closing_fence(lines)
    if close is None:
        return None
    data, _ = vaultlib.parse_frontmatter_text(text)
    if new_status != old_status:
        close = _set_property(lines, close, "status", [f"status: {new_status}"])
    current = data.get("led_to") or []
    if isinstance(current, str):
        current = [current]
    merged = list(current)
    for link in links:
        if link not in merged:
            merged.append(link)
    if merged != list(current):
        close = _set_property(lines, close, "led_to", [led_to_line(merged)])
    if _property_extent(lines, close, "updated"):
        close = _set_property(lines, close, "updated", [f"updated: {today}"])
    _append_history(lines, close, history_entry)
    return "\n".join(lines)


def history_lines(body_lines):
    """The non-blank lines of the `## History` section."""
    out, inside = [], False
    for line in body_lines:
        if HISTORY_HEADING.match(line):
            inside = True
        elif inside and HEADING.match(line):
            break
        elif inside and line.strip():
            out.append(line)
    return out


def load(path, ideas_root):
    """One idea as a dict, or None when the file is not an idea record."""
    match = FILE_PATTERN.match(path.name)
    if not match:
        return None
    try:
        text = vaultlib.read_vault_text(path)
    except (OSError, UnicodeDecodeError):
        return None
    data, error = vaultlib.parse_frontmatter_text(text)
    if error:
        return None
    lines = text.split("\n")
    close = _closing_fence(lines)
    body = lines[close + 1:] if close is not None else []
    words = data.get("words")
    if not isinstance(words, str) or not words:
        words = "\n".join(line[2:] for line in body if line.startswith(">"))
    led_to = data.get("led_to") or []
    if isinstance(led_to, str):
        led_to = [led_to]
    category = path.parent.relative_to(ideas_root).as_posix()
    number = int(match.group(1))
    return {
        "number": number,
        "id": f"IDEA-{number:03d}",
        "path": path,
        "category": "" if category == "." else category,
        "status": str(data.get("status", "")),
        "words": words,
        "led_to": led_to,
        "led_to_note": str(data.get("led_to_note", "")),
        "title": re.sub(r"^IDEA-\d+:?\s*", "", str(data.get("title", ""))),
        "history": history_lines(body),
    }


def load_all(vault_root):
    """Every idea under `ideas/`, ordered by number."""
    ideas_root = Path(vault_root) / "ideas"
    if not ideas_root.is_dir():
        return []
    ideas = []
    for path in sorted(ideas_root.rglob("IDEA-*.md")):
        idea = load(path, ideas_root)
        if idea:
            ideas.append(idea)
    return sorted(ideas, key=lambda idea: idea["number"])
