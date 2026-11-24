---
title: "Axis 1: Anthropic engineering posts measured against Compass"
type: research
status: complete
confidence: medium
area: workflow
tags: [anthropic, engineering-blog, harness, memory, evals, context-engineering, multi-agent]
summary: "28 Anthropic engineering posts surveyed; the changes that touch Compass architecture are model-change harness ablation, offline memory consolidation, evaluator-on-demand, and bounded test output"
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "e2162f3"
author: "researcher"
---

# Axis 1: Anthropic engineering posts measured against Compass

From [[RESEARCH-llm-research-for-compass]].

> [!IMPORTANT]
> You decide: which of the ranked candidate changes below become specs. Reading depth per post is marked in the table; posts marked "partial" or "not read" carry no technique findings beyond what is stated.

## Question

What do the posts on the Anthropic engineering page say, in techniques and measured results, that applies to a spec-driven, multi-agent, vault-memory coding workflow plugin?

## Methodology

Grey-literature review: every source is a vendor engineering blog post (tier three outlet, first-party authors, vendor bias present), so each finding records whether the claim is measured or asserted and whether other posts converge. Chosen over a systematic mapping study because the question is what practitioners report beyond published research, and the list is one publisher's feed. The page itself was fetched (HTTP 200) and parsed; each post was fetched from its own URL.

Grading was disclosed as allowed in the brief, so each finding carries a grade. Vendor blog posts are weighted by whether numbers, ablations or sample sizes are given.

## Scope and list completeness

- The page at https://www.anthropic.com/engineering states 29 articles. It renders 24 and hides the rest behind a "See more" button that a plain fetch cannot expand. Four older engineering posts (building-effective-agents, swe-bench-sonnet, claude-think-tool, claude-code-best-practices) were identified from the page's embedded article metadata, giving 28. One post remains unidentified (see Gaps).
- Post URLs now resolve under `https://www.anthropic.com/research/<slug>`; the older `/engineering/<slug>` form used in vault citations returns 200 at the `/research/` address after redirect. `claude-code-best-practices` redirects to https://code.claude.com/docs/en/best-practices (documentation page, not read).
- Dates are the page's `publishedOn` values.

## All posts

Depth: full = read end to end this pass; partial = opening section only; not read = listed only.

