---
title: Agent-Written Tests Are Measurably Good, Not Merely Numerous
type: spec
status: approved
approved: 2026-08-07
confidence: high
area: testing
tags: [testing, test-quality, tester-agent, bloat, adversarial, verification]
created: 2026-08-07
updated: 2026-08-07
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]", "[[SPEC-012-learning-loop]]"]
summary: "per-test admission bar; suite size an outcome, never a target (approved 2026-08-07)"
---

# Agent-Written Tests Are Measurably Good, Not Merely Numerous

## Problem

Compass mandates tests for every code change and tells agents to write them adversarially, but nothing defines, measures, or bounds test quality. The observable result is suites that grow without judgment: a simple task recently closed with 841 tests in its suite, and this repo's own learning-loop plan added 178 tests in a single day. Nobody can say which of those tests earn their keep.

Count is the only visible metric, so count becomes the proxy for rigor - and it is a bad proxy in both directions. A large suite can be shallow: tests that assert implementation details (breaking on every refactor while catching no bugs), tests that duplicate each other's coverage under different names, tests of the framework or the standard library, happy-path assertions restated N ways. A small suite can be strong. Today Compass cannot tell the difference, and neither can the human reading "suite green at 841" - green tells you the tests pass, not that they would fail when the code is wrong.

The costs compound: suite runtime grows on every hook and fix-loop cycle, maintenance burden grows with every refactor, review of test code becomes impossible at volume, and worst, false confidence - a wall of green from tests that cannot fail hides the defect the one missing test would have caught.

## Who is affected

- The tester agent, which has a mandate ("adversarial") but no operational definition of it, no budget, and no feedback on whether its tests can actually detect defects.
- The builder, whose fix loop runs the whole suite every cycle and pays the runtime cost of every low-value test forever.
- The validator, which reports "N tests green" as evidence while having no way to assess whether the tests constrain the implementation at all.
- The human, who cannot review hundreds of agent-written tests and is left trusting count.

## Decisions (made by the human)

- **D-01:** Every test must be really good and meaningful, or it is not written: the bar is a per-test admission criterion, not a suite-size judgment. Whatever count survives that bar is the right count - a suite is never rejected for being large or accepted for being small. (Roger, 2026-08-07.)
- **D-02:** Deep research precedes any mechanism: how to make great unit tests with AI is an open question to be answered from literature, tooling, and empirical work on our own suites - not improvised into agent prose. (Roger, 2026-08-07.)
- **D-03:** No single quality number is the gate; instruments are stationed: D-01 governs authoring, a mechanical admission filter gates, mutation analysis is an on-demand diagnostic that never blocks, and seeded defects validate the bar itself. Mutation-score thresholds, coverage-overlap test pruning, and proportionality formulas are not built - the research falsified each. (Roger, 2026-08-07, accepting [[RESEARCH-test-quality-synthesis]]'s station model.)
- **D-04:** The procedural practices are adopted: tests are authored from the task's spec/acceptance criteria rather than the builder's diff, failing tests are committed before implementation as a tamper-evident checkpoint, the fresh-context tester/builder split is retained as load-bearing, and the boundary-and-fixture criterion (exercise the exact boundary; a fixture value never equals the constant it overrides) stands beside D-01. (Roger, 2026-08-07, from [[RESEARCH-test-quality-craft-and-practice]].)
- **D-05:** The mechanism is a regression guard protecting a measured-good state, not a cleanup campaign: no retroactive fleet-wide regrading; existing suites are graded on demand, not by decree. (Roger, 2026-08-07; own-suite measurement in [[RESEARCH-test-quality-empirical]].)
- **D-06:** Measurement lives in the compass CLI off the agent token budget, Python-first; the language-agnostic core waits for a second language's evidence. (Roger, 2026-08-07.)

## Desired Outcome

Every test an agent writes clears an admission bar before it exists: it earns its place by the real defect class it can catch, and a test that cannot name one is not written. Suite size becomes an outcome of that bar, never a target in either direction. A reviewer - human or mechanical - can verify the bar was applied, and "suite green at N" stops being the report; what the suite can detect becomes the report.

## Needs (what a solution must satisfy)

- An operational per-test admission criterion agents can be held to - what a single test must demonstrate to deserve existence (the defect class it catches), what makes a suite sufficient, and the classes of test that never qualify (implementation-detail assertions, duplicated coverage, framework tests, restated happy paths).
- A way to measure it: quality must be checkable by mechanism or by cheap review, not asserted by the agent that wrote it.
- Meaningless tests are identified rather than accumulated - both at writing time (the admission bar) and in existing suites (overlap and no-defect-class detection).
- The tester and builder agents receive this as enforceable guidance, and the validator can audit against it - in the same spirit that decision coverage and lesson coverage made other invisible qualities auditable.
- Existing bloated suites can be assessed retroactively, so the fleet's accumulated tests can be graded and pruned, not just future ones.
- Works within Compass's constraints: mechanical measurement belongs in the harness/CLI off the agent token budget; language- and framework-specific where it must be, but with a language-agnostic core.

## Hypothesis (falsifiable)

If every test must clear an operational admission bar with mechanical measurement, then the meaningless-test share of new suites approaches zero while defect-detection power holds or improves - measured by seeded-defect or equivalent evaluation on before/after suites.

## Falsification criteria

- Admission-bar suites catch fewer seeded defects than the padded ones they replace.
- The admission criterion cannot be made operational - agents cannot apply it per test, or applying it degenerates into a size heuristic in either direction.
- Measurement cost (runtime, tooling, tokens) exceeds the cost of the bloat it prevents.

## Success criteria

- The research produces an evidence-backed definition and measurement approach for AI-written test quality, with confidence levels.
- On at least one real suite (this repo's 420-test CLI suite is a candidate), the mechanism grades tests and its grades survive human spot-review.
- Tester/builder/validator guidance is updated from the research, and a subsequent task's suite is demonstrably proportionate and measured.

## Non-Goals

- Choosing the mechanism now - mutation testing, seeded defects, coverage models, review rubrics are research territory (D-02).
- Reducing the testing mandate itself: every code change still gets tests; this spec is about their quality, never permission to skip them.
- Test frameworks or languages beyond what the fleet actually uses.

## Open questions (for research, after approval)

- What does the literature and tooling landscape say about measuring test suite power (mutation score, fault-seeding, behavioral coverage vs line coverage)?
- Why do AI agents overproduce weak tests, and which prompt/harness levers change that - budgets, review passes, write-tests-first, quality rubrics?
- What is the right proportionality baseline - behavior count, branch count, public-surface size?
- How is retroactive grading of an existing large suite made cheap enough to run fleet-wide?
