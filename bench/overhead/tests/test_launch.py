"""Tests for launch.py: the isolated environment, the command line, the clean
plugin check and the classification of a session's end.

Adversarial themes: a credential that survives into the child silently moves a
run from the subscription to the API; a stale transcript from an earlier run
turns a crash into a usage-limit halt; a classifier keyed on `subtype` or on a
substring of stdout halts healthy runs and misses real limits.
"""

import json
import os
import time

import pytest

import fake_claude
import launch
from conftest import CREDENTIAL_VARS


def is_under(child, parent):
    child = os.path.normcase(os.path.realpath(str(child)))
    parent = os.path.normcase(os.path.realpath(str(parent)))
    return os.path.commonpath([child, parent]) == parent


def same(left, right):
    return os.path.normcase(os.path.realpath(str(left))) == os.path.normcase(os.path.realpath(str(right)))


def value_after(argv, flag):
    return argv[argv.index(flag) + 1]


def run(project, repo, private_root, fake_cmd, **kwargs):
    return launch.run_session(
        project, "build the thing", repo_root=repo, private_root=private_root,
        claude_cmd=fake_cmd, **kwargs,
    )


def test_session_environment_drops_credentials_and_sets_the_sandbox_variables(private_root, tmp_path):
    """Adversarial where: any one of the five credential variables left in the
    child, or a parent value for a variable the harness must override (config
    dir, GitHub config, dsh home, auto-update, pip guard) winning over the
    sandbox value, breaks the isolation the measurement depends on."""
    human_gh = tmp_path / "human-gh"
    human_dsh = tmp_path / "human-dsh"
    human_gh.mkdir()
    human_dsh.mkdir()
    parent = {name: f"parent-secret-{index}" for index, name in enumerate(CREDENTIAL_VARS)}
    parent.update({
        "KEEP_ME": "kept-value",
        "DISABLE_AUTOUPDATER": "0",
        "PIP_REQUIRE_VIRTUALENV": "0",
        "CLAUDE_CONFIG_DIR": str(tmp_path / "human-claude-config"),
        "GH_CONFIG_DIR": str(human_gh),
        "DSH_HOME": str(human_dsh),
    })
    before = dict(parent)

    env = launch.session_environment(parent, private_root)

    assert parent == before
    for name in CREDENTIAL_VARS:
        assert name not in env, name
    assert env["KEEP_ME"] == "kept-value"
    assert env["DISABLE_AUTOUPDATER"] == "1"
    assert env["PIP_REQUIRE_VIRTUALENV"] == "1"
    assert same(env["CLAUDE_CONFIG_DIR"], private_root / "claude-config")
    gh = env["GH_CONFIG_DIR"]
    assert is_under(gh, private_root) and not same(gh, human_gh)
    assert os.path.isdir(gh) and os.listdir(gh) == []
    dsh = env["DSH_HOME"]
    assert is_under(dsh, private_root) and not same(dsh, human_dsh)
    assert not os.path.exists(dsh)

    bare = launch.session_environment({"KEEP_ME": "kept-value"}, private_root)
    assert not set(CREDENTIAL_VARS) & set(bare)


def test_session_environment_takes_editor_folders_off_path_and_keeps_the_rest_in_order(private_root):
    """Adversarial where: matching the substring `code` would drop unrelated
    folders such as a codecs directory, and a case-sensitive match would keep a
    capitalised Cursor folder, which opens a review window."""
    keep = ["/opt/codecs", "/opt/python313/bin", "/usr/bin"]
    drop = [
        "/opt/Microsoft VS Code/bin",
        "/home/u/.local/cursor/resources/app/bin",
        "/home/u/Programs/Cursor/bin",
    ]
    entries = [keep[0], drop[0], keep[1], drop[1], drop[2], keep[2]]

    env = launch.session_environment({"PATH": os.pathsep.join(entries)}, private_root)

    assert env["PATH"].split(os.pathsep) == keep


