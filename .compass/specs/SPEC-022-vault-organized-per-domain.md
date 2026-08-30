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

Before this spec every spec and every research doc is dropped flat at the root and consolidation can only trim lessons, because the other lines are individually non-redundant: the redundancy is structural. Things that belong together are not together, so consolidation has nothing to merge. Consolidation needs to happen guided through taxonomy.

The grouping machinery exists at ([[SPEC-010-universal-hybrid-hierarchy]]), a bulk-migration skill was built for this - and the usage record shows it never ran anywhere, while `doctor` reported 17 unactioned grouping candidates. The same disease [[SPEC-017-capabilities-are-reachable-and-measured]] names: capability shipped, nothing drives it. The root issue here is that the user will not remember to use all of these functionalities unless we present to the user or make it run automatically. Which on it's one might require a high level UX spec. 

## Desired Outcome

Organization is per domain, the way mathematics is organized into subdomains and each subdomain into further subdomains - for specs, research, and everything else in the vault.

- Similar artifacts live grouped in domain folders, recursively: a domain can hold subdomains, any depth.
- The root index should explain each area on it's current level only and not be verbose. The idea is that the complexity grows the deeper you go. So more explanations - that are needed - will be found deeper in the structure.
- Consolidation includes this grouping: when the index is over cap and the weight is structural, the move is taxonomy - group and point - never trimming entries. It's ok for the trigger to be token size that is needed to operate. The real metric that we need is to understand how much "useless" tokens we're getting for a specific task. The goal of this spec is to bring that useless token to 0.
- As everything else in compass, this spec should also run on this vault, not just ships as capability. And we use this vault as the first alpha tester.
- We should never delete or lose information when optimizing the way information is distributed.

The goal: two things at once - how humans organize topics and how machines find topics and how to minimize cache misses - there shouldn't be ambiguity about which area holds the information you need.

## Decisions

- **D-01:** Consolidation is also taxonomy. When the hot path is over cap and the weight is structural (many flat lines), the remedy is grouping into domains, never deleting or truncating entries.
- **D-02:** Per-domain organization applies to everything in the vault - specs, research, anything else - and recurses: subdomains within domains, which can go as deep as needed.
- **D-03:** The filesystem is the taxonomy; an index is a view of one level. The folder itself is the listing, the index shows the meaning, but sometimes you might get all you need to find the file you want just by using `ls`. This semantic logic will help both LLMs and humans to make sense of the data. This is not about organizing the index file only - the files themselves are organized in a folder structure that enforces the taxonomy. The index explains the first level; entering a folder shows that folder's first level; and so on down. So a LLM or a human can easily find what they need just by going into sub folders and checking the index.md file of each without having to read the whole thing. 
- **D-04:** Taxonomize could apply at spec creation. Making a new spec is a possible reorganization point: place it, or at least leave a hint for the next consolidation - recorded by the authoring agent, which understands the spec better than any later pass. So the system should take advantage of this.
- **D-05:** Each folder has its own index doc. Similar to [[SPEC-005-index-auto-maintained-and-mirrored-per-folder]].
- **D-06:** The classification-science research (how humans and machines organize topics; placement without ambiguity) is an important reference. Research into how computer-science applies classification science is the most critical for us. 
- **D-07:** Reorganization moves are suggested to the human, never something the human must remember to trigger. The harness notices the trigger - ceiling breach, pending hints, cap warning - and puts the proposal forward; approval applies it.
- **D-10:** As simple as possible but no simpler: a spec is just a file, and single-file specs at the root are completely fine. A folder exists only when a subject holds 2 or more specs; updating Compass in a vault that moved to one-spec-per-folder undoes it - folder with 2+ members, single file otherwise. Supersedes the born-folder rule of [[SPEC-016-sizing-work-beyond-one-spec]].
- **D-09:** No forced domain count. Each level splits by one characteristic only; a folder's name states the value it fixes. Siblings are values of that characteristic, so they cannot overlap. A folder splits when a second value arrives, never before. A name widens only when its contents widen - depth alone never forces a more generic top.

## Non-Goals

- Losing anything - covered by the resident Data rule; grouping moves files, wikilinks keep resolving.
- Inventing domains speculatively, just because there is a rule to invent domains. Domains come from what the artifacts already are; the human approves the grouping of his own knowledge.
- Lessons - the catalog is their index; they group by tags already.
