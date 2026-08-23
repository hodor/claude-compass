---
title: Blinding covers the roles, the answer key, and the vault the raters read
type: lesson
status: active
category: process
area: methodology
tags: [experiments, blinding, validation, measurement, empirical]
created: 2026-08-08
updated: 2026-08-23
score: 5
summary: "Blinding fails through the answer key and the vault's own hot path, not only shared roles; verify the rater is blind"
seen: []
---

The paired seeded-defect run scored the test-design bar 15/15 against the baseline's 13/15, but the agent that read the answer key - the seeded-defect table it had to replay - is the same agent that authored the arm under test.
Replay needs the table; authoring must never see it, so one agent holding both roles leaks the outcome measure into the thing being measured, and a caveat in the writeup does not repair the number.
Blinding the runs from each other is not blinding the raters: the mandatory session-start protocol makes every agent read `index.md` and `active.md`, which named the sizing initiative and its approved decisions, so "no hint of the expected answer" was false by construction.
A control set of known answers produced by the same reasoning now under test is a circular key, not a key; run raters in a scratch vault whose hot path is silent, and verify that leak is gone rather than asserting it.
Split the roles whenever an experiment validates a mechanism this project owns - one agent authors each arm from the specs alone, a separate agent seeds the defects and scores - and until that rerun exists read the result as evidence the mechanism works as designed, never as a measured hit rate ([[RESEARCH-test-quality-bar-validation]]).
