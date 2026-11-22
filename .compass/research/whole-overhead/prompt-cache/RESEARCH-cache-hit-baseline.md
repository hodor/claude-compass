---
title: "Prompt-cache hit rate baseline, measured from local transcripts"
type: research
status: complete
confidence: medium
area: tooling
tags: [tokens, cost, prompt-caching, measurement, subagents]
summary: "main sessions read 96-99% of input from the cache, subagents 92-95%, but the first request of a session reads only 17-24%, and next-session reuse stops at a fixed block of about 7.8k tokens"
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "6faced1"
author: "researcher"
depends_on: ["[[SPEC-033-prompt-cache-is-a-design-input]]", "[[research/llm-research/REVIEW-llm-research-for-compass]]"]
---

# Prompt-cache hit rate baseline, measured from local transcripts

Research for [[SPEC-033-prompt-cache-is-a-design-input]], axis 1 of [[index]]. It measures item C1 of [[research/llm-research/REVIEW-llm-research-for-compass]] and tests the session-start claim of item A1 for the first time.

### Question

How much of Compass's repeated input is read from the provider prompt cache today, per kind of agent and across two sequential sessions, and how would a Compass change that lowers it be seen?

### Methodology

Repository mining (an empirical study of existing artifacts): the host's local session transcripts are the artifact, aggregated by a script; it fits "how does an existing system actually behave". Grading is allowed; every number below is measured, not asserted.

### Method and caveats

- Hit rate = `cache_read_input_tokens / (cache_read + cache_creation + input_tokens)`, tokens-weighted over a set unless "per message" is stated. Messages deduplicated by `requestId`; synthetic and all-zero usage rows dropped.
- Layout verified: main transcript `<session>.jsonl` per project dir; subagent transcripts in `<session>/subagents/agent-*.jsonl` with a beside `.meta.json` whose `agentType` field names the type (built-in and Compass types, plus ad-hoc names such as plan or build task labels). A subagent's first assistant message is its first request.
- Sets: "this repo" (233 sessions, 2026-09-13 to 2026-11-21, 539 subagent transcripts); "other Compass projects" (any project dir whose working directory or an ancestor holds a `.compass/` vault; 106 dirs, 1,441 sessions, 3,829 subagents, 2026-08-25 to 2026-11-21, includes experiment and harness directories); "non-Compass projects" (24 dirs, 169 sessions, 90 subagents).
- Session transcripts are mostly entrypoint `sdk-cli` (headless host run, the entrypoint this orchestrating session also reports) plus `cli` (interactive). Looprunner workers do not appear as separate transcripts here and are measured from their ledgers instead.
- Counts are not causes: the transcripts show what was read, not why a prefix differed. Cause claims are marked inferred.
- Script and raw output are scratch files outside the repo; only aggregates are recorded here.

### Findings

1. **Whole-session hit rate is high everywhere, because later requests reuse the growing prefix** (confidence: high)
   Main sessions: this repo 96.4% (1.34 billion input tokens, 8,144 requests), other Compass projects 97.5%, non-Compass 98.7%. Per-message median 99.3-99.5%; 3.0-4.9% of requests are below 50%. Excluding each session's first request changes the rate by under 1 point.
   - Evidence: scratch script over all transcripts, aggregate output (not in repo).
   - Marks: measured local telemetry; no retraction; not a preprint; 0 citations; 3 sets agree
   - Grade: high (direct measurement of the thing asked)

2. **The first request of a session reads 17-24% from the cache** (confidence: high)
   First-request hit: this repo 23.5% (n=233), other Compass 17.1% (n=1,441), non-Compass 21.9% (n=169). Median first request holds 32k-40k tokens; median 7.4k-7.7k are read and 28k-34k are written. First requests under 5% hit: 13% (this repo), 24% (other Compass), 21% (non-Compass); at 50% or more: 13%, 6%, 11%.
   - Marks: measured local telemetry; not retracted; not a preprint; 0 citations; 3 sets agree
   - Grade: high

3. **The first request's written prefix is read back by the second, so a first-request miss is a one-time write** (confidence: high)
   Second-request hit: this repo 77.2%, other Compass 80.3%; third 95.3% and 95.2%. First-request writes are 12.6% of all cache-creation tokens in this repo's main sessions (6.1% in other Compass projects, 1.7% non-Compass) and 0.63% of all main-session input.
   - Marks: measured local telemetry; 0 citations; 3 sets agree
   - Grade: high

