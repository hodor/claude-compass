"""Tests for compare.py: per agent type, mean weighted tokens per launch in two
saved sets of profiles, the change, and a bootstrap interval over sessions.

Interface under test:

    compare.load_profiles(folder) -> {agent key: [session weighted tokens]}
    compare.load_outcomes(folder) -> {"goals": {score: count}, "tests": {result: count}}
    compare.bootstrap_interval(before, after) -> (low, high) | None
    compare.main(argv) -> exit code, report on stdout

Adversarial themes: a type present in one set only; a set with a type that has
no sessions; sets whose outcomes differ still printing a token verdict; an
interval that moves between runs; an interval that excludes the change for
identical sets; a private agent type or an input folder name reaching the
report.
"""

import json
import random

import pytest

import compare

KNOWN = frozenset({"builder", "validator"})


def entry(sessions):
    sessions = [float(value) for value in sessions]
    mean = sum(sessions) / len(sessions) if sessions else 0.0
    return {"sessions": len(sessions), "mean": mean, "median": mean, "families": {}, "session_weighted": sessions}


def write_profile(folder, name, by_agent):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.json").write_text(json.dumps({"weighted": 1.0, "by_agent": by_agent}), encoding="utf-8")


def write_outcome(folder, name, met=0, partly=0, unmet=0, tests="pass"):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.json").write_text(json.dumps({
        "counts": {"met": met, "partly met": partly, "not met": unmet},
        "recorded": {"builder_tests": tests},
    }), encoding="utf-8")


@pytest.fixture
def plugin(tmp_path):
    root = tmp_path / "plugin"
    (root / "agents").mkdir(parents=True)
    for name in KNOWN:
        (root / "agents" / f"{name}.md").write_text("x", encoding="utf-8")
    return root


def run(capsys, before, after, plugin, *extra):
    code = compare.main([str(before), str(after), "--plugin-root", str(plugin), *extra])
    return code, capsys.readouterr().out


def row_of(out, name):
    return next(line for line in out.splitlines() if line.startswith(f"| {name} "))


def test_load_profiles_pools_the_sessions_of_every_file_per_agent_type(tmp_path):
    write_profile(tmp_path / "a", "one", {"subagent:builder": entry([100, 200])})
    write_profile(tmp_path / "a", "two", {"subagent:builder": entry([300]), "subagent:validator": entry([50])})

    pooled = compare.load_profiles(tmp_path / "a")

    assert sorted(pooled["subagent:builder"]) == [100, 200, 300]
    assert pooled["subagent:validator"] == [50]


def test_a_folder_without_a_profile_is_refused_so_it_cannot_pass_as_an_empty_set(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError):
        compare.load_profiles(tmp_path / "empty")
    with pytest.raises(ValueError):
        compare.load_profiles(tmp_path / "missing")


def test_a_profile_saved_before_by_agent_existed_is_refused_not_read_as_zero_launches(tmp_path):
    (tmp_path / "old").mkdir()
    (tmp_path / "old" / "p.json").write_text(json.dumps({"weighted": 5.0, "by_kind": {}}), encoding="utf-8")
    with pytest.raises(ValueError):
        compare.load_profiles(tmp_path / "old")


def test_a_malformed_profile_file_is_refused_without_naming_its_path(tmp_path):
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "proj-secret.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        compare.load_profiles(tmp_path / "bad")
    assert "proj-secret" not in str(caught.value)


def test_the_report_prints_the_hand_computed_means_and_change_per_type(tmp_path, plugin, capsys):
    write_profile(tmp_path / "before", "a", {"subagent:builder": entry([100, 200, 300]), "subagent:validator": entry([50, 70])})
    write_profile(tmp_path / "after", "a", {"subagent:builder": entry([80, 120, 160]), "subagent:validator": entry([60, 80])})

    code, out = run(capsys, tmp_path / "before", tmp_path / "after", plugin)

    builder, validator = row_of(out, "builder"), row_of(out, "validator")
    assert code == 0
    assert "200" in builder and "120" in builder and "-80" in builder and "-40.0%" in builder
    assert "60" in validator and "70" in validator and "+10" in validator and "+16.7%" in validator


