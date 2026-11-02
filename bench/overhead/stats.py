"""The overhead share, its spread, the batch size and a bootstrap interval.

A topic is `{"compass": [total of run 1, run 2, ...], "baseline": [same]}`; run
i of one arm pairs with run i of the other. `topics` maps a topic id to such a
dict. Totals are plain numbers, weighted or raw tokens.

The share of a set of pairs is a ratio of sums, `(sum(compass) - sum(baseline))
/ sum(compass)`, so a large build weighs more than a small one. The batch size
is the two-sample size for a drop of `delta` in the share at 95% confidence and
80% power, `n = (z_0.975 + z_0.8)^2 * 2 * sigma_w^2 / delta^2`, with `sigma_w`
the within-topic standard deviation of the pair shares.
"""

import math
import random
import statistics

Z_CONFIDENCE = statistics.NormalDist().inv_cdf(0.975)
Z_POWER = statistics.NormalDist().inv_cdf(0.8)
WINDOW_SECONDS = 18000


def share(pairs):
    """Ratio of sums over `pairs` of (compass total, baseline total)."""
    pairs = list(pairs)
    if not pairs:
        raise ValueError("a share needs at least one pair")
    compass = sum(c for c, _ in pairs)
    if compass == 0:
        raise ValueError("the compass total is zero")
    return (compass - sum(b for _, b in pairs)) / compass


def _pairs(topic):
    compass, baseline = topic["compass"], topic["baseline"]
    if len(compass) != len(baseline):
        raise ValueError("a topic needs the same number of runs in both arms")
    return list(zip(compass, baseline))


def topic_shares(topics):
    """{topic id: share of that topic's pairs}."""
    return {name: share(_pairs(topic)) for name, topic in topics.items()}


def overall_share(topics):
    """The share over every pair of every topic."""
    return share([pair for topic in topics.values() for pair in _pairs(topic)])


def _pair_share(compass, baseline):
    if compass == 0:
        raise ValueError("a pair has a compass total of zero")
    return (compass - baseline) / compass


def pooled_within_sd(topics):
    """(sd, df): the pooled standard deviation of pair shares within topics."""
    squares, df = 0.0, 0
    for topic in topics.values():
        shares = [_pair_share(c, b) for c, b in _pairs(topic)]
        if len(shares) < 2:
            continue
        mean = sum(shares) / len(shares)
        squares += sum((s - mean) ** 2 for s in shares)
        df += len(shares) - 1
    if df == 0:
        raise ValueError("no topic has a repeated run")
    return math.sqrt(squares / df), df


def between_topic_sd(topics):
    """Sample standard deviation of the topic shares."""
    if len(topics) < 2:
        raise ValueError("the spread between topics needs two topics")
    return statistics.stdev(topic_shares(topics).values())


def _lower_gamma_regularized(a, x):
    """P(a, x), the regularized lower incomplete gamma function."""
    if x <= 0:
        return 0.0
    log_front = a * math.log(x) - x - math.lgamma(a)
    if x < a + 1:
        term = total = 1.0 / a
        n = a
        while abs(term) > abs(total) * 1e-16:
            n += 1
            term *= x / n
            total += term
        return total * math.exp(log_front)
    tiny = 1e-300
    b = x + 1 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 10000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-16:
            break
    return 1.0 - math.exp(log_front) * h


def chi_square_quantile(p, df):
    """The `p` quantile of the chi-square distribution with `df` degrees of freedom."""
    a = df / 2.0
    low, high = 0.0, max(1.0, float(df))
    while _lower_gamma_regularized(a, high) < p:
        high *= 2
    for _ in range(300):
        middle = (low + high) / 2
        if _lower_gamma_regularized(a, middle) < p:
            low = middle
        else:
            high = middle
    return 2.0 * (low + high) / 2


def sd_upper_bound(sd, df, confidence=0.8):
    """sd * sqrt(df / q), q the (1 - confidence) chi-square quantile."""
    if df < 1 or sd < 0 or not 0 < confidence < 1:
        raise ValueError("the bound needs df >= 1, sd >= 0 and a confidence inside (0, 1)")
    return sd * math.sqrt(df / chi_square_quantile(1 - confidence, df))


def batch_size(sigma_w, delta):
    """Builds per arm to see a drop of `delta` given the within-topic spread `sigma_w`."""
    if sigma_w < 0 or delta <= 0:
        raise ValueError("the batch size needs sigma_w >= 0 and delta > 0")
    exact = (Z_CONFIDENCE + Z_POWER) ** 2 * 2 * sigma_w ** 2 / delta ** 2
    return math.ceil(round(exact, 9))


def batch_plan(share_value, sd, df, relative_drop=0.10):
    """{"point", "upper"}: the batch size at the spread's estimate and at its upper bound."""
    if share_value == 0:
        raise ValueError("a relative drop of a zero share is zero")
    delta = relative_drop * abs(share_value)
    return {
        "point": batch_size(sd, delta),
        "upper": batch_size(sd_upper_bound(sd, df), delta),
    }


def bootstrap_interval(topics, *, seed, resamples=2000, confidence=0.95):
    """Percentile interval of the overall share over topics resampled with replacement."""
    names = list(topics)
    if len(names) < 2:
        raise ValueError("a bootstrap over topics needs two topics")
    pairs = {name: _pairs(topics[name]) for name in names}
    rng = random.Random(seed)
    values = []
    for _ in range(resamples):
        drawn = [rng.choice(names) for _ in names]
        values.append(share([pair for name in drawn for pair in pairs[name]]))
    values.sort()
    tail = (1 - confidence) / 2
    low = values[min(len(values) - 1, int(tail * len(values)))]
    high = values[max(0, math.ceil((1 - tail) * len(values)) - 1)]
    return low, high


def builds_per_window(seconds, window_seconds=WINDOW_SECONDS):
    """Whole builds of the mean of `seconds` that fit one window."""
    seconds = list(seconds)
    if not seconds:
        raise ValueError("no build durations")
    mean = sum(seconds) / len(seconds)
    if mean <= 0:
        raise ValueError("the mean build duration is not positive")
    return math.floor(window_seconds / mean)