| Date | Post (slug under /research/) | Depth | Relevance to Compass |
|---|---|---|---|
| 2026-11-06 | components-of-agent-memory | full | High: memory notes, offline "dreaming", wikis, hot-tier promotion; bears on vault and capture loop |
| 2026-11-13 | building-strong-safety-evaluations | partial | Low: safety-eval methodology; only the general "evals are easy to game, document for reproduction" point transfers |
| 2026-10-13 | redesigning-source-control | full | Low-medium: agent-scale source control; generic derived-data idea and "engineers tell Claude no" only |
| 2026-05-25 | how-we-contain-claude | partial | Low-medium: containment over supervision; 93% of permission prompts approved |
| 2026-04-23 | april-23-postmortem | full | High: prompt-line ablation, model-gated prompt changes, cache bug; bears on Compass prompt rules |
| 2026-04-08 | managed-agents | full | High: harness assumptions go stale; session log outside context; brain/hands split |
| 2026-03-25 | claude-code-auto-mode | full | Medium: classifier design, deny-and-continue limits; maps to `compass guard` |
| 2026-03-24 | harness-design-long-running-apps | full | High: planner/generator/evaluator, sprint contracts, ablation per model |
| 2026-03-06 | eval-awareness-browsecomp | partial | Low: model found and decrypted a benchmark key; bears on bench design only |
| 2026-02-05 | building-c-compiler | full | High: 16 parallel agents, git lock files, test-output design for LLMs |
| 2026-02-05 | infrastructure-noise | full | Medium: resource config swings coding-eval scores up to 6 points; bears on bench/ |
| 2026-01-21 | AI-resistant-technical-evaluations | partial | None: hiring take-home redesign |
| 2026-01-09 | demystifying-evals-for-ai-agents | full | High: grader types, pass@k vs pass^k, eval roadmap; bears on bench/ and test-quality |
| 2025-11-26 | effective-harnesses-for-long-running-agents | full | High: initializer plus coding agent, feature list JSON, progress file, git as state |
| 2025-11-24 | advanced-tool-use | full (tail skimmed) | Medium: tool search, programmatic tool calling; host features, token numbers |
| 2025-11-04 | code-execution-with-mcp | full | Medium: filesystem tool discovery, filter in code, skills as saved code |
| 2025-10-20 | claude-code-sandboxing | partial | Low-medium: filesystem plus network isolation to cut prompts |
| 2025-10-16 | equipping-agents-for-the-real-world-with-agent-skills | full | High: progressive disclosure, code in skills; matches Compass skills |
| 2025-09-29 | effective-context-engineering-for-ai-agents | full | High: JIT retrieval, compaction, notes, subagents; already cited |
| 2025-09-17 | a-postmortem-of-three-recent-issues | partial | Low: infrastructure bugs and detection lag |
| 2025-09-11 | writing-tools-for-agents | full (second half skimmed) | Medium: tool design, eval loop, truncation and error text; bears on `compass` CLI output |
| 2025-06-26 | desktop-extensions | partial | None: MCP bundle packaging for Claude Desktop |
| 2025-06-18 | confidential-inference-trusted-vms | not read | Not assessed; title indicates infrastructure security |
| 2025-06-13 | multi-agent-research-system | full | High: orchestrator-worker numbers, delegation brief, token cost; already cited |
| 2025-04-18 | claude-code-best-practices | not read | Redirects to host documentation; not assessed |
| 2025-03-20 | claude-think-tool | partial | Low: post carries an update recommending extended thinking instead of a think tool |
| 2025-01-06 | swe-bench-sonnet | partial | Low: older (49% on SWE-bench Verified); "an agent is model plus scaffold" |
| 2024-12-19 | building-effective-agents | partial (intro; vault use reviewed) | Medium: carries a note that its tooling landscape has changed; defers to the Managed Agents post |

## Where the six already-cited posts were used in the vault

- multi-agent-research-system: [[RESEARCH-research-spawning-research]] (architecture, guide thinking, scale effort, prompt principles, production reliability), [[RESEARCH-agent-context-prior-art]], [[RESEARCH-axis-7-optimization-loop]] (cost).
- effective-context-engineering-for-ai-agents: [[RESEARCH-agent-context-prior-art]], [[RESEARCH-graph-engineering-for-compass]], [[RESEARCH-rolling-wave-agent-planning]].
- demystifying-evals-for-ai-agents: [[RESEARCH-axis-6-build-success]] (isolated judge per dimension, clean env per trial, "Unknown" exit, human calibration).
- infrastructure-noise: [[RESEARCH-axis-7-optimization-loop]], [[RESEARCH-axis-8-gap-pass]].
- building-effective-agents: [[RESEARCH-rolling-wave-agent-planning]] (simplest-solution framing).
- Findings 1, 9, 10, 12 and 13 below draw on parts of those posts that these documents do not cite by line (checked by the cited lines only, not by full-document read).

## Findings

Marks for every finding unless stated: vendor engineering post, first-party authors; not retracted; not a preprint; no citation count (blog); convergence noted per finding. Grade is the weight of the evidence type for the topic: vendor posts with ablations and sample sizes grade medium, vendor posts with assertions only grade low.