def test_a_type_present_in_one_set_only_is_listed_with_no_change_and_no_interval(tmp_path, plugin, capsys):
    write_profile(tmp_path / "before", "a", {"subagent:builder": entry([100, 200]), "subagent:validator": entry([50, 60])})
    write_profile(tmp_path / "after", "a", {"subagent:builder": entry([100, 200])})

    code, out = run(capsys, tmp_path / "before", tmp_path / "after", plugin)

    row = row_of(out, "validator")
    assert code == 0
    assert "55" in row
    assert "only in before" in row
    assert "+" not in row and "%" not in row


def test_a_type_with_zero_sessions_on_one_side_is_treated_as_absent_there(tmp_path, plugin, capsys):
    write_profile(tmp_path / "before", "a", {"subagent:builder": entry([100, 200])})
    write_profile(tmp_path / "after", "a", {"subagent:builder": entry([])})

    code, out = run(capsys, tmp_path / "before", tmp_path / "after", plugin)

    assert code == 0
    assert "only in before" in row_of(out, "builder")


def test_two_sets_with_no_agent_sessions_print_that_there_is_nothing_to_compare(tmp_path, plugin, capsys):
    write_profile(tmp_path / "before", "a", {})
    write_profile(tmp_path / "after", "a", {})

    code, out = run(capsys, tmp_path / "before", tmp_path / "after", plugin)

    assert code == 0
    assert "no agent sessions" in out.lower()


def test_a_zero_before_mean_gives_no_percentage_instead_of_a_division_error(tmp_path, plugin, capsys):
    write_profile(tmp_path / "before", "a", {"subagent:builder": entry([0, 0])})
    write_profile(tmp_path / "after", "a", {"subagent:builder": entry([10, 20])})

    code, out = run(capsys, tmp_path / "before", tmp_path / "after", plugin)

    row = row_of(out, "builder")
    assert code == 0
    assert "+15" in row
    assert row.split("|")[7].strip() == "n/a"


def test_the_interval_is_the_same_on_every_call_whatever_the_global_random_state():
    before, after = [100, 200, 300, 250, 120], [90, 80, 160, 140, 100]

    random.seed(1)
    first = compare.bootstrap_interval(before, after)
    random.seed(2)

    assert compare.bootstrap_interval(before, after) == first


def test_the_interval_brackets_the_observed_change_and_is_ordered():
    before, after = [100, 200, 300, 250, 120], [90, 80, 160, 140, 100]
    change = sum(after) / len(after) - sum(before) / len(before)

    low, high = compare.bootstrap_interval(before, after)

    assert low <= change <= high
    assert low < high


def test_identical_constant_sets_give_a_zero_width_interval_at_zero():
    assert compare.bootstrap_interval([100, 100, 100], [100, 100, 100]) == (0.0, 0.0)


def test_a_clearly_lower_set_has_an_interval_entirely_below_zero():
    low, high = compare.bootstrap_interval([1000, 1010, 990, 1005, 995], [100, 105, 95, 98, 102])

    assert high < 0


def test_the_interval_needs_two_sessions_on_each_side():
    assert compare.bootstrap_interval([100], [90, 80]) is None
    assert compare.bootstrap_interval([100, 90], [80]) is None
    assert compare.bootstrap_interval([], [80, 70]) is None


def test_the_printed_interval_is_identical_across_two_runs(tmp_path, plugin, capsys):
    write_profile(tmp_path / "before", "a", {"subagent:builder": entry([100, 200, 300, 250])})
    write_profile(tmp_path / "after", "a", {"subagent:builder": entry([90, 80, 160, 140])})

    _, first = run(capsys, tmp_path / "before", tmp_path / "after", plugin)
    _, second = run(capsys, tmp_path / "before", tmp_path / "after", plugin)

    assert first == second
    assert "95%" in first


def test_unequal_outcome_counts_print_outcome_differs_and_no_token_verdict(tmp_path, plugin, capsys):
    write_profile(tmp_path / "before", "a", {"subagent:builder": entry([100, 200])})
    write_profile(tmp_path / "after", "a", {"subagent:builder": entry([10, 20])})
    write_outcome(tmp_path / "ob", "a", met=5, partly=1)
    write_outcome(tmp_path / "oa", "a", met=4, partly=2)

    code, out = run(capsys, tmp_path / "before", tmp_path / "after", plugin,
                    "--outcomes-before", str(tmp_path / "ob"), "--outcomes-after", str(tmp_path / "oa"))

    assert code == 0
    assert "outcome differs" in out
    assert "| builder" not in out
    assert "95%" not in out and "%" not in out


