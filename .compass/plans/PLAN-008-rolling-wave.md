---
title: "Rolling-Wave Plans (Detail Regions, Three-State Coverage, the Elaboration Loop)"
type: plan
status: draft
confidence: medium
area: methodology
tags: [planning, rolling-wave, elaboration, coverage, plan-format, cli]
created: 2026-08-11
updated: 2026-08-11
author: "planner agent"
depends_on: ["[[SPEC-015-rolling-wave-planning]]", "[[ADR-009-rolling-wave-mechanism]]", "[[RESEARCH-rolling-wave-synthesis]]"]
---

# Rolling-Wave Plans (Detail Regions, Three-State Coverage, the Elaboration Loop)

## Goal

Make plan detail track proximity. [[SPEC-015-rolling-wave-planning]] ruled that a plan specifies the near work fully and names the far work in one line each (D-04), that prototypes are first-class near work when a question blocks later detail (D-02), and that a wave is judged, never counted (D-03). [[ADR-009-rolling-wave-mechanism]] chose the mechanism: a literal `## Later (intent only)` boundary, a `commit-upfront` escape hatch, elaboration at the build flow's existing merge gate, and a coverage gate that reads three states instead of two. This plan builds the mechanical half first - the format's boundary parser and the two coverage commands that read it - then elaborates the prose surfaces that teach agents to write and consume the format, from what the first wave actually produces.

Grounded in [[RESEARCH-rolling-wave-synthesis]], whose do-not-build list is carried below with its citations intact.

**This plan is written in the format it implements**, and that is its acceptance test. The first wave is fully detailed; the prose work sits under `## Later (intent only)` as one line each; the elaboration step runs mid-plan and appends a `## Wave 1 elaborated` section. If the format cannot carry this plan legibly, the format is wrong and that finding lands before any agent is taught to write it.

## Prerequisites

