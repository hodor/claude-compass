---
title: "Invisible Capture (the Detached Worker, the Quiet Fallback, the Worker Ledger)"
type: plan
status: draft
confidence: medium
area: architecture
tags: [capture, hooks, headless, background-worker, observability]
created: 2026-08-24
updated: 2026-08-24
author: "orchestrator"
summary: "capture moves off the conversation into a hook-spawned detached worker, with recorded runs, dead-worker detection, a quiet fallback, and a live-fire acceptance"
depends_on: ["[[SPEC-018-scaffolding-invisible-to-the-human]]", "[[ADR-013-detached-worker-quiet-fallback]]", "[[RESEARCH-invisible-scaffolding]]"]
---

# Invisible Capture (the Detached Worker, the Quiet Fallback, the Worker Ledger)

## Goal

The capture pass keeps running on every due opportunity and stops occupying the human's conversation. [[ADR-013-detached-worker-quiet-fallback]] fixed the mechanism: a hook-spawned detached headless worker as the primary path (D-01/D-02), a recorded ledger of every run (D-03), mechanical dead-worker detection (D-04), the quiet `additionalContext` channel as fallback with the rendered block as last resort (D-05), the run lock extended to the worker (D-06), stdin gated and output logged (D-07), no daemon (D-08), small model tier (D-09), and a doctor reconciliation row (D-10).

## Prerequisites

- [[SPEC-018-scaffolding-invisible-to-the-human]] approved 2026-08-24; [[ADR-013-detached-worker-quiet-fallback]] accepted, ten trackable decisions.
- Both live experiments recorded in [[RESEARCH-invisible-scaffolding]]: detach survives a real hook on this host; additionalContext wakes the model without rendering.
- Suite green at HEAD (625 tests), `compass validate` 0 errors.

## Desired End State

- A due opportunity spawns a detached worker; the conversation shows nothing. The worker runs extract-lessons, closes the opportunity, and its run exists as ledger rows.
- A worker that dies is detected and the opportunity degrades to the quiet channel, then (only if that fails to produce a pass) to today's rendered block. Nothing is ever lost silently.
- `doctor` answers "did the invisible machinery actually run" from the ledger.
- One real opportunity on this vault processed end-to-end by the worker, observed, before anything ships to the fleet.

## What We're NOT Doing

