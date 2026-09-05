---
title: Done Log
summary: "completed tasks swept out of active.md by compass sweep, verbatim, newest day last"
---

# Done Log

## 2026-08-28

### Shipped

- [x] [[PLAN-001-lessons-and-index-implementation]] - 12 tasks (2026-05-24)
- [x] [[PLAN-002-compass-cli-implementation]] - CLI + command-hook cutover, ~99.8% bookkeeping-token reduction (2026-06-14)
- [x] [[PLAN-003-hybrid-hierarchy]], [[PLAN-004-decision-coverage]], [[PLAN-005-model-table]] - 23/23 tasks, validator BATCH PASS (2026-07-24)
- [x] [[PLAN-006-learning-loop]] - v0.5.0, 16 tasks, VALIDATED 9/9 probes, fleet-wide 2026-08-06. Root cause found en route: hooks load only from settings files ([[LESSON-hooks-load-only-from-settings]]), so no Compass hook had ever fired anywhere before that date.
- [x] [[PLAN-007-test-quality]] - v0.6.0-v0.6.3, 12 live tasks (Phase C parked behind named unpark triggers). The paired experiment validated the bar: Arm B 15/15 vs Arm A 13/15 on 77 tests vs 109 ([[RESEARCH-test-quality-bar-validation]]).
- [x] [[PLAN-008-rolling-wave]] - v0.7.0, 12 tasks across 3 waves + 2 live elaborations, fleet-wide in 48/48 vaults 2026-08-11.

### Sizing + discoverability initiative
- [x] [[SPEC-016-sizing-work-beyond-one-spec]] APPROVED, D-01..D-05. Both creation paths ship; Compass sizes and acts without asking; the notice is said once and silenceable; internal vocabulary never surfaced; configurable and callable.
- [x] [[SPEC-017-capabilities-are-reachable-and-measured]] APPROVED, D-01..D-02. Adopt both hermes mechanisms (progressive-disclosure index + usage measurement). Audit: `make-unit`, `unit-check`, `admit-check`, `touched`, `resolve-model` reachable from nothing; `clean-tmp` and `tree` redundant with `sync`. Admission control from [[ADR-004-hierarchical-specs-with-facets]] has never run in any vault.
- [x] Two consolidate-gate defects fixed in passing: its trigger markers did not match the literals `sync` writes, and the aggregate hot-path cap had no marker or responder at all. `sync` now writes a hot-path marker carrying a per-file breakdown.

### Active-set hygiene initiative
- [x] [[SPEC-019-active-holds-only-active-work]] APPROVED 2026-08-28 - active.md accumulates done tasks forever; hot path pays for history every turn.
- [x] [[RESEARCH-active-set-prior-art]] - 3 parallel axes (Claude Code harness, hermes-agent, classic OSS), 49 findings. Flag-then-sweep dominates; no system lets intelligence decide membership; PostToolUse `compass sync` is the already-owned zero-token trigger.
- [x] [[ADR-014-active-sweep-on-sync]] accepted: flag-then-sweep inside sync; wholesale section moves; archive/done.md; validate drift warning.

### Scaffolding-noise initiative
- [x] Capture re-nag spaced to every 5 turns (commit fc9ce75) - the per-turn 'still open' spam is gone.

### PLAN-009 wave 1 (approved 2026-08-23)

[[PLAN-009-sizing-mechanism]] APPROVED. Wave 1 is the shape-change mechanism end to end; the prose waits on TASK-083.