- [[SPEC-015-rolling-wave-planning]] approved 2026-08-11 (D-02, D-03, D-04 bind every task below).
- [[ADR-009-rolling-wave-mechanism]] accepted 2026-08-11, and its seven mechanism decisions carry trackable `D-NN` bullets (normalized 2026-08-11 by the human's ruling). Its research is current: [[RESEARCH-rolling-wave-synthesis]] records `git_commit: 268aebc`, five commits behind HEAD.
- The CLI suite is green at HEAD: `python -m unittest discover -s plugin/cli/tests` reports `Ran 507 tests` / `OK` (verified 2026-08-11).
- Both sources are parseable and fully claimed. `compass coverage PLAN-008-rolling-wave` with default sources exits 0 over all ten decisions; see **Verification of this plan**.

## Desired End State

- A plan holds one detailed wave plus a `## Later (intent only)` list, and every Compass tool that reads plans knows which side of that line it is on.
- `compass coverage` reports three states. A decision claimed by a detailed task is `covered`; a decision claimed only by an intent line is `scoped` and never fails; a decision claimed by nothing is `NOT COVERED` and fails exactly as today. `compass lesson-coverage` reports the same three states, still gating on nothing but an unresolvable citation.
- A plan with no `## Later` section produces the same verdict and the same exit code it produces today. [[PLAN-006-learning-loop]] and [[PLAN-007-test-quality]] are the regression pins.
- The planner specifies the current wave and lists the rest; the build flow elaborates the next wave at the merge gate it already has; the validator audits the wave sections; the methodology skill describes the loop. (All in the later list, elaborated after wave 1.)
- This plan's own life is the evidence: at least two elaboration steps, one whole-plan approval, and both gates PASS with zero decisions still `scoped` at completion.

## What We're NOT Doing

Carried from [[RESEARCH-rolling-wave-synthesis]]'s do-NOT-build list, each killed by evidence rather than by budget, plus three scoping exclusions this plan adds.

- **Per-wave re-approval.** Zero of six surveyed methodologies re-run approval when detail is added (Practice approval-semantics map); it is also SPEC-015's own falsification criterion 2. Elaboration is presented as a delta and proceeds.
- **Fixed-N-task waves.** Rejected independently by all three axes (Practice-8, Practice-20, Agent-2, Agent-8, and the Flow gap confirming the literature yields no wave count). SPEC-015 D-03 rules it out directly.
- **Single-task waves / pure per-item pull.** Agent-3: step-wise-greedy is provably arbitrarily suboptimal once the horizon reaches 2.
- **A per-wave size budget or appetite.** The synthesis recommended importing Shape Up's appetite (Practice-9); SPEC-015 D-03 declined it, and [[LESSON-human-practice-rationing-assumes-human-scarcity]] says why: a cap imported from human practice rations human throughput, which is not the scarce resource here. No task encodes a size rule.
- **A formal middle detail tier.** SPEC-015 D-04: two tiers only. The frontier judgment already does the middle tier's constraint-clearance job.
- **Inline rewriting of intent lines as the elaboration record.** Agent-10 (cross-task error propagation), Flow-13 (a changelog without the why is the documented PPC failure), Practice-13 (the update artifact is separate from the approval artifact). Intent lines are consumed or explicitly superseded in a wave section, never edited in place.
- **A Definition-of-Ready style readiness checklist as the elaboration gate.** Practice-4: over-formalizing readiness becomes the heavyweight gate SPEC-015 falsifies on.
- **A bare "waves elaborated: N" counter.** Flow-13: the observed PPC failure mode, not a hypothetical one.
- **A detail-decay function by horizon distance.** No source in any axis measures it (Agent gap 1, Flow gap 4); any formula would be invented.
- **Cost-of-delay reordering.** Synthesis open point 3: 1.5 of 3 axes, and a planner agent cannot currently measure cost of delay. Out of v1, revisit if plans show sequence-driven detail waste.
- **A new CLI command.** ADR-009: the wave sections are the record and `compass` needs no `elaborate` verb for v1. `maincli.py` is untouched by this plan, so its `COMMAND_SPECS` list is not a contact point.
- **Any change to the build flow's test-first station, checkpoints, fix loop, or `open-ids` green definition.** The elaboration step is added at the merge gate that already exists; PLAN-007's stations are load-bearing and stay exactly as they are.
- **Retrofitting existing plans.** PLAN-006 and PLAN-007 keep their fully-detailed shape and are used here only as regression pins.

## Constraints (all tasks)

- CLI: stdlib only, never exits 2, `python`/`python3` both supported. Writes route through `vaultlib.write_text_lf`. Tests in stdlib `unittest` under `plugin/cli/tests/`.
- Suite green means `python -m unittest discover -s plugin/cli/tests` with no failures outside `compass test-checkpoint open-ids`, per PLAN-007's mechanical definition.
- Behavior changes land in `plugin/`. Nothing is live in this repo until the matching file reaches `.claude/`; the later list carries the refresh.
- Mechanical work stays off the agent budget ([[SPEC-004-mechanical-work-off-the-agent-budget]], [[LESSON-no-agent-bookkeeping]]). "Which detail state is this task in" is a parser's answer, never an agent's reading.
- Every code task goes through PLAN-007's test-first station. A prototype task is exempt by nature: its deliverable is an answer, not production behavior (ADR-009).

## Mechanism decisions this plan makes

ADR-009 fixes the shape; these are the choices the tasks implement, and each is a place the ADR left a gap a builder would otherwise improvise through.

- **The boundary is a region, not a per-task field.** A line's detail state is decided by which region it sits in: everything before the first `## Later` heading is **detailed**; the Later region runs to the next heading of level 2 or higher; a `## Wave N elaborated` section is a third region, **record**, whose citations claim nothing. Inferring state per-task from the absence of a `files:` field would be a shape heuristic of exactly the kind [[LESSON-type-dir-discovery-needs-content-signal]] warns about: it breaks the first time an intent line names the artifact it touches, which ADR-009 explicitly allows it to do.
- **The record region claims nothing, on purpose.** A wave section quotes intent lines as it supersedes them. If those quotes claimed, elaborating wave 1 would silently mark wave 3's decisions covered - a false pass in the exact gate SPEC-015 Need 5 exists to protect. When an intent line is genuinely elaborated, the new detailed task block carries the citation, so nothing is lost by the record region staying inert.
- **Intent lines are task lines.** A later line is `- [ ] TASK-NNN: intent - files: [...], decisions: [...]` with no complexity, no depends_on and no verification bullets. Keeping the head grammar identical means `lesson-coverage`'s existing `TASK_LINE` parser attributes them, distribution to `backlog.md` is unchanged, and elaboration is a matter of adding detail rather than rewriting a line into a different species.
- **`commit-upfront` overrides the region for one task.** A task line inside the Later region carrying `commit-upfront: <reason>` classifies as detailed, along with its indented continuation lines, until the next task line. This is the single flag ADR-009 specifies serving both justifications (Flow-18/Flow-19 late-change cost, Agent-8 low uncertainty), and it needs no second grammar.
- **Both regions live in one module.** `planlib.py` classifies lines and both coverage commands read it. Two independent implementations of the boundary would drift, and the boundary is the one thing the whole mechanism rests on.
- **`decisionslib` needs no notion of detail state, but it does need a fix.** Detail state is a property of the plan, not of the source, so the extractor is unchanged in that respect. It carries a real defect this plan reproduced: an ADR whose Decision section cites *another* document's decisions in prose and declares none of its own is classified `could-not-parse`, which fails the gate. ADR-009 was the instance that surfaced it. See TASK-067.
- **Scoped is reported, never rewarded.** The gate passes on `scoped` because forcing detail is the thing SPEC-015 exists to stop, but a decision that is still `scoped` when a plan closes is a decision that never got built. The validator's wave audit (later list) is where that lands, and this plan's own acceptance requires zero scoped at completion.

## Phases

### Wave 1 (detailed): the boundary and the gates

The mechanical half, and the whole of it: after this wave the tools understand the format even though no agent is yet taught to write it. That ordering is deliberate - the prose in wave 2 has to describe output that exists, and TASK-070 exists to make sure it describes the right output.

- [ ] TASK-066: `planlib.py` - the plan detail-region classifier - complexity: M, depends_on: none, files: [plugin/cli/planlib.py, plugin/cli/tests/test_planlib.py], decisions: [SPEC-015-rolling-wave-planning/D-04, ADR-009-rolling-wave-mechanism/D-01, ADR-009-rolling-wave-mechanism/D-07], lessons: [LESSON-no-agent-bookkeeping, LESSON-type-dir-discovery-needs-content-signal]
  - One function, `classify_lines(text)`, returning a mapping of 1-based line number to `detailed`, `scoped`, or `record`. Callers treat an absent key as `detailed`, so a plan with no headings at all behaves exactly as today.
  - **Region rules.** The Later region opens on `^##\s+Later\b` (case-insensitive, so `## Later (intent only)` and `## later` both match, and `## Latergrade` does not) and closes at the next `#` or `##` heading, or EOF; `###` and deeper stay inside it. A record region opens on `^##\s+Wave\s+\S+\s+elaborated\b` (case-insensitive) and closes the same way. Everything else is detailed.
  - **`commit-upfront` override.** Inside the Later region, a task line matching `lesson_coverage.TASK_LINE`'s head grammar and containing `commit-upfront` classifies `detailed`, as do the indented lines beneath it, until the next task line or the end of the region.
  - Fences are stripped internally via `vaultlib.strip_fenced_code`, which preserves the line count, so a `## Later` heading quoted inside a fenced example never opens a region and the returned numbers still index the original text. Inline code spans are stripped the same way for the heading match. CRLF input is normalized first.
  - Automated verification: unittest - a document with no `## Later` maps every line detailed; lines under `## Later (intent only)` map scoped and the first line of the following `## Risks` maps detailed again; a `### sub` heading inside Later stays scoped; `## Later` inside a fenced block opens nothing; `## later` matches and `## Latergrade` does not; a `commit-upfront` task line inside Later maps detailed together with its indented bullets, and the next plain intent line maps scoped again; a `## Wave 1 elaborated` heading maps its body `record`; line numbers of a document containing a fenced block align with the original text (assert against a known line); CRLF input produces the same map as LF; an empty document and a document that is only frontmatter return empty maps without raising.
  - Manual verification: run the classifier over this plan file and read the three regions it reports back. A human should be able to point at the `## Later` heading and agree with every line's state without consulting the code, and in particular should agree that TASK-076's `commit-upfront` block is detailed while the lines above and below it are scoped.

- [ ] TASK-067: `decisionslib` stops reading cross-document references as unparsed local decisions - complexity: S, depends_on: none, files: [plugin/cli/decisionslib.py, plugin/cli/tests/test_decisionslib.py]
  - Reproduced during planning, before ADR-009 was normalized: `coverage --against ADR-009-rolling-wave-mechanism` printed `COULD NOT PARSE` and exited 1. The section declared no `D-NN` bullets of its own and referred to `(SPEC-015 D-02)` and `(SPEC-015 D-03)`; the zero-extraction evidence heuristic saw a `D-` token and concluded there were decisions it had failed to read. Normalizing that one ADR removed this vault's instance of the symptom, not the cause: any ADR that declares no local decisions and cites another document's in prose still hard-fails the gate on the whole source.
  - The fix is narrow: before the evidence test runs, remove **qualified** references from the text being examined - a `D-NN` token immediately preceded by a document stem (`SPEC-`, `ADR-`, `PLAN-`, `RESEARCH-` prefixed, separated by a space or a slash) or sitting inside a `[[wikilink]]`. What remains is tested exactly as today. A bare `D-01` with no qualifying name still poisons, because that is the shape of a real local decision the parser could not read.
  - Nothing else in the three-outcome contract moves: parse-miss poisoning on a malformed `- **D-` bullet, the ID-shaped bold-bullet heuristic, and the unterminated-fence signal all keep their current behavior.
  - Automated verification: unittest - an ADR-009-shaped fixture (a `## Decision` section, no `D-NN` bullets, prose citing `SPEC-015 D-02` and `[[SPEC-015-rolling-wave-planning]]`) returns `none-present`; the same fixture with a bare `D-01` in prose still returns `could-not-parse`; a malformed `- **D-` bullet still returns `could-not-parse` with the decisions parsed so far; a source-qualified `SPEC-007-decision-coverage-tracing/D-03` in prose is not evidence; every existing test in `test_decisionslib.py` and `test_decision_corpus.py` still passes unchanged. Plus corpus pins that hold after the normalization: `python plugin/cli/compass decisions ADR-009-rolling-wave-mechanism` exits 0 reporting its seven decisions, and `python plugin/cli/compass coverage PLAN-008-rolling-wave` (default sources, no `--against`) exits 0 over all ten. The pre-normalization document shape is preserved as a unittest fixture, since it is the only place the defect now reproduces.
  - Manual verification: read the amended evidence rule and answer one question - could a real spec whose author mistyped a decision bullet now slip through as `none-present`? Construct that document by hand and confirm it still fails. The heuristic exists to catch exactly that author, and loosening it is the risk this task carries.

- [ ] TASK-068: `compass coverage` reads three states - complexity: M, depends_on: TASK-066, files: [plugin/cli/commands/coverage.py, plugin/cli/tests/test_commands.py], decisions: [SPEC-015-rolling-wave-planning/D-04, ADR-009-rolling-wave-mechanism/D-06]
  - `_claims` gains the region of each citation from `planlib.classify_lines`. A `record`-region citation is discarded outright. Per decision: a detailed claim wins and reports `covered (line N)`; a scoped-only claim reports `scoped (line N)`; no claim reports `NOT COVERED`. The gate fails on uncovered and unparseable sources exactly as today, and never on scoped.
  - Summary line becomes `N trackable decision(s) in M source(s): X covered, Y scoped, Z uncovered -> PASS`, with the unparseable clause unchanged. Two existing assertions in `CoverageCommandTests` match on `"1 covered, 1 uncovered"` and are updated as part of this task, not left to fail.
  - The module docstring gains the three states and the record-region rule, in the same voice as the rest of the file.
  - Automated verification: unittest - a decision cited only from a line under `## Later` reports `scoped`, counts in the scoped column and exits 0; the same decision cited from a detailed task reports `covered`; cited from both reports `covered` and counts once; cited from nowhere still reports `NOT COVERED` and exits 1; a `commit-upfront` task inside the Later region yields `covered`, not `scoped`; a citation appearing only inside a `## Wave 1 elaborated` section yields `NOT COVERED`; a plan with no `## Later` section produces the same rows and exit code as before the change; an unparseable source still fails even when everything else is covered or scoped; exit code is never 2. Plus real-corpus pins: `compass coverage PLAN-006-learning-loop` and `compass coverage PLAN-007-test-quality` both still exit 0.
  - Manual verification: run the command against this plan and read the table. A human must be able to tell, from the table alone and without opening the plan, which decisions are built in wave 1 and which are still only named - and must agree that a `scoped` row is a promise rather than a gap.

- [ ] TASK-069: `compass lesson-coverage` reads three states - complexity: S, depends_on: TASK-066, files: [plugin/cli/commands/lesson_coverage.py, plugin/cli/tests/test_lesson_coverage.py], decisions: [SPEC-015-rolling-wave-planning/D-04, ADR-009-rolling-wave-mechanism/D-06]
  - The same region read, applied to `lessons:` citations. Status gains `scoped` for a lesson cited only from intent lines; a lesson cited from both regions is `cited`. `unresolvable` and `surfaced-but-uncited` are untouched, and so is the exit rule: only an unresolvable citation fails. The `--json` payload gains a `scoped` list beside `cited`.
  - Summary gains the scoped count. The "no citations" summary is unchanged for a plan with no `lessons:` field anywhere.
  - Automated verification: unittest - a lesson cited only from a Later-region task line reports `scoped` and exits 0; cited from a detailed task reports `cited`; cited from both reports `cited` once; an unresolvable citation from the Later region still exits 1, because a typo is a typo in either region; the `--json` payload carries the scoped entry with its citing tasks; a plan with no `## Later` produces the previous output; never exits 2. Plus a corpus pin: `compass lesson-coverage PLAN-007-test-quality` still exits 0 with its previous row set.
  - Manual verification: run it against this plan and confirm the scoped row for [[LESSON-human-practice-rationing-assumes-human-scarcity]] reads as "this lesson binds work that is not specified yet" rather than as an omission. If a reader cannot tell scoped from uncited at a glance, the wording is wrong.

- [ ] TASK-070: prototype - is the region rule sound on real plans? - complexity: S, kind: prototype, depends_on: TASK-068, TASK-069, files: [], decisions: [SPEC-015-rolling-wave-planning/D-02, ADR-009-rolling-wave-mechanism/D-02]
  - **Question:** does attributing citations by region hold up on documents written by people rather than by fixtures, and what must the planner brief forbid or require for it to stay sound?
  - **Method:** run both amended commands over four inputs and record the verdicts verbatim. (1) [[PLAN-006-learning-loop]] and (2) [[PLAN-007-test-quality]], neither of which has a `## Later` section, as the backward-compatibility evidence. (3) This plan, which has a Later region, a `commit-upfront` block inside it and citations in prose sections on both sides of the boundary. (4) A scratch copy of this plan with a synthetic `## Wave 1 elaborated` section that quotes an intent line's citation, which is the false-pass the record region exists to prevent.
  - **Deliverable:** an answer, recorded in the `## Wave 1 elaborated` section, covering three points - whether any citation site outside a task line changes a verdict on a real plan; whether the record region actually blocks the quoted-citation false pass; and what constraint, if any, the planner brief must state about where citations may appear. That answer is the input to TASK-071 and TASK-072, which is why this task sits before the elaboration step rather than after it.
  - This is a prototype under SPEC-015 D-02: its output is an answer, not shipped code, so it carries no test-first station. If it finds a defect, the fix is opened in this wave and TASK-068 or TASK-069 reopens - a prototype that discovers something and files it for later is a prototype that wasted the wave it was in.
  - Automated verification: the four command runs are recorded with their full output and exit codes in the wave section, and are reproducible by re-running the recorded commands.
  - Manual verification: the human reads the answer and rules whether the region rule is sound enough to teach to the planner. A "yes, with a constraint" answer is the expected shape; a "no" answer stops wave 2 and reopens the boundary design, which is precisely what a prototype is for.

**Pause point and elaboration step (the mid-plan exercise).** When wave 1's tasks complete and verify at the merge gate: run the elaboration. Read the wave's verified outcomes - the four command runs from TASK-070, the two gates' real output, whatever the region rule turned out to require - then rewrite the next coherent set of intent lines below into full task blocks and append a `## Wave 1 elaborated` section recording what was learned and why any detail differs from its intent line. Present the delta to the human (what was learned, what wave 2 is); do not re-approve the plan. In `all-phases` mode the human pause is skipped; the elaboration step is not, because it is the mechanism under test.

## Later (intent only)

The prose surfaces that teach agents to write and consume the format. Every one of them describes output that wave 1 produces, which is why they are named here and specified after. TASK-076 is written in full despite its distance, under the `commit-upfront` rule.

- [ ] TASK-071: planner brief flips from "specify all tasks" to "specify the current wave fully, list the rest as intent, flag commit-upfront exceptions" - files: [plugin/templates/agents/planner.md], decisions: [SPEC-015-rolling-wave-planning/D-03, SPEC-015-rolling-wave-planning/D-04, ADR-009-rolling-wave-mechanism/D-01, ADR-009-rolling-wave-mechanism/D-03], lessons: [LESSON-human-practice-rationing-assumes-human-scarcity]
- [ ] TASK-072: `plan` skill carries the format (the `## Later` boundary, intent-line grammar, `commit-upfront`) and draws the line between iterate and elaborate - files: [plugin/skills/plan/SKILL.md], decisions: [SPEC-015-rolling-wave-planning/D-04, ADR-009-rolling-wave-mechanism/D-01, ADR-009-rolling-wave-mechanism/D-05]
- [ ] TASK-073: `build` skill gains the elaboration step at its existing merge gate, fired on verified completion; stations, checkpoints and the `open-ids` green definition untouched - files: [plugin/skills/build/SKILL.md], decisions: [SPEC-015-rolling-wave-planning/D-02, ADR-009-rolling-wave-mechanism/D-04, ADR-009-rolling-wave-mechanism/D-05]
- [ ] TASK-074: validator audits the wave sections - elaborated detail that never got cited, decisions still scoped at plan close, intent lines edited in place rather than superseded - files: [plugin/templates/agents/validator.md], decisions: [ADR-009-rolling-wave-mechanism/D-07]
- [ ] TASK-075: methodology skill describes the build-learn-elaborate loop alongside the pipeline it sits inside - files: [plugin/skills/methodology/SKILL.md]
- [ ] TASK-076: install refresh and acceptance - complexity: M, depends_on: TASK-071, TASK-072, TASK-073, TASK-074, TASK-075, files: [.claude/], commit-upfront: the acceptance battery is the same shape every Compass plan runs and its detail does not depend on anything wave 1 or wave 2 produces, decisions: [SPEC-015-rolling-wave-planning/D-04, ADR-009-rolling-wave-mechanism/D-01]
  - Copy `plugin/cli`, `plugin/skills/*` and `plugin/templates/agents/*` into `.claude/` (or run `/compass:update`), then run acceptance from the installed copy, which is the only way the refresh is proven.
  - Automated verification: `python -m unittest discover -s plugin/cli/tests` green with the new tests included (507 at plan start, higher here), green meaning no failures outside `compass test-checkpoint open-ids`; `python .claude/cli/compass doctor` exits 0; `python .claude/cli/compass coverage PLAN-008-rolling-wave` exits 0 with **zero scoped rows** - every decision this plan named must be built by the time it closes; `python .claude/cli/compass lesson-coverage PLAN-008-rolling-wave` exits 0; `compass coverage` and `compass lesson-coverage` still exit 0 on PLAN-006 and PLAN-007.
  - Manual verification: the human reads this plan end to end as the artifact the format produced and answers SPEC-015's success criteria directly - did at least two elaboration steps run, did the plan get approved exactly once, and did a knowledge item from wave 1 demonstrably change a later wave's detail in a way the wave sections show. A plan whose wave sections record nothing that changed is the falsification signal, not a clean run.

## Parallel-safe tasks

- **Wave 1:** TASK-066 and TASK-067 are file-disjoint and depend on nothing - safe together. TASK-068 and TASK-069 both depend on TASK-066 and touch different command and test files - safe together. TASK-070 runs alone, after both.
- **Wave 2 (as named):** TASK-071 through TASK-075 each own exactly one file and none is shared, so all five are file-disjoint. Whether they are also *knowledge*-disjoint is a question for the elaboration step, not for now.

## Ownership and contact points

- `plugin/cli/planlib.py` - created by TASK-066, read by TASK-068 and TASK-069. No task edits it after creation.
- `plugin/cli/tests/test_commands.py` - exclusive to TASK-068 (it holds `CoverageCommandTests`, including the two summary assertions that change).
- `plugin/cli/tests/test_lesson_coverage.py` - exclusive to TASK-069.
- `plugin/cli/decisionslib.py` and `test_decisionslib.py` - exclusive to TASK-067.
- `plugin/cli/maincli.py` - **not touched by this plan.** No new command is registered, so the usual `COMMAND_SPECS` merge-order contact point does not exist here.
- Each later-list task owns one file exclusively; agent-template frontmatter and body are edited by a single task each, so the collision shape that needs merge-order rules does not arise.

## Risks

- **A citation in plan prose after the `## Later` heading claims scoped by accident.** The region rule attributes by position, and plans carry prose, not only task lines. Mitigations: the region closes at the next `##` heading, so it cannot swallow `## Risks` or a coverage table; TASK-070 probes it against real plans before any agent is taught the format; the constraint TASK-070 finds is what TASK-071 states.
- **Scoped becomes a parking lot.** A plan could scope every decision and pass the gate, which would satisfy the mechanism and defeat SPEC-015's Need 5. Mitigations: an unclaimed decision still fails; the validator's wave audit (TASK-074) reports decisions still scoped at plan close; TASK-076's acceptance requires this plan itself to close with zero scoped rows.
- **Elaboration grows into the ceremony it replaced.** SPEC-015 falsification criterion 2, and the one this plan is most likely to trip: a delta presentation that turns into a review turns into an approval. Mitigations: ADR-009 fixes the delta as "what was learned, what the next wave is"; this plan runs the step twice and TASK-076's manual verification asks the human directly whether approval touchpoints increased.
- **Loosening the `could-not-parse` heuristic hides a real malformed decision.** TASK-067 trades a small amount of strictness for a gate that does not fail on a legitimate ADR. Mitigation: only *qualified* references are removed and a bare `D-NN` still poisons; the manual verification constructs the mistyped-bullet document by hand and confirms it still fails.
- **The far list is under-specified into improvisation.** SPEC-015 falsification criterion 1, the opposite failure from the one above. Mitigation: intent lines name the file they touch and the decision they serve, so a builder cannot be handed one - elaboration is a required step before any later task is executable, and the build flow's task selection reads `active.md`, which only detailed tasks reach.

## Inherited questions

SPEC-015's four open questions were answered by the research and closed by ADR-009: wave boundary (frontier judgment, no caps), record location (per-wave sections appended to the plan), far-task coverage (three states, scoped never fails), and the planner brief (specify the wave, list the rest). Nothing is deferred into this plan. One question the ADR did not anticipate surfaced during planning and was ruled before approval.

- **Should ADR-009's `## Decision` section be normalized into `D-NN` bullets?** Ruled yes and executed (human, 2026-08-11). ADR-006, ADR-007 and ADR-008 all carry `- **D-NN:**` bullets; ADR-009 stated its mechanism in bold-lead paragraphs, so none of its seven decisions was individually trackable and the gate never checked that the ADR's own choices survived into the plan - the exact gap [[SPEC-007-decision-coverage-tracing]] exists to close. The section is now seven bullets (D-01 format, D-02 prototypes, D-03 boundary, D-04 loop, D-05 approval, D-06 coverage, D-07 record), each claimed by the task that implements it.
- TASK-067 lands regardless of that ruling. The `could-not-parse` defect it fixes is not specific to ADR-009: any ADR that declares no local decisions and cites another document's in prose fails the gate the same way, and the normalization removed this plan's instance of the symptom without touching the cause.

## Verification of this plan

Both gates were run against the draft after ADR-009's decisions were normalized. Default sources (the plan's own `depends_on`, filtered to specs and decisions) cover both documents, so the run below is the one the approval gate performs.

