---
title: "Cache Theory for Compass's Context Tiers: Tag/Data Split, Inclusion, and the Correctness of a Miss"
type: research
status: complete
confidence: high
area: architecture
tags: [cache, hot-path, progressive-disclosure, retrieval, working-set, inclusion, speculation]
created: 2026-08-23
updated: 2026-08-23
author: paper-research
depends_on: ["[[SPEC-017-capabilities-are-reachable-and-measured]]"]
summary: "tag/data split, inclusion cost, and why a hardware miss cannot cost correctness"
---

# Cache Theory for Compass's Context Tiers

## Question

How should a bounded always-resident tier relate to a larger on-demand store, when a miss must never silently lose required content?

The human's requirement, verbatim (Roger, 2026-08-23): "only relevant lessons should be added and at the relevant time but IT IS 100% REQUIRED that they do load at the appropriate time."

## Method

Three researchers in parallel, one per axis. Two further axes were dropped before spawning because [[RESEARCH-hierarchical-knowledge-base-design]] already settles them at HIGH confidence, adversarially verified 3-0: working-set sizing of the hot tier (its Finding 7) and admission control against the thrashing cliff (its Finding 8), both from Denning, ACM 10.1145/1070838.1070856. Re-running them would have re-derived Denning for nothing.

That prior research is also the origin of two shipped-but-unreachable commands. `admit-check` and `touched` are its Finding 8, decided in [[ADR-004-hierarchical-specs-with-facets]], built, and never wired to any caller. The theory was done, the code was written, and the connection was never made.

## The Mapping, Stated Before the Findings

| Compass | Hardware |
|---|---|
| hot path (`index.md` + `active.md` + lessons catalog), always loaded | resident tier |
| `compass lessons --for <doc>` | demand fetch |
| lesson name + summary | tag |
| full catalog row (tags, area, score) | data |
| `compass lesson-coverage` | advisory report, gating nothing |
| 5,000-token cap | capacity |

Every finding below is marked as either a structural map or a metaphor. The distinction is load-bearing and is not smoothed over anywhere in this document.

## Axis 1: The Tag/Data Split

**The split is the same architecture, by name, not by analogy.** Smith describes caches that store tags and data in two separate physical stores, called the "address array" and the "data array" (Smith, "Cache Memories," ACM Computing Surveys 14(3), 1982, p.477). Compass's proposal - name and summary resident, full record fetched - is that pattern. (HIGH)

**Tag width is a leftover, not a knob.** Block size fixes the offset bits, set count fixes the index bits, and the tag is whatever high-order bits remain (Smith 1982, §2.2.1, Fig. 8, p.488). The identity a tag carries is exactly what disambiguates its slot from everything else that could occupy it. Nothing more. (HIGH)

**The load-bearing transfer is what breaks when identity is missing.** In virtual-address caches, a tag that omits the address-space identifier causes *synonyms*: distinct entities collide and the cache returns silently incorrect hits, not merely slower ones. The only detection is a full reverse-mapping structure searched on every miss (Smith 1982, §2.9, pp.510-511). Applied here: a resident summary that cannot distinguish two lessons will silently substitute one for the other, and no downstream stage will notice. (HIGH, maps)

**Sector caches are the precedent for one identity covering a longer record.** The IBM 360/85 used one tag per 1024-byte sector with 64-byte blocks fetched individually as referenced (Smith 1982, §2.2, pp.487-488, citing Conti 1968). The generalized form is one tag plus one validity bit per constituent block. (HIGH, maps)

**Sectoring's documented cost is hit rate.** Smith reports the sector organization's hit ratio is worse than an equivalent set-associative cache and declines to analyze it further (Smith 1982, p.488). Seznec's decoupled sector caches (ISCA 1994) later reduced that penalty, motivated by a concrete overhead figure: on the MIPS R4000 a 24-bit tag costs up to 18.75% of total storage at 16-byte lines. Larger sectors cut tag overhead but raise miss ratio. (MEDIUM; Seznec read via a third-party summary, not the ACM original)

