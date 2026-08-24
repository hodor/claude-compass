---
title: Active Tasks
updated: 2026-08-23
---

# Active Tasks

Completed initiatives are one line each; their detail lives in the named plan.

## Shipped

- [x] [[PLAN-001-lessons-and-index-implementation]] - 12 tasks (2026-05-24)
- [x] [[PLAN-002-compass-cli-implementation]] - CLI + command-hook cutover, ~99.8% bookkeeping-token reduction (2026-06-14)
- [x] [[PLAN-003-hybrid-hierarchy]], [[PLAN-004-decision-coverage]], [[PLAN-005-model-table]] - 23/23 tasks, validator BATCH PASS (2026-07-24)
- [x] [[PLAN-006-learning-loop]] - v0.5.0, 16 tasks, VALIDATED 9/9 probes, fleet-wide 2026-08-06. Root cause found en route: hooks load only from settings files ([[LESSON-hooks-load-only-from-settings]]), so no Compass hook had ever fired anywhere before that date.
- [x] [[PLAN-007-test-quality]] - v0.6.0-v0.6.3, 12 live tasks (Phase C parked behind named unpark triggers). The paired experiment validated the bar: Arm B 15/15 vs Arm A 13/15 on 77 tests vs 109 ([[RESEARCH-test-quality-bar-validation]]).
- [x] [[PLAN-008-rolling-wave]] - v0.7.0, 12 tasks across 3 waves + 2 live elaborations, fleet-wide in 48/48 vaults 2026-08-11.

## Sizing + discoverability initiative (Roger, 2026-08-23)

Triggered by a live failure in another project: a vision session produced seven epic-sized needs and Compass proposed seven flat specs with no signal anything was wrong.

- [x] [[SPEC-016-sizing-work-beyond-one-spec]] APPROVED, D-01..D-05. Both creation paths ship; Compass sizes and acts without asking; the notice is said once and silenceable; internal vocabulary never surfaced; configurable and callable.
- [x] [[SPEC-017-capabilities-are-reachable-and-measured]] APPROVED, D-01..D-02. Adopt both hermes mechanisms (progressive-disclosure index + usage measurement). Audit: `make-unit`, `unit-check`, `admit-check`, `touched`, `resolve-model` reachable from nothing; `clean-tmp` and `tree` redundant with `sync`. Admission control from [[ADR-004-hierarchical-specs-with-facets]] has never run in any vault.
- [x] Two consolidate-gate defects fixed in passing: its trigger markers did not match the literals `sync` writes, and the aggregate hot-path cap had no marker or responder at all. `sync` now writes a hot-path marker carrying a per-file breakdown.
- [ ] NEXT: research both specs, then one ADR. Open axes: SPEC-016's mechanism (skill step vs hook vs CLI gate), SPEC-017's index location.
- [ ] Open: pin the project where the seven-monster-specs session happened ([[LESSON-pin-the-motivating-datum]]).

## Scaffolding-noise initiative (Roger, 2026-08-24)

- [x] Capture re-nag spaced to every 5 turns (commit fc9ce75) - the per-turn 'still open' spam is gone.
- [ ] [[SPEC-018-scaffolding-invisible-to-the-human]] drafted, awaiting promotion. D-01 scaffolding stays hidden not removed; D-02 agents run the show between gates.

## PLAN-009 wave 1 (approved 2026-08-23)

[[PLAN-009-sizing-mechanism]] APPROVED. Wave 1 is the shape-change mechanism end to end; the prose waits on TASK-083.

- [x] TASK-078: `compass make-unit` accepts zero artifacts (M) - creates the dir itself, refuses colliding names, splits the existing usage test
- [x] Off-plan fix: `test-checkpoint verify` false-positived TASK-078's checkpoint when the checkpoint commit also carried an unrelated markdown file, AST-parsing it and reporting a tokenizer error as `modified`. Fixed by [[ADR-012-test-checkpoint-py-membership-git-authoritative]]: `.py` membership stays git-authoritative (the JSON-tamper regression test still passes), a bundled non-`.py` file is classified only when explicitly recorded.
- [x] TASK-079: the inverse of every shape change - `compass demote`, `make-unit --undo` (M, after 078)
- [x] TASK-080: sizing decisions record themselves from the commands that perform them, keyed on a stable `sizing_id` (L, after 078/079) - `commands/sizing.py`; `make-unit`, `promote`, `demote` each require `--reason` on `--apply` and write a `log:` row to `.compass/meta/sizing-log.yaml`; `promote` gained the dry-run/`--apply` gate it lacked; a malformed row is skipped, never raised; `compass sizing stats` names the audit-denominator gap on a zero correction rate
- [x] TASK-081: `validate` reconciles shapes on disk against the log (S, after 080) - every unit folder and folder spec is checked for a `sizing_id` that resolves in `sizing-log.yaml`; no id -> `sizing_unrecorded`, an id naming no row -> `sizing_orphaned_id`, both warnings only, never the exit code; a missing log file produces only unrecorded warnings, no crash
- [x] TASK-082: `compass doctor` reports unit-promotion candidates (S, after 078) - advisory row wraps `unit_check.find_candidates` in its own try/except, degrading to WARN on a scan failure so it can never collapse the other rows into one FAIL
- [x] TASK-083: prototype COMPLETE, pre-registered ESCALATION band (2026-08-23): kappa gain +0.084 CI [-0.140,+0.361] includes zero; both arms 40.0% accuracy vs 46.7% constant-majority baseline; raters up-size vs the human shape; D-02 gives a two-way answer for a three-way choice and raters mapped breadth->unit, contradicting ADR-011 D-06. Full record: .compass/tmp/sizing-prototype/RESULTS.md. RESOLVED 2026-08-24 by SPEC-016 D-06: every spec is born folder-like if that simplifies; the flat-vs-folder judgment dissolves. Wave-2 elaboration folds the ruling in.

