"""Post-build adversarial tests for `cachelib`.

Covers defect classes visible only in the implementation: timestamp parsing
and offsets, record-ordering rules, malformed records and sidecar files,
instruction-file alignment, hash and type handling inside blob and
api-request records, and ledger edge values.
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cachelib  # noqa: E402

BASE = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
INTRO = "Codebase and user instructions are shown below. Be sure to adhere to these."
DESC = {
    "user": "user's private global instructions for all projects",
    "project": "project instructions, checked into the codebase",
    "rule": "project instructions, checked into the codebase",
    "memory": "user's auto-memory, persists across conversations",
}


def at(minutes):
    return (BASE + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def use(read=0, create=0, inp=0, **extra):
    body = {"input_tokens": inp, "cache_creation_input_tokens": create,
            "cache_read_input_tokens": read, "output_tokens": 1}
    body.update(extra)
    return body


def put(path, records, raw_tail=b""):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = b"".join(json.dumps(r).encode("utf-8") + b"\n" for r in records)
    path.write_bytes(data + raw_tail)
    return path


def asst(rid, ts, usage, ref=None, **extra):
    rec = {"type": "assistant", "timestamp": ts, "requestId": rid, "requestRef": ref,
           "message": {"model": "m1", "usage": usage}}
    rec.update(extra)
    return rec


def blob_of(role, texts):
    message = {"role": role, "content": [{"type": "text", "text": t} for t in texts]}
    digest = hashlib.sha1(json.dumps(message, sort_keys=True).encode()).hexdigest()[:16]
    return {"type": "api-request-blob", "hash": digest, "message": message}


def instruction(files):
    parts = [f"<system-reminder>\n{INTRO}\n"]
    for kind, name, body in files:
        parts.append(f"Contents of /p/{name} ({DESC[kind]}):\n\n{body}\n")
    return "\n".join(parts) + "</system-reminder>"


def session(path, blobs, start=0, shape="S", ref="r1", extra_records=()):
    records = [{"type": "attachment", "timestamp": at(start)}]
    records += list(blobs)
    records.append({"type": "api-request", "id": ref, "shapeHash": shape,
                    "params": {"model": "m1"}, "tail": [b["hash"] for b in blobs]})
    records.append(asst("q-" + ref, at(start + 1), use(read=5), ref=ref))
    records += list(extra_records)
    return put(path, records)


# ---- timestamps ----------------------------------------------------------


def test_gap_honours_utc_offsets_in_timestamps(tmp_path):
    """Adversarial where: a timestamp with a +02:00 offset is subtracted as
    wall-clock text, shifting the gap by the offset."""
    a = put(tmp_path / "a.jsonl", [asst("x", "2026-03-01T10:00:00+00:00", use(read=1))])
    b = put(tmp_path / "b.jsonl", [asst("y", "2026-03-01T12:30:00+02:00", use(read=1))])
    assert cachelib.compare_first_requests(a, b).gap_minutes == pytest.approx(30.0)


def test_naive_timestamp_counts_as_utc_not_local_time(tmp_path):
    """Adversarial where: a naive timestamp read in local time makes the gap
    depend on the machine's timezone."""
    a = put(tmp_path / "a.jsonl", [asst("x", "2026-03-01T10:00:00Z", use(read=1))])
    b = put(tmp_path / "b.jsonl", [asst("y", "2026-03-01T10:20:00", use(read=1))])
    assert cachelib.compare_first_requests(a, b).gap_minutes == pytest.approx(20.0)


def test_extreme_timestamps_do_not_raise(tmp_path):
    """Adversarial where: year 1 and year 9999 timestamps overflow a
    `.timestamp()` conversion on some platforms."""
    sub = tmp_path / "s" / "subagents"
    put(sub / "agent-1.jsonl", [asst("a", "0001-01-01T00:00:00Z", use(read=1))])
    put(sub / "agent-2.jsonl", [asst("b", "9999-12-31T23:59:59Z", use(read=1))])
    for n in ("1", "2"):
        (sub / f"agent-{n}.meta.json").write_text('{"agentType": "t"}')
    transcript = put(tmp_path / "s.jsonl", [])
    rows = cachelib.subagent_summaries(transcript)
    assert [r.agent_type for r in rows] == ["t", "t"]
    assert rows[1].minutes_since_previous_same_type > 0


