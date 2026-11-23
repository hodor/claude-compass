---
title: "Probe pilot: what the host summary keeps at eight recorded compactions"
type: research
status: complete
confidence: medium
area: methodology
tags: [compaction, probes, session-continuity, handoff, bench, kpi]
summary: "Eight recorded compactions, two arms, 16 tool-less sessions: the host summary scores artifact recall 0.31, continuation 0.33, decision 0.67 and recall 0.00 against a floor of 0.00 everywhere; no reply failed to parse; artifact and continuation probes are frequent enough to compare arms, recall and decision are not"
created: 2026-11-22
updated: 2026-11-22
depends_on: ["[[plans/PLAN-033-compaction-keeps-the-session-state]]", "[[research/pipeline/compaction-survival/RESEARCH-axis-4-probe-kpi]]"]
---

# Probe pilot: what the host summary keeps

> [!summary] Result
> Given only the host's compaction summary, a fresh model names about a third of the files the session edited and the task in hand at a third of the points, and the option the human chose at two of three. With no text it scores zero on every probe. Script-graded probes are plentiful for files and task ids and scarce for errors and decisions.

## Method

The pilot used the probe runner in `bench/overhead` (`probe.py`) on this repository's own recorded sessions. The project folder holds 21 compaction points: 18 in five session transcripts and 3 in subagent transcripts. Eight points were picked, one per transcript: one from each of the five sessions and the three subagent points. For each point the runner froze its questions and answers from the history before the compaction, then asked them in two fresh sessions with no tools and the point's own model:

- **host-summary**: the session carries the summary the host wrote at that compaction.
- **none**: the session carries nothing. This is the floor.

Each reply was graded by script. Artifact is the share of edited files named (recall) and the share of named files that were edited (precision); recall and decision are a normalized substring match; continuation is an exact task or plan id.

## Report

| arm | probe | points | mean score | unparsed | mean carried tokens |
|---|---|---|---|---|---|
| host-summary | artifact | 8 | 0.31 | 0 | 8001 |
| host-summary | recall | 3 | 0.00 | 0 | 8001 |
| host-summary | continuation | 6 | 0.33 | 0 | 8001 |
| host-summary | decision | 3 | 0.67 | 0 | 8001 |
| none | artifact | 8 | 0.00 | 0 | 0 |
| none | recall | 3 | 0.00 | 0 | 0 |
| none | continuation | 6 | 0.00 | 0 | 0 |
| none | decision | 3 | 0.00 | 0 | 0 |

Carried tokens are the host-summary session's input-side tokens minus the floor session's at the same point: about 5,000 to 6,500 at session points and 11,000 to 13,000 at subagent points.

## Probes per point

| point | from | artifact | recall | continuation | decision | probes |
|---|---|---|---|---|---|---|
| 1 | session | 1 | 1 | 1 | 1 | 4 |
| 2 | session | 1 | 1 | 1 | 1 | 4 |
| 3 | session | 1 | 0 | 1 | 1 | 3 |
| 4 | session | 1 | 0 | 1 | 0 | 2 |
| 5 | session | 1 | 0 | 1 | 0 | 2 |
| 6 | subagent | 1 | 0 | 1 | 0 | 2 |
| 7 | subagent | 1 | 1 | 0 | 0 | 2 |
| 8 | subagent | 1 | 0 | 0 | 0 | 1 |

20 probes over 8 points: 2.5 per point, 3.0 at session points and 1.7 at subagent points. Subagents ask the human nothing, so they never yield a decision probe.

## Unparsed rate

0 of 16 replies failed to parse (0%). Every reply was one JSON object with the requested keys.

## Artifact recall against the floor

The host summary names 0.31 of the edited files on average; the floor names none. Per point the recall runs from 0 to 1: the summary of a short subagent run named every file, while summaries of long sessions with 25 to 52 edited files named under a third. The expected set holds every file edited since the session began, earlier compactions included, so at a later compaction the summary is asked about edits an earlier summary may already have dropped. Precision is 0.26 on average: most files the summary names are not in the edit trail.

## What the misses show

- **Recall** scored 0 at all three points. At one the reply quoted the error class and message but stopped before the error's last clause, and a whole-literal substring match scores that 0. The other two replies said the summary did not hold the error and guessed.
- **Continuation** missed at 4 of 6 points: twice by one task number, twice with another plan or task. The probe asks for the last id the assistant named, which is not always the work in hand.
- **Decision** missed once, where the last structured answer approved a document and the reply named another option.

## Cost

16 sessions. The 10 at session points ran on Opus 5.5: 125,341 weighted tokens (raw: 20 input, 3,932 output, 6,490 cache read, 84,269 cache write). The 6 at subagent points ran on Sonnet 5, which the price table does not hold, so they carry no weight: 12 input, 367 output, 21,090 cache read and 88,826 cache write tokens.

## What this says about the Later tasks

- **Arms can be compared on artifact and continuation.** Artifact appears at every point and continuation at 6 of 8; the floor is a clean zero, so any arm's gain over it is visible. The whole pool of 21 points gives about 21 artifact and 16 continuation probes, enough for a bootstrap interval over points in TASK-339.
- **Recall and decision are too scarce to compare alone.** Three points each in eight; the pool would give about eight. A per-type interval over that few points is too wide to rank arms. They can still be reported, or pooled with continuation as one "state" score.
- **Recall grading is too strict for the judge-free arms.** A correct but shortened quote scores 0. TASK-340's judge, or a rule that accepts the error class plus the message's first clause, would grade it.
- **The artifact key needs a window.** Scoring a summary on edits from before earlier compactions understates every arm the same way, but it hides how much each one keeps of the latest stretch. TASK-337's mechanical arm will name the whole edit trail and win this probe by construction; a second artifact score over the edits since the previous boundary would separate the arms fairly.
- **The pool grows with use.** The 21 points come from five sessions. More sessions add points; nothing in the runner limits the count.

The comparison is worth running on artifact and continuation now, with recall and decision reported beside them until the pool grows.
