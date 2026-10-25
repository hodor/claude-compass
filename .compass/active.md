---
title: Active Tasks
updated: 2026-09-13
---

# Active Tasks

## Sizing + discoverability initiative

Triggered by a live failure in another project: a vision session produced seven epic-sized needs and Compass proposed seven flat specs with no signal anything was wrong.

- [ ] Open: pin the project where the seven-monster-specs session happened ([[LESSON-pin-the-motivating-datum]]).

## Per-domain organization initiative

- [ ] D-13 follow-up: grep across all indexes made the most obvious first move for agents (capability + rule nudge; folds into TASK-119's strategy work)
- [ ] v0.15.0's premature skill/sync edits were reverted; index depth-0 rule stays (shipped); everything further waits on the plan.

## Research covers the whole spec (SPEC-023)

- [ ] [[specs/pipeline/SPEC-024-walled-sources-through-the-browser]] awaits the human's ruling.
- [ ] Open: a text-and-data-mining request to ACM is the human's to send if wanted.

## PLAN-018 Wave 2: prove the stop rule, exercise the list, close the autopilot gap

Plan: [[PLAN-018-research-covers-the-whole-spec]]. Wave 1 shipped as v0.24.0 on 2026-09-14; its manual checks await the human. Wave 2 starts on his word.

- [ ] TASK-129: Run the completeness scorer against a real spec and a real research document and record whether it detects a gap a human agrees is a gap - files: [.compass/research/pipeline/RESEARCH-spec-coverage-experiment.md], decisions: [SPEC-023-research-covers-the-whole-spec/D-05], commit-upfront: the experiment's shape is inferred from the code contract and fixed now, because a later change to it would invalidate everything written against its result
- [ ] TASK-131: Exercise every shipped retriever against its live source and record the result beside the entry - complexity: S, depends_on: none, files: [plugin/cli/sources.yaml, plugin/cli/tests/test_sourceslib.py], decisions: [SPEC-023-research-covers-the-whole-spec/D-09, SPEC-023-research-covers-the-whole-spec/D-03]
- [ ] TASK-135: Make the autopilot research step call the entry point, so a pipeline run gets the derivation, the axis gate and the grading disclosure - complexity: S, depends_on: none, files: [plugin/skills/autopilot/SKILL.md], decisions: [SPEC-023-research-covers-the-whole-spec/D-01, SPEC-023-research-covers-the-whole-spec/D-05]

## PLAN-019: stop and suggest a handoff at 80% context

Plan: [[PLAN-019-stop-at-80-percent-context]]. TASK-137 and TASK-138 shipped as v0.26.0.

- [ ] TASK-139: Live acceptance in an interactive Claude Code session - the human watches the stop and the handoff (`COMPASS_CONTEXT_THRESHOLD` lowers the line).

## PLAN-020: clone old sessions to harvest their lessons

Plan: [[PLAN-020-clone-old-sessions]].

- [ ] TASK-146: Live acceptance on this repo

## PLAN-021 Wave 2: judge, schedule, ast-grep sensor, skill, release

Plan: [[PLAN-021-control-loops]].

- [ ] TASK-161: A code loop end to end: an ast-grep sensor adapter, then a loop that removes a bad pattern from a real repository the human names, run to its stop - complexity: L, depends_on: TASK-158, TASK-159
- [ ] TASK-160: `/compass:loop`: guided creation through steps 0 to 7 - complexity: M, depends_on: TASK-158, TASK-159, TASK-161
- [ ] TASK-162: The Maya recipe on the local lane, marked untested on this machine - complexity: S, depends_on: TASK-160
- [ ] TASK-163: Teach the vault conventions about loops and ship 0.29.0 - complexity: M, depends_on: TASK-158, TASK-159, TASK-160, TASK-161, TASK-162

## Next Up

- [ ] SubagentStop typed-signal fix, fleet-wide (payload evidence captured: `agent_type` empty string). Queued in [[backlog]].
- [ ] [[SPEC-006-multi-host-agent-cli-support]] hosts: hermes first, then deepseek-harness (dsh; fit assessed in [[research/distribution/RESEARCH-deepseek-harness-fit]], 2026-09-04), then Kimi Code / Codex.
- [ ] Blinded rerun of the test-bar experiment ([[LESSON-blind-the-author-in-self-validation]]).
- [ ] Review and approve all plugin files - 3/21 approved, paused since 2026-03-12; largely superseded by the per-file reviews every later plan performed.

## Blocked

- Fleet pushes outstanding from the v0.6.x waves: 7 projects have no git, 2 no remote, 1 has all Compass paths gitignored (private project 1), 4 were push-rejected behind their remotes (3 private project 2 checkouts + wt-spec056) and need a human pull/rebase call. private project 3's remote no longer exists.

## PLAN-022: review documents in Obsidian

Plan: [[PLAN-022-review-in-obsidian]]. Wave 1 ends when the human runs one real review through the shipped parts.

- [ ] TASK-165: Ship the Compass Review plugin at `plugin/obsidian/compass-review/` from the prototype in `.compass/.obsidian/plugins/compass-review/`, with a Node test harness that stubs the `obsidian` module and drives the request, bar, verdict and step-aside paths - complexity: M, depends_on: none, files: [plugin/obsidian/compass-review/main.js, plugin/obsidian/compass-review/manifest.json, plugin/obsidian/compass-review/styles.css, plugin/obsidian/tests/test_main.js, plugin/cli/tests/test_obsidian_plugin.py]
- [ ] TASK-166: `compass review <file> [--title T] [--timeout S] [--no-wait]` writes the request under the vault's `tmp/review/`, opens the `obsidian://compass-review` link, waits for the verdict, and prints the verdict JSON then the file as the human left it; exit 0 on a verdict, 1 on timeout, 2 when not configured; `compass review --status` prints pending requests - complexity: M, depends_on: none, files: [plugin/cli/commands/review.py, plugin/cli/reviewlib.py, plugin/cli/maincli.py, plugin/cli/tests/test_review.py]
- [ ] TASK-167: `compass guard` denies a subagent's Write or Edit to a file that has a pending review request, naming the request and that the file is the human's until the verdict - complexity: S, depends_on: TASK-166, files: [plugin/cli/commands/guard.py, plugin/cli/tests/test_guard.py]
- [ ] TASK-168: Setup and update copy the plugin into the vault's `.obsidian/plugins/compass-review/` when `.obsidian/` exists, add it to `community-plugins.json` without dropping other entries, and never create `.obsidian/`; doctor reports the plugin as absent, installed but off, or on, and when off prints the steps to turn it on (Settings, Community plugins, leave restricted mode, enable Compass Review) - complexity: M, depends_on: TASK-165, files: [plugin/skills/setup/SKILL.md, plugin/skills/update/SKILL.md, plugin/cli/commands/self_update.py, plugin/cli/commands/doctor.py, plugin/cli/tests/test_doctor.py, plugin/cli/tests/test_self_update.py]
- [ ] TASK-169: Setup installs `.compass/review-inbox.base` (draft specs, draft plans, pending review requests) and `.compass/lessons.base` (lessons by area and category, sorted by score), each created only when absent - complexity: S, depends_on: none, files: [plugin/templates/vault/review-inbox.base, plugin/templates/vault/lessons.base, plugin/skills/setup/SKILL.md, plugin/cli/tests/test_vault_bases.py]
- [ ] TASK-170: Experiment: with `compass review` running in the background and an `AskUserQuestion` open, the human approves in Obsidian; record whether the session acts on the verdict before the question is answered, and the shape gates take as a result - complexity: S, depends_on: TASK-166, files: [.compass/research/RESEARCH-review-in-obsidian.md]
