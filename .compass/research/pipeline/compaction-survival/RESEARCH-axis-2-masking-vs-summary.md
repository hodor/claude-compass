---
title: "Compaction survival, axis 2: masking versus summary"
type: research
status: complete
confidence: medium
area: methodology
tags: [compaction, context-window, observation-masking, summarization, handoff, hooks]
summary: "Measured comparison of observation masking, tool-result clearing, anchored summaries and free LLM summaries for carrying coding-agent state across a full context; no source compares masking against anchored summaries directly"
created: 2026-11-21
updated: 2026-11-21
author: researcher
---

## Research: masking versus summary as the carry-forward method

From [[SPEC-025-stop-and-suggest-handoff-at-80-percent-context]] (the compaction-survival need added 2026-11-21).

### Question
Which carry-forward method keeps open tasks, files touched and decisions in front of a coding agent at the lowest token cost, and which of those methods can a hook-only plugin apply?

### Methodology
Technology landscape / comparative evaluation (DESMET feature-analysis mode over published measurements), because the axis asks which of several concrete options to pick. Primary papers and vendor pages were read for the numbers; Complexity Trap and ACON were read through their arXiv HTML. Grading: the brief carried `grading: allowed`, so each finding carries a grade by source type and measured-versus-asserted.

### Findings

1. **Complexity Trap: masking halves cost and matches LLM summary on solve rate in 4 of 5 setups** (confidence: high)
   - SWE-agent, SWE-bench Verified (500 instances), turn limit 250. Raw / masking (last M=10 observations kept) / LLM-summary (N=21 turns summarized, M=10 kept), solve % and $ per instance:
     - Qwen3-32B: 17.0 / 1.12, 15.0 / 0.55, 16.0 / 0.50
     - Qwen3-32B thinking: 23.0 / 0.51, 24.6 / 0.46, 24.8 / 0.51
     - Qwen3-Coder 480B: 53.4 / 1.29, 54.8 / 0.61, 53.8 / 0.64
     - Gemini 2.5 Flash: 32.8 / 0.41, 35.6 / 0.18, 36.0 / 0.24
     - Gemini 2.5 Flash thinking: 40.4 / 0.56, 36.4 / 0.24, 31.4 / 0.25
   - Differences between masking and summary are within about 1 point in 3 setups; masking lost 2 points to the raw agent on one setup (Qwen3-32B 17.0 to 15.0) and led summary by 5 points on another (Flash thinking, 36.4 against 31.4).
   - https://arxiv.org/html/2508.21433 (v3, camera-ready for NeurIPS 2025 DL4Code workshop; first 100,000 of 135,226 characters read)
   - Compass part: vault already holds this as [[research/llm-research/RESEARCH-axis-3-agent-memory]] finding 3; the table above adds the per-model numbers that note summarized.
   - Marks: preprint plus workshop paper, retraction not checked, 85 citations (S2, per the axis-3 note), convergence with findings 5, 6 and 9
   - Grade: measured, one run per cell, SWE tasks only; medium-high

2. **Complexity Trap: what masking keeps and loses, and the hybrid** (confidence: high)
   - Masking keeps the whole history of agent reasoning and actions and replaces only observations older than M turns with a placeholder such as "Previous 8 lines omitted for brevity". Edit commands and the file paths they name therefore stay in context; old file contents and test logs go. The paper does not measure this loss; it names the fixed window "agnostic to the relevance or staleness" of observations.
   - Observations are about 84% of an average SWE-agent turn (secondary report of the paper), which is why masking them removes most of the tokens.
   - Hybrid (masking while turns accumulate, summary as last resort, N=43, M=10): tested only on Qwen3-Coder 480B, 50-instance subset; +2.6 points solve rate over raw, cost 7% below masking and 11% below summary (figure only, no absolute numbers).
   - Window does not transfer: OpenHands needed M=58; M=10 "degrades drastically" there because OpenHands keeps retry turns SWE-agent drops.
   - https://arxiv.org/html/2508.21433 ; https://arxiv.org/abs/2508.21433
   - Marks: preprint plus workshop paper, retraction not checked, citations as finding 1, convergence with finding 3
   - Grade: measured for cost and solve rate; the file-loss claim is asserted, unmeasured; medium

