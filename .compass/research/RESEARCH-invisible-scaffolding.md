---
title: "Invisible Scaffolding: Harness Channels, Candidate Architectures, and Two Live Experiments"
type: research
status: complete
confidence: high
area: architecture
tags: [hooks, headless, background-worker, conversation-surface, capture, observability]
created: 2026-08-24
updated: 2026-08-24
author: paper-research
summary: "detached hook-spawned workers survive on the fleet host (verified live); additionalContext reaches the model and continues the session; the block channel becomes fallback"
depends_on: ["[[SPEC-018-scaffolding-invisible-to-the-human]]", "[[RESEARCH-hermes-memory-mechanics]]"]
---

# Invisible Scaffolding

## Question

What lets Compass's scaffolding (capture, extraction, checks) run in full with zero human-conversation footprint, given a stdlib-only CLI, command hooks, and a fleet of ~40 vaults on Windows hosts?

## Method

Two researchers in parallel (harness capabilities from official docs; architecture evaluation against the vault's own precedents), then two live experiments on this machine, human-approved, because the two facts the decision turns on were undocumented. Instrumentation was marker-guarded, fired once, and was reverted immediately after observation.

## Harness facts (official docs, verified where marked)

- **`hookSpecificOutput.additionalContext` is a model-facing channel on Stop** (and PreToolUse, PostToolUse, SubagentStop, others). The `reason` of a `decision: block` renders to the human; `additionalContext` is documented as not rendering. (HIGH, docs)
- **No documented pattern for hook-spawned detached workers**; whether the harness reaps a hook's grandchildren was a genuine doc gap. (resolved by experiment 1 below)
- **Subagent spawn/completion rows and task notifications are core harness UI.** No plugin can suppress them. Anything that spawns an in-session subagent has a visible floor. (HIGH, docs)
- **Headless `claude -p` is TTY-free, inherits auth from the environment or credential store, exits non-zero with output on auth failure** - observable, not a silent hang. Background Bash tasks inside a headless run are killed ~5s after it returns, so a worker must do its work in its own process, not in a sub-background. (HIGH, docs)
- **Teammates are model-spawned only and unavailable headless**; a hook cannot originate one. (HIGH, docs)
- **No cross-session deferred-execution primitive exists**; SessionStart/SessionEnd hooks exist but any queue is ours to build - and Compass already has one, the opportunity directory. (HIGH, docs)

## Architecture evaluation (full detail in the reviewer output, distilled)

| design | verdict |
|---|---|
| A. Hook-spawned detached headless worker | **viable, now verified**; the one blocking unknown was reaped-grandchildren, resolved below |
| B. Queue-and-defer to boundaries | sound as the degradation path; staleness and may-never-fire risks make it a poor primary |
| C. Minimize the visible channel | floor is one rendered line per opportunity **if** using `decision: block`; cannot reach zero by construction |
| D. Standing daemon / cron sweep | rejected: contradicts [[compass-cli/specs/SPEC-004-mechanical-work-off-the-agent-budget]]'s no-daemon stance, highest silent-failure blast radius, and hermes's own curator chose lifecycle piggybacking over a daemon |

**Cost correction to the evaluation:** the reviewer scored A as adding a second Claude instance's cost. It does not add - it **replaces** the in-session subagent pass that runs today (~80-130k tokens per firing, observed this session). Same work, same model tier available, zero main-context tokens, zero transcript lines. A is cost-neutral against today and strictly better against north-star goal 4.

**Prior art in this vault:** [[SPEC-005-index-auto-maintained-and-mirrored-per-folder]] designed and prototyped exactly this mechanism (hook-spawned detached `claude -p`) for summaries in June; it was paused on token cost for a per-write workload, not on feasibility. Its unresolved open question - the cross-platform detach mechanism - is answered by experiment 1.

## Experiment 1: does a detached worker survive the hook? YES

Marker-guarded probe added to this session's local `capture_check.py` (human-approved; the auto-mode classifier correctly refused to let the model arm the self-instruction half without human action). On a real Stop-hook firing, the hook spawned a detached child (`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`, streams to DEVNULL, `close_fds`) that slept 20 seconds and wrote a marker.

**Result: the marker was written.** The harness does not reap hook-spawned detached grandchildren on this Windows host - the exact host class the fleet runs on. The OS-level control (same spawn from a short-lived non-hook parent) also survived.

## Experiment 2: does additionalContext reach the model invisibly? YES, and it continues the session

The human armed the second probe by running the patch script themselves. On the next Stop, the hook emitted `hookSpecificOutput.additionalContext` with a distinctive instruction and **no block decision**.

**Result:** the text reached the model as a system-reminder, the session continued without any user input, and the model complied with the embedded instruction. The docs say the channel does not render in the user transcript; nothing in the delivery contradicted that, though the model cannot see the user's screen, so non-rendering rests on the docs' claim plus the absence of any "Stop hook feedback" framing. Caveat: an invisible wake still costs a model turn - this channel is quiet, not free.

## Synthesis

The primary path exists and is verified: **the hook spawns a detached headless worker that runs the pass off-conversation entirely** - no block, no subagent row, no relay, no main-context tokens. The quiet channel (`additionalContext`) is the right **fallback** when the worker cannot run (no auth, spawn failure, worker died), replacing today's rendered block+reason. The rendered block remains only as the last resort if the quiet channel proves unreliable in practice.

Obligations any implementation inherits, from the vault's own principles:
- **Every worker run is recorded** (started/finished/failed rows): a silent absence is the defect ([[ADR-010-identity-resident-fetch-mandatory]] D-06; hermes's documented blind spot is exactly this, `try/except: pass` around its spawn).
- **A dead worker is detected**: an opportunity still open past grace with a started-row and no finished-row means the worker died; the fallback channel fires then.
- **The run lock extends to the worker**: today's lock scopes the hook only; a worker writing lessons while the main session writes the vault is a real race.
- **The worker gates stdin** per [[LESSON-hook-cli-gate-stdin-on-flag]] and logs its own stdout/stderr to a file, since nothing else will surface a crash.

## Gaps

- Non-rendering of additionalContext is docs-based plus absence of evidence; the human sees the screen and can falsify it in one glance.
- Worker cost at fleet scale is bounded by opportunity frequency (capture fires rarely by design), but no measured dollar figure exists yet; the worker's own log rows make that measurable.
- Whether harness reaping behaves the same on non-Windows fleet hosts (a few exist) is untested; the worker's started/finished rows make a silent difference visible per-host.
