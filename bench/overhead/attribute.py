"""Reconciliation of a pilot's token records and probes of the split by source.

Reconciliation. `reconcile_build` sets three totals of one build side by side:
the run log's (the counting rule: the last `result` totals of the build's
session), the sessions' own `cost-state` totals, and the deduplicated sum of
assistant records over the session, its `subagents/` files and (apart from the
build) its capture workers. A response written as several records, or repeated
in a subagent file, is counted once. The gaps between the totals are given
names the transcripts show:

- unfinished turn: a session killed at a cap writes no `cost-state`, and its
  last turn is in the transcript but never reached a `result` event; the tokens
  after the last end-of-turn marker.
- auxiliary request: a model's input and output tokens in `cost-state` that no
  assistant record carries (a request the harness made on the model's behalf,
  such as a page summary), while the model's cache tokens match.
- auxiliary request (inferred): the same gap in a build whose sessions wrote no
  `cost-state` to show it, named only when the build made web calls.
- compaction: a gap beside a `compact_boundary` record.
- resume: records above the session's own totals in a transcript that holds
  records of two session ids.

What remains is the unattributed gap; a build agrees when it is within
`TOLERANCE` of the logged total in weighted and raw tokens.

Request text. `rebuild_requests` rebuilds each request of a transcript (its
system text, tool definitions and messages, from the stored request chain) and
sets its UTF-8 bytes beside the API's input count for the response.

Ablation. `run_ablation` runs `claude -p "hi"` in a bare project and in
projects holding one file each (a rules file, a skill, an agent definition) and
gives each file's real first-request tokens beside its bytes divided by 4.

    python attribute.py measure --run-log LOG
    python attribute.py ablate
    python attribute.py otel
    python attribute.py report --report FILE
    python attribute.py discard --report FILE [--keep PROJECT ...]
"""

import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import drive
import grade
import launch
import records
import sandbox
import token_profile

UNFINISHED_TURN = "unfinished turn"
AUXILIARY_REQUEST = "auxiliary request"
AUXILIARY_INFERRED = "auxiliary request (inferred)"
COMPACTION = "compaction"
RESUME = "resume"

HEADING = "### Reconciliation and the split by source"
DISCARD_PENDING = "- Pilot projects discarded: pending."
_DISCARD_LINE = re.compile(r"^- Pilot projects discarded:.*$", re.MULTILINE)

# Share of the logged total a build's unattributed gap may reach and still agree.
TOLERANCE = 0.005
END_OF_TURN_MARKERS = ("stop_hook_summary", "turn_duration")
WEB_TOOLS = frozenset({"WebFetch", "WebSearch"})
INPUT_KINDS = ("input", "output")
CACHE_KINDS = ("cache_read", "cache_write")
_REMINDER_WRAPPER = re.compile(r"^\s*<system-reminder>\s*|\s*</system-reminder>\s*$")
_EVENT_NAME = re.compile(r"claude_code\.[a-z_]+(?:\.[a-z_]+)*")
OTEL_ENVIRONMENT = {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "console",
    "OTEL_LOGS_EXPORTER": "console",
    "OTEL_METRIC_EXPORT_INTERVAL": "1000",
    "OTEL_LOGS_EXPORT_INTERVAL": "1000",
    "OTEL_LOG_TOOL_DETAILS": "1",
}
CALL_TIMEOUT_SECONDS = 600
CALL_BUDGET_USD = "2"


class AttributionError(Exception):
    """A measurement or a closing step that cannot go ahead."""


# transcripts


def _top_level(folder):
    return sorted(Path(folder).glob("*.jsonl"))


def _subagent_files(folder, stem):
    return sorted((Path(folder) / stem / "subagents").glob("*.jsonl"))


def _totals(models):
    """(raw tokens, weighted tokens) of a {model: kinds} table."""
    raw = sum(kinds["input"] + kinds["cache_read"] + kinds["cache_write"] + kinds["output"] for kinds in models.values())
    return raw, sum(kinds["weighted"] for kinds in models.values())


def _family(folder, path, lines, kind, cut=None):
    """({model: kinds}, responses) of a top-level session and its subagent
    files. `cut` = (end index, timestamp, strict) keeps the first `end` lines
    and the subagent lines stamped no later (strictly earlier when `strict`)."""
    if cut is None:
        parent_lines = lines
    else:
        parent_lines = lines[: cut[0]]
    first = token_profile.profile_session(parent_lines, kind)
    parent_ids = frozenset(first["counted_ids"])
    family = [first]
    for agent_path in _subagent_files(folder, path.stem):
        agent_lines = token_profile._read_lines(agent_path)
        if cut is not None and cut[1] is not None:
            agent_lines = [
                item for item in agent_lines
                if not item.get("timestamp") or (item["timestamp"] < cut[1] if cut[2] else item["timestamp"] <= cut[1])
            ]
        elif cut is not None:
            agent_lines = []
        agent = token_profile._agent_type(agent_path.with_name(agent_path.stem + ".meta.json"))
        family.append(token_profile.profile_session(agent_lines, f"subagent:{agent}", skip_ids=parent_ids))
    return token_profile._family_models(family), sum(session["requests"] for session in family)


