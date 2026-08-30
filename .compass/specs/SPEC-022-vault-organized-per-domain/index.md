---
title: "The Vault Is Organized Per Domain, Recursively; the Index Speaks in Broad Areas"
type: spec
status: approved
approved: 2026-08-30
confidence: high
area: methodology
tags: [taxonomy, hierarchy, domains, index, consolidation, hot-path]
created: 2026-08-30
updated: 2026-08-30
depends_on: ["[[SPEC-003-hierarchical-vault-organization]]", "[[SPEC-010-universal-hybrid-hierarchy]]", "[[SPEC-005-index-auto-maintained-and-mirrored-per-folder]]"]
summary: "similar specs and research group into domain folders, recursively; the root index says one line per broad area instead of dropping every artifact flat (approved 2026-08-30, Roger's ruling)"
---

# The Vault Is Organized Per Domain, Recursively

## Problem

In Roger's words (2026-08-30, on seeing consolidation stall against a flat index): "Clearly the problem is you're not aggregating things. So what you should be doing is kinda like taxonomy. You need to get things similar grouped together and put it in a single research folder, single spec folder. And then in the index, you say: this is about this broad area. Right now you have everything - every single spec, single research - just dropped there. You're not putting them together. So that, of course, will never allow you to really consolidate. Consolidation is also taxonomy."

The evidence agrees with him. This vault's root index lists 22 specs, 35 research docs, 20 ADRs, 15 plans - one line each, flat, 3,796 tokens of index in a 5,000-token hot-path cap, and consolidation just proved it can only trim lessons because everything else is already non-redundant *lines*: the redundancy is structural, not textual. Meanwhile the grouping machinery has existed for months - folder specs nest to any depth ([[SPEC-010-universal-hybrid-hierarchy]]), `/compass:taxonomize` was built for exactly this bulk migration - and the usage record shows taxonomize has never run anywhere, while `doctor` reports 17 unit-promotion candidates nobody acted on. The same disease [[SPEC-017-capabilities-are-reachable-and-measured]] named: capability shipped, nothing drives it.

## Desired Outcome

In his words: "In this organization, you should go per domain. Right? The same way you organize mathematics into multiple thousands of subdomains, each subdomain is gonna have another subdomain. This needs to be done with both specs, research, anything else inside Compass."

- Similar artifacts live grouped in domain folders - specs with their kin, research with its kin - recursively: a domain can hold subdomains, any depth.
- The root index says one line per broad area, with the area's own index carrying its members. Not every artifact dropped flat at the root.
- Consolidation includes this grouping: when the index is what's over cap, the move is taxonomy - group and point - not trimming lines.
- The grouping actually runs on this vault, not just ships as capability.

## Decisions (made by the human)

- **D-01:** "Consolidation is also taxonomy." When the hot path is over cap and the weight is structural (many flat lines), the remedy is grouping into domains, never deleting or truncating entries. (Roger, 2026-08-30.)
- **D-02:** Per-domain organization applies to everything in the vault - "both specs, research, anything else inside Compass" - and recurses: subdomains within domains, "the same way you organize mathematics." (Roger, 2026-08-30.)

## Non-Goals

- Losing anything - covered by the resident Data rule; grouping moves files, wikilinks keep resolving.
- Inventing domains speculatively. Domains come from what the artifacts already are; the human approves the grouping of his own knowledge.
- Lessons - the catalog is their index (v0.14.2); they group by tags already.
