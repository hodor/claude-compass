---
title: "active.md Holds Only Active Work"
type: spec
status: approved
approved: 2026-08-28
confidence: high
area: methodology
tags: [hot-path, active-tasks, token-budget, vault-hygiene, harness, cache]
created: 2026-08-28
updated: 2026-08-28
depends_on: ["[[compass-cli/specs/SPEC-004-mechanical-work-off-the-agent-budget]]", "[[SPEC-003-hierarchical-vault-organization]]"]
summary: "completed work accumulates in active.md forever because nothing in the harness moves it out; the hot path pays for history on every turn (approved 2026-08-28)"
aliases: ["SPEC-019-active-holds-only-active-work"]
---

# active.md Holds Only Active Work

## Problem

`active.md` is a hot-path file: every session, every builder, every validator loads it on every spawn. Its contract is "current tasks" - yet nothing in Compass ever removes a task from it. The whole pipeline only adds and checks off in place:

- The builder marks tasks `[x]` in `active.md` and stops there.
- `/compass:build` and `/compass:autopilot` verify the checkoff happened, nothing more.
- `compass sync` rebuilds index and tag-index on every vault write but never touches `active.md` beyond counting its tokens.
- `checkup` flags stale and inconsistent tasks, not accumulated done ones.
- The only backpressure is the aggregate hot-path cap warning, which fires late, names file sizes without saying what to prune, and routes to `/compass:consolidate` - which only operates on lessons.

So completed work leaves `active.md` only when a human or an agent volunteers to compact it. In practice nobody does: this vault's `active.md` carries 27 `[x]` lines out of 29, back to PLAN-001 (2026-05-24), costing 2,606 tokens of a 5,000-token hot path that is currently at 10,172 - and every one of those tokens is paid again on every agent turn, in every session, forever.

**Motivating datum** (pinned per [[LESSON-pin-the-motivating-datum]]): this repo, `.compass/active.md` at commit cb2c467, measured 2026-08-28 during a session on the fleet host; hot-path marker read `10172 / 5000 tokens (index.md 4509, active.md 2606, meta/lessons-catalog.yaml 3057)`.

## Desired Outcome

`active.md` contains only work that is active right now. Specifically:

- A task that completes leaves `active.md` as part of completing, not as a separate chore someone must remember. Departure is as automatic as the checkoff is today.
- Removal costs no agent tokens and no human attention - mechanical work belongs to scripts and hooks ([[compass-cli/specs/SPEC-004-mechanical-work-off-the-agent-budget]]).
- Nothing is lost. Completed work remains findable with its outcome summary - the record moves, it does not vanish. A next session can still answer "what shipped and where is its detail" without `active.md` carrying it.
- The invariant is enforced, not aspirational: drift (done lines lingering in `active.md`) is detected by the harness, not discovered by a human reading a bloated file.
- The hot path stops paying a permanent, growing tax for history; `active.md`'s size tracks work in flight, not project age.

## Non-Goals

- Shrinking `index.md` or the lessons catalog - the other two hot-path components have their own caps and responders.
- Changing what counts as a task or how tasks are planned, distributed, or checked off.
- A general archival policy for the whole vault; this spec is about the `active.md` contract only.
