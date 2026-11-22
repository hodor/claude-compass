---
title: Subagent worktrees fork from a stale base; builders must fast-forward to master and the orchestrator must commit between waves
type: lesson
status: active
category: process
area: workflow
tags: [worktree, subagents, parallel-builders, stale-base, orchestration, git]
created: 2026-07-24
updated: 2026-11-21
score: 5
summary: "Worktree subagents fork from the remote default branch unless worktree.baseRef is \"head\"; uncommitted files are always invisible"
seen: []
---

By default a worktree-isolated subagent forks from the pushed/remote base, missing unpushed local commits; `worktree.baseRef: "head"` forks from local HEAD (verified on 2.1.330).
Uncommitted and untracked files stay invisible to every worktree: commit each wave's output before spawning the next, or address files by absolute path.
Without `baseRef: "head"`, each builder first fast-forwards its worktree branch to master and stops loudly if named prerequisites are missing.
Direct main-checkout writes may be permission-blocked for isolated agents: build in the worktree, report a carry-back list, orchestrator copies back, runs the suite, commits.

## Record (preserved)
Surfaced by parallel builders halting on missing PLAN/ADR files that existed only uncommitted. The `baseRef` setting and the working frontmatter `isolation` came from [[RESEARCH-axis-2b-host-features-gap]] C1, C2.