Elaboration fires at the merge gate once wave 1's outcomes are verified. Later tasks are in [[backlog]].

## PLAN-009 wave 2 (elaborated 2026-08-24)

Prose rewritten around SPEC-016 D-06/D-07: the walk is gone; every spec born a folder, recursively; only the unit question survives to vision.

- [x] TASK-085: spec skill - every spec born a folder, recursively (M, first: 084/086 depend on it)
- [x] TASK-084: vision skill - only the unit question, plain words, once - judges root-spec-vs-workspace from what the human said, acts via make-unit, never asks; notice one plain sentence, silenceable, reversible; net -2 lines
- [x] TASK-086: spec authoring routes into the owning unit (S, after 085)
- [x] TASK-087: parent/child authoring template (S, after 086)

## PLAN-009 wave 3 (elaborated 2026-08-24)

- [x] TASK-088: methodology documents the sizing surface, callable by name (S)
- [x] TASK-089: acceptance PASS from installed copy (2026-08-24): doctor 0 FAIL, suite 625 green, coverage --strict 18/18, lesson-coverage PASS, scratch round trip decision+correction joined by id. PLAN-009 COMPLETE: 12/12 live tasks across 3 waves + 2 elaborations; TASK-090 parked in Later behind its accumulate-decisions trigger.

## PLAN-010 wave 1 (approved 2026-08-24)

[[PLAN-010-invisible-capture]] APPROVED. Capture moves off the conversation; ADR-013 D-01..D-11 bind.

- [x] TASK-091: worker wrapper + ledger vocabulary (L, first - 092/093 read its vocabulary)
- [x] TASK-092: capture-check spawns, gates recursion, orders fallbacks (L, after 091)
- [x] TASK-093: doctor reconciles the worker ledger (S, after 091, parallel with 092) - new "worker ledger" row wraps `capturelib.read_log`/`load_config`/`load_state` in its own try/except; WARNs on an unfinished spawn past `worker_grace_seconds`, the `no_headless_at` latch, or the last three completed spawns all failing, OK otherwise, never FAIL. One sanctioned collateral edit in test_doctor.py's older `UnitPromotionCandidateTests` (bumped 3 hardcoded row-count literals 7→8, extended `KNOWN_BASELINE_CHECKS` after `PRE_TASK_093_CHECKS` is computed) - see `.compass/.annotations/plugin--cli--tests--test_doctor.py.json`.
- [x] TASK-092: capture-check spawns, gates recursion, orders fallbacks (L, after 091). Code review caught and fixed two real bugs pre-handoff: `worker-spawn-error` rows were invisible to the ladder (missing from `WORKER_EVENTS`, delaying retry by a full grace window) and a respawn's own Popen failure double-spent the two-attempt budget in one call (`_spawn_worker` no longer spends; spending is centralized in `_respawn_or_quiet`). Re-ran suite after the fix: same result, no regressions. Suite: 675 passed, 1 skipped, 63 subtests passed; 19 failed = test_doctor.py's 18 expected TASK-093 reds + 1 discovered pre-existing casualty (`CaptureCheckTests::test_concurrent_check_blocked_by_run_lock`, out of the six sanctioned test edits, asserts the old block-on-due contract on an unmocked due path - needs a 7th edit in a fix cycle).
- [x] TASK-093: doctor reconciles the worker ledger (S, after 091, parallel with 092)
- [x] TASK-094: live fire PASS on path/cost, FAIL on cheap-tier quality (blind judge: reasoning) -> tier bumped to balanced, re-fire pending

- [ ] TASK-099: worker-session double catalog rows - reproduce through a real spawned session, then fix (M)
- [ ] TASK-095: balanced-tier re-fire judged blind, then fleet v0.8.0 to 50 vaults (M, after 099)

Later tasks in [[backlog]].

## Next Up

- [ ] SubagentStop typed-signal fix, fleet-wide (payload evidence captured: `agent_type` empty string). Queued in [[backlog]].
- [ ] [[SPEC-014-update-safe-customizations]] approval + research (issue #6).
- [ ] [[SPEC-011-vault-graph-queries]] pipeline: research/ADR on substrate, then planner consumer.
- [ ] [[SPEC-006-multi-host-agent-cli-support]] hosts: hermes first, then Kimi Code / Codex.
- [ ] Blinded rerun of the test-bar experiment ([[LESSON-blind-the-author-in-self-validation]]).
- [ ] Review and approve all plugin files - 3/21 approved, paused since 2026-03-12; largely superseded by the per-file reviews every later plan performed.

## Blocked

- Fleet pushes outstanding from the v0.6.x waves: 7 projects have no git, 2 no remote, 1 has all Compass paths gitignored (iwyc-unreal), 4 were push-rejected behind their remotes (3 ue5-editor-mcp checkouts + wt-spec056) and need a human pull/rebase call. pg-jira-exporter's remote no longer exists.
