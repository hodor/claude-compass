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


PAIR_NAMES = [f"build{index}" for index in range(7)]


def write_pairs(tmp_path, variant_met, full_met=8, items=8, names=PAIR_NAMES, variant_overrides=None):
    """Full arm in `ob`, variant arm in `oa`, one outcome file per paired build."""
    overrides = variant_overrides or {}
    for name in names:
        met = overrides.get(name, variant_met)
        write_outcome(tmp_path / "ob", name, met=full_met, unmet=items - full_met)
        write_outcome(tmp_path / "oa", name, met=met, unmet=items - met)
    write_profile(tmp_path / "before", "a", {"subagent:builder": entry([100, 200])})
    write_profile(tmp_path / "after", "a", {"subagent:builder": entry([10, 20])})


def run_outcomes(capsys, tmp_path, plugin, *extra):
    return run(capsys, tmp_path / "before", tmp_path / "after", plugin,
               "--outcomes-before", str(tmp_path / "ob"), "--outcomes-after", str(tmp_path / "oa"), *extra)


@pytest.mark.parametrize("name, diffs, margin, verdict, bound", [
    ("loses exactly the margin", [-0.25] * 4, 0.25, "worse", -0.25),
    ("just inside the margin", [-0.234375] * 4, 0.25, "not worse", -0.234375),
    ("just outside the margin", [-0.265625] * 4, 0.25, "worse", -0.265625),
    ("zero margin, zero change is not strictly above", [0.0] * 4, 0.0, "worse", 0.0),
    ("variant better than full", [0.5] * 3, 0.25, "not worse", 0.5),
    ("two pairs is the smallest accepted set", [-0.125, -0.125], 0.25, "not worse", -0.125),
])
def test_noninferiority_needs_the_bound_strictly_above_minus_the_margin(name, diffs, margin, verdict, bound):
    """Adversarial where: a bound sitting exactly on minus the margin must read
    "worse" (>= instead of > flips it), and one step inside must read "not
    worse" (an off-by-one tolerance flips it)."""
    result = compare.noninferiority(diffs, margin)

    assert result["verdict"] == verdict
    assert result["bound"] == pytest.approx(bound, abs=1e-12)
    assert result["pairs"] == len(diffs)


def test_noninferiority_refuses_fewer_than_two_pairs():
    """Adversarial where: one pair has no spread to resample, so a verdict from
    it would be a false certainty; zero pairs must not divide by zero."""
    with pytest.raises(ValueError):
        compare.noninferiority([], 0.25)
    with pytest.raises(ValueError):
        compare.noninferiority([-0.125], 0.25)
    assert compare.noninferiority([-0.125, -0.125], 0.25)["pairs"] == 2


def test_noninferiority_bound_is_the_one_sided_fifth_percentile_of_resampled_means():
    """Adversarial where: a two-sided (2.5th percentile) or upper-tail bound
    reads a different number from the one-sided 95% bound. Twenty builds, four
    of them losing the whole item share (-1): the resampled mean is -K/20 with
    K binomial(20, 0.2); P(K>=7)=0.087 and P(K>=8)=0.032 put the 5th percentile
    at -0.35 and the 2.5th at -0.40."""
    diffs = [-1.0] * 4 + [0.0] * 16

    result = compare.noninferiority(diffs, 0.36)

    assert result["bound"] == pytest.approx(-0.35, abs=1e-9)
    assert result["verdict"] == "not worse"
    assert compare.noninferiority(diffs, 0.34)["verdict"] == "worse"


def test_noninferiority_is_repeatable_whatever_the_global_random_state_and_leaves_its_input_alone():
    """Adversarial where: a bound drawn from the global `random` module moves
    between runs, and a sort done in place reorders the caller's list."""
    diffs = [0.125, -0.5, 0.25, -0.125, 0.0, -0.375]
    original = list(diffs)

    random.seed(1)
    first = compare.noninferiority(diffs, 0.25)
    random.seed(2)
    second = compare.noninferiority(diffs, 0.25)

    assert first == second
    assert diffs == original


