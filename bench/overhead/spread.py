"""The per-part spread of a variant pilot: how much one removed part moves a build.

`pairs` reads a pilot run log and pairs run i of a variant arm with run i of
the full `compass` arm on the same topic. Each pair carries the difference
(variant minus full) in the share of frozen goal items met, in weighted
tokens, and the station spawns of each side read from the project's station
log. A pair in which either build was stopped by a cap or failed is left out
and listed with its reason, as is a build with no verdict or no partner. A
pair whose two builds were both stopped by the wall-time cap, each arm having
had the same time, is also kept in `capped_pairs` and summarized apart.

`summarize` gives, over the counted pairs, the mean and the pooled
within-topic standard deviation of each difference, the ablation batch size
for a drop of `drop` in the goal share at the spread's estimate and at its
upper 80% chi-square bound (`stats.batch_size`), the noninferiority verdict at
`margin` (`compare.noninferiority`), the builders' review share of builder
tokens, and the mean station spawns per build in each arm.

`render` writes the result as markdown: aggregates only, topics by letter.

    python spread.py --variant compass-minus-PART [--run-log FILE]
        [--margin 0.05] [--drop 0.1] [--private-root DIR]
"""

import argparse
import json
import math
import sys
from pathlib import Path

import compare
import pilot
import records
import stats
import token_profile

FULL = "compass"
REVIEW_KIND = token_profile.BUILDER_REVIEW_KIND
BUILDER_KIND = "subagent:builder"


def _key(event):
    return event["topic"], event["arm"], event["run"]


def _goal_share(counts):
    total = sum(int(counts.get(score) or 0) for score in compare.SCORES)
    if total == 0:
        return None
    return int(counts.get("met") or 0) / total


def _station_spawns(counts):
    """{station: spawns} summed over models."""
    out = {}
    for name, values in (counts or {}).items():
        station = name.split("|", 1)[0]
        out[station] = out.get(station, 0) + int((values or {}).get("spawns") or 0)
    return out


def _review_tokens(summary):
    """(review, builder) weighted tokens of one profile, or None."""
    by_agent = (summary or {}).get("by_agent") or {}
    review = sum((by_agent.get(REVIEW_KIND) or {}).get("session_weighted") or [])
    builder = sum((by_agent.get(BUILDER_KIND) or {}).get("session_weighted") or [])
    return review, builder


def _pair(topic, run, sides, shares, variant, stations, profile):
    review = {}
    for arm, side in sides.items():
        try:
            review[arm] = _review_tokens(profile(side["project"]))
        except (OSError, ValueError, KeyError, TypeError):
            review[arm] = None
    return {
        "topic": topic, "run": run,
        "goal_diff": shares[variant] - shares[FULL],
        "weighted_diff": sides[variant]["weighted"] - sides[FULL]["weighted"],
        "weighted": {arm: side["weighted"] for arm, side in sides.items()},
        "stations": {arm: _station_spawns(stations(side["project"])) for arm, side in sides.items()},
        "review": review,
    }


def pairs(events, variant, *, stations, profile):
    """{"pairs": [...], "excluded": [...]} of the variant against the full arm."""
    if not records.is_variant(variant):
        raise ValueError("a variant id is compass-minus- and a lower-case part name")
    closed = {_key(e): e for e in events if e.get("event") == "build-closed"}
    judged = {_key(e): e.get("counts") for e in events if e.get("event") == "judged"}
    slots = sorted({(t, r) for t, a, r in closed if a in (FULL, variant)})
    out, excluded, capped_pairs = [], [], []
    for topic, run in slots:
        sides = {arm: closed.get((topic, arm, run)) for arm in (FULL, variant)}
        if any(side is None for side in sides.values()):
            excluded.append({"topic": topic, "run": run, "reason": "unpaired",
                             "arms": [arm for arm, side in sides.items() if side is not None]})
            continue
        capped = [arm for arm, side in sides.items() if pilot._capped(side)]
        failed = [arm for arm, side in sides.items() if not pilot._finished(side)]
        shares = {arm: _goal_share(judged.get((topic, arm, run)) or {}) for arm in sides}
        if capped or failed:
            excluded.append({"topic": topic, "run": run, "reason": "capped" if capped else "failed",
                             "arms": capped or failed})
            if len(capped) == len(sides) and all(value is not None for value in shares.values()):
                capped_pairs.append(_pair(topic, run, sides, shares, variant, stations, profile))
            continue
        if any(value is None for value in shares.values()):
            excluded.append({"topic": topic, "run": run, "reason": "unjudged",
                             "arms": [arm for arm, value in shares.items() if value is None]})
            continue
        out.append(_pair(topic, run, sides, shares, variant, stations, profile))
    return {"variant": variant, "pairs": out, "excluded": excluded, "capped_pairs": capped_pairs}


