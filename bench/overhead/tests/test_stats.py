"""Tests for stats.py: the share, its spread, the batch size and the bootstrap.

Interface the tests pin (stats.py; token totals are plain numbers, weighted or raw)
---------------------------------------------------------------------------------
A topic is {"compass": [total of run 1, run 2, ...], "baseline": [same]}; run i
of one arm pairs with run i of the other. `topics` is {topic id: topic}.

    share(pairs) -> float
        pairs = [(compass total, baseline total), ...] over builds. The ratio of
        sums: (sum(compass) - sum(baseline)) / sum(compass). ValueError for no
        pairs or a compass sum of 0. A negative share is a valid result.
    topic_shares(topics) -> {topic id: share of that topic's pairs}
        ValueError when a topic has different run counts in its two arms.
    overall_share(topics) -> share over every pair of every topic
    pooled_within_sd(topics) -> (sd, df)
        Per pair the share (compass - baseline) / compass. Within each topic the
        squared deviations of those pair shares from the topic's mean are summed;
        df = sum(runs - 1) over topics; sd = sqrt(sum of squares / df). ValueError
        when df is 0.
    between_topic_sd(topics) -> float
        Sample standard deviation (n - 1) of the topic shares; ValueError under
        two topics.
    sd_upper_bound(sd, df, confidence=0.8) -> float
        sd * sqrt(df / q) where q is the (1 - confidence) quantile of the
        chi-square distribution with df degrees of freedom. ValueError for
        df < 1, sd < 0 or a confidence outside (0, 1).
    batch_size(sigma_w, delta) -> int
        ceil((z_0.975 + z_0.8)^2 * 2 * sigma_w^2 / delta^2). ValueError for
        sigma_w < 0 or delta <= 0.
    batch_plan(share, sd, df, relative_drop=0.10) -> {"point": n, "upper": n}
        delta = relative_drop * abs(share); "point" is batch_size(sd, delta) and
        "upper" is batch_size(sd_upper_bound(sd, df), delta). ValueError when
        share is 0.
    bootstrap_interval(topics, *, seed, resamples=2000, confidence=0.95)
            -> (low, high)
        Resamples the topics with replacement `resamples` times, takes the
        overall share of each resample and returns the percentile interval.
        A pure function of its arguments: it uses its own generator seeded with
        `seed` and leaves the global `random` state alone. ValueError under two
        topics.
    builds_per_window(seconds, window_seconds=18000) -> int
        Whole builds of the mean of `seconds` that fit one window; ValueError
        for an empty list or a non-positive mean.
"""

import math
import random

import pytest

import stats


def topic(compass, baseline):
    return {"compass": list(compass), "baseline": list(baseline)}


TWO_TOPICS = {
    "A": topic([100, 100], [50, 60]),
    "B": topic([100, 100], [80, 60]),
}


@pytest.mark.parametrize(
    "name, pairs, expected",
    [
        ("single pair", [(100, 60)], 0.4),
        ("sums, not a mean of the pair ratios", [(100, 60), (300, 200)], 0.35),
        ("baseline above compass is negative", [(50, 100)], -1.0),
        ("equal arms share nothing", [(80, 80), (20, 20)], 0.0),
    ],
)
def test_share_is_a_ratio_of_sums(name, pairs, expected):
    """Adversarial where: averaging the per-build ratios (0.3667 for the second
    case) lets a small build weigh as much as a large one."""
    assert stats.share(pairs) == pytest.approx(expected, abs=1e-12), name


@pytest.mark.parametrize("pairs", [[], [(0, 0)], [(0, 5)]])
def test_share_refuses_an_empty_or_zero_denominator(pairs):
    """Adversarial where: a zero compass sum must raise, not return inf or nan
    that flows into a report."""
    with pytest.raises(ValueError):
        stats.share(pairs)


def test_topic_and_overall_shares_weigh_builds_by_size_and_refuse_ragged_arms():
    """Adversarial where: the overall share taken as the mean of the topic
    shares (0.275 here) instead of the ratio of sums over every build (0.3);
    a topic with two compass runs and one baseline run silently dropping a run."""
    topics = {"A": topic([100, 300], [60, 200]), "B": topic([100, 100], [90, 70])}
    assert stats.topic_shares(topics) == pytest.approx({"A": 0.35, "B": 0.2})
    assert stats.overall_share(topics) == pytest.approx(0.3)
    with pytest.raises(ValueError):
        stats.topic_shares({"A": topic([100, 100], [50])})


