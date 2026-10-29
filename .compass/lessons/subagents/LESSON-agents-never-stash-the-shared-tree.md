---
title: Agents never stash or reset a tree the human also edits
type: lesson
status: active
category: process
area: workflow
tags: [git, stash, subagents, tester, uncommitted-work]
created: 2026-10-29
updated: 2026-10-29
score: 5
summary: "A subagent that runs git stash in a shared checkout reverts the human's uncommitted files; brief agents to never stash, reset or checkout there"
source: extract-lessons:PLAN-024-wave-4
seen: []
---

A pre-build tester ran `git stash` to get a clean baseline and reverted the human's uncommitted `.obsidian/app.json` (PLAN-024 wave 4); only the stash let it be restored.
The human's working tree holds edits no commit records. Stash, reset, checkout and clean destroy or hide them.
Brief testers and builders to compare against a commit or a worktree instead, and to leave uncommitted files untouched.
