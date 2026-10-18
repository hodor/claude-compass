---
title: "Control Theory for Compass Loops: Consolidated Research"
type: research
status: done
confidence: medium
area: pipeline
tags: [loops, control-theory, feedback, sensors, llm-judge, fsm, flow-control, humanlayer, react-doctor, maya, convergence, budgets, rule-compilation, guard]
created: 2026-10-17
updated: 2026-10-17
git_branch: "master"
git_commit: "eadad7f"
author: "reviewer"
depends_on: ["[[specs/pipeline/SPEC-026-control-theory-for-loops]]"]
summary: "Eleven axes plus three gap passes on agent control loops: HumanLayer's loop converges on every axis that read it; control theory gives vocabulary, no tested guarantee; no product offers a per-day or per-loop dollar cap, so a loop sums per-run cost itself; a skill-plus-rules judge is untested anywhere; loop files survive update in user skill dirs and .compass/meta, never .claude/cli; Maya, the FSM claim and judge precision stay open"
---

# Control Theory for Compass Loops: Consolidated Research

## Question

What does it take for a Compass loop, its own or one built for a user's task, to measure something, change a system in small low-risk steps, get feedback on the quality of each step, stay stable amid disturbances, and remain steerable by a human? The question comes from [[specs/pipeline/SPEC-026-control-theory-for-loops]], which lays out seven steps (end state, sensor, dampener, controller, actuator, loop, human on the loop, flow control), names deterministic and judge sensors, asserts that every control loop is also a finite state machine (FSM), and lists eight example loops, one of them an animation made in Autodesk Maya.

## Scope

Included: the control-theory vocabulary and the literature applying it to software and LLM agents; the sensors Claude Code exposes and the reliability of LLM judges as sensors; each of the seven steps as practiced by HumanLayer and comparable tools; FSM theory and FSM-shaped agent frameworks; the loops Compass runs today, audited in code; loops outside code (Maya); the spec's example loops with measured prior art; react-doctor and HumanLayer as prior art.

Excluded: design recommendations. This document holds evidence; a plan decides.

## Methodology

Consolidation of eleven parallel research axes, each run under its own methodology from the research-methods skill, with grading allowed for every axis (each finding carries a grade for how much its evidence-type mark should weigh). This document builds a convergence matrix over the claims more than one axis could address, then organizes all findings by the spec's structure.

Three gap passes (G1 to G3) followed, each aimed at a gap the eleven axes left open. Their findings are numbered 87 onward and sit in the section they inform; the claims they touch are scored in the gap-pass rows below the main matrix.

Agreement is computed over the axes that addressed a claim, never over all eleven: each axis covered a different slice of the spec, so silence is not dissent. Classes: **converged** at 80% or more of addressing axes with at least two axes; **partial** at 50 to 79%; **divergent** below 50% or an even split with no majority. A claim only one axis could address is tagged "single axis" in its finding.

| Handle | Axis | Methodology | Main evidence base |
|---|---|---|---|
| A1 | Control theory mapped to agent loops | Systematic mapping study | Shevtsov et al. IEEE TSE 2018 read in full; HumanLayer skill; 2026 preprints read as HTML or abstract |
| A2 | Sensors, deterministic and judge | Repository mining plus mapping study | 44 real `claude -p` result events, Python Agent SDK source, Claude Code docs; judge papers via a fetch summarizer, only Zheng et al. in full text |
| A3 | react-doctor | Repository mining | Clone of `millionco/react-doctor` at `84ad0c8d` |
| A4 | HumanLayer | Grey-literature review | Mistele talk transcript (YouTube captions), `humanlayer/skills` clone at `653b641`, Dex Horthy podcast and essay |
| A5 | Users' loops, Maya | Mapping study plus repository mining | GG_MayaMCP, abrahamADSK/maya-mcp, Autodesk docs, Claude Code scheduling docs |
| A6 | The spec's example loops | Grey-literature review | Google arXiv:2501.06972 and the Airbnb post read in full; most other sources via search summaries |
| A7 | Compass's own loops | Repository mining | Full read of `plugin/`; counts over this vault's logs on 2026-10-17 |
| A8 | Safety and stability | Systematic mapping study | Claude Code docs, local `claude --help` v2.1.302, Ralph plugin, ESLint, Betterer and ast-grep docs |
| A9 | The seven steps as a Compass pipeline | Systematic mapping study | Compass source, HumanLayer skill, Renovate and LangGraph source, Temporal and GitHub docs |
| A10 | Controller and control signal | Technology landscape (DESMET feature analysis) | ast-grep source, HumanLayer skill, Google FSE 2025 paper (PDF), Sentry and PostHog docs |
| A11 | FSMs | Systematic mapping study plus repository mining | LangGraph and XState source, Compass source; theory and LLM-FSM papers mostly at abstract level |
| G1 | Budgets and cost per accepted change | DESMET feature analysis plus a live run of Claude Code 2.1.302 | Three `claude -p` runs on this machine (JSON and transcript saved), vendor docs of seven agent products, blogs and preprints on cost per change |
| G2 | Skill or natural-language rules as judge sensor; rule compilation | Systematic mapping study | arXiv abstracts and HTML via a fetch summarizer, OpenAlex counts, Uber, G-Research and ast-grep engineering blogs |
| G3 | Where a loop's files live in a Compass project | Repository mining plus two experiments in a scratch project | `self_update._apply` and `guard.decide` run against the real `plugin/`; update, overlay, guard, vault and SPEC-009 sources read |

## Convergence Summary

| Category | Count | Claims |
|---|---|---|
| Converged | 35 | C1 to C5, C7, C8, C10, C12 to C21, C23 to C28, C32 to C34, C36, C38 to C40, C45 to C48 |
| Partial | 4 | C6 (what the baseline commits), C22 (ratchets exist), C41 (update empties the skills dir), C42 (cost per accepted change unreported) |
| Divergent | 5 | C9 (talk names a telemetry vendor), C29 (explicit FSM structure helps), C31 (where the LLM sits), C43 (judge drift unstudied), C44 (judge-score filtering absent) |
| Single axis, gap | 4 | C11 (golden patterns tested), C30 (FSM claim formalized), C35 (agent fork upkeep), C37 (react-doctor score formula) |

## Convergence Matrix

Cells: Y or N with the axis's own confidence (h, m, l); `-` means the axis did not address the claim. Agreement = Y over addressing axes.

| # | Claim | A1 | A2 | A3 | A4 | A5 | A6 | A7 | A8 | A9 | A10 | A11 | Agreement |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 | The seven steps come from Kyle Mistele's "Loop Engineering from First Principles" (HumanLayer) | Y(m) | - | - | Y(h) | - | Y(m) | - | Y(m) | Y(h) | Y(m) | - | 6/6 |
| C2 | HumanLayer's `design-control-loop` skill: phases A to H; set point, sensor, controller, actuator, disturbances, dampener | Y(h) | - | - | Y(h) | Y(h) | Y(h) | - | Y(h) | Y(h) | Y(h) | - | 7/7 |
| C3 | Sensor and controller, or controller and actuator, may be fused | Y(h) | - | Y(h) | Y(h) | Y(h) | Y(h) | - | - | Y(h) | Y(h) | - | 7/7 |
| C4 | The sensor must sit out of the actuator's reach (an inline comment cannot silence it) | Y(m) | - | Y(h) | Y(h) | - | Y(h) | - | Y(h) | - | Y(m) | - | 6/6 |
| C5 | Dampener = committed baseline plus a per-PR check on newly introduced deviations; optional, advisory by default | Y(h) | - | Y(h) | Y(h) | Y(h) | Y(h) | - | Y(h) | Y(h) | Y(m) | - | 8/8 |
| C6 | The baseline commits a violation count (Y) rather than the sorted violation list (N) | Y(m) | - | - | N(h) | - | Y(m) | - | - | - | - | - | 2/3 |
| C7 | Start the controller deterministic and tune it over time; an agent controller is allowed, the talk discourages it | Y(h) | - | - | Y(h) | - | Y(h) | - | - | - | Y(m) | - | 4/4 |
| C8 | Control signal = a controller output file spliced into the actuator prompt under a fixed heading, no schema | - | - | - | Y(h) | - | - | - | - | - | Y(h) | - | 2/2 |
| C9 | The talk names a telemetry vendor (Sentry) as controller input | - | - | - | N(h) | - | - | - | - | - | Y(m) | - | 1/2 |
| C10 | Golden patterns = hand-written before/after pairs and anti-patterns inside the actuator skill; no format prescribed | - | - | - | Y(h) | Y(l) | - | - | - | - | Y(h) | - | 3/3 |
| C11 | Golden patterns have been tested directly inside agent loops | - | - | - | - | - | - | - | - | - | N(l) | - | 0/1 |
| C12 | Loop = one sense-control-actuate iteration per scheduled CI run, opening one PR | - | - | - | Y(h) | Y(h) | Y(h) | - | - | Y(h) | - | - | 4/4 |
| C13 | Human on the loop = version-controlled feedback file loaded after the controller, plus `/iterate` PR comments | Y(h) | - | - | Y(h) | Y(m) | Y(h) | - | Y(h) | Y(h) | Y(h) | - | 7/7 |
| C14 | Flow control = at most one open PR per loop, checked before checkout; manual dispatch bypasses | Y(h) | - | - | Y(h) | Y(h) | Y(h) | - | Y(h) | Y(h) | Y(h) | - | 7/7 |
| C15 | HumanLayer's skill has no stop condition, budget, rollback, deadband or oscillation concept | Y(h) | - | - | - | - | - | - | Y(h) | - | - | - | 2/2 |
| C16 | Human review capacity is the binding limit on loop throughput | - | - | - | Y(h) | - | Y(h) | - | Y(m) | - | - | - | 3/3 |
| C17 | Claude Code's result carries cost, turns and duration; caps are print-mode only; cost is a client estimate; resume resets the budget | - | Y(h) | - | - | - | - | - | Y(h) | - | - | - | 2/2, 3/3 with G1 |
| C18 | Domain counts are not exposed by Claude Code; the loop's own command computes them | - | Y(h) | Y(h) | Y(h) | - | - | - | - | - | - | - | 3/3 |
| C19 | A judge without an external signal is an unreliable sensor; grounding it in measured evidence helps | - | Y(h) | - | - | Y(m) | - | - | - | - | - | - | 2/2, 3/3 with G2 |
| C20 | A sensor reading needs a validity or completeness check separate from its value | - | Y(h) | Y(h) | - | Y(m) | Y(m) | - | - | - | - | - | 4/4 |
| C21 | No source measures stability, oscillation or settling of a coding-agent loop over a real repository | Y(h) | - | - | - | - | Y(h) | Y(m) | - | - | - | - | 3/3 |
| C22 | Ratchet mechanisms exist and are usable as dampeners | N(m) | - | - | - | - | Y(m) | - | Y(h) | - | - | - | 2/3 |
| C23 | Every Compass loop is bounded by counts or timers, none by cost | - | - | - | - | - | - | Y(m) | - | Y(m) | - | Y(m) | 3/3 |
| C24 | Compass has no wall-clock scheduler | - | - | - | - | - | - | Y(m) | - | Y(m) | - | - | 2/2 |
| C25 | Compass has no persistent human-steering file read into an actuator | - | - | - | - | - | - | Y(m) | - | Y(m) | - | - | 2/2 |
| C26 | The capture worker is a working in-repo precedent for an unattended headless actuator | - | - | - | - | - | - | Y(h) | - | Y(h) | - | Y(h) | 3/3 |
| C27 | The capture machinery is an explicit FSM persisted in a state file plus an append-only ledger | - | - | - | - | - | - | Y(h) | - | Y(h) | - | Y(h) | 3/3 |
| C28 | The build fix loop is capped at 3 cycles per task, then escalates | - | - | - | - | - | - | Y(h) | - | Y(h) | - | Y(h) | 3/3 |
| C29 | Explicit FSM structure raises agent success and cuts cost | Y(m) | - | - | - | - | Y(h) | - | - | - | - | Y/N(m) | sources split |
| C30 | Some source formalizes "every control loop is also an FSM" | - | - | - | - | - | - | - | - | - | - | N(m) | 0/1 |
| C31 | Where the LLM sits in the loop | see Divergent | | | | | | | | | | | 4 positions |
| C32 | No LLM loop has been tested in Maya, nor outside a code repository with CI | - | - | - | - | Y(m) | Y(h) | - | - | Y(h) | - | - | 3/3 |
| C33 | A licensed local DCC does not fit the GitHub Actions or cloud-routine lane | - | - | - | - | Y(m) | - | - | - | Y(m) | - | - | 2/2 |
| C34 | Claude Code scheduling: `/loop` 7-day expiry, Desktop tasks 1-minute minimum on a waking machine, cloud routines 1-hour minimum on a fresh clone | - | - | - | - | Y(h) | - | - | Y(h) | Y(h) | - | - | 3/3 |
| C35 | Agent-driven fork maintenance has measured prior art | - | - | - | - | - | N(m) | - | - | - | - | - | 0/1 |
| C36 | react-doctor is a hybrid sensor and controller (problems plus "top three to fix") | - | - | Y(h) | Y(h) | - | Y(h) | - | - | - | - | - | 3/3 |
| C37 | react-doctor's score formula is reproducible from the open source | - | - | N(h) | - | - | - | - | - | - | - | - | 0/1 |
| C38 | Revert-on-break is used as a stability device in agent loops | - | - | - | - | - | Y(m) | - | Y(m) | - | - | - | 2/2 |
| C39 | Trajectory structure (repetition, FSM-state features) predicts agent failure | - | - | - | - | - | - | - | Y(l) | - | - | Y(l) | 2/2 |
| C40 | Steering state lives outside the model, persisted in files | - | - | - | Y(h) | - | - | - | Y(h) | Y(h) | - | - | 3/3 |

### Gap-pass rows

Claims a gap pass addressed. "Prior" lists the original axes' cells for the claim.

| # | Claim | Prior | G1 | G2 | G3 | Agreement |
|---|---|---|---|---|---|---|
| C17 | Caps are per invocation and resume does not count restored spend | A2 Y(h), A8 Y(h) | Y(h), live run | - | - | 3/3 |
| C19 | A judge without an external signal is unreliable; grounding helps | A2 Y(h), A5 Y(m) | - | Y(m) | - | 3/3 |
| C41 | Self-update empties the installed skills directory before copying, so a user skill there may be lost | A9 Y(m), A7 Y(m), both read code only and marked survival unverified | - | - | N(h), run experiment | 2/3 |
| C42 | No source reports dollar cost per accepted change | A4 Y(h), A6 Y(h) | N(m) for agent PRs in general, Y(m) for migration PRs | - | - | 2/3 |
| C43 | Judge-score drift across model versions has no direct study | A2 Y(l) | - | N(m), essay-scoring and anchor-set studies | - | 1/2 |
| C44 | No temporal filter or noise gate has been applied to judge-score series | A2 Y(l) | - | N(l), noise-band, EWMA and SPRT gates as CI tools | - | 1/2 |
| C45 | No study tests a skill or natural-language rule set as the judge against labelled data | A2 Y(l) | - | Y(m) | - | 2/2 |
| C46 | Repeated identical judge calls disagree even at temperature 0; voting reduces variance with diminishing returns | A2 Y(m) | - | Y(m) | - | 2/2 |
| C47 | Rubrics and yes/no checklists reduce judge disagreement | A2 Y(m) | - | Y(m) | - | 2/2 |
| C48 | Uber's LLM drafts deterministic AST rules for Java-to-Kotlin, never code | A6 Y(l-m) | - | Y(l) | - | 2/2 |

## Findings

### Attribution: where the seven steps come from

1. **The seven steps come from Kyle Mistele's talk "Loop Engineering from First Principles", not from a Dex Horthy talk** (confidence: high; axes A4, A1, A6, A8, A9, A10; C1)
   Mistele is HumanLayer's co-founder and CTO; the talk was given at AI Engineer World's Fair 2026. Its closing slide says "we built a skill" (`[1032s]`), which is the `design-control-loop` plugin in `humanlayer/skills`, added in commit `39fb327` (2026-06-30). Dex Horthy, HumanLayer's CEO, cites the same loop shape only in passing in a separate podcast.
   - Evidence: https://www.youtube.com/watch?v=xIt_mTQp6mY, uploaded 2026-07-25, about 18 minutes, transcript read in full (A4)
   - Evidence: Pragmatic Engineer podcast, YouTube `Usufn8IQJgw`, `[2216s]-[2300s]` (A4)
   - Marks: practitioner talk by the system's builder, primary; auto-captions with some mis-transcribed words; 31,021 views at fetch; talk and shipped skill agree. A1, A6, A8, A9 and A10 read only third-party summaries of the talk.
   - Grade: high

2. **The spec's Problem sentence is Mistele's own test for whether a task suits a loop** (confidence: high; single axis A4)
   "The key questions are, can we find something we can measure? Can we apply changes incrementally? And can we get feedback on the quality of those changes?" Loops "avoid over steering and destabilizing the system".
   - Evidence: transcript `[363s]-[386s]`, `[540s]-[547s]`
   - Marks: practitioner talk, primary; 1 source
   - Grade: high

3. **Each spec step maps to one phase of HumanLayer's skill** (confidence: high; axes A4, A5, A9)
   Spec step 0 = set point (Phase B1); 1 = sensor; 2 = dampener (Phase B5, offered as optional); 3 = controller; 4 = actuator (Phase C builds its skill); 5 = Phase E, CI wiring; 6 = Phase F; 7 = Phase G. The skill adds phases the spec does not name: A (read the repo before asking), D (run each component locally and standalone before CI), H (validate, dry-run, then speed up). Each phase has a completion criterion; "There is no fixed toolset and no template to reproduce."
   - Evidence: `design-control-loop/SKILL.md:10, 31-39, 41-157` at `653b641`
   - Marks: shipped code, owner checked (humanlayer org); 3 axes read it directly
   - Grade: high

### The control-theory mapping

4. **HumanLayer's loop is the classical feedback loop applied to a codebase** (confidence: high; axes A4, A1; C2)
   Plant = "your codebase"; set point = desired state; sensor measures current state; "the difference between those two things is your measured error"; the controller "turns it into a control signal about an incremental change"; the actuator applies it to a system "undergoing disturbances in the meantime"; then "we remeasure". The skill's set point is an invariant, a threshold or a direction, with a scope of what may be changed and what is read-only. Disturbances named: teammates, dependencies, generated code.
   - Evidence: transcript `[275s]-[312s]`; `control-loop-taxonomy.md:7-19`; `SKILL.md` Mental model
   - Marks: practitioner talk plus shipped code, primary; 2 sources agree
   - Grade: high

5. **The canonical block diagram for software adaptation, and what feedback buys over feedforward** (confidence: high; single axis A1)
   Set point minus measured output = error -> controller -> control signal -> software system (with disturbances) -> measured output. Feedback rejects unknown disturbances and tracks the set point; feedforward handles disturbances that can be measured and modeled, without output feedback. Controllers compose: cascaded, hierarchical, parallel, switching. MAPE-K (Monitor, Analyze, Plan, Execute over Knowledge) is the software-engineering counterpart, read second-hand through the same review (confidence medium).
   - Evidence: Shevtsov et al., IEEE TSE 44(8) 2018, doi 10.1109/TSE.2017.2704579, Sec 3.1-4.4, Figs 4-5
   - Marks: peer-reviewed systematic review of 42 studies from 1,512 hits; not retracted; 90 citations (OpenAlex)
   - Grade: high

