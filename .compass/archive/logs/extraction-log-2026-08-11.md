# Extraction Log - 2026-08-11

## Opportunity OPP-20260811T171715895315Z (interval) - 2026-08-11T17:17:15Z

### Triggers
- fix-loop >=2: no
- validator Deviation (problem): no
- debug invoked: no
- STOP-and-report: no
- plan revised: no
- validator-finished / debug-finished (signal): no
- handoff-written (signal): no
- interval reached with signal(s): yes (vault-write, subagent-finished)

### Candidates

1. **Source:** `lessons/LESSON-remove-context-before-adding.md` + `tmp/subagent-captures/2026-08-10T00-36-10_unknown.md`
   **Finding:** v0.6.7 fixed the double-ask by subtraction - removing autopilot's unowned checkpoint and compressing the rule net-negative - after v0.6.6 tried added prose.
   **Anti-list:** matched bucket "Anything already documented in a spec, ADR, plan, vision, or CLAUDE.md" (the active lesson's own body already names this episode: "a double-ask lived in a skill's extra unowned checkpoint, not in a missing rule")
   **Outcome:** rejected - same episode that authored the lesson on 2026-08-09, not an independent recurrence, and no correction to make

2. **Source:** `specs/SPEC-015-rolling-wave-planning.md`
   **Finding:** Uniform task detail across a whole plan is speculative for far tasks; builders stop on "codebase contradicts the plan" for tasks specced many tasks ago.
   **Anti-list:** matched bucket "Anything already documented in a spec, ADR, plan, vision, or CLAUDE.md" (SPEC-015 Problem section, approved 2026-08-11); also "Unresolved or untested recommended approaches recorded as if validated" - the rolling-wave remedy is a falsifiable hypothesis with unmet success criteria
   **Outcome:** rejected

3. **Source:** `specs/SPEC-014-update-safe-customizations.md`
   **Finding:** A survive-update mechanism existed on exactly one surface (`models.yaml` + `apply-models`) and was never generalized, so every other customization surface was silently destroyed by update - twice, with "retype it from the ADR" as the standing workaround.
   **Anti-list:** matched bucket "Anything already documented in a spec, ADR, plan, vision, or CLAUDE.md" (SPEC-014 Problem section states the precedent and the gap verbatim); neighboring rule already active as `LESSON-installer-removes-only-what-it-installed.md`
   **Outcome:** rejected

### Contradiction check
Catalog rows overlapping `area: methodology` / planning tags read (`LESSON-adversarial-plan-review-before-build`, `LESSON-remove-context-before-adding`, `LESSON-pin-the-motivating-datum`). No evidence in the window falsifies or narrows an active lesson: SPEC-015 changes what detail exists to review, not whether plans get adversarial review before approval. No revise or archive payload prepared.

### Notes
Remaining evidence carried no candidate: `lessons/LESSON-revert-to-prove-a-regression-test.md` and `lessons/LESSON-append-only-index-misses-mutations.md` are the window's vault writes themselves, not findings about them; the five `tmp/subagent-captures/` files are handoff and approval one-liners ("approve both", "approved", fleet-ship status) with no finding content.

### Summary
Candidates: 3 | Written: 0 | Rejected: 3 | Errors: 0

## Opportunity OPP-20260811T181114837830Z (interval) - 2026-08-11T18:11:14Z

### Triggers
- fix-loop >=2: no
- validator Deviation (problem): no
- debug invoked: no
- STOP-and-report: no
- plan revised: no
- validator-finished / debug-finished (signal): no
- handoff-written (signal): no
- interval reached with signal(s): yes (subagent-finished, vault-write)

### Candidates

1. **Source:** `research/RESEARCH-rolling-wave-synthesis.md` walkthrough exchange (window context)
   **Finding:** The synthesis walkthrough was delivered in the vocabulary the research invented (frontier, appetite, elaboration record); the human could not rule until it was re-explained in plain words.
   **Anti-list:** passed - not a style preference but a failed decision surface with a measured cost (one round trip); the standing preference lives in the human's private memory and one handoff, neither of which reaches an agent-facing surface, and no spec, ADR, or CLAUDE.md states it
   **Outcome:** `lesson-write` returned `created: LESSON-walkthroughs-in-the-humans-words.md`

2. **Source:** `research/RESEARCH-rolling-wave-synthesis.md` (Tension 1, Open point 1) vs `specs/SPEC-015-rolling-wave-planning.md` D-03
   **Finding:** The synthesis folded Shape Up's per-wave size budget into its recommended mechanism on 1-of-3 axis support; the human cut it and banned the framing, because size-rationing manages a human throughput scarcity agents do not have.
   **Anti-list:** passed - SPEC-015 D-03 and ADR-009's Rejected list record the ruling for wave sizing only; the rule for how a future synthesis should treat an imported rationing mechanism is stated nowhere, and the finding is about what already happened, not about whether rolling-wave works
   **Outcome:** `lesson-write` returned `created: LESSON-human-practice-rationing-assumes-human-scarcity.md`

3. **Source:** `specs/SPEC-015-rolling-wave-planning.md` D-02, `decisions/ADR-009-rolling-wave-mechanism.md`
   **Finding:** Prototype tasks are first-class near work - a named question in, an answer out, satisfying the testing mandate by their nature.
   **Anti-list:** matched bucket "Anything already documented in a spec, ADR, plan, vision, or CLAUDE.md" (SPEC-015 D-02 and ADR-009 "Prototype tasks" verbatim); also "Unresolved or untested approaches" - the mechanism is designed, not yet built or run
   **Outcome:** rejected

### Contradiction check
Catalog rows overlapping `area: methodology` and planning/review tags read (`LESSON-adversarial-plan-review-before-build`, `LESSON-remove-context-before-adding`, `LESSON-pin-the-motivating-datum`, `LESSON-tag-index-trades-cost-for-directed-retrieval`). Nothing in the window falsifies or narrows an active lesson: the overruled size budget is a new rule about importing practice, not a correction to any lesson's claim. No revise or archive payload prepared.

### Notes
The thirteen `tmp/subagent-captures/` files in the window are one-line human nudges ("status?", "continue", "as recommended") with no finding content. `tmp/extraction-log-2026-08-11.md` is this log itself. The three axis research documents carried no candidate independent of the synthesis that consolidates them.

### Summary
Candidates: 3 | Written: 2 | Rejected: 1 | Errors: 0

## Opportunity OPP-20260811T190123383649Z (interval) - 2026-08-11T19:01:23Z

### Triggers
- fix-loop >=2: no
- validator Deviation (problem): no
- debug invoked: no
- STOP-and-report: no
- plan revised: no
- validator-finished / debug-finished (signal): no
- handoff-written (signal): no
- interval reached with signal(s): yes (subagent-finished, vault-write)

### Candidates

1. **Source:** `plans/PLAN-008-rolling-wave.md` TASK-066 (line 86) vs its own Later region (lines 125, 126), via the mechanism review lens
   **Finding:** The `commit-upfront` override matches the bare word anywhere in a task line; two of the plan's own intent lines mention the flag while describing it, so they classify `detailed` and the wave-1 acceptance test at line 203 (those exact rows must reclassify to `scoped`) becomes unpassable. Code-span stripping, already applied for the heading match, catches line 126 and not line 125 - the mention is bare prose.
   **Anti-list:** passed - not a code pattern (the fix is unwritten and the rule is about matcher design, not about this file), and no spec, ADR or plan states it; PLAN-008 line 86 states the defective rule only
   **Outcome:** `lesson-write` returned `refined: LESSON-wikilink-validator-skip-code.md` - the matched lesson's remedy (strip fenced blocks and inline code spans) is shown insufficient by this instance, so the rule generalized from code-region exclusion to grammar-position anchoring, and the summary and tags were updated in the file and the catalog row

2. **Source:** window review round on `plans/PLAN-008-rolling-wave.md` (3 lenses dispatched, 2 returned)
   **Finding:** The lenses found a live self-falsification the author could not see, and the elaborated-block placement hole was found independently by two of them.
   **Anti-list:** passed as a recurrence instance, not as new content
   **Outcome:** `lesson-write` returned `recurrence: LESSON-adversarial-plan-review-before-build.md` (seen 2026-08-11, score 5 -> 6)

3. **Source:** `plans/PLAN-008-rolling-wave.md` line 22
   **Finding:** Writing an artifact in the format it specifies exposes self-falsifications a review of an ordinary artifact cannot produce - dogfood as acceptance test.
   **Anti-list:** matched bucket "Anything already documented in a spec, ADR, plan, vision, or CLAUDE.md" - PLAN-008 line 22 states the technique, its rationale and its timing benefit verbatim ("This plan is written in the format it implements, and that is its acceptance test... that finding lands before any agent is taught to write it"). A lesson would add only that it paid off.
   **Outcome:** rejected

### Contradiction check
Catalog rows overlapping the finding's tags read: `LESSON-hook-payloads-observe-before-coding` (payload shape assumed vs observed - not falsified here; PLAN-008's field shape was known and the matcher was loose), `LESSON-wikilink-validator-skip-code` (matched, routed to refinement above), `LESSON-type-dir-discovery-needs-content-signal`, `LESSON-adversarial-plan-review-before-build`. Nothing in the window falsifies an active lesson's claim. No revise or archive payload prepared.

