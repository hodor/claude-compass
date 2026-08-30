---
title: "Graph Engineering for Compass - Landscape, Prior Art, and Gap Analysis"
type: research
status: complete
confidence: medium
area: methodology
tags: [graph-engineering, knowledge-graph, wikilinks, typed-edges, retrieval, prior-art]
created: 2026-07-25
updated: 2026-07-25
git_branch: "master"
git_commit: "d3abd84"
author: "researcher (Claude)"
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]", "[[RESEARCH-rag-fit-for-large-vaults]]"]
summary: "landscape, prior art, gap analysis"
---

# Graph Engineering for Compass - Landscape, Prior Art, and Gap Analysis

## Question

What does "graph engineering" mean in 2025-2026 agent systems, what does Compass's vault already constitute graph-theoretically, and should Compass build any explicit graph-engineering capability on top of it - and if so, what, in what order, at what cost against the four ranked goals (accuracy > perfect memory > near-zero cache misses > low tokens)?

## Methodology

Technology-landscape review plus codebase audit (scoping-review style for the internal half). Read the cited Compass specs, ADRs, prior research, and lessons; read every graph-adjacent line of the `compass` CLI (`vaultlib.py`, `commands/unit_check.py`, `commands/coverage.py`, `decisionslib.py`, `commands/sync.py`, `commands/validate.py`); read GSD's MemPalace and Graphify capability source in full (`capability.json` for both, `agents/gsd-mempalace-curator.md`, the real `src/graphify.cts` TypeScript module, `commands/gsd/graphify.md`); read hermes-agent's `agent/learning_graph.py` in full. A parallel background sub-agent ran a technology-landscape web survey (14 tool calls, 20 distinct sources) covering GraphRAG/LightRAG/HippoRAG, Graphiti/Zep, Aider/SCIP code graphs, and small-corpus graph-vs-flat evidence; its findings are folded in below with their own confidence levels.

## Headline finding

Compass's vault is already a real, if informally-named, graph: wikilinks are untyped edges, `depends_on` is a typed-ish edge list, folder containment is a hierarchy edge, tags are a hyperedge overlay, and - as of v0.4.0 - `decisions:doc/D-NN` citations are a genuine new typed, source-qualified edge the CLI already parses (`decisionslib.py`, `coverage.py`). `unit_check.py` already runs a real transitive-closure graph traversal over `depends_on`. The highest-value, lowest-cost graph-engineering move is not adopting new machinery but **formalizing what already exists into a queryable derived artifact** (a `compass graph` command over the same substrate `compass sync` already walks), starting with backlink/orphan detection that today runs as a full agent-token vault crawl instead of a harness command. Everything past that - LLM-inferred entity extraction, temporal knowledge graphs, embeddings, external graph stores - is the same shape of over-engineering the RAG and GSD research already ruled out for this corpus size, and the 2025-2026 literature itself is contested on whether graph memory beats flat memory even at scales orders of magnitude larger than Compass's vault.

## Findings

### Axis 1 - What "graph engineering" means now (web survey)

1. **"Graph engineering" is not an established discipline name** (confidence: medium). Unlike "context engineering" (traceable coinage: Tobi Lütke, June 2025, amplified by Karpathy, formalized in an Anthropic engineering post and an arXiv survey), no equivalent canonical definition or manifesto exists for "graph engineering." Where the phrase appears in 2025-2026 sources it means "building graph-structured memory," treated as one tactic subordinate to context/memory engineering, not a parallel discipline.
 - https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
 - https://arxiv.org/pdf/2507.13334

2. **GraphRAG mechanism: entity/relationship extraction + hierarchical community detection, tuned for two distinct query shapes** (confidence: high). Microsoft GraphRAG builds an entity graph via LLM extraction, then runs Leiden community detection. Local search combines graph entities with raw chunks for specific questions; global search map-reduces over AI-generated community summaries for broad/thematic questions. Microsoft's own guidance: general questions -> global search, specific questions -> local (effectively vector-like) search.
 - arXiv:2404.16130 (original GraphRAG paper)

3. **Indexing/query cost varies by 2-3 orders of magnitude across GraphRAG variants** (confidence: medium). Full Microsoft GraphRAG indexing runs ~$20-40 per 1M tokens (GPT-4o); LightRAG claims ~$0.50 for comparable indexing; Microsoft's own LazyGraphRAG claims ~0.1% of GraphRAG's indexing cost. One source reports GraphRAG global search needing ~610K tokens/query versus LightRAG's ~100 tokens - illustrative of the cost spread, not a like-for-like query comparison.
 - https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/
 - https://callsphere.ai/blog/vw6g-microsoft-graphrag-knowledge-graph-2026

