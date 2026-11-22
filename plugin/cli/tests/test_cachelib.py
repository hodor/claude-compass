"""Tests for `cachelib`: read-only prompt-cache readers over host transcripts.

Public API under test (module `plugin/cli/cachelib.py`, standard library
only; every function returns objects holding counts, kinds and times, never a
path, session id, cwd, request id or message text; no function raises on a
malformed record, a record is skipped or yields None instead):

    KINDS = ("system-or-tools", "instruction-files", "git-snapshot",
             "memory-index", "environment", "other", "none", "unknown")
    INSTRUCTION_FILE_KINDS = ("project-claude-md", "rule-file",
                              "user-claude-md", "memory-index")

    @dataclass(frozen=True) Request:
        timestamp: str | None          # the record's own `timestamp` string
        model: str | None              # assistant message.model
        input_tokens: int
        cache_creation_input_tokens: int
        cache_read_input_tokens: int
        ephemeral_5m_input_tokens: int | None   # usage.cache_creation split
        ephemeral_1h_input_tokens: int | None   # None when the split is absent

    requests(transcript) -> list[Request]
        One Request per distinct `requestId` of the transcript's assistant
        records, in file order, taking the FIRST record of that requestId.
        `isSidechain` is NOT filtered (subagent transcripts mark every record
        as sidechain). A record without a non-empty string `requestId`, with
        no dict `message`/`usage`, with a non-numeric usage value (string that
        is not an int, list, dict), or with all-zero usage is skipped. A bool
        usage value counts as 0 (never 1), as `context_check._used_of` does,
        so a record whose only non-zero value is `true` is all-zero and
        skipped. The split is None for both keys when `usage.cache_creation`
        is absent or not a dict; a missing key inside a dict is None too.

    hit_ratio(reqs) -> float | None
        sum(read) / sum(read + creation + input) over `reqs`, tokens-weighted
        (not a mean of per-request ratios); None when the denominator is 0.

    first_read_share(firsts) -> float | None
        Share of the given first requests whose cache_read_input_tokens > 0;
        None for an empty list. `firsts` is a list of Request (or None
        entries, which are ignored).

    @dataclass(frozen=True) SessionSummary:
        first: Request | None          # first deduplicated request
        whole_hit: float | None        # hit_ratio over every request
        request_count: int
        entrypoint: str | None         # first non-empty `entrypoint` string
        started_at: str | None         # first parseable `timestamp` of any record
        ended_at: str | None           # timestamp of the last request

    session_summary(transcript) -> SessionSummary

    @dataclass(frozen=True) SubagentSummary:
        agent_type: str                # `agentType` of the beside
                                       # `<name>.meta.json`; "unknown" when the
                                       # file is missing, not JSON, not an
                                       # object, or agentType is not a
                                       # non-empty string
        first: Request | None
        whole_hit: float | None
        request_count: int
        started_at: str | None
        minutes_since_previous_same_type: float | None

    subagent_summaries(transcript) -> list[SubagentSummary]
        Through `sessionslib.subagent_transcripts`, ordered by started_at
        ascending (not by file name). `minutes_since_previous_same_type` is
        started_at minus the previous started_at of the same agent_type
        (None for the first of its type).

    @dataclass(frozen=True) PairComparison:
        gap_minutes: float | None      # later.started_at - earlier.ended_at
        comparable: bool
        first_difference: str          # one of KINDS
        instruction_file_kind: str | None   # set only when first_difference
                                       # is "instruction-files" and the first
                                       # differing file is identifiable

    compare_first_requests(earlier, later) -> PairComparison
        The first request of each transcript is linked to its `api-request`
        record through assistant.requestRef == api-request.id. comparable is
        True when both have an api-request with equal `params` and equal
        `shapeHash`. first_difference:
          "unknown"          either transcript has no request or no linked
                             api-request, or a differing blob is missing
          "system-or-tools"  shapeHash differs
          otherwise the `tail` hash lists are walked in order; the first
          position whose hashes differ (or that exists on one side only) names
          the block; inside a differing blob the content blocks are compared
          in order and the first differing block is classified by its text:
            contains "Codebase and user instructions are shown below"
                                                  -> "instruction-files"
            contains "# gitStatus"                -> "git-snapshot"
            contains "# Memory Index" (and none of the above) -> "memory-index"
            role "system" and text starts "# Environment" -> "environment"
            anything else                         -> "other"
          "none"             no difference
        Instruction text is split into files at lines
        `Contents of <path> (<description>):`; the first file (in text order,
        a file present on one side only counts) whose header or body differs
        gives instruction_file_kind: description starting "user's auto-memory"
        -> "memory-index"; path ending CLAUDE.md with description starting
        "user's private" -> "user-claude-md"; path ending CLAUDE.md otherwise
        -> "project-claude-md"; any other path -> "rule-file".

    @dataclass(frozen=True) LedgerTotals:
        run_count: int
        cache_read_tokens: int
        cache_creation_tokens: int
        input_tokens: int

    ledger_totals(loop_dir) -> LedgerTotals
        Sums those three fields over the `type == "run"` rows of
        `<loop_dir>/ledger.jsonl`; a missing or non-int (bool included) or
        negative value counts 0; unparseable lines and other row types are
        ignored; a missing ledger gives zeros.

Fixtures are written by code in this module into pytest's tmp_path, so a
wiped folder rebuilds identically. Every fixture path, session id, cwd and
text carries a LEAK marker the leak test hunts for.
"""

