---
title: "Axis 1: the task difficulty signal Compass has today"
type: research
status: complete
confidence: medium
area: tooling
tags: [tokens, cost, harness, verification, models, sizing]
summary: "Compass has one per-task difficulty field (planner-set S/M/L, unparsed, unrecorded after build) and a per-agent model policy; no checking station varies by either, and the S/M/L field is too loose to key a deterministic checking level without a defined rubric"
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "6faced1"
author: researcher
depends_on: ["[[SPEC-034-checking-cost-follows-task-and-model]]"]
---

# Axis 1: the task difficulty signal Compass has today

From [[SPEC-034-checking-cost-follows-task-and-model]]. Index: [[index]].

## Question

How does Compass size tasks today, where is each size or model field set and recorded, do the checking stations vary by it, and could it key a checking level so the same task on the same model gets the same answer?

## Methodology

Repository mining (empirical study of the artifact): read `plugin/` and `.claude/agents/` code, run `compass` commands, and count vault plan lines. It fits "how does an existing system actually behave". No external literature was read; the question is about Compass's own state. Grading: allowed. Evidence type here is source code or a command run (grade: measured, authoritative for current behavior); retraction, preprint and citation marks do not apply to repository evidence.

## Findings

1. **One per-task difficulty field exists: `complexity: S|M|L`, written by the planner on the task line.** The planner template writes `- [ ] TASK-NNN: ... - complexity: S, depends_on: ..., files: [...]` and carries a rubric table: S single file straightforward; M 2-5 files, some complexity; L 5+ files or significant complexity; larger than L is split (confidence: high).
   - `plugin/templates/agents/planner.md:80` - task-line grammar with `complexity:`
   - `plugin/templates/agents/planner.md:149-155` - Task Sizing rubric (file count plus a judged "complexity" word)
   - `plugin/templates/agents/planner.md:118` - plan-level `Estimated complexity: [S/M/L overall]` in the approval message only
   - Marks: source code read, n/a retraction, n/a preprint, n/a citations, convergence: the same grammar in `plugin/skills/obsidian/templates.md:201` and `plugin/skills/retroactive/SKILL.md:90`
   - Grade: authoritative for current behavior (measured by reading)

2. **It is set once, at plan-write time, by the planner agent, and the human sees it at plan approval.** Intent-only lines under `## Later` carry no complexity by rule; it is assigned when the build flow's step 7d promotes them into a detailed wave, so a task has a size only after its wave is elaborated (confidence: high).
   - `plugin/templates/agents/planner.md:45` - intent lines "with no `complexity`"; `commit-upfront` tasks are written out "complexity through verification"
   - `plugin/skills/build/SKILL.md:66` - 7d promotes intent lines into full task blocks
   - Marks: source code read, n/a, n/a, n/a, single source per claim

3. **No code reads `complexity:`.** The only task-line regex, `TASK_LINE`, stops at the task id. A grep for `complexity` across `plugin/cli/*.py` and `plugin/cli/commands/*.py` excluding tests returns nothing; matches are in tests and fixtures only. No hook reads it. It is prose for planner, human and autopilot (confidence: high).
   - `plugin/cli/planlib.py:53` - `TASK_LINE = ...(TASK-[A-Za-z0-9_-]+):` captures id only
   - `plugin/cli/tests/test_planlib.py:187`, `plugin/cli/tests/test_lesson_coverage.py:101` - the only code mentions are fixture text
   - Marks: grep run over the tree, n/a, n/a, n/a, single source

4. **The field is recorded in plan files and `active.md` and never updated after build.** Plans hold it on task lines; `active.md` and `backlog.md` copy the task lines (10 occurrences in `active.md` at the time of reading). The phase summary schema and `test-checkpoint` records carry no size or model field; the only post-hoc difficulty signal is `fix_loop_cycles` per task (confidence: high).
   - `plugin/skills/build/SKILL.md:60` - `phase-summary.yaml` lists `fix_loop_cycles`, `validator_deviations`, `debug_invocations`, `stop_and_report_events`, `plan_revisions`; no complexity or model
   - Marks: source code read plus vault grep, n/a, n/a, n/a, single source

