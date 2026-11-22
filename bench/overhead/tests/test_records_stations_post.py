"""Probes for the station counts that only the implementation reveals.

The interface is described at the top of test_records_stations.py.

Adversarial themes: the log read must never raise whatever the file holds (the
build's record is written after the session, so a raise loses the whole session's
spend), the driver must hand the project folder to the record on every end path
and arm, a model name the log carries is kept or bucketed by the same rule the
rest of the record uses, and the row keeps its exact key set.
"""

import json
import time

import pytest

import human
import records
from test_drive import ScriptedHuman, build, read_records
from test_records_stations import M1, M2, SECRETS, disk_text, entry, essential, row, write_log

BASE_KEYS = {
    "recorded_at", "machine", "role", "outcome", "arm", "variant", "build_model", "plugin_sha",
    "claude_code_version", "results", "duration_ms", "models", "weighted", "unpriced_models",
}
LOG_ROWS = [row("tester-post", M1, bugs=2), row("validator", M2, fails=1), row("fix-cycle", M1, verdict="harmful")]
LOG_COUNTS = {
    f"tester-post|{M1}": entry(spawns=1, bugs=2),
    f"validator|{M2}": entry(spawns=1, fails=1),
    f"fix-cycle|{M1}": entry(spawns=1, harmful=1),
}
LOG_FILE = ".compass/meta/station-log.jsonl"


def log_text(rows):
    return "".join(json.dumps(item) + "\n" for item in rows)


def push_remote(repo, tmp_path, git):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "-q", "--bare")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "HEAD")


@pytest.mark.parametrize("arm", ["compass", "compass-minus-hooks", "baseline"])
@pytest.mark.parametrize("end", ["done", "limit", "crash"])
def test_every_arm_and_end_path_records_the_stations_the_session_logged(
    arm, end, project, repo, private_root, tmp_path, git
):
    """Adversarial where: drive_build records on three end paths (human done, usage
    limit, crash) and in a variant arm; a path that omits `project_dir` leaves the
    stations empty, a baseline-arm build must stay empty beside a log, and the row's
    key set must grow by exactly `stations`."""
    end_turn = {"done": {"text": "T2"}, "limit": {"limit": "rejected"}, "crash": {"crash": True}}[end]
    logged = {**end_turn, "write": {LOG_FILE: log_text(LOG_ROWS)}}
    if arm == "baseline":
        spec = {"turns": [logged]}
    else:
        push_remote(repo, tmp_path, git)
        setup = {"text": "setup finished", "write": {".compass/meta/plugin.yaml": "source: x\ncommit: 0\n"}}
        spec = {"turns": [setup, logged]}
    who = ScriptedHuman([human.Reply(text="done", done=True)])

    build(project, repo, private_root, tmp_path, spec, who, arm=arm)

    built = [item for item in read_records(private_root) if item["role"] == "build"]
    assert len(built) == 1
    assert set(built[0]) == BASE_KEYS | {"stations"}
    expected = {} if arm == "baseline" else essential(LOG_COUNTS)
    assert essential(built[0]["stations"]) == expected


@pytest.mark.parametrize("depth", [1000, 200000])
def test_a_deeply_nested_log_line_costs_only_itself(project, private_root, depth):
    """Adversarial where: json.loads raises RecursionError (not ValueError) on a deeply
    nested line; a read that only catches ValueError lets that escape from record_session,
    so one corrupt line loses the whole session's record. The neighbours still count."""
    path = write_log(project, [row("builder", M1)], raw_lines=[b"[" * depth, b'{"a":' * depth])
    path.write_bytes(path.read_bytes() + (json.dumps(row("builder", M1)) + "\n").encode("utf-8"))

    counts = records.station_counts(project)
    written = records.record_session([], role="build", outcome="done", arm="compass",
                                     private_root=private_root, project_dir=project)

    assert counts == {f"builder|{M1}": entry(spawns=2)}
    assert written["stations"] == counts