### Notes
The twelve `tmp/subagent-captures/` files in the window are one-line human nudges ("go ahead with the plan", "ok reviews", "apply the amendments once all reviews are in") with no finding content. `lessons/LESSON-walkthroughs-in-the-humans-words.md` and `lessons/LESSON-human-practice-rationing-assumes-human-scarcity.md` are the previous pass's own writes, not findings about them. `tmp/extraction-log-2026-08-11.md` is this log. ADR-009's normalization to `D-NN` bullets carried no candidate of its own: PLAN-008's "Inherited questions" records the ruling and TASK-067 owns the underlying `decisionslib` defect.

### Summary
Candidates: 3 | Written: 1 | Recurrence: 1 | Rejected: 1 | Errors: 0

## Opportunity OPP-20260811T220204623941Z (interval) - 2026-08-11T22:02:04Z

### Triggers
- fix-loop >=2: no
- validator Deviation (problem): no
- debug invoked: no
- STOP-and-report: no
- plan revised: no
- validator-finished / debug-finished (signal): no
- handoff-written (signal): no
- interval reached with signal(s): yes (subagent-finished, vault-write)

### Candidates

1. **Source:** `teammate:pretest-067` artifacts - `tmp/red-TASK-067.txt`, `tmp/test-checkpoints/TASK-067.json`, `plugin/cli/commands/test_checkpoint.py:32`
   **Finding:** The first live pre-build station on an existing module produced a red run of 40 tests with 3 failures; the checkpoint recorded all 40 ids and stored the red run as an opaque path, so `verify --against-run`'s "now passes" requirement is carried by 3 tests and 37 already-green ones ride along unproven.
   **Anti-list:** passed - not a code pattern (the mechanism gap is real but the rule is about what a red run proves, per test rather than per run), and no spec, ADR, plan or agent template states it; `templates/agents/tester.md:56` addresses only the opposite direction, an import-only failure standing in for a whole suite
   **Outcome:** `lesson-write` returned `refined: LESSON-revert-to-prove-a-regression-test.md` - the matched lesson's rule ("a regression test that still passes on the reverted fix is vacuous") generalized from the post-fix revert check to any station, with the pre-build red run named as the same discrimination read per test; summary changed, so the catalog row and the index line were updated with the body

