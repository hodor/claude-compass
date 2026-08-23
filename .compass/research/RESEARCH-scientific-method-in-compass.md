---
title: Is the Scientific Method Actually Embodied in Compass?
type: research
status: complete
confidence: high
area: methodology
tags: [scientific-method, falsifiability, hypothesis, pre-registration, popper, bayesian, replication]
created: 2026-06-10
updated: 2026-06-10
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]", "[[ADR-001-methodology-as-skill-with-vault]]", "[[ADR-002-retrospective-lessons-subsystem]]"]
summary: "does Compass embody the scientific method or borrow its vocabulary; 8 gaps"
---

## Question

Roger says the scientific method was his core motivation for building Compass. Does the current Spec to Research to Plan to Build to Validate pipeline, plus the lessons subsystem and "Bayesian convergence" pattern, actually implement scientific-method practices, or only borrow the vocabulary? What is missing?

## Methodology

Direct read of Compass's authoritative artifacts: `plugin/skills/methodology/SKILL.md`, the four stage skills (`spec`, `research`, `plan`, `validate`), the agent protocols for `researcher`, `planner`, `tester`, `validator`, `reviewer`, plus `SPEC-001` and `ADR-001`/`ADR-002`. Cross-checked the lessons subsystem (`skills/lessons`, the `obsidian` lesson template). Surveyed standard sources on philosophy of science and modern open-science practice; contested positions flagged explicitly.

## Findings

### 1. What the scientific method actually is (confidence: high)

No single canonical scientific method exists; instead a family of partially overlapping ones, each contested.

- **Baconian inductivism** (Bacon, *Novum Organum* 1620): collect observations, generalize. Criticism: theory-ladenness of observation (Hanson 1958) - you cannot observe without prior commitments.
- **Popper's falsificationism** (*Logic of Scientific Discovery* 1934/1959): a theory is scientific only if it forbids something. Test by refutation, not confirmation. Confirmation cannot distinguish a true theory from a clever false one.
- **Lakatos's research programmes** (1970): a "hard core" protected by an "auxiliary belt." Programmes are *progressive* (predict novel facts) or *degenerating* (only retro-fit failures).
- **Kuhn's paradigms** (*Structure of Scientific Revolutions* 1962): normal science is puzzle-solving inside a paradigm; revolutions come from accumulated anomalies. Scientists do not abandon theories on first disconfirmation.
- **Bayesian epistemology** (Howson and Urbach 1989; Jaynes 2003): beliefs are probability distributions; evidence shifts them via Bayes' rule. Requires explicit priors and likelihoods.
- **Modern practice / open science** (post-2005 replication crisis, Ioannidis "Why Most Published Research Findings Are False"): pre-registration (OSF, AsPredicted), registered reports (Nosek and Lakens, *Cortex* 2014) accepted before data collection, effect-size and confidence-interval reporting over p-values (Cumming 2014), adversarial collaboration (Mellers, Hertwig, Kahneman 2001), replication as first-class artifact (Many Labs).

Contested points to be honest about: induction's logical status (Hume's problem), Popper's verisimilitude, whether Bayesian priors are "subjective" or principled, whether "the" scientific method is one method at all (Feyerabend, *Against Method* 1975).

### 2. Mapping Compass onto scientific-method aspects

**Spec stage** (`plugin/skills/spec/SKILL.md`). Claims to capture the "NEED, not the solution" and gates on human approval. Scientific analogue: framing the research question. **Falls short**: required sections are "Problem" and "Desired Outcome" (`spec/SKILL.md:59`, `obsidian/SKILL.md:79`). Neither requires a falsifiable hypothesis, an effect size that would count as success, a prediction about cost or time, or a pre-registered stopping criterion. "Success Criteria" is optional (`obsidian/SKILL.md:200`). Compass specs are user-story documents, not pre-registrations.

**Research stage** (`plugin/skills/research/SKILL.md`, `templates/agents/researcher.md`). Claims survey methodology with confidence levels and four named approaches (`obsidian/SKILL.md:222-230`: scoping review, systematic mapping, technology landscape, etc.). Genuinely good practice for literature review. **Falls short**: research is framed as "a survey of what exists - not original research" (`obsidian/SKILL.md:222`). No provision for *experimental* research, no requirement to identify "which finding would change the plan."

**Plan stage** (`plugin/skills/plan/SKILL.md`, plan template `obsidian/SKILL.md:296-351`). Tasks have two-tier success criteria - automated + manual checks (`methodology/SKILL.md:270-278`). Scientific analogue: a study protocol. **Falls short**: no field for *predicted outcome*, no prediction about effect size, no pre-registered falsification criterion. Verification checks are existence/conformance ("the file exists", "the test passes"), not predictions whose failure would discredit the plan.

**Build / Test / Validate** (`validate/SKILL.md`, `tester.md`, `validator.md`). Best-aligned part. Validator must run commands, not read code (`validator.md:18`). Step 6 mandates "adversarial probing" beyond the plan's checks (`validator.md:84-91`). Tester explicitly designed to BREAK code, not prove it works (`tester.md:15`). Genuine Popperian spirit. **Falls short**: validator compares implementation against the plan, not against the spec's hypothesis. Once VERDICT: PASS, the cycle ends. No follow-up "did it actually help users" measurement.

