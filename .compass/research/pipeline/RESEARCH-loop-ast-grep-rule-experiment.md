---
title: "Can an agent draft accurate ast-grep rules from natural-language rules"
type: research
status: done
confidence: medium
area: pipeline
tags: [loops, sensors, ast-grep, rule-synthesis, experiment, precision, recall]
created: 2026-10-18
updated: 2026-10-18
git_branch: master
git_commit: 6752d44
author: researcher
depends_on: ["[[specs/pipeline/SPEC-026-control-theory-for-loops]]"]
summary: "Verdict DRAFT: headless sonnet, following the ast-grep author's recipe with no labels, drafted all three local rules at precision 1.0 and recall 1.0 (10/10 each); the corpus is easy, so the result is a ceiling"
---

# Can an agent draft accurate ast-grep rules from natural-language rules

From [[specs/pipeline/SPEC-026-control-theory-for-loops]], task TASK-155 of [[plans/PLAN-021-control-loops]]. Follows [[RESEARCH-loop-judge-sensor-experiment]]; feeds TASK-160 and TASK-161.

## Question
Given a rule in plain language and no labels, does a headless sonnet session following the ast-grep author's recipe draft a rule whose matches on the TASK-154 corpus have precision 1.0 and recall 1.0?

## Methodology
Repository mining, run as a pre-registered seeded-defect experiment: the corpus carries planted violations, the verdict rule was fixed in the plan before any session ran, and the drafting sessions never saw `labels.json`. No `grading:` field reached this run, so the findings are marked and ungraded.

## Fixed before running (from the plan)
- Recipe: [[RESEARCH-control-theory-for-loops]] finding 104 (sample snippet, rule, test against the snippet, scan), at most 3 test rounds per rule.
- Verdict DRAFT (the loop skill may draft sensor rules and show their matches to the human) if at least 2 of 3 rules reach precision 1.0 and recall 1.0 on the corpus; otherwise ASK (the skill asks the human for the rule or for confirmation of a sample of its matches).
- Scoring: a match counts when it names the label's file with the line within 2. ast-grep reports 0-based lines, so `score.py` adds 1.
- Do-nothing baseline: a rule matching nothing scores recall 0/10 on each rule and precision undefined; the verdict rule needs 1.0 on both, so it cannot pass.

