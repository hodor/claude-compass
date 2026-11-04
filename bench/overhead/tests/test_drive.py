"""Tests for drive.py: one long build session driven turn by turn.

Interface the tests pin (drive.py, human.py, hooks/answer_question.py)
----------------------------------------------------------------------
drive.py
    drive_build(project, opening_message, *, human, repo_root, arm,
                private_root=None, claude_cmd=None, parent_env=None,
                max_wall_seconds=9000, max_turns=400, max_budget_usd=50,
                clock=time.monotonic) -> DriveResult
        Holds one build open as `claude -p --input-format stream-json
        --output-format stream-json --verbose --setting-sources project,local
        --strict-mcp-config --max-budget-usd <n>` (plus `--plugin-dir
        <repo_root>/plugin` in the "compass" arm) with the project as cwd and
        the launch.py isolated environment, plus OVERHEAD_HOOK_CONFIG naming a
        JSON file {"project": <path>, "answer_command": [argv...]} under the
        private root. Raises launch.Refused, before anything starts, when
        plugin/ has uncommitted changes.
        Messages go to stdin one per line as
        {"type": "user", "message": {"role": "user", "content": [{"type":
        "text", "text": <message>}]}}. The baseline arm sends `opening_message`
        first. The "compass" arm sends `/compass:setup` first; when its turn
        ends the driver sets `commit:` in <project>/.compass/meta/plugin.yaml to
        the sha of the remote head of `repo_root` (`git ls-remote origin HEAD`)
        and sends `opening_message` without asking the human.
        Before launch the driver merges a PreToolUse command hook for
        AskUserQuestion, Bash, Write and Edit (running hooks/answer_question.py)
        into <project>/.claude/settings.local.json, keeping other settings.
        A turn is one `result` event. After each turn the driver calls
        `human.reply(<assistant text of the turn>)` and sends `reply.text`,
        until the reply is `done`, a cap is hit or the session ends badly.
        A done reply's text is not sent. The driver closes stdin to end the
        session.
        `human` is any object with `reply(text) -> human.Reply` and
        `answer_command` (a list: the argv the hook runs to answer questions).
    DriveResult
        .end            "human-done" | "wall-time" | "turns" | "usage-limit" | "failed"
        .turns          number of `result` events read (the setup turn counts)
        .resets_at      unix time from a rejected rate_limit_event, else None
        .init_counts    {"before": {"skills": n, "agents": m}, "after": {...}} from
                        the first and the last `system/init` event ("compass" arm)
        .events         every JSON event of the build session
    Record rows (records.record_session, role "build"): outcome is "done" for
    "human-done", "usage-limit" for "usage-limit" and "failed" for the rest;
    arm and plugin_sha (HEAD of repo_root) are set. Each simulated-human session
    is recorded by human.py as its own role "human" row; none of its tokens
    reach the build row. `main(argv)` is the command line:
    `python drive.py PROJECT --arm {compass,baseline} --opening-file FILE
    --brief-file FILE --human-folder DIR [--max-minutes N] [--max-turns N]
    [--max-budget-usd N]`.

human.py
    Reply(text, done=False, events=(), outcome="done")   dataclass
    SimulatedHuman(brief, *, folder, repo_root, arm, state_file, private_root=None,
                   claude_cmd=None, budget=12, readme=None,
                   model="claude-sonnet-4-6", timeout=None)
        brief = {"items": [{"id", "name", "detail"}, ...]}
        .reply(message) -> Reply          one isolated one-shot session in `folder`
        .answer_questions(questions) -> {question text: answer text}
        .questions_used                   revealing questions answered so far
        .answer_command                   argv of `python human.py answer --state-file F`
    A message "names" an item when the item's name occurs in it, ignoring case.
    Only named items' details reach the session's prompt. A message naming at
    least one item is a revealing question: it uses one unit of budget. Once
    `budget` is used up a revealing question is answered "decide yourself"
    without starting a session. Other messages (gate approvals, continue
    messages) are always passed to the session and use no budget. The session's
    result text is JSON {"text": str, "done": bool}; text that is not such JSON
    is the reply text with done False; done is true only for the JSON value true.
    The README text is in the prompt only in the "compass" arm. The count of used
    questions lives in `state_file`, so a fresh process sees it.
    Every session it starts is recorded as a role "human" row.

hooks/answer_question.py
    decide(event, *, project, answer) -> dict | None
        `event` is the PreToolUse event. None means no opinion. Otherwise
        {"hookSpecificOutput": {"hookEventName": "PreToolUse",
        "permissionDecision": "allow" | "deny", "permissionDecisionReason": str,
        "updatedInput": {...}}}.
    main(argv, stdin_text, env) -> (exit code, stdout text); as a script it reads
    the event from stdin and the config file named by OVERHEAD_HOOK_CONFIG.

Adversarial themes: a driver that stops at the first end of turn, that counts a
cap off by one, that sends the wrong message shape, that mixes the human's
tokens into the build's, or that hangs on a crash.
"""

