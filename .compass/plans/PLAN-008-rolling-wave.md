---
title: "Rolling-Wave Plans (Detail Regions, Three-State Coverage, the Elaboration Loop)"
type: plan
status: approved
approved: 2026-08-11
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

**This plan is written in the format it implements**, and that is its acceptance test. The first wave is fully detailed; the prose work sits under `## Later (intent only)` as one line each; the elaboration step runs mid-plan, promotes the next lines up into a new detailed wave section and appends a `## Wave 1 elaborated` record. If the format cannot carry this plan legibly, the format is wrong and that finding lands before any agent is taught to write it.

## Prerequisites

- [[SPEC-015-rolling-wave-planning]] approved 2026-08-11 (D-02, D-03, D-04 bind every task below).
- [[ADR-009-rolling-wave-mechanism]] accepted 2026-08-11, and its seven mechanism decisions carry trackable `D-NN` bullets (normalized 2026-08-11 by the human's ruling). Its research is current: [[RESEARCH-rolling-wave-synthesis]] records `git_commit: 268aebc`, five commits behind HEAD.
- The CLI suite is green at HEAD: `python -m unittest discover -s plugin/cli/tests` reports `Ran 507 tests` / `OK` (verified 2026-08-11).
- Both sources are parseable and fully claimed. `compass coverage PLAN-008-rolling-wave` with default sources exits 0 over all ten decisions; see **Verification of this plan**.

## Desired End State

- A plan holds one detailed wave plus a `## Later (intent only)` list, and every Compass tool that reads plans knows which side of that line it is on.
- `compass coverage` reports three states. A decision claimed by a detailed task is `covered`; a decision claimed only by an intent line is `scoped` and never fails; a decision claimed by nothing is `NOT COVERED` and fails exactly as today. `--strict` turns `scoped` into a failure for the one caller that needs it: plan completion. `compass lesson-coverage` reports the same three states, still gating on nothing but an unresolvable citation.
- A plan with no `## Later` section produces the same verdict and the same exit code it produces today. [[PLAN-006-learning-loop]] and [[PLAN-007-test-quality]] are the regression pins.
- The planner specifies the current wave and lists the rest; the build flow elaborates the next wave at the merge gate it already has; the validator audits the wave sections; the methodology skill describes the loop; the plan template carries the format. (All in the later list, elaborated after the wave they depend on.)
- This plan's own life is the evidence: two elaboration steps, one whole-plan approval, and both gates PASS with zero decisions still `scoped` at completion.

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
- **Elaboration moves text upward.** A promoted line becomes a full task block in a new `### Wave N (detailed)` section under `## Phases`, above `## Later`, and the intent line it came from is deleted. Nothing is elaborated in place, because a task block written inside the Later region would still classify `scoped` and a task block written inside the record region would claim nothing at all - either way the elaboration would silently fail to move the gate. The distribution half follows the same direction: intent lines go to `backlog.md` and never to `active.md`, and the elaboration step moves the promoted ids from `backlog.md` into `active.md` so the build flow's task selection can see them.
- **The record region claims nothing, on purpose.** A wave section records what was learned and quotes intent lines - inside fences - as it supersedes them. If those quotes claimed, elaborating wave 1 would silently mark wave 3's decisions covered, a false pass in the exact gate SPEC-015 Need 5 exists to protect. When an intent line is genuinely elaborated, the promoted task block above carries the citation, so nothing is lost by the record region staying inert.
- **Intent lines are task lines.** A later line is `- [ ] TASK-NNN: intent - files: [...], decisions: [...]` with no complexity, no depends_on and no verification bullets. Keeping the head grammar identical means one `TASK_LINE` parser attributes them everywhere, distribution to `backlog.md` is unchanged, and elaboration is a matter of adding detail rather than rewriting a line into a different species.
- **`commit-upfront:` is a field, not a word.** A task line inside the Later region classifies as detailed when one of its trailing comma-separated fields begins with the `commit-upfront:` name-and-colon token, along with its indented continuation lines. A bare mention in intent prose does not trigger it, and that distinction is not pedantry: TASK-071 and TASK-072 below both describe the flag in their own intent lines, so a classifier that matched the bare word would read this plan's Later region as detailed and falsify itself on the first document it ever ran against. This is the single flag ADR-009 specifies serving both justifications (Flow-18/Flow-19 late-change cost, Agent-8 low uncertainty), and it needs no second grammar.
- **Both regions live in one module.** `planlib.py` classifies lines and owns the `TASK_LINE` regex; both coverage commands read it. Two independent implementations of the boundary would drift, and the boundary is the one thing the whole mechanism rests on. The direction matters too: `planlib` is a library, so `commands/` imports from it and never the reverse - no CLI library currently imports from `commands/` and this plan does not make it the first.
- **A broken fence is reported, never absorbed.** `strip_fenced_code` already returns an unterminated-fence flag because an unclosed fence blanks everything after it. The classifier passes that flag through and both commands print a note saying the regions were unreadable and every line was treated as detailed. The alternative - a plan whose Later region silently disappears and whose gate silently passes - is the failure this whole mechanism exists to prevent.
- **`decisionslib` needs no notion of detail state, but it does need a fix.** Detail state is a property of the plan, not of the source, so the extractor is unchanged in that respect. It carries a real defect this plan reproduced: an ADR whose Decision section cites *another* document's decisions in prose and declares none of its own is classified `could-not-parse`, which fails the gate. ADR-009 was the instance that surfaced it. See TASK-067.
- **Scoped is reported, never rewarded.** The default gate passes on `scoped` because forcing detail is the thing SPEC-015 exists to stop, but a decision that is still `scoped` when a plan closes is a decision that never got built. That is what `--strict` is for: it counts scoped as uncovered, and plan completion runs it. The validator's wave audit (later list) records it, and this plan's own acceptance requires a clean strict run.

## Phases

### Wave 1 (detailed): the boundary and the gates

The mechanical half, and the whole of it: after this wave the tools understand the format even though no agent is yet taught to write it. That ordering is deliberate - the prose in wave 2 has to describe output that exists, and TASK-070 exists to make sure it describes the right output. TASK-067 is the exception that proves the rule: it is a hitchhiker, a cheap and independent defect fix that rides along because it touches nothing else here and would otherwise need a plan of its own. Naming it as such matters, because a wave that quietly absorbs unrelated work is a counterexample to the coherence judgment SPEC-015 D-03 asks the planner to make, and this plan should not be the first one to set that example.

- [ ] TASK-066: `planlib.py` - the plan detail-region classifier - complexity: M, depends_on: none, files: [plugin/cli/planlib.py, plugin/cli/tests/test_planlib.py], decisions: [SPEC-015-rolling-wave-planning/D-04, ADR-009-rolling-wave-mechanism/D-01, ADR-009-rolling-wave-mechanism/D-07], lessons: [LESSON-no-agent-bookkeeping, LESSON-type-dir-discovery-needs-content-signal]
  - One function, `classify_lines(text)`, returning `(regions, unterminated_fence)`. `regions` is **sparse**: it maps a 1-based line number to `scoped` or `record` only, and callers treat an absent key as `detailed`. A plan with no `## Later` section therefore returns an empty map and behaves exactly as today.
  - `planlib` also owns the `TASK_LINE` regex, since it is the module both coverage commands read and a library must not import from `commands/`. TASK-069 deletes the local definition in `lesson_coverage.py` and imports this one.
  - **Region rules.** The Later region opens on `^##\s+Later\b` (case-insensitive, so `## Later (intent only)` and `## later` both match, and `## Latergrade` does not) and closes at the next `#` or `##` heading, or EOF; `###` and deeper stay inside it. A record region opens on `^##\s+Waves?\b.*\belaborated\b`, case-insensitive: it matches the canonical `## Wave 1 elaborated` and the shapes an author actually writes around it, such as `## Wave 1 - elaborated (2026-08-12)`, while a promoted `## Wave 2 (detailed)` heading carries no `elaborated` token and stays detailed. Everything else is detailed.
  - **The `commit-upfront:` override.** Inside the Later region, a task line matching the head grammar classifies `detailed` when one of its trailing comma-separated fields *begins* with the name-and-colon token `commit-upfront:`, matched after inline code spans are stripped. Its indented continuation lines carry the same state until the next task line, the first non-blank unindented line, or the end of the region; a blank line carries the current state rather than ending the block. A bare mention mid-sentence and a backticked one never trigger it - TASK-071 and TASK-072 both talk about the flag without carrying it. Because the field is written last on the line, its reason text may contain commas.
  - Fences are stripped internally via `vaultlib.strip_fenced_code`, which preserves the line count, so a `## Later` heading quoted inside a fenced example never opens a region and the returned numbers still index the original text. Inline code spans are stripped the same way for the heading and field matches. CRLF input is normalized first. The `unterminated_fence` flag is passed through to the caller rather than discarded, because a broken fence blanks the rest of the document and would otherwise make an unreadable plan look fully detailed.
  - Automated verification: unittest - a document with no `## Later` returns an empty map; lines under `## Later (intent only)` map scoped and the first line of the following `## Risks` is absent from the map; a `### sub` heading inside Later stays scoped; a second `## Later` heading later in the document opens a second scoped region; a `## Wave 1 elaborated` section appearing *before* the `## Later` heading maps record and does not stop the Later region opening afterwards; `## Later` inside a fenced block opens nothing; `## later` matches and `## Latergrade` does not; `## Wave 1 - elaborated (2026-08-12)` maps its body record and `## Wave 2 (detailed)` does not; TASK-076's line verbatim maps detailed together with its indented bullets and a blank line inside them, and the next plain intent line maps scoped again; both terminator shapes end the override (a following task line, and a following non-blank unindented line); TASK-071's line verbatim stays scoped even though it names the flag, and so does a backticked mention; an unterminated fence returns the flag True; line numbers of a document containing a fenced block align with the original text (assert against a known line); CRLF input produces the same map as LF; an empty document and a document that is only frontmatter return empty maps without raising.
  - Manual verification: run the classifier over this plan file and read the three regions it reports back. A human should be able to point at the `## Later` heading and agree with every line's state without consulting the code, and in particular should agree that TASK-076's `commit-upfront:` block is detailed while the lines above and below it are scoped - including TASK-071's and TASK-072's lines, which mention the flag by name.

- [ ] TASK-067: `decisionslib` stops reading cross-document references as unparsed local decisions - complexity: S, depends_on: none, files: [plugin/cli/decisionslib.py, plugin/cli/tests/test_decisionslib.py]
  - Reproduced during planning, before ADR-009 was normalized: `coverage --against ADR-009-rolling-wave-mechanism` printed `COULD NOT PARSE` and exited 1. The section declared no `D-NN` bullets of its own and referred to `(SPEC-015 D-02)` and `(SPEC-015 D-03)`; the zero-extraction evidence heuristic saw a `D-` token and concluded there were decisions it had failed to read. Normalizing that one ADR removed this vault's instance of the symptom, not the cause: any ADR that declares no local decisions and cites another document's in prose still hard-fails the gate on the whole source.
  - The fix is narrow: before the evidence test runs, remove **qualified** references from the text being examined - a `D-NN` token immediately preceded by a document stem (`SPEC-`, `ADR-`, `PLAN-`, `RESEARCH-` prefixed, separated by a space or a slash) or sitting inside a `[[wikilink]]`. What remains is tested exactly as today. A bare `D-01` with no qualifying name still poisons, because that is the shape of a real local decision the parser could not read.
  - Nothing else in the three-outcome contract moves: parse-miss poisoning on a malformed `- **D-` bullet, the ID-shaped bold-bullet heuristic, and the unterminated-fence signal all keep their current behavior.
  - Automated verification: unittest - an ADR-009-shaped fixture reproducing the real document (a `## Decision` section, no `D-NN` bullets, prose citing `SPEC-015 D-02` and `SPEC-015 D-03` and no wikilink, because the document that surfaced this had none) returns `none-present`; a separate fixture exercises the wikilink branch, citing `[[ADR-009-rolling-wave-mechanism/D-03]]` and returning `none-present` likewise; the first fixture with a bare `D-01` added in prose still returns `could-not-parse`; a malformed `- **D-` bullet still returns `could-not-parse` with the decisions parsed so far; a source-qualified `SPEC-007-decision-coverage-tracing/D-03` in prose is not evidence; every existing test in `test_decisionslib.py` and `test_decision_corpus.py` still passes unchanged. Plus corpus pins that hold after the normalization: `python plugin/cli/compass decisions ADR-009-rolling-wave-mechanism` exits 0 reporting its seven decisions, and `python plugin/cli/compass coverage PLAN-008-rolling-wave` (default sources, no `--against`) exits 0 over all ten.
  - Manual verification: read the amended evidence rule and answer one question - could a real spec whose author mistyped a decision bullet now slip through as `none-present`? Construct that document by hand and confirm it still fails. The heuristic exists to catch exactly that author, and loosening it is the risk this task carries.

- [ ] TASK-068: `compass coverage` reads three states - complexity: M, depends_on: TASK-066, files: [plugin/cli/commands/coverage.py, plugin/cli/tests/test_commands.py], decisions: [SPEC-015-rolling-wave-planning/D-04, ADR-009-rolling-wave-mechanism/D-06]
  - `_claims` collects **every** claim site with the region it sits in, instead of keeping the first one it sees. Precedence per decision: task-line claims decide, and a detailed task line beats a scoped one - `covered (line N)` at the detailed line. If the only task-line claims are intent lines, the decision is `scoped (line N)`. A citation in ordinary prose counts only when no task line claims that decision at all, and then at its own region's state; otherwise a sentence in `## Risks` - which sits after the Later region closes, hence detailed - would quietly upgrade a decision that only an intent line ever promised. `record`-region citations are discarded outright. The gate fails on uncovered and unparseable sources exactly as today, and never on scoped.
  - `--strict` counts `scoped` as uncovered for the exit code and ends the summary `-> FAIL (strict)`. The default stays lenient because that is the gate a plan is approved against; `--strict` is what plan *completion* runs, where a decision still sitting in `scoped` is a decision that was named and never built. TASK-074 records it in the validator's audit and TASK-076's acceptance requires it to exit 0.
  - Summary line becomes `N trackable decision(s) in M source(s): X covered, Y scoped, Z uncovered -> PASS`, with the unparseable clause unchanged. Four assertions in `CoverageCommandTests` match on the old two-state summary string (`test_commands.py` lines 725, 735, 789 and 817 at plan start) and are updated inside this task, not left to fail. For a plan with no `## Later` section the verdict and the exit code are identical before and after; only the summary wording changes, and that change is intended.
  - When `classify_lines` reports an unterminated fence, the command emits a note - the regions were unreadable and every line was treated as detailed - and proceeds. Blanking the regions silently would turn a broken fence into a green run.
  - The module docstring gains the three states and the record-region rule, in the same voice as the rest of the file.
  - Automated verification: unittest - a decision cited only from a line under `## Later` reports `scoped`, counts in the scoped column and exits 0; the same decision cited from a detailed task reports `covered`; cited from both reports `covered` once, at the detailed line, whichever came first in the file; a decision claimed by an intent line and also mentioned by a qualified citation in prose after the Later region stays `scoped`; a decision claimed by no task line but cited in detailed prose is `covered`; cited from nowhere still reports `NOT COVERED` and exits 1; a `commit-upfront:` task inside the Later region yields `covered`, not `scoped`; a citation appearing only inside a `## Wave 1 elaborated` section yields `NOT COVERED`; `--strict` turns a scoped-only plan into exit 1 with `FAIL (strict)` while the same plan exits 0 without the flag, and a plan with nothing scoped gives identical output under both; a plan with no `## Later` section produces the same rows and exit code as before the change; a plan with an unterminated fence prints the note and treats every line as detailed; an unparseable source still fails even when everything else is covered or scoped; exit code is never 2. Plus real-corpus pins: `compass coverage PLAN-006-learning-loop` and `compass coverage PLAN-007-test-quality` both still exit 0.
  - Manual verification: run the command against this plan and read the table. A human must be able to tell, from the table alone and without opening the plan, which decisions are built in wave 1 and which are still only named - and must agree that a `scoped` row is a promise rather than a gap.

- [ ] TASK-069: `compass lesson-coverage` reads three states - complexity: S, depends_on: TASK-066, files: [plugin/cli/commands/lesson_coverage.py, plugin/cli/tests/test_lesson_coverage.py], decisions: [SPEC-015-rolling-wave-planning/D-04, ADR-009-rolling-wave-mechanism/D-06]
  - The same region read, applied to `lessons:` citations. Status gains `scoped` for a lesson cited only from intent lines; a lesson cited from both regions is `cited`. `unresolvable` and `surfaced-but-uncited` are untouched, and so is the exit rule: only an unresolvable citation fails. The `--json` payload gains a `scoped` list beside `cited`.
  - The local `TASK_LINE` definition is deleted and imported from `planlib` instead, so one regex defines a task line for the whole CLI.
  - Summary gains the scoped count. The "no citations" summary is unchanged for a plan with no `lessons:` field anywhere. An unterminated fence produces the same note TASK-068 defines.
  - Automated verification: unittest - a lesson cited only from a Later-region task line reports `scoped` and exits 0; cited from a detailed task reports `cited`; cited from both reports `cited` once; an unresolvable citation from the Later region still exits 1, because a typo is a typo in either region; the `--json` payload carries the scoped entry with its citing tasks; a plan with no `## Later` produces the previous output; an unterminated fence prints the note; never exits 2. Plus corpus pins: `compass lesson-coverage PLAN-007-test-quality` and `compass lesson-coverage PLAN-006-learning-loop` still exit 0 with their previous row sets.
  - Manual verification: run it against this plan and confirm the scoped row for [[LESSON-human-practice-rationing-assumes-human-scarcity]] reads as "this lesson binds work that is not specified yet" rather than as an omission. If a reader cannot tell scoped from uncited at a glance, the wording is wrong.

- [ ] TASK-070: prototype - can a prose citation upgrade a scoped decision on a real plan? - complexity: XS, kind: prototype, depends_on: TASK-068, TASK-069, files: [], decisions: [SPEC-015-rolling-wave-planning/D-02, ADR-009-rolling-wave-mechanism/D-02]
  - **Question:** on a document written by a person rather than by a fixture, does a qualified citation sitting in ordinary prose change a decision's verdict - and therefore what must the planner brief forbid or require about where citations may appear?
  - **Method:** one probe, not a battery. Take a scratch copy of this plan, add a single qualified citation for a decision that only an intent line claims (`ADR-009-rolling-wave-mechanism/D-04` is the clean case) to a sentence in `## Risks`, and run `compass coverage` against the copy. Record whether that row reads `scoped` or `covered`, verbatim with its exit code. The regression runs over PLAN-006, PLAN-007 and this plan are already automated verification inside TASK-068 and TASK-069; repeating them here would be duplicated evidence, not a probe. This one run is the only question the wave has not already answered.
  - **Deliverable:** the answer, written into this task's phase report at `.compass/tmp/phase-reports/<phase-id>/task-070-build.md` - what the verdict was, and what constraint the planner brief must state about citation placement. The elaboration step transcribes it into the `## Wave 1 elaborated` section, since a task cannot record its own deliverable in a section that does not exist until after the task completes. That answer is the input to TASK-071 and TASK-072, which is why this task sits before the elaboration step rather than after it.
  - This is a prototype under SPEC-015 D-02: its output is an answer, not shipped code, so it carries no test-first station and routes through `compass test-checkpoint record TASK-070 --not-required`. If it finds a defect, the fix is opened in this wave and TASK-068 or TASK-069 reopens - a prototype that discovers something and files it for later is a prototype that wasted the wave it was in.
  - Automated verification: the command, its full output and its exit code are recorded in the phase report and re-running the recorded command reproduces them; `compass test-checkpoint verify TASK-070` is satisfied by the `--not-required` record.
  - Manual verification: the human reads the answer and rules whether the region rule is sound enough to teach to the planner. A "yes, with a constraint" answer is the expected shape; a "no" answer stops wave 2 and reopens the boundary design, which is precisely what a prototype is for.

**Pause point and elaboration step (the mid-plan exercise).** The elaboration step is build step **7d**. It runs after 7a assembles the phase reports - which are its input, TASK-070's answer among them - and after 7b extracts lessons, and before 7c pauses for the human. In `all-phases` mode the human pause at 7c is skipped; 7d is not, because it is the mechanism under test. It must complete before the next phase's step 3, so that no tester is ever handed a task with no verification bullets to write against.

The step itself: read the wave's verified outcomes - TASK-070's recorded answer, the two gates' real output, whatever the region rule turned out to require - then promote the next coherent set of intent lines into full task blocks, consuming each line by moving it into the detailed wave, never editing it where it sits. Promoted blocks land as a new `### Wave N (detailed)` section under `## Phases` above `## Later`, the consumed intent lines are deleted from the Later region, and their task ids move from `backlog.md` into `active.md`. Then append a `## Wave N elaborated` section that records, for every promoted line, either what changed and which verified outcome changed it or literally "unchanged - intent held"; a promoted line with no entry is a defect rather than a shortcut, and until TASK-074 exists there is nothing else guarding it. That section quotes intent lines only inside fences, because a task block written there would claim nothing and would flip its own decisions back to NOT COVERED. Present the delta to the human (what was learned, what the next wave is); do not re-approve the plan.

### Wave 2 (detailed): the authoring surfaces

Promoted by the wave-1 elaboration from the Later list's authoring group. Each block carries what wave 1 verified: the landed region rules, the live gate behavior, and TASK-070's recorded answer on citation placement.

- [ ] TASK-071: planner brief teaches the format - complexity: S, depends_on: none, files: [plugin/templates/agents/planner.md], decisions: [SPEC-015-rolling-wave-planning/D-03, SPEC-015-rolling-wave-planning/D-04, ADR-009-rolling-wave-mechanism/D-01, ADR-009-rolling-wave-mechanism/D-03], lessons: [LESSON-human-practice-rationing-assumes-human-scarcity]
  - The brief flips from "specify all tasks" to: specify the current wave fully - the frontier judgment, one coherent phase or concern, no numeric caps, never one task alone unless only one is workable - and list the rest under `## Later (intent only)` as one head-grammar line each, flagging `commit-upfront:` exceptions with the reason last on the line.
  - Distribution rule: intent lines go to `backlog.md`, never `active.md`; the elaboration step moves promoted ids up.
  - Citation placement, from TASK-070's recorded answer: every decision belongs in some task line's `decisions:` field, detailed or intent; prose that discusses a decision names it bare (`D-04`) or in backticks, both of which claim nothing. The hazard the brief must state is not prose upgrading a promise - task lines always win - but prose *manufacturing* one: a qualified citation for a decision no task line names anywhere reads `covered` from detailed prose alone and passes even `--strict` with nothing committed to build it.
  - The canonical record heading is `## Wave N elaborated`; an intent line quoted inside a detailed block is fenced or backticked.
  - Automated verification: grep the template for the frontier wording (no caps, never one task alone), the `## Later` instruction, the backlog.md distribution rule, `commit-upfront:` with reason-last, the canonical heading, the fence-or-backtick rule, and the decisions-live-in-task-lines constraint with the manufactured-promise hazard; `python plugin/cli/compass validate` clean; zero occurrences of "specify all tasks".
  - Manual verification: read the amended brief as if you were the planner writing your first rolling-wave plan and confirm nothing forces you to detail far work, and that the citation rule is stated as a rule, not a warning.

- [ ] TASK-072: `plan` skill carries the format and the iterate-vs-elaborate line - complexity: M, depends_on: none, files: [plugin/skills/plan/SKILL.md], decisions: [SPEC-015-rolling-wave-planning/D-04, ADR-009-rolling-wave-mechanism/D-01, ADR-009-rolling-wave-mechanism/D-05]
  - The format section states what wave 1 landed: the `## Later (intent only)` boundary and its region semantics, the intent-line head grammar, the `commit-upfront:` field (name-and-colon, field position, reason last), the canonical `## Wave N elaborated` heading and that its region claims nothing, the fence-or-backtick rule for quoted intent lines, and the gate's live behavior - `scoped` rows and the scoped summary clause appear only when a Later region exists, and `--strict` is the plan-completion gate.
  - The iterate-vs-elaborate line, per ADR-009 D-05: shape changes (scope, dropped goals, new phases) are plan-iteration with the human gate exactly as today; elaboration is the build flow's own step, presents a delta, and never re-approves. The skill's iterate-mode ripple table gains a row for wave sections (a shape change that invalidates an unpromoted intent line supersedes it in the record section, never edits it in place).
  - The citation-placement rule from TASK-070's answer, stated where the skill documents `decisions:` fields.
  - Automated verification: greps for the boundary, the grammar elements, the canonical heading, claims-nothing, fence-or-backtick, scoped-only-when-Later, `--strict`, the iterate-vs-elaborate distinction, the supersede-not-edit rule, and the citation constraint; `python plugin/cli/compass validate` clean.
  - Manual verification: a reader who knows today's plan skill reads only the diff and can answer: when do I iterate, when do I elaborate, and who approves what. If any of the three answers takes more than a sentence, the wording failed.

- [ ] TASK-077: the obsidian plan template starts plans in the format - complexity: S, depends_on: none, files: [plugin/skills/obsidian/SKILL.md], decisions: [ADR-009-rolling-wave-mechanism/D-01]
  - The plan template gains a `## Later (intent only)` section holding one example intent line in head grammar and one `commit-upfront:` example with the field last; a one-line note states that `## Wave N elaborated` sections are appended by the elaboration step, not authored upfront. The task-line grammar documentation names `decisions:` and `lessons:` as the citation home per TASK-070's rule.
  - Automated verification: grep the template for the section, both example lines, the appended-not-authored note, and the citation-home sentence; `python plugin/cli/compass validate` clean.
  - Manual verification: copy the template into a scratch plan, run `compass coverage` against it, and confirm the example intent line classifies scoped and nothing errors - a template that starts plans broken is worse than no template.

### Wave 3 (detailed): the consuming side

Promoted by the wave-2 elaboration. Each block is written against what wave 2 actually landed: the planner brief's wording, the plan skill's region rules including the reopening subtlety and the wave-placement trap its review surfaced, and the live elaboration incident wave 1's own execution recorded.

- [ ] TASK-073: `build` skill gains the elaboration step 7d - complexity: M, depends_on: none, files: [plugin/skills/build/SKILL.md], decisions: [SPEC-015-rolling-wave-planning/D-02, ADR-009-rolling-wave-mechanism/D-04, ADR-009-rolling-wave-mechanism/D-05]
  - Step 7d sits after 7a (phase reports - its input) and 7b (lessons), before 7c (pause); `all-phases` skips 7c only; 7d completes before the next phase's step 3 so no tester is handed a task without verification bullets.
  - The step: read the wave's verified outcomes (phase reports, gate output, prototype answers), promote the next coherent set of intent lines into full task blocks placed as a `### Wave N (detailed)` heading under `## Phases` above `## Later` - a level-3 heading does not close a Later region, so placement above the boundary is what keeps promoted blocks detailed (the trap wave 2's review named); delete consumed intent lines; move promoted ids from `backlog.md` to `active.md`; append the canonical `## Wave N elaborated` section recording, per promoted line, what changed and which verified outcome changed it, or literally "unchanged - intent held"; quote superseded intent lines only inside fences.
  - Editing discipline, from wave 1's recorded incident: structural edits anchor on whole heading lines, never substring matches - a backticked mention of the boundary heading in prose is not the boundary, and a substring replace spliced this plan's own Goal paragraph before the gates caught it.
  - Prototype outcomes: a `kind: prototype` task's recorded answer is elaboration input (SPEC-015 D-02); its phase report is where the answer lives.
  - Automated verification: grep for 7d's position (after 7b, before 7c), the all-phases rule, the before-next-step-3 requirement, the placement instruction with the level-3 trap, the backlog-to-active move, the canonical heading, the per-line changed-or-held record rule, the fence rule, and the line-anchored editing discipline; `python plugin/cli/compass validate` clean.
  - Manual verification: walk one imagined wave boundary through the amended step on paper and confirm every write it instructs has an unambiguous anchor.