@pytest.mark.parametrize(
    "name, topics, sd, df",
    [
        ("two topics of two runs", TWO_TOPICS, math.sqrt(0.0125), 2),
        (
            "a three-run topic carries its own two degrees of freedom",
            {**TWO_TOPICS, "C": topic([100, 100, 100], [90, 80, 70])},
            math.sqrt(0.045 / 4),
            4,
        ),
        (
            "a one-run topic adds no degrees of freedom",
            {**TWO_TOPICS, "D": topic([100], [10])},
            math.sqrt(0.0125),
            2,
        ),
    ],
)
def test_pooled_within_sd_pools_squares_by_degrees_of_freedom(name, topics, sd, df):
    """Adversarial where: dividing by the number of runs instead of runs minus
    one per topic, or averaging per-topic sds, gives a different pooled value;
    a one-run topic must not shift the mean or the divisor."""
    got_sd, got_df = stats.pooled_within_sd(topics)
    assert got_df == df, name
    assert got_sd == pytest.approx(sd, rel=1e-9), name


def test_pooled_within_sd_needs_a_repeated_run():
    """Adversarial where: every topic run once leaves df = 0; a division by zero
    or a silent 0.0 spread would size the batch from nothing."""
    with pytest.raises(ValueError):
        stats.pooled_within_sd({"A": topic([100], [50]), "B": topic([100], [60])})


def test_between_topic_sd_is_the_sample_sd_of_topic_shares():
    """Adversarial where: the population sd (divide by n) understates the
    spread; shares 0.45 and 0.3 have a sample sd of 0.10607."""
    assert stats.between_topic_sd(TWO_TOPICS) == pytest.approx(0.15 / math.sqrt(2))
    with pytest.raises(ValueError):
        stats.between_topic_sd({"A": TWO_TOPICS["A"]})


@pytest.mark.parametrize(
    "df, confidence, factor",
    [
        (1, 0.8, 3.9471538755),
        (2, 0.8, 2.1169364935),
        (3, 0.8, 1.7275872940),
        (4, 0.8, 1.5575754225),
        (2, 0.5, 1.2011224087),
    ],
)
def test_sd_upper_bound_uses_the_chi_square_quantile(df, confidence, factor):
    """Adversarial where: using the upper tail quantile (or df + 1) shrinks the
    bound below the sd it is meant to cover; factors are hand-checked chi-square
    quantiles (df = 2 is exact: sqrt(1 / -ln(1 - p)))."""
    assert stats.sd_upper_bound(1.0, df, confidence) == pytest.approx(factor, rel=1e-6)
    assert stats.sd_upper_bound(0.2, df, confidence) == pytest.approx(0.2 * factor, rel=1e-6)


def test_sd_upper_bound_is_above_the_estimate_and_tightens_with_more_data():
    """Adversarial where: a bound below the estimate, or one that widens as the
    degrees of freedom grow (invariant: strictly decreasing toward the sd)."""
    bounds = [stats.sd_upper_bound(1.0, df) for df in range(1, 40)]
    assert all(b > 1.0 for b in bounds)
    assert all(later < earlier for earlier, later in zip(bounds, bounds[1:]))


@pytest.mark.parametrize("args", [(1.0, 0), (1.0, -3), (-0.1, 4), (1.0, 4, 0.0), (1.0, 4, 1.0)])
def test_sd_upper_bound_refuses_impossible_inputs(args):
    """Adversarial where: df = 0 or a confidence on the open boundary would
    divide by zero or by an infinite quantile."""
    with pytest.raises(ValueError):
        stats.sd_upper_bound(*args)


@pytest.mark.parametrize(
    "name, sigma, delta, expected",
    [
        ("hand case 62.79 rounds up", 0.1, 0.05, 63),
        ("19.38 rounds up, not to nearest", 0.1, 0.09, 20),
        ("15.70", 0.05, 0.05, 16),
        ("quadrupling the variance of the 0.1 case: 251.16 rounds up", 0.2, 0.05, 252),
    ],
)
def test_batch_size_follows_the_two_sample_formula(name, sigma, delta, expected):
    """Adversarial where: rounding to nearest instead of up leaves the batch
    underpowered (19.38 would become 19); using sigma instead of sigma squared,
    or dropping the factor 2, changes every row."""
    assert stats.batch_size(sigma, delta) == expected, name