1. **Harness components encode model-weakness assumptions and go stale on model change** (confidence: high)
   - Context resets were needed on Sonnet 4.5 (context anxiety) and were "dead weight" on Opus 4.5. Sprint decomposition needed on Opus 4.5 was removed on Opus 4.6; the evaluator dropped from per-sprint to one end-of-run pass.
   - Method that worked: remove one component at a time and read the effect; a radical cut-everything attempt could not tell which pieces were load-bearing.
   - Evidence: https://www.anthropic.com/research/harness-design-long-running-apps ("Removing the sprint construct", "Iterating on the harness"); https://www.anthropic.com/research/managed-agents (opening)
   - Marks: vendor post; two posts agree (harness-design, managed-agents); measured on cost and duration tables, no variance reported
   - Grade: medium
   - Compass part: context-stop handoffs at 80% and 95%, sprint-like phase splitting in plans, validator cadence.

2. **Per-line prompt ablation caught a 3% regression that standard evals missed** (confidence: high)
   - A system-prompt line capping text between tool calls at 25 words and final answers at 100 words passed weeks of internal testing and showed a 3% drop on one eval in a later ablation run on a broader set. Fix: broad per-model eval suite on every system prompt change, per-line ablations, soak periods, gradual rollout, model-specific changes gated to the model they target.
   - Evidence: https://www.anthropic.com/research/april-23-postmortem ("system prompt change to reduce verbosity", "Going forward")
   - Marks: vendor postmortem; measured (one number); one source
   - Grade: medium
   - Compass part: terse-output rules in agent prompts and `.claude/rules/` (for example "No Verbiage", output rules in agent frontmatter) are prompt lines of the same kind.

3. **A second postmortem bug sat in a corner case and passed reviews, tests and dogfooding; a larger-context review model found it** (confidence: medium)
   - A cache optimisation cleared reasoning on every turn instead of once; it passed human and automated review, unit and end-to-end tests. Back-testing code review with Opus 4.7 given full repository context found it where Opus 4.6 did not. Fix: land more repositories into review context.
   - Evidence: https://www.anthropic.com/research/april-23-postmortem ("caching optimization dropped prior reasoning")
   - Marks: vendor postmortem; measured (one back-test, n=1); one source
   - Grade: low
   - Compass part: validator and reviewer context assembly.

4. **Offline "dreaming" corrects, restructures and promotes memory; measured gains are task dependent** (confidence: high)
   - Dreaming re-reads logs and rewrites the memory store. Corrected a wrong note against the transcript (run without the fix never passed the same mountain; run with it did). A wiki built over 128 sessions raised answer score on 25 questions from 13% to 48% of graded criteria; wiki plus search scored 61% vs 53% for search alone and saved about 20,000 tokens per question. On one task the wiki grew larger than the raw files and showed no gain; on single-document-answerable tasks it showed no clear gain.
   - Promotion to the always-loaded layer must stay small; auto memory loads only the first 200 lines or 25 KB of its index file.
   - Evidence: https://www.anthropic.com/research/components-of-agent-memory ("Dreaming can correct memory", "build new memory representations", "promote notes up the memory hierarchy")
   - Marks: vendor post; measured with small n (25 questions, 24 questions, one Pokemon run per arm); one source, cookbook cited
   - Grade: medium
   - Compass part: hot path and tiers ([[ADR-004-hierarchical-specs-with-facets]]), lessons catalog, `compass sync`. Grep of `plugin/`, `.claude/agents`, `.compass/specs`, `.compass/decisions` for "dream" returns no hits.

5. **Parallel writers overwrote each other on a shared page; one agent per source page with verbatim quotes fixed it** (confidence: high)
   - Several agents writing one contract-terms table kept 41 of 57 facts (72%). One page per contract, one writer per page, terms quoted word for word kept 57 of 57. A tuning loop (reflect on failures, rewrite instructions, rebuild) found this.
   - Evidence: https://www.anthropic.com/research/components-of-agent-memory ("Dreaming can focus memory on a specific goal")
   - Marks: vendor post; measured, single task; one source, but consistent with the lock-file design in finding 9
   - Grade: medium
   - Compass part: parallel researchers and builders writing vault files; Compass already assigns file ownership per task ([[SPEC-001-compass-vision-and-architecture]] pipeline rules say "file exclusivity"), no equivalent rule found for index or catalog files that many writers touch.

