---
title: "Test a delimiter-bounded block rewriter with content that quotes the delimiter"
type: lesson
status: active
category: process
area: testing
tags: [testing, delimiters, markers, adversarial, block-rewrite]
created: 2026-10-29
updated: 2026-10-29
score: 5
summary: "Code that rewrites a span between marker lines must be tested with content quoting the marker; first-occurrence find cuts or duplicates text"
source: "extract-lessons:phase:OPP-20261029T034655427631Z"
seen: []
---

Marker or fence text can appear inside the content a block holds (a code fence, a user addition).
A first-occurrence `find` then ends the block early: shipped tail is cut, or each rerun duplicates text.
Plan 026 hit this twice in one phase (overlay marker, rules end fence); the post-build tester caught both.
Write the quoted-delimiter test pre-build, and rerun the block rewrite 3 times to check idempotence.
