---
title: "Axis 3: Part-by-part re-baseline on the bench harness"
type: research
status: complete
confidence: medium
area: tooling
tags: [tokens, cost, harness, ablation, measurement, bench]
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "6faced1"
author: researcher
summary: "how a with-against-without run of each harness part would run on bench/overhead after a model change, what injects a variant, what is recorded, what a per-part effect costs, and what the harness lacks"
---

# Axis 3: Part-by-part re-baseline on the bench harness

From [[SPEC-034-checking-cost-follows-task-and-model]]. Index: [[index]]. Prior work read: [[RESEARCH-axis-7-optimization-loop]], [[RESEARCH-axis-4-topics-and-sample-size]], [[REVIEW-whole-overhead]], [[RESEARCH-whole-overhead-pilot]], [[RESEARCH-whole-overhead-pilot-run-1]].

## Question

How would a with-against-without measurement of each harness part (thresholds, phase splits, validator cadence, tester stations, prompt rules, emphasis markers) run on the existing bench harness after a model or host change, and what does the harness lack for it?

## Methodology

Repository mining (empirical study of an artifact): the question is how an existing system behaves, so the bench code, its tests' contracts and the pilot records were read directly; no external source was needed. No grading disclosure was withheld: the brief carried `grading: allowed`, so each finding carries a Grade weighing evidence type (code read directly counts high; a computed estimate counts lower than a measurement).

## Findings

### A. What runs today

1. **Two harnesses exist; only `bench/overhead/` is live.** (confidence: high)
   `bench/README.md` documents arms driven by `agents/compass-agent.sh` and `agents/baseline-agent.sh` over Terminal-Bench, SWE-bench Pro and SWE-Lancer, but the README itself says those wrappers are not on disk and `bench/agents/` does not exist. `bench/configs/arm-*.yaml` pin `claude-opus-4-7`, budget 2 USD, and no module under `bench/overhead/` reads them.
   - `bench/README.md:23-25` (wrappers not on disk); `bench/configs/arm-compass.yaml:11-12`; grep of `bench/overhead/*.py` for `configs/` finds nothing; `bench/agents/` absent
   - Marks: code read; n/a; n/a; n/a; 3 sources agree (README, configs, filesystem)
   - Grade: high

2. **A run is one build of a frozen topic in one arm, driven by a simulated human, judged against a frozen goal list.** (confidence: high)
   `pilot.py` probes topics, freezes goal lists, builds each topic `runs_per_arm` times per arm (arm order alternates by `(index + run) % 2`), then judges each build. `drive.py` holds one `claude -p` stream-json session open and asks the simulated human at each end of turn; `judge.py` scores each goal item `met` / `partly met` / `not met`.
   - `bench/overhead/pilot.py:1-20`, `:363-370` (slots, alternating arm order); `drive.py:1-60`; `judge.py:22-26`
   - Marks: code read; n/a; n/a; n/a; 1 source
   - Grade: high

3. **The only two arms are `compass` and `baseline`; the arm list is a constant, not a parameter.** (confidence: high)
   `records.ARMS = ("compass", "baseline")`; `drive_build` raises on any other arm; `record_session` validates `arm` against it; `stats.py` and `pilot.py` aggregate keyed `{"compass": [...], "baseline": [...]}`. A variant arm (plugin minus one part) has no name, no record value and no aggregate slot.
   - `bench/overhead/records.py:41`, `:204`; `drive.py:~395-398` (arm check); `stats.py:3-4`; `pilot.py:518`, `:597`
   - Marks: code read; n/a; n/a; n/a; 4 sources agree
   - Grade: high

