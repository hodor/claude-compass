---
title: "Invisible Capture (the Detached Worker, the Quiet Fallback, the Worker Ledger)"
type: plan
status: approved
approved: 2026-08-24
confidence: medium
area: architecture
tags: [capture, hooks, headless, background-worker, observability]
created: 2026-08-24
updated: 2026-08-24
author: "orchestrator"
summary: "capture moves off the conversation into a hook-spawned detached worker, with recorded runs, dead-worker detection, a quiet fallback, and a paired live-fire acceptance"
depends_on: ["[[SPEC-018-scaffolding-invisible-to-the-human]]", "[[ADR-013-detached-worker-quiet-fallback]]", "[[RESEARCH-invisible-scaffolding]]"]
---

# Invisible Capture (the Detached Worker, the Quiet Fallback, the Worker Ledger)

## Goal

The capture pass keeps running on every due opportunity and stops occupying the human's conversation. [[ADR-013-detached-worker-quiet-fallback]] fixed the mechanism, including its plan-review amendments: the worker takes its own lock (D-06 as corrected), the worker's session must not fire the vault's own hooks (D-11), and D-08 is informational.

**This plan was revised after a two-lens adversarial review** (25 findings). The three that restructured it: the worker's spawned session would have fired the vault's own hooks and fed the capture loop its own signals; the run lock could not be shared with a minutes-long worker; and the live-fire's quality band was unmeasurable and could not fail. The review record is in `## Review findings applied`.

## Prerequisites

- [[SPEC-018-scaffolding-invisible-to-the-human]] approved 2026-08-24; [[ADR-013-detached-worker-quiet-fallback]] accepted and amended, eleven trackable decisions.
- Both live experiments recorded in [[RESEARCH-invisible-scaffolding]].
- Suite green at HEAD: `python -m pytest tests/ -q` reports `625 passed, 61 subtests passed`. `compass validate` reports `0 error(s), 6 warning(s)`, all pre-existing.

## Desired End State

- A due opportunity spawns a detached worker; the conversation shows nothing; the worker's own session runs no Compass hooks.
- Every spawn attempt exists as ledger rows written by the party that can still write them: the hook records the spawn, the worker records its own end.
- A worker that dies, a spawn that never started, and a host that cannot run workers each degrade along D-05's order, every step recorded.
- `doctor` answers "did the invisible machinery actually run" from the ledger.
- One real opportunity processed by the worker, judged against a paired in-session pass by a blind judge, before anything ships to the fleet.

## What We're NOT Doing

- **A standing daemon or cron sweep** (ADR-013 D-08).
- **Removing or weakening any capture behavior** (SPEC-018 D-01): triggers, anti-list, dedup, close contract untouched; only the execution surface moves.
- **Fleet distribution in this plan** - Later, after the live fire's band.
- **Moving other scaffolding into workers**; command hooks have no conversation footprint already.
- **Suppressing harness UI** - settled impossible by research.
- **hooks.json changes.** The recursion gate lives in the CLI commands, so the shipped hook config is untouched and fleet distribution carries no hook-migration risk.

## Constraints (all tasks)

- Every code task writes tests through the `test-design` bar and runs the full suite; manual verifications run `python plugin/cli/compass ...`.
- Every task moves work into the harness and out of agent tokens.
- The hook path never exits 2 and never blocks the turn on worker mechanics: every failure downgrades, records, and returns 0.
- New timeouts and thresholds get named config keys with defaults in `capturelib.DEFAULT_CONFIG`; an undefined criterion is a spec defect ([[LESSON-untestable-criterion-is-a-spec-defect]]).
- `compass validate` stays at 0 errors.

## Mechanism decisions this plan makes

