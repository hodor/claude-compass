"""Measurement helpers for control loops: the actuator's result event, the
domain sensor, the spend sums over a loop's ledger, and the judgment of a
change between two sensor readings.

The result event is the JSON envelope `claude -p --output-format json` prints.
Cost, turns, duration, subtype and `is_error` come from its top-level fields;
token totals are summed over every model in `modelUsage`, because the
top-level `usage` block is zeroed on a budget stop and differs from
`modelUsage` on a resumed session.

A domain sensor is an argv list run from the project root. It prints
`{"valid": true, "value": <number>, "items": [<identity>, ...]}`. Anything
else, including a hung or missing command, is an invalid `Reading` carrying a
reason; `run_sensor` never raises.

A judge is an agent that reads plain-language rules and answers with one JSON
line per violation, `{"rule", "file", "line"}`. `parse_judge_lines` keeps the
well-formed lines of one answer and counts the rest; `vote_findings` keeps the
findings that more than half of the configured runs report. The reading is
advisory and reaches no transition.

The context sensor reads what an install of a plugin tree adds to every
session: each `templates/rules/*.md` whole, and the `name`, `description` and
`when_to_use` frontmatter fields of each `skills/*/SKILL.md` and
`templates/agents/*.md`, plus the CLAUDE.md section the setup skill proposes
(item `skills/setup/SKILL.md#claude-md-addition`). A source is estimated at its
UTF-8 bytes divided by 4, rounded up, and the value sums the sources. Its
items are the sources' plugin-relative paths with forward slashes.

Given a usage folder, the context sensor also counts the text that sessions
load on demand: each `skills/*/SKILL.md` whole, every other text file inside a
skill folder, and each `templates/agents/*.md` whole. A usage folder holds one
`*.json` file per machine, `{"sessions": S, "loads": {<source>: <count>}}`, as
`scan_usage` writes it. A source's weight is its loads summed over the files
divided by their sessions summed; the value adds each source's tokens times
its weight to the always-loaded tokens and rounds once at the end. A source
with weight 0 adds nothing and is not an item.

`scan_usage` reads Claude Code session transcripts and counts, per source of
the plugin tree, the sessions that loaded it. The result names only plugin
sources and counts.

Ledger rows are dicts. A row may carry `ts` (ISO-8601) and `cost_usd`; rows
without `cost_usd` contribute nothing to a spend sum. Days are UTC calendar
days.
"""

import hashlib
import json
import math
import os
import re
import socket
import subprocess
import tempfile
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import proctree
import vaultlib

TOKEN_FIELDS = (
    ("input_tokens", "inputTokens"),
    ("output_tokens", "outputTokens"),
    ("cache_read_tokens", "cacheReadInputTokens"),
    ("cache_creation_tokens", "cacheCreationInputTokens"),
)
_KILL_WAIT_SECONDS = proctree.KILL_WAIT_SECONDS
UNKNOWN_DAY = "unknown"

CONTEXT_FIELDS = ("name", "description", "when_to_use")
CONTEXT_BYTES_PER_TOKEN = 4
SETUP_SKILL = "skills/setup/SKILL.md"
CLAUDE_MD_ITEM = SETUP_SKILL + "#claude-md-addition"
CLAUDE_MD_HEADING = re.compile(r"^#+\s.*CLAUDE\.md addition")
MARKDOWN_HEADING = re.compile(r"^#+\s")
BOM = "\ufeff"

SKILL_READ = re.compile(r"/\.claude/skills/([^/]+)/(.+)$")
AGENT_READ = re.compile(r"/\.claude/agents/([^/]+\.md)$")
NAMESPACE_PREFIX = "compass:"
MACHINE_HASH_LENGTH = 12
DEFAULT_SCAN_DAYS = 30


class NoResultEvent(ValueError):
    """The text holds no usable result event."""


class ResultEvent:
    def __init__(
        self,
        cost_usd,
        num_turns,
        duration_ms,
        subtype,
        is_error,
        result,
        input_tokens,
        output_tokens,
        cache_read_tokens,
        cache_creation_tokens,
    ):
        self.cost_usd = cost_usd
        self.num_turns = num_turns
        self.duration_ms = duration_ms
        self.subtype = subtype
        self.is_error = is_error
        self.result = result
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_tokens = cache_read_tokens
        self.cache_creation_tokens = cache_creation_tokens