4. **The compass arm loads the plugin from `<repo_root>/plugin`, requires it clean in git, and installs it into the project twice-removed from the working tree.** (confidence: high)
   `check_plugin_clean` refuses unless `repo_root` is the top of a git work tree and `plugin/` has no staged, modified or untracked change; it returns HEAD as the commit id recorded with the run. A setup session loads `--plugin-dir <repo_root>/plugin` and runs `/compass:setup`; the build session then runs from the project's own `.claude/` install, without `--plugin-dir`.
   - `bench/overhead/launch.py:192-213`, `:398-399`; `drive.py:414-415`, `:17-27` (docstring on the two-stage load)
   - Marks: code read; n/a; n/a; n/a; 2 sources agree
   - Grade: high

### B. How a variant could be injected, part by part

5. **Variant injection path: a committed copy of the repository with one edit under `plugin/`, passed as `repo_root`.** (confidence: medium)
   Because the harness refuses a dirty `plugin/` and records HEAD, an edited variant has to be a commit in a separate clone or worktree; `repo_root` is a parameter of `drive_build` and `run_session`. The driver also pins the project's `plugin.yaml` `commit:` to `git ls-remote origin HEAD` of `repo_root`, so the start-of-session self-update treats the install as current instead of overwriting it; a variant clone therefore needs an `origin` the pin can read. The overwrite-avoidance part is inferred from the pin's stated purpose, not tested.
   - `bench/overhead/drive.py:224-243` (`remote_head`, `pin_commit`), `:415`, `:534`; `launch.py:192-213`; `plugin/cli/commands/self_update.py:9` (sha-gated update)
   - Marks: code read plus inference; n/a; n/a; n/a; 2 sources agree
   - Grade: medium

6. **Thresholds (context stop) can be varied with no plugin edit: environment variables the harness passes through.** (confidence: high for the variables, medium for the pass-through)
   `context_check.py` reads `COMPASS_CONTEXT_THRESHOLD` (default 80) and `COMPASS_CONTEXT_FINAL_THRESHOLD` (default 95), plus `COMPASS_CONTEXT_WINDOW`. `launch.session_environment` drops credentials, provider, model-selection and git-location variables and nothing named `COMPASS_*`, so a variable set in `parent_env` reaches the build. The hook description says the stop fires once at each level; a headless run has no human to read the suggestion, so a threshold variant's effect in a simulated-human build is untested.
   - `plugin/cli/commands/context_check.py:47-48`, `:83`, `:90`; `bench/overhead/launch.py:54-66`, `:142-151`; `plugin/hooks/hooks.json:2` (hook description)
   - Marks: code read; n/a; n/a; n/a; 2 sources agree
   - Grade: high (variables), medium (effect in a headless build)

7. **Per-agent model and effort are also environment-variable parts.** (confidence: high)
   `modelslib.resolve` takes the built-in tier roster, then `.compass/meta/models.yaml`, then `COMPASS_MODEL_<AGENT>` and `COMPASS_EFFORT_<AGENT>`; precedence is environment highest. `DEFAULT_ROSTER` puts planner, validator, reviewer and debug on `strong` and builder, researcher, tester on `balanced`. `/compass:setup` applies the table to agent frontmatter, so an environment override has to be set before the setup session to reach the installed agent files.
   - `plugin/cli/modelslib.py:1-12`, `:24-50`, `:206`; `plugin/cli/commands/apply_models.py`; `plugin/templates/agents/*.md`
   - Marks: code read; n/a; n/a; n/a; 1 source; the "set before setup" ordering is inferred
   - Grade: high (precedence), medium (ordering)

8. **Phase splits, validator cadence and tester stations live in skill, command and agent text; a variant is a text edit.** (confidence: high)
   The two tester stations and the validator's place after builders are prose in `.claude/skills/methodology/SKILL.md` ("Task execution", "Parallel execution", "Testing mandate") and the agent files under `plugin/templates/agents/` (`tester.md`, `validator.md`, `builder.md`). No flag turns a station off. Removing a station is an edit to those files committed in the variant clone.
   - `.claude/skills/methodology/SKILL.md` (Task execution; Parallel execution; Testing mandate); `plugin/templates/agents/tester.md`, `validator.md`
   - Marks: code and skill text read; n/a; n/a; n/a; 2 sources agree
   - Grade: high