- [ ] TASK-074: validator audits the wave record - complexity: S, depends_on: none, files: [plugin/templates/agents/validator.md], decisions: [ADR-009-rolling-wave-mechanism/D-07]
  - A report-only sibling of the existing coverage audits, same evidence-block form: run `compass coverage <plan> --strict` (the completion gate - scoped rows are decisions named and never built) and, for plans carrying wave sections, classify: promoted lines with no wave-section entry; entries with neither a changed-because nor an "unchanged - intent held"; intent lines edited in place rather than superseded (detectable: an intent line whose text differs from its fenced quote in the record); elaborated detail whose citations never bound (ordinary uncovered at that point). Gates on nothing.
  - Automated verification: grep for `--strict`, the evidence block, the four classifications, report-only phrasing with no block/fail verdict language; `python plugin/cli/compass validate` clean.
  - Manual verification: read the step and confirm a validator running mid-plan (waves still open) reports scoped rows as promises, not defects.

- [ ] TASK-075: methodology describes the build-learn-elaborate loop - complexity: S, depends_on: none, files: [plugin/skills/methodology/SKILL.md], decisions: [SPEC-015-rolling-wave-planning/D-04]
  - One proportionate subsection beside the pipeline and the learning loop: plans hold a detailed wave and an intent list; waves are judged frontiers, never counts; elaboration fires at the merge gate on verified outcomes and presents a delta; approval attaches once to near detail plus far shape; `--strict` closes the loop at plan completion. Points at the plan skill for the format's letter.
  - Automated verification: grep for the loop's five elements and the plan-skill pointer; `python plugin/cli/compass validate` clean.
  - Manual verification: the section reads as a description of how planning works, not as an announcement of a change.

