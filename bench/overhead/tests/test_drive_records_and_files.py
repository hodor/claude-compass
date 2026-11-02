"""Probes for drive.py that only the implementation reveals.

The interface is described at the top of test_drive.py.

Adversarial themes: files named from the project folder's last component
(two projects with one name), the record a session leaves when it dies in its
first turn or in the middle of a later one, the line rewrite that pins the
installed commit, a settings file whose hooks have an unexpected shape, and a
simulated human whose reply is blank.
"""

import json

import pytest

import drive
import human
import launch
from test_drive import ScriptedHuman, build, messages, read_records


def test_two_projects_with_one_folder_name_keep_separate_hook_configs(tmp_path, private_root):
    """Adversarial where: the config file is named from the project's last path
    component, so `a/app` and `b/app` share one file and the second build
    overwrites the first's project and answer command; the first hook then
    fences the wrong folder and asks the wrong simulated human."""
    first = tmp_path / "a" / "app"
    second = tmp_path / "b" / "app"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    path_one = drive.write_hook_config(first, private_root, ["human-one"])
    path_two = drive.write_hook_config(second, private_root, ["human-two"])

    assert path_one != path_two
    assert json.loads(path_one.read_text(encoding="utf-8")) == {"project": str(first), "answer_command": ["human-one"]}
    assert json.loads(path_two.read_text(encoding="utf-8")) == {"project": str(second), "answer_command": ["human-two"]}


@pytest.mark.parametrize(
    "case",
    [
        {"name": "limit-in-second-turn", "turns": [{"text": "T1"}, {"limit": "rejected"}], "outcome": "usage-limit",
         "input": 20},
        {"name": "crash-in-second-turn", "turns": [{"text": "T1"}, {"crash": True}], "outcome": "failed",
         "input": 10},
        {"name": "crash-in-first-turn", "turns": [{"crash": True}], "outcome": "failed", "input": 0},
    ],
    ids=lambda case: case["name"],
)
def test_a_session_that_dies_mid_turn_leaves_exactly_one_row_with_the_tokens_it_reported(
    project, repo, private_root, tmp_path, case
):
    """Adversarial where: a crash or usage limit that skips the recording step
    loses the whole session's spend, one that records twice (once per exit
    path) doubles it, and a crash before any result event must not raise from an
    empty usage table; the row must carry what the finished turns and the limit
    result reported, once."""
    who = ScriptedHuman([])

    result, _ = build(project, repo, private_root, tmp_path, {"turns": case["turns"]}, who)

    rows = [row for row in read_records(private_root) if row["role"] == "build"]
    assert len(rows) == 1
    assert rows[0]["outcome"] == case["outcome"] == result.end
    spent = sum(usage["input"] for usage in rows[0]["models"].values())
    assert spent == case["input"]


@pytest.mark.parametrize(
    "case",
    [
        {"name": "lookalike-key", "before": "version: 1\ninstalled_commit: old\n",
         "after": "version: 1\ninstalled_commit: old\ncommit: NEW\n"},
        {"name": "indented-key", "before": "source:\n  commit: old\n  url: x\n",
         "after": "source:\n  commit: NEW\n  url: x\n"},
        {"name": "no-trailing-newline", "before": "version: 1", "after": "version: 1\ncommit: NEW\n"},
        {"name": "commented-key", "before": "# commit: old\nversion: 1\n",
         "after": "# commit: old\nversion: 1\ncommit: NEW\n"},
    ],
    ids=lambda case: case["name"],
)
def test_pinning_the_commit_rewrites_only_the_commit_key(project, case):
    """Adversarial where: an unanchored match rewrites `installed_commit:` or a
    commented `# commit:` line instead of the key, and a missing key must be
    appended on its own line even when the file has no trailing newline."""
    path = project / ".compass" / "meta" / "plugin.yaml"
    path.parent.mkdir(parents=True)
    path.write_bytes(case["before"].encode("utf-8"))

    assert drive.pin_commit(project, "NEW") is True

    assert path.read_bytes().decode("utf-8").replace("\r\n", "\n") == case["after"]


def test_a_blank_human_reply_sends_the_continue_message(project, repo, private_root, tmp_path):
    """Adversarial where: a human whose reply is only whitespace would send an
    empty user message, which the real session rejects or treats as the end of
    input; the driver must send `continue` instead."""
    who = ScriptedHuman([human.Reply(text="   \n"), human.Reply(text="bye", done=True)])

    result, cmd = build(project, repo, private_root, tmp_path, {"turns": [{"text": "T1"}, {"text": "T2"}]}, who)

    assert result.end == "human-done"
    assert messages(cmd) == ["OPENING", "continue"]


@pytest.mark.parametrize(
    "settings",
    [
        {"hooks": None},
        {"hooks": {"PreToolUse": ["not a group"]}},
        {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": ["not a hook"]}]}},
    ],
    ids=["hooks-null", "group-is-a-string", "hook-is-a-string"],
)
def test_a_settings_file_with_misshapen_hooks_is_refused_or_repaired_not_crashed(project, settings):
    """Adversarial where: the merge indexes into the existing hooks without
    checking their shape, so one misshapen entry among valid settings ends in
    an AttributeError traceback instead of the `launch.Refused` the command
    line reports as a refusal."""
    path = project / ".claude" / "settings.local.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(settings), encoding="utf-8")

    try:
        drive.install_hook(project)
    except launch.Refused:
        return

    merged = json.loads(path.read_text(encoding="utf-8"))
    commands = [hook["command"] for group in merged["hooks"]["PreToolUse"] for hook in group["hooks"]]
    assert any(drive.HOOK_SCRIPT.name in command for command in commands)
