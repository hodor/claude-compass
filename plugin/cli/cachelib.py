"""Read-only prompt-cache readers over Claude Code session transcripts.

A transcript holds one `assistant` record per content block of a model
request, all sharing a `requestId` and carrying the request's `usage`
(`input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`
and a `cache_creation` split into 5-minute and 1-hour writes). Each request
is also described by an `api-request` record (`id`, `params`, `shapeHash`, and
a `tail` list of `api-request-blob` hashes), linked to the assistant record
through its `requestRef`. A subagent keeps its own transcript under
`<session>/subagents/agent-*.jsonl` with an `agent-*.meta.json` beside it.

Every reader opens transcripts in binary read mode, skips records it cannot
make sense of, and returns objects holding counts, kinds and times only: no
path, session id, working directory, request id or message text. Standard
library only.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import sessionslib

KINDS = ("system-or-tools", "instruction-files", "git-snapshot", "memory-index",
         "environment", "other", "none", "unknown")
INSTRUCTION_FILE_KINDS = ("project-claude-md", "rule-file", "user-claude-md", "memory-index")

_USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
_INSTRUCTION_MARK = "Codebase and user instructions are shown below"
_BLOCK_CLOSE = "</system-reminder>"
_FILE_HEADER = re.compile(r"^Contents of (.*) \((.*)\):[ \t]*$", re.MULTILINE)


@dataclass(frozen=True)
class Request:
    timestamp: "str | None"
    model: "str | None"
    input_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    ephemeral_5m_input_tokens: "int | None"
    ephemeral_1h_input_tokens: "int | None"


@dataclass(frozen=True)
class SessionSummary:
    first: "Request | None"
    whole_hit: "float | None"
    request_count: int
    entrypoint: "str | None"
    started_at: "str | None"
    ended_at: "str | None"


@dataclass(frozen=True)
class SubagentSummary:
    agent_type: str
    first: "Request | None"
    whole_hit: "float | None"
    request_count: int
    started_at: "str | None"
    minutes_since_previous_same_type: "float | None"


@dataclass(frozen=True)
class PairComparison:
    gap_minutes: "float | None"
    comparable: bool
    first_difference: str
    instruction_file_kind: "str | None"


@dataclass(frozen=True)
class LedgerTotals:
    run_count: int
    cache_read_tokens: int
    cache_creation_tokens: int
    input_tokens: int


# ---- primitives -----------------------------------------------------------


def _parse_time(value):
    """A timezone-aware datetime for an ISO timestamp string, else None."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _time_string(value):
    """The timestamp string itself when it parses, else None."""
    return value if _parse_time(value) is not None else None


def _records(path):
    """Parsed records of a JSONL file; an unreadable file yields nothing."""
    try:
        yield from sessionslib.records(path)
    except (OSError, ValueError):
        return


def _token_count(value):
    """The int a usage value counts as: a bool or None is 0, a number or an
    integer string its int value; anything else, and any negative value,
    raises ValueError."""
    if isinstance(value, bool) or value is None:
        return 0
    try:
        count = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("non-numeric usage value") from None
    if count < 0:
        raise ValueError("negative usage value")
    return count


