"""Tests for bench/overhead/spread.py: the per-part spread of a variant pilot.

Module contract the tests pin
-----------------------------
pairs(events, variant, *, stations, profile) -> dict
    events      the pilot run log's events (`build-closed` and `judged`)
    stations    stations(project) -> {"<station>|<model>": {"spawns": n, ...}}
    profile     profile(project) -> a token_profile summary, or raises
    returns {"pairs": [...], "excluded": [...]}: one pair per (topic, run)
    closed and judged in both `compass` and `variant`; a pair with a build
    that a cap stopped, or that failed, goes to `excluded` with the reason
    and both arms, never into `pairs`.
summarize(result, *, margin, drop) -> dict
    the within-topic spread of each difference, the batch sizes, the
    noninferiority verdict and the builder-review share.
render(summary) -> str   markdown, aggregates only, topics by letter.
"""

import math

import pytest

import compare
import spread
import stats

VARIANT = "compass-minus-post-tester"


def _closed(topic, arm, run, *, end="human-done", exit=0, weighted=1000.0):
    return {
        "event": "build-closed", "topic": topic, "arm": arm, "run": run, "exit": exit, "end": end,
        "weighted": weighted, "project": f"/projects/{topic}-{arm}-{run}",
    }


def _judged(topic, arm, run, met, total=10):
    return {
        "event": "judged", "topic": topic, "arm": arm, "run": run,
        "counts": {"met": met, "partly met": 0, "not met": total - met},
    }


def _stations(project):
    if "minus" in project:
        return {"tester-pre|m": {"spawns": 2}, "validator|m": {"spawns": 1, "fail": 0}}
    return {"tester-pre|m": {"spawns": 2}, "tester-post|m": {"spawns": 2, "bugs": 3}, "validator|m": {"spawns": 1}}


def _profile(project):
    return {
        "weighted": 1000.0,
        "by_agent": {
            "subagent:builder": {"sessions": 2, "session_weighted": [300.0, 300.0]},
            "subagent:builder-review": {"sessions": 2, "session_weighted": [50.0, 50.0]},
        },
    }


def _pilot_events(capped=None, failed=None):
    """Three topics, two runs per arm. `capped` and `failed` name one
    (topic, arm, run) each."""
    events = []
    met = {"t-a": (8, 7), "t-b": (6, 6), "t-c": (9, 7)}
    for topic, (full_met, variant_met) in met.items():
        for run in (1, 2):
            for arm, value, weighted in (("compass", full_met, 2000.0), (VARIANT, variant_met - (run - 1), 1500.0)):
                key = (topic, arm, run)
                end, exit = "human-done", 0
                if key == capped:
                    end, exit = "wall-time", 1
                if key == failed:
                    end, exit = "failed", 1
                events.append(_closed(topic, arm, run, end=end, exit=exit, weighted=weighted + run))
                events.append(_judged(topic, arm, run, value))
    return events


def test_a_capped_build_is_left_out_of_the_spread_and_listed():
    """Adversarial where: a pair whose variant build hit the wall-time cap
    enters the spread (its goal difference is the cap's, not the part's), is
    silently dropped without a listing, or takes its full-arm partner into
    the spread alone."""
    result = spread.pairs(_pilot_events(capped=("t-b", VARIANT, 2)), VARIANT, stations=_stations, profile=_profile)
    keys = {(p["topic"], p["run"]) for p in result["pairs"]}
    assert ("t-b", 2) not in keys
    assert len(result["pairs"]) == 5
    assert result["excluded"] == [{"topic": "t-b", "run": 2, "reason": "capped", "arms": [VARIANT]}]
    summary = spread.summarize(result, margin=0.05, drop=0.1)
    assert summary["pairs"] == 5
    assert summary["excluded"] == {"capped": 1}


def test_a_failed_build_is_excluded_with_its_own_reason():
    result = spread.pairs(_pilot_events(failed=("t-a", "compass", 1)), VARIANT, stations=_stations, profile=_profile)
    assert {(p["topic"], p["run"]) for p in result["pairs"]} == {("t-a", 2), ("t-b", 1), ("t-b", 2), ("t-c", 1), ("t-c", 2)}
    assert result["excluded"] == [{"topic": "t-a", "run": 1, "reason": "failed", "arms": ["compass"]}]


