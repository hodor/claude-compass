---
title: "Turn and budget caps past one turn and across resume"
type: research
status: done
confidence: high
area: pipeline
tags: [loops, claude-code, max-turns, max-budget-usd, resume, experiment]
created: 2026-10-18
updated: 2026-10-18
git_branch: master
git_commit: 413ac40
author: researcher
depends_on: ["[[specs/pipeline/SPEC-026-control-theory-for-loops]]"]
summary: "Verdict: --max-turns N lets exactly N tool rounds run (num_turns reads N+1) in 6 of 6 runs, so the default max_turns is 30; on --resume both caps count only the new invocation, so the no-resume rule stays only for the budget sum"
---

# Turn and budget caps past one turn and across resume

From [[specs/pipeline/SPEC-026-control-theory-for-loops]], task TASK-153 of [[plans/PLAN-021-control-loops]]. Extends the one-turn observation in [[research/pipeline/RESEARCH-control-theory-for-loops]].

## Question
Does `--max-turns N` allow N tool rounds beyond N=1, and do `--max-turns` and `--max-budget-usd` count only the resumed invocation or the whole session?

## Methodology
Repository mining shape "how does an existing system actually behave", run as an experiment on the installed artifact (Claude Code 2.1.302, `claude-haiku-4-5-20251001`), with the session transcript as the primary record. Marks are recorded on every finding; the brief carried no `grading:` state, so findings are marked and ungraded because nobody was asked.

