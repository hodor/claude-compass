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
summary: "similar specs and research group into domain folders, recursively; the root index says one line per broad area instead of dropping every artifact flat (approved 2026-08-30)"
---

# The Vault Is Organized Per Domain, Recursively

## Problem

Every spec and every research doc is dropped flat at the root, one index line each - 22 specs, 35 research docs, 20 ADRs, 15 plans, 3,796 tokens of index against a 5,000-token hot-path cap - and consolidation can only trim lessons, because the other lines are individually non-redundant: the redundancy is structural. Things that belong together are not together, so consolidation has nothing to merge. Consolidation is also taxonomy.

The grouping machinery has existed for months - folder specs nest to any depth ([[SPEC-010-universal-hybrid-hierarchy]]), a bulk-migration skill was built for exactly this - and the usage record shows it never ran anywhere, while `doctor` reported 17 unactioned grouping candidates. The same disease [[SPEC-017-capabilities-are-reachable-and-measured]] names: capability shipped, nothing drives it.

## Desired Outcome

Organization is per domain, the way mathematics is organized into subdomains and each subdomain into further subdomains - for specs, research, and everything else in the vault.

- Similar artifacts live grouped in domain folders, recursively: a domain can hold subdomains, any depth.
- The root index says one line per broad area. An area's contents are the folder itself.
- Consolidation includes this grouping: when the index is over cap and the weight is structural, the move is taxonomy - group and point - never trimming entries.
- The grouping actually runs on this vault, not just ships as capability.

The goal: two things at once - how humans organize topics and how machines organize topics - such that there is no ambiguity about which main area holds the information you need.

## Decisions (made by the human)

- **D-01:** Consolidation is also taxonomy. When the hot path is over cap and the weight is structural (many flat lines), the remedy is grouping into domains, never deleting or truncating entries.
- **D-02:** Per-domain organization applies to everything in the vault - specs, research, anything else - and recurses: subdomains within domains.
- **D-03:** The filesystem is the taxonomy; an index is a view of one level. This is not about organizing the index file - the files themselves are organized in a folder structure that enforces the taxonomy. The index explains the first level; entering a folder shows that folder's first level; and so on down.
- **D-04:** Taxonomize applies at spec creation. Making a new spec is a reorganization point: place it, or at least leave a hint for the next consolidation - recorded by the authoring agent, which understands the spec better than any later pass.
- **D-05:** Each folder has its own index doc. Revives [[SPEC-005-index-auto-maintained-and-mirrored-per-folder]], on hold since 2026-06-19.
- **D-06:** The classification-science research (how humans and machines organize topics; placement without ambiguity) is the most important axis - it grounds the design; the codebase and design-space axes serve its findings, not the reverse.
- **D-07:** Reorganization moves are suggested to the human, never something the human must remember to trigger. The harness notices the trigger - ceiling breach, pending hints, cap warning - and puts the proposal forward; approval applies it.
- **D-08:** The folder itself is the listing; the index is the meaning. `ls` on a folder shows exactly what is in it; its index says what it is about. Generated member listings inside indexes are rejected: they make every change cost three writes - the file, the folder, and the listing.
- **D-09:** No forced domain count - a limit may be suggested, never imposed. The real rule is orthogonality, plus the depth gradient: the deeper a subtree is, the more generic its top must be. Ten spec folders with ten completely orthogonal topics are fine.

## Non-Goals

- Losing anything - covered by the resident Data rule; grouping moves files, wikilinks keep resolving.
- Inventing domains speculatively. Domains come from what the artifacts already are; the human approves the grouping of his own knowledge.
- Lessons - the catalog is their index; they group by tags already.
