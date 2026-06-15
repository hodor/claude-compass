---
title: Backlog
updated: 2026-05-24
---

# Backlog

> PLAN-001 Phases 3-6 are now tracked in [[active]] under "Next Up" / "In Progress".

## Next research effort (queued 2026-06-14)

- [ ] **Diagnose and redesign the human-review model in plans.** Problem (Roger, 2026-06-14): phase pauses rarely land on anything he actually needs to review, so they read as interruptions, not checkpoints - "I don't think it's working well." Phase boundaries should be driven by *dependencies*, not by review checkpoints; lesson extraction does not justify a boundary (run it once at the end). The open question is what *should* trigger a human look - event-based? decision-point-based? confidence-based? Diagnose why phase-gated review fails before proposing a fix (do not jump to a solution); survey how other agentic-dev systems checkpoint humans. Touches `build`, `plan`, `methodology`, `extract-lessons` skills. Becomes a SPEC + research effort. [[PLAN-002-compass-cli-implementation]] already applies the interim rule (phases = dependencies, lessons at end).

## compass CLI follow-ups (surfaced 2026-06-14 during live hook test)

- [x] `compass validate` now checks the top-level files' own wikilinks (`index.md`, `active.md`, `backlog.md`, `vision.md`), so a stale index entry (a link to a deleted artifact) surfaces as a `broken_wikilink` warning. Covers both the stale-entry and index-own-links gaps. (2026-06-15)

## Compass productization (queued 2026-06-14, from Roger)

- [ ] **(DEPRIORITIZED - revisit later, Roger 2026-06-15)** Port the compass CLI from Python to Rust. Open decision before starting: distribution model changes (a compiled binary cannot be `cp`-copied as source into `.claude/cli/` the way Python is - needs prebuilt per-platform binaries in the repo + CI, or a build-on-install toolchain). [[ADR-005-compass-cli-for-mechanical-work]] chose Python to ship and prove [[SPEC-004-mechanical-work-off-the-agent-budget]]; Rust was deferred. Now the design is proven and the command surface is stable, so port it: a single static binary removes the runtime dependency AND the whole `python3`-vs-`python` interpreter problem (no detection branch, no python-presence check), and starts faster - the hook fires on every vault write. Keep the CLI contract identical (`sync --hook`, `validate`, `next-num`, ...) and re-create the test suite's semantics (golden output, seeded-defect, idempotency, never-exit-2).
- [x] **Cross-session compass bug self-reporting -> deduplicated GitHub issues.** (2026-06-15) Built: CLI auto-captures its own crashes; `compass capture-bug` for agent-noticed bugs; `compass file-bugs [--apply]` dedupes against open issues by fingerprint and files via `gh` (dry-run default, outward-facing). `/compass:report-bug` skill is the entry point. Fingerprint = hash(command + signature), so the same bug across sessions/repos collapses to one local record and one GitHub issue.
- [x] **Separated update from bootstrap; renamed bootstrap -> setup.** (2026-06-15) `init` was rejected: it shadows Claude Code's built-in `/init` in the bare-invocation model that `.claude/skills/` copies use; `setup`/`update` are collision-free. `/compass:update` is git-based and removes skills deleted in the source (handles the rename). setup is first-time-only. All references fixed; plugin v0.3.0. Verified by an end-to-end update dry-run against the live repo.
- [x] **Rewrote stale README for v0.3.0.** (2026-06-15) Added the CLI + command-hook section, `/compass:update`, the missing commands, and fixed the dropped-"counters" / old-tester-hook staleness.
- [ ] **Iteratively test compass against real repos until install works perfectly.** Use real repos (product-owner, others) as fixtures - their `.compass/` vaults stay READ-ONLY. Loop: run `/compass:update` (and `/compass:bootstrap` for fresh setup) -> observe what fails -> fix the skills/CLI in THIS repo -> repeat until install + `compass sync` + `compass validate` work cleanly on every test repo. Track which repos pass. First fixture finding (2026-06-14): the CLI was overfit to the dogfood vault - fixed in commit 02414a5 by generalizing type-dir discovery and validate severity.

## Other

- [ ] Build `/compass` orchestrator skill - single entry point that delegates to agents based on project state
- [ ] Archive workflow - move completed tasks from active.md to archive/
- [ ] Plugin marketplace listing - publish to Claude Code plugin marketplace

## Superseded by [[SPEC-002-lessons-and-index-subsystem]]

- ~~Cross-project lessons aggregation~~ - declared explicit non-goal in SPEC-002
- ~~Lesson score adjustment - track lesson applicability over time~~ - now part of TASK-001 (score bumped on recurrence by `lesson-write`)