import dataclasses
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cachelib  # noqa: E402

BASE = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
LEAK_SID = "LEAKSID-5d1c"
LEAK_CWD = "/LEAKCWD-9f2e/work"
LEAK_PATH = "/fx-LEAKPATH-3b7a"
LEAK_TEXT = "LEAKTEXT-77c4"
INTRO = "Codebase and user instructions are shown below. Be sure to adhere to these."
DESC = {
    "user": "user's private global instructions for all projects",
    "project": "project instructions, checked into the codebase",
    "rule": "project instructions, checked into the codebase",
    "memory": "user's auto-memory, persists across conversations",
}
DEFAULT_FILES = [
    ("user", "u1"), ("project", "p1"), ("rule", "r1"), ("rule", "r2"), ("memory", "m1"),
]


def at(minutes):
    """ISO timestamp `minutes` after BASE, in the host's `...000Z` form."""
    return (BASE + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def usage(read=0, create=0, inp=0, split=("absent",)):
    body = {
        "input_tokens": inp,
        "cache_creation_input_tokens": create,
        "cache_read_input_tokens": read,
        "output_tokens": 5,
    }
    if split != ("absent",):
        body["cache_creation"] = {
            "ephemeral_5m_input_tokens": split[0],
            "ephemeral_1h_input_tokens": split[1],
        }
    return body


def instruction_text(files):
    parts = [f"<system-reminder>\n{INTRO}\n"]
    for index, (kind, body) in enumerate(files):
        name = {"user": "CLAUDE.md", "project": "CLAUDE.md", "memory": "MEMORY.md"}.get(
            kind, f"rule{index}.md")
        folder = {"user": "home/.claude", "project": "proj", "memory": "mem",
                  "rule": "proj/.claude/rules"}[kind]
        parts.append(f"Contents of {LEAK_PATH}/{folder}/{name} ({DESC[kind]}):\n\n{body}\n")
    return "\n".join(parts) + "</system-reminder>"


def git_text(status):
    return ("<system-reminder>\nAs you answer the user's questions, you can use the "
            f"following context:\n# gitStatus\n{status}\n</system-reminder>")


def blob(role, texts):
    message = {"role": role, "content": [{"type": "text", "text": t} for t in texts]}
    digest = hashlib.sha1(json.dumps(message, sort_keys=True).encode()).hexdigest()[:16]
    return {"type": "api-request-blob", "sessionId": LEAK_SID, "hash": digest, "message": message}


def default_blobs(files=None, git="status A", env="env A", prompt="prompt A", extra_user=()):
    files = DEFAULT_FILES if files is None else files
    user = blob("user", [instruction_text(files), git_text(git),
                         "<system-reminder>\nAttribution rules\n</system-reminder>",
                         f"{LEAK_TEXT} {prompt}", *extra_user])
    system = blob("system", [f"# Environment\n{env}"])
    return [user, system]


def write_lines(path, records, tail_garbage=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(r) + "\n" for r in records)
    if tail_garbage is not None:
        data += tail_garbage
    path.write_bytes(data.encode("utf-8"))


def assistant(request_id, ts, use, ref=None, model="claude-test-1", sidechain=False, **extra):
    record = {
        "type": "assistant", "isSidechain": sidechain, "timestamp": ts, "requestId": request_id,
        "requestRef": ref, "entrypoint": "cli", "cwd": LEAK_CWD, "sessionId": LEAK_SID,
        "message": {"model": model, "role": "assistant",
                    "content": [{"type": "text", "text": LEAK_TEXT}], "usage": use},
    }
    record.update(extra)
    return record


def session_records(start=0, blobs=None, shape="S1", model="claude-test-1", params_extra=None,
                    use=None, entry="cli", requests=1, sidechain=False, request_ids=None):
    """A transcript with a leading attachment record at `start`, the request
    context records, and `requests` distinct assistant requests one minute
    apart. The first request links to its api-request through requestRef."""
    blobs = default_blobs() if blobs is None else blobs
    use = usage(read=100, create=10, inp=1) if use is None else use
    params = {"model": model, "max_tokens": 64000, **(params_extra or {})}
    ref = f"ref-{LEAK_SID}-{start}"
    records = [{"type": "attachment", "timestamp": at(start), "entrypoint": entry,
                "sessionId": LEAK_SID, "cwd": LEAK_CWD, "attachment": {"type": "environment"}}]
    records += [{"type": "api-request-shape", "shapeHash": shape, "timestamp": at(start)}]
    records += blobs
    records.append({
        "type": "api-request", "id": ref, "timestamp": at(start), "shapeHash": shape,
        "params": params, "tail": [b["hash"] for b in blobs], "keep": 0,
        "sessionId": LEAK_SID,
    })
    for n in range(requests):
        rid = (request_ids or [f"req-{start}-{n}"] * requests)[n]
        records.append(assistant(rid, at(start + 1 + n), use, ref=ref if n == 0 else None,
                                 model=model, sidechain=sidechain, entrypoint=entry))
    return records


def make_session(tmp_path, name, **kwargs):
    path = tmp_path / f"{name}.jsonl"
    write_lines(path, session_records(**kwargs))
    return path


def pair(tmp_path, first_kwargs=None, second_kwargs=None, gap=10):
    first = make_session(tmp_path, "a", start=0, **(first_kwargs or {}))
    second = make_session(tmp_path, "b", start=1 + gap, **(second_kwargs or {}))
    return cachelib.compare_first_requests(first, second)


# ---- requests -------------------------------------------------------------


def test_request_repeated_under_one_request_id_counts_once(tmp_path):
    """Adversarial where: the host writes one assistant record per content
    block, so a request with three blocks must not triple its tokens."""
    use = usage(read=900, create=0, inp=100)
    records = [assistant("req-1", at(1), use), assistant("req-1", at(2), use),
               assistant("req-1", at(3), use), assistant("req-2", at(4), usage(read=5))]
    path = tmp_path / "s.jsonl"
    write_lines(path, records)
    got = cachelib.requests(path)
    assert [(r.timestamp, r.cache_read_input_tokens) for r in got] == [
        (at(1), 900), (at(4), 5)]


def test_all_zero_usage_row_is_dropped(tmp_path):
    """Adversarial where: synthetic messages carry all-zero usage and would
    drag a hit ratio or a request count if kept."""
    path = tmp_path / "s.jsonl"
    write_lines(path, [assistant("req-0", at(1), usage()), assistant("req-1", at(2), usage(inp=1))])
    got = cachelib.requests(path)
    assert [r.input_tokens for r in got] == [1]


def test_true_usage_value_is_rejected_not_counted_as_one(tmp_path):
    """Adversarial where: bool is an int subclass in Python, so `true` would
    silently count as one token."""
    only_true = usage(inp=0)
    only_true["cache_read_input_tokens"] = True
    mixed = usage(create=50)
    mixed["cache_read_input_tokens"] = True
    path = tmp_path / "s.jsonl"
    write_lines(path, [assistant("req-a", at(1), only_true), assistant("req-b", at(2), mixed)])
    got = cachelib.requests(path)
    assert len(got) == 1
    assert (got[0].cache_read_input_tokens, got[0].cache_creation_input_tokens) == (0, 50)


@pytest.mark.parametrize("bad", ["abc", [3], {"n": 3}])
def test_non_numeric_usage_value_rejects_the_record(tmp_path, bad):
    """Adversarial where: a usage field of the wrong type must skip that
    record rather than raise or count garbage."""
    broken = usage(read=10, inp=1)
    broken["cache_creation_input_tokens"] = bad
    path = tmp_path / "s.jsonl"
    write_lines(path, [assistant("req-a", at(1), broken), assistant("req-b", at(2), usage(inp=2))])
    assert [r.input_tokens for r in cachelib.requests(path)] == [2]


def test_request_without_cache_creation_split_gives_none_not_zero(tmp_path):
    """Adversarial where: an absent split coerced to 0 would read as 'all
    tokens were uncached writes of neither TTL'."""
    path = tmp_path / "s.jsonl"
    write_lines(path, [
        assistant("req-a", at(1), usage(create=7)),
        assistant("req-b", at(2), usage(create=9, split=(4, 5))),
        assistant("req-c", at(3), {**usage(create=3), "cache_creation": "n/a"}),
        assistant("req-d", at(4), {**usage(create=3), "cache_creation": {"ephemeral_1h_input_tokens": 3}}),
    ])
    a, b, c, d = cachelib.requests(path)
    assert (a.ephemeral_5m_input_tokens, a.ephemeral_1h_input_tokens) == (None, None)
    assert (b.ephemeral_5m_input_tokens, b.ephemeral_1h_input_tokens) == (4, 5)
    assert (c.ephemeral_5m_input_tokens, c.ephemeral_1h_input_tokens) == (None, None)
    assert (d.ephemeral_5m_input_tokens, d.ephemeral_1h_input_tokens) == (None, 3)


def test_zero_split_values_stay_zero_not_none(tmp_path):
    """Adversarial where: a present split of 0 must not be confused with an
    absent one (boundary of the None rule)."""
    path = tmp_path / "s.jsonl"
    write_lines(path, [assistant("req-a", at(1), usage(read=5, split=(0, 0)))])
    (got,) = cachelib.requests(path)
    assert (got.ephemeral_5m_input_tokens, got.ephemeral_1h_input_tokens) == (0, 0)


def test_model_and_token_fields_are_read_from_the_record(tmp_path):
    path = tmp_path / "s.jsonl"
    write_lines(path, [assistant("req-a", at(3), usage(read=1, create=2, inp=3), model="claude-x-9")])
    (got,) = cachelib.requests(path)
    assert (got.timestamp, got.model, got.input_tokens, got.cache_creation_input_tokens,
            got.cache_read_input_tokens) == (at(3), "claude-x-9", 3, 2, 1)


def test_sidechain_assistant_records_count_in_subagent_transcripts(tmp_path):
    """Adversarial where: `context_check._used_of` skips isSidechain records,
    but every record of a subagent transcript is a sidechain record."""
    path = tmp_path / "agent.jsonl"
    write_lines(path, [assistant("req-a", at(1), usage(read=8), sidechain=True)])
    assert [r.cache_read_input_tokens for r in cachelib.requests(path)] == [8]


def test_record_without_request_id_is_skipped(tmp_path):
    """Adversarial where: a record that cannot be deduplicated must not be
    counted as a fresh request each time it repeats."""
    rec = assistant("req-a", at(1), usage(read=8))
    del rec["requestId"]
    empty = assistant("", at(2), usage(read=8))
    path = tmp_path / "s.jsonl"
    write_lines(path, [rec, rec, empty, assistant("req-b", at(3), usage(read=1))])
    assert [r.cache_read_input_tokens for r in cachelib.requests(path)] == [1]


def test_truncated_last_line_and_malformed_records_are_skipped(tmp_path):
    """Adversarial where: a transcript being written ends mid-line; wrong
    shapes in message, usage or content must never raise."""
    records = [
        assistant("req-a", at(1), usage(read=4)),
        {"type": "assistant", "requestId": "req-b", "message": "text"},
        {"type": "assistant", "requestId": "req-c", "message": {"usage": [1, 2]}},
        {"type": "assistant", "requestId": "req-d", "message": {"usage": None}},
        {"type": "user", "requestId": "req-e", "message": {"usage": usage(read=99)}},
        assistant("req-f", at(2), usage(read=6)),
    ]
    path = tmp_path / "s.jsonl"
    write_lines(path, records, tail_garbage='[1, 2]\nnot json\n{"type": "assistant", "requestId": "req-g", "mess')
    assert [r.cache_read_input_tokens for r in cachelib.requests(path)] == [4, 6]


def test_transcript_without_assistant_records_gives_empty_list(tmp_path):
    path = tmp_path / "s.jsonl"
    write_lines(path, [{"type": "user", "timestamp": at(1)}])
    assert cachelib.requests(path) == []


# ---- hit ratios -----------------------------------------------------------


def make_requests(tmp_path, specs):
    path = tmp_path / "hits.jsonl"
    write_lines(path, [assistant(f"req-{i}", at(i), usage(**spec)) for i, spec in enumerate(specs)])
    return cachelib.requests(path)


def test_hit_ratio_is_tokens_weighted_not_mean_of_ratios(tmp_path):
    """Adversarial where: a mean of per-request ratios would give 0.45; the
    tokens-weighted share is 900/1100."""
    got = make_requests(tmp_path, [dict(read=900, inp=100), dict(create=100)])
    assert cachelib.hit_ratio(got) == pytest.approx(900 / 1100)


def test_hit_ratio_denominator_counts_creation_and_input(tmp_path):
    got = make_requests(tmp_path, [dict(read=10, create=20, inp=30)])
    assert cachelib.hit_ratio(got) == pytest.approx(10 / 60)


def test_hit_ratio_of_nothing_is_none_not_zero_division():
    assert cachelib.hit_ratio([]) is None


def test_hit_ratio_all_miss_is_zero_and_all_hit_is_one(tmp_path):
    got = make_requests(tmp_path, [dict(create=5)])
    assert cachelib.hit_ratio(got) == 0.0
    got = make_requests(tmp_path, [dict(read=5)])
    assert cachelib.hit_ratio(got) == 1.0


def test_first_read_share_is_binary_any_read(tmp_path):
    """Adversarial where: a one-token read counts as a hit (boundary), and a
    big read does not weigh more than a small one."""
    got = make_requests(tmp_path, [dict(read=1), dict(read=99999), dict(create=50), dict(inp=3)])
    assert cachelib.first_read_share(got) == pytest.approx(0.5)


def test_first_read_share_of_nothing_is_none():
    assert cachelib.first_read_share([]) is None
    assert cachelib.first_read_share([None]) is None


# ---- sessions -------------------------------------------------------------


def test_session_summary_reports_first_request_whole_hit_entrypoint_and_times(tmp_path):
    records = [
        {"type": "queue-operation", "timestamp": at(0)},
        {"type": "attachment", "timestamp": at(1), "entrypoint": ""},
        assistant("req-a", at(2), usage(create=100), entrypoint="sdk-cli"),
        assistant("req-b", at(7), usage(read=100), entrypoint="sdk-cli"),
    ]
    path = tmp_path / "s.jsonl"
    write_lines(path, records)
    got = cachelib.session_summary(path)
    assert got.first.cache_creation_input_tokens == 100
    assert got.first.cache_read_input_tokens == 0
    assert got.whole_hit == pytest.approx(0.5)
    assert got.request_count == 2
    assert got.entrypoint == "sdk-cli"
    assert (got.started_at, got.ended_at) == (at(0), at(7))


def test_session_summary_without_requests_is_empty_not_error(tmp_path):
    path = tmp_path / "s.jsonl"
    write_lines(path, [{"type": "user"}])
    got = cachelib.session_summary(path)
    assert (got.first, got.whole_hit, got.request_count, got.entrypoint,
            got.started_at, got.ended_at) == (None, None, 0, None, None, None)


def test_session_summary_ignores_unparseable_timestamps(tmp_path):
    """Adversarial where: a malformed `timestamp` must not become the session
    start."""
    path = tmp_path / "s.jsonl"
    write_lines(path, [{"type": "attachment", "timestamp": 12345},
                       {"type": "attachment", "timestamp": "yesterday-ish"},
                       assistant("req-a", at(4), usage(read=1))])
    assert cachelib.session_summary(path).started_at == at(4)


# ---- subagents ------------------------------------------------------------


def make_subagent(tmp_path, name, start, meta="skip", read=10):
    side = tmp_path / "sess" / "subagents"
    write_lines(side / f"agent-{name}.jsonl", [
        assistant(f"req-{name}", at(start), usage(read=read, create=10), sidechain=True)])
    if meta != "skip":
        text = meta if isinstance(meta, str) else json.dumps(meta)
        (side / f"agent-{name}.meta.json").write_text(text, encoding="utf-8")


def test_subagent_type_comes_from_meta_and_unknown_when_missing_or_malformed(tmp_path):
    """Adversarial where: a missing or damaged sidecar must degrade to
    `unknown`, not raise or inherit another agent's type."""
    make_subagent(tmp_path, "a1", 1, meta={"agentType": "tester", "description": LEAK_TEXT})
    make_subagent(tmp_path, "b2", 2)
    make_subagent(tmp_path, "c3", 3, meta="{not json")
    make_subagent(tmp_path, "d4", 4, meta=["agentType", "tester"])
    make_subagent(tmp_path, "e5", 5, meta={"agentType": 7})
    make_subagent(tmp_path, "f6", 6, meta={"agentType": ""})
    parent = tmp_path / "sess.jsonl"
    write_lines(parent, [assistant("req-p", at(0), usage(read=1))])
    got = cachelib.subagent_summaries(parent)
    assert [s.agent_type for s in got] == ["tester", "unknown", "unknown", "unknown", "unknown", "unknown"]


def test_minutes_since_previous_same_type_sibling_uses_start_time_not_file_order(tmp_path):
    """Adversarial where: file names are random ids, so ordering by name
    would pair siblings wrongly; other-type siblings must not interleave."""
    make_subagent(tmp_path, "zzz", 1, meta={"agentType": "builder"})
    make_subagent(tmp_path, "aaa", 9, meta={"agentType": "builder"})
    make_subagent(tmp_path, "mmm", 5, meta={"agentType": "tester"})
    make_subagent(tmp_path, "bbb", 13, meta={"agentType": "builder"})
    parent = tmp_path / "sess.jsonl"
    write_lines(parent, [assistant("req-p", at(0), usage(read=1))])
    got = cachelib.subagent_summaries(parent)
    assert [(s.agent_type, s.started_at, s.minutes_since_previous_same_type) for s in got] == [
        ("builder", at(1), None), ("tester", at(5), None),
        ("builder", at(9), 8.0), ("builder", at(13), 4.0)]


def test_subagent_summary_carries_first_request_and_whole_hit(tmp_path):
    make_subagent(tmp_path, "a1", 1, meta={"agentType": "tester"}, read=30)
    parent = tmp_path / "sess.jsonl"
    write_lines(parent, [assistant("req-p", at(0), usage(read=1))])
    (got,) = cachelib.subagent_summaries(parent)
    assert got.first.cache_read_input_tokens == 30
    assert got.whole_hit == pytest.approx(30 / 40)
    assert got.request_count == 1


def test_subagent_summaries_without_a_side_folder_is_empty(tmp_path):
    parent = tmp_path / "sess.jsonl"
    write_lines(parent, [assistant("req-p", at(0), usage(read=1))])
    assert cachelib.subagent_summaries(parent) == []


# ---- pair comparison ------------------------------------------------------


def test_identical_first_requests_are_comparable_with_no_difference(tmp_path):
    got = pair(tmp_path, gap=12)
    assert got.comparable is True
    assert got.first_difference == "none"
    assert got.instruction_file_kind is None


def test_gap_is_minutes_from_last_request_of_first_to_start_of_second(tmp_path):
    """Adversarial where: a gap measured from the first session's start would
    over-report the idle time a cache TTL cares about."""
    first = make_session(tmp_path, "a", start=0, requests=4)  # last request at minute 4
    second = make_session(tmp_path, "b", start=10)
    got = cachelib.compare_first_requests(first, second)
    assert got.gap_minutes == pytest.approx(6.0)


def test_pair_crossing_a_model_change_is_not_comparable(tmp_path):
    got = pair(tmp_path, second_kwargs={"model": "claude-test-2"})
    assert got.comparable is False


def test_pair_with_different_params_but_same_model_is_not_comparable(tmp_path):
    got = pair(tmp_path, second_kwargs={"params_extra": {"max_tokens": 1}})
    assert got.comparable is False


def test_pair_with_different_shape_hash_is_not_comparable_and_names_system_or_tools(tmp_path):
    got = pair(tmp_path, second_kwargs={"shape": "S2"})
    assert (got.comparable, got.first_difference) == (False, "system-or-tools")


def test_pair_whose_snapshot_block_alone_differs_names_git_snapshot(tmp_path):
    got = pair(tmp_path, second_kwargs={"blobs": default_blobs(git="status B")})
    assert (got.comparable, got.first_difference, got.instruction_file_kind) == (
        True, "git-snapshot", None)


def test_pair_whose_rule_file_text_differs_names_instruction_files_rule_file(tmp_path):
    files = [("user", "u1"), ("project", "p1"), ("rule", "r1"), ("rule", "r2-CHANGED"), ("memory", "m1")]
    got = pair(tmp_path, second_kwargs={"blobs": default_blobs(files=files)})
    assert (got.first_difference, got.instruction_file_kind) == ("instruction-files", "rule-file")


@pytest.mark.parametrize("index,expected", [
    (0, "user-claude-md"), (1, "project-claude-md"), (2, "rule-file"), (4, "memory-index")])
def test_each_instruction_file_kind_is_named_by_header_and_description(tmp_path, index, expected):
    files = [(kind, body + ("-CHANGED" if i == index else "")) for i, (kind, body) in enumerate(DEFAULT_FILES)]
    got = pair(tmp_path, second_kwargs={"blobs": default_blobs(files=files)})
    assert (got.first_difference, got.instruction_file_kind) == ("instruction-files", expected)


def test_first_differing_file_in_text_order_wins_when_several_differ(tmp_path):
    """Adversarial where: naming the last or most frequent differing file
    instead of the first would mislabel the cache break point."""
    files = [("user", "u1"), ("project", "p1-X"), ("rule", "r1-X"), ("rule", "r2"), ("memory", "m1-X")]
    got = pair(tmp_path, second_kwargs={"blobs": default_blobs(files=files)})
    assert got.instruction_file_kind == "project-claude-md"


def test_file_present_on_one_side_only_is_the_first_difference(tmp_path):
    """Adversarial where: an added or removed file leaves every earlier file
    identical, so a walk that stops at the shorter list would say none."""
    removed = DEFAULT_FILES[:-1]
    got = pair(tmp_path, second_kwargs={"blobs": default_blobs(files=removed)})
    assert (got.first_difference, got.instruction_file_kind) == ("instruction-files", "memory-index")
    added = DEFAULT_FILES + [("rule", "r3")]
    got = pair(tmp_path, first_kwargs={"blobs": default_blobs(files=added)})
    assert (got.first_difference, got.instruction_file_kind) == ("instruction-files", "rule-file")


def test_instruction_block_difference_outside_any_file_has_no_file_kind(tmp_path):
    first = default_blobs()
    second = default_blobs()
    text = second[0]["message"]["content"][0]["text"].replace(INTRO, INTRO + " Extra line.")
    second[0]["message"]["content"][0]["text"] = text
    second[0]["hash"] = "h-changed-preamble"
    got = pair(tmp_path, first_kwargs={"blobs": first}, second_kwargs={"blobs": second})
    assert (got.first_difference, got.instruction_file_kind) == ("instruction-files", None)


def test_environment_block_difference_is_named_environment(tmp_path):
    got = pair(tmp_path, second_kwargs={"blobs": default_blobs(env="env B")})
    assert got.first_difference == "environment"


def test_user_prompt_difference_is_named_other(tmp_path):
    got = pair(tmp_path, second_kwargs={"blobs": default_blobs(prompt="prompt B")})
    assert got.first_difference == "other"


def test_memory_index_block_difference_is_named_memory_index(tmp_path):
    memory = "<system-reminder>\n# Memory Index\n- [a](a.md)\n</system-reminder>"
    first = default_blobs(extra_user=[memory])
    second = default_blobs(extra_user=[memory.replace("a.md", "b.md")])
    got = pair(tmp_path, first_kwargs={"blobs": first}, second_kwargs={"blobs": second})
    assert got.first_difference == "memory-index"


def test_earlier_block_wins_over_later_block_difference(tmp_path):
    """Adversarial where: the cache breaks at the first differing block, so
    a later difference (environment) must not be reported."""
    got = pair(tmp_path, second_kwargs={"blobs": default_blobs(git="status B", env="env B")})
    assert got.first_difference == "git-snapshot"


def test_extra_trailing_message_in_tail_is_the_first_difference(tmp_path):
    first = default_blobs()
    second = default_blobs() + [blob("system", ["# Environment update\n- changed"])]
    got = pair(tmp_path, first_kwargs={"blobs": first}, second_kwargs={"blobs": second})
    assert got.first_difference == "environment"


def test_transcript_without_request_records_names_unknown(tmp_path):
    first = make_session(tmp_path, "a", start=0)
    second = tmp_path / "b.jsonl"
    write_lines(second, [{"type": "user", "timestamp": at(20)}])
    got = cachelib.compare_first_requests(first, second)
    assert (got.comparable, got.first_difference) == (False, "unknown")
    got = cachelib.compare_first_requests(second, first)
    assert (got.comparable, got.first_difference) == (False, "unknown")


def test_first_request_without_linked_api_request_names_unknown(tmp_path):
    """Adversarial where: an assistant request whose requestRef matches no
    api-request record cannot be compared, and must not match a wrong one."""
    first = make_session(tmp_path, "a", start=0)
    records = [r for r in session_records(start=10) if r["type"] != "api-request"]
    second = tmp_path / "b.jsonl"
    write_lines(second, records)
    got = cachelib.compare_first_requests(first, second)
    assert (got.comparable, got.first_difference) == (False, "unknown")


def test_missing_blob_for_a_differing_hash_names_unknown(tmp_path):
    second_blobs = default_blobs(git="status B")
    records = [r for r in session_records(start=10, blobs=second_blobs)
               if not (r["type"] == "api-request-blob" and r["hash"] == second_blobs[0]["hash"])]
    second = tmp_path / "b.jsonl"
    write_lines(second, records)
    first = make_session(tmp_path, "a", start=0)
    assert cachelib.compare_first_requests(first, second).first_difference == "unknown"


def test_pair_comparison_survives_truncated_last_line(tmp_path):
    first = make_session(tmp_path, "a", start=0)
    second = tmp_path / "b.jsonl"
    write_lines(second, session_records(start=10), tail_garbage='{"type": "api-request-blob", "ha')
    got = cachelib.compare_first_requests(first, second)
    assert got.first_difference == "none"


def test_gap_is_none_when_a_timestamp_is_missing(tmp_path):
    first = tmp_path / "a.jsonl"
    records = session_records(start=0)
    for r in records:
        r.pop("timestamp", None)
    write_lines(first, records)
    second = make_session(tmp_path, "b", start=10)
    assert cachelib.compare_first_requests(first, second).gap_minutes is None


# ---- loop ledger ----------------------------------------------------------


def write_ledger(loop_dir, rows, tail_garbage=None):
    loop_dir.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(r) + "\n" for r in rows)
    if tail_garbage:
        data += tail_garbage
    (loop_dir / "ledger.jsonl").write_bytes(data.encode("utf-8"))


