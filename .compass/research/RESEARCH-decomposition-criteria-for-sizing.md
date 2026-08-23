---
title: "Decomposition Criteria for Sizing: No Metric Exists, Cheap Reversal Licenses Acting, and the Surviving Risk Is Social"
type: research
status: complete
confidence: high
area: methodology
tags: [decomposition, sizing, parnas, cohesion, real-options, reversibility, units]
created: 2026-08-23
updated: 2026-08-23
author: paper-research
depends_on: ["[[SPEC-016-sizing-work-beyond-one-spec]]", "[[RESEARCH-hierarchical-knowledge-base-design]]", "[[RESEARCH-cache-theory-for-context-tiers]]"]
summary: "no sizing metric exists; cheap reversal licenses acting early; the surviving risk is lock-in"
---

# Decomposition Criteria for Sizing

## Question

[[SPEC-016-sizing-work-beyond-one-spec]] requires Compass to judge whether a need is too big for one spec and act on that judgment at vision time, without asking. Three things had to be established before a mechanism could be designed:

- What criteria distinguish "one problem, many parts" (depth) from "several problems" (breadth)?
- Is committing to a structure that early defensible, or does the literature say defer?
- Does the vault's own "reactive, not predictive" ruling forbid it?

## Method

Three researchers in parallel, one per axis. Axis C was briefed adversarially, because a plausible reading of the vault's own prior research would have invalidated an approved decision.

## Axis A: What Signals Depth Rather Than Breadth

**The criterion is information hiding, not process steps.** Parnas is explicit: begin from the list of design decisions likely to change, and give each module one to hide. Beginning from a flowchart is "almost always incorrect" ("On the Criteria To Be Used in Decomposing Systems into Modules," CACM 15(12), 1972, p.1058). (HIGH, maps)

**Two decompositions of the same problem can differ only in where the seams fall.** Parnas's KWIC pair contains the same content sliced two ways, with very different quality (1972, pp.1053-1055). This directly undercuts any sizing rule that counts sub-problems: the same need can be cut well or badly at the same count. (HIGH, maps)

**The operational test is a changeability walk.** Parnas enumerates five decisions likely to change and, for each, counts how many modules must change under each decomposition (1972, p.1055). Applied here: given a candidate volatile decision, ask how many candidate sub-problems must move together if it moves. Entangled with the same one or two decisions means depth; independent means breadth. This is judgment against explicit criteria, applied per decision, not a scan of surface text. (HIGH, maps)

**Parnas 1976 supplies the parent/child content template.** Family development is a decision graph: decisions above a branch point are shared by every member below it, decisions below it differentiate members ("On the Design and Development of Program Families," IEEE TSE SE-2(1), 1976, p.2). A folder or unit `index.md` holds the decisions common to all children; a child exists to diverge on something the parent left open. Divergence with no shared root decision above it is not a child, it is a sibling somewhere else. (HIGH, maps)

**A family is defined by decision-sharing being worth exploiting, not by a member count.** Parnas's own definition turns entirely on "whenever it is worthwhile" (1976, p.1). No numeric threshold is offered, by the author who defined the concept. (HIGH, maps)

**Depth existing is not proof depth was earned.** Parnas separates hierarchical structure from clean decomposition as two desirable but independent properties (1972, p.1058). A unit folder with children is a shape; whether it is the right shape is a different question the shape cannot answer. (HIGH, maps)

**Conway adds an orthogonal axis.** A design's structure mirrors the communication structure of the organization producing it ("How Do Committees Invent?", Datamation, 1968). A unit folder grants a full pipeline, which is a workflow boundary and not only a content boundary, so whether the work will be driven as one continuous thread of attention bears on the answer independently of whether the content is coherent. The 1968 paper is descriptive; the prescriptive "inverse Conway" framing is a later addition and is not Conway's. (HIGH, maps)

### No mechanical signal exists, and inventing one would be unsupported

This is the axis's most important result, and it closes off an option that would otherwise have looked attractive.

The cohesion ladder (Stevens, Myers & Constantine, "Structured Design," IBM Systems Journal 13(2), 1974) looks like an objective taxonomy. Woodward had 163 raters classify cohesion and coupling on one medium-sized program and found wide disagreement ("Difficulties Using Cohesion and Coupling as Quality Indicators," Software Quality Journal 2, 1993). Chidamber & Kemerer then built LCOM specifically to remove that subjectivity by computing cohesion from code (IEEE TSE 20(6), 1994), and Basili, Briand & Melo found across eight systems that LCOM was **not** a significant predictor of the fault-proneness it proxies for, while five other metrics in the same suite were (IEEE TSE 22(10), 1996, pp.751-761).

So: human raters cannot apply the taxonomy consistently to code, where control flow and data dependencies are concrete and inspectable, and the one attempt to mechanize it over that same favorable domain failed to predict what it was built to predict. A depth-versus-breadth score over prose problem statements would not inherit a validated technique. It would be a new, unvalidated invention, and any proposal of one must be labeled as such. (HIGH)

Also flagged as **metaphor only**: Parnas's efficiency trade-off (1972, p.1057) is about procedure-call overhead in compiled code. Specs have no runtime. It must not be imported as a reason to prefer breadth.

