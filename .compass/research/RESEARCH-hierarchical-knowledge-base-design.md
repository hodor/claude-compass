---
title: Hierarchical Knowledge Base Design for AI Agents - Multi-Source Synthesis
type: research
status: complete
confidence: high
area: methodology
tags: [hierarchy, taxonomy, cache, memgpt, raptor, facets, working-set, lost-in-the-middle]
created: 2026-06-10
updated: 2026-06-10
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]"]
---

## Question

How should we design a hierarchical knowledge base for AI agents to minimize cache misses and enable scalable taxonomy management, given that Compass agents read a "hot path" every turn and must navigate to specific specs at any depth without crawling?

## Methodology

Deep-research fan-out: 5 search angles, 23 sources fetched, 106 claims extracted, 25 verified adversarially (need 2-of-3 votes to confirm or refute), 22 confirmed, 3 killed. Sources span ArXiv primary literature (MemGPT, RAPTOR, lost-in-the-middle), ACM (Denning), library science (Ranganathan, Berkeley Discipline of Organizing), and practitioner sources (Brendan Gregg working set, NN/g polyhierarchy, Obsidian community).

Angles: LLM agent memory architectures, Parent-document retrieval and summary indexing, Faceted classification vs strict hierarchy, Working set theory and cache hierarchy design, Hierarchical refactoring and migration.

## Headline finding