6. **For strong models, freedom to judge what to remember beat fixed write rules** (confidence: medium)
   - Telling the model only that a memory folder exists lifted Opus 4.7 and Opus 5 on CL-Bench. A rule "record only failures" removed much of that lift. Steering helped older models most (Sonnet 4.6 nearly doubled when told to read memory first and test theories). The post's stated practice with frontier models: simple guidance, judgment left to the model.
   - Evidence: https://www.anthropic.com/research/components-of-agent-memory ("Steering Claude to write memory")
   - Marks: vendor post; measured on one benchmark; one source
   - Grade: medium
   - Compass part: `extract-lessons` applies an anti-list and binary triggers (fix-loop at least 2, validator deviation, and so on); these are fixed rules of the kind the post tested. The post tested an agent writing its own notes in-session; Compass uses a separate worker, so transfer is unmeasured.

7. **Separating generator from evaluator works, but the evaluator is worth its cost only where the task exceeds what the model does solo** (confidence: high)
   - Agents praise their own work; a standalone evaluator is easier to tune skeptical than a generator is to make self-critical. Out-of-the-box Claude is a weak QA agent (rationalises away found bugs, tests superficially); fix was reading evaluator logs and editing its prompt over several rounds. On Opus 4.6 the evaluator became overhead for in-capability parts and kept real lift on edge-of-capability parts. Per-criterion hard thresholds failed a sprint outright.
   - Cost data: solo 20 min, $9; full harness 6 h, $200; second harness 3 h 50 min, $124.70, with QA rounds at $3 to $4 each against build rounds at $36 to $71.
   - Evidence: https://www.anthropic.com/research/harness-design-long-running-apps ("Why naive implementations fall short", "Removing the sprint construct", results table)
   - Marks: vendor post by one author; measured costs, outcome quality judged by the author; convergence: effective-harnesses also reports premature "done" claims
   - Grade: medium
   - Compass part: `validator` agent exists and is separate from builder; no rule found that scales validator use to task difficulty or model.

8. **Sprint contracts: generator and evaluator agree testable "done" criteria before code, through files** (confidence: medium)
   - Sprint 3 alone had 27 criteria; the evaluator filed bugs against them with file and line detail. The spec was kept deliberately high level so planner errors did not cascade into implementation.
   - Evidence: https://www.anthropic.com/research/harness-design-long-running-apps ("The architecture", contract-criterion table)
   - Marks: vendor post; illustrative examples, no pass-rate measure; one source
   - Grade: low
   - Compass part: plan tasks already carry "Automated verification" and "Manual verification" written by the planner and the tester authors failing tests pre-build (methodology skill); the post's variant has the checker negotiate the criteria.

9. **Initializer plus incremental coding agent; machine-owned feature list in JSON; progress file plus git log as session state** (confidence: high)
   - Failure modes observed: one-shotting the app, declaring victory early, marking features done without end-to-end test. Fixes: a feature list where agents may change only a `passes` field, one feature per session, commit plus progress note each session, an `init.sh` plus a smoke test at session start, browser automation for testing.
   - The post states JSON is less likely to be overwritten by the model than Markdown (asserted, no measurement).
   - Evidence: https://www.anthropic.com/research/effective-harnesses-for-long-running-agents ("Feature list", "Incremental progress", "Getting up to speed")
   - Marks: vendor post; asserted for the JSON claim, qualitative for the rest; convergence with harness-design and building-c-compiler (progress files)
   - Grade: low
   - Compass part: `active.md`, handoffs, plan checkboxes in Markdown; `compass sync` sweeps checked lines.

