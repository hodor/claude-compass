---
title: "Completed Tasks Are Swept from active.md by compass sync, Wholesale by Section, into archive/done.md"
type: decision
status: accepted
confidence: high
area: methodology
tags: [active-tasks, hot-path, sweep, sync, token-budget, archive]
created: 2026-08-28
updated: 2026-08-28
author: "orchestrator"
summary: "sync gains a sweep step: done task lines leave active.md mechanically on every sync, whole sections move when fully done, records land verbatim in archive/done.md, validate warns on drift"
depends_on: ["[[SPEC-019-active-holds-only-active-work]]", "[[RESEARCH-active-set-prior-art]]", "[[compass-cli/specs/SPEC-004-mechanical-work-off-the-agent-budget]]"]
---

# Completed Tasks Are Swept from active.md by compass sync

## Context

[[SPEC-019-active-holds-only-active-work]]: nothing removes a done task from `active.md`, so the hot path pays for history on every turn. [[RESEARCH-active-set-prior-art]] surveyed Claude Code, hermes-agent, and classic open source: the dominant proven shape is flag-then-sweep (Taskwarrior legacy gc, todo.txt AUTO_ARCHIVE, hermes cron), membership is always decided by a flag check and never by an intelligence, history always survives in a colder store, and the sweep must be mechanically guaranteed - the systems that rely on a consumer remembering (zombie reaping, org-mode manual archive) are the ones that accumulate cruft. Compass already owns a guaranteed zero-token trigger: the PostToolUse hook runs `compass sync` on every vault write, and its stdout never reaches model context.

## Decision

Flag-then-sweep, implemented inside `compass sync`. The generated-view alternative (active.md derived from plan files) was rejected: active.md legitimately carries initiative prose and ad-hoc tasks that live in no plan, so deriving it would either lose them or demand a second authoring surface.

- **D-01: The `[x]` checkoff is the flag; `compass sync` is the sweep.** Builders keep checking tasks off in `active.md` exactly as today; every sync run (hook-fired on any vault write, or invoked directly) reaps them. No new agent step, no new hook entry, zero agent tokens.
- **D-02: A done item is a top-level `- [x]` line plus its indented block, with no unchecked descendant.** A `[x]` parent with a `[ ]` child is not done and is not touched. Fenced code is never parsed as tasks.
- **D-03: A section whose every task is done moves wholesale** - heading, prose, tasks - preserving initiative context in the record. A mixed section loses only its done item blocks; its prose and open tasks stay.
- **D-04: Records land verbatim in `.compass/archive/done.md`**, appended under a per-day heading with their source section named. Markdown and wikilinks survive unmodified; removal is relocation, never destruction. `archive/` is already outside artifact scanning, so done.md joins no index and no catalog.
- **D-05: `compass validate` warns (`active_done`) when active.md still holds done items** - drift detection for writes that bypassed the hook. Warning only, never the exit code.
- **D-06: Sweep is also callable alone as `compass sweep`** with a dry-run default and `--apply`, for inspection and for vaults where a human wants to see what would move.
- **D-07: Membership is never judged.** The sweep reads checkbox state, indentation, and headings - no dates, no heuristics, no model. What the sweep cannot classify mechanically, it leaves in place.

## Consequences

- `active.md`'s size tracks work in flight; this vault drops ~2,600 hot-path tokens paid on every agent turn.
- The `## Shipped` convention retires: its rows are exactly what done.md now holds.
- A builder's post-checkoff read of active.md no longer finds the `[x]` line; "task closed" is verified by its absence from active.md (and presence in done.md), and builder/build docs say so.
- An agent editing active.md concurrently with a sweep can hit a stale-anchor Edit failure and must re-read - the same, already-accepted hazard sync's index rewrites have.
