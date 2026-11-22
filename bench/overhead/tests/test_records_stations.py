"""Tests for the station counts a build's record row carries.

`records.station_counts(project_dir)` reads `<project_dir>/.compass/meta/station-log.jsonl`
and returns {"<station>|<model>": {"spawns", "bugs", "fails", "unparsed"}} with a
`helpful`/`neutral`/`harmful` count added under a fix-cycle entry. `record_session`
takes `project_dir=` and writes the result into `row["stations"]` for a build whose arm
is not "baseline".

Adversarial themes: the record may hold allowlisted integers only, so any text field
of a log row, any name outside a safe pattern and any malformed count must never reach
it; a missing or damaged log is zero counts, never an error; one bad line or one bad
field must not discard its neighbours.
"""

import json
import random
import re

import pytest

import fake_claude
import records

M1 = "claude-zeta-3-7"
M2 = "claude-yodel-4-1[1m]"
SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
CORE = ("spawns", "bugs", "fails", "unparsed")
SAFE_KEY = re.compile(r"[A-Za-z0-9._\[\]-]+\|[A-Za-z0-9._\[\]-]+")
SECRETS = ["harpsichord-tuner", "D:/data/secret-project", "/srv/secret-proj", "sk-ant-0123456789"]


def log_path(project):
    return project / ".compass" / "meta" / "station-log.jsonl"


def write_log(project, rows, raw_lines=()):
    path = log_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(item).encode("utf-8") for item in rows] + list(raw_lines)
    path.write_bytes(b"\n".join(lines) + b"\n")
    return path


def row(station, model, **fields):
    base = {"ts": "2026-11-20T10:00:00Z", "agent_type": station, "station": station, "task": "TASK-349",
            "model": model, "model_source": "frontmatter", "result": "ok"}
    base.update(fields)
    return base


def entry(**counts):
    return {**dict.fromkeys(CORE, 0), **counts}


def essential(counts):
    """Counts with zero-valued verdict keys dropped, so an entry may omit or carry them."""
    return {key: {name: value for name, value in item.items() if name in CORE or value != 0}
            for key, item in counts.items()}


def assert_only_ints(counts):
    for key, item in counts.items():
        for name, value in item.items():
            assert type(value) is int and value >= 0, (key, name, value)


def build_record(project, private_root, events, **overrides):
    arguments = {"role": "build", "outcome": "done", "arm": "compass", "plugin_sha": SHA,
                 "private_root": private_root, "project_dir": project}
    arguments.update(overrides)
    return records.record_session(events, **arguments)


def disk_text(private_root):
    folder = private_root / "records"
    return "".join(path.read_text(encoding="utf-8") for path in folder.glob("*.jsonl")) if folder.exists() else ""


CANNED = [
    row("tester-pre", M1), row("tester-pre", M1),
    row("tester-post", M1, bugs=2), row("tester-post", M1, bugs=3), row("tester-post", M2, bugs=0),
    row("validator", M2, fails=4, result="fail"), row("validator", M2, fails=0),
    row("builder", M1), row("debug", M2),
    row("fix-cycle", M1, cycle=1, verdict="helpful"), row("fix-cycle", M1, cycle=2, verdict="helpful"),
    row("fix-cycle", M1, cycle=3, verdict="harmful"),
    row("general-purpose", M2, verdict="unparsed"), row("tester", M1, verdict="unparsed"),
]

CANNED_EXPECTED = {
    f"tester-pre|{M1}": entry(spawns=2),
    f"tester-post|{M1}": entry(spawns=2, bugs=5),
    f"tester-post|{M2}": entry(spawns=1),
    f"validator|{M2}": entry(spawns=2, fails=4),
    f"builder|{M1}": entry(spawns=1),
    f"debug|{M2}": entry(spawns=1),
    f"fix-cycle|{M1}": entry(spawns=3, helpful=2, harmful=1),
    f"general-purpose|{M2}": entry(spawns=1, unparsed=1),
    f"tester|{M1}": entry(spawns=1, unparsed=1),
}