def _last_turn_end(lines):
    """(end index, timestamp, strict) of the last finished turn of a session:
    just after its last end-of-turn marker, else just before its last typed
    message."""
    for index in range(len(lines) - 1, -1, -1):
        item = lines[index]
        if item.get("type") == "system" and item.get("subtype") in END_OF_TURN_MARKERS:
            return index + 1, item.get("timestamp"), False
    for index in range(len(lines) - 1, -1, -1):
        if token_profile._typed_messages([lines[index]]) == 1:
            return index, lines[index].get("timestamp"), True
    return 0, None, True


def _cost_state(lines):
    found = None
    for item in lines:
        if item.get("type") == "cost-state" and isinstance(item.get("modelUsage"), dict):
            found = item
    return found


def _web_calls(lines, seen):
    for item in lines:
        if item.get("type") != "assistant":
            continue
        for block in (item.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") in WEB_TOOLS:
                seen.add(block.get("id") or id(block))


def _weigh_kinds(table):
    """Weighted total of a {model: {kind: tokens}} table (an unpriced model weighs 0)."""
    return records.weigh({model: {kind: kinds.get(kind, 0) for kind in records.KINDS} for model, kinds in table.items()})[0]


def _raw_kinds(table):
    return sum(sum(kinds.values()) for kinds in table.values())


def _distinct_session_ids(lines):
    return {item["sessionId"] for item in lines if item.get("type") in ("user", "assistant") and item.get("sessionId")}


def _residual(reported, counted):
    """{model: {kind: reported - counted}} over every model and kind either holds."""
    table = {}
    for model in set(reported) | set(counted):
        table[model] = {
            kind: reported.get(model, {}).get(kind, 0) - counted.get(model, {}).get(kind, 0) for kind in records.KINDS
        }
    return table


def _named_gaps(lines, residual):
    """[(cause, {model: {kind: tokens}}, sign)] for one session's residual
    (its `cost-state` minus its counted records); sign is the direction the
    cause moves the records relative to the logged total."""
    positive = {model: {k: max(v, 0) for k, v in kinds.items()} for model, kinds in residual.items()}
    negative = {model: {k: max(-v, 0) for k, v in kinds.items()} for model, kinds in residual.items()}
    named = []
    compacted = any(item.get("type") == "system" and item.get("subtype") == "compact_boundary" for item in lines)
    if compacted:
        named.append((COMPACTION, positive, -1))
    else:
        auxiliary = {
            model: kinds for model, kinds in positive.items()
            if sum(kinds.values()) > 0 and all(kinds[kind] == 0 for kind in CACHE_KINDS)
        }
        if auxiliary:
            named.append((AUXILIARY_REQUEST, auxiliary, -1))
    if any(sum(kinds.values()) for kinds in negative.values()) and len(_distinct_session_ids(lines)) > 1:
        named.append((RESUME, negative, 1))
    return named


def reconcile_build(folder, logged):
    """Three totals of one build, the causes of their gaps and what is left.

    `folder` is the build's transcript folder; `logged` is {"weighted", "raw"}
    from the run log. Raises ValueError when the folder holds no session.
    """
    folder = Path(folder)
    paths = _top_level(folder)
    if not paths:
        raise ValueError("the folder holds no session transcript")

    records_models, responses = {}, 0
    cost_models, reporting, missing = {}, 0, 0
    causes = {}
    worker_raw = worker_weighted = workers = 0
    unfinished_raw = unfinished_weighted = 0
    web = set()
    signed = {"raw": 0, "weighted": 0.0}

    def add_cause(name, table, sign):
        raw = _raw_kinds(table)
        weighted = _weigh_kinds(table)
        entry = causes.setdefault(name, {"cause": name, "weighted": 0.0, "raw": 0})
        entry["weighted"] += weighted
        entry["raw"] += raw
        signed["raw"] += sign * raw
        signed["weighted"] += sign * weighted

    for path in paths:
        lines = token_profile._read_lines(path)
        kind = token_profile.session_kind(lines)
        models, count = _family(folder, path, lines, kind)
        if kind == "capture-worker":
            raw, weighted = _totals(models)
            workers += 1
            worker_raw += raw
            worker_weighted += weighted
            continue
        _web_calls(lines, web)
        for agent_path in _subagent_files(folder, path.stem):
            _web_calls(token_profile._read_lines(agent_path), web)
        for model, kinds in models.items():
            token_profile._add(records_models, model, kinds)
        responses += count
        state = _cost_state(lines)
        if state is None:
            missing += 1
            cut = _last_turn_end(lines)
            kept, _ = _family(folder, path, lines, kind, cut=cut)
            full_raw, full_weighted = _totals(models)
            kept_raw, kept_weighted = _totals(kept)
            unfinished_raw += full_raw - kept_raw
            unfinished_weighted += full_weighted - kept_weighted
            continue
        reporting += 1
        reported = records._result_usage(state)
        for model, kinds in reported.items():
            entry = cost_models.setdefault(model, dict.fromkeys(records.KINDS, 0))
            for name in records.KINDS:
                entry[name] += kinds[name]
        counted = {model: {k: kinds[k] for k in records.KINDS} for model, kinds in models.items()}
        for name, table, sign in _named_gaps(lines, _residual(reported, counted)):
            add_cause(name, table, sign)

    records_raw, records_weighted = _totals(records_models)
    if unfinished_raw or unfinished_weighted:
        causes[UNFINISHED_TURN] = {"cause": UNFINISHED_TURN, "weighted": unfinished_weighted, "raw": unfinished_raw}
        signed["raw"] += unfinished_raw
        signed["weighted"] += unfinished_weighted

    gap_raw = records_raw - logged["raw"] - signed["raw"]
    if missing and web and gap_raw < 0:
        causes[AUXILIARY_INFERRED] = {"cause": AUXILIARY_INFERRED, "weighted": 0.0, "raw": -gap_raw}
        signed["raw"] += gap_raw
    unattributed = {
        "weighted": records_weighted - logged["weighted"] - signed["weighted"],
        "raw": records_raw - logged["raw"] - signed["raw"],
    }
    agrees = (
        abs(unattributed["weighted"]) <= TOLERANCE * max(logged["weighted"], 1)
        and abs(unattributed["raw"]) <= TOLERANCE * max(logged["raw"], 1)
    )
    return {
        "logged": {"weighted": logged["weighted"], "raw": logged["raw"]},
        "cost_state": {
            "weighted": _weigh_kinds(cost_models) if reporting else None,
            "raw": _raw_kinds(cost_models) if reporting else None,
            "sessions": reporting,
            "missing": missing,
        },
        "records": {"weighted": records_weighted, "raw": records_raw, "responses": responses},
        "workers": {"sessions": workers, "weighted": worker_weighted, "raw": worker_raw},
        "causes": list(causes.values()),
        "unattributed": unattributed,
        "agrees": agrees,
        "web_calls": len(web),
    }


# attachments


def attachment_kinds(folders):
    """{kind: {"reached", "empty", "chars"}} over every attachment record of the
    sessions and subagent files in `folders`: an attachment reached the model
    when its rendering holds text."""
    found = {}
    for folder in folders:
        folder = Path(folder)
        paths = []
        for path in _top_level(folder):
            paths.append(path)
            paths.extend(_subagent_files(folder, path.stem))
        for path in paths:
            for item in token_profile._read_lines(path):
                if item.get("type") != "attachment":
                    continue
                attachment = item.get("attachment")
                name = attachment.get("type") if isinstance(attachment, dict) else None
                kind = name if isinstance(name, str) and token_profile._SKILL_NAME.fullmatch(name) else "unknown"
                entry = found.setdefault(kind, {"reached": 0, "empty": 0, "chars": 0})
                chars = token_profile._chars(item.get("rendered"))
                if chars > 0:
                    entry["reached"] += 1
                    entry["chars"] += chars
                else:
                    entry["empty"] += 1
    return found


# request text


def _message_hash(message):
    text = json.dumps(message, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _segments(content):
    """The strings one message's content shows the model; None when it holds an
    image or a document, whose bytes say nothing about its tokens."""
    if isinstance(content, str):
        return [content] if content else []
    if not isinstance(content, list):
        return []
    out = []
    for block in content:
        if isinstance(block, str):
            out.append(block)
        elif isinstance(block, dict):
            kind = block.get("type")
            if kind in ("image", "document"):
                return None
            if kind == "text":
                out.append(block.get("text") or "")
            elif kind == "thinking":
                out.append(block.get("thinking") or "")
            elif kind == "tool_use":
                arguments = json.dumps(block.get("input", {}), ensure_ascii=False, sort_keys=True)
                out.append(f"{block.get('name', '')} {arguments}")
            elif kind == "tool_result":
                inner = _segments(block.get("content"))
                if inner is None:
                    return None
                out.extend(inner)
            else:
                out.append(json.dumps(block, ensure_ascii=False, sort_keys=True))
    return [text for text in out if text]


def _resolve(request_id, requests, lookup, memo, replies):
    """The message list of a request: its base's first `keep` messages and its
    tail; None when any link of the chain is missing or loops. A tail message
    with no stored copy that comes first after a base takes the response
    records of the base request, which is the assistant message it repeats."""
    chain = []
    current = request_id
    while current is not None and current not in memo and current not in chain:
        chain.append(current)
        request = requests.get(current)
        current = request.get("base") if request else None
    looped = current is not None and current in chain
    prior = [] if current is None else memo.get(current)
    for item in reversed(chain):
        request = requests.get(item)
        result = None
        if request is not None and prior is not None and not looped:
            keep = request.get("keep", 0)
            if isinstance(keep, int) and not isinstance(keep, bool) and 0 <= keep <= len(prior):
                tail = []
                for position, digest in enumerate(request.get("tail") or []):
                    message = lookup.get(digest)
                    if message is None and position == 0:
                        message = replies.get(request.get("base"))
                    tail.append(message)
                if all(message is not None for message in tail):
                    result = prior[:keep] + tail
        memo[item] = result
        prior = result
    return memo.get(request_id)


def _request_texts(lines):
    """[(row, text or None)] for each `api-request` of a transcript, in order."""
    shapes, requests, order, lookup = {}, {}, [], {}
    answers, replies = {}, {}
    for item in lines:
        kind = item.get("type")
        if kind == "api-request-shape" and isinstance(item.get("shapeHash"), str):
            shapes[item["shapeHash"]] = item.get("shape")
        elif kind == "api-request" and isinstance(item.get("id"), str):
            requests[item["id"]] = item
            order.append(item["id"])
        elif kind == "api-request-blob" and isinstance(item.get("hash"), str):
            lookup[item["hash"]] = item.get("message")
        elif kind == "assistant" and item.get("requestRef"):
            answers[item["requestRef"]] = item.get("message") or {}
            joined = replies.setdefault(item["requestRef"], {"id": None, "message": None})
            message = item.get("message") or {}
            if joined["id"] != message.get("id"):
                joined["id"], joined["message"] = message.get("id"), {"role": "assistant", "content": []}
            joined["message"]["content"].extend(message.get("content") or [])
    merged = {}
    for item in lines:
        message = item.get("message")
        if item.get("type") == "user" and isinstance(message, dict):
            lookup.setdefault(_message_hash(message), message)
        elif item.get("type") == "assistant" and isinstance(message, dict):
            lookup.setdefault(_message_hash(message), message)
            joined = merged.setdefault(message.get("id"), {"role": "assistant", "content": []})
            joined["content"].extend(message.get("content") or [])
    for message in merged.values():
        lookup.setdefault(_message_hash(message), message)
    # Tool results of parallel calls are separate transcript records and one request message.
    group = []
    for item in [*lines, {"type": "assistant"}]:
        message = item.get("message")
        if item.get("type") == "user" and isinstance(message, dict) and isinstance(message.get("content"), list):
            group.append(message)
        elif item.get("type") in ("assistant", "api-request"):
            if len(group) > 1:
                joined = {"role": "user", "content": [block for part in group for block in part["content"]]}
                lookup.setdefault(_message_hash(joined), joined)
            group = []

    replies = {key: value["message"] for key, value in replies.items()}
    memo, found = {}, []
    for request_id in order:
        request = requests[request_id]
        messages = _resolve(request_id, requests, lookup, memo, replies)
        shape = shapes.get(request.get("shapeHash"))
        usage = token_profile._usage(answers.get(request_id))
        row = {
            "id": request_id,
            "status": "ok",
            "api_tokens": usage["input"] + usage["cache_read"] + usage["cache_write"] if usage else None,
            "bytes": None,
        }
        text = None
        if messages is None or not isinstance(shape, dict):
            row["status"] = "unresolved"
        else:
            pieces = []
            system = shape.get("system")
            for block in system if isinstance(system, list) else [system]:
                pieces.append(block.get("text") if isinstance(block, dict) else block)
            for tool in shape.get("tools") or []:
                pieces.append(json.dumps(tool, ensure_ascii=False, sort_keys=True))
            media = False
            for message in messages:
                segments = _segments((message or {}).get("content"))
                if segments is None:
                    media = True
                    break
                pieces.extend(segments)
            if media:
                row["status"] = "media"
            else:
                text = "\n".join(piece for piece in pieces if isinstance(piece, str) and piece)
                row["bytes"] = len(text.encode("utf-8"))
                if usage is None:
                    row["status"] = "no response"
        found.append((row, text))
    return found


def rebuild_requests(lines):
    """[{"id", "status", "api_tokens", "bytes"}] for each request of a transcript.

    A request's text is its system text, its tool definitions and its messages'
    text, tool calls and tool results, the non-empty strings joined by newlines;
    `bytes` is that text's UTF-8 length and `api_tokens` the response's input,
    cache read and cache write tokens. `status` is `ok`, `unresolved` (a link of
    the stored chain is missing), `media` (an image or document) or
    `no response`.
    """
    return [row for row, _ in _request_texts(lines)]


def compare_requests(rows):
    """Tokens against bytes divided by 4 over the measurable requests."""
    measurable = [r for r in rows if r["status"] == "ok" and r["bytes"] and r["api_tokens"] is not None]
    skipped = Counter(r["status"] for r in rows if r["status"] != "ok")
    ratios = [r["api_tokens"] / (r["bytes"] / 4) for r in measurable]
    summary = {
        "requests": len(measurable),
        "skipped": dict(skipped),
        "pooled": None, "first": None, "median": None, "min": None, "max": None,
    }
    if not measurable:
        return summary
    summary["pooled"] = sum(r["api_tokens"] for r in measurable) / (sum(r["bytes"] for r in measurable) / 4)
    if rows and rows[0] is measurable[0]:
        summary["first"] = ratios[0]
    summary["median"] = statistics.median(ratios)
    summary["min"], summary["max"] = min(ratios), max(ratios)
    return summary


def attachments_in_requests(lines):
    """{"rendered", "found"}: the attachments with rendered text, and how many
    of those have their text (without its `<system-reminder>` wrapper, which the
    stored request leaves off) inside some rebuilt request."""
    texts = [text for _, text in _request_texts(lines) if text]
    joined = "\0".join(texts)
    rendered = found = 0
    for item in lines:
        if item.get("type") != "attachment":
            continue
        blocks = item.get("rendered")
        pieces = []
        for block in blocks if isinstance(blocks, list) else []:
            segments = _segments(block.get("content")) if isinstance(block, dict) else None
            pieces.extend(_REMINDER_WRAPPER.sub("", piece) for piece in segments or [])
        if not pieces:
            continue
        rendered += 1
        if all(piece in joined for piece in pieces):
            found += 1
    return {"rendered": rendered, "found": found}


# ablation


@dataclass(frozen=True)
class Item:
    label: str
    source: Path
    dest: str


def default_items(repo_root):
    plugin = Path(repo_root) / "plugin"
    return [
        Item("rules file", plugin / "templates" / "rules" / "compass-pipeline.md", ".claude/rules/compass-pipeline.md"),
        Item("skill", plugin / "skills" / "methodology" / "SKILL.md", ".claude/skills/methodology/SKILL.md"),
        Item("agent definition", plugin / "templates" / "agents" / "builder.md", ".claude/agents/builder.md"),
    ]


def call_cost(event_lists):
    """Calls, raw tokens and list-price weighted tokens over the result events of several sessions."""
    totals = {}
    for events in event_lists:
        for model, counts in records.count_tokens(events).items():
            entry = totals.setdefault(model, dict.fromkeys(records.KINDS, 0))
            for kind in records.KINDS:
                entry[kind] += counts[kind]
    return {"calls": len(event_lists), "raw": _raw_kinds(totals), "weighted": records.weigh(totals)[0]}


def read_first_request(project, private_root=None):
    """{"tokens", "bytes", "model"} of the first request of the only session of `project`."""
    folder = token_profile.transcript_folder(project, private_root)
    paths = _top_level(folder) if folder.is_dir() else []
    if len(paths) != 1:
        raise ValueError(f"expected one session transcript, found {len(paths)}")
    lines = token_profile._read_lines(paths[0])
    rows = rebuild_requests(lines)
    if not rows or rows[0]["bytes"] is None or rows[0]["api_tokens"] is None:
        raise ValueError("the first request cannot be measured")
    model = next(
        (records._model_key((item.get("message") or {}).get("model"))
         for item in lines if item.get("type") == "assistant"),
        records.UNKNOWN_MODEL,
    )
    return {"tokens": rows[0]["api_tokens"], "bytes": rows[0]["bytes"], "model": model}


def _ratio(numerator, denominator):
    return numerator / denominator if denominator and denominator > 0 else None


def run_ablation(items, *, make_project, run_prompt, read_first_request):
    """One row per item: first-request tokens in a bare project and in one
    holding the item's file, beside the file's bytes divided by 4."""
    for item in items:
        if not Path(item.source).is_file():
            raise FileNotFoundError(f"{item.label}: {item.source} is not a file")

    def measure(placed):
        project = Path(make_project())
        if placed is not None:
            target = project / placed.dest
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(Path(placed.source).read_bytes())
        run_prompt(project)
        return read_first_request(project)

    baseline = measure(None)
    rows = []
    for item in items:
        with_item = measure(item)
        size = Path(item.source).stat().st_size
        delta = with_item["tokens"] - baseline["tokens"]
        added = with_item["bytes"] - baseline["bytes"]
        rows.append({
            "label": item.label,
            "model": with_item["model"],
            "file_bytes": size,
            "tokens_without": baseline["tokens"],
            "tokens_with": with_item["tokens"],
            "delta_tokens": delta,
            "added_bytes": added,
            "ratio_to_file": _ratio(delta, size / 4) if size else None,
            "ratio_to_added": _ratio(delta, added / 4) if added > 0 else None,
        })
    return rows


# console exporter


def analyze_console(text, nonce, names):
    """What the console exporter's output shows: whether it wrote anything,
    whether the prompt was echoed into it, the event names it used and whether
    the skill and agent in `names` ({"skill": ..., "agent": ...}) appear by name."""
    echoed = nonce in text
    found = {
        "wrote_output": bool(text.strip()),
        "prompt_echoed": echoed,
        "events": dict(Counter(_EVENT_NAME.findall(text))),
    }
    for role, name in names.items():
        quoted = re.escape(name)
        whole = re.compile(rf"(?<![\w-]){quoted}(?![\w-])")
        keys = Counter(re.findall(rf"([A-Za-z_.]+)['\"]?\s*:\s*['\"]{quoted}['\"]", text))
        found[f"{role}_named"] = bool(whole.search(text)) and not echoed
        found[f"{role}_keys"] = dict(keys) if not echoed else {}
    return found


def split_console(stdout):
    """(events, rest): the JSON objects of a session's stdout and every other line."""
    events, rest = [], []
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            rest.append(line)
            continue
        if isinstance(value, dict):
            events.append(value)
        else:
            rest.append(line)
    return events, "\n".join(rest)


# the report section


def _int(value):
    return "n/a" if value is None else str(int(round(value)))


def _ratio_text(value):
    return "n/a" if value is None else f"{value:.2f}"


def _share(part, whole):
    return "n/a" if not whole else f"{part / whole:.1%}"


def render_section(result):
    """The report section from counts only."""
    builds = result.get("builds", [])
    lines = [
        HEADING,
        "",
        "Every build's token records, set side by side: the run log (the counting rule), the sessions' own "
        "`cost-state` totals and the deduplicated sum of assistant records over the build session, its subagent "
        "files and its setup session. Capture workers are listed apart. Builds are named by topic letter and run.",
        "",
        "#### Weighted tokens per build",
        "",
        "| Build | Arm | End | Logged | Cost-state | Records | Records minus logged | Capture workers | Unattributed | Agrees |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for build in builds:
        logged, state, found = build["logged"], build["cost_state"], build["records"]
        gap = found["weighted"] - logged["weighted"]
        lines.append(
            f"| {build['label']} | {build['arm']} | {build['end']} | {_int(logged['weighted'])} "
            f"| {_int(state['weighted'])} | {_int(found['weighted'])} | {_int(gap)} ({_share(gap, logged['weighted'])}) "
            f"| {_int(build['workers']['weighted'])} | {_int(build['unattributed']['weighted'])} "
            f"| {'yes' if build['agrees'] else 'no'} |"
        )
    lines += [
        "",
        "#### Raw tokens per build",
        "",
        "| Build | Logged | Cost-state | Records | Records minus logged | Capture workers | Web calls | Unattributed |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for build in builds:
        logged, state, found = build["logged"], build["cost_state"], build["records"]
        gap = found["raw"] - logged["raw"]
        lines.append(
            f"| {build['label']} | {_int(logged['raw'])} | {_int(state['raw'])} | {_int(found['raw'])} "
            f"| {_int(gap)} ({_share(gap, logged['raw'])}) | {_int(build['workers']['raw'])} "
            f"| {build['web_calls']} | {_int(build['unattributed']['raw'])} |"
        )
    lines += [
        "",
        "#### Causes of the gaps",
        "",
        "- Unfinished turn: a session killed at a cap writes no `cost-state`, and its last turn is in the transcript "
        "but never reached a `result` event; counted from the last end-of-turn marker.",
        "- Auxiliary request: a model's input and output tokens in `cost-state` that no assistant record carries, "
        "while its cache tokens match. Inferred when the build wrote no `cost-state` and made web calls.",
        "- Compaction and resume: named when a `compact_boundary` record, or records of a second session id, "
        "sit beside the gap.",
        "",
        "| Build | Cause | Weighted | Raw |",
        "|---|---|---|---|",
    ]
    named = 0
    for build in builds:
        for cause in build["causes"]:
            named += 1
            lines.append(f"| {build['label']} | {cause['cause']} | {_int(cause['weighted'])} | {_int(cause['raw'])} |")
    if not named:
        lines.append("| none | none | 0 | 0 |")

    lines += ["", "#### Attachment kinds that reached the model", ""]
    attachments = result.get("attachments", {})
    arms = sorted(attachments)
    if arms:
        header = "| Kind | " + " | ".join(f"{arm} reached | {arm} chars | {arm} empty" for arm in arms) + " |"
        lines += [header, "|---|" + "---|---|---|" * len(arms)]
        kinds = sorted({kind for arm in arms for kind in attachments[arm]})
        for kind in kinds:
            cells = []
            for arm in arms:
                entry = attachments[arm].get(kind, {"reached": 0, "empty": 0, "chars": 0})
                cells += [str(entry["reached"]), str(entry["chars"]), str(entry["empty"])]
            lines.append(f"| {kind} | " + " | ".join(cells) + " |")
        silent = sorted(kind for kind in {k for arm in arms for k in attachments[arm]}
                        if all(attachments[arm].get(kind, {}).get("reached", 0) == 0 for arm in arms))
        lines += ["", f"- Recorded but never rendered into a request: {', '.join(silent) if silent else 'none'}."]

    requests = result.get("requests")
    if requests:
        lines += [
            "",
            "#### Request text against the API's input count",
            "",
            f"One Compass-arm session, {requests['requests']} requests rebuilt from the transcript; "
            f"ratio = API input tokens over the request's UTF-8 bytes divided by 4.",
            "",
            f"- Pooled ratio: {_ratio_text(requests['pooled'])}; first request: {_ratio_text(requests['first'])}; "
            f"median {_ratio_text(requests['median'])}, lowest {_ratio_text(requests['min'])}, "
            f"highest {_ratio_text(requests['max'])}.",
            f"- Requests left out: {', '.join(f'{n} {s}' for s, n in sorted(requests['skipped'].items())) or 'none'}.",
        ]
        if requests.get("attachments"):
            seen = requests["attachments"]
            lines.append(f"- Attachments with rendered text found inside a rebuilt request: {seen['found']} of {seen['rendered']}.")

    ablation = result.get("ablation")
    if ablation:
        lines += [
            "",
            "#### Ablation calls",
            "",
            "An isolated `claude -p \"hi\"` in a bare project and in a project holding one file; real first-request "
            "tokens beside the file's bytes divided by 4. The added-bytes column is the growth of the rebuilt request text.",
            "",
            "| File | File bytes | Tokens without | Tokens with | Added tokens | Added request bytes "
            "| Tokens over file bytes/4 | Tokens over added bytes/4 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for row in ablation["rows"]:
            lines.append(
                f"| {row['label']} | {row['file_bytes']} | {row['tokens_without']} | {row['tokens_with']} "
                f"| {row['delta_tokens']} | {row['added_bytes']} | {_ratio_text(row['ratio_to_file'])} "
                f"| {_ratio_text(row['ratio_to_added'])} |"
            )
        cost = ablation["cost"]
        lines += ["", f"- Cost of the {cost['calls']} calls: {cost['raw']} raw tokens, {_int(cost['weighted'])} weighted."]

    otel = result.get("otel")
    if otel:
        events = ", ".join(f"{name} x{count}" for name, count in sorted(otel["events"].items())) or "none"
        lines += [
            "",
            "#### Console exporter",
            "",
            "OpenTelemetry console exporter, tried once on a session that loaded one skill and one agent.",
            "",
            f"- Output written: {'yes' if otel['wrote_output'] else 'no'}; prompt echoed into it: "
            f"{'yes' if otel['prompt_echoed'] else 'no'}.",
            f"- Event names seen: {events}.",
            f"- The skill appears by name: {'yes' if otel['skill_named'] else 'no'}; "
            f"the agent appears by name: {'yes' if otel['agent_named'] else 'no'}.",
        ]
        for role in ("skill", "agent"):
            keys = otel.get(f"{role}_keys") or {}
            if keys:
                lines.append(f"- The {role} name sits under: {', '.join(f'{k} x{n}' for k, n in sorted(keys.items()))}.")
        cost = otel.get("cost")
        if cost:
            lines.append(f"- Cost of the call: {cost['raw']} raw tokens, {_int(cost['weighted'])} weighted.")

    lines += ["", DISCARD_PENDING]
    return "\n".join(lines) + "\n"


def replace_section(report_text, section):
    """`report_text` with this section replaced by `section`, or added before
    the validity part (or at the end) when the report has none."""
    lines = report_text.splitlines(keepends=True)
    start = next((n for n, line in enumerate(lines) if line.rstrip() == HEADING), None)
    if start is not None:
        end = next((n for n in range(start + 1, len(lines)) if re.match(r"#{1,3} ", lines[n])), len(lines))
        return "".join(lines[:start]) + section + ("\n" if end < len(lines) else "") + "".join(lines[end:])
    insert = next((n for n, line in enumerate(lines) if line.rstrip() == "### Validity of this run"), None)
    if insert is None:
        base = report_text if report_text.endswith("\n") or not report_text else report_text + "\n"
        return base + ("\n" if base else "") + section
    return "".join(lines[:insert]) + section + "\n" + "".join(lines[insert:])


def mark_discarded(report_text, discarded, kept):
    """`report_text` with the discard line of the section giving the counts."""
    return _DISCARD_LINE.sub(f"- Pilot projects discarded: {discarded} discarded, {kept} kept.", report_text)


# closing the projects


def _git(directory, *args):
    return subprocess.run(
        ["git", "-C", str(directory), *args], capture_output=True, text=True, encoding="utf-8",
        env=launch.git_environment(),
    )


def check_report_committed(report_path):
    """Raise AttributionError unless the report holds the section and is committed unchanged."""
    report = Path(report_path)
    if not report.is_file():
        raise AttributionError("the pilot report does not exist")
    if HEADING not in report.read_text(encoding="utf-8").splitlines():
        raise AttributionError("the pilot report has no reconciliation section")
    try:
        inside = _git(report.parent, "rev-parse", "--is-inside-work-tree")
        tracked = _git(report.parent, "ls-files", "--error-unmatch", "--", report.name)
        status = _git(report.parent, "status", "--porcelain", "--", report.name)
    except OSError as error:
        raise AttributionError(f"git cannot be run: {error}") from error
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        raise AttributionError("the pilot report is not inside a git work tree")
    if tracked.returncode != 0:
        raise AttributionError("the pilot report is not committed")
    if status.stdout.strip():
        raise AttributionError("the pilot report has uncommitted changes")


def discard_projects(projects_root, keep, report_path, discard):
    """Discard every project under `projects_root` except those named in `keep`.

    Refuses, before deleting anything, unless the report holds the section and
    is committed unchanged, and when a name in `keep` is no project. `discard`
    is called with each project path.
    """
    check_report_committed(report_path)
    projects = sandbox.list_projects(projects_root)
    names = {project.name for project in projects}
    unknown = sorted(set(keep) - names)
    if unknown:
        raise AttributionError("no such project to keep: " + ", ".join(unknown))
    gone = 0
    for project in projects:
        if project.name in keep:
            continue
        discard(project)
        gone += 1
    return {"discarded": gone, "kept": len(projects) - gone}


# the command line


def _result_path(private_root):
    return Path(private_root) / "attribution" / "result.json"


def _load_result(private_root):
    path = _result_path(private_root)
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_result(private_root, result):
    path = _result_path(private_root)
    if records._inside_work_tree(path.parent.parent):
        raise AttributionError("attribution results stay outside git work trees")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8", newline="\n")


def _run_log(path):
    log = Path(path)
    if not log.is_file():
        raise AttributionError("there is no pilot run log")
    events = []
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def measure(run_log, private_root):
    """Reconcile every closed build, list the attachment kinds and compare one
    Compass-arm session's request text with the API's counts."""
    events = _run_log(run_log)
    letters = grade.topic_letters(events)
    closed = [e for e in events if e.get("event") == "build-closed" and e.get("project")]
    builds, folders = [], {}
    for event in closed:
        folder = token_profile.transcript_folder(event["project"], private_root)
        row = reconcile_build(folder, {"weighted": event["weighted"], "raw": event["raw"]})
        row.update({"label": f"{letters.get(event['topic'], '?')}{event['run']}", "arm": event["arm"], "end": event["end"]})
        builds.append(row)
        folders.setdefault(event["arm"], []).append(folder)
    result = {
        "builds": builds,
        "attachments": {arm: attachment_kinds(found) for arm, found in folders.items()},
    }
    chosen = next((e for e in closed if e["arm"] == "compass" and e["end"] == "human-done"), None)
    chosen = chosen or next((e for e in closed if e["arm"] == "compass"), None)
    if chosen is not None:
        folder = token_profile.transcript_folder(chosen["project"], private_root)
        for path in _top_level(folder):
            lines = token_profile._read_lines(path)
            if token_profile.session_kind(lines) == "build":
                summary = compare_requests(rebuild_requests(lines))
                summary["attachments"] = attachments_in_requests(lines)
                result["requests"] = summary
                break
    return result


def _call_environment(project, private_root, extra=None):
    env = drive.apply_home(dict(os.environ), drive.sandbox_home(project, private_root))
    env.update(extra or {})
    return env


def ablate(repo_root, private_root, projects_root):
    calls = []

    def make_project():
        return sandbox.new_project(projects_root)

    def run_prompt(project):
        result = launch.run_session(
            project, "hi", repo_root=repo_root, private_root=private_root, plugin=False,
            parent_env=_call_environment(project, private_root),
            extra_args=["--max-budget-usd", CALL_BUDGET_USD], timeout=CALL_TIMEOUT_SECONDS,
        )
        if result.status != launch.DONE:
            raise AttributionError(f"an ablation call ended {result.status}")
        calls.append(result.events)
        return result.events

    rows = run_ablation(
        default_items(repo_root), make_project=make_project, run_prompt=run_prompt,
        read_first_request=lambda project: read_first_request(project, private_root),
    )
    return {"rows": rows, "cost": call_cost(calls)}


def console_exporter(repo_root, private_root, projects_root):
    """Run one session that loads a skill and an agent under the console exporter."""
    items = [item for item in default_items(repo_root) if item.label != "rules file"]
    project = sandbox.new_project(projects_root)
    for item in items:
        target = project / item.dest
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(Path(item.source).read_bytes())
    names = {"skill": "methodology", "agent": "builder"}
    nonce = f"ref-{hashlib.sha256(str(time.time()).encode()).hexdigest()[:12]}"
    prompt = (
        f"({nonce}) Use the Skill tool to load the skill named {names['skill']}. Then use the Agent tool to start the "
        f"agent named {names['agent']} with the prompt \"Reply with the single word ok.\" Then stop."
    )
    env = launch.session_environment(_call_environment(project, private_root, OTEL_ENVIRONMENT), private_root)
    command = launch.resolve_command(None, env) + [
        "-p", "--output-format", "stream-json", "--verbose", "--setting-sources", "project,local",
        "--strict-mcp-config", "--max-budget-usd", CALL_BUDGET_USD,
    ]
    code, stdout, stderr = launch._run(command, prompt, str(project), env, CALL_TIMEOUT_SECONDS)
    events, rest = split_console(stdout)
    raw_text = rest + "\n" + stderr
    folder = _result_path(private_root).parent
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "otel-console.txt").write_text(raw_text, encoding="utf-8")
    found = analyze_console(raw_text, nonce, names)
    found["cost"] = call_cost([events])
    found["exit"] = code
    return found


def _build_parser():
    parser = argparse.ArgumentParser(prog="attribute.py", description="Reconcile the pilot's token records.")
    parser.add_argument("--private-root", default=None)
    repo = Path(__file__).resolve().parents[2]
    parser.add_argument("--repo-root", default=str(repo))
    parser.add_argument("--projects-root", default=str(sandbox.DEFAULT_PROJECTS_ROOT))
    verbs = parser.add_subparsers(dest="verb", required=True)
    one = verbs.add_parser("measure", help="reconcile every build and rebuild one session's requests")
    one.add_argument("--run-log", default=None)
    verbs.add_parser("ablate", help="run the ablation calls")
    verbs.add_parser("otel", help="try the console exporter once")
    default_report = repo / ".compass" / "research" / "whole-overhead" / "RESEARCH-whole-overhead-pilot.md"
    write = verbs.add_parser("report", help="write the section into the pilot report")
    write.add_argument("--report", default=str(default_report))
    closing = verbs.add_parser("discard", help="discard every pilot project once the report is committed")
    closing.add_argument("--report", default=str(default_report))
    closing.add_argument("--keep", action="append", default=[], help="a project to leave in place")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    private_root = Path(args.private_root) if args.private_root else launch.default_private_root()
    try:
        if args.verb == "measure":
            log = args.run_log or str(private_root / "pilot" / "run-log.jsonl")
            result = _load_result(private_root)
            result.update(measure(log, private_root))
            _save_result(private_root, result)
            print(f"measured {len(result['builds'])} builds; agree {sum(b['agrees'] for b in result['builds'])}")
        elif args.verb == "ablate":
            result = _load_result(private_root)
            result["ablation"] = ablate(args.repo_root, private_root, args.projects_root)
            _save_result(private_root, result)
            print(f"ablated {len(result['ablation']['rows'])} items")
        elif args.verb == "otel":
            result = _load_result(private_root)
            if "otel" in result:
                raise AttributionError("the console exporter was tried already")
            result["otel"] = console_exporter(args.repo_root, private_root, args.projects_root)
            _save_result(private_root, result)
            print("console exporter tried once")
        elif args.verb == "report":
            report = Path(args.report)
            if not report.is_file():
                raise AttributionError("the pilot report does not exist")
            result = _load_result(private_root)
            if "builds" not in result:
                raise AttributionError("nothing measured yet; run measure first")
            text = report.read_text(encoding="utf-8")
            report.write_text(replace_section(text, render_section(result)), encoding="utf-8", newline="\n")
            print("report section written")
        else:
            config_dir = private_root / "claude-config"

            def discard(project):
                sandbox.discard_project(project, config_dir=config_dir, projects_root=args.projects_root)

            done = discard_projects(args.projects_root, args.keep, args.report, discard)
            report = Path(args.report)
            report.write_text(
                mark_discarded(report.read_text(encoding="utf-8"), done["discarded"], done["kept"]),
                encoding="utf-8", newline="\n",
            )
            print(f"discarded {done['discarded']}, kept {done['kept']}")
    except (AttributionError, grade.GradeError, sandbox.Refused, launch.Refused, ValueError, OSError, RuntimeError) as error:
        print(f"attribute: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