@pytest.mark.parametrize("model", ["claude-opus-4-5-20251101", "claude-sonnet-4-5[1m]", "claude-opus-4.1"])
def test_dated_and_suffixed_claude_model_ids_keep_their_name_as_the_key(model, project):
    """Adversarial where: a `[1m]` context suffix or an eight-digit date must pass the
    safe-name check untouched; stripping or bucketing them would merge distinct models."""
    write_log(project, [row("builder", model), row("builder", model)])

    assert records.station_counts(project) == {f"builder|{model}": entry(spawns=2)}


@pytest.mark.parametrize("model", ["harpsichord-tuner", "acme-billing", "..", "[[]]"])
def test_a_model_that_is_not_a_claude_id_is_bucketed_like_the_rest_of_the_record(model, project, private_root):
    """Adversarial where: records.py keys `models` through _MODEL_ID (claude-* only) and
    buckets anything else as unknown-model; the stations key must follow the same rule,
    or a project-chosen name made of letters and hyphens is written to the record."""
    write_log(project, [row("builder", model)])

    written = records.record_session([], role="build", outcome="done", arm="compass",
                                     private_root=private_root, project_dir=project)

    assert list(written["stations"]) == ["builder|unknown-model"]
    assert model not in disk_text(private_root)


def test_the_log_read_counts_a_big_log_with_mixed_line_endings_exactly(project):
    """Adversarial where: a read that drops a final line with no newline or a CRLF-ended
    line undercounts a build; 30000 rows (some CRLF, the last unterminated) must count
    exactly and quickly."""
    path = write_log(project, [row("tester-post", M1, bugs=1) for _ in range(29998)])
    line = json.dumps(row("tester-post", M1, bugs=1)).encode("utf-8")
    with open(path, "ab") as handle:
        handle.write(line + b"\r\n" + line)

    started = time.monotonic()
    counts = records.station_counts(project)

    assert counts == {f"tester-post|{M1}": entry(spawns=30000, bugs=30000)}
    assert time.monotonic() - started < 10


def test_an_invalid_byte_sequence_inside_one_line_costs_only_that_line(project):
    """Adversarial where: the log is decoded as a whole; one line with invalid UTF-8
    must not raise nor discard the lines around it."""
    bad = b'{"station": "builder", "model": "' + M1.encode("utf-8") + b'", "bugs": 9, "x": "\xff\xfe"}'
    write_log(project, [row("builder", M1)], raw_lines=[bad, json.dumps(row("builder", M1)).encode("utf-8")])

    counts = records.station_counts(project)

    assert counts[f"builder|{M1}"]["spawns"] >= 2
    assert counts[f"builder|{M1}"]["bugs"] in (0, 9)


@pytest.mark.parametrize("shape", ["log-is-a-folder", "meta-is-a-file", "compass-is-a-file", "str-path"])
def test_an_unreadable_log_location_gives_empty_stations_not_an_error(shape, project, private_root):
    """Adversarial where: the log path exists but cannot be read as a file (a folder, an
    ancestor that is a file, or the project folder handed over as text); the read must
    give {} rather than raise out of the build's recording step."""
    meta = project / ".compass" / "meta"
    if shape == "log-is-a-folder":
        (meta / "station-log.jsonl").mkdir(parents=True)
    elif shape == "meta-is-a-file":
        meta.parent.mkdir(parents=True)
        meta.write_text("x", encoding="utf-8")
    elif shape == "compass-is-a-file":
        (project / ".compass").write_text("x", encoding="utf-8")
    target = str(project) if shape == "str-path" else project

    written = records.record_session([], role="build", outcome="failed", arm="compass",
                                     private_root=private_root, project_dir=target)

    assert written["stations"] == {}


def test_a_station_name_with_path_or_text_characters_is_dropped_beside_a_plain_row(project, private_root):
    """Adversarial where: only names matching the safe pattern may form a key; stations
    spelled as a path, a token with a space or a drive path are dropped while the plain
    row beside them stays counted."""
    unsafe = [secret for secret in SECRETS if not secret.replace("-", "").isalnum()]
    write_log(project, [row(secret, M1) for secret in unsafe] + [row("builder", M1)])

    written = records.record_session([], role="build", outcome="done", arm="compass",
                                     private_root=private_root, project_dir=project)

    assert list(written["stations"]) == [f"builder|{M1}"]
    assert not [secret for secret in unsafe if secret in disk_text(private_root)]