5. **A second size record exists, `sizing_id` plus `.compass/meta/sizing-log.yaml`, but it sizes the vault's shape, not a code task.** It logs `make-unit`, `promote`, `demote` and `make-unit --undo` decisions (`shape: unit|folder|domain`, `by: agent|human`); `sizing_id` is written into the subject artifact's frontmatter. `compass sizing stats` reports it. It has no relation to task difficulty or to checking (confidence: high).
   - `plugin/cli/commands/sizing.py:1-30` - what a sizing decision is, row schema, `sizing_id` survival across `git mv`
   - Marks: source code read plus the log read, n/a, n/a, n/a, single source
   - Aggregate: the log holds 35 rows: 31 decision, 4 correction; 30 shape domain, 5 shape folder; all 35 `by: agent`. `compass sizing` was invoked once in the usage record (`.compass/meta/usage.yaml`, count 1, last 2026-10-17).

6. **Model and effort are chosen per agent, not per task, and are static at install time.** `modelslib.DEFAULT_ROSTER` maps each agent to a tier: planner, validator, reviewer, debug strong; builder, tester, researcher and the analyzers balanced; locators and pr-describe cheap. `HOST_CATALOGS["claude-code"]` maps strong to opus, balanced to sonnet, cheap to haiku; `TIER_EFFORT` gives high, high, low (confidence: high).
   - `plugin/cli/modelslib.py:43-59` - roster; `:28-30` - catalog; `:73` - tier effort
   - `plugin/cli/modelslib.py:1-12` - precedence: built-in roster, then `.compass/meta/models.yaml` project override, then `COMPASS_MODEL_<AGENT>` / `COMPASS_EFFORT_<AGENT>` environment
   - `compass models` output run in this repo: builder sonnet high, tester sonnet high, validator opus high, planner opus high; no `.compass/meta/models.yaml` exists
   - Marks: source code read plus command run, n/a, n/a, n/a, convergence: `.claude/agents/{builder,tester,validator}.md` frontmatter matches the roster

7. **The resolved model reaches a run only through agent frontmatter written by `compass apply-models`.** The build and autopilot skills name agents to spawn and never pass a model or effort per spawn (a grep for `model` in `plugin/skills/build/SKILL.md` and for `model:` in `plugin/skills/autopilot/SKILL.md` returns no spawn parameter). `apply-models` rewrites only `model:` and `effort:` lines of the installed agent files; an `inherit` resolution writes no `model:` line (confidence: high).
   - `plugin/cli/commands/apply_models.py:1-12` - rewrites frontmatter only
   - `plugin/skills/setup/SKILL.md:102-118` - setup runs `apply-models`; `plugin/skills/checkup/SKILL.md:23` - checkup compares frontmatter to roster
   - Marks: source code read, n/a, n/a, n/a, single source

8. **`compass resolve-model` can answer a per-agent query at spawn time but no skill, agent or hook calls it.** Its only references are its own file, the CLI command table and the methodology skill, which states it "awaits its wiring verdict" with `touched` and `admit-check`. Usage count shows `apply-models` 63 invocations; `resolve-model` is unwired (confidence: high).
   - `plugin/cli/commands/resolve_model.py:1-8` - prints `<model> <effort>` for one agent, takes no task argument
   - `plugin/skills/methodology/SKILL.md:279` - "live or retire by measured use, not by guess"
   - `.compass/meta/usage.yaml` - `apply-models` count 63, last 2026-11-21
   - Marks: grep for callers plus source read, n/a, n/a, n/a, single source

9. **No checking station varies by difficulty or model; every station runs in full on every task.**
   - Pre-build tester: runs for every selected task whose `files:` include executable source; a task without executable source records `--not-required`, a file-type switch, not a size one (`plugin/skills/build/SKILL.md:28-34`).
   - Post-build tester: spawned after every builder, and again after every merge (`plugin/skills/build/SKILL.md:39,48`); the tester's own failure modes forbid running only part of the suite (`plugin/templates/agents/tester.md:137`).
   - Builder self-review: step 8 spawns a code-review sub-agent on every diff with a fixed charter (`plugin/templates/agents/builder.md:63-67`).
   - Validator: offered as an optional step at the end of a build (`plugin/skills/build/SKILL.md:87`); once run, adversarial probing is "mandatory" with at least one probe regardless of task (`plugin/templates/agents/validator.md:114-116`, `:229`).
   - Autopilot: "Skipping the tester because 'this is small.' It always runs" and the validator "is the final gate" (`plugin/skills/autopilot/SKILL.md:120-121`).
   - The only places a size gate exists: autopilot hard-exits on L or larger (`plugin/skills/autopilot/SKILL.md:14,26-28`), which narrows what enters autopilot and does not change checking inside it. `agent-frontmatter.md:12` says `maxTurns: [15-60 based on complexity]`, an authoring guide for per-agent caps, fixed per agent in the files (builder 50, tester 30, validator 25).
   - Confidence: high. Marks: source code read across five files, n/a, n/a, n/a, convergence: five independent files agree.

