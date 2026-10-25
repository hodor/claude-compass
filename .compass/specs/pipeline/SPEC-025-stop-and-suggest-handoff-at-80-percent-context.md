---
title: "Stop and Suggest a Handoff at 80% Context Usage"
type: spec
status: approved
confidence: low
area: methodology
tags: [handoff, context-window, session-continuity, hooks]
summary: "Compass automatically stops working and suggests a handoff when the session reaches 80% of context usage"
created: 2026-10-02
updated: 2026-10-02
approved: 2026-10-02
---

# Stop and Suggest a Handoff at 80% Context Usage

## Problem

[guess: Compass keeps working as the session's context fills up, and nothing makes it stop before the session runs out of room for a clean handoff.]

## Desired Outcome

Compass automatically STOPs working and suggests a handoff when we reach 80% of context usage.

KPI: [guess: every session that reaches 80% context usage stops and suggests a handoff; zero sessions continue working past 80%.]

## Decisions

- **D-01:** Stopping means finishing the current step, then stopping before starting the next one; work is never cut off mid-step.
- **D-02:** 80% means 80% of the whole context window.
- **D-03:** Claude Code is built first; dsh follows once dsh hooks receive a transcript path and honor a halt ([[research/pipeline/RESEARCH-context-threshold-stop]]).
- **D-04:** The suggestion is made once. If the human declines, work continues, and the handoff is suggested one more time at 95% context usage.