def test_run_session_child_sees_the_isolated_environment_flags_and_project_cwd(
    project, repo, private_root, fake_cmd, use_scenario, monkeypatch
):
    """Adversarial where: the environment built for the child must be the one the
    child receives (credentials set in the parent, a config dir pointing at the
    human's account); the flags must carry exactly `project,local` as setting
    sources (a wider list loads the human's user rules) and the project as cwd."""
    log = use_scenario("clean")
    for index, name in enumerate(CREDENTIAL_VARS):
        monkeypatch.setenv(name, f"parent-secret-{index}")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(project / "human-config"))
    monkeypatch.setenv("KEEP_ME", "kept-value")

    run(project, repo, private_root, fake_cmd)

    (call,) = log.calls()
    argv, env = call["argv"], call["env"]
    assert same(call["cwd"], project)
    assert "-p" in argv
    assert value_after(argv, "--output-format") == "stream-json"
    assert "--verbose" in argv
    assert value_after(argv, "--setting-sources") == "project,local"
    assert "--strict-mcp-config" in argv
    assert "--plugin-dir" not in argv
    for name in CREDENTIAL_VARS:
        assert name not in env, name
    assert same(env["CLAUDE_CONFIG_DIR"], private_root / "claude-config")
    assert env["KEEP_ME"] == "kept-value"
    assert env["DISABLE_AUTOUPDATER"] == "1"
    assert env["PIP_REQUIRE_VIRTUALENV"] == "1"


def test_run_session_loads_the_plugin_from_the_repository_only_in_the_compass_arm(
    project, repo, private_root, fake_cmd, use_scenario
):
    """Adversarial where: pointing --plugin-dir anywhere but the repository's
    plugin/ folder measures a different Compass than the one under test."""
    log = use_scenario("clean")

    run(project, repo, private_root, fake_cmd, plugin=True)

    (call,) = log.calls()
    assert same(value_after(call["argv"], "--plugin-dir"), repo / "plugin")


def _modify(repo, git):
    (repo / "plugin" / "keep.txt").write_text("changed\n", encoding="utf-8")


def _untracked(repo, git):
    (repo / "plugin" / "new.txt").write_text("new\n", encoding="utf-8")


def _staged(repo, git):
    (repo / "plugin" / "staged.txt").write_text("staged\n", encoding="utf-8")
    git(repo, "add", "plugin/staged.txt")


def _deleted(repo, git):
    (repo / "plugin" / "keep.txt").unlink()


@pytest.mark.parametrize("change", [_modify, _untracked, _staged, _deleted], ids=lambda f: f.__name__.strip("_"))
def test_run_session_refuses_a_dirty_plugin_folder_before_starting_claude(
    project, repo, private_root, fake_cmd, use_scenario, git, change
):
    """Adversarial where: a build run from an uncommitted plugin/ records a sha
    that does not describe the Compass it measured; untracked, staged and
    deleted files are as dirty as a modified one."""
    log = use_scenario("clean")
    change(repo, git)

    with pytest.raises(launch.Refused):
        run(project, repo, private_root, fake_cmd, plugin=True)

    assert log.calls() == []


def test_run_session_refuses_when_git_cannot_report_the_plugin_state(
    project, tmp_path, private_root, fake_cmd, use_scenario
):
    """Adversarial where: `git status` failing prints nothing, and empty output
    read as clean lets an unverifiable plugin/ through."""
    log = use_scenario("clean")
    plain = tmp_path / "plain"
    (plain / "plugin").mkdir(parents=True)

    with pytest.raises(launch.Refused):
        run(project, plain, private_root, fake_cmd, plugin=True)

    assert log.calls() == []


def _dirty_readme(repo, git):
    (repo / "README.md").write_text("changed outside plugin\n", encoding="utf-8")


