"""Tests for token_profile.py: where a build's tokens go, from its transcripts.

Interface under test:

    token_profile.profile_folder(folder) -> summary
        summary["weighted"]          weighted tokens over every session
        summary["sessions"]          {kind: count}
        summary["by_kind"]           {kind: {input, cache_read, cache_write, output, weighted}}
        summary["by_source"]         {source: {...}}
        summary["by_phase"]          {phase: {...}}
        summary["reconciliation"]    {"sessions_checked", "largest_gap"}
    token_profile.session_kind(lines) -> "setup" | "build" | "capture-worker"
    token_profile.render(summary) -> markdown text

Adversarial themes: a response written as several records counted more than
once; a split whose parts do not add up to the response's tokens; new content
charged cache-read tokens or old content charged the cache write; a compaction
that leaves the old context charged; a subagent's skills becoming the build's
phase; a session's own totals compared without its subagents; message text, a
session id, a project path or a project file name leaking into the summary.
"""

import json
import os

import pytest

import records
import token_profile

MODEL = "claude-opus-5-5"
SECRET_TEXT = "the user wants a lighthouse keeper simulator"
SECRET_SESSION = "9f8e7d6c-1111-4222-8333-444455556666"
SECRET_PATH = "C:/work/proj-secret/.compass/specs/SPEC-001-lighthouse-keeper.md"


def assistant(message_id, usage, blocks, request_ref="r1", sidechain=False):
    return {
        "type": "assistant", "isSidechain": sidechain, "sessionId": SECRET_SESSION, "requestRef": request_ref,
        "message": {"id": message_id, "model": MODEL, "usage": usage, "content": blocks},
    }


def usage(input_=0, read=0, write=0, output=0):
    return {"input_tokens": input_, "cache_read_input_tokens": read,
            "cache_creation_input_tokens": write, "output_tokens": output}


def user_text(text, meta=False):
    record = {"type": "user", "sessionId": SECRET_SESSION, "message": {"role": "user", "content": text}}
    if meta:
        record["isMeta"] = True
    return record


def tool_result(tool_id, text):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_id, "content": text}]}}


def shape(system_chars=400):
    return {"type": "api-request-shape", "shapeHash": "h1", "shape": {
        "system": [{"type": "text", "text": "s" * system_chars}],
        "tools": [{"name": "Bash", "description": "b" * 100}, {"name": "Skill", "description": "k" * 300}],
    }}


def request(request_id):
    return {"type": "api-request", "id": request_id, "shapeHash": "h1"}


def write_session(folder, name, lines):
    path = folder / f"{name}.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return path