## Later (intent only)

The one remaining line, held to the end under its own rule.

TASK-076 is written in full despite its distance, under the `commit-upfront:` rule.

- [ ] TASK-076: install refresh and acceptance - complexity: M, depends_on: TASK-071, TASK-072, TASK-073, TASK-074, TASK-075, TASK-077, files: [.claude/], decisions: [SPEC-015-rolling-wave-planning/D-04, ADR-009-rolling-wave-mechanism/D-01], commit-upfront: the acceptance battery is the same shape every Compass plan runs and its detail does not depend on anything wave 1 or wave 2 produces
  - Copy `plugin/cli`, `plugin/skills/*` and `plugin/templates/agents/*` into `.claude/` (or run `/compass:update`), then run acceptance from the installed copy, which is the only way the refresh is proven.
  - Automated verification: `python -m unittest discover -s plugin/cli/tests` green with the new tests included (507 at plan start, higher here), green meaning no failures outside `compass test-checkpoint open-ids`; `python .claude/cli/compass doctor` exits 0; `python .claude/cli/compass coverage PLAN-008-rolling-wave --strict` exits 0 - under `--strict` that is the same statement as zero scoped rows, and every decision this plan named must be built by the time it closes; `python .claude/cli/compass lesson-coverage PLAN-008-rolling-wave` exits 0; `compass coverage` and `compass lesson-coverage` still exit 0 on PLAN-006 and PLAN-007.
  - Manual verification: count what this plan actually cost the human - one approval, plus one delta per elaboration, plus any mid-build amendment - against the one-approval baseline SPEC-015 success criterion 3 sets, and for each wave delta answer whether reading it cost less attention than the mid-build amendment it was supposed to replace. Nobody has measured that before, which is the point of measuring it here. Then answer the other two criteria from the document itself: did at least two elaboration steps run, and did a knowledge item from an earlier wave demonstrably change a later wave's detail in a way the wave sections show. A plan whose wave sections record nothing that changed is the falsification signal, not a clean run.

