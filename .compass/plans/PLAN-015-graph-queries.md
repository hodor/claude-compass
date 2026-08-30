---
title: "Graph Queries (graphlib, compass graph, consumer wiring, ripple step)"
type: plan
status: done
completed: 2026-08-29
approved: 2026-08-29
confidence: high
area: methodology
tags: [graph, orphans, hub-ranking, impact-traversal, cli]
created: 2026-08-29
updated: 2026-08-29
author: "orchestrator"
summary: "implement ADR-018: graphlib edge parser, compass graph orphans/hubs/impact, unit-check hub guard, vault-health/checkup orphan steps become CLI calls, planner ripple step; live validation against recomputed ground truth; ship v0.13.0"
depends_on: ["[[SPEC-011-vault-graph-queries]]", "[[ADR-018-graph-queries-jit-over-markdown]]", "[[RESEARCH-grep-vs-graph-experiment]]"]
lessons: ["[[LESSON-wikilink-validator-skip-code]]", "[[LESSON-verify-the-inverse-not-the-forward-path]]"]
---

# Graph Queries

## Goal

Implements every D of [[ADR-018-graph-queries-jit-over-markdown]]. Approved 2026-08-29 under the standing go; stations collapsed into the main thread, tests red-first.

## Ripple (compass graph impact, run at plan time once TASK-105 lands)

`compass graph impact SPEC-011-vault-graph-queries` (run live, exercising the planner ripple step on a real plan per the spec's success criterion): hop 1 - active.md, ADR-018, PLAN-015 (this plan), PLAN-006, RESEARCH-grep-vs-graph-experiment, SPEC-012, one handoff, each via depends_on or wikilink edges named in the output; hop 2 fans out through PLAN-006 and SPEC-012 into the learning-loop lineage. Consumers changed by edit (vault-health, checkup, planner) carry no dependency edge, which the traversal correctly does not invent.

## Tasks

- [x] TASK-105: `graphlib.py` (build_graph: nodes, typed edges, fence-aware, ambiguity-safe) + `commands/graph.py` (orphans, hubs, impact) with adversarial tests red-first (L)
- [x] TASK-106: unit-check hub-dominance guard (inbound depends_on >= 10 stops seeding), with a test proving SPEC-001-shaped dominance is guarded and threshold-3 fixtures unaffected (S, after 105)
- [x] TASK-107: consumers - vault-health + checkup orphan steps call `compass graph orphans`; planner template ripple step (S, after 105)
- [x] TASK-108: live validation - hub order vs independent grep tally, SPEC-003 closure recomputed and spot-audited, orphan run on this vault; suite green; v0.13.0; push; fleet pull verified (M, after 106/107)