- [x] TASK-078: `compass make-unit` accepts zero artifacts (M) - creates the dir itself, refuses colliding names, splits the existing usage test
- [x] Off-plan fix: `test-checkpoint verify` false-positived TASK-078's checkpoint when the checkpoint commit also carried an unrelated markdown file, AST-parsing it and reporting a tokenizer error as `modified`. Fixed by [[ADR-012-test-checkpoint-py-membership-git-authoritative]]: `.py` membership stays git-authoritative (the JSON-tamper regression test still passes), a bundled non-`.py` file is classified only when explicitly recorded.
- [x] TASK-079: the inverse of every shape change - `compass demote`, `make-unit --undo` (M, after 078)
- [x] TASK-080: sizing decisions record themselves from the commands that perform them, keyed on a stable `sizing_id` (L, after 078/079) - `commands/sizing.py`; `make-unit`, `promote`, `demote` each require `--reason` on `--apply` and write a `log:` row to `.compass/meta/sizing-log.yaml`; `promote` gained the dry-run/`--apply` gate it lacked; a malformed row is skipped, never raised; `compass sizing stats` names the audit-denominator gap on a zero correction rate
- [x] TASK-081: `validate` reconciles shapes on disk against the log (S, after 080) - every unit folder and folder spec is checked for a `sizing_id` that resolves in `sizing-log.yaml`; no id -> `sizing_unrecorded`, an id naming no row -> `sizing_orphaned_id`, both warnings only, never the exit code; a missing log file produces only unrecorded warnings, no crash
- [x] TASK-082: `compass doctor` reports unit-promotion candidates (S, after 078) - advisory row wraps `unit_check.find_candidates` in its own try/except, degrading to WARN on a scan failure so it can never collapse the other rows into one FAIL
- [x] TASK-083: prototype COMPLETE, pre-registered ESCALATION band (2026-08-23): kappa gain +0.084 CI [-0.140,+0.361] includes zero; both arms 40.0% accuracy vs 46.7% constant-majority baseline; raters up-size vs the human shape; D-02 gives a two-way answer for a three-way choice and raters mapped breadth->unit, contradicting ADR-011 D-06. Full record: .compass/tmp/sizing-prototype/RESULTS.md. RESOLVED 2026-08-24 by SPEC-016 D-06: every spec is born folder-like if that simplifies; the flat-vs-folder judgment dissolves. Wave-2 elaboration folds the ruling in.

Elaboration fires at the merge gate once wave 1's outcomes are verified. Later tasks are in [[backlog]].

### PLAN-009 wave 2 (elaborated 2026-08-24)

Prose rewritten around SPEC-016 D-06/D-07: the walk is gone; every spec born a folder, recursively; only the unit question survives to vision.

- [x] TASK-085: spec skill - every spec born a folder, recursively (M, first: 084/086 depend on it)
- [x] TASK-084: vision skill - only the unit question, plain words, once - judges root-spec-vs-workspace from what the human said, acts via make-unit, never asks; notice one plain sentence, silenceable, reversible; net -2 lines
- [x] TASK-086: spec authoring routes into the owning unit (S, after 085)
- [x] TASK-087: parent/child authoring template (S, after 086)

### PLAN-009 wave 3 (elaborated 2026-08-24)

- [x] TASK-088: methodology documents the sizing surface, callable by name (S)
- [x] TASK-089: acceptance PASS from installed copy (2026-08-24): doctor 0 FAIL, suite 625 green, coverage --strict 18/18, lesson-coverage PASS, scratch round trip decision+correction joined by id. PLAN-009 COMPLETE: 12/12 live tasks across 3 waves + 2 elaborations; TASK-090 parked in Later behind its accumulate-decisions trigger.

### PLAN-010 wave 1 (approved 2026-08-24)

[[PLAN-010-invisible-capture]] APPROVED. Capture moves off the conversation; ADR-013 D-01..D-11 bind.