## Parallel-safe tasks

- **Wave 1:** TASK-066 and TASK-067 are file-disjoint and depend on nothing - safe together. TASK-068 and TASK-069 both depend on TASK-066 and touch different command and test files - safe together. TASK-070 runs alone, after both.
- **Wave 2 (as named):** TASK-071, TASK-072 and TASK-077 each own exactly one file and none is shared, so all three are file-disjoint. Whether they are also *knowledge*-disjoint is a question for the elaboration step, not for now.
- **Wave 3 (as named):** TASK-073, TASK-074 and TASK-075 are file-disjoint from each other; TASK-076 copies all of them into `.claude/` and therefore runs alone, last.

## Ownership and contact points

- `plugin/cli/planlib.py` - created by TASK-066, read by TASK-068 and TASK-069. No task edits it after creation.
- `plugin/cli/commands/coverage.py` and `plugin/cli/tests/test_commands.py` - exclusive to TASK-068 (the test file holds `CoverageCommandTests`, including the four summary assertions that change).
- `plugin/cli/commands/lesson_coverage.py` and `plugin/cli/tests/test_lesson_coverage.py` - exclusive to TASK-069, which also removes the local `TASK_LINE` and imports `planlib`'s.
- `plugin/cli/decisionslib.py` and `test_decisionslib.py` - exclusive to TASK-067.
- `plugin/cli/maincli.py` - **not touched by this plan.** No new command is registered, so the usual `COMMAND_SPECS` merge-order contact point does not exist here. `--strict` is a flag on an existing command, parsed inside `coverage.py`.
- Later-list ownership, one file each and no sharing: TASK-071 `plugin/templates/agents/planner.md`, TASK-072 `plugin/skills/plan/SKILL.md`, TASK-073 `plugin/skills/build/SKILL.md`, TASK-074 `plugin/templates/agents/validator.md`, TASK-075 `plugin/skills/methodology/SKILL.md`, TASK-077 `plugin/skills/obsidian/SKILL.md`. Agent-template frontmatter and body are edited by a single task each, so the collision shape that needs merge-order rules does not arise. TASK-076 owns `.claude/` and runs alone.

