---
title: "Research: integration points, rerunnable evidence, same-family votes, cost scaling"
type: research
status: complete
confidence: medium
area: testing
tags: [research, verification, validator, evidence, reviewer, model-family, cost]
created: 2026-11-21
updated: 2026-11-21
author: researcher
git_branch: "master"
git_commit: "6faced1"
summary: "where reachability, change-ablation and spec-conformance checks hook into the build and validate flow, what a rerunnable evidence record needs, same-family judge correlation, and the sibling cost spec"
---

# Research: integration and evidence (axis 4)

From [[SPEC-034-verification-beyond-test-pass]]. Reuses [[research/llm-research/REVIEW-llm-research-for-compass]] A3, A4, B9 and [[research/llm-research/RESEARCH-axis-4-multi-agent-verification]] f12-f14; sibling axes in [[research/test-quality/beyond-test-pass/RESEARCH-change-ablation]] and [[research/test-quality/beyond-test-pass/RESEARCH-spec-conformance]].

## Question
Where would the three new checks plug into today's build and validate flow, what must an evidence record hold to be rerunnable, how would the reviewer matrix cap same-family agreement, and how should the checks scale with the checking-cost spec?

## Methodology
Repository mining (empirical read of the artifact: agent templates, skills, CLI, on-disk records) for (a), (b-local), (c-local) and (d); a technology-landscape read of prior art (SLSA, SWE-bench) and a scripted-search read of 2025-2026 papers for (b) and (c). Brief carried `grading: allowed`; grades given per finding.

## (a) Where verification runs today and where the three checks hook in

1. **The flow has five verification stations, in this order** (confidence: high)
   - Pre-build tester writes failing tests, records red output; orchestrator runs `compass test-checkpoint record` (`plugin/skills/build/SKILL.md:28-36`, `plugin/templates/agents/tester.md:37-60`).
   - Builder writes code, runs a diff-only style review sub-agent, runs no tests (`plugin/templates/agents/builder.md:55-71`).
   - Post-build tester runs the full suite, `test-checkpoint verify --against-run`, adds implementation-visible tests (`tester.md:62-87`).
   - Fix loop: `verify --tree`, `cycle` ledger, max 3 cycles (`SKILL.md:42`).
   - Post-merge: tester on the merged state plus `verify TASK-NNN`; then optional validator (`SKILL.md:44-48`, `:87`).
   - Marks: source code read; no retraction; not a preprint; 0 citations; 1 source (the repo).
   - Grade: high (read directly).

2. **The validator is the only station that sees the whole plan and the baseline-to-HEAD diff, which is the input all three checks need** (confidence: high)
   - Step 3 computes `git diff <baseline>..HEAD` with `--stat`, `--name-status` and `git log` (`validator.md:44-52`); step 4 loops per task with 4a-4g audits, all report-only except pass/fail on tasks' own automated checks (`validator.md:54-108`); step 5 re-runs the suite (`:110-112`); step 6 is one mandatory adversarial probe (`:114-126`); step 9 lists what a PASS report must contain (`:141-151`).
   - Tools are `Read, Grep, Glob, Bash`; `Write, Edit` disallowed; may write ephemeral scripts to a temp dir (`validator.md:4,17`).
   - Marks: source read; 1 source.
   - Grade: high.

3. **Hook point for reachability: a new step 4h in `validator.md`, after 4f/4g, per task, plus an optional earlier read in the builder's step 8 review** (confidence: medium)
   - Reads: the task's `files:` from the plan (`validator.md:34`), `git diff --name-status` from step 3 (`:44-52`), and the project's entry points. Compass has no recorded entry-point list: for its own CLI the registry is the `COMMANDS` table in `plugin/cli/maincli.py:42-61` and the hook commands in `plugin/hooks/hooks.json`; for another project the entry point is whatever the task or spec names as "a command or user action" (SPEC-034 wording).
   - Output: a `Check / Command run / Output observed / Result` block per new symbol, the existing check format (`validator.md:19-30`), so it inherits the "no command = SKIP not PASS" rule.
   - Open: how a "new symbol" list and an "entry point" are obtained is not in the repo today (see Gaps).
   - Marks: source read plus inference; 1 source.
   - Grade: medium (hook point verified, the mechanism is not specified anywhere).

