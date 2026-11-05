---
title: "Whole overhead pilot"
type: research
status: draft
confidence: low
area: workflow
summary: "Overhead share of Compass over twelve builds on three topics, its spread, the batch size it implies, and the cost of one build"
tags: [overhead, pilot, measurement]
created: 2026-11-05
updated: 2026-11-05
git_branch: "master"
git_commit: "fdc9bb2"
author: "pilot.py"
---

# Whole overhead pilot

```mermaid
flowchart LR
  P["probe: 20 picks"] --> T["3 frozen topics"]
  T --> B["12 judged builds"] --> S["share and batch size"]
```

> [!IMPORTANT]
> You decide: whether the batch size and the cost of one build below are a pace your subscription can carry.

## Question

How much of a build's weighted tokens does Compass add, how much does that share vary between and within topics, and how many builds per arm does a 10% relative drop in it take to see at 95% confidence and 80% power? Related: [[SPEC-032-whole-overhead-measured-on-real-projects]].

## Findings

### The pilot

- Topic form chosen: seeded.
- Probe, seeded: 10 picks in 9 distinct kind and language classes.
- Probe, unseeded: 10 picks in 1 distinct kind and language classes.
- Builds closed: 12; refused: 0.
- Failed builds, left out of the shares: 0; finished builds without a judged verdict, also left out: 0.
- Builds stopped by the wall-time or turn cap and counted up to it: 4 with Compass, 0 without; the shares below are lower bounds.

### Overhead share

Share = (Compass-arm tokens minus without-Compass tokens, summed over builds) over Compass-arm tokens summed.

| Topic | Weighted share | Raw share |
|---|---|---|
| A | 97.5% | 98.7% |
| B | 66.7% | 32.3% |
| C | 51.2% | 8.2% |
| All | 77.2% | 58.8% |

- Bootstrap interval of the weighted share over topics (95%): 51.2% to 97.5%.
- Spread between topics (standard deviation of topic shares): 0.2354.
- Spread within a topic, between its runs (pooled standard deviation of pair shares, 3 degrees of freedom): 1.7199.

### Batch size

Builds per arm to see a 10% relative drop in the weighted share at 95% confidence and 80% power:

- From the point estimate of the within-topic spread: 7801.
- From its upper 80% chi-square bound: 23282.
- Windows of 5 hours for the point batch (both arms): 5201.
- Windows of 5 hours for the upper batch (both arms): 15522.

### Cost and time of one build

- Mean wall time: 5256 seconds; mean turns: 17.9.
- Builds that fit one 5-hour window: 3.
- Mean weighted tokens, compass arm: 10148381; mean raw tokens: 59411932.
- Mean weighted tokens, baseline arm: 2318289; mean raw tokens: 24457332.

### Where the tokens go

Mean weighted tokens per build, read from every session transcript of the build's project (setup, build, subagents, capture workers); see `bench/overhead/token_profile.py` for the counting and the split by source.

- Builds profiled: compass 6, baseline 6.
- Overhead share over whole projects (weighted): 78.4%.

#### Compass arm: 10722193 weighted tokens per build

Largest gap between counted tokens and a session's own totals: 2.1%.

| Session kind | Weighted per build | Share |
|---|---|---|
| subagent:tester | 3160394 | 29.5% |
| subagent:builder | 2993752 | 27.9% |
| subagent:researcher | 1468626 | 13.7% |
| build | 1294141 | 12.1% |
| subagent:planner | 832894 | 7.8% |
| capture-worker | 332641 | 3.1% |
| subagent:reviewer | 232865 | 2.2% |
| subagent:validator | 217997 | 2.0% |
| subagent:general-purpose | 127114 | 1.2% |
| setup | 61770 | 0.6% |

| Source family | Weighted per build | Share |
|---|---|---|
| output | 4125432 | 38.5% |
| tool result | 2215051 | 20.7% |
| skill body | 1304534 | 12.2% |
| tool call | 1061689 | 9.9% |
| attachment | 812090 | 7.6% |
| prefix:tool definitions | 550608 | 5.1% |
| prefix | 401114 | 3.7% |
| user | 181362 | 1.7% |
| assistant | 70313 | 0.7% |

| Source | Weighted per build | Share |
|---|---|---|
| output:subagent:tester | 1544286 | 14.4% |
| skill body:preloaded | 1291425 | 12.0% |
| output:subagent:builder | 1049242 | 9.8% |
| tool result:Bash | 810556 | 7.6% |
| tool call:Write | 579997 | 5.4% |
| output:subagent:researcher | 558527 | 5.2% |
| tool result:Read project | 422803 | 3.9% |
| prefix:system prompt | 401114 | 3.7% |
| output:subagent:planner | 369661 | 3.4% |
| tool result:Read .compass/plans/ | 271707 | 2.5% |
| tool call:Bash | 267548 | 2.5% |
| attachment:instructions | 265882 | 2.5% |
| attachment:agent_listing_delta | 177526 | 1.7% |
| attachment:skill_listing | 148771 | 1.4% |
| prefix:tool Agent | 131003 | 1.2% |

