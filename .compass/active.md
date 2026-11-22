---
title: Active Tasks
updated: 2026-09-13
---

# Active Tasks

## Sizing + discoverability initiative

Triggered by a live failure in another project: a vision session produced seven epic-sized needs and Compass proposed seven flat specs with no signal anything was wrong.

- [ ] Open: pin the project where the seven-monster-specs session happened ([[LESSON-pin-the-motivating-datum]]).

## Per-domain organization initiative

- [ ] v0.15.0's premature skill/sync edits were reverted; index depth-0 rule stays (shipped); everything further waits on the plan.

## Research covers the whole spec (SPEC-023)

- [ ] [[specs/pipeline/SPEC-024-walled-sources-through-the-browser]] awaits the human's ruling.
- [ ] Open: a text-and-data-mining request to ACM is the human's to send if wanted.

## PLAN-018 Wave 2: prove the stop rule, exercise the list, close the autopilot gap

Plan: [[PLAN-018-research-covers-the-whole-spec]]. Wave 1 shipped as v0.24.0 on 2026-09-14; its manual checks await the human. Wave 2 starts on his word.

- [ ] TASK-129: Run the completeness scorer on a real spec and research
- [ ] TASK-131: Exercise every shipped retriever against its live source
- [ ] TASK-135: Autopilot research calls the research entry point

## PLAN-019: stop and suggest a handoff at 80% context

Plan: [[PLAN-019-stop-at-80-percent-context]]. TASK-137 and TASK-138 shipped as v0.26.0.

- [ ] TASK-139: Live acceptance in an interactive Claude Code session - the human watches the stop and the handoff (`COMPASS_CONTEXT_THRESHOLD` lowers the line).

## PLAN-020: clone old sessions to harvest their lessons

Plan: [[PLAN-020-clone-old-sessions]].

- [ ] TASK-146: Live acceptance on this repo

## PLAN-021 Wave 2: judge, schedule, ast-grep sensor, skill, release

Plan: [[PLAN-021-control-loops]].

- [ ] TASK-161: The ast-grep sensor adapter, pinned to saved scan output - complexity: M, depends_on: TASK-158, TASK-159, TASK-236
- [ ] TASK-160: `/compass:loop`: guided creation through steps 0 to 7 - complexity: M, depends_on: TASK-158, TASK-159, TASK-161
- [ ] TASK-162: The Maya recipe on the local lane, marked untested on this machine - complexity: S, depends_on: TASK-160
- [ ] TASK-163: Teach the vault conventions about loops and ship the next minor release - complexity: M, depends_on: TASK-158, TASK-159, TASK-160, TASK-161, TASK-162, TASK-236

## PLAN-028 Wave 1: the pilot

Plan: [[PLAN-028-whole-overhead-on-real-projects]]; each task's full text, files and checks are there.

- [ ] TASK-249: You grade four pilot builds - complexity: S, depends_on: TASK-248
## PLAN-031 Wave 1: prove screenplays on real editors

Plan: [[PLAN-031-screenplays-in-the-vault]]; each task's full text, files and checks are there.

- [ ] TASK-287: Live check 1, round-trip hashes - complexity: S, depends_on: TASK-286
- [ ] TASK-288: Live check 2, links on the current Obsidian build - complexity: S, depends_on: TASK-286
- [ ] TASK-289: Live check 3, an agent's edit reloads in both editors - complexity: S, depends_on: TASK-286
- [ ] TASK-290: Live check 4, install the way Compass will - complexity: S, depends_on: TASK-286
- [ ] TASK-291: Live check 5, the two previews side by side - complexity: S, depends_on: TASK-286

## PLAN-032 Wave 1: consolidation grounded in sources

Plan: [[plans\PLAN-032-consolidation-grounded-in-sources]]; each task's full text, files and checks are there.

- [ ] TASK-301: Register `drift` and `lesson-check` in `COMMAND_SPECS` with one-line help each; handlers arrive in TASK-305 and TASK-306 and report... - complexity: S, depends_on: none
- [ ] TASK-302: Sync refreshes existing catalog rows from their lesson files: `status`, `category`, `area`, `tags`, `score` and `escalated` are... - complexity: M, depends_on: none
- [ ] TASK-303: `driftlib.py` code-reference classifier - complexity: M, depends_on: none
- [ ] TASK-304: Add the text checks to `driftlib.py`: each `[[link]] - desc` line in every `index.md` (parsed with sync's `ENTRY_PATTERN`) against its... - complexity: S, depends_on: TASK-303
- [ ] TASK-305: `compass drift` command - complexity: M, depends_on: TASK-301, TASK-304
- [ ] TASK-306: `compass lesson-check <lesson> [--base REV]` mechanical admission check, base default `HEAD` - complexity: M, depends_on: TASK-301, TASK-305
- [ ] TASK-307: Skills edit lessons by delta - complexity: M, depends_on: TASK-302, TASK-306
- [ ] TASK-308: Seeded-staleness probe for the script half ([[AXIS-5-gap-pass]] f4-f5) - complexity: M, depends_on: TASK-305
- [ ] TASK-309: Ship Wave 1: bump `plugin/.claude-plugin/plugin.json` minor version and copy the changed `plugin/` files (both new command modules,... - complexity: S, depends_on: TASK-307, TASK-308

## PLAN-034 Wave 1: checking cost follows task and model

Plan: [[plans\PLAN-034-checking-cost-follows-task-and-model]]; each task's full text, files and checks are there.

- [ ] TASK-342: ADR recording ruling 1: a task-difficulty class assigned by judgment under a written rubric and recorded by the harness is allowed under... - complexity: S, depends_on: none
- [ ] TASK-343: Variant arms and the build's model, repo-local in `bench/overhead/` - complexity: L, depends_on: none
- [ ] TASK-344: A noninferiority guard in `compare.py` - complexity: S, depends_on: TASK-343
- [ ] TASK-345: The builder's review attributed - complexity: S, depends_on: none
- [ ] TASK-346: Every checking spawn recorded, shipped in `plugin/` - complexity: M, depends_on: none
- [ ] TASK-347: The letter parsed and the stations report, shipped in `plugin/` - complexity: M, depends_on: TASK-346
- [ ] TASK-348: Release and local refresh: bump `plugin/.claude-plugin/plugin.json` to the next minor, run `python plugin/cli/compass self-update... - complexity: S, depends_on: TASK-346, TASK-347
- [ ] TASK-349: The bench reads the station record - complexity: S, depends_on: TASK-343, TASK-346
- [ ] TASK-350: Letter repeatability, measured - complexity: M, depends_on: none
- [ ] TASK-351: Two smoke builds on the subscription, one at a time - complexity: S, depends_on: TASK-343, TASK-346, TASK-349
- [ ] TASK-352: The per-part spread pilot - complexity: M, depends_on: TASK-344, TASK-345, TASK-351

## Next Up

- [ ] SubagentStop typed-signal fix, fleet-wide (payload evidence captured: `agent_type` empty string). Queued in [[backlog]].
- [ ] [[SPEC-006-multi-host-agent-cli-support]] hosts: hermes first, then deepseek-harness (dsh; fit assessed in [[research/distribution/RESEARCH-deepseek-harness-fit]], 2026-09-04), then Kimi Code / Codex.
- [ ] Blinded rerun of the test-bar experiment ([[LESSON-blind-the-author-in-self-validation]]).
