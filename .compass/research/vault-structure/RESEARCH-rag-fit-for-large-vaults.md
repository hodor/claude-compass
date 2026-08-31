---
title: Does Compass Need RAG / Vector Search, and When (Large-Vault Case)
type: research
status: complete
confidence: high
area: methodology
tags: [rag, vector-search, retrieval, bm25, embeddings, large-vault, scaling, cache]
created: 2026-07-22
updated: 2026-07-22
depends_on: ["[[SPEC-003-hierarchical-vault-organization]]", "[[ADR-005-compass-cli-for-mechanical-work]]", "[[LESSON-tag-index-trades-cost-for-directed-retrieval]]"]
summary: "RAG net-negative below ~300-500 docs; lexical rung first"
---

## Question

Should Compass add an optional RAG / vector-search layer to find things in the vault? The motivating case is **users with very large Compass projects** (hundreds of docs), where the current index + faceted tags + glob/grep navigation may degrade. Does semantic retrieval earn its cost there, and where is the crossover?

## Methodology

Read Compass's current retrieval design (root index, tag-index, [[ADR-005-compass-cli-for-mechanical-work]], [[SPEC-003-hierarchical-vault-organization]], the tag-index lesson) and measured the live corpus. Surveyed 2025-2026 evidence on agentic vs vector retrieval, BM25-vs-embeddings crossover, agent-memory frameworks (Letta/Mem0), and local vector stores (sqlite-vec/FAISS). Counter-evidence (Milvus, Cursor) included deliberately.

## Headline finding

For today's corpus, RAG is net-negative or neutral on every ranked goal, and the strongest pro-vector evidence is about large code bases Compass does not resemble. The case is not "never" - it is "not until a single vault is large **and** queries measurably fail on vocabulary mismatch," and even then a cheaper lexical rung comes before vectors.

## Findings

1. **Current corpus is far below the vector-payoff regime (HIGH).** Live vault ~55 markdown docs, ~52K words; [[SPEC-003-hierarchical-vault-organization]] designs for a ceiling of ~50 specs + 10 lessons under a 5K-token hot path. ANN vector indexes do not earn their cost until well past ~100K vectors - 2-4 orders of magnitude away.

2. **Anthropic removed vector RAG from Claude Code and replaced it with grep (HIGH).** Reasons stated - precision (exact match, no fuzzy positives), freshness (reads live files, no stale index), privacy (nothing leaves the machine), simplicity (no index infra) - map one-to-one onto Compass's constraints. The broader trend (Cursor, Windsurf, Cline, Sourcegraph Amp; Letta's filesystem memory scoring 74.0 on LOCOMO vs Mem0's graph 68.5) is *away* from vectors for agent memory. Trend confidence: medium (largely practitioner sources).

3. **On memory-retrieval benchmarks grep matches/beats vectors and is far more noise-robust (MEDIUM).** LongMemEval: under rising irrelevant context, vector retrieval fell ~71% -> ~35% while grep held ~74%. Authors conclude performance is dominated by the agent harness, not the retrieval algorithm. A curated, low-noise, agent-authored vault is exactly where the vector edge is smallest.

4. **BM25/lexical is competitive-to-better on small corpora; embeddings win on scale + synonyms + paraphrase (HIGH).** For small corpora embeddings are "overkill"; BM25 gives better precision on the exact technical terms a curated vault uses. Semantic wins on coverage/synonyms and large collections. Compass's tag/title vocabulary is authored to match queries, shrinking the synonym gap.

5. **The pro-vector wins are large CODE bases, not prose vaults (HIGH).** Milvus/Cursor report ~40% token cuts at equal recall - all on large codebases where grep floods context and renamed symbols defeat literal search, and Cursor parses code into tree-sitter AST chunks before embedding. Neither condition holds for a curated markdown vault; the failure mode vectors solve is one the bounded hot path + tag index already prevent.

6. **A local vector store is feasible but drags in an embedding dependency that breaks the low-dep / no-service constraint (MEDIUM).** sqlite-vec fits "no daemon, single file, cross-platform" - the natural CLI-not-MCP choice. But embeddings need either a local model (`sentence-transformers` pulls torch, hundreds of MB, hostile to the low-dep Python CLI and Windows install) or an embedding API (adds an external service + key + network + cost/privacy surface, the same logic [[ADR-005-compass-cli-for-mechanical-work]] used to reject MCP). Stock Windows Python sometimes disables SQLite loadable extensions - an unverified gating risk.