class Reading:
    """A sensor reading. `usage` and `skipped` are set by the context sensor
    when it was given a usage folder: `usage` is "none" or a dict of machine
    and session counts, `skipped` names the usage files that did not parse."""

    def __init__(self, valid, value=None, items=(), reason=None, usage=None, skipped=()):
        self.valid = valid
        self.value = value
        self.items = list(items)
        self.reason = reason
        self.usage = usage
        self.skipped = list(skipped)

    def __repr__(self):
        return (
            f"Reading(valid={self.valid!r}, value={self.value!r}, "
            f"items={self.items!r}, reason={self.reason!r})"
        )


def _is_number(value):
    """True for a real int or float that float() can hold: not a bool, not
    NaN or infinite, and not an integer beyond the float range."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _int_field(obj, key):
    value = obj.get(key)
    return int(value) if _is_number(value) else 0


def parse_result(text):
    """Parse the stdout of `claude -p --output-format json` into a ResultEvent.
    Raises NoResultEvent when the text is not one complete result envelope
    with a numeric `total_cost_usd`."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError, RecursionError) as exc:
        raise NoResultEvent(f"no result event in the output ({exc})") from None
    if not isinstance(data, dict) or data.get("type") != "result":
        raise NoResultEvent("no result event in the output")
    cost = data.get("total_cost_usd")
    if not _is_number(cost) or cost < 0:
        raise NoResultEvent("no result event with a non-negative numeric total_cost_usd")

    totals = dict.fromkeys((name for name, _ in TOKEN_FIELDS), 0)
    model_usage = data.get("modelUsage")
    if isinstance(model_usage, dict):
        for usage in model_usage.values():
            if not isinstance(usage, dict):
                continue
            for name, key in TOKEN_FIELDS:
                totals[name] += _int_field(usage, key)

    result = data.get("result")
    subtype = data.get("subtype")
    return ResultEvent(
        cost_usd=float(cost),
        num_turns=_int_field(data, "num_turns"),
        duration_ms=_int_field(data, "duration_ms"),
        subtype=subtype if isinstance(subtype, str) else "",
        is_error=bool(data.get("is_error")),
        result=result if isinstance(result, str) else None,
        **totals,
    )


class JudgeParse:
    """The lines of one judge answer: `findings` as (rule, file, line) tuples
    in input order, `discarded` the count of lines that were not kept."""

    def __init__(self, findings, discarded):
        self.findings = list(findings)
        self.discarded = discarded


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


# A finding's file name is shorter than this many characters.
MAX_FILE_NAME = 300
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cs", "Zl", "Zp"})


def safe_file_name(name):
    """True when `name` can ride in the ledger and a prompt: a non-empty
    relative path inside the project (no root, drive or `..` component), under
    MAX_FILE_NAME characters, free of control characters, line and paragraph
    separators and lone surrogates."""
    if not isinstance(name, str) or not name or len(name) >= MAX_FILE_NAME:
        return False
    if any(unicodedata.category(c) in _UNSAFE_CATEGORIES for c in name):
        return False
    if name[0] in "/\\" or (len(name) > 1 and name[1] == ":"):
        return False
    return ".." not in name.replace("\\", "/").split("/")


def parse_judge_lines(text, rule_ids):
    """Parse a judge's final answer. A non-blank line is kept when it is a
    JSON object naming a rule of `rule_ids`, a `file` that passes
    `safe_file_name` and an integer `line`; every other non-blank line is
    discarded and counted. Lines end at `\n` after `\r\n` is normalised, and a
    leading byte order mark is dropped. Never raises."""
    known = set(rule_ids)
    findings, discarded = [], 0
    text = text if isinstance(text, str) else ""
    text = text.removeprefix("\ufeff").replace("\r\n", "\n")
    for raw in text.split("\n"):
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (ValueError, RecursionError):
            data = None
        if (
            isinstance(data, dict)
            and isinstance(data.get("rule"), str)
            and data["rule"] in known
            and safe_file_name(data.get("file"))
            and _is_int(data.get("line"))
        ):
            findings.append((data["rule"], data["file"], data["line"]))
        else:
            discarded += 1
    return JudgeParse(findings, discarded)