## Risks

- **A citation in plan prose after the `## Later` heading claims scoped by accident.** The region rule attributes by position, and plans carry prose, not only task lines. Mitigations: the region closes at the next `##` heading, so it cannot swallow `## Risks` or a coverage table; prose citations only count when no task line claims the decision (TASK-068's precedence rule); TASK-070 probes exactly that rule against a real document before any agent is taught the format, and the constraint it finds is what TASK-071 states.
- **Scoped becomes a parking lot.** A plan could scope every decision and pass the gate, which would satisfy the mechanism and defeat SPEC-015's Need 5. Mitigations: an unclaimed decision still fails; `--strict` makes scoped fail for the caller that should not tolerate it; the validator's wave audit (TASK-074) runs it at plan close; TASK-076's acceptance requires a clean strict run on this plan itself.
- **Elaboration grows into the ceremony it replaced.** SPEC-015 falsification criterion 2, and the one this plan is most likely to trip: a delta presentation that turns into a review turns into an approval. Mitigations: ADR-009 fixes the delta as "what was learned, what the next wave is"; this plan runs the step twice and TASK-076's manual verification counts the human's touchpoints against the one-approval baseline rather than asking whether it felt heavy.
- **Promotion is a text move, and text moves lose things.** Elaboration deletes an intent line and writes a task block in a different section; a line could be dropped, or promoted without its citations, and the gate would report the decision uncovered at exactly the moment the work started. Mitigations: the wave section requires a per-line entry, so a silently dropped line has no entry to show; TASK-074 audits promoted lines against their entries; the `NOT COVERED` failure is loud, immediate, and lands on the wave being elaborated.
- **Loosening the `could-not-parse` heuristic hides a real malformed decision.** TASK-067 trades a small amount of strictness for a gate that does not fail on a legitimate ADR. Mitigation: only *qualified* references are removed and a bare `D-NN` still poisons; the manual verification constructs the mistyped-bullet document by hand and confirms it still fails.
- **The far list is under-specified into improvisation.** SPEC-015 falsification criterion 1, the opposite failure from the one above. Mitigation: intent lines name the file they touch and the decision they serve, and they distribute to `backlog.md` only - the build flow's task selection reads `active.md`, which a task reaches only when the elaboration step moves it there, and it moves there only with full detail attached.

## Inherited questions

SPEC-015's four open questions were answered by the research and closed by ADR-009: wave boundary (frontier judgment, no caps), record location (per-wave sections appended to the plan), far-task coverage (three states, scoped never fails), and the planner brief (specify the wave, list the rest). Nothing is deferred into this plan. One question the ADR did not anticipate surfaced during planning and was ruled before approval.

- **Should ADR-009's `## Decision` section be normalized into `D-NN` bullets?** Ruled yes and executed (human, 2026-08-11). ADR-006, ADR-007 and ADR-008 all carry `- **D-NN:**` bullets; ADR-009 stated its mechanism in bold-lead paragraphs, so none of its seven decisions was individually trackable and the gate never checked that the ADR's own choices survived into the plan - the exact gap [[SPEC-007-decision-coverage-tracing]] exists to close. The section is now seven bullets (D-01 format, D-02 prototypes, D-03 boundary, D-04 loop, D-05 approval, D-06 coverage, D-07 record), each claimed by the task that implements it.
- TASK-067 lands regardless of that ruling. The `could-not-parse` defect it fixes is not specific to ADR-009: any ADR that declares no local decisions and cites another document's in prose fails the gate the same way, and the normalization removed this plan's instance of the symptom without touching the cause.

## Verification of this plan

Both gates were run against the draft after ADR-009's decisions were normalized. Default sources (the plan's own `depends_on`, filtered to specs and decisions) cover both documents, so the run below is the one the approval gate performs.