- [x] TASK-091: worker wrapper + ledger vocabulary (L, first - 092/093 read its vocabulary)
- [x] TASK-092: capture-check spawns, gates recursion, orders fallbacks (L, after 091)
- [x] TASK-093: doctor reconciles the worker ledger (S, after 091, parallel with 092) - new "worker ledger" row wraps `capturelib.read_log`/`load_config`/`load_state` in its own try/except; WARNs on an unfinished spawn past `worker_grace_seconds`, the `no_headless_at` latch, or the last three completed spawns all failing, OK otherwise, never FAIL. One sanctioned collateral edit in test_doctor.py's older `UnitPromotionCandidateTests` (bumped 3 hardcoded row-count literals 7→8, extended `KNOWN_BASELINE_CHECKS` after `PRE_TASK_093_CHECKS` is computed) - see `.compass/.annotations/plugin--cli--tests--test_doctor.py.json`.
- [x] TASK-092: capture-check spawns, gates recursion, orders fallbacks (L, after 091). Code review caught and fixed two real bugs pre-handoff: `worker-spawn-error` rows were invisible to the ladder (missing from `WORKER_EVENTS`, delaying retry by a full grace window) and a respawn's own Popen failure double-spent the two-attempt budget in one call (`_spawn_worker` no longer spends; spending is centralized in `_respawn_or_quiet`). Re-ran suite after the fix: same result, no regressions. Suite: 675 passed, 1 skipped, 63 subtests passed; 19 failed = test_doctor.py's 18 expected TASK-093 reds + 1 discovered pre-existing casualty (`CaptureCheckTests::test_concurrent_check_blocked_by_run_lock`, out of the six sanctioned test edits, asserts the old block-on-due contract on an unmocked due path - needs a 7th edit in a fix cycle).
- [x] TASK-093: doctor reconciles the worker ledger (S, after 091, parallel with 092)
- [x] TASK-094: live fire PASS on path/cost, FAIL on cheap-tier quality (blind judge: reasoning) -> tier bumped to balanced, re-fire pending

- [x] TASK-099: root cause found in the worker's transcript (it hand-inserted rows the hook had appended); sync now collapses duplicate rows and reports it; lesson-write's carve-out closed
- [x] TASK-095: re-fire PASS (worker 5/5 vs in-session 4/5, $0.96); v0.8.0 distributed to 50/50 vaults, all doctor-clean (2026-08-24)

- [x] TASK-096/097/098 (2026-08-24): POSIX pinned-not-observed, SessionStart pickup registered fleet-wide, between-gates silence in the pipeline rule and build skill. PLAN-010 COMPLETE.
- [x] Off-plan fix v0.8.2 (2026-08-24): live defect in daschie-sort - the agent handed the human `/compass:learned` because no agent-callable capture path existed. [[ADR-013-detached-worker-quiet-fallback]] D-12: `compass capture-note` files the observation as evidence plus a strong signal; six skill/rule sites rewritten to forbid suggesting the slash command. 696 tests green.

### Active-set hygiene initiative

- [x] TASK-091: sweep engine + `compass sweep` dry-run/apply ([[PLAN-011-active-sweep]])
- [x] TASK-092: wire into sync + `active_done` validate warning (after 091)
- [x] TASK-093: doc alignment - builder, build, checkup, CLAUDE.md (after 092)
- [x] TASK-094: local install refresh + live acceptance: sweep moved 36 lines, hot path 10172->8489, validate 0 errors (after 093)

### Self-update initiative

- [x] TASK-095: `compass self-update` command - sha gate, throttle, local-source mode, staged apply ([[PLAN-012-self-update]])
- [x] TASK-096: SessionStart(startup) hook entry + setup/update skill alignment (after 095)
- [x] TASK-097: live acceptance: applied-local 0.8.2 -> 0.10.0, throttle held on rerun, settings registered, doctor 0 FAIL (after 096)

## 2026-08-29

### Human's-words initiative

- [x] [[SPEC-021-capture-in-the-humans-words]] approved; [[RESEARCH-humans-words-fidelity]] complete (54 findings, 3 axes); [[ADR-016-capture-by-extraction]] accepted.
- [x] TASK-098: spec skill extract-and-arrange rewrite ([[PLAN-013-capture-by-extraction]])
- [x] TASK-099: vision + specs + retroactive skills, same discipline (after 098)
- [x] TASK-100: pipeline-rule scope line, 0.11.0, suite 734 green, pushed, fleet pull verified (after 099)