- **A standing daemon or cron sweep** (ADR-013 D-08; SPEC-004's recorded stance).
- **Removing or weakening any capture behavior** (SPEC-018 D-01). The triggers, anti-list, dedup, and close contract are untouched; only the execution surface moves.
- **Fleet distribution in this plan.** The worker ships fleet-wide with the next version wave, after the live-fire acceptance here; hosts without auth degrade per D-05 automatically.
- **Moving other scaffolding (sync, signals) into workers.** Those are command hooks with no conversation footprint already.
- **Suppressing harness UI.** Research settled that as impossible; out of scope by spec Non-Goal.

## Constraints (all tasks)

- Every code task writes tests through the `test-design` bar and runs the full suite; manual verifications run `python plugin/cli/compass ...`, never the stale install.
- Every task moves work into the harness and out of agent tokens; a task adding an agent step a command could do is rejected at review.
- The hook path must never exit 2 and never block the turn on worker mechanics: every failure downgrades, records, and returns 0.
- `compass validate` stays at 0 errors.

## Phases

### Wave 1 (detailed): the worker, the ledger, the fallback, and the live fire

- [ ] TASK-091: the worker wrapper - `compass capture-worker <opp-id>` - complexity: M, depends_on: none, files: [plugin/cli/commands/capture_worker.py, plugin/cli/maincli.py, plugin/cli/tests/test_capture_worker.py], decisions: [ADR-013-detached-worker-quiet-fallback/D-02, ADR-013-detached-worker-quiet-fallback/D-03, ADR-013-detached-worker-quiet-fallback/D-06, ADR-013-detached-worker-quiet-fallback/D-07, ADR-013-detached-worker-quiet-fallback/D-09], lessons: [LESSON-hook-cli-gate-stdin-on-flag, LESSON-no-agent-bookkeeping]
  - The process the hook detaches. It: writes `worker-started` to the capture log; acquires the vault run lock (failure = `worker-failed` with reason `lock-held`, exit 0); resolves the worker model from the model table with the small tier as default; runs `claude -p` with the extraction prompt (the same contract the block reason carries today: run extract-lessons against the opportunity dir, close via capture-close), cwd at the project root, stdin closed, stdout/stderr to `.compass/tmp/worker-logs/<opp-id>.log`; on child exit writes `worker-finished` (exit 0 and the opportunity is closed) or `worker-failed` (any other case, with the exit code and last log line as reason); releases the lock.
  - `claude` not on PATH or exiting immediately with auth failure is a `worker-failed` with reason `no-headless`, which is what D-05's fallback keys on.
  - Args hand-parsed; never exits 2; malformed opp-id refuses with exit 1 and no rows.
  - Automated verification: unittest with a stubbed `claude` executable (a scratch script on PATH) - started+finished rows on success; started+failed with reason on nonzero exit; `no-headless` when the stub is absent; lock-held path writes failed and does not run the stub; log file created and carries the stub's output; rows are append-only via the existing capture-log helpers; never exits 2; opp-id that does not exist refuses cleanly.
  - Manual verification: run the wrapper by hand on a scratch opportunity with the stub and read the ledger rows as a story: started, finished, closed.
- [ ] TASK-092: capture-check spawns the worker and orders the fallbacks - complexity: M, depends_on: TASK-091, files: [plugin/cli/commands/capture_check.py, plugin/cli/tests/test_capture_commands.py], decisions: [ADR-013-detached-worker-quiet-fallback/D-01, ADR-013-detached-worker-quiet-fallback/D-04, ADR-013-detached-worker-quiet-fallback/D-05, ADR-013-detached-worker-quiet-fallback/D-08, SPEC-018-scaffolding-invisible-to-the-human/D-01], lessons: [LESSON-hook-payloads-observe-before-coding]
  - On due: instead of emitting the block, spawn `compass capture-worker <opp-id>` detached (the experiment's exact flags on Windows; `start_new_session=True` on POSIX) and print nothing. The conversation sees nothing.
  - Fallback ordering on the *next* checks, keyed on ledger rows for the open opportunity: started-with-finished → normal (opportunity closes, mutex clears). Started, no finished, past grace → dead worker: respawn once; two dead → emit the instruction via `hookSpecificOutput.additionalContext` (the quiet channel), marked in state. Quiet channel emitted and the opportunity still open past another grace → today's `decision: block` as last resort, re-emit spacing unchanged.
  - The worker is per-event and dies when done; nothing here schedules, polls, or persists a process (D-08). Every capture behavior - triggers, anti-list, dedup, close contract - is untouched; only the execution surface moves (SPEC-018 D-01).
  - `no-headless` failure short-circuits straight to the quiet channel without the second spawn, and remembers per-vault (a state flag) so hosts without auth do not retry the spawn every opportunity.
  - Automated verification: unittest - due opportunity spawns (stubbed Popen recorded) and prints nothing; dead worker past grace respawns once; second death emits additionalContext JSON exactly once with no block; still-open past the further grace emits the block with the existing reason text; `no-headless` skips to quiet immediately and sets the flag; the flag makes the next opportunity go quiet-first without a spawn attempt; a finished worker clears state normally; existing reemit/abandon tests pass unchanged for the block path; never exits 2; hook-mode stdin drain unchanged.
  - Manual verification: with the stub present, watch one full cycle on a scratch vault: due → silence → ledger shows started/finished → opportunity closed. Then delete the stub and watch the same cycle degrade to the quiet channel.
- [ ] TASK-093: doctor reconciles the worker ledger - complexity: S, depends_on: TASK-091, files: [plugin/cli/commands/doctor.py, plugin/cli/tests/test_doctor.py], decisions: [ADR-013-detached-worker-quiet-fallback/D-10]
  - A row from the capture log: workers started/finished/failed counts, started-without-finished (with age), fallback firings, last failure reason. WARN when any started-row is unfinished past grace or the last N spawns all failed; OK otherwise; never FAIL, never moves the exit code. Wrapped in its own try/except like the unit-candidates row.
  - Automated verification: unittest - healthy ledger reads OK with counts; an unfinished started-row past grace WARNs naming the opp-id; all-failed-recently WARNs with the reason; corrupt log line degrades to WARN not crash; exit code untouched in all cases; --json stays one object.
  - Manual verification: run doctor on this vault after the live fire and confirm the row tells the story a human needs at a glance.
- [ ] TASK-094: live fire - one real opportunity through the worker on this vault - complexity: M, kind: prototype, depends_on: TASK-092, TASK-093, files: [.compass/tmp/worker-logs/], decisions: [ADR-013-detached-worker-quiet-fallback/D-01, ADR-013-detached-worker-quiet-fallback/D-03, SPEC-018-scaffolding-invisible-to-the-human/D-02], lessons: [LESSON-hook-payloads-observe-before-coding, LESSON-revert-to-prove-a-regression-test]
  - **Question:** does the whole path work with the real `claude -p`, on this machine, on a genuine opportunity - and does the extraction quality on the small tier pass the bar the in-session pass set?
  - **Method:** install the built CLI into `.claude/`, wait for (or induce with real signals) the next due opportunity, and observe: no conversation output, ledger rows appear, worker log shows the pass, opportunity closes with the standard outcome, any lessons written pass the existing catalog checks. Then the falsification half: rename the stub... rename `claude` off PATH temporarily is not acceptable on a live host; instead induce the dead-worker path by spawning against a nonexistent opp-id fixture in a scratch vault and observing the quiet-channel degradation there.
  - **Deliverable:** the observed ledger, the worker log, the extraction outcome, and a measured token/dollar figure for one worker run - the first real cost number this pipeline has ([[RESEARCH-invisible-scaffolding]] gap). Bands, fixed now: pass quality at or above the in-session pass and cost at or below it → ship to Later's fleet task; quality below the bar on the small tier → bump D-09's tier and re-fire once; path failure anywhere → the defect is fixed in this wave, not shipped around.
  - Routes through `compass test-checkpoint record TASK-094 --not-required`.
  - Automated verification: the ledger rows and closed opportunity from the live fire, quoted verbatim in the phase report; the scratch-vault degradation observed and quoted.
  - Manual verification: the human confirms their conversation showed nothing during the pass - the one observation only they can make.

**Pause point and elaboration step.** As before: reports, lessons, then promote from `## Later` with the delta recorded.

## Later (intent only)

- [ ] TASK-095: fleet distribution (v0.8.0) - the worker, the sizing mechanism, folder-born specs, and the BOM/consolidate fixes ship together - files: [plugin/, fleet], decisions: [ADR-013-detached-worker-quiet-fallback/D-05], commit-upfront: the distribution battery is the shape every version wave runs; it waits only on TASK-094's band
- [ ] TASK-096: POSIX detach verification on a non-Windows fleet host - decisions: [ADR-013-detached-worker-quiet-fallback/D-01]
- [ ] TASK-097: SessionStart pickup of opportunities left open by a host that could never run workers - decisions: [ADR-013-detached-worker-quiet-fallback/D-05]

## Parallel-safe tasks

- **Wave 1:** TASK-091 first (092 and 093 both read its ledger row vocabulary; 093 shares the capture-log reader). TASK-092 and TASK-093 are file-disjoint and run in parallel after it. TASK-094 last, alone.

## Risks

- **The rendered-block last resort masks a quiet-channel failure.** Mitigation: the ledger records which channel fired; doctor's row surfaces fallback counts, so a fleet quietly living on the block channel is visible.
- **Worker quality on the small tier.** TASK-094's band handles it: bump the tier once, measured, before shipping.
- **additionalContext rendering behavior changes in a future harness release.** The ledger makes it visible (fallback firings with no human complaint = fine; the human seeing text = one glance falsifies), and the block path remains as the always-works floor.

## Verification of this plan

Measured 2026-08-24, before approval, from `python plugin/cli/compass`:

```
compass coverage PLAN-010-invisible-capture
summary: 12 trackable decision(s) in 2 source(s): 12 covered, 0 scoped, 0 uncovered -> PASS

compass lesson-coverage PLAN-010-invisible-capture
summary: 4 cited, 0 scoped, 0 unresolvable, 3 surfaced-but-uncited (advisory) -> PASS
```

At completion, `compass coverage PLAN-010-invisible-capture --strict` must exit 0 apart from Later's fleet/POSIX/pickup tasks, which close in their own wave.
