---
name: methodology
description: The Compass development workflow pipeline — Spec, Research, Plan, Tasks, Build — with human involvement gradient, status transitions, testing mandate, and required artifacts enforcement
version: 1.0.0
allowed-tools: [Read, Glob, Grep]
---

# Methodology — The Compass Workflow

Compass provides a structured development pipeline that ensures humans own strategic decisions while AI handles execution. Every agent in the Compass system follows this methodology.

## The Pipeline

```
Spec → Research → Plan → Tasks → Build
```

Each stage produces artifacts that feed the next. Stages can be revisited, but never skipped.

## Hot Path

Every agent MUST read the hot path first, before doing any other work:

1. `.compass/index.md` — Master map of all project documents
2. `.compass/active.md` — Current tasks (in-progress + blocked)
3. `.compass/meta/lessons-catalog.yaml` — Scan for relevant lessons

This is the "cache line" — the minimum context needed to orient. Only after reading the hot path should an agent load additional documents (specs, research, plans) as needed.

## Human Involvement Gradient

| Level | Human Role | AI Role | Autonomy |
|-------|-----------|---------|----------|
| Specs | Human models, makes decisions | Ask questions one at a time, structure answers | LOW — agent never fills blanks without permission |
| Research | Human reviews findings, redirects | Execute autonomously, present evidence with confidence | MEDIUM — agent works independently but never decides |
| Plans | Human approves before tasks are created | Propose based on specs + research | MEDIUM — agent proposes, human approves |
| Tasks | Human reviews output | Execute autonomously, write tests, update status | HIGH — agent works independently within defined scope |
| Decisions (ADRs) | Human approves | Present options with evidence | LOW — agent presents, human decides |

**CRITICAL: Agents must FORCE humans to make decisions.** Never decide silently at strategic levels. If unsure, ask. If the decision has architectural implications, create an ADR.

## Decision Recording (ADRs)

Architecture Decision Records are **orthogonal to the pipeline** — they can be created at any stage when a significant decision is made.

When to create an ADR:
- Choosing between competing approaches with meaningful trade-offs
- Adopting or abandoning a technology, pattern, or convention
- Any decision that would surprise a future team member

ADRs live in `.compass/decisions/` and follow the `ADR-NNN-descriptive-name.md` naming convention.

## Testing Mandate

**Non-negotiable.** Every agent that writes code MUST:

1. **Determine test type**: Analyze the project and code to decide between property-based tests, unit tests, or integration tests. The agent decides — this is not prescribed.
2. **Set up test location**: Tests live OUTSIDE `.compass/`, integrated with the project's own code. The agent defines a centralized test structure appropriate for the project's language and framework.
3. **Write tests**: Cover the code being written or modified.
4. **Run full test suite**: Execute ALL existing tests to ensure nothing is broken.

Tests are the safety net that allows humans to trust AI-written code. Skipping tests is never acceptable.

## Status Transitions

```
draft → review → approved → active → done → archived
```

| Transition | Who | When |
|-----------|-----|------|
| draft → review | Agent | Work is complete, ready for human review |
| review → approved | Human | Human has reviewed and approved |
| approved → active | Agent/Human | Work has begun |
| active → done | Agent | Task completed, tests pass |
| done → archived | Agent/Human | Moved out of hot path |

## Required Artifacts Enforcement

A Compass project is not properly set up unless it has:

- [ ] At least one **spec** (the vision/purpose of the project)
- [ ] At least one **ADR** (a recorded decision)
- [ ] An `index.md` with links to all documents
- [ ] An `active.md` tracking current work
- [ ] A `meta/config.yaml` with numbering counters
- [ ] A `meta/lessons-catalog.yaml` (can be empty)

**If any of these are missing, the agent MUST flag this and request their creation.** These are not optional — they are the minimum viable vault.

## Compass Uses Compass

When bootstrapping a new project, Compass applies its own methodology:
- Bootstrap creates `SPEC-001` for the project setup itself
- Tasks for onboarding are tracked in `active.md`
- Decisions about project setup become ADRs

This is not a special case — it's the standard workflow applied to itself.

## File Organization

```
.compass/
├── index.md              — HOT: master map with 1-line summaries + [[links]]
├── active.md             — HOT: current tasks (in-progress + blocked + next up)
├── backlog.md            — Cold: future tasks
├── meta/
│   ├── config.yaml       — Counters for SPEC/ADR/TASK numbering
│   └── lessons-catalog.yaml — O(1) tag lookup for lessons
├── specs/                — Specifications
├── research/             — Research findings
├── plans/                — Implementation plans
├── decisions/            — Architecture Decision Records
├── lessons/              — Lessons learned
└── archive/              — Completed/retired documents
```

## Agent Protocol (Common to All Agents)

1. Read the hot path (index.md, active.md, lessons catalog)
2. Identify what you're here to do
3. Load additional context as needed (specific specs, research, plans)
4. Search for relevant lessons
5. Do the work
6. Update vault state (active.md, index.md) to reflect changes
7. Create lessons if you encountered something surprising
