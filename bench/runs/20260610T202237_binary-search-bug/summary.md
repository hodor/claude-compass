# Smoke run: binary-search-bug

**Fixture:** off-by-one in `binary_search` (`lo = mid` should be `lo = mid + 1`); the bug causes an infinite loop when `target > max(arr)`.
**Date:** 2026-06-10T20:22:37Z
**Both arms:** spawned via Claude Code `Agent` tool, `general-purpose` subagent_type, same prompt task, only the system context differs.

## Results

| Arm | Success | Tokens | Tool uses | Wall (s) |
|---|---|---|---|---|
| baseline | yes (5/5) | 21,696 | 4 | 23.9 |
| compass  | yes (5/5) | 22,619 | 4 | 28.5 |
| delta    | tie      | +4.3% | tie | +19.3% |

## Pareto judgment

Tie on outcome, baseline wins cost and time. On this fixture the methodology context cost ~4% more tokens and ~5 seconds longer with no quality difference.

## What this fixture does and doesn't measure

This task is a 1-line bug fix with a clear bug signature (test timed out → infinite loop → off-by-one is the most common cause of infinite loops in binary search). The diagnosis is essentially free once you read the test failure. Methodology can't help with what you can already see.

This fixture confirms the harness works end-to-end and that the methodology context does not produce *runaway* overhead - 4% is reasonable. It does NOT measure the cases where Compass should actually win: multi-step tasks with ambiguity, edge-case-heavy features, multi-file changes where planning catches what diving in misses.

## Per-arm transcripts (process delta)

Both arms made the same 1-line fix. The compass arm's report was more structured (separate fields for "spec inferred", "root cause diagnosis", "minimal change") while the baseline arm's report bundled them. On a problem this simple, the structure adds nothing the diff doesn't already show.

## Next fixture to build

A multi-step task with edge cases where methodology has room to matter. For example: "Implement `merge_sorted_lists(a, b)` and tests. The function must handle empty inputs, duplicates, mixed types." Baseline likely dives in without enumerating edge cases; compass arm's spec phase might surface them up front. That's the comparison that would discriminate.