**Smith's own precedent for compressing identity.** The 370/168, 3033 and 470V assign a short hardware tag (5 bits on the 3033) to a much longer OS address-space identifier, tracked in a side table. The documented cost of narrowing: the short-tag namespace is bounded, and reassigning a tag requires purging every entry that used the old assignment (Smith 1982, ~p.525). Compressed identity is affordable only alongside a purge mechanism for when the compressed space is exhausted. (HIGH, maps)

### The boundary of axis 1

A cache tag is a **locator verified by exact comparison**. A hit is deterministic, and false positives are engineered to near zero or eliminated by full verification on an apparent hit. A name-plus-summary is a **semantic preview a model judges**. There is no comparator.

So the failure mode is not a false hit in bits. It is a summary that fails to mention the fact that would have made the agent fetch. Cache theory answers how much *identity* a tag needs for correctness. It cannot answer how much *description* a summary needs to be understood. That is a natural-language relevance problem, and the hardware literature does not reach it. **Metaphor, not map. Do not let a planner treat tag-width math as a summary-length answer.**

## Axis 4: Inclusive vs Exclusive, and the Cost of Duplication

**Inclusion is a coherence mechanism, not a storage strategy.** Baer & Wang (ISCA 1988, "On the Inclusion Properties for Multi-Level Cache Hierarchies") state its purpose as reducing coherence complexity. It exists to serve coherence protocols. (HIGH; primary text unreachable, three independent secondary sources agree verbatim on the purpose statement)

**Its cost is capacity, unconditionally.** Under strict inclusion, unique storage across the hierarchy equals the larger level's size, not the sum. Duplication never buys capacity; it only ever costs it. (HIGH)

**Its payoff is snoop filtering, and that payoff has a precondition.** An outer miss can answer "not present anywhere" without probing the inner caches (Jaleel et al., "Achieving Non-Inclusive Cache Performance with Inclusive Caches," MICRO-43 2010, §II). This pays off only when the outer structure is checked *instead of* the inner one on some fraction of accesses. (HIGH)

**Near-parity levels make inclusion a bad trade.** At a 1:8 inner-to-outer ratio, inclusive is on average 3% worse than non-inclusive; at 1:4, 8% worse, up to 33%. The paper's own conclusion for such ratios: better not to enforce inclusion (Jaleel et al., §II, Fig. 2). (MEDIUM as transfer; the percentages are products of replacement-policy dynamics Compass has no equivalent of, so only the qualitative conclusion carries)

**Inclusion victims do not transfer at all.** Jaleel et al.'s headline result is that inclusion's penalty comes from hot inner lines being force-evicted by outer LRU decay, not from lost capacity. That presupposes eviction traffic and a replacement policy. Compass's two lesson structures have neither; both are static content read in full every turn. **Not even a metaphor - it answers a question that presupposes machinery Compass does not have.** (HIGH confidence in the non-transfer)

### Verdict on the 700-token duplication

**Waste, by the literature's own terms.** `index.md` lists all 28 lessons and `lessons-catalog.yaml` carries the same 28 rows, and both load unconditionally every turn. No branch anywhere checks one and skips the other, so inclusion's only payoff is structurally unavailable - not diminished, absent. The cost is exactly what Baer & Wang describe, and it is measurable in Compass's own budget.

The one defense available - that the two forms serve different access patterns (wikilink navigation vs `compass lessons` ranking) - is a real pattern, but it requires the specialized structure to be loaded *selectively*. Loading both eagerly destroys the specialization it would justify.

## Axis 5: Why a Hardware Miss Cannot Cost Correctness

This is the axis the human's requirement turns on.

**The crux.** Every load in the ISA unconditionally issues a memory reference. There is no instruction-level path where the CPU judges an access unnecessary and skips it. A miss does not fail the access, it lengthens it: the memory hierarchy's state machine has no "give up" transition, only "hit" or "miss, then fetch from the next level." Correctness follows because the backing store is a strict superset of any cache's contents. (HIGH)

**Hill's 3C model maps cleanly** (Hill 1987 dissertation; Hill & Smith 1989). Compulsory: a lesson category that has genuinely never applied - an inherent floor, not a defect. Capacity: the 5,000-token cap forcing lessons to the cold tier, with `compass lessons` re-fetching as the direct echo of a capacity-miss refetch. Conflict: the ranker's top-N cutoff, where a relevant lesson is displaced by a less-relevant one competing for the same slot - structurally a set-associative conflict miss. (HIGH)

