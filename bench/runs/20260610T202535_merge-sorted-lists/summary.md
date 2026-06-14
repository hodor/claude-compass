# Smoke run: merge-sorted-lists

**Fixture:** implement `merge_sorted_lists(a, b)` against a 9-test spec covering empties, duplicates within and across, negatives, long lists, no-mutation, and ValueError on unsorted input. The prompt deliberately did NOT enumerate the edge cases - only the test file did, so "reading the tests first" was the discriminator.

**Date:** 2026-06-10T20:25:35Z

## Results

| Arm | Success | Tokens | Tool uses | Wall (s) |
|---|---|---|---|---|
| baseline | yes (9/9) | 22,495 | 5 | 33.5 |
| compass  | yes (9/9) | 23,580 | 4 | 33.1 |
| delta    | tie       | +4.8% | -20% | -1.2% |

## Pareto judgment

Tie on outcome, compass arm used one fewer tool call at marginal extra token cost, wall-time tie. Neither arm dominates.

## What this fixture revealed

Both arms read the test file before writing the implementation, extracted the full contract (including no-mutation and ValueError-on-unsorted), and wrote correct implementations on first try. The compass arm's report explicitly enumerated 9 behaviors; the baseline arm's report summarized in one sentence but the IMPLEMENTATION caught the same edge cases anyway.

This tells us something important: at the level of a competent frontier-model agent, "tests are the spec" is already the default behavior. Compass methodology context is encoding a practice the model already follows. The discrimination signal is therefore zero on tasks where the tests are well-written.

## Implication

To discriminate Compass methodology from baseline, the fixture must have one of these properties:
1. The spec is ambiguous and NOT fully captured by tests - so Compass's "interview" or "research" patterns would gather info baseline misses.
2. Multi-file changes where ordering and dependency matters - so planning matters more than implementing.
3. Edge cases that the agent must SURFACE (because tests don't yet exist) rather than satisfy (because tests already specify them).
4. Tasks long enough that Compass's task decomposition would prevent the baseline from getting lost mid-task.

Single-function bug-fix and single-function feature-implementation against test-driven specs are insufficient to discriminate. Both fixtures so far have shown this.

## Recommendation

Stop adding more single-function smoke fixtures. Either:
- Build a multi-file fixture with ambiguous spec (e.g., "implement a small REST API with caching - here's the user story, no tests provided up front") OR
- Graduate to Terminal-Bench's actual tasks, which are multi-step terminal workflows with non-trivial planning, and run that via the Agent tool pattern we just verified works.

Both arms passing 9/9 with similar cost on a designed-to-discriminate fixture is itself a finding: the Compass methodology overhead is bounded (~5% tokens) and doesn't degrade outcomes. That's a Pareto-neutral result, useful as a floor.