def _split_value(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _request_of(record):
    """The (request id, Request) an assistant record carries, or None when it
    has no usable request id, no usage, a non-numeric usage value, or only
    zero usage."""
    if record.get("type") != "assistant":
        return None
    request_id = record.get("requestId")
    if not isinstance(request_id, str) or not request_id:
        return None
    message = record.get("message")
    usage = message.get("usage") if isinstance(message, dict) else None
    if not isinstance(usage, dict):
        return None
    try:
        counts = [_token_count(usage.get(key)) for key in _USAGE_KEYS]
    except ValueError:
        return None
    if not any(counts):
        return None
    split = usage.get("cache_creation")
    split = split if isinstance(split, dict) else {}
    model = message.get("model")
    return request_id, Request(
        timestamp=_time_string(record.get("timestamp")),
        model=model if isinstance(model, str) else None,
        input_tokens=counts[0],
        cache_creation_input_tokens=counts[1],
        cache_read_input_tokens=counts[2],
        ephemeral_5m_input_tokens=_split_value(split.get("ephemeral_5m_input_tokens")),
        ephemeral_1h_input_tokens=_split_value(split.get("ephemeral_1h_input_tokens")),
    )


class _Scan:
    """One pass over a transcript: its deduplicated requests, the requestRef
    of the first, the first parseable timestamp, the first entrypoint, and
    the `api-request` records by id."""

    def __init__(self, path):
        self.requests = []
        self.first_ref = None
        self.started = None
        self.entrypoint = None
        self.api = {}
        seen = set()
        for record in _records(path):
            if self.started is None:
                self.started = _time_string(record.get("timestamp"))
            entry = record.get("entrypoint")
            if self.entrypoint is None and isinstance(entry, str) and entry:
                self.entrypoint = entry
            kind = record.get("type")
            if kind == "api-request":
                ident = record.get("id")
                if isinstance(ident, str):
                    self.api[ident] = record
            elif kind == "assistant":
                found = _request_of(record)
                if found is None or found[0] in seen:
                    continue
                seen.add(found[0])
                if not self.requests:
                    ref = record.get("requestRef")
                    self.first_ref = ref if isinstance(ref, str) else None
                self.requests.append(found[1])


# ---- requests and hit ratios ----------------------------------------------


def requests(transcript):
    """One Request per distinct `requestId` of a transcript's assistant
    records, in file order, from the first record of each id. Sidechain
    records count: every record of a subagent transcript is one."""
    return _Scan(transcript).requests


def hit_ratio(reqs):
    """Cache-read tokens over read + creation + input tokens, weighted by
    tokens across `reqs`; None when there are no tokens."""
    read = sum(r.cache_read_input_tokens for r in reqs)
    total = read + sum(r.cache_creation_input_tokens + r.input_tokens for r in reqs)
    return read / total if total else None


def first_read_share(firsts):
    """Share of the given first requests that read any cache; None when there
    are none. None entries are ignored."""
    firsts = [r for r in firsts if r is not None]
    if not firsts:
        return None
    return sum(1 for r in firsts if r.cache_read_input_tokens > 0) / len(firsts)


# ---- sessions and subagents ----------------------------------------------


def _summary_of(scan):
    reqs = scan.requests
    return reqs[0] if reqs else None, hit_ratio(reqs), len(reqs)


def session_summary(transcript):
    scan = _Scan(transcript)
    first, whole, count = _summary_of(scan)
    return SessionSummary(
        first=first, whole_hit=whole, request_count=count, entrypoint=scan.entrypoint,
        started_at=scan.started, ended_at=scan.requests[-1].timestamp if scan.requests else None)


def _agent_type(path):
    meta = path.with_name(path.name[: -len(".jsonl")] + ".meta.json")
    try:
        data = json.loads(meta.read_bytes().decode("utf-8-sig"))
    except (OSError, ValueError, RecursionError):
        return "unknown"
    kind = data.get("agentType") if isinstance(data, dict) else None
    return kind if isinstance(kind, str) and kind else "unknown"


def subagent_summaries(transcript):
    """One SubagentSummary per subagent transcript of a session, ordered by
    start time; `minutes_since_previous_same_type` is the start-to-start
    distance to the previous subagent of the same type."""
    try:
        paths = sessionslib.subagent_transcripts(transcript)
    except OSError:
        return []
    rows = []
    for path in paths:
        scan = _Scan(path)
        rows.append((_agent_type(path), scan, _parse_time(scan.started)))
    rows.sort(key=lambda row: (row[2] is None, row[2].timestamp() if row[2] else 0.0))
    previous = {}
    out = []
    for agent_type, scan, started in rows:
        before = previous.get(agent_type)
        minutes = (started - before).total_seconds() / 60 if started and before else None
        if started:
            previous[agent_type] = started
        first, whole, count = _summary_of(scan)
        out.append(SubagentSummary(
            agent_type=agent_type, first=first, whole_hit=whole, request_count=count,
            started_at=scan.started, minutes_since_previous_same_type=minutes))
    return out


# ---- pair comparison -------------------------------------------------------


def _blobs(path, hashes):
    """The `api-request-blob` messages of a transcript for the given hashes."""
    found = {}
    for record in _records(path):
        digest = record.get("hash")
        if record.get("type") == "api-request-blob" and isinstance(digest, str) and digest in hashes:
            message = record.get("message")
            if isinstance(message, dict):
                found[record["hash"]] = message
    return found


def _block_texts(message):
    """The content blocks of a blob message as comparable strings."""
    content = message.get("content")
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    texts = []
    for block in content:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            texts.append(block["text"])
        elif isinstance(block, str):
            texts.append(block)
        else:
            texts.append(json.dumps(block, sort_keys=True, default=str))
    return texts


def _classify(role, text):
    if _INSTRUCTION_MARK in text:
        return "instruction-files"
    if "# gitStatus" in text:
        return "git-snapshot"
    if "# Memory Index" in text:
        return "memory-index"
    if role == "system" and text.startswith("# Environment"):
        return "environment"
    return "other"


def _instruction_files(text):
    """(path, description, body) per `Contents of <path> (<description>):`
    section of an instruction block, in text order. A body excludes the
    whitespace around it and the block's closing tag."""
    marks = list(_FILE_HEADER.finditer(text))
    files = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        body = text[mark.end():end].strip()
        if body.endswith(_BLOCK_CLOSE):
            body = body[: -len(_BLOCK_CLOSE)].rstrip()
        files.append((mark.group(1), mark.group(2), body))
    return files


def _file_kind(path, description):
    if description.startswith("user's auto-memory"):
        return "memory-index"
    if path.endswith("CLAUDE.md"):
        return "user-claude-md" if description.startswith("user's private") else "project-claude-md"
    return "rule-file"


def _instruction_file_kind(before, after):
    """Kind of the first instruction file, in text order, that differs
    between two instruction blocks, matching files by path; a file that is
    absent or changed on the later side is found in the earlier side's order,
    then a file only the later side holds. None when no file differs."""
    old, new = _instruction_files(before), _instruction_files(after)
    newer = _by_identity(new)
    for key, (path, description, body) in _by_identity(old).items():
        if newer.get(key) != (path, description, body):
            return _file_kind(path, description)
    older = _by_identity(old)
    for key, (path, description, _) in newer.items():
        if key not in older:
            return _file_kind(path, description)
    return None


def _by_identity(files):
    """Instruction files keyed by path and occurrence number, in text order,
    so a file is matched with its counterpart however the list around it
    changed."""
    keyed = {}
    seen = {}
    for path, description, body in files:
        seen[path] = seen.get(path, 0) + 1
        keyed[(path, seen[path])] = (path, description, body)
    return keyed


def _blob_difference(old, new):
    """(kind, file kind) of the first differing content block of two blob
    messages, or None when they hold the same blocks."""
    role = new.get("role") if isinstance(new.get("role"), str) else old.get("role")
    mine, theirs = _block_texts(old), _block_texts(new)
    for index in range(max(len(mine), len(theirs))):
        a = mine[index] if index < len(mine) else None
        b = theirs[index] if index < len(theirs) else None
        if a == b:
            continue
        kinds = [_classify(role, text) for text in (b, a) if text is not None]
        kind = next((k for k in kinds if k != "other"), "other")
        file_kind = None
        if kind == "instruction-files":
            file_kind = _instruction_file_kind(a or "", b or "")
        return kind, file_kind
    return None


def _walk_tails(earlier, later, old_tail, new_tail):
    """(kind, file kind) of the first block that differs between two `tail`
    lists, "none" when no block differs, "unknown" when a needed blob is
    missing."""
    for index in range(max(len(old_tail), len(new_tail))):
        a = old_tail[index] if index < len(old_tail) else None
        b = new_tail[index] if index < len(new_tail) else None
        if a == b:
            continue
        old_blobs = _blobs(earlier, {a}) if a is not None else {}
        new_blobs = _blobs(later, {b}) if b is not None else {}
        if (a is not None and a not in old_blobs) or (b is not None and b not in new_blobs):
            return "unknown", None
        difference = _blob_difference(old_blobs.get(a, {}), new_blobs.get(b, {}))
        if difference is not None:
            return difference
    return "none", None


def _tail(api):
    tail = api.get("tail")
    if isinstance(tail, list) and all(isinstance(h, str) for h in tail):
        return tail
    return None


def compare_first_requests(earlier, later):
    """Compare the first request of two transcripts: whether they are
    comparable (same params and shape) and the first block that differs."""
    old, new = _Scan(earlier), _Scan(later)
    ended = _parse_time(old.requests[-1].timestamp) if old.requests else None
    started = _parse_time(new.started)
    gap = (started - ended).total_seconds() / 60 if ended and started else None
    old_api = old.api.get(old.first_ref) if old.requests else None
    new_api = new.api.get(new.first_ref) if new.requests else None
    if old_api is None or new_api is None:
        return PairComparison(gap, False, "unknown", None)
    comparable = (old_api.get("params") == new_api.get("params")
                  and old_api.get("shapeHash") == new_api.get("shapeHash"))
    if old_api.get("shapeHash") != new_api.get("shapeHash"):
        return PairComparison(gap, comparable, "system-or-tools", None)
    old_tail, new_tail = _tail(old_api), _tail(new_api)
    if old_tail is None or new_tail is None:
        return PairComparison(gap, comparable, "unknown", None)
    kind, file_kind = _walk_tails(earlier, later, old_tail, new_tail)
    return PairComparison(gap, comparable, kind, file_kind)


# ---- loop ledger -----------------------------------------------------------


def _ledger_count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def ledger_totals(loop_dir):
    """Run count and cache-read, cache-creation and input token sums over the
    `run` rows of `<loop_dir>/ledger.jsonl`."""
    runs = read = creation = inp = 0
    for row in _records(Path(loop_dir) / "ledger.jsonl"):
        if row.get("type") != "run":
            continue
        runs += 1
        read += _ledger_count(row.get("cache_read_tokens"))
        creation += _ledger_count(row.get("cache_creation_tokens"))
        inp += _ledger_count(row.get("input_tokens"))
    return LedgerTotals(runs, read, creation, inp)
