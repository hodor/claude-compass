---
title: "Research: verification beyond test-pass"
type: research
status: complete
confidence: low
area: testing
tags: [research, testing, verification, reachability, spec-coverage]
summary: "how Compass can confirm new code is reached, tests depend on the change, and code meets the spec"
created: 2026-11-21
updated: 2026-11-21
spec: "[[SPEC-034-verification-beyond-test-pass]]"
grading: allowed
---

# Research: verification beyond test-pass

Traces to [[SPEC-034-verification-beyond-test-pass]]. Builds on [[research/llm-research/REVIEW-llm-research-for-compass]] (section A3, items B8 and B9) and [[research/test-quality/RESEARCH-test-quality-synthesis]], which covers mutation testing.

## Axes

1. **Reachability** - how to check cheaply, across languages, that new code is reached from the deliverable's real entry points (a command, a user action). Sought in static call-graph and coverage tooling, and in the `plugin/` CLI as a worked case. File: [[research/test-quality/beyond-test-pass/RESEARCH-reachability]].
2. **Tests depend on the change** - change-ablation (stub or revert the diff, see which tests flip): cost, tooling, and how it relates to diff-scoped mutation testing. Sought in mutation and test-adequacy literature and tools, run on a `plugin/` example. File: [[research/test-quality/beyond-test-pass/RESEARCH-change-ablation]].
3. **Code meets the spec** - comparing code against each spec requirement (spec-kit converge style) against Compass's decision coverage, and how an unmet requirement comes back as open work; includes a builder review charter of correctness against the spec, skipping style (B8). Sought in spec-driven tools, LLM-judge literature, and `plugin/` templates. File: [[research/test-quality/beyond-test-pass/RESEARCH-spec-conformance]].
4. **Integration and evidence** - where the three checks sit in Compass's builder, tester and validator today, how a done claim stays checkable by rerunning its evidence, and checker independence: the reviewer matrix recording model family, with same-family agreement capped (B9). Sought in `plugin/` code and agent templates, plus judge-independence literature. File: [[research/test-quality/beyond-test-pass/RESEARCH-integration-and-evidence]].

Facet audit: functional (axes 1-3), non-functional cost (axes 1, 2), interfaces (axis 4), constraint "checkable by rerunning evidence" (axis 4), stakeholder context (axis 3, unmet work returned to the human's pipeline).

Grading: allowed (the human waived the axis gate).

## Status

- All four axes complete. Consolidation: [[research/test-quality/beyond-test-pass/REVIEW-beyond-test-pass]]. A gap pass on non-CLI entry points (web route, UI action, hook subprocess) is appended to the reachability file.