3. **Complexity Trap: summaries lengthen runs and the summarizer call is itself costly** (confidence: high)
   - Mean turns, Gemini Flash: raw 50, masking 44, summary 52. Qwen3-Coder: summary runs 15% longer than raw and 13% longer than masking. Qwen3-32B: masking ran 13% longer than raw (the effect is not one-directional).
   - Summarizer share of instance cost: 2.86% (Qwen3-32B), 0.65% (32B thinking), 7.20% (Coder 480B), 6.71% (Flash), 5.24% (Flash thinking), because each call processes a unique turn sequence and reuses the prompt cache poorly. With summarizer cost removed, the cost gap between the two methods "largely disappears".
   - https://arxiv.org/html/2508.21433
   - Marks: as finding 1
   - Grade: measured; medium-high

4. **No source compares masking against an anchored (fixed-section) summary on the same benchmark** (confidence: medium, a negative finding)
   - Complexity Trap compares masking, a free-form OpenHands-style summary and a hybrid; its summary has no fixed sections or file index. Factory (finding 5) compares three summaries on probe scores, not against masking, on real sessions, not a solve-rate benchmark. ACON (finding 7) has no masking baseline. The two measurement families use different metrics (solve rate and cost versus judge probe scores), so their numbers cannot be put on one scale.
   - A web search for 2026 follow-ups returned one head-to-head masking source (Complexity Trap) and none that adds a fixed-section summary arm; coverage of the search is not exhaustive.
   - Marks: absence claim from a bounded search; convergence across the vault's two earlier axis notes, which say the same ([[research/llm-research/RESEARCH-axis-6-harness-engineering]] Contradictions: "No source compares the two")
   - Grade: not applicable (absence); medium

5. **Factory: anchored iterative summary scored 3.70 against 3.44 and 3.35; artifact trail was the weakest dimension for all** (confidence: medium)
   - Probe eval over 36,611 real-session messages, hundreds of compression points, four probes each (recall, artifact, continuation, decision), GPT-5.2 judge blind to method, 0-5 scale. Dimension scores (Factory / Anthropic / OpenAI): accuracy 4.04 / 3.74 / 3.43; context awareness 4.01 / 3.56 / 3.64; artifact trail 2.45 / 2.33 / 2.19; completeness 4.44 / 4.37 / 4.37; continuity 3.80 / 3.67 / 3.77; instruction following 4.99 / 4.95 / 4.92.
   - Factory keeps a persistent summary with sections for session intent, file changes, decisions and next steps and merges only the newly cut span into it; Anthropic regenerates the full summary at every compression, which Factory says causes "silent drift". OpenAI's compact output is opaque and, per Factory, "discards file paths as low-entropy content". Compression ratios: about 98.6 to 99.3%.
   - Factory's own conclusion: file-trail tracking "needs handling beyond summarization", a separate artifact index or explicit file-state tracking in the scaffold. Marks gaps: the page gives per-probe scores only for two examples (a 178-message debugging session: recall 4.8 / 3.9 / 3.2), and the overall gap (0.26 to 0.35 points) is small against a 5-point scale.
   - https://factory.com/news/evaluating-compression (factory.ai redirects there)
   - Compass part: [[research/llm-research/RESEARCH-axis-6-harness-engineering]] finding 14 holds the same result; the per-dimension table and the regenerate-versus-merge contrast are new here.
   - Marks: vendor post, retraction n/a, not preprint, citations n/a, convergence with finding 8 (file index) and 9
   - Grade: measured, vendor-run, self-favoring, judge-only; medium-low

6. **Anthropic context editing: clearing old tool results is a server-side rule with measured gains on the vendor's own evals** (confidence: medium)
   - Announcement (2025-09-29), Claude Sonnet 4.5: memory tool plus context editing "improved performance by 39% over baseline", context editing alone 29%, on an internal agentic-search eval; on a 100-turn web-search eval context editing cut token use 84% and let workflows finish that "would otherwise fail due to context exhaustion". Coding example: "old file reads and test results" are cleared, "debugging insights and architectural decisions" go to memory.
   - Mechanism (`clear_tool_uses_20250919`): trigger default 100,000 input tokens, keep default 3 tool uses, `clear_at_least`, `exclude_tools`, `clear_tool_inputs` default false (tool calls stay visible, only results go), each cleared result replaced by placeholder text. Clearing invalidates the cached prefix, so `clear_at_least` is the cost guard. The client keeps the full history; the API reports `applied_edits`. With the memory tool enabled, Claude is warned before clearing so it can save to memory.
   - The page calls server-side compaction (`compact_20260112`) "the primary strategy" for long conversations and clearing the finer-control option. The page does not mention Claude Code.
   - https://claude.com/blog/context-management ; https://platform.claude.com/docs/en/build-with-claude/context-editing (first 100,000 of 102,210 characters read)
   - Compass part: [[research/llm-research/RESEARCH-axis-2-host-features]] finding 30 holds the parameters; the measured percentages are new here. The eval, baseline and sample sizes are not published on the page.
   - Marks: vendor post and vendor docs, retraction n/a, not preprint, citations n/a, convergence with finding 1 on direction
   - Grade: asserted percentages from an internal unpublished eval, mechanism documented in code-facing docs; medium-low for the numbers, high for the mechanism

