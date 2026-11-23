---
title: A session with --plugin-dir that then runs /compass:setup registers every hook twice
type: lesson
status: active
category: domain
area: devops
tags: [hooks, plugin-dir, setup, double-registration, install-drift]
created: 2026-11-04
updated: 2026-11-04
score: 5
summary: "--plugin-dir plus /compass:setup in one session registers each hook twice and lists skills twice; capture-check and sync run twice per event"
source: extract-lessons:OPP-20261104T082508961360Z
seen: []
---

Loading Compass with `--plugin-dir` registers the plugin's hooks.json; `/compass:setup` then merges the same hooks into `.claude/settings.json`, so each hook is registered twice and both `compass:*` and project skills are listed.
`compass capture-check` and `compass sync` then run twice per event until the session restarts.
Use one install path per session: `--plugin-dir` alone, or setup alone; restart after running setup under `--plugin-dir`.
