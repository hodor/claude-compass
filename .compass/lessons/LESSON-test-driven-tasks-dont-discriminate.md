---
title: Test-driven single-function tasks cannot discriminate methodology layers
type: lesson
status: active
category: process
area: workflow
tags: [benchmarks, evaluation, bench-design, frontier-models, methodology-eval]
created: 2026-06-10
updated: 2026-06-10
score: 5
summary: "When tests fully encode the spec, frontier models already read-tests-first; methodology can't be measured on such tasks"
seen: []
---

On tasks where the test suite fully encodes the spec, frontier-model agents already read tests first by default.
A methodology layer that prescribes "tests are the spec" cannot show measurable benefit when the agent already does that without instruction.
Smoke runs on a bug-fix fixture and a feature fixture with 9 edge-case tests both gave tie outcomes with about 5% token overhead for the methodology arm.
Discriminating fixtures need one of: ambiguous spec not in tests, multi-file scope where ordering matters, or absent test suite forcing the agent to surface edge cases rather than satisfy prewritten ones.
The Pareto-neutral result is itself useful as a floor: Compass methodology overhead is bounded around 5% tokens with no quality regression on test-driven tasks.