## Setup
- Each run executes in its own folder under `~\AppData\Local\Temp\claude\F--claude-plugins-compass\ae974588-929f-4f0a-8ff2-ad796c7400a9\scratchpad\caps\` (outside the repo, no project hooks). Command shape: `claude -p --model claude-haiku-4-5-20251001 [--max-turns N | --max-budget-usd X] [--resume SID] --allowedTools "Write Bash" --output-format json "<prompt>"`.
- Capped-run prompt: create `f1.txt` to `f8.txt`, one Write call per assistant message, then `ls` with Bash (ten tool rounds). Resume-arm prompts follow the same shape with `g`, `h`, `k` files.
- All 12 stderr files are empty; `permission_denials` is `[]` in every run.
- Raw JSON, stderr, transcript copies and the files each run wrote are in `F:\claude\plugins\compass\.compass\tmp\loop-experiments\caps\` (`*.json`, `*.err`, `transcripts\`, `workdirs\`, `summarize.py`). Original transcripts: `~\.claude\projects\C--Users-user-AppData-Local-Temp-claude-F--claude-plugins-compass-ae974588-929f-4f0a-8ff2-ad796c7400a9-scratchpad-caps-<run>\<session_id>.jsonl`.
- A resume arm is two invocations on one session: a seed (`--max-turns 5`, "write g1.txt then say done", `success`, 2 turns) and the resume. A resume writes into the same transcript file as its seed, so each seed and resume pair shares one `transcripts\rsN.jsonl`.

## Runs

`num_turns`, `subtype` and `total_cost_usd` are copied from the saved JSON. Tool rounds are `tool_use` blocks in the transcript (for resume rows, only those after the resume prompt). Resume `total_cost_usd` is the session's cumulative spend.

| Run | Flag | num_turns | subtype | total_cost_usd | tool_use | tool_result |
|---|---|---|---|---|---|---|
| a3r1 | `--max-turns 3` | 4 | error_max_turns | 0.0519574 | 3 | 3 |
| a3r2 | `--max-turns 3` | 4 | error_max_turns | 0.0380743 | 3 | 3 |
| a3r3 | `--max-turns 3` | 4 | error_max_turns | 0.0380368 | 3 | 3 |
| a5r1 | `--max-turns 5` | 6 | error_max_turns | 0.0450354 | 5 | 5 |
| a5r2 | `--max-turns 5` | 6 | error_max_turns | 0.0464606 | 5 | 5 |
| a5r3 | `--max-turns 5` | 6 | error_max_turns | 0.0462518 | 5 | 5 |
| rs1_seed | `--max-turns 5` | 2 | success | 0.0340209 | 1 | 1 |
| rs1_resume | `--resume`, `--max-turns 2` | 3 | error_max_turns | 0.0427983 | 2 | 2 |
| rs2_seed | `--max-turns 5` | 2 | success | 0.0336039 | 1 | 1 |
| rs2_resume | `--resume`, `--max-budget-usd 0.003` | 2 | error_max_budget_usd | 0.0377279 | 1 | 1 |
| rs3_seed | `--max-turns 5` | 2 | success | 0.0341979 | 1 | 1 |
| rs3_resume | `--resume`, `--max-budget-usd 0.012` | 3 | error_max_budget_usd | 0.0470160 | 3 | 2 |

New spend of each resume (resume total minus seed total): rs1 0.0087774, rs2 0.0041240, rs3 0.0128181.

Total spend of the experiment: \$0.3934 (six capped runs plus the three resume sessions' cumulative totals, which already contain their seeds).

## Findings

1. **`--max-turns N` let exactly N tool rounds run in all six capped runs, N=3 and N=5; `num_turns` reads N+1** (confidence: high)
   Cap 3 produced 3 `tool_use` and 3 `tool_result` blocks and 3 files on disk in each of three runs; cap 5 produced 5 and 5 and 5 files in each of three runs. Every run ended `error_max_turns`, `terminal_reason: max_turns`, exit code 1, with the eighth-round prompt unfinished. `num_turns` equals executed `tool_result` count plus 1 in every row of the table, matching the N=1 run (num_turns 2) in [[research/pipeline/RESEARCH-control-theory-for-loops]].
   - `.compass/tmp/loop-experiments/caps/a3r1.json` to `a5r3.json`, `transcripts/a3r1.jsonl` to `a5r3.jsonl`
   - Marks: live run, code executed, transcript read; n/a retraction; not a preprint; n/a citations; 6 runs agree and agree with the N=1 run of the earlier gap pass

2. **A resumed invocation counts its own turns only: a session already at 2 turns, resumed with `--max-turns 2`, ran 2 new tool rounds** (confidence: high)
   rs1's seed used 2 turns. The resume then executed 2 tool rounds (g2, g3), reported `num_turns` 3, `error_max_turns`, `"Reached maximum number of turns (2)"`. Had the restored turns counted, the resume would have had no room for a round. The cap behaves on resume as it does on a fresh run.
   - `rs1_resume.json`, `transcripts/rs1.jsonl`
   - Marks: live run, transcript read; n/a; not a preprint; n/a; 1 run, agrees with findings 1 and 4
   - Caveat: single resume run at N=2, haiku only.

3. **A resume whose new spend alone exceeds `--max-budget-usd` stops with `error_max_budget_usd`, after the response that crosses the cap** (confidence: high)
   rs2: cap \$0.003, new spend \$0.004124, one tool round executed, `terminal_reason: budget_exhausted`, `"Reached maximum budget ($0.003)"`. rs3: cap \$0.012, new spend \$0.0128181, three tool rounds, same subtype. Both runs spent more than the cap by the cost of the final response (about 1.4x and 1.07x). Exit code 1 in both.
   - `rs2_resume.json`, `rs3_resume.json`
   - Marks: live run; n/a; not a preprint; n/a; 2 runs agree, and agree with the earlier gap pass's fresh-session budget stop

4. **The budget cap measures spend since the resumed process started: rs3 ran three rounds with \$0.0342 already restored against a \$0.012 cap** (confidence: high)
   rs3's restored total was \$0.0341979, already 2.8x the cap. A cap that counted restored spend would have stopped after the first response; the run continued until its own new spend reached \$0.0128181. Together with the earlier run (cap \$0.02, restored \$0.0416, new spend \$0.0047655, `success`), the cap does not include restored spend in three resumes.
   - `rs3_seed.json`, `rs3_resume.json`, `rs3.jsonl`
   - Marks: live run; n/a; not a preprint; n/a; 2 runs here plus 1 earlier run agree

5. **On a budget stop, the tool call in flight can run without a recorded result: rs3's third resume round left `k4.txt` on disk with no `tool_result` in the transcript** (confidence: medium)
   The transcript ends with a `tool_use` for the fourth file, then `last-prompt` and `cost-state` records. `workdirs/rs3/k4.txt` exists and contains `4`. `num_turns` 3 follows the pattern in finding 1 (recorded results plus 1) while three Write calls ran. A wrapper counting rounds from the transcript's results undercounts side effects by one on a budget stop.
   - `transcripts/rs3.jsonl` (last assistant record), `workdirs/rs3/k4.txt`
   - Marks: live run, transcript and disk read; n/a; not a preprint; n/a; 1 run
   - Caveat: single occurrence. rs2's budget stop and every turn-cap stop recorded a result for each executed call.

6. **Resume `total_cost_usd` is the session's cumulative spend; the per-resume figure is the difference to the seed's total** (confidence: high)
   In all three pairs the resume total exceeds the seed total by the new spend (\$0.0087774, \$0.0041240, \$0.0128181), consistent with the earlier gap pass's finding that a resumed result reports cumulative spend.
   - `rs1_seed.json` to `rs3_resume.json`
   - Marks: live run; n/a; not a preprint; n/a; 3 pairs agree

## Verdict

The verdict rules were fixed in [[plans/PLAN-021-control-loops]] (TASK-153) before the first run:

> If tool rounds equal the cap in all six capped runs, the default is 30 and the skill says "cap N allows N tool rounds"; otherwise the default is the measured rounds-per-cap ratio times 30, rounded down. The resume arms decide the no-resume rule: if a resumed run honors both caps, the rule stays only for the budget sum; if it ignores either, the rule is also the only cap protection.

- **Default `max_turns`: 30.** Tool rounds equal the cap in all six capped runs (3, 3, 3, 5, 5, 5). The skill states "cap N allows N tool rounds"; the JSON `num_turns` reads N+1.
- **No-resume rule: stays only for the budget sum.** The resumed run honored both caps. `--max-turns 2` bounded the resume to 2 new rounds (finding 2) and `--max-budget-usd` stopped it once its own new spend crossed the cap (findings 3 and 4). Both caps apply per invocation, so a loop that resumes one session each iteration gets a fresh turn cap and a fresh budget cap each time. The rule therefore exists to keep the summed spend bounded by the ledger, and the turn cap stays protective on its own.

## Reproduction

Command run, from `F:\claude\plugins\compass\.compass\tmp\loop-experiments\caps\`:

```
python -c "
import json,glob
for f in sorted(glob.glob('*.json')):
    d=json.load(open(f));n=0;tu=tr=0
    lo,hi=(2,99) if f.endswith('_resume.json') else ((1,2) if f.endswith('_seed.json') else (1,99))
    for l in open('transcripts/'+f.split('_')[0].replace('.json','')+'.jsonl',encoding='utf8'):
        r=json.loads(l);m=r.get('message')
        if r['type']=='user' and isinstance(m,dict) and isinstance(m['content'],str):n+=1
        if lo<=n<hi and isinstance(m,dict) and isinstance(m['content'],list):
            for b in m['content']:
                tu+=r['type']=='assistant' and b['type']=='tool_use';tr+=r['type']=='user' and b['type']=='tool_result'
    print(f[:-5],d['num_turns'],d['subtype'],d['total_cost_usd'],tu,tr)