4. **Consensus query-type split: graphs help multi-hop/entity-centric/global-summary queries, not single-fact lookup** (confidence: medium, corroborated across sources, not one controlled study). Vector-only baselines were measured at 77.9% recall at 2-hop, dropping to 46.2% at 4-hop - the degradation curve cited as the graph opportunity zone. HippoRAG (NeurIPS 2024) claims up to 20% improvement on multi-hop QA via Personalized PageRank seeded from query entities, and claims single-step retrieval 10-20x cheaper than iterative retrieval - the paper's own figures, no independent replication found.
 - https://www.falkordb.com/blog/vectorrag-vs-graphrag-technical-challenges-enterprise-ai-march25/
 - NeurIPS 2024 HippoRAG paper; github.com/osu-nlp-group/hipporag

5. **Temporal KG (Graphiti/Zep): bi-temporal edges, incremental update, contested benchmark claims** (confidence: medium). Every Graphiti edge carries a validity interval (`t_valid`/`t_invalid`); facts are invalidated, not deleted, and entities/communities update incrementally per new "episode" without full-graph recomputation. Zep's own/vendor-adjacent benchmark reports beating Mem0 (63.8% vs 49.0% on LongMemEval, concentrated in temporal/knowledge-update queries) and MemGPT narrowly (94.8% vs 93.4% on MemGPT's own DMR benchmark) - but see Contradictions.
 - arXiv:2501.13956 ("Zep: A Temporal Knowledge Graph Architecture for Agent Memory")
 - https://vectorize.io/articles/mem0-vs-zep

6. **An independent framework paper finds graphs do NOT consistently beat flat/sequential memory** (confidence: medium, single paper but directly adversarial and on-topic). "Does Memory Need Graphs?" finds simpler flat/sequential organizations often match or exceed graph-based approaches at substantially lower compute; graph benefit concentrates in complex-reasoning queries and narrows as scale decreases, while indexing/query-latency/storage overhead are measurably higher for graphs.
 - arXiv:2601.01280

7. **Code graphs enable structural queries grep/embeddings cannot: call chains, blast radius, dependency chains** (confidence: medium-high). Aider's repo-map extracts tree-sitter definition/reference tags per file, builds a cross-file reference graph, and ranks symbols with NetworkX PageRank - computed fresh per request, never persisted as a queryable store. Sourcegraph's SCIP (protobuf schema, stable symbol IDs) is the foundation for cross-repo code intelligence, though even Sourcegraph does not offer "blast radius" as a single first-class graph operation - it composes search + code intel.
 - https://aider.chat/2023/10/22/repomap.html
 - https://sourcegraph.com/blog/announcing-scip

8. **Small-scale guidance: syntactic/tree-sitter maps suffice below enterprise scale; graph databases are often unneeded infrastructure** (confidence: medium). One synthesized source: "Tree-sitter repo maps, SQLite symbol stores... often give enough structure for small-to-mid repositories at low cost. They do not need a build." Separately, Hamel Husain's RAG retrospective argues graph databases are "usually overkill for RAG" - a CSV or Postgres table, or even HNSW's internal graph structure, already gets graph-like retrieval without new infrastructure.
 - https://anthonywest.co.uk/research/code-intelligence-indexing-2026-openai
 - https://hamel.dev/notes/llm/rag/not_dead.html

9. **Small-corpus direct evidence is thin; the one directly relevant data point favors flat retrieval** (confidence: low/gap, explicitly flagged by the sub-agent). No study isolates corpus size as the sole variable at Compass's scale (tens-hundreds of docs). The closest: a page-level study on a single math textbook found plain embedding RAG beating GraphRAG on both retrieval accuracy and F1 - the graph pipeline pulled in extraneous pages with "limited control over granularity."
 - arXiv:2509.16780

10. **No graph-memory failure postmortems found; documented failure modes are latency variance and overconfidence, not narrative "we reverted" stories** (confidence: medium for the failure modes, gap for postmortems). A 2026 cyber-threat-intel evaluation reports graph-only pipelines showing latency variance and overconfident answers when the graph lacks needed information (no "I don't know" fallback); hybrid pipelines with query repair performed more reliably. Direct search for reversion postmortems (team abandoned GraphRAG for simpler retrieval) found none - absence of evidence, not evidence of absence.
 - arXiv:2604.11419v1