def _within(values_by_topic):
    """(mean, pooled within-topic sd, df); sd and df None without a repeat."""
    every = [v for values in values_by_topic.values() for v in values]
    mean = sum(every) / len(every) if every else None
    squares, df = 0.0, 0
    for values in values_by_topic.values():
        if len(values) < 2:
            continue
        centre = sum(values) / len(values)
        squares += sum((v - centre) ** 2 for v in values)
        df += len(values) - 1
    if df == 0:
        return mean, None, None
    return mean, math.sqrt(squares / df), df


def _stats(counted, variant, margin, drop):
    by_topic = {"goal": {}, "weighted": {}}
    for pair in counted:
        by_topic["goal"].setdefault(pair["topic"], []).append(pair["goal_diff"])
        by_topic["weighted"].setdefault(pair["topic"], []).append(pair["weighted_diff"])
    out = {"variant": variant, "pairs": len(counted), "margin": margin, "drop": drop}
    for name, values in by_topic.items():
        mean, sd, df = _within(values)
        out[name] = {"mean": mean, "within_sd": sd, "df": df}
    full_weighted = sum(p["weighted"][FULL] for p in counted)
    out["weighted"]["relative"] = (
        sum(p["weighted_diff"] for p in counted) / full_weighted if full_weighted else None
    )
    out["batch"] = None
    goal = out["goal"]
    if goal["within_sd"] is not None:
        out["batch"] = {
            "point": stats.batch_size(goal["within_sd"], drop),
            "upper": stats.batch_size(stats.sd_upper_bound(goal["within_sd"], goal["df"]), drop),
        }
    out["verdict"] = None
    if len(counted) >= 2:
        out["verdict"] = compare.noninferiority([p["goal_diff"] for p in counted], margin)
    reviews = [side for p in counted for side in p["review"].values()]
    if counted and all(side is not None for side in reviews):
        review = sum(r for r, _ in reviews)
        builder = sum(b for _, b in reviews)
        out["builder_review_share"] = review / (review + builder) if review + builder else None
    else:
        out["builder_review_share"] = None
    out["stations"] = {}
    for arm in (FULL, variant):
        totals = {}
        for pair in counted:
            for station, spawns in pair["stations"][arm].items():
                totals[station] = totals.get(station, 0) + spawns
        out["stations"][arm] = {s: n / len(counted) for s, n in sorted(totals.items())} if counted else {}
    return out


def summarize(result, *, margin, drop):
    """The statistics over the counted pairs, with `equal_time` holding the
    same statistics over the pairs both of whose builds hit the wall-time cap."""
    variant = result["variant"]
    out = _stats(result["pairs"], variant, margin, drop)
    out["equal_time"] = _stats(result.get("capped_pairs") or [], variant, margin, drop)
    reasons = {}
    for item in result["excluded"]:
        reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
    out["excluded"] = reasons
    return out


def _num(value, digits=3):
    return "n/a" if value is None else f"{value:.{digits}f}"


def _letters(topics):
    return {topic: chr(ord("A") + i) for i, topic in enumerate(sorted(topics))}