### Sizing + discoverability initiative
- [x] [[ADR-017-capability-index-and-usage-record]] accepted for [[SPEC-017-capabilities-are-reachable-and-measured]].
- [x] TASK-101: usage.py + dispatch recording + report ([[PLAN-014-capability-usage]])
- [x] TASK-102: doctor never-used advisory, 14-day window before WARN (after 101)
- [x] TASK-103: retire clean-tmp/tree; reachability line; methodology note (after 101)
- [x] TASK-104: suite 746 green, v0.12.0, pushed, fleet pull verified (after 102/103)

### Scaffolding-noise initiative

- [x] [[SPEC-018-scaffolding-invisible-to-the-human]] approved 2026-08-24 and SHIPPED via [[ADR-013-detached-worker-quiet-fallback]]/PLAN-010 (stale line corrected).

### Next Up
- [x] [[ADR-018-graph-queries-jit-over-markdown]] accepted for [[SPEC-011-vault-graph-queries]].
- [x] TASK-105: vaultgraph + compass graph orphans/hubs/impact ([[PLAN-015-graph-queries]])
- [x] TASK-106: unit-check hub-dominance guard, cap 10 (after 105)
- [x] TASK-107: vault-health/checkup/planner consumers (after 105)
- [x] TASK-108: live validation PASS - SPEC-001 tally 21=21, ADR-005 off-by-one audited in graph's favor, 3 true orphans; suite 768 green (after 106/107)