6. **Control theory's formal qualities and how software adaptation actually uses them** (confidence: high; single axis A1)
   Named qualities: stability (converge rather than diverge), steady-state error, settling time (neither too short, which hurts robustness, nor too long), maximum overshoot, and robustness to model error. Only 13 of 42 studies give formal guarantees. Controllers used: PID family 50% (PI most common), MPC 26%, optimal 10%, deadbeat 8%, feedforward 5%; bang-bang appears as on/off admission control. Models are mostly linear, time-invariant, discrete and grey-box, refit at runtime because software has no physical laws and goes stale after updates. Sensor and actuator implementation is described in only 7 studies; the field calls itself "still in a preliminary stage", with open problems in turning qualities such as security into set points and in mapping controller outputs to software actuators.
   - Evidence: Shevtsov et al. Sec 4.3, 6, 7.4-7.6, 8.3, Tables 7-11, Fig 16
   - Marks: as finding 5
   - Grade: high

7. **Control theory applied to LLM agents is a 2026 cluster of preprints that propose vocabulary and mechanisms without proving stability for a loop over a codebase** (confidence: medium; single axis A1)
   - Harness as controller: state = context plus memory, LLM = stochastic policy; defines Lyapunov-like stability, context drift and control lag; authors say metrics were not estimated and the stress test "has not been run" (arXiv:2605.23950, HTML read, 1 citation).
   - Context assembly as the controlled variable: stability defined as windowed mean reward non-decreasing, "much weaker" than Lyapunov; 3 of 4 runs trended slightly negative (arXiv:2607.25408, HTML read).
   - CyberCorrect: oscillation = answer at t equals t-2 but not t-1; overshoot = severity rising by more than delta; stop below 0.05 change, cap 3 iterations, roll back on overshoot; 14.7 calls per task vs 6.2; metrics use the detector's own severity, not ground truth (arXiv:2605.17305, HTML read).
   - Regulatory control (dairy-barn ventilation, not code): one agent per PI loop, deterministic selectors with no LLM, the LLM returns a mode and intensity while code computes the numeric command; a proportional-only agent flipped bang-bang style until integral action and an oscillation history in the prompt were added; agents ran every 5 minutes vs 2 s classical (arXiv:2606.30877, HTML truncated).
   - Catalog-bounded LLM controller with a Lean 4 Lyapunov certificate, cyber-defense domain (arXiv:2605.03034, abstract only).
   - PID inside activation steering, controllability of next-token output, latent-space guardrails, consensus as a switched system, decoders as hybrid systems, LLMs for autonomic computing: abstracts only, different plants (arXiv:2510.04309, 2310.04444, 2510.13727, 2608.25099, 2610.01478, 2407.14402).
   - Marks: preprints 2024-2026, 0 to 1 citations, single source each; 2510.13727 conference-listed (IASEAI 2026)
   - Grade: low

8. **Term-by-term, the sources cover some control concepts and leave others empty** (confidence: medium; axes A1, A2, A6, A8; C22)
   | Concept | Covered by |
   |---|---|
   | Set point, sensor, controller, actuator, disturbance | HumanLayer (findings 4, 22 to 51); TSE review (5) |
   | Stability, overshoot, settling time | TSE review (6); CyberCorrect and context-assembly preprints, weak definitions (7) |
   | Oscillation | CyberCorrect alternation; regulatory-control mode flipping (7) |
   | Integral windup | CyberCorrect rollback, regulatory-control clipped integral (7) |
   | Gain, step size | Regulatory-control prompt curation (7); HumanLayer expresses step size as prose (31) |
   | Sampling rate | Regulatory control only, 5 min vs 2 s (7) |
   | Ratchet | None in the LLM-agent literature (A1); exists as CI tooling: Betterer, ESLint bulk suppressions (finding 28) |
   | Deadband, hysteresis | None found in agent loops (A1); temporal filtering (Kalman, EMA) of judge scores none found (A2); noise-band, EWMA and sequential-test gates on judge scores exist as CI tools, none called hysteresis, none tested in a loop (G2, finding 101; C44) |
   | Flow control, WIP limit | HumanLayer one open PR (finding 51); not a control-theory term in the sources |
   - Marks: synthesis over cited findings; "none found" means none in the sources each axis read
   - Grade: medium

9. **No source measures a coding-agent loop's step response, settling time, oscillation, or regressions caused by the loop itself** (confidence: high as a bounded absence; axes A1, A6, A7; C21)
   CyberCorrect comes closest but runs on reasoning tasks. Migration reports give landed-unchanged or pass rates only. No Compass loop has been run to failure to confirm a runaway or oscillation path.
   - Marks: negative finding across three independent searches and one code audit
   - Grade: medium

### Sensors: deterministic

10. **The stream-json `result` event is a ready-made per-run sensor frame** (confidence: high; axes A2, A8; C17)
    Keys in real events include `subtype`, `is_error`, `stop_reason`, `terminal_reason`, `duration_ms`, `duration_api_ms`, `num_turns`, `total_cost_usd`, `usage`, `modelUsage`, `permission_denials`, `subagent_stats`. Subtypes: `success`, `error_max_turns`, `error_max_budget_usd`, `error_during_execution`, `error_max_structured_output_retries`. Over 44 real capture-worker runs (haiku-4-5): cost 0.36 / 0.71 / 2.19 USD (min/median/max), turns 17 / 28 / 55, wall time 80 / 189 / 529 s, one workload only (confidence medium for the magnitudes). Compass's `clone` already parses this event (`plugin/cli/commands/clone.py:371-394`).
    - Evidence: 44 `"type":"result"` lines in `.compass/archive/logs/OPP-*.log`; claude-agent-sdk-python `types.py` `ResultMessage`; https://code.claude.com/docs/en/agent-sdk/agent-loop
    - Marks: code and emitted data, owner checked; docs; 3 sources agree
    - Grade: high

11. **`usage`, `total_cost_usd` and `modelUsage` count different things, and naive sums over-count** (confidence: high; single axis A2)
    `usage` covers only the top-level loop; `total_cost_usd` and `modelUsage` include subagents. Per-step `output_tokens` on assistant messages is a placeholder; one API response appears as several records sharing an `id` (555 of 866 local ids appear 2 to 6 times), so sums must dedupe by `id`.
    - Evidence: https://code.claude.com/docs/en/agent-sdk/cost-tracking; local transcript survey
    - Marks: official docs plus local data; 2 sources agree
    - Grade: high

12. **Cost is a client-side estimate, budget caps are per invocation, and resume resets them** (confidence: high; axes A2, A8; C17)
    Docs: "Do not bill end users or trigger financial decisions from these fields." `--max-budget-usd` and `--max-turns` are print-mode only; spend can pass the budget cap by up to one response plus still-running subagents; totals restored by `--resume`/`--continue` do not count toward the cap, while a resumed result reports the session's cumulative spend. A crashed session may report zeroed cost. `--max-turns` is documented but missing from `claude --help` v2.1.302 on this machine.
    - Evidence: https://code.claude.com/docs/en/cli-reference; cost-tracking doc; agent-loop doc "Budget headroom"
    - Marks: vendor docs, 3 pages agree; local help partial confirmation; confirmed by a live run on 2.1.302 (G1, findings 87 to 89)
    - Grade: high

13. **Hooks can halt a run but carry no cost; domain counts must come from the loop's own command** (confidence: high; axes A2, A3, A4; C18)
    No hook payload carries usage or cost, except `SessionStart` on resume or fork (`context_tokens`, `estimated_cache_write_usd`). A hook can stop the run with `continue:false` (verified live in [[research/pipeline/RESEARCH-context-threshold-stop]]) or block with `decision:"block"`. The only domain-adjacent built-ins are lines added and removed, commits and PRs. Counts such as "unmigrated files" come from the user's own command (ast-grep, test runner); its exit code and count are the sensor. Whether `Stop` and `SessionEnd` inputs carry usage is unconfirmed (docs fetch truncated).
    - Evidence: https://code.claude.com/docs/en/hooks; absence across statusline, OTel, hooks docs and result keys
    - Marks: official docs plus a prior live probe; negative finding across 5 sources
    - Grade: high for halting, medium for the absence claim

14. **OpenTelemetry and the statusline expose cost, tokens, tool results, lines and context fill, with limits** (confidence: medium; single axis A2)
    OTel (`CLAUDE_CODE_ENABLE_TELEMETRY=1`): `claude_code.cost.usage`, `claude_code.token.usage` with subagent attribution, `claude_code.tool_result` with `success` and `error_type`, commit and PR counts; exporter env in a repo's `.claude/settings.json` is ignored. The statusline JSON carries live cost and `context_window.used_percentage` but runs only in interactive sessions, so it is not a headless-loop sensor.
    - Evidence: https://code.claude.com/docs/en/monitoring-usage (summarizing fetch, not run); https://code.claude.com/docs/en/statusline
    - Marks: official docs; OTel not exercised
    - Grade: medium for OTel, high for statusline

15. **A sensor reading needs a validity check separate from its value: "no findings" must not read as "healthy"** (confidence: high; axes A2, A3, A5, A6; C20)
    Each axis found its own instance. react-doctor reports carry `complete`, `analyzedFiles`, `skippedChecks`, and docs say "Consumers must not infer coverage from an empty diagnostics array" (A3). Claude Code error results can under-report cost and `cost-state` is written only on normal exit (A2). A count-only check passes an animation cache where every frame is identical; compare count and at least one varying channel (A5). In language translation, 100% incremental compile coexists with 80.08% test pass; test262 percentages move from about 99.6% to 94.2% depending on runner scoring (A6).
    - Evidence: react-doctor `docs/json-report.md:23-34`; cost-tracking doc; `maya-mcp/docs/skills/maya-headless-batch/SKILL.md` section 4; arXiv:2603.02617, test262.fyi (search summaries)
    - Marks: code and docs for A2, A3; single-source skill for A5; search summaries for A6; 4 axes agree
    - Grade: high (grouping of independently cited instances)

87. **`--max-turns 1` is honored: the run ends with exit 1 and `subtype: error_max_turns` after the first tool has run, and `num_turns` reports 2** (confidence: high; single axis G1)
    Live run, haiku-4-5, Claude Code 2.1.302: `claude -p --max-turns 1 --output-format json "say hi then list files with a tool"`. Verbatim: `"terminal_reason":"max_turns"`, `"stop_reason":"tool_use"`, `"is_error":true`, `"num_turns":2`, `"errors":["Reached maximum number of turns (1)"]`, `"total_cost_usd":0.041615`; the JSON has no `result` key. The transcript holds the `tool_use` and its `tool_result` and no assistant message after it: the model turn ran, its tool executed, and the run stopped before the next model call. The flag works while still absent from `claude --help`.
    - Evidence: `.compass/tmp/research-control-loops/gap-01-evidence/r1.json`; session transcript `25441f85-ede7-4bc2-a5bf-949a899a07af.jsonl`
    - Marks: live run on the installed product, 1 run; agrees with vendor docs
    - Grade: high
    - Caveat: one observation at N=1; the reading "cap N allows N tool rounds" is untested at N greater than 1.

88. **On resume, `total_cost_usd` and `modelUsage` are cumulative, `num_turns` and `usage` are per invocation, and `--max-budget-usd` counts only new spend** (confidence: high; single axis G1)
    Run 2 resumed run 1's session with `--max-budget-usd 0.02`. The restored total (\$0.041615) already exceeded the cap; the run still returned `success` at cumulative \$0.0463805, of which \$0.0047655 was new. `modelUsage` summed both runs (`outputTokens` 219 = 171 + 48); top-level `usage` showed only the new call. A loop that resumes one session per iteration gets a fresh cap each time.
    - Evidence: `gap-01-evidence/r2.json`
    - Marks: live run, 1 run; confirms the docs claim in finding 12
    - Grade: high
    - Caveat: not tested: a resume whose new spend alone exceeds the cap.

89. **A hit budget ends the run with `subtype: error_max_budget_usd`, exit 1, `terminal_reason: budget_exhausted`, checked after the first response; `usage` is zeroed on that stop** (confidence: high; single axis G1)
    Run 3, fresh session, `--max-budget-usd 0.001`: `"errors":["Reached maximum budget ($0.001)"]`, `"num_turns":1`, `"total_cost_usd":0.0174133`, 17 times the cap, so the cap is checked after a response, not before the request. Top-level `usage` is empty (`"iterations":[]`) while `modelUsage` carries the real tokens, so a parser reads `total_cost_usd` or `modelUsage` on a budget stop, never `usage`.
    - Evidence: `gap-01-evidence/r3.json`
    - Marks: live run, 1 run; agrees with the docs ("Spend can therefore pass the cap")
    - Grade: high
    - Caveat: a \$0.001 cap is below one response's cost on any model; the overshoot ratio reflects that choice.

90. **The session transcript holds `cost-state` records, a per-session spend ledger a script can read without the CLI** (confidence: high for presence, low for format stability; single axis G1)
    After each invocation the JSONL gains `{"type":"cost-state","totalCostUSD":...,"modelUsage":{...},"totalAPIDuration":...,"totalLinesAdded":...,"hasUnknownModelCost":false}`: 0.041615 after run 1, 0.0463805 after run 2. It is the record resume restores, and a wrapper can sum it per session independently of `--max-budget-usd`. Finding 15 notes it is written only on normal exit.
    - Evidence: run 1 transcript, two `cost-state` records
    - Marks: live run, file read; schema absent from the public docs read
    - Grade: high for presence on 2.1.302, low for stability across versions

91. **Per-iteration cost depends on cache hits: a cold first call cost \$0.042, a warm resume \$0.005, a fresh second session \$0.017** (confidence: medium; single axis G1)
    Run 1 wrote 20,375 tokens to the 1-hour cache; run 2 read them back and wrote 1,239; run 3 read 13,053 and wrote 7,349. Resume iterations inside the cache lifetime cost less than fresh sessions.
    - Evidence: `gap-01-evidence/r1.json`, `r2.json`, `r3.json`
    - Marks: live run, 3 runs, haiku only; local list-price estimates (`"costBasis":"list"`), not the bill
    - Grade: medium

### Sensors: judges

16. **Judge biases are large, systematic and judge-specific** (confidence: high; single axis A2)
    Order-swap consistency: GPT-4 65.0%, GPT-3.5 46.2%, Claude-v1 23.8%; swapping order alone reverses rankings; bias grows as the quality gap shrinks (arXiv:2306.05685, 2305.17926, 2406.07791). A repetitive-list attack fooled Claude-v1 and GPT-3.5 91.3% of the time, GPT-4 8.7%; length-controlled AlpacaEval corrects verbosity with a GLM (Spearman 0.94 to 0.98 with Chatbot Arena) (arXiv:2404.04475, confidence medium). Self-preference has two proposed mechanisms, self-recognition and low perplexity (arXiv:2404.13076, 2410.21819, confidence medium); a 12-bias taxonomy finds biases persist in advanced models (arXiv:2410.02736).
    - Marks: peer-reviewed (NeurIPS 2023 D&B 12,261 cites; ACL 1,412; AACL 345; ICLR 2025 456), Dubois preprint 1,024 cites; not retracted; 3 independent papers agree on position bias
    - Grade: high for position bias, medium for the rest

17. **Repeated identical judge calls disagree, even at temperature 0** (confidence: medium; single axis A2)
    Pairwise preference flips 13.6% on average across trials; neutral rewording changes the majority outcome in 25% of cases; about 11 trials match the 50-trial verdict at 95% (arXiv:2606.13685). Scores vary substantially at temperature 0 across 5 judges, completeness most (arXiv:2603.04417). Pointwise and pairwise outputs are mutually inconsistent; expected-value scoring over rating probabilities plus both-order aggregation cut transitivity inconsistency from 15.22% to 4.40% (arXiv:2509.21117, preprint); the mean of the judgment-token distribution beats the mode (arXiv:2503.03064, EMNLP 2025 Findings).
    - Marks: 2026 single-author preprints for the noise figures (0 and 7 citations); mixed for consistency fixes; all via a fetch summarizer; G2 reaches the same direction on code review (findings 97, 98; C46)
    - Grade: low for the noise numbers, medium for the consistency fixes

18. **Judge-human agreement is not accuracy: on hard items judges approach chance** (confidence: high; single axis A2)
    GPT-4 agrees with humans 85% excluding ties, against human-human 81% (arXiv:2306.05685). With labels from objective correctness, strong models are "just slightly better than random guessing" on hard knowledge, reasoning, math and coding pairs (JudgeBench, arXiv:2410.12784, ICLR 2025). Only the largest of 13 judges align reasonably, still lenient (arXiv:2406.12624).
    - Marks: peer-reviewed; 401 and 283 citations; 3 sources; the two headline figures measure different ground truths
    - Grade: high

19. **Rubrics and checklists reduce judge variance; panels and calibration help with caveats** (confidence: medium; single axis A2)
    Yes/no checklists raised inter-evaluator agreement by 0.45 (CheckEval, arXiv:2403.18771, EMNLP 2025); a 13B rubric-conditioned judge reached Pearson 0.897 with humans (Prometheus, arXiv:2310.08491, ICLR 2024); grading changes the criteria users hold ("criteria drift", arXiv:2404.12272). Diverse-family panels beat one large judge and were 7x cheaper (PoLL, arXiv:2404.18796), but plain averaging of five judges did not beat the best single judge in a days-old preprint (arXiv:2610.21179). A small human-labeled set lets a measurement-error correction control Type-I error (arXiv:2601.20913, ICLR 2026); with 5% annotator overlap, deployment decisions are wrong 25% of the time (arXiv:2609.31857). On rubric-item verification for agentic coding and deep research (RuVerBench, 2,458 human-labelled instances, arXiv:2606.29920, EMNLP 2026 accepted per its abstract page), top models still show "substantial noise", weaker models are more prompt-sensitive, majority voting gives diminishing returns, and batching several items per call trades accuracy for cost (G2; C47).
    - Marks: mixed peer-reviewed and preprint; calibration papers all 2026 and nearly uncited; RuVerBench abstract only, 0 citations; 2 axes agree on rubrics
    - Grade: medium for rubrics, low for panels' contested part and for calibration

20. **A judge without an external signal is a weak feedback path; tool-grounded critics help** (confidence: high; axes A2, A5; C19)
    Without external feedback LLMs "struggle to self-correct" reasoning (arXiv:2310.01798, ICLR 2024, 1,341 cites); self-critique degrades GPT-4 on planning while a sound external verifier improves it (arXiv:2402.08115); CRITIC stresses tools as external feedback (arXiv:2305.11738). Agent-as-a-Judge with tools matches a human-evaluation baseline on DevAI (arXiv:2410.10934, ICML 2025, confidence medium). A vision-model judge agrees with experts at Cohen's kappa 0.70 on coarse animation criteria and 0.10 on fine-grained part-level ones, and one paper recommends feeding it measured evidence such as optical flow (arXiv:2606.04773, abstract; A5).
    - Marks: 4 peer-reviewed for the external-signal claim; VLM figure from one preprint abstract, direction consistent with several unfetched abstracts; G2 agrees from the rule-generation side, where every system reporting results anchors on an executed test (finding 106)
    - Grade: high for external signal, medium for the VLM figure