### Axis 2 - What Compass already has, graph-theoretically

11. **Wikilinks are untyped edges, resolved by a real name-resolution index** (confidence: high). `resolvable_names_map` maps every markdown file's stem, path-qualified name, and (for folder specs) folder name to its vault-relative path; a name mapping to 2+ paths is an ambiguous edge.
 - `plugin/cli/vaultlib.py:283-305`

12. **`depends_on` is a typed(-ish) edge list, already walked transitively** (confidence: high). `unit_check.py`'s `_reachable_specs` does a real BFS/DFS-style transitive closure over `depends_on` edges (cycle-safe via a visited set) to find every spec reachable from an artifact, then groups artifacts by reachable spec to detect type-spread clusters.
 - `plugin/cli/commands/unit_check.py:43-56, 67-104`

13. **`decisions:doc/D-NN` citation is a new, genuinely typed, source-qualified edge shipped in v0.4.0** (confidence: high). `decisionslib.py` extracts discrete `D-NN` decision nodes from spec/ADR "Decisions" sections (three bullet grammars, trackable/non-trackable via `[informational]`/`[deferred]` tags or a discretion subheading); `coverage.py` resolves `<doc-name>/D-NN` citations in plan bodies back to those nodes through the same name-resolution wikilinks use, and reports covered/uncovered per source.
 - `plugin/cli/decisionslib.py:1-29, 194-234`; `plugin/cli/commands/coverage.py:28-42, 91-110`

14. **Folder containment and tags are two more edge types already materialized** (confidence: high). `classify_root_dirs`/`scan_artifacts` encode hierarchy (type dir, unit, depth) as structural containment; `_sync_tag_index` in `sync.py` regenerates `meta/tag-index.yaml`, a full tag-to-file hyperedge map, on every write.
 - `plugin/cli/vaultlib.py:55-96, 260-280`; `plugin/cli/commands/sync.py:230-246`

15. **`compass validate` resolves every wikilink vault-wide but does not compute backlinks, orphans, or any centrality metric** (confidence: high, direct read of the full command). It reports `broken_wikilink` and `ambiguous_wikilink` per outgoing link found, and hot-path cap breaches - no reverse-index, no orphan report, no degree/centrality output anywhere in the CLI.
 - `plugin/cli/commands/validate.py:1-137` (full file read, no orphan logic present)

16. **Orphan/backlink detection is delegated to an agent-token vault crawl instead of the harness** (confidence: high). `vault-health/SKILL.md` states outright: "Files not referenced by `index.md` or any other vault file. The CLI does not check this; do it here" - then instructs the agent to read `index.md` and every vault file's wikilinks in-context to compute the diff. This is the exact category of mechanical, deterministic work [[ADR-005-compass-cli-for-mechanical-work]] says belongs in the CLI, not a skill.
 - `plugin/skills/vault-health/SKILL.md:24-38`

17. **No mechanical multi-hop typed query exists today** (confidence: high, absence verified by reading every CLI command). Compass cannot answer "which builds implement decisions from specs that this research influenced" as a single command; it would require chaining `depends_on` (research -> spec) with `decisions`-citation edges (spec -> plan) by hand.

18. **No temporal validity or centrality analytics exist** (confidence: high). Status is current-state only (`draft -> ... -> archived`, `supersedes` is a single pointer, not an interval); there is no `valid_from`/`valid_to` anywhere, and no degree/hub/dead-doc report beyond `unit_check`'s narrow type-spread heuristic.

### Axis 3 - Source-verified prior art

19. **MemPalace: (subject, predicate, object) triples with provenance and temporal validity, additive by design** (confidence: high, direct source read). Facts get `valid_from`/`valid_to`; the triple itself is the idempotency key (`mempalace_kg_query` before `mempalace_kg_add`, skip if already present with the same `valid_from`); superseded facts are invalidated via `mempalace_kg_invalidate`, never deleted. Every operation is `onError: skip` and wing-scoped (never crosses project boundaries) - a MemPalace failure must never fail the host pipeline's ship step.
 - `gsd-core/agents/gsd-mempalace-curator.md:18-46`; `gsd-core/capabilities/mempalace/capability.json:32-41`