4. **The reused part of a first request is a fixed block of about 5.5k-7.8k tokens** (confidence: high on the number, medium on what it is)
   Most common first-request `cache_read` values in this repo: 7,702 (48 sessions), 7,825 (40), 22,552 (31), 0 (30). Other Compass projects: 0 (341), 5,777 (78), 7,706 (74), 5,522 (56). Non-Compass: 631, 0, 5,581. A block that small and constant across sessions fits the host's system prompt plus tool definitions (inferred, not decomposed here; axis 2 decomposes the prefix). The 22,552 value appears only in this repo.
   - Marks: measured local telemetry; 0 citations; 3 sets agree; identity of the block inferred
   - Grade: high

5. **Next-session reuse stops at that fixed block, including inside the 1-hour lifetime** (confidence: medium)
   For `sdk-cli` sessions that start 5 to 60 minutes after the previous session in the same project ended (n=55 this repo, 470 other Compass): median first-request read 7,825 and 7,706 tokens; reads of at least 60% of the request are 0% and 2%. Within 5 minutes: 28% and 23% (this repo's 22,552 mode explains most). Non-Compass projects show the same shape (median read 631-1,739 tokens; 18-20% at 60% or more, n=82 and 10). Creation is 99% 1-hour tier, so the 5-minute expiry does not explain the miss at 5-60 minutes.
   - Caveat: transcripts mix interactive sessions and headless runs with different settings; consecutive sessions in a project dir are not necessarily comparable launches; cause (git-status snapshot, vault churn, CLAUDE.md edits, date line) is not isolated, so SPEC-033's "likely" stays inferred.
   - Marks: measured local telemetry; 0 citations; 3 sets agree on shape
   - Grade: medium (measured, confounded launches)

6. **Cross-session first-request hit by gap after the previous session ended (`sdk-cli`)** (confidence: medium)
   Weighted hit, this repo: concurrent 19.0% (n=11), up to 5 min 33.0% (109), 5-60 min 20.9% (55), over 1 h 9.2% (51). Other Compass: 13.5% (186), 35.6% (162), 23.6% (470), 6.9% (354). Non-Compass: 15.3% (10), 40.2% (82), 21.3% (10), 9.8% (2). Median gap between a project's consecutive sessions: 5.6 min this repo, 36.3 min other Compass, 0.9 min non-Compass.
   - Marks: measured local telemetry; 0 citations; 3 sets agree
   - Grade: medium

7. **Subagents hit 92-95% overall but start cold: first request 13% (this repo)** (confidence: high)
   All subagent requests: this repo 91.9% (13,629 requests, 1.41 billion tokens), other Compass 93.7%, non-Compass 94.5%. First request of a subagent: 12.9%, 13.7%, 9.7%; zero cache read in 49%, 44%, 61% of subagents. Median first-request read is 5.3k (this repo) and 2.8k (other Compass) tokens of a median 45k and 38k, so a subagent writes 32k-37k tokens at the start.
   - Marks: measured local telemetry; 0 citations; 3 sets agree
   - Grade: high

8. **Per subagent type: hit over all requests, then first request only** (confidence: high where n is large, low for n of 1-15)

   | Type | This repo: agents, hit, first req | Other Compass: agents, hit, first req |
   |---|---|---|
   | builder | 104, 92.4%, 6.1% | 507, 93.2%, 8.9% |
   | tester | 122, 91.1%, 13.5% | 484, 91.4%, 15.2% |
   | researcher | 84, 91.3%, 15.7% | 366, 91.2%, 14.1% |
   | planner | 14, 92.5%, 2.2% | 40, 93.4%, 1.5% |
   | reviewer | 14, 83.3%, 1.8% | 60, 86.2%, 2.3% |
   | debug | 6, 86.6%, 4.7% | 9, 90.9%, 2.5% |
   | validator | none | 6, 91.5%, 0.0% |
   | pattern-finder | 5, 80.5%, 0.0% | 15, 75.4%, 1.5% |
   | general-purpose | 142, 91.0%, 10.1% | 852, 95.0%, 8.1% |
   | Explore | none | 36, 89.5%, 13.2% |
   | fork | none | 10, 93.3%, 17.6% |

   Short-lived types (reviewer, debug, pattern-finder, the edit and mesh judges) sit lowest overall (53%-86%) because first-request writes are a larger share of their few requests. Of this repo's ad-hoc named agents (plan, build and test task labels, one transcript each), most of the largest show first-request hits of 36-68%; the rest show 0%. The high group is consistent with an agent started from the parent's context (inferred, not verified).
   - Marks: measured local telemetry; 0 citations; 2 sets agree
   - Grade: high for rows with n of 80 or more, low below 15

9. **Looprunner workers hit 88% overall, insensitive to spacing in this sample** (confidence: medium)
   85 ledger runs across 3 loops: weighted 88.2% (25.9M tokens), per-run median 80.0%, p10 73.3%, p90 92.4%. Runs spaced up to 5 min (n=69): 86.9%; 5-60 min (12): 91.9%; over 1 h (2): 89.3%; median turns per run 5, 15.5, 11. Turns per run dominate; spacing barely shows. A run's first request is not recorded separately in the ledger.
   - `plugin/cli/looprunner.py:674` - ledger writes `cache_read_tokens`, `cache_creation_tokens`, `input_tokens` per run.
   - Marks: measured Compass ledger telemetry; 0 citations; single set
   - Grade: medium (small n, no first-request split)

10. **Cache writes are almost entirely the 1-hour tier in these transcripts** (confidence: high)
    `usage.cache_creation` splits `ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens`: this repo 0.77M vs 46.7M, other Compass 6.2M vs 782.6M, non-Compass 0 vs 206.7M. Axis 3 holds the price consequence.
    - Marks: measured local telemetry; 0 citations; 3 sets agree
    - Grade: high

11. **What the CLI already reads (reusable for a detector)** (confidence: high)
    - `plugin/cli/commands/context_check.py:140-155` `_used_of` sums `input + cache_creation + cache_read` of a main-agent (`isSidechain` false) assistant message as context size; no hit rate.
    - `plugin/cli/sessionslib.py:184` `used_tokens` wraps it; `:125` `transcripts_dir`, `:137` `subagent_transcripts`, `:145` `records`, `:176` `entrypoint` already locate a project's transcripts and each session's subagent folder.
    - `plugin/cli/sensorlib.py:65-69` `TOKEN_FIELDS` and `:155` `parse_result` read `cacheReadInputTokens` and `cacheCreationInputTokens` from the headless result's `modelUsage`; `looprunner.py:674` stores them per run in each loop's ledger.
    - `plugin/cli/commands/usage.py:25` records command invocation counts in `.compass/meta/usage.yaml`, nothing about tokens.
    - Nothing computes a hit rate, reads `usage.cache_creation` TTL fields, or reads a subagent's `agentType` meta file. [[RESEARCH-axis-2-attribution]] records the same for the bench harness (`analyze.py` prices cache tokens but `summarize` omits them).
    - Marks: code read, current master; 0 citations; 1 source
    - Grade: high

12. **How a change that lowers the rate would be seen** (confidence: medium, a design fact derived from the numbers)
    The whole-session rate moved under 1 point when first requests were excluded (finding 1), so it cannot see a prefix break; the first-request read (tokens and hit) and the next-session pairing can. Both come from fields in every transcript request; the timestamps, entrypoint and project dir needed to pair consecutive sessions are in the same records.
    - Marks: derived from findings 1-11; no citations
    - Grade: medium

### Contradictions

- Finding 1 (97% whole-session) vs finding 2 (17-24% first request): both hold; the first request is under 1% of tokens but 6-13% of cache writes, so the aggregate hides it.
- SPEC-033 says two sequential sessions likely share no cached start past the git-status snapshot. Finding 5 measures reuse stopping at about 7.8k tokens, which matches; non-Compass projects show the same stop, so vault churn is not shown to be the sole cause.

### Gaps

- No decomposition of the 28k-34k tokens written at session start into system prompt, CLAUDE.md, rules, skills list, hook output and git status (axis 2).
- Cause of the break is untested: a controlled pair of launches (same project, same minute, vault clean vs churned) would isolate it.
- Interactive `cli` sessions are only 7 in this repo (first-request hit 14.1%); under-sampled.
- Looprunner first-request hit is not recorded; the ledger holds per-run totals.
- The 22,552-token read mode is unexplained.
- The context-inheriting agent pattern in finding 8 is inferred from first-request hits, not from agent definitions.

### Candidate changes

Listed for the planner; no choice made.
- A. A per-session first-request cache read and hit rate, with pairing to the previous session in the same project, in a CLI report reusing `sessionslib.transcripts_dir`, `records`, `entrypoint` and `context_check._used_of` (low token usage, almost zero cache misses). Not covered today.
- B. A per-agent-type hit rate from the subagent `agentType` meta file in the same report (low token usage). Not covered today.
- C. Record a loop run's first request separately in the ledger (almost zero cache misses). Partly covered: `looprunner.py:674` records run totals.
- D. Adopt the baseline above (first-request hit 17-24%, fixed block about 7.8k tokens, subagent first request 13%) as the KPI starting point SPEC-033 asks for.
