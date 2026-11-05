"""Tests for probe_initial_prompt.py: reading one subagent transcript for the
start-here Reads, the first user turn and the refusals, and the two-session run.

Adversarial themes: a Read of `.compass/lessons/index.md` counted for
`.compass/index.md`; Reads that come after other work counted as the initial
prompt; a skill preload taken for the first user turn; a file's text that quotes
a refusal counted as one; a session that never produced a transcript reported as
"did not run" instead of "no answer".
"""

import json
import os
import time
from pathlib import Path

import pytest

import fake_session_claude as fake
import launch
import probe_initial_prompt as probe
import sandbox

INDEX = "C:\\proj\\.compass\\index.md"
ACTIVE = "C:\\proj\\.compass\\active.md"
LESSONS = "C:\\proj\\.compass\\lessons\\index.md"
INITIAL_PROMPT = "Read these files now: .compass/index.md, .compass/active.md, .compass/lessons/index.md"


def user(content, meta=False):
    entry = {"type": "user", "message": {"role": "user", "content": content}}
    if meta:
        entry["isMeta"] = True
    return entry


def calls(*pairs):
    """One assistant entry holding the given (tool, input) calls."""
    blocks = [{"type": "tool_use", "id": f"toolu_{i}", "name": name, "input": tool_input} for i, (name, tool_input) in enumerate(pairs)]
    return {"type": "assistant", "message": {"role": "assistant", "content": blocks}}


def read(path):
    return ("Read", {"file_path": path})


def result(text, error=False):
    block = {"type": "tool_result", "tool_use_id": "toolu_0", "content": text}
    if error:
        block["is_error"] = True
    return user([block])


def facts(*entries):
    return probe.analyse(list(entries))


def test_three_reads_before_the_first_other_tool_call_is_ran():
    got = facts(
        user(probe.BRIEF),
        calls(read(INDEX)), result("x"), calls(read(ACTIVE)), result("x"), calls(read(LESSONS)), result("x"),
        calls(("Write", {"file_path": "C:\\proj\\hello.txt", "content": "hello"})),
    )

    assert got["initial_prompt"] == "ran"
    assert got["leading_start_here_reads"] == list(probe.START_HERE)
    assert got["first_tool_call"] == "Read"


def test_three_reads_in_one_assistant_message_in_any_order_is_ran():
    got = facts(user(probe.BRIEF), calls(read(LESSONS), read(INDEX), read(ACTIVE)), calls(("Bash", {"command": "ls"})))

    assert got["initial_prompt"] == "ran"
    assert got["start_here_reads"] == [".compass/lessons/index.md", ".compass/index.md", ".compass/active.md"]


def test_no_start_here_read_is_did_not_run():
    got = facts(user(probe.BRIEF), calls(("Bash", {"command": "git rev-parse --show-toplevel"})), calls(read("C:\\proj\\hello.txt")))

    assert got["initial_prompt"] == "did not run"
    assert got["start_here_reads"] == []
    assert got["first_tool_call"] == "Bash"


def test_one_of_the_three_reads_is_did_not_run():
    got = facts(user(probe.BRIEF), calls(read(ACTIVE)), calls(("Write", {"file_path": "C:\\proj\\hello.txt"})))

    assert got["initial_prompt"] == "did not run"
    assert got["leading_start_here_reads"] == [".compass/active.md"]


def test_two_of_the_three_reads_is_did_not_run():
    got = facts(user(probe.BRIEF), calls(read(INDEX), read(ACTIVE)), calls(("Write", {"file_path": "C:\\proj\\hello.txt"})))

    assert got["initial_prompt"] == "did not run"


def test_the_lessons_index_read_twice_does_not_stand_for_the_vault_index():
    """Adversarial where: matching on the file name `index.md` alone, or on a
    suffix that both paths share, counts two Reads of one file as two files."""
    got = facts(user(probe.BRIEF), calls(read(LESSONS), read(LESSONS), read(ACTIVE)), calls(("Bash", {"command": "ls"})))

    assert got["initial_prompt"] == "did not run"
    assert got["start_here_reads"] == [".compass/lessons/index.md", ".compass/active.md"]