```
$ python plugin/cli/compass coverage PLAN-008-rolling-wave
compass coverage: note: 25 bare D-NN token(s) in plans/PLAN-008-rolling-wave.md claim nothing; a citation is source-qualified: <doc-name>/D-NN
compass coverage: plans/PLAN-008-rolling-wave.md
source                          decision  trackable  status
SPEC-015-rolling-wave-planning  D-02      yes        covered (line 117)
SPEC-015-rolling-wave-planning  D-03      yes        covered (line 137)
SPEC-015-rolling-wave-planning  D-04      yes        covered (line 85)
ADR-009-rolling-wave-mechanism  D-01      yes        covered (line 85)
ADR-009-rolling-wave-mechanism  D-02      yes        covered (line 117)
ADR-009-rolling-wave-mechanism  D-03      yes        covered (line 137)
ADR-009-rolling-wave-mechanism  D-04      yes        covered (line 140)
ADR-009-rolling-wave-mechanism  D-05      yes        covered (line 138)
ADR-009-rolling-wave-mechanism  D-06      yes        covered (line 101)
ADR-009-rolling-wave-mechanism  D-07      yes        covered (line 85)
summary: 10 trackable decision(s) in 2 source(s): 10 covered, 0 uncovered -> PASS
EXIT=0
```

