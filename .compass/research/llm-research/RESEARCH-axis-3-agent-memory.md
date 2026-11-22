---
title: "Agent memory and long-horizon context, 2025-2026, measured against the vault"
type: research
status: complete
confidence: medium
area: architecture
tags: [memory, context, compaction, consolidation, benchmarks, lessons, llm-research]
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "e2162f3"
author: researcher
depends_on: ["[[RESEARCH-llm-research-for-compass]]"]
summary: "2025-2026 agent-memory papers against Compass's hot path, 5-line lessons and consolidation: helpful/harmful counters, delta-only curation, masking over summarizing, length-alone degradation, sleep-time precompute"
---

# Agent memory and long-horizon context, 2025-2026

From [[RESEARCH-llm-research-for-compass]], axis 3. Spec touched most directly: [[SPEC-028-agent-memory-is-good-enough]] (draft, KPI still a guess), plus [[SPEC-001-compass-vision-and-architecture]] north stars.

## Question

Which 2025-2026 findings on agent memory, compaction, context degradation and memory benchmarks are new relative to the vault, and which would change the hot path, cold tier, 5-line lessons, consolidation skill or the ADR-004 lost-in-the-middle rationale?

## Methodology

Systematic mapping study (the default: the axis is broad and no single practice is being evaluated). Seeded from known papers; Semantic Scholar batch metadata for venue and citation counts (queried 2026-11-21); abstract and full-text reads for the load-bearing papers; a forward-citation pass over the strongest 2025 papers. The brief allowed grading: each finding carries a grade by source type and by measured vs asserted.

## Already in the vault (not repeated)

MemGPT three tiers, RAPTOR, lost-in-the-middle, Chroma context rot (300-token focused prompts beat 113k on LongMemEval), ACON, Zep/Graphiti bi-temporal edges, Letta filesystem 74.0 vs Mem0 graph 68.5 on LoCoMo, "Does Memory Need Graphs", grep vs vector under noise, Denning working set, a cache-theory mapping, an autoDream-style consolidation pass: [[RESEARCH-hierarchical-knowledge-base-design]], [[RESEARCH-cache-theory-for-context-tiers]], [[RESEARCH-rag-fit-for-large-vaults]], [[RESEARCH-graph-engineering-for-compass]], [[RESEARCH-lessons-and-index-architecture]], [[RESEARCH-agent-context-prior-art]].

## Findings

1. **Rewriting an accumulated context with an LLM collapses it; itemized deltas merged by non-LLM code do not** (confidence: high)
   - ACE (Agentic Context Engineering): in an AppWorld run a whole-context LLM rewrite took a context from 18,282 tokens (66.7 accuracy) to 122 tokens (57.1), below the 63.7 no-adaptation baseline. The paper names two failure modes: "brevity bias" (summaries drop domain detail) and "context collapse" (repeated rewriting erodes detail).
   - ACE's design: a context is a list of bullets, each with an id and helpful/harmful counters. A Reflector extracts lessons from traces; a Curator emits small delta entries merged "deterministically ... by lightweight, non-LLM logic". New ids append, existing bullets update in place (counters), duplicates are removed by embedding comparison, after every delta or only when the window is exceeded.
   - Measured: +10.6% on agent benchmarks, +8.6% on finance; offline latency 82.3% lower and rollouts 75.1% fewer than GEPA; online token cost 83.6% lower than Dynamic Cheatsheet. Ablation: dropping the Reflector and multi-epoch refinement lowers the AppWorld average from 59.4 to 55.1. It needs a strong Reflector; without reliable feedback the context is polluted (offline FiNER without labels: 71.1 vs 70.7 base).
   - https://arxiv.org/abs/2510.04618 ; https://arxiv.org/html/2510.04618 (read to char 100,000 of 131,315)
   - Touches: consolidate skill step 4 (LLM rewrites verbose lesson bodies to 5 lines), `lesson-write`, the 5-line cap.
   - Marks: peer-reviewed (ICLR per Semantic Scholar); retraction not checked; not preprint-only; 576 citations (S2); convergence: agrees with finding 2 on counters, one source on collapse
   - Grade: measured on benchmarks by the authors, no independent replication found; peer review weighs little in this field; medium-high

