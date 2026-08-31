---
title: Bloat and holes coexist; suite size is not coverage evidence
type: lesson
status: active
category: process
area: testing
tags: [testing, test-review, coverage, suite-size, empirical]
created: 2026-08-08
updated: 2026-08-08
score: 5
summary: "44 tests for two behaviors carried mass redundancy and two critical holes at once; a delete list is half a review"
seen: []
---

A feature promising two behaviors carried 44 tests, and the review that found the bloat found two critical holes in the same pass: a helper deletable with the whole suite still green, and the input type production actually passes never exercised.
Per-case authoring inflates the count while spending the attention that behavior enumeration would have spent on what is uncovered, so a high test-per-behavior ratio predicts holes rather than ruling them out.
The paired bar experiment shows the same shape from the other side: 77 bar-authored tests caught 15/15 seeded defects where 109 undirected ones caught 13/15.
Audit both axes in one pass, and never read suite size as coverage evidence in either direction.