**Lessons subsystem** (`ADR-002`, `skills/lessons/SKILL.md`). Captures at phase boundaries behind binary triggers: fix-loop >=2, validator deviation-problem, debug invoked, plan revised mid-phase (`ADR-002:38-42`). **Falls short**: triggers are all *negative* events. There is no symmetric mechanism for *confirmation* lessons ("we predicted X, X happened, the heuristic worked"). Categories are `process | domain` only; neither distinguishes confirmation from disconfirmation. A lesson "X always works" and a lesson "X sometimes fails" are indistinguishable in the catalog.

**"Bayesian convergence"** (`SPEC-001:54-60`, `templates/agents/reviewer.md`). Reviewer builds a convergence matrix classifying findings as Converged (>=80%), Partial (50-79%), Divergent (<50%) (`reviewer.md:50-57`). **This is not Bayesian.** It is *frequentist majority voting across independent samples*. A real Bayesian protocol requires each agent to emit a posterior probability with its prior and likelihood, then combine via Bayes' rule or at minimum log-odds pooling. No priors, no likelihoods, no posterior update - just agreement counts. The name is aspirational.

### 3. Specific gaps

| Gap | Status |
|---|---|
| Specs require a falsifiable hypothesis | No. `spec/SKILL.md:41-50` requires Problem + Desired Outcome only. |
| Plans pre-register predictions and falsification criteria | No. Plan template has Goal / Phases / Risks / Open Questions; no prediction field. |
| Validator tries to falsify the implementation | Partially. `validator.md:84` mandates adversarial probes, but only against the plan's checks, not against the spec's hypothesis. |
| Lessons distinguish confirmation from disconfirmation | No. `lessons/SKILL.md:10-13` has process/domain only; triggers are all failure-shaped. |
| Mechanism preventing HARKing (hypothesizing after results known) | No. Spec is mutable at any time; nothing locks the pre-build hypothesis. |
| Effect-size / "what counts as meaningful" criterion | No. Success Criteria is optional and checkbox-shaped. |
| Replication (run same plan twice independently) | No. Plans move `draft -> approved -> active -> done -> archived` once. No re-run notion. |
| Bayesian convergence is actually Bayesian | No. Majority voting with thresholds. |

## Recommendations

1. **Add a falsifiable-hypothesis section to spec**, alongside Problem and Desired Outcome. Required: "What observation, if we saw it after shipping, would prove this spec wrong?" The Popperian floor.
2. **Add Predictions to the plan template.** Small list of numeric or behavioral predictions made before build, frozen by git_commit pinning. Validator's job grows to "did the prediction hold."
3. **Lock specs against HARKing.** When a plan reaches `active`, snapshot the depending specs into the plan file. Any later spec edit forks a new spec via the existing `supersedes` field.
4. **Split lessons into confirmation vs disconfirmation.** Add `polarity: confirmed | disconfirmed | mixed`. Add a positive trigger to extract-lessons: "prediction held, first-try pass." Balances the failure-only catalog.
5. **Rename or rebuild "Bayesian convergence."** Either honor the name (each agent emits a posterior, combine via log-odds pooling), or rename to "multi-agent convergence voting" so SPEC-001's claim stops being misleading.
6. **Add a registered-replication command.** `/compass:replicate PLAN-NNN` re-runs an approved plan in a fresh worktree with a fresh agent stack; compares outcomes; flags non-reproducibility as Deviation (problem).
7. **Add adversarial-collaboration mode.** For high-stakes specs, spawn a "devil's advocate" researcher whose only job is to find evidence the spec is wrong, before plan approval. Output: a one-page rebuttal that the human reads alongside the spec.
8. **Effect-size column on Success Criteria.** Promote Success Criteria from optional to required for any spec whose Desired Outcome is quantitative; each criterion names a threshold and a measurement method.

Most of these are additive and small. The cheapest first move is 1 + 2 + 3 together: require a hypothesis, freeze it, and check it after build. That alone takes Compass from "user-story pipeline" to "pre-registered study protocol" and earns the scientific-method framing it currently only claims.

## Sources

Bacon *Novum Organum* (1620), Hanson *Patterns of Discovery* (1958), Popper *Logic of Scientific Discovery* (1934/1959), Lakatos *Methodology of Scientific Research Programmes* (1970), Kuhn *Structure of Scientific Revolutions* (1962), Feyerabend *Against Method* (1975), Howson and Urbach *Scientific Reasoning: The Bayesian Approach* (1989), Jaynes *Probability Theory: The Logic of Science* (2003), Ioannidis 2005 *PLOS Med* "Why Most Published Research Findings Are False", Nosek and Lakens *Cortex* 2014 "Registered Reports", Cumming 2014 *Psych Sci* on effect-size estimation, Mellers Hertwig Kahneman 2001 *Psych Sci* on adversarial collaboration, Many Labs replication project.

Compass files referenced inline above by `file:line`.
