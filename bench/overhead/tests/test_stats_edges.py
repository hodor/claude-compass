"""Edge tests for stats.py: degenerate samples the pilot can actually produce.

Adversarial themes: zero variance, an arm that recorded no tokens, a Compass
arm cheaper than the baseline, fewer than two topics, and bootstrap resamples
that draw only a degenerate topic.
"""

import pytest

import stats

GOOD = {"compass": [100.0, 110.0], "baseline": [80.0, 85.0]}
OTHER = {"compass": [200.0, 190.0], "baseline": [150.0, 170.0]}


def test_zero_within_topic_variance_does_not_plan_zero_builds():
    """Adversarial where: identical pair shares give sd = 0 and a plan of zero
    builds per arm (or an infinite one), which tells the human that no builds
    are needed to see a 10% drop."""
    flat = {"a": {"compass": [100.0, 100.0], "baseline": [80.0, 80.0]}}
    sd, df = stats.pooled_within_sd(flat)
    assert (sd, df) == (0.0, 1)
    try:
        plan = stats.batch_plan(stats.overall_share(flat), sd, df)
    except ValueError:
        return
    assert plan["point"] >= 1 and plan["upper"] >= 1


@pytest.mark.parametrize("share_value", [-0.4, -0.01])
def test_a_cheaper_compass_arm_plans_the_same_batch_as_the_mirrored_share(share_value):
    """Adversarial where: a negative share (Compass cheaper) makes delta
    negative so batch_size raises, or plans from a signed drop instead of
    its size."""
    assert stats.batch_plan(share_value, 0.05, 4) == stats.batch_plan(-share_value, 0.05, 4)


def test_shares_go_negative_when_compass_costs_less():
    """Adversarial where: clamping a negative share to zero or taking its
    absolute value in share(), hiding that Compass was the cheaper arm."""
    assert stats.share([(50.0, 100.0)]) == -1.0
    mixed = {"a": {"compass": [50.0], "baseline": [100.0]}, "b": {"compass": [100.0], "baseline": [50.0]}}
    assert stats.topic_shares(mixed) == {"a": -1.0, "b": 0.5}
    assert stats.overall_share(mixed) == pytest.approx(0.0)


def test_a_zero_token_baseline_is_a_share_of_one_and_a_zero_token_compass_arm_is_refused():
    """Adversarial where: an arm that recorded no tokens yields nan or inf
    rather than 1.0 (baseline empty) or a ValueError (compass empty)."""
    assert stats.share([(100.0, 0.0), (50.0, 0.0)]) == 1.0
    with pytest.raises(ValueError):
        stats.share([(0.0, 10.0), (0.0, 20.0)])
    with pytest.raises(ValueError):
        stats.pooled_within_sd({"a": {"compass": [0.0, 5.0], "baseline": [1.0, 2.0]}})


def test_bootstrap_survives_a_resample_that_draws_only_a_zero_token_topic():
    """Adversarial where: one topic whose Compass builds recorded nothing makes
    every resample that draws only that topic raise, so a single failed topic
    voids the interval of the healthy ones."""
    topics = {"dead": {"compass": [0.0, 0.0], "baseline": [0.0, 0.0]}, "ok": GOOD, "ok2": OTHER}
    low, high = stats.bootstrap_interval(topics, seed=3)
    assert low <= high


def test_bootstrap_with_zero_resamples_is_a_value_error_not_an_index_error():
    """Adversarial where: an empty sorted list indexed at its tail."""
    with pytest.raises(ValueError):
        stats.bootstrap_interval({"a": GOOD, "b": OTHER}, seed=1, resamples=0)


def test_bootstrap_with_one_resample_returns_one_ordered_pair():
    """Adversarial where: the percentile indexes at the smallest sample size
    cross over (low above high) or fall off the list."""
    low, high = stats.bootstrap_interval({"a": GOOD, "b": OTHER}, seed=1, resamples=1)
    assert low == high


@pytest.mark.parametrize("topics", [{}, {"a": GOOD}], ids=["no topic", "one topic"])
def test_bootstrap_and_between_spread_need_two_topics_but_one_topic_still_has_a_share(topics):
    """Adversarial where: one topic bootstrapped to a zero-width interval that
    reads as certainty, or a between-topic sd of 0 for a single topic."""
    with pytest.raises(ValueError):
        stats.bootstrap_interval(topics, seed=0)
    with pytest.raises(ValueError):
        stats.between_topic_sd(topics)
    if topics:
        assert stats.pooled_within_sd(topics)[1] == 1
        assert stats.overall_share(topics) == pytest.approx((210 - 165) / 210)


def test_builds_per_window_boundaries():
    """Adversarial where: a mean exactly one window long fits zero builds
    through float rounding; a mean over the window floors to 0 without error."""
    assert stats.builds_per_window([18000.0]) == 1
    assert stats.builds_per_window([6000.0, 6000.0, 6000.0]) == 3
    assert stats.builds_per_window([18000.5]) == 0
    assert stats.builds_per_window([0.0, 1e-9]) > 0