@pytest.mark.parametrize("args", [(0.1, 0.0), (0.1, -0.05), (-0.1, 0.05)])
def test_batch_size_refuses_a_zero_drop_or_negative_spread(args):
    """Adversarial where: delta = 0 divides by zero; a negative sigma squares
    into a plausible batch size."""
    with pytest.raises(ValueError):
        stats.batch_size(*args)


def test_batch_plan_sizes_at_the_point_estimate_and_the_upper_bound():
    """Adversarial where: taking the drop as a fraction of the spread or of a
    signed share; share 0.35, sd 0.1118, df 2 gives delta 0.035, 161 builds at
    the estimate and 718 at the bound of 0.2367. A negative share uses its size."""
    sd = math.sqrt(0.0125)
    assert stats.batch_plan(0.35, sd, 2) == {"point": 161, "upper": 718}
    assert stats.batch_plan(-0.35, sd, 2) == {"point": 161, "upper": 718}
    with pytest.raises(ValueError):
        stats.batch_plan(0.0, sd, 2)


def test_bootstrap_interval_hand_case_with_two_topics():
    """Adversarial where: resampling runs instead of topics, or an interval
    narrower than the topics allow; topic shares 0.0 and 0.5 give resamples of
    0.0, 0.25 or 0.5 with 25% on each end, so the 95% interval is exactly 0 to 0.5."""
    topics = {"A": topic([100], [100]), "B": topic([100], [50])}
    low, high = stats.bootstrap_interval(topics, seed=7)
    assert (low, high) == (pytest.approx(0.0, abs=1e-12), pytest.approx(0.5, abs=1e-12))


def test_bootstrap_interval_is_deterministic_in_range_and_leaves_global_random_alone():
    """Adversarial where: a global-random draw makes the interval change between
    runs and disturbs the caller's random stream; any share of a resample is a
    weighted mean of topic shares, so the interval stays inside their range."""
    topics = {
        "A": topic([100, 120], [60, 70]),
        "B": topic([300, 280], [250, 200]),
        "C": topic([90, 95], [10, 20]),
    }
    shares = stats.topic_shares(topics).values()
    random.seed(5)
    first = stats.bootstrap_interval(topics, seed=11)
    after = random.random()
    random.seed(5)
    expected_after = random.random()
    assert after == expected_after
    assert stats.bootstrap_interval(topics, seed=11) == first
    low, high = first
    assert min(shares) - 1e-12 <= low <= high <= max(shares) + 1e-12


def test_bootstrap_interval_of_identical_topics_is_a_point_and_needs_two_topics():
    """Adversarial where: a degenerate sample reporting spread that is not there,
    or a single topic resampled into a fake interval."""
    same = {"A": topic([100], [60]), "B": topic([100], [60]), "C": topic([100], [60])}
    low, high = stats.bootstrap_interval(same, seed=1)
    assert low == pytest.approx(0.4) and high == pytest.approx(0.4)
    with pytest.raises(ValueError):
        stats.bootstrap_interval({"A": same["A"]}, seed=1)


@pytest.mark.parametrize(
    "name, seconds, expected",
    [
        ("mean 1800 s fits 10", [1500, 2100], 10),
        ("mean 2000 s fits 9, not 10", [2000, 2000], 9),
        ("a mean of exactly one window fits 1", [18000], 1),
        ("a build longer than the window fits none", [18001], 0),
    ],
)
def test_builds_per_window_floors_the_mean(name, seconds, expected):
    """Adversarial where: rounding up promises a build that does not fit the
    five-hour window; the boundary is a mean of exactly 18000 seconds."""
    assert stats.builds_per_window(seconds) == expected, name


@pytest.mark.parametrize("seconds", [[], [0], [0, 0]])
def test_builds_per_window_refuses_nothing_to_average(seconds):
    """Adversarial where: an empty list or zero mean divides by zero."""
    with pytest.raises(ValueError):
        stats.builds_per_window(seconds)
