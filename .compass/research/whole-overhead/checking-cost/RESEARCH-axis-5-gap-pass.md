---
title: "Research: builder review attribution and defect records (checking-cost gap pass)"
type: research
status: complete
confidence: medium
summary: "The builder's code review is a separate sub-agent with its own transcript (about 10% of builder-plus-review weighted tokens in 29 sampled builds); existing records count fix cycles and a few post-build bug lines but not defects caught per station."
area: workflow
tags: [tokens, cost, verification, measurement, builder, tester, validator]
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "6faced1"
author: "researcher"
depends_on: ["[[SPEC-034-checking-cost-follows-task-and-model]]", "[[REVIEW-checking-cost]]"]
---

## Research: builder review attribution and defect records

From [[SPEC-034-checking-cost-follows-task-and-model]]. Closes the two Gaps listed in [[REVIEW-checking-cost]] (lines 187-192). No bench run was made; aggregates only.

### Question
Where do the builder's code-review tokens land, and can defects caught per station be counted from existing build records?

### Methodology
Repository mining (an empirical study of existing artifacts: agent definitions, subagent transcripts, bench records, vault records), because both gaps ask how existing code and records behave. No disclosure about grading was refused: the brief carried `grading: allowed`; every source here is first-party code or logs, so grades reflect "measured from artifact" and not peer review.

### Gap 1: builder self-review attribution

1. **Builder review step spawns a separate sub-agent** (confidence: high)
   Step 8 reads "Spawn a sub-agent with the diff (`git diff`)", and the builder's tool list includes `Agent`. The shipped template and the local install are identical at those lines.
   - `.claude/agents/builder.md:4,63-67` - tools line and step 8.
   - `plugin/templates/agents/builder.md:63-67` - same text (the full-file diff reports no difference).
   - Marks: first-party code, no retraction, not a preprint, no citations, converges with the transcript counts below.
   - Grade: high (read directly from the definition).

2. **Transcripts show the spawn, in 40 of 104 builder sessions** (confidence: high)
   In this repo's project transcripts there are 553 subagent files, 104 of them `builder`. 39 builders made one `Agent` call, 1 made two, 64 made none. 29 of the 40 spawned a diff review (descriptions such as "Review TASK-NNN diff", or type `reviewer`: 27 `general-purpose`, 1 `reviewer`, 1 `pattern-finder`); the rest were "Fresh-eyes ..." document reviews. Builder reports with a "### Code Review" section: 19 of 133 captured builder reports.
   - Subagent `.meta.json` files, `agentType` and `parentAgentId` fields (counted, not quoted).
   - `plugin/templates/agents/builder.md:109` - report format with the Code Review section.
   - Marks: first-party log, no retraction, not a preprint, no citations, single source type (transcripts + captures agree on direction, differ on count).
   - Grade: high for the counts, medium for what the 64 non-spawn builders did (builder definition text changed over time; the first spawn appears 2026-10-17, the first builder 2026-09-21 by transcript timestamps).

3. **Review tokens land in a separate transcript, not the builder's** (confidence: high)
   Each review child has its own `.jsonl` and `.meta.json` with `parentAgentId` = the builder's agent id and `spawnDepth` 2 (builders are depth 1), `requestShape` `background`. The builder's own file carries one agent id and only an `async_launched` tool result for the spawn (keys: agentId, description, prompt, status; no token fields). So the child's usage is not inside the builder file's usage.
   - Child `.meta.json` vs builder `.jsonl` (inspected on a sample, then counted over all 41 children of builders).
   - Marks: first-party log, no retraction, not a preprint, no citations, one source.
   - Grade: high.

4. **The profiler files the child as `subagent:general-purpose`, with no builder link** (confidence: high)
   `token_profile.py` names each subagent session `subagent:<agentType from its .meta.json>`, so a review child is `subagent:general-purpose` (or `reviewer`), not `subagent:builder`. No `parentAgentId` read exists in `bench/overhead` or `plugin/cli`. The 149 `general-purpose` sessions here include the 39 builder children, so type alone cannot isolate builder review; the `parentAgentId` join can.
   - `bench/overhead/token_profile.py:442-443` - agent type from `.meta.json`, session kind `subagent:<type>`.
   - `bench/overhead/token_profile.py:585` - `general-purpose` accepted as a subagent kind.
   - `bench/overhead/records.py:15` - run totals from `modelUsage` already include subagent usage.
   - Marks: first-party code, no retraction, not a preprint, no citations, grep over `bench/overhead` and `plugin/cli` returned no `parentAgentId`.
   - Grade: high.