| Phase | Weighted per build | Share |
|---|---|---|
| subagent:tester | 3160394 | 29.5% |
| subagent:builder | 2993752 | 27.9% |
| subagent:researcher | 1468626 | 13.7% |
| subagent:planner | 832894 | 7.8% |
| build | 548386 | 5.1% |
| vision | 429065 | 4.0% |
| capture-worker | 332641 | 3.1% |
| subagent:reviewer | 232865 | 2.2% |
| subagent:validator | 217997 | 2.0% |
| research | 156994 | 1.5% |
| none | 136264 | 1.3% |
| subagent:general-purpose | 127114 | 1.2% |
| compass:setup | 61770 | 0.6% |
| spec | 23432 | 0.2% |

#### Baseline arm: 2318289 weighted tokens per build

Largest gap between counted tokens and a session's own totals: 0.0%.

| Session kind | Weighted per build | Share |
|---|---|---|
| build | 2224185 | 95.9% |
| subagent:general-purpose | 94104 | 4.1% |

| Source family | Weighted per build | Share |
|---|---|---|
| output | 813465 | 35.1% |
| tool call | 762414 | 32.9% |
| tool result | 405820 | 17.5% |
| prefix:tool definitions | 135142 | 5.8% |
| attachment | 104761 | 4.5% |
| assistant | 64249 | 2.8% |
| prefix | 21012 | 0.9% |
| user | 7447 | 0.3% |
| skill body | 3979 | 0.2% |

| Source | Weighted per build | Share |
|---|---|---|
| output:none | 598636 | 25.8% |
| tool call:Write | 550686 | 23.8% |
| tool result:Read project | 214543 | 9.3% |
| output:(other) | 172198 | 7.4% |
| tool result:Bash | 135493 | 5.8% |
| tool call:Bash | 126070 | 5.4% |
| tool call:Edit | 74385 | 3.2% |
| assistant:text | 50839 | 2.2% |
| output:subagent:general-purpose | 42631 | 1.8% |
| attachment:budget_usd | 32154 | 1.4% |
| attachment:edited_text_file | 30114 | 1.3% |
| prefix:tool PowerShell | 28234 | 1.2% |
| prefix:system prompt | 21012 | 0.9% |
| attachment:skill_listing | 20006 | 0.9% |
| prefix:tool Agent | 17123 | 0.7% |

| Phase | Weighted per build | Share |
|---|---|---|
| none | 1373138 | 59.2% |
| (other) | 851048 | 36.7% |
| subagent:general-purpose | 94104 | 4.1% |

### Weighted tokens per launched agent (before PLAN-029)

The "before" figures of [[PLAN-029-crafted-agent-context]]: every subagent session of the six Compass-arm builds, plugin at commit e331edd, counted by `token_profile.py --by-agent`. Four of the six builds stopped at the wall-time cap, so these are launches up to the cap.

| Agent type | Launches | Mean weighted per launch | Median |
|---|---|---|---|
| tester | 51 | 371811 | 266575 |
| builder | 48 | 374219 | 299116 |
| researcher | 24 | 367156 | 371687 |
| planner | 10 | 499736 | 416916 |
| reviewer | 4 | 349298 | 356789 |
| validator | 4 | 326995 | 295470 |
| general-purpose | 19 | 40141 | 0 |

### Judge

- Goal items, compass arm: met 27, not met 17, partly met 18.
- Goal items, baseline arm: met 41, not met 8, partly met 13.

### Headless checks

Read from the session transcripts after the run; the pilot's run log does not hold them. Builds are named by topic (A, B, C) and run (1, 2): A1 is the first Compass-arm build of topic A.