import json
import os
import re

import pytest

import drive
import fake_claude
import fake_session_claude as fake
import human
import launch
import records


class Ticker:
    """A fake clock that advances `step` seconds on every reading."""

    def __init__(self, step):
        self.now = 0.0
        self.step = step

    def __call__(self):
        value = self.now
        self.now += self.step
        return value


class ScriptedHuman:
    """Replies from a list, then `fallback`; remembers what it was asked."""

    answer_command = ["python", "answer-stub.py"]

    def __init__(self, replies, fallback=None):
        self.replies = list(replies)
        self.fallback = fallback if fallback is not None else human.Reply(text="keep going")
        self.asked = []

    def reply(self, text):
        self.asked.append(text)
        return self.replies.pop(0) if self.replies else self.fallback


def read_records(private_root):
    rows = []
    for path in sorted((private_root / "records").glob("*.jsonl")):
        rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return rows


def messages(cmd):
    return [entry["text"] for entry in fake.read_log(cmd) if entry["kind"] == "message"]


def start_entry(cmd):
    return next(entry for entry in fake.read_log(cmd) if entry["kind"] == "start")


def start_entries(cmd):
    return [entry for entry in fake.read_log(cmd) if entry["kind"] == "start"]


def build(project, repo, private_root, tmp_path, spec, who, **kwargs):
    cmd = fake.command({"mode": "stream", **spec}, tmp_path / "specs")
    kwargs.setdefault("arm", "baseline")
    result = drive.drive_build(
        project, "OPENING", human=who, repo_root=repo, private_root=private_root,
        claude_cmd=cmd, **kwargs,
    )
    return result, cmd


def test_continues_after_each_end_of_turn_until_the_human_says_done(project, repo, private_root, tmp_path):
    """Adversarial where: a driver that stops at the first end of turn, that
    answers with the wrong text, or that sends the done reply on would run a
    one-turn build or one turn too many; the message shape on stdin is the
    contract the real claude parses."""
    who = ScriptedHuman([
        human.Reply(text="reply-one"),
        human.Reply(text="all good, ship it", done=True),
    ])
    spec = {"turns": [{"text": "T1"}, {"text": "T2"}, {"text": "T3"}]}

    result, cmd = build(project, repo, private_root, tmp_path, spec, who)

    assert result.end == "human-done"
    assert result.turns == 2
    assert messages(cmd) == ["OPENING", "reply-one"]
    assert who.asked == ["T1", "T2"]
    assert not [e for e in fake.read_log(cmd) if e["kind"] == "bad-message"]


