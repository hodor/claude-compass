---
title: "Graph Queries Are Computed JIT from the Markdown at Invocation; compass graph Ships Orphans, Hubs, and Impact with Their Consumers"
type: decision
status: accepted
confidence: high
area: methodology
tags: [graph, queries, orphans, hub-ranking, impact-traversal, cli]
created: 2026-08-29
updated: 2026-08-29
author: "orchestrator"
summary: "no derived store: compass graph parses edges (depends_on, wikilink, containment) at query time so staleness cannot exist; orphans/hubs/impact ship wired into vault-health, checkup, unit-check's hub guard, and a planner ripple step"
depends_on: ["[[SPEC-011-vault-graph-queries]]", "[[RESEARCH-grep-vs-graph-experiment]]", "[[RESEARCH-graph-engineering-for-compass]]"]
---

# Graph Queries JIT over Markdown

## Context

[[SPEC-011-vault-graph-queries]] scopes three query classes by their consumers (D-04): orphan detection (vault-health, checkup crawl today), hub ranking (unit-check's recorded dominance defect), impact traversal (planner miscounted by hand in both directions). D-01 forbids a new store; answers must be edge-auditable, staleness-detectable, and off the agent budget.

## Decision

- **D-01: No derived artifact at all - the graph is parsed from the markdown at every invocation.** ~120 files parse in well under a second; a store would buy nothing and would create the staleness problem the spec demands we detect. Computed-at-invocation makes the consistency requirement vacuously true, which is the strongest way to satisfy it.
- **D-02: Three structural edge kinds, and prose is not an edge.** `depends_on` (frontmatter wikilinks), `wikilink` (body links outside code fences and inline code, the same iteration `validate` trusts), `containment` (a folder artifact's `index.md` to the children inside it). A document's bare name in prose creates nothing - the manual disambiguation the experiment showed failing is gone by construction. Ambiguous names resolve to no edge, matching `unit-check`.
- **D-03: One command, `compass graph`, three subcommands, every answer naming its edges.** `orphans` (zero inbound excluding the root `index.md` catalog rows - the subtle definition the spec pins, encoded once), `hubs [--top N]` (inbound degree, `depends_on` and `wikilink` counted separately), `impact <name> [--depth N]` (inbound BFS, default depth 2, each hop printed as `src -[kind]-> dst` so the consumer audits edges, not totals).
- **D-04: Consumers ship in the same release.** vault-health's and checkup's orphan steps become one CLI call; `find_candidates` gains a hub-dominance guard (a spec with inbound `depends_on` degree at or above 10 stops seeding candidate groups - SPEC-001 measures 17, the next real candidate seed well under the cap); the planner template gains a ripple step that runs `compass graph impact` on each source spec and records the answer in the plan.
- **D-05: Validation recomputes ground truth live** - hub order checked against an independent grep tally at validation time, the SPEC-003 closure recomputed rather than compared to the experiment's known-wrong set.

## Consequences

- Deletions, renames, and CLI moves need no special handling: the next query reads the disk.
- Query cost is a full-vault parse per invocation - acceptable now, and the JIT boundary is one function (`graphlib.build_graph`) behind which a cache could sit if a vault ever grows enough to hurt.
- `unit-check`'s candidate list shrinks: SPEC-001's mega-group disappears, which is the recorded defect being fixed, not information lost.
