---
title: Backlog
updated: 2026-05-24
---

# Backlog

> PLAN-001 Phases 3-6 are now tracked in [[active]] under "Next Up" / "In Progress".

## Candidate specs (raised, not yet drafted)

- [ ] **Hermes-agent portable techniques (from [[RESEARCH-hermes-vs-compass-fit]], 2026-07-25).** Four host-agnostic mechanisms worth Compass specs of their own: (1) FTS5 session search over past conversations - Compass has NO session-recall equivalent beyond handoffs, and this also serves Roger's fast-contextual-lesson-retrieval wish; (2) the curator's pre-mutation snapshot/rollback gate - a reversibility mechanism /compass:consolidate lacks today; (3) the 50%-of-context compression trigger with head/tail protection; (4) the offline trajectory compressor (bench/ relevance). Also: hermes is a viable SPEC-006 host candidate - its shell-hooks system speaks Claude Code's hook protocol (post_tool_call + matcher = compass sync port, classification (a)); gaps are named subagent roles (adapter) and human approval gates (no equivalent, must be designed).

- [ ] **Lesson-coverage parity (Roger, 2026-07-23).** Question raised while approving unit-nested lessons: lessons surface at plan/build time by tag *search* (advisory, unverified), while ADR rulings are getting *coverage* (enumerable + mechanically audited) via [[SPEC-007-decision-coverage-tracing]]. Should high-score lessons matching a task's area get the same treatment - plan records which lessons were consulted, validator audits that none were skipped? Needs its own spec; interacts with the lessons catalog and the validator.

## Deferred specs (not current work)

- [ ] **[[SPEC-009-configurable-pipeline-workflows]] (deferred, Roger 2026-07-23).** Draft exists with D-01 (workflows configure cross-phase contracts, not just order) recorded. Deliberately NOT today's work: it ripples through every skill and must be reviewed against SPEC-007's coverage roles and the pipeline rules before any build. Pick up after the hierarchy work ([[SPEC-010-universal-hybrid-hierarchy]]) lands.

## Next research effort (queued 2026-06-14)

- [ ] **Diagnose and redesign the human-review model in plans.** Problem (Roger, 2026-06-14): phase pauses rarely land on anything he actually needs to review, so they read as interruptions, not checkpoints - "I don't think it's working well." Phase boundaries should be driven by *dependencies*, not by review checkpoints; lesson extraction does not justify a boundary (run it once at the end). The open question is what *should* trigger a human look - event-based? decision-point-based? confidence-based? Diagnose why phase-gated review fails before proposing a fix (do not jump to a solution); survey how other agentic-dev systems checkpoint humans. Touches `build`, `plan`, `methodology`, `extract-lessons` skills. Becomes a SPEC + research effort. [[PLAN-002-compass-cli-implementation]] already applies the interim rule (phases = dependencies, lessons at end).

## compass CLI follow-ups (surfaced 2026-06-14 during live hook test)

- [ ] **Hot-path token cap has no owning reduction mechanism (surfaced 2026-08-08).** ADR-004's 5,000-token hot-path cap warns via `compass validate`/`hot-path`, but `/compass:consolidate` triggers only on its own line/count caps (index lines, catalog lines, lesson count), which were all within bounds while the token cap sat 60% over. Manual trimming of active.md and index summaries recovered 8,071 -> 5,622; the residual is genuine content. Design decision needed: raise the cap, teach consolidate the token cap as a trigger with active.md/index trimming in scope, or accept manual trims. Related: the cap warning should name its reduction lever.

