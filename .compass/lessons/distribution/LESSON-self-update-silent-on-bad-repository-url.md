---
title: Self-update silent on bad repository URL
type: lesson
status: active
category: process
area: architecture
tags: [self-update, doctor, repository, offline, silent-failure]
created: 2026-09-14
updated: 2026-09-14
score: 5
summary: A bad repository URL in plugin.yaml makes self-update look permanently offline; doctor should verify it resolves
source: extract-lessons:agent-noted
seen: []
---

`_ls_remote` returns `None` for any unreachable repository, so `check()` reports `status: offline` whether the network is down or `plugin.yaml`'s `repository:` field is simply wrong.
Offline is intentionally unlogged (ADR-015 D-05), so a bad URL becomes a permanent, silent no-op: the install never updates again, indistinguishable from a transient outage.
`doctor` should independently verify the recorded repository resolves and flag it when it does not.