7. **ACON: learned compression guidelines cut peak tokens 26 to 54% and mostly held accuracy; it has no masking arm** (confidence: medium)
   - Agent and compressor gpt-4.1. AppWorld accuracy (no compression 56.0, history compression with ACON UT+CO 56.5, peak tokens 9.93k to 7.33k); AppWorld hard tasks fell to 30.2 from 39.7. OfficeBench: every compressor scored below no compression (76.84); ACON UT 74.74 at 32% fewer peak tokens. 8-objective QA: ACON UT beat no compression (EM .373 vs .366), peak tokens 10.35k to 4.71k.
   - Baselines: FIFO truncation, embedding retrieval, LLMLingua, a generic prompting compressor. AppWorld accuracy: FIFO 45.8, retrieval 27.4, LLMLingua 39.3, prompting 43.5. Compressors tuned by contrasting success-uncompressed with failure-compressed runs, optimization under $2 per benchmark; distilled compressors keep over 95% of the teacher; end-to-end AppWorld cost fell from $0.331 to $0.285 per task but latency rose from 73 s to 88 s.
   - The paper names the risk directly: "losing a single detail such as a file path or an API parameter can derail the entire workflow"; it does not measure file-path loss.
   - https://arxiv.org/html/2510.00615 (v3, accepted ICML 2026; first 100,000 of 202,242 characters read)
   - Marks: peer-reviewed (ICML 2026 per the arXiv page), retraction not checked, not preprint-only, citations not checked, convergence with finding 5 (guidelines versus fixed sections are both "tell the compressor what to keep")
   - Grade: measured, non-coding benchmarks (AppWorld is API tasks, OfficeBench is office apps); medium

8. **2026 follow-up, frontier models: no compaction strategy beat plain self-summary on benchmark score, and one strategy is tool-output pruning (masking) with a threshold** (confidence: medium)
   - Five strategies in one scaffold (OpenCode): self-summarization baseline, tool-output pruning (old outputs replaced by a placeholder, about 40K tokens of recent outputs kept, runs only if it frees at least 20K), filesystem offloading (full history saved as JSON, the summary names the path), clear-thinking, small-model (Haiku 4.5) summary. Models: Claude Opus 4.6, GPT-5.4, GPT-5.3-Codex, Gemini 3.1 Pro (Gemini rarely compacted). Benchmarks: PaperBench (3 papers), ProgramBench, PostTrainBench.
   - PaperBench, 160K threshold: no strategy beat the baseline beyond confidence intervals; ProgramBench: no significant effect for any model. Haiku summary hurt GPT-5.4 (0.59 to 0.43) and Codex (0.38 to 0.18); filesystem offload hurt Codex (about 0.24). Tool-output pruning stayed near baseline. No tokens or cost per strategy reported.
   - The authors' explanation: the goal is fixed and progress sits on disk, so most dropped content is recoverable; benchmarks are "compaction-friendly".
   - https://arxiv.org/html/2610.31778v1 (first 100,000 of 120,219 characters read)
   - Marks: preprint, retraction not checked, citations not checked (about one month old), convergence with finding 1 (masking and summary tie) and finding 9
   - Grade: measured, few tasks per cell, one scaffold, thresholds cover only 16 to 38% of a 1M window; medium