# Findings of one rule and file whose lines sit this close to a neighbour are
# one finding.
CLUSTER_GAP = 2


def _rule_order(rule):
    digits = rule[1:]
    return (0, int(digits), rule) if digits.isdigit() else (1, 0, rule)


def vote_findings(runs, configured):
    """Cluster the findings of the valid judge `runs` (each a list of
    (rule, file, line) tuples) and keep the clusters that more than half of
    `configured` runs report. Findings of one rule and file chain into a
    cluster while neighbouring lines sit within CLUSTER_GAP. A kept cluster
    is `{"rule", "file", "line", "votes"}`: `line` the lowest line, `votes`
    the number of distinct runs that reported into it."""
    grouped = {}
    for index, found in enumerate(runs):
        for rule, file, line in found:
            grouped.setdefault((rule, file), []).append((line, index))
    kept = []
    for (rule, file), points in grouped.items():
        points.sort()
        clusters, current, previous = [], [], None
        for line, index in points:
            if previous is not None and line - previous > CLUSTER_GAP:
                clusters.append(current)
                current = []
            current.append((line, index))
            previous = line
        clusters.append(current)
        for cluster in clusters:
            votes = len({index for _line, index in cluster})
            if votes * 2 > configured:
                kept.append(
                    {"rule": rule, "file": file, "line": cluster[0][0], "votes": votes}
                )
    kept.sort(key=lambda k: (_rule_order(k["rule"]), k["file"], k["line"]))
    return kept


def _invalid(reason):
    return Reading(valid=False, reason=reason)


def _reading_from_stdout(text, returncode):
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        shown = text.strip()[:200] or "empty output"
        return _invalid(f"sensor output is not JSON (exit {returncode}): {shown}")
    if not isinstance(data, dict):
        return _invalid("sensor output is not a JSON object")
    if data.get("valid") is not True:
        return _invalid("sensor reported valid: false")
    value = data.get("value")
    if not _is_number(value):
        return _invalid(f"sensor value is not a finite number: {value!r}")
    items = data.get("items")
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        return _invalid("sensor items is not a list of strings")
    return Reading(valid=True, value=float(value), items=items)


def run_sensor(command, cwd, timeout):
    """Run the sensor `command` (an argv list) from `cwd` and return its
    Reading. A sensor still running after `timeout` seconds has its process
    tree killed and reads as invalid."""
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **proctree.popen_kwargs(),
        )
    except (OSError, ValueError, TypeError, IndexError) as exc:
        return _invalid(f"could not start the sensor: {exc}")
    job = proctree.assign(proc)
    try:
        stdout, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proctree.kill(proc, job)
        try:
            proc.communicate(timeout=_KILL_WAIT_SECONDS)
        except (subprocess.TimeoutExpired, OSError, ValueError):
            pass
        return _invalid(f"sensor timed out after {timeout:g} seconds")
    except (OSError, ValueError) as exc:
        proctree.kill(proc, job)
        return _invalid(f"could not read the sensor output: {exc}")
    finally:
        proctree.release(job)
    return _reading_from_stdout(stdout.decode("utf-8", errors="replace"), proc.returncode)