def _block(summary, counted, letter):
    variant = summary["variant"]
    lines = [
        "| Topic | Run | Goal share difference | Weighted tokens difference | Full arm stations | Variant stations |",
        "|---|---|---|---|---|---|",
    ]
    for pair in sorted(counted, key=lambda p: (letter[p["topic"]], p["run"])):
        def spawns(arm):
            items = pair["stations"][arm]
            return ", ".join(f"{s} {n}" for s, n in sorted(items.items())) or "none"
        lines.append(
            f"| {letter[pair['topic']]} | {pair['run']} | {pair['goal_diff']:+.2f} | "
            f"{pair['weighted_diff']:+,.0f} | {spawns(FULL)} | {spawns(variant)} |"
        )
    goal, weighted = summary["goal"], summary["weighted"]
    lines += [
        "",
        "| Measure | Mean difference | Within-topic SD | df |",
        "|---|---|---|---|",
        f"| Goal share | {_num(goal['mean'])} | {_num(goal['within_sd'])} | {goal['df'] or 'n/a'} |",
        f"| Weighted tokens | {_num(weighted['mean'], 0)} | {_num(weighted['within_sd'], 0)} | {weighted['df'] or 'n/a'} |",
        "",
        f"- Weighted tokens of the variant against the full arm, ratio of sums: {_num(weighted['relative'])}.",
    ]
    batch = summary["batch"]
    if batch:
        lines.append(
            f"- Ablation batch for a drop of {summary['drop']:.2f} in the goal share: {batch['point']} builds per arm "
            f"at the spread's estimate, {batch['upper']} at its upper 80% bound."
        )
    else:
        lines.append("- Ablation batch: n/a (no topic has two pairs).")
    verdict = summary["verdict"]
    if verdict:
        lines.append(
            f"- Noninferiority at a margin of {summary['margin']:.2f}: {verdict['verdict']} (lower bound "
            f"{verdict['bound']:+.3f} over {verdict['pairs']} pairs), indicative at this size."
        )
    else:
        lines.append("- Noninferiority: n/a (fewer than two pairs), indicative at best.")
    lines.append(f"- The builders' review share of builder tokens: {_num(summary['builder_review_share'])}.")
    for arm in (FULL, variant):
        means = summary["stations"][arm]
        text = ", ".join(f"{s} {n:.1f}" for s, n in means.items()) or "none"
        lines.append(f"- Mean station spawns per build, `{arm}`: {text}.")
    return lines


def render(summary, result):
    """Markdown of the summary and the per-pair tables: no topic id, path or
    project name; topics are lettered in sorted order."""
    variant = summary["variant"]
    capped_pairs = result.get("capped_pairs") or []
    letter = _letters(
        {p["topic"] for p in result["pairs"]} | {p["topic"] for p in capped_pairs} | {e["topic"] for e in result["excluded"]}
    )
    lines = [
        f"{summary['pairs']} counted pairs of `{variant}` against full Compass, run i against run i "
        "of the same topic, both builds ended by the simulated human. Differences are the variant minus the full arm.",
        "",
        *_block(summary, result["pairs"], letter),
    ]
    equal = summary.get("equal_time")
    if capped_pairs and equal:
        lines += [
            "",
            f"{equal['pairs']} pairs whose two builds both hit the wall-time cap, so each arm had the same wall time; "
            "their goal share is what each arm finished by the cap.",
            "",
            *_block(equal, capped_pairs, letter),
        ]
    excluded = result["excluded"]
    if excluded:
        lines += ["", "Left out of the counted pairs:", ""]
        for item in sorted(excluded, key=lambda e: (letter[e["topic"]], e["run"])):
            lines.append(f"- topic {letter[item['topic']]} run {item['run']}: {item['reason']} ({', '.join(item['arms'])})")
    return "\n".join(lines) + "\n"


def _events(path):
    events = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--variant", required=True)
    parser.add_argument("--run-log", default=None)
    parser.add_argument("--private-root", default=None)
    parser.add_argument("--margin", type=float, default=0.05)
    parser.add_argument("--drop", type=float, default=0.1)
    args = parser.parse_args(argv)
    import topics

    private_root = Path(args.private_root) if args.private_root else topics.private_dir()
    log = Path(args.run_log) if args.run_log else pilot.run_log_path(private_root)

    def profile(project):
        return token_profile.profile_project(project, private_root, wait=False)

    def stations(project):
        return records.station_counts(project)

    result = pairs(_events(log), args.variant, stations=stations, profile=profile)
    sys.stdout.write(render(summarize(result, margin=args.margin, drop=args.drop), result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