def test_ledger_totals_sum_the_run_rows(tmp_path):
    write_ledger(tmp_path, [
        {"type": "run", "cache_read_tokens": 100, "cache_creation_tokens": 10, "input_tokens": 1},
        {"type": "run", "cache_read_tokens": 200, "cache_creation_tokens": 20, "input_tokens": 2},
        {"type": "review", "cache_read_tokens": 5000, "cache_creation_tokens": 5000, "input_tokens": 5000},
        {"type": "transition", "cache_read_tokens": 7},
    ])
    assert dataclasses.astuple(cachelib.ledger_totals(tmp_path)) == (2, 300, 30, 3)


def test_ledger_totals_ignore_bad_values_and_damaged_lines(tmp_path):
    """Adversarial where: a bool, string or negative token count in one row,
    or a cut-off last line, must not poison the sum or raise."""
    write_ledger(tmp_path, [
        {"type": "run", "cache_read_tokens": True, "cache_creation_tokens": "9", "input_tokens": -4},
        {"type": "run", "cache_read_tokens": 50},
        {"type": "run", "cache_read_tokens": None, "cache_creation_tokens": 5.5, "input_tokens": 3},
    ], tail_garbage='not json\n[1]\n{"type": "run", "cache_read_tokens": 99')
    totals = cachelib.ledger_totals(tmp_path)
    assert (totals.cache_read_tokens, totals.input_tokens) == (50, 3)
    assert totals.cache_creation_tokens == 0
    assert totals.run_count == 3


