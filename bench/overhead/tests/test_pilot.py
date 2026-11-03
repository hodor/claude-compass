"""Tests for pilot.py: the topic probe, twelve builds, the run log and the report.

Interface the tests pin (pilot.py; stats.py is pinned in test_stats.py)
-----------------------------------------------------------------------
pilot.py
    drive_brief(items, brief_text) -> dict
        `items` is a frozen goal list [{"id", "text", "command"}, ...]. Returns
        {"context": brief_text, "items": [{"id", "name", "detail"}, ...]} in the
        order of `items`, with exactly those three keys per item and nothing
        else (the goal's command stays out). `detail` is the item text and `id`
        its id. `name` is two to four words, each a word of the item's text
        (compared ignoring case), unique ignoring case within the list, and
        chosen so that `human.SimulatedHuman.named_items(<name>)` returns that
        item alone: no name occurs as a whole-word phrase inside another name.
        ValueError for an item text of fewer than two words and for items for
        which no distinct names exist (identical texts).

    run_log_path(private_root) -> Path           under `private_root`
        JSON lines, appended, never rewritten. Events the tests read:
        {"event": "build-closed", "topic", "arm", "run", "exit", "seconds",
         "turns", "weighted", "raw"}   a build that ended with drive exit 0 or 1
        {"event": "build-refused", "topic", "arm", "run"}   drive exit 2
        {"event": "usage-limit", "resets_at"}   a halt (drive exit 3 or a session
                                                that ended usage-limit)
        {"event": "judged", "topic", "arm", "run", "counts"}
        `weighted` and `raw` are the list-price weighted and the raw token totals
        of the build rows (role "build") that the drive call appended to the
        records; `seconds` is the clock difference around the call and `turns`
        is read from the one JSON line drive prints to stdout.

    run_pilot(*, repo_root, private_root, projects_root, report_path=None,
              claude_cmd=None, parent_env=None, probe_size=10, topic_count=3,
              runs_per_arm=2, pick=topics.pick_topic, freeze=goals.write_goals,
              judge=judge.judge_project, drive=drive.main,
              new_project=sandbox.new_project, clock=time.monotonic) -> PilotResult
        Stages, in order, each skipped when the run log and the private files
        show it finished, so re-running the same command resumes:
        1. Probe: `probe_size` unseeded picks (seed None) and `probe_size` seeded
           picks with seeds 0 .. probe_size - 1. Then the form is
           topics.choose_form over the pool (more distinct classes, unseeded on a
           tie).
        2. `topic_count` more picks in that form (seeds probe_size .. when
           seeded), each frozen with `freeze(topic_id, ...)`; the probe picks are
           never frozen.
        3. Builds: every pilot topic `runs_per_arm` times in each arm, one at a
           time, each in a fresh project from `new_project(projects_root)`. The
           first topic's first run in each arm comes first (the smoke pair).
           `drive(argv)` gets the argv of drive.main: [project, "--arm", arm,
           "--opening-file", F, "--brief-file", F, "--human-folder", D,
           "--private-root", private_root]; it returns the exit code
           (0 human-done, 1 other end, 2 refused, 3 usage limit) and prints one
           JSON line {"end", "turns", "resets_at"} to stdout. The brief file is
           JSON from drive_brief over the frozen goals and brief text; the
           opening file holds the topic description and no goal item text. All
           three paths sit under `private_root`.
        4. Each closed build is judged: `judge(project, topic_id, ...)`.
        5. With `report_path`, a complete pilot writes the report there.
        PilotResult: .status "complete" | "usage-limit" | "blocked" | "refused";
        .resets_at; .form; .topics (the pilot topic ids in pool order);
        .probe {"seeded"|"unseeded": {"picks": n, "classes": distinct
        (kind, language) pairs}}; .closed (count of build-closed events in the log);
        .refused (count of build-refused events); .aggregates (None until complete) with
        "weighted_share", "raw_share", "topic_shares" {"weighted"|"raw": {topic
        id: share}}, "within_sd", "df" (stats.pooled_within_sd over the weighted
        pair shares), "batch" (stats.batch_plan of the weighted share),
        "mean_seconds", "mean_turns", "builds_per_window".
        A usage limit anywhere (a SessionError with status "usage-limit" from
        pick, freeze or judge, or drive exit 3) stops with status "usage-limit"
        and is resumed by the next run; a build that ended with exit 3 is run
        again on resume, a build already closed is not. Drive exit 2 logs a
        refusal, stops with "refused", and that build is never run again by later
        runs, which go on with the rest. A non-zero exit in the smoke pair stops
        with "blocked", and later runs return "blocked" without driving.
        records.Refused is raised, before any session, build or file write, when
        `private_root` sits inside a git work tree.
        The report is research-vault markdown (frontmatter with `type: research`)
        holding aggregates only: no topic title or description, goal or brief
        text, path, project folder name, session id or model output.
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

import human
import pilot
import records
import sandbox
import stats
import topics

SENTINEL_TEXT = "ZEBRAQUILL"
SENTINEL_BRIEF = "BRIEFSENTINEL"
SENTINEL_SESSION = "SESSIONSENTINEL-9f3"
SENTINEL_OUTPUT = "MODELOUTPUTSENTINEL"
RESETS_AT = 1790000000
MODEL = "claude-opus-5-5"
GOAL_TEXTS = (
    "Export the monthly report as a CSV file " + SENTINEL_TEXT,
    "Show a running total on the summary screen " + SENTINEL_TEXT,
    "Reject negative amounts with a clear message " + SENTINEL_TEXT,
)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


INIT_COUNTS = {"before": {"skills": 3, "agents": 1}, "after": {"skills": 40, "agents": 14}}


class World:
    """Fakes for pick, freeze, judge and drive that write the private files the
    real ones write, and remember every call."""

    def __init__(self, private_root, *, seeded_classes=10, unseeded_classes=3):
        self.private_root = private_root
        self.fill = {"seeded": seeded_classes, "unseeded": unseeded_classes}
        self.clock = Clock()
        self.exits = {}  # 1-based drive call number -> exit code
        self.limit = None  # (stage, nth call of that stage), raised once
        self.picks, self.pick_ok, self.freezes, self.freeze_ok = [], [], [], []
        self.judges, self.judge_ok, self.drives = [], [], []
        self.rows = {}  # (topic, arm, run) -> (weighted, raw)
        self.done_runs = {}
        self.counter = 0

    def _maybe_limit(self, stage, calls):
        if self.limit == (stage, len(calls)):
            self.limit = None
            raise topics.SessionError("usage-limit")

    def pick(self, *, seeded, seed=None, repo_root, private_root=None, claude_cmd=None, parent_env=None):
        form = "seeded" if seeded else "unseeded"
        self.picks.append((form, seed))
        self._maybe_limit("pick", self.picks)
        index = sum(1 for f, _ in self.pick_ok if f == form)
        slot = index % self.fill[form]
        self.counter += 1
        entry = {
            "id": f"t-{self.counter:08x}", "form": form, "seed": seed,
            "title": f"TITLE {SENTINEL_TEXT} {self.counter}",
            "description": f"DESCRIPTION {SENTINEL_TEXT} {self.counter}",
            "kind": topics.KINDS[slot % len(topics.KINDS)],
            "size": "small",
            "language": topics.LANGUAGES[(slot // len(topics.KINDS)) % len(topics.LANGUAGES)],
        }
        pool = topics.load_pool(private_root)
        topics.write_json(topics.topics_dir(private_root) / "pool.json", {"topics": [*pool, entry]})
        self.pick_ok.append((form, seed))
        return entry

    def freeze(self, topic_id, *, repo_root, private_root=None, claude_cmd=None, parent_env=None):
        self.freezes.append(topic_id)
        self._maybe_limit("freeze", self.freezes)
        items = [{"id": f"g{n}", "text": text, "command": f"python check{n}.py" if n == 1 else None}
                 for n, text in enumerate(GOAL_TEXTS, 1)]
        brief = f"{SENTINEL_BRIEF} for {topic_id}"
        base = topics.topics_dir(private_root)
        topics.write_json(base / "goals" / f"{topic_id}.json", {"topic_id": topic_id, "items": items})
        topics.write_json(base / "briefs" / f"{topic_id}.json", {"topic_id": topic_id, "brief": brief})
        self.freeze_ok.append(topic_id)
        return {"items": items, "brief": brief}

    def judge(self, project, topic_id, *, repo_root, private_root=None, claude_cmd=None, parent_env=None):
        self.judges.append((str(project), topic_id))
        self._maybe_limit("judge", self.judges)
        self.judge_ok.append((str(project), topic_id))
        return {"topic_id": topic_id, "counts": {"met": 2, "partly met": 1, "not met": 0},
                "scores": [{"id": "g1", "score": "met", "reason": SENTINEL_OUTPUT}]}

    def drive(self, argv):
        call = len(self.drives) + 1
        option = lambda name: argv[argv.index(name) + 1]  # noqa: E731
        brief = json.loads(open(option("--brief-file"), encoding="utf-8").read())
        topic_id = brief["context"].rsplit(" ", 1)[1]
        arm = option("--arm")
        self.drives.append({"project": argv[0], "arm": arm, "topic": topic_id, "argv": list(argv)})
        code = self.exits.get(call, 0)
        if code == 2:
            return 2
        key = (topic_id, arm)
        run = self.done_runs.get(key, 0) + 1
        index = int(topic_id[2:], 16) % 3 + 1
        compass = arm == "compass"
        usage = {
            "inputTokens": 1000 * index + (400 * index if compass else 0) + 30 * run,
            "outputTokens": 0,
            "cacheReadInputTokens": 8000 * index + (6000 * index if compass else 0) + 50 * run,
            "cacheCreationInputTokens": 0,
        }
        row = records.record_session(
            [{"type": "result", "modelUsage": {MODEL: usage}}], role="build",
            outcome={0: "done", 1: "failed", 3: "usage-limit"}[code], arm=arm,
            private_root=option("--private-root"),
        )
        self.clock.now += 120 if compass else 80
        end = {0: "human-done", 1: "failed", 3: "usage-limit"}[code]
        print(json.dumps({
            "end": end, "turns": 30 if compass else 10,
            "resets_at": RESETS_AT if code == 3 else None,
            "session_id": SENTINEL_SESSION, "text": SENTINEL_OUTPUT,
            "reason": "" if code == 0 else "the session ended", "init_counts": INIT_COUNTS if compass else None,
        }))
        if code != 3:
            self.done_runs[key] = run
            raw = sum(row["models"][MODEL].values())
            self.rows[(topic_id, arm, run)] = (row["weighted"], raw)
        return code


def go(world, repo, private_root, projects_root, **kwargs):
    return pilot.run_pilot(
        repo_root=repo, private_root=private_root, projects_root=projects_root,
        pick=world.pick, freeze=world.freeze, judge=world.judge, drive=world.drive,
        clock=world.clock, **kwargs,
    )


def log_events(private_root, name=None):
    path = pilot.run_log_path(private_root)
    if not path.exists():
        return []
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [e for e in events if name is None or e["event"] == name]


def ok_drives(world):
    return [d for i, d in enumerate(world.drives, 1) if world.exits.get(i, 0) in (0, 1)]


ITEMS_OVERLAP = [
    {"id": "g1", "text": "Export the monthly report as a CSV file", "command": "python x.py"},
    {"id": "g2", "text": "Export the monthly report as a PDF file", "command": None},
    {"id": "g3", "text": "Reject negative amounts with a clear error message", "command": None},
    {"id": "g4", "text": "Export the monthly report", "command": None},
]
ITEMS_PUNCTUATION = [
    {"id": "g1", "text": "The test target runs (with `-v`) and exits with code 0.", "command": "make test"},
    {"id": "g2", "text": "README explains install steps, usage and limits.", "command": None},
]


@pytest.mark.parametrize("items", [ITEMS_OVERLAP, ITEMS_PUNCTUATION], ids=["overlapping", "punctuation"])
def test_drive_brief_has_the_drive_shape_and_names_reveal_only_their_item(items, repo, private_root, tmp_path):
    """Adversarial where: items sharing most words get names that are phrases of
    each other, so one question reveals two hidden goals; a name with edge
    punctuation never matches the human's whole-word search; a goal's command
    or a stray key leaks into the brief."""
    brief = pilot.drive_brief(items, "FREE TEXT")
    assert set(brief) == {"context", "items"}
    assert brief["context"] == "FREE TEXT"
    assert json.loads(json.dumps(brief)) == brief
    assert [i["id"] for i in brief["items"]] == [i["id"] for i in items]
    assert [i["detail"] for i in brief["items"]] == [i["text"] for i in items]
    assert all(set(i) == {"id", "name", "detail"} for i in brief["items"])
    assert not any(i["command"] and i["command"] in json.dumps(brief) for i in items)

    names = [i["name"] for i in brief["items"]]
    assert len({n.lower() for n in names}) == len(names)
    who = human.SimulatedHuman(
        brief, folder=tmp_path / "human", repo_root=repo, arm="baseline",
        state_file=tmp_path / "state" / "human.json", private_root=private_root,
    )
    for item, name in zip(brief["items"], names):
        assert 2 <= len(name.split()) <= 4, name
        words = set(re.findall(r"\w+", next(i["text"] for i in items if i["id"] == item["id"]).lower()))
        assert set(re.findall(r"\w+", name.lower())) <= words, name
        assert [n["id"] for n in who.named_items(name)] == [item["id"]], name
        assert [n["id"] for n in who.named_items(f"Can you tell me about {name.upper()}?")] == [item["id"]]


@pytest.mark.parametrize(
    "items",
    [
        [{"id": "g1", "text": "Dockerfile", "command": None}],
        [{"id": "g1", "text": "Export report to CSV", "command": None},
         {"id": "g2", "text": "Export report to CSV", "command": None}],
    ],
    ids=["one-word text", "identical texts"],
)
def test_drive_brief_refuses_items_that_cannot_be_named(items):
    """Adversarial where: a one-word item given a padded or empty name, or two
    identical items given the same name, so the human reveals both at once."""
    with pytest.raises(ValueError):
        pilot.drive_brief(items, "text")


@pytest.mark.parametrize(
    "seeded_classes, unseeded_classes, form",
    [(10, 3, "seeded"), (3, 10, "unseeded"), (4, 4, "unseeded")],
    ids=["seeded fills more", "unseeded fills more", "tie goes to unseeded"],
)
def test_probe_chooses_the_form_and_only_pilot_topics_are_frozen(
    seeded_classes, unseeded_classes, form, repo, private_root, projects_root,
):
    """Adversarial where: the tie broken toward seeded, the probe picks frozen
    and built, or seeds reused or skipped (the probe uses seeds 0 to 9, the
    pilot topics the next three) so a re-run changes the pool."""
    world = World(private_root, seeded_classes=seeded_classes, unseeded_classes=unseeded_classes)
    result = go(world, repo, private_root, projects_root)
    assert result.status == "complete"
    assert result.form == form
    assert result.probe == {
        "seeded": {"picks": 10, "classes": seeded_classes},
        "unseeded": {"picks": 10, "classes": unseeded_classes},
    }
    probe, pilot_picks = world.picks[:20], world.picks[20:]
    assert sorted(s for f, s in probe if f == "seeded") == list(range(10))
    assert [s for f, s in probe if f == "unseeded"] == [None] * 10
    expected_seeds = [10, 11, 12] if form == "seeded" else [None] * 3
    assert pilot_picks == [(form, s) for s in expected_seeds]
    pool_ids = [e["id"] for e in topics.load_pool(private_root)]
    assert result.topics == pool_ids[20:] and len(result.topics) == 3
    assert world.freezes == result.topics
    assert {d["topic"] for d in world.drives} == set(result.topics)


def test_builds_run_in_fresh_projects_with_private_files_and_every_build_is_judged(
    repo, private_root, projects_root,
):
    """Adversarial where: the opening message carrying the hidden goals, brief
    or goal files written inside the repository, one project shared by two
    builds, the smoke pair not first, a build left unjudged."""
    world = World(private_root)
    result = go(world, repo, private_root, projects_root)
    first = result.topics[0]
    assert {(d["topic"], d["arm"]) for d in world.drives[:2]} == {(first, "compass"), (first, "baseline")}
    assert len(world.drives) == 12
    for topic_id in result.topics:
        for arm in ("compass", "baseline"):
            assert sum(1 for d in world.drives if (d["topic"], d["arm"]) == (topic_id, arm)) == 2
    projects = [d["project"] for d in world.drives]
    assert len(set(projects)) == 12
    assert {str(p) for p in sandbox.list_projects(projects_root)} == set(projects)

    for d in world.drives:
        argv, base = d["argv"], private_root.resolve()
        option = lambda name: argv[argv.index(name) + 1]  # noqa: E731
        assert option("--private-root") == str(private_root)
        for flag in ("--opening-file", "--brief-file", "--human-folder"):
            assert base in Path(option(flag)).resolve().parents, flag
        goals = json.loads((topics.topics_dir(private_root) / "goals" / f"{d['topic']}.json").read_text("utf-8"))
        brief_text = json.loads((topics.topics_dir(private_root) / "briefs" / f"{d['topic']}.json").read_text("utf-8"))
        sent = json.loads(open(option("--brief-file"), encoding="utf-8").read())
        assert sent == pilot.drive_brief(goals["items"], brief_text["brief"])
        opening = open(option("--opening-file"), encoding="utf-8").read()
        entry = next(e for e in topics.load_pool(private_root) if e["id"] == d["topic"])
        assert entry["description"] in opening
        assert not any(text in opening for text in GOAL_TEXTS)
        assert SENTINEL_BRIEF not in opening

    assert sorted(world.judge_ok) == sorted((d["project"], d["topic"]) for d in world.drives)
    assert len(log_events(private_root, "build-closed")) == 12 == result.closed
    assert len(log_events(private_root, "judged")) == 12
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True)
    assert status.stdout.strip() == ""


@pytest.mark.parametrize("blocked_call", [1, 2])
def test_a_failed_smoke_build_blocks_the_pilot_for_every_later_run(blocked_call, repo, private_root, projects_root):
    """Adversarial where: the pilot carrying on to ten more builds after the
    smoke pair hit a headless blocker, or a re-run forgetting the block and
    driving again."""
    world = World(private_root)
    world.exits[blocked_call] = 1
    result = go(world, repo, private_root, projects_root)
    assert result.status == "blocked"
    assert len(world.drives) <= 2
    calls = len(world.drives)
    again = go(world, repo, private_root, projects_root)
    assert again.status == "blocked"
    assert len(world.drives) == calls


@pytest.mark.parametrize(
    "stage, nth",
    [("drive", 5), ("pick", 8), ("freeze", 2), ("judge", 3)],
    ids=["during a build", "during the probe", "while freezing goals", "while judging"],
)
def test_a_usage_limit_halts_and_the_same_command_resumes_without_repeating_finished_work(
    stage, nth, repo, private_root, projects_root,
):
    """Adversarial where: a resume that re-picks, re-freezes, re-builds or
    re-judges finished work (double spend of the subscription), drops the
    halted step, rewrites the log instead of appending, or loses the resetsAt
    of the halt."""
    world = World(private_root)
    if stage == "drive":
        world.exits[nth] = 3
    else:
        world.limit = (stage, nth)
    first = go(world, repo, private_root, projects_root)
    assert first.status == "usage-limit"
    if stage == "drive":
        assert first.resets_at == RESETS_AT
        assert log_events(private_root, "usage-limit")[-1]["resets_at"] == RESETS_AT
        assert len(log_events(private_root, "build-closed")) == nth - 1
    text_after_halt = pilot.run_log_path(private_root).read_text(encoding="utf-8")

    second = go(world, repo, private_root, projects_root)
    assert second.status == "complete"
    assert pilot.run_log_path(private_root).read_text(encoding="utf-8").startswith(text_after_halt)
    assert len(world.pick_ok) == 23
    assert sorted(seed for form, seed in world.pick_ok if form == "seeded") == list(range(13))
    assert len(world.freeze_ok) == 3 and len(set(world.freeze_ok)) == 3
    assert len(ok_drives(world)) == 12 and len({d["project"] for d in ok_drives(world)}) == 12
    assert len(world.drives) == (13 if stage == "drive" else 12)
    assert len(world.judge_ok) == 12 and len(set(world.judge_ok)) == 12
    assert len(log_events(private_root, "build-closed")) == 12


def test_a_refused_build_is_never_retried_and_the_rest_still_run(repo, private_root, projects_root):
    """Adversarial where: retrying a refused build (it is refused again, or
    worse runs after the plugin tree changed), or the refusal ending the
    whole pilot for good."""
    world = World(private_root)
    world.exits[6] = 2
    first = go(world, repo, private_root, projects_root)
    assert first.status == "refused"
    assert len(log_events(private_root, "build-refused")) == 1
    refused = world.drives[5]
    calls_before = len(world.drives)

    second = go(world, repo, private_root, projects_root)
    assert second.status == "complete"
    assert len(world.drives) == 12
    assert len(world.drives) - calls_before == 6
    assert len(ok_drives(world)) == 11
    assert second.closed == 11 and second.refused == 1
    assert world.drives.count(refused) == 1


def test_a_private_root_inside_a_git_work_tree_is_refused_before_anything_happens(repo, projects_root):
    """Adversarial where: pool, goals, briefs and the run log written into a
    work tree where one `git add` publishes the topics and the hidden goals."""
    inside = repo / "private"
    world = World(inside)
    with pytest.raises(records.Refused):
        go(world, repo, inside, projects_root)
    assert world.picks == [] and world.drives == [] and world.judges == []
    assert not [p for p in inside.rglob("*") if p.is_file()]


def test_aggregates_are_ratios_of_sums_over_the_record_rows_of_the_builds(repo, private_root, projects_root):
    """Adversarial where: the share built from halted or failed rows, from the
    mean of per-topic ratios, or with raw and weighted totals swapped (cache
    reads weigh 0.05 here, so the two shares differ); a halted build's row is
    still in the records and must not count."""
    world = World(private_root)
    world.exits[7] = 3
    go(world, repo, private_root, projects_root)
    result = go(world, repo, private_root, projects_root)
    assert result.status == "complete"

    def totals(column, arm, topic_id=None):
        return sum(v[column] for (t, a, _), v in world.rows.items() if a == arm and topic_id in (None, t))

    agg = result.aggregates
    for column, name in ((0, "weighted"), (1, "raw")):
        expected = (totals(column, "compass") - totals(column, "baseline")) / totals(column, "compass")
        assert agg[f"{name}_share"] == pytest.approx(expected, rel=1e-9)
        for topic_id in result.topics:
            c, b = totals(column, "compass", topic_id), totals(column, "baseline", topic_id)
            assert agg["topic_shares"][name][topic_id] == pytest.approx((c - b) / c, rel=1e-9)
    assert agg["weighted_share"] != pytest.approx(agg["raw_share"], rel=1e-3)

    by_topic = {
        t: {arm: [world.rows[(t, arm, run)][0] for run in (1, 2)] for arm in ("compass", "baseline")}
        for t in result.topics
    }
    sd, df = stats.pooled_within_sd(by_topic)
    assert agg["df"] == df == 3
    assert agg["within_sd"] == pytest.approx(sd, rel=1e-9)
    assert agg["batch"] == stats.batch_plan(agg["weighted_share"], sd, df)
    assert agg["mean_seconds"] == pytest.approx(100.0)
    assert agg["mean_turns"] == pytest.approx(20.0)
    assert agg["builds_per_window"] == stats.builds_per_window([120, 80] * 6)


def test_the_report_holds_aggregates_and_nothing_private(repo, private_root, projects_root, tmp_path):
    """Adversarial where: the report copying a topic title or description, goal
    or brief text, a project folder name, a path, a session id or model output
    from the run (all present in the fakes), or an em or en dash."""
    report = tmp_path / "out" / "RESEARCH-whole-overhead-pilot.md"
    world = World(private_root)
    result = go(world, repo, private_root, projects_root, report_path=report)
    text = report.read_text(encoding="utf-8")
    assert text.startswith("---") and re.search(r"^type: research$", text, re.MULTILINE)
    for batch in result.aggregates["batch"].values():
        assert str(batch) in text
    forbidden = [
        SENTINEL_TEXT, SENTINEL_BRIEF, SENTINEL_SESSION, SENTINEL_OUTPUT,
        str(tmp_path), str(private_root), str(repo), str(projects_root),
        *[d["project"] for d in world.drives],
        *[p.name for p in sandbox.list_projects(projects_root)],
        chr(0x2013), chr(0x2014),
    ]
    assert [f for f in forbidden if f in text] == []
    assert not re.search(r"[A-Za-z]:[\\/]", text)


class EmptyJudgeWorld(World):
    """A world whose judge scores chosen judge calls as meeting no goal item."""

    def __init__(self, private_root, empty_calls):
        super().__init__(private_root)
        self.empty_calls = set(empty_calls)

    def judge(self, project, topic_id, **kwargs):
        verdict = super().judge(project, topic_id, **kwargs)
        if len(self.judges) in self.empty_calls:
            verdict = {**verdict, "counts": {"met": 0, "partly met": 0, "not met": 3}}
        return verdict


@pytest.mark.parametrize("empty_call", [1, 2])
def test_a_smoke_build_that_meets_no_goal_item_blocks_the_pilot(empty_call, repo, private_root, projects_root):
    """Adversarial where: a smoke build exits 0 but leaves nothing the judge can
    credit (a headless build whose writes were all refused), and the pilot spends
    ten more builds on the same failure, or a re-run forgets the block."""
    world = EmptyJudgeWorld(private_root, [empty_call])

    result = go(world, repo, private_root, projects_root)

    assert result.status == "blocked"
    assert len(world.drives) == empty_call
    assert log_events(private_root, "blocked")[-1]["reason"]
    again = go(world, repo, private_root, projects_root)
    assert again.status == "blocked"
    assert len(world.drives) == empty_call


def test_a_later_build_that_meets_no_goal_item_does_not_block(repo, private_root, projects_root):
    """Adversarial where: the empty-build guard fires on every build, halting a
    pilot whose smoke pair worked because one later build genuinely failed."""
    world = EmptyJudgeWorld(private_root, [5])

    result = go(world, repo, private_root, projects_root)

    assert result.status == "complete"
    assert len(world.drives) == 12


def test_a_closed_build_logs_how_it_ended_and_what_its_session_loaded(repo, private_root, projects_root):
    """Adversarial where: the drive's end, its reason and the session's skill
    and agent counts are printed but dropped, so a failed build cannot be
    diagnosed and a double plugin load cannot be seen from the run log."""
    world = World(private_root)
    world.exits[3] = 1

    go(world, repo, private_root, projects_root)

    closed = log_events(private_root, "build-closed")
    compass = [e for e in closed if e["arm"] == "compass"]
    assert compass and all(e["init_counts"] == INIT_COUNTS for e in compass)
    failed = [e for e in closed if e["exit"] == 1]
    assert len(failed) == 1
    assert failed[0]["end"] == "failed" and failed[0]["reason"] == "the session ended"
    assert all(e["end"] == "human-done" for e in closed if e["exit"] == 0)