## Axis B: Early Commitment vs Deferral

**The rule of three is folklore.** Traced to Roberts & Johnson's "Three Examples" pattern (1996) and popularized by Fowler (1999); no controlled study supports the number. Its underlying argument does transfer, though, and it is about evidence rather than cost: below a few instances you cannot see the true abstraction, so extracting locks in a guess. At vision time Compass has strictly less evidence than one instance. (HIGH for the folklore status, MEDIUM for the argument)

**Speculative generality has a documented exception, and its precondition matters.** Unused abstraction is a smell, except when building for a known population of consumers whose need is evidenced rather than predicted (Fowler's catalog). At vision time the need is stated by the human in the transcript, which is what makes this the evidenced case rather than the speculative one. (MEDIUM)

**Deferral is only valuable up to a point.** Poppendieck's last responsible moment is the moment at which failing to decide eliminates an important alternative (*Lean Software Development*, 2003). Crossing it without deciding means the decision gets made by default, which is generally worse than either an early or a timely deliberate choice. Monster specs are exactly that default. (HIGH, maps)

**Real options says the value of waiting collapses when late exercise is as cheap as early.** Modularity's option value is a function of uncertainty and the cost of exercising later (Baldwin & Clark, *Design Rules Vol. 1*, MIT Press, 2000; Sullivan, Griswold, Cai & Hallen, "The Structure and Value of Modularity in Software Design," FSE 2001, which applied option pricing to Parnas's KWIC case and reproduced his informal argument). (HIGH for the economic logic; the magnitudes do not transfer)

**Reversible decisions warrant fast, unescalated action.** The two-way-door framing (Bezos, Amazon 2015 shareholder letter) makes process weight a function of reversibility rather than of the decision's content. Applying one-way-door rigor to a two-way door makes an organization needlessly slow. (MEDIUM; practitioner heuristic, not peer-reviewed)

**The empirical "late restructuring is expensive" evidence is real, and it is about code.** Kim, Zimmermann & Nagappan (FSE 2012, n=328 plus a Windows case study) found 77% of engineers perceive refactoring as risking subtle regressions, and the late re-layering of Windows binaries required a multi-year centralized team, custom dependency tooling, new CI gates, and runtime shims. It paid off, at organization scale. The cost driver is behavior preservation under a compiled, runtime-coupled dependency graph. **Metaphor, not map: the magnitude must not transfer.** Compass has no runtime, no compiler, and no behavior to regress. (HIGH for the finding, HIGH for the non-transfer)

**Boehm's cost-of-change curve is itself contested.** The canonical 100x figure was closer to 5:1 for small non-critical projects even in the original 1981 data, and iterative development with automated testing has flattened it further. It should not be imported as a timeless constant. (MEDIUM)

**Compass's forward path was inspected rather than assumed; the reverse path does not exist.** `compass make-unit` git-moves the artifacts into a new unit folder, leaves filenames, numbers and frontmatter untouched so bare-stem wikilinks keep resolving, regenerates derived state in-process, and validates, in one apply step (`plugin/cli/commands/make_unit.py`). There is no caller whose behavior could regress. (HIGH, direct code inspection)

**Correction, 2026-08-23, from adversarial review of [[PLAN-009-sizing-mechanism]]:** that inspection covered only the forward direction. `plugin/cli/commands/` holds `make-unit` and `promote` and no inverse of either - no `demote`, no `unmake-unit`, no undo. Reverting a shape today means a hand `git mv` plus manual index repair. So "reversal is cheap", the premise the whole early-commitment argument rests on, is verified for creating a shape and unverified for undoing one. The premise becomes true only once the inverse ships; until then it is a claim about an unimplemented operation. (HIGH, direct code inspection)

### The surviving risk is social, not mechanical

Cheap reversal answers the mechanical objection completely. It does not answer Metz's ("The Wrong Abstraction," 2016), and that one survives intact.

Her mechanism: a shape extracted early acquires **normative weight**. It signals "this is how it should be done," so when an almost-compatible case arrives, maintainers bend it with parameters and conditionals rather than reverting. The cost is not the difficulty of the undo. It is that nobody undoes it.

That transfers to documents exactly. A structure Compass imposed can be defended precisely because Compass imposed it, and a `git mv` being trivial does not help if no one ever calls it.

**So the falsification test is not mechanical cost.** It is whether anyone, human or agent, ever says in effect "it is already a unit, let us live with it" about a structure nobody actually chose.

## Axis C: The Reactive-Not-Predictive Tension

[[RESEARCH-hierarchical-knowledge-base-design]] Finding 11 says hot-tier promotion should be query-driven and not predictive, at HIGH confidence, verified 3-0, and [[ADR-004-hierarchical-specs-with-facets]] cites it in rejecting predictive prefetching. SPEC-016 D-02 has Compass act at vision time. The question was whether that is the same thing.

**Verdict: Finding 11 does not govern SPEC-016 D-02.** The word "predictive" was doing double duty.