5. **Size of the review share in the sampled builds** (confidence: medium)
   Over the 29 builders that spawned a diff review, summed message usage: builder sessions output 3.74M, cache write 28.5M, cache read 464M, input 9.5k tokens; review children output 0.55M, cache write 4.39M, cache read 16.8M, input 71.6k. With the repo's own sonnet-5-5 weights (output 5, cache write 1.25, cache read 0.05), the children are about 9.1M of about 86.7M weighted, near 10.5%. Caveats: the weights are applied to all rows although the model mix was not checked, and the builder sessions include fix-loop continuations that run after the review.
   - Weights: `bench/overhead/records.py:67-78` (`OUTPUT_WEIGHT`, `CACHE_WRITE_WEIGHT`, `PRICED_MODELS`).
   - Marks: first-party log, no retraction, not a preprint, no citations, one source.
   - Grade: medium (measured, model mix unchecked, one repo).

6. **The two positions in the review are each partly right** (confidence: high)
   Position A (separate sub-agent) is confirmed. Position B (filed under `subagent:builder`, inseparable) is not what the profiler does today: it files the child under its own type; what is missing is the parent link, so a separate measurement needs the `parentAgentId` join, not a new spawn.
   - See findings 1, 3 and 4.
   - Marks: derived from findings above, convergence: 2 independent artifact types (definition, transcripts).
   - Grade: high.

### Gap 2: defects from existing records

7. **Bench build runs (`bench/runs/*`) have no stations to count** (confidence: high)
   The three recorded runs (2026-06-10) hold one row per arm (success, score, tokens, turns), two diffs, and a summary. Their method delivers the methodology as text to a `general-purpose` subagent, so no builder, tester or validator station ran. Outcomes were ties (5/5, 9/9, SWE-bench Pro 6/6 each arm).
   - `bench/runs/summary-cross-runs.md:4` - method line.
   - `bench/runs/20260610T223212_swebp-qutebrowser-elf/summary.md` - result table.
   - Marks: first-party record, no retraction, not a preprint, no citations, one source.
   - Grade: high; supports "zero station defects countable here".

8. **Pilot judge verdicts count goal items met, not defects per station** (confidence: high)
   The judge stores per-goal scores and counts (met / partly met / not met) and has two slots for station evidence, `builder_tests` and `validator_verdict`. Across the 29 stored verdicts the totals are 121 met, 64 partly met, 114 not met; 6 verdicts have no goal met. In all 29, both station slots are `None`, so no station verdict was recorded into them.
   - `bench/overhead/judge.py:252` - signature with `builder_tests=None, validator_verdict=None`.
   - `bench/overhead/judge.py:289-295` - verdict dict with `counts` and `recorded`.
   - Verdict JSON files under the private overhead root (counted, no content read).
   - Marks: first-party record, no retraction, not a preprint, no citations, one source.
   - Grade: high for the counts; the goal counts are an outcome measure per build, usable as escaped-defect evidence, not as caught-per-station evidence.

9. **Tester post-build reports carry a countable defect section, with small n** (confidence: high)
   The post-build report format has "Bugs Found" with `file:line`, repro command, expected and actual. Of 121 captured tester reports, 5 hold a "### Bugs Found" section, which is the number of reports (not bugs) with a defect the post-build station caught. Pre-build reports carry red evidence and an optional plan defect, which is a different event.
   - `plugin/templates/agents/tester.md:123` - "Bugs Found (post-build only, omit if none)".
   - `plugin/templates/agents/tester.md:112,120` - pre-build "Red Evidence" and "Plan Defect" sections.
   - Vault `tmp` subagent captures (counted by grep on the section heading).
   - Marks: first-party record, no retraction, not a preprint, no citations, one source.
   - Grade: high for the format; low coverage because the captures sit in gitignored scratch and span all work in the repo, not a measured sample.