@pytest.mark.parametrize("name, variant_met, margin, verdict", [
    ("loses exactly the margin", 6, "0.25", "worse"),
    ("one step inside the margin", 7, "0.25", "not worse"),
    ("same outcome as the full arm", 8, "0.25", "not worse"),
    ("loses more than a looser margin allows", 4, "0.3", "worse"),
    ("loses less than a looser margin allows", 6, "0.3", "not worse"),
])
def test_margin_prints_the_verdict_with_the_pair_count_instead_of_the_equality_guard(
        tmp_path, plugin, capsys, name, variant_met, margin, verdict):
    """Adversarial where: with --margin the equality guard must not fire on a
    tolerated loss, and the verdict line must carry the pair count (seven
    builds; no other number in the line is a 7)."""
    write_pairs(tmp_path, variant_met)

    code, out = run_outcomes(capsys, tmp_path, plugin, "--margin", margin)

    verdict_line = next(line for line in out.splitlines() if "worse" in line)
    assert code == 0
    assert "outcome differs" not in out
    assert ("not worse" in verdict_line) == (verdict == "not worse")
    assert "7" in verdict_line


def test_margin_with_one_paired_build_is_refused_as_too_few(tmp_path, plugin, capsys):
    """Adversarial where: a single pair would print a confident verdict from no
    spread at all."""
    write_pairs(tmp_path, 8, names=["build0"])

    code, out = run_outcomes(capsys, tmp_path, plugin, "--margin", "0.25")

    assert code != 0
    assert "worse" not in out


@pytest.mark.parametrize("name, variant_met, full_met", [
    ("one build lost one goal item", 7, 8),
    ("the variant met more than the full arm", 8, 6),
])
def test_without_margin_any_outcome_difference_still_prints_outcome_differs_and_no_token_verdict(
        tmp_path, plugin, capsys, name, variant_met, full_met):
    """Adversarial where: adding --margin must leave the exact-equality guard
    intact when it is absent, in either direction of the difference."""
    write_pairs(tmp_path, 8, full_met=full_met, variant_overrides={"build3": variant_met})

    code, out = run_outcomes(capsys, tmp_path, plugin)

    assert code == 0
    assert "outcome differs, so no token verdict" in out
    assert "| builder" not in out
    assert "worse" not in out


def test_goal_shares_count_partly_met_in_the_denominator_but_not_the_numerator(tmp_path):
    """Adversarial where: a partly met item counted as met (or dropped from the
    denominator) inflates the variant share; 4 met + 4 partly met of 8 is 0.5,
    against 1.0 for the full arm, so every pair differs by exactly -0.5."""
    for name in ("a", "b"):
        write_outcome(tmp_path / "ob", name, met=8)
        write_outcome(tmp_path / "oa", name, met=4, partly=4)

    diffs = compare.paired_differences(tmp_path / "ob", tmp_path / "oa")

    assert diffs == [-0.5, -0.5]


@pytest.mark.parametrize("name, full_names, variant_names", [
    ("same count, one name swapped", ["b1", "b2", "b3"], ["b1", "b2", "b9"]),
    ("variant holds an extra build", ["b1", "b2"], ["b1", "b2", "b3"]),
    ("variant holds one build fewer", ["b1", "b2", "b3"], ["b1", "b2"]),
])
def test_margin_refuses_outcome_folders_naming_different_builds_without_leaking_names(
        tmp_path, plugin, capsys, name, full_names, variant_names):
    """Adversarial where: pairing by position or by the shared subset would
    silently compare the wrong builds; a mismatched set must exit non-zero with
    no verdict and without printing a file name."""
    for build in full_names:
        write_outcome(tmp_path / "ob", build, met=8)
    for build in variant_names:
        write_outcome(tmp_path / "oa", build, met=8)
    write_profile(tmp_path / "before", "a", {"subagent:builder": entry([100, 200])})
    write_profile(tmp_path / "after", "a", {"subagent:builder": entry([10, 20])})

    code, out = run_outcomes(capsys, tmp_path, plugin, "--margin", "0.25")
    err = capsys.readouterr().err

    assert code == 2
    assert "worse" not in out
    assert "| builder" not in out
    assert "b9" not in out + err and "b3" not in out + err