Run per source, `--against SPEC-015-rolling-wave-planning` reports `3 trackable decision(s) in 1 source(s): 3 covered, 0 uncovered -> PASS` (EXIT=0) and `--against ADR-009-rolling-wave-mechanism` reports `7 trackable decision(s) in 1 source(s): 7 covered, 0 uncovered -> PASS` (EXIT=0). The bare-token note is expected and matches [[PLAN-006-learning-loop]] and [[PLAN-007-test-quality]]: prose refers to decisions by local ID, which by design claims nothing.

```
$ python plugin/cli/compass lesson-coverage PLAN-008-rolling-wave
compass lesson-coverage: plans/PLAN-008-rolling-wave.md
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

`python plugin/cli/compass validate` reports `0 error(s), 5 warning(s)` and exits 0; all five warnings are pre-existing vault-wide items (three missing frontmatter fields elsewhere, the hot-path token cap) and none is raised against this plan.

**What these numbers mean today, and what they must mean after wave 1.** Both runs above are the *binary* gate: it scans the whole plan body and cannot see the `## Later` boundary, so a citation on an intent line reads `covered`. After TASK-068 and TASK-069 land, re-running the same two commands must reclassify **exactly four rows** to `scoped` and leave the other six `covered`, with the exit codes still 0. That reclassification is the acceptance test for wave 1, and this section is the before-image it is measured against.