- **What is predicted differs.** Finding 11 concerns forecasting future, unobserved access under a recurring bounded budget, which is the genuinely hard problem the prefetch literature studies. Sizing classifies information already present in the vision transcript. Classification from present evidence is not forecasting. (HIGH)
- **The cost of being wrong differs.** A wrong hot-tier promotion recurs against a hard per-turn cap until evicted. A wrong sizing call costs one non-destructive migration. (MEDIUM)
- **The fallback that makes acting safe differs but exists in both.** Prediction is safe in the memory tier because a guaranteed demand fetch sits underneath it. It is safe here because [[RESEARCH-hierarchical-knowledge-base-design]] Finding 6 already establishes that migrations in this scheme are non-destructive. (HIGH)

**Boundary condition, and it must be carried into the decision:** the verdict holds only while sizing is classification of what the human actually said. If the judgment ever acts on unstated, inferred future scope, that instance is forecasting and does fall back under Finding 11.

Also noted: arXiv:2605.17989, which Finding 11 cited as active-but-unvalidated, has since been accepted to ICML 2026. It addresses predicting when to trigger RAG retrieval, which is adjacent to rather than identical with MemGPT-style tier promotion, so it neither validates nor refutes Finding 11's specific claim. (MEDIUM)

## Convergence

All three axes arrive at the same shape from different literatures: **act, keep the undo cheap, and watch for lock-in.**

Axis A says the judgment cannot be a score, so it must be a procedure with explicit criteria. Axis B says acting early is defensible precisely because reversal is cheap, and that the real risk is nobody reversing. Axis C says this is classification rather than forecasting, so the vault's own prohibition does not reach it.

They also converge on what to measure. Axis B's gap is that no one has counted how often a mis-sized Compass spec actually gets converted versus lived with. That is the same instrument [[SPEC-017-capabilities-are-reachable-and-measured]] D-03 asks for on the retrieval side: a correction that is never observed is indistinguishable from a correction that was never needed.

## Implementation Notes for a Planner

1. The sizing mechanism is a directed judgment procedure, not a score. Any numeric threshold proposed must be labeled an unvalidated invention.
2. The procedure is the changeability walk: name the volatile decisions, then ask how many candidate sub-problems move together if one moves.
3. A parent holds decisions shared by all children; a child exists to diverge on something the parent left open. This is the authoring template, and it is checkable by reading.
4. Whether the work will be driven as one continuous thread is a second, independent input (Conway).
5. Sizing must classify what the human said. Acting on inferred future scope crosses into forecasting and loses the axis C verdict.
6. Record every sizing decision and every later correction, so "committed too early" becomes measurable rather than asserted.
7. Guard the social failure explicitly: a structure Compass chose must be as easy to question as one the human chose, and the mechanism should make correcting it a normal act rather than a reversal of something official.

## Open Questions

- Can an LLM agent execute the changeability walk consistently across runs and across agents? The literature predates LLM document decomposition entirely and is silent. This is the question a working mechanism most needs answered, and it is empirical.
- How often are mis-sized specs actually corrected versus lived with? Unmeasured today, and it is the falsification test for the lock-in risk.
- No study exists applying information hiding or cohesion to natural-language problem statements. Every mapping in axis A is a transfer judgment, not a literature finding.
- Primary-source gaps: Stevens/Myers/Constantine 1974 read via secondary sources; the option-pricing formalism was not translated into concrete numbers.

## References

- Baldwin & Clark, *Design Rules, Vol. 1: The Power of Modularity*, MIT Press, 2000.
- Basili, Briand & Melo, "A Validation of Object-Oriented Design Metrics as Quality Indicators," IEEE TSE 22(10), 1996.
- Bezos, Amazon 2015 Shareholder Letter (two-way doors).
- Boehm, *Software Engineering Economics*, 1981; Boehm & Basili, IEEE Computer, 2001.
- Chidamber & Kemerer, "A Metrics Suite for Object Oriented Design," IEEE TSE 20(6), 1994.
- Conway, "How Do Committees Invent?", Datamation, 1968.
- Fowler, *Refactoring*, 1999 (rule of three, speculative generality).
- Kim, Zimmermann & Nagappan, "A Field Study of Refactoring Challenges and Benefits," FSE 2012.
- Metz, "The Wrong Abstraction," 2016.
- Parnas, "On the Criteria To Be Used in Decomposing Systems into Modules," CACM 15(12), 1972.
- Parnas, "On the Design and Development of Program Families," IEEE TSE SE-2(1), 1976.
- Poppendieck & Poppendieck, *Lean Software Development: An Agile Toolkit*, 2003.
- Roberts & Johnson, "Evolving Frameworks," 1996.
- Stevens, Myers & Constantine, "Structured Design," IBM Systems Journal 13(2), 1974.
- Sullivan, Griswold, Cai & Hallen, "The Structure and Value of Modularity in Software Design," FSE 2001.
- VanderWiel & Lilja, "Data Prefetch Mechanisms," ACM Computing Surveys 32(2), 2000 (via [[RESEARCH-cache-theory-for-context-tiers]]).
- Woodward, "Difficulties Using Cohesion and Coupling as Quality Indicators," Software Quality Journal 2, 1993.