- **New config keys:** `worker_grace_seconds: 600` (a started worker older than this with no finished row is dead), `no_headless_retry_seconds: 86400` (how long a no-headless verdict suppresses spawn attempts). Both in `DEFAULT_CONFIG`; `load_config` already defaults per-key for partial files.
- **New state fields, flat, in `DEFAULT_STATE`:** `worker_attempts: 0` (spawn deaths counted per opportunity, distinct from `reemits`, reset on open), `worker_quiet_at: null` (quiet channel emitted for this opportunity), `no_headless_at: null` (timestamp latch, expiring, cleared by any successful worker finish). Flat because `_default_state` deep-copies only `signals`; a nested dict would share one mutable across vaults in-process.
- **Ledger vocabulary:** `worker-started` (written by capture-check after a successful `Popen`, carrying pid), `worker-spawn-error` (written by capture-check when `Popen` itself raises), `worker-finished` (worker, carrying the `extracted:` line), `worker-failed` (worker, carrying reason: `lock-held` | `no-headless` | exit code + last log line), `fallback-fired` (capture-check, carrying `channel: quiet|block`). All through the existing `_log_event` shape, made public as `capturelib.read_log`/`log_event`.
- **Failure-reason branching:** `lock-held` retries on the next check without spending an attempt; `no-headless` sets the latch and goes quiet immediately; `worker-spawn-error` and a death each spend one of the two attempts (D-04).
- **The worker binary resolves through `COMPASS_CLAUDE_BIN`** (env, then the `claude_bin` key in the capture config, then PATH `claude`). The worker lock file is a JSON object `{"pid": int, "started_at": iso}` - the shape every other file this module writes uses. This makes the unittest stub deterministic and lets the live fire induce the real `no-headless` path on a scratch vault by pointing the override at a failing stub - the same code path an auth-less fleet host takes.
- **capture-check never classifies no-headless itself.** A `Popen` failure in capture-check is always `worker-spawn-error` and spends an attempt; only the wrapper, which can see the child's stderr, produces `no-headless`. Two spawn errors degrade to quiet through the ordinary ladder, so a host where the spawn itself cannot work still ends quiet without a classifier.
- **The block last resort behaves exactly as today once reached.** `REEMIT_SPACING_TURNS`, `max_reemits` and the abandon path drive repeats of the block only, unchanged. The two existing tests pinning that spacing enter the block state through the new ladder (or seed it directly in state); their spacing and abandon assertions stay identical - a sanctioned fixture-entry update, not an assertion change.
- **`worker_quiet_at` resets on open**, exactly as `worker_attempts` does.
- **Abandon defers to a live worker:** the abandon path first checks for a started row younger than `worker_grace_seconds` with no finished row and defers rather than closing, so an opportunity is never abandoned out from under a running worker.

## Phases

### Wave 1 (detailed): the worker, the ledger, the fallback, and the paired live fire

- [x] TASK-091: the worker wrapper and the ledger vocabulary - complexity: L, depends_on: none, files: [plugin/cli/commands/capture_worker.py, plugin/cli/capturelib.py, plugin/cli/commands/capture_stats.py, plugin/cli/modelslib.py, plugin/cli/maincli.py, plugin/cli/tests/test_capture_worker.py, plugin/cli/tests/test_capturelib.py], decisions: [ADR-013-detached-worker-quiet-fallback/D-02, ADR-013-detached-worker-quiet-fallback/D-03, ADR-013-detached-worker-quiet-fallback/D-06, ADR-013-detached-worker-quiet-fallback/D-07, ADR-013-detached-worker-quiet-fallback/D-09], lessons: [LESSON-hook-cli-gate-stdin-on-flag, LESSON-no-agent-bookkeeping]
  - `capturelib` gains: the two config keys and three state fields above (in `DEFAULT_CONFIG`/`DEFAULT_STATE`, so the equality-pinned state tests keep passing); public `log_event`/`read_log`; and the worker lock - `tmp/capture-worker.lock` holding pid and ISO start, stale after `worker_grace_seconds`, owner-checked release (only the pid that wrote it removes it). The hook's own 60-second mutex is untouched.
  - `compass capture-worker <opp-id>`: takes the worker lock (contention: one bounded retry after a short sleep, then `worker-failed` reason `lock-held`, exit 0); resolves the binary via `COMPASS_CLAUDE_BIN` → config → PATH; resolves the model via `modelslib.resolve("capture-worker")` - a new non-agent roster row `capture-worker: cheap`, excluded from `AGENT_FILES` the way `index-summary` is; runs the child with cwd at the project root, stdin `DEVNULL`, stdout/stderr to `.compass/tmp/worker-logs/<opp-id>.log`, and the inherited environment **plus** `COMPASS_WORKER_SESSION=1` - added, never replaced, because `CLAUDE_PROJECT_DIR` and auth must survive (ADR-013 D-11).
  - **The worker prompt, stated in full** (it is not the block reason, which addresses an orchestrator): "Run the extract-lessons skill against the opportunity directory at `<absolute path>`. You are the disposable context: do not spawn subagents. Apply the skill's full contract - triggers, anti-list, dedup against the catalog, lesson-write for survivors, audit log - and close the opportunity via `compass capture-close`. Print exactly one final line in the form `extracted: <N written, N revised, N rejected> - <phrase>`." Passed with `--output-format json` so usage (cost) is machine-readable from the log.
  - On child exit: exit 0 and the opportunity closed → `worker-finished` carrying the `extracted:` line and the reported usage; anything else → `worker-failed` with the exit code and last log line; `no-headless` when the binary is missing or the child exits nonzero within 5 seconds with an auth-shaped stderr token (`auth`, `login`, `credential`, case-insensitive) - the classifier is exact, bounded, and tested. Lock released in `finally`, owner-checked.
  - `capture_stats.KNOWN_EVENTS` gains the five new kinds; `compute_stats` counts are untouched, so existing rates do not move.
  - Args hand-parsed; never exits 2; malformed or missing opp-id refuses with exit 1 and no rows.
  - Automated verification: unittest with a stub binary via `COMPASS_CLAUDE_BIN` - the wrapper writes only end rows, never a started row; finished row on success carrying the extracted line; failed with exit code on nonzero; `no-headless` on the auth-shaped fast failure and on a missing binary; `lock-held` after contention with a live lock, and the stub never runs; a stale lock (backdated mtime) is broken and the run proceeds; owner-check: the wrapper never removes a lock another pid wrote; the exact child argv is asserted including the resolved model (the stub records argv), pinning that `--model` is never `inherit`; log file carries stub output; state's `no_headless_at` set on the no-headless path and cleared on a later success; never exits 2; `read_log` round-trips all five kinds; the state-equality pins in test_capturelib still pass.
  - Manual verification: run the wrapper by hand on a scratch opportunity with the stub and read the ledger as a story: spawn recorded by the caller, end recorded by the worker, opportunity closed.
