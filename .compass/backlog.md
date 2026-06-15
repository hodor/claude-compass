---
title: Backlog
updated: 2026-05-24
---

# Backlog

> PLAN-001 Phases 3-6 are now tracked in [[active]] under "Next Up" / "In Progress".

## Next research effort (queued 2026-06-14)

- [ ] **Diagnose and redesign the human-review model in plans.** Problem (Roger, 2026-06-14): phase pauses rarely land on anything he actually needs to review, so they read as interruptions, not checkpoints - "I don't think it's working well." Phase boundaries should be driven by *dependencies*, not by review checkpoints; lesson extraction does not justify a boundary (run it once at the end). The open question is what *should* trigger a human look - event-based? decision-point-based? confidence-based? Diagnose why phase-gated review fails before proposing a fix (do not jump to a solution); survey how other agentic-dev systems checkpoint humans. Touches `build`, `plan`, `methodology`, `extract-lessons` skills. Becomes a SPEC + research effort. [[PLAN-002-compass-cli-implementation]] already applies the interim rule (phases = dependencies, lessons at end).

## compass CLI follow-ups (surfaced 2026-06-14 during live hook test)

- [ ] `compass sync` is append-only for `index.md`, so deleting an artifact leaves a stale index line (the tag-index, full-regen, drops it correctly). Add a `stale_entry` finding to `compass validate` (or a `sync --prune` opt-in) so deletions surface instead of lingering silently.
- [ ] `compass validate` checks wikilinks only inside the type-dir artifacts it scans; it does NOT validate `index.md`'s own wikilinks, so a broken link there slips through. Add `index.md` / `active.md` / `backlog.md` to the link-resolution pass.

## Compass productization (queued 2026-06-14, from Roger)

- [ ] **Port the compass CLI from Python to Rust.** [[ADR-005-compass-cli-for-mechanical-work]] chose Python to ship and prove [[SPEC-004-mechanical-work-off-the-agent-budget]]; Rust was deferred. Now the design is proven and the command surface is stable, so port it: a single static binary removes the runtime dependency AND the whole `python3`-vs-`python` interpreter problem (no detection branch, no python-presence check), and starts faster - the hook fires on every vault write. Keep the CLI contract identical (`sync --hook`, `validate`, `next-num`, ...) and re-create the test suite's semantics (golden output, seeded-defect, idempotency, never-exit-2).
- [ ] **Cross-session compass bug self-reporting -> deduplicated GitHub issues.** When Compass runs in another repo and a session hits a compass bug (CLI error, hook failure, a validate false positive, etc.), it should open a GitHub issue against the compass repo - WITHOUT duplicating an existing one. Needs: a capture path (a `compass report-bug` command and/or a way agents invoke it), a stable fingerprint per bug, a dedup step that searches open issues by that fingerprint before filing, and `gh` integration. Decide the trigger (automatic on CLI error vs. agent-judged).
- [ ] **Finish separating update from bootstrap; rename bootstrap.** DONE: git-based [[update]] skill created (`/compass:update`). Remaining: remove update mode from `bootstrap`, rename `bootstrap` -> `start` (or `init`/`setup` - decide), and fix all references (CLAUDE.md, command lists, docs). After the split, bootstrap = first-time project setup only (vault scaffold + install + CLAUDE.md + vision kickoff); update = refresh the install from git.
- [ ] **Iteratively test compass against real repos until install works perfectly.** Use real repos (product-owner, others) as fixtures - their `.compass/` vaults stay READ-ONLY. Loop: run `/compass:update` (and `/compass:bootstrap` for fresh setup) -> observe what fails -> fix the skills/CLI in THIS repo -> repeat until install + `compass sync` + `compass validate` work cleanly on every test repo. Track which repos pass. First fixture finding (2026-06-14): the CLI was overfit to the dogfood vault - fixed in [[02414a5]] (commit) by generalizing type-dir discovery and validate severity.

## Other

- [ ] Build `/compass` orchestrator skill - single entry point that delegates to agents based on project state
- [ ] Archive workflow - move completed tasks from active.md to archive/
- [ ] Plugin marketplace listing - publish to Claude Code plugin marketplace

## Superseded by [[SPEC-002-lessons-and-index-subsystem]]

- ~~Cross-project lessons aggregation~~ - declared explicit non-goal in SPEC-002
- ~~Lesson score adjustment - track lesson applicability over time~~ - now part of TASK-001 (score bumped on recurrence by `lesson-write`)
