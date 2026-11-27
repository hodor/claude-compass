---
title: A loop runs unattended by auto-accepting increments that match the pattern the human accepted
type: lesson
status: active
category: process
area: workflow
tags: [loops, review, automation, increments]
created: 2026-11-27
updated: 2026-11-27
score: 5
summary: Run a loop unattended by script-checking each increment against the pattern the human accepted; hold only the odd ones for him
source: clone-old:20261127T194235328024Z
seen: []
---

Once the human has accepted a few increments by hand, a script checks each new one against that pattern and auto-accepts and commits it on its own.
LOOP-001's pattern: only the selected file changed, required phrases in the added lines, at most 25 lines removed, judge verdict helpful; 54 increments ran with no human stop.
Only increments that miss the pattern go to the human; he called reviewing what a script can check wasted time.
Before any push of the accepted increments, run the private-data scan against the deny-list.