@pytest.mark.parametrize("value", [12345, True, None, ["2026-03-01"], "yesterday", "", "  "])
def test_non_string_or_garbage_timestamp_is_none_in_request(tmp_path, value):
    """Adversarial where: a non-string timestamp reaches `Request.timestamp`
    or crashes the parser."""
    path = put(tmp_path / "t.jsonl", [asst("x", value, use(read=1))])
    assert cachelib.requests(path)[0].timestamp is None


# ---- subagent ordering and meta ------------------------------------------


def _sub(tmp_path, specs):
    """specs: list of (file number, timestamp or None, agentType or None)."""
    sub = tmp_path / "sess" / "subagents"
    for number, ts, kind in specs:
        put(sub / f"agent-{number}.jsonl", [asst(f"r{number}", ts, use(read=1))])
        if kind is not None:
            (sub / f"agent-{number}.meta.json").write_text(json.dumps({"agentType": kind}))
    transcript = tmp_path / "sess.jsonl"
    put(transcript, [])
    return cachelib.subagent_summaries(transcript)


def test_subagent_without_a_parseable_start_sorts_last_and_keeps_chain(tmp_path):
    """Adversarial where: a start-less subagent breaks the sort key or resets
    the previous-same-type chain."""
    rows = _sub(tmp_path, [(1, at(0), "t"), (2, "garbage", "t"), (3, at(10), "t")])
    assert [r.started_at for r in rows] == [at(0), at(10), None]
    assert rows[1].minutes_since_previous_same_type == pytest.approx(10.0)
    assert rows[2].minutes_since_previous_same_type is None


def test_previous_same_type_skips_other_types_in_between(tmp_path):
    """Adversarial where: the previous start is taken from the previous row
    of any type instead of the same type."""
    rows = _sub(tmp_path, [(1, at(0), "a"), (2, at(3), "b"), (3, at(12), "a")])
    assert rows[2].minutes_since_previous_same_type == pytest.approx(12.0)
    assert rows[1].minutes_since_previous_same_type is None


def test_simultaneous_starts_of_one_type_give_zero_minutes_not_none(tmp_path):
    """Adversarial where: a falsy 0.0 gap is treated as missing."""
    rows = _sub(tmp_path, [(1, at(0), "a"), (2, at(0), "a")])
    assert rows[1].minutes_since_previous_same_type == 0.0


def test_meta_with_utf8_bom_is_read(tmp_path):
    """Adversarial where: a BOM makes a valid meta file read as unknown."""
    sub = tmp_path / "sess" / "subagents"
    put(sub / "agent-1.jsonl", [asst("r", at(0), use(read=1))])
    (sub / "agent-1.meta.json").write_bytes(b'\xef\xbb\xbf{"agentType": "bom"}')
    transcript = put(tmp_path / "sess.jsonl", [])
    assert cachelib.subagent_summaries(transcript)[0].agent_type == "bom"


@pytest.mark.parametrize("content", [
    b"\xff\xfe\x00bad", b"[]", b"null", b'{"agentType": 7}', b'{"agentType": ""}',
    b'{"agentType": null}', b"", pytest.param(b"[" * 200000, id="deeply-nested"),
])
def test_malformed_meta_gives_unknown_never_raises(tmp_path, content):
    """Adversarial where: undecodable bytes, a non-object root, a wrong-typed
    value or deep nesting escape as an exception."""
    sub = tmp_path / "sess" / "subagents"
    put(sub / "agent-1.jsonl", [asst("r", at(0), use(read=1))])
    (sub / "agent-1.meta.json").write_bytes(content)
    transcript = put(tmp_path / "sess.jsonl", [])
    assert cachelib.subagent_summaries(transcript)[0].agent_type == "unknown"