Design Compass as a MemGPT-inspired three-tier system: tiny hot path always in context, warm branch summaries fetched on navigation, cold full spec bodies fetched only on demand. Overlay a faceted tag layer on top of the strict folder tree so multi-perspective specs are reachable from multiple parents without restructuring. Size the hot tier by what is actively touched (Denning's working set), enforce admission control because thrashing is a cliff and not gradual decay, place hot-path content at the START or END of the prompt to avoid the lost-in-the-middle U-curve.

## Verified findings (high confidence unless noted)

### 1. Three-tier memory architecture (HIGH)

Adopt MemGPT's RAM / recall / archival pattern: hot path (root index + active tasks + lessons catalog, always in context), warm tier (branch summaries fetched on navigation), cold tier (full spec bodies fetched on demand). Movement between tiers is query-driven via explicit function calls; eviction is occupancy-triggered (~70-100% thresholds in MemGPT) and accompanied by recursive summarization rather than discard. Sources: Packer et al. MemGPT (arxiv 2310.08560), Letta/MemoryOS analyses (arxiv 2602.19320, 2603.07670). 3-0 verified.

### 2. Hot path must be ruthlessly small (HIGH)

The root index contains pointers, one-line summaries, active task IDs, and lesson tags - never spec bodies. Documented failure modes:

- "Page the wrong things in and you waste precious context tokens; archive too aggressively and you create memory blindness" (memory blindness = agent does not know a fact exists).
- Capacity collapse is empirical: performance degrades as memory store grows even within the context window (MemBench, Vending-Bench).

Sources: arxiv 2602.19320, 2603.07670. 3-0 verified.

### 3. Position hot path at START or END of prompt (HIGH)

Mid-context placement causes 20-30 point accuracy degradation in retrieval, replicated across GPT-4, Claude, and other frontier models in 128K+ contexts. Effect attributed to RoPE long-term decay plus attention sinks. The U-shaped curve was documented in Liu et al. TACL 2024 and independently replicated by RULER, Chroma Research 2025, and arxiv 2510.10276. Source: arxiv 2307.03172. 3-0 verified.

### 4. RAPTOR-style branch summaries (HIGH)

Branch summaries at each folder level should be built bottom-up: recursively embed, cluster, and summarize children. A folder's index.md is the summary node above its leaf specs. Retrieval can target any abstraction level - root for broad questions, leaf for specific ones. RAPTOR is ICLR 2024, peer-reviewed. Source: arxiv 2401.18059. 3-0 verified.

### 5. Faceted classification overlays strict hierarchy (HIGH)

Ranganathan developed faceted classification specifically because hierarchical bibliographic schemes could not accommodate multi-perspective subjects. Strict hierarchies fail for specs that belong to multiple parents (e.g., a master material is both a #rendering concern and a #tile-editor concern). Faceted schemes synthesize terms from multiple facets rather than forcing one linear path. Independently corroborated by Berkeley's Discipline of Organizing, INFLIBNET, and 2026 Cataloging & Classification Quarterly. Source: redalyc.org/journal/3843/384357586006/html. 3-0 verified.

### 6. Migrations are non-destructive in faceted schemes (HIGH)

Analytico-synthetic schemes scale to new subjects without rewriting the existing scheme. When promoting a flat spec to a folder: convert the spec body to index.md, add sub-specs as new files, update the root index pointer, do NOT restructure the existing tag vocabulary - new terms insert into the table without changing existing scheme. Confirmed by Rowley's Organizing Knowledge and Berkeley/O'Reilly Discipline of Organizing. Source: redalyc.org/journal/3843/384357586006/html. 3-0 verified.

### 7. Size hot tier by working set, not total inventory (HIGH)

Real workloads have highly skewed access (Brendan Gregg's example: MySQL 80MB hot out of 100MB total, 61% hit ratio vs 39% for uniform). Active tasks and recently-touched specs deserve hot-path slots, not every top-level spec. Working set is what the application actively touches, not what is allocated. Sources: brendangregg.com/wss.html, ACM 10.1145/1070838.1070856 (Denning's locality model generalized as "distance" across temporal, spatial, cost dimensions). 3-0 verified.

### 8. Admission control on hot path expansion (HIGH)

Thrashing precipitates suddenly above a critical threshold; it is not gradual degradation. Denning analytically showed this in 1968 and proposed admission control: refuse to activate any program whose working set won't fit. 2025 Chroma research on 18 frontier LLMs confirms the cliff phenomenon - models "drop off a cliff unpredictably." CONCUR draws explicit parallel to TCP congestion control. For Compass: refuse to add a spec to hot-path context unless the resulting working set still fits. Source: ACM 10.1145/1070838.1070856. 3-0 verified.

### 9. Fanout per folder is likely larger than intuition suggests (MEDIUM, derived)

Cache-conscious B+ tree research (CSB+ trees, Pentium III) showed optimal node size was 16x the cache line, not 1x - optimizing a single metric (cache misses, or in our case "folder is too big") misses dominant costs (branch mispredictions, TLB misses, or in our case "too many folders to navigate"). Heuristic 8-20 children per folder before splitting; needs empirical tuning. The analogy transfers only at the meta level (don't optimize one metric in isolation); the specific instruction-count/TLB mechanism does not map to LLM context cost. Source: pages.cs.wisc.edu/~jignesh/publ/cci.pdf. 3-0 verified for the meta-lesson; 8-20 is a derived heuristic.

### 10. Spec earns its own folder when 3+ sub-concerns or body exceeds ~2K tokens (MEDIUM, derived)

Below that threshold the cost of an extra directory hop and an extra summary node exceeds the benefit; above it, leaving content flat creates a mid-context blob that triggers lost-in-the-middle. The 2K-token threshold is a design heuristic synthesized from RAPTOR (leaf chunks must embed coherently), lost-in-the-middle (large mid-context blobs penalized), and capacity collapse (unbounded accumulation penalized). Not a published number; needs empirical tuning. Sources: arxiv 2307.03172, arxiv 2401.18059.

### 11. Reactive promotion, not predictive (HIGH)

Hot-tier promotion should be query-driven via explicit function calls (MemGPT-style page-fault analog), not predictive prefetching. Predictive prefetching for agent memory is an active research area (e.g., arxiv 2605.17989) but not validated for production. Source: emergentmind.com/topics/memgpt-style-memory-management. 3-0 verified.

## Refuted claims (do not rely on)

These claims were adversarially killed (2-of-3 votes against):

- **Compressed-domain memory shows 31x speedup and 14x token reduction.** Refuted as unsupported / cherry-picked. arxiv 2602.13594.
- **Programs exhibit clean phase behavior** representable as `(L_i, T_i)` sequences. Refuted as oversimplified.
- **Locality has two clean mechanisms (temporal + spatial) both driven by divide-and-conquer.** Refuted as overstated.

These are flagged so future readers don't anchor on them.

## Open questions

1. **Optimal fanout per folder for Claude Sonnet/Opus sessions** - does the cache-conscious "larger than intuition" result transfer, or do LLMs prefer narrower trees because of attention cost per token? Needs A/B test.
2. **Auto-generate vs hand-curate branch summaries.** RAPTOR auto-generates; Compass currently hand-writes. How should summaries be invalidated when sub-specs change?
3. **Where lessons catalog sits in the hot path.** Inline text, tags on specs, or separate retrievable index? Each has different cache behavior.
4. **What concrete admission-control signal Compass should use.** Token count? Spec count? Working-set heuristic based on which specs the agent has touched in the last N turns?

## Sources

Primary (peer-reviewed or original): arxiv 2310.08560 (MemGPT), arxiv 2401.18059 (RAPTOR), arxiv 2307.03172 (lost-in-the-middle), arxiv 2602.19320 + arxiv 2603.07670 (agent memory surveys), ACM 10.1145/1070838.1070856 (Denning), pages.cs.wisc.edu/~jignesh/publ/cci.pdf (CSB+ trees), redalyc.org/journal/3843/384357586006 (faceted classification).

Secondary: berkeley.pressbooks.pub Discipline of Organizing, nngroup.com polyhierarchy, tsl.texas.gov folksonomy-and-taxonomy, brendangregg.com/wss.html, Wikipedia Adaptive Replacement Cache.

Practitioner: Obsidian forums (zettelkasten folder structure), Letta/MemGPT GitHub patterns, towardsdatascience agent-memory guides.

## Stats

105 sub-agents, 23 sources fetched, 106 claims extracted, 25 verified, 22 confirmed (3-0 or 2-1), 3 killed, 11 distinct findings after synthesis.
