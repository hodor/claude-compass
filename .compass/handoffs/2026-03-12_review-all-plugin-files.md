---
title: "Handoff: Review and approve all plugin files"
type: handoff
status: active
area: workflow
tags: [review, approval, templates, spec-redesign, research-redesign]
created: 2026-03-12
updated: 2026-03-12
git_branch: "none (not yet initialized)"
git_commit: "none"
author: "claude"
---

# Handoff: Review and Approve All Plugin Files

## Session Summary

Human requested a file-by-file review and approval of all 21 Compass plugin files. During the review of file 1 (`obsidian/SKILL.md`), we discovered that document templates (spec, research) needed to be grounded in actual research rather than improvised. We sent multiple research agents to investigate established formats for both specs and research documents, then redesigned both templates based on the findings.

## Tasks

| Task | Status | Notes |
|------|--------|-------|
| TASK-001: Review all 21 files | in-progress | 1/21 in review (partially approved) |

## Review Progress

### File 1: `plugin/skills/obsidian/SKILL.md` — IN REVIEW (partially approved)

Changes made during review:
- **Status Transitions heading**: Fixed — changed to "Status Field Transitions" with explanatory line tying it to the `status` frontmatter field
- **Spec template REDESIGNED**: Removed MADR sections (Decision Drivers, Considered Options, Consequences — those belong on ADRs). Replaced with IEEE/Rust RFC/Shape Up-informed structure: Problem, Context, User Scenarios, Desired Outcome, Success Criteria, Constraints, Assumptions & Dependencies, Non-Goals, Risks, Open Questions. Only Problem and Desired Outcome required. Added option for agents to use alternative formats (Rust RFC, Python PEP, Go Proposal).
- **Research template REDESIGNED**: Replaced improvised template with survey-methodology-backed structure. Four approaches defined (Scoping Review, SLR, Systematic Mapping Study, Technology Landscape) — agent picks based on question type. New sections: Scope, Taxonomy, Prior Art, Raw Evidence appendix. Only Question and Findings required.
- **Remaining templates NOT YET REVIEWED**: Plan, Lesson, Handoff, Decision (ADR) templates still need human approval

### Skills (review first — no dependencies)

| # | File | Status | Notes |
|---|------|--------|-------|
| 1 | `plugin/skills/obsidian/SKILL.md` | IN REVIEW | Spec + Research templates approved. Plan/Lesson/Handoff/ADR templates pending. |
| 2 | `plugin/skills/lessons/SKILL.md` | not started | |
| 3 | `plugin/skills/methodology/SKILL.md` | not started | |

### Agents (review after skills)

| # | File | Status | Notes |
|---|------|--------|-------|
| 4 | `plugin/agents/bootstrap.md` | not started | |
| 5 | `plugin/agents/spec-writer.md` | CASCADE FIX | Updated during spec redesign — removed MADR refs, new question flow (10 questions), updated embedded template, added alternative format option. Needs re-review when we reach agents. |
| 6 | `plugin/agents/researcher.md` | not started | |
| 7 | `plugin/agents/planner.md` | not started | |
| 8 | `plugin/agents/planner-iterate.md` | not started | |
| 9 | `plugin/agents/builder.md` | not started | |
| 10 | `plugin/agents/reviewer.md` | not started | |
| 11 | `plugin/agents/handoff-create.md` | not started | |
| 12 | `plugin/agents/handoff-resume.md` | not started | |
| 13 | `plugin/agents/pattern-finder.md` | not started | |
| 14 | `plugin/agents/debug.md` | not started | |
| 15 | `plugin/agents/autopilot.md` | not started | |
| 16 | `plugin/agents/validator.md` | not started | |
| 17 | `plugin/agents/retroactive.md` | not started | |
| 18 | `plugin/agents/pr-describe.md` | not started | |

### Vault Structure

| # | File | Status |
|---|------|--------|
| 19 | `.compass/index.md` | not started |
| 20 | `.compass/meta/config.yaml` | not started |
| 21 | `plugin/.claude-plugin/plugin.json` | not started |

### Cascading fixes applied:
- `plugin/agents/spec-writer.md` — removed all MADR references, updated question flow (10 questions), updated embedded template, added alternative format option
- `.compass/specs/SPEC-001-compass-vision-and-architecture.md` — fixed stale MADR reference on line 148

## Decisions Made

1. **Spec template must NOT be MADR**: Specs answer "what must the system do?" — ADRs answer "what did we decide?" These are different documents. MADR sections (Decision Drivers, Considered Options, Consequences) belong exclusively on the ADR template.
2. **Research template must be survey-based**: Our researcher does scoping reviews / systematic mapping / technology landscapes — not original research. Template redesigned to reflect this with four named approaches.
3. **Alternative formats allowed**: Agents can use Rust RFC, Python PEP, Go Proposal, or any established format for specs, as long as they keep YAML frontmatter + Problem + Desired Outcome.
4. **Research-before-templates rule**: Every template must be grounded in research of established formats. Never improvise templates. (Saved as feedback memory.)
5. **Templates are flexible**: Only a few sections are required per template. The rest is use-when-relevant.

## Research Conducted (6 batches of agents)

All research reports were consumed in-conversation (not saved to vault). Key sources:
- **Spec**: IEEE 830/29148, Volere, Wiegers, Rust/Go/React RFCs, Python PEPs, Shape Up, Amazon PR/FAQ, Google design docs, GitHub spec-kit, Kiro
- **Research**: IMRaD, PRISMA, Kitchenham SLR, Petersen SMS, Arksey & O'Malley scoping reviews, CIA ACH, NTSB, NASA trade studies, McKinsey MECE/SCR, Gartner/Forrester/ThoughtWorks, OWASP/PTES, Dovetail atomic research

## Blockers

None currently.

## Action Items (Next Session)

1. [ ] Finish reviewing obsidian/SKILL.md — review the Plan, Lesson, Handoff, and ADR templates (research these too if needed)
2. [ ] Review file 2: `plugin/skills/lessons/SKILL.md`
3. [ ] Review file 3: `plugin/skills/methodology/SKILL.md`
4. [ ] Review files 4-18: all 15 agents
5. [ ] Review files 19-21: vault structure (index.md, config.yaml, plugin.json)
6. [ ] After all approved: git init + commit + push

## Artifacts (Load in Order)

1. `.compass/active.md` — current task state
2. `plugin/skills/obsidian/SKILL.md` — the file currently in review (resume from the Plan template)
3. `plugin/agents/spec-writer.md` — was updated as a cascade fix, should be re-reviewed when we get to agents

## Context for Resuming

- The human is thorough — they will question the origin of every template. Research established formats BEFORE presenting any template for approval.
- Present ONE file at a time and wait for explicit approval.
- The review order is: skills first (no deps), then agents, then vault structure.
- When we resume, we're mid-way through file 1 (`obsidian/SKILL.md`). The spec and research templates are done. Next up: Plan template, then Lesson, Handoff, ADR templates in that file.
- The human speaks Brazilian Portuguese sometimes.
- Feedback memory saved: always research before creating templates.