@pytest.mark.parametrize(
    "case",
    [
        {"name": "turns", "kwargs": {"max_turns": 3}, "expect_end": "turns", "expect_turns": 3, "expect_asked": 2},
        {"name": "wall-time", "kwargs": {"max_wall_seconds": 100, "clock": Ticker(40)}, "expect_end": "wall-time"},
    ],
    ids=lambda case: case["name"],
)
def test_each_cap_ends_the_build_without_asking_the_human_again(project, repo, private_root, tmp_path, case):
    """Adversarial where: an off-by-one on the turn cap (a fourth turn after
    `max_turns=3`, or the human asked once more after the last allowed turn)
    and a wall-time cap that is never read leave a build running past its
    allowance; a human that never says done must not keep the session alive."""
    who = ScriptedHuman([], fallback=human.Reply(text="more"))
    spec = {"turns": [{"text": f"T{i}"} for i in range(1, 40)]}

    result, cmd = build(project, repo, private_root, tmp_path, spec, who, **case["kwargs"])

    assert result.end == case["expect_end"]
    if "expect_turns" in case:
        assert result.turns == case["expect_turns"]
        assert len(who.asked) == case["expect_asked"]
        assert len(messages(cmd)) == case["expect_turns"]
    else:
        assert 1 <= result.turns < 39
    row = [r for r in read_records(private_root) if r["role"] == "build"][0]
    assert row["outcome"] == "failed"


@pytest.mark.parametrize(
    "case",
    [
        {"name": "rejected-limit-event", "turn": {"limit": "rejected"}, "end": "usage-limit", "outcome": "usage-limit"},
        {"name": "api-error-limit", "turn": {"limit": "api_error"}, "end": "usage-limit", "outcome": "usage-limit"},
        {"name": "budget-guard-error", "turn": {"error": True}, "end": "failed", "outcome": "failed"},
        {"name": "crash-mid-line", "turn": {"crash": True}, "end": "failed", "outcome": "failed"},
    ],
    ids=lambda case: case["name"],
)
def test_a_bad_end_of_the_build_session_stops_the_driver_and_is_recorded(
    project, repo, private_root, tmp_path, case
):
    """Adversarial where: a driver that treats an error or limit result as an
    ordinary end of turn asks the human and keeps writing to a dead session; a
    crash with a truncated JSON line must end as `failed` rather than hang or
    raise, and the row's outcome must say which kind of end it was."""
    who = ScriptedHuman([])
    spec = {"turns": [{"text": "T1"}, case["turn"]]}

    result, cmd = build(project, repo, private_root, tmp_path, spec, who)

    assert result.end == case["end"]
    assert who.asked == ["T1"]
    assert len(messages(cmd)) == 2
    if case["end"] == "usage-limit" and case["turn"]["limit"] == "rejected":
        assert result.resets_at == fake_claude.RESETS_AT
    row = [r for r in read_records(private_root) if r["role"] == "build"][0]
    assert row["outcome"] == case["outcome"]


@pytest.mark.parametrize("outcome", ["usage-limit", "failed"])
def test_a_human_session_that_ends_badly_ends_the_build_the_same_way(project, repo, private_root, tmp_path, outcome):
    """Adversarial where: the simulated human hits the usage limit or crashes;
    a driver that only watches the build session sends an empty message or
    loops on a human that can never answer."""
    who = ScriptedHuman([human.Reply(text="", outcome=outcome)])
    spec = {"turns": [{"text": "T1"}, {"text": "T2"}]}

    result, cmd = build(project, repo, private_root, tmp_path, spec, who)

    assert result.end == outcome
    assert messages(cmd) == ["OPENING"]


