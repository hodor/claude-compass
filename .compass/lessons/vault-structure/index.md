---
title: "vault-structure"
type: domain
status: active
tags: [domain, lessons, vault, links, indexes]
summary: "vault mechanics - indexes, links, discovery, placement"
created: 2026-08-30
updated: 2026-08-30
sizing_id: sz-2026-08-30-19
---

# vault-structure

## Scope

Class here: vault mechanics - indexes, links, discovery, placement

## Lessons

- [[lessons/vault-structure/LESSON-append-only-index-misses-mutations|LESSON-append-only-index-misses-mutations]] - Append-only derived indexes miss both stale mutations and second-writer duplicates; repair must be active, not assumed.
- [[lessons/vault-structure/LESSON-hierarchical-placement-tolerate-disagreement|LESSON-hierarchical-placement-tolerate-disagreement]] - Inter-indexer agreement is inherently low; stop at a correct coarse ancestor rather than force a wrong specific leaf
- [[lessons/vault-structure/LESSON-obsidian-bare-link-creates-stray-note|LESSON-obsidian-bare-link-creates-stray-note]] - Obsidian does not resolve a bare folder-spec wikilink to its index.md; click-through creates a zero-byte stray note
- [[lessons/vault-structure/LESSON-scope-notes-are-load-bearing|LESSON-scope-notes-are-load-bearing]] - A missing Class-here scope line cost a probe 16,900 useless tokens; repair cut it to 2,971
- [[lessons/vault-structure/LESSON-scratch-vaults-need-compass-dir|LESSON-scratch-vaults-need-compass-dir]] - CLAUDE_PROJECT_DIR redirects the compass CLI only when it contains .compass; otherwise cwd-walk silently targets the enclosing vault
- [[lessons/vault-structure/LESSON-sizing-unrecorded-blind-to-born-folder|LESSON-sizing-unrecorded-blind-to-born-folder]] - SPEC-016 D-06's folder shape breaks file-stem==spec-name assumptions: sizing check, doctor suggested-name
- [[lessons/vault-structure/LESSON-tag-index-trades-cost-for-directed-retrieval|LESSON-tag-index-trades-cost-for-directed-retrieval]] - Tag index makes agents more thorough and faster wall-time, but does not automatically reduce tokens; the cost win depends on the query shape
- [[lessons/vault-structure/LESSON-template-shape-vs-template-precondition|LESSON-template-shape-vs-template-precondition]] - A folder-spec template built for 'problem + decisions' doesn't fit a folder that only groups topically related docs
- [[lessons/vault-structure/LESSON-type-dir-discovery-needs-content-signal|LESSON-type-dir-discovery-needs-content-signal]] - Treating every .compass subdir as an artifact type dir breaks on vaults that store non-artifact dirs there; require the known core dirs OR a typed-artifact signal
- [[lessons/vault-structure/LESSON-wikilink-validator-skip-code|LESSON-wikilink-validator-skip-code]] - Match use, not mention - matchers and edit anchors alike: bind to grammar position, never a substring prose repeats