20. **Graphify is a real, shipping graph engine, not a markdown convention** (confidence: high, full TypeScript source read). `graph.json` holds `{nodes, edges, hyperedges, built_at_commit}`; queries run seed-then-expand BFS (label/description substring match, `maxHops=2` default) over a bidirectional adjacency map; a token budget trims edges by dropping confidence tiers in strict order `AMBIGUOUS -> INFERRED -> EXTRACTED` before removing unreachable nodes; `graphify status` compares `built_at_commit` against current HEAD via `git rev-list --count` to report `commit_stale` distinctly from mtime-based staleness; `graphify diff` computes added/removed/changed nodes and edges against a saved snapshot.
 - `gsd-core/src/graphify.cts:178-339, 405-563`

21. **Graphify's build step must run in the foreground, never a spawned subagent** (confidence: high). A documented incident (#3166) shows subagent isolation SIGTERM'ing the post-extraction phase mid-write when the parent agent exited, leaving the AST-extraction cache populated but no `graph.json` written - the skill's anti-pattern #1 is "DO NOT spawn an agent for any operation."
 - `gsd-core/commands/gsd/graphify.md:150-152, 198-201`

22. **Graphify is opt-in, gated, and depends on an external Python binary** (confidence: high). `graphify.enabled` defaults `false`; the capability shells out to a separately `uv pip install`'d `graphifyy` CLI with version-range checks (`>=0.4.0,<1.0`) and a 300s default build timeout - a real external dependency, not bundled logic.
 - `gsd-core/src/graphify.cts:106-174`; `gsd-core/capabilities/graphify/capability.json`

23. **Hermes's `learning_graph.py` is an ephemeral visualization graph, not a persisted/queried store** (confidence: high, full source read). It rebuilds nodes/edges on each call from declared `related_skills` links (explicit, not inferred) plus lexical token-overlap scoring between memory-file chunks and skill names; output is a JSON payload for a desktop panel. No query language, no persistence beyond the source files it reads, no LLM extraction step.
 - `hermes-agent/agent/learning_graph.py:125-323`

### Axis 4 - The Compass-native opportunity

24. **The reverse-index needed for backlinks/orphans is already one map-flip away from existing stdlib code, matching a prior measured harness-vs-agent-token precedent** (confidence: high). `resolvable_names_map` (vaultlib.py:283-305) plus a single pass over every file's outgoing wikilinks gives backlinks/orphans in pure stdlib with no new parsing. The SPEC-004 measurement of moving vault bookkeeping from an agent hook to the CLI found a ~99.8% token-floor reduction (3,145 -> ~6 tokens per fire) for a structurally similar move; orphan detection today does the same category of full-vault-crawl-in-context work `vault-health/SKILL.md:24-28` performs today.
 - `plugin/cli/vaultlib.py:283-305`; `.compass/compass-cli/research/RESEARCH-cli-token-reduction-measurement.md:17-31`

25. **The decision-citation graph is already fully parsed; only a query/report layer is missing** (confidence: high). `coverage.py` and `decisionslib.py` already produce, for a given plan, every `(source, D-NN, covered/uncovered)` tuple - the data for a "decision lineage" report already exists; nothing new needs to be extracted from prose.
 - `plugin/cli/commands/coverage.py:167-216`

26. **`unit_check.py`'s transitive closure is already generic enough to extend to a general graph traversal** (confidence: high). `_reachable_specs` walks `depends_on` edges filtered to one target type (`spec`); the same edge dictionary (`edges = {record: [dep, ...]}`) generalizes trivially to "traverse any typed edge, forward or reversed, to any target type" - which is most of what an "impact of change" (who depends on X) or "what does X reach" query needs.
 - `plugin/cli/commands/unit_check.py:43-56, 83-91`

## Taxonomy: capability classification