2. **Source:** `teammate:pretest-066` artifacts - `tmp/red-TASK-066.txt`, `tmp/test-checkpoints/TASK-066.json`
   **Finding:** TASK-066's red evidence is a single `ModuleNotFoundError: No module named 'planlib'` ("Ran 1 test") standing for 15 checkpointed ids, none of which has been seen to fail for its own reason.
   **Anti-list:** matched bucket "Anything already documented in a spec, ADR, plan, vision, or CLAUDE.md" - `plugin/templates/agents/tester.md:56` states this case verbatim, including the remedy (label it as such; the post-build `--against-run` check is what proves a real failure reason)
   **Outcome:** rejected

3. **Source:** `tmp/plan-008-amendments.md` (21 findings across three lenses, all applied pre-build)
   **Finding:** The consolidated three-lens package was convergent and applied in full before any builder spawned.
   **Anti-list:** matched as a duplicate instance - this is the same review round already counted as a recurrence on `LESSON-adversarial-plan-review-before-build` at OPP-20260811T190123383649Z (seen 2026-08-11, score 5 -> 6); a second bump for the application half of one round would inflate the score without a new instance
   **Outcome:** rejected

### Contradiction check
Catalog rows overlapping the window's testing and methodology tags read: `LESSON-revert-to-prove-a-regression-test` (matched, routed to refinement above), `LESSON-suite-size-is-not-coverage`, `LESSON-blind-the-author-in-self-validation`, `LESSON-test-driven-tasks-dont-discriminate`, `LESSON-adversarial-plan-review-before-build`. Nothing in the window falsifies an active lesson's claim - the two-station flow's first live run confirms the discrimination rule rather than contradicting it. No revise or archive payload prepared.

