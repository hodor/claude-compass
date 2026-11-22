---
title: "Axis 5: gap pass - KPI probe, correction admission, pass cost, source reach"
type: research
status: complete
confidence: medium
area: methodology
tags: [lessons, consolidation, drift, kpi, admission, cost, provenance, learning-loop]
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "6faced1"
author: researcher
spec: "[[SPEC-002-consolidation-grounded-in-sources]]"
depends_on: ["[[REVIEW-consolidation-from-sources]]", "[[AXIS-2-recheck-against-sources]]", "[[SPEC-028-agent-memory-is-good-enough]]"]
summary: "Closes the four review gaps: a seeded-staleness KPI design with thresholds (SPEC-028 supplies no harness), admission options per correction type, measured worker cost (median 0.52 USD, 75 passes) and a judge-pass estimate, and which lesson sources survive a fresh clone"
---

# Axis 5: gap pass

From [[SPEC-002-consolidation-grounded-in-sources]]. Closes the Gaps section of [[REVIEW-consolidation-from-sources]].

## Question

What KPI sample, admission rule, per-pass cost and surviving source pointer does the recheck of lessons, index lines and `file:line` references need?

## Methodology

Repository mining: every claim below was measured or read in this repository (logs, code, `git check-ignore`), because all four gaps ask how the existing artifact behaves. The KPI design in section 1 is a design inference built on those measurements and is marked so. grading: allowed; evidence is code or measured data unless marked.

## 1. KPI probe: seeded staleness

1. **SPEC-028 supplies no harness and measures a different thing** (confidence: high)
   [[SPEC-028-agent-memory-is-good-enough]] is `status: draft`, its KPI is a guess ("a fresh Compass agent finds the right answer"), and no plan names it (grep of `.compass/plans` and `plugin/`: no hit). It measures recall by a reader; the SPEC-002 KPI measures detection of staleness by a checker. Research under it proposes question classes only ([[research/llm-research/REVIEW-llm-research-for-compass]] row C8).
   - `.compass/specs/learning/SPEC-028-agent-memory-is-good-enough.md:7,22`
   - Marks: vault documents, read in full; not applicable; not preprint; citations n/a; convergence: three research docs cite it, none builds a harness
   - Grade: code and vault, directly read

2. **Pieces that exist and can be reused: bench/overhead launcher, frozen goals, blind judge, hand-grade comparison, bootstrap interval** (confidence: high)
   `goals.py` refuses a second write of a frozen list, `judge.py` strips `.git`, `.compass`, `.claude` and is read-only, `grade.py` compares the judge with hand grading, `compare.py` gives a 95% bootstrap interval. None builds a probe or a seeded set. The same pattern fits a seeded sample: freeze the seed list before the checker runs.
   - [[research/pipeline/compaction-survival/RESEARCH-axis-4-probe-kpi]] finding 15 (`judge.py:1-12,38,73`; `goals.py:9-12`; `bench/overhead/README.md:57-65`)
   - `plugin/skills/methodology/SKILL.md` Testing mandate item 4 names "seeded defects" for tests only ("A paired seeded-defect probe"); no seeded-vault code found by grep of `plugin/` (matches in `test_sync.py`, `test_looprunner.py`, `test_idea_command.py` were not read)
   - Marks: code read; convergence: README and source agree (per the cited research)
   - Grade: code, directly read; the seeded-defect grep is a negative search, not proof of absence

3. **Natural drift already exists in the live vault, so the sample needs a baseline run** (confidence: high)
   Measured by [[AXIS-2-recheck-against-sources]] on the live vault: 380 `file:line` refs (132 provably unchanged, 118 behind an earlier edit, 41 inside an edited hunk, 1 missing path, 57 unclassifiable); 11 of 123 index lines differ from the target `summary`; 7 of 60 catalog `score` values differ from the file. A "no fresh ones reported" rule fails on natural drift unless it is cleared first. Counted here: 61 lesson files on disk, 60 with frontmatter read by script, 27 with a `source`.
   - `.compass/research/learning/consolidation-from-sources/AXIS-2-recheck-against-sources.md:61,75,81`
   - Marks: measured by script (axis 2); not applicable; convergence: axes 2 and 3 agree on the catalog count
   - Grade: measured, same-model-family reading

