---
title: "Accuracy of an agent judging natural-language rules against planted violations"
type: research
status: done
confidence: medium
area: pipeline
tags: [loops, sensors, judge, llm-judge, experiment, precision, recall, majority-vote]
created: 2026-10-18
updated: 2026-10-18
git_branch: master
git_commit: d0970dc
author: researcher
depends_on: ["[[specs/pipeline/SPEC-026-control-theory-for-loops]]"]
summary: "Verdict GATE: headless sonnet judging 5 rules over 30 files scored precision 1.00 and recall 1.00 on each local rule at majority-of-3 and majority-of-5, flip rate 0.00; the corpus is easy, so the result is a ceiling"
---

# Accuracy of an agent judging natural-language rules against planted violations

From [[specs/pipeline/SPEC-026-control-theory-for-loops]], task TASK-154 of [[plans/PLAN-021-control-loops]]. Feeds TASK-158 (judge sensors).

## Question
How accurately does a headless sonnet session, reading rules in natural language, find planted violations in a small Python corpus, and does a majority vote of its runs reach the fixed GATE thresholds?

## Methodology
Repository mining (empirical study of how an existing system behaves), run as a pre-registered seeded-defect experiment: the corpus is built with known violations, the thresholds and verdict rule were fixed in the plan before any judge ran, and the constant answers were scored first. No `grading:` field reached this run, so the findings are marked and ungraded.

## Fixed before running (from the plan)
- Constant answers scored first: "nothing violates" and "every file violates every rule".
- Majority-of-3 uses runs 1 to 3; majority-of-5 uses all five.
- GATE if majority-of-3 reaches precision 0.90 and recall 0.80 on each of the three local rules separately, with flip rate at most 0.10; otherwise ADVISORY. Both verdicts complete the task.
- Choices made by the scoring script before runs 2 to 5 were read (run 1 had been read): a finding matches a label on rule and file with the line within 2; majority clusters join findings of one rule and file whose lines are within 2 of a neighbour and need 2 of 3 (or 3 of 5) distinct runs; flip rate universe is every (rule, file) pair that is labelled or reported by any run, with a verdict of "at least one finding for the pair" per run. Definitions are in the docstring of `score.py`.