```
$ python plugin/cli/compass coverage PLAN-008-rolling-wave
compass coverage: note: 23 bare D-NN token(s) in plans/PLAN-008-rolling-wave.md claim nothing; a citation is source-qualified: <doc-name>/D-NN
compass coverage: plans/PLAN-008-rolling-wave.md
source                          decision  trackable  status
SPEC-015-rolling-wave-planning  D-02      yes        covered (line 111)
SPEC-015-rolling-wave-planning  D-03      yes        covered (line 125)
SPEC-015-rolling-wave-planning  D-04      yes        covered (line 83)
ADR-009-rolling-wave-mechanism  D-01      yes        covered (line 83)
ADR-009-rolling-wave-mechanism  D-02      yes        covered (line 111)
ADR-009-rolling-wave-mechanism  D-03      yes        covered (line 125)
ADR-009-rolling-wave-mechanism  D-04      yes        covered (line 127)
ADR-009-rolling-wave-mechanism  D-05      yes        covered (line 126)
ADR-009-rolling-wave-mechanism  D-06      yes        covered (line 98)
ADR-009-rolling-wave-mechanism  D-07      yes        covered (line 83)
summary: 10 trackable decision(s) in 2 source(s): 10 covered, 0 uncovered -> PASS
EXIT=0
```