def test_meta_that_is_a_directory_gives_unknown(tmp_path):
    """Adversarial where: an OSError other than missing-file escapes."""
    sub = tmp_path / "sess" / "subagents"
    put(sub / "agent-1.jsonl", [asst("r", at(0), use(read=1))])
    (sub / "agent-1.meta.json").mkdir()
    transcript = put(tmp_path / "sess.jsonl", [])
    assert cachelib.subagent_summaries(transcript)[0].agent_type == "unknown"


def test_subagent_folder_entries_that_are_not_transcripts_are_ignored(tmp_path):
    """Adversarial where: a directory or a non-jsonl file in `subagents/`
    becomes a phantom subagent row."""
    sub = tmp_path / "sess" / "subagents"
    put(sub / "agent-1.jsonl", [asst("r", at(0), use(read=1))])
    (sub / "agent-2.jsonl").mkdir()
    (sub / "agent-3.txt").write_text("x")
    transcript = put(tmp_path / "sess.jsonl", [])
    assert len(cachelib.subagent_summaries(transcript)) == 1


def test_subagent_with_only_zero_usage_has_no_first_and_no_ratio(tmp_path):
    """Adversarial where: an empty subagent crashes the summary or reports a
    zero ratio instead of None."""
    sub = tmp_path / "sess" / "subagents"
    put(sub / "agent-1.jsonl", [asst("r", at(0), use())])
    transcript = put(tmp_path / "sess.jsonl", [])
    row = cachelib.subagent_summaries(transcript)[0]
    assert (row.first, row.whole_hit, row.request_count) == (None, None, 0)


# ---- malformed records and values ----------------------------------------


def test_non_dict_json_lines_nul_bytes_and_bad_utf8_are_skipped(tmp_path):
    """Adversarial where: a JSON array, scalar, NUL-laden or invalid-UTF-8
    line aborts the scan of the records after it."""
    raw = b'[1,2]\n42\n"s"\nnull\n\x00\x00\n\xff\xfe{"type":"assistant"}\n'
    path = put(tmp_path / "t.jsonl", [], raw_tail=raw)
    with open(path, "ab") as fh:
        fh.write(json.dumps(asst("ok", at(0), use(read=3))).encode() + b"\n")
    assert [r.cache_read_input_tokens for r in cachelib.requests(path)] == [3]


@pytest.mark.parametrize("rid", [7, None, ["a"], {"a": 1}, "", True])
def test_non_string_or_empty_request_id_is_skipped(tmp_path, rid):
    """Adversarial where: a non-string requestId is used as a dedupe key and
    raises (unhashable) or merges unrelated records."""
    path = put(tmp_path / "t.jsonl", [asst(rid, at(0), use(read=1))])
    assert cachelib.requests(path) == []


@pytest.mark.parametrize("message", [None, [], "text", 5, {"usage": None}, {"usage": []},
                                      {"usage": "x"}])
def test_non_dict_message_or_usage_is_skipped(tmp_path, message):
    """Adversarial where: a wrong-typed `message` or `usage` raises
    AttributeError."""
    rec = {"type": "assistant", "requestId": "x", "timestamp": at(0), "message": message}
    assert cachelib.requests(put(tmp_path / "t.jsonl", [rec])) == []


