---
title: Parallel builders in one worktree share one git index, so a commit sweeps in a sibling's staged files
type: lesson
status: active
category: process
area: workflow
tags: [git, parallel-builders, worktree, staging, commit]
created: 2026-11-21
updated: 2026-11-21
score: 6
summary: "Builders sharing one worktree share one index; a sibling's commit takes your staged files under its message"
source: extract-lessons:OPP-20261122T061744619708Z
seen: [2026-11-22]
---

Two builders in the same worktree share one git index. TASK-343's staged files landed in another builder's `test(TASK-346)` commit; its own commit found nothing to commit.
`git add <file>` then `git commit` is not atomic across agents: the other agent's commit takes everything staged.
Commit with explicit paths (`git commit -m ... -- <files>`), or give each parallel builder its own worktree, and check `git show --stat HEAD` afterwards.