def test_a_pair_needs_both_arms_judged_and_never_pairs_with_baseline():
    """Adversarial where: a variant build pairs with the baseline arm of the
    same run, or a build with no verdict enters with a guessed share."""
    events = [
        _closed("t-a", "baseline", 1), _judged("t-a", "baseline", 1, 5),
        _closed("t-a", VARIANT, 1), _judged("t-a", VARIANT, 1, 5),
        _closed("t-b", "compass", 1), _judged("t-b", "compass", 1, 5),
        _closed("t-b", VARIANT, 1),
    ]
    result = spread.pairs(events, VARIANT, stations=_stations, profile=_profile)
    assert result["pairs"] == []
    assert {(e["topic"], e["reason"]) for e in result["excluded"]} == {("t-a", "unpaired"), ("t-b", "unjudged")}


def test_pair_differences_are_variant_minus_full():
    result = spread.pairs(_pilot_events(), VARIANT, stations=_stations, profile=_profile)
    first = next(p for p in result["pairs"] if (p["topic"], p["run"]) == ("t-a", 1))
    assert first["goal_diff"] == pytest.approx(0.7 - 0.8)
    assert first["weighted_diff"] == pytest.approx(1501.0 - 2001.0)
    assert first["stations"]["compass"]["tester-post"] == 2
    assert first["stations"][VARIANT].get("tester-post", 0) == 0
    assert first["stations"]["compass"]["tester-pre"] == 2


def test_summary_spread_batch_and_verdict_match_the_hand_computation():
    """Adversarial where: the spread pools across topics instead of within
    them (so a topic effect inflates it), the upper bound is not the 80%
    chi-square bound, or the verdict is computed over something other than
    the goal differences of the counted pairs."""
    result = spread.pairs(_pilot_events(), VARIANT, stations=_stations, profile=_profile)
    summary = spread.summarize(result, margin=0.05, drop=0.1)
    diffs = {}
    for p in result["pairs"]:
        diffs.setdefault(p["topic"], []).append(p["goal_diff"])
    squares = sum(sum((d - sum(v) / len(v)) ** 2 for d in v) for v in diffs.values())
    df = sum(len(v) - 1 for v in diffs.values())
    sd = math.sqrt(squares / df)
    assert summary["goal"]["within_sd"] == pytest.approx(sd)
    assert summary["goal"]["df"] == df == 3
    assert summary["batch"]["point"] == stats.batch_size(sd, 0.1)
    assert summary["batch"]["upper"] == stats.batch_size(stats.sd_upper_bound(sd, df), 0.1)
    every = [p["goal_diff"] for p in result["pairs"]]
    assert summary["verdict"] == compare.noninferiority(every, 0.05)
    assert summary["goal"]["mean"] == pytest.approx(sum(every) / len(every))
    assert summary["builder_review_share"] == pytest.approx(100.0 / 700.0)
    assert summary["stations"]["compass"]["tester-post"] == pytest.approx(2.0)
    assert summary["stations"][VARIANT].get("tester-post", 0) == 0


def test_a_profile_that_cannot_be_read_leaves_the_share_out_not_the_pair():
    def broken(project):
        raise OSError("no transcript")

    result = spread.pairs(_pilot_events(), VARIANT, stations=_stations, profile=broken)
    assert len(result["pairs"]) == 6
    assert spread.summarize(result, margin=0.05, drop=0.1)["builder_review_share"] is None


def test_too_few_pairs_give_no_spread_or_verdict_instead_of_raising():
    events = [
        _closed("t-a", "compass", 1), _judged("t-a", "compass", 1, 8),
        _closed("t-a", VARIANT, 1), _judged("t-a", VARIANT, 1, 7),
    ]
    summary = spread.summarize(spread.pairs(events, VARIANT, stations=_stations, profile=_profile), margin=0.05, drop=0.1)
    assert summary["pairs"] == 1
    assert summary["goal"]["within_sd"] is None
    assert summary["batch"] is None
    assert summary["verdict"] is None


def test_render_holds_aggregates_and_no_topic_id_or_path():
    result = spread.pairs(_pilot_events(capped=("t-c", "compass", 1)), VARIANT, stations=_stations, profile=_profile)
    text = spread.render(spread.summarize(result, margin=0.05, drop=0.1), result)
    for leaked in ("t-a", "t-b", "t-c", "/projects/", "project"):
        assert leaked not in text, leaked
    assert "indicative" in text
    assert "capped" in text
    assert "| A |" in text