def test_reads_after_other_work_are_not_the_initial_prompt():
    """Adversarial where: a builder that does its own task first and reads the
    three files later reads them because of its brief or its body, not because
    of `initialPrompt`; only the leading run counts."""
    got = facts(
        user(probe.BRIEF),
        calls(("Bash", {"command": "git status"})),
        calls(read(INDEX), read(ACTIVE), read(LESSONS)),
    )

    assert got["initial_prompt"] == "did not run"
    assert got["start_here_reads"] == list(probe.START_HERE)
    assert got["leading_start_here_reads"] == []


@pytest.mark.parametrize(
    "path",
    ["C:\\proj\\.compass\\index.md.bak", "C:\\proj\\src\\index.md", "C:\\proj\\xcompass\\index.md", "index.md", 12, None],
)
def test_lookalike_paths_are_not_start_here_files(path):
    assert probe.start_here_file(path) is None


def test_a_relative_and_a_posix_path_are_start_here_files():
    assert probe.start_here_file(".compass/index.md") == ".compass/index.md"
    assert probe.start_here_file("/c/proj/.compass/lessons/index.md") == ".compass/lessons/index.md"


def test_a_transcript_with_no_tool_call_is_did_not_run():
    got = facts(user(probe.BRIEF))

    assert got["initial_prompt"] == "did not run"
    assert got["first_tool_call"] is None
    assert got["tool_calls"] == 0


def test_first_user_turn_is_the_brief_and_skill_preloads_are_skipped():
    """Adversarial where: the preloaded skill bodies are user entries too; the
    first of them taken for the first user turn hides what the agent was told."""
    got = facts(
        user([{"type": "text", "text": "<command-name>obsidian</command-name>"}], meta=True),
        user(probe.BRIEF),
    )

    assert got["first_user_turn_is_brief"] is True
    assert got["first_user_turn_names_start_here"] is False
    assert got["first_user_turn_characters"] == len(probe.BRIEF)


def test_first_user_turn_that_carries_the_initial_prompt_is_reported():
    got = facts(user([{"type": "text", "text": INITIAL_PROMPT}, {"type": "text", "text": probe.BRIEF}]))

    assert got["first_user_turn_is_brief"] is False
    assert got["first_user_turn_names_start_here"] is True


def test_no_user_entry_gives_no_first_user_turn():
    got = facts(calls(read(INDEX)))

    assert probe.first_user_turn([calls(read(INDEX))]) is None
    assert got["first_user_turn_is_brief"] is False
    assert got["first_user_turn_characters"] == 0


def test_permission_refusals_and_hook_refusals_are_counted_apart():
    got = facts(
        user(probe.BRIEF),
        calls(("Write", {"file_path": "x"})),
        result("Claude requested permissions to write to x, but you haven\u2019t granted it yet.", error=True),
        result("The user doesn't want to proceed with this tool use. The tool use was rejected", error=True),
        result("PreToolUse:Bash hook error: the path '/tmp' leaves the project", error=True),
    )

    assert got["permission_denials"] == 2
    assert got["hook_denials"] == 1
    assert got["without_permission_denials"] is False


def test_ordinary_errors_and_quoted_refusal_text_are_not_refusals():
    """Adversarial where: a failing command (`Exit code 1`) and a file that
    quotes the refusal wording in a successful Read are not refusals."""
    got = facts(
        user(probe.BRIEF),
        result("Exit code 1\nboom", error=True),
        result("the message says you haven't granted it yet"),
        user([{"type": "tool_result", "tool_use_id": "t", "content": [{"type": "text", "text": "fine"}]}]),
    )

    assert got["permission_denials"] == 0
    assert got["hook_denials"] == 0
    assert got["without_permission_denials"] is True


def test_a_refusal_in_a_list_content_result_is_counted():
    block = {
        "type": "tool_result", "is_error": True,
        "content": [{"type": "text", "text": "requested permissions to use Bash, but you haven't granted it yet."}],
    }

    assert facts(user([block]))["permission_denials"] == 1


def test_a_hook_refusal_alone_is_not_a_permission_denial():
    got = facts(result("PreToolUse:Write hook error: the path leaves the project", error=True))

    assert got["without_permission_denials"] is True
    assert got["hook_denials"] == 1


def test_read_entries_skips_lines_that_do_not_parse(tmp_path):
    path = tmp_path / "agent.jsonl"
    path.write_text(
        json.dumps(user("a")) + "\n\nnot json\n[1, 2]\n" + json.dumps(user("b")) + '\n{"type": "user", "mess',
        encoding="utf-8",
    )

    assert [probe._text_of(entry) for entry in probe.read_entries(path)] == ["a", "b"]