4. **Design: seeded-staleness sample in a throwaway clone** (confidence: medium, design inference)
   - Scratch: `git clone --local` of the repo into an empty directory outside the vault, then commit seed edits there. The real vault and its branch are never touched; git history in the clone is what the `file:line` checker reads, so seeds must be real commits.
   - Baseline first: run the checker on the unseeded clone; every finding is natural drift, recorded and excluded from scoring (or hand-judged once). Controls are drawn only from items the baseline reports clean (for refs: the 132 provably unchanged).
   - Seed with a fixed random seed, a frozen list written before the run (the `goals.py` freeze pattern), 20% stale, stratified by class:
     - refs, 40 items, 8 stale: 3 line shifted (insert lines above the cited line), 3 cited line edited, 1 file renamed (`git mv`, expected rename proposal), 1 file deleted.
     - index lines, 30 items, 6 stale: 3 target `summary` edited, 3 index line text edited.
     - catalog rows, 30 items, 6 stale: 3 `score`, 3 `summary` changed in the lesson file.
     - lesson meaning, 20 items, 10 stale: needs a source pointer that does not exist today (section 4), so these are synthetic lessons written with a tracked quote; half have the quote or the cited code made to contradict the body. Reported separately as the model-half sample.
   - Marks: design inference from findings 1-3 and axis 2 finding 11
   - Grade: design, untested

