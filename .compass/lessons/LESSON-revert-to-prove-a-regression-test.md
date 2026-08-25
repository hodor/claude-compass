---
title: Revert the fix to prove a regression test discriminates
type: lesson
status: active
category: process
area: testing
tags: [testing, regression-tests, revert-check, bug-reports, empirical]
created: 2026-08-08
updated: 2026-08-24
score: 6
summary: "A test or fix that passes without discriminating the change under test is unwritten; prove it by revert or red run"
seen: [2026-08-23]
---

A test that passes without the change under test is unwritten, and a fix whose own tests pass is unproven the same way - both need the same revert to discriminate.
Twenty-three tests for three bugs: reverted, 16 failed and 7 passed both, two of those seven provably vacuous (an oracle borrowed from the lenient reader, a repro too narrow to hit the defect).
A catalog-corruption fix separately passed its own tests yet fixed nothing - the real cause was a BOM, not the CRLF the fix targeted.
A bug report names a symptom, not the mechanism; neither failure is visible from a green run.
Read the red run per test, or revert the fix on a scratch copy, and treat anything that passes without the change under test as unwritten until it discriminates.
