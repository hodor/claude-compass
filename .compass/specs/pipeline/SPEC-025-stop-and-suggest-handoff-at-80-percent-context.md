---
title: "Stop and Suggest a Handoff at 80% Context Usage"
type: spec
status: approved
confidence: low
area: methodology
tags: [handoff, context-window, session-continuity, hooks]
summary: "Compass automatically stops working and suggests a handoff when the session reaches 80% of context usage"
created: 2026-10-02
updated: 2026-11-21
approved: 2026-10-02
---

# Stop and Suggest a Handoff at 80% Context Usage

## Problem

[guess: Compass keeps working as the session's context fills up, and nothing makes it stop before the session runs out of room for a clean handoff.]

When a session fills, its history is carried forward as a model-written summary: the host's compaction summary, or the handoff Compass suggests at 80%. Research found summaries lose what the next session needs and make runs longer, 13 to 15% on coding tasks, and every summarizing method studied lost the trail of which files were touched ([[research/llm-research/REVIEW-llm-research-for-compass]]). The host (the tool running the model, such as Claude Code) announces compaction before and after it runs, and Compass does nothing at either point, so what survives compaction is left to the host's summary alone.

## Desired Outcome

Compass automatically STOPs working and suggests a handoff when we reach 80% of context usage.

KPI: [guess: every session that reaches 80% context usage stops and suggests a handoff; zero sessions continue working past 80%.]

A session that continues past a full context keeps the state its next step depends on (open tasks, files touched, decisions taken) in front of the model, with as little model-written summary as possible.

KPI: [guess: after a compaction or a handoff, probe questions on recall, artifacts, the next step and decisions taken are answered as well as before it, at fewer tokens than a model-written summary.]

## Decisions

- **D-01:** Stopping means finishing the current step, then stopping before starting the next one; work is never cut off mid-step.
- **D-02:** 80% means 80% of the whole context window.
- **D-03:** Claude Code is built first; dsh follows once dsh hooks receive a transcript path and honor a halt ([[research/pipeline/RESEARCH-context-threshold-stop]]).
- **D-04:** The suggestion is made once. If the human declines, work continues, and the handoff is suggested one more time at 95% context usage.
