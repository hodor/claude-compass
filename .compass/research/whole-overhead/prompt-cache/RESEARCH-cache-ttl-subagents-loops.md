---
title: "Cache lifetime for subagents, build waves and loop workers"
type: research
status: complete
confidence: medium
area: tooling
tags: [tokens, prompt-caching, ttl, subagents, looprunner, measurement]
summary: "TTL controls, price break-even, subagent prefix sharing and measured local gaps: subagents write 100% 5-minute cache, main sessions 99% 1-hour; parallel same-type starts hit 82%"
created: 2026-11-21
updated: 2026-11-21
author: researcher
---

# Cache lifetime for subagents, build waves and loop workers

From [[SPEC-033-prompt-cache-is-a-design-input]]. Reuses [[research/llm-research/REVIEW-llm-research-for-compass]] item A1 and its "2b B7" claim; B7's doc rules are re-verified below against the live page and extended with measurement.

### Question
Which cache-TTL controls exist, what do they cost, do sibling subagents and parents share a cached start, and what do Compass's own gaps (waves, loop spacing, human gates) look like against the TTL?

### Methodology
Repository mining (empirical study of the host's own transcripts) plus a case-study read of the provider and host documentation and the Compass code. Mining fits "how does an existing system actually behave"; docs are read only to name the controls and prices, then checked against transcripts.

Grading: allowed (brief). Marks on each finding: evidence type, retraction, preprint, citation count, convergence. Vendor docs and local measurements are neither retractable nor preprint and have no citation count; those marks read "n/a" and are not repeated per finding.

Measurement base (aggregates only): 1,784 main-session transcripts (115,780 distinct requests, 2026-08 to 2026-11) and 4,445 subagent transcripts (116,513 requests). Requests are deduplicated by message id; gap = timestamp difference between consecutive requests of one transcript (approximation: timestamps mark the response record, not the request start). Script: `ttl_measure.py` in the session scratchpad. Probable bias: one user's one machine, subscription billing (see F5).

## Findings

### A. Controls and prices (docs)

1. **Four host controls set the TTL, with a fixed precedence** (confidence: high)
   Two buckets: "main conversation" (interactive, `-p`, Agent SDK) and "everything else" (subagents, workflows, teammates, forks, compaction, titles). Controls: `promptCacheTtl` / `CLAUDE_CODE_PROMPT_CACHE_TTL` (main), `subagentPromptCacheTtl` / `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL` (everything else), `cacheTtl` under the subagent's `experimental` frontmatter (v2.1.248+), `ENABLE_PROMPT_CACHING_1H=1` (both buckets). Values `5m` or `1h` only; v2.1.242+ for the settings and env vars. Order: `FORCE_PROMPT_CACHING_5M=1`, bucket env var, bucket setting, agent `experimental.cacheTtl`, `ENABLE_PROMPT_CACHING_1H`, bucket default.
   - https://code.claude.com/docs/en/prompt-caching ("Choose the TTL yourself") - read in full this pass
   - Marks: vendor doc, read live 2026-11-21; converges with B7 (same page, earlier read)
   - Grade: high (asserted by vendor, rules checkable; defaults confirmed by F5)

2. **Defaults: 1 hour only for the main conversation on a subscription within plan usage; everything else 5 minutes** (confidence: high)
   API key, usage credits or cloud provider: main conversation 5 minutes. Over plan usage the main conversation drops to 5 minutes. A `1h` in agent `experimental.cacheTtl` is ignored while the subscription is on usage credits. Some server-controlled helper requests get 1 hour.
   - https://code.claude.com/docs/en/prompt-caching ("Which TTL each request gets")
   - Marks: vendor doc; converges with B7 and F5
   - Grade: high

3. **Price: 5m write 1.25x, 1h write 2x, read 0.1x base input; Opus 5.5 and Sonnet 5.5 read 0.05x; Fable/Mythos 5.1+ read 0.025x** (confidence: high)
   A hit refreshes the lifetime at no cost; the lifetime runs from the start of the request that wrote or read, not its end (a 4-minute stream leaves about 1 minute). A read of a 5m entry restarts a 5-minute life even if that request asks for 1h. Multipliers stack with Batch discounts.
   - https://platform.claude.com/docs/en/build-with-claude/prompt-caching ("Pricing", "Cache storage and sharing", TTL refresh paragraph)
   - Marks: vendor doc; first half of the page read (first 100,000 of 155,517 characters)
   - Grade: high

4. **Break-even: the 1-hour write pays only if a prefix is reused after a 5-60 minute gap more than about 65% of the time** (confidence: medium)
   Derived from F3, not stated by the source. Per prefix of N tokens: 5m path = 1.25N + 1.25N per expiry; 1h path = 2N + 0.1N per gap reuse. One idle gap (5m-1h) per prefix gives 1.25*2 = 2.5N vs 2.1N (1h wins); continuous use with no gap gives 1.25N vs 2N (5m wins by 0.75N). Break-even probability of a 5-60 minute gap = 0.75/1.15 = 65% (62.5% at 0.05x reads). Gaps over 1 hour expire both TTLs.
   - Derivation from F3 prices; no source states the number
   - Marks: derived; convergence n/a
   - Grade: medium (arithmetic is exact, inputs are vendor prices)

5. **Minimum cacheable prompt: 512 tokens on the 5.x family (Fable, Mythos, Opus 5/5.5, Sonnet 5.5, Haiku 5.5); 1,024 on Sonnet 5, Sonnet 4.6/4.5, Opus 4.8; 2,048 on Opus 4.7; 4,096 on Opus 4.6/4.5 and Haiku 4.5** (confidence: high)
   Shorter prompts are processed uncached with no error; both cache counters read 0. Compass's agent system prompts are far above 512 tokens (see F9 median 2,821 cached tokens for a first request).
   - https://platform.claude.com/docs/en/build-with-claude/prompt-caching ("Minimum cacheable prompt length")
   - Marks: vendor doc
   - Grade: high

6. **TTL mixing rule and parallel-request rule** (confidence: high)
   A request may mix 1h and 5m breakpoints but 1h entries must come first. A cache entry exists only after the first response starts, so concurrent requests do not share it; the docs say to wait for the first response. Lookback is 20 blocks per breakpoint.
   - https://platform.claude.com/docs/en/build-with-claude/prompt-caching ("Mixing TTLs", "Concurrent requests", "20-block lookback")
   - Marks: vendor doc
   - Grade: high

### B. Sharing between agents (docs and measurement)

7. **A subagent shares no prefix with its parent; a fork does; a resumed subagent can read its own earlier cache** (confidence: high)
   A subagent has its own system prompt and tools, so its first request does not read the parent's cache; the parent's cache is unaffected by spawning. A fork inherits system prompt, tools and history and reads the parent's cache. Workflow fan-outs hold all but the first same-prefix agent up to 5 seconds by default so the first writes the cache; ordinary parallel Agent calls are not described as held.
   - https://code.claude.com/docs/en/prompt-caching ("Subagents and the cache"); the workflows page it cites was not fetched
   - Marks: vendor doc; converges with B7
   - Grade: high

8. **Cache scope is machine plus directory; parallel sessions in one directory share, sequential sessions share only if the startup git snapshot matches** (confidence: high)
   The system prompt embeds auto-memory paths and the conversation opens with cwd, platform, shell, OS; the startup git status snapshot (branch, recent commits) is part of the prefix. This restates the spec's premise as vendor doc; the measurement of sequential-session sharing is out of this axis.
   - https://code.claude.com/docs/en/prompt-caching ("Cache scope")
   - Marks: vendor doc; converges with the spec problem statement
   - Grade: high

9. **Measured: same-type subagents started in a burst or within 5 minutes of a sibling hit the cache on their first request 82% to 95% of the time; beyond 5 minutes the rate falls to 42% and beyond 1 hour to 13%** (confidence: medium)
   Grouped by project and agent type, ordered by first-request time. Bucket of gap since the previous same-type start: none earlier 52% (n=995); under 10 seconds 82% (n=885); 10 s to 5 min 95% (n=686); 5 min to 1 h 42% (n=1,094); over 1 h 13% (n=785). Restricted to siblings of the same parent the figures are 82% (n=884), 95%, 43%, 14%. The shared part is small: median first request reads 2,821 tokens and writes 32,617 (read share of first-request input 16-19% in the warm buckets), so the shared prefix is the agent's system prompt plus tools and the rest is task-specific.
   - Local transcripts, script `ttl_measure.py`; no sibling parallelism claim beyond hit/miss of the first request
   - Marks: measured, one machine; converges with F7 (same type shares; unrelated gap expires)
   - Grade: medium (measured, but the hit may come from a non-sibling earlier request and the 82% parallel-burst hits cannot be separated from a prior-wave cache)

10. **Measured: every subagent cache write on this machine is 5-minute; 0 of 4,445 subagent transcripts contain a 1-hour write** (confidence: high)
   Includes background (3,971), foreground (380) and unlabeled (94) shapes. No transcript sets a subagent TTL; consistent with F2 and with B7's finding that Compass sets none.
   - Local transcripts: `usage.cache_creation.ephemeral_1h_input_tokens` is 0 in all 116,513 subagent requests
   - Marks: measured; converges with F2
   - Grade: high

11. **Measured: main sessions write 99.3% 1-hour cache; `-p` (sdk-cli) sessions 100%, interactive 99.0%** (confidence: high)
   929.7M cache-write tokens in 115,780 main requests; 1,777 of 1,784 transcripts contain a 1-hour write. Read share of main input is 97.3%; subagents 93.4%. Matches the F2 default for a subscription within plan usage.
   - Local transcripts, same script
   - Marks: measured; converges with F2
   - Grade: high

12. **Measured gaps: in main sessions 4.9% of consecutive requests are more than 5 minutes apart and 0.9% more than 1 hour; within one subagent 1.3% and 0.09%** (confidence: medium)
   Median gap 12.2 s (main) and 9.7 s (subagent); p90 87 s and 52 s. In subagents, requests after a >5-minute gap are 1,420 of 112,068 but carry 24% of write tokens (173.6M of 721.9M), nearly all in the 5-minute to 1-hour band (156.8M). Subagent duration: median 359 s, p90 1,838 s, 54% run longer than 5 minutes, 4.5% longer than 1 hour; median 18 requests.
   - Local transcripts. Timestamp caveat: gap measured between response records.
   - Marks: measured
   - Grade: medium

13. **Counterfactual on measured traffic: moving subagent writes to 1 hour would raise their modeled cost by about 15%; main traffic is unchanged by the modeled switch** (confidence: low)
   Cost units in base-input tokens (writes 1.25/2, reads 0.1): subagents 2.354B actual vs 2.710B if every write were 1h with expiry-gap rewrites avoided (ratio 1.151). The model credits a gap only when the next request wrote cache and re-reads at most the previous total; it assumes no other expiry cause. Main traffic ratio 1.000 (already 1h). Read with F4: the within-agent gaps (1.3%) are too few for 1h to repay its write premium; the case for 1h depends on a different grouping (F9: reuse across same-type agents 5-60 minutes apart).
   - Local transcripts, `ttl_measure.py` function `cf`
   - Marks: modeled from measured
   - Grade: low (simplified model; cross-agent reuse is not in the counterfactual)

### C. Compass code today

14. **Compass sets no cache TTL anywhere: no env var in the loop worker, no `experimental.cacheTtl` in agent frontmatter, no setting in hooks** (confidence: high)
   `launch_session` copies the parent environment and adds only `COMPASS_WORKER_SESSION` and a default `CLAUDE_PROJECT_DIR` (`plugin/cli/looprunner.py:759-761`); argv carries `-p --output-format json --model --max-turns --max-budget-usd --strict-mcp-config` (`:750-756`). The builder, tester and validator templates carry `model`, `effort`, `maxTurns`, `memory`, `permissionMode`, `initialPrompt` and (validator only) `background: true`, no `experimental` map (`plugin/templates/agents/builder.md:1-14`, `tester.md`, `validator.md:12`). A grep of `plugin/` for `cacheTtl`, `CACHE_TTL`, `subagentPromptCacheTtl`, `PROMPT_CACHING` finds nothing; `plugin/hooks/hooks.json` has no cache setting. Because the worker env is inherited, a TTL env var exported by the scheduler or the user's shell reaches workers without a code change.
   - Marks: local code read; converges with B7 and F10
   - Grade: high

15. **Frontmatter syntax is verified: `cacheTtl` goes inside an `experimental` map, `5m` or `1h`, subagent files only, v2.1.248+** (confidence: high)
   Written as `experimental:` then `  cacheTtl: 1h`. Ignored in `--agents` JSON, ignored for `1h` while a subscription draws usage credits. `background`, `isolation` and `effort` are listed in the same table.
   - https://code.claude.com/docs/en/sub-agents ("Frontmatter reference"), first 100,000 of 115,219 characters read
   - Marks: vendor doc; converges with F1
   - Grade: high

16. **The looprunner has no spacing logic; run spacing is whatever the external scheduler does, default daily** (confidence: high)
   `looprunner.py` contains no interval or sleep between runs (the only sleep is the lock retry, `:480`); one run is one `execute()` (`:532`) that launches one actuator session (`:642`). The scheduler commands render `DEFAULT_CRON = "0 6 * * *"` and a local 06:00 task (`plugin/cli/commands/loop.py:110-111`), so consecutive runs are about 24 hours apart, past both TTLs: every run starts a cold cache whatever the TTL. Inside a run the optional judge launches `runs` fresh `claude -p` sessions back to back with the same prompt (`looprunner.py:773-774`), spaced by session duration only.
   - Marks: local code read; convergence n/a
   - Grade: high (code), the judge-sessions' hit rate is unmeasured (see Gaps)

17. **Loop workers are main-conversation requests of `-p` sessions, so they get the 1-hour default only on a subscription; on an API key or credits they get 5 minutes** (confidence: medium)
   Derived from F2: a worker is `claude -p` (main bucket). Measured: all 1,523 `sdk-cli` transcripts on this machine wrote 100% 1-hour (subscription). A scheduled run under CI (`github-workflow.yml`, rendered by `compass loop schedule --github`) bills by API key by construction, where the default is 5 minutes; that case is not measured here.
   - https://code.claude.com/docs/en/prompt-caching ("Which TTL each request gets"); `plugin/cli/loop_templates/github-workflow.yml:1-8`
   - Marks: derived from doc plus measurement; converges
   - Grade: medium

18. **Build waves: pre-build tester wave, then one builder per task in parallel worktrees, a tester per builder, fix loop by SendMessage to the same builder** (confidence: high)
   Parallel builders are separate Agent tool calls with `isolation: "worktree"`, not a workflow fan-out (`plugin/skills/build/SKILL.md:36-39`); the tester pre-build station is "a wave of its own" before builders spawn (`:36`); fixes go to the same builder's worktree (`:42`). The 5-second hold applies to workflow fan-outs only (F7), so concurrent Agent-tool builders each write their own cache (the entry exists only after a first response starts, F6). A SendMessage fix is a resumed subagent, which may read the cache the original run warmed if still within the TTL (F7).
   - Marks: local code read; docs converge
   - Grade: high

19. **Measured per type: builders run a median 17 minutes (82% longer than 5 minutes, 11% longer than 1 hour), testers 7 minutes (65%, 5%), researchers 8 minutes (79%, 2%), planners 15 minutes (93%, 4%)** (confidence: medium)
   All five Compass types write 100% 5-minute cache (1h share 0.0). Whole-agent hit rate: builder 93.6%, tester 91.7%, researcher 91.6%, planner 93.7%. First-request hit: builder 54%, tester 69%, researcher 65%, reviewer 13%, planner 6%, debug 13%; validator n=7 only. Validator, reviewer, debug counts are small (7, 76, 15).
   - Local transcripts, `wt_types.py`
   - Marks: measured, one machine
   - Grade: medium

20. **Measured: first-request hits of same-type agents started within 5 minutes of a sibling are 95% (n=196) for worktree-spawned and 87% (n=1,376) for others** (confidence: medium)
   Worktree agents run in different directories, and the docs say the cache scopes to directory (F8, workflow page names working directory as part of the matching prefix). The data shows worktree siblings do hit; what they hit is the shared agent prefix, a small part of the input (read share of first-request input 14% worktree, 18% others), so the doc's directory scope and the 95% hit rate agree only if the shared block sits before the directory-dependent text. Which block is shared is not decomposed here.
   - Local transcripts, `wt_types.py`; https://code.claude.com/docs/en/workflows ("Prompt caching in a fan-out")
   - Marks: measured plus vendor doc; the two partially disagree (see Contradictions)
   - Grade: medium

### D. Human gate waits

21. **A review or gate wait under 5 minutes costs nothing on the main session; 5 to 60 minutes also costs nothing today because main sessions use 1 hour; over 1 hour costs a full rewrite** (confidence: high)
   Interactive (`cli`) sessions: after 5-60 minute gaps (n=3,627) the next request reads 88% of its input and writes a median 1.4k tokens. After gaps over 1 hour (n=986) it reads 3.7% and writes a median 159k tokens. All main sessions, over-1-hour gaps are 1,048 of 113,996 (0.9%) yet carry 10.0% of modeled main cost (252M write tokens at 2x); for interactive sessions the rewrite excess over a warm read is 11.9% of modeled interactive cost. The 1-hour tier is what makes 5-60 minute review waits free; on 5-minute billing the 4,495 main gaps of 5-60 minutes (10.7% of cost share) would also rewrite, with the 0.1x read replaced by 1.25x write.
   - Local transcripts, `gate_wait.py` and `wt_types.py`; price from F3
   - Marks: measured, one machine, one billing mode
   - Grade: medium-high (measured on the host's own telemetry; gate waits are indistinguishable from other idle time, so the gap is a proxy)

22. **Gate waits are the main-session case and subagents are the other: subagent requests after a >5-minute gap read only 16.5% of their input versus 88.5% for main after 5-60 minutes** (confidence: high)
   The two differ by TTL: 5-minute subagent entries expire during the long tool runs of a build, where main's 1-hour entries survive. 1,423 subagent requests follow >5-minute gaps and carry 24% of subagent write tokens (F12).
   - Local transcripts, `gate_wait.py`
   - Marks: measured
   - Grade: high

### E. Reconciliation with axis 1

23. **"99% of cache writes are 1-hour" (axis 1) covers main sessions only; subagent writes are 0% 1-hour (this axis); both are measured** (confidence: high)
   [[RESEARCH-cache-hit-baseline]] finding 10 counts `usage.cache_creation` over main-session transcripts (this repo 0.77M 5m vs 46.7M 1h; other Compass projects 6.2M vs 782.6M; non-Compass 0 vs 206.7M). This axis reads the same fields over 1,784 main transcripts (99.3% 1h, 929.7M write tokens, all vault and non-vault projects together, scratch trial directories excluded) and separately over 4,445 subagent transcripts (0% 1h, 868.2M write tokens). The two agree on the main tier; the subagent figure was not in axis 1's set. Subagent write tokens are 48% of all measured cache-write tokens, so a statement about "writes" without a bucket misleads. Hit-rate figures differ slightly by set (axis 1 96.4-98.7% main; 97.3% here, all projects pooled).
   - [[RESEARCH-cache-hit-baseline]] findings 1 and 10; local transcripts
   - Marks: measured, two scripts, same host data; converges
   - Grade: high

## Candidate changes for Compass

Ranked by measured impact. None is recommended; each is an option for the planner with the number that bears on it.

1. **Set `experimental: cacheTtl: 1h` on the long-running agent types (builder first)** - north stars: low token usage, near-zero cache misses. Touches `plugin/templates/agents/builder.md` (and tester, researcher, planner as the planner chooses). Evidence: builders run a median 17 minutes and 82% exceed 5 minutes (F19); subagent requests after a >5-minute gap read 16.5% against 88.5% when the entry lasts (F22); the 1h write costs 2x against 1.25x (F3), break-even needs a 5-60 minute reuse in about 65% of prefixes (F4). Counter-evidence: the modeled all-1h switch raises subagent cost 15% on measured traffic because only 1.3% of in-agent gaps exceed 5 minutes (F13). The case rests on cross-agent reuse 5-60 minutes apart (42% first-request hit today, F9) which the model leaves out. Already covered: no (B7, F14). Unresolved cost: needs an A/B on builder waves.
2. **Set `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL` or `subagentPromptCacheTtl` for the whole project instead of per agent** - touches the settings file Compass installs (no such entry today, F14). Same evidence and same trade-off as 1; it covers every type including ad hoc ones and the spawn by workflows, with the cost that short helpers (locators, 7-minute testers) also pay 2x. Already covered: no.
3. **Set `promptCacheTtl: 1h` or `CLAUDE_CODE_PROMPT_CACHE_TTL=1h` in the looprunner worker env (and in the scheduled-run workflow template) for API-key billing** - touches `plugin/cli/looprunner.py:759-761` and `plugin/cli/loop_templates/github-workflow.yml`. Evidence: workers are `-p` main requests that default to 5 minutes on API key (F17), but daily runs (F16) expire both TTLs, so only the judge's back-to-back sessions and a worker's own long turns could gain; judge cross-session reads are unmeasured. Already covered: no. Likely low value at the default cron; relevant only if a loop is scheduled at intervals under an hour.
4. **Run the judge's repeated sessions inside the TTL of the first and keep their prompt and tool set byte-identical** - touches `looprunner.py:773-774`. The judge already sends the same prompt to each session; a hit needs the first response to have begun and the entry to be alive (F6). Needs a measurement of judge sessions' first-request reads before any change. Already covered: unknown.
5. **Stage build-wave builders so the first writes before the rest start, or fan out through a workflow (5-second hold)** - touches `plugin/skills/build/SKILL.md:39`. Evidence: concurrent Agent-tool builders write separately (F18, F6), yet measured parallel-start hits are already 82% (F9, F20), so the headroom is the small shared prefix (14-19% of first-request input), not the whole input. Low expected gain; listed because the host offers the mechanism.
6. **Shorten or avoid human-gate waits over 1 hour on the main session, or accept a `/compact` before a long break** - touches the review gate flow (the pipeline rule's review step). Evidence: over-1-hour gaps are 0.9% of main gaps and 10% of modeled main cost; a long wait rewrites a median 159k tokens (F21). The host already can compact an idle 1-hour-TTL conversation (`idleCompaction`, doc, setting not read in detail). Whether Compass should do anything here is a planner question; its cost is bounded by how often gates exceed an hour.
7. **Add the TTL split and per-type first-request hit rate to Compass's measurement** - north star: accuracy of the cache baseline. Today no tool reads `usage.cache_creation` TTL fields (also axis 1). The scripts in this pass (`ttl_measure.py`, `wt_types.py`, `gate_wait.py`, session scratchpad) are a starting point.

## Contradictions
- F20 vs the docs' directory scope (F8): worktree-spawned siblings in different directories hit the cache on 95% of first requests, although the docs say the cache scopes to one directory. Resolved only partially: the shared block can be a prefix that precedes the directory text; not decomposed here.
- F13 (modeled 1h raises subagent cost 15%) vs candidate 1 (1h helps builders): the model counts in-agent gaps only; builders' long-run reuse across agents is outside it.
- B7 said subagents "default to 5 minutes"; the measured 0% 1h agrees. B7 said the effect on builder waves was inferred; F9, F20, F22 now measure the first-request hit and the post-gap read, while the wave-level dollar effect stays modeled.

## Gaps
- Looprunner worker sessions are not separate transcripts here (see [[RESEARCH-cache-hit-baseline]]); their TTL tier on API-key billing and the judge's repeated-session hit rate are unmeasured. Closing it: read `usage.cache_creation` in a run's saved `claude -p --output-format json` stdout (`judge-N-stdout.json` in the run scratch) or run two judge sessions in an API-key environment.
- All measurement is one machine on a subscription; API-key and cloud-provider billing (5-minute main default) is covered by documentation only.
- A cause for the 95% worktree-sibling hit (which prefix block is shared) is not decomposed; axis 2 decomposes session prefixes, not subagent prefixes.
- Gap timing uses response-record timestamps, not request start; the provider counts the TTL from request start (F3), so 5-minute gap shares near the threshold are approximate.
- Hit counts for the 5-minute subagent entries across waves rely on grouping by project and agent type; two unrelated runs in one project can read each other's cache and are counted as siblings.
- Workflows documentation for the per-agent frontmatter order and the `idleCompaction` setting were not read in full; the API prompt-caching page was read to character 100,000 of 155,517.
- The cost counterfactual (F13) models only in-agent gaps; a model with cross-agent reuse needs the wave start times per task, not tested.
