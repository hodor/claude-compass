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

Plan: [[PLAN-028-whole-overhead-on-real-projects]].

- [ ] TASK-244: You log the sandbox config into your Claude subscription, once, in PowerShell: `$env:CLAUDE_CONFIG_DIR = "$HOME\.compass\overhead\claude-config"; claude`, then type `/login`, sign in with your subscription account in the browser, type `/exit`, and close that PowerShell window so the variable goes with it; a human step, nothing ships - complexity: S, depends_on: none, files: [~/.compass/overhead/claude-config/], decisions: [SPEC-032-whole-overhead-measured-on-real-projects/D-02], lessons: [LESSON-subscription-cost-is-an-estimate-not-a-budget]
- [ ] TASK-245: Sandbox, isolated launch and private records, repo-local in `bench/overhead/`: `sandbox.py` creates a project under the projects root (its own `git init`), lists projects, keeps one (copies it to a folder given with `--to`) and discards one (deletes the folder and runs `claude purge <path> --yes` with the sandbox config); `launch.py` builds the command line and environment of "The harness" section for any session, refuses to start when `plugin/` has uncommitted changes, runs the session, reads `stream-json`, and classifies its end as done, failed or usage-limit (a `rate_limit_event` with `status: rejected`, an `api_error` of `usage_limit_reached`, or exit 1 with nothing on stdout and an `isApiErrorMessage` entry at the transcript tail), keying on `api_error`, never on `subtype`; `records.py` counts each session as "The harness" section describes, adds list-price weights, and appends one allowlisted row per session to `~/.compass/overhead/records/<machine>.jsonl`; the shared fake `claude` replays canned `stream-json`: a clean run, a run with a subagent, a multi-turn session with a `/clear`, each of the three usage-limit shapes, and a crash; `bench/README.md` states its two wrapper scripts are not on disk and points to `bench/overhead/README.md` - complexity: L, depends_on: none, files: [bench/overhead/README.md, bench/overhead/sandbox.py, bench/overhead/launch.py, bench/overhead/records.py, bench/overhead/tests/conftest.py, bench/overhead/tests/fake_claude.py, bench/overhead/tests/test_sandbox.py, bench/overhead/tests/test_launch.py, bench/overhead/tests/test_records.py, bench/README.md], decisions: [SPEC-032-whole-overhead-measured-on-real-projects/D-02], lessons: [LESSON-subscription-cost-is-an-estimate-not-a-budget, LESSON-headless-worker-denies-tools-silently]
- [ ] TASK-246: The session driver and the simulated human, repo-local. `drive.py` holds one build session open as `claude -p --input-format stream-json --output-format stream-json --verbose` in the project, sends the opening message, and at every end of turn (a gate that ends its turn, Compass's stop at 80% of the context window, a question asked in prose) asks the simulated human for the next message, until the simulated human says the build is done or a cap is hit [guess: 90 minutes wall time, 400 turns, `--max-budget-usd 25` as a runaway guard only]. In the Compass arm it applies "The Compass under test" in "The harness" section and records the skill and agent counts of `system/init` before and after setup. `human.py` runs the simulated human as its own isolated session from its own folder: it holds the hidden brief from TASK-247, reveals a goal item only to a question that names it, has no solution knowledge, knows Compass's user commands from its README in the Compass arm, and answers at most 12 questions that reveal goal items [guess]; gate approvals and continue messages do not count, and once the budget is spent it answers "decide yourself". `hooks/answer_question.py` is a PreToolUse command hook the driver writes into the project's `.claude/settings.local.json`: it answers `AskUserQuestion` by returning `permissionDecision: allow` with `updatedInput` holding the questions and the simulated human's answers, and denies a Bash, Write or Edit call whose path leaves the project, any `gh` command and any `git push`. A live probe opens the task and keeps the first route under which `system/init` lists `AskUserQuestion`: `stream-json` input with the hook, then `--permission-prompt-tool` naming a tool of the harness's own stdio server passed with `--mcp-config`, then the Agent SDK in `bench/overhead/.venv`; the route found is recorded - complexity: L, depends_on: TASK-245, files: [bench/overhead/drive.py, bench/overhead/human.py, bench/overhead/permission_server.py, bench/overhead/hooks/answer_question.py, bench/overhead/tests/test_drive.py, bench/overhead/tests/test_human.py, bench/overhead/tests/test_answer_question.py], decisions: [SPEC-032-whole-overhead-measured-on-real-projects/D-01], lessons: [LESSON-headless-worker-denies-tools-silently, LESSON-blind-the-author-in-self-validation]
- [ ] TASK-247: Topics, frozen goals and the judge, repo-local. `topics.py` asks an isolated session to pick one project it would build, seeded or unseeded (ruling 2), and adds the pick to `~/.compass/overhead/topics/pool.json` under a random topic id. `goals.py` has a separate session, which never takes part in the build, turn the pick into a frozen goal list (each item checkable in the finished project, with a command to run where one exists) and the simulated human's hidden brief, stored beside the pool before any build of that topic. `judge.py` copies a finished project without `.git`, `.compass/`, `.claude/`, `CLAUDE.md` or Compass lines in `.gitignore`, runs a judge session on the copy that inspects the files and scores each goal item met, partly met or not met with the file or command output as its reason, and runs the goal list's commands; the builder's own tests and Compass's validator verdict are recorded beside the score and not counted - complexity: L, depends_on: TASK-245, files: [bench/overhead/topics.py, bench/overhead/goals.py, bench/overhead/judge.py, bench/overhead/tests/test_topics.py, bench/overhead/tests/test_goals.py, bench/overhead/tests/test_judge.py], decisions: [SPEC-032-whole-overhead-measured-on-real-projects/D-01], lessons: [LESSON-blind-the-author-in-self-validation, LESSON-score-the-do-nothing-baseline-before-running]
- [ ] TASK-248: The pilot, on the subscription, one session at a time, resumable from its own run log after a usage-limit halt by re-running the same command. First the topic probe: 10 unseeded and 10 seeded picks [guess], each placed in a code-defined kind and language class; the pool takes the form ruling 2 names. Then three topics enter the pool with frozen goals, and twelve builds run, each topic twice in each arm [guess], the first topic's pair first as a smoke check that stops the pilot on any headless blocker; each build is judged. The report, `research/whole-overhead/RESEARCH-whole-overhead-pilot.md`, gives: the weighted and raw overhead share per topic as a ratio of sums (Compass-arm tokens minus without-Compass tokens, summed over builds, over Compass-arm tokens summed); the spread between topics and between the two runs of one topic in each arm; the batch size for a 10% relative drop in the share at 95% confidence and 80% power [guess], from the point estimate of the within-topic spread and from its upper 80% chi-square bound; cost estimate, wall time, turns and builds per five-hour window; and each headless check: Compass's hooks under the flags, a review gate falling back to a picker with no window opened, whether `--plugin-dir` and setup together load Compass twice (the `system/init` counts), which built-in plugins loaded, `.claude/` unchanged by self-update, the capture workers counted, and how many frozen goal items the Compass arm's own spec dropped; all projects stay until TASK-250 - complexity: M, depends_on: TASK-244, TASK-246, TASK-247, files: [bench/overhead/pilot.py, bench/overhead/stats.py, bench/overhead/tests/test_pilot.py, bench/overhead/tests/test_stats.py, .compass/research/whole-overhead/RESEARCH-whole-overhead-pilot.md, .compass/research/whole-overhead/index.md], decisions: [SPEC-032-whole-overhead-measured-on-real-projects/D-01, SPEC-032-whole-overhead-measured-on-real-projects/D-02], lessons: [LESSON-score-the-do-nothing-baseline-before-running, LESSON-deterministic-fixtures-survive-scratch-wipes, LESSON-subscription-cost-is-an-estimate-not-a-budget]
- [ ] TASK-249: You grade four pilot builds, two from each arm, once: `bench/overhead/grade.py` prepares a copy of each the way the judge's copy is made, under neutral names, and a grading sheet under `~/.compass/overhead/grading/` listing the frozen goals; you mark each goal met, partly met or not met and mark any project you want kept; the script then gives the judge's agreement with you per goal item and adds it to its own section of the pilot report - complexity: S, depends_on: TASK-248, files: [bench/overhead/grade.py, bench/overhead/tests/test_grade.py, .compass/research/whole-overhead/RESEARCH-whole-overhead-pilot.md], decisions: [SPEC-032-whole-overhead-measured-on-real-projects/D-02], lessons: [LESSON-measure-the-procedures-intermediates, LESSON-blind-the-author-in-self-validation]
- [ ] TASK-250: Records reconciled, the split by source probed, and the pilot's projects closed. `attribute.py` compares, per build, the counting rule's totals with the transcript's `cost-state` and with the deduplicated sum of assistant records (parent, `subagents/` files, workers), and names the cause of any mismatch the transcript shows (resume, compaction, an auxiliary request); it lists which attachment kinds reached the model; for one Compass-arm session it rebuilds each request's text from the transcript and compares its UTF-8 bytes divided by 4 with the API's input count; and three ablation calls (an isolated `claude -p "hi"` with and without one Compass rules file, one skill, one agent definition) give each one's real first-request tokens beside its bytes divided by 4. The console OpenTelemetry exporter is tried once and the report says whether Compass's skills and agents appear by name. The results go into their own section of the pilot report; then every pilot project is discarded except the ones marked to keep in TASK-249, which `sandbox.py keep --to <folder>` copies out first - complexity: M, depends_on: TASK-248, TASK-249, files: [bench/overhead/attribute.py, bench/overhead/tests/test_attribute.py, .compass/research/whole-overhead/RESEARCH-whole-overhead-pilot.md], decisions: [SPEC-032-whole-overhead-measured-on-real-projects/D-03, SPEC-032-whole-overhead-measured-on-real-projects/D-02]

## Next Up

- [ ] SubagentStop typed-signal fix, fleet-wide (payload evidence captured: `agent_type` empty string). Queued in [[backlog]].
- [ ] [[SPEC-006-multi-host-agent-cli-support]] hosts: hermes first, then deepseek-harness (dsh; fit assessed in [[research/distribution/RESEARCH-deepseek-harness-fit]], 2026-09-04), then Kimi Code / Codex.
- [ ] Blinded rerun of the test-bar experiment ([[LESSON-blind-the-author-in-self-validation]]).
