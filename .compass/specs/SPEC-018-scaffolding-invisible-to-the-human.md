---
title: "Compass's Scaffolding Runs in Full and the Human Never Has to Read It"
type: spec
status: approved
approved: 2026-08-24
confidence: high
area: methodology
tags: [conversation-surface, hooks, capture, noise, autonomy, human-attention]
taxonomy_hint: "learning holds its capture half, but it governs every machinery surface"
created: 2026-08-24
updated: 2026-08-24
summary: "the machinery keeps running - capture passes, checks, agent relays - but none of it occupies the human's conversation"
depends_on: ["[[SPEC-012-learning-loop]]", "[[SPEC-004-mechanical-work-off-the-agent-budget]]"]
---

# Compass's Scaffolding Runs in Full and the Human Never Has to Read It

## Problem

Compass's machinery occupies the conversation the human is trying to have. A capture hook blocks the turn and its announcement is printed to the human; while the pass runs, every further turn repeated the announcement; agent spawns and completions surface as notices; the orchestrator relays status between them. Observed 2026-08-24, in Compass's own development session: the human asked one question and six turns of scaffolding landed in front of the answer, four of them literally the orchestrator saying it was still waiting.

The human's words: "all that shit is noise to me. I just want to read what you tell me. I don't want to have to read all of the scrap that you're doing. This is a problem with all of Compass."

[[SPEC-004-mechanical-work-off-the-agent-budget]] moved bookkeeping off the agent's token budget. This is the same problem one level up: the work moved off the token budget and onto the human's reading budget, which is the scarcer resource.

## Who is affected

- The human, whose attention is spent on scaffolding instead of outcomes.
- Every Compass user, since the capture loop and build flow ship to all of them.
- The pipeline itself: a human trained to skim past Compass output also skims past the one line that mattered.

## Decisions (made by the human)

- **D-01:** The scaffolding stays. Nothing about the capture loop, the checks, or the passes is reduced or removed; the fix is to hide it.
- **D-02:** Agents run the show. The pipeline proceeds without consulting the human step by step; the human is engaged at real gates - spec promotion, plan approval, escalations - and otherwise reads outcomes.

## Desired Outcome

Everything Compass does today keeps happening - capture, extraction, checks, reconciliation - and the human's conversation carries only what the human needs: answers, outcomes, and the questions only they can rule on. A background completion costs the human at most one line, and routine machinery costs them nothing. Status lives in logs and the vault, where it can be pulled when wanted, instead of being pushed into the transcript.

## Needs

- Background passes execute without drafting the main conversation as their runner or their messenger.
- A hook that must communicate with the model does so without printing to the human, or in the fewest lines the harness allows.
- Progress and status are readable on demand from logs and vault state, never streamed into the transcript.
- The pipeline's default posture between gates is silent forward motion; surfacing something mid-flow is reserved for blockers and escalations.

## Non-Goals

- Removing or weakening any scaffolding (D-01 forbids it).
- Choosing the mechanism - whether hidden execution means detached headless workers, harness features, or something else is research and ADR territory.
- Changing what the harness itself renders (task notices are Claude Code's surface); the spec governs what Compass feeds into it.

## Open Questions

- What execution substrates can run a capture pass with zero conversation footprint on this harness, and what does each cost?
- Which of the noise observed is Compass's to fix versus fixed only by the harness?
