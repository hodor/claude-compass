"""Edge tests for pilot.run_pilot found by reading its resume, judge and
report code.

Adversarial themes: a crash that leaves the run log or the pool half-written,
a pool and a run log that disagree, repeated usage-limit halts, a judge that
fails for one build, degenerate token totals, and a report with nothing to
compute.
"""

import json
import re

import pytest

import pilot
import records
import stats
import topics
from test_pilot import MODEL, RESETS_AT, SENTINEL_SESSION, World, go, log_events

ARMS = ("compass", "baseline")


class ScriptedWorld(World):
    """A World whose build token usage is chosen per (topic, arm, run) and whose
    drive or pick can crash (KeyboardInterrupt) after writing its private file."""

    def __init__(self, *args, usage=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usage = usage
        self.crash_drive_call = None
        self.crash_pick_call = None

    def pick(self, **kwargs):
        entry = super().pick(**kwargs)
        if self.crash_pick_call == len(self.pick_ok):
            self.crash_pick_call = None
            raise KeyboardInterrupt
        return entry

    def drive(self, argv):
        call = len(self.drives) + 1
        if self.usage is None and self.crash_drive_call != call:
            return super().drive(argv)
        option = lambda name: argv[argv.index(name) + 1]  # noqa: E731
        brief = json.loads(open(option("--brief-file"), encoding="utf-8").read())
        topic_id, arm = brief["context"].rsplit(" ", 1)[1], option("--arm")
        self.drives.append({"project": argv[0], "arm": arm, "topic": topic_id, "argv": list(argv)})
        code = self.exits.get(call, 0)
        run = self.done_runs.get((topic_id, arm), 0) + 1
        total = self.usage(topic_id, arm, run) if self.usage else 1000
        row = records.record_session(
            [{"type": "result", "modelUsage": {MODEL: {
                "inputTokens": total, "outputTokens": 0,
                "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0}}}],
            role="build", outcome={0: "done", 1: "failed"}[code], arm=arm,
            private_root=option("--private-root"),
        )
        if self.crash_drive_call == call:
            self.crash_drive_call = None
            raise KeyboardInterrupt
        self.clock.now += 100
        print(json.dumps({"end": "human-done", "turns": 5, "resets_at": None}))
        self.done_runs[(topic_id, arm)] = run
        self.rows[(topic_id, arm, run)] = (row["weighted"], sum(row["models"][MODEL].values()))
        return code


def build_rows(private_root):
    rows = []
    for path in sorted((private_root / "records").glob("*.jsonl")):
        rows += [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]
    return [r for r in rows if r.get("role") == "build"]


def keys(events):
    return [(e["topic"], e["arm"], e["run"]) for e in events]


def parsable_events(private_root, name):
    found = []
    for line in pilot.run_log_path(private_root).read_text("utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("event") == name:
            found.append(event)
    return found


def test_a_torn_last_log_line_does_not_swallow_the_next_event(repo, private_root, projects_root):
    """Adversarial where: a crash mid-write leaves a partial line with no
    newline; the next append glues onto it, the glued line fails to parse, and
    the build-closed event it carried is lost, so the build runs again on the
    third run (double spend) and the aggregates miss a build."""
    world = World(private_root)
    world.exits[5] = 3
    assert go(world, repo, private_root, projects_root).status == "usage-limit"
    with open(pilot.run_log_path(private_root), "a", encoding="utf-8", newline="\n") as handle:
        handle.write('{"event": "judged", "topic": "t-0000')
    assert go(world, repo, private_root, projects_root).status == "complete"
    closed = parsable_events(private_root, "build-closed")
    assert len(closed) == 12 and len(set(keys(closed))) == 12
    drives_before = len(world.drives)
    again = go(world, repo, private_root, projects_root)
    assert again.status == "complete"
    assert len(world.drives) == drives_before
    assert len(world.judge_ok) == 12


def test_a_build_that_crashed_after_its_record_row_is_redone_and_counted_once(repo, private_root, projects_root):
    """Adversarial where: the crashed build's orphan records row is added to
    the redone build's totals (mark taken before the crash), or the build is
    skipped on resume because its row exists."""
    world = ScriptedWorld(private_root)
    world.crash_drive_call = 4
    with pytest.raises(KeyboardInterrupt):
        go(world, repo, private_root, projects_root)
    assert len(log_events(private_root, "build-closed")) == 3
    result = go(world, repo, private_root, projects_root)
    assert result.status == "complete" and result.closed == 12
    rows = build_rows(private_root)
    assert len(rows) == 13
    orphan = rows[3]
    closed = log_events(private_root, "build-closed")
    assert len(set(keys(closed))) == 12
    for arm in ARMS:
        expected = sum(r["weighted"] for r in rows if r["arm"] == arm)
        expected -= orphan["weighted"] if orphan["arm"] == arm else 0
        assert sum(e["weighted"] for e in closed if e["arm"] == arm) == pytest.approx(expected)


def test_a_pool_entry_written_before_a_crash_but_never_logged_is_not_a_pilot_topic(repo, private_root, projects_root):
    """Adversarial where: pick crashed between writing the pool and logging the
    pick; the resume counts the orphan as a pilot topic, builds it without
    goals, or counts it in the probe."""
    world = ScriptedWorld(private_root)
    world.crash_pick_call = 21
    with pytest.raises(KeyboardInterrupt):
        go(world, repo, private_root, projects_root)
    result = go(world, repo, private_root, projects_root)
    assert result.status == "complete"
    logged = [e["topic"] for e in log_events(private_root, "picked") if e["stage"] == "pilot"]
    assert result.topics == logged and len(logged) == 3
    assert {d["topic"] for d in world.drives} == set(logged)
    assert result.probe["seeded"]["picks"] == 10 and result.probe["unseeded"]["picks"] == 10


def test_a_pool_that_lost_a_logged_topic_fails_with_a_real_error_not_stop_iteration(repo, private_root, projects_root):
    """Adversarial where: the run log names a pilot topic the pool no longer
    holds; the builder's lookup runs off the end of the pool and surfaces a
    bare StopIteration."""
    world = World(private_root)
    world.exits[2] = 3
    assert go(world, repo, private_root, projects_root).status == "usage-limit"
    pool_file = topics.topics_dir(private_root) / "pool.json"
    pool = json.loads(pool_file.read_text("utf-8"))
    dropped = [e["topic"] for e in log_events(private_root, "picked") if e["stage"] == "pilot"][-1]
    pool["topics"] = [e for e in pool["topics"] if e["id"] != dropped]
    pool_file.write_text(json.dumps(pool), encoding="utf-8")
    try:
        result = go(world, repo, private_root, projects_root)
    except StopIteration:
        pytest.fail("pilot raised a bare StopIteration for a topic missing from the pool")
    except Exception:
        return
    assert result.status != "complete"


@pytest.mark.parametrize(
    "halts", [{1: 3}, {2: 3}, {12: 3}, {3: 3, 4: 3, 5: 3}], ids=["first", "smoke pair", "last", "back to back"],
)
def test_repeated_usage_limit_halts_keep_the_build_order_of_an_uninterrupted_run(
    halts, repo, private_root, projects_root, tmp_path,
):
    """Adversarial where: a halt on the resumed build, or on the first or last
    build, reorders the slots, skips the halted one or repeats a finished one."""
    plain_root = tmp_path / "plain" / "overhead"
    plain = World(plain_root)
    go(plain, repo, plain_root, tmp_path / "plain-projects")
    expected = [(d["topic"], d["arm"]) for d in plain.drives]

    world = World(private_root)
    world.exits.update(halts)
    statuses = []
    for _ in range(len(halts) + 2):
        statuses.append(go(world, repo, private_root, projects_root).status)
        if statuses[-1] == "complete":
            break
    assert statuses[-1] == "complete" and statuses[:-1] == ["usage-limit"] * len(halts)
    ran = [(d["topic"], d["arm"]) for i, d in enumerate(world.drives, 1) if halts.get(i) != 3]
    assert ran == expected
    assert len(log_events(private_root, "usage-limit")) == len(halts)
    assert all(e["resets_at"] == RESETS_AT for e in log_events(private_root, "usage-limit"))
    assert len(world.judge_ok) == 12


@pytest.mark.parametrize(
    "failure", [ValueError("unusable"), topics.SessionError("failed")], ids=["unusable reply", "failed session"],
)
def test_a_judge_that_keeps_failing_for_one_build_loses_no_other_build(failure, repo, private_root, projects_root):
    """Adversarial where: one build's judge failing three times discards the
    closed builds before it, or on resume rebuilds them instead of judging only
    the one that failed."""
    world = World(private_root)
    real = world.judge
    state = {"failing": True}

    def judge(project, topic_id, **kwargs):
        if state["failing"] and len(world.judge_ok) == 3:
            raise failure
        return real(project, topic_id, **kwargs)

    def runner():
        return pilot.run_pilot(
            repo_root=repo, private_root=private_root, projects_root=projects_root,
            pick=world.pick, freeze=world.freeze, judge=judge, drive=world.drive, clock=world.clock,
        )

    with pytest.raises(type(failure)):
        runner()
    assert len(log_events(private_root, "build-closed")) == 4
    assert len(log_events(private_root, "judged")) == 3
    assert len(world.drives) == 4

    state["failing"] = False
    result = runner()
    assert result.status == "complete" and result.closed == 12
    assert len(world.drives) == 12
    assert len(set(keys(log_events(private_root, "judged")))) == 12


def test_a_judge_that_fails_once_is_retried_without_a_second_judged_event(repo, private_root, projects_root):
    """Adversarial where: one unusable judge reply halts the pilot instead of
    being retried, or the retry leaves two judged events for one build."""
    world = World(private_root)
    real = world.judge
    calls = []

    def judge(project, topic_id, **kwargs):
        calls.append(project)
        if len(calls) == 2:
            raise ValueError("unusable")
        return real(project, topic_id, **kwargs)

    result = pilot.run_pilot(
        repo_root=repo, private_root=private_root, projects_root=projects_root,
        pick=world.pick, freeze=world.freeze, judge=judge, drive=world.drive, clock=world.clock,
    )
    assert result.status == "complete"
    assert len(calls) == 13
    assert len(log_events(private_root, "judged")) == 12


def run_to_report(world, repo, private_root, projects_root, tmp_path, **kwargs):
    report = tmp_path / "out" / "report.md"
    result = go(world, repo, private_root, projects_root, report_path=report, **kwargs)
    return result, report.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "topic_count, runs", [(1, 2), (3, 1), (1, 1)], ids=["one topic", "one run per arm", "one of each"],
)
def test_a_pilot_with_nothing_to_compute_still_writes_a_report_without_none_or_nan(
    topic_count, runs, repo, private_root, projects_root, tmp_path,
):
    """Adversarial where: the bootstrap, the between-topic spread or the
    within-topic spread cannot be computed and the report prints the Python
    value ('None degrees of freedom', 'nan') or raises while formatting."""
    world = World(private_root)
    result, text = run_to_report(
        world, repo, private_root, projects_root, tmp_path,
        probe_size=2, topic_count=topic_count, runs_per_arm=runs,
    )
    assert result.status == "complete"
    agg = result.aggregates
    if topic_count == 1:
        assert agg["interval"] is None and agg["between_sd"] is None
    if runs == 1:
        assert agg["within_sd"] is None and agg["batch"] is None
    assert re.findall(r"\b(None|nan|inf)\b", text) == []
    assert "not computable" in text.lower()


def test_a_compass_arm_with_no_tokens_has_no_share_and_the_report_says_so(repo, private_root, projects_root, tmp_path):
    """Adversarial where: every Compass build recorded zero tokens; the share
    divides by zero, or the failure of one statistic stops the report."""
    world = ScriptedWorld(private_root, usage=lambda t, arm, run: 0 if arm == "compass" else 500)
    result, text = run_to_report(world, repo, private_root, projects_root, tmp_path)
    assert result.status == "complete"
    assert result.aggregates["weighted_share"] is None and result.aggregates["batch"] is None
    assert re.findall(r"\b(None|nan|inf)\b", text) == []


def test_a_cheaper_compass_arm_reports_a_negative_share_and_a_batch_size(repo, private_root, projects_root, tmp_path):
    """Adversarial where: Compass cheaper than baseline gives a negative share;
    the batch plan raises or is dropped, or the sign is lost in the report."""
    world = ScriptedWorld(
        private_root, usage=lambda t, arm, run: (800 if arm == "compass" else 1000) + 37 * run + 13 * int(t[-1], 16),
    )
    result, text = run_to_report(world, repo, private_root, projects_root, tmp_path)
    agg = result.aggregates
    assert agg["weighted_share"] < 0
    assert agg["batch"] == stats.batch_plan(agg["weighted_share"], agg["within_sd"], agg["df"])
    assert agg["batch"]["point"] >= 1
    assert re.search(r"\| All \| -\d+\.\d%", text)


def test_a_failed_build_with_real_tokens_does_not_enter_the_share(repo, private_root, projects_root):
    """Adversarial where: a build that ended 'failed' (drive exit 1) after the
    smoke pair counts its half-finished tokens in the paired totals, shifting
    the share (the aggregate is over finished builds only)."""
    world = ScriptedWorld(private_root, usage=lambda t, arm, run: (1500 if arm == "compass" else 1000) + 11 * run)
    world.exits[7] = 1
    result = go(world, repo, private_root, projects_root)
    assert result.status == "complete"
    failed = next(e for e in log_events(private_root, "build-closed") if e["exit"] == 1)
    kept = {k: v for k, v in world.rows.items() if (k[0], k[2]) != (failed["topic"], failed["run"])}
    compass = sum(v[0] for k, v in kept.items() if k[1] == "compass")
    baseline = sum(v[0] for k, v in kept.items() if k[1] == "baseline")
    assert result.aggregates["weighted_share"] == pytest.approx((compass - baseline) / compass)


HOSTILE = [
    "Quartz|Ledger ``` --- [[SPEC-999]]",
    "Quartz\nLedger\n# heading",
    "uniçode Quartz ☃ Ledger",
    "Quartz \\ Ledger {{x}} $$",
]


@pytest.mark.parametrize("hostile", HOSTILE, ids=["markup", "newlines", "unicode", "escapes"])
def test_report_carries_no_topic_goal_brief_or_path_text_whatever_the_text_holds(
    hostile, repo, projects_root, tmp_path, monkeypatch,
):
    """Adversarial where: topic titles, goal items, briefs and a private folder
    name built from markup, newlines, unicode or words that also appear in the
    report template reach the report through any field."""
    import test_pilot

    goals = (f"Share {hostile} Builds", f"Topic Weighted {hostile} Raw", f"Mean {hostile} judge")
    monkeypatch.setattr(test_pilot, "SENTINEL_TEXT", hostile)
    monkeypatch.setattr(test_pilot, "GOAL_TEXTS", goals)
    monkeypatch.setattr(test_pilot, "SENTINEL_BRIEF", "Quartz")
    private_root = tmp_path / "Quartz Vault" / "overhead"
    world = World(private_root)
    result, text = run_to_report(world, repo, private_root, projects_root, tmp_path)
    assert result.status == "complete"
    assert "Quartz" not in text and "Ledger" not in text and "Vault" not in text
    for forbidden in (
        *goals, hostile, SENTINEL_SESSION, private_root.as_posix(), repo.as_posix(), projects_root.as_posix(),
    ):
        assert forbidden not in text
    assert chr(0x2013) not in text and chr(0x2014) not in text