def test_ledger_totals_for_a_missing_ledger_are_zero(tmp_path):
    assert dataclasses.astuple(cachelib.ledger_totals(tmp_path / "no-loop")) == (0, 0, 0, 0)


# ---- leak test ------------------------------------------------------------

ISO = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")


def leaves(value):
    if dataclasses.is_dataclass(value):
        yield from leaves(dataclasses.asdict(value))
    elif isinstance(value, dict):
        for item in value.values():
            yield from leaves(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from leaves(item)
    else:
        yield value


def test_no_returned_value_carries_a_path_session_id_cwd_or_message_text(tmp_path):
    """Adversarial where: a reader that echoes a file path, id or text into
    a result would publish it through any report built on cachelib."""
    files = [("user", f"u {LEAK_TEXT}"), ("project", "p1"), ("rule", "r1"), ("memory", "m1")]
    changed = [(k, b + "-CHANGED") for k, b in files]
    first = make_session(tmp_path, "a", start=0, requests=3,
                         blobs=default_blobs(files=files, prompt=LEAK_TEXT))
    second = make_session(tmp_path, "b", start=20, blobs=default_blobs(files=changed))
    make_subagent(tmp_path, "a1", 1, meta={"agentType": "tester", "description": LEAK_TEXT})
    write_lines(tmp_path / "sess.jsonl", session_records(start=0))
    write_ledger(tmp_path / "loop", [{"type": "run", "cache_read_tokens": 1, "item": LEAK_TEXT,
                                      "run_id": LEAK_SID}])
    results = [
        cachelib.requests(first),
        cachelib.session_summary(first),
        cachelib.subagent_summaries(tmp_path / "sess.jsonl"),
        cachelib.compare_first_requests(first, second),
        cachelib.ledger_totals(tmp_path / "loop"),
    ]
    found = list(leaves(results))
    assert any(isinstance(v, str) for v in found), "fixture must exercise string fields"
    allowed = set(cachelib.KINDS) | set(cachelib.INSTRUCTION_FILE_KINDS) | {
        "claude-test-1", "cli", "tester"}
    for value in found:
        if isinstance(value, str):
            assert value in allowed or ISO.match(value), f"unexpected string in result: {value!r}"
            for marker in (LEAK_PATH, LEAK_SID, LEAK_CWD, LEAK_TEXT, "req-", "ref-"):
                assert marker not in value