Run per source, `--against SPEC-015-rolling-wave-planning` reports 3 covered / 0 uncovered and `--against ADR-009-rolling-wave-mechanism` reports 7 covered / 0 uncovered, both PASS. The bare-token note is expected and matches [[PLAN-006-learning-loop]] and [[PLAN-007-test-quality]]: prose refers to decisions by local ID, which by design claims nothing.

```
$ python plugin/cli/compass lesson-coverage PLAN-008-rolling-wave
lesson                                                     cited by  status
LESSON-human-practice-rationing-assumes-human-scarcity.md  TASK-071  cited
LESSON-no-agent-bookkeeping.md                             TASK-066  cited
LESSON-type-dir-discovery-needs-content-signal.md          TASK-066  cited
LESSON-hook-cli-gate-stdin-on-flag.md                      -         surfaced-but-uncited (advisory)
LESSON-scratch-vaults-need-compass-dir.md                  -         surfaced-but-uncited (advisory)
LESSON-suite-size-is-not-coverage.md                       -         surfaced-but-uncited (advisory)
LESSON-adversarial-plan-review-before-build.md             -         surfaced-but-uncited (advisory)
summary: 3 cited, 0 unresolvable, 4 surfaced-but-uncited (advisory) -> PASS
EXIT=0
```

**What these numbers mean today, and what they must mean after wave 1.** Both runs above are the *binary* gate: it scans the whole plan body and cannot see the `## Later` boundary, so a citation on an intent line reads `covered`. Six of the ten rows are claimed only from intent lines - SPEC-015 D-03 and ADR-009 D-03 at line 125, D-05 at line 126, D-04 at line 127, plus the intent-line half of D-01 and D-07 - and the `LESSON-human-practice-rationing-assumes-human-scarcity` row is `cited` for the same reason. After TASK-068 and TASK-069 land, re-running these two commands must reclassify exactly those rows to `scoped` while every detailed claim stays `covered` and the exit codes stay 0. That reclassification is the acceptance test for wave 1, and this section is the before-image it is measured against.