9. **Prompt rules and emphasis markers are the rules files plus agent bodies; the emphasis markers are countable by grep.** (confidence: high)
   Rules ship from `plugin/templates/rules/` (`compass-pipeline.md`, `session-start.md`, `wikilinks.md`, `compass-agent-patterns.md`). `CRITICAL` or `MUST` appears 6 times across the shipped agent and rule templates (grep count). The pilot attributes 2.5% of a Compass build's weighted tokens to `attachment:instructions` and 3.7% to the system-prompt prefix, which bounds what rule text can move.
   - `plugin/templates/rules/`; grep `CRITICAL|MUST` over `plugin/templates/agents/*.md` and `plugin/templates/rules/*.md` returns 6; `RESEARCH-whole-overhead-pilot.md` source table
   - Marks: code read; n/a; n/a; n/a; 2 sources agree
   - Grade: high

10. **Sub-line or per-rule variants have no sensor today: tokens are recorded per request kind and source family, not per rule.** (confidence: high)
    `token_profile.py` splits a build by session kind, source family (output, tool result, skill body, attachment, prefix) and source (for example `skill body:preloaded`, `attachment:instructions`); `attribute.py ablate` measures the first-request tokens of one file at a time with `claude -p "hi"`. Neither reports the effect of a rule on behavior; the first reports where tokens went.
    - `bench/overhead/token_profile.py` (`--by-agent`); `bench/overhead/attribute.py:556-640` (`run_ablation`), `:1058-1076` (`ablate`); [[REVIEW-whole-overhead]] settled item h1
    - Marks: code read; n/a; n/a; n/a; 2 sources agree
    - Grade: high

### C. What a run records

11. **Each session appends one allowlisted row: tokens by model and kind, a weighted total, plugin commit, Claude Code version, outcome.** (confidence: high)
    Fields: `arm`, `plugin_sha`, `claude_code_version`, `results`, `duration_ms`, per-model `input/output/cache_read/cache_write`, `weighted`, `unpriced_models`. The weight is list price relative to fresh input (output 5, cache write 1.25, cache read 0.1, lower for newer families). No topic, path or model output is stored. There is no part label, variant id or defect field.
    - `bench/overhead/records.py:194-233`; `bench/overhead/README.md` "Records"
    - Marks: code read; n/a; n/a; n/a; 2 sources agree
    - Grade: high

12. **Success is the judge's goal counts plus builder tests and validator verdict stored beside them.** (confidence: high)
    The judge scores each frozen goal item; `recorded.builder_tests` and `recorded.validator_verdict` are stored but "take no part in the counts". The judge runs on `claude-opus-5-5`. There is no count of defects caught per station and no seeded-defect step in `bench/overhead/`; the seeded-defect method exists in the vault for test quality (15 seeded defects, bar arm 15/15 against 13/15), run against source modules rather than against builds.
    - `bench/overhead/judge.py:26`, `:252-294`; `bench/overhead/README.md` "Comparing launches"; `.compass/research/test-quality/RESEARCH-test-quality-bar-validation.md:19`
    - Marks: code read; vault record, single author; n/a; n/a; 2 sources agree
    - Grade: high (code), medium (the seeded-defect result as a template)

13. **`compare.py` gives a per-agent-type before/after with a bootstrap interval and an outcome guard that blocks on any count difference.** (confidence: high)
    It pools sessions per agent type across saved profiles, prints the mean weighted tokens per launch, the change, and a 95% bootstrap interval (2000 resamples, fixed seed), and needs two sessions on each side. With `--outcomes-before/--outcomes-after`, any difference in summed goal counts or test tallies prints "outcome differs, so no token verdict". The guard is exact-equality, not a noninferiority margin, so it reports a block rather than a tolerance.
    - `bench/overhead/compare.py:1-16`, `:165-190`; `bench/overhead/README.md` "Comparing launches"
    - Marks: code read; n/a; n/a; n/a; 2 sources agree
    - Grade: high