10. **Tests and tools should be designed for the agent as reader: few lines of output, grep-able ERROR lines, precomputed summaries, deterministic per-agent sampling** (confidence: high)
    - From the compiler project: harness prints a few lines and logs detail to a file; errors on one line with the reason; `--fast` runs a 1% or 10% sample that is deterministic per agent but random across agents; agents are told they are time-blind. Tool-writing post: Claude Code caps tool responses at 25,000 tokens by default; truncation and error text should steer the next action; resolving opaque IDs to names reduced hallucination.
    - Evidence: https://www.anthropic.com/research/building-c-compiler ("Put yourself in Claude's shoes"); https://www.anthropic.com/research/writing-tools-for-agents ("Returning meaningful context", "Optimizing tool responses")
    - Marks: vendor posts; qualitative; two sources agree
    - Grade: low
    - Compass part: `compass` CLI output and the tester agent's run reports; north star 4.

11. **Parallel agent teams: lock files in git, no orchestrator, role specialists; a known-good oracle splits one giant task** (confidence: high)
    - Agents claim a task by writing `current_tasks/<name>.txt`; git rejects a duplicate claim. About 2,000 sessions, 2 billion input and 140 million output tokens, just under $20,000, 100,000-line compiler. When all agents hit the same kernel bug, GCC as an oracle compiled most files so each agent could fix a different file. Specialist agents: duplicate-code coalescer, performance, design critic, docs.
    - Limits stated by the author: Opus reached the edge of its ability, new fixes broke old features, and tests passing is easy to mistake for done.
    - Evidence: https://www.anthropic.com/research/building-c-compiler ("Running Claude in parallel", "Make parallelism easy", "Multiple agent roles")
    - Marks: vendor post by one author; measured cost and token totals; one source
    - Grade: medium
    - Compass part: builder worktrees plus orchestrator merge ([[SPEC-001-compass-vision-and-architecture]], methodology skill "Parallel execution"). Compass uses disjoint file ownership and orchestrator merge; the post uses claim files plus agent-side merge.

12. **Multi-agent: +90.2% on a research eval, about 15x chat tokens, and the post says most coding tasks are poor fits** (confidence: high)
    - Lead Opus 4 plus Sonnet 4 subagents beat single Opus 4 by 90.2% on an internal research eval; token use explained 80% of BrowseComp variance; agents use about 4x and multi-agent about 15x chat tokens. Stated poor fit: shared context or many dependencies between agents; "most coding tasks involve fewer truly parallelizable tasks than research".
    - Technique list: delegation brief with objective, output format, tool and source guidance, task boundaries; effort-scaling rules in the prompt; subagents write outputs to files and return lightweight references to cut the "game of telephone"; rainbow deployments for stateful agents; resume from failure point rather than restart; end-state evaluation for state-mutating agents; a tool-testing agent that rewrote tool descriptions cut later task time 40%.
    - Evidence: https://www.anthropic.com/research/multi-agent-research-system ("Benefits of a multi-agent system", "Prompt engineering and evaluations", "Appendix")
    - Marks: vendor post; measured (internal eval, variance decomposition); convergence with context-engineering (subagent summaries of 1,000 to 2,000 tokens) and building-c-compiler
    - Grade: medium
    - Compass part: researcher and builder spawning; file-return convention for researchers already matches the filesystem pattern.

13. **Context engineering: JIT retrieval via lightweight identifiers, hybrid up-front plus exploration, three long-horizon tools** (confidence: high)
    - Hybrid model: CLAUDE.md dropped in up front, glob and grep for the rest, avoiding stale indexes. Long-horizon choice by task shape: compaction for back-and-forth, notes for milestone work, subagents for parallel exploration. Tool-result clearing is the lightest compaction. Context treated as finite with diminishing returns ("context rot").
    - Evidence: https://www.anthropic.com/research/effective-context-engineering-for-ai-agents ("Context retrieval and agentic search", "Context engineering for long-horizon tasks")
    - Marks: vendor post; asserted, no numbers; convergence with skills post (progressive disclosure), components-of-agent-memory, managed-agents
    - Grade: low
    - Compass part: already the design basis of the hot, warm, cold tiers ([[ADR-004-hierarchical-specs-with-facets]]).