2. **Past experiences drive future outputs, bad records compound, and later task outcomes are free quality labels for stored memory** (confidence: medium)
   - "Experience-following": high similarity between a new task input and a retrieved record gives highly similar outputs. Errors in stored records compound, and "seemingly correct executions" can mislead. Selective addition and deletion help, and future task evaluations "can serve as free quality labels for stored memory".
   - Abstract-only read: no gain figures extracted.
   - https://arxiv.org/abs/2505.16067
   - Touches: lesson `score`/`seen` (recurrence only, no harm signal), `compass lesson-coverage` (cited / uncited / unresolvable, no outcome), validator.
   - Marks: peer-reviewed (ACL 2025 per S2); retraction not checked; not preprint-only; 153 citations (S2); convergence with finding 1 (helpful and harmful counters)
   - Grade: measured empirical study, abstract only read; medium

3. **LLM summarization of agent history is no better than dropping old observations, and it lengthens runs** (confidence: high)
   - SWE-agent on SWE-bench Verified (500 instances), five model configurations. Observation masking (last 10 turns kept) roughly halves cost versus the raw agent and matches or slightly beats LLM summarization on solve rate in 4 of 5 setups. Example, Qwen3-Coder 480B: solve rate 53.4 raw / 54.8 masking / 53.8 summary; cost 1.29 / 0.61 / 0.64 dollars per instance.
   - Summarization lengthened trajectories 13-15% on two models; the authors read summaries as a "reinforcing signal" to keep going. Summarizer calls reuse the prompt cache poorly and cost 2.9-7.2% of the run (thinking variants 0.65-5.2%). A masking-plus-summary hybrid cost 7% less than masking and 11% less than summary on a 50-instance subset.
   - The window did not transfer between scaffolds: M=10 on SWE-agent, M=58 on OpenHands.
   - https://arxiv.org/abs/2508.21433 ; https://arxiv.org/html/2508.21433 (read to char 100,000 of 135,226)
   - Touches: handoff skill and the 80% context stop ([[SPEC-025-stop-and-suggest-handoff-at-80-percent-context]]), which end in an LLM-written summary.
   - Marks: preprint (arXiv; venue blank in S2); retraction not checked; 85 citations (S2); convergence with Anthropic's "clearing old tool results is the safest lightest-touch" in [[RESEARCH-agent-context-prior-art]]
   - Grade: measured, SWE tasks only, one run per cell; medium-high

4. **Input length alone degrades accuracy by 13.9-85% even with perfect retrieval** (confidence: high)
   - Five LLMs on math, QA and coding. Degradation persisted when irrelevant tokens were replaced by whitespace, when they were masked from attention, and when all evidence sat directly before the question. Lengths were well under advertised limits. Mitigation: have the model recite the retrieved evidence before solving, turning a long task into a short one; up to +4% for GPT-4o on RULER.
   - https://arxiv.org/abs/2510.05381
   - Touches: ADR-004 rationale, which cites position (20-30 points mid-context). Length is a second, position-independent reason to bound the hot path and every agent brief.
   - Marks: peer-reviewed (Findings of EMNLP 2025); retraction not checked; not preprint-only; 225 citations (S2); convergence with Chroma (length alone degrades, 18 models), already in the vault
   - Grade: measured; medium-high

