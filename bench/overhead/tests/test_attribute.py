"""Tests for attribute.py: reconciling a build's token records and probing the split by source.

Interface under test:

    attribute.reconcile_build(folder, logged) -> dict
        logged       {"weighted", "raw"} from the pilot run log
        "logged", "cost_state" (weighted/raw None when no session wrote one), "records",
        "workers", "causes" ([{"cause", "weighted", "raw"}]), "unattributed", "agrees",
        "web_calls"
    attribute.attachment_kinds(folders) -> {kind: {"reached", "empty", "chars"}}
    attribute.rebuild_requests(lines) -> [{"id", "status", "api_tokens", "bytes"}]
    attribute.compare_requests(rows) -> {"requests", "pooled", "first", "median", "min", "max", ...}
    attribute.run_ablation(items, *, make_project, run_prompt, read_first_request) -> rows
    attribute.analyze_console(text, nonce, names) -> dict
    attribute.render_section(result) / replace_section(report_text, section)
    attribute.discard_projects(...)

Adversarial themes: a response written as several records or repeated in a
subagent file counted twice; a killed session's last turn credited to the wrong
place; a mismatch no cause explains passing as agreement; a cache-token gap
named an auxiliary request; multi-byte text measured in characters; an
unresolvable request chain raising or skewing the ratio; a zero-byte ablation
dividing by zero; message text, session ids or paths reaching the report;
projects deleted before the report is committed.
"""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

import attribute
import records

OPUS = "claude-opus-5-5"
HAIKU = "claude-haiku-5-5"
SESSION = "5e5510aa-1111-4222-8333-444455556666"
OTHER_SESSION = "0ddba11c-1111-4222-8333-444455556666"
SECRET_TEXT = "the user wants a lighthouse keeper simulator"
SECRET_PATH = "C:/work/proj-secret/notes.md"
DASHES = (chr(0x2013), chr(0x2014))
WORKER_PROMPT = "Read the file .claude/skills/extract-lessons/SKILL.md"


def usage(input_=0, read=0, write=0, output=0):
    return {"input_tokens": input_, "cache_read_input_tokens": read,
            "cache_creation_input_tokens": write, "output_tokens": output}


def assistant(message_id, use, ts, model=OPUS, blocks=None, ref=None, session=SESSION):
    return {
        "type": "assistant", "timestamp": ts, "sessionId": session, "requestRef": ref,
        "message": {"id": message_id, "model": model, "usage": use,
                    "content": blocks if blocks is not None else [{"type": "text", "text": "ok"}]},
    }


def user(text, ts="2026-01-01T00:00:00.000Z", session=SESSION):
    return {"type": "user", "timestamp": ts, "sessionId": session,
            "message": {"role": "user", "content": text}}


def stop(ts):
    return {"type": "system", "subtype": "stop_hook_summary", "timestamp": ts}


def cost_state(**models):
    """cost_state(**{"claude-opus-5-5": (input, read, write, output)}) with `_` for `-`."""
    usage_by_model = {}
    for name, (input_, read, write, output) in models.items():
        usage_by_model[name.replace("_", "-")] = {
            "inputTokens": input_, "cacheReadInputTokens": read,
            "cacheCreationInputTokens": write, "outputTokens": output,
        }
    return {"type": "cost-state", "sessionId": SESSION, "modelUsage": usage_by_model}


