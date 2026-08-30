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

The goal, in his words (2026-08-30): "what we're talking about here for taxonomy is 2 things - how humans organize topics and how machines organize topics. The main goal is to have it organized in a way that there is no ambiguity in which main area you should go to find the info you need."

## Decisions (made by the human)

- **D-01:** "Consolidation is also taxonomy." When the hot path is over cap and the weight is structural (many flat lines), the remedy is grouping into domains, never deleting or truncating entries. (Roger, 2026-08-30.)
- **D-03:** "This is NOT about organizing the index file, it's about always organizing all the files in a folder structure that enforces taxonomy - this IS CRITICAL for us." The filesystem is the taxonomy; every index is just a view of one level: "the index just explains the first level of that structure, and if you go into that folder you just see the first level of that folder, and so on." (Roger, 2026-08-30.)
- **D-04:** Taxonomize applies at spec creation too: "when making a new spec is a good point to reorganize if needed, and at least mark for the next consolidate/taxonomize a hint - by the agent who understands the spec better than others." (Roger, 2026-08-30.)
- **D-05:** "Each folder should have its own index.md!" (Roger, 2026-08-30.) This revives [[SPEC-005-index-auto-maintained-and-mirrored-per-folder]], on hold since 2026-06-19 - the per-folder index is the view of that folder's first level.
- **D-06:** The classification-science research (how humans and machines organize topics, placement without ambiguity) "should be the most important one" - it grounds the design; the codebase and design-space axes serve its findings, not the reverse. (Roger, 2026-08-30.)
- **D-07:** Reorganization moves "need to be suggested to the user, it cannot be something the user has to remember to trigger." (Roger, 2026-08-30, on PLAN-016's hand-run migration wording.) The harness notices the trigger - ceiling breach, pending hints, cap warning - and puts the proposal in front of him; his approval applies it. Nothing waits on human memory.
- **D-08:** The folder itself is the listing; the index is the meaning. "Ideally you should just do an ls on the specs folder to understand exactly what's in there, and read the index to understand what it should be about" - generated member listings inside indexes are rejected: "every time you make a change you have to change the file, the folder and this thing." (Roger, 2026-08-30, confirming after discussion.)
- **D-09:** No forced domain count: "we don't have to force a limit, we can suggest a limit but the real rule is that it needs to be orthogonal and DEPENDING ON HOW DEEP IT IS we need the top to be more generic. So the deeper it is, the more generic the top has to be. It's completely fine to have 10 different spec folders with 10 completely orthogonal topics." (Roger, 2026-08-30.)
- **D-02:** Per-domain organization applies to everything in the vault - "both specs, research, anything else inside Compass" - and recurses: subdomains within domains, "the same way you organize mathematics." (Roger, 2026-08-30.)

## Non-Goals

- Losing anything - covered by the resident Data rule; grouping moves files, wikilinks keep resolving.
- Inventing domains speculatively. Domains come from what the artifacts already are; the human approves the grouping of his own knowledge.
- Lessons - the catalog is their index (v0.14.2); they group by tags already.