def build_lines(cost=None):
    lines = [
        shape(), request("r1"), request("r2"), request("r3"),
        user_text(SECRET_TEXT * 10),
        assistant("m1", usage(input_=5, write=1000, output=40), [{"type": "text", "text": "part one"}]),
        assistant("m1", usage(input_=5, write=1000, output=40), [
            {"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "compass:spec"}}]),
        tool_result("t1", "Launching skill"),
        user_text("x" * 2000, meta=True),
        assistant("m2", usage(input_=2, read=1000, write=500, output=60), [
            {"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": SECRET_PATH}}], request_ref="r2"),
        tool_result("t2", SECRET_TEXT * 30),
        assistant("m3", usage(input_=1, read=1500, write=300, output=20), [{"type": "text", "text": "done"}],
                  request_ref="r3"),
    ]
    if cost is not None:
        lines.append({"type": "cost-state", "sessionId": SECRET_SESSION, "modelUsage": cost})
    return lines


@pytest.fixture
def folder(tmp_path):
    folder = tmp_path / "C--work-proj-secret"
    folder.mkdir()
    return folder


def kinds_total(table):
    return {kind: sum(entry[kind] for entry in table.values()) for kind in ("input", "cache_read", "cache_write", "output")}


def test_a_response_written_as_several_records_counts_once(folder):
    write_session(folder, SECRET_SESSION, build_lines())

    summary = token_profile.profile_folder(folder)

    build = summary["by_kind"]["build"]
    assert build["input"] == 5 + 2 + 1
    assert build["cache_write"] == 1000 + 500 + 300
    assert build["cache_read"] == 1000 + 1500
    assert build["output"] == 40 + 60 + 20


def test_the_split_by_source_and_by_phase_add_up_to_the_counted_tokens(folder):
    write_session(folder, SECRET_SESSION, build_lines())

    summary = token_profile.profile_folder(folder)

    counted = {kind: summary["by_kind"]["build"][kind] for kind in ("input", "cache_read", "cache_write", "output")}
    for table in ("by_source", "by_phase"):
        got = kinds_total(summary[table])
        for kind, value in counted.items():
            assert got[kind] == pytest.approx(value, abs=0.5), (table, kind)
    totals = {MODEL: {kind: summary["models"][MODEL][kind] for kind in records.KINDS}}
    assert summary["weighted"] == pytest.approx(records.weigh(totals)[0], abs=0.5)


def test_cache_writes_go_to_content_added_since_the_last_response_and_reads_to_the_rest(folder):
    write_session(folder, SECRET_SESSION, build_lines())

    summary = token_profile.profile_folder(folder)

    sources = summary["by_source"]
    read_result = sources["tool result:Read .compass/specs/"]
    assert read_result["cache_write"] > 0
    assert read_result["cache_read"] == 0
    assert sources["prefix:system prompt"]["cache_read"] > 0
    assert sources["skill body:compass:spec"]["cache_write"] > 0
    assert sources["user:message"]["cache_read"] > 0


def test_a_compaction_leaves_the_old_context_uncharged(folder):
    lines = [
        shape(), request("r1"), request("r2"),
        user_text("y" * 5000),
        assistant("m1", usage(write=1000, output=10), [{"type": "text", "text": "a"}]),
        {"type": "system", "subtype": "compact_boundary"},
        {"type": "user", "isCompactSummary": True, "message": {"role": "user", "content": "z" * 100}},
        assistant("m2", usage(read=500, write=50, output=10), [{"type": "text", "text": "b"}], request_ref="r2"),
    ]
    write_session(folder, SECRET_SESSION, lines)

    summary = token_profile.profile_folder(folder)

    assert summary["by_source"]["user:message"]["cache_read"] == 0
    assert summary["by_source"]["compaction summary"]["cache_write"] > 0


def test_sessions_are_classified_and_a_subagents_skills_stay_out_of_the_build_phases(folder):
    write_session(folder, SECRET_SESSION, build_lines())
    write_session(folder, "worker", [
        user_text(token_profile.CAPTURE_PROMPT + " and follow its steps"),
        assistant("w1", usage(write=100, output=5), [{"type": "text", "text": "ok"}]),
    ])
    write_session(folder, "setup-only", [
        user_text("<command-message>compass:setup</command-message>\n" + token_profile.SETUP_COMMAND),
        assistant("s1", usage(write=100, output=5), [{"type": "text", "text": "ok"}]),
    ])
    agents = folder / SECRET_SESSION / "subagents"
    agents.mkdir(parents=True)
    (agents / "agent-a1.meta.json").write_text(json.dumps({"agentType": "researcher"}), encoding="utf-8")
    write_session(agents, "agent-a1", [
        user_text("research brief"),
        user_text("<command-message>methodology</command-message>\n<command-name>methodology</command-name>\n"
                  + "w" * 3000, meta=True),
        user_text("The coordinator sent a message while you were working", meta=True),
        assistant("a1", usage(write=200, output=30), [
            {"type": "tool_use", "id": "t9", "name": "Skill", "input": {"skill": "lessons"}}], sidechain=True),
    ])

    summary = token_profile.profile_folder(folder)

    assert summary["sessions"] == {"build": 1, "capture-worker": 1, "setup": 1, "subagent:researcher": 1}
    assert summary["by_kind"]["subagent:researcher"]["output"] == 30
    assert "lessons" not in summary["by_phase"]
    assert summary["by_phase"]["subagent:researcher"]["output"] == 30
    assert summary["by_source"]["skill body:methodology"]["cache_write"] > 0
    assert "user:meta" in summary["by_source"]
    assert summary["by_phase"]["compass:spec"]["output"] > 0


def test_a_sessions_own_totals_are_compared_with_it_and_its_subagents(folder):
    session_total = {"inputTokens": 8, "outputTokens": 120 + 30, "cacheReadInputTokens": 2500,
                     "cacheCreationInputTokens": 1800 + 200}
    write_session(folder, SECRET_SESSION, build_lines(cost={MODEL: session_total}))
    agents = folder / SECRET_SESSION / "subagents"
    agents.mkdir(parents=True)
    write_session(agents, "agent-a1", [assistant("a1", usage(write=200, output=30), [], sidechain=True)])

    summary = token_profile.profile_folder(folder)
    assert summary["reconciliation"] == {"sessions_checked": 1, "largest_gap": 0.0}

    folder_two = folder.parent / "other"
    folder_two.mkdir()
    write_session(folder_two, SECRET_SESSION, build_lines(cost={MODEL: {**session_total, "outputTokens": 1000}}))
    assert token_profile.profile_folder(folder_two)["reconciliation"]["largest_gap"] > 0.1


def test_no_text_session_id_project_path_or_project_file_name_reaches_the_summary(folder):
    write_session(folder, SECRET_SESSION, build_lines(cost={MODEL: {"inputTokens": 1}}))

    summary = token_profile.profile_folder(folder)
    dumped = json.dumps(summary) + token_profile.render(summary)

    for secret in ("lighthouse", SECRET_SESSION, "proj-secret", "SPEC-001", "part one", "C:/work"):
        assert secret not in dumped


@pytest.mark.parametrize("path, expected", [
    ("C:/p/.compass/index.md", ".compass/index.md"),
    ("C:/p/.compass/specs/SPEC-004-name.md", ".compass/specs/"),
    ("C:\\p\\.compass\\research\\deep\\x.md", ".compass/research/"),
    ("C:/p/.claude/skills/spec/SKILL.md", ".claude/skills/spec/SKILL.md"),
    ("C:/p/src/main.rs", "project"),
    (None, "project"),
])
def test_file_paths_fall_into_compass_folders_install_files_or_the_project(path, expected):
    assert token_profile._path_source(path) == expected


def test_an_empty_or_missing_folder_is_refused_so_it_cannot_dilute_a_mean(tmp_path):
    """Adversarial where: a project whose transcripts are missing profiles as
    zero tokens and pulls its arm's mean down."""
    with pytest.raises(ValueError):
        token_profile.profile_folder(tmp_path / "missing")
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError):
        token_profile.profile_folder(tmp_path / "empty")


@pytest.mark.parametrize("source, expected", [
    ("skill body:compass:spec", "skill body:compass:spec"),
    ("skill body:lighthouse", "skill body:(other)"),
    ("output:subagent:researcher", "output:subagent:researcher"),
    ("output:subagent:lighthouse-agent", "output:(other)"),
    ("tool result:Read .claude/skills/spec/SKILL.md", "tool result:Read .claude/skills/spec/SKILL.md"),
    ("tool result:Read .claude/skills/lighthouse/SKILL.md", "tool result:Read .claude/(other)"),
    ("tool result:Read .compass/specs/", "tool result:Read .compass/specs/"),
    ("tool result:Read .compass/lighthouse/", "tool result:Read .compass/(other)"),
    ("tool call:mcp__lighthouse__x", "tool call:(other)"),
    ("attachment:skill_listing", "attachment:skill_listing"),
    ("prefix:tool Bash", "prefix:tool Bash"),
    ("assistant:text", "assistant:text"),
    ("lighthouse", "(other)"),
])
def test_only_names_in_the_public_vocabulary_pass_into_a_public_report(source, expected):
    known = frozenset({"spec", "researcher"})
    assert token_profile.public_source(source, known) == expected


def test_compass_names_cover_the_plugins_skills_and_its_agent_templates(tmp_path):
    """Adversarial where: agents shipped as templates are missed, so every
    subagent of a Compass build shows as `(other)` in the report."""
    (tmp_path / "skills" / "spec").mkdir(parents=True)
    (tmp_path / "templates" / "agents").mkdir(parents=True)
    (tmp_path / "templates" / "agents" / "researcher.md").write_text("x", encoding="utf-8")
    known = token_profile.compass_names(tmp_path)
    assert {"spec", "researcher"} <= known
    assert token_profile.public_phase("subagent:researcher", known) == "subagent:researcher"


@pytest.mark.parametrize("path", [
    "C:\work\p\.claude\skills\plan\SKILL.md",
    "C:/work/p/.claude/skills/plan/SKILL.md",
])
def test_reading_a_skill_file_in_the_main_session_moves_the_phase_to_that_skill(folder, path):
    """Adversarial where: a build that loads later pipeline steps by reading
    their SKILL.md (not through the Skill tool) books the rest of the build to
    the first skill, in either path spelling."""
    write_session(folder, SECRET_SESSION, [
        user_text("<command-message>compass:vision</command-message>\n<command-name>/compass:vision</command-name>"),
        user_text(token_profile.SKILL_BODY_START + ": vision skill text", meta=True),
        assistant("m1", usage(write=100, output=10), [
            {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": path}}]),
        tool_result("t1", "plan skill text"),
        assistant("m2", usage(read=100, write=50, output=30), [{"type": "text", "text": "planning"}]),
        user_text("go on"),
        assistant("m3", usage(read=150, write=10, output=7), [{"type": "text", "text": "more"}]),
    ])

    summary = token_profile.profile_folder(folder)

    assert summary["by_phase"]["compass:vision"]["output"] == 10
    assert summary["by_phase"]["plan"]["output"] == 30 + 7


def test_waiting_for_a_quiet_folder_returns_once_nothing_changed_for_the_quiet_time(tmp_path):
    """Adversarial where: the profile is taken while a capture worker still
    writes, or the wait never ends on a folder that stays busy."""
    (tmp_path / "s.jsonl").write_text("{}\n", encoding="utf-8")
    written = (tmp_path / "s.jsonl").stat().st_mtime
    now = {"t": written + 10}
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now["t"] += seconds

    assert token_profile.wait_until_quiet(tmp_path, quiet_seconds=60, limit_seconds=600,
                                          clock=lambda: now["t"], sleep=sleep) is True
    assert now["t"] - written >= 60 and sleeps

    def busy_sleep(seconds):
        now["t"] += seconds
        os.utime(tmp_path / "s.jsonl", (now["t"], now["t"]))

    start = now["t"]
    os.utime(tmp_path / "s.jsonl", (start, start))
    assert token_profile.wait_until_quiet(tmp_path, quiet_seconds=60, limit_seconds=100,
                                          clock=lambda: now["t"], sleep=busy_sleep) is False
    assert now["t"] - start <= 100 + 15


def test_a_response_streamed_as_several_records_is_not_its_own_input(folder):
    """Adversarial where: the thinking and text records of one response sit
    in the context when that response is counted, taking a share of its own
    cache write."""
    write_session(folder, SECRET_SESSION, [
        shape(), request("r1"),
        user_text("q" * 1000),
        assistant("m1", usage(write=1000, output=50), [{"type": "text", "text": "t" * 5000}]),
        assistant("m1", usage(write=1000, output=50), [{"type": "tool_use", "id": "t1", "name": "Bash",
                                                       "input": {"command": "c" * 5000}}]),
    ])

    summary = token_profile.profile_folder(folder)

    assert "assistant:text" not in summary["by_source"]
    assert "tool call:Bash" not in summary["by_source"]
    assert summary["by_kind"]["build"]["cache_write"] == 1000


def test_a_forked_subagent_does_not_count_the_parent_response_it_repeats(folder):
    """Adversarial where: a fork's file repeats the parent's last response,
    and its tokens are counted in both files."""
    write_session(folder, SECRET_SESSION, [
        user_text("go"),
        assistant("m1", usage(write=700, output=10), [{"type": "text", "text": "spawning"}]),
    ])
    agents = folder / SECRET_SESSION / "subagents"
    agents.mkdir(parents=True)
    write_session(agents, "agent-f1", [
        {"type": "fork-context-ref", "parentLastUuid": "x"},
        assistant("m1", usage(write=700, output=10), [{"type": "text", "text": "spawning"}], sidechain=True),
        user_text("fork brief"),
        assistant("f2", usage(read=700, write=30, output=5), [{"type": "text", "text": "ok"}], sidechain=True),
    ])

    summary = token_profile.profile_folder(folder)

    assert summary["models"][MODEL]["cache_write"] == 700 + 30
    assert summary["models"][MODEL]["output"] == 10 + 5


@pytest.mark.parametrize("source, expected", [
    ("tool result:Read .claude/rules/lighthouse.md", "tool result:Read .claude/(other)"),
    ("tool result:Read .claude/rules/compass-pipeline.md", "tool result:Read .claude/rules/compass-pipeline.md"),
    ("tool result:Read .claude/cli/commands/lighthouse.py", "tool result:Read .claude/cli/"),
    ("tool call:Lighthouse", "tool call:(other)"),
    ("prefix:tool Lighthouse", "prefix:tool (other)"),
])
def test_install_paths_and_tool_names_pass_only_from_the_known_lists(source, expected):
    assert token_profile.public_source(source, frozenset({"compass-pipeline"})) == expected


def write_agent(folder, parent, name, agent_type, usages):
    """A subagent session of `parent` whose responses carry `usages`, one
    response each, after a plain brief."""
    agents = folder / parent / "subagents"
    agents.mkdir(parents=True, exist_ok=True)
    (agents / f"{name}.meta.json").write_text(json.dumps({"agentType": agent_type}), encoding="utf-8")
    lines = [user_text("b" * 300)]
    for index, one in enumerate(usages):
        lines.append(assistant(f"{name}-{index}", one, [{"type": "text", "text": "ok"}], sidechain=True))
    write_session(agents, name, lines)


def test_by_agent_counts_each_type_and_its_means_are_the_hand_summed_weighted_tokens(folder):
    """Defect class: a per-type mean that divides by the project's session count,
    or sums the types into one row. Weights: input 1, output 5."""
    write_session(folder, SECRET_SESSION, build_lines())
    write_agent(folder, SECRET_SESSION, "agent-b1", "builder", [usage(input_=100, output=10)])
    write_agent(folder, SECRET_SESSION, "agent-b2", "builder", [usage(input_=200, output=20)])
    write_agent(folder, SECRET_SESSION, "agent-v1", "validator", [usage(input_=40, output=2)])

    by_agent = token_profile.profile_folder(folder)["by_agent"]

    assert set(by_agent) == {"subagent:builder", "subagent:validator"}
    assert by_agent["subagent:builder"]["sessions"] == 2
    assert by_agent["subagent:validator"]["sessions"] == 1
    assert by_agent["subagent:builder"]["mean"] == pytest.approx((150 + 300) / 2)
    assert by_agent["subagent:validator"]["mean"] == pytest.approx(50)
    assert sorted(by_agent["subagent:builder"]["session_weighted"]) == [150, 300]


def test_by_agent_median_is_the_middle_session_not_the_mean(folder):
    write_session(folder, SECRET_SESSION, build_lines())
    for index, tokens in enumerate((100, 200, 1000)):
        write_agent(folder, SECRET_SESSION, f"agent-b{index}", "builder", [usage(input_=tokens)])

    entry = token_profile.profile_folder(folder)["by_agent"]["subagent:builder"]

    assert entry["median"] == pytest.approx(200)
    assert entry["mean"] == pytest.approx(1300 / 3, abs=0.1)


def test_a_sessions_weighted_tokens_sum_every_response_of_that_session(folder):
    write_session(folder, SECRET_SESSION, build_lines())
    write_agent(folder, SECRET_SESSION, "agent-b1", "builder", [usage(input_=10, output=1), usage(input_=20, output=2)])

    entry = token_profile.profile_folder(folder)["by_agent"]["subagent:builder"]

    assert entry["session_weighted"] == [pytest.approx(10 + 5 + 20 + 10)]


def test_by_agent_shares_split_a_types_tokens_by_source_family_and_sum_to_one(folder):
    write_session(folder, SECRET_SESSION, build_lines())
    write_agent(folder, SECRET_SESSION, "agent-b1", "builder", [usage(input_=100, output=10)])

    shares = token_profile.profile_folder(folder)["by_agent"]["subagent:builder"]["families"]

    assert shares == {"user": pytest.approx(100 / 150, abs=1e-3), "output": pytest.approx(50 / 150, abs=1e-3)}
    assert sum(shares.values()) == pytest.approx(1.0, abs=1e-3)


def test_by_agent_is_empty_without_subagent_sessions_and_top_level_kinds_stay_out(folder):
    write_session(folder, SECRET_SESSION, build_lines())

    assert token_profile.profile_folder(folder)["by_agent"] == {}


def test_a_subagent_with_no_counted_response_still_counts_as_a_session_with_zero_tokens(folder):
    """Defect class: a launch that wrote nothing disappearing from the per-launch mean."""
    write_session(folder, SECRET_SESSION, build_lines())
    write_agent(folder, SECRET_SESSION, "agent-b1", "builder", [])
    write_agent(folder, SECRET_SESSION, "agent-b2", "builder", [usage(input_=100)])

    entry = token_profile.profile_folder(folder)["by_agent"]["subagent:builder"]

    assert entry["sessions"] == 2
    assert entry["mean"] == pytest.approx(50)
    assert entry["families"] != {}


def test_an_agent_with_no_tokens_has_empty_shares_rather_than_a_division_error(folder):
    write_session(folder, SECRET_SESSION, build_lines())
    write_agent(folder, SECRET_SESSION, "agent-b1", "builder", [])

    entry = token_profile.profile_folder(folder)["by_agent"]["subagent:builder"]

    assert entry["mean"] == 0
    assert entry["families"] == {}


def test_public_by_agent_renames_private_types_and_pools_them_into_one_row():
    by_agent = {
        "subagent:builder": {"sessions": 1, "mean": 100.0, "median": 100.0, "families": {"user": 1.0},
                             "session_weighted": [100.0]},
        "subagent:lighthouse-agent": {"sessions": 1, "mean": 200.0, "median": 200.0, "families": {"tool result": 1.0},
                                      "session_weighted": [200.0]},
        "subagent:keeper-agent": {"sessions": 2, "mean": 500.0, "median": 500.0, "families": {"tool result": 1.0},
                                  "session_weighted": [400.0, 600.0]},
    }

    public = token_profile.public_by_agent(by_agent, frozenset({"builder"}))

    assert set(public) == {"subagent:builder", "(other)"}
    assert public["(other)"]["sessions"] == 3
    assert public["(other)"]["mean"] == pytest.approx((200 + 400 + 600) / 3)
    assert public["(other)"]["median"] == pytest.approx(400)
    assert public["(other)"]["families"] == {"tool result": pytest.approx(1.0)}


def test_the_by_agent_render_lists_counts_means_and_family_shares_without_private_names(folder):
    write_session(folder, SECRET_SESSION, build_lines())
    write_agent(folder, SECRET_SESSION, "agent-b1", "builder", [usage(input_=100, output=10)])
    write_agent(folder, SECRET_SESSION, "agent-b2", "builder", [usage(input_=200, output=20)])
    write_agent(folder, SECRET_SESSION, "agent-x1", "lighthouse-agent", [usage(input_=40)])
    summary = token_profile.profile_folder(folder)

    text = token_profile.render_by_agent(summary, frozenset({"builder"}))

    assert "subagent:builder" in text
    assert "225" in text
    assert "(other)" in text
    assert "lighthouse" not in text
    assert "output" in text and "user" in text


def test_the_by_agent_render_of_a_project_with_no_subagents_says_so(folder):
    write_session(folder, SECRET_SESSION, build_lines())

    text = token_profile.render_by_agent(token_profile.profile_folder(folder), frozenset())

    assert "no subagent" in text.lower()


def test_the_by_agent_flag_prints_only_the_per_agent_table(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(token_profile, "wait_until_quiet", lambda folder: True)
    root = tmp_path / "private"
    project = tmp_path / "proj-abc123"
    project.mkdir()
    transcripts = token_profile.transcript_folder(project, root)
    transcripts.mkdir(parents=True)
    write_session(transcripts, SECRET_SESSION, build_lines())
    write_agent(transcripts, SECRET_SESSION, "agent-b1", "builder", [usage(input_=100, output=10)])
    plugin = tmp_path / "plugin"
    (plugin / "agents").mkdir(parents=True)
    (plugin / "agents" / "builder.md").write_text("x", encoding="utf-8")

    code = token_profile.main([str(project), "--private-root", str(root), "--by-agent", "--plugin-root", str(plugin)])

    out = capsys.readouterr().out
    assert code == 0
    assert "subagent:builder" in out
    assert "Weighted tokens:" not in out
    assert "Active skill" not in out
