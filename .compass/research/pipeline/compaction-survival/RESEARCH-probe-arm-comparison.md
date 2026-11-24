---
title: "Probe arm comparison: the host summary against the mechanical state block at 21 recorded compactions"
type: research
status: complete
confidence: medium
area: methodology
tags: [compaction, probes, session-continuity, handoff, bench, kpi]
summary: "21 recorded compactions, four arms, 68 tool-less sessions: the host summary plus the state block beats the host summary alone on artifact recall only (+0.09, interval [0.01, 0.20]) and carries 36% more tokens; the state block alone carries 61% fewer tokens and is not distinguishable from the host summary on any type with 10 or more pairs; recall and decision have too few pairs for a verdict; 9 more points are waiting on the human's go"
created: 2026-11-23
updated: 2026-11-23
git_branch: "master"
git_commit: "30b5877"
author: builder
depends_on: ["[[plans/PLAN-033-compaction-keeps-the-session-state]]", "[[research/pipeline/compaction-survival/RESEARCH-probe-pilot]]"]
---

# Probe arm comparison

```mermaid
flowchart LR
    P["21 recorded compactions"] --> Q["questions frozen from the history before each one"]
    Q --> A1["host-summary"]
    Q --> A2["mechanical"]
    Q --> A3["compass"]
    Q --> A4["none"]
    A1 --> G["scored by script"]
    A2 --> G
    A3 --> G
    A4 --> G
    G --> D["paired difference from host-summary, per probe type"]
```

> [!summary] Result
> Adding the mechanical state block to the host summary names more of the edited files (0.56 against 0.47, a gain whose interval just clears zero) and costs about 1,900 more tokens. The block alone costs 2,068 tokens, 61% fewer than the host summary's 5,269, and scores lower on every type but decision, though no difference reaches a verdict. Task, error and decision probes are too few to rank anything.

## Method

Each arm gives a fresh model with no tools the same questions about a recorded compaction and a different carried text:

- **host-summary**: the summary the host wrote at that compaction.
- **none**: nothing. This is the floor.
- **mechanical**: the state block Compass renders from the transcript and git history as they stood at that compaction, with no model call.
- **compass**: the host summary followed by the state block, the order a Compass session holds them after a compaction. At a subagent compaction it carries the summary alone, since the session-start hook prints nothing there.

Probe types: `artifact` is the share of the edited files named, over the whole session; `artifact-recent` the same over the edits since the previous compaction; `recall` an error line or failed-test count from a failing tool result; `continuation` the task or plan id in hand; `decision` the option the human last chose; `state` the mean of a point's recall, continuation and decision scores. A paired interval is the 95% bootstrap interval of the mean difference from host-summary over the points both arms were asked, resampling points with replacement.