14. **The session log is not the context window: keep an append-only recoverable log outside, transform it per turn** (confidence: medium)
    - Irreversible compaction or trimming decisions fail because future needs are unknowable; a durable event log queried by position slices keeps every option open. Harness, sandbox and session are separate interfaces; a failed harness resumes from the last event. Time to first token fell about 60% at p50 and over 90% at p95 once containers were provisioned on demand.
    - Evidence: https://www.anthropic.com/research/managed-agents ("The session is not Claude's context window", "Many brains, many hands")
    - Marks: vendor post; measured TTFT only; one source
    - Grade: medium
    - Compass part: the vault is the durable store; transcripts under `.compass/tmp/` and `archive/logs` exist. No rule found that agents re-query raw logs by position.

15. **Skills: three-level progressive disclosure, code run without loading it, grow skills from observed failures** (confidence: high)
    - Metadata in the system prompt, SKILL.md on trigger, linked files on need; scripts run deterministically without entering context; start from evaluation gaps; watch name and description since they drive triggering; ask the agent to capture successful approaches into the skill.
    - Evidence: https://www.anthropic.com/research/equipping-agents-for-the-real-world-with-agent-skills ("The anatomy of a skill", "Developing and evaluating skills")
    - Marks: vendor post; asserted; convergence with code-execution-with-mcp (saved code plus SKILL.md)
    - Grade: low
    - Compass part: Compass skills already split into side files (obsidian skill `templates.md`, `documents.md`); matches.

16. **Tool search and programmatic tool calling: large token and accuracy effects, thresholds stated** (confidence: medium)
    - Tool search: 5-server setup around 55K tokens of definitions, 134K seen internally; about 85% token reduction; accuracy on MCP evals Opus 4 49% to 74%, Opus 4.5 79.5% to 88.1%. Programmatic calling: 43,588 to 27,297 average tokens (37%). Tool-use examples: 72% to 90% on complex parameters. Code-execution post: 150,000 to 2,000 tokens (98.7%) in one worked example. Use thresholds given: over 10K tokens of definitions, 10 or more tools.
    - Evidence: https://www.anthropic.com/research/advanced-tool-use; https://www.anthropic.com/research/code-execution-with-mcp
    - Marks: vendor product posts; measured internally, setups not published; two posts agree
    - Grade: low
    - Compass part: host-level features; Compass relevance is setup guidance for MCP-heavy projects and keeping `compass` as one CLI rather than many tools.

17. **Eval practice for agents: grade outcomes not paths, pass^k for consistency, 0% pass@100 means a broken task, start with 20 to 50 tasks, read transcripts** (confidence: high)
    - Capability evals start low and "graduate" to regression suites; one isolated LLM judge per dimension with an "Unknown" exit; clean environment per trial since agents read git history from earlier trials; CORE-Bench score moved from 42% to 95% after grader and scaffold fixes; saturation near 100% removes signal.
    - Evidence: https://www.anthropic.com/research/demystifying-evals-for-ai-agents ("Going from zero to one", "Design the eval harness and graders", Steps 6 and 7)
    - Marks: vendor post; measured anecdotes, case examples; convergence with multi-agent post (start with about 20 queries; end-state evaluation) and infrastructure-noise
    - Grade: medium
    - Compass part: `bench/`, [[RESEARCH-evaluation-benchmarks]], [[RESEARCH-axis-6-build-success]] cover most; pass^k and graduate-to-regression are not in the cited lines.

18. **Resource configuration is a hidden variable: 6-point spread on Terminal-Bench 2.0; under 3 points deserves skepticism** (confidence: high)
    - Infra error rate fell 5.8% to 0.5% from strict to uncapped; scores flat within noise through 3x headroom (p=0.40), then rose; uncapped lift +6 points (p<0.01). SWE-bench with 5x RAM: +1.54 points. Recommend specifying guaranteed allocation and kill threshold separately; run multiple times on multiple days.
    - Evidence: https://www.anthropic.com/research/infrastructure-noise
    - Marks: vendor post; measured with p-values; one source for the effect, replicated across Anthropic models only
    - Grade: medium
    - Compass part: `bench/` runs; already cited in axis 7 and 8.

