---
title: Verify code-wiring claims by grepping call sites, not the definition
type: lesson
status: active
category: process
area: methodology
tags: [code-reading, verification, call-sites, confidence, research]
created: 2026-09-13
updated: 2026-09-13
score: 5
summary: "A confident claim that a predicate or flag is wired up can be wrong from reading only its defining module; grep every call site first"
source: "extract-lessons:OPP-20260913T214949623748Z"
seen: []
---

Two SPEC-023 researchers reached opposite high-confidence conclusions on whether STORM's `is_valid_source` predicate was ever wired up, because each read a different module of the same repo.
One `grep -rn` for the predicate's name across the whole cloned repository settled it: the predicate is defined but no call site ever passes it, so it is dead code.
Why: reading the function that defines a seam proves the seam exists, never that anything calls it; only a repo-wide call-site search proves wiring.