- Compass's hooks ran under the flags in all six Compass-arm builds. Each end of turn ran one Stop capture-check (5 to 58 per build session). Every vault write in the build session and its subagents ran `compass sync`. `compass guard` checked subagent calls and denied deletes in 5 builds; C1, whose only subagent was a validator, had no denial. The hooks' state files are under `.compass/tmp/` (high).
- Every build reached a review gate and ran `compass review` from the build session. Each call that got past argument checks answered `not configured`: no Obsidian vault, and no VS Code or Cursor on the PATH, so no window opened. `AskUserQuestion` is not among the 16 or 17 tools of a headless session, so every gate was asked as numbered plain text and the simulated human typed the answer. Wasted calls: in A1 and A2, `--why` with a single file was rejected ("needs several files"), and A2 once called a bare `compass`, which is not on the PATH (high).
- Compass loaded once in all six builds. By the `system/init` counts, the setup session, started with `--plugin-dir`, had 53 skills: 19 built-in and 34 `compass:*`. The build session, started without it, had 53: 19 built-in and the 34 project copies, with no `compass:*` skill. Agents went from 6 to 19: the 13 project copies, since the plugin ships none. Every Stop ran one capture-check and every vault write ran one sync (high).
- No other plugin loaded in a setup, build or baseline session: 14 built-in skills, the 6 built-in agents, no MCP tools. Two build sessions later listed extra skill sets. A1 listed 10 from a third-party repository that its research step cloned under `.compass/tmp/` (init count 63). A2 listed the project skills again from three agent worktrees under `.claude/worktrees/` (init count 152). Capture workers run outside the flags, and they loaded 13 account skills and 4 claude.ai connectors (58 deferred MCP tools) (high).
- Self-update left `.claude/` unchanged. In all six builds, the skills, agents, rules and CLI match the plugin at the pinned commit e331edd byte for byte, line endings aside. Each build has the check stamp, no update log and no update call. The only additions are untracked: agent worktrees (A2), a planner's agent memory (B2) and test caches under the CLI (high).
- Capture workers are counted by the profile and not by the run log. The six builds started 19 extract-lessons sessions, one per capture opportunity: A1 5, A2 7, B1 2, B2 2, C1 1, C2 2. They come to 3.1% of the Compass arm's profiled weighted tokens. The shares under "Overhead share" come from the run log and so leave them out; the whole-project share that counts them is 78.4% against 77.2% (high).
- Frozen goal items the Compass arm's own specs dropped, judged against each spec's text. Four items name a toolchain, a build command or the test suite; a spec carries no technology, so they are not counted. Left out entirely: A1 1, B2 1, all others 0. Contradicted: A1 1 (an input format dropped by a spec decision), A2 2 (a different default size for a top list, and unreadable lines skipped where the goal asks for a nonzero exit), B1 1 (actor speed in place of one player action, then every monster). Stated without the goal's number or detail (counts of floors, weapons, monster types, the end-of-run summary's fields): A1 1, B1 5, B2 5, C1 2, C2 3. Every build wrote all the specs it planned (medium).

### Validity of this run

- **The shares are lower bounds.** Four Compass builds (A2, B1, B2, C2) stopped at the 150-minute cap and are counted up to it. The baseline builds all finished. Beyond capture workers, the profile finds 0.29M to 0.49M more weighted tokens than the run log in each capped build; in the two finished builds the two counts match exactly.
- **One pair drives the spread and the batch size.** Weighted share per pair, (compass minus baseline) over compass: A1 96.9%, A2 98.0%, B1 90.8%, B2 40.2%, C1 -324.2%, C2 94.0%. C1's Compass build ended after 6 turns with 1.16M weighted. Its main session did the work itself and launched only a validator, where the other five launched 19 to 48 subagents. Its baseline pair ran 17 turns with 4.92M. C1 gives 98.6% of the within-topic sum of squares behind the 1.7199 spread.
- **The batch size formula does not fit these pairs.** A pair share is bounded above by 1 and unbounded below, so a small Compass build sends it far below zero. The formula assumes pair shares that spread evenly around their mean, and it has 3 degrees of freedom here. The runs of the two arms are independent and pair by run number only. Pairing them the other way within each topic gives a spread of 0.1801 and batches of 86 (point) and 256 (upper). Leaving topic C out gives 0.2529 and batches of 169 and 756. 7801 and 23282 describe the C1 pair, not the noise of the share.
- **The share and the spread weigh builds differently.** The share is a ratio of sums, so C1 counts by its size: 1.16M of 60.9M Compass-arm tokens. The spread comes from per-pair ratios, which weigh every pair equally.
- **The baseline arm varies more than the Compass arm.** Four of the six baseline builds ended after 1 or 2 turns, when the simulated human said it was done. Baseline totals range from 0.27M to 6.59M (24 times), Compass totals from 1.16M to 13.47M (12 times). B2 and C1 hold 83% of the baseline arm's weighted tokens.
- **The judge's counts compare finished work with cut-off work.** Goals met: baseline 41, Compass 27. Per Compass build: A1 2, A2 0, B1 8, B2 1, C1 8, C2 8; per baseline build: 5, 5, 7, 7, 8, 9. Four Compass projects were judged as they stood at the cap. The two finished Compass builds met 2 and 8 goals; their baseline pairs met 5 and 8.
- **Web research is a Compass-only cost here.** Search and fetch were allowed in both arms. Compass subagents in four builds (A1, A2, B2, C2) made 474 fetches and 75 searches; no baseline build made any. Their results count in the Compass arm's tokens.
- **Capture workers are outside the shares.** Their 3.1% is left out of "Overhead share". They run outside the harness's flags and loaded account skills and claude.ai connectors that the build sessions did not.
- **Three topics bound the between-topic figures.** Every bootstrap resample of three topics lies between the lowest and highest topic share, so the interval is those two shares. Mean wall time and turns are also cut off by the cap in four of the six Compass builds.