def test_command_line_hook_settings_and_environment_of_the_build_session(
    project, repo, private_root, tmp_path, monkeypatch
):
    """Adversarial where: a budget flag read from a default instead of the
    argument (17.5 differs from the default 25), a missing stream-json input
    flag, a hook that overwrites the project's other local settings, a project
    cwd that is not the project, and credentials surviving into the child."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "parent-secret")
    settings = project / ".claude" / "settings.local.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}}), encoding="utf-8")
    who = ScriptedHuman([human.Reply(text="done", done=True)])

    _, cmd = build(project, repo, private_root, tmp_path, {"turns": [{}]}, who, max_budget_usd=17.5)

    entry = start_entry(cmd)
    argv = entry["argv"]
    for flag in ("-p", "--verbose", "--strict-mcp-config"):
        assert flag in argv
    assert argv[argv.index("--input-format") + 1] == "stream-json"
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert argv[argv.index("--setting-sources") + 1] == "project,local"
    assert argv[argv.index("--max-budget-usd") + 1] == "17.5"
    assert "--plugin-dir" not in argv
    assert os.path.samefile(entry["cwd"], project)
    assert "ANTHROPIC_API_KEY" not in entry["env"]

    saved = json.loads(settings.read_text(encoding="utf-8"))
    assert saved["permissions"] == {"allow": ["Bash(ls)"]}
    ours = [
        group for group in saved["hooks"]["PreToolUse"]
        if any("answer_question.py" in hook["command"] for hook in group["hooks"])
    ]
    assert len(ours) == 1
    for tool in ("AskUserQuestion", "Bash", "Write", "Edit"):
        assert re.fullmatch(ours[0]["matcher"], tool), tool
    config_path = entry["env"]["OVERHEAD_HOOK_CONFIG"]
    config = json.loads(open(config_path, encoding="utf-8").read())
    assert os.path.samefile(config["project"], project)
    assert config["answer_command"] == ScriptedHuman.answer_command


def test_the_default_budget_guard_is_50_dollars(project, repo, private_root, tmp_path):
    """Adversarial where: omitting the budget argument must still pass the
    runaway guard; a driver that adds the flag only when asked leaves a build
    without a spending limit."""
    who = ScriptedHuman([human.Reply(text="done", done=True)])

    _, cmd = build(project, repo, private_root, tmp_path, {"turns": [{}]}, who)

    argv = start_entry(cmd)["argv"]
    assert argv[argv.index("--max-budget-usd") + 1] == "50"


def test_installing_the_hook_twice_leaves_one_entry(project, repo, private_root, tmp_path):
    """Adversarial where: a resumed build that appends the hook again would
    answer every question twice."""
    for _ in range(2):
        who = ScriptedHuman([human.Reply(text="done", done=True)])
        build(project, repo, private_root, tmp_path, {"turns": [{}]}, who)

    saved = json.loads((project / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    commands = [hook["command"] for group in saved["hooks"]["PreToolUse"] for hook in group["hooks"]]
    assert sum("answer_question.py" in command for command in commands) == 1


def test_compass_arm_runs_setup_first_pins_the_commit_and_records_init_counts(
    project, repo, private_root, tmp_path, git
):
    """Adversarial where: the Compass arm must send `/compass:setup` before the
    topic, in a session of its own started with `--plugin-dir`, and start the
    build session without it, not asking the human in
    between; a `commit:` pinned to local HEAD
    instead of the remote head (the repo has an unpushed commit) lets the
    self-update fire; the skill and agent counts must be the first and the
    last `system/init`, not the same event twice."""
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "-q", "--bare")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "HEAD")
    remote_head = git(repo, "rev-parse", "HEAD")
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "unpushed")
    local_head = git(repo, "rev-parse", "HEAD")
    assert local_head != remote_head
    plugin_yaml = "source: somewhere\ncommit: 0000000\nversion: 3\n"
    who = ScriptedHuman([human.Reply(text="done", done=True)])
    spec = {
        "init": {"skills": 1, "agents": 0},
        "turns": [
            {"text": "setup finished", "init": {"skills": 40, "agents": 0},
             "write": {".compass/meta/plugin.yaml": plugin_yaml}},
            {"text": "T2", "init": {"skills": 7, "agents": 3}},
        ],
    }

    result, cmd = build(project, repo, private_root, tmp_path, spec, who, arm="compass")

    assert messages(cmd) == ["/compass:setup", "OPENING"]
    assert who.asked == ["T2"]
    starts = start_entries(cmd)
    assert len(starts) == 2
    setup_argv, build_argv = starts[0]["argv"], starts[1]["argv"]
    assert setup_argv[setup_argv.index("--plugin-dir") + 1] == str(repo / "plugin")
    assert "--plugin-dir" not in build_argv
    saved = (project / ".compass" / "meta" / "plugin.yaml").read_text(encoding="utf-8")
    assert f"commit: {remote_head}" in saved
    assert local_head not in saved
    assert "source: somewhere" in saved and "version: 3" in saved
    assert result.init_counts == {
        "before": {"skills": 1, "agents": 0},
        "after": {"skills": 7, "agents": 3},
    }
    row = [r for r in read_records(private_root) if r["role"] == "build"][0]
    assert row["arm"] == "compass"
    assert row["plugin_sha"] == local_head


def test_dirty_plugin_refuses_before_anything_starts(project, repo, private_root, tmp_path):
    """Adversarial where: a build that starts from an uncommitted plugin/
    records a sha that does not describe the Compass that ran."""
    (repo / "plugin" / "keep.txt").write_text("edited\n", encoding="utf-8")
    cmd = fake.command({"mode": "stream", "turns": [{}]}, tmp_path / "specs")

    with pytest.raises(launch.Refused):
        drive.drive_build(
            project, "OPENING", human=ScriptedHuman([]), repo_root=repo, arm="baseline",
            private_root=private_root, claude_cmd=cmd,
        )

    assert fake.read_log(cmd) == []
    assert not (project / ".claude" / "settings.local.json").exists()
    assert read_records(private_root) == []


def test_human_tokens_get_their_own_rows_and_stay_out_of_the_build_row(
    project, repo, private_root, tmp_path
):
    """Adversarial where: the simulated human's tokens added to the build's
    count would fold the measurer into the measured; every human session must
    leave a role `human` row and the build row must hold only the build's
    summed usage (two turns of 10/5/100/20 each)."""
    human_cmd = fake.command(
        {"mode": "oneshot", "usage": [900, 800, 700, 600],
         "replies": [json.dumps({"text": "go on", "done": False}),
                     json.dumps({"text": "fine", "done": True})]},
        tmp_path / "human-specs",
    )
    folder = tmp_path / "human-folder"
    folder.mkdir()
    who = human.SimulatedHuman(
        {"items": [{"id": "G1", "name": "csv export", "detail": "header row"}]},
        folder=folder, repo_root=repo, arm="baseline", state_file=tmp_path / "state.json",
        private_root=private_root, claude_cmd=human_cmd,
    )
    spec = {"turns": [{"text": "T1"}, {"text": "T2"}, {"text": "T3"}]}

    result, _ = build(project, repo, private_root, tmp_path, spec, who)

    assert result.end == "human-done"
    rows = read_records(private_root)
    human_rows = [r for r in rows if r["role"] == "human"]
    build_rows = [r for r in rows if r["role"] == "build"]
    assert len(human_rows) == 2 and len(build_rows) == 1
    assert build_rows[0]["models"][fake_claude.MAIN_MODEL] == {
        "input": 20, "output": 10, "cache_read": 200, "cache_write": 40,
    }
    assert human_rows[0]["models"][fake_claude.MAIN_MODEL]["input"] == 900
    assert build_rows[0]["outcome"] == "done"


def test_no_one_is_asked_while_background_tasks_run(project, repo, private_root, tmp_path):
    """Adversarial where: an end of turn with a background agent still running
    goes to the human, who answers "ok" to a turn that asked nothing, and the
    turn the finished task starts is answered a second time; the human must
    read both turns' text once, after the last task ends."""
    who = ScriptedHuman([human.Reply(text="done", done=True)])
    spec = {"turns": [
        {"text": "started the research agents", "background": ["a1", "a2"]},
        {"text": "", "auto": True, "background": ["a2"]},
        {"text": "research is in", "auto": True, "background": []},
    ]}

    result, cmd = build(project, repo, private_root, tmp_path, spec, who)

    assert messages(cmd) == ["OPENING"]
    assert who.asked == ["started the research agents\n\nresearch is in"]
    assert result.end == drive.HUMAN_DONE
    assert result.turns == 3