def write_transcript(private_root, project, session, name, agent_type, entries, age=0, meta=True):
    folder = (
        private_root / "claude-config" / "projects" / launch.encode_cwd(os.path.abspath(project)) / session / "subagents"
    )
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.jsonl"
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
    if meta:
        (folder / f"{name}.meta.json").write_text(json.dumps({"agentType": agent_type}), encoding="utf-8")
    moment = time.time() - age
    os.utime(path, (moment, moment))
    return path


def test_find_subagent_transcript_takes_the_newest_builder_since_the_start(private_root, project):
    started = time.time() - 60
    write_transcript(private_root, project, "s1", "agent-tester", "tester", [user("t")])
    write_transcript(private_root, project, "s1", "agent-old", "builder", [user("old")], age=3600)
    write_transcript(private_root, project, "s1", "agent-nometa", "builder", [user("nm")], meta=False)
    newest = write_transcript(private_root, project, "s1", "agent-new", "builder", [user("new")], age=1)

    assert probe.find_subagent_transcript(private_root, project, started) == newest
    assert probe.find_subagent_transcript(private_root, project, time.time() + 600) is None


def test_find_subagent_transcript_is_none_without_a_builder(private_root, project):
    write_transcript(private_root, project, "s1", "agent-v", "validator", [user("v")])

    assert probe.find_subagent_transcript(private_root, project, time.time() - 60) is None


@pytest.fixture
def sandbox_project(tmp_path, projects_root):
    return sandbox.new_project(projects_root)


def run_probe(project, repo, private_root, tmp_path, replies, **kwargs):
    cmd = fake.command({"mode": "oneshot", "replies": replies}, tmp_path / "specs")
    facts = probe.run_probe(
        project, repo_root=repo, private_root=private_root, claude_cmd=cmd, remote_sha="abc1234", **kwargs,
    )
    return facts, cmd


SETUP_REPLY = {"text": "set up", "write": {".compass/meta/plugin.yaml": "commit: old\n"}}
RAN_TRANSCRIPT = [
    user(probe.BRIEF),
    calls(read(INDEX), read(ACTIVE), read(LESSONS)),
    calls(("Write", {"file_path": "C:\\proj\\hello.txt", "content": "hello"})),
]


def test_run_probe_runs_setup_under_the_plugin_dir_then_the_launch_without_it(
    sandbox_project, repo, private_root, tmp_path
):
    """Adversarial where: a launch session that also carries `--plugin-dir`
    loads Compass twice, so a builder's context is no longer the installed one;
    a setup session without it has no `/compass:setup` to run."""
    reply = {"text": "done", "subagent": {"agentType": "builder", "entries": RAN_TRANSCRIPT}}

    got, cmd = run_probe(sandbox_project, repo, private_root, tmp_path, [SETUP_REPLY, reply])

    starts = [entry for entry in fake.read_log(cmd) if entry["kind"] == "start"]
    stdins = [entry["text"] for entry in fake.read_log(cmd) if entry["kind"] == "stdin"]
    assert len(starts) == 2
    assert "--plugin-dir" in starts[0]["argv"]
    assert "--plugin-dir" not in starts[1]["argv"]
    assert stdins == ["/compass:setup", probe.OPENING_MESSAGE]
    assert got["transcript_found"] is True
    assert got["analysis"]["initial_prompt"] == "ran"
    assert got["analysis"]["without_permission_denials"] is True


