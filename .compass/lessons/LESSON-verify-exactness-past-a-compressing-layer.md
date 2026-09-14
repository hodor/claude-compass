---
title: Verify exact text past a compressing layer before judging it
type: lesson
status: active
category: process
area: methodology
tags: [verification, headroom, compression, bash-output, exactness]
created: 2026-09-14
updated: 2026-09-14
score: 5
summary: "Headroom-compressed Bash output can drop words; verify exact text via Read or grep before judging it"
source: "extract-lessons:OPP-20260914T005941901328Z"
seen: []
---

Bash output relayed through the headroom compression layer stripped articles from an awk excerpt of a rules file, changing its apparent meaning.
Why: compression optimizes for token count, not exactness, so a dropped word can silently invert what a rule says.
Verify text read through headroom or another compressing layer with the Read tool or a grep on the raw file before judging it.