def test_a_turn_with_no_text_is_continued_without_the_human(project, repo, private_root, tmp_path):
    """Adversarial where: the human is shown an empty message and, reading
    nothing to answer, invents a new request."""
    who = ScriptedHuman([human.Reply(text="done", done=True)])
    spec = {"turns": [{"text": ""}, {"text": "T2"}]}

    result, cmd = build(project, repo, private_root, tmp_path, spec, who)

    assert who.asked == ["T2"]
    assert messages(cmd) == ["OPENING", drive.CONTINUE_MESSAGE]


def test_the_setup_and_build_sessions_are_counted_once_each(project, repo, private_root, tmp_path, git):
    """Adversarial where: a record that keeps only the last session drops the
    setup session's tokens, or one that reads totals across the restart as one
    running count loses or doubles them."""
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "-q", "--bare")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "HEAD")
    spec = {"turns": [
        {"text": "setup finished", "usage": [100, 0, 0, 0],
         "write": {".compass/meta/plugin.yaml": "commit: 0\n"}},
        {"text": "T2", "usage": [7, 0, 0, 0]},
        {"text": "T3", "usage": [5, 0, 0, 0]},
    ]}
    who = ScriptedHuman([human.Reply(text="more"), human.Reply(text="done", done=True)])

    build(project, repo, private_root, tmp_path, spec, who, arm="compass")

    row = [r for r in read_records(private_root) if r["role"] == "build"][0]
    inputs = sum(counts["input"] for counts in row["models"].values())
    assert inputs == 100 + 7 + 5


