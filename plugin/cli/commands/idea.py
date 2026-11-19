"""`compass idea add|status|find` - the ideas the human has given, in his words.

    compass idea add --category <slug> --words "<text>" [--source <prompt-id>] [--status <s>] [--apply]
    compass idea status <IDEA-NNN> <status> [--words "<his sentence>" --source <prompt-id>] [--led-to "[[doc]]"] [--apply]
    compass idea find "<text or IDEA-NNN>"

`add` files one idea as `ideas/<category>/IDEA-NNN-<slug>.md`, numbered from
the highest `IDEA-NNN` anywhere under `ideas/`. With `--source` the words
must be an exact substring of that logged prompt (`.compass/tmp/prompt-log.jsonl`);
words already held by another idea, an unknown status, a missing category
folder, and words a YAML reader would alter are refused with nothing written.
`status` sets the status, appends to `led_to`, and appends one dated line to
`## History`, quoting his sentence when `--words` is given. Both are dry-run
unless `--apply` is passed.

`find` prints an idea by id; otherwise every idea whose words, `led_to_note`
or title holds the text (case-insensitive), and with no such hit the five
ideas sharing the most words with the text. A miss prints one line, exit 0.
"""

import datetime
import json
import re
import sys

import idealib
import vaultlib
from commands import next_num

USAGE = __doc__

VALUE_FLAGS = {"--category", "--words", "--source", "--status", "--led-to"}
MAX_RANKED = 5
MIN_WORD_LENGTH = 3


def _fail(message):
    sys.stderr.write(f"compass idea: {message}\n")
    return 1


def _parse(args, allowed):
    """Split args into (positionals, {flag: value}, apply, error). A value
    flag takes the next argument verbatim, whatever it starts with."""
    positionals, values, apply = [], {}, False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--apply":
            apply = True
        elif arg in VALUE_FLAGS:
            if arg not in allowed:
                return None, None, None, f"{arg} does not apply to this subcommand"
            if i + 1 >= len(args):
                return None, None, None, f"{arg} requires a value"
            values[arg] = args[i + 1]
            i += 1
        elif arg.startswith("--"):
            return None, None, None, f"unknown flag {arg}"
        else:
            positionals.append(arg)
        i += 1
    return positionals, values, apply, None


def _checked_words(vault_root, words, source):
    """Error text when `words` cannot be filed (as his words from `source`
    when given), else None."""
    problem = idealib.storable_error(words)
    if problem:
        return problem
    if source is not None:
        prompt = idealib.prompt_text(vault_root, source)
        if prompt is None:
            return f"no logged prompt {source}"
        if not idealib.verbatim(words, prompt):
            return f"the words are not verbatim in logged prompt {source}"
    return None


def _history_quote(words):
    return json.dumps(words, ensure_ascii=False)


def _add(args):
    positionals, values, apply, error = _parse(
        args, {"--category", "--words", "--source", "--status"})
    if error:
        return _fail(error)
    if positionals:
        return _fail(f"unexpected argument {positionals[0]!r}")
    category = values.get("--category")
    words = values.get("--words")
    source = values.get("--source")
    status = values.get("--status", "new")
    if not category:
        return _fail("--category is required")
    if words is None:
        return _fail("--words is required")
    if status not in idealib.STATUSES:
        return _fail(f"unknown status {status!r}; one of {', '.join(idealib.STATUSES)}")

    vault_root = vaultlib.find_vault_root()
    segments = category.strip("/").split("/")
    if not all(idealib.FOLDER_NAME.match(s) for s in segments):
        return _fail(f"{category!r} is not a category folder name")
    category = "/".join(segments)
    folder = vault_root / "ideas" / category
    if not folder.is_dir():
        return _fail(f"no category folder ideas/{category}; make-domain creates one")

    problem = _checked_words(vault_root, words, source)
    if problem:
        return _fail(problem)
    for existing in idealib.load_all(vault_root):
        if existing["words"] == words:
            return _fail(f"these words are already {existing['id']} ({existing['category']})")

    highest = next_num._highest(vault_root / "ideas", re.compile(r"^IDEA-(\d+)-"))
    number = highest + 1
    today = datetime.date.today().isoformat()
    filed = f"filed from prompt {source}" if source else "filed"
    text = idealib.render(
        number, words, status, category,
        source or "compass idea add", today, f"- {today}: {status} ({filed})")
    if not idealib.round_trips(text, words):
        return _fail("these words do not read back unchanged from a property; nothing written")
    path = folder / f"IDEA-{number:03d}-{idealib.slug(words)}.md"
    rel = path.relative_to(vault_root).as_posix()
    if not apply:
        sys.stdout.write(f"compass idea: would add IDEA-{number:03d} at {rel} (dry-run; pass --apply to write)\n")
        return 0
    vaultlib.write_text_lf(path, text)
    sys.stdout.write(f"compass idea: added IDEA-{number:03d} at {rel}\n")
    return 0


