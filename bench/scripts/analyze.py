#!/usr/bin/env python3
"""
Aggregate per-task results from a run directory and report the Pareto front
over (success_rate, total_tokens, total_cost) for each arm.

Expected results layout under results/<run-dir>/:
  arm_compass.jsonl
  arm_baseline.jsonl

Each jsonl line:
  {
    "task_id": "...",
    "benchmark": "terminal-bench" | "swe-bench-pro" | "swe-lancer",
    "split": "ic" | "managerial" | null,
    "success": true | false,
    "score": 0.0,
    "tokens_input": int,
    "tokens_output": int,
    "tokens_cache_read": int,
    "tokens_cache_write": int,
    "wall_seconds": float,
    "model": "...",
    "turn_budget": int,
    "turns_used": int
  }
"""

from __future__ import annotations
import argparse, json, pathlib, sys
from collections import defaultdict


PRICING = {
    "claude-opus-4-7":   {"input": 15.0,  "output": 75.0, "cache_read": 1.5,  "cache_write": 18.75},
    "claude-sonnet-4-6": {"input": 3.0,   "output": 15.0, "cache_read": 0.3,  "cache_write": 3.75},
    "claude-haiku-4-5":  {"input": 0.80,  "output": 4.0,  "cache_read": 0.08, "cache_write": 1.0},
}


def cost_usd(row: dict) -> float:
    p = PRICING.get(row.get("model", ""), {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0})
    return (
        row.get("tokens_input", 0)       * p["input"]
        + row.get("tokens_output", 0)      * p["output"]
        + row.get("tokens_cache_read", 0)  * p["cache_read"]
        + row.get("tokens_cache_write", 0) * p["cache_write"]
    ) / 1_000_000.0


def load(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    n = len(rows)
    successes = sum(1 for r in rows if r.get("success"))
    tokens = sum(r.get("tokens_input", 0) + r.get("tokens_output", 0) for r in rows)
    cost = sum(cost_usd(r) for r in rows)
    wall = sum(r.get("wall_seconds", 0.0) for r in rows)
    return {
        "n": n,
        "success_rate": successes / n,
        "tokens_total": tokens,
        "tokens_per_task": tokens / n,
        "cost_usd_total": cost,
        "cost_usd_per_task": cost / n,
        "wall_seconds_per_task": wall / n,
    }


def render(summaries: dict[str, dict]) -> str:
    cols = ["arm", "n", "success_rate", "tokens_per_task", "cost_usd_per_task", "wall_seconds_per_task"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for arm, s in summaries.items():
        if s.get("n", 0) == 0:
            lines.append(f"| {arm} | 0 | (no rows) | - | - | - |")
            continue
        lines.append(
            f"| {arm} | {s['n']} | {s['success_rate']:.1%} | "
            f"{s['tokens_per_task']:.0f} | ${s['cost_usd_per_task']:.4f} | "
            f"{s['wall_seconds_per_task']:.1f} |"
        )
    return "\n".join(lines)


def pareto_judgment(summaries: dict[str, dict]) -> str:
    c = summaries.get("compass", {})
    b = summaries.get("baseline", {})
    if not c.get("n") or not b.get("n"):
        return "incomplete - need rows for both arms"
    if c["success_rate"] >= b["success_rate"] and c["cost_usd_per_task"] <= b["cost_usd_per_task"]:
        return "compass wins the Pareto front (>= success at <= cost)"
    if c["success_rate"] <= b["success_rate"] and c["cost_usd_per_task"] >= b["cost_usd_per_task"]:
        return "baseline wins the Pareto front (>= success at <= cost)"
    return "neither arm dominates - tradeoff zone"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=pathlib.Path)
    args = ap.parse_args()

    if not args.run_dir.is_dir():
        print(f"not a directory: {args.run_dir}", file=sys.stderr)
        return 2

    arms = {
        "compass":  load(args.run_dir / "arm_compass.jsonl"),
        "baseline": load(args.run_dir / "arm_baseline.jsonl"),
    }

    summaries = {arm: summarize(rows) for arm, rows in arms.items()}

    print(f"# Run: {args.run_dir.name}\n")
    print(render(summaries))
    print(f"\n**Pareto judgment:** {pareto_judgment(summaries)}\n")

    per_bench = defaultdict(lambda: defaultdict(list))
    for arm, rows in arms.items():
        for r in rows:
            per_bench[r.get("benchmark", "unknown")][arm].append(r)
    if per_bench:
        print("## By benchmark\n")
        for bench, byarm in per_bench.items():
            print(f"### {bench}")
            print(render({arm: summarize(rows) for arm, rows in byarm.items()}))
            print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