## Setup
- Corpus: 30 Python files in `core/` (10), `cli/` (6), `util/` (6), `api/` (6), `plugins/` (2), plus `rules.md` and `api.md`, written by this agent from `build_corpus.py` (`.compass/tmp/loop-experiments/build_corpus.py`). Rules: R1 no bare `except:`, R2 no `print()` outside `cli/`, R3 every public function (module level or class body, name without leading underscore) has a docstring as its first statement, R4 nothing under `core/` imports `cli/`, R5 every function named in `api.md` exists in the module `api.md` names (violation reported at the `api.md` entry line).
- Labels: 40 planted (R1 10, R2 10, R3 10, R4 5, R5 5), at most one per (rule, file) pair except the five R5 entries in `api.md`. Near-miss distractors: `except Exception:` and `except (A, B):`, `print(` inside a string and a comment, `print` in `cli/` files, `_private` functions with no docstring, `__init__`/`__repr__`, nested functions with no docstring, a comment "do not import cli here" in a `core/` file, `serialize_users` existing while `api.md` also names `serialize_order`.
- AST scan (`ast_scan.py`) of R1 to R3, extended to R4 and R5, found 40 violations: 0 unlabelled, 0 labelled but not found. `labels.json` is unchanged by the scan.
- Judge: copy of the corpus without `labels.json` and without the vault, at `~\AppData\Local\Temp\claude\F--claude-plugins-compass\<session>\scratchpad\judge-corpus\` (32 files). Each run is a separate `claude -p --model sonnet --output-format json --tools Read,Glob,Grep --allowedTools Read,Glob,Grep --setting-sources project --strict-mcp-config --disable-slash-commands --no-session-persistence --max-budget-usd 1.20`, prompt on stdin (`judge/prompt.txt`: read `rules.md`, go rule by rule over each file, answer with one JSON line per violation). Runs 2 to 5 ran in parallel. Wrapper: `judge/run_judge.sh N`.

## Findings

1. **Constant answers cannot pass** (confidence: high)
   "Nothing violates": 0 answers, recall 0/40 = 0.000, precision undefined. "Every file violates every rule" over the 30 Python files: 150 answers, 35 match a labelled (rule, file) pair, precision 35/150 = 0.233, recall 35/40 = 0.875 (the five R5 labels sit in `api.md`, outside the 30 files). The plan's formula 40/150 = 0.267. Counting `api.md` as a 31st file: 36/151 = 0.238, recall 1.000. Per local rule the all-files answer scores precision 10/30 = 0.333.
   - `judge/scores.json` key `constant` - every figure above
   - Marks: experiment, own run; not retracted; not a preprint; 0 citations; 1 source

2. **Every run found all 40 violations with no extras** (confidence: high)
   Each of the five runs returned exactly 40 JSON lines, and the set of (rule, file, line) triples in each run equals the label set exactly (same line, not only within 2), with no unparseable lines. Per run and per rule precision and recall are 1.000 (R1 10/10, R2 10/10, R3 10/10, R4 5/5, R5 5/5).
   - `judge/scores.json` key `single`, `run_meta`
   - Marks: experiment, own run; not retracted; not a preprint; 0 citations; 5 runs agree

3. **Majority-of-3 and majority-of-5 are perfect on every rule** (confidence: high)
   Majority-of-3 (runs 1 to 3): R1, R2, R3, R4, R5 each precision 1.000 and recall 1.000 (10/10, 10/10, 10/10, 5/5, 5/5 clusters true, all labels hit). Majority-of-5 identical. No missed label and no extra majority cluster in either.
   - `judge/scores.json` keys `maj3`, `maj5`, `maj3_missed`, `maj3_extra`, `maj5_missed`, `maj5_extra`
   - Marks: experiment, own run; not retracted; not a preprint; 0 citations; 5 runs agree

4. **Flip rate is 0.00** (confidence: high)
   Of 36 (rule, file) pairs (35 labelled pairs plus `R5 api.md`; no run reported a pair outside the labels) 0 differ across the five runs. Over the full grid of 151 pairs, 0 of 151.
   - `judge/scores.json` key `flip`
   - Marks: experiment, own run; not retracted; not a preprint; 0 citations; 5 runs agree

5. **Verdict: GATE** (confidence: medium)
   Majority-of-3 precision 1.000 >= 0.90 and recall 1.000 >= 0.80 on each of R1, R2, R3 separately, flip rate 0.000 <= 0.10: both parts of the fixed rule hold, so the rule returns GATE (a judge reading may decide `done` and harmful). Confidence is medium because the result is a ceiling on an easy corpus (see Gaps).
   - `judge/scores.json` keys `verdict`, `verdict_parts`
   - Marks: experiment, own run; not retracted; not a preprint; 0 citations; 1 source

6. **Cost and effort** (confidence: high)
   Five judge runs cost 0.6192 USD in total (run 1 0.1571, run 2 0.1203, run 3 0.1003, run 4 0.1240, run 5 0.1174), each 35 turns, `subtype` `success`, `terminal_reason` `completed`, no permission denials. Spend is the only spend of the experiment (corpus authoring and the AST scan call no model); budget was under 5 USD.
   - `judge/run1.json` to `judge/run5.json` - `total_cost_usd`, `num_turns`, `subtype`
   - Marks: experiment, own run; not retracted; not a preprint; 0 citations; 5 runs agree

7. **The judge reads rules and files with three read-only tools** (confidence: medium)
   With `--tools Read,Glob,Grep` and `--setting-sources project` run from a folder holding no `.compass/` vault, each run took 35 turns of tool use to cover 30 files plus `rules.md` and `api.md`, and returned only JSON lines. Runs used `--no-session-persistence`, so tool calls were not saved.
   - `judge/run_judge.sh` - the exact flags
   - Marks: experiment, own run; not retracted; not a preprint; 0 citations; 1 source

## Spot-check list for the human
Planted violations (open in `.compass/tmp/loop-experiments/corpus/`): `core/engine.py:23` (bare `except:`), `core/scheduler.py:26` (`print`), `core/registry.py:12` (`lookup` has no docstring), `core/events.py:2` (`import cli.output`), `api.md:8` (`handle_delete` is not defined in `api/handlers.py`).
Judge findings (run 1, `judge/run1.json`): `{"rule":"R1","file":"util/paths.py","line":24}`, `{"rule":"R2","file":"util/hashing.py","line":19}`, `{"rule":"R3","file":"util/retry.py","line":5}`, `{"rule":"R4","file":"core/storage.py","line":5}`, `{"rule":"R5","file":"api.md","line":56}`.

## Reproduce
```
python F:\claude\plugins\compass\.compass\tmp\loop-experiments\build_corpus.py
python F:\claude\plugins\compass\.compass\tmp\loop-experiments\ast_scan.py F:\claude\plugins\compass\.compass\tmp\loop-experiments\corpus
python F:\claude\plugins\compass\.compass\tmp\loop-experiments\judge\score.py
```
The first regenerates the corpus and `labels.json`; the second prints 40 found, 0 unlabelled; the third reads `judge/run1.json` to `run5.json` and `corpus/labels.json`, prints every number above and writes `judge/scores.json`. A judge run is `judge/run_judge.sh N` from inside `judge-corpus`.

## Contradictions
None.

## Gaps
- The corpus is easy: violations are structurally plain, one per file at most, and the distractors are the ones listed above. A perfect score shows the judge clears this bar; it gives no measured accuracy for subtler rules, longer files, rules without a crisp definition, or violations buried among many near-misses. Nothing in the run distinguishes a judge of 100 percent accuracy from one that merely ceilings here.
- One agent wrote the corpus, the rules and the AST scan; the judge is a separate session that saw no labels and no vault, but the rules were written with the planted violations in mind, so the rule text is unusually precise (for example the definition of a public function).
- The judge's tool calls were not saved, so what it read and how it reasoned between turns cannot be inspected; only its final JSON lines exist.
- Flip rate has no definition in the plan beyond "rule-and-file verdicts that differ across runs"; this document uses the labelled-or-reported universe and also reports the full grid; both are 0.
- Five runs of one model on one corpus at one time; run-to-run variance across days or model versions was not sampled.
- R4 and R5 were scored but have no GATE threshold in the plan.