def test_a_background_task_that_never_reports_goes_to_the_human_after_the_idle_limit(
    project, repo, private_root, tmp_path, monkeypatch,
):
    """Adversarial where: the session lists a task it never reports finished
    (a monitor left running), and the driver waits for a turn that never comes
    until the wall-time cap ends the build."""
    monkeypatch.setattr(drive, "BACKGROUND_IDLE_SECONDS", 150)
    monkeypatch.setattr(drive, "POLL_SECONDS", 0.05)
    who = ScriptedHuman([human.Reply(text="done", done=True)])
    spec = {"turns": [{"text": "watching the server", "background": ["m1"]}]}

    result, cmd = build(
        project, repo, private_root, tmp_path, spec, who, clock=Ticker(40), max_wall_seconds=10 ** 9,
    )

    assert who.asked == ["watching the server"]
    assert result.end == drive.HUMAN_DONE


def test_self_started_turns_keep_the_session_counts(project, repo, private_root, tmp_path):
    """Adversarial where: the `system/init` that opens a self-started turn, in
    the same session, is read as a new session (tokens counted twice) or as the
    after-setup skill count."""
    who = ScriptedHuman([human.Reply(text="done", done=True)])
    spec = {"init": {"skills": 4, "agents": 2}, "turns": [
        {"text": "started", "background": ["a1"], "usage": [10, 0, 0, 0]},
        {"text": "finished", "auto": True, "background": [], "usage": [3, 0, 0, 0]},
    ]}

    result, cmd = build(project, repo, private_root, tmp_path, spec, who)

    assert result.init_counts == {"before": {"skills": 4, "agents": 2}, "after": {"skills": 4, "agents": 2}}
    row = [r for r in read_records(private_root) if r["role"] == "build"][0]
    assert sum(counts["input"] for counts in row["models"].values()) == 13