### Notes
`plans/PLAN-008-rolling-wave.md` is a plan and the window's own vault write; its content is the anti-list's documented-elsewhere bucket by definition. `lessons/LESSON-wikilink-validator-skip-code.md` and `lessons/LESSON-adversarial-plan-review-before-build.md` are the previous pass's own writes. The twelve `tmp/subagent-captures/` files are one-line human nudges ("approve", "continue", "apply the amendments") with no finding content. `teammate:review-008-evidence` produced the gate-verified half of the amendment package already accounted for in candidate 3.

### Summary
Candidates: 3 | Written: 1 (refined) | Rejected: 2 | Errors: 0

## Opportunity OPP-20260811T222246764857Z (interval) - 2026-08-11T22:22:46Z

### Triggers
- fix-loop >=2: no
- validator Deviation (problem): no
- debug invoked: no
- STOP-and-report: no
- plan revised: no
- validator-finished / debug-finished (signal): no
- handoff-written (signal): no
- interval reached with signal(s): yes (subagent-finished, vault-write)

### Candidates

1. **Source:** `plugin/cli/commands/test_checkpoint.py:73` and `:567` vs commit `e3b6528`; original fixtures at `plugin/cli/tests/test_test_checkpoint.py` (commit `9a496ca`)
   **Finding:** The first live `verify --against-run` caught two shipped defects in the run-evidence parser: newer `unittest -v` repeats the test name inside the parenthesized path (so the last segment is not the class), and a docstring-bearing test prints across two lines the single-line regex never matched - meaning exactly the tests the test-design bar mandates were the unverifiable ones. The parser's own fixtures were hand-authored in the same assumed format, so 25 tests were green against a parser that could not read its real producer.
   **Anti-list:** passed - not a code pattern (the rule is about where a format comes from, not about this regex), not a debugging recipe (the fix is in the commit; the rule is what precedes writing the parser at all), and no spec, ADR, plan or CLAUDE.md states it
   **Outcome:** `lesson-write` returned `refined: LESSON-hook-payloads-observe-before-coding.md` - the rule widened from hook payloads to any parsed emission, and gained the fixture clause (hand-authored fixtures inherit the parser's assumption, so the suite stays green while the shipped code cannot read reality); title, summary and tags changed, so the catalog row and the index line were updated with the body

2. **Source:** `plugin/cli/decisionslib.py` (TASK-067, commit `e3b6528`)
   **Finding:** Stem-qualified `D-NN` cross-references are mentions, not unparsed local decisions; the zero-extraction evidence check must strip them before testing.
   **Anti-list:** matched as a duplicate instance - the mention-vs-use rule was already refined into `LESSON-wikilink-validator-skip-code.md` at OPP-20260811T190123383649Z from the finding TASK-067 implements; the commit message documents the remedy
   **Outcome:** rejected

3. **Source:** `teammate:pretest-069`, commits `66bf37b` / `e7af164` (TASK-068/069 red runs)
   **Finding:** Wave-1 tasks landed through the complete pre-build red run / build / post-build checkpoint lifecycle.
   **Anti-list:** matched a duplicate instance and bucket "Anything already documented in a spec, ADR, plan, vision, or CLAUDE.md" - what a red run proves per test was refined into `LESSON-revert-to-prove-a-regression-test.md` one pass earlier (OPP-20260811T220204623941Z), and PLAN-008 plus the commit messages document the lifecycle itself
   **Outcome:** rejected

### Contradiction check
Catalog rows overlapping the window's parsing, testing and workflow tags read: `LESSON-hook-payloads-observe-before-coding` (matched, routed to refinement above), `LESSON-blind-the-author-in-self-validation`, `LESSON-wikilink-validator-skip-code`, `LESSON-revert-to-prove-a-regression-test`, `LESSON-suite-size-is-not-coverage`. Nothing in the window falsifies an active lesson. `LESSON-blind-the-author-in-self-validation` was read closely: the parser incident is author-blindness of a kind (one author wrote both parser and fixtures), but that lesson's claim is about an experiment leaking its answer key into the arm under test, and its remedy is role-splitting across agents; the parser's remedy is captured real output, which the refined lesson now states. Not a recurrence, not a contradiction. No revise or archive payload prepared.

### Notes
The twelve `tmp/subagent-captures/` files in the window are one-line human nudges ("continue", "status?") with no finding content. `lessons/LESSON-revert-to-prove-a-regression-test.md` is the previous pass's own write, not a finding about it. `teammate:build-066` / `build-067` carried no candidate beyond the two defects and the decisionslib fix accounted for above.

### Summary
Candidates: 3 | Written: 1 (refined) | Rejected: 2 | Errors: 0

## Opportunity OPP-20260811T225127269851Z (interval) - 2026-08-11T22:51:27Z

### Triggers
- fix-loop >=2: no
- validator Deviation (problem): no
- debug invoked: no
- STOP-and-report: no
- plan revised: no
- validator-finished / debug-finished (signal): no
- handoff-written (signal): no
- interval reached with signal(s): yes (subagent-finished, vault-write)

### Candidates

1. **Source:** the wave-1 elaboration edit on `plans/PLAN-008-rolling-wave.md` (window context), against `plugin/cli/planlib.py` heading semantics
   **Finding:** The orchestrator's own scripted replace anchored on the string `## Later (intent only)` and matched a backticked prose mention of that heading instead of the heading line, splicing the promoted wave mid-paragraph; the gates caught every intermediate state and the edit was redone line-anchored. The document's parser closes a region on a heading at line start; the edit bound to a substring the same document repeats as prose.
   **Anti-list:** passed - not a code pattern (no code changed; the rule is about where an anchor binds), not a debugging recipe, and no spec, ADR, plan, agent template or CLAUDE.md states it (grep for line-anchor guidance across `plugin/`, `.compass/`, `.claude/rules` returns nothing); the plan's record section and the elaboration commit record the promoted content, never the misfire
   **Outcome:** `lesson-write` returned `refined: LESSON-wikilink-validator-skip-code.md` - the matched lesson covered only matchers a developer writes; this instance shows the identical failure on the write side, so the rule widened from matcher design to any anchor into a document, an edit's find string included. Title, summary and tags changed, so the catalog row and the index line were updated with the body.

2. **Source:** `tmp/subagent-captures/2026-08-11T22-50-43_reviewer.md` (13 findings on the TASK-072 skill diff, 7 of them accuracy)
   **Finding:** Prose teaching a mechanism the same change built drifted from the implementation in seven places (`--strict` semantics, the `has_later` gate, what closes a Later region), each verifiable by reading the module the sentence describes.
   **Anti-list:** matched bucket "Anything already documented in a spec, ADR, plan, vision, or CLAUDE.md" - the global CLAUDE.md rule "NEVER assume - ALWAYS verify... if you're unsure how something works in this project, read the code first" states it, and `LESSON-dont-strip-agent-quality-stations` already covers keeping the review station that caught these
   **Outcome:** rejected

3. **Source:** `plans/PLAN-008-rolling-wave.md:257-263` vs the fence-or-backtick rule TASK-071/077 shipped in the same wave
   **Finding:** The first elaboration record authored in the new format quoted its superseded intent lines unfenced, breaking the rule the same wave was shipping; review caught it and the quotes are fenced now.
   **Anti-list:** matched as a duplicate instance - the dogfood-as-acceptance-test rule is stated verbatim at `plans/PLAN-008-rolling-wave.md:22` and was already rejected on that ground at OPP-20260811T190123383649Z
   **Outcome:** rejected

### Contradiction check
Catalog rows overlapping the window's parsing, planning and workflow tags read: `LESSON-wikilink-validator-skip-code` (matched, routed to refinement above), `LESSON-hook-payloads-observe-before-coding`, `LESSON-adversarial-plan-review-before-build`, `LESSON-remove-context-before-adding`, `LESSON-dont-strip-agent-quality-stations`. Nothing in the window falsifies an active lesson: TASK-070's probe confirmed the precedence rule it tested rather than overturning it, and the wave-1 loop ran as designed. `LESSON-remove-context-before-adding` was read closely against candidate 1 and does not match - its claim is about fixing a behavior bug by removing prose rather than adding it, while the edit misfire is a mis-bound anchor with no prose remedy either way. No revise or archive payload prepared.

### Notes
The fourteen 129-byte `tmp/subagent-captures/` files in the window are one-line human nudges ("continue", "status?", "continue with wave 2") with no finding content. `tmp/phase-reports/PLAN-008-wave-1/task-070-build.md` records a probe whose own Surprise section reads "None" and whose consequence is already committed in TASK-071/077. `specs/SPEC-001-scratch.md` and `plans/PLAN-001-scratch.md` are TASK-077's throwaway template fixtures. `lessons/LESSON-hook-payloads-observe-before-coding.md` is the previous pass's own write.

### Summary
Candidates: 3 | Written: 1 (refined) | Rejected: 2 | Errors: 0