21. **Judge-score drift and temporal filtering of judge scores have no direct study** (confidence: low; single axis A2)
    GPT-4 accuracy on one task dropped 84% to 51% between March and June 2023 versions (arXiv:2307.09009), but that measures generation, not judging. One arXiv search found no Kalman, EMA, low-pass or hysteresis filtering of judge-score series. No study tests a skill or a set of natural-language rules as the judge, which is the non-deterministic sensor the spec names; rubric and checklist papers are the nearest.
    - Marks: bounded negative from one search per topic
    - Grade: medium for "model behavior drifts", low for "judge scores drift"
    - Later evidence: G2 searched these topics directly. It agrees no study tests a skill or rule set as the judge (finding 92; C45), but found judge-version drift studied in essay scoring and anchor-set drift monitoring (finding 100; C43), and noise-band, EWMA and sequential-test gates on judge scores (finding 101; C44). Both disagreements are listed under Divergent.

92. **No benchmark scores an LLM against an arbitrary written style guide with ground-truth labels, and no study tests a skill plus natural-language rules as the judge** (confidence: medium; axes G2, A2; C45)
    Searches found only pieces: PEP-8 detection, Checkstyle-style rules, MISRA C, architectural decision records, project-specific review; a 2026 search summary concluded no public multi-language benchmark of this shape exists. The nearest design to borrow is CompliBench, which plants known violations for exact labels, but it targets dialogue, not code.
    - Evidence: arXiv:2604.12312 (CompliBench); arXiv:2602.07609; arXiv:2510.23068; search summaries 2026-10
    - Marks: preprints; not retracted; absence from several searches, not an exhaustive review; 0 to few citations; 3 searches agree
    - Grade: low (negative finding)

93. **Rule-compliance judging splits by rule type: explicit, locally visible rules do well; implicit, cross-file or organizational rules do not** (confidence: medium; single axis G2)
    Over 980 architectural decision records in 109 repositories, four LLMs agreed substantially and were accurate on decisions explicit in code, less so on infrastructure, implicit-intent and multi-module decisions (arXiv:2602.07609). A Python study found LLMs better on documentation and type-hint violations than on stylistic consistency (Koya University PEP-8 study, search summary). LASIK (KAIST, MISRA C, ASE 2026 per listing) decomposes functions into suspicious sites, checks each against a rule, found 1.3 to 2.7 times more true violations than static analyzers on 10 embedded projects, with a 26.7% false-alarm ratio (search summary only; confidence low).
    - Marks: preprints plus one unverified journal listing and one conference paper not fetched; 0 citations (2602.07609); 3 sources agree on direction
    - Grade: medium for the split, low for LASIK

94. **An industrial two-agent pattern turns requirements into rules, then audits code against them; the rule-mining step is itself non-deterministic at temperature 0** (confidence: medium for the mechanism, low for results; single axis G2)
    At NIO (Claude Opus 4.6 for both agents), ruleMiner extracted verifiable rules and logged 75 issues out of 222 items (ambiguous, contradictory, unverifiable); codeAuditor broke each rule into concrete checks (limits, thresholds, uniqueness, triggers) and returned 8 Fail or Unknown findings, none judged false positive in the inspected set. Recall was not evaluated; the authors call results preliminary. ruleMiner produced different rule sets across runs at minimum temperature; the authors merged up to three runs rather than measuring the difference. Both stages stay LLM-based.
    - Evidence: arXiv:2605.17926 (2026-05-18)
    - Marks: industrial experience report, preprint; not retracted; 0 citations; 1 source
    - Grade: low

95. **Uber uReview splits generating from filtering: a grader model with per-category thresholds, and a five-run reproduction check for "addressed"** (confidence: high for the design, low for quality numbers; single axis G2)
    A second prompt grades each comment with a confidence score; cutoffs are set per assistant, language and comment category from developer feedback; a similarity filter dedups; a classifier suppresses categories of historically low value. Best pairing by F1: Claude-4-Sonnet generating, o4-mini-high grading. A comment counts as addressed only if none of 5 re-runs on the final commit reproduces it; 5 is the smallest count that "virtually eliminates missed detections". Reported: about 75% of rated comments useful, over 65% addressed (51% for human comments), 90% or more of about 65,000 weekly diffs covered. A "Best Practices" assistant reads a shared registry of Uber style rules into the prompt, never compiled into checks.
    - Evidence: https://www.uber.com/us/en/blog/ureview/ (2025-08-12)
    - Marks: vendor engineering blog with ownership interest; no precision published; 1 primary source plus secondary summaries
    - Grade: medium for the design, low for the quality claims

96. **G-Research's coding-standards reviewer: separate recall and precision passes, severity from the RFC 2119 keyword, output validated against a rules index** (confidence: medium; single axis G2)
    A single pass gave 2 to 3 false positives in 8 findings; a second call re-checks each finding. Model adoption gates: MUST and MUST NOT rules at 100% recall, SHOULD at 75%, no false positives on the integration set, overall precision above 85%. Output is forced into a Pydantic schema; a finding citing an unknown rule, title or level is rejected; severity is computed from the keyword, not by the model. No test-set size, repeated-run averaging or calibration method is given.
    - Evidence: https://www.gresearch.com/news/building-a-code-review-tool-the-llm-patterns-that-actually-work/ (2026-05-13)
    - Marks: company engineering blog, owner checked; 1 source
    - Grade: medium for the mechanism, low for effectiveness

97. **Whole-PR LLM review reaches F1 about 19% at best, and merging repeated reviews from one model raises it** (confidence: medium; single axis G2)
    SWR-Bench, 1,000 manually verified PRs across 12 projects: best PR-Review with Gemini-2.5-Pro, precision 16.65%, recall 23.18%, F1 19.38%; four other tool families had precision below 10%. Only 36 found issues overlapped across models and 27 across five runs of one model. Merging 10 reviews of the same PR from Gemini-2.5-Flash raised F1 from 15.25% to 21.91% and recall by 118.83%, the precision and recall trade steered by intersecting or unioning runs. The LLM grader of review hits agreed with humans 89.2 to 94.9%. These are real-bug review tasks, not rule-set compliance.
    - Evidence: arXiv:2509.01494 (2025-09-01)
    - Marks: preprint, no venue listed; 0 citations; 1 source
    - Grade: medium

98. **The same code review at temperature 0 yields different findings; repeated sampling cuts variance with diminishing returns and leaves bias in place** (confidence: medium; axes G2, A2; C46)
    Four LLMs, 70 Java commits, 5 repeats at temperature 0 (21,000 responses): responses varied, no consistency score given (arXiv:2502.20747). Rating Roulette (EMNLP 2025 Findings) finds "low intra-rater reliability", "almost arbitrary in worst case"; a search summary gives Krippendorff alpha 0.265 to 0.563 over 3 runs and temperature 0 lowering human agreement for two models (arXiv:2510.27106). About 11 trials match the 50-trial verdict at 95% (arXiv:2606.13685); averaging k=8 scores raised RewardBench 2 accuracy from 71.7% to 81.5% at 5x cost, about 70% of the gain by k=3 (arXiv:2604.13717, vendor-affiliated). A search summary states bias terms do not shrink with more calls (arXiv:2602.21368, not fetched).
    - Marks: preprints and one Findings paper, 0 to 11 citations; not retracted; 3 sources agree on direction; most figures on preference tasks, not rule compliance; Rating Roulette figures via summary
    - Grade: high for the existence of run-to-run disagreement, medium for voting, low for the alpha figures

99. **Consistency is not validity: a judge can repeat its own score 97% of the time and correlate 0.28 with humans** (confidence: medium; single axis G2)
    Local judges: LLaMA-3-8B Pearson 0.275 with humans (Qwen2.5-7B 0.340) while repeating its scores 97.3% and 92.3% of the time (arXiv:2609.13824). An essay-scoring audit found replication was not the bottleneck at temperature 0, phi 0.80 or more with two or fewer repeats (arXiv:2608.29517).
    - Marks: preprints; 0 citations; 2 sources agree; figures from search summaries
    - Grade: low

100. **Judge-version changes shift scores loudly, and judge drift can be separated from system drift with a frozen anchor set** (confidence: medium; single axis G2; C43)
    A pre-registered audit of 12 essay judges from 4 providers found every version comparison changed severity beyond chance, up to 133 points on a 0 to 1000 scale, and rejected "silent drift" because agreement with humans moved in four of five comparisons; one judge was retired mid-study (arXiv:2608.29517, under review). "Who Drifted" re-scores a fixed human-labelled anchor set at intervals, tracks the judge-versus-human gap with a betting e-process, and attributes drift to none, system or judge: a silent version bump flagged as judge drift in 60 of 60 runs, a rolling z-test false-alarmed on 75% of drift-free streams, cost about 0.64 of judging every item (arXiv:2606.15474, abstract only). Practitioner posts converge on pinning a dated judge snapshot, storing judge ID, prompt hash and rubric version with every score, keeping a frozen labelled regression set, and A/B testing a candidate judge before switching (tianpan.co, qaskills.sh, via search summary). No study covers judge drift for code review or rule checking.
    - Marks: single-author preprints, 0 citations, non-code domains; practitioner posts, tier-3 blogs, advice not measurement
    - Grade: low to medium for the two studies, low for the practices

101. **Noise-band, control-chart and sequential-test gates exist for noisy judge scores; none is called hysteresis and none is tested on a rule-compliance sensor** (confidence: low; single axis G2; C44)
    llm-eval-gate fails CI only when a change is both large and outside a noise band $\sigma \sqrt{se_{base}^2 + se_{cand}^2}$; drift-caliper applies EWMA with a target average run length to judge scores; AgentAssay adapts Wald's SPRT with a PASS / FAIL / INCONCLUSIVE verdict and reports 78% fewer trials (arXiv:2603.02601). A coarse score grid (0, 0.25, ..., 1) is suggested to stop sub-grid noise moving aggregates. Reading the INCONCLUSIVE zone and the noise band as a deadband is G2's inference; the sources do not use that framing.
    - Evidence: https://github.com/CJstate/llm-eval-gate; https://github.com/binary-glide/drift-caliper; arXiv:2603.02601 (all via search summary)
    - Marks: code repos, owner not checked, no stars retrieved; preprint, citations not retrieved; 3 sources, different mechanisms
    - Grade: low

102. **Anchoring a judge to a deterministic count is stated as advice, never measured** (confidence: low; single axis G2)
    Uber's advice: push what you can into linters, compiler and tests, and let the agent handle what is left against encoded standards; uReview frames linters for syntactic patterns and the LLM for semantic ones. No source measures a hybrid sensor where a deterministic count gates or recalibrates a judge's reading. Checkstyle+ and "Still Manual?" combine an LLM with a linter at configuration time only.
    - Evidence: https://ai.engineer/talks/EL123UNokkI-building-ureview-ubers-multi-agent-code-review (summary); uReview post
    - Marks: vendor talk and blog; 2 sources agree on stance; no measurement
    - Grade: low

### Sensors: compiling rules into deterministic checks

103. **Uber's documented LLM-writes-rules work is the Java-to-Kotlin pipeline; no Uber artifact turns natural-language lint rules into ast-grep or semgrep** (confidence: medium; axes G2, A6; C48)
    An LLM drafts AST rules for Uber's in-house Rectify tool; each rule runs through the migration pipeline and CI (tests, builds, lint), failures feed back to the LLM, passing rules go to platform engineers for review, and approved rules become permanent deterministic transformations. Seeds come from a dataset of what the tooling missed (tool output diffed against developer-landed migrations), not from natural-language rules. Stated reason: hallucinated code could cause production outages. Timeline projection: about 4 years against about 3 for hand-written rules in CI and about 8 as baseline. No accuracy, acceptance or rule counts. Agrees with finding 80.
    - Evidence: https://www.zenml.io/llmops-database/llm-driven-developer-experience-and-code-migrations-at-scale (secondary summary of a talk; video not watched)
    - Marks: grey literature, secondary; 2 sources
    - Grade: low

104. **ast-grep's author documents a five-step loop for LLM rule writing, with named failure modes and no accuracy number** (confidence: high for the recipe; single axis G2)
    Little training data on ast-grep syntax causes hallucination: O3 invented CodeQL- or jscodeshift-like syntax, Gemini borrowed Semgrep syntax, Claude 4 wrote valid syntax but missed subtle details; errors compound across composed atomic rules. What worked: understand the request, write a sample snippet, write a rule matching it, test the rule against the snippet, search the codebase. No success rate is given.
    - Evidence: https://ast-grep.github.io/blog/ast-grep-agent.html (June 2025)
    - Marks: tool maintainer's blog, owner checked; 1 source
    - Grade: medium for the recipe, none for accuracy

105. **Accuracy of LLM-written checkers depends on what counts as success, from valid-rule rate to confirmed real bugs** (confidence: medium; single axis G2)
    - AutoChecker: PMD rules from a description plus a test suite, one failing case at a time; 20 random PMD rules, average test pass rate 82.28%, ahead of 5 baselines (arXiv:2411.06796; ICSE 2026 per one summary, unconfirmed; 1 citation).
    - KNighter: Clang Static Analyzer checkers synthesized from patches, validated against the patch and refined against false positives; 92 new Linux kernel bugs, 77 confirmed, 57 fixed, 30 CVEs (arXiv:2503.09002, SOSP 2025, 11 citations).
    - QLCoder: CodeQL queries through execution feedback, 53.4% success with Claude Code against 10% for Claude Code alone (arXiv:2511.08462, ICLR 2026, search summary only).
    - SemOpt: Semgrep rules per cluster of optimization commits; rule-generation success 92.28% (C/C++) and 99.86% (Python) measures a valid rule, not a correct one; raw scanning precision 1.56%, recall 82.78% (arXiv:2510.16384, search summary, 2 citations).
    - Marks: peer-reviewed and preprints; not retracted; metrics differ, so the four do not converge on one number
    - Grade: medium for KNighter and AutoChecker, low for QLCoder and SemOpt

106. **Every rule-generation system that reports results runs each candidate and iterates; one-shot generation works poorly** (confidence: medium; single axis G2)
    ast-grep tests against a snippet, AutoChecker against a failing test case, KNighter against the patch, QLCoder through execution feedback (100% compile with an agent framework), Uber's Rectify rules through CI, Autogrep against vulnerable and fixed code. The test case or suite is the deterministic anchor in each. The ast-grep post and the QLCoder summary report unaided frontier agents far lower.
    - Evidence: findings 103 to 105; Autogrep https://lambdasec.github.io/AutoGrep-Automated-Generation-and-Filtering-of-Semgrep-Rules-from-Vulnerability-Patches/ (search summary)
    - Marks: mixed peer-reviewed, preprints and blogs; 6 sources agree on the pattern
    - Grade: medium

107. **Natural-language coding standards can be mapped to linter configuration: LintCFG reports above 90% on a DSL step and about 70% on detailed configuration** (confidence: medium; single axis G2)
    Pipeline: tool-agnostic DSL, standard to DSL rules, DSL to linter option names and values, consistency check, per-linter output (Checkstyle for Java, ESLint for JavaScript). DSL precision and recall above 90%; fine-grained configuration accuracy, precision, recall and F1 near 70%. It sets options of existing rules and writes no new rule logic.
    - Evidence: arXiv:2602.07783 (FSE 2026, DOI 10.1145/3797064, abstract)
    - Marks: peer-reviewed; 1 citation; 1 source
    - Grade: medium

108. **No source reports accuracy for LLM-written semgrep or ast-grep rules from natural-language coding conventions** (confidence: medium; single axis G2)
    Searches found LintCFG (configuration), AutoChecker (PMD) and security-focused generators, not this case; the ast-grep post is qualitative.
    - Marks: absence from 4 searches; not exhaustive
    - Grade: low (negative finding)

### Step 0: End state

22. **The end state is a codebase property with a scope, and it is the one step that fits a spec** (confidence: high for the shape, medium for the Compass placement; axes A1, A4, A6, A9)
    HumanLayer's example end state: migrate their RPC API to Effect, adopted first "for some of our race-prone code". Other end states named in the talk: root out bad patterns, comply with someone's OpenAPI spec, keep an MCP server compliant with the current MCP spec version, mirror a project between Python and TypeScript, maintain a Vite-based fork of Next.js against upstream ("Vite" inferred from a garbled caption). Under Compass rules a spec holds the need with no technology choices, so step 0 fits a spec while steps 1 to 7 (a sensor tool, a schedule, an actuator agent) do not (A9, single axis, inference from the rule).
    - Evidence: transcript `[341s]-[361s]`, `[508s]-[539s]`; `.claude/rules/compass-pipeline.md` "Specs"
    - Marks: practitioner talk, primary; first-party Compass rules
    - Grade: high for the talk, medium for the placement

### Step 1: Sensor

23. **Sensor options are deterministic, agentic, or a pipeline of both; HumanLayer chose ast-grep because it sits out of the actuator's reach** (confidence: high; axes A4, A1, A3, A6, A8, A10; C4)
    Options listed: "your ESLint rules, your AST grep", or "an agent and a skill and a bunch of natural language rules", or both (`[433s]-[452s]`). For the Effect loop: ast-grep, because it is "language-agnostic" and "out of band from your TypeScript config or ESLint rules, which ... you have watched Claude disable those with inline comments" (`[590s]-[603s]`). Raw output carries about 50 keys per violation, filtered to four and sorted deterministically (`[625s]-[633s]`; which four is not stated). The skill names sensor trade-offs: stability, cost, repeatability, and "whether the measurement can be silently disabled" (`SKILL.md:66`). Suppression is itself detectable: ast-grep ships `unused-suppression` and `no-suppress-all` rules, off by default (A10); react-doctor has a `--no-respect-inline-disables` audit mode (A3).
    - Marks: practitioner talk plus shipped code, primary; 6 axes agree
    - Grade: high

24. **ast-grep gives the fields a sensor and controller need, but no baseline and no ranking** (confidence: high; axes A8, A10)
    `ast-grep scan` exits 1 only when an `error`-severity rule matches; `--format github|sarif` for CI; `--json=stream` gives one match per line with `file`, `range` (start and end line and column), `text`, `charCount`, `metaVariables`. Rules live in `sgconfig.yml` plus `rules/`, separate from ESLint and TypeScript config. There is no built-in baseline file (a wrapper must commit the scan output) and no ranking by size; size must be derived downstream from `range`.
    - Evidence: ast-grep `crates/cli/src/print/json_print.rs:20-88` at `14934d6`; https://ast-grep.github.io/reference/cli/scan.html
    - Marks: code read plus project docs; 2 sources agree. The size derivation was reasoned from the schema, not executed.
    - Grade: high