@pytest.mark.parametrize("side", ["ob", "oa"])
def test_margin_refuses_a_goal_file_with_zero_items_whichever_arm_holds_it(tmp_path, plugin, capsys, side):
    """Adversarial where: a verdict file scoring no goal item divides 0 by 0 in
    the share; it must be refused (exit 2), not crash or read as share 0."""
    write_pairs(tmp_path, 8, names=["b1", "b2", "b3"])
    write_outcome(tmp_path / side, "b2", met=0, partly=0, unmet=0)

    code, out = run_outcomes(capsys, tmp_path, plugin, "--margin", "0.25")

    assert code == 2
    assert "worse" not in out


@pytest.mark.parametrize("counts", [
    {"met": 2, "partly met": -2, "not met": 0},
    {"met": "many", "not met": 1},
])
def test_margin_refuses_unusable_goal_counts_instead_of_a_share_outside_zero_to_one(tmp_path, plugin, capsys, counts):
    """Adversarial where: counts that cancel to a zero total, or a non-numeric
    count, must surface as a refusal rather than a traceback."""
    write_pairs(tmp_path, 8, names=["b1", "b2", "b3"])
    (tmp_path / "oa" / "b2.json").write_text(json.dumps({"counts": counts}), encoding="utf-8")

    code, out = run_outcomes(capsys, tmp_path, plugin, "--margin", "0.25")

    assert code == 2
    assert "worse" not in out


@pytest.mark.parametrize("margin", ["-0.125", "-1", "abc", ""])
def test_margin_rejects_a_negative_or_non_numeric_value_with_no_verdict(tmp_path, plugin, capsys, margin):
    """Adversarial where: a negative margin makes 'not worse' require a gain
    and a non-numeric one must not reach the comparison; either refusal exits
    2 (returned or raised by the argument parser) with no verdict printed."""
    write_pairs(tmp_path, 8)

    try:
        code, out = run_outcomes(capsys, tmp_path, plugin, "--margin", margin)
    except SystemExit as stop:
        code, out = stop.code, capsys.readouterr().out

    assert code == 2
    assert "worse" not in out


def test_margin_without_both_outcome_folders_is_refused(tmp_path, plugin, capsys):
    """Adversarial where: --margin with no outcome folders has nothing to pair;
    it must exit 2 rather than fall through to a token-only report."""
    write_pairs(tmp_path, 8)

    code, out = run(capsys, tmp_path / "before", tmp_path / "after", plugin, "--margin", "0.25")

    assert code == 2
    assert "| builder" not in out


@pytest.mark.parametrize("margin", ["nan", "1.5", "inf"])
def test_a_margin_beyond_a_fraction_of_goal_items_is_refused(tmp_path, plugin, capsys, margin):
    """Adversarial where: the margin is a fraction of goal items, so a value
    above 1 (or not a number) tolerates every possible loss and would read
    'not worse' for a variant that built nothing."""
    write_pairs(tmp_path, 0)

    code, out = run_outcomes(capsys, tmp_path, plugin, "--margin", margin)

    assert code == 2
    assert "not worse" not in out


def test_a_verdict_of_not_worse_is_followed_by_the_token_table_and_worse_by_none(tmp_path, plugin, capsys):
    """Adversarial where: the worse branch returns early and the not-worse
    branch must still reach the token comparison; a swapped condition would
    print the table for the losing variant."""
    write_pairs(tmp_path, 7)
    _, kept = run_outcomes(capsys, tmp_path, plugin, "--margin", "0.25")
    write_pairs(tmp_path, 0)
    _, lost = run_outcomes(capsys, tmp_path, plugin, "--margin", "0.25")

    assert "| builder" in kept
    assert "| builder" not in lost
    assert "No token verdict" in lost


def test_the_margin_verdict_line_holds_no_em_or_en_dash(tmp_path, plugin, capsys):
    """Adversarial where: the verdict line is built from a signed bound and a
    negated margin; a typographic minus in either would break the report's
    plain-text contract."""
    write_pairs(tmp_path, 6)

    _, out = run_outcomes(capsys, tmp_path, plugin, "--margin", "0.5")

    assert "worse" in out
    assert "—" not in out and "–" not in out and "−" not in out
