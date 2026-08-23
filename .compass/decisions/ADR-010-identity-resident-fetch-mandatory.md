---
title: "Identity Stays Resident, the Fetch Stops Being Optional, and Every Miss Is Counted"
type: decision
status: accepted
confidence: high
area: architecture
tags: [cache, hot-path, retrieval, lessons, progressive-disclosure, observability]
created: 2026-08-23
updated: 2026-08-23
depends_on: ["[[SPEC-017-capabilities-are-reachable-and-measured]]", "[[RESEARCH-cache-theory-for-context-tiers]]", "[[ADR-004-hierarchical-specs-with-facets]]"]
---

# Identity Stays Resident, the Fetch Stops Being Optional, and Every Miss Is Counted

## Context

[[SPEC-017-capabilities-are-reachable-and-measured]] carries three rulings: adopt both hermes mechanisms, surfacing and measurement (D-01); never ask the human how Compass should run (D-02); and a miss must be observable, because a measured miss rate of zero means either nothing was tiered or every miss is silent (D-03).

[[RESEARCH-cache-theory-for-context-tiers]] answered the three axes the vault had not already settled. [[RESEARCH-hierarchical-knowledge-base-design]] had already settled working-set sizing and admission control from Denning, at HIGH confidence.

The state that forced the question: the hot path measures 6,633 tokens against a 5,000 cap, and all 28 lessons are listed twice inside it, once in `index.md` and once in the full `lessons-catalog.yaml`.

## Decision

- **D-01:** The resident tier carries identity only. One line per lesson, name plus summary, enough to disambiguate that lesson from every other. The ranking fields (`tags`, `area`, `score`, `status`) leave the hot path; `compass lessons` reads them from disk when it runs, which it already does.
- **D-02:** The duplication ends. One structure carries the lessons in the hot path, not two. Inclusion's only payoff is answering on behalf of the inner level without probing it, which requires one structure to be checked instead of the other; Compass loads both unconditionally every turn, so the payoff is structurally unavailable while the capacity cost is paid in full.
- **D-03:** Retrieval moves off agent discretion. The lessons fetch fires from the harness at the work sites, the way capture already fires from `Stop` and `SubagentStop`. Compass's write side is hook-owned and its read side is not, and that asymmetry is the whole defect.
- **D-04:** `compass lesson-coverage` becomes a gate at the completion point, not an advisory report. A task cannot reach done while a lesson that ranked relevant remains uncited, absent an explicit recorded override. This is retirement-gating, the same shape as `--strict` on `compass coverage`.
- **D-05:** D-03 and D-04 both ship. They are complements, not alternatives: D-03 governs whether the fetch happens, D-04 governs the consequence when a fetched lesson is ignored. Shipping only one leaves half the requirement unmet.
- **D-06:** Every miss is counted and reported. `compass lessons` records what was asked for, what surfaced, and what did not, and the count is readable. A reported miss rate of zero is treated as a defect signal to investigate, never as success.
- **D-07:** The gate is checked by the harness, not honored by convention. An exit code respected because an agent chooses to respect it is a documented obligation, not a mechanism.
- **D-08:** `admit-check` and `touched` get wired to a caller or retired outright. They implement Denning's admission control from [[ADR-004-hierarchical-specs-with-facets]] and have never run in any vault. Leaving them is the exact condition this spec exists to end.

## Rationale

Hardware never gets its correctness guarantee by making the requester's judgment more reliable. Every load in the ISA unconditionally issues a memory reference; there is no path where the CPU decides an access is unnecessary and skips it, and the memory hierarchy's state machine has no give-up transition. A miss lengthens an access, it never fails one. The guarantee comes from removing the judgment (D-03) or from gating a later unavoidable point (D-04).

What makes an obligation enforceable is that the initiator's own forward progress is gated on discharging it. A write cannot retire past an unacknowledged invalidation; a TLB shootdown initiator blocks until every remote core acknowledges. That is why D-07 exists as its own decision: the difference between a mechanism and a convention is exactly whether something non-bypassable checks it.

Speculation-with-verification is the closest structural match to the current design, and it fails in one specific place. A pipeline runs past a predicted branch with results uncommitted, and nothing retires until a mandatory check resolves. Compass has the speculate half and not the verify-gates-commit half.

D-01 follows from what a tag is for: the identity that disambiguates a slot from everything else that could occupy it, and nothing more. D-06 follows from D-03 of the spec, and from the fact that prefetch quality is measured by accuracy, coverage and timeliness rather than assumed.

## Consequences

The hot path drops to roughly 3,600 tokens, back inside the cap with room, and the cap stays where [[ADR-004-hierarchical-specs-with-facets]] set it.

Retrieval becomes harness work rather than agent work, which serves north-star goal 4 and costs no agent tokens. It also removes a decision the agent currently gets wrong silently.

The gate will fail builds that would previously have passed. That is the intent, and it is why the override in D-04 is explicit and recorded rather than implicit.

Two gaps stay open and are not closed by this decision, recorded so nobody reads it as more complete than it is:

- **The never-surfaced gap.** A gate built on the ranker protects only lessons the ranker surfaces. A relevant lesson with poor tag overlap that never makes the cut is invisible to the advisory report and to the gate alike. That is a ranking-quality problem, and no hardware analogue reaches 100% on it.
- **Summary length.** Cache theory says how much identity is enough for correctness. It cannot say how much description a summary needs to support a relevance judgment, because that is a natural-language problem the literature does not reach. It needs an empirical answer against the real corpus.

## Alternatives Considered

**Raise the hot-path cap.** Concedes the budget instead of removing duplication that buys nothing. Rejected: the duplication is waste on its own terms, independent of what the cap is.

**Keep retrieval advisory and rely on directive prompt wording.** This is what hermes does, and hermes's own design is explicit that the mandatory framing is prompt-hoped rather than harness-enforced: nothing blocks the turn if the model skips the scan. It cannot meet a 100% requirement. Rejected for that reason, while adopting hermes's surfacing shape, which is sound.

**Ship only the gate, leaving the fetch discretionary.** Catches a lesson that surfaced and was ignored, never one that was never fetched. Rejected as half the requirement.

**Ship only the harness-owned fetch, no gate.** Guarantees the content arrives and says nothing about whether it was applied. Rejected as the other half.