25. **Compass's research skill already has the machinery to feed sensor design** (confidence: medium; single axis A9)
    A "what can measure the gap" question is an ordinary research axis; session enumeration (`claude mcp list`, `claude plugin list --json`) would surface telemetry connectors already installed; code-shaped questions dispatch to `research-codebase`, the same job as HumanLayer's Phase A repo discovery. The curated `sources.yaml` rows are scholarly, so it offers nothing for telemetry.
    - Evidence: `plugin/skills/research/SKILL.md:16-21, 25-43`; `plugin/cli/sources.yaml`
    - Marks: first-party code and skill text; mapping to sensor design is inference
    - Grade: medium

### Step 2: Dampener

26. **HumanLayer's dampener: one full scan on main, committed, then a per-PR check that the branch added no new violations** (confidence: high; axes A4, A1, A6, A8; C5)
    Mistele steps "outside of our control loop paradigm": before migrating one procedure at a time, "we need to enforce that all new procedures are using effect". Mechanism: "run a full scan once on main, sort all the violations deterministically, and track it in our version control. And then on every new PR, we can see if the branch added any unmigrated procedures." The disturbance is teammates shipping Claude-written code; the purpose is to make sure "they're not undoing our loop's work". He calls it a "disturbance dampener" only if "we ... squint", and "now that we've stopped the bleeding, we can actually design our controller".
    - Evidence: transcript `[636s]-[679s]`
    - Marks: practitioner talk, primary; 4 axes agree on the mechanism (3 via summaries)
    - Grade: high

27. **In the shipped skill the dampener is optional and advisory, with a path to blocking** (confidence: high; axes A4, A5, A6, A8, A9; C5)
    "Offer it; not every loop needs one": "a PR check that compares the sensor's output against a baseline and surfaces (or eventually blocks) newly introduced deviations". The React Doctor example runs on every PR and push to main, "diffs against the merge base and comments on only the newly introduced issues", "advisory by default (never red-Xes a teammate's PR)". Whether HumanLayer's own Effect dampener fails or comments is not stated.
    - Evidence: `SKILL.md:75`; `control-loop-taxonomy.md:60`; `example-control-loop.md:35-39`
    - Marks: shipped code, owner checked; 5 axes agree
    - Grade: high