**Compass's actual failure has no C at all.** The 3C taxonomy classifies misses on accesses that *happened*. Nothing classifies "the load was never issued," because the ISA guarantees issuance one abstraction layer below where miss taxonomy begins. The nearest real phenomenon is a compiler dead-code-eliminating a load - a software bug with verification tooling watching for it, not an operating condition. Compass's retrieval never being called is that case, permanently in production, with nothing watching. (HIGH)

**What makes an obligation enforceable.** In snoopy protocols there is no opt-out-of-snooping state (Papamarcos & Patel, ISCA 1984); in directory protocols the writer collects acknowledgments from every sharer before the write is visible (Censier & Feautrier, IEEE TC 1978). The mechanism, precisely: **the write cannot retire until the invalidation obligation is discharged.** The obligation binds because the initiator's own forward progress is gated on it, not because the initiator is well-behaved. TLB shootdown is the same shape - the initiator blocks until every remote core acknowledges the flush (Teller et al., ASPLOS 1989). (HIGH)

**Prefetching is never a correctness mechanism, structurally.** Accuracy, coverage and timeliness are its evaluation triple (VanderWiel & Lilja, ACM Computing Surveys 32(2), 2000). A prefetch is layered *on top of* the guaranteed demand fetch, never instead of it; if it is wrong or absent, the demand access still runs and still returns the correct value. `compass lesson-coverage`'s surfaced-but-uncited row is structurally a prefetch-accuracy report - but the demand-fetch fallback underneath it, the thing that runs anyway and gets the content regardless, does not exist. That absence is precisely why the current mechanism cannot be correctness-transparent. (HIGH)

**Speculation-with-verification is the closest match, and it is incomplete in exactly the place that matters.** A pipeline runs past a predicted branch with results uncommitted in the reorder buffer; nothing becomes architecturally visible until the branch resolves; a misprediction forces a mandatory squash and replay. Memory disambiguation works the same way (Chrysos & Emer, "Memory Dependence Prediction Using Store Sets," ISCA 1998). The invariant: **every speculative action has a mandatory, non-bypassable check gating the commit point.** Compass has the speculate half - an agent optionally reads, optionally cites - and not the verify-gates-commit half. `lesson-coverage` is report-only, and the lessons skill says so explicitly: low or missing coverage is a finding, never a block. (HIGH)

### Direct answer

**A 100% guarantee is achievable, but never by making the fetch decision more reliable.** Hardware's guarantee never comes from trusting the requester's judgment. It comes from removing the judgment, or from gating a later unavoidable point. Two routes, and they are complements, not alternatives:

**Route A - remove the discretion.** Retrieval runs from something outside the agent's judgment, exactly as lesson *capture* already does: the `Stop` and `SubagentStop` hooks fire `compass capture-check` deterministically, and no agent decides mid-conversation whether to run them. Compass's write side is already hook-owned; its read side is not. This reproduces the crux property exactly.

**Route B - gate the completion point.** Accept the fetch as advisory, then block the transition: a task cannot go to done, or a plan to complete, while a lesson that ranked relevant remains uncited, absent an explicit override. This is retirement-gating, and it is the same shape as `--strict` on `compass coverage` for decisions, already shipped per [[ADR-009-rolling-wave-mechanism]].

### Two boundaries neither route erases

**Scope.** Hardware's guarantee covers only addresses the program actually references. A gate built on the ranker's top-N protects only lessons the ranking surfaces. A relevant lesson with poor tag overlap that never makes the cut is invisible to the advisory report and to any future gate alike. Route B closes "surfaced but ignored." It does not close "never surfaced," which is a ranking-quality problem with no hardware analogue that reaches 100%.

**Enforcement.** Hardware gates are enforced by hardware; there is no bypass instruction. A CLI exit code honored because an agent chooses to honor it is a convention, not the same enforceability class. For Route B to match the mechanism rather than merely resemble it, the check must be wired into something non-bypassable - a harness-level block on the status transition, checked the way a hook checks.