def write_lines(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


def write_session(folder, name, lines):
    write_lines(folder / f"{name}.jsonl", lines)


def write_subagent(folder, parent, name, lines, agent="builder"):
    base = folder / parent / "subagents"
    write_lines(base / f"{name}.jsonl", lines)
    (base / f"{name}.meta.json").write_text(json.dumps({"agentType": agent}), encoding="utf-8")


def weighted_of(**models):
    totals = {}
    for name, (input_, read, write, output) in models.items():
        totals[name.replace("_", "-")] = {"input": input_, "cache_read": read, "cache_write": write, "output": output}
    return records.weigh(totals)[0]


@pytest.fixture
def folder(tmp_path):
    folder = tmp_path / "C--work-proj-secret"
    folder.mkdir()
    return folder


def tokens(use):
    return use["input_tokens"] + use["cache_read_input_tokens"] + use["cache_creation_input_tokens"] + use["output_tokens"]


def clean_build(folder):
    """One build session of two responses that wrote its own totals."""
    first, second = usage(5, 0, 1000, 40), usage(2, 1000, 500, 60)
    write_session(folder, SESSION, [
        user(SECRET_TEXT),
        assistant("m1", first, "2026-01-01T00:00:01.000Z"),
        assistant("m2", second, "2026-01-01T00:00:02.000Z"),
        stop("2026-01-01T00:00:03.000Z"),
        cost_state(claude_opus_5_5=(7, 1000, 1500, 100)),
    ])
    raw = tokens(first) + tokens(second)
    weighted = weighted_of(claude_opus_5_5=(7, 1000, 1500, 100))
    return {"weighted": weighted, "raw": raw}


# reconciliation


def test_a_clean_build_agrees_in_all_three_totals_and_names_no_cause(folder):
    logged = clean_build(folder)
    result = attribute.reconcile_build(folder, logged)
    assert result["records"]["raw"] == result["cost_state"]["raw"] == logged["raw"]
    assert result["records"]["weighted"] == pytest.approx(logged["weighted"])
    assert result["cost_state"]["weighted"] == pytest.approx(logged["weighted"])
    assert result["causes"] == []
    assert result["agrees"] is True


def test_a_response_written_as_several_records_and_in_a_subagent_file_counts_once(folder):
    use = usage(3, 100, 50, 10)
    write_session(folder, SESSION, [
        user(SECRET_TEXT),
        assistant("m1", use, "2026-01-01T00:00:01.000Z"),
        assistant("m1", use, "2026-01-01T00:00:01.500Z"),
        stop("2026-01-01T00:00:03.000Z"),
    ])
    write_subagent(folder, SESSION, "agent-1", [assistant("m1", use, "2026-01-01T00:00:02.000Z")])
    result = attribute.reconcile_build(folder, {"weighted": 0, "raw": 0})
    assert result["records"]["raw"] == tokens(use)
    assert result["records"]["responses"] == 1


def test_a_constructed_mismatch_is_flagged_with_its_size_and_no_cause(folder):
    logged = clean_build(folder)
    inflated = {"weighted": logged["weighted"] * 1.1, "raw": int(logged["raw"] * 1.1)}
    result = attribute.reconcile_build(folder, inflated)
    assert result["agrees"] is False
    assert result["causes"] == []
    assert result["unattributed"]["raw"] == logged["raw"] - inflated["raw"]
    assert result["unattributed"]["weighted"] == pytest.approx(logged["weighted"] - inflated["weighted"])


def test_a_gap_inside_the_tolerance_still_agrees(folder):
    logged = clean_build(folder)
    nudged = {"weighted": logged["weighted"] + 1, "raw": logged["raw"] + 1}
    assert attribute.reconcile_build(folder, nudged)["agrees"] is True


def test_a_killed_session_credits_the_turn_after_the_last_stop_to_an_unfinished_turn(folder):
    done, lost = usage(5, 0, 1000, 40), usage(2, 1000, 500, 60)
    sub_done, sub_lost = usage(1, 0, 200, 10), usage(1, 0, 300, 20)
    write_session(folder, SESSION, [
        user("start"),
        assistant("m1", done, "2026-01-01T00:00:01.000Z"),
        stop("2026-01-01T00:00:02.000Z"),
        user("next"),
        assistant("m2", lost, "2026-01-01T00:00:03.000Z"),
    ])
    write_subagent(folder, SESSION, "agent-1", [
        assistant("s1", sub_done, "2026-01-01T00:00:01.500Z"),
        assistant("s2", sub_lost, "2026-01-01T00:00:03.500Z"),
    ])
    logged_raw = tokens(done) + tokens(sub_done)
    logged = {"weighted": weighted_of(claude_opus_5_5=(6, 0, 1200, 50)), "raw": logged_raw}
    result = attribute.reconcile_build(folder, logged)
    assert result["cost_state"]["raw"] is None and result["cost_state"]["missing"] == 1
    assert [c["cause"] for c in result["causes"]] == [attribute.UNFINISHED_TURN]
    assert result["causes"][0]["raw"] == tokens(lost) + tokens(sub_lost)
    assert result["records"]["raw"] == logged_raw + tokens(lost) + tokens(sub_lost)
    assert result["unattributed"]["raw"] == 0
    assert result["agrees"] is True


def test_a_killed_session_with_no_stop_marker_loses_the_whole_session_to_the_unfinished_turn(folder):
    use = usage(5, 0, 1000, 40)
    write_session(folder, SESSION, [user("start"), assistant("m1", use, "2026-01-01T00:00:01.000Z")])
    result = attribute.reconcile_build(folder, {"weighted": 0, "raw": 0})
    assert result["causes"][0]["cause"] == attribute.UNFINISHED_TURN
    assert result["causes"][0]["raw"] == tokens(use)


def test_a_session_that_wrote_cost_state_never_has_an_unfinished_turn(folder):
    use = usage(5, 0, 1000, 40)
    write_session(folder, SESSION, [
        user("start"), assistant("m1", use, "2026-01-01T00:00:01.000Z"),
        user("again"), assistant("m2", use, "2026-01-01T00:00:03.000Z"),
        cost_state(claude_opus_5_5=(10, 0, 2000, 80)),
    ])
    result = attribute.reconcile_build(folder, {"weighted": 0, "raw": 0})
    assert all(c["cause"] != attribute.UNFINISHED_TURN for c in result["causes"])


def test_input_and_output_beyond_the_records_of_one_model_are_an_auxiliary_request(folder):
    main, extra_in, extra_out = usage(5, 0, 1000, 40), 15000, 700
    write_session(folder, SESSION, [
        user("start"),
        assistant("m1", main, "2026-01-01T00:00:01.000Z"),
        assistant("h1", usage(1, 50, 60, 2), "2026-01-01T00:00:01.500Z", model=HAIKU),
        stop("2026-01-01T00:00:03.000Z"),
        cost_state(claude_opus_5_5=(5, 0, 1000, 40), claude_haiku_5_5=(1 + extra_in, 50, 60, 2 + extra_out)),
    ])
    summed = tokens(main) + 1 + 50 + 60 + 2
    logged = {"weighted": weighted_of(claude_opus_5_5=(5, 0, 1000, 40)), "raw": summed + extra_in + extra_out}
    result = attribute.reconcile_build(folder, logged)
    assert [c["cause"] for c in result["causes"]] == [attribute.AUXILIARY_REQUEST]
    assert result["causes"][0]["raw"] == extra_in + extra_out
    assert result["causes"][0]["weighted"] == 0.0
    assert result["cost_state"]["raw"] == logged["raw"]
    assert result["records"]["raw"] == summed
    assert result["agrees"] is True


def test_a_cache_token_gap_is_not_named_an_auxiliary_request(folder):
    write_session(folder, SESSION, [
        user("start"), assistant("m1", usage(5, 0, 1000, 40), "2026-01-01T00:00:01.000Z"),
        stop("2026-01-01T00:00:03.000Z"),
        cost_state(claude_opus_5_5=(5, 9000, 1000, 40)),
    ])
    result = attribute.reconcile_build(folder, {"weighted": 0, "raw": 0})
    assert result["causes"] == []
    assert result["cost_state"]["raw"] - result["records"]["raw"] == 9000


def test_a_gap_beside_a_compaction_is_named_compaction(folder):
    write_session(folder, SESSION, [
        user("start"), assistant("m1", usage(5, 0, 1000, 40), "2026-01-01T00:00:01.000Z"),
        {"type": "system", "subtype": "compact_boundary", "timestamp": "2026-01-01T00:00:02.000Z"},
        stop("2026-01-01T00:00:03.000Z"),
        cost_state(claude_opus_5_5=(5, 9000, 1000, 40)),
    ])
    result = attribute.reconcile_build(folder, {"weighted": 0, "raw": 0})
    assert [c["cause"] for c in result["causes"]] == [attribute.COMPACTION]
    assert result["causes"][0]["raw"] == 9000


def test_records_above_the_session_totals_with_two_session_ids_are_a_resume(folder):
    old, new = usage(5, 0, 1000, 40), usage(2, 100, 0, 10)
    write_session(folder, SESSION, [
        user("start", session=OTHER_SESSION),
        assistant("m1", old, "2026-01-01T00:00:01.000Z", session=OTHER_SESSION),
        assistant("m2", new, "2026-01-01T00:00:02.000Z"),
        stop("2026-01-01T00:00:03.000Z"),
        cost_state(claude_opus_5_5=(2, 100, 0, 10)),
    ])
    logged = {"weighted": weighted_of(claude_opus_5_5=(2, 100, 0, 10)), "raw": tokens(new)}
    result = attribute.reconcile_build(folder, logged)
    assert [c["cause"] for c in result["causes"]] == [attribute.RESUME]
    assert result["causes"][0]["raw"] == tokens(old)
    assert result["agrees"] is True


def test_records_above_the_session_totals_with_one_session_id_stay_unexplained(folder):
    write_session(folder, SESSION, [
        user("start"), assistant("m1", usage(5, 0, 1000, 40), "2026-01-01T00:00:01.000Z"),
        stop("2026-01-01T00:00:03.000Z"),
        cost_state(claude_opus_5_5=(1, 0, 10, 1)),
    ])
    logged = {"weighted": weighted_of(claude_opus_5_5=(1, 0, 10, 1)), "raw": 12}
    result = attribute.reconcile_build(folder, logged)
    assert result["causes"] == []
    assert result["agrees"] is False


def test_a_model_with_no_price_adds_raw_tokens_and_no_weight(folder):
    write_session(folder, SESSION, [
        user("start"), assistant("h1", usage(100, 0, 0, 50), "2026-01-01T00:00:01.000Z", model=HAIKU),
        stop("2026-01-01T00:00:03.000Z"),
    ])
    result = attribute.reconcile_build(folder, {"weighted": 0, "raw": 150})
    assert result["records"]["raw"] == 150
    assert result["records"]["weighted"] == 0
    assert result["agrees"] is True


def test_capture_workers_are_reported_apart_and_stay_out_of_the_build_totals(folder):
    clean = clean_build(folder)
    write_session(folder, "11111111-1111-4111-8111-111111111111", [
        user(WORKER_PROMPT), assistant("w1", usage(1, 0, 400, 30), "2026-01-01T00:00:05.000Z"),
        cost_state(claude_opus_5_5=(1, 0, 400, 30)),
    ])
    result = attribute.reconcile_build(folder, clean)
    assert result["workers"]["sessions"] == 1
    assert result["workers"]["raw"] == 431
    assert result["records"]["raw"] == clean["raw"]
    assert result["agrees"] is True


def test_cost_state_totals_cover_only_the_sessions_that_wrote_one(folder):
    clean = clean_build(folder)
    write_session(folder, "22222222-2222-4222-8222-222222222222", [
        user("/compass:setup " + "<command-name>/compass:setup</command-name>"),
        assistant("p1", usage(1, 0, 10, 1), "2026-01-01T00:00:00.100Z"),
    ])
    result = attribute.reconcile_build(folder, clean)
    assert result["cost_state"]["sessions"] == 1
    assert result["cost_state"]["missing"] == 1
    assert result["cost_state"]["raw"] == clean["raw"]


def test_web_calls_count_each_tool_call_once_across_streamed_records_and_subagents(folder):
    fetch = [{"type": "tool_use", "id": "t1", "name": "WebFetch", "input": {"url": "u"}}]
    search = [{"type": "tool_use", "id": "t2", "name": "WebSearch", "input": {"query": "q"}}]
    write_session(folder, SESSION, [
        user("start"),
        assistant("m1", usage(1, 0, 1, 1), "2026-01-01T00:00:01.000Z", blocks=fetch),
        assistant("m1", usage(1, 0, 1, 1), "2026-01-01T00:00:01.100Z", blocks=fetch),
        stop("2026-01-01T00:00:03.000Z"),
    ])
    write_subagent(folder, SESSION, "agent-1", [assistant("s1", usage(1, 0, 1, 1), "2026-01-01T00:00:02.000Z", blocks=search)])
    assert attribute.reconcile_build(folder, {"weighted": 0, "raw": 0})["web_calls"] == 2


def test_a_killed_build_with_web_calls_names_its_raw_gap_an_inferred_auxiliary_request(folder):
    fetch = [{"type": "tool_use", "id": "t1", "name": "WebFetch", "input": {"url": "u"}}]
    write_session(folder, SESSION, [
        user("start"), assistant("m1", usage(5, 0, 1000, 40), "2026-01-01T00:00:01.000Z", blocks=fetch),
        stop("2026-01-01T00:00:03.000Z"),
    ])
    result = attribute.reconcile_build(folder, {"weighted": weighted_of(claude_opus_5_5=(5, 0, 1000, 40)), "raw": 1045 + 12000})
    named = [c["cause"] for c in result["causes"]]
    assert named == [attribute.AUXILIARY_INFERRED]
    assert result["causes"][0]["raw"] == 12000
    assert result["unattributed"]["raw"] == 0


def test_a_killed_build_without_web_calls_leaves_its_raw_gap_unattributed(folder):
    write_session(folder, SESSION, [
        user("start"), assistant("m1", usage(5, 0, 1000, 40), "2026-01-01T00:00:01.000Z"),
        stop("2026-01-01T00:00:03.000Z"),
    ])
    result = attribute.reconcile_build(folder, {"weighted": weighted_of(claude_opus_5_5=(5, 0, 1000, 40)), "raw": 1045 + 12000})
    assert result["causes"] == []
    assert result["unattributed"]["raw"] == -12000
    assert result["agrees"] is False


def test_the_result_holds_no_text_session_id_or_path(folder):
    use = usage(5, 0, 1000, 40)
    write_session(folder, SESSION, [
        user(SECRET_TEXT),
        assistant("m1", use, "2026-01-01T00:00:01.000Z",
                  blocks=[{"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": SECRET_PATH}}]),
        stop("2026-01-01T00:00:03.000Z"),
    ])
    dumped = json.dumps(attribute.reconcile_build(folder, {"weighted": 0, "raw": 0}))
    for secret in (SECRET_TEXT, SESSION, SECRET_PATH, "proj-secret"):
        assert secret not in dumped