- [ ] **SubagentStop typed signals are dead code in v0.5.0, fleet-wide (surfaced 2026-08-08 by PLAN-007 adversarial review; payload captured same day).** A live payload (instrumentation in this repo's settings.json, `tmp/subagentstop-payloads.jsonl`) shows `agent_type` arrives as an EMPTY STRING for teammate-style (named/background) agents, and the payload carries no name field at all - just an opaque `agent_id`, transcript paths, and `last_assistant_message`. So `capture_signal.py`'s SIGNAL_KINDS map falls to "unknown" every time, no `validator-finished`/`debug-finished`/`builder-finished` strong signal has ever fired, and the matcher is evidently not filtering on emptiness either. Open question before fixing: does a classic inline `Agent`-tool spawn (unnamed, foreground) populate `agent_type`? Test that first; if yes, the typed path works for inline spawns and teammate completions should be typed from the TeammateIdle side (`teammate:<name>` refs already recorded) instead; if no, retire the SIGNAL_KINDS map honestly. Then regression-test against the real captured shape and redistribute. Affects all 42 vaults.

- [ ] **Decide `find_vault_root` fallback semantics (surfaced 2026-08-06 by PLAN-006 validation).** When `CLAUDE_PROJECT_DIR` names a directory without `.compass`, the CLI silently walks up from cwd and can act on the enclosing repo's vault - this is how a read-only validation probe mutated real capture state ([[LESSON-scratch-vaults-need-compass-dir]]), and the same edge means a hook firing in a nested non-Compass dir writes to the parent vault. Open design question: is the fallback wanted (nested dirs delegating to the parent vault) or should an explicitly-set env var that fails validation be an error? Touches every CLI command; decide deliberately, not as a drive-by fix.

- [x] `compass validate` now checks the top-level files' own wikilinks (`index.md`, `active.md`, `backlog.md`, `vision.md`), so a stale index entry (a link to a deleted artifact) surfaces as a `broken_wikilink` warning. Covers both the stale-entry and index-own-links gaps. (2026-06-15)

## Compass productization (queued 2026-06-14, from Roger)

- [ ] **(DEPRIORITIZED - revisit later, Roger 2026-06-15)** Port the compass CLI from Python to Rust. Open decision before starting: distribution model changes (a compiled binary cannot be `cp`-copied as source into `.claude/cli/` the way Python is - needs prebuilt per-platform binaries in the repo + CI, or a build-on-install toolchain). [[ADR-005-compass-cli-for-mechanical-work]] chose Python to ship and prove [[SPEC-004-mechanical-work-off-the-agent-budget]]; Rust was deferred. Now the design is proven and the command surface is stable, so port it: a single static binary removes the runtime dependency AND the whole `python3`-vs-`python` interpreter problem (no detection branch, no python-presence check), and starts faster - the hook fires on every vault write. Keep the CLI contract identical (`sync --hook`, `validate`, `next-num`, ...) and re-create the test suite's semantics (golden output, seeded-defect, idempotency, never-exit-2).
- [x] **Cross-session compass bug self-reporting -> deduplicated GitHub issues.** (2026-06-15) Built: CLI auto-captures its own crashes; `compass capture-bug` for agent-noticed bugs; `compass file-bugs [--apply]` dedupes against open issues by fingerprint and files via `gh` (dry-run default, outward-facing). `/compass:report-bug` skill is the entry point. Fingerprint = hash(command + signature), so the same bug across sessions/repos collapses to one local record and one GitHub issue.
- [x] **Separated update from bootstrap; renamed bootstrap -> setup.** (2026-06-15) `init` was rejected: it shadows Claude Code's built-in `/init` in the bare-invocation model that `.claude/skills/` copies use; `setup`/`update` are collision-free. `/compass:update` is git-based and removes skills deleted in the source (handles the rename). setup is first-time-only. All references fixed; plugin v0.3.0. Verified by an end-to-end update dry-run against the live repo.
- [x] **Rewrote stale README for v0.3.0.** (2026-06-15) Added the CLI + command-hook section, `/compass:update`, the missing commands, and fixed the dropped-"counters" / old-tester-hook staleness.
- [ ] **Iteratively test compass against real repos until install works perfectly.** Use real repos (product-owner, others) as fixtures - their `.compass/` vaults stay READ-ONLY. Loop: run `/compass:update` (and `/compass:bootstrap` for fresh setup) -> observe what fails -> fix the skills/CLI in THIS repo -> repeat until install + `compass sync` + `compass validate` work cleanly on every test repo. Track which repos pass. First fixture finding (2026-06-14): the CLI was overfit to the dogfood vault - fixed in commit 02414a5 by generalizing type-dir discovery and validate severity.

## Finish SPEC-004 for Stop/SubagentStop hooks (queued 2026-06-15, from iwyc-unreal investigation)

- [ ] **Convert the `Stop` and `SubagentStop` hooks from `type: agent` to command hooks.** SPEC-004 moved PostToolUse to a command (per-write, ~0 tokens) but left these two as agents. `Stop` (extract-lessons backstop) spawns an agent on EVERY turn-end; `SubagentStop` (capture) spawns one per subagent. Both do mechanical work - a glob check for unprocessed phase-reports, and writing a subagent report verbatim - that belongs in `compass` commands (e.g. `compass stop-check`, `compass capture-subagent`), the same way `compass sync` replaced the PostToolUse agent. This is the biggest remaining ongoing Compass token cost: it fires per-turn, not just on vault writes. Extends [[SPEC-004-mechanical-work-off-the-agent-budget]] / [[ADR-005-compass-cli-for-mechanical-work]]; same `[[LESSON-no-agent-bookkeeping]]` principle.
- [ ] **Bootstrap/setup should not leave a stale `settings.local.json` tester hook.** Old installs (iwyc-unreal, product-owner) still carry an agent-type "tester-after-builder" SubagentStop hook in `settings.local.json`, redundant with the new capture hook and spawning a full tester agent per builder. Decide: is auto-test-after-builder wanted at all (vs `/compass:build`'s fix loop)? If not, have setup/update remove it; if yes, make it a deliberate, documented opt-in.

## Other

- [ ] Build `/compass` orchestrator skill - single entry point that delegates to agents based on project state
- [ ] Archive workflow - move completed tasks from active.md to archive/
- [ ] Plugin marketplace listing - publish to Claude Code plugin marketplace

## Superseded by [[SPEC-002-lessons-and-index-subsystem]]

- ~~Cross-project lessons aggregation~~ - declared explicit non-goal in SPEC-002
- ~~Lesson score adjustment - track lesson applicability over time~~ - now part of TASK-001 (score bumped on recurrence by `lesson-write`)