5. **Sleep-time compute: precompute over the stored context while idle, amortize across queries** (confidence: medium)
   - Test-time compute for equal accuracy down about 5x (Stateful GSM-Symbolic and Stateful AIME); accuracy up to +13% and +18% with more sleep-time compute; average cost per query down 2.5x when several questions share a context. Benefit correlates with how predictable the query is from the context. The abstract mentions a software-engineering case study without numbers.
   - https://arxiv.org/abs/2504.13171
   - Touches: [[ADR-013-detached-worker-quiet-fallback]] workers and `compass sync`. Compass precomputes mechanically (tag-index, sweep); no model-run precompute (a brief per next-up task) exists.
   - Marks: preprint (arXiv); retraction not checked; 51 citations (S2); single source for the Compass transfer
   - Grade: measured on synthetic reasoning benchmarks, not memory tasks; low-medium for transfer

6. **A memory layer trades accuracy for tokens and latency: full context still scores highest on LoCoMo** (confidence: high)
   - LLM-judge overall: full-context 72.90, Mem0g 68.44, Mem0 66.88, Zep 65.99, LangMem 58.10, OpenAI memory 52.90, A-Mem (re-run) 48.38, best RAG 60.97. Mem0 context 1,764 tokens vs 26,031; p95 total latency 1.44 s vs 17.12 s.
   - Mem0 write path: an LLM picks ADD, UPDATE, DELETE or NOOP per candidate fact after retrieving the 10 nearest stored memories. Mem0g marks conflicting edges invalid instead of deleting.
   - https://arxiv.org/html/2504.19413
   - Touches: north-star ranking (accuracy above token cost); the dedup design (write-time manifest in [[RESEARCH-lessons-and-index-architecture]] vs this retrieve-then-decide write path).
   - Marks: peer-reviewed venue (ECAI 2025), vendor-authored; retraction not checked; 946 citations (S2); convergence with Letta 74.0 vs Mem0g 68.5 already in the vault: both show engineered memory losing to a simpler baseline, different baselines
   - Grade: measured by the vendor against competitors it ran itself; medium

7. **Memory-system evidence is fragile: benchmark saturation, judge sensitivity, backbone dependence, hidden maintenance cost** (confidence: medium)
   - A 2026 survey with an empirical section reports four limits: benchmarks "often underscaled", metrics "misaligned with semantic utility" with judge-sensitive scores, accuracy varying "significantly across backbone models", and the latency and throughput cost of memory maintenance "frequently overlooked". Abstract only; no numbers.
   - https://arxiv.org/abs/2602.19320 (v2 revised 2026-05-20)
   - Touches: [[SPEC-028-agent-memory-is-good-enough]] KPI design: any vault-recall measure inherits these four threats.
   - Marks: preprint (arXiv); retraction not checked; 33 citations (S2); convergence with the vault's own N=1 caution in [[RESEARCH-rag-fit-for-large-vaults]]
   - Grade: survey with empirical analysis, abstract read only; medium

8. **Forward citations of the ACE paper point at harness and skill-library work** (confidence: low, titles only)
   - Top citing papers by count (S2, 576 total): Meta-Harness (2603.28052, 403), Agentic Harness Engineering (2604.25850, 191), Self-Harness (2606.09498, 147), SkillX: automatically constructing skill knowledge bases (2604.04804, 93), Rethinking Evaluation of Harness Evolution Agents (2607.12227, 78). Forward citations of Sleep-time compute include MemoryAgentBench (2507.05257, 335) and PersonaMem-v2 (2512.06688).
   - Titles and counts only; none read. Overlaps axis 6 (harness engineering) and the skill-library topic.
   - Marks: metadata only; preprints per S2
   - Grade: not graded (not read)