def test_a_folder_with_no_session_is_refused(folder):
    with pytest.raises(ValueError):
        attribute.reconcile_build(folder, {"weighted": 0, "raw": 0})


# attachment kinds


def attachment(kind, rendered):
    return {"type": "attachment", "attachment": {"type": kind}, "rendered": rendered}


def test_attachment_kinds_split_rendered_text_from_empty_renderings(folder):
    write_session(folder, SESSION, [
        attachment("skill_listing", [{"content": "x" * 30}]),
        attachment("skill_listing", [{"content": "y" * 20}]),
        attachment("environment", []),
        attachment("todo_reminder", None),
        attachment("edited_text_file", [{"content": ""}]),
    ])
    write_subagent(folder, SESSION, "agent-1", [attachment("skill_listing", [{"content": "z" * 5}])])
    found = attribute.attachment_kinds([folder])
    assert found["skill_listing"] == {"reached": 3, "empty": 0, "chars": 55}
    assert found["environment"]["reached"] == 0 and found["environment"]["empty"] == 1
    assert found["todo_reminder"]["reached"] == 0
    assert found["edited_text_file"]["reached"] == 0


def test_attachment_kinds_pool_over_folders_and_name_a_typeless_attachment_unknown(folder, tmp_path):
    second = tmp_path / "other"
    second.mkdir()
    write_session(folder, SESSION, [attachment("skill_listing", [{"content": "x"}])])
    write_session(second, SESSION, [attachment("skill_listing", [{"content": "yy"}]),
                                    {"type": "attachment", "attachment": {}, "rendered": [{"content": "q"}]}])
    found = attribute.attachment_kinds([folder, second])
    assert found["skill_listing"]["reached"] == 2 and found["skill_listing"]["chars"] == 3
    assert found["unknown"]["reached"] == 1