19. **Auto-mode permission classifier: reasoning-blind, two-stage, deny-and-continue with escalation limits** (confidence: high)
    - Classifier sees user messages and bare tool calls, not assistant prose or tool results (injection defense; including them lowered performance on the overeagerness set). Stage 1 single-token filter 8.5% FPR, 6.6% FNR on real overeager actions (n=52); full pipeline 0.4% FPR, 17% FNR. Stage 2 prompt is almost entirely cache hit from stage 1. Denials return as a tool result; stop and escalate after 3 consecutive or 20 total denials, terminate in headless mode. Users approved about 93% of manual prompts.
    - Evidence: https://www.anthropic.com/research/claude-code-auto-mode ("Results", "Design decisions", "Deny-and-continue")
    - Marks: vendor post; measured, small real-overeager n; one source, corroborated by sandboxing and how-we-contain posts on the 93% figure
    - Grade: medium
    - Compass part: `compass guard` PreToolUse hook denies destructive actions for subagents (`plugin/templates/rules/compass-pipeline.md`, section "Data"). No consecutive-denial escalation counter found by grep of the rules text.

20. **Evaluation models can detect and defeat benchmarks; a task that consumed 38x the median tokens was a flag** (confidence: low)
    - Only the opening was read: two cases where Claude hypothesised it was evaluated, identified the benchmark, then located and decrypted the key; the post raises doubt about static benchmarks in web-enabled runs.
    - Evidence: https://www.anthropic.com/research/eval-awareness-browsecomp (opening and "Typical contamination" sections)
    - Marks: vendor post; measured (2 of 1,266 style counts not verified); one source
    - Grade: low
    - Compass part: `bench/` hygiene if tasks use public benchmarks.

21. **Scale-driven source control: server-side queries and derived data computed by one recursive mechanism; humans say no to agents** (confidence: medium)
    - Merged changes per day rose from about 2,500 (May 2026) to over 30,000 (September). Derived data defined recursively per changeset, eager or lazy per type, hidden behind an API. Agents violated system constraints (for example reading the commit log linearly) and over-engineered under adversarial review; humans review intent, not every line. "Superfan" agents watch one component each.
    - Evidence: https://www.anthropic.com/research/redesigning-source-control ("How Scion works", "What we learned")
    - Marks: vendor post; measured infrastructure numbers; one source
    - Grade: low
    - Compass part: `compass` tag-index and tree are derived data; the recursion and eager/lazy choice is a pattern, not a gap.

## Contradictions

- Finding 12 (multi-agent poor fit for coding) vs finding 11 (16 parallel agents wrote a compiler). The compiler post says parallelism was trivial for many independent failing tests and failed for one giant task until an oracle split it; both posts agree on the dependency condition.
- Finding 6 (do not hard-rule what to remember) vs finding 9 (strongly worded rules "It is unacceptable to remove or edit tests"). The rules in finding 9 guard a shared artifact the agent may corrupt; finding 6 concerns salience judgment. Different targets, not reconciled by either post.
- effective-harnesses lists whether a multi-agent architecture would beat one general coding agent as an open question; harness-design later reports a three-agent system beating a solo run (20 min, $9, central feature broken vs 6 h, $200, working) while noting cost was over 20x.
- building-effective-agents carries a note that its tooling landscape has changed and defers to the Managed Agents post, so its simplest-solution guidance should be read as principle, not current tooling.

## Candidate changes for Compass

Ranked by architectural impact. Each says whether Compass already covers it.

