---
title: "Capture by Extraction (interview-skill rewrites, pipeline-rule scope line)"
type: plan
status: done
completed: 2026-08-29
approved: 2026-08-29
confidence: high
area: methodology
tags: [verbatim, capture, skills, vision, spec-writing]
created: 2026-08-29
updated: 2026-08-29
author: "orchestrator"
summary: "implement ADR-016 across spec/vision/specs/retroactive skills and the pipeline rules; ship via push + fleet self-update; acceptance by re-reading the changed instructions against every D"
depends_on: ["[[SPEC-021-capture-in-the-humans-words]]", "[[ADR-016-capture-by-extraction]]", "[[RESEARCH-humans-words-fidelity]]"]
---

# Capture by Extraction

## Goal

Implements every D of [[ADR-016-capture-by-extraction]]. Prose-only change to skill instructions; no CLI code.

Approved 2026-08-29 under Roger's blanket go; stations collapsed into the main thread.

## Tasks

- [x] TASK-098: spec skill - interview step extracts and arranges, clean-verbatim tier, [unclear] flags, verbatim rerouting, walkthrough-as-member-checking note (M)
- [x] TASK-099: vision skill - braindump "organize" means arrange his sentences; needs list and vision doc sections carry his words; specs + retroactive skills same discipline (M, after 098)
- [x] TASK-100: pipeline rules Document Writing gains the one scope sentence; suite green; version bump; push; fleet vault verified pulling the release via self-update (S, after 099)
  - Automated: grep shows the new rules present in all four skills; `python -m pytest tests/ -q` green; one fleet vault's `compass self-update` reports the new version.