# request text against the API's input count


def message_hash(message):
    text = json.dumps(message, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def blob(message):
    return {"type": "api-request-blob", "hash": message_hash(message), "message": message}


def shape(system="sys", tools=()):
    return {"type": "api-request-shape", "shapeHash": "h1",
            "shape": {"system": [{"type": "text", "text": system}], "tools": list(tools)}}


def request(request_id, tail, keep=0, base=None):
    row = {"type": "api-request", "id": request_id, "shapeHash": "h1", "keep": keep,
           "tail": [message_hash(m) if isinstance(m, dict) else m for m in tail]}
    if base:
        row["base"] = base
    return row


def text_message(role, text):
    return {"role": role, "content": [{"type": "text", "text": text}]}


def session_with_two_requests():
    """Two requests: the second keeps the first's two messages and adds two."""
    first = [text_message("user", "h\u00e9llo"), text_message("system", "note")]
    answer = text_message("assistant", "ok")
    result = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "fine"}]}
    return [
        shape(),
        blob(first[0]), blob(first[1]),
        request("r1", first),
        assistant("m1", usage(2, 0, 30, 5), "2026-01-01T00:00:01.000Z", ref="r1"),
        blob(answer),
        {"type": "user", "timestamp": "2026-01-01T00:00:02.000Z", "message": result},
        request("r2", [answer, result], keep=2, base="r1"),
        assistant("m2", usage(2, 30, 10, 5), "2026-01-01T00:00:03.000Z", ref="r2"),
    ], result


def test_a_request_is_rebuilt_from_its_base_the_kept_messages_and_its_tail_in_utf8_bytes():
    lines, _ = session_with_two_requests()
    rows = attribute.rebuild_requests(lines)
    assert [row["status"] for row in rows] == ["ok", "ok"]
    # "sys", "h\u00e9llo" (6 bytes), "note", joined by newlines
    assert rows[0]["bytes"] == len("sys\nh\u00e9llo\nnote".encode("utf-8")) == 15
    assert rows[1]["bytes"] == len("sys\nh\u00e9llo\nnote\nok\nfine".encode("utf-8"))
    assert rows[0]["api_tokens"] == 32
    assert rows[1]["api_tokens"] == 42


def test_multibyte_text_counts_bytes_and_not_characters():
    wide = "\u00e9" * 10 + "\U0001f600" * 5
    lines = [shape(system=""), blob(text_message("user", wide)),
             request("r1", [text_message("user", wide)]),
             assistant("m1", usage(1, 0, 0, 1), "2026-01-01T00:00:01.000Z", ref="r1")]
    assert attribute.rebuild_requests(lines)[0]["bytes"] == len(wide.encode("utf-8")) == 40


def test_the_api_count_is_the_last_record_of_a_response_written_in_pieces():
    lines, _ = session_with_two_requests()
    lines.insert(4, assistant("m1", usage(2, 0, 1, 1), "2026-01-01T00:00:00.900Z", ref="r1"))
    assert attribute.rebuild_requests(lines)[0]["api_tokens"] == 32


def test_a_tail_hash_that_resolves_to_nothing_marks_the_request_unresolved_without_raising():
    lines = [shape(), request("r1", ["f" * 64]),
             assistant("m1", usage(1, 0, 0, 1), "2026-01-01T00:00:01.000Z", ref="r1")]
    rows = attribute.rebuild_requests(lines)
    assert rows[0]["status"] == "unresolved"
    assert rows[0]["bytes"] is None


def test_a_keep_beyond_the_base_or_a_missing_base_marks_the_request_unresolved():
    lines, _ = session_with_two_requests()
    lines[7]["keep"] = 9
    assert attribute.rebuild_requests(lines)[1]["status"] == "unresolved"
    lines, _ = session_with_two_requests()
    lines[7]["base"] = "no-such-request"
    assert attribute.rebuild_requests(lines)[1]["status"] == "unresolved"


def test_a_request_with_an_image_is_skipped_as_media_and_a_request_with_no_response_is_noted():
    picture = {"role": "user", "content": [{"type": "image", "source": {"data": "AAAA"}}]}
    lines = [shape(), blob(picture), request("r1", [picture]),
             assistant("m1", usage(1, 0, 0, 1), "2026-01-01T00:00:01.000Z", ref="r1"),
             blob(text_message("user", "x")), request("r2", [text_message("user", "x")])]
    rows = attribute.rebuild_requests(lines)
    assert rows[0]["status"] == "media"
    assert rows[1]["status"] == "no response"