def _estimate(byte_count):
    return -(-byte_count // CONTEXT_BYTES_PER_TOKEN)


def _context_sources(plugin):
    """Every (relative path, path) the context sensor reads under `plugin`,
    in path order: rules files, skill definitions and agent definitions."""
    patterns = ("templates/rules/*.md", "skills/*/SKILL.md", "templates/agents/*.md")
    found = {}
    for pattern in patterns:
        for path in plugin.glob(pattern):
            found[path.relative_to(plugin).as_posix()] = path
    return sorted(found.items())


def _claude_md_proposal(text):
    """The body of the first ```markdown fence under the heading that names the
    CLAUDE.md addition, or None when the heading's own section holds no closed
    fence. A heading line outside the fence ends the section."""
    lines = text.replace("\r\n", "\n").split("\n")
    heading = next((i for i, line in enumerate(lines) if CLAUDE_MD_HEADING.match(line)), None)
    if heading is None:
        return None
    opening = None
    for i in range(heading + 1, len(lines)):
        if lines[i].startswith("```markdown"):
            opening = i
            break
        if MARKDOWN_HEADING.match(lines[i]):
            return None
    if opening is None:
        return None
    for i in range(opening + 1, len(lines)):
        if lines[i].startswith("```"):
            return "".join(line + "\n" for line in lines[opening + 1 : i])
    return None


def _field_bytes(rel, raw):
    """UTF-8 bytes of the `name`, `description` and `when_to_use` values in
    the frontmatter of `raw`, and the decoded text without a leading byte
    order mark."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{rel}: {exc}") from exc
    if text.startswith(BOM):
        text = text[len(BOM):]
    data, error = vaultlib.parse_frontmatter_text(text)
    if error:
        raise ValueError(f"{rel}: {error}")
    total = 0
    for field in CONTEXT_FIELDS:
        value = data.get(field)
        if isinstance(value, str):
            total += len(value.encode("utf-8"))
    return total, text


def _load_usage(usage_dir):
    """Read every `*.json` in `usage_dir`. Returns (loads, sessions, machines,
    skipped): `loads` the per-source counts summed over the usable files,
    `sessions` their summed session counts, `machines` the number of files
    that held at least one session, `skipped` the names of files that are not
    a usage file. An absent folder yields nothing."""
    loads, sessions, machines, skipped = Counter(), 0, 0, []
    if usage_dir is None or not Path(usage_dir).is_dir():
        return loads, sessions, machines, skipped
    for path in sorted(Path(usage_dir).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            skipped.append(path.name)
            continue
        file_sessions = data.get("sessions") if isinstance(data, dict) else None
        file_loads = data.get("loads") if isinstance(data, dict) else None
        if (
            not _is_int(file_sessions)
            or file_sessions < 0
            or not isinstance(file_loads, dict)
            or not all(_is_int(n) and 0 <= n <= file_sessions for n in file_loads.values())
        ):
            skipped.append(path.name)
            continue
        if file_sessions == 0:
            continue
        sessions += file_sessions
        machines += 1
        loads.update(file_loads)
    return loads, sessions, machines, skipped


def _plain_key(key):
    """True when every part of the plugin-relative `key` is an ordinary name:
    not empty, not a dot hop, no backslash and no drive colon."""
    return all(
        part not in ("", ".", "..") and "\\" not in part and ":" not in part
        for part in key.split("/")
    )


def _loaded_on_demand(key):
    """True when `key` names a source the sessions load on demand: a file
    inside a skill folder or an agent definition."""
    if not _plain_key(key):
        return False
    parts = key.split("/")
    if parts[0] == "skills":
        return len(parts) >= 3
    return len(parts) == 3 and parts[:2] == ["templates", "agents"] and parts[2].endswith(".md")


def _weighted_tokens(plugin, loads, sessions, items):
    """The summed tokens of the on-demand sources each times its weight, and
    the keys appended to `items` for sources not yet listed. A key naming no
    file under `plugin`, or a file that is not UTF-8 text, adds nothing."""
    total = 0.0
    root = plugin.resolve()
    listed = set(items)
    for key in sorted(loads):
        if loads[key] <= 0 or not _loaded_on_demand(key):
            continue
        path = plugin / key
        if not path.is_file() or root not in path.resolve().parents:
            continue
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if b"\x00" in raw:
            continue
        total += _estimate(len(raw)) * loads[key] / sessions
        if key not in listed:
            listed.add(key)
            items.append(key)
    return total


def sense_context(plugin, usage_dir=None):
    """Read what an install of the plugin tree at `plugin` adds to every
    session and return a Reading. With `usage_dir`, the skill, agent and skill
    folder sources sessions load on demand are added, weighted by use. A
    missing directory or a source that cannot be read gives an invalid Reading
    carrying the reason."""
    if not plugin.is_dir():
        return _invalid(f"plugin directory not found: {plugin}")
    sources = _context_sources(plugin)
    if not sources:
        return _invalid(f"no context sources found under {plugin}")
    value = 0
    items = []
    try:
        for rel, path in sources:
            raw = path.read_bytes()
            if rel.startswith("templates/rules/"):
                value += _estimate(len(raw))
            else:
                size, text = _field_bytes(rel, raw)
                value += _estimate(size)
                if rel == SETUP_SKILL:
                    proposal = _claude_md_proposal(text)
                    if proposal is not None:
                        value += _estimate(len(proposal.encode("utf-8")))
                        items.append(CLAUDE_MD_ITEM)
            items.append(rel)
        if usage_dir is None:
            return Reading(valid=True, value=value, items=items)
        loads, sessions, machines, skipped = _load_usage(usage_dir)
        weighted = _weighted_tokens(plugin, loads, sessions, items) if sessions else 0.0
    except (OSError, ValueError) as exc:
        return _invalid(f"could not read a context source: {exc}")
    usage = {"machines": machines, "sessions": sessions} if sessions else "none"
    return Reading(valid=True, value=int(round(value + weighted)), items=items,
                   usage=usage, skipped=skipped)


def judge(before, after, direction):
    """Classify the change from `before` to `after` as "helpful", "neutral"
    or "harmful". Helpful: the value moved toward the target and no item is
    new. Harmful: the value moved away or any item is new, where items
    compare as a multiset. Neutral: anything else."""
    if direction not in ("down", "up"):
        raise ValueError(f"direction must be 'down' or 'up', got {direction!r}")
    if not (before.valid and after.valid):
        raise ValueError("judge needs two valid readings")
    delta = after.value - before.value
    if direction == "down":
        delta = -delta
    new_items = Counter(after.items) - Counter(before.items)
    if delta < 0 or new_items:
        return "harmful"
    if delta > 0:
        return "helpful"
    return "neutral"


def _utc(moment):
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _row_day(row):
    """The row's UTC day as "YYYY-MM-DD", or None when `ts` is absent or
    unreadable."""
    ts = row.get("ts")
    if not isinstance(ts, str):
        return None
    try:
        return _utc(datetime.fromisoformat(ts.replace("Z", "+00:00"))).strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        return None


def _row_cost(row):
    """The row's spend, or None when it carries no readable non-negative
    `cost_usd`. A negative cost is skipped so it can never cancel real spend."""
    cost = row.get("cost_usd")
    return float(cost) if _is_number(cost) and cost >= 0 else None


def spend_by_day(rows):
    """Sum `cost_usd` per UTC day ("YYYY-MM-DD"). The ledger is append-only
    and chronological, so a costed row whose `ts` is absent or unreadable
    takes the day of the nearest preceding row with a readable `ts`; with no
    such row it is summed under UNKNOWN_DAY. Rows without a readable cost are
    skipped."""
    days = {}
    last_day = None
    for row in rows:
        day = _row_day(row)
        if day is not None:
            last_day = day
        cost = _row_cost(row)
        if cost is None:
            continue
        key = day or last_day or UNKNOWN_DAY
        days[key] = days.get(key, 0.0) + cost
    return days


def spend_today(rows, now):
    """Spend on the UTC day that contains `now` (a naive `now` counts as UTC),
    plus any spend under UNKNOWN_DAY, which cannot be placed on a day and so
    counts against every day."""
    days = spend_by_day(rows)
    return days.get(_utc(now).strftime("%Y-%m-%d"), 0.0) + days.get(UNKNOWN_DAY, 0.0)


def spend_lifetime(rows):
    """Sum `cost_usd` over every row that carries a readable one."""
    return sum(cost for cost in map(_row_cost, rows) if cost is not None)


def machine_id():
    """A 12 hex digit hash of this machine's host name."""
    digest = hashlib.sha256(socket.gethostname().encode("utf-8")).hexdigest()
    return digest[:MACHINE_HASH_LENGTH]


def _bare(name):
    """`name` without a leading `compass:` namespace."""
    name = name.strip()
    return name[len(NAMESPACE_PREFIX):] if name.startswith(NAMESPACE_PREFIX) else name


def _source_exists(plugin, key, cache):
    """True when `key` is a plugin-relative path of a file under `plugin`."""
    if key not in cache:
        cache[key] = _plain_key(key) and (plugin / key).is_file()
    return cache[key]


def _block_keys(block):
    """The plugin source keys one tool_use block loads: zero or one."""
    name, tool_input = block.get("name"), block.get("input")
    if not isinstance(tool_input, dict):
        return []
    if name == "Skill" and isinstance(tool_input.get("skill"), str):
        return [f"skills/{_bare(tool_input['skill'])}/SKILL.md"]
    if name in ("Agent", "Task") and isinstance(tool_input.get("subagent_type"), str):
        return [f"templates/agents/{_bare(tool_input['subagent_type'])}.md"]
    if name == "Read" and isinstance(tool_input.get("file_path"), str):
        path = tool_input["file_path"].replace("\\", "/")
        skill = SKILL_READ.search(path)
        if skill:
            return [f"skills/{skill.group(1)}/{skill.group(2)}"]
        agent = AGENT_READ.search(path)
        if agent:
            return [f"templates/agents/{agent.group(1)}"]
    return []


def _line_trace(entry):
    """(keys, names_compass) for one transcript entry: the source keys its
    tool_use blocks load, and whether a tool_use or a hook entry names
    compass."""
    keys, names = [], False
    if entry.get("type") == "attachment":
        attachment = entry.get("attachment")
        kind = attachment.get("type") if isinstance(attachment, dict) else None
        if isinstance(kind, str) and "hook" in kind.lower():
            names = "compass" in json.dumps(attachment).lower()
        return keys, names
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if entry.get("type") != "assistant" or not isinstance(content, list):
        return keys, names
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        keys.extend(_block_keys(block))
        if "compass" in json.dumps(block.get("input", "")).lower():
            names = True
    return keys, names


def _scan_session(path, plugin, cache):
    """(keys, traced, bad) for one transcript: the plugin source keys the
    session loaded, whether Compass was in it, and the count of lines that
    could not be read (one for a file with no readable line at all)."""
    keys, traced, bad, good = set(), False, 0, 0
    with open(path, "rb") as handle:
        for raw in handle:
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw.decode("utf-8"))
            except (ValueError, RecursionError):
                bad += 1
                continue
            good += 1
            if not isinstance(entry, dict):
                continue
            found, names = _line_trace(entry)
            keys.update(key for key in found if _source_exists(plugin, key, cache))
            traced = traced or names
    if good == 0 and bad:
        bad = 1
    return keys, traced or bool(keys), bad