@pytest.mark.parametrize("order", ["as-written", "reversed", "shuffled"])
def test_a_canned_log_gives_the_expected_counts_per_station_and_model(project, order):
    """Adversarial where: counts keyed by station alone merge two models, a last-row-wins
    update loses earlier rows, and a fix-cycle row counted under a plain station name
    loses its verdict split; none of these may depend on the order the rows were logged."""
    rows = list(CANNED)
    if order == "reversed":
        rows.reverse()
    elif order == "shuffled":
        random.Random(11).shuffle(rows)
    write_log(project, rows)

    counts = records.station_counts(project)

    assert essential(counts) == essential(CANNED_EXPECTED)
    assert_only_ints(counts)


def _no_log(project):
    return project


def _absent_folder(project):
    return project.parent / "no-such-project"


def _empty_file(project):
    write_log(project, []).write_bytes(b"")
    return project


def _blank_lines(project):
    write_log(project, []).write_bytes(b"\n\n  \n")
    return project


def _garbage_only(project):
    write_log(project, [], raw_lines=[b"not json", b"{"])
    return project


@pytest.mark.parametrize("prepare", [_no_log, _absent_folder, _empty_file, _blank_lines, _garbage_only],
                         ids=lambda function: function.__name__.strip("_"))
def test_a_missing_or_empty_log_gives_zero_counts_not_an_error(prepare, project):
    """Adversarial where: a reader that opens the log without checking it exists raises
    at the close of a build that never spawned a station, and a build with no counts
    would then lose its whole record row."""
    target = prepare(project)

    assert records.station_counts(target) == {}


def test_a_damaged_line_costs_only_itself(project):
    """Adversarial where: a log with truncated, binary or non-object lines among good
    ones (a crash mid-write is the usual cause) must keep the good rows; a parse loop
    that aborts at the first bad line, or lets invalid UTF-8 raise, zeroes the lot."""
    good = [row("builder", M1), row("tester-post", M1, bugs=2)]
    write_log(project, good[:1], raw_lines=[
        b"", b"{not json", b"[1, 2]", b"7", b"null", b'"a string"', b"\xff\xfe\x00 binary",
        json.dumps(good[1]).encode("utf-8"), b'{"station": "builder", "model": "claude-zeta-3-7", "tas',
    ])

    counts = records.station_counts(project)

    assert essential(counts) == essential({
        f"builder|{M1}": entry(spawns=1), f"tester-post|{M1}": entry(spawns=1, bugs=2)})


MALFORMED = [
    ("negative", -5), ("string", "7"), ("boolean", True), ("null", None), ("list", [3]), ("object", {"a": 3}),
]


@pytest.mark.parametrize("label,bad", MALFORMED, ids=[item[0] for item in MALFORMED])
def test_a_malformed_count_zeroes_its_own_field_only(label, bad, project):
    """Adversarial where: validation per row drops the good neighbour rows (or raises),
    and validation that lets `True` through counts a boolean as one bug or one failure."""
    write_log(project, [
        row("tester-post", M1, bugs=3), row("tester-post", M1, bugs=bad),
        row("validator", M1, fails=bad), row("validator", M1, fails=2),
    ])

    counts = records.station_counts(project)

    assert essential(counts) == essential({
        f"tester-post|{M1}": entry(spawns=2, bugs=3), f"validator|{M1}": entry(spawns=2, fails=2)})
    assert_only_ints(counts)


UNSAFE_NAMES = [
    ("space", "claude zeta"), ("slash", "claude/zeta"), ("backslash", "claude\\zeta"),
    ("windows-path", "D:\\data\\secret-project"), ("pipe", "claude-zeta|evil"), ("newline", "claude\nzeta"),
    ("traversal", "claude-zeta/../../secret"), ("non-ascii", "claude-z\u00e9ta"), ("empty", ""),
    ("null", None), ("number", 42), ("list", ["claude-zeta"]),
    ("secret-text", "harpsichord tuner at /srv/secret-proj"),
]