5. **Definition of reported and the pass threshold** (confidence: medium, design inference)
   - Reported: the drift report holds a row naming the seeded item, with evidence beside it (file, line, commit, old and new text, per [[SPEC-002-consolidation-grounded-in-sources]] outcome). A row for the right item with the wrong class counts as detected, class error tracked separately. A row for a control item is a false positive. The model half counts only a verdict of "contradicted" with a quoted span; "unverifiable" on a seeded item is a miss.
   - Script half (refs, index lines, catalog rows): pass = every seeded item reported and zero control items reported. Deterministic checks make 100% the bar the spec states ("the stale ones and no fresh ones"). With 76 script-half items, 0 false positives bound the false-positive rate at about 5% (rule of three: 3/60 for the 60 fresh controls here).
   - Model half: 20 items; 10 of 10 seeded caught gives a 95% one-sided lower bound of about 0.74 (0.05^(1/10)), so 10 seeds are too few to claim 0.9. Using 20 stale and 20 fresh synthetic lessons gives 0.86 at 20 of 20. Suggested pass: recall at least 18 of 20 and at most 1 of 20 fresh reported, stated with its interval, not as a point rate. These bounds are computed here from the binomial; nothing in the vault sets them.
   - Rerun on 2 or 3 seeds of the random draw; the judge runs on a model family other than the capture worker's where possible ([[research/pipeline/compaction-survival/RESEARCH-axis-4-probe-kpi]] finding 16 names same-family judging as the open bias).
   - Marks: computation by this run; not applicable; convergence: n/a
   - Grade: computed bound, design choice (the thresholds are a planner and human decision, not a source's)

## 2. Correction admission

6. **Comparable Compass gates today** (confidence: high)
   | Gate | Where | Kind |
   |---|---|---|
   | `compass review` per document, checkbox per item | `plugin/skills/consolidate/SKILL.md:171` (domain proposal), `plan/SKILL.md:21`, `build/SKILL.md:78` | human, visual surface |
   | Anti-list, dedup judge, 5-line cap (`body_too_long` returned by the model) | `plugin/skills/lesson-write/SKILL.md:67-69,144,156` | model plus prose rule |
   | Consolidate merges and rewrites: "Report every merge/rewrite ... for the human's audit" | `plugin/skills/consolidate/SKILL.md:56-71` | after-the-fact report, no gate |
   | `compass guard`: denies delete or gutting of vault text for subagents; blocks edits to a file under review | `plugin/cli/commands/guard.py:291-343,347-366` | mechanical, PreToolUse |
   | `sync._text_preserved`: an index line is dropped only if its text survives in the target | `plugin/cli/commands/sync.py:221-234,257-260` | mechanical |
   | `compass validate`: links, frontmatter, caps; opens no `file:line` ref and no lesson body | `plugin/cli/commands/validate.py:42-51` (per review) | mechanical |
   - `consolidate/SKILL.md:171` is the one existing human gate on lessons-adjacent structure: a draft proposal with one checkbox per item, ticked approves, unticked leaves it.
   - Marks: code read; convergence: gates agree with [[REVIEW-consolidation-from-sources]] claims 1, 3
   - Grade: code, directly read

7. **Admission options, with what each can and cannot establish** (confidence: medium)
   - **Human review through `compass review`:** a batch document, one checkbox per correction, old text, new text and evidence beside it. Cost is the human's attention; scales poorly past tens of items. Precedent: finding 6 row 1.
   - **Model judge:** reads the correction and its source and says supported or not. Same-family bias and a lenient-judge risk are documented ([[research/pipeline/compaction-survival/RESEARCH-axis-4-probe-kpi]] findings 12-13: one audit reports a lenient judge accepting up to 63% of wrong answers, second-hand, preprint). Establishes meaning, not preservation.
   - **Mechanical check:** the correction is an edit plus its displaced text. Checkable by script: the old text appears verbatim in the file's `## Record (preserved)` (`lesson-write/SKILL.md:97`), the body is at most 5 lines, `seen`, `score`, tags unchanged, `compass validate` passes, and for a ref fix the new location holds the cited line text (`git grep -F`) or `git log --diff-filter=R -M` shows R100. Establishes that nothing was lost; says nothing about whether the new text is true.
   - Note: today no code enforces the Record rule for lessons (0 of 60 bodies exceed 5 lines now; [[AXIS-1-consolidation-and-delta-edits]] f3-f4).
   - Marks: code read plus vault documents; one second-hand preprint audit; convergence: three axes agree corrections are edit plus preserved text
   - Grade: code, directly read for the gates; the judge-leniency figure is preprint, second-hand

8. **Candidate pairing per correction type** (confidence: medium, design inference; the choice is the planner's and the human's)
   | Correction | Candidate admission | Why it fits the evidence |
   |---|---|---|
   | Mechanical ref fix (path rename, shifted line) | Mechanical check alone, applied by code, logged in the drift report | The proof is git (R100 rename, cited line text found at new line); axis 2 f8-f9 show this is script-decidable. An edited-hunk ref has no proof, so it stays report-only |
   | Index line resync | Mechanical: derive the line from the target `summary`, preserved by `_text_preserved`; direction fixed (target wins), so a divergent index line is old text kept in the report | `sync.py` already owns index lines; 11 of 123 differ today; resync reads one field |
   | Lesson body change | Mechanical check first (Record holds displaced text, 5-line cap, validate), then human review through `compass review` with a checkbox per lesson; the model judge supplies the evidence column, not the verdict | Body text is the active guidance every agent reads; the judge's bias is documented and the replacement text cannot be proven by script; the consolidate proposal already uses this shape |
   - Marks: design inference from findings 6-7; convergence: none (no source prescribes it)
   - Grade: design, untested

## 3. Cost of a pass

9. **Measured: 75 capture-worker passes, median 0.52 USD, mean 0.57, p90 0.92, max 2.19, total 42.82** (confidence: high)
   Each archived worker log is the headless child's JSON result, carrying `total_cost_usd`, `usage`, `num_turns`, `duration_ms`. Parsed all 75 `OPP-*.log` files with a script (file names span 2026-08-24 to 2026-10-19; later passes are not in `archive/logs`).
   | Per pass | min | median | mean | p90 | max |
   |---|---|---|---|---|---|
   | cache-read tokens | 279,972 | 870,064 | 1,185,517 | 2,106,023 | 6,190,323 |
   | cache-creation tokens | 39,806 | 57,100 | 64,469 | 89,857 | 159,070 |
   | output tokens | 1,641 | 9,593 | 10,133 | 21,651 | 30,770 |
   | uncached input tokens | 14 | 34 | 41 | 64 | 276 |
   | turns | 9 | 21 | 24 | 37 | 55 |
   | seconds | 22 | 119 | 137 | 262 | 529 |
   Models in the logs: `claude-sonnet-5` 42 passes, `claude-sonnet-5-5` 29, a Haiku sub-call alongside Sonnet in 3, Haiku only in 1.
   - `plugin/cli/commands/capture_worker.py:299-303` (argv: `-p`, `--model`, `--output-format json`, `--allowedTools`; no budget flag), `:281` (tools `Read,Write,Edit,Glob,Grep,Skill,Bash(python:*)`), `modelslib.py:58` (`capture-worker` tier `balanced`)
   - Marks: measured from logs; not applicable; convergence: 75 samples, consistent shape
   - Grade: measured, single machine and single project

10. **A judge pass is a no-tool single call, roughly 50x cheaper than a worker pass; the figure is an estimate** (confidence: low)
    A bounded judge call (lesson body of at most 5 lines, a stored excerpt, a code window; verdict plus quoted span) is about 3,000 input and 300 output tokens by this run's sizing. Effective rates implied by one log (46 input, 83,111 cache-creation, 1,966,874 cache-read, 23,009 output tokens, 0.956 USD) come to about 2 USD per million input tokens if cache-write is 2x, read 0.1x and output 5x base; those multipliers are an assumption, not a published price. At that rate a judge pass is about 0.01 USD (band 0.005 to 0.03 with a cold cache), and judging all 60 lessons is about 0.6 to 1.8 USD, near one worker pass. The script half costs no tokens (SPEC-004 constraint).
    - Derived from finding 9's log rows; no judge pass has been run
    - Marks: estimate; convergence: none; rates inferred
    - Grade: estimate, low

11. **Where a cost field could be recorded** (confidence: high on the code, the placement is open)
    `capture_worker.py:344-353` already holds the whole JSON envelope in `stdout_text`, writes it to `.compass/tmp/worker-logs/<opp-id>.log` (`:63,108`; gitignored under `tmp/`), and logs `worker-finished` with only `extracted` (`:353`). `_extracted_line` (`:214-235`) parses the envelope but reads only `result`. So `total_cost_usd` and `usage` are available at the point the ledger row is written and are dropped. Candidate homes: extra fields on the `worker-finished` row in `.compass/tmp/capture-log.jsonl` (read by `compass capture-stats`); or a tracked per-pass record. `meta/usage.yaml` counts invocations only (`capture-worker` count 117; no cost or token key).
    - `plugin/cli/commands/capture_worker.py:63,108,214-235,344-353`; `.compass/meta/usage.yaml` (grep for cost/usd/token: no hit)
    - Marks: code read; convergence: log shape and code agree
    - Grade: code, directly read

## 4. Source reach from a fresh clone

12. **Lesson files are tracked; the pointers inside them mostly are not** (confidence: high)
    | Pointer | In a fresh clone? | Evidence |
    |---|---|---|
    | Lesson file and its `source:` string | yes (56 of 60 lesson files tracked; 4 untracked new ones) | `git ls-files .compass/lessons` |
    | `OPP-<UTC>` opportunity dir | no: `.compass/tmp/` is gitignored (21 of 21 OPP-pointing lessons resolve on this disk only) | `git check-ignore -v` prints `.gitignore:2:.compass/tmp/` for `capture-opportunities`, `phase-reports`, `retrieval-log.jsonl`, `capture-log.jsonl` |
    | Worker log `archive/logs/<OPP>.log` (holds `session_id`) | no: not ignored but never committed; 0 tracked, 93 untracked; 16 of 21 present | `git ls-files .compass/archive/logs` lists only 5 `extraction-log-*.md` files |
    | Session transcript | no: lives outside the repository at `<config>/projects/<project-key>/<session-id>.jsonl` | `plugin/cli/sessionslib.py:4,125-126` |
    | Tracked extraction logs `archive/logs/extraction-log-2026-08-0*.md` | yes, but only 5 files (Aug 6-12); each opens sections named by `OPP-<UTC>`; contents not read beyond headers | `git ls-files`; `grep OPP` on the 08-06 file |
    - Only 27 of 60 lessons carry a `source` at all, none with a sha, session id or quote ([[AXIS-2-recheck-against-sources]] f1).
    - Marks: `git check-ignore` and `git ls-files` run here; convergence: matches axis 2 f2
    - Grade: command output, directly run

13. **Pointer forms that resolve from a clone** (confidence: medium)
    - A commit sha resolves if the commit is pushed and not rewritten. The lesson's own add commit needs no new field: `git log --diff-filter=A -- <lesson>` returned a commit for all 56 tracked lessons (sample: first lesson, commit `03ad50f`, 2026-09-13). That is the commit at capture, recoverable today for tracked lessons.
    - A quoted excerpt stored in the lesson's `## Record (preserved)` section is tracked text, immune to scratch cleanup and exempt from the 5-line cap (`lesson-write/SKILL.md:97`). Fits the Data rule; grows the file, not the hot path.
    - Code claims: `refs: [{path, line, commit}]` resolve with `git show <commit>:<path>` in a clone.
    - A session id alone does not resolve; the transcript is on one machine. A session id kept beside a quote gives provenance, not recheck.
    - Marks: command run (git log) plus design inference for the field forms; convergence: axis 2 f12 proposes the same field set
    - Grade: command output for the add-commit; design for the rest

## Contradictions

- None new. The add-commit pointer (finding 13) narrows [[AXIS-2-recheck-against-sources]] finding 1 ("No commit sha ... is recorded"): no sha field exists, but git history gives one.

## Gaps

- Judge-pass cost is estimated, not run; the rate multipliers in finding 10 are assumed. One real judge call on a flagged lesson would close it.
- Worker logs after 2026-10-19 are absent from `archive/logs`, so recent per-pass cost is unmeasured; cost is one machine, one project.
- Natural content-level false-positive rate of the git `file:line` check is still unmeasured (axis 2 gap); the seeded sample measures recall on seeds, not on real drift.
- The model-half sample needs a stored-excerpt pointer that no lesson has; until that field exists the 20-item synthetic set is the only way to test it.
- Whether the lenient-judge audit (finding 7) holds was not verified; it is quoted from a second-hand summary.
- The 5 tracked `extraction-log-*.md` files were not read for quoted evidence.