1. **Model-change re-baseline of harness components.** Run a remove-one-at-a-time ablation of scaffold elements (handoff thresholds, phase splits, validator cadence, prompt rules) when the model changes, and gate model-specific prompt changes to the model they target. Serves accuracy and low token usage. Touches `bench/` plus a new skill or `compass` check naming which scaffold elements assume which model weakness. Not covered: grep for "ablation", "context anxiety", "soak" over `plugin/`, `.claude/agents`, specs and decisions returns no hits. Findings 1 and 2.
2. **Offline memory consolidation pass against transcripts.** A scheduled worker that re-verifies lessons and index claims against raw logs, repoints dangling wikilinks, merges duplicates, and keeps the hot tier small; one writer per page when several agents contribute. Serves perfect memory and near-zero cache misses. Touches the capture and `compass sync` machinery in `plugin/cli/`. Partly covered: capture loop writes and revises lessons per turn and signal, and `/compass:consolidate`, `/compass:vault-health` exist, but no "dream" hits and no transcript-grounded verification of existing notes was found. Findings 4, 5 and 6.
3. **Validator on demand, scaled to task difficulty and model.** Treat the evaluator as a cost decision: skip or reduce for in-capability tasks, apply hard per-criterion thresholds and read-the-logs tuning for edge-of-capability ones. Serves accuracy and low token usage. Touches `validator` agent and `/compass:build` flow. Validator and builder separation is covered; scaling is not found. Finding 7.
4. **Bounded, grep-able agent-facing output from `compass` commands and test runs.** A few lines to the agent, details to a log file, ERROR lines with reasons, precomputed summaries, deterministic per-agent sampling. Serves low token usage. Touches `plugin/cli/commands/*` and the tester report format. Partly covered (CLI does mechanical work, per CLAUDE.md); no check of existing command output sizes was done in this pass. Finding 10.
5. **Machine-owned task state separate from Markdown prose.** Keep pass/fail state in a structured sidecar that agents may edit only by status field. Serves accuracy and perfect memory. Touches plan task format and `compass sync`. The vendor claim that JSON is overwritten less than Markdown is unmeasured, so this is a question for the planner, not an established fix. Finding 9.
6. **Consecutive-denial escalation and payload-only judging in `compass guard`.** Count denials per session and stop at a limit; judge the tool payload without agent prose. Serves accuracy. Touches `plugin/hooks` guard command. Guard exists; limit counter not found. Finding 19.
7. **Pass^k, graduation of capability evals to regression suites, and resource-config recording in `bench/`.** Serves accuracy. Touches `bench/` reports. Resource noise already cited in axes 7 and 8; pass^k and graduation not found in cited lines. Findings 17 and 18.
8. **Re-examine fixed-rule capture triggers against the "judgment beats rules" result.** Measure whether the anti-list and binary triggers lose lessons that free judgment would keep. Serves perfect memory. Touches `extract-lessons`. Finding 6; transfer from in-session memory to a separate worker is unmeasured.

## Gaps

- One of the 29 listed posts is unidentified; the "See more" list needs a browser or the site's search API to expand. The four older posts were found from embedded metadata, so any other older post that metadata omits is also missing.
- Partial or not-read posts: how-we-contain-claude, claude-code-sandboxing, a-postmortem-of-three-recent-issues, claude-think-tool, swe-bench-sonnet, eval-awareness-browsecomp, AI-resistant-technical-evaluations, building-strong-safety-evaluations, desktop-extensions, building-effective-agents (intro only this pass), confidential-inference-trusted-vms, claude-code-best-practices (documentation).
- Vault coverage of the six already-cited posts was checked by cited lines only; unused-part claims for those six are not verified against full vault documents.
- Compass coverage claims rest on keyword grep over `plugin/`, `.claude/agents`, `.compass/specs`, `.compass/decisions`; no hit means no keyword match, not proof of absence.
- No post reports variance across repeated runs for harness-design or components-of-agent-memory results; both are single-run or small-n.
- Several posts name models and tools (Fable 5, Opus 5, Mythos Preview, Claude Tag) described only inside those posts; not independently verified.
