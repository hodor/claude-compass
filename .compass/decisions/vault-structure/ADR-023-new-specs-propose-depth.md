---
title: "A New Spec Is Offered Its Deeper Home; the Human Decides"
type: decision
status: accepted
confidence: medium
area: methodology
tags: [taxonomy, specs, placement, human-gates]
created: 2026-10-25
updated: 2026-10-25
author: "orchestrator"
summary: "when a new spec has a candidate parent or pair, the authoring agent proposes the deeper home as one question; shallow plus a taxonomy_hint only when the human declines or nothing fits"
depends_on: ["[[specs/vault-structure/SPEC-022-vault-organized-per-domain]]", "[[research/vault-structure/RESEARCH-taxonomy-for-unambiguous-placement]]"]
---

# A New Spec Is Offered Its Deeper Home; the Human Decides

## Fork

Spec creation filed shallower whenever placement was uncertain, recording a `taxonomy_hint` for a later consolidation, the stop-at-the-coarser-correct-ancestor rule from [[research/vault-structure/RESEARCH-taxonomy-for-unambiguous-placement]]. Under that rule no spec in the vault ever gained a child. [[specs/vault-structure/SPEC-022-vault-organized-per-domain]] D-04 asks for a taxonomy review at creation that adds depth when needed. Three answers were live: keep shallow-when-unsure, place deep by default without asking, or propose the deeper home and let the human decide. The human chose the third.

## Decision

- **D-01:** When `compass placement` finds a candidate parent or pair for a new spec, the authoring agent proposes the deeper home as one question to the human, the best fit first. The spec is filed shallow with a `taxonomy_hint` only when the human declines or no candidate fits. An approved move runs in the same step, so no folder is left holding only its index.

## Consequences

Good: depth arrives at the moment the author understands the spec best; a wrong deep guess is caught by the human before it lands; the hint queue stops being the only path to structure; `compass move` and `compass demote` keep a reversal cheap.

Bad: spec creation gains one question whenever a candidate exists, which costs the human attention on every such spec; the quality of the proposal rests on how well `compass placement` ranks its evidence; a human who approves by habit can let a weak proposal through.
