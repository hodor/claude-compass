---
title: Backlog
updated: 2026-05-24
---

# Backlog

> PLAN-001 Phases 3-6 are now tracked in [[active]] under "Next Up" / "In Progress".

## Next research effort (queued 2026-06-14)

- [ ] **Diagnose and redesign the human-review model in plans.** Problem (Roger, 2026-06-14): phase pauses rarely land on anything he actually needs to review, so they read as interruptions, not checkpoints - "I don't think it's working well." Phase boundaries should be driven by *dependencies*, not by review checkpoints; lesson extraction does not justify a boundary (run it once at the end). The open question is what *should* trigger a human look - event-based? decision-point-based? confidence-based? Diagnose why phase-gated review fails before proposing a fix (do not jump to a solution); survey how other agentic-dev systems checkpoint humans. Touches `build`, `plan`, `methodology`, `extract-lessons` skills. Becomes a SPEC + research effort. [[PLAN-002-compass-cli-implementation]] already applies the interim rule (phases = dependencies, lessons at end).

## Other

- [ ] Build `/compass` orchestrator skill - single entry point that delegates to agents based on project state
- [ ] Archive workflow - move completed tasks from active.md to archive/
- [ ] Plugin marketplace listing - publish to Claude Code plugin marketplace

## Superseded by [[SPEC-002-lessons-and-index-subsystem]]

- ~~Cross-project lessons aggregation~~ - declared explicit non-goal in SPEC-002
- ~~Lesson score adjustment - track lesson applicability over time~~ - now part of TASK-001 (score bumped on recurrence by `lesson-write`)
