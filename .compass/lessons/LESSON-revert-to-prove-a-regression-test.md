---
title: Revert the fix to prove a regression test discriminates
type: lesson
status: active
category: process
area: testing
tags: [testing, regression-tests, revert-check, bug-reports, empirical]
created: 2026-08-08
updated: 2026-08-08
score: 5
summary: "A regression test that still passes on the reverted fix is vacuous; revert and re-run every new test before shipping"
seen: []
---

Twenty-three tests were written for three field-reported bugs; re-run against a reverted copy of the fix, 16 failed and 7 passed both, and two of those seven were provably vacuous.
One asserted the catalog "parses cleanly" through the tolerant regex reader that never looks at the corrupted header instead of the strict parser that rejects it; the other pinned itself to the reporter's literal repro, which resolves fine for a single file - the real defect only fires on a name collision.
A bug report names a symptom, not the mechanism, and an oracle borrowed from lenient production code cannot see the damage it was written to catch; neither failure is visible from a green run.
Revert the fix on a scratch copy, re-run the new tests, and treat every test that still passes as unwritten until it discriminates.