14. **The sample-size machinery models a two-arm paired share, which maps onto one part at a time.** (confidence: high)
    `stats.batch_size` is `(z_0.975 + z_0.8)^2 * 2 * sigma_w^2 / delta^2`, minimum 2, with `sigma_w` the pooled within-topic SD of pair shares (`pooled_within_sd`); `builds_per_window` divides a 5-hour window by mean build seconds. Pairing is by topic and run index, so a part-removed arm would pair with the full-Compass arm by the same index.
    - `bench/overhead/stats.py:1-12`, `:59`, `:136`, `:192`; `bench/overhead/pilot.py:363-370`
    - Marks: code read; n/a; n/a; n/a; 2 sources agree (code and [[RESEARCH-axis-4-topics-and-sample-size]])
    - Grade: high

### D. Cost and run count

15. **Measured cost of one build today: about 10.1M weighted tokens (compass arm), 5256 s wall, 3 builds per 5-hour window.** (confidence: medium)
    From the second pilot: 12 builds on 3 topics; baseline arm 2.32M weighted; four Compass-arm builds hit the wall-time or turn cap, so the figures are lower bounds. Defaults are caps of 9000 s, 400 turns and 50 USD per build. One station shows the cost of checking: in the pilot the tester sessions took 29.5% and the validator 2.0% of a Compass build's weighted tokens, builder 27.9%.
    - `RESEARCH-whole-overhead-pilot.md` "Cost and time of one build" and "Where the tokens go"; `bench/overhead/drive.py:79-81`
    - Marks: harness measurement, 12 builds, one run, own pilot; n/a; n/a; n/a; 1 source
    - Grade: medium (measured, small n, capped builds)