def _find_by_id(vault_root, text):
    match = idealib.ID_PATTERN.match(text.strip())
    if not match:
        return None
    number = int(match.group(1))
    for idea in idealib.load_all(vault_root):
        if idea["number"] == number:
            return idea
    return None


def _status(args):
    positionals, values, apply, error = _parse(args, {"--words", "--source", "--led-to"})
    if error:
        return _fail(error)
    if len(positionals) != 2:
        return _fail("usage: compass idea status <IDEA-NNN> <status> [--words ... --source ...] [--led-to ...] [--apply]")
    ident, new_status = positionals
    words = values.get("--words")
    source = values.get("--source")
    link = values.get("--led-to")
    if new_status not in idealib.STATUSES:
        return _fail(f"unknown status {new_status!r}; one of {', '.join(idealib.STATUSES)}")
    if source is not None and words is None:
        return _fail("--source needs --words, the sentence to check against it")
    if link is not None and not link.strip():
        return _fail("--led-to must not be blank")
    if link is not None and idealib.single_line_error(link):
        return _fail(f"--led-to: {idealib.single_line_error(link)}")

    vault_root = vaultlib.find_vault_root()
    idea = _find_by_id(vault_root, ident)
    if idea is None:
        return _fail(f"no idea {ident}")
    if words is not None:
        problem = _checked_words(vault_root, words, source)
        if problem:
            return _fail(problem)

    old_status = idea["status"]
    reasons = []
    if link and link not in idea["led_to"]:
        reasons.append(f"led to {link}")
    if words is not None:
        reasons.append(f"his words: {_history_quote(words)}")
    if new_status == old_status and not reasons:
        sys.stdout.write(f"compass idea: {idea['id']} is already {new_status}; nothing changed\n")
        return 0
    today = datetime.date.today().isoformat()
    change = f"{old_status} -> {new_status}" if new_status != old_status else new_status
    entry = f"- {today}: {change} ({'; '.join(reasons) if reasons else 'status set'})"
    text = idealib.change(
        vaultlib.read_vault_text(idea["path"]), old_status, new_status,
        [link] if link else [], entry, today)
    if text is None:
        return _fail(f"{idea['id']} has no frontmatter")
    rel = idea["path"].relative_to(vault_root).as_posix()
    if not apply:
        sys.stdout.write(f"compass idea: would change {idea['id']} {change} in {rel} (dry-run; pass --apply to write)\n")
        return 0
    vaultlib.write_text_lf(idea["path"], text)
    sys.stdout.write(f"compass idea: {idea['id']} {change}\n")
    return 0


def _tokens(text):
    return {w for w in re.findall(r"\w+", text.lower()) if len(w) >= MIN_WORD_LENGTH}


def _show(idea):
    lines = [f"{idea['id']}  {idea['category']}  {idea['status']}"]
    words = idea["words"].split("\n")
    lines.append("  words: " + words[0])
    lines.extend("         " + line for line in words[1:])
    lines.append("  led_to: " + ", ".join(idea["led_to"]))
    lines.append("  led_to_note: " + idea["led_to_note"])
    lines.append("  history:")
    lines.extend("    " + line for line in idea["history"])
    return "\n".join(lines)


def _find(args):
    positionals, _, _, error = _parse(args, set())
    if error:
        return _fail(error)
    if len(positionals) != 1 or not positionals[0].strip():
        return _fail('usage: compass idea find "<text or IDEA-NNN>"')
    query = positionals[0]
    vault_root = vaultlib.find_vault_root()

    if idealib.ID_PATTERN.match(query.strip()):
        idea = _find_by_id(vault_root, query)
        if idea is None:
            sys.stdout.write(f"compass idea: no idea {query.strip()}\n")
        else:
            sys.stdout.write(_show(idea) + "\n")
        return 0

    ideas = idealib.load_all(vault_root)
    needle = query.lower()
    hits = [
        idea for idea in ideas
        if any(needle in field.lower() for field in (idea["words"], idea["led_to_note"], idea["title"]))
    ]
    if not hits:
        wanted = _tokens(query)
        scored = []
        for idea in ideas:
            shared = len(wanted & _tokens(" ".join((idea["words"], idea["led_to_note"], idea["title"]))))
            if shared:
                scored.append((-shared, idea["number"], idea))
        hits = [idea for _, _, idea in sorted(scored, key=lambda row: row[:2])[:MAX_RANKED]]
    if not hits:
        sys.stdout.write(f"compass idea: no idea matches {query!r}\n")
        return 0
    sys.stdout.write("\n\n".join(_show(idea) for idea in hits) + "\n")
    return 0


def run(args):
    handlers = {"add": _add, "status": _status, "find": _find}
    if not args or args[0] not in handlers:
        sys.stderr.write(USAGE)
        return 1
    return handlers[args[0]](args[1:])
