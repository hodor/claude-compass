"""`--runs` and `--run-log`: a single replay build kept apart from the pilot.

A smoke build replays one pool topic once, in one arm, and logs to a run log
of its own, so the pilot's run log never treats it as one of the pilot's
builds and the pilot's resume logic never skips a slot because a smoke build
closed it.
"""

import json

import pytest

import pilot
from test_pilot import World, go, seed_pool


def _events(path, name=None):
    if not path.exists():
        return []
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [e for e in events if name is None or e["event"] == name]


def test_runs_one_builds_each_named_topic_once_per_arm(repo, private_root, projects_root):
    """Adversarial where: `runs_per_arm=1` still builds two runs, or builds
    run 2 instead of run 1, so the smoke build would not pair with run 1."""
    world = World(private_root)
    ids = seed_pool(world, repo, private_root, 2)
    result = go(world, repo, private_root, projects_root, topic_ids=[ids[0]], arms=("compass",), runs_per_arm=1)
    assert result.status == "complete"
    assert [(d["topic"], d["arm"]) for d in world.drives] == [(ids[0], "compass")]
    closed = _events(pilot.run_log_path(private_root), "build-closed")
    assert [(e["topic"], e["arm"], e["run"]) for e in closed] == [(ids[0], "compass", 1)]


def test_a_named_run_log_takes_every_event_and_the_pilot_log_stays_untouched(
    repo, private_root, projects_root, tmp_path,
):
    """Adversarial where: the named log gets the build events but the judge or
    a halt still writes to the pilot's log; or a build closed in the pilot's
    log is skipped by a run on a named log (the two must not share state)."""
    world = World(private_root)
    ids = seed_pool(world, repo, private_root, 2)
    go(world, repo, private_root, projects_root, topic_ids=[ids[0]], arms=("compass",), runs_per_arm=1)
    main_log = pilot.run_log_path(private_root)
    before = main_log.read_bytes()

    smoke = tmp_path / "logs" / "smoke.jsonl"
    world.drives.clear()
    result = go(
        world, repo, private_root, projects_root, topic_ids=[ids[0]], arms=("compass",), runs_per_arm=1,
        run_log=smoke,
    )
    assert result.status == "complete"
    assert len(world.drives) == 1
    assert main_log.read_bytes() == before
    assert [e["event"] for e in _events(smoke)] == ["build-closed", "judged"]


def test_a_named_run_log_inside_a_git_work_tree_is_refused_before_any_build(repo, private_root, projects_root):
    """Adversarial where: a run log written into the repository leaks project
    paths into a file git can commit."""
    world = World(private_root)
    ids = seed_pool(world, repo, private_root, 1)
    with pytest.raises(pilot.PilotError):
        go(world, repo, private_root, projects_root, topic_ids=ids, arms=("compass",), run_log=repo / "log.jsonl")
    assert world.drives == []


@pytest.mark.parametrize("runs", [0, -1])
def test_runs_below_one_is_refused_before_any_build(runs, repo, private_root, projects_root):
    world = World(private_root)
    ids = seed_pool(world, repo, private_root, 1)
    with pytest.raises(pilot.PilotError):
        go(world, repo, private_root, projects_root, topic_ids=ids, arms=("compass",), runs_per_arm=runs)
    assert world.drives == []


def test_main_passes_runs_and_run_log_through(monkeypatch, tmp_path):
    seen = {}

    def fake_run_pilot(**kwargs):
        seen.update(kwargs)
        return pilot.PilotResult(status="complete")

    monkeypatch.setattr(pilot, "run_pilot", fake_run_pilot)
    log = tmp_path / "smoke.jsonl"
    code = pilot.main([
        "--private-root", str(tmp_path / "priv"), "--topics", "t-1", "--arms", "compass",
        "--runs", "1", "--run-log", str(log),
    ])
    assert code == 0
    assert seen["runs_per_arm"] == 1
    assert str(seen["run_log"]) == str(log)

    seen.clear()
    assert pilot.main(["--private-root", str(tmp_path / "priv")]) == 0
    assert seen["runs_per_arm"] == 2
    assert seen["run_log"] is None