@pytest.mark.parametrize("field", ["model", "station"])
@pytest.mark.parametrize("label,unsafe", UNSAFE_NAMES, ids=[item[0] for item in UNSAFE_NAMES])
def test_a_station_or_model_outside_the_safe_pattern_never_reaches_the_counts(field, label, unsafe, project):
    """Adversarial where: the key is built from log text, so a name carrying a path,
    free text or the `|` separator would land in the record (or split into a wrong
    station and model); it must be dropped or bucketed, with the safe row untouched."""
    write_log(project, [row("builder", M1), {**row("builder", M1), field: unsafe}])

    counts = records.station_counts(project)

    assert counts[f"builder|{M1}"]["spawns"] == 1
    assert all(SAFE_KEY.fullmatch(key) and key.count("|") == 1 for key in counts), sorted(counts)
    text = json.dumps(counts)
    assert not [secret for secret in SECRETS + ["evil", "tuner"] if secret in text]
    assert sum(item["spawns"] for item in counts.values()) <= 2
    assert_only_ints(counts)


def test_unexpected_text_fields_and_verdicts_never_reach_the_written_record(project, private_root):
    """Metamorphic: adding any extra text key (top level or nested) and free text in
    `task`, `result`, `ts`, `model_source` and `agent_type` to every log row must not
    change the stations in the row, and none of that text may appear in the row or on disk.

    Adversarial where: a row copied wholesale into the record, or a fix-cycle verdict
    used as a key, leaks whatever text the log carries (a task title, a path, a token)."""
    events = fake_claude.events_for("subagent", project)
    plain = [row(source["station"], source["model"],
                 **{name: value for name, value in source.items() if name in ("bugs", "fails", "verdict", "cycle")})
             for source in CANNED]
    write_log(project, plain)
    baseline_row = build_record(project, private_root / "plain", events)
    noisy = []
    for number, source in enumerate(plain):
        secret = SECRETS[number % len(SECRETS)]
        noisy.append({**source, "task": secret, "result": secret, "ts": secret, "model_source": secret,
                      "agent_type": secret, "note": secret, f"zz_{number}": [secret, {"nested": secret}]})
    noisy.append(row("fix-cycle", M1, cycle=4, verdict=SECRETS[0]))
    write_log(project, noisy)

    built = build_record(project, private_root / "noisy", events)

    expected = essential(baseline_row["stations"])
    expected[f"fix-cycle|{M1}"]["spawns"] += 1
    assert essential(built["stations"]) == expected
    text = json.dumps(built) + disk_text(private_root / "noisy")
    assert not [secret for secret in SECRETS if secret in text]


def test_a_baseline_arm_build_has_empty_stations_even_beside_a_log(project, private_root):
    """Adversarial where: a baseline-arm build is the control with no stations; a
    project folder that happens to hold a station log must not give it counts, and a
    compass build with no project folder or no log must not fail."""
    events = fake_claude.events_for("subagent", project)
    write_log(project, CANNED)
    project_without_log = project.parent / "other-proj"
    project_without_log.mkdir()

    baseline = build_record(project, private_root / "baseline", events, arm="baseline")
    compass_without_folder = build_record(None, private_root / "no-folder", events)
    compass_without_log = build_record(project_without_log, private_root / "no-log", events)

    assert baseline["stations"] == {}
    assert compass_without_folder["stations"] == {}
    assert compass_without_log["stations"] == {}


def test_a_compass_build_row_carries_the_counts_in_its_record_and_changes_nothing_else(project, private_root):
    """Adversarial where: stations are the one new allowlisted field; a build that
    writes them must put them in the row that reaches disk (not only the returned
    dict) and must leave every other field exactly as it was without them."""
    events = fake_claude.events_for("subagent", project)
    write_log(project, CANNED)

    with_log = build_record(project, private_root / "with", events)
    without = build_record(None, private_root / "without", events)

    assert essential(with_log["stations"]) == essential(CANNED_EXPECTED)
    on_disk = [json.loads(line) for line in disk_text(private_root / "with").splitlines()]
    assert on_disk == [with_log]
    drop = {"recorded_at", "stations"}
    assert {k: v for k, v in with_log.items() if k not in drop} == {k: v for k, v in without.items() if k not in drop}