| Capability | Compass today | Bucket | Notes |
|---|---|---|---|
| Untyped node/edge graph (wikilinks) | Have | already-have | `vaultlib.resolvable_names_map` |
| Typed edge: `depends_on` | Have | already-have | frontmatter list, walked by `unit_check.py` |
| Typed edge: decision citation (`doc/D-NN`) | Have (v0.4.0) | already-have | `decisionslib.py` + `coverage.py` |
| Backlink / orphan query | Agent-crawl only | cheap-to-add | reverse `resolvable_names_map`, stdlib only |
| Transitive multi-hop typed query (impact-of-change) | Partial, spec-only | cheap-to-add | generalize `_reachable_specs` to all edge types, both directions |
| Serialized derived graph (`meta/graph.json`) | No | cheap-to-add | emit alongside `tag-index.yaml` in `compass sync`, regenerable, no new store |
| Node degree / hub / dead-doc analytics | No | cheap-to-add | degree count over the derived graph, stdlib |
| Decision-lineage report (spec D-NN -> plan -> build citation) | Partial (plan only) | cheap-to-add | extend once task-level citation (SPEC-007 D-04) is authored in practice |
| Temporal validity (`valid_from`/`valid_to`) | No (status is current-state; `supersedes` is a single pointer) | concept-only, no build | Compass already has the light version via `status: archived` + `supersedes`; a full interval model is a convention change, not new infrastructure |
| LLM-inferred entity/relationship extraction with confidence tiers | No | needs-new-infra, do-not-adopt | Graphify's own pattern; [[RESEARCH-gsd-core-improvements-for-compass]] already placed the full MemPalace KG and Graphify AST graph on the do-NOT-adopt list |
| AST / code knowledge graph | No | needs-new-infra, out of scope | belongs to the target project's source, not `.compass/` |
| Vector/semantic graph retrieval (GraphRAG-style) | No | needs-new-infra, do-not-adopt at current scale | [[RESEARCH-rag-fit-for-large-vaults]] already rejected the vector half for this corpus |
| Graph visualization export | No | cheap-to-add, optional | Obsidian already renders the wikilink graph natively; a `graph.json` export is a stdlib serialization of data already collected, not a new capability |

## Contradictions

- `checkup/SKILL.md:31` and `vault-health/SKILL.md:24-28` both prescribe orphan detection as agent-token work ("The CLI does not check this; do it here"), which contradicts the harness-over-prompts principle Compass otherwise applies to every mechanical vault check ([[ADR-005-compass-cli-for-mechanical-work]]). This is not a factual conflict between sources but a gap between stated principle and current practice - see Finding 24.
- Zep/Graphiti's own and vendor-adjacent benchmarks (Finding 5: Zep beats Mem0 63.8% vs 49.0% on LongMemEval) directly contradict an independent framework paper (Finding 6, arXiv:2601.01280) finding flat/sequential memory matches or beats graph memory at lower overhead. Neither has been reconciled by a third party in the evidence gathered.
- The contested claim above is consistent with, not contradicted by, [[RESEARCH-rag-fit-for-large-vaults]]'s prior finding that Letta's flat filesystem memory (74.0 LOCOMO) beat Mem0's graph memory (68.5) - two independent lines of evidence now both suggest graph memory's edge over flat/file memory is unsettled even well above Compass's scale.

## Gaps

- No benchmark (web or internal) isolates corpus size as the independent variable at Compass's actual scale (tens-hundreds of markdown docs with a pre-existing human-authored link graph). All GraphRAG/HippoRAG/Graphiti evidence comes from dialog transcripts or enterprise corpora built from scratch by LLM extraction - none start from a vault that already has wikilinks for free, which is Compass's actual starting condition.
- No real query has yet failed against the current CLI for lack of multi-hop traversal; the case for `compass graph` is argued from capability (the data already exists, unqueried) rather than a measured failure, the same caution [[LESSON-tag-index-trades-cost-for-directed-retrieval]] raises about unmeasured retrieval claims.
- MemPalace's cross-mode migration of `.planning/graphs/` into the temporal KG is explicitly "not yet implemented" per its own config description (`mempalace.memory_mode` docstring) - the temporal-validity pattern cannot be confirmed as proven at scale from this source alone.

## Recommendation

Ranked by cost against the four goals, same discipline as [[RESEARCH-rag-fit-for-large-vaults]]: cheapest and most-verified first, explicit do-NOT list, explicit triggers for revisiting deferred items.

**Adopt now (near-zero cost, reuses existing stdlib substrate):**
1. A `compass graph` command, backed by a derived `meta/graph.json` that `compass sync` regenerates alongside `tag-index.yaml` - no new store, no new dependency, markdown stays source of truth. First two queries: (a) backlinks/orphans, replacing the full-vault agent-token crawl in `vault-health/SKILL.md` with the same reverse-index math `compass validate` already computes forward; (b) impact-of-change, generalizing `unit_check.py`'s existing transitive-closure function to walk `depends_on` + decision-citation + wikilink edges in either direction. Serves goals 1 (deterministic vs. judgment-based), 3 (bounded, cache-friendly derived artifact), and 4 (removes an agent-token crawl) directly, at a cost the SPEC-004 CLI-vs-hook precedent already measured (~99.8% reduction on a structurally similar move).

**Study, low priority, contingent on real usage:**
2. A decision-lineage report (`compass graph decisions <spec>`) extending `coverage.py`'s already-parsed citation data toward validator/build-time citations, once SPEC-007 D-04's task-level citation convention is actually being authored in plans - no new extraction needed, just a report over data already collected.