9. **Two benchmark taxonomies give SPEC-028 question classes: LongMemEval's five abilities and MemoryAgentBench's four competencies** (confidence: high for the lists, low for results)
   - LongMemEval (500 curated questions in scalable chat histories): information extraction, multi-session reasoning, temporal reasoning, knowledge updates, abstention. Commercial assistants and long-context LLMs lose about 30% accuracy across sustained interactions. Its three-stage view (indexing, retrieval, reading) lists three design levers: session decomposition (storage granularity), fact-augmented key expansion (extracted facts added to index keys), time-aware query expansion.
   - MemoryAgentBench (multi-turn, information arrives incrementally): accurate retrieval, test-time learning, long-range understanding, selective forgetting. Authors state no earlier benchmark covers all four and that tested methods "fall short of mastering all four". No per-system scores read.
   - https://arxiv.org/abs/2410.10813 ; https://arxiv.org/abs/2507.05257
   - Touches: [[SPEC-028-agent-memory-is-good-enough]] KPI ("questions whose answers the vault already holds"): neither taxonomy is used; "knowledge updates", "abstention" (vault does not hold the answer) and "selective forgetting" have no counterpart in the draft. Fact-augmented keys map onto lesson tags and summaries in the catalog.
   - Marks: both peer-reviewed (ICLR 2025 for LongMemEval; MemoryAgentBench ICLR per S2); retraction not checked; 972 and 335 citations (S2); convergence: same five-ability set appears in the vault only via practitioner posts
   - Grade: benchmark definitions, abstract only read; medium

10. **Strategy memories built from failures as well as successes, and layered skill libraries, are the 2025-2026 form of "skills as memory"** (confidence: low-medium)
    - ReasoningBank (ICLR 2026): distills reusable reasoning strategies from both successful and failed runs, with the agent judging success itself; stores strategies, not raw trajectories; retrieves at test time and writes back. Claims consistent gains over trajectory memory and success-only workflow memory on web and software-engineering benchmarks; abstract gives no numbers. Memory-aware test-time scaling adds contrastive experiences. Code: Google Research repository.
    - SkillX (2026, "work in progress"): a strong model builds a three-tier skill base (strategic plans, functional skills, atomic skills), refined by execution feedback and exploratory expansion, then handed to weaker agents on AppWorld, BFCL-v3 and tau2-Bench; qualitative gains only in the abstract.
    - https://arxiv.org/abs/2509.25140 ; https://arxiv.org/abs/2604.04804
    - Touches: `extract-lessons` triggers (fix-loop, validator deviation, debug, STOP-and-report: all failure-shaped; successes are not mined) and the process/domain lesson split (two types, no strategic/functional/atomic layering).
    - Marks: ReasoningBank peer-reviewed (ICLR), 351 citations; SkillX preprint, 93 citations; retraction not checked; convergence: both extract reusable units from trajectories
    - Grade: measured by authors, abstracts only read; low-medium

11. **Existence and venue verified, content not read** (confidence: low for content)
   - A-MEM (NeurIPS 2025, 1,457 cites), Memory-R1 (ACL 2025, 257), MemAgent (ICLR, 271), MEM1 (ICLR, 278), BEAM "Beyond a Million Tokens" (86), MIRIX (182), MemOS (170), MemoryOS (EMNLP 2025, 191), LightMem (ICLR, 229), Memento (126), AgentFold (110), Context-Folding (178), survey "Memory in the Age of AI Agents" (333). Older anchors: MemoryBank (AAAI 2023, 917), Agent Workflow Memory (ICML 2024, 503), LoCoMo (ACL 2024, 1,177).
   - Source: Semantic Scholar batch endpoint, 2026-11-21.
   - Marks: metadata only
   - Grade: not graded (not read)

## Candidate changes for Compass

Ranked by architectural impact. Each is a fork for the human and planner, not a recommendation.