The four that must move are the ones whose only task-line claim is an intent line: SPEC-015 D-03 and ADR-009 D-03 (both at line 137, TASK-071), ADR-009 D-05 (line 138, TASK-072) and ADR-009 D-04 (line 140, TASK-073). The six that must not move include two that could be mistaken for movers: ADR-009 D-01 and D-07 are also claimed from intent lines, but TASK-066 claims them at line 85 in the detailed wave, and a detailed claim beats a scoped one - reporting them `scoped` would be a defect in TASK-068's precedence rule, not a success. Expected after-image summary: `10 trackable decision(s) in 2 source(s): 6 covered, 4 scoped, 0 uncovered -> PASS`, exit 0. On the lesson side, `LESSON-human-practice-rationing-assumes-human-scarcity` must move to `scoped` (TASK-071 is its only citer) while the two lessons TASK-066 cites stay `cited`.


## Wave 1 elaborated

Wave 1 outcomes consumed: TASK-066..069 landed and verified against run evidence (suite 552, checkpoints landed, open set empty); the live gate on this plan produced the predicted after-image exactly (6 covered, 4 scoped, 0 uncovered); TASK-070's probe answered no - prose cannot upgrade a task-line claim - and surfaced the real hazard, a prose citation manufacturing a promise no task line made (report: `tmp/phase-reports/PLAN-008-wave-1/task-070-build.md`). Hitchhiker discovery, out of wave scope but recorded: three real `unittest -v` output formats broke the checkpoint verifier's run-evidence parser and were fixed with pinned regressions during landing.

Promoted lines:
- TASK-071 - changed: gains the citation-placement rule and the manufactured-promise hazard from TASK-070's answer; neither was in the intent line.
- TASK-072 - changed: gains the same citation rule, plus the landed gate behavior the skill must describe (scoped clause only when a Later region exists; `--strict` as the completion gate) - wording that could not have been written before wave 1 fixed it.
- TASK-077 - unchanged - intent held.

Superseded intent lines, quoted for the record:

```
- [ ] TASK-071: planner brief flips from "specify all tasks" to "specify the current wave fully - the frontier judgment, no caps, never one task alone - list the rest as intent, flag commit-upfront: exceptions"; it also states that intent lines distribute to backlog.md and never to active.md, pins the canonical Wave-N-elaborated heading, and requires an intent line quoted inside a detailed block to be fenced or backticked
- [ ] TASK-072: plan skill carries the format - the Later boundary, intent-line grammar, the commit-upfront: field, the canonical Wave-N-elaborated heading, the fence-or-backtick rule for quoted intent lines - and draws the line between iterate and elaborate
- [ ] TASK-077: the plan template in the obsidian skill gains the Later (intent only) section, the intent-line grammar and the commit-upfront: field
```

## Wave 2 elaborated

Wave 2 outcomes consumed: TASK-071/072/077 landed with review-verified accuracy against the wave-1 code - the plan-skill review alone corrected six factual claims, surfacing the region-reopening rule (a level-1/2 heading past Later is detailed again) and the wave-placement trap (a level-3 heading does not close a Later region); the template's example intent line verified scoped in a live scratch run; wave 1's own elaboration recorded a real substring-anchor splice the gates caught.

Promoted lines:
- TASK-073 - changed: gains the placement instruction with the level-3 trap and the line-anchored editing discipline, both from wave-2 review findings and the wave-1 incident; neither was in the intent line.
- TASK-074 - changed: the in-place-edit classification gains its detection method (intent text differing from its fenced record quote), derivable only now that a real record section exists to compare against.
- TASK-075 - unchanged - intent held.

Superseded intent lines, quoted for the record:

```
- [ ] TASK-073: build skill gains the elaboration step as step 7d - after 7a's phase reports and 7b's lessons, before 7c's pause, and completed before the next phase's step 3 - promoting elaborated lines upward into a new detailed wave section and moving their ids from backlog.md to active.md; stations, checkpoints, fix loop and the open-ids green definition untouched
- [ ] TASK-074: validator audits the wave sections - elaborated detail that never got cited, promoted lines with no wave-section entry, intent lines edited in place rather than superseded, and decisions still scoped at plan close via compass coverage --strict
- [ ] TASK-075: methodology skill describes the build-learn-elaborate loop alongside the pipeline it sits inside
```