print(sum(json.load(open(f))['total_cost_usd'] for f in glob.glob('a*r*.json')+glob.glob('rs*_resume.json')))
"
```

Output (columns: run, num_turns, subtype, total_cost_usd, tool_use, tool_result; the last line is the total spend):

```
a3r1 4 error_max_turns 0.0519574 3 3
a3r2 4 error_max_turns 0.0380743 3 3
a3r3 4 error_max_turns 0.0380368 3 3
a5r1 6 error_max_turns 0.045035399999999996 5 5
a5r2 6 error_max_turns 0.046460600000000005 5 5
a5r3 6 error_max_turns 0.046251799999999996 5 5
rs1_resume 3 error_max_turns 0.0427983 2 2
rs1_seed 2 success 0.0340209 1 1
rs2_resume 2 error_max_budget_usd 0.0377279 1 1
rs2_seed 2 success 0.0336039 1 1
rs3_resume 3 error_max_budget_usd 0.04701600000000001 3 2
rs3_seed 2 success 0.0341979 1 1
0.3933585
```

`summarize.py` in the same folder prints the same figures with the file counts on disk and each resume's new spend.

## Gaps
- One model (haiku 4.5), one prompt shape (one Write per message). A prompt that batches several tool calls in one assistant message was not run, so whether a "round" is a model turn or a tool call under batching is untested.
- `--max-turns` was tested at 3 and 5 on fresh sessions and at 2 on one resume. Values near 30 were not run.
- The rs3 in-flight tool call (finding 5) was seen once.