7. **RAG hurts goals 3 and 4, is neutral on 1 and 2 (MEDIUM).** Goal 3 (near-zero cache misses) depends on a bounded, deterministic hot path loaded the same way every session; a query-dependent vector layer injects different chunks each turn and adds a per-write index to rebuild/invalidate on the `compass sync` path. Goal 4: the analogous tag-index A/B already cost +23% tokens / +17% tool calls at N=1 ([[LESSON-tag-index-trades-cost-for-directed-retrieval]]); a vector layer adds retrieval overhead without the corpus scale that makes embeddings pay. Markdown files remain source of truth either way, so goal 2 is unaffected; grep's exact-match precision is neutral-to-better for goal 1.

8. **The real vector niche - synonym/paraphrase recall - is partly closeable without vectors (MEDIUM).** Where embeddings would genuinely help ("cache eviction" query vs the vault's "admission control" wording), faceted tags + `/compass:consolidate` synonym-merging already reach across vocabulary. If it becomes a real pain, BM25 over titles+tags+summaries, or an LLM query-expansion-then-grep pass, captures most of the benefit at a fraction of the cost with zero new dependencies.

## Mapping to the four ranked goals

| Goal (ranked) | Effect of adding vector RAG |
|---|---|
| 1. Accuracy | Neutral-to-negative; fuzzy positives add noise, grep is more precise on exact identifiers. |
| 2. Perfect memory | Neutral; markdown stays source of truth, a vector index is a derived cache. |
| 3. Near-zero cache misses | Negative; non-deterministic retrieval + per-write index churn perturb the stable hot path. |
| 4. Low token usage | Neutral-to-negative at this scale; the tag-index layer already cost +23% tokens at N=1. |

## Recommendation

**Skip now; defer behind an explicit, measured trigger.** Do not add a vector/RAG layer today. This is the same reasoning that rejected MCP in [[ADR-005-compass-cli-for-mechanical-work]]: do not add a process/dependency to a path a simpler mechanism already serves.

**Trigger to revisit (the large-project case):** a single vault past roughly **300-500 docs** (where linear index/glob navigation measurably degrades) **AND** a measured share of real queries failing on vocabulary mismatch that tag consolidation cannot fix. Both conditions, not either.

**Escalation ladder when the trigger fires (cheapest first):**
1. BM25 / lexical ranking over titles + tags + summaries (no new deps, deterministic).
2. LLM query-expansion-then-grep (no index, rides existing tooling).
3. Only as last resort: an **opt-in** local sqlite-vec index built by a `compass index` command, hybrid with the tag index, no external embedding service - gated on verifying Windows loadable-extension support and an embedding dependency that does not pull torch.

## Gaps

- No direct retrieval-quality measurement on this vault under any method; the tag-index lesson is N=1. Cheap experiment: 10 real vault questions, tag-index+grep vs a throwaway sqlite-vec build, measure recall and tokens.
- Windows `sqlite3.enable_load_extension` availability is unverified and gates any sqlite-vec design.
- The "industry moving away from vectors" trend rests on practitioner sources, not controlled benchmarks - directional, not settled.

## Sources

- Anthropic dropped vector RAG for grep: vadim.blog/claude-code-no-indexing; sesamedisk.com/direct-corpus-interaction-ai-retrieval
- Grep vs vector under noise: dev.to/pueding/is-grep-all-you-need-534k
- Pro-vector (large codebases): milvus.io "Why I'm Against Claude Code's Grep-Only Retrieval"; particula.tech/blog/semantic-code-search-vs-grep-coding-agents; nexustrade.io Cursor vs Claude Code memory architecture
- BM25 vs embeddings small-corpus: medium.com/@ThinkingLoop "When to Ditch Your Vector DB for BM25"; arxiv.org/html/2505.11582v2; docs.bswen.com/blog/2026-03-27-bm25-vs-vector-embeddings
- Agent memory: vectorize.io/articles/mem0-vs-letta (Letta filesystem 74.0 vs Mem0 graph 68.5 LOCOMO)
- Local vector store: sqlite-vec deep dive (medium.com/@stephenc211); dev.to/zoricic SQLite as a vector DB