def test_a_different_test_result_alone_makes_the_outcome_differ(tmp_path, plugin, capsys):
    write_profile(tmp_path / "before", "a", {"subagent:builder": entry([100, 200])})
    write_profile(tmp_path / "after", "a", {"subagent:builder": entry([10, 20])})
    write_outcome(tmp_path / "ob", "a", met=5, tests="pass")
    write_outcome(tmp_path / "oa", "a", met=5, tests="fail")

    _, out = run(capsys, tmp_path / "before", tmp_path / "after", plugin,
                 "--outcomes-before", str(tmp_path / "ob"), "--outcomes-after", str(tmp_path / "oa"))

    assert "outcome differs" in out
    assert "| builder" not in out


def test_equal_outcome_counts_print_the_token_table_and_say_the_outcomes_match(tmp_path, plugin, capsys):
    write_profile(tmp_path / "before", "a", {"subagent:builder": entry([100, 200])})
    write_profile(tmp_path / "after", "a", {"subagent:builder": entry([10, 20])})
    write_outcome(tmp_path / "ob", "a", met=5, partly=1)
    write_outcome(tmp_path / "ob", "b", met=3, tests="fail")
    write_outcome(tmp_path / "oa", "x", met=3, tests="fail")
    write_outcome(tmp_path / "oa", "y", met=5, partly=1)

    _, out = run(capsys, tmp_path / "before", tmp_path / "after", plugin,
                 "--outcomes-before", str(tmp_path / "ob"), "--outcomes-after", str(tmp_path / "oa"))

    assert "outcome differs" not in out
    assert "| builder" in out
    assert "outcomes match" in out.lower()


def test_one_outcomes_folder_without_the_other_is_refused(tmp_path, plugin, capsys):
    write_profile(tmp_path / "before", "a", {"subagent:builder": entry([100, 200])})
    write_profile(tmp_path / "after", "a", {"subagent:builder": entry([10, 20])})
    write_outcome(tmp_path / "ob", "a", met=5)

    code = compare.main([str(tmp_path / "before"), str(tmp_path / "after"), "--plugin-root", str(plugin),
                         "--outcomes-before", str(tmp_path / "ob")])

    assert code != 0
    assert "| builder" not in capsys.readouterr().out


def test_an_outcome_folder_with_no_verdict_is_refused_not_read_as_zero_goals(tmp_path):
    (tmp_path / "none").mkdir()
    with pytest.raises(ValueError):
        compare.load_outcomes(tmp_path / "none")


def test_private_agent_types_print_as_other_and_pool_across_each_set(tmp_path, plugin, capsys):
    write_profile(tmp_path / "before", "a", {
        "subagent:lighthouse-agent": entry([100, 200]), "subagent:keeper-agent": entry([300, 400])})
    write_profile(tmp_path / "after", "a", {"subagent:lighthouse-agent": entry([50, 60])})

    code, out = run(capsys, tmp_path / "before", tmp_path / "after", plugin)

    row = row_of(out, "(other)")
    assert code == 0
    assert "lighthouse" not in out and "keeper" not in out
    assert "250" in row
    assert "55" in row


def test_the_report_carries_no_folder_or_file_name_from_the_inputs(tmp_path, plugin, capsys):
    write_profile(tmp_path / "proj-secret-before", "session-9f8e", {"subagent:builder": entry([100, 200])})
    write_profile(tmp_path / "proj-secret-after", "session-1a2b", {"subagent:builder": entry([10, 20])})

    _, out = run(capsys, tmp_path / "proj-secret-before", tmp_path / "proj-secret-after", plugin)

    for secret in ("proj-secret", "session-9f8e", "session-1a2b", str(tmp_path)):
        assert secret not in out


def test_the_report_text_holds_no_em_or_en_dash(tmp_path, plugin, capsys):
    write_profile(tmp_path / "before", "a", {"subagent:builder": entry([100, 200]), "subagent:validator": entry([5, 6])})
    write_profile(tmp_path / "after", "a", {"subagent:builder": entry([10, 20])})

    _, out = run(capsys, tmp_path / "before", tmp_path / "after", plugin)

    assert chr(0x2013) not in out and chr(0x2014) not in out