9. **Same paper: summaries silently drop rules, compounding with each compaction; files hold the progress, not the rules** (confidence: medium)
   - ProgramBench had 3 anti-cheating rules in the task prompt. Rules dropped per compaction: Codex 2.73 (all three lost in 80% of compactions), GPT-5.4 1.76, Opus 0.51. Cumulative: 0.92 at the first compaction, 1.93 by the 10th, 2.65 by the 30th, because each summary is built on the previous one. The summary prompt asked for "constraints or preferences that should persist" and they were dropped anyway.
   - SWE-chat, 44 real sessions, 269 constraints: 81% kept, 19% dropped (24.5% under a second judge). Dropped by category: feature requirements 6.2%, process instructions 35.9%, scope exclusions 36.8%.
   - The authors' reading: summaries keep what the agent needs to continue, the rules are "not necessarily needed to continue, only to continue correctly". The agent can re-read progress from disk; a rule that exists only in context is lost if the summary drops it.
   - https://arxiv.org/html/2610.31778v1
   - Compass part: the vault's decisions, scope exclusions and process rules (D-nn bullets, "never" lines in specs) are the same category; Compass's re-injected hot path carries index and active tasks, not a session's stated constraints.
   - Marks: as finding 8; convergence with finding 5 (Factory: artifact and decision probes are weakest)
   - Grade: measured; the SWE-chat part does not measure effect on outcome; medium

10. **OpenHands condenser: summary-based, cost halved only after cache effects are handled, resolve rate flat** (confidence: medium)
    - Blog (2025): up to 2x lower per-turn cost on a SWE-bench Verified subset, resolve rate 54% against 53% baseline; condensation fires only at a size threshold to keep prompt-cache reuse. SDK paper repeats "up to 2x with no degradation", citing the blog. Earlier pull request (Feb 2025): full SWE-bench Verified, 100-iteration cap, 200 instances resolved against 203 baseline, and cost $40 more because of lower cache utilization; a cache-reusing variant on 50 instances: baseline 53%, cache version 47%, condenser 54%.
    - OpenHands also ships a masking-like condenser: an `AmortizedForgettingCondenser` that forgets without summarizing, and (OpenHands-Versa, arXiv:2506.03011) a browsing condenser that keeps only the most recent observation and masks older ones with a fixed placeholder. No OpenHands source compares the two on one benchmark; the Complexity Trap ran its OpenHands check itself.
    - https://www.openhands.dev/blog/openhands-context-condensensation-for-more-efficient-ai-agents ; https://github.com/OpenHands/OpenHands/pull/6597 ; https://github.com/OpenHands/OpenHands/pull/7588 (all read through search summaries only; pages not opened)
    - Marks: vendor blog plus pull-request notes, not preprint, retraction n/a, citations n/a, convergence with finding 3 on cost-cache interplay
    - Grade: measured on subsets, vendor-run; medium-low

11. **Staged compaction with an artifact index: masking at 80%, LLM summary only at 99%, file index inside the summary; the paper reports no controlled evaluation** (confidence: medium)
    - OpenDev terminal agent (arXiv:2603.05344, section 2.3.6): thresholds 70% warn, 80% observation masking (older tool results replaced by a reference pointer of about 15 tokens), 85% fast pruning, 90% aggressive masking, 99% full LLM summary with recent messages verbatim. The summary carries an Artifact Index of every file touched and what was done (read, created, modified, deleted), and the full history is archived to disk with its path in the summary. The summary is periodically rebuilt from the full history, not from the previous summary, to avoid drift.
    - Claimed result: compaction "reduced peak context consumption by approximately 54%"; the paper gives no method or baseline and states it "lacks systematic quantitative evaluation". The conclusion's single trigger figure is "the 70% compaction trigger", which differs from the 80% masking stage in section 2.3.6 (stage list and conclusion are not reconciled in the text read).
    - https://arxiv.org/html/2603.05344v1 (characters 100,000 to 300,000 of 358,364 read; the section text was partly garbled in the fetch)
    - Marks: preprint, retraction not checked, citations not checked, single source; matches Factory's remedy (finding 5) in design but not in evidence
    - Grade: design description, outcome asserted, unmeasured; low-medium

12. **Learned context management beats static threshold compression on SWE-bench Verified, with no masking arm shown** (confidence: low)
    - SWE-Compressor (arXiv:2512.22087, "Context as a Tool"): the agent calls a context-management tool at milestones; context split into stable task semantics, condensed long-term memory, high-fidelity short-term interactions. Abstract: 57.6% solved; a search summary lists ReAct 49.8 and threshold-compression 53.8 at 32B on OpenHands. Needs training, so it is not available to a plugin. The full tables were not read.
    - https://arxiv.org/abs/2512.22087 (abstract only); AutoCompact arXiv:2610.02163 (trains when to compact; title and search summary only)
    - Marks: preprint, retraction not checked, citations not checked, single source
    - Grade: measured per abstract, tables unread; low