1. **Outcome counters on lessons (helpful and harmful), written by the validator or the coverage pass.** North stars: accuracy, perfect memory. Evidence: findings 1 and 2. Would change: lesson frontmatter and catalog fields, `lesson-write`, `compass lesson-coverage` (today cited / uncited / unresolvable), validator report, consolidate's archive criteria. Covered today? Partly: `score` and `seen` count recurrence, `escalated` flags non-application; nothing records that a cited lesson preceded a failed task. Not covered.
2. **Consolidation by deltas applied mechanically, with a shrink guard.** North stars: accuracy, perfect memory. Evidence: finding 1. Would change: the consolidate skill's step 4 so the model proposes itemized edits and a CLI applies them, plus a check that a rewrite keeps tags, identifiers and numbers present in the original. Covered today? Partly: the original is kept under "Record (preserved)" and nothing is destroyed (data rule), which bounds permanent loss but not loss from the hot representation; no mechanical check exists.
3. **Handoff and the 80% stop: prefer clearing old tool output and structured notes over an LLM summary of the session.** North stars: low token usage, accuracy. Evidence: finding 3. Would change: handoff skill and the stop text of [[PLAN-019-stop-at-80-percent-context]]. Overlaps axis 2 (host context editing, memory tool), so the reviewer should merge there. Covered today? Handoff is an LLM-written summary; "persist the plan to the vault before the window fills" already exists.
4. **State length, not only position, as the cap rationale; add a recitation step in builder and planner.** North stars: accuracy, low token usage. Evidence: finding 4. Would change: ADR-004 and methodology skill wording; builder and planner agent text (restate surfaced lessons before acting). Covered today? Position yes; length-alone and recitation no.
5. **A model-run precompute worker for next-up tasks.** North stars: near-zero cache misses, accuracy. Evidence: finding 5. Would change: a detached worker that builds a per-task brief (lesson shortlist, files, decisions) from `active.md` before the task starts. Covered today? Mechanical precompute yes; model-run no. Transfer evidence is weak.
6. **SPEC-028 measurement design takes its question classes from the benchmark taxonomies and inherits their threats.** North star: accuracy. Evidence: findings 7 and 9. Would change: the KPI draft in [[SPEC-028-agent-memory-is-good-enough]] to sort vault questions into extraction, multi-document, temporal, knowledge-update, abstention and selective-forgetting classes, grade by checkable end state rather than an LLM judge, and run on more than one backbone. Covered today? SPEC-028 is a draft with a guessed KPI and one undifferentiated question class.
7. **Mine successes and layer lessons, as strategy memories do.** North stars: accuracy, perfect memory. Evidence: finding 10. Would change: `extract-lessons` triggers (add a success-shaped trigger) and possibly the lesson types (a strategic/functional/atomic layer beside process/domain). Covered today? No; failure-shaped triggers only, two flat types. Evidence is abstract-level only.

## Contradictions

- Finding 4 (length alone degrades) and ADR-004 (position in the middle costs 20-30 points) are compatible but ADR-004 names one cause; [[RESEARCH-agent-context-prior-art]] already records that Chroma saw no position effect in its needle tests.
- Finding 6 (full context 72.9 beats Mem0 66.9) and the vault's "flat memory beats graph memory": both show engineered memory losing to a simpler baseline, but the baselines differ (full context vs filesystem), so they do not yet say the same thing.
- Finding 3 (summarization no better than masking) and Cognition's "compress history with an LLM" in [[RESEARCH-agent-context-prior-art]]: Cognition's claim is an opinion without a measurement.

## Gaps

- Not read, only verified to exist: every paper in findings 8 and 11. In particular BEAM (benchmark design for SPEC-028), Agent Workflow Memory, A-MEM (note linking, close to a wikilink vault), Memory-R1, MEM1.
- Abstract-level only: findings 7, 9 and 10 (MemoryAgentBench scores, ReasoningBank and SkillX numbers were not extracted).
- Grep of `plugin/skills` and the specs found no recitation step and no helpful/harmful or outcome field in `lesson-write` or `lessons`, which supports "not covered" in candidates 1 and 4.
- Forward-citation pass covered ACE and Sleep-time compute by title only; Anatomy of Agentic Memory, Complexity Trap and the 2025 survey were not forward-traced.
- Forgetting and decay (MemoryBank, 2026 work) not read.
- Memory poisoning of persisted notes (agent-written lessons reloaded as instructions) not investigated.
- LongMemEval and LoCoMo question taxonomies not read first-hand; the vault's claims about them come from practitioner posts.
- Retraction status not checked for any paper.
- No Compass-side measurement exists for any claim here; every transfer to the vault is inference from benchmarks on other tasks.