10. **The vault's recorded sizes are loosely tied to the planner rubric.** Of 250 task lines with a `complexity:` letter in `.compass/plans/` (S 96, M 121, L 31, XS 2), the mean file count is S 2.27, M 3.34, L 3.84. Against the rubric's file bounds: 59 of 96 S tasks list more than 1 file, and 20 of 31 L tasks list fewer than 5. XS is used 2 times and is absent from the rubric (confidence: medium; computed by a script over plan task lines, a task listed in more than one plan file would count twice, not checked).
    - `plugin/templates/agents/planner.md:149-153` - rubric
    - `.compass/plans/PLAN-008-rolling-wave.md:120`, `PLAN-010-invisible-capture.md:126` - the two `XS` lines
    - Marks: counted from vault data (aggregates only), n/a, n/a, n/a, single source
    - Note: the rubric pairs a file count with a judged "some complexity" or "significant complexity" word, so the table does not determine the letter from `files:` alone.

11. **A planner-set letter is a judgment, not a function of the task, so it would not give the same answer twice by itself.** The planner is told "use your judgment on wave boundaries and task sizes" (`plugin/templates/agents/planner.md:43`). The same task text re-planned by another planner run, or a different model, can receive a different letter. The recorded letter is stable only after it is written into the plan: reading it back is deterministic, assigning it is not (confidence: medium; inferred from the rubric text and the finding 10 counts, not tested by re-planning).
    - Marks: inferred from source plus vault counts, n/a, n/a, n/a, single source

12. **What a checking level could key on today, by determinism of the value.** Documenting options, not choosing:
    - `complexity:` letter: present on 250 detailed task lines, human-reviewed at plan approval, stable once written; assigned by judgment; absent on intent lines until promotion (findings 1, 2, 10, 11).
    - `files:` list length and the executable-source test: already machine-readable by `TASK_LINE` neighbors and already used by the pre-build station's `--not-required` switch (`plugin/skills/build/SKILL.md:28,34`); not currently used for a level.
    - The model tier and effort from `compass resolve-model <agent>`: deterministic for a given install and project override, task-independent (findings 6-8).
    - `fix_loop_cycles` per task: an after-the-fact difficulty measure available only after the stations have already run (finding 4); it cannot set a level before the stations.
    - `kind:` field (`prototype`, `recall`): 8 prototype lines and 1 recall line in plans, read by the build flow's 7d step only (`plugin/skills/build/SKILL.md:68`).
    - Confidence: medium. Marks: source and vault counts, n/a, n/a, n/a, single source.

## Judgment: could the existing signal key a checking level?

Stated as what the evidence supports, no recommendation:

- Yes in form: `complexity:` is the one per-task field, set before the build, recorded in the plan and in `active.md`, and visible to the human at approval, so a level read from it is deterministic once the plan is written (findings 1, 2, 4).
- Not yet in substance: no code parses it, no station reads it, and the letter's meaning is loose against its own rubric in the vault (findings 3, 9, 10, 11). Two gaps would have to be closed by someone with authority to decide: a defined rule from letter or `files:` to level, and a place the chosen level is recorded (finding 4 shows no field for it today).
- The "same model" half of the spec's sentence has a deterministic key today: the roster, override and environment resolution in `modelslib` (finding 6). It is per agent and bound at install by `apply-models`, so a per-task model choice would need `resolve-model` wired or a spawn-time model parameter (findings 7, 8).

## Gaps

- Whether the planner's letters are repeatable on the same task: untested. A re-plan experiment on a sample of existing tasks would settle it.
- Whether letters track actual checking cost or defects caught: axis 2 covers station cost; no per-task cost or defect record joins to `complexity:` in what was read.
- The Agent tool's spawn parameters for a per-spawn model or effort override were not read from source here; findings 7 and 8 rest on the skills' text, which never passes one.
- Prior-art on difficulty-keyed depth belongs to axis 4 and was not covered here.

## Contradictions

- `plugin/templates/agents/planner.md:149-153` defines S as "single file" and L as "5+ files", yet the vault holds many S tasks listing more than one file and many L tasks listing fewer than five (finding 10). The rubric names file counts and a judged word; the plans follow the judged word.