**Concept only, no build:**
3. GSD's "invalidate, don't delete" temporal-validity idea - Compass already has the light version (`status: archived`, `supersedes`). Formalize a full `valid_from`/`valid_to` interval model only if a real "what did we believe on date X, before it was later revised" question actually surfaces; until then this is a convention Compass already follows, not a gap.

**Do NOT adopt:**
4. LLM-driven entity/relationship extraction from vault prose, confidence-tiered inferred edges, embeddings, or community-summary retrieval (the Graphify/GraphRAG pattern). [[RESEARCH-gsd-core-improvements-for-compass]] already placed the full MemPalace KG and Graphify AST graph on the do-NOT-adopt list for cost; [[RESEARCH-rag-fit-for-large-vaults]] already rejected the vector half of this for the same corpus. The 2025-2026 literature itself does not resolve whether graph memory beats flat memory even at scales far larger than Compass's ~65-file vault (Contradictions, above) - there is no evidence base to justify the extraction/confidence-tier machinery Graphify needs.
5. AST/code knowledge graphs (Aider-style PageRank repo maps, Sourcegraph SCIP). Out of scope for `.compass/`: that graph describes the target project's source code, not the methodology vault. If a Compass agent role (builder/planner) ever needs blast-radius or call-chain analysis over a target project's code, that is a distinct capability and a distinct spec - not "graph engineering for the vault."
6. Any external graph database, MCP server, or long-running graph service. Consistent with [[ADR-005-compass-cli-for-mechanical-work]]'s rejection of MCP and process dependencies for internal bookkeeping.

**Trigger conditions to revisit deferred items:**
- Revisit entity-extraction/inferred-edge machinery only if the vault crosses [[RESEARCH-rag-fit-for-large-vaults]]'s ~300-500 doc trigger **and** a measured set of real queries needs relationships not already expressible as wikilink/`depends_on`/decision-citation edges (e.g., "these two specs address the same underlying problem" with no explicit link) that tag consolidation cannot fix.
- Revisit temporal-validity as a built feature only if a real question surfaces that `status`/`archived`/`supersedes` cannot answer.
- Revisit code-graph tooling only as a separate spec, if a builder/planner role needs blast-radius/call-chain analysis over a target project's source.

## Addendum: the Anthropic-playbook synthesis note (human-supplied, 2026-07-25)

A 12-page working note ('Knowledge Graph Engineering for Multi-Agentic Systems: The Anthropic Playbook', independent synthesis of Anthropic's KG cookbook + agent-pattern guidance; supplied by the human via Drive) describes the full unstructured-to-graph pipeline: Haiku structured-output extraction, Sonnet entity resolution, MultiDiGraph assembly with hub summarization, k-hop subgraph querying with edge citations. Reading it against this research sharpens the conclusion rather than changing it:

- **Compass skips the expensive half by construction (HIGH).** The playbook spends its LLM budget on stages 1-2 (extraction, resolution) because its input is unstructured documents. The vault is authored structure: wikilinks, depends_on, decisions:/D-NN citations, tags, and containment are pre-extracted typed edges with canonical names enforced by validate. Compass needs no NER, no resolver.
- **What the playbook calls stages 3-4 is exactly the recommended build.** Assembly (a derived queryable graph) and querying (multi-hop with citations) are the missing pieces this research already recommends as compass graph + meta/graph.json.
- **Adopt from the playbook into the compass graph design:** (1) k-hop subgraph serialization (k=2 default) so a seed artifact yields an impact neighborhood the planner/validator can consume, with answers citing specific edges; (2) the graph diagnostics as cheap vault-health analytics: connected components (fragmentation), degree distribution (hub detection - the SPEC-001 hub the unit-check noise finding already surfaced), edges/nodes density ratio; (3) the grounding discipline for the validator: claims checked against explicit edges with provenance, 'flag what the graph does not contain'.
- **Confirms the do-not-adopt list:** the playbook itself gates LLM extraction behind unstructured input and multi-hop need (its own decision framework, Table VI); for a corpus that is structured at authoring time, only assembly and querying earn their cost. Temporal edges and confidence scoring are its named future directions - matching this research's deferred items.

Source: 'Knowledge Graph Engineering for Multi-Agentic Systems: The Anthropic Playbook - A Synthesis for Study' (independent, July 2026), drive.google.com/file/d/1zoBfq19IwYQdZamVEUmsBNfo44nws34Y.