def test_tool_definitions_and_tool_calls_count_toward_the_request_text():
    tool = {"name": "Bash", "description": "runs a command"}
    call = {"role": "assistant", "content": [{"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": "ls"}}]}
    base_only = [shape(tools=[]), blob(text_message("user", "x")), request("r1", [text_message("user", "x")]),
                 assistant("m1", usage(1, 0, 0, 1), "2026-01-01T00:00:01.000Z", ref="r1")]
    with_more = [shape(tools=[tool]), blob(text_message("user", "x")), blob(call),
                 request("r1", [text_message("user", "x"), call]),
                 assistant("m1", usage(1, 0, 0, 1), "2026-01-01T00:00:01.000Z", ref="r1")]
    plain = attribute.rebuild_requests(base_only)[0]["bytes"]
    richer = attribute.rebuild_requests(with_more)[0]["bytes"]
    assert richer > plain + len(json.dumps(tool))


def test_the_ratio_pools_tokens_over_bytes_divided_by_four_and_skips_what_it_cannot_measure():
    rows = [
        {"id": "a", "status": "ok", "api_tokens": 100, "bytes": 200},
        {"id": "b", "status": "ok", "api_tokens": 300, "bytes": 400},
        {"id": "c", "status": "unresolved", "api_tokens": 50, "bytes": None},
        {"id": "d", "status": "media", "api_tokens": 50, "bytes": None},
        {"id": "e", "status": "no response", "api_tokens": None, "bytes": 10},
    ]
    summary = attribute.compare_requests(rows)
    assert summary["requests"] == 2
    assert summary["skipped"] == {"unresolved": 1, "media": 1, "no response": 1}
    assert summary["pooled"] == pytest.approx(400 / (600 / 4))
    assert summary["first"] == pytest.approx(100 / (200 / 4))
    assert summary["min"] == pytest.approx(2.0)
    assert summary["max"] == pytest.approx(3.0)
    assert summary["median"] == pytest.approx(2.5)


def test_a_comparison_with_nothing_measurable_has_no_ratio_and_does_not_divide_by_zero():
    summary = attribute.compare_requests([{"id": "a", "status": "ok", "api_tokens": 5, "bytes": 0}])
    assert summary["pooled"] is None and summary["first"] is None


def test_rendered_attachments_are_checked_against_the_rebuilt_requests():
    note = text_message("system", "budget note")
    lines = [shape(), blob(note), request("r1", [note]),
             assistant("m1", usage(1, 0, 0, 1), "2026-01-01T00:00:01.000Z", ref="r1"),
             attachment("budget_usd", [{"content": "budget note"}]),
             attachment("never_sent", [{"content": "text the model never saw"}]),
             attachment("empty_one", [])]
    assert attribute.attachments_in_requests(lines) == {"rendered": 2, "found": 1}


def test_a_system_reminder_wrapper_around_a_rendered_attachment_does_not_hide_it_from_the_match():
    note = text_message("system", "budget note")
    lines = [shape(), blob(note), request("r1", [note]),
             assistant("m1", usage(1, 0, 0, 1), "2026-01-01T00:00:01.000Z", ref="r1"),
             attachment("budget_usd", [{"content": "<system-reminder>\nbudget note\n</system-reminder>"}])]
    assert attribute.attachments_in_requests(lines) == {"rendered": 1, "found": 1}


def test_parallel_tool_results_and_a_split_reply_resolve_to_the_request_messages():
    reply_a = {"role": "assistant", "content": [{"type": "thinking", "thinking": "", "signature": "x"}]}
    reply_b = {"role": "assistant", "content": [{"type": "text", "text": "calling"}]}
    joined_reply = {"role": "assistant", "content": reply_a["content"] + reply_b["content"]}
    res_a = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "one"}]}
    res_b = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "b", "content": "two"}]}
    both = {"role": "user", "content": res_a["content"] + res_b["content"]}
    first = text_message("user", "go")
    lines = [
        shape(), blob(first), request("r1", [first]),
        {"type": "assistant", "requestRef": "r1", "message": dict(reply_a, id="m1", usage=usage(1, 0, 0, 1))},
        {"type": "assistant", "requestRef": "r1", "message": dict(reply_b, id="m1", usage=usage(1, 0, 0, 1))},
        {"type": "user", "message": res_a}, {"type": "user", "message": res_b},
        request("r2", [joined_reply, both], keep=1, base="r1"),
        assistant("m2", usage(1, 0, 0, 1), "2026-01-01T00:00:03.000Z", ref="r2"),
    ]
    rows = attribute.rebuild_requests(lines)
    assert rows[1]["status"] == "ok"
    assert rows[1]["bytes"] == len("sys\ngo\ncalling\none\ntwo")


def test_a_request_chain_that_loops_is_unresolved_and_does_not_hang():
    first = text_message("user", "go")
    lines = [shape(), blob(first), request("r1", [first], base="r2"), request("r2", [first], base="r1"),
             assistant("m1", usage(1, 0, 0, 1), "2026-01-01T00:00:01.000Z", ref="r1")]
    assert [row["status"] for row in attribute.rebuild_requests(lines)] == ["unresolved", "unresolved"]


# ablation