28. **Ratchet tools that implement the dampener as a committed baseline** (confidence: high for ESLint and ast-grep, medium for Betterer and semgrep; axes A3, A6, A8, A10; C22)
    - ESLint bulk suppressions (v9.24.0): `eslint --suppress-all` writes `eslint-suppressions.json`; new violations report, old ones do not; fixing a suppressed violation exits non-zero until `--prune-suppressions` runs, so improvement must be committed; only `"error"` rules are suppressed (https://eslint.org/docs/latest/use/suppressions; vendor docs).
    - Betterer: `.betterer.results` committed; better updates the file, worse fails; `betterer ci` fails on any difference "whether results got better or worse"; stored character positions break across CRLF/LF checkouts (project docs; A6's half via search summary).
    - semgrep `--baseline-commit <hash>` reports only results not in that commit (vendor docs).
    - react-doctor `--baseline <report.json>`, `--scope changed` (a second lint pass on base content reports only introduced findings, degrading to a plain diff when the base is unreachable), and a finding identity that ignores file and line and treats duplicates as a multiset, so "an additional occurrence is still reported as introduced" (code, A3).
    - Marks: vendor and project docs plus code; 4 axes
    - Grade: high for ESLint, ast-grep, react-doctor; medium for Betterer, semgrep

29. **Compass's build fix loop already has a dampener against the actuator rewriting the sensor** (confidence: high; single axis A7)
    Before each fix cycle, `compass test-checkpoint verify` re-reads each checkpointed test's baseline with `git show <sha>:<path>` and classifies the current file by AST as `unchanged`, `added-only`, `modified` or `missing`, fixtures and `__init__` hashes included; `modified` is surfaced to the human before the cycle continues, and the builder may not edit checkpointed tests.
    - Evidence: `plugin/cli/commands/test_checkpoint.py:326-388, 803-838`; `plugin/skills/build/SKILL.md:42`; `plugin/templates/agents/builder.md:41`
    - Marks: code, read in full; 3 sites agree
    - Grade: high

### Step 3: Controller and control signal

30. **Controllers range from "first item in the sorted list" to an agent; the deterministic end is preferred and tuned over time** (confidence: high; axes A4, A1, A6, A10; C7)
    Simplest: "deterministically pick the first violation from the list. You can use bash and jq" (`[681s]-[686s]`). Lower risk: "use AST grep to find the smallest unmigrated procedure and always pick the smallest one" (`[686s]-[695s]`). Agentic is allowed but: "I don't think you should ever send an agent to do deterministic code's job, but you certainly can" (`[697s]-[711s]`, verified in the transcript; A10 had it only from a summary). The skill calls the controller "the part you will tune over time from loop output - start simple and expect to revise it", and names batch size and a scope gate (safe directories; exclude generated and vendored code) as controller knobs. Without a tuned controller "we might make too large of a change all at once, or ... the wrong change entirely" (`[494s]-[507s]`). Google independently reports that "LLM planning capabilities are often not needed and add a layer of complexity" (arXiv:2501.06972 §VIII).
    - Marks: practitioner talk plus shipped code, primary; Google experience report; 4 axes agree
    - Grade: high

31. **The control signal is a text file the controller writes and the workflow splices into the actuator's prompt, with no schema** (confidence: high; axes A4, A10; C8)
    The controller step writes `/tmp/controller-output.md`; the actuator step appends it under `## Selected work (controller output)`, followed by `## Agent Memory` (the feedback file). The prompt template says: "Work the target(s) the controller selected (see 'Selected work' if present); otherwise find high-confidence targets yourself", then "Keep this to one small, reviewable increment." Step size is a sentence plus a scope fence, never a number. The worked React Doctor loop has no separate controller; "fix up to 5 issues from those top 3 rules this run" lives in the actuator prompt.
    - Evidence: `workflow-template.yml:182-214`; `prompt-template.md:13`; `example-control-loop.md` "Controller"
    - Marks: shipped code, owner checked; 2 axes read it directly
    - Grade: high

32. **The talk's richer control signal carries the evidence behind the choice, so the actuator improves the code rather than migrating one to one** (confidence: high; axes A4, A10)
    Look at telemetry "and figure out which procedures have the most errors or the least instrumentation or has a gap in our APM", then "include not just the procedure to migrate, but also all the data about the things that we're trying to fix" (`[719s]-[745s]`), framed as optional ("if we want to get really clever"). Whether the talk names a vendor is a divergence (C9, see Divergent).
    - Marks: practitioner talk, primary
    - Grade: high

33. **Google's migration system: an imprecise finder, a plain control signal, and validation ordered cheap to expensive** (confidence: high; axes A10, A6)
    Finder: Kythe references up to distance five, regex categorizers bucket them into not-migrated, irrelevant, relevant, left-over; left-over goes to humans; they chose "an inaccurate yet practical approach" over AST or data-flow analysis. Signal: an instruction prompt, the full file, suggested line numbers as comments; fixed model, temperature 0, three attempts per file. Validation: success, whitespace-only, AST parse, "punt" (ask the LLM whether the change was needed), build, regression tests; any failure sends the file to manual. A nightly loop runs "until no left-over references remain". Result: 39 migrations, 595 changes, 74.45% of changes by the LLM, developer-estimated 50% time reduction. Hallucinations (reformatting, added comments, unrelated edits) were 25.55% of changes; developers started with small, localized IDs and moved to larger ones, which raised the LLM share.
    - Evidence: arXiv:2504.09691 §3.1-3.3, §4.3, Table 1 (FSE Companion 2025, PDF read)
    - Marks: peer-reviewed; not retracted; 1 source, one company, internal fine-tuned Gemini
    - Grade: high for mechanism and numbers as reported, medium for generalization

34. **Telemetry gives issue-level ranking; Sentry Seer is an existing ranker plus separable actuator** (confidence: medium; single axis A10)
    Sentry's organization issues endpoint sorts server-side by `freq`, `user`, `trends`, `recommended` and returns `count`, `userCount`, `culprit`, `seerFixabilityScore`; counts are per issue group, not per function (mapping to code runs through `culprit` or stack frames; negative finding, confidence low). Seer starts Autofix automatically at 10 or more events, seen in the last 14 days, with a high enough fixability score, and a settings ceiling ("Stop after Root Cause", "Stop after Plan", "Stop after PR Drafted"); at the code step it can hand root cause and plan to Claude Agent, Cursor or Copilot. PostHog sorts issues by occurrences, users, sessions; its HogQL query API shape and rate limits come from search summaries (confidence low-medium). No source defines a formula combining frequency, users and fix size.
    - Evidence: docs.sentry.io issues API and Seer pages; posthog.com docs and PR summaries
    - Marks: vendor docs, vendor interest; not code
    - Grade: medium for Sentry, low-medium for PostHog

35. **Leaf-first dependency ordering is common in repo-level translation, with a named weakness** (confidence: low-medium; single axis A10)
    AlphaTrans, ORBIT and a graph-RAG migration queue translate callees before callers; PtrTrans names "definition-use conflicts" because a unit cannot see its callers' usage; Super Library Agent adds callers and callees as context instead (arXiv:2410.24117, 2604.12048, 2609.12464, 2510.10956, 2608.29310). These are cross-language translation tasks; transfer to same-language refactors is untested.
    - Marks: one web-search summary, papers not opened; preprints 2024-2026
    - Grade: low-medium

### Step 4: Actuator

36. **The actuator is any CLI coding agent plus a repo-local skill, and the workflow, not the agent, commits and opens the PR** (confidence: high; axes A4, A1, A6, A9)
    "Our actuator is just an agent plus a skill ... bring your CLI coding agent of choice. You should spend a lot of time on the skill. Not all of that should be up front" (`[754s]-[765s]`). The agent writes a final response from a template; the workflow then "deterministically commit[s] and push[es] and create[s] a PR using the final message as our PR description" (`[785s]-[798s]`). The prompt tells the agent not to stop and ask for feedback (CI is non-interactive). In the worked React Doctor loop each issue gets fix, ignore (reason in config) or skip (leave for a human), and each fix is committed separately after typecheck, quality checks and a sensor re-run on staged files.
    - Evidence: transcript; `prompt-template.md:32`; `agent-runner-templates.md`; `example-control-loop.md`
    - Marks: practitioner talk plus shipped code, primary
    - Grade: high

37. **Golden patterns are hand-written idiomatic examples in the actuator skill; HumanLayer prescribes no format** (confidence: high; axes A4, A10, A5; C10)
    "We like to build out what we call golden patterns by hand before setting the agent loose ... because they're just pattern replicators and otherwise you're getting what's in the docs or what the agent knows from the internet" (`[765s]-[780s]`). The skill says only: ask whether existing patterns should be followed, inspect the code to find them, capture them in the actuator skill, move long examples to `references/`, and "keep one source of truth for each rule" across skill, prompt and memory file. The worked skill `narrow-react-prop-types` expresses them as before/after code pairs (`onRename?.(id, name)` becomes `onRename(id, name)`), a Core Requirements list, steps each with a completion criterion, a Review Checklist and an Anti-Patterns list. Dex describes the same technique without a tool: "Here's what good looks like. Here's what bad looks like. Go fix one thing and bring it back."
    - Evidence: `SKILL.md:72, 85-87`; `narrow-react-prop-types/SKILL.md:103-127, 161-180`; `skill-template.md:1-57`; Pragmatic Engineer `[2248s]-[2254s]`
    - Marks: shipped code, owner checked; talk and podcast; 3 sources agree
    - Grade: high

38. **Research on exemplars is indirect: curated examples help, similarity-retrieved code and generic context files do not reliably help** (confidence: medium; single axis A10; C11)
    Retrieved bug-fix demonstrations gave 76% exact match for assertion generation and 52% for repair (CEDAR, ICSE 2023, search summary). Retrieved "similar code" degraded repository-level generation by up to 15%, while in-context code and API information helped (arXiv:2503.20589, preprint). Repository context files "do not generally improve task success rates" and add over 20% inference cost; developer-written files are marginally positive, and files help for non-standard practices (arXiv:2602.11988; v1 said success "tends to reduce", v3 of 2026-09-29 softened it). No study tests hand-written exemplars inside an autonomous agent loop.
    - Marks: one peer-reviewed via summary, two preprints; the context-file headline moved between versions
    - Grade: medium for the context-file study, low-medium otherwise; low for "agents are pattern replicators" as tested fact

39. **Rule messages written as instructions are a practitioner channel to the actuator** (confidence: low-medium; axes A10, A6)
    Fiberplane: violations must be errors because "Warnings get completely ignored"; the ast-grep `message` is written as an instruction with a `note` holding bad and good code; agents in long sessions "start to ignore" CLAUDE.md conventions; an agent can write an ast-grep rule to ban a pattern immediately.
    - Evidence: dev.to/fiberplane/how-we-use-effect-and-ast-grep-to-make-our-codebase-work-better-with-agents-493j
    - Marks: grey literature, vendor-adjacent company blog; 1 source; consistent with ast-grep's `message` and `note` fields
    - Grade: low-medium

40. **A Compass subagent actuator meets `compass guard`; where its skill lives decides whether it survives update** (confidence: high; axes A9, A7, G3; C41)
    The guard denies, for every subagent, delete verbs, `git clean`, `git reset --hard`, `git checkout --`, force-push and a Write that empties a file; loops whose work is removing legacy code would meet it. G3 ran the guard and confirmed its scope is project-wide, not limited to `.compass/` (finding 119). HumanLayer places the actuator skill in `.claude/skills/<name>/`. A9 and A7 read that `_copy_tree_best_effort` empties the target before copying and left survival of non-shipped skills unverified; G3 ran `_apply` and found that only `.claude/cli/` is emptied, while user skill dirs survive (findings 113, 114). The disagreement is listed under Partial.
    - Evidence: `plugin/cli/commands/guard.py:6, 27-29, 181-225`; `plugin/cli/commands/self_update.py:143-170`
    - Marks: code read by A9 and A7; code read plus run experiment by G3
    - Grade: high

### Step 5: Loop and schedule

41. **One loop iteration per scheduled CI run, opening one small PR** (confidence: high; axes A4, A5, A6, A9; C12)
    "GitHub actions or your GitLab or your CircleCI ... it has access to your code, it has access to your secrets, and it has great dispatch and scheduling primitives. We don't need a new cluster for this." The workflow "runs a single iteration of the loop, sense, control, actuate, and creates a PR", scheduled "once a day": "every morning we walk into the office to a small incremental PR that's low risk" (`[801s]-[830s]`). Template triggers: `schedule` (cron `0 13 * * *`), `workflow_dispatch`, `issue_comment`; a per-loop `concurrency` group with `cancel-in-progress: true`; the PR is skipped when the agent made no commits. Each component must run locally before CI; the first CI run needs a temporary `push` trigger because a workflow cannot be dispatched before it has run once. Dex: triggers need not be cron (Sentry alert, support ticket, failing test).
    - Evidence: transcript; `workflow-template.yml:14-28, 173-253`; `SKILL.md:28, 95-107, 151-153`
    - Marks: practitioner talk plus shipped code, primary; 4 axes agree
    - Grade: high

42. **GitHub Actions carries constraints a loop must design around** (confidence: high; axes A8, A9)
    Cron is 5-field POSIX in UTC, minimum 5 minutes, runs only from the default branch, may be delayed or dropped near the top of the hour; public-repo schedules are disabled after 60 days without repository activity. Commits pushed with the default `GITHUB_TOKEN` do not trigger workflows, so CI gates may not run on an agent's pushes without an app token. Claude Code Action rejects bot actors unless listed in `allowed_bots`, "which keeps bots from triggering Claude in a loop", and its docs recommend `--max-turns`, workflow timeouts and concurrency to limit cost. Concurrency allows one running run per group; pending-run semantics were read by A8 (one pending by default, `queue: max` up to 100) and left unverified by A9.
    - Evidence: https://docs.github.com/en/actions/using-jobs/using-concurrency; events-that-trigger-workflows; https://code.claude.com/docs/en/github-actions
    - Marks: vendor docs; 2 axes
    - Grade: high

43. **Claude Code's own scheduling surfaces differ in where they run and how they fail** (confidence: high; axes A5, A8, A9; C34)
    - `/loop` and in-session cron: session-scoped, 50 tasks per session, recurring tasks expire after 7 days ("bounds how long a forgotten loop can run"), 1-minute minimum, jitter, fires only while idle, no catch-up; bare `/loop` runs a maintenance prompt that "does not start new initiatives"; `.claude/loop.md` holds the default prompt (truncated past 25,000 bytes).
    - Desktop scheduled tasks: local files and MCP config, 1-minute minimum, fire only while the app runs and the machine is awake, one catch-up run for the most recent miss within 7 days, a run history recording skipped runs with the reason, per-task permission mode (a manual-mode task stalls on an unapproved tool).
    - Cloud routines (research preview): fresh clone without local files, 1-hour minimum, 100 scheduled runs per hour per account, account-owned and not repo-tracked, branches prefixed `claude/`, green status "means session started", not task success.
    - Evidence: https://code.claude.com/docs/en/scheduled-tasks; desktop-scheduled-tasks; routines
    - Marks: vendor docs; 3 axes agree
    - Grade: high for current behavior, medium for durability of routines

44. **Temporal treats a schedule as its own entity with overlap and catch-up policy** (confidence: high; single axis A9)
    Overlap policies: Skip (default), BufferOne, BufferAll, CancelOther, TerminateOther, AllowAll; catch-up window default one year; a failed run pauses the schedule; backfill replays missed actions. A9 compares HumanLayer's one-open-PR gate to Skip.
    - Evidence: https://docs.temporal.io/schedule
    - Marks: vendor docs; 1 source
    - Grade: high

45. **Compass has no wall-clock scheduler; its loops are driven by hooks and turns** (confidence: medium; axes A9, A7; C24)
    Stop runs `capture-check` each turn, SubagentStop and TeammateIdle run `capture-signal`, SessionStart runs `self-update`. A grep for cron and schedule across `plugin/` returned nothing relevant.
    - Evidence: `plugin/hooks/hooks.json`; grep results
    - Marks: code search, negative result
    - Grade: medium

### Step 6: Human on the loop

46. **The feedback file exists because the first loop was turned off for being too hard to steer** (confidence: high; axes A4, A1, A5, A8, A9, A10; C13)
    The first version "was actually really frustrating and we turned [the] loop off" because correcting it meant checking out the branch, changing the skill and the code, committing and pushing (`[831s]-[846s]`). Fix: "a feedback file that's tracked in version control just as a markdown file ... deterministically load it into our actuator agent's context every time that it runs after we run the controller" (`[853s]-[863s]`). On a `/iterate` PR comment, the workflow loads the PR, diff, comments and description and tells the agent "to fix the code, but also to update that feedback file"; being in version control, "you can see how you've changed it over time, you can revert it".
    - Marks: practitioner talk plus shipped code, primary; 6 axes agree
    - Grade: high

47. **The feedback file's format, routing and editing rules** (confidence: high; axes A4, A10)
    Template: `# Agent Memory: <Task Title>`, one paragraph stating it is "the human-on-the-loop steering channel ... loaded into the actuator on every run (after the controller) ... Keep durable guidance only - not one-off instructions or single-run logs", then a `## Guidance` bullet list; path `.github/agent-memory/<task-slug>.md`. Good entries: "permanent scope exclusions, known false-positive areas, and reviewer feedback that should change future selections". Routing: a hidden PR-body marker `<!-- codelayer-agent:workflow=<id>;memory=<path>;version=1 -->`; the workflow no-ops before checkout unless the marker matches; commenters must be OWNER, MEMBER or COLLABORATOR. The iteration prompt says "If the feedback is only PR-specific, update the PR but do not add it to memory."
    - Evidence: `memory-template.md:1-7`; `SKILL.md:129-132`; `agent-iteration.ts:41-110`; `workflow-template.yml:34-42, 71-84`
    - Marks: shipped code, owner checked; 3 sources agree
    - Grade: high

48. **Across tools, steering state lives outside the model, in files** (confidence: high; axes A8, A4, A9; C40)
    Claude Code: edits to `.claude/loop.md` apply on the next iteration; `/goal` replaces or clears the condition; Ralph keeps its iteration counter in `.claude/ralph-loop.local.md`; `claude attach|logs|stop` manage background sessions. HumanLayer: the memory file and `/iterate`. Huntley's Ralph: the human adds "signs" to the prompt after repeated mistakes.
    - Evidence: https://code.claude.com/docs/en/scheduled-tasks, /goal, cli-reference; HumanLayer skill; https://ghuntley.com/ralph/
    - Marks: vendor docs, skill code, practitioner blog; 4 independent sources show the pattern
    - Grade: high

49. **Compass steers by gates and pauses only; no human-edited file steers an actuator between runs** (confidence: medium; axes A7, A9; C25)
    Prior art has two modes: between-run standing feedback (HumanLayer's memory file) and in-run pause and resume (LangGraph `interrupt()` with a checkpointer; the node re-executes, so it must be idempotent). Compass has the second: spec and plan gates, the build fix prompt "yes / skip / abort", the 7c phase pause, autopilot's checkpoints, the context-stop accept-or-decline. A grep for a persistent steering file read into an actuator found none; nearest are overlays in `.compass/meta/local/` (text appended to shipped agents) and `meta/capture.json`. The capture loop is hidden from the human by design ("Tell the human nothing: the ledger holds the result").
    - Evidence: `plugin/skills/build/SKILL.md:42, 78`; `plugin/skills/autopilot/SKILL.md:38-45`; `plugin/cli/commands/capture_check.py:122-124`; `plugin/cli/commands/overlay.py:1-30`; `langgraph/types.py:833-925`
    - Marks: code plus absence search
    - Grade: high for facts, medium for the mapping

50. **HumanLayer's own failure story: unattended agents could not maintain code quality** (confidence: high for the quotes, medium for incident details; single axis A4)
    In July 2025 HumanLayer "went full lights-off"; an issue arose the agent could not solve and they had to "dig into the codebase you stopped reading three months ago"; "by the ~third time in november, we decided it would be easier to rewrite from scratch". Thesis: models "can't maintain and improve codebase quality over time, not without a decent amount of human steering". Mistele: "we can design loops and still read the code"; humans review every loop PR in both accounts.
    - Evidence: Dex essay `wsff.md:209-230` (`humanlayer/advanced-context-engineering-for-coding-agents` at `da16ab7`); Dex talk YouTube `Ib5GBkD555M` `[496s]-[529s]`; Mistele `[252s]-[260s]`
    - Marks: practitioner essay, talk and podcast, primary; Dex states his own vendor bias; 3 sources agree
    - Grade: high for what HumanLayer does, low as evidence the approach generalizes

### Step 7: Flow control, caps and safety

51. **Flow control is a WIP limit of one open PR per loop, checked before checkout** (confidence: high; axes A4, A1, A5, A8, A9, A10; C14)
    Motivation: when the team was away for a week, "the PRs from all of our loops would just stack up. They duplicate work. They'd conflict" (`[910s]-[937s]`). Before checkout, the workflow checks for an open PR with the loop's label and shuts down if one exists, because "no human reviewed the last output, so there's no reason to stack up even more work for humans to review" (`[944s]-[978s]`). Code: `gh pr list --state open --label "$AGENT_LABEL" --limit 1`; the gate applies to `schedule` and `workflow_call` only, so manual dispatch bypasses it. This limits PRs in progress, not run rate. Speed-ups once trusted: pick 3 or 5 targets per run, each in its own implementation phase and context window, or run four times and give each PR to a different teammate; at one procedure a day, 150 procedures "is going to take 6 months". A8 reads the speed-ups as conflicting with the one-PR bound, unresolved in the talk.
    - Evidence: transcript `[910s]-[1013s]`; `workflow-template.yml:55-63, 251-253`; `SKILL.md:140-143, 155`
    - Marks: practitioner talk plus shipped code, primary; 6 axes agree
    - Grade: high

52. **Human review capacity is the binding limit on how fast a loop may run** (confidence: high; axes A4, A6, A8; C16)
    Google: "the bottleneck was the speed at which engineers could review", so "we purposefully limited the number of changes we generate every week"; Joda-time chunks started only in directories with reviewers ready (arXiv:2501.06972 §V-VI, self-reported). Little's law (cycle time = WIP / throughput) and Reinertsen's flow principles (control queue size, match WIP to the rate work goes out) give the theory, read through secondary summaries.
    - Marks: practitioner talk, Google experience report, secondary summaries of a 1961 theorem and a 2009 book; 3 axes agree
    - Grade: high for the practitioner evidence, medium for the theory (primary texts unread)

53. **HumanLayer's skill leaves stop conditions, budgets and rollback uncovered** (confidence: high; axes A1, A8; C15)
    The skill never uses "oscillation", "deadband", "stabilization" or "ratchet". The talk calls the approach "really expensive if you don't work at a frontier lab" and offers no budget mechanism; rollback is mentioned only for the feedback file. 12-factor-agents, also HumanLayer's, has no control-theory content, but factor 9 breaks the loop after 3 consecutive errors and escalates to a human, and factor 10 keeps agents to "3-10, maybe 20 steps max".
    - Evidence: `SKILL.md`; ai.engineer talk page summary; `12-factor-agents/content/factor-09-compact-errors.md:31-62`, `factor-10-small-focused-agents.md:9`
    - Marks: shipped code and docs, owner checked
    - Grade: high

54. **Claude Code's stop mechanics: a Stop-hook circuit breaker of 8, and two kinds of iteration cap** (confidence: high; axes A8, A3)
    A Stop hook can force continuation with exit code 2 or `{"decision":"block"}`; Claude Code overrides it "after it blocks eight times in a row with no tool call from Claude in between". Scripts should read `stop_hook_active` and exit 0 when true; react-doctor's hook does so and caps Cursor continuations at 1. `/goal` evaluates after each turn with a small model (met, not met, impossible), and any turn or time bound is condition text judged by that model; the Ralph plugin's `--max-iterations` is a numeric counter in a state file, deleted when reached, and a corrupt state file ends the loop.
    - Evidence: https://code.claude.com/docs/en/hooks-guide, /hooks, /goal; `anthropics/claude-plugins-official` `plugins/ralph-loop/hooks/stop-hook.sh` (summarizing fetch); react-doctor `install-agent-hooks.ts:236-362`
    - Marks: vendor docs; official plugin code via summary; react-doctor code
    - Grade: high

55. **Unattended permission postures and hook loading in headless runs** (confidence: high; single axis A8, plus A5 for one bug)
    `--permission-prompts none` denies anything that would prompt; `dontAsk` is the documented locked-down CI mode; `bypassPermissions` requires a sandbox and cannot run as root; auto mode pauses after 3 blocks in a row or 20 total, and in `-p` the calls that would still prompt are denied. `--bare` skips hooks, skills, plugins, MCP and CLAUDE.md; without it, `-p` runs project hooks and `.mcp.json` servers "even in a folder you've never trusted", so a Stop-hook breaker depends on hooks loading. `claude -p` waits up to 10 minutes on background work by default. An open, single-reporter issue says headless runs from Windows Task Scheduler may be denied allow-listed tools, attributed by the reporter to the auto-mode classifier (anthropics/claude-code#99795; confidence low).
    - Evidence: https://code.claude.com/docs/en/headless, /permission-modes
    - Marks: vendor docs, 3 pages agree; community issue unconfirmed by maintainers
    - Grade: high for docs, low for the issue

56. **Bots and hosted agents ship WIP limits as numeric defaults** (confidence: medium; axes A6, A8, A9)
    Dependabot `open-pull-requests-limit` default 5 (security updates a separate limit of 10), grouped updates count as one, `cooldown` withholds PRs after a release. Renovate `prConcurrentLimit` 10, `prHourlyLimit` 2 (read from source by A9), `minimumReleaseAge` (a dampener-like wait), `automerge` false, `automergeType: pr` merges only branches "up-to-date and green"; lowering a limit does nothing until existing PRs close. Copilot cloud agent: one PR per task, 59-minute sessions, cannot approve or merge, workflows wait for a write-access human. Jules and Devin quotas come from third-party pages (low).
    - Evidence: docs.github.com Dependabot options; docs.renovatebot.com and `lib/config/options/index.ts`; docs.github.com Copilot coding agent
    - Marks: vendor docs and source; 3 axes
    - Grade: high for Dependabot, Renovate, Copilot; low for Jules, Devin

57. **Revert-on-break appears as a stability device, but only in two sources and none post-merge** (confidence: medium; axes A6, A8; C38)
    Karpathy's autoresearch keeps a commit only on strict improvement of the metric and runs `git reset HEAD~1` on equal or worse, on crash, or past a 10-minute budget. EvoC2Rust swaps translated modules into a compiling skeleton one at a time and reverts any module that breaks compilation. No source covers automated post-merge revert for agent loops.
    - Evidence: https://github.com/karpathy/autoresearch (search summary); arXiv:2508.04295 (search summary)
    - Marks: code repo via summary plus secondary write-up; preprint via summary
    - Grade: medium

58. **Failure has signatures a loop could sense: repetition and state-trace features** (confidence: low-medium; axes A8, A11; C39)
    A length-10 repetitive action sequence corresponds to an 89% chance of failure (SWE-smith, arXiv:2504.21798); failed trajectories run 12 to 82% longer than successful ones (arXiv:2511.00197); a compact FSM fitted to traces from twelve datasets predicts failure at AUROC up to 0.94 and supports online early stopping (arXiv:2608.23670). Fixes that only cut repetition did not raise resolve rates.
    - Marks: preprints, single-benchmark settings, older model generations; via search summaries and abstracts
    - Grade: low-medium

59. **Blind loops versus incremental loops** (confidence: medium; axes A4, A8)
    Huntley's original Ralph is `while :; do cat PROMPT.md | claude-code ; done`, with no stop condition; safety is "backpressure" (types, tests, static analyzers) and a human re-planning when it "goes completely off track"; Huntley would not use it on existing codebases. Mistele: blind loops yield "40,000 line PRs that just nobody wants to read"; "the best Ralphs are actually applying control theory".
    - Evidence: https://ghuntley.com/ralph/ (2025-07-14); transcript `[44s]-[91s]`, `[399s]-[425s]`
    - Marks: practitioner blog and talk; opinion, not measured
    - Grade: medium

109. **Claude Code cloud routines cap run counts per hour, never dollars per day** (confidence: high; single axis G1)
    Scheduled runs: 100 per hour per account (waits at the limit); run-now, API and one-off re-arm: 30 per hour per routine, 100 per account (fails at the limit); "None of these hourly limits has overage". Runs draw down subscription usage like interactive sessions; past the limit, orgs with usage credits continue metered, others are rejected until the window resets.
    - Evidence: https://code.claude.com/docs/en/routines (Usage and limits)
    - Marks: vendor docs, research preview; 1 page
    - Grade: high

110. **Anthropic spend limits are windowed or monthly: seat allowances on rolling five-hour and weekly windows, monthly API org, workspace and Claude Code per-user caps** (confidence: high; single axis G1)
    claude.ai plans: per-seat allowance on five-hour and weekly windows, then optional usage-credit limits per organization, group or member; `/usage` shows a Loops row with per-task token totals. API: monthly tier caps (Start \$500, Build \$1,000, Scale \$200,000), an optional lower org limit (HTTP 400), the tier cap returning 429 `enforced_spend_limit_reached`; workspace limits are monthly; the Claude Code workspace is the only one with per-user monthly limits. No daily period is offered.
    - Evidence: https://code.claude.com/docs/en/costs; https://platform.claude.com/docs/en/api/rate-limits; https://platform.claude.com/docs/en/manage-claude/workspaces
    - Marks: vendor docs; 3 pages agree
    - Grade: high

111. **Other agent products bound spend monthly, per session or per cycle; only Jules uses a rolling daily unit, and it counts tasks** (confidence: medium; single axis G1)
    - OpenAI: monthly hard limits per organization and project, 429 `organization_spend_limit_exceeded` or `project_spend_limit_exceeded`, enforcement "not instantaneous"; page fetch trimmed, Help Center reported to still describe soft limits (grade medium-high).
    - Devin: ACU limits per session (`max_acu_limit`, behavior at the cap undocumented), per user per month, per organization per cycle; a session is blocked if any applicable limit is reached (grade high for read pages).
    - Cursor cloud agents: API pricing, spend limit requested at first use, monthly, enforcement not instant; per-member limits Enterprise-only; sources conflict on whether a team limit blocks every member (grade medium).
    - GitHub Copilot cloud agent (legacy premium-request billing): one premium request per session; budgets alert at 75, 90 and 100% and are never described as blocking; the June 2026 AI Credits model rests on third-party summaries (grade high legacy, low credits).
    - Jules: 15 / 100 / 300 tasks per rolling 24 hours and 3 / 15 / 60 concurrent, per user, not pooled (grade high).
    - Evidence: developers.openai.com spend-limits; docs.devin.ai usage-policies and v1 sessions; cursor.com/docs/cloud-agent; docs.github.com Copilot premium requests; jules.google/docs/usage-limits
    - Marks: vendor docs, some via search summaries; contradictions listed below

112. **No product read offers a per-day dollar cap or a per-loop or per-repo budget; a loop budget is summed outside the product from per-run records** (confidence: medium; single axis G1)
    Per-run bounds are a session, task or invocation: `--max-budget-usd`, `--max-turns`, Devin `max_acu_limit`, one Copilot premium request per session. Routines scope by repository and branch permission, not spend. For Claude Code the per-run records are `total_cost_usd` in each result (finding 10) and the transcript's `cost-state` records (finding 90).
    - Marks: synthesis over findings 87 to 89, 109 to 111; bounded absence across 7 vendors' docs, not every feature
    - Grade: medium

### FSMs

60. **No source formalizes "every control loop is also an FSM"; the theory supports FSM models of controllers, with a documented counter-stance** (confidence: medium; single axis A11; C30)
    Supervisory control models the plant as a discrete-event automaton; a supervisor acts only by disabling controllable events, a specification is realizable iff it is controllable, and nonblocking (a done state stays reachable) is a separate property (Ramadge and Wonham 1987, doi 10.1137/0325013, about 3,346 citations, read through secondary summaries). Hybrid automata couple a finite control graph with continuous flow in each state, the formal bridge between a continuous error signal and a mode machine (Henzinger, LICS 1996, abstract). Statecharts add hierarchy, concurrency and broadcast (Harel 1987, about 6,756 citations). Counter-stance: Kubernetes API conventions say conditions "are observations and not, themselves, state machines", the system is "level-based rather than edge-triggered", and `phase` "was essentially a state-machine enumeration field, that contradicted system-design principles" (`api-conventions.md:484-499`). Behavior trees are claimed to generalize FSMs and scale better (robotics literature, abstracts).
    - Marks: peer-reviewed classics read second-hand or at abstract level; Kubernetes spec repo read raw
    - Grade: high for the classics' standing, medium for the Kubernetes stance (one ecosystem)

61. **LLM agents built as explicit FSMs: reported gains and a counter-result** (confidence: medium; single axis A11, plus A6; C29)
    StateFlow separates states and transitions from in-state actions: +13% success at 5x less cost on InterCode SQL, +28% at 3x less on ALFWorld vs ReAct (arXiv:2403.11322, COLM 2024). HEXIS compiles SKILL.md files into extended FSMs with transition guards: +16.2 points over Skill+ReAct and 38.4 to 88.9% fewer tokens (arXiv:2609.30123, weeks-old single-author preprint). A deterministic blueprint where the LLM "never [decides] the workflow's path": 35.56% vs 18.00% on TravelPlanner (arXiv:2508.02721). Airbnb's migration used a per-file state machine whose steps are both unit of work and sensor (A6, finding 79). Counter: an imperative phase state machine's "brittleness does not reliably improve task success or compliance" against a skill-reading agent, with retrieval the dominant bottleneck (arXiv:2606.06923).
    - Marks: one peer-reviewed, the rest preprints, all from abstracts; benchmark tasks
    - Grade: medium for StateFlow, low for the rest

62. **Guards on transitions prevent unsafe actions but do not guarantee safe completion** (confidence: medium; single axis A11)
    AgentSpec rules (trigger, predicate, enforcement: terminate, ask user, corrective call) prevented over 90% of unsafe code executions with millisecond overhead (arXiv:2503.18666, ICSE 2026). On tau-bench with two small models, mediation intercepted up to 94% of non-compliant actions while safe success stayed below 5% and recovery after a block ranged from 21% to near zero (arXiv:2603.19328, preprint). A blocked transition needs a defined recovery state.
    - Marks: one peer-reviewed, one preprint, abstracts
    - Grade: medium and low

63. **FSM frameworks give resumability, guards, step caps and path generation in code** (confidence: high; axes A11, A9)
    LangGraph: conditional edges, checkpoints with per-node `versions_seen`, `interrupt_before`/`interrupt_after`, and `GraphRecursionError` when the configurable `recursion_limit` is exhausted (default 1000). XState: a pure `transition(logic, snapshot, event)`, guards on transitions, snapshot status `active | done | error | stopped`, persisted and restored snapshots, a `graph` package that generates paths and a test model. Temporal: durable execution by replaying an event history, so workflow code must be deterministic (LLM calls belong in activities, an inference). 12-factor factor 8: own the loop, save the thread and `break` on async or high-stakes intents. No measured effect of any framework on LLM-agent reliability was found.
    - Evidence: `langgraph/graph/state.py:982, 1183-1264`, `errors.py:68-72` at `0870f5e`; XState `packages/core/src/{types,State,createActor,transition}.ts` at `6a85c40`; docs.temporal.io/workflow-execution
    - Marks: code, owner checked; Temporal docs via summary
    - Grade: high for mechanisms

64. **Compass already persists FSM state two ways, and its capture loop is an explicit FSM** (confidence: high; axes A7, A9, A11; C27)
    Pattern 1: a `status:` field in frontmatter (`draft -> review -> approved -> active -> done -> archived`, each transition with an owner; review to approved is human-only). Pattern 2: a JSON state file plus an append-only JSONL ledger. Capture per opportunity: none open, open with worker live, respawned (attempts 0 to 2), quiet, block, closed or abandoned; transitions guarded by arithmetic (`due()` is pure); the current rung is recomputed from the latest ledger row, so state survives across sessions and detached processes. `compass clone` writes `run.json` with a closed status vocabulary and `finished_at` null while running. Handoff resume classifies entry into clean, diverged, incomplete or stale. Compass has no named "throttled" or "sensing" state.
    - Evidence: `plugin/cli/commands/capture_check.py:1-52, 88, 225-395`; `plugin/cli/capturelib.py:46-58, 242-262, 291, 373`; `plugin/cli/commands/clone.py:24-37, 410-503`; `plugin/skills/methodology/SKILL.md` status table; `plugin/skills/handoff/SKILL.md:125-138`
    - Marks: code, owner checked; 3 axes agree
    - Grade: high

### Compass's own loops today

65. **Eight loops run today, each with a setpoint, sensor, controller, actuator, stop and weak spot** (confidence: high; axis A7, with A9 and A11 agreeing on the shared rows)
    | Loop | Setpoint | Sensor | Controller | Actuator | Stop | Weak spot |
    |---|---|---|---|---|---|---|
    | Build fix loop | suite green outside `open-ids` | tester run plus `test-checkpoint verify` | orchestrator LLM | same builder via SendMessage | 3 cycles per task | cycle count only in prose; no progress or cost sensor |
    | Capture | none stated | turn counter and signals; anti-list judge | `due()` arithmetic | detached headless `claude -p` | `capture-close`; 2 attempts; abandon at 900 s | no outcome sensor on lesson value; no cost log |
    | Context stop | usage under 80%, then 95% | transcript token usage | threshold compare | `continue:false` plus message | once per level | no usage history |
    | Rolling-wave elaboration | `## Later` empty at completion | `compass coverage --strict` | orchestrator LLM at step 7d | edits plan, moves task ids | strict gate | elaboration correctness unmeasured |
    | Self-update | installed sha = remote HEAD | `git ls-remote` | sha compare, 1-hour floor | file copy, settings merge | sha equal or error | no post-apply health check, no rollback |
    | Autopilot | task through the pipeline | agent reports; validator verdict | orchestrator LLM | spawns agents | two human checkpoints, L+ exit | research respawn unbounded; no cost cap |
    | Clone-old | feature sessions harvested | `sessions list`, clone status; lesson-write judge | skill steps | `compass clone` workers | `--max N`, per-clone timeout | clone log has no reader, so reruns re-clone |
    | Sizing log | none (record only) | none | `make-unit`/`promote`, self-update flatten | file moves | n/a | correction rate has no denominator |
    - Evidence: A7 findings 1 to 22, each with `file:line`
    - Marks: code read in full; autopilot and rolling-wave from skill text only (no Python controller)
    - Grade: high

66. **The fix loop's cap lives in prose and its sensor cannot tell progress from regression** (confidence: high; axes A7, A9, A11; C28)
    "Max 3 cycles per task, then escalate" appears in `build/SKILL.md:42`, the pipeline rule, and as "max 3 iterations" for validator re-review; no Python counts cycles (only a hand-written `fix_loop_cycles` in `phase-summary.yaml`). No sensor compares the failing set between cycle N and N-1, so a cycle that makes things worse looks the same to the stop rule as one that makes them better. A plan with many tasks has no total cap. The setpoint itself moves when a checkpoint lands (`test_checkpoint.py:861-891`).
    - Marks: code plus exact grep for absences
    - Grade: high

67. **The capture loop is the most instrumented loop, and its outcome never feeds back** (confidence: high for counts, low as a quality reading; single axis A7)
    Over `.compass/tmp/capture-log.jsonl` (812 rows, 2026-08-06 to 2026-10-18): 80 opened and fired, 538 skipped (all "below interval"), 57 worker-started, 55 finished, 2 failed; written in 43 of 80; 61 written, 213 rejected, 14 recurrence, 1 revised; worker median 175 s, max 533 s. `fire_rate` is 100% by construction (it measures "closed"). Tunables (`interval` 12, `max_reemits` 3, abandon 900 s, grace 600 s, 24-hour no-headless latch) are static; nothing reads lesson value (`retrieval-log.jsonl`, `lesson-coverage`) back into `due()` or `interval`. Runaway guards: `COMPASS_WORKER_SESSION` stops self-triggering, two lock files, bounded retries, signals capped at 50. Whether the worker's json envelope holds `total_cost_usd` is unverified; only the `extracted:` line is read.
    - Evidence: `plugin/cli/capturelib.py:35-42, 62-65, 109-137, 291-318`; `plugin/cli/commands/capture_check.py:71-88, 225-449`; `plugin/cli/commands/capture_worker.py:213-350`
    - Marks: code plus counts over one vault's log
    - Grade: high for mechanism, medium for counts

68. **Every Compass loop that acts unwatched is bounded by counts or timers, none by cost** (confidence: medium; axes A7, A9, A11; C23)
    Capture: attempts, re-emits, abandon timer, latch, lock. Fix loop: 3 cycles. Clone: `--max` and timeout. Context: one stop per level. Self-update: 1-hour floor. A grep for `cost|budget` in `plugin/cli/commands` finds `cost_usd` only in `clone.py`, recorded per clone and never summed against a budget.
    - Marks: code plus absence search over one directory
    - Grade: medium

69. **Deterministic sensors decide when; models decide what and whether it was good** (confidence: medium; single axis A7)
    Capture due, context level, sha compare, checkpoint verify and the active-task sweep are deterministic. The anti-list, step 7d elaboration, the validator verdict and lesson-write dedup are model judgments. Only the fix loop pairs a model-judged action with a deterministic quality reading of its result.
    - Marks: synthesis over A7's audited loops
    - Grade: medium

70. **Other weak spots found in code** (confidence: high on code facts, low where noted; single axis A7)
    Self-update has no health check or rollback, swallows per-file copy failures, and empties targets before copying. Autopilot's "If research is thin, spawn another researcher" has no bound or definition of thin. Clone-old's `meta/clone-log.jsonl` has a writer and no reader, and is absent in this vault although `clone` ran twice (cause unknown). The sizing log shows 25 decisions, 4 corrections (all 2026-08-30, flattening born-folder specs), and prints that "0 corrections is uninterpretable without the audit denominator". `promote` and self-update's flatten can in principle flip a spec back and forth (inferred from two readings, untested, confidence low). Context-check passes every failure silently and assumes a 1M window for unknown models.
    - Evidence: `self_update.py:145-170, 299-342`; `autopilot/SKILL.md:32`; `clone.py:449-464`; `sizing.py:299-304`; `context_check.py:131, 306-312`
    - Marks: code; absence by grep and filesystem check
    - Grade: high, low for the flip-flop

71. **Measurements Compass already records, usable as sensor inputs** (confidence: high for writer and reader, medium for current state; single axis A7)
    | Record | Writer | Reader | Usable fields |
    |---|---|---|---|
    | `meta/usage.yaml` | every CLI dispatch | `usage`, `doctor` | count and last date per command |
    | `tmp/capture-log.jsonl` | capturelib, worker | `capture-stats`, `doctor`, capture-check | event, triggers, written/rejected/revised counts |
    | `tmp/retrieval-log.jsonl` | `compass lessons` | none found | query, surfaced files |
    | `meta/sizing-log.yaml` | `make-unit`, `promote`, `demote`, self-update | `sizing stats` | action, shape, by, reason |
    | `meta/clone-log.jsonl` and `run.json` | `clone`, `sessions record` | clone-old step 4 only | status, `cost_usd`, lessons merged |
    | `tmp/test-checkpoints/TASK-NNN.json` | `test-checkpoint` | `verify`, `open-ids` | hashes, test ids, landed |
    | `tmp/phase-reports/*/phase-summary.yaml` | orchestrator by hand | capture-check, extract-lessons | fix-loop cycles, deviations, debug invocations |
    | `tmp/context-state.json` | context-check | context-check | highest level offered per session |
    | Claude Code transcripts | Claude Code | `sessions`, `context-check`, `clone` | per-message token usage, model, commits |
    - Evidence: A7 finding 23 with writer and reader `file:line`
    - Marks: code located by grep and reading, plus a filesystem snapshot
    - Grade: high

72. **Compass already holds the primitives HumanLayer's later steps need, except a scheduler and a steering file** (confidence: high; axes A9, A7; C26)
    Headless actuator: the capture worker runs `claude -p ... --output-format json --allowedTools ...` with stdin closed, an env marker, a per-run log and a `no-headless` failure class; its model resolves through the model policy table. Flow control: one worker per vault by lock, bounded retries, the fix-loop cap, file exclusivity for parallel builders, autopilot's L+ exit. Config formats a loop definition could reuse: `meta/capture.json`, `meta/models.yaml`, `sources.yaml`, overlays. [[specs/pipeline/SPEC-009-configurable-pipeline-workflows]] is the nearest home for flow-as-data but is a deferred draft modeling one-pass phases, not repeating cycles; whether a loop is a workflow, a phase or a new artifact type is undecided. Where a loop's files can live today is in findings 113 to 123.
    - Evidence: `plugin/cli/commands/capture_worker.py:22-35, 301-321`; `plugin/cli/modelslib.py:1-12`; `.compass/specs/pipeline/SPEC-009-configurable-pipeline-workflows.md:11, 43, 74-88`; `plugin/cli/commands/coverage.py:66-82`
    - Marks: code and first-party spec; 2 axes
    - Grade: high

### Where a loop lives in a Compass project

All findings in this section are G3's, from code read plus `self_update._apply` and `guard.decide` run in a scratch project at `eadad7f` (single axis unless noted).

113. **Update never deletes a user-authored agent, rule, command or skill dir; it overwrites same-named shipped files** (confidence: high; G3)
    `_apply` copies shipped agents, rules and commands file by file with no deletion pass, and for each shipped skill dir copies only its top-level `*.md`; the only removal is the named `RETIRED_SKILLS` list. A user `.claude/skills/my-loop/` with `SKILL.md`, a script, a `golden/` folder and refs, a user agent, rule, command and hook file all survived. A user-edited `builder.md` was replaced; user extras inside the shipped `research` skill dir survived; a user skill that later collides with a newly shipped name loses its same-named `*.md`. dsh materialization removes only `compass-*` dirs no longer shipped.
    - Evidence: `plugin/cli/commands/self_update.py:43-46, 234-256`; `plugin/skills/update/SKILL.md:41-54`; `plugin/cli/tests/test_self_update.py:233-244`; `plugin/cli/hostlib.py:146-180`
    - Marks: code read plus run experiment; 3 sources agree
    - Grade: high

114. **`.claude/cli/` is emptied and replaced on every update, so a sensor script placed there is deleted** (confidence: high; G3; C41)
    `_copy_tree_best_effort(src/cli, .claude/cli)` unlinks or removes every destination entry before copying; `.claude/cli/my_sensor.py` was missing after `_apply`. The manual skill runs `rm -rf .claude/cli`. This is the only emptied target.
    - Evidence: `self_update.py:145-170, 257`; `plugin/skills/update/SKILL.md:56-58`
    - Marks: code read plus run experiment; 3 sources agree
    - Grade: high

115. **Hook registration replaces only groups that run a shipped command or Compass's CLI; a user's own hook survives even when it mentions "compass"** (confidence: high; G3 plus code read at consolidation)
    `merge_settings` treats a group as Compass-owned when any of its hooks runs a command the manifest ships or matches `.claude/cli/compass` or `$CLAUDE_PLUGIN_ROOT/cli/compass`; every other group and top-level key is kept. A test pins that `python3 tools/compass_report.py`, `echo compass` and paths containing `compass` survive while stale Compass CLI commands are replaced. A group mixing a Compass CLI command with a user command is replaced whole. The manual `/compass:update` skill still drops any group whose command contains the substring `compass` (see Contradictions).
    - Evidence: `self_update.py:174-211, 237`; `test_self_update.py:363-395`; `plugin/skills/update/SKILL.md:125-129, 158`
    - Marks: code read and test read; G3's run showed the earlier substring rule, since replaced in `self_update.py`
    - Grade: high

116. **`compass overlay` appends `*.md` addenda to existing targets and creates nothing** (confidence: high; G3)
    `.compass/meta/local/{agents,rules}/<name>.md` and `skills/<name>.md` append to the matching `.claude/` file after the refresh; a missing target is reported ORPHAN and skipped. A user-authored skill can be a target. Scripts, subfolders and golden-pattern folders cannot be overlaid. ADR-020 D-06 scopes whole new local files out because local-only skills already survive.
    - Evidence: `plugin/cli/commands/overlay.py:33-84`; `self_update.py:278-285`; [[ADR-020-local-overlays-appended-after-refresh]] D-01, D-05, D-06
    - Marks: code read plus run experiment
    - Grade: high

117. **`.compass/meta/` is untouched by update except `plugin.yaml` and invisible to the vault scanner; a new root folder is unclassified unless its index declares `type: unit`** (confidence: high; G3)
    `.compass/meta/loops/migrate.md` survived update; `NON_TYPE_DIRS` skips `meta`, `tmp`, `archive`, `.annotations`, so files there are neither artifacts nor validated. A `.compass/loops/` folder without a marker returned `unclassified` and draws `unclassified_root_folder` from validate (warning text read, not executed). No `loop` artifact type exists.
    - Evidence: `self_update.py:66-89, 418-427`; `plugin/cli/vaultlib.py:14-82`; `plugin/cli/commands/validate.py:13, 215`
    - Marks: code read plus run experiment; 3 sources agree
    - Grade: high

118. **`.claude/` is not durable in every project; `.compass/` is version-controlled wherever the project tracks it** (confidence: medium; G3)
    ADR-020 D-01 records `.claude/` as excluded in some projects; this repo gitignores `.claude/` and `.compass/tmp/`; setup and doctor have no gitignore handling for user projects. What a given user project tracks was not inspected.
    - Evidence: ADR-020 D-01; `.gitignore`
    - Marks: first-party decision record plus file read; 2 sources
    - Grade: medium

119. **`compass guard` judges only subagent calls, and its scope is the whole project** (confidence: high; G3)
    The hook exits unless the event carries `agent_id` or `agent_type`. For subagents against non-vault `src/old.ts`: denied `rm`, `git rm`, `git checkout --`, `git restore`, `git reset --hard`, `git push --force`, `git branch -D`, `git stash drop`, inline `os.remove`, an empty Write; allowed `sed -i`, `mv`, `ast-grep run -U`, `git commit` and plain push, `gh pr create`, `> file` truncation, a Write shrinking 60 lines to 1 character, an Edit blanking 30 lines. Shrink and blanking checks apply only inside the vault, and `meta/` and `archive/` are exempt from them, while delete verbs against `meta/` are denied.
    - Evidence: `plugin/cli/commands/guard.py:27-30, 45-50, 64-90, 101-107, 184-209, 298-335, 376-377`; `plugin/hooks/hooks.json:12`
    - Marks: code read plus run experiment; 3 sources agree
    - Grade: high

120. **A top-level `claude -p` loop run is a main-agent session to the guard, and the guard runs only where `.claude/cli/compass` is installed** (confidence: high for code facts, medium for the CI consequence; G3)
    A top-level process carries no `agent_id`, so the guard constrains only subagents it spawns. The hook begins `[ -f "$CLAUDE_PROJECT_DIR/.claude/cli/compass" ] || exit 0`, so a fresh CI checkout without `.claude/` has no guard. Compass's headless workers set `COMPASS_WORKER_SESSION=1`, which silences capture, context and sync hooks; a loop session without it runs those hooks where registered.
    - Evidence: `guard.py:376-377`; `hooks.json:12`; `capture_check.py:406`, `capture_signal.py:131`, `capture_note.py:65`, `context_check.py:292`, `sync.py:1030`, `capture_worker.py:306`, `clone.py:554`
    - Marks: code read, not run; CI behavior inferred
    - Grade: high for code, medium for CI

121. **No existing state file is loop-shaped; persistent ledgers belong outside `tmp/`** (confidence: high; G3)
    Nearest patterns: `tmp/capture-state.json` (per-session counters, gitignored scratch), `tmp/capture-log.jsonl` (append-only, aged into `archive/logs/` after 365 days), `meta/capture.json` (durable tunables), `<COMPASS_HOME>/sessions/<project>/<run-id>/run.json` written atomically outside the project, with `meta/clone-log.jsonl` as its project trace. Sync ages only three known names under `tmp/`; a new ledger there stays unaged, and `tmp/` is scratch a subagent may delete. The Data rule moves aged records colder, never deletes.
    - Evidence: `plugin/cli/capturelib.py:35-77, 147-172`; `clone.py:15-22, 207-221`; `sync.py:62-63, 828-902`; `guard.py:84`; `.claude/rules/compass-pipeline.md` "Data"
    - Marks: code read; 6 modules
    - Grade: high

122. **SPEC-009 is a deferred draft whose needs bind a loop definition, with format and location left open; its only code seam is a hardcoded function** (confidence: high; G3, agreeing with finding 72)
    [[specs/pipeline/SPEC-009-configurable-pipeline-workflows]] D-01: a workflow configures contracts between phases. Needs: zero-config default, the workflow is data the harness resolves, malformed configuration fails loud. Constraints: mechanical resolution, reuse existing config conventions, host-agnostic, cross-platform. Non-goals: ad-hoc phase invention. `workflow_binding()` in `coverage.py:66-82` returns the hardcoded spec and decision to plan binding; ADR-007 requires a config seam for SPEC-009; SPEC-014 D-01 says shipping SPEC-014 first gives SPEC-009 a substrate. The config conventions to reuse all sit under `.compass/meta/`: `capture.json`, `models.yaml`, `local/`, `plugin.yaml`. No document read decides whether a loop is a workflow, a phase or a new artifact type.
    - Evidence: SPEC-009 lines 11, 32-39, 43, 56, 69-88; `.compass/backlog.md:27`; ADR-007 Consequences; SPEC-014 line 34; `capturelib.py:72-73`; `modelslib.py:169`
    - Marks: first-party code, specs and ADRs; 4 sources agree
    - Grade: high

123. **Placement map: what the code shows for each loop part and location** (confidence: high except cells marked; G3)
    | Part | `.claude/skills/<name>/` or `.claude/agents/` | `.claude/cli/` | `.compass/meta/<x>/` | `.compass/<x>/` root folder | project source tree |
    |---|---|---|---|---|---|
    | Actuator skill or agent | survives unless a shipped name collides (113); may be untracked (118) | deleted (114) | whether Claude Code loads a skill from here is unchecked | unclassified unless `type: unit` (117) | not checked |
    | Sensor and controller scripts | survive inside a user skill dir (113) | deleted (114) | survive (117) | survive, unscanned unless a unit (117) | untouched by update and scanner |
    | Loop definition, golden patterns | skill-dir files survive (113); overlay appends `*.md` only (116) | deleted (114) | survive, unscanned, exempt from shrink checks (117, 119) | scanned only as a unit or type dir (117) | untouched |
    | Feedback file | as a skill-dir file (113) | deleted (114) | survives (117) | as a unit artifact | untouched |
    | Run ledger | untracked where `.claude/` is ignored (118) | deleted (114) | persists, no aging for new names (121) | n/a | n/a |
    | Hook registering a sensor | survives unless it runs a shipped command or Compass's CLI (115) | n/a | n/a | n/a | same rule (115) |

### Loops for users' tasks: Maya

73. **An agent drives Maya through `commandPort` in a live session or `mayapy` in batch, each with hard constraints** (confidence: high; single axis A5)
    Every public Maya MCP server read opens `cmds.commandPort` in a running GUI Maya and sends Python or MEL. The port has no authentication and runs with the user's permissions; GG_MayaMCP accepts only localhost and gates raw Python behind an env flag; it exposes 71 typed tools, including keyframe read and write and a single-frame viewport capture, but no render or movie playblast. commandPort runs on Maya's main thread, freezing the GUI, so multi-file, per-frame, render and cache work belongs out of process (medium, measured on Maya 2027 macOS only). `mayapy`/`maya.standalone` is batch mode with UI commands disabled and licences checked out at `initialize()`; plugins (Alembic, USD, FBX, mtoa) do not auto-load, and mayapy 2027 exits 0 after `initialize()` whatever `sys.exit(N)` says, so runners leave through `os._exit` (medium, one platform).
    - Evidence: `GG_MayaMCP/docs/adr/0001-commandport.md`, `docs/spec/tools.md`, `docs/spec/security.md` at `06862e0`; https://help.autodesk.com commandPort and Python-outside-Maya pages; `maya-mcp/docs/skills/maya-headless-batch/SKILL.md` and `scripts/mayapy_runner.py` at `21b3ad7`
    - Marks: code and first-party docs; owner checked; 2 to 3 sources per claim
    - Grade: high for transport and batch mode, medium for single-platform measurements

74. **Headless playblast and batch-render licensing are contested between sources** (confidence: low; single axis A5)
    A practitioner article says playblast works under `maya -batch` and `mayapy`; the maya-mcp skill says playblast, viewport capture and Qt are unavailable in standalone; Autodesk's playblast page is silent. Autodesk forum answers disagree with each other and with an audit consultancy on whether batch rendering needs a Maya licence; the mayapy docs say `initialize()` checks one out. A9 and A5 note this needs a run on the target machine.
    - Evidence: https://www.regnareb.com/pro/2021/06/headless-playblasts-batches/; maya-mcp skill section 2; Autodesk playblast and Render CLI pages; forums.autodesk.com thread
    - Marks: blog (author unverified), owner-checked skill, first-party docs, forum; sources disagree
    - Grade: low

75. **Maya offers deterministic sensors; LLM loops on 3D content close on rendered images, never yet in Maya** (confidence: medium; axes A5, A6, A9; C32)
    Deterministic candidates surfaced by MCP tools: keyframe counts and values (`animation.get_keyframes` returns `{time, value}` lists and `total_keyframe_count`), time range, topology checks, file exists and non-empty, render wall time, runner exit status. LLM 3D agents (SceneCraft, SceneAssistant in Blender; Cutscene Agent in Unreal) render, critique with a vision model and revise, stopping when acceptable "or a maximum iteration budget is reached"; Cutscene Agent reads scene state as JSON and takes timestamps from tool returns "rather than LLM estimates". No paper ran such a loop in Maya, and no axis found prior art for any loop outside a code repository with CI.
    - Evidence: `GG_MayaMCP/src/maya_mcp/tools/animation.py:508-560`; arXiv:2403.01248, 2603.12238 (abstracts), 2604.25318 (HTML)
    - Marks: code; preprints 2024-2026, citation counts not retrieved; 3 sources agree on render-critique-revise
    - Grade: high for tool contracts, medium for the literature

76. **A licensed local DCC fits the local lane, and HumanLayer's PR-shaped parts need replacing** (confidence: medium for the lane, low for the kit; axes A5, A9; C33)
    Cloud routines run on a fresh clone without local files; Desktop tasks and OS-scheduled `claude -p` keep local files and MCP config, so a licensed Maya points to the local lane (A5's inference from the docs' table). HumanLayer's dampener, memory file, `/iterate` and flow control are all PR-shaped. Parts a non-code loop kit would replace: repo, CI, package manager, lint and typecheck as validators, PR as the unit of change, PR comment as the steering channel, open-PR count as WIP. Slots with no counterpart in the skill: where the actuator runs (live session, batch, cloud), licence and machine availability, what one increment's artifact is and how it is versioned, how a non-deterministic sensor is calibrated, what a skipped run means. A candidate Maya mapping (set point = a written brief plus reference; one unreviewed shot version open at a time as WIP) is A5's untested assembly.
    - Evidence: https://code.claude.com/docs/en/scheduled-tasks, /headless; `design-control-loop/SKILL.md` Phases A, B5, E, F, G; `control-loop-taxonomy.md` design questions 1 to 9
    - Marks: first-party docs plus shipped code; assemblies stated by no source
    - Grade: medium for the lane, low for the kit and the mapping

### The spec's example loops

77. **For each example loop, a sensor already exists outside the agent, and the step is kept small by a count, a unit or a limit** (confidence: medium; axes A6, A5)
    | Loop | Sensor | Step size | Quality feedback | Prior art, measured |
    |---|---|---|---|---|
    | Eradicate bad patterns | count of AST or lint matches, tracked in VCS | one violation, or up to 5 fixes from top 3 rules; one open PR | typecheck, lint, tests, sensor re-run; dampener PR check | HumanLayer; Betterer; codemods; Piranha 65% landed unchanged |
    | Adopt a framework incrementally | unmigrated-site count, per-file step status | one file, procedure, or dependency-closed cluster where reviewers are ready | build, unit tests, lint, tsc, LLM repair, owner review | Airbnb 3.5K files in 6 weeks vs 1.5 years estimated; Google JUnit3 5,359 files in 3 months |
    | Maintain a fork | commits behind upstream, conflict yes or no | one fast-forward or clean merge; conflicts stop the bot | sync PR CI | GitHub `merge-upstream`, wei/pull; no agent-driven result |
    | Mirror into another language | compile rate, source test pass rate, output equivalence | one function or module behind a compiling skeleton; revert on break | compiler, then tests, then differential output | EvoC2Rust, CRUST-Bench; Uber J2K |
    | Keep integrations up to date | installed vs latest version | one update PR; concurrency, grouping, cooldown | CI; automerge only when green | Renovate, Dependabot |
    | Comply with a third-party spec | conformance suite pass rate | one failing test or feature area | the suite; scoring rules move the number | WPT/Interop 2025 intersection 25 to 95 |
    | Resolve anomalies | monitoring alerts | one remediation workflow per alert; concurrent-repair cap | re-run the checker; unrecovered becomes a ticket | Meta FBAR, 94% of server alarms auto-cleared (self-reported) |
    | Maya animation | keyframe and file checks, vision judge (A5) | one shot or rubric failure (A5, untested) | captured-frame review (A5, untested) | none |
    - Evidence: A6 findings 1 to 19; A5 findings 10 to 21
    - Marks: mixed; see the provenance table below
    - Grade: medium

78. **Google's migrations: a deterministic finder locates, the LLM edits, success is time saved** (confidence: high as reported; single axis A6)
    Int32-to-int64 IDs: a human picks a seed field, Kythe finds references three levels out, the LLM gets path and line; success is "AI saving at least 50% of the time for the end-to-end work"; 80% of landed code AI-authored over a 500M+ line codebase. JUnit3-to-4: about 87% of AI code committed unchanged. Stated lessons: AST tooling is "always correct" and unaffected by model changes; an AST diff of before and after catches simple model slips; non-LLM steps are cheaper. Stale-flag cleanup reads its sensor from the experiment system.
    - Evidence: arXiv:2501.06972 §III-VIII (HTML read)
    - Marks: experience report, authors say "not a research study"; preprint v1 2025-01-12; engineer-estimated savings
    - Grade: medium

79. **Airbnb's migration: a per-file state machine as both step and sensor, tuned by "sample, tune, sweep"** (confidence: high as reported; single axis A6)
    Each file passes ordered steps (refactor, fix Jest, fix lint and tsc, mark complete) and advances only when the current step's check passes; a status comment per file records per-step pass counts; retries carry the latest errors (most files pass within 10 attempts; the hardest 50 to 100 with 40K to 100K token prompts). 75% of about 3.5K files in 4 hours; 97% after 4 days of tuning; the last 3% by hand in about a week. Tuning loop: pick 5 to 10 failing files showing one issue, change prompts, re-run the sample, sweep everything.
    - Evidence: airbnb.tech/infrastructure/accelerating-large-scale-test-migration-with-llms/ (read)
    - Marks: first-party engineering blog, affiliation checked; 1 primary source
    - Grade: medium

80. **Uber places the LLM differently: it writes deterministic rules, not code** (confidence: medium to low; single axis A6)
    Piranha deletes stale flags by AST, sensor = flag unmodified beyond a team threshold; diffs go to the flag owner and are never auto-landed; 65% landed without changes, over 85% compile and pass tests (ICSE-SEIP 2020, via search summary). Shepherd rolls out in rounds: run, read failure logs, add missing patterns, rerun. Java-to-Kotlin: direct LLM generation was rejected for hallucination risk; the LLM drafts AST rules from the delta between tooling output and historical human migrations, then repairs them on test failure (KotlinConf 2025 slides via summary; the 8-years-to-4 timeline is a projection).
    - Marks: one peer-reviewed via summary; first-party blog and talk via summaries
    - Grade: medium for Piranha, low-medium for the Kotlin pipeline

81. **Fork upkeep tooling stops at conflicts, and the overwrite options destroy fork-only work** (confidence: medium; single axis A6; C35)
    GitHub's `merge-upstream` does fast-forward or clean merge and returns 409 on conflict, with no force option; `gh repo sync --force` and wei/pull `hardreset` permanently discard fork-only commits, and wei/pull's default with no config hard-resets. No source reports an agent-driven fork merge or rebasing a patch series onto upstream.
    - Evidence: github.com/wei/pull; docs.github.com "Sync a fork branch" (search summaries)
    - Marks: repo and docs via summaries plus one issue report
    - Grade: medium

82. **No source reports token or dollar cost per accepted change** (confidence: high as a bounded absence; axes A6, A4)
    Airbnb calls cost "far more efficient" than manual without a figure; Google says costs "add up"; HumanLayer reports no merged-PR counts, error rates or cost per iteration. G1 confirms the absence for migration PRs and finds figures for agent changes outside migrations (findings 124, 125); the disagreement is listed under Partial (C42).
    - Marks: negative finding across every migration source read
    - Grade: medium

124. **Dollars per merged migration PR remain unreported; SWE-bench+ defines cost per accepted result as total cost over issues resolved** (confidence: medium; G1; C42)
    Google's migration study reports 595 changes and 50% time saved, no dollars; library-migration papers report cost per KLOC or per run. SWE-bench+ Table 4 (548 instances): RAG+GPT-4 \$32.5 per fix, RAG+GPT-3.5 \$10.0, SWE-Agent+GPT-4 \$655.0, AutoCodeRover+GPT-4o \$12.61, on benchmark issues, not merged PRs; the paper's prose quotes different numbers for two rows.
    - Evidence: search summaries of arXiv:2504.09691, 2504.13272, 2510.08810; arXiv:2410.06992 v2 §5 Table 4 (HTML read)
    - Marks: negative finding across a few hundred hits; SWE-bench+ preprint 2024-10, not retracted, citations not found
    - Grade: medium for the absence, medium-low for SWE-bench+

125. **Measured cost figures for agent changes outside migrations exist, each from one source** (confidence: medium, low for merge rates; G1; C42)
    - Feature to automated-gate merge: \$2.59 to \$33.38 across 23 model-and-harness pairings, 29 runs, one task; same model, different CLI about 2.5x; a gate-approved run passed 12 of 38 unit tests on a second task (blog.apac.insight.com, 2026-07-06; single-author blog; grade medium-low).
    - Sonar's own repository: one agent PR about \$41 (512 round trips, 152.8M cache-read tokens); 18 comparable PRs averaged about \$65, median about \$52 (vendor blog selling a cost tool; grade medium-low).
    - TraceLab, about 4,300 Claude Code and Codex sessions: mean \$9.70, median \$0.61, p99 \$178 per session, cache reads 59.5% of cost (arXiv:2606.30560 v2, preprint; per session, not per change; grade medium-low).
    - Merge rate, the denominator: 43.0% to 84.3% merge probability by agent, and 83.8% eventual merge but 54.9% merged unmodified in another study (search summaries of arXiv:2607.21832 or 2605.22534; not read; grade low).
    - Marks: blogs, a vendor post and preprints; 0 or unknown citations; costs are list-price estimates, not bills

### Prior art: react-doctor

83. **react-doctor is a deterministic multi-rule sensor whose scalar score comes from a closed remote service** (confidence: high; single axis A3; C37)
    `millionco/react-doctor` (formerly `aidenybai/react-doctor`, released mid-February 2026, 15,012 stars): 906 registry entries, 688 default-enabled before framework gating (launch said "47-plus"). It runs AST rules, whole-tree file scans, a dead-code pass, a supply-chain score per dependency and an optional runtime trace, bucketed into Security, Bugs, Performance, Accessibility, Maintainability. The CLI POSTs sanitized diagnostics to `https://www.react.doctor/api/score`, which returns a 0-100 score and per-rule priority P0 to P3; the weighting is not in the open source; bands 75 and 50 are code constants; the score is `null` on timeout, under `--no-score`, or when the diagnostic set is incomplete. Rules are typed objects gated by project capabilities (`requires`, `disabledWhen`), validated against a pinned 2,000-repo corpus before merge ("False positives are treated as correctness bugs"), and retired by evidence with a compatibility shim.
    - Evidence: clone at `84ad0c8d`: `packages/core/src/request-score.ts:27-57`; `constants.ts:156-164`; `plugin/utils/rule.ts:14-111`; `docs/HOW_TO_WRITE_A_RULE.md`; `packages/evals/README.md`; `docs/rule-retirements.md`
    - Marks: code, owner checked; 15,012 stars; 1 source
    - Grade: high

84. **react-doctor hands fixing to an external agent with incremental-change controls built into the payload** (confidence: high; axes A3, A4, A6; C36)
    There is no auto-fixer at HEAD (an early `fix` command deeplinked into the author's paid product, Ami). The CLI builds a handoff payload: top 3 rule groups by score-API priority, a fix recipe, a path to `diagnostics.json`; text says "Leave the rest for a follow-up", "don't suppress or silence the rule", re-run and check the issue is gone. `fixGroupId` groups same-root-cause findings so one fix counts as one task. A rule firing in 40 or more files is flagged "Migration-scale": fix a sample, confirm the recipe, get the code owner's sign-off. The remote agent playbook (fetched through a summarizer) requires a clean baseline scan, "smallest local change", a same-scope rescan plus an unfiltered regression scan before a fix counts, and stops the whole run when coverage, ownership or authority breaks. Mistele calls React Doctor "a hybrid sensor and controller".
    - Evidence: `build-handoff-payload.ts:18-80`; `constants.ts:800-841`; `packages/react-doctor/CHANGELOG.md:3077-3088`; https://www.react.doctor/prompts/react-doctor-agent.md (summarized); transcript `[458s]-[493s]`
    - Marks: code, owner checked; playbook via summary (medium)
    - Grade: high, medium for the playbook

85. **react-doctor separates measurement, scope, gate and surface, and keeps no history** (confidence: high; single axis A3)
    A Stop hook runs `react-doctor --scope changed --blocking warning --no-score` and blocks once with the report as the reason, the same Stop-hook-block mechanism Compass's capture uses. `--blocking none|warning|error` sets what fails CI (the GitHub Action defaults to advisory); per-surface controls let a rule count in the CLI, PR comment, score or CI failure independently. No score history, trend file or ratchet exists in the source; over-time signals are PR comments, a commit status and Action outputs including `fixed-issues` (absence by grep over `types/`, medium). A human-steering file, `.react-doctor/false-positives.md`, exists only in the remote playbook, with no reader in the repo (low).
    - Evidence: `install-agent-hooks.ts:236-362`; `cli/index.ts:188-290`; `action.yml`; `docs/json-report.md`
    - Marks: code, owner checked; 1 source
    - Grade: high

### Prior art: HumanLayer

86. **HumanLayer's loop tooling is the `design-control-loop` interview skill; its other public work sits at other layers** (confidence: high; single axis A4)
    `design-control-loop` interviews the user (Phase B in order: set point with scope, sensor, controller, actuator with credentials and golden patterns, disturbances and dampener) after reading the repo, then builds sensor and controller scripts, an actuator skill, a workflow, a memory file and an optional dampener; its predecessor `build-iterated-agentic-loop` landed 2026-06-23. The old `humanlayer/humanlayer` repo is "pretty much all deprecated" and has no loop tooling. 12-factor-agents has no control-theory content (findings 53, 63 cover its relevant factors). "Advanced context engineering" (research, plan, implement; context utilization kept at 40 to 60%) is a within-run technique, not the loop. Agent runner templates cover Claude Code, Codex, OpenCode and CodeLayer.
    - Evidence: `humanlayer/skills` at `653b641`; `humanlayer/humanlayer` at `99abe67`; `humanlayer/12-factor-agents` at `d20c728`; `ace-fca.md:12, 60, 218, 308`
    - Marks: shipped code and docs, owner checked
    - Grade: high

All other HumanLayer findings sit under the step they inform: findings 1 to 4, 22 to 23, 26 to 27, 30 to 32, 36 to 37, 41, 46 to 47, 50 to 51, 53.

## Divergent (human decision)

1. **Where the LLM sits in the loop** (C31; positions held by sources, reported without conflict by A1, A4, A6, A10, A11)
   - Position A, LLM as actuator only, deterministic sensor and controller: HumanLayer ("never send an agent to do deterministic code's job"), Google (deterministic finder, "LLM planning capabilities are often not needed"), regulatory control (LLM returns a mode, code computes the command), Blueprint-First (LLM "never [decides] the workflow's path"). Findings 7, 30, 33, 61.
   - Position B, LLM authors deterministic rules and never edits code: Uber Java-to-Kotlin, Fiberplane's agent-written ast-grep bans; checker-synthesis systems (KNighter, AutoChecker, QLCoder) work only with an execution anchor. Findings 39, 80, 103 to 106.
   - Position C, LLM edits directly under brute-force retry inside a per-file state machine: Airbnb. Finding 79.
   - Position D, the agent owns its own control flow from skill files: the declarative agent of arXiv:2606.06923, which beat an imperative phase machine when retrieval was good. Finding 61.
   Google also says deterministic AST migrations "have not proven to be quite as effective" for contextual variance, against Uber's rejection of LLM code generation.

2. **How much explicit transition state a controller should hold** (C29)
   - Explicit FSMs help: StateFlow, HEXIS, Blueprint-First, Airbnb's per-file machine (findings 61, 79); statecharts as the scaling fix (finding 60).
   - Level-based observation instead of state machines: Kubernetes API conventions (finding 60).
   - Behavior trees generalize and scale better than FSMs (finding 60).
   - A rigid phase machine did not reliably help (arXiv:2606.06923, finding 61).
   Task types differ (fixed procedures vs knowledge-grounded service; robotics vs agents); no source compares them on a control loop over a codebase.

3. **Whether the talk names a telemetry vendor as controller input** (C9, split 1/1)
   - A4: the transcript names only "telemetry" and "APM"; PostHog and sentry.io in the spec are the spec's own extension; Dex names Sentry only as a loop trigger. Read from the transcript `[719s]-[745s]`, grade high.
   - A10: "Telemetry (Sentry traces, error counts, instrumentation gaps) named as a controller input", read from a third-party summary on the ai.engineer page, grade medium.

4. **Whether judge-score drift has been studied** (C43, split 1/1)
   - A2: no direct study; the nearest is generation drift between GPT-4 versions (finding 21), one search, grade low.
   - G2: judge-version drift is studied in essay scoring, and an anchor-set method separates judge from system drift (finding 100), abstracts and single-author preprints, grade low to medium.
   - Both agree nothing covers code review or rule checking.

5. **Whether temporal filters or noise gates exist for judge scores** (C44, split 1/1)
   - A2: no Kalman, EMA, low-pass or hysteresis filtering found (finding 21), grade low.
   - G2: noise-band, EWMA and SPRT gates exist as CI tools (finding 101), via search summaries, grade low.
   - Both agree none is tested inside an agent loop or on a rule-compliance sensor.

## Partial (needs attention)

1. **What the dampener's baseline commits** (C6, 2/3)
   - Majority (A1, A6, via talk summaries): the violation count is tracked in version control; output trimmed "from ~50 lines of context to 4 lines".
   - Minority (A4, transcript): "sort all the violations deterministically, and track it in our version control", where "it" follows the sorted violation list; raw output is "about 50 keys per violation", filtered to four keys.
   - The majority rests on summaries, the minority on the primary transcript; which form is committed decides whether a PR check can name the new violation or only detect a rise.

2. **Whether ratchets exist for agent loops** (C22, 2/3)
   - Majority (A6, A8): Betterer and ESLint bulk suppressions are committed-baseline ratchets that fail on regression (finding 28).
   - Minority (A1): no source applies ratchet, deadband or hysteresis to LLM-agent loops.
   - Scope explains it: A1 searched the LLM-agent control literature, A6 and A8 searched CI tooling. Deadband and hysteresis stay unfound by every axis.

3. **Whether self-update empties the installed skills directory** (C41, 2/3)
   - Majority (A9, A7): `_copy_tree_best_effort` empties the target before copying; read from code, survival of non-shipped skills marked unverified (finding 40).
   - Minority (G3): only `.claude/cli/` is emptied; skills are copied file by file and a user skill dir survived a run of `_apply` (findings 113, 114).
   - The majority read code only; the minority ran it.

4. **Whether any source reports dollar cost per accepted change** (C42, 2/3)
   - Majority (A4, A6): none in any migration source (finding 82).
   - Minority (G1): figures exist for agent features, PRs and benchmark fixes, one source each (findings 124, 125), while confirming none for migration PRs.
   - Scope explains it: A4 and A6 read migration sources, G1 searched agent cost broadly.

## Evidence resting on summaries or abstracts

Findings below were not read in the primary text. Where a later axis read the primary, it is noted.

| Axis | Read only as summary or abstract | Primary read elsewhere |
|---|---|---|
| A1 | Mistele talk (daily.dev summary); Hellerstein et al. and Filieri 2015 (catalog only); arXiv:2605.03034, 2510.04309, 2310.04444, 2510.13727, 2608.25099, 2610.01478, 2407.14402 (abstracts); MAPE-K (via the TSE review) | Talk verified by A4's transcript |
| A2 | All Part B judge-paper numbers via a fetch summarizer except arXiv:2306.05685; 2026 papers not re-fetched; OTel from docs, not run; surveys at abstract level | none |
| A3 | Remote agent playbook and false-positives file (summarizer); launch tweet (HTTP 402, known from search results) | none |
| A4 | none of its cited evidence; third-party recaps used only to locate sources | n/a |
| A5 | Autodesk Python-outside-Maya page (search excerpt); abrahamADSK tool behavior (README, not traced into source); arXiv:2403.01248, 2603.12238, 2606.04773 (abstracts); four VLM-motion papers (search results only); chadrik/maya-mcp-server (README skim) | none |
| A6 | Mistele talk (biggo summary); Piranha, Shepherd, Uber Kotlin, Betterer, Dependabot, fork tooling, C-to-Rust papers, WPT, test262, FBAR, Google SRE, jscodeshift (search summaries); Renovate page truncated | Talk verified by A4; Betterer docs read by A8; Renovate source read by A9 |
| A7 | none (code and logs) | n/a |
| A8 | Ralph `stop-hook.sh` (summarizing fetch); autoresearch (search summary); Little and Reinertsen (secondary blogs); SWE-smith and other trajectory papers (search results); Devin and Jules (third-party or snippets); Mistele talk (ai.engineer summary) | Talk verified by A4 |
| A9 | Mistele talk (search summary); GitHub concurrency pending-run semantics (unread) | Talk verified by A4; concurrency read by A8 |
| A10 | Mistele talk and its "never send an agent" quote (ai.engineer summary); leaf-first translation papers; CEDAR; Xia et al. figures; PostHog API and endpoints (search summaries of docs and PRs); comby (overview page only) | Talk and quote verified by A4 |
| G1 | Cursor help page, OpenAI daily options and reset date, Copilot AI Credits, Devin v3 org limit (search summaries); library-migration cost papers and both merge-rate studies (summaries) | none |
| G2 | Nearly every paper at abstract level through a fetch summarizer; Rating Roulette alphas, arXiv:2609.13824 correlations, SemOpt, QLCoder, LASIK, llm-eval-gate, drift-caliper, AgentAssay and practitioner drift posts via search summaries; Uber Rectify via a secondary talk summary | none |
| G3 | none (code read, two experiments run); full `_perform` path, manual update bash and the validate warning read, not run | n/a |
| A11 | Ramadge-Wonham (secondary summaries); hybrid automata, behavior trees, StateFlow, HEXIS, Blueprint-First, arXiv:2606.06923, 2603.19328, 2608.23670, tau-bench (abstracts); StateFlow's ReAct-rewrite control (secondary); 12-factor, Temporal, Anthropic "building effective agents" (fetch summaries) | 12-factor factors 8 to 10 read by A4 from a clone |

## Contradictions

- **Spec vs transcript, step 2.** The spec says the dampener step was "an insane amount of work in their case and it breaks a bunch of stuff". The transcript says only that they had to "enforce that all new procedures are using effect" to "stop the bleeding" (A4, finding 26). The source of the gloss is not found.
- **Spec vs transcript, telemetry.** The spec names PostHog and sentry.io for the controller; A4 finds no vendor in the talk, A10's summary says Sentry (Divergent 3).
- **HumanLayer vs itself, controller and sensor.** The talk discourages an agent controller; the skill offers a fully agentic controller as an option (A4, A6, A10). A talk summary says avoid agents for deterministic detection; the skill lists "an agent-based check" as an allowed sensor (A6).
- **HumanLayer speed-ups vs the one-PR bound.** Batching and parallel workflows multiply open work; the talk does not reconcile this with one open PR per loop (A8 reading; A4 lists the speed-ups without noting a conflict).
- **Context files vs feedback files.** Repository context files "do not generally improve task success" and cost over 20% more (arXiv:2602.11988), while HumanLayer steers its actuator with a feedback file and golden patterns. The study tested AGENTS.md-style files on Python issues and says files help for non-standard practices (A10).
- **Exemplars help vs similar code hurts.** Retrieved demonstrations raised few-shot edit accuracy (CEDAR); retrieved similar code lowered repository-level generation by up to 15% (arXiv:2503.20589). Task and setting differ (A10).
- **Self-correction.** Self-Refine and Reflexion report gains from same-model critique; Huang et al. and Stechly et al. report losses on reasoning and planning without external signals (A2).
- **Judge agreement.** 85% agreement with human preference (Zheng) vs near-chance on objective-correctness pairs (JudgeBench): different ground truths (A2).
- **Judge panels.** PoLL says diverse panels beat one large judge; arXiv:2610.21179 says plain averaging did not beat the best single judge, while weighting with disagreement filtering did (A2).
- **Stability definitions.** Classical stability is convergence to a fixed point; CyberCorrect and the context-assembly paper define it as bounded or non-decreasing score, and both call it weaker than proof (A1).
- **Iteration caps.** `/goal`'s cap is text judged by an evaluator model; Ralph's is a counter in a shell script. They give different guarantees (A8).
- **Enforcement.** AgentSpec prevents over 90% of unsafe executions; mediation on tau-bench left safe success below 5% with poor recovery after blocks (A11).
- **Maya.** Headless playblast works (practitioner article) vs is unavailable in standalone (maya-mcp skill); batch render needs a licence (consultancy, mayapy docs) vs does not (forum answers). GG_MayaMCP rejects `mayapy`; abrahamADSK/maya-mcp ships a mayapy path for heavy work, a design difference (A5).
- **Feedback file location.** Step 6 wants a file tracked in version control; Claude Code routines are account-owned and not repo-tracked, while `.claude/loop.md` and HumanLayer's memory file are repo files (A9).
- **Actuator skill location.** HumanLayer puts the actuator skill in `.claude/skills/`; A9 and A7 read Compass's self-update as emptying the skills directory, G3's run shows a user skill dir survives and only `.claude/cli/` is emptied (Partial 3, C41).
- **Update docs vs collisions.** `plugin/skills/update/SKILL.md:49-51` and `self_update.py:43-45` say user-authored skills are never touched, yet a user skill with a shipped name has its `*.md` overwritten (G3, finding 113).
- **Two update paths, two hook rules.** `self_update.py` replaces only groups running a shipped command or Compass's CLI; the manual `/compass:update` skill still drops every group whose command contains `compass` (`plugin/skills/update/SKILL.md:125-129, 158`; finding 115).
- **Judge voting vs validity.** Voting cuts variance by about 1 to 10 points (finding 98) while a judge can be 97% self-consistent and 0.28 correlated with humans (finding 99); they measure different things (G2).
- **Temperature 0.** Rating Roulette reports temperature 0 lowering human agreement for two models; other studies say it reduces but does not remove inconsistency (G2).
- **Graders without error rates.** uReview and G-Research filter with a second LLM (findings 95, 96) while finding 20 records judges without external signals as weak; neither post gives the grader's own error rate (G2).
- **Uber attribution.** The research brief credited Uber with LLM-written ast-grep or semgrep rules; the sources found show Rectify AST rules for Kotlin migration only (finding 103).
- **Vendor budget pages.** OpenAI Help Center (soft limits) vs developer docs (hard limits); Cursor's help (limit stops one user) vs a third-party guide (team limit blocks all); Jules Pro 100 tasks (vendor) vs 75 (March 2026 article) (G1).
- **Cost figures inside sources.** The Insight post says \$3 to \$33, a search summary of it \$7 to \$70; SWE-bench+ prose vs its Table 4 (G1, findings 124, 125).
- **Fix-loop cap scopes.** "Max 3 cycles per task", "up to 3 cycles, then escalate", and "max 3 iterations" for validator re-review: one number for three loops, enforced by no code (A7).
- **Talk prediction vs result.** The harness-as-controller paper predicts better harnesses reduce model-choice sensitivity, yet reports cross-model variance rising under its full harness (A1).

## Gaps

What the research leaves open. No remaining gap is **plan-blocking**: each is either closable only by a run, marked **experiment** (per the pipeline rules it belongs in a plan as an experiment), or a design choice for the human or the plan, marked **decision**.

Closed by the gap passes: daily budgets as a research question (G1: no product offers a per-day or per-loop dollar cap, a loop sums per-run records, the per-run caps behave as documented; findings 87 to 90, 109 to 112); the judge-as-sensor search (G2: the exact sensor is untested anywhere, with neighbouring evidence on noise, drift, gates and rule compilation; findings 92 to 108); the loop's home in a Compass project (G3: survival under update, guard scope, state files, SPEC-009 constraints; findings 113 to 123); `--max-turns` runtime behavior (finding 87).

- **Budget edges (experiment).** `--max-turns` at N greater than 1 and across `--resume`; a resume whose new spend alone exceeds the cap; whether the budget check ever precedes the first request. Only live runs settle these. Unread pages: Copilot AI Credits, the full OpenAI spend-limits page, Cursor's help page, Devin's per-session cap behavior. Finding 10 counts `total_cost_usd` in 44 capture-worker logs and finding 67 records that the worker reads only its `extracted:` line, so no Compass code sums cost today.
- **Judge precision and noise for a skill plus natural-language rules (experiment).** Precision and recall of that sensor against labelled compliance data, its per-rule flip rate across repeated runs, and judge drift for code review across model versions have no source; only a plan-time experiment on a labelled set (planted violations, repeated runs) can measure them (findings 92, 98, 100). Deadband or hysteresis on a judge reading inside a loop is untested (finding 101); anchoring a judge to a deterministic count is advice only (finding 102). Several figures (Rating Roulette, SemOpt, QLCoder, LASIK, arXiv:2609.13824) need a full-text check before a plan leans on them.
- **Accuracy of LLM-written ast-grep or semgrep rules from natural-language rules (experiment).** Unreported (finding 108); the documented recipe is test-against-a-snippet (finding 104). The Uber talk was seen only through a secondary summary.
- **What a loop is in Compass (decision).** Whether a loop is a [[specs/pipeline/SPEC-009-configurable-pipeline-workflows]] workflow, a phase or a new artifact type is undecided in every document read; SPEC-009 is a deferred draft and its format and location are open (findings 72, 122).
- **Loop-home residue.** Whether Claude Code loads a skill from outside `.claude/skills/`; what a user's project tracks in git (finding 118); guard and capture hooks in a fresh CI checkout, inferred from code only (finding 120, experiment); no ledger vocabulary, aging rule or doctor check exists for a new ledger name (finding 121, decision).
- **Golden patterns tested directly in agent loops.** No controlled study; evidence is single-shot few-shot work and practitioner opinion (finding 38).
- **"All control loops are also FSMs".** No source formalizes or tests the claim; Kubernetes documents the opposite stance (finding 60). Ramadge-Wonham definitions are second-hand.
- **Any LLM loop tested in Maya, or any loop outside a code repository with CI** (findings 75, 76). Studio pipeline schedulers and flow control (ShotGrid/Flow, Deadline, render-farm submitters) were not searched. No evidence that a vision model judging a clip against a reference clip is reliable enough to drive a controller.
- **Headless playblast and batch-render licensing (experiment).** Sources disagree; closing it needs a run on the user's Maya version and Autodesk's licence terms, which were not fetched (finding 74).
- **Agent-driven fork maintenance.** Only sync tooling found; no agent-driven merge result and no patch-queue rebasing prior art (Chromium, Electron) (finding 81).
- **Loop stability measured empirically.** No step response, settling time, oscillation or loop-caused regression measured for a coding-agent loop over a real repository; no Compass loop run to failure (finding 9).
- **Deadband and hysteresis for agent loops.** None found in agent loops; noise-band and sequential-test gates exist for judge scores only (finding 101); autoscaler hysteresis and the Kubernetes HPA stabilization window were named but not searched (finding 8).
- **Cost per accepted change for migrations.** Unreported (findings 82, 124); figures outside migrations rest on one source each, and the merge-rate studies that would give the denominator were not read in full (finding 125).
- **Claude Code internals (experiment for the first).** Auto mode at its block thresholds inside a pure `-p` run; `Stop`, `SubagentStop` and `SessionEnd` hook input schemas; the TypeScript `SDKResultMessage` definition; stability of the undocumented `cost-state` record format (findings 13, 55, 90).
- **Telemetry intake.** Sentry per-function aggregation, `is:regressed` and `is:escalating` semantics, Seer's programmatic trigger; PostHog query API shape and rate limits verified against its docs. Compass has no PostHog or Sentry intake (finding 34).
- **HumanLayer specifics.** Which four ast-grep keys are kept and the rule text (slides not viewed); whether its own Effect dampener fails or comments; quantitative results (findings 23, 27, 82).
- **react-doctor specifics.** The score formula and whether the server stores per-repo history (finding 83).
- **Automated post-merge revert for agent loops.** None found (finding 57).
- **Primary texts unread.** Hellerstein et al. 2004, Kephart and Chess 2003, Filieri et al. 2015, Lehman's laws of software evolution, Ashby's law, Little 1961, Reinertsen 2009, Wonham and Cai 2019.
- **Citation counts.** Missing for most 2026 preprints (Semantic Scholar rate-limited; OpenAlex near zero for new preprints), for every paper on axes A5, A6, A10, and for G1's preprints (arXiv:2606.30560, 2410.06992, 2607.21832, 2605.22534).

### Live record (2026-10-18)

One loop run to its own stop with Compass 0.28.0, in a scratch git project outside this repo. The loop `LOOP-001-remove-prints` removes `print(` calls from three seeded Python files holding four calls. Sensor: a 10-line `python sensor.py` listing each call as `file:line text`; target 0, direction down, controller `first`, actuator `claude-haiku-4-5-20251001` with Read, Edit, Glob and Grep, `max_turns` 30, `max_budget_usd` 0.30, `daily_budget_usd` 0.80, `total_budget_usd` 2.00, `wip_limit` 2. Every run was a separate `compass loop run LOOP-001`.

| Run | Ending transition | Outcome | Item | Cost (USD) |
|---|---|---|---|---|
| 1 | verifying - helpful -> idle | helpful, 4 -> 3 | `src/alpha.py:print("hello", name)` | 0.0527927 |
| 2 | verifying - helpful -> idle | helpful, 3 -> 2 | `src/beta.py:print("sub called")` | 0.0282162 |
| 3 | gating - wip-full -> throttled | throttled, 2 unreviewed reach the limit 2; no actuator launched | none | 0.0 |
| - | `loop review ... accept` for runs 1 and 2; review rows only, no transition | | | |
| 4 | throttled - start -> sensing, then verifying - helpful -> idle | helpful, 2 -> 1 | `src/beta.py:print("sum is", total)` | 0.0278661 |
| 5 | verifying - helpful -> idle | helpful, 1 -> 0 | `src/gamma.py:print(text)` | 0.0280252 |
| 6 | sensing - at-set-point -> done | done, reading 0 at set point 0; no actuator launched | none | 0.0 |

Summed spend: 0.1369002 USD over four actuator runs, each 3 turns with subtype `success`. `compass loop status LOOP-001` printed `spend today: 0.1369 of 0.8 usd` and `spend lifetime: 0.1369 of 2 usd`, matching the ledger's own `cost_usd` sum computed in Python. Each increment removed exactly its selected line and nothing else; run 1's diff is the single line `-    print("hello", name)` in `src/alpha.py`.

Observed alongside: `status` after the `done` run printed `last reading: none`, because it reads `reading_after` of the last run row and a run that ends at the gate records only `reading_before`. The actuator session also created a `.serena/` folder in the project, so user-level MCP servers start inside a loop's headless worker.

`python -m pytest plugin/cli/tests -q` on the 0.28.0 tree: `1539 passed, 1 skipped, 1461 subtests passed`.