def _ignored_in_plugin(repo, git):
    (repo / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-q", "-m", "ignore pyc")
    (repo / "plugin" / "cache.pyc").write_bytes(b"\x00")


@pytest.mark.parametrize("change", [None, _dirty_readme, _ignored_in_plugin], ids=["clean", "readme", "ignored"])
def test_run_session_starts_when_plugin_is_clean_whatever_else_is_dirty(
    project, repo, private_root, fake_cmd, use_scenario, git, change
):
    """Adversarial where: the check scoped to the whole repository would refuse
    on a dirty file outside plugin/, and one that reads ignored files as changes
    would refuse on a byte-code cache."""
    log = use_scenario("clean")
    if change is not None:
        change(repo, git)

    result = run(project, repo, private_root, fake_cmd, plugin=True)

    assert len(log.calls()) == 1
    assert result.status == "done"


CLASSIFICATION = [
    ("clean", "done"),
    ("clean_with_stray_line", "done"),
    ("clean_mentions_limit", "done"),
    ("subagent", "done"),
    ("multiturn_clear", "done"),
    ("limit_event", "usage-limit"),
    ("limit_api_error", "usage-limit"),
    ("limit_api_error_other_subtype", "usage-limit"),
    ("limit_silent", "usage-limit"),
    ("transient_429", "failed"),
    ("error_result_other", "failed"),
    ("subtype_lookalike", "failed"),
    ("crash", "failed"),
    ("silent_crash", "failed"),
    ("silent_crash_no_transcript", "failed"),
    ("no_result_exit0", "failed"),
]


@pytest.mark.parametrize("name,expected", CLASSIFICATION, ids=[row[0] for row in CLASSIFICATION])
def test_run_session_classifies_the_end_of_each_session(
    project, repo, private_root, fake_cmd, use_scenario, name, expected
):
    """Adversarial where: the usage-limit decision keys on `api_error` (or a
    rejected rate_limit_event, or the transcript tail), never on `subtype`: a
    limit result whose subtype reads `success` or `error_during_execution` is
    still a limit, a lookalike subtype with no api_error is not, a transient 429
    is not, and a clean run that quotes limit words in its text is not."""
    use_scenario(name)

    result = run(project, repo, private_root, fake_cmd)

    assert result.status == expected
    assert result.returncode == fake_claude.scenario(name, project)[1]


def test_rejected_rate_limit_event_carries_its_reset_time_and_an_allowed_one_does_not(
    project, repo, private_root, fake_cmd, use_scenario
):
    """Adversarial where: reading `resetsAt` from any rate_limit_event, as the
    allowed one in a healthy run carries it too, reports a reset time for a
    session that never hit a limit."""
    use_scenario("limit_event")
    halted = run(project, repo, private_root, fake_cmd)
    use_scenario("clean")
    healthy = run(project, repo, private_root, fake_cmd)

    assert halted.resets_at == fake_claude.RESETS_AT
    assert healthy.resets_at is None


def test_run_session_returns_the_json_events_in_order_and_skips_unparseable_lines(
    project, repo, private_root, fake_cmd, use_scenario
):
    """Adversarial where: a stray log line mid-stream must not abort the read,
    and a line cut off by a crash must be dropped rather than parsed half-way."""
    use_scenario("clean_with_stray_line")
    stray = run(project, repo, private_root, fake_cmd)
    use_scenario("crash")
    crashed = run(project, repo, private_root, fake_cmd)

    expected = [e["type"] for e in fake_claude.events_for("clean_with_stray_line", project)]
    assert [e["type"] for e in stray.events] == expected
    assert [e["type"] for e in crashed.events] == ["system", "assistant"]


@pytest.mark.parametrize("stale_name", ["0000-old.jsonl", "zzzz-old.jsonl"])
@pytest.mark.parametrize(
    "scenario_name,stale_has_api_error,expected",
    [("silent_crash", True, "failed"), ("limit_silent", False, "usage-limit")],
    ids=["stale-limit-then-crash", "stale-benign-then-limit"],
)
def test_transcript_tail_is_read_from_the_newest_transcript_of_the_project(
    project, repo, private_root, fake_cmd, use_scenario, stale_name, scenario_name, stale_has_api_error, expected
):
    """Adversarial where: a transcript left by an earlier session in the same
    project folder, sorting before or after the new one by name, must not decide
    the classification of this session."""
    use_scenario(scenario_name)
    folder = private_root / "claude-config" / "projects" / fake_claude.encode_cwd(project)
    folder.mkdir(parents=True)
    stale = folder / stale_name
    stale_lines = fake_claude._transcript("old", project, api_error_tail=stale_has_api_error)
    stale.write_text("".join(json.dumps(line) + "\n" for line in stale_lines), encoding="utf-8")
    hour_ago = time.time() - 3600
    os.utime(stale, (hour_ago, hour_ago))

    result = run(project, repo, private_root, fake_cmd)

    assert result.status == expected
