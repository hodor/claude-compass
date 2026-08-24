---
title: "Capture Runs in a Detached Worker; the Quiet Channel Is the Fallback; Every Run Is Recorded"
type: decision
status: accepted
confidence: high
area: architecture
tags: [hooks, headless, background-worker, capture, conversation-surface, observability]
created: 2026-08-24
updated: 2026-08-24
author: "orchestrator"
summary: "the Stop hook spawns a detached headless worker for the extraction pass; additionalContext replaces the rendered block as fallback; worker runs are logged and reconciled"
depends_on: ["[[SPEC-018-scaffolding-invisible-to-the-human]]", "[[RESEARCH-invisible-scaffolding]]", "[[SPEC-012-learning-loop]]", "[[ADR-010-identity-resident-fetch-mandatory]]"]
---

# Capture Runs in a Detached Worker; the Quiet Channel Is the Fallback; Every Run Is Recorded

## Context

[[SPEC-018-scaffolding-invisible-to-the-human]] rules that the scaffolding stays and is hidden (D-01), and that agents run the pipeline without drafting the human between gates (D-02). [[RESEARCH-invisible-scaffolding]] verified the two facts the design turns on, by live experiment on the fleet's own host class: a detached process spawned from a real Stop hook survives the hook's exit, and `hookSpecificOutput.additionalContext` on Stop reaches the model and continues the session without rendering a block.

## Decision

- **D-01:** On a due capture opportunity, the Stop hook spawns a **detached headless worker** (`claude -p`, detached process group, streams to its own log file) that runs the extract-lessons pass against the opportunity directory. The main conversation is never drafted: no block, no subagent row, no relay.
- **D-02:** The worker **replaces** the in-session subagent pass; it does not add to it. Same work, zero main-context tokens, zero transcript lines. It runs the same skill contract, closes the opportunity via `capture-close`, and its final one-line summary goes to the capture log, not the conversation.
- **D-03:** **Every worker run is recorded** in the capture log: `worker-started` at spawn (written by the hook), `worker-finished` or `worker-failed` (written by the worker). A zero-failure log with zero finishes is read as breakage, never health.
- **D-04:** **A dead worker is detected mechanically.** An opportunity still open past the existing grace with a started-row and no finished-row is a dead worker; the next `capture-check` fires the fallback instead of respawning forever. Respawn at most once; two dead workers on one opportunity go to the fallback channel.
- **D-05:** The **fallback channel is `additionalContext`, not the rendered block.** No auth, spawn failure, or dead workers: the hook emits the instruction through the quiet channel, which wakes the model without rendering. The `decision: block` path is retained in code as last resort only, behind the quiet channel failing to produce a pass.
- **D-06:** The **run lock extends to the worker.** The worker acquires the same per-vault lock family the hook uses before writing lessons; the main session's own writes and the worker's cannot interleave on catalog or index. Lock acquisition failure is a recorded `worker-failed` reason, not a hang.
- **D-07:** The worker **gates stdin closed**, per [[LESSON-hook-cli-gate-stdin-on-flag]], and writes stdout/stderr to `.compass/tmp/worker-logs/<opp-id>.log`, pruned on the existing log-retention schedule.
- **D-08:** **No standing daemon and no cron.** The worker is per-event: spawned by the hook, dies when done. [[compass-cli/specs/SPEC-004-mechanical-work-off-the-agent-budget]]'s no-daemon stance holds; hermes's curator precedent agrees.
- **D-09:** The worker runs on the **cheapest model tier that passes the extraction quality bar**, configured through the model-resolution table ([[ADR-008-model-resolution-table]]), defaulting to the small tier.
- **D-10:** `doctor` gains a row reconciling the capture log's worker rows: started-without-finished counts, fallback firings, and the last worker failure reason. The invisible machinery stays auditable on demand.

## Rationale

The design was constrained to zero visible footprint with nothing removed. Only a worker outside the session reaches zero: anything in-session renders a subagent row (core UI, unsuppressible), and the block channel renders its reason by contract. The single fact that made the worker safe to choose - the harness not reaping hook grandchildren - was undocumented, so it was observed live rather than assumed, and the quiet-channel fallback was likewise observed reaching the model without a rendered block.

D-03/D-04/D-10 exist because hermes's structurally identical background pass has a documented blind spot - `try/except: pass` around the spawn, no trace distinguishing "ran, found nothing" from "never ran" - and [[ADR-010-identity-resident-fetch-mandatory]] D-06 already rules that a silent absence is a defect. The invisible version of the machinery must be more observable than the visible one was, not less, because nobody will notice its failure by scrolling past it.

D-02 corrects a mis-scoring in the research's candidate table: the worker is cost-neutral, not additive, because it replaces a pass of the same size that today runs inside the session.

## Consequences

The human's conversation carries zero capture scaffolding in the normal path. The pass still runs on every due opportunity, closes it, and writes the same lessons.

A second Claude process runs occasionally on the host. Its cost equals the subagent pass it replaces, on a smaller tier; its log rows make the real cost measurable for the first time.

The fallback preserves the guarantee: if workers cannot run at all on a host (no credentials in the environment), capture degrades to the quiet channel - one invisible wake per opportunity - and only past that to today's rendered block. Nothing is lost on any host.

Fleet distribution note: hooks.json changes ship to every vault; hosts differ in auth availability. The worker path self-disables cleanly where `claude` cannot run, by D-05's fallback order.

## Alternatives Considered

**Queue to session boundaries only.** No new mechanism, but evidence goes stale and an abandoned repo never fires; kept as the degradation inside D-05's ordering, rejected as primary.

**Minimize the block channel.** Floor is one rendered line per opportunity; the spec's desired outcome says routine machinery costs nothing. Kept only as D-05's last resort.

**Standing per-machine sweeper.** Rejected outright: contradicts the recorded no-daemon stance, needs per-OS scheduler infrastructure Compass has never shipped, and is the highest-blast-radius silent-failure shape.