def scan_usage(projects, plugin, days=DEFAULT_SCAN_DAYS, now=None):
    """Count, over the `*.jsonl` transcripts under `projects` modified within
    `days`, the sessions Compass was in and the sessions that loaded each
    source of the plugin tree at `plugin`. Returns (sessions, loads, skipped):
    `loads` maps a plugin-relative source path to its session count and holds
    only paths of files that exist under `plugin`; `skipped` counts the lines
    and files that could not be read."""
    cutoff = (time.time() if now is None else now) - days * 86400
    loads, sessions, skipped, cache = Counter(), 0, 0, {}
    for path in sorted(Path(projects).rglob("*.jsonl")):
        try:
            if not path.is_file() or path.stat().st_mtime < cutoff:
                continue
            keys, traced, bad = _scan_session(path, plugin, cache)
        except OSError:
            skipped += 1
            continue
        skipped += bad
        if traced:
            sessions += 1
            loads.update(keys)
    return sessions, dict(sorted(loads.items())), skipped


def write_usage(out, sessions, loads, days):
    """Write the usage file at `out` atomically and return its content: the
    machine hash, the scan time, the window, the session count and the loads."""
    data = {
        "machine": machine_id(),
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "days": days,
        "sessions": sessions,
        "loads": loads,
    }
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(out.parent), prefix=".usage-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(tmp, out)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return data