13. **Summary-based compaction can launder forged user text into memory in harnesses that flatten roles** (confidence: medium)
    - Pixee author, arXiv:2610.29869: harnesses that flatten the conversation to labeled plain text before summarizing (pi, opencode, Cline, Aider, OpenHands) carried a forged approval into memory 87 to 100% of the time; role-typed harnesses (Codex, Gemini CLI, Qwen Code, Continue) 0%. A serializer-level fix (escaping role labels) and a provenance check (caught 77%, demoted 2% of legitimate content) are given. Masking does not rewrite text through a summarizer, so this vector is a summary property; the paper does not test masking.
    - https://arxiv.org/abs/2610.29869 (abstract only)
    - Marks: preprint, retraction not checked, citations not checked, single source
    - Grade: measured in controlled sandbox runs; medium-low. Touches a handoff built by a model from a transcript that contains tool output or web text.

14. **A hook-only plugin cannot mask or clear the host's history, but it can steer three things around compaction** (confidence: high for the host events, medium for what each yields)
    - Host side, from the vault's reading of the Claude Code hooks reference ([[research/llm-research/RESEARCH-axis-2-host-features]], hooks finding): PreCompact (matcher `manual|auto`) stdout, capped at 10,000 characters, becomes instructions for the compaction summary, and exit 2 or `decision: block` blocks the compaction; PostCompact receives `compact_summary` with no decision control; SessionStart fires after compaction with `source: "compact"` and accepts `additionalContext`. Context editing (`clear_tool_uses`) and the memory tool are API parameters on the message request; the context-editing page does not mention Claude Code, so a plugin has no lever on them. The vault notes the hooks reference itself was read there, not here.
    - Compass today: `plugin/hooks/hooks.json` registers PreToolUse, PostToolUse, SessionStart (startup and unmatched), Stop, TeammateIdle and SubagentStop; no PreCompact, PostCompact or compact-source handler. `plugin/cli/commands/context_check.py` re-arms its 80% and 95% levels after a compaction.
    - What a plugin chooses: (a) the text PreCompact appends to the summary prompt, i.e. which fixed sections the host summarizer is told to keep; (b) what SessionStart(compact) re-injects as `additionalContext`, which is exactly what survives outside the model-written summary; (c) what its own handoff document holds. Method mapping for those choices: an external memory file re-read after compaction is applicable in full (it is the re-injection); an anchored summary with fixed sections is applicable as PreCompact instructions and as the handoff body; masking, clearing and rule-based elision of past tool output are not applicable to the host history, but are applicable to what the plugin itself writes into a handoff (include file paths and decisions, leave out tool output bodies).
    - Marks: vendor docs (read via vault notes), not preprint, retraction n/a, citations n/a; the host-side facts from one prior vault note; file-level facts read in `plugin/` this pass
    - Grade: documented behavior, not tested this pass; medium-high

15. **Cost ordering of the carry-forward methods, from the numbers above** (confidence: medium)
    - Masking or clearing: no extra model call; the one cost is a prompt-cache break at each clear (Anthropic docs; Complexity Trap notes the summarizer calls reuse cache poorly). Cost 0.18 to 0.61 dollars per instance against 0.24 to 0.64 for LLM summary, raw 0.41 to 1.29 (finding 1).
    - Free LLM summary: summarizer is 0.65 to 7.2% of instance cost, runs 13 to 15% longer on two models, and silently drops rules (findings 3, 9).
    - Anchored summary: summarizer cost as above plus a better score in one vendor eval (3.70 against 3.44 and 3.35), file-trail still 2.45 of 5 (finding 5).
    - External memory file re-read: cost is the re-read tokens; no solve-rate measurement found for a coding agent that re-reads a memory file after a forced compaction. Anthropic's 39% (memory plus clearing) against 29% (clearing alone) is the only vendor number, on an unpublished eval (finding 6).
    - Rule-based elision (FIFO, truncation, LLMLingua): ACON's AppWorld accuracy 45.8 (FIFO) and 39.3 (LLMLingua) against 56.0 uncompressed, so unguided elision lost 10 to 17 points there (finding 7).
    - Marks: synthesis across findings 1 to 7; convergence of cost direction across Complexity Trap, ACON and Anthropic
    - Grade: derived comparison of different benchmarks, not a controlled comparison; low-medium

