---
title: "Consolidation Grounded in Sources: Research"
type: research
status: complete
confidence: low
area: methodology
tags: [lessons, consolidation, memory, drift, learning-loop]
summary: "how lessons, index lines and file:line references can be rechecked against transcripts and code, edited by delta instead of rewrite, and scored by outcome"
created: 2026-11-21
updated: 2026-11-21
spec: "[[SPEC-002-consolidation-grounded-in-sources]]"
grading: allowed
---

# Consolidation Grounded in Sources: Research

Research for [[SPEC-002-consolidation-grounded-in-sources]]. Prior evidence reused: [[research/llm-research/REVIEW-llm-research-for-compass]].

## Axes

1. **Consolidation today and delta edits** - how `plugin/skills/consolidate` works step by step, where it rewrites whole bodies, and how ACE-style delta edits and grow-and-refine would replace that. Sought in `plugin/skills/consolidate`, `plugin/skills/lesson-write`, `plugin/cli`, and the ACE paper and its descendants. File: [[research/learning/consolidation-from-sources/AXIS-1-consolidation-and-delta-edits]].
2. **Mechanical recheck against sources** - how a lesson, an index line or a `file:line` reference can be checked against the transcript, code or git history it came from, and how drift is reported with its evidence and each correction checked before it takes effect. Sought in `plugin/cli` (validate, capture, sync), lesson frontmatter, and papers on memory verification and stale-reference detection. File: [[research/learning/consolidation-from-sources/AXIS-2-recheck-against-sources]].
3. **Lesson track record** - how Compass could know whether work that cited a lesson then passed or failed. Sought in the lessons catalog, build and validator reports, capture opportunities, and papers on outcome-scored agent memory. File: [[research/learning/consolidation-from-sources/AXIS-3-lesson-track-record]].
4. **Where the pass runs** - how the detached capture worker could host a periodic recheck pass off the agent token budget, and what triggers it. Sought in `plugin/hooks`, the capture worker in `plugin/cli`, and [[compass-cli/specs/SPEC-004-mechanical-work-off-the-agent-budget]]. File: [[research/learning/consolidation-from-sources/AXIS-4-periodic-pass-host]].

Facet audit: functional (axes 1-3), non-functional cost and reliability (axis 4), interfaces (axes 2, 4), constraints Data rule and off-budget work (axes 1, 2, 4), stakeholder context (axis 2, corrections the human can check).

Grading: allowed (the human waived the axis gate).

Gap pass: [[research/learning/consolidation-from-sources/AXIS-5-gap-pass]] - KPI probe, correction admission, cost per pass, source reach from a fresh clone.

Review: [[research/learning/consolidation-from-sources/REVIEW-consolidation-from-sources]].

## Status

- Axes 1-4 and the gap pass complete; the review consolidates them.