- [ ] TASK-092: capture-check spawns, gates recursion, and orders the fallbacks - complexity: L, depends_on: TASK-091, files: [plugin/cli/commands/capture_check.py, plugin/cli/commands/capture_signal.py, plugin/cli/commands/sync.py, plugin/cli/tests/test_capture_commands.py, plugin/cli/tests/test_sync.py], decisions: [ADR-013-detached-worker-quiet-fallback/D-01, ADR-013-detached-worker-quiet-fallback/D-04, ADR-013-detached-worker-quiet-fallback/D-05, ADR-013-detached-worker-quiet-fallback/D-11, SPEC-018-scaffolding-invisible-to-the-human/D-01], lessons: [LESSON-hook-payloads-observe-before-coding]
  - **The recursion gate first (D-11):** `capture_check.run`, `capture_signal.run`, and `sync`'s `_record_write_signal` all return/skip immediately when `COMPASS_WORKER_SESSION` is set. The worker's own writes still sync the index (that part is wanted); they record no signals, bump no turns, and can never emit a block into the headless session. It ships in the same task as the spawn so no intermediate commit can loop.
  - On due, when `no_headless_at` is unset or expired: `Popen` the wrapper detached - `[sys.executable, <resolved compass script>, "capture-worker", opp_id]`, the experiment's flags on Windows, `start_new_session=True` on POSIX - then write `worker-started` with the pid. `Popen` raising writes `worker-spawn-error` instead. Nothing is printed either way; the conversation sees nothing. The hook's own mutex releases in its existing `finally`, after the spawn - the worker lock is a different lock, so there is no self-contention.
  - Fallback ladder on subsequent checks, branching on ledger rows and the reason vocabulary: finished → normal close, `worker_attempts` reset, `no_headless_at` cleared. `lock-held` → respawn next check, attempt not spent. Started with no end row past `worker_grace_seconds`, or `worker-spawn-error`, or **an open opportunity with no rows at all past the grace** (the spawn-that-never-was branch) → spend an attempt and respawn; past two attempts → `fallback-fired channel: quiet` row plus the `hookSpecificOutput.additionalContext` emission carrying the worker prompt's contract addressed to the session, `worker_quiet_at` set. Quiet emitted and still open past another `worker_grace_seconds` → `fallback-fired channel: block` row and today's `decision: block`, re-emit spacing unchanged.
  - `no-headless` (from the wrapper's row or a spawn error shaped that way) → straight to quiet, latch set; the latch expires after `no_headless_retry_seconds` and any successful finish clears it, so a host that gains auth recovers by itself.
  - The abandon path defers while a live worker is inside its grace, per the mechanism decisions.
  - `sync.py` additionally sweeps `worker-logs/*.log` older than the existing 30-day extraction-log retention (ADR-013 D-07's pruning clause, previously unowned).
  - Every capture behavior - triggers, anti-list, dedup, close contract - is untouched; only the execution surface moves (SPEC-018 D-01).
  - Automated verification: unittest - due spawns (stubbed Popen records argv) and prints nothing; recursion gate: with the env marker set, capture-check returns 0 before bumping turns, capture-signal records nothing, sync records no vault-write signal but still syncs the index (in test_sync.py); dead worker past grace respawns once and spends an attempt; zero-rows-past-grace behaves identically; `lock-held` respawns without spending; second death emits additionalContext exactly once with a `fallback-fired` quiet row and no block; still open past another grace emits the block with its `fallback-fired` row; `no-headless` goes quiet immediately, sets the latch, the next opportunity inside the TTL attempts no spawn while one after expiry does; a finish clears latch and attempts; abandon defers under a live worker and still fires when no worker rows exist and the old conditions hold; existing reemit/abandon tests pass unchanged on the block path; never exits 2; the payload-assembly rule holds - one JSON object per run, never two.
  - Manual verification: with the stub, watch one full silent cycle on a scratch vault (due → nothing printed → ledger start/finish → closed), then point `COMPASS_CLAUDE_BIN` at a failing stub and watch the same vault degrade to the quiet channel with its `fallback-fired` row.
- [ ] TASK-093: doctor reconciles the worker ledger - complexity: S, depends_on: TASK-091, files: [plugin/cli/commands/doctor.py, plugin/cli/tests/test_doctor.py], decisions: [ADR-013-detached-worker-quiet-fallback/D-10]
  - A row reading the ledger via `capturelib.read_log`: workers started/finished/failed counts, started-without-end past grace (naming the opp-id and age), fallback firings by channel, the last failure reason, and **the no-headless latch when set, with its date** - a worker path silently latched off is exactly what this row exists to surface. WARN on any of: unfinished past grace, latch set, or the last three spawns all failed; OK otherwise; never FAIL, never moves the exit code; wrapped in its own try/except like the unit-candidates row.
  - Automated verification: unittest - healthy ledger OK with counts; unfinished past grace WARNs naming the opp-id; latch set WARNs with the date; three consecutive failures WARN with the reason; corrupt log line degrades to WARN not crash; exit code untouched throughout; --json stays one object.
  - Manual verification: run doctor after the live fire and confirm the row tells the story at a glance, including that the latch line is absent on this healthy host.
- [ ] TASK-094: live fire - the worker against a paired in-session pass, judged blind - complexity: L, kind: prototype, depends_on: TASK-092, TASK-093, files: [.compass/tmp/worker-logs/], decisions: [ADR-013-detached-worker-quiet-fallback/D-01, ADR-013-detached-worker-quiet-fallback/D-03], lessons: [LESSON-blind-the-author-in-self-validation, LESSON-score-the-do-nothing-baseline-before-running, LESSON-revert-to-prove-a-regression-test]
  - **Question:** does the detached path work end-to-end with the real binary on this machine, and does a cold worker's extraction hold up against the in-session pass on the SAME opportunity?
  - **Paired, not sequential:** when the next genuine opportunity opens, copy its directory before anything processes it. The worker runs against the live one (the real path); an in-session subagent pass of today's shape runs against the copy in a scratch vault carrying the same catalog. Both produce candidate lists and verdicts.
  - **Judged blind:** a separate agent, not the orchestrator and shown neither pass's provenance, compares candidates and verdicts against the extract-lessons contract (triggers honored, anti-list applied, dedup correct) and flags disagreements. Pre-registered: the worker passes when it reaches the same write/reject verdicts on the candidates both passes surfaced and misses no candidate the in-session pass wrote. The do-nothing baseline is stated in advance: an empty window where both passes write zero is a void trial, not a pass - the comparison counts only when the in-session pass found at least one candidate.
  - **Cold-context risk is its own axis, distinct from tier:** if the worker misses candidates the in-session pass caught from session context, a tier bump is not the remedy; the remedy is enriching the opportunity evidence at capture time, and that finding goes to elaboration, not to a silent tier change.
  - **Degradation drill on the real path:** on a scratch vault, `COMPASS_CLAUDE_BIN` pointed at an auth-failing stub - the same `no-headless` code path an auth-less fleet host takes - observing latch, quiet-channel row, and recovery after clearing the override.
  - **Cost measured, not estimated:** the worker's `--output-format json` usage from the real run, recorded in the phase report - the first real cost figure for this pipeline.
  - Bands, fixed now: pass + cost at or below the in-session equivalent → the fleet task unblocks. Verdict disagreements traceable to cold context → elaboration enriches opportunity evidence and re-fires once. Tier-attributable quality failure (the blind judge says reasoning, not context, failed) → one tier bump, written to `.compass/meta/models.yaml` and recorded as an ADR-013 D-09 amendment by this task, re-fire once. Path failure anywhere → fixed in this wave. Two re-fires without a pass → the plan stops and reports rather than shipping.
  - Routes through `compass test-checkpoint record TASK-094 --not-required`.
  - Automated verification: the ledger rows, both passes' outputs, the blind judge's verdict, and the measured usage, quoted verbatim in the phase report and reproducible from the retained files.
  - Manual verification: the human confirms their conversation showed nothing during the worker's pass - the one observation only they can make.

**Pause point and elaboration step.** As before: reports, lessons, then promote from `## Later` with the delta recorded.

## Later (intent only)

- [ ] TASK-095: fleet distribution (v0.8.0) - the worker plus everything shipped since v0.7.0 - decisions: [ADR-013-detached-worker-quiet-fallback/D-05]
- [ ] TASK-096: POSIX detach verification on a non-Windows fleet host - decisions: [ADR-013-detached-worker-quiet-fallback/D-01]
- [ ] TASK-097: SessionStart pickup of opportunities left open on hosts that could never run workers - decisions: [ADR-013-detached-worker-quiet-fallback/D-05]
- [ ] TASK-098: the pipeline posture between gates - relays, consults and status lines the orchestrator still emits, audited against the outcomes-and-gates-only bar - decisions: [SPEC-018-scaffolding-invisible-to-the-human/D-02]

## Parallel-safe tasks

- **Wave 1:** TASK-091 first. TASK-092 and TASK-093 after it: file-disjoint, safe together. TASK-094 last, alone.

## Risks

- **The rendered-block last resort masks a quiet-channel failure.** The ledger's `fallback-fired` rows and doctor's channel counts make a fleet quietly living on the block channel visible.
- **Cold-context extraction quality**, named distinctly from tier; TASK-094's bands separate the two and prescribe different remedies.
- **additionalContext behavior changes in a future harness release.** The ledger shows fallback usage; the block path remains the always-works floor.
- **The no-headless classifier misfires on a transient error.** Bounded: the latch expires on its TTL, any success clears it, and doctor surfaces it with its date.

## Review findings applied

Two lenses, 25 findings, all verified before acceptance. The restructuring three: the worker's session firing the vault's own hooks (now ADR-013 D-11 and TASK-092's recursion gate); the shared run lock (ADR-013 D-06 corrected - own lock, owner-checked, grace-sized staleness); the unmeasurable live-fire band (now paired on the same opportunity, judged blind, with a stated void-trial baseline and per-axis remedies). Also folded: hook-written started rows plus a spawn-error row and a zero-rows branch; reason-vocabulary branching; the expiring no-headless latch surfaced by doctor; `fallback-fired` ledger rows; worker-log pruning ownership; the full worker prompt replacing the block-reason pointer; the model roster row with argv pinned in test; config keys for every grace; flat state fields; capture-stats vocabulary; SPEC-018 D-02 moved from decoration on the acceptance task to its own scoped Later line; the strict-gate before-image below.

## Verification of this plan

Measured 2026-08-24, before approval, from `python plugin/cli/compass` (re-run after this revision):

```
compass coverage PLAN-010-invisible-capture
summary: 12 trackable decision(s) in 2 source(s): 11 covered, 1 scoped, 0 uncovered -> PASS

compass coverage PLAN-010-invisible-capture --strict
summary: 12 trackable decision(s) in 2 source(s): 11 covered, 1 scoped, 0 uncovered -> FAIL (strict)

compass lesson-coverage PLAN-010-invisible-capture
summary: 6 cited, 0 scoped, 0 unresolvable, 3 surfaced-but-uncited (advisory) -> PASS
```

Twelve trackable, not thirteen: ADR-013 D-08's `[informational]` tag removes it from tracking, which is the tag's purpose.

The intended before-image: SPEC-018/D-02 `scoped` on TASK-098, making `--strict` FAIL now and pass only once that wave builds it - a completion gate that can actually fail.
