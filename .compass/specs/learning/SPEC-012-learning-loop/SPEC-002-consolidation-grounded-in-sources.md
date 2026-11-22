---
title: "Consolidation Is Grounded in Sources"
type: spec
status: approved
confidence: low
area: methodology
tags: [lessons, consolidation, memory, drift, learning-loop]
summary: "lessons and index claims stay true to the transcripts and code they came from: drift is found and reported, and each lesson's track record is known"
created: 2026-11-21
updated: 2026-11-21
depends_on: ["[[SPEC-012-learning-loop]]", "[[research/llm-research/REVIEW-llm-research-for-compass]]"]
---

# Consolidation Is Grounded in Sources

```mermaid
flowchart LR
  P["Problem: lessons and index claims<br/>are never rechecked against their<br/>sources; whole-context model<br/>rewrites erode detail"] --> O["Outcome: memory stays true<br/>to its sources, drift is visible,<br/>and each lesson's track record<br/>is known"]
```

> [!IMPORTANT]

## Problem

The vault's memory (lessons, index lines, `file:line` references) drifts from what it describes, and nothing notices ([[research/llm-research/REVIEW-llm-research-for-compass]]).

- **Nothing rechecks memory against its sources.** A lesson is written or revised when a capture fires, and consolidation runs only when a size cap is hit. After that, no step reads the transcript a lesson came from or the code a `file:line` reference points at to confirm it still holds. Stale instructions are followed and never repaired.
- **A whole-context model rewrite erodes detail.** Consolidation asks a model to rewrite verbose lesson bodies. A peer-reviewed study measured whole-context model rewrites of an agent's memory as harmful: accuracy fell below having no memory at all.
- **Lessons carry no outcome.** A lesson's score counts how often it recurs, never whether work that cited it then passed or failed, so a lesson that misleads looks the same as one that helps.

## Desired Outcome

Lessons, index lines and code references are rechecked against the transcripts and code they came from. What no longer holds is reported as drift with the evidence beside it, and every correction can be checked on its own before it takes effect. Whether the work that cited each lesson passed or failed is known.

KPI: [guess: on a sample of lessons and index lines where a known share was made stale on purpose, the recheck reports the stale ones and no fresh ones; [[SPEC-028-agent-memory-is-good-enough]] may supply the measure.]

## Constraints

- Nothing destroys information (the Data rule): drift is reported, and stale text moves colder; it is never deleted.
- Mechanical work stays off the agent token budget ([[compass-cli/specs/SPEC-004-mechanical-work-off-the-agent-budget]]).
