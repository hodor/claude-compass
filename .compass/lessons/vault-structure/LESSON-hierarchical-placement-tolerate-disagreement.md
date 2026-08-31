---
title: Hierarchical Placement Should Tolerate Disagreement, Not Assume Convergence
type: lesson
status: active
category: domain
area: methodology
tags: [taxonomy, classification, hierarchical-placement, literature-import, confidence-threshold]
created: 2026-08-30
updated: 2026-08-30
score: 5
summary: "Inter-indexer agreement is inherently low; stop at a correct coarse ancestor rather than force a wrong specific leaf"
source: "extract-lessons:interval:OPP-20260830T185106235068Z"
seen: []
---

Human indexer studies since the 1960s find inconsistency inherent, not fixable: 10-60% agreement across studies, worse with more/narrower categories per item (Markey 1984, Sievert & Andrews 1991).
Hierarchical classifiers show the matching failure: a wrong top-level pick can't be corrected lower in the tree (Silla & Freitas); the documented mitigation stops at a correct-but-coarser ancestor when confidence is low, rather than forcing a specific wrong leaf.
Apply to Compass's own domain-folder placement: design for graceful re-filing, not first-placement accuracy - park a doc at a correct parent over guessing a wrong child.