The pool is 21 points: the 8 pilot points (whose host-summary and none replies are the pilot's, regraded under the current recall rule) and 13 more, taken in listing order as the first that render a state block. `mechanical` and `compass` ran on all 21, `host-summary` and `none` on the 13 new ones, so each arm holds 21 graded points. Every point asked rendered a block: no point is no-state in any arm.

## Report

| arm | probe | points | mean score | unparsed | mean carried tokens |
|---|---|---|---|---|---|
| compass | artifact | 21 | 0.56 | 0 | 7185 |
| compass | artifact-recent | 16 | 0.64 | 0 | 7185 |
| compass | recall | 5 | 0.20 | 0 | 7185 |
| compass | continuation | 12 | 0.33 | 0 | 7185 |
| compass | decision | 8 | 0.88 | 0 | 7185 |
| compass | state | 13 | 0.50 | 0 | 7185 |
| host-summary | artifact | 21 | 0.47 | 0 | 5269 |
| host-summary | artifact-recent | 16 | 0.50 | 0 | 5269 |
| host-summary | recall | 5 | 0.20 | 0 | 5269 |
| host-summary | continuation | 12 | 0.42 | 0 | 5269 |
| host-summary | decision | 8 | 0.38 | 0 | 5269 |
| host-summary | state | 13 | 0.46 | 0 | 5269 |
| mechanical | artifact | 21 | 0.32 | 0 | 2068 |
| mechanical | artifact-recent | 16 | 0.37 | 0 | 2068 |
| mechanical | recall | 5 | 0.00 | 0 | 2068 |
| mechanical | continuation | 12 | 0.25 | 0 | 2068 |
| mechanical | decision | 8 | 0.50 | 0 | 2068 |
| mechanical | state | 13 | 0.29 | 0 | 2068 |
| none | artifact | 21 | 0.00 | 0 | 0 |
| none | artifact-recent | 16 | 0.00 | 0 | 0 |
| none | recall | 5 | 0.00 | 0 | 0 |
| none | continuation | 12 | 0.00 | 0 | 0 |
| none | decision | 8 | 0.00 | 0 | 0 |
| none | state | 13 | 0.00 | 0 | 0 |

Paired differences from host-summary:

| arm | probe | pairs | mean difference from host-summary | 95% paired interval |
|---|---|---|---|---|
| compass | artifact | 21 | 0.09 | [0.01, 0.20] |
| compass | artifact-recent | 16 | 0.14 | [-0.00, 0.33] |
| compass | recall | 5 | 0.00 | too few points |
| compass | continuation | 12 | -0.08 | [-0.25, 0.00] |
| compass | decision | 8 | 0.50 | too few points |
| compass | state | 13 | 0.04 | [-0.18, 0.21] |
| mechanical | artifact | 21 | -0.15 | [-0.42, 0.13] |
| mechanical | artifact-recent | 16 | -0.13 | [-0.49, 0.26] |
| mechanical | recall | 5 | -0.20 | too few points |
| mechanical | continuation | 12 | -0.17 | [-0.42, 0.00] |
| mechanical | decision | 8 | 0.12 | too few points |
| mechanical | state | 13 | -0.17 | [-0.42, 0.09] |
| none | artifact | 21 | -0.47 | [-0.65, -0.29] |
| none | artifact-recent | 16 | -0.50 | [-0.69, -0.30] |
| none | recall | 5 | -0.20 | too few points |
| none | continuation | 12 | -0.42 | [-0.67, -0.17] |
| none | decision | 8 | -0.38 | too few points |
| none | state | 13 | -0.46 | [-0.68, -0.24] |

The host summary's `artifact` mean is 0.47 over these 21 points; the pilot's 0.31 was over its 8.

## Tokens carried

Carried tokens are a session's input-side tokens minus the `none` session's at the same point.

| arm | mean carried tokens | against host-summary |
|---|---|---|
| none | 0 | fewer |
| mechanical | 2,068 | fewer (61% fewer) |
| host-summary | 5,269 | reference |
| compass | 7,185 | more (36% more) |

No-state points: 0 in every arm.

## Verdicts

Better means the interval's low end is above 0, worse its high end is below 0, otherwise not distinguishable. A type under 10 pairs gets no verdict.

| arm | probe | pairs | verdict against host-summary |
|---|---|---|---|
| compass | artifact | 21 | better (low end 0.005) |
| compass | artifact-recent | 16 | not distinguishable (low end -0.003) |
| compass | continuation | 12 | not distinguishable (high end exactly 0) |
| compass | state | 13 | not distinguishable |
| compass | recall | 5 | no verdict, too few points |
| compass | decision | 8 | no verdict, too few points |
| mechanical | artifact | 21 | not distinguishable |
| mechanical | artifact-recent | 16 | not distinguishable |
| mechanical | continuation | 12 | not distinguishable (high end exactly 0) |
| mechanical | state | 13 | not distinguishable |
| mechanical | recall | 5 | no verdict, too few points |
| mechanical | decision | 8 | no verdict, too few points |

- **compass** names more edited files than the host summary alone, at 36% more carried tokens. Its one verdict is on a low end 0.005 above zero, so the gain is marginal.
- **mechanical** carries 61% fewer tokens than the host summary. Its means sit below the host summary's on artifact, artifact-recent, continuation and state, and every interval spans 0, so the data neither show a loss nor rule one out.

## Cost

68 sessions, 34 on Opus 5.5, 28 on Haiku 5.5 and 6 on Sonnet 5. The Opus 5.5 sessions weigh 530,175 tokens (raw: 68 input, 20,061 output, 22,066 cache read, 342,959 cache write); the pilot's 10 Opus sessions weighed 125,341.

The price table holds no weight for Haiku 5.5 or Sonnet 5, so the weighted total undercounts the run: it counts none of the 34 sessions on those models. Their raw tokens:

| model | sessions | input | output | cache read | cache write |
|---|---|---|---|---|---|
| Haiku 5.5 | 28 | 56 | 7,855 | 18,172 | 220,106 |
| Sonnet 5 | 6 | 12 | 562 | 21,090 | 91,955 |

## Not yet run

- **9 more recorded points exist and are not yet asked**, up to 36 sessions. Their run is waiting on the human's go. One of them has no state block to render, so it starts no session for the two block arms.
- The `handoff` arm (a headless session writes a handoff from the history before the compaction) and the `before` arm (the model holds the history itself, the KPI's reference) are not yet run, so the comparison holds no handoff or before-the-boundary figure.
- Recall and decision have 5 and 8 points; a verdict on either waits for more points or for a judge that grades free text.
