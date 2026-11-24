---
title: "Axis 2: what the checking stations cost"
type: research
status: complete
confidence: medium
area: tooling
tags: [tokens, cost, harness, verification, measurement, tester, validator]
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "6faced1"
author: "researcher"
summary: "No run records per-station tokens or defects caught; re-profiling the repo's own transcripts gives tester pre and post about 17% of all session-family tokens, builder 25%, validator 0.1%; catches are unrecorded"
spec: "[[SPEC-034-checking-cost-follows-task-and-model]]"
---

## Research: what the checking stations cost per task

From [[SPEC-034-checking-cost-follows-task-and-model]]. Index: [[index]].

### Question
What share of task tokens do the post-build tester, the validator and the builder's own review spend, and what did they catch (defects, fix-loop cycles)?

### Methodology
Repository mining (empirical study of the artifact): bench run records, the usage record, capture logs, and the profiler `bench/overhead/token_profile.py` re-run over this repo's own session transcripts, split by subagent type. Grading: the brief carried `grading: allowed`; grades below weigh evidence type for a fast-moving field, measured over asserted.

### Findings

1. **No run or log records per-station tokens, defects caught or fix-loop cycles.** (confidence: high)
   What is recorded: per-arm totals only in the smoke runs; per-subagent-type tokens only if the profiler is re-run on transcripts; command invocation counts in the usage file; capture signals by name. No file ties a tester, validator or builder-review spend to a task, a verdict or a fix cycle.
   - `bench/runs/20260610T202237_binary-search-bug/arm_compass.jsonl:1` - one row: tokens_total 22619, tokens_input/output null, turns 4.
   - `bench/runs/summary-cross-runs.md` - smoke arms use one `general-purpose` subagent; no tester, validator or review stage ran.
   - Marks: code and records, owner checked; not retracted; not preprint; 0 citations; 3 sources agree
   - Grade: high (measured absence, read directly)

2. **Bench smoke and SWE-bench Pro runs carry no checking-station data.** (confidence: high)
   Smoke fixtures: 21.7k to 23.6k tokens per arm, 4 to 5 tool calls, Compass arm +4% to +5% tokens. SWE-bench Pro single task: baseline 42,354 vs Compass 58,797 tokens (+39%), 17 vs 35 tool calls; the extra was reading, a stub harness and a 10,000-trial fuzz check, all inside one agent. Both arms passed, so no defect separated them.
   - `bench/runs/20260610T223212_swebp-qutebrowser-elf/summary.md` (Results, Process delta)
   - Marks: measured, N=1 per fixture; not retracted; not preprint; 0 citations; 1 source
   - Grade: medium-low (measured, N=1, no station split)

3. **The pilot run profiles subagent types but reports shares within a type, not of the task total.** (confidence: high)
   95 subagent sessions in 6 Compass-arm builds: researcher 36, builder 20, tester 13, planner 7, reviewer 7, validator 6, general-purpose 6. Output is 36% to 46% of each type's weighted tokens; preloaded skill bodies 12.8% to 22.1%. Subagents total about 47.5M weighted tokens in the Compass arm; mean weighted tokens per Compass build 6,967,451 (baseline 770,470). The tester or validator share of a build is not in the document.
   - `.compass/research/whole-overhead/RESEARCH-compass-agent-context-measured.md:111-124` (type share table), `:129`
   - `.compass/research/whole-overhead/RESEARCH-whole-overhead-pilot-run-1.md:69-70`
   - Marks: transcript; not retracted; not preprint; 0 citations; 1 source; harness faults named there inflate the main session, not a subagent's own composition
   - Grade: medium (measured, one pilot, 6 to 20 sessions per type)

4. **Fixed start cost per checking spawn is large before any checking work.** (confidence: medium)
   First-request context: tester 42.2k tokens, validator 38.5k, builder 39.3k, reviewer 36.7k. Preloaded skill bodies are 73.4k chars for the tester, 64.6k for the validator; 14.3k chars of memory section sit in both. Validator: 6 of 6 sessions ran `compass lesson-coverage`, 5 of 6 `test-smells`, 4 of 6 `test-checkpoint`; tester ran `test-smells` in 13 of 13.
   - `RESEARCH-compass-agent-context-measured.md:84,89-96,166`
   - Marks: transcript; not retracted; not preprint; 0 citations; 1 source, 95 sessions
   - Grade: medium (measured)

