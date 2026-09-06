---
title: Behavior bugs are fixed by removing context or adding harness, not by adding prose
type: lesson
status: active
category: process
area: methodology
tags: [context-size, rules, prose, harness, token-efficiency]
created: 2026-08-09
updated: 2026-08-09
score: 5
summary: "Fix a behavior bug by removing the prose that trains it or adding a harness gate; added prose is the last resort and must be net-negative"
seen: []
---

A behavior bug's first fix is deletion: find the prose that trains or permits the behavior and remove it (a double-ask lived in a skill's extra unowned checkpoint, not in a missing rule).
Second is harness: a hook, CLI gate, or mechanical check enforces what instructions only request.
Prose is last, and any addition compresses its surroundings to net-negative tokens - every rule line loads into every session forever.
