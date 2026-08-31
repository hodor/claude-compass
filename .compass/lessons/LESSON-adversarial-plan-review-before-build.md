---
title: Multi-lens adversarial review of specs and plans catches what authors cannot see
type: lesson
status: active
category: process
area: methodology
tags: [review, plans, specs, adversarial, multi-lens, measurement]
taxonomy_hint: "pipeline once a second workflow-review lesson arrives"
created: 2026-08-08
updated: 2026-08-30
score: 9
summary: "Review specs/plans with 3 adversarial lenses before approval, and have reviewers measure against the real corpus, not opine"
seen: [2026-08-11, 2026-08-24, 2026-08-30]
---

Before human approval, review a spec or plan with parallel adversarial lenses (evidence-fidelity, mechanism-attack, product/YAGNI); authors cannot see their own scope inversions or mechanism holes.
Three instances: a spec review inverted a scope to match real consumers; a plan review found five blocking mechanism bugs (inert verify, one-line checkpoint bypass, undefined green) pre-build; a second plan review found four mechanism-level defects and twenty supporting gaps (hooks in headless sessions, run lock semantics, grace arithmetic, file ownership), all post-approval amendments.
Give reviewers the real corpus and require measurements: measured false-positive rates retired two planned calibration tasks and unfitted a check that could not fire on its own ground truth.