## Convergence and Contradictions

All three axes converge on one conclusion from different directions: **the resident tier should carry identity, and identity only, and the fetch beneath it must not be discretionary.** Axis 1 says identity is what disambiguates and nothing more. Axis 4 says carrying the same content at two levels buys nothing without selective access. Axis 5 says the fetch under the identity has to be mandatory or the whole structure is advisory.

One tension worth recording: Smith 1982 concluded sector organizations have worse hit ratios and dropped them; Seznec 1994 engineered most of that penalty away. Twelve years and a different design separate the two, so it is not a contradiction, but Smith's dismissal is not the final word on sectoring.

One caveat on metric reuse: VanderWiel & Lilja note accuracy/coverage/timeliness are inadequate for prefetch into a shared cache because of pollution. If that triple is reused to score lesson surfacing, a cited-but-irrelevant lesson is a pollution failure that wastes budget, structurally distinct from a relevant-but-never-surfaced failure. Conflating them misuses the metric.

## Implementation Notes for a Planner

1. The duplication goes. Only one structure carries the 28 lessons in the hot path, and it carries name plus summary, not the ranking fields `compass lessons` reads from disk anyway.
2. Retrieval moves off agent discretion (Route A) or the completion point gets gated (Route B). Doing neither leaves the human's stated requirement unmet, and this document should not be read as supporting a third option.
3. Whatever carries identity must disambiguate. Two lessons whose summaries do not distinguish them is the synonym case, and it fails silently.
4. Any gate must be harness-checked, not honored by convention, or it is a documented obligation rather than a mechanism.
5. `admit-check` and `touched` already implement Denning's admission control from [[ADR-004-hierarchical-specs-with-facets]]. Wire them or retire them; leaving them is the exact condition [[SPEC-017-capabilities-are-reachable-and-measured]] exists to end.

## Open Questions

- How long must a resident summary be to support a relevance judgment? Cache theory explicitly cannot answer this (axis 1 boundary). It needs an empirical answer against the real corpus.
- Does the "never surfaced" gap warrant its own instrument, given no route here closes it?
- Baer & Wang's necessary-and-sufficient inclusion conditions were not read in primary form (ACM DL 403).
- Seznec ISCA 1994 read via third-party summary; the 18.75% figure needs primary confirmation before being cited as hard.
- Hill & Smith 1989's miss-class definitions were taken from summaries, not the primary text.
- A lead, not a source: arXiv:2603.09875v1 maps MESI states onto agent authorization revocation and claims a safety bound independent of agent behavior. Single author, unreviewed, and its enforceability argument could not be extracted from a partial fetch. Verify directly before relying on it.

## References

- Baer & Wang, "On the Inclusion Properties for Multi-Level Cache Hierarchies," ISCA 1988.
- Censier & Feautrier, "A New Solution to Coherence Problems in Multicache Systems," IEEE Trans. Computers, 1978.
- Chrysos & Emer, "Memory Dependence Prediction Using Store Sets," ISCA 1998.
- Conti, sector cache of the IBM 360/85, 1968 (via Smith 1982).
- Denning, working-set model and admission control, ACM 10.1145/1070838.1070856 (via [[RESEARCH-hierarchical-knowledge-base-design]]).
- Hill, "Aspects of Cache Memory and Instruction Buffer Performance," UC Berkeley dissertation, 1987; Hill & Smith, "Evaluating Associativity in CPU Caches," IEEE Trans. Computers 38(12), 1989.
- Jaleel et al., "Achieving Non-Inclusive Cache Performance with Inclusive Caches," MICRO-43, 2010.
- Papamarcos & Patel, "A Low-Overhead Coherence Solution for Multiprocessors with Private Cache Memories," ISCA 1984.
- Seznec, "Decoupled Sector Caches," ISCA 1994.
- Smith, "Cache Memories," ACM Computing Surveys 14(3), 1982.
- Teller et al., "Translation Lookaside Buffer Consistency: A Software Approach," ASPLOS 1989.
- VanderWiel & Lilja, "Data Prefetch Mechanisms," ACM Computing Surveys 32(2), 2000.