16. **The measured spread is unusable for sizing: the pilot's within-topic SD was 1.72 on 3 degrees of freedom, giving a 7801-build point estimate.** (confidence: high that it is unusable, low for any per-part figure)
    The SD was inflated by capped builds and three topics; the first pilot's 0.0367 came from a run its own write-up marks invalid. Each is a whole-Compass share, not the effect of one part. No measured SD of a per-part token or goal-count difference exists anywhere in the repository.
    - `RESEARCH-whole-overhead-pilot.md` "Batch size" (7801 point, 23282 upper); `RESEARCH-whole-overhead-pilot-run-1.md` "Validity of this run"
    - Marks: harness measurement; n/a; n/a; n/a; 2 sources disagree on the SD by 47x (explained by the first run's faults)
    - Grade: high for the unusability, low for planning use

17. **Per-part run counts follow the existing formula; an illustrative table, with the SD ratio a guess.** (confidence: low)
    Builds per arm n = 15.7 x (SD / delta)^2, where delta is the effect to see and SD is the per-build SD of the same quantity:
    | SD / delta | 1 | 3 | 5 | 10 |
    |---|---|---|---|---|
    | builds per arm | 16 | 141 | 393 | 1570 |
    At 3 builds per window and two arms, 16 builds per arm is about 11 windows (55 hours) per part, and 141 is about 94 windows. Six parts (thresholds, phase splits, validator cadence, tester stations, prompt rules, emphasis markers) with one removed arm each share one full-Compass arm, so the arm count is 1 + 6, not 12. Paired repeats of a topic (K) cut variance with a ceiling of 2/3 ([[RESEARCH-axis-7-optimization-loop]] finding 23). A single token-share of the effect is smaller than the whole overhead, so SD / delta is larger than for the whole share; its size is not measured.
    - `bench/overhead/stats.py:136-160` (formula); `RESEARCH-whole-overhead-pilot.md` (3 builds per window); arithmetic done here
    - Marks: computed from code formula and one measurement; n/a; n/a; n/a; 1 source
    - Grade: low (the ratio is an assumption)

18. **A cheaper screen exists in the vault's loop machinery but its judge has no noise band and its sensor cost is off the budget.** (confidence: high)
    A loop sensor that runs builds would not count its spend toward the daily or lifetime budget, the sensor timeout is 120 s in LOOP-003, and `judge()` calls any decrease helpful. A multi-hour build sensor would need those changed first.
    - [[RESEARCH-axis-7-optimization-loop]] findings 3, 4, 5 (`plugin/cli/sensorlib.py:528-545`; `plugin/cli/looprunner.py:658`, `:786-803`)
    - Marks: code read in the prior axis; n/a; n/a; n/a; 1 source
    - Grade: high

### E. How Compass knows the model or host changed today

19. **Compass records no model id in `plugin.yaml` and has no model-change trigger.** (confidence: high)
    `meta/plugin.yaml` holds plugin name, version, commit, source, repository, install time and mode; no model, no host. `meta/installed.json` and `usage.yaml` hold nothing keyed to a model id for this purpose (grep found none for `installed.json`). The host is the string `claude-code` by default in `hostlib.DEFAULT_HOSTS` and `modelslib.DEFAULT_HOST`.
    - `.compass/meta/plugin.yaml`; `plugin/cli/hostlib.py:33`; `plugin/cli/modelslib.py:24`
    - Marks: file and code read; n/a; n/a; n/a; 3 sources agree
    - Grade: high

20. **Where a model id is observable: session transcripts and the harness's own records.** (confidence: high)
    `sessionslib.model_id` reads the model from the transcript's attachment, falling back to the last main-agent assistant record, and appends an extended-window suffix when usage exceeds the standard window; `context_check` uses the same to pick the window for the 80% / 95% stop. The harness row stores `claude_code_version` and per-model token counts, so two rows' `models` keys and versions show a model or CLI change after the fact.
    - `plugin/cli/sessionslib.py:190-225`; `plugin/cli/commands/context_check.py:18`, `:119-128`; `bench/overhead/records.py:158-229`
    - Marks: code read; n/a; n/a; n/a; 2 sources agree
    - Grade: high

21. **The harness fixes its own model choices apart from the build's, and they are older than the session's current model.** (confidence: high)
    `ANTHROPIC_MODEL` and `ANTHROPIC_DEFAULT_*_MODEL` are removed from the session environment and `drive.py` passes no `--model`, so the build model is whatever Claude Code defaults to for the account. The simulated human runs `claude-sonnet-4-6`, topic generation `claude-sonnet-4-6`, the judge `claude-opus-5-5`; `arm-*.yaml` name `claude-opus-4-7`. The harness therefore has no field that states which model built a given build other than the per-model token keys in the row.
    - `bench/overhead/launch.py:54-66`; `bench/overhead/drive.py:~395-398` (command, no `--model`); `human.py:53`, `:281`; `topics.py:33`, `:167`; `judge.py:26`; `bench/configs/arm-compass.yaml:12`
    - Marks: code read; n/a; n/a; n/a; 5 sources agree
    - Grade: high

22. **The planned trigger exists as an unbuilt task: re-measure the without-Compass arm on a model or Claude Code change.** (confidence: high)
    TASK-256 of [[PLAN-028-whole-overhead-on-real-projects]] is unchecked. The review states neither it nor [[PLAN-029-crafted-agent-context]] "ablates scaffold parts per model", and the station ablation (C4) is open.
    - `.compass/plans/PLAN-028-whole-overhead-on-real-projects.md:147` (TASK-256); [[REVIEW-llm-research-for-compass]] A5 "Covered" line and table row C4
    - Marks: vault read; n/a; n/a; n/a; 2 sources agree
    - Grade: high

### F. What the harness lacks for part-by-part runs

23. **Gap list, each read from code:**
    - A variant arm label and a place for it in records, run log, `stats.py` and `pilot.py` aggregates (finding 3).
    - A way to build a variant plugin tree without a manual clone; the harness has only a "plugin/ must be clean" gate (finding 4, `launch.py:192-213`).
    - A per-build defect measure: judge goal counts and the stored `validator_verdict` only (finding 12). A part that checks (tester station, validator cadence) is valued by defects caught, which is not recorded.
    - A noninferiority comparison for quality: `compare.py` blocks on any count difference (finding 13), so a variant that differs by one goal item prints no token verdict.
    - A station-level token breakdown per variant is available (`--by-agent`), but a station's catches are not.
    - A recorded model id for the build and a trigger comparing it with the last baseline's (findings 19 to 22).
    - A model-change-safe baseline: the harness defaults the build model implicitly, so a rerun after a model change differs from the earlier baseline in two things at once (model, and the part removed) unless the full-Compass arm is rerun in the same batch.
    - Confidence: high for each item as a code-read absence; medium that the list is complete.
    - Marks: code read; n/a; n/a; n/a; 1 source
    - Grade: high for absences, medium for completeness

## Contradictions

- Findings 1 and 21: `bench/configs/arm-*.yaml` and `bench/README.md` describe a model-pinned, benchmark-driven harness (`claude-opus-4-7`, 2 USD budget); the live `bench/overhead/` code reads none of it and defaults the build model implicitly with a 50 USD cap.
- Findings 15 and 16: the pilot's measured cost and the SD it produced do not support each other as sizing inputs; the SD came from capped builds on three topics.

## Gaps

- No measured SD of a per-part effect (token or goal-count difference) exists; the table in finding 17 rests on an assumed ratio. Closing it takes a small repeated pilot of one removed part.
- Whether a threshold or station variant shows any effect in a simulated-human build is untested; context-stop suggestions need a human turn to be read (finding 6).
- The overwrite-avoidance claim in finding 5 (a variant commit not being replaced by self-update through the pin) is inferred from the pin's purpose; a dry run with a single throwaway build would confirm it. No full bench run was launched in this pass.
- Whether defects caught can be counted from the build record (validator verdicts in transcripts) or needs a seeded-defect step was not determined here; the seeded-defect precedent lives in the test-quality research.
- Emphasis-marker removal across the roughly 6 markers in agent and rule templates is too small to detect through token share; a per-line effect would need a quality metric rather than a token one. Prior art on one-line ablation sits in [[REVIEW-llm-research-for-compass]] A5, which this axis did not re-verify.

## Candidate changes for Compass

Ranked by impact. Each is a documented option for the planner, not a decision.

1. **Name a variant arm and a part label in the harness.** North star: accuracy (parts found unhelpful by measurement, not guess). Change in `bench/overhead/`: widen `records.ARMS` and the aggregates in `stats.py` / `pilot.py` to a variant id, and record it in each row. Covered: no (finding 3).
2. **Record the build model id and trigger a re-baseline on change.** North star: accuracy, perfect memory. Change: a model field in the record row and in the baseline's stored metadata, and a comparison step that flags a new model or Claude Code version (the unbuilt TASK-256 of [[PLAN-028-whole-overhead-on-real-projects]]). Covered: partly (rows already hold per-model token keys and CLI version, findings 11, 20, 22).
3. **Add a per-build defect measure and a noninferiority outcome guard.** North star: accuracy. Change: count defects caught per station (seeded defects or validator findings) and replace `compare.py`'s exact-equality block with a stated margin. Covered: no (findings 12, 13).
4. **Start with the cheap variants: environment-variable parts first.** North star: low token usage. Thresholds (`COMPASS_CONTEXT_THRESHOLD`) and per-agent model/effort (`COMPASS_MODEL_<AGENT>`) vary with no plugin edit; text parts (stations, validator cadence, rules, emphasis) need a committed variant clone. Covered: the variables exist, no harness use of them (findings 6, 7).
5. **Measure the SD of a per-part effect with a small repeated pilot before sizing any batch.** North star: accuracy, low token usage. Change: one removed part, K repeats on a few topics, feed the SD to `stats.batch_size`. Covered: the formula exists, the per-part SD does not (findings 16, 17).