class Fake:
    """Stands in for the session runner: a fixed token count per file placed in the project."""

    def __init__(self, tmp_path, per_item):
        self.tmp_path = tmp_path
        self.per_item = per_item
        self.projects = []
        self.prompts = []

    def make_project(self):
        project = self.tmp_path / f"proj-{len(self.projects):06x}"
        project.mkdir()
        self.projects.append(project)
        return project

    def run_prompt(self, project):
        self.prompts.append(project)
        return [{"type": "result", "modelUsage": {OPUS: {"inputTokens": 1, "outputTokens": 1,
                                                          "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0}}}]

    def read_first_request(self, project):
        base_tokens, base_bytes = 20000, 60000
        extra_tokens = extra_bytes = 0
        for relative, (tokens_, bytes_) in self.per_item.items():
            if (project / relative).exists():
                extra_tokens += tokens_
                extra_bytes += bytes_
        return {"tokens": base_tokens + extra_tokens, "bytes": base_bytes + extra_bytes, "model": OPUS}


def item_files(tmp_path):
    rules = tmp_path / "src" / "rule.md"
    skill = tmp_path / "src" / "SKILL.md"
    agent = tmp_path / "src" / "agent.md"
    rules.parent.mkdir()
    rules.write_text("r" * 4000, encoding="utf-8")
    skill.write_text("s" * 2000, encoding="utf-8")
    agent.write_text("a" * 800, encoding="utf-8")
    return [
        attribute.Item("rules file", rules, ".claude/rules/rule.md"),
        attribute.Item("skill", skill, ".claude/skills/methodology/SKILL.md"),
        attribute.Item("agent definition", agent, ".claude/agents/builder.md"),
    ]


def test_each_item_is_placed_on_its_own_path_and_measured_against_one_baseline(tmp_path):
    fake = Fake(tmp_path / "w", {
        ".claude/rules/rule.md": (1000, 4000),
        ".claude/skills/methodology/SKILL.md": (40, 150),
        ".claude/agents/builder.md": (30, 120),
    })
    (tmp_path / "w").mkdir()
    rows = attribute.run_ablation(
        item_files(tmp_path), make_project=fake.make_project, run_prompt=fake.run_prompt,
        read_first_request=fake.read_first_request,
    )
    assert len(fake.prompts) == 4 and len(set(fake.prompts)) == 4
    by = {row["label"]: row for row in rows}
    assert by["rules file"]["delta_tokens"] == 1000
    assert by["rules file"]["ratio_to_file"] == pytest.approx(1000 / (4000 / 4))
    assert by["rules file"]["ratio_to_added"] == pytest.approx(1000 / (4000 / 4))
    assert by["skill"]["delta_tokens"] == 40
    assert by["skill"]["file_bytes"] == 2000
    assert by["skill"]["ratio_to_file"] == pytest.approx(40 / (2000 / 4))
    assert by["skill"]["ratio_to_added"] == pytest.approx(40 / (150 / 4))
    assert by["agent definition"]["added_bytes"] == 120
    assert by["agent definition"]["tokens_with"] == by["agent definition"]["tokens_without"] + 30
    assert not (fake.projects[0] / ".claude").exists()


def test_an_item_that_adds_no_bytes_has_no_ratio_to_added_bytes(tmp_path):
    (tmp_path / "w").mkdir()
    fake = Fake(tmp_path / "w", {".claude/rules/rule.md": (5, 0)})
    rows = attribute.run_ablation(
        item_files(tmp_path)[:1], make_project=fake.make_project, run_prompt=fake.run_prompt,
        read_first_request=fake.read_first_request,
    )
    assert rows[0]["ratio_to_added"] is None
    assert rows[0]["ratio_to_file"] == pytest.approx(5 / 1000)


def test_a_negative_delta_is_reported_with_its_sign(tmp_path):
    (tmp_path / "w").mkdir()
    fake = Fake(tmp_path / "w", {".claude/rules/rule.md": (-7, 4000)})
    rows = attribute.run_ablation(
        item_files(tmp_path)[:1], make_project=fake.make_project, run_prompt=fake.run_prompt,
        read_first_request=fake.read_first_request,
    )
    assert rows[0]["delta_tokens"] == -7
    assert rows[0]["ratio_to_file"] < 0


def test_a_missing_item_file_stops_the_ablation_before_any_session_runs(tmp_path):
    (tmp_path / "w").mkdir()
    fake = Fake(tmp_path / "w", {})
    items = [attribute.Item("skill", tmp_path / "gone.md", ".claude/skills/x/SKILL.md")]
    with pytest.raises(FileNotFoundError):
        attribute.run_ablation(items, make_project=fake.make_project, run_prompt=fake.run_prompt,
                               read_first_request=fake.read_first_request)
    assert fake.prompts == []


def test_the_cost_of_the_calls_sums_the_weighted_tokens_of_their_results():
    events = [[{"type": "result", "modelUsage": {OPUS: {"inputTokens": 10, "outputTokens": 2,
                                                         "cacheReadInputTokens": 100, "cacheCreationInputTokens": 20}}}],
              [{"type": "result", "modelUsage": {OPUS: {"inputTokens": 10, "outputTokens": 2,
                                                         "cacheReadInputTokens": 100, "cacheCreationInputTokens": 20}}}]]
    cost = attribute.call_cost(events)
    assert cost["calls"] == 2
    assert cost["raw"] == 264
    assert cost["weighted"] == pytest.approx(2 * (10 + 5 * 2 + 0.05 * 100 + 1.25 * 20))


def test_a_first_request_is_read_from_the_only_transcript_of_a_project(tmp_path):
    private = tmp_path / "private"
    project = tmp_path / "projects" / "proj-aaaaaa"
    project.mkdir(parents=True)
    transcripts = attribute.token_profile.transcript_folder(project, private)
    transcripts.mkdir(parents=True)
    lines, _ = session_with_two_requests()
    write_session(transcripts, SESSION, lines)
    first = attribute.read_first_request(project, private)
    assert first["tokens"] == 32
    assert first["bytes"] == 15
    assert first["model"] == OPUS


def test_a_project_with_two_sessions_is_refused_by_the_first_request_reader(tmp_path):
    private = tmp_path / "private"
    project = tmp_path / "projects" / "proj-aaaaaa"
    project.mkdir(parents=True)
    transcripts = attribute.token_profile.transcript_folder(project, private)
    transcripts.mkdir(parents=True)
    lines, _ = session_with_two_requests()
    write_session(transcripts, SESSION, lines)
    write_session(transcripts, OTHER_SESSION, lines)
    with pytest.raises(ValueError):
        attribute.read_first_request(project, private)


# console exporter


def test_names_in_the_exporter_output_count_when_the_prompt_was_not_echoed():
    text = "\n".join([
        "{ name: 'claude_code.tool_result', attributes: { tool_name: 'Skill', skill_name: 'methodology' } }",
        "{ name: 'claude_code.tool_result', attributes: { tool_name: 'Agent', subagent_type: 'builder' } }",
        "{ name: 'claude_code.api_request' }",
    ])
    found = attribute.analyze_console(text, "NONCE-123", {"skill": "methodology", "agent": "builder"})
    assert found["wrote_output"] is True
    assert found["prompt_echoed"] is False
    assert found["skill_named"] is True and found["agent_named"] is True
    assert found["events"] == {"claude_code.tool_result": 2, "claude_code.api_request": 1}


def test_an_echoed_prompt_means_the_names_do_not_count():
    text = "{ prompt: 'NONCE-123 load methodology then builder' }"
    found = attribute.analyze_console(text, "NONCE-123", {"skill": "methodology", "agent": "builder"})
    assert found["prompt_echoed"] is True
    assert found["skill_named"] is False and found["agent_named"] is False


def test_an_exporter_that_wrote_nothing_names_nothing():
    found = attribute.analyze_console("  \n", "NONCE", {"skill": "methodology", "agent": "builder"})
    assert found["wrote_output"] is False
    assert found["skill_named"] is False and found["agent_named"] is False
    assert found["events"] == {}


def test_a_name_inside_a_longer_word_is_not_a_match():
    found = attribute.analyze_console("tool_name: 'Skill' x: 'methodologyx' y: 'rebuilder'", "N",
                                      {"skill": "methodology", "agent": "builder"})
    assert found["skill_named"] is False and found["agent_named"] is False


def test_invoked_tools_count_each_skill_and_agent_call_once(tmp_path):
    private = tmp_path / "private"
    project = tmp_path / "projects" / "proj-aaaaaa"
    project.mkdir(parents=True)
    transcripts = attribute.token_profile.transcript_folder(project, private)
    transcripts.mkdir(parents=True)
    skill = [{"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "x"}}]
    agent = [{"type": "tool_use", "id": "t2", "name": "Agent", "input": {"subagent_type": "y"}}]
    write_session(transcripts, SESSION, [
        assistant("m1", usage(1, 0, 0, 1), "2026-01-01T00:00:01.000Z", blocks=skill),
        assistant("m1", usage(1, 0, 0, 1), "2026-01-01T00:00:01.100Z", blocks=skill),
        assistant("m2", usage(1, 0, 0, 1), "2026-01-01T00:00:02.000Z", blocks=agent),
    ])
    assert attribute.invoked_tools(project, private) == {"skill": 1, "agent": 1}


def test_an_exporter_object_printed_as_json_is_kept_out_of_the_stream_events():
    stream = json.dumps({"type": "result", "modelUsage": {}})
    exporter = json.dumps({"name": "claude_code.tool_result", "attributes": {"tool_name": "Skill"}})
    events, rest = attribute.split_console("\n".join([stream, exporter, "plain line"]))
    assert [e["type"] for e in events] == ["result"]
    assert "claude_code.tool_result" in rest and "plain line" in rest


# the report section


def build_row(label, arm, end, w, causes=(), agrees=True):
    return {
        "label": label, "arm": arm, "end": end,
        "logged": {"weighted": w, "raw": w * 6},
        "cost_state": {"weighted": w if end == "human-done" else None, "raw": w * 6 if end == "human-done" else None,
                       "sessions": 2, "missing": 0 if end == "human-done" else 1},
        "records": {"weighted": w + 5, "raw": w * 6 - 9, "responses": 40},
        "workers": {"sessions": 2, "weighted": 11.0, "raw": 99},
        "causes": [dict(c) for c in causes],
        "unattributed": {"weighted": 0.0, "raw": 0}, "agrees": agrees, "web_calls": 3,
    }


def sample_result():
    return {
        "builds": [
            build_row("A1", "compass", "human-done", 1000, [{"cause": attribute.AUXILIARY_REQUEST, "weighted": 0.0, "raw": 77}]),
            build_row("B2", "compass", "wall-time", 2000, [{"cause": attribute.UNFINISHED_TURN, "weighted": 55.0, "raw": 300}]),
            build_row("C1", "baseline", "human-done", 500),
        ],
        "attachments": {
            "compass": {"skill_listing": {"reached": 9, "empty": 0, "chars": 1234},
                        "environment": {"reached": 0, "empty": 4, "chars": 0}},
            "baseline": {"skill_listing": {"reached": 3, "empty": 0, "chars": 99}},
        },
        "requests": {"requests": 10, "skipped": {"unresolved": 1}, "pooled": 1.31, "first": 1.25, "median": 1.3,
                     "min": 1.0, "max": 1.9, "attachments": {"rendered": 12, "found": 11}},
        "ablation": {
            "rows": [
                {"label": "rules file", "file_bytes": 9612, "tokens_without": 100, "tokens_with": 2500, "delta_tokens": 2400,
                 "added_bytes": 9700, "ratio_to_file": 0.9784, "ratio_to_added": 0.99},
                {"label": "skill", "file_bytes": 20852, "tokens_without": 100, "tokens_with": 160, "delta_tokens": 60,
                 "added_bytes": 300, "ratio_to_file": 0.01, "ratio_to_added": 0.8},
            ],
            "cost": {"calls": 4, "raw": 120000, "weighted": 30000.0},
        },
        "otel": {"wrote_output": True, "prompt_echoed": False, "skill_named": False, "agent_named": False,
                 "events": {"claude_code.tool_result": 3}, "cost": {"calls": 1, "raw": 90000, "weighted": 20000.0}},
    }


def test_the_section_lists_every_build_with_its_three_totals_and_each_ablation_ratio():
    text = attribute.render_section(sample_result())
    assert text.startswith(attribute.HEADING)
    for label in ("A1", "B2", "C1"):
        assert f"| {label} |" in text
    assert "1000" in text and "2000" in text and "500" in text
    assert attribute.UNFINISHED_TURN in text and attribute.AUXILIARY_REQUEST in text
    assert "0.98" in text
    assert "rules file" in text and "skill" in text
    assert "claude_code.tool_result" in text


def test_a_build_whose_session_wrote_no_cost_state_shows_it_as_not_available():
    text = attribute.render_section(sample_result())
    rows = {line.split("|")[1].strip() + line.split("|")[2].strip(): line for line in text.splitlines() if line.startswith("| B2 |")}
    assert "n/a" in rows["B2compass"]
    clean = [line for line in text.splitlines() if line.startswith("| C1 |")][0]
    assert "n/a" not in clean.split("|")[5]


def test_the_raw_and_cause_tables_name_the_arm_of_each_build():
    text = attribute.render_section(sample_result())
    assert "| Build | Arm | Logged |" in text
    assert "| Build | Arm | Cause |" in text


def test_the_section_holds_no_dash_character_and_no_private_detail():
    result = sample_result()
    result["builds"][0]["unattributed"]["raw"] = -5
    text = attribute.render_section(result)
    assert not any(dash in text for dash in DASHES)
    for secret in (SECRET_TEXT, SESSION, SECRET_PATH, "proj-", "C:\\", "/Users/"):
        assert secret not in text


def test_a_missing_ratio_renders_as_not_available_and_not_as_none():
    result = sample_result()
    result["ablation"]["rows"][0]["ratio_to_added"] = None
    result["requests"]["pooled"] = None
    text = attribute.render_section(result)
    assert "None" not in text
    assert "n/a" in text


def test_the_section_replaces_its_earlier_copy_and_leaves_the_rest_of_the_report():
    report = "# R\n\n### Judge\n\njudge text\n\n### Validity of this run\n\nvalid text\n"
    once = attribute.replace_section(report, attribute.render_section(sample_result()))
    assert once.index(attribute.HEADING) < once.index("### Validity of this run")
    assert once.index("### Judge") < once.index(attribute.HEADING)
    twice = attribute.replace_section(once, attribute.render_section(sample_result()))
    assert twice == once
    assert twice.count(attribute.HEADING) == 1
    assert "judge text" in twice and "valid text" in twice


def test_the_section_is_appended_when_the_report_has_no_validity_part():
    report = "# R\n\n### Judge\n\njudge text\n"
    out = attribute.replace_section(report, attribute.render_section(sample_result()))
    assert out.startswith(report) and out.rstrip().endswith(attribute.render_section(sample_result()).rstrip())


def test_a_replaced_section_stops_at_the_next_heading_and_keeps_what_follows():
    section = attribute.render_section(sample_result())
    report = f"# R\n\n{section}\n### Validity of this run\n\nkept\n"
    changed = sample_result()
    changed["builds"][0]["label"] = "Z9"
    out = attribute.replace_section(report, attribute.render_section(changed))
    assert "| Z9 |" in out and "| A1 |" not in out
    assert out.rstrip().endswith("kept")


def test_the_discard_note_replaces_the_pending_line():
    section = attribute.render_section(sample_result())
    assert attribute.DISCARD_PENDING in section
    report = "# R\n\n" + section
    out = attribute.mark_discarded(report, discarded=34, kept=0)
    assert attribute.DISCARD_PENDING not in out
    assert "34 discarded, 0 kept" in out
    assert attribute.mark_discarded(out, discarded=34, kept=0) == out


# closing the projects


class Discards:
    def __init__(self):
        self.done = []

    def __call__(self, project):
        self.done.append(Path(project).name)


def make_projects(root, names):
    root.mkdir(parents=True, exist_ok=True)
    (root / ".compass-overhead-projects").write_text("marker", encoding="utf-8")
    for name in names:
        (root / name).mkdir()
    return root


def committed_report(tmp_path, with_section=True):
    repo = tmp_path / "repo"
    repo.mkdir()
    report = repo / "report.md"
    report.write_text("# R\n\n" + (attribute.render_section(sample_result()) if with_section else "nothing\n"), encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for command in (["init", "-q"], ["add", "report.md"], ["commit", "-q", "-m", "x"]):
        subprocess.run(["git", "-C", str(repo), *command], check=True, env=env, capture_output=True)
    return repo, report


def test_every_project_is_discarded_when_none_is_kept_and_the_report_is_committed(tmp_path):
    root = make_projects(tmp_path / "projects", ["proj-aaaaaa", "proj-bbbbbb", "proj-cccccc"])
    repo, report = committed_report(tmp_path)
    discards = Discards()
    done = attribute.discard_projects(root, keep=[], report_path=report, discard=discards)
    assert sorted(discards.done) == ["proj-aaaaaa", "proj-bbbbbb", "proj-cccccc"]
    assert done == {"discarded": 3, "kept": 0}


def test_a_kept_project_is_left_alone(tmp_path):
    root = make_projects(tmp_path / "projects", ["proj-aaaaaa", "proj-bbbbbb"])
    repo, report = committed_report(tmp_path)
    discards = Discards()
    done = attribute.discard_projects(root, keep=["proj-bbbbbb"], report_path=report, discard=discards)
    assert discards.done == ["proj-aaaaaa"]
    assert done == {"discarded": 1, "kept": 1}


def test_a_keep_name_that_matches_no_project_stops_everything_before_a_deletion(tmp_path):
    root = make_projects(tmp_path / "projects", ["proj-aaaaaa"])
    repo, report = committed_report(tmp_path)
    discards = Discards()
    with pytest.raises(attribute.AttributionError):
        attribute.discard_projects(root, keep=["proj-typo00"], report_path=report, discard=discards)
    assert discards.done == []


def test_an_uncommitted_report_stops_the_discard(tmp_path):
    root = make_projects(tmp_path / "projects", ["proj-aaaaaa"])
    repo, report = committed_report(tmp_path)
    report.write_text(report.read_text(encoding="utf-8") + "\nedit\n", encoding="utf-8")
    discards = Discards()
    with pytest.raises(attribute.AttributionError):
        attribute.discard_projects(root, keep=[], report_path=report, discard=discards)
    assert discards.done == []


def test_a_report_without_the_section_stops_the_discard(tmp_path):
    root = make_projects(tmp_path / "projects", ["proj-aaaaaa"])
    repo, report = committed_report(tmp_path, with_section=False)
    discards = Discards()
    with pytest.raises(attribute.AttributionError):
        attribute.discard_projects(root, keep=[], report_path=report, discard=discards)
    assert discards.done == []


def test_a_report_outside_any_git_work_tree_stops_the_discard(tmp_path):
    root = make_projects(tmp_path / "projects", ["proj-aaaaaa"])
    report = tmp_path / "loose" / "report.md"
    report.parent.mkdir()
    report.write_text("# R\n\n" + attribute.render_section(sample_result()), encoding="utf-8")
    discards = Discards()
    with pytest.raises(attribute.AttributionError):
        attribute.discard_projects(root, keep=[], report_path=report, discard=discards)
    assert discards.done == []


# command line


def test_the_command_line_refuses_an_unknown_verb_and_a_missing_run_log(tmp_path, capsys):
    with pytest.raises(SystemExit):
        attribute.main(["nonsense"])
    code = attribute.main(["--private-root", str(tmp_path), "measure", "--run-log", str(tmp_path / "none.jsonl")])
    assert code == 2
    assert "run log" in capsys.readouterr().err


def test_the_source_files_hold_no_dash_character():
    here = Path(attribute.__file__)
    for path in (here, Path(__file__), here.with_name("README.md")):
        text = path.read_text(encoding="utf-8")
        assert not any(dash in text for dash in DASHES), path.name
