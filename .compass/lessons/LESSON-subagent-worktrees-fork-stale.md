---
title: Subagent worktrees fork from a stale base; builders must fast-forward to master and the orchestrator must commit between waves
type: lesson
status: active
category: process
area: workflow
tags: [worktree, subagents, parallel-builders, stale-base, orchestration, git]
created: 2026-07-24
updated: 2026-07-24
score: 5
summary: "Worktree-isolated subagents fork from a pre-session commit; without a fast-forward to master and committed prior waves, they see a world where earlier work does not exist"
seen: []
---

A worktree-isolated subagent's branch can fork from a commit predating the session, not current HEAD; relative paths inside the worktree then show a world without the plans, ADRs, or prior-wave code the task depends on.
Two-part protocol: the orchestrator commits each wave's output to master before spawning the next, and every spawned builder first fast-forwards its worktree branch to master and verifies its named prerequisites exist, stopping loudly if not.
Uncommitted files in the main checkout are invisible to every worktree; anything a subagent must read has to be committed, or addressed by absolute path into the main checkout.
Direct main-checkout writes may also be permission-blocked for isolated agents, so the reliable loop is: fast-forward worktree, build there, report a carry-back file list, orchestrator copies back, runs the suite, commits.
Surfaced by parallel builders halting on missing PLAN/ADR files that existed only uncommitted; the halt-and-report protocol caught it before any wrong-base code was written.