## Setup
- Tool: `ast-grep-cli` **0.51.0** (`pip install ast-grep-cli` into a new venv `astgrep-venv` in the scratchpad; `ast-grep --version` prints `ast-grep 0.51.0`).
- Corpus copy per rule (`astgrep-R1/`, `astgrep-R2/`, `astgrep-R3/` in the scratchpad): the 32 files of `.compass/tmp/loop-experiments/corpus/` without `labels.json`.
- One session per rule: `claude -p --model sonnet --output-format json --tools Bash,Read,Write,Glob --allowedTools "Bash(<venv ast-grep.exe>:*)" Read Write Glob --setting-sources project --strict-mcp-config --disable-slash-commands --no-session-persistence --max-budget-usd 0.90`, prompt on stdin. The prompt gives the rule text verbatim from `rules.md` and the five recipe steps (`prompt-template.txt`, `prompts/R*.txt`). Wrapper: `run_rule.sh R1|R2|R3`.
- Each session wrote `rule.yml` and `snippet.py`; both are saved as `R*-rule.yml` and `R*-snippet.py`. The raw scan outputs `R*-scan.jsonl` were produced by re-running each saved rule over the corpus folder (the sessions' own final scans also covered their `snippet.py`, so their counts were 12, 12 and 14).

All files are in `.compass/tmp/loop-experiments/ast-grep/`.

## Findings

1. **Version** (confidence: high)
   ast-grep 0.51.0, installed with pip into a new venv, never the system Python.
   - Marks: experiment, own run; not retracted; not a preprint; 0 citations; 1 source

2. **R1 no-bare-except: precision 1.00, recall 1.00** (confidence: high)
   10 matches, 10 true positives, 0 false positives, 0 missed; every match is on the label's exact line. Session: 6 turns, `success`, 0.0619 USD.
   - `ast-grep/R1-rule.yml`, `ast-grep/R1-scan.jsonl`, `ast-grep/scores.json`
   - Marks: experiment, own run; not retracted; not a preprint; 0 citations; 1 source

3. **R2 no-print-outside-cli: precision 1.00, recall 1.00** (confidence: high)
   10 matches, 10 true positives, 0 false positives, 0 missed, exact lines. The rule carries an `ignores` glob for `cli/**`. Session: 6 turns, `success`, 0.0465 USD.
   - `ast-grep/R2-rule.yml`, `ast-grep/R2-scan.jsonl`, `ast-grep/scores.json`
   - Marks: experiment, own run; not retracted; not a preprint; 0 citations; 1 source

4. **R3 public-docstring: precision 1.00, recall 1.00** (confidence: high)
   10 matches, 10 true positives, 0 false positives, 0 missed, exact lines. It is the longest rule: kind, name regex, a negated docstring check, and an `any` over module-level, class-body and decorated positions. Session: 6 turns, `success`, 0.0720 USD.
   - `ast-grep/R3-rule.yml`, `ast-grep/R3-scan.jsonl`, `ast-grep/scores.json`
   - Marks: experiment, own run; not retracted; not a preprint; 0 citations; 1 source

5. **Verdict: DRAFT** (confidence: medium)
   3 of 3 rules reach precision 1.0 and recall 1.0; the fixed rule needs 2 of 3. Confidence is medium because the corpus is easy (see Gaps).
   - `ast-grep/scores.json` keys `ruleset_pass_2_of_3`, `verdict`
   - Marks: experiment, own run; not retracted; not a preprint; 0 citations; 1 source

6. **Spend** (confidence: high)
   Total 0.1804 USD (R1 0.0619, R2 0.0465, R3 0.0720), under the 3 USD limit. No other model spend.
   - `ast-grep/R*-session.json` key `total_cost_usd`
   - Marks: experiment, own run; not retracted; not a preprint; 0 citations; 3 runs agree

7. **Permission and write behavior** (confidence: medium)
   R1 and R3 each had one Bash call denied (a heredoc that wrote files and ran the scan in one command, outside the allowed ast-grep prefix); each session continued by writing files with the Write tool. R2 had no denial. All three ended `success` in 6 turns.
   - `ast-grep/R1-session.json`, `ast-grep/R3-session.json` key `permission_denials`
   - Marks: experiment, own run; not retracted; not a preprint; 0 citations; 3 runs agree

8. **Raw output shape** (confidence: high)
   `ast-grep scan --rule <file> --json=stream .` prints one JSON object per match with `file` (OS path separators, `util\\retry.py` on Windows), `range.start.line` (0-based), `ruleId`, `severity`, `message`, `text`, `lines`. It also prints an `Error: N error(s) found in code.` block and exits 1 when an error-severity rule matches.
   - `ast-grep/R1-scan.jsonl`
   - Marks: experiment, own run; not retracted; not a preprint; 0 citations; 1 source

## The three rules (verbatim)

R1, `ast-grep/R1-rule.yml`:
```yaml
id: no-bare-except
language: python
severity: error
message: Bare `except:` is not allowed; catch `Exception` or a specific error.
rule:
  kind: except_clause
  regex: '^except\s*:'
```

R2, `ast-grep/R2-rule.yml`:
```yaml
id: no-print-outside-cli
language: python
severity: error
message: print() is only allowed in files under cli/
files:
  - "**/*.py"
ignores:
  - "cli/**"
  - "**/cli/**"
rule:
  kind: call
  has:
    field: function
    kind: identifier
    regex: "^print$"
```

R3, `ast-grep/R3-rule.yml`:
```yaml
id: public-docstring
language: python
severity: error
message: Public function must have a docstring as the first statement of its body.
rule:
  all:
    - kind: function_definition
    - has:
        field: name
        regex: '^[^_]'
    - not:
        has:
          field: body
          has:
            nthChild: 1
            kind: expression_statement
            has:
              kind: string
    - any:
        - inside:
            stopBy: neighbor
            kind: module
        - inside:
            stopBy: neighbor
            kind: block
            inside:
              stopBy: neighbor
              kind: class_definition
        - inside:
            stopBy: neighbor
            kind: decorated_definition
            inside:
              stopBy: neighbor
              any:
                - kind: module
                - kind: block
                  inside:
                    stopBy: neighbor
                    kind: class_definition
```

## Reproduce
Run from `F:\claude\plugins\compass\.compass\tmp\loop-experiments\corpus`, with `BIN` the venv's `ast-grep.exe`:
```
BIN scan --rule ../ast-grep/R1-rule.yml --json=stream . | grep -c '^{'   -> 10
BIN scan --rule ../ast-grep/R2-rule.yml --json=stream . | grep -c '^{'   -> 10
BIN scan --rule ../ast-grep/R3-rule.yml --json=stream . | grep -c '^{'   -> 10
python ../ast-grep/score.py   -> R1, R2, R3 each precision 1.0, recall 1.0; verdict DRAFT
```
The counts are the output of running these commands; each scan exits 1 because error-severity rules matched. `score.py` reads `R*-scan.jsonl` and `corpus/labels.json` and writes `scores.json`.

## Gaps
- The corpus is easy: one plain structure per violation, a short list of near-misses, rules written with the planted violations in mind. A perfect score is a ceiling, not an accuracy estimate for subtler rules, other languages or larger code.
- The sessions ran with `--no-session-persistence`, so the number of test rounds each used (limit 3) and the intermediate rule versions were not saved; only the final rule, snippet and result exist.
- One session per rule, one model, one time; run-to-run variance in the drafted rule was not sampled.
- Only the three single-file rules were attempted; cross-file rules R4 and R5 were not.
- A snippet alone cannot test R2's path glob, so its `cli/` exemption was checked only by the corpus scan.