4. **Hook point for change-ablation: the post-build tester step 3 (it already has the worktree, the suite command and the checkpoint) or a validator step 4i; inputs are the checkpoint record and the per-task merge commit** (confidence: medium)
   - Checkpoint record holds `commit`, `files[].ids`, `red_evidence`, `landed`, `landed_at` (`plugin/cli/commands/test_checkpoint.py:566-680`, on-disk `.compass/tmp/test-checkpoints/TASK-NNN.json`).
   - Build step 6 merges each task with `git merge --no-ff ... "Merge TASK-NNN: ..."` (`SKILL.md:44-48`), so `git diff <merge>^1 <merge>` is the exact task diff to revert in a scratch worktree.
   - Agent-created worktrees under `.claude/worktrees/` and `.compass/tmp/` are exempt from the guard hook, so a scratch ablation worktree there is deletable by a subagent (`plugin/cli/commands/guard.py:13-14,89-91`).
   - Tests added post-build by the tester have no recorded red run at all (`RESEARCH-change-ablation` finding 3, same repo).
   - Marks: source read; 2 sources (SKILL.md and test_checkpoint.py agree on the record shape).
   - Grade: medium-high.

5. **Hook point for spec conformance: validator step 4d (decision coverage) is the nearest neighbour; the new check belongs beside it, and its "unmet requirement becomes open work" output has no existing consumer** (confidence: high)
   - 4d runs `compass coverage <plan>` (decisions to tasks, never to code) and crosses `decisions:` citations with the diff by prose judgment, report-only (`validator.md:74-78`; `RESEARCH-spec-conformance` findings 6-7).
   - A validator FAIL goes back to builders as targeted fixes in the parallel-execution pattern (`plugin/skills/methodology/SKILL.md`, Parallel execution phases 3-4), but build's own fix loop is triggered only by tester-reported bugs (`SKILL.md:42`; `RESEARCH-spec-conformance` finding 8). Re-opening an unmet requirement as a task is the missing wire.
   - Marks: source read; 3 sources agree.
   - Grade: high.

6. **The validator report is not written to any file by the validator; it exists as the subagent's final message, captured by hook** (confidence: high)
   - `disallowedTools: Write, Edit` (`validator.md:5`). The SubagentStop hook writes the final message to `.compass/tmp/subagent-captures/<timestamp>_<agent>.md`; build step 7a renames it to `.compass/tmp/phase-reports/<phase>/validator.md` (`plugin/hooks/hooks.json` description; `SKILL.md:52-62`). `.compass/tmp/` is gitignored (`.gitignore:2`).
   - `phase-summary.yaml` carries only `validator_deviations` as `{task, kind, description}` rows (`plugin/skills/extract-lessons/phase-summary.md`).
   - Marks: source read; 3 sources agree.
   - Grade: high.

## (b) "A claim that a task is done is checkable by rerunning its evidence"

7. **What Compass keeps today: per-check text blocks and a per-task checkpoint index, both in gitignored scratch** (confidence: high)
   - Validator check blocks hold exact command and observed output (truncated to 125 chars per line) in the report text (`validator.md:19-30,159`); no commit SHA, no environment, no full output.
   - Checkpoint index (`.compass/tmp/test-checkpoints/TASK-NNN.json`) holds commit SHA, per-file SHA-256, test ids, `red_evidence` path, `landed`, `accepted_skips`; git, not the index, is authoritative for content (`test_checkpoint.py:1-12`). Evidence files such as `.compass/tmp/red-TASK-066.txt` are referenced by path only and live in `.compass/tmp/`.
   - `cycles.jsonl` per task records fix-loop verdicts (`test_checkpoint.py:67-75`).
   - `sizing-log.yaml` records shape decisions of `make-unit`/`promote`/`demote`, not verification (`plugin/cli/commands/sizing.py:1-30`); the A4 review item to reuse it for station ablation would need a new row type.
   - Marks: source read plus on-disk record read; 3 sources agree.
   - Grade: high.