5. **Re-profiling this repo's own transcripts (233 sessions) gives per-type shares of all session-family tokens.** (confidence: medium)
   Method: `token_profile.profile_session` over each top-level session and its `subagents/` files, parent-recorded responses skipped; weighted tokens per `bench/overhead/records.py` weights; family total 329.1M weighted (main sessions 118.0M, subagents 211.1M). Share of family total, with spawn count, median per spawn:
   - builder 102 spawns, 25.4%, median 659k
   - tester pre-build station 62 spawns, 9.2%, median 417k
   - tester post-build station 56 spawns, 8.0%, median 422k (4 more tester spawns not classifiable from their descriptions, 0.4%)
   - reviewer 13, 2.0%, median 477k
   - validator 1 spawn, 0.1%, 346k
   - researcher 61, 9.2%; planner 14, 4.1%; general-purpose 138, 4.8%
   The two tester stations together are 17.2% of family tokens, about two thirds of the builder's 25.4%; the validator share is near zero because the agent was spawned once.
   - Script run once on the transcripts folder of this repo; script in the session scratchpad, not shipped. Station split by regex on the spawn description (`pre`, `post`, `author`, `suite`), so it is a heuristic.
   - Marks: transcript, computed by me; not retracted; not preprint; 0 citations; 1 source (dev sessions, not benchmark tasks)
   - Grade: medium-low (measured but heuristic split, denominator is all session work including non-build work, not per task)

6. **The builder's own review step cannot be separated from the builder's tokens.** (confidence: medium)
   Review runs inside the builder session. The profiler assigns a phase by the last skill loaded, and in a subagent session the phase is the session kind, so format and code review tokens sit in the one `subagent:builder` phase.
   - `bench/overhead/token_profile.py:30-33` (Phases paragraph)
   - Marks: code, owner checked; not retracted; not preprint; 0 citations; 1 source
   - Grade: high (read in code)

7. **Defects caught and fix-loop cycles are not recorded as data.** (confidence: medium)
   Capture-log signal counts over 173 opportunities: subagent-finished 129, builder-finished 56, agent-noted 40, debug-finished 8, validator-finished 1; no opportunity file in the 173 contains a `fix-loop` trigger. Re-test spawns do exist as names in the transcript folder (3 of 8 tasks with a `-post` station also have a `-post2` spawn), a hint of a fix cycle, not a count of defects.
   - `.compass/tmp/capture-log.jsonl` (1952 rows); `.compass/tmp/capture-opportunities/` (grep `fix-loop`: 0 files)
   - `plugin/cli/commands/` has `capture_signal.py`, `test_checkpoint.py`, `test_smells.py`; none stores a verdict or defect count per task
   - Marks: records; not retracted; not preprint; 0 citations; 2 sources agree
   - Grade: medium (measured absence in two logs; the `-post2` reading is inference from names)

8. **The usage record counts command invocations, not agent spend.** (confidence: high)
   Since 2026-09-13: `test-checkpoint` 221, `test-smells` 42, `validate` 26, `lesson-coverage` 154, `guard` 4565. `validate` is a CLI command name; the validator agent shows 1 spawn in this repo's transcripts, so the two should not be assumed to be the same event.
   - `.compass/meta/usage.yaml:1-102`; `python plugin/cli/compass usage`
   - Marks: records; not retracted; not preprint; 0 citations; 1 source
   - Grade: high (read directly)

9. **Capture workers are outside any task total and add tokens.** (confidence: medium)
   Pilot: 3 to 19 extract-lessons sessions per build, an estimated 4% to 17% on top of the Compass arm's weighted total. Archive logs hold capture-worker run results (cost and usage per worker), not per-station checking cost.
   - `RESEARCH-whole-overhead-pilot-run-1.md:86`; `.compass/archive/logs/` (98 files, e.g. first file: modelUsage by model, no agent type)
   - Marks: records; not retracted; not preprint; 0 citations; 2 sources
   - Grade: medium

### Contradictions
- Finding 5 shows 62 pre-build and 56 post-build tester spawns against 102 builder spawns; the methodology text says two tester stations per code task. The ratio (about 1.2 tester spawns per builder spawn) is not 2, so some tasks skipped a station or builders were spawned for non-plan work. Unresolved here.

### Gaps
- Per task share (station tokens over the task total) is not computable from any stored record. A measurement needs: a task id on each subagent spawn (the meta file holds `description` and `toolUseId` only), an explicit station field (tester pre, tester post, validator, builder review), and the tester or validator verdict plus fix-cycle count written to a log next to the spawn.
- Builder review tokens need a marker in the builder transcript (a phase tag or a separate spawn) to separate them.
- Defects caught per station need a ground truth: seeded defects (the vault records a probe catching 15 of 15, not re-verified here) or a frozen goal list judged after the run, as [[REVIEW-whole-overhead]] describes.
- About 40 spawns with descriptive agent types (build-NNN, test-NNN-pre/post) show 0 weighted tokens in my re-run; they were skipped by the parent-id filter or are forks, and are excluded from finding 5. Cause not isolated.
- Finding 5 counts this repo's dev sessions, not benchmark tasks; main-session tokens (118.0M, 36% of the family total) are not split by task either.