### Next Up
- [x] [[SPEC-014-update-safe-customizations]] APPROVED 2026-08-29 (issue #6); self-update raised the stakes, folded into the Problem.

### Next Up
- [x] SubagentStop FIXED ([[ADR-019-subagentstop-redelivery-and-teammate-typing]]): inline spawns were always typed; double-delivery found and deduped; teammates typed from name. Suite 775 green.

### Next Up
- [x] [[RESEARCH-update-safe-customization]] complete: prior art charted; the Defold benchmark corpus was found empty
- [x] [[ADR-020-local-overlays-appended-after-refresh]] accepted and SHIPPED v0.14.0: `.compass/meta/local/` overlays appended after each refresh, `compass overlay`, doctor row, CLAUDE.md pinned untouched by test. Live round-trip verified.

## 2026-08-30

### Per-domain organization initiative
- [x] [[ADR-021-index-speaks-in-domains]] accepted + SHIPPED v0.15.0: root index lists depth-0 only; taxonomize retired into consolidate as its Structure pass

### Per-domain organization initiative
- [x] [[RESEARCH-taxonomy-for-unambiguous-placement]] complete (50 findings, 3 axes, science primary).
- [x] [[ADR-022-domains-scope-notes-shallow-when-unsure]] accepted on the human's go ("sounds great let's give it a shot go").

### Per-domain organization initiative
- [x] [[PLAN-016-domain-taxonomy]] APPROVED 2026-08-30; the human reviews the migrated vault, not the tasks.

### Per-domain organization initiative
- [x] TASK-109: record names, count refresh, loop guard, piped links
- [x] TASK-110: make-domain + validate suggestions
- [x] TASK-111: link rules

### Per-domain organization initiative
- [x] TASK-112: skill contracts
- [x] TASK-118: born flat - folder at the second member; self-update normalizes over-shaped vaults

### Per-domain organization initiative
- [x] TASK-116: compass tree

### Per-domain organization initiative
- [x] TASK-117: useless-token baseline

### Per-domain organization initiative
- [x] TASK-113: proposal by the atomic rule + Wikipedia score (diff approved 2026-08-30)

### Per-domain organization initiative
- [x] TASK-114: migrate this vault, drills, re-measure (finder 9/10, filer 4/5 unanimous, probes -30%; cap shortfall -> consolidate lessons pass)

### Per-domain organization initiative
- [x] TASK-115: ship + fleet verify + handoff (v0.16.0, doctor 0 FAIL on knowledge-curation)

### Per-domain organization initiative
- [x] TASK-120: taxonomize decisions/ and lessons/ (SPEC-022 D-12) - applied; 52 moves, 0 errors, catalog untouched

### Per-domain organization initiative
- [x] TASK-120: taxonomize decisions/ and lessons/ (SPEC-022 D-12) - applied; 52 moves, 0 errors, catalog untouched

### Per-domain organization initiative
- [x] TASK-121: lessons load like everything else (D-14) - hot path 3,332/5,000, under cap for the first time

### Per-domain organization initiative
- [x] TASK-119: measurement empirically proven (runs 2-3: 12/12 recall, 0 hallucination, 0.0000 token error); D-11 binding active

## 2026-08-31

### GitHub issues from live v0.17 use (filed 2026-08-31)

- [x] Fix and test #14 - sync lists depth>0 folder children in the root index (ADR-021 D-01)
- [x] Fix and test #15 - make-domain refuses unit-internal paths
- [x] Fix and test #16 - fix-frontmatter cannot add `summary:` although validate warns on it
- [x] Fix and test #17 - `_sync_index` is append-only, never prunes relocated entries
- [x] Fix and test #18 - no link-preserving move for domain grouping in make-domain
- [x] Fix and test #19 - validate flags abbreviated bare-stem wikilinks that rules/wikilinks.md sanctions
- [x] Fix and test #20 - consolidate skill states a false premise that destroys information (Step 7)

## 2026-09-05

### PLAN-017 dsh host support - Wave 1 (approved 2026-09-05)

- [x] TASK-001: stand up a live dsh rig - install dsh, scratch dual-host project, record version + harness home ([[PLAN-017-dsh-host-support]])
- [x] TASK-002: hand-author the minimal Compass profile bundle; prove a vault write inside dsh fires compass sync
- [x] TASK-003: live probe - Stop-block contract, capture loop survival, SessionStart source literal
- [x] TASK-004: instruction-surface placement matrix - each host loads each instruction exactly once
- Pause point after Wave 1: human confirms manual verification before any Later wave elaborates.

### PLAN-017 dsh host support - Wave 2 (human ruling at the Wave 1 gate: every wave verifies suite-green plus live under both hosts)
- [x] TASK-014: PostToolUse matcher legal on both hosts - manifest, setup translation, merge_settings moved together
- [x] TASK-005: host seam - plugin.yaml roster, per-host _apply loop, generated .dsh/hooks.json; dual-host live bar passed

### PLAN-017 dsh host support - Wave 2 (human ruling at the Wave 1 gate: every wave verifies suite-green plus live under both hosts)
- [x] Wave 2 pause point confirmed; human: "feel free to go"
- [x] TASK-007: tool-name map, platform-resolved shell (pwsh on win32)
- [x] TASK-006: skill materializer - 32 skills in dsh dialect, catalog + load proven live
- [x] TASK-008: bundle generator - delegation to compass_debug proven live; relative configPath works

### PLAN-017 dsh host support - Wave 2 (human ruling at the Wave 1 gate: every wave verifies suite-green plus live under both hosts)

- [x] Wave 3 pause point confirmed; TASK-012 ruling delegated ("do what will be the best for all compass users")
- [x] TASK-010: rules folded into AGENTS.md managed section; dsh quotes them verbatim
- [x] TASK-009: dsh model column - delegation routed on deepseek-v4-pro live
- [x] TASK-011: host-aware doctor - materializations, skew, capture posture
- [x] TASK-012: host-aware capture worker - dsh headless completed a real extract pass, claude masked
- [x] TASK-013: dual-host acceptance - both CLIs drove the pipeline, validate 0 errors; PLAN-017 COMPLETE
