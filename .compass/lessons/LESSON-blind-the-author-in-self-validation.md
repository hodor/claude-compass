---
title: Blind the arm author when an experiment validates a mechanism you own
type: lesson
status: active
category: process
area: methodology
tags: [experiments, blinding, validation, measurement, empirical]
created: 2026-08-08
updated: 2026-08-08
score: 5
summary: "One agent that both replays the seeded defects and authors the arm under test measures itself, not the mechanism"
seen: []
---

The paired seeded-defect run scored the test-design bar 15/15 against the baseline's 13/15, but the agent that read the answer key - the seeded-defect table it had to replay - is the same agent that authored the arm under test.
Replay needs the table; authoring must never see it, so one agent holding both roles leaks the outcome measure into the thing being measured, and a caveat in the writeup does not repair the number.
Split the roles whenever an experiment validates a mechanism this project owns: one agent authors each arm from the specs alone, a separate agent seeds the defects and scores.
Until that rerun exists, read the result as evidence the mechanism works when applied as designed, never as a measured hit rate ([[RESEARCH-test-quality-bar-validation]]).
