---
title: Self-update correction logic shipped in version N runs under the N-1 updater
type: lesson
status: active
category: process
area: architecture
tags: [self-update, cli, versioning, migration, bootstrap]
taxonomy_hint: "distribution"
created: 2026-08-31
updated: 2026-08-31
score: 5
summary: "Self-update correction logic shipped in version N runs under the N-1 updater; it first fires on the following update"
source: "extract-lessons:signal-OPP-20260831T013154672389Z"
seen: []
---

compass update runs its correction functions (e.g. `_normalize_flat_specs` in `self_update.py`) using the CLI code already installed on disk.
A correction shipped in version N cannot run during the update that installs N; that run is still executing N-1's code.
It first fires on the update after N, so a vault jumping several versions in one run gets newer normalizations one cycle late.
