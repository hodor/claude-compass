---
title: Active Tasks
updated: 2026-03-12
---

# Active Tasks

## Done

- [x] Finalize vision spec — resolve open questions in [[SPEC-001-compass-vision-and-architecture]]
- [x] Set up plugin structure — create agents and skills

## In Progress

- [ ] TASK-001: Review and approve all plugin files (21 files) — human approves each file one by one
  - Progress: file 1/21 (`plugin/skills/obsidian/SKILL.md`) — APPROVED
  - All 6 templates reviewed and approved: Spec, Research, Plan, Lesson, Handoff, ADR
  - Plan template: enhanced with Current State, Desired End State, Not Doing, file paths, Testing Strategy, Open Questions (inspired by HumanLayer)
  - Lesson template: redesigned with Reinertsen's process/domain distinction, new sections (Context, What Happened, Why, Lesson, Applicability)
  - Handoff template: enhanced with Artifacts section and Current Phase tracking (inspired by HumanLayer)
  - ADR template: confirmed as Nygard standard (Context, Decision, Consequences) — no changes needed
  - Cascade fixes applied: `plugin/agents/spec-writer.md`, `SPEC-001` line 148, `plugin/skills/lessons/SKILL.md`, `plugin/agents/builder.md`, `plugin/skills/methodology/SKILL.md`
  - HumanLayer mining: adopted plan validation, builder plan-tracking, TODO priority annotations
  - Files 2-21: not started
  - Next file: `plugin/skills/lessons/SKILL.md` (file 2)
  - Handoff: [[2026-03-12_session-2-obsidian-approved]]

## Blocked

_None._

## Next Up

- [ ] Create ADR-001 — document key architectural decisions (methodology as skill, file naming, tasks in active.md)
- [ ] Test bootstrap agent on a fresh project
- [ ] Test spec-writer agent interactively
- [ ] Push to GitHub repository
