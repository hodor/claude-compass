---
title: "The Root Index Lists One Line Per Top-Level Entry; a Domain Folder's Own index.md Carries Its Members; Taxonomize Is Consolidation's Structural Arm"
type: decision
status: accepted
confidence: high
area: methodology
tags: [taxonomy, index, domains, hierarchy, sync, consolidation]
created: 2026-08-30
updated: 2026-08-30
author: "orchestrator"
summary: "sync stops listing folder children in the root index - the folder line with its child count is the pointer; taxonomize retires into consolidate as its Structure pass; the migration itself is a proposal the human approves"
depends_on: ["[[SPEC-022-vault-organized-per-domain]]", "[[ADR-004-hierarchical-specs-with-facets]]", "[[ADR-006-hybrid-hierarchy-implementation]]"]
---

# The Index Speaks in Domains

## Context

[[SPEC-022-vault-organized-per-domain]], Roger's ruling: group similar artifacts into domain folders recursively; the index says one line per broad area; consolidation is also taxonomy. The mechanisms exist ([[SPEC-010-universal-hybrid-hierarchy]] folder nesting, `/compass:taxonomize`, `compass make-unit`/`promote`) and have never been driven: taxonomize shows zero usage, doctor's 17 grouping candidates sat unactioned, and sync's root index lists every artifact at every depth, so grouping bought no index relief even where it happened.

## Decision

- **D-01: The root index lists depth-0 entries only.** A folder artifact's line - `[[name]] (folder, N children) - summary` - is the pointer to its whole subtree; children stop appearing in the root index at any depth. They live in the folder on disk, resolve by wikilink exactly as before, and the folder's own `index.md` (the spec/domain document itself) names what matters about them. This is what makes grouping pay: every artifact moved under a domain is a line removed from the hot path.
- **D-02: Taxonomize and consolidate are one skill.** Roger, mid-build: "taxonomize and consolidate need to be consolidated into one IMO." The taxonomize skill retires (its dir removed on update like `bootstrap`); its protocol lives on as `/compass:consolidate`'s Structure pass, which runs when the cap breakdown names non-redundant index lines. One trigger, one skill, both halves of consolidation - textual and structural.
- **D-03: The migration is a proposal the human approves.** Taxonomize's existing gate stands: it presents the grouping as a diff, and only the human's approval moves files. Domains are his knowledge's shape, not the agent's guess.
- **D-04: Grouping moves are the existing commands** - `compass promote` (spec gains children), `compass make-unit` (workstream), plain `git mv` into folder specs - all sizing-logged where they apply. No new migration machinery.

## Consequences

- The root index's size tracks the number of top-level areas, not the number of artifacts - the mathematics-subdomain shape Roger named.
- A reader wanting a domain's members opens the domain: one hop, cold-tier, exactly the MemGPT tiering ADR-004 designed.
- Depth-0-only listing lands before the migration, so the taxonomize apply immediately shrinks the index rather than reshuffling equal-length listings.