8. **A rerunnable record needs more than the check block carries; the parts that exist are the commit SHA and the command** (confidence: medium)
   - Present today: exact command (validator block), `commit` and test ids (checkpoint).
   - Absent today: the commit SHA the check ran against (the validator's baseline is plan frontmatter `git_commit`, not HEAD at run time), full untruncated output, exit code, runner and interpreter versions, the working tree state (clean or dirty), a durable location (everything above sits in gitignored `.compass/tmp/`).
   - Inference from the three prior-art shapes below; no Compass document specifies a rerun contract. This is a gap for the planner, not a decision.
   - Marks: inference over source read; 1 source plus prior art.
   - Grade: medium (inference).

9. **Prior art 1: SLSA v1 provenance separates what to rerun (`buildDefinition`) from what happened (`runDetails`)** (confidence: high)
   - `buildDefinition`: `buildType` URI, `externalParameters` (untrusted inputs, must be verified), `internalParameters`, `resolvedDependencies` (artifacts pinned by digest, e.g. git commit). `runDetails`: `builder.id`, `invocationId`, `startedOn`/`finishedOn`, `byproducts` (logs, hard-to-regenerate outputs).
   - Design rule: the platform should use the build definition as its only top-level input, so the recorded information is guaranteed sufficient to rerun.
   - https://slsa.dev/spec/v1.0/provenance - read in full this session.
   - Marks: specification (vendor-neutral standard, OpenSSF); not retracted; not a preprint; citation count n/a; 1 source.
   - Grade: high (normative spec, asserted design not measured against agent work).

10. **Prior art 2: SWE-bench writes one folder per instance whose files are exactly the rerun inputs and the observed result** (confidence: high)
    - Per instance: `patch.diff` (patch applied), `eval.sh` (script that ran the tests), `test_output.txt` (everything the tests printed), `run_instance.log` (harness steps and why it stopped), `report.json` (per-instance result); one `results.json` per run.
    - Harness results are reproducible because the script and patch are stored, not described.
    - https://raw.githubusercontent.com/SWE-bench/SWE-bench/main/docs/guides/evaluation.md - read this session (the page does not list `report.json` fields).
    - Marks: project documentation of a widely used benchmark harness; no retraction; not a preprint; citation count not collected; 1 source.
    - Grade: medium-high (practitioner/open-source documentation, asserted behavior).

11. **Prior art 3, local: Compass's own checkpoint already follows the "store the pointer, let git hold the content" pattern** (confidence: high)
    - `verify` re-reads baseline text with `git show <sha>:<path>` and never trusts index content (`test_checkpoint.py:6-10`). A rerunnable evidence record extending this pattern would store a SHA, a command, a pinned test id list and an output file path, with git or a content hash as the check against tampering.
    - Marks: source read; 1 source.
    - Grade: high for the existing pattern; the extension is a proposal for the planner, not a finding.

12. **CI artifacts (general prior art) were not fetched; the claim that CI systems retain logs and artifacts per run is common knowledge, not verified here** (confidence: low)
    - Not read from any source this session. Listed so the gap is visible, not filled.

## (c) Reviewer convergence matrix and same-family agreement (B9)

13. **The reviewer matrix scores agreement count only and records neither model nor family** (confidence: high)
    - Matrix columns are "Agent 1..5" with YES/NO and a confidence; categories are Converged (>=80%), Partial (50-79%), Divergent (<50%) by percentage (`plugin/templates/agents/reviewer.md:42-60`). The reviewer's own model is `opus` (`:6`).
    - Marks: source read; 1 source.
    - Grade: high.

14. **Compass holds model identity only as a tier-to-name table per host; there is no family field** (confidence: high)
    - `HOST_CATALOGS["claude-code"] = {strong: opus, balanced: sonnet, cheap: haiku}` and a `dsh` host mapping tiers to `deepseek-official/deepseek-v4-*` (`plugin/cli/modelslib.py:27-39`). `DEFAULT_ROSTER` maps agents to tiers (`:43-59`); researcher is `balanced` (`researcher.md:6`). Grep for `family` in `plugin/cli/*.py` and `plugin/templates/agents/*.md` found nothing.
    - Every agent template pins a Claude tier, so by default all matrix columns are one family; the `dsh` catalog is the only place a second family can appear, and its two tiers (`pro`, `flash`) share a provider prefix.
    - Marks: source read; 2 sources (modelslib.py, agent frontmatter).
    - Grade: high.

15. **What the cap would touch, as documented in the code (not a recommendation)** (confidence: medium)
    - Source of each agent's model: the spawn record or the `resolve-model` result for the agent name (`plugin/cli/commands/resolve_model.py`; `compass models`). A family value would derive from the model name prefix or a new column in `HOST_CATALOGS`; neither exists.
    - Reviewer inputs are "N agent outputs inline or file references" with no model metadata (`reviewer.md:25-28`), and researcher saved files carry no model field in their frontmatter template (`plugin/skills/obsidian/templates.md` research frontmatter lists author, git_branch, git_commit only).
    - Two ways the source material supports: count same-family agents as one vote, or keep counts and flag "n of m agreeing agents share a family". The prior review recorded the options but no choice (`RESEARCH-axis-4-multi-agent-verification` candidate 4).
    - Marks: source read plus inference; 1 source.
    - Grade: medium.

16. **Evidence 1: cross-model review was not significantly better than fresh same-model review; Jaccard overlap of findings 41.2%** (confidence: low-medium, reused)
    - arXiv:2610.01471 abstract, as recorded in `RESEARCH-axis-4-multi-agent-verification` f12. Not re-fetched; arXiv API was unreachable from the sandbox this session.
    - Marks: single-author preprint, 2026-10; not retracted; 0 citations known; 1 source.
    - Grade: low-medium (measured on planted errors, small).

17. **Evidence 2: a panel of 9 frontier judges from 7 families carried about 2 independent votes; same-family pairs are only slightly more correlated than cross-family pairs** (confidence: medium)
    - Kohli, "Nine Judges, Two Effective Votes: Correlated Errors Undermine LLM Evaluation Panels", arXiv:2605.29800, submitted 2026-05-28. Kish effective sample size on three NLI datasets with 100 human annotations per item plus RewardBench; panel accuracy 8-22 points below independent voting; best single judge matches or beats the panel; aggregation closes at most 11% of the gap. The abstract page was fetched; a search summary reports same-family phi about 0.44 vs cross-family 0.39, and that keeping the best judge per family gave n_eff 1.93 (summary only, not read in the paper).
    - This contradicts "family is the axis that matters" and supports "any agreement among strong models is weaker evidence than its count".
    - https://arxiv.org/abs/2605.29800
    - Marks: single-author preprint; not retracted; citation count 1 known (a 2026 follow-up cites it, arXiv:2608.08002, from search results); 2 sources on the correlation theme.
    - Grade: medium (measured, NLI and preference tasks, not code review).

18. **Evidence 3: errors are correlated across 350+ LLMs; same-developer, same-architecture and similar-size models agree more; more accurate models are more correlated; judges inflate same-family weaker models** (confidence: medium)
    - Kim, Garg, Peng, Garg, "Correlated Errors in Large Language Models", arXiv:2506.07962, 2025-06. Models agree 60% of the time when both are wrong, against 1/3 under uniform random wrong answers on one leaderboard; judges inflate the accuracy of weaker models, "especially models from the same provider or family". Read from a search summary, abstract and search listing only.
    - https://arxiv.org/abs/2506.07962
    - Marks: preprint (likely venue version exists, not checked); not retracted; citations not collected, cited by arXiv:2608.08002; 2 sources.
    - Grade: medium (large measured sample; summary-level read).

19. **Evidence 4: self-preference is linked to self-recognition** (confidence: medium, older)
    - Panickssery, Bowman, Feng, "LLM Evaluators Recognize and Favor Their Own Generations", arXiv:2404.13076, 2024-04 (older than the 2025-2026 preference). Models recognize their own text above chance; fine-tuned self-recognition correlates linearly with self-preference strength; abstract names GPT-4 and Llama 2.
    - https://arxiv.org/abs/2404.13076
    - Marks: preprint (later conference version not checked); not retracted; widely cited, count not collected; 1 source read.
    - Grade: medium (measured, causal controls, 2024 models).

20. **Evidence 5, reused: same-model debate does not beat self-consistency at equal compute; family-level favoritism preprints vary in size and direction** (confidence: medium and low)
    - `RESEARCH-axis-4-multi-agent-verification` f13 (low) and f14 (medium), not re-read.
    - Convergence across 2, 3 and these: 6 sources agree that same-family or same-model agreement is not independent evidence; they disagree on whether family is the right grouping (finding 17 puts cross-family pairs such as two top-tier models at similar correlation to same-family pairs).

## (d) Cost: the sibling spec and how the checks scale

21. **The sibling spec states a problem and an outcome but no rule, no D-NN and no tier table yet** (confidence: high)
    - [[specs/tooling/SPEC-027-compass-uses-fewer-tokens/SPEC-034-checking-cost-follows-task-and-model]] (approved, `confidence: low`): checking stations "run in full on every task"; outcome is a stated rule from "the task's difficulty and the model", recorded so "the same task on the same model always gets the same answer". Its KPI is a guess. Constraint: lighter checking must be earned by measurement showing defects caught do not fall; an unhelpful part is reported and kept (text moved colder).
    - The two specs share an id number (SPEC-034) in different folders: `.compass/specs/pipeline/` and `.compass/specs/tooling/SPEC-027-compass-uses-fewer-tokens/`. Wikilinks by bare stem resolve by full filename, so the long names do not collide, but the number does (Contradictions).
    - Marks: vault documents read; 1 source.
    - Grade: high.

22. **No input for a difficulty rule exists in the repo today** (confidence: medium)
    - Candidate difficulty signals already recorded: task size (plan tasks carry sizing via the planner), `fix_loop_cycles` per task in `phase-summary.yaml`, `compass test-checkpoint cycle` verdicts, and `validator_deviations` (`phase-summary.md`). None is mapped to a checking level. Model identity is available through `compass models` / `resolve-model` (`modelslib.py`).
    - The three new checks differ in cost shape, from the sibling axis files: reachability is a static or one-run probe per new symbol (cheap); ablation is one extra full suite run per task, plus a revert worktree (cost scales with suite time, `RESEARCH-change-ablation` cost section); spec conformance is LLM-judged per requirement (tokens scale with spec size and diff size).
    - Marks: source read plus inference; 2 sources.
    - Grade: medium.

23. **Cost evidence to carry from the earlier review** (confidence: medium, reused)
    - On one model the evaluator was overhead for in-capability parts and kept lift on hard parts; QA rounds cost $3-4 against build rounds of $36-71 (A4 evidence, "1 f7", vendor/practitioner). Agent-written tests moved no resolve rate while costing 33-49% more input tokens ("4 f15", preprint). Both from [[research/llm-research/REVIEW-llm-research-for-compass]] A4; not re-read.
    - The brief's constraint ties to the sibling spec: a check dropped for easy tasks must be shown not to lower defects caught on a measured sample (sibling Constraints), which is why the SPEC-034 KPI of "flags every planted instance" is the natural test bed for any lighter setting.
    - Marks: reused; vendor/practitioner post plus preprint; 2 sources.
    - Grade: medium.

## Contradictions
- Finding 16 (cross-model review not significantly better) and finding 17 (family diversity alone does not recover independence) agree that family is a weak separator; finding 18 and `RESEARCH-axis-4` f13 say same-family judges favor family members. Family-level evidence is thus mixed on direction and size; per-pair effect from 2605.29800 is small (about 0.05 phi) in one dataset.
- Two specs numbered SPEC-034 exist ([[SPEC-034-verification-beyond-test-pass]] and the checking-cost spec under `specs/tooling/`). Different folders, so file names differ, but a bare "SPEC-034" is ambiguous.

## Gaps
- No entry-point inventory or "new symbol" extractor exists in `plugin/`; (a) item 3 names the hook, not the mechanism. Closing it: a research pass on call-graph or coverage-based reachability for the languages Compass projects use.
- No rerun contract is written anywhere in the vault; item 8 is inference. Closing it: a planner decision on the fields and a durable (committed or archive) location, since `.compass/tmp/` is gitignored.
- CI artifacts as prior art not researched (item 12).
- 2506.07962 and 2605.29800 were read from abstract pages and search summaries; the same-family phi values are from a summary only. arXiv API and PDF text for 2610.01471, 2611.18616, 2604.22891 and 2607.28636 were not reachable.
- No measurement of how often Compass multi-agent runs mix families; all agent templates pin Claude tiers, so under defaults every matrix column shares one family (item 14) and the cap would apply to every run until a second host catalog is in use.
- Difficulty signal for the cost rule is not defined in any document (item 22).

## Candidate changes for Compass (ranked by impact)

1. **Rerunnable evidence record per task, written by the harness.** North star: accuracy, perfect memory. Would change: a `compass` command (new, or an option on `test-checkpoint`) that stores command, commit SHA, exit code, full output file, versions, under a committed location; the validator step 9 PASS list requires it for each new check. Already covered: partly (checkpoint index holds SHA and hashes; validator blocks hold command and truncated output; both in gitignored tmp). Directly serves the SPEC-034 constraint.
2. **Wire spec-conformance output into the build loop as open tasks.** North star: accuracy. Would change: validator step 4 adds a conformance audit beside 4d; `plugin/skills/build/SKILL.md` step 5 accepts validator-found unmet requirements as fix-loop triggers, not only tester bugs. Covered: no.
3. **Ablation placed at the per-task merge commit.** North star: accuracy. Would change: build step 6 or tester post-build step 3 reverts `git diff <merge>^1 <merge>` in a scratch worktree under `.claude/worktrees/` and runs the task's checkpointed test ids; result goes to the evidence record. Covered: pre-build red evidence only (once, before build).
4. **Reachability as validator step 4h with an entry-point source named per project.** North star: accuracy. Would change: `validator.md` and a plan/spec field naming the entry point. Covered: no.
5. **Reviewer matrix records model family per agent and caps same-family agreement (B9).** North star: accuracy. Would change: `reviewer.md` matrix gains a family row and a rule for the Converged class; `modelslib.py` gains a family column or derivation. Covered: no. Evidence supports "same-model agreement is weak evidence" and does not settle one-vote-per-family vs flag-only.
6. **Scale the three checks through the sibling cost spec once it holds a rule.** North star: accuracy then tokens. Would change: the checking level is read from the recorded cost decision; the planted-defect KPI of SPEC-034 doubles as the "defects caught do not fall" proof. Covered: no (the sibling has no rule yet).
