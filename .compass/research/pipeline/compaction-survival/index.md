---
title: "What Survives Compaction and Handoff"
type: research
status: complete
confidence: medium
area: methodology
tags: [handoff, context-window, compaction, hooks, session-continuity]
summary: "Evidence on keeping open tasks, files touched and decisions in front of the model after a compaction or handoff, with as little model-written summary as possible"
created: 2026-11-21
updated: 2026-11-21
depends_on: ["[[specs/pipeline/SPEC-025-stop-and-suggest-handoff-at-80-percent-context]]"]
---

# What Survives Compaction and Handoff

Evidence for the compaction-survival need of [[specs/pipeline/SPEC-025-stop-and-suggest-handoff-at-80-percent-context]]: a session that continues past a full context keeps the state its next step depends on in front of the model, with as little model-written summary as possible. The 80% stop itself is covered by [[research/pipeline/RESEARCH-context-threshold-stop]]. Prior evidence: [[research/llm-research/REVIEW-llm-research-for-compass]] rows 13 and 14, candidate C5.

grading: allowed.

## Axes

1. **Host compaction hooks.** What PreCompact, PostCompact and SessionStart with `source: compact` receive and what their output can inject or steer, confirmed by a local trial on Claude Code. Sought in: Claude Code hook docs, a live probe. File: [[research/pipeline/compaction-survival/RESEARCH-axis-1-compaction-hooks]].
2. **Masking versus summary.** Which carry-forward method keeps the next step's state at the lowest token cost: observation masking, rule-based elision, structured or anchored summaries, free summaries. Sought in: arXiv and vendor engineering posts, 2025-2026. File: [[research/pipeline/compaction-survival/RESEARCH-axis-2-masking-vs-summary]].
3. **Mechanical state assembly.** Which of open tasks, files touched and decisions taken Compass can assemble from the transcript, the vault and git with no model call, and what the handoff skill and hooks carry today. Sought in: `plugin/` code, a session transcript's structure. File: [[research/pipeline/compaction-survival/RESEARCH-axis-3-mechanical-state]].
4. **Probe-based measurement.** How Factory's probe evaluation (recall, artifact, continuation, decision) works and how Compass can run it as the KPI on its own sessions. Sought in: Factory's post, follow-on work, `bench/`. File: [[research/pipeline/compaction-survival/RESEARCH-axis-4-probe-kpi]].

## Review

All four axes are written. Consolidation: [[research/pipeline/compaction-survival/REVIEW-compaction-survival]].

## Measurements

- [[research/pipeline/compaction-survival/RESEARCH-probe-pilot]] - Eight recorded compactions, two arms, 16 tool-less sessions: the host summary scores artifact recall 0.31, continuation 0.33, decision 0.67 and recall 0.00 against a floor of 0.00 everywhere; no reply failed to parse; artifact and continuation probes are frequent enough to compare arms, recall and decision are not
- [[research/pipeline/compaction-survival/RESEARCH-probe-arm-comparison]] - 29 recorded compactions, four arms: with the revised state block, which lists the edited files in every block, the host summary plus the block names more edited files than the summary alone (0.67 against 0.45, interval [0.12, 0.32]) at 50% more tokens; the block alone carries 48% fewer tokens, matches the summary on files and loses on continuation and the pooled state score
- [[research/pipeline/compaction-survival/RESEARCH-probe-reference-arms]] - A session rebuilt from the history before a recorded compaction loads headless with no tools and answers from that history, so the before and handoff arms resume it rather than reading the history as text
