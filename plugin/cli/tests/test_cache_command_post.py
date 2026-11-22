"""Tests for `compass cache` branches that only the implementation introduced:
the git work tree probe of `--save`, the argument scanner, the saved-file
reader and the project discovery of `--all-compass`.

Every invocation is a subprocess of `plugin/cli/compass`, built on the machine
fixtures of `test_cache_command`.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_cache_command import (  # noqa: E402
    World,
    assert_failed,
    build_machine,
    use,
    write_jsonl,
)


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def _git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    )


def _repo(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    return path


def _link(link, target):
    try:
        os.symlink(str(target), str(link), target_is_directory=Path(target).is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")


def _tiny(world):
    proj = world.project("LEAKPOST-ONE")
    world.session(proj, "a", 0, [1], [use(500, 500, 0)])
    return proj


# ---- --save target: the git work tree probe ---------------------------------


def test_save_refuses_a_folder_whose_ancestor_holds_a_git_file(world):
    """Adversarial where: a linked worktree or submodule has a `.git` FILE, and a
    probe that tests `is_dir()` instead of `exists()` would write a baseline into
    it."""
    proj = _tiny(world)
    tree = world.root / "linked"
    tree.mkdir()
    (tree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    target = tree / "sub" / "out.json"
    assert_failed(world.run(proj, "--save", str(target)), "git")
    assert not (tree / "sub").exists()


def test_save_refuses_a_relative_path_when_the_working_directory_is_in_a_repo(world):
    """Adversarial where: a relative `--save` resolves against the working
    directory; the probe must judge the resolved path, not the bare name, or the
    ordinary `compass cache --save base.json` run at a repo root writes into the
    repo."""
    proj = _tiny(world)
    _repo(proj)
    result = world.run(proj, "--save", "base.json")
    assert_failed(result, "git")
    assert not (proj / "base.json").exists()


def test_save_refuses_a_path_reached_through_a_symlinked_folder(world):
    """Adversarial where: a folder outside any repo that is a link into a repo;
    a probe that walks the lexical parents never sees the `.git`."""
    proj = _tiny(world)
    repo = _repo(world.root / "repo")
    (repo / "data").mkdir()
    _link(world.root / "alias", repo / "data")
    assert_failed(
        world.run(proj, "--save", str(world.root / "alias" / "out.json")), "git"
    )
    assert not (repo / "data" / "out.json").exists()


def test_save_refuses_a_file_that_is_a_symlink_into_a_repo(world):
    """Adversarial where: the target file itself is a link to a path inside a
    repo; writing through it lands in the work tree."""
    proj = _tiny(world)
    repo = _repo(world.root / "repo")
    _link(world.root / "out.json", repo / "baseline.json")
    result = world.run(proj, "--save", str(world.root / "out.json"))
    assert_failed(result, "git")
    assert not (repo / "baseline.json").exists()


def test_save_accepts_a_sibling_whose_name_only_resembles_a_git_folder(world):
    """Adversarial where: a folder named `.github` or `x.git` beside the target is
    not a work tree; a prefix or substring probe refuses a valid baseline."""
    proj = _tiny(world)
    (world.root / "keep" / ".github").mkdir(parents=True)
    (world.root / "keep" / "x.git").mkdir()
    target = world.root / "keep" / "out.json"
    result = world.run(proj, "--save", str(target))
    assert result.returncode == 0, result.stderr
    assert json.loads(target.read_text(encoding="utf-8"))["version"] == 1


def test_save_with_a_non_ascii_path_prints_saved_without_a_traceback(world):
    """Adversarial where: the `saved <path>` line is written to a pipe whose
    encoding cannot hold the path; a bare write raises UnicodeEncodeError."""
    proj = _tiny(world)
    target = world.root / "baseline-日本" / "out.json"
    env = world.env()
    env.pop("PYTHONIOENCODING")
    result = world.run(proj, "--save", str(target), env=env)
    assert result.returncode == 0, result.stderr
    assert "traceback" not in result.stderr.lower()
    assert target.is_file()


# ---- --days parsing ---------------------------------------------------------


@pytest.mark.parametrize(
    "days", ["٣", "+5", " 5", "5 ", "1_0", "0x10", "1e2", "-1", "000000000", "5.0"]
)
def test_days_rejects_spellings_that_int_would_accept(world, days):
    """Adversarial where: `int()` accepts Arabic-Indic digits, a sign, padding and
    underscores; the scanner must accept only ASCII digits and a value of at
    least 1."""
    proj = _tiny(world)
    assert_failed(world.run(proj, "--days", days), "--days")


def test_days_accepts_leading_zeros_and_the_last_value_that_can_be_represented(world):
    """Adversarial where: the digit-count guard and the date-range guard meet at
    the earliest representable date; one day further is refused, the largest
    count that fits must run."""
    proj = _tiny(world)
    assert world.run(proj, "--days", "0007").returncode == 0
    reach = (
        datetime.now(timezone.utc) - datetime(1, 1, 1, tzinfo=timezone.utc)
    ).days - 1
    assert world.run(proj, "--days", str(reach)).returncode == 0
    assert_failed(world.run(proj, "--days", str(reach + 2)), "--days")


def test_days_given_twice_uses_the_last_and_validates_each(world):
    """Adversarial where: an option scanner that keeps the first value, or that
    skips validating an overridden one."""
    proj = _tiny(world)
    assert world.json(proj, "--days", "5", "--days", "9")["days"] == 9
    assert_failed(world.run(proj, "--days", "5", "--days", "x"), "--days")


@pytest.mark.parametrize(
    "args",
    [
        ["--days=7"],
        ["--days", "--json"],
        ["--compare"],
        ["--compare", ""],
        ["--save", "a", "b"],
        ["extra"],
    ],
)
def test_option_scanner_failures_exit_one_with_a_message(world, args):
    """Adversarial where: the `--name=value` spelling, an option swallowing the
    next option as its value, and stray positionals each fall through the scanner
    differently."""
    proj = _tiny(world)
    assert_failed(world.run(proj, *args))


def test_save_followed_by_another_option_takes_the_default_path(world):
    """Adversarial where: `--save --json` must not treat `--json` as the file
    name."""
    proj = _tiny(world)
    result = world.run(proj, "--save", "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["version"] == 1
    assert not (proj / "--json").exists()
    assert list((world.compass_home / "cache").glob("*.json"))


# ---- --compare: saved-file shapes and ordering ------------------------------


def _before(world, main, **extra):
    path = world.root / "before.json"
    path.write_text(json.dumps({"main": main, **extra}), encoding="utf-8")
    return path


GOOD = {"first_request_hit": {"value": 0.5}, "next_session_read_share": {"value": None}}


def test_compare_accepts_a_minimal_saved_object_with_no_n_and_no_other_keys(world):
    """Adversarial where: a reader indexing keys the saved object may lack
    (`n`, `subagents`, the unguarded measures)."""
    proj = _tiny(world)
    result = world.run(proj, "--compare", str(_before(world, GOOD)))
    assert result.returncode == 0, result.stderr
    assert "traceback" not in result.stderr.lower()
    assert "main first-request hit: before 50.0% after" in result.stdout
    assert "main whole-session hit" not in result.stdout


@pytest.mark.parametrize(
    "subagents",
    [
        [],
        None,
        "x",
        {"builder": None},
        {"builder": []},
        {"builder": {"first_request_hit": "x"}},
        {"builder": {"first_request_hit": {"value": True}}},
    ],
)
def test_compare_skips_malformed_subagent_sections_without_crashing(world, subagents):
    """Adversarial where: the subagent rows read a section the validation of the
    two guarded measures never looked at."""
    proj = _tiny(world)
    result = world.run(
        proj, "--compare", str(_before(world, GOOD, subagents=subagents))
    )
    assert "traceback" not in result.stderr.lower()
    assert result.returncode == 0, result.stderr
    assert "subagent" not in result.stdout


@pytest.mark.parametrize(
    "text",
    [
        '{"main": {"first_request_hit": {"value": NaN},'
        ' "next_session_read_share": {"value": null}}}',
        '{"main": {"first_request_hit": {"value": Infinity},'
        ' "next_session_read_share": {"value": null}}}',
        '{"main": {"first_request_hit": {"value": "0.5"},'
        ' "next_session_read_share": {"value": null}}}',
        '{"main": {"first_request_hit": {"n": 3},'
        ' "next_session_read_share": {"value": null}}}',
        '{"main": {"first_request_hit": 0.5,'
        ' "next_session_read_share": {"value": null}}}',
        "[" * 5000,
        '﻿{"main": 3}',
    ],
)
def test_compare_refuses_values_a_comparison_cannot_use(world, text):
    """Adversarial where: JSON accepts NaN and Infinity, which make every
    comparison false and so would read as no fall; a bare value, a missing key
    and deeply nested input must refuse, not raise."""
    proj = _tiny(world)
    path = world.root / "before.json"
    path.write_text(text, encoding="utf-8")
    assert_failed(world.run(proj, "--compare", str(path)))


def test_compare_null_current_value_prints_not_available_and_does_not_fail(world):
    """Adversarial where: a window with no data (after is null, n=0) against a
    real before value must format as `n/a` for both the change and the exit
    code, never subtract None."""
    proj = world.project("LEAKPOST-EMPTY")
    before = _before(
        world,
        {
            "first_request_hit": {"value": 0.9},
            "next_session_read_share": {"value": 0.9},
            "first_request_read_median": {"value": 5000.0},
        },
    )
    result = world.run(proj, "--compare", str(before))
    assert result.returncode == 0, result.stderr
    assert "main first-request hit: before 90.0% after n/a change n/a" in result.stdout
    assert (
        "main first-request read median: before 5000 after n/a change n/a"
        in result.stdout
    )


def test_compare_prints_positive_zero_for_a_change_that_rounds_to_zero(world):
    """Adversarial where: -0.04 points rounds to -0.0, which formats as `-0.0
    points`."""
    proj = _tiny(world)
    current = world.json(proj)["main"]["first_request_hit"]["value"]
    before = _before(
        world,
        {
            "first_request_hit": {"value": current + 0.0004},
            "next_session_read_share": {"value": None},
        },
    )
    result = world.run(proj, "--compare", str(before))
    assert result.returncode == 0, result.stderr
    assert "change +0.0 points" in result.stdout
    assert "-0.0" not in result.stdout


@pytest.mark.parametrize("fall,expected", [(0.0504, 0), (0.0506, 1)])
def test_compare_band_rounds_the_unrounded_change_to_one_decimal(world, fall, expected):
    """Adversarial where: a fall of 5.04 points rounds to 5.0 and passes, 5.06
    rounds to 5.1 and fails; comparing the raw value, or rounding before the
    subtraction, moves the edge."""
    proj = _tiny(world)
    current = world.json(proj)["main"]["first_request_hit"]["value"]
    before = _before(
        world,
        {
            "first_request_hit": {"value": current + fall},
            "next_session_read_share": {"value": None},
        },
    )
    assert world.run(proj, "--compare", str(before)).returncode == expected


def test_compare_with_json_keeps_stdout_one_object_and_sends_rows_to_stderr(world):
    """Adversarial where: comparison rows written to stdout corrupt the JSON
    line that `--json` promises."""
    proj = _tiny(world)
    before = _before(world, GOOD)
    result = world.run(proj, "--json", "--compare", str(before))
    assert result.stdout.count("\n") == 1
    assert json.loads(result.stdout)["version"] == 1
    assert "main first-request hit: before" in result.stderr


def test_compare_reads_the_saved_file_before_save_overwrites_it(world):
    """Adversarial where: `--save F --compare F` is the update-the-baseline run;
    reading F after the write compares the report with itself and always passes."""
    proj = _tiny(world)
    current = world.json(proj)["main"]["first_request_hit"]["value"]
    target = world.root / "base.json"
    target.write_text(
        json.dumps(
            {
                "main": {
                    "first_request_hit": {"value": current + 0.5},
                    "next_session_read_share": {"value": None},
                }
            }
        ),
        encoding="utf-8",
    )
    result = world.run(proj, "--save", str(target), "--compare", str(target))
    assert result.returncode == 1
    assert "fell" in result.stderr
    assert json.loads(target.read_text(encoding="utf-8"))["main"]["first_request_hit"][
        "value"
    ] == pytest.approx(current)


def test_invalid_compare_file_stops_before_save_writes_anything(world):
    """Adversarial where: validating the saved file after the save would leave a
    baseline behind from a run that reported failure."""
    proj = _tiny(world)
    bad = world.root / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    out = world.root / "out.json"
    assert_failed(world.run(proj, "--save", str(out), "--compare", str(bad)))
    assert not out.exists()


# ---- scope: vault discovery -------------------------------------------------


def test_without_a_vault_anywhere_the_command_fails_cleanly(world):
    """Adversarial where: `find_vault_root` raising FileNotFoundError outside the
    guarded block would print a traceback."""
    bare = world.work / "novault"
    bare.mkdir()
    result = world.run(bare)
    assert_failed(result)


def test_linked_worktree_reads_the_main_checkout_transcripts_and_vault(world):
    """Adversarial where: run from a linked git worktree, the transcript folder is
    keyed by the main checkout; a key derived from the worktree path reads
    nothing."""
    main = _repo(world.work / "main-proj")
    (main / ".compass").mkdir()
    (main / "f.txt").write_text("x", encoding="utf-8")
    _git(main, "add", "f.txt")
    _git(
        main, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"
    )
    tree = world.work / "linked-proj"
    _git(main, "worktree", "add", "-q", str(tree))
    (tree / ".compass").mkdir(exist_ok=True)
    world.session(main, "a", 0, [1], [use(500, 500, 0)])
    data = world.json(tree)
    assert data["main"]["first_request_hit"]["n"] == 1


def test_all_compass_survives_odd_cwd_values_in_the_first_records(world):
    """Adversarial where: the first recorded `cwd` is a number, an empty string, a
    string with a NUL, or a path that is a file; discovery must skip the value or
    folder, never raise, and still find the real cwd on a later record."""
    proj = world.project("LEAKPOST-REAL")
    folder = world.folder(proj)
    write_jsonl(
        folder / "a.jsonl",
        [
            {"type": "attachment", "timestamp": "2026-01-01T00:00:00Z", "cwd": 12345},
            {"type": "attachment", "timestamp": "2026-01-01T00:00:01Z", "cwd": ""},
            {
                "type": "attachment",
                "timestamp": "2026-01-01T00:00:02Z",
                "cwd": str(proj),
            },
        ],
    )
    nul = world.cfg / "projects" / "nul-folder"
    write_jsonl(nul / "a.jsonl", [{"type": "attachment", "cwd": "bad\x00path"}])
    isfile = world.cfg / "projects" / "file-folder"
    (world.work / "a-file").write_text("x", encoding="utf-8")
    write_jsonl(
        isfile / "a.jsonl", [{"type": "attachment", "cwd": str(world.work / "a-file")}]
    )
    data = world.json(proj, "--all-compass")
    assert data["projects"] == 1


def test_all_compass_counts_two_folders_with_one_cwd_once(world):
    """Adversarial where: two transcript folders (a renamed key, a case variant)
    that record the same cwd would double every sum if the vault key were not
    deduplicated."""
    proj = world.project("LEAKPOST-TWICE")
    world.session(proj, "a", 0, [1], [use(500, 500, 0)])
    twin = world.cfg / "projects" / "twin-key"
    write_jsonl(twin / "b.jsonl", [{"type": "attachment", "cwd": str(proj)}])
    data = world.json(proj, "--all-compass")
    assert data["projects"] == 1
    assert data["main"]["first_request_hit"]["n"] == 1


def test_all_compass_with_a_missing_projects_folder_reads_zero(world):
    """Adversarial where: `CLAUDE_CONFIG_DIR/projects` absent (a fresh machine)
    must read as no projects, not raise."""
    proj = world.project("LEAKPOST-NOPROJECTS")
    world.session(proj, "a", 0, [1], [use(500, 500, 0)])
    with_data = world.json(proj, "--all-compass")
    (world.cfg / "projects").rename(world.root / "moved-projects")
    data = world.json(proj, "--all-compass")
    assert with_data["projects"] > data["projects"]
    assert data["main"]["whole_hit"]["n"] < with_data["main"]["whole_hit"]["n"]
    assert data["main"]["whole_hit"]["value"] is None


def test_text_report_with_a_non_ascii_agent_type_does_not_crash_a_narrow_pipe(world):
    """Adversarial where: an agent type or loop name outside the pipe's encoding
    reaches `sys.stdout.write` as a UnicodeEncodeError."""
    proj, _ = build_machine(world)
    parent = next(p for p in world.folder(proj).glob("s-e.jsonl"))
    world.subagent(parent, "uni", "agente-日本", 4, [5], [use(1, 1, 0)], proj)
    env = world.env()
    env.pop("PYTHONIOENCODING")
    result = world.run(proj, env=env)
    assert result.returncode == 0, result.stderr
    assert "traceback" not in result.stderr.lower()
    assert "subagent agente-" in result.stdout