@pytest.mark.parametrize("raw_value", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_non_finite_json_numbers_in_usage_reject_the_record(tmp_path, raw_value):
    """Adversarial where: `int(nan)` or `int(inf)` raises ValueError or
    OverflowError past the guard."""
    line = ('{"type":"assistant","requestId":"x","message":{"usage":'
            '{"cache_read_input_tokens":%s}}}\n' % raw_value)
    path = tmp_path / "t.jsonl"
    path.write_text(line)
    assert cachelib.requests(path) == []


def test_integer_valued_string_usage_counts_as_that_integer(tmp_path):
    """Adversarial where: an integer string is rejected or concatenated
    instead of coerced."""
    path = put(tmp_path / "t.jsonl", [asst("x", at(0), use(read="40", create=10))])
    req = cachelib.requests(path)[0]
    assert (req.cache_read_input_tokens, req.cache_creation_input_tokens) == (40, 10)


def test_negative_usage_never_yields_a_ratio_outside_unit_interval(tmp_path):
    """Adversarial where: a negative token value passes the any-nonzero guard
    and drives hit_ratio outside [0, 1]."""
    path = put(tmp_path / "t.jsonl", [asst("x", at(0), use(read=-10, create=5))])
    reqs = cachelib.requests(path)
    ratio = cachelib.hit_ratio(reqs)
    assert all(v >= 0 for r in reqs for v in (
        r.input_tokens, r.cache_creation_input_tokens, r.cache_read_input_tokens))
    assert ratio is None or 0.0 <= ratio <= 1.0


@pytest.mark.parametrize("split", [[1, 2], "x", 5, None, {"ephemeral_5m_input_tokens": 1.5,
                                                          "ephemeral_1h_input_tokens": True}])
def test_odd_cache_creation_split_gives_none_values(tmp_path, split):
    """Adversarial where: a list, scalar, float or bool split value is
    reported as a token count."""
    path = put(tmp_path / "t.jsonl", [asst("x", at(0), use(read=1, cache_creation=split))])
    req = cachelib.requests(path)[0]
    assert (req.ephemeral_5m_input_tokens, req.ephemeral_1h_input_tokens) == (None, None)


def test_non_string_model_is_none(tmp_path):
    """Adversarial where: a non-string model flows into the frozen record."""
    rec = asst("x", at(0), use(read=1))
    rec["message"]["model"] = {"id": "m"}
    assert cachelib.requests(put(tmp_path / "t.jsonl", [rec]))[0].model is None


def test_huge_token_counts_keep_exact_ratio(tmp_path):
    """Adversarial where: float accumulation loses precision on very large
    ints, shifting a ratio that should be exact."""
    big = 10 ** 30
    path = put(tmp_path / "t.jsonl", [asst("x", at(0), use(read=big, create=big))])
    assert cachelib.hit_ratio(cachelib.requests(path)) == 0.5


def test_missing_or_garbage_files_never_raise(tmp_path):
    """Adversarial where: an unreadable transcript escapes as an exception
    from any public reader."""
    missing = tmp_path / "nope.jsonl"
    garbage = tmp_path / "g.jsonl"
    garbage.write_bytes(os.urandom(4096))
    for path in (missing, garbage, tmp_path):
        assert cachelib.requests(path) == []
        assert cachelib.session_summary(path).request_count == 0
        assert cachelib.subagent_summaries(path) == []
        assert cachelib.compare_first_requests(path, garbage).first_difference == "unknown"


def test_first_record_of_a_request_wins_over_later_duplicates(tmp_path):
    """Adversarial where: a later streaming record with larger usage replaces
    the first."""
    path = put(tmp_path / "t.jsonl", [asst("x", at(0), use(read=1)),
                                      asst("x", at(1), use(read=999))])
    assert [r.cache_read_input_tokens for r in cachelib.requests(path)] == [1]


# ---- pair comparison internals -------------------------------------------


def test_blob_record_with_unhashable_hash_does_not_break_comparison(tmp_path):
    """Adversarial where: `record.get("hash") in hashes` raises TypeError for
    a list or dict hash in a damaged blob record."""
    blobs = [blob_of("user", ["same"]), blob_of("system", ["# Environment\nA"])]
    changed = [blob_of("user", ["same"]), blob_of("system", ["# Environment\nB"])]
    a = session(tmp_path / "a.jsonl", blobs,
                extra_records=[{"type": "api-request-blob", "hash": ["x"], "message": {}},
                               {"type": "api-request-blob", "hash": {"x": 1}, "message": {}}])
    b = session(tmp_path / "b.jsonl", changed, start=5, ref="r2")
    assert cachelib.compare_first_requests(a, b).first_difference == "environment"


def test_api_request_after_the_assistant_record_still_links(tmp_path):
    """Adversarial where: the api-request is looked up only among records
    preceding the assistant record."""
    blobs = [blob_of("user", ["u"])]
    records = [asst("q", at(1), use(read=1), ref="late")] + blobs + [
        {"type": "api-request", "id": "late", "shapeHash": "S", "params": {},
         "tail": [blobs[0]["hash"]]}]
    a = put(tmp_path / "a.jsonl", records)
    assert cachelib.compare_first_requests(a, a).first_difference == "none"


@pytest.mark.parametrize("tail", [None, "abc", 5, {"a": 1}, [1, 2], ["ok", None]])
def test_malformed_tail_names_unknown(tmp_path, tail):
    """Adversarial where: a non-list or non-string tail raises or is walked
    as if it were hashes."""
    records = [{"type": "api-request", "id": "r", "shapeHash": "S", "params": {}, "tail": tail},
               asst("q", at(0), use(read=1), ref="r")]
    a = put(tmp_path / "a.jsonl", records)
    assert cachelib.compare_first_requests(a, a).first_difference == "unknown"


@pytest.mark.parametrize("ref", [5, ["r"], {"r": 1}, True])
def test_non_string_request_ref_names_unknown(tmp_path, ref):
    """Adversarial where: an unhashable requestRef is used as a dict key."""
    records = [{"type": "api-request", "id": "r", "shapeHash": "S", "params": {}, "tail": []},
               asst("q", at(0), use(read=1), ref=ref)]
    a = put(tmp_path / "a.jsonl", records)
    assert cachelib.compare_first_requests(a, a).first_difference == "unknown"


@pytest.mark.parametrize("content", [
    None, 5, "plain string", [], [None], [5, True], [{"type": "image", "source": {"d": "x"}}],
    [{"type": "tool_use", "input": {"b": 1, "a": [1, 2]}}], [{"text": 5}], [["nested"]],
])
def test_odd_blob_content_shapes_compare_without_raising(tmp_path, content):
    """Adversarial where: non-text content blocks or a non-list content
    crash the block comparison."""
    odd = {"type": "api-request-blob", "hash": "H1",
           "message": {"role": "user", "content": content}}
    other = {"type": "api-request-blob", "hash": "H2",
             "message": {"role": "user", "content": [{"type": "text", "text": "x"}]}}
    a = put(tmp_path / "a.jsonl", [odd, {"type": "api-request", "id": "r", "shapeHash": "S",
                                          "params": {}, "tail": ["H1"]},
                                   asst("q", at(0), use(read=1), ref="r")])
    b = put(tmp_path / "b.jsonl", [other, {"type": "api-request", "id": "r", "shapeHash": "S",
                                            "params": {}, "tail": ["H2"]},
                                   asst("q", at(9), use(read=1), ref="r")])
    result = cachelib.compare_first_requests(a, b)
    assert result.first_difference in cachelib.KINDS


def test_blob_with_non_dict_message_does_not_raise(tmp_path):
    """Adversarial where: a blob without a dict `message` is treated as
    present and compared as empty content, or crashes on a non-str role."""
    a = put(tmp_path / "a.jsonl", [
        {"type": "api-request-blob", "hash": "H1", "message": "nope"},
        {"type": "api-request", "id": "r", "shapeHash": "S", "params": {}, "tail": ["H1"]},
        asst("q", at(0), use(read=1), ref="r")])
    b = put(tmp_path / "b.jsonl", [
        {"type": "api-request-blob", "hash": "H2", "message": {"role": 3, "content": "x"}},
        {"type": "api-request", "id": "r", "shapeHash": "S", "params": {}, "tail": ["H2"]},
        asst("q", at(9), use(read=1), ref="r")])
    assert cachelib.compare_first_requests(a, b).first_difference == "unknown"


def test_instruction_file_removed_from_the_middle_names_the_removed_file(tmp_path):
    """Adversarial where: files are paired by position, so removing the
    project CLAUDE.md shifts every later file and the next file's kind is
    reported instead of the removed one."""
    full = [("user", "u/CLAUDE.md", "u"), ("project", "CLAUDE.md", "p"),
            ("rule", "rules/a.md", "r"), ("memory", "MEMORY.md", "m")]
    cut = [full[0], full[2], full[3]]
    a = session(tmp_path / "a.jsonl", [blob_of("user", [instruction(full)])])
    b = session(tmp_path / "b.jsonl", [blob_of("user", [instruction(cut)])], start=5, ref="r2")
    result = cachelib.compare_first_requests(a, b)
    assert (result.first_difference, result.instruction_file_kind) == (
        "instruction-files", "project-claude-md")


def test_instruction_file_path_with_parentheses_keeps_its_kind(tmp_path):
    """Adversarial where: a path such as `Program Files (x86)` splits the
    header at the wrong parenthesis and misclassifies the file."""
    def files(body):
        return [("user", "Program Files (x86)/u/CLAUDE.md", body)]
    a = session(tmp_path / "a.jsonl", [blob_of("user", [instruction(files("one"))])])
    b = session(tmp_path / "b.jsonl", [blob_of("user", [instruction(files("two"))])],
                start=5, ref="r2")
    assert cachelib.compare_first_requests(a, b).instruction_file_kind == "user-claude-md"


def test_changed_last_file_body_is_detected_despite_closing_tag_strip(tmp_path):
    """Adversarial where: stripping the closing tag from the last file's body
    hides a one-character change at its end."""
    def files(tail):
        return [("project", "CLAUDE.md", "keep"), ("memory", "MEMORY.md", "entry " + tail)]
    a = session(tmp_path / "a.jsonl", [blob_of("user", [instruction(files("a"))])])
    b = session(tmp_path / "b.jsonl", [blob_of("user", [instruction(files("b"))])],
                start=5, ref="r2")
    result = cachelib.compare_first_requests(a, b)
    assert result.instruction_file_kind == "memory-index"


def test_identical_transcripts_compare_as_none_and_comparable(tmp_path):
    """Adversarial where: a pair of identical first requests reports a
    difference."""
    blobs = [blob_of("user", [instruction([("project", "CLAUDE.md", "p")])])]
    a = session(tmp_path / "a.jsonl", blobs)
    result = cachelib.compare_first_requests(a, a)
    assert (result.comparable, result.first_difference, result.instruction_file_kind) == (
        True, "none", None)


def test_gap_is_negative_not_clamped_when_pair_overlaps(tmp_path):
    """Adversarial where: an overlapping pair is silently clamped or turned
    into None; a negative gap tells the caller the pair is not sequential."""
    a = put(tmp_path / "a.jsonl", [asst("x", at(30), use(read=1))])
    b = put(tmp_path / "b.jsonl", [asst("y", at(10), use(read=1))])
    assert cachelib.compare_first_requests(a, b).gap_minutes == pytest.approx(-20.0)


# ---- ledger --------------------------------------------------------------


def test_ledger_that_is_a_directory_gives_zeros(tmp_path):
    """Adversarial where: an OSError other than missing-file escapes."""
    (tmp_path / "ledger.jsonl").mkdir()
    assert cachelib.ledger_totals(tmp_path) == cachelib.LedgerTotals(0, 0, 0, 0)


def test_ledger_run_rows_with_odd_values_still_count_as_runs(tmp_path):
    """Adversarial where: a run row with bad values is dropped from run_count
    along with its values."""
    put(tmp_path / "ledger.jsonl", [
        {"type": "run", "cache_read_tokens": "5", "cache_creation_tokens": 2.5,
         "input_tokens": True},
        {"type": "run", "cache_read_tokens": 7},
        {"type": "RUN", "cache_read_tokens": 100},
        {"cache_read_tokens": 100},
    ])
    assert cachelib.ledger_totals(str(tmp_path)) == cachelib.LedgerTotals(2, 7, 0, 0)