def test_run_probe_runs_both_sessions_in_the_sandbox_with_the_fence_and_a_budget(
    sandbox_project, repo, private_root, tmp_path
):
    reply = {"text": "done", "subagent": {"agentType": "builder", "entries": RAN_TRANSCRIPT}}

    _, cmd = run_probe(sandbox_project, repo, private_root, tmp_path, [SETUP_REPLY, reply], max_budget_usd=2.5)

    for entry in [e for e in fake.read_log(cmd) if e["kind"] == "start"]:
        assert entry["argv"][entry["argv"].index("--max-budget-usd") + 1] == "2.5"
        assert os.path.normcase(entry["env"]["CLAUDE_CONFIG_DIR"]) == os.path.normcase(str(private_root / "claude-config"))
        assert os.path.normcase(os.path.realpath(entry["cwd"])) == os.path.normcase(os.path.realpath(sandbox_project))
        config = json.loads(Path(entry["env"]["OVERHEAD_HOOK_CONFIG"]).read_text(encoding="utf-8"))
        assert os.path.normcase(config["project"]) == os.path.normcase(str(sandbox_project))
        assert os.path.normcase(entry["env"]["HOME"]).startswith(os.path.normcase(str(private_root / "homes")))
    settings = json.loads((sandbox_project / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    assert "answer_question.py" in json.dumps(settings["hooks"]["PreToolUse"])


def test_run_probe_pins_the_plugin_commit_between_the_sessions(sandbox_project, repo, private_root, tmp_path):
    reply = {"text": "done", "subagent": {"agentType": "builder", "entries": RAN_TRANSCRIPT}}

    run_probe(sandbox_project, repo, private_root, tmp_path, [SETUP_REPLY, reply])

    assert "commit: abc1234" in (sandbox_project / ".compass" / "meta" / "plugin.yaml").read_text(encoding="utf-8")


def test_run_probe_reports_did_not_run_for_a_builder_that_read_nothing(
    sandbox_project, repo, private_root, tmp_path
):
    entries = [user(probe.BRIEF), calls(("Bash", {"command": "git status"}))]
    reply = {"text": "done", "subagent": {"agentType": "builder", "entries": entries}}

    got, _ = run_probe(sandbox_project, repo, private_root, tmp_path, [SETUP_REPLY, reply])

    assert got["analysis"]["initial_prompt"] == "did not run"
    assert got["analysis"]["first_user_turn_is_brief"] is True


def test_run_probe_has_no_answer_when_the_launch_wrote_no_builder_transcript(
    sandbox_project, repo, private_root, tmp_path
):
    """Adversarial where: a main agent that never launched the builder must not
    read as "did not run"; there is nothing to analyse."""
    reply = {"text": "done", "subagent": {"agentType": "tester", "entries": RAN_TRANSCRIPT}}

    got, _ = run_probe(sandbox_project, repo, private_root, tmp_path, [SETUP_REPLY, reply])

    assert got["launch"]["status"] == "done"
    assert got["transcript_found"] is False
    assert got["analysis"] is None


def test_run_probe_stops_after_a_setup_that_did_not_finish(sandbox_project, repo, private_root, tmp_path):
    got, cmd = run_probe(sandbox_project, repo, private_root, tmp_path, [{"limit": True}])

    assert got["setup"]["status"] == "usage-limit"
    assert got["launch"] is None
    assert len([e for e in fake.read_log(cmd) if e["kind"] == "start"]) == 1


def test_run_probe_stops_when_setup_left_no_plugin_yaml(sandbox_project, repo, private_root, tmp_path):
    got, cmd = run_probe(sandbox_project, repo, private_root, tmp_path, ["set up"])

    assert got["setup"]["status"] == "failed"
    assert got["launch"] is None
    assert len([e for e in fake.read_log(cmd) if e["kind"] == "start"]) == 1


def test_run_probe_refuses_a_changed_plugin_before_any_session(
    sandbox_project, repo, private_root, tmp_path
):
    (repo / "plugin" / "keep.txt").write_text("changed\n", encoding="utf-8")
    cmd = fake.command({"mode": "oneshot", "replies": ["x"]}, tmp_path / "specs")

    with pytest.raises(launch.Refused):
        probe.run_probe(sandbox_project, repo_root=repo, private_root=private_root, claude_cmd=cmd, remote_sha="abc1234")

    assert fake.read_log(cmd) == []


def test_analyse_command_prints_the_facts_of_one_transcript(tmp_path, capsys):
    path = tmp_path / "agent.jsonl"
    path.write_text("\n".join(json.dumps(entry) for entry in RAN_TRANSCRIPT) + "\n", encoding="utf-8")

    code = probe.main(["--analyse", str(path)])

    printed = json.loads(capsys.readouterr().out)
    assert code == 0
    assert printed["initial_prompt"] == "ran"


def test_analyse_command_refuses_a_missing_file(tmp_path, capsys):
    code = probe.main(["--analyse", str(tmp_path / "absent.jsonl")])

    assert code == 2
    assert "refused" in capsys.readouterr().err
