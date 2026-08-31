---
title: A criterion you cannot source an input for is a defect in the specification, not a missing test
type: lesson
status: active
category: process
area: testing
tags: [testing, pre-build-station, acceptance-criteria, spec-defect, oracle]
created: 2026-08-23
updated: 2026-08-24
score: 6
summary: "A criterion that defines no input class cannot be tested; report the spec defect, never invent the equivalence class"
seen: [2026-08-24]
---

A plan's verification bullet asserted "a malformed name exits 1" while defining malformed nowhere - no character class, no length rule, no sample - and the pre-build tester reported the gap rather than picking a plausible class.
An invented equivalence class is invisible downstream: the test still goes red before the build, against whatever error the feature does not yet handle, then green after, certifying a rule nobody specified.
A red run therefore proves discrimination, not that the oracle's rule is real; only the criterion's source can do that, so this is the hole [[LESSON-revert-to-prove-a-regression-test]] cannot see.
When a criterion names a check it never defines, lift the rule from the implementation into the plan or stop and report - never guess it. Here it was three classes in `_check_target` (slash, backslash, leading dot), and the plan was amended.
A test-first station's most valuable output can be a defect in the specification rather than a test.