### Candidate changes for Compass
Ranked by impact. Each names the north star and whether Compass covers it. These are options for the planner, not decisions.

1. **Re-inject a fixed block on SessionStart(compact): active tasks, branch and files touched this session, decisions and scope exclusions in force.** Serves accuracy and perfect memory. Change in `plugin/`: a `source: "compact"` SessionStart handler running a `compass` command that prints the block as `additionalContext` (10,000-character cap), built mechanically from `active.md`, the git status and the session's tool-use log. Evidence: findings 5, 9, 14; rules and file trail are the two losses every measured method shows. Covered today: no (no compact-source handler, finding 14; [[research/llm-research/RESEARCH-axis-2-host-features]] already ranks the same handler).
2. **PreCompact instructions that name the fixed sections the host summary must keep.** Serves accuracy. Change: a PreCompact handler printing short section instructions (intent, files changed with paths, decisions, scope exclusions, next step) up to 10,000 characters. Evidence: findings 5, 9 (anchored sections beat free-form in the one comparison; rule loss happens even when the prompt asks for constraints, so the instruction alone is not enough, which is why item 1 comes first). Covered today: no.
3. **Make the handoff body mechanical for the file trail and decisions, model-written only for intent and next step.** Serves low token usage and accuracy. Change: the handoff command fills file paths (from git status and tool-use log) and the decision bullets (D-nn lines of the specs in play) itself; the model writes two short sections. Evidence: findings 5, 11 (file index outside the summary), 3 (model-written summary costs tokens and lengthens runs). Covered today: the handoff template has an Artifacts (exhaustive paths) section that a model fills ([[research/llm-research/RESEARCH-axis-6-harness-engineering]] finding 13); mechanical filling is not confirmed either way in this pass.
4. **Keep tool-output bodies out of the handoff and the re-injected block (masking applied to Compass's own documents).** Serves low token usage. Change: handoff and re-injection hold references (path, line, command) never output bodies, matching masking's keep-actions-drop-observations split (finding 2). Covered today: the handoff rules already say `file:line` references, never large code blocks (the `methodology` skill, section "Handoffs"); no check enforces it.
5. **Treat the masking-versus-anchored-summary question as open and, if it matters, settle it with a Compass-side probe.** Serves accuracy. Finding 4 says no source compares them; the probe format (four probe types) is already in the vault ([[research/llm-research/RESEARCH-axis-6-harness-engineering]] finding 14) and axis 4 of this set covers the probe KPI. Covered today: not run.

### Contradictions
- Finding 1 (summary no better than masking) and finding 5 (one summary style beats others by a small margin) do not conflict: they compare different arms on different metrics. Neither has the other's arm.
- Finding 6 (Anthropic names compaction the primary strategy) versus finding 1 (masking matches summary at half the cost): the vendor gives no measurement of compaction against clearing.

- Finding 11 (OpenDev: 80% masking stage, 70% as "the compaction trigger") is internally inconsistent in the text read; the 54% figure carries no method.
- Finding 8 (all strategies tie on benchmark score) versus finding 9 (summaries lose 19% of constraints, up to 37% for scope exclusions): the benchmark scores do not register rule loss that SWE-chat does; the paper states benchmarks cannot see it.

### Gaps
- No source compares masking against a fixed-section summary on one benchmark (finding 4); a Compass-side probe would be the settling experiment.
- No measurement found of an agent re-reading an external memory file after compaction versus a model-written summary (finding 15).
- Complexity Trap's last 35,000 characters (hybrid section 5.3 detail, appendices) were not read; hybrid numbers are figure-only. Model-name table for 5 configurations came from the fetch, not the paper's text directly.
- OpenDev compaction (finding 11): stage text for 90% and 99% was garbled; Appendix I constants not read. OpenHands (finding 10), SWE-Compressor and AutoCompact (finding 12) were read via search summaries or abstract only.
- Citation counts and retraction status were not checked for the 2026 preprints; the 2025 figure for Complexity Trap is the vault's earlier Semantic Scholar count.
- Hook behavior (finding 14) rests on the vault's earlier reading of the Claude Code hooks reference, not a fresh read or a live test; sibling axis 1 of this set covers hooks.
