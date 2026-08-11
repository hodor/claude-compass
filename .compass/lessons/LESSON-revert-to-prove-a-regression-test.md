---
title: Revert the fix to prove a regression test discriminates
type: lesson
status: active
category: process
area: testing
tags: [testing, regression-tests, revert-check, bug-reports, empirical]
created: 2026-08-08
updated: 2026-08-11
score: 5
summary: "A test that passes without the change under test is unwritten; prove it per test, by revert after the fix or by the red run before it"
seen: []
---

Twenty-three tests written for three field-reported bugs; re-run against a reverted copy of the fix, 16 failed, 7 passed both, and two of those seven were provably vacuous.
One asserted the catalog "parses cleanly" through the tolerant regex reader that never looks at the corrupted header instead of the strict parser that rejects it; the other pinned itself to the reporter's literal repro, which resolves fine for a single file - the real defect only fires on a name collision.
A bug report names a symptom, not the mechanism, and an oracle borrowed from lenient production code cannot see the damage it was written to catch; neither failure is visible from a green run.
The pre-build station buys the same discrimination for free, but only read per test: a suite authored against an existing module is mostly green at its own red run (40 tests, 3 failures), and a checkpoint storing that run as one opaque artifact lets the other 37 ride the post-build "now passes" verify as passengers.
Read the red run per test, or revert the fix on a scratch copy, and treat every test that passes without the change under test as unwritten until it discriminates.