10. **Validator output is structured but nearly absent from records** (confidence: high)
   The validator report has a per-task result column and PASS/FAIL, and "Unfixed Bugs" lists. This repo holds one validator subagent transcript and one validator capture; none of the 14 phase summaries lists a validator deviation (all `validator_deviations` empty).
   - `plugin/templates/agents/validator.md:183,236,242` - results row, unfixed bugs, final Result line.
   - `plugin/templates/agents/validator.md:122` - unfixed tester bugs become FAIL items.
   - Phase summaries under vault `tmp/phase-reports/*/phase-summary.yaml` (14 files).
   - Marks: first-party record, no retraction, not a preprint, no citations, one source.
   - Grade: high that validator defects cannot be counted from these records (n = 1).

11. **Fix-loop cycles are recorded per task, and measure rounds, not defects** (confidence: high)
   `phase-summary.yaml` carries `fix_loop_cycles` per task: 39 tasks across 14 summaries, 13 with a nonzero count. `compass test-checkpoint cycle` appends a per-cycle verdict (`helpful`, `harmful`, `neutral`) with the failing-test set to `TASK-NNN.cycles.jsonl`, escalating at cycle 3 or on a harmful cycle; only 2 such ledger files remain in the vault now. A cycle starts after the post-build tester reports failing tests, so a cycle count is a count of rounds after the first failure, not of distinct defects, and it does not name which station found them.
   - `plugin/skills/build/SKILL.md:60` - `fix_loop_cycles` field and where it is read from.
   - `plugin/cli/commands/test_checkpoint.py:67-74` - cycle judging and escalation.
   - `.compass/tmp/phase-reports/PHASE-001-plan-021-wave-1/phase-summary.yaml:5-16` - an example of the recorded counts (stop events there: test-defect events on the checkpointed tests, i.e. defects in the pre-build station's own output).
   - Marks: first-party record, no retraction, not a preprint, no citations, one source.
   - Grade: high.

12. **No existing record holds counterfactual or seeded ground truth** (confidence: high)
   `bench/overhead` has no step that injects a known defect (the "seeded" in `pilot.py` means seeded topic picks, not defects). Records show what stations reported on builds that ran with all stations on; none records what a station removed would have missed. The two sources that do carry ground truth are the frozen goal lists (an outcome per build) and any defect a human knows in advance (a seeded one).
   - `bench/overhead/pilot.py:7-8,347-363` - "seeded" means topic picks.
   - `.compass/research/whole-overhead/checking-cost/REVIEW-checking-cost.md:108` - same finding earlier, no seeded-defect step.
   - Marks: first-party code, no retraction, not a preprint, no citations, grep for seed/defect/mutant/inject in `bench/overhead` returned only topic-seed lines.
   - Grade: high.

### Options the records leave open (not ranked)
- Count defects caught per station from the formats above (tester Bugs Found lines, validator FAIL items, fix-cycle counts): usable only for a run made with a per-spawn station record; existing records give n of 5 and 1.
- Station-ablation arms scored against frozen goals: the existing judge supplies the outcome (goal counts); the difference between arms is the defect-caught proxy per station. No seeding needed; resolution is limited by the number of goal items per topic.
- Seeded defects: gives known truth per defect and per-station detection rate; requires building the injection step, which does not exist.

### Contradictions
- Review `REVIEW-checking-cost` Position B says the profiler files builder review under `subagent:builder`; the profiler code (`token_profile.py:442-443`) and transcripts (finding 3) file it under the child's own agent type.

### Gaps
- Model mix of the 29 sampled builds and their children is unchecked, so the 10.5% weighted share applies sonnet-5-5 weights to every row.
- Why 64 of 104 builders spawned nothing (older definition text, a document task, or skipped step 8) is not established; the builder definition's change history was not read.
- Pilot-arm builds under `~/.compass/overhead` were not opened beyond counts; whether their builder sessions spawned reviews is unread (profiles list 5 builder, 4 tester, 4 validator sessions across 12 profiles, aggregates only).
