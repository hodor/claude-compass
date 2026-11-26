---
title: "Axis 6: harness engineering from other labs and agent vendors, 2025-2026"
type: research
status: complete
confidence: medium
area: workflow
tags: [harness-engineering, context-engineering, kv-cache, agents-md, compaction, long-running-agents, evaluation]
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "bf8c771"
author: researcher
summary: "What OpenAI, Manus, Cursor, Cognition, Amp, Factory, OpenHands, Cline, Gemini CLI and a 2026 source-code survey say about harness design, checked against what Compass already does; reports only what the earlier context prior-art review did not cover"
---

# Axis 6: harness engineering from other labs and agent vendors, 2025-2026

From [[RESEARCH-llm-research-for-compass]] (axis 6). Builds on [[research/whole-overhead/agent-context/RESEARCH-agent-context-prior-art]]; that review's findings (Anthropic context engineering, 12-factor agents, Cognition's "Don't build multi-agents", Chroma context rot, ACON) are not repeated.

## Question

What do other labs' and agent vendors' 2025-2026 engineering posts and papers document about harness design (tools, context, memory files, planning, long runs, evaluation) that Compass does not already do?

## Methodology

Grey-literature review: the subject is vendor and practitioner engineering posts, plus three papers (one peer-reviewed accept, two preprints). Quality is not excluded on score; each finding carries source type, measured-or-asserted, and a mechanical-marks line. Compass coverage was checked by grepping `plugin/` and `.compass/` (terms: kv-cache, prompt cach, cache hit, recit, todo.md, condens, compaction, AGENTS.md, doc-gardening, lint hints).

Grading was allowed in the brief. Grades are by source type and measured/asserted. Citation counts were not retrieved for any paper (marked "n/r"). A sibling-axis claim not verified by me is marked as such.

## Findings

### A. Cache-friendly context (north star 3 and 4)

1. **Stable prefix, append-only context, deterministic serialization are the vendor-stated rules for KV-cache hit rate** (confidence: high)
   - Manus calls cache hit rate "the single most important metric" for a production agent. Input to output is about 100:1 tokens; cached input is 10x cheaper (0.30 vs 3 USD/MTok on Sonnet). Rules: no timestamp at the top of the system prompt, never edit earlier actions or observations, serialize JSON with stable key order, set cache breakpoints by hand where the provider does not.
   - https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus (read in full)
   - The 2026 source-code survey names the same pattern in three harnesses: Claude Code "Cache Boundary", Hermes "Bit-Perfect Prefixes", OpenHands prompt registry with cache tiers (arXiv:2609.00006 §7.2, read via the HTML page, first 100k of 295k characters).
   - Grade: vendor post, asserted (price figures are the provider's list prices; no hit-rate number given). Marks: vendor post, not retracted, not preprint, citations n/a; converges with finding 2 and the survey.
   - Compass part: the hot path (`.compass/index.md`, `active.md`, `lessons/index.md`) loads at the start of every agent via `initialPrompt`; `active.md` and `index.md` are rewritten by `compass sync` on every vault write. Compass cites "cache misses" only in the vault-navigation sense (SPEC-001 line 38). No Compass doc or code treats the provider prompt cache as a design input (grep of plugin/, specs, decisions, research found it only in Hermes research notes).

2. **Pruning that edits the prompt layout costs more than it saves; compaction can be designed around the prefix** (confidence: medium)
   - TokenPilot: context pruning and eviction change prompt layout, causing "prefix mismatches and cache invalidation". Its design keeps prefixes stable and batches eviction on a cautious schedule. Reports cost down 56-61% in isolated mode and 61-87% in continuous mode on two benchmarks, performance "competitive". Accepted to EMNLP 2026 Findings.
   - https://arxiv.org/abs/2606.17016 (abstract read, v2 2026-08-28; method body not read)
   - Marks: peer-reviewed (Findings track), not retracted, not preprint now, citations n/r, 1 source plus finding 1 agree.
   - Grade: measured on two benchmarks the paper picked; transfer to a coding agent unverified.
   - Compass part: Compass never edits a running context; its only mid-session intervention is the 80% and 95% handoff stop (`plugin/cli/commands/context_check.py` lines 1-40). The compaction itself is the host's.

3. **OpenHands condenser: summarize the first half of events at intervals, keep the full event log, accept one cache wipe per condensation** (confidence: medium)
   - Condensation is recorded as an event; the full log is kept and the LLM view is rebuilt from it, so the condenser is stateless. A cheaper model can summarize. The 2x per-turn cost claim comes from a vendor blog on a SWE-bench Verified subset (April 2025); the SDK paper cites that blog, not its own measurement.
   - https://arxiv.org/html/2511.03690v1 §4.6 ; https://www.openhands.dev/blog/openhands-context-condensensation-for-more-efficient-ai-agents (both via search summaries, not read in full)
   - Marks: preprint (arXiv 2511.03690, 2025-11-05) and vendor blog, not retracted, citations n/r, 2 sources that share one origin (not independent).
   - Grade: asserted by the SDK paper, measured once in the blog.
   - Compass part: none of the Compass docs describe a derived, regenerable view over an untouched log. The vault already keeps sources and derived indexes apart (sync regenerates indexes), so the shape exists for the vault, not for conversation history.

### B. Files as memory and what to put in them

4. **Large tool output goes to a file; the agent reads it with tail and grep; chat history is also a file after summarization** (confidence: high for the mechanism, low for the effect size)
   - Cursor (2026-01-06) writes long shell and MCP outputs to files, gives the agent a pointer to the full chat history after a summary, and writes terminal sessions to disk for grep. Claim: "fewer unnecessary summarizations". No number given for these three; only the MCP item has a measure (finding 5).
   - https://cursor.com/blog/dynamic-context-discovery (read in full)
   - Marks: vendor post, not retracted, not preprint, citations n/a; converges with Manus ("compression is always reversible: keep the URL or the sandbox path") and with Anthropic's file-reference handover already in the prior-art review (its finding 19).
   - Grade: vendor post, asserted.
   - Compass part: SubagentStop writes a subagent's final report to `.compass/tmp/subagent-captures/` (`plugin/hooks/hooks.json` description), but as capture evidence, not as a spill for the parent. The prior-art review's launcher options already cover capped reports with the full text spilled to a file; this adds the chat-history-as-file leg, which no Compass doc mentions.

5. **Lazy tool descriptions cut tokens 46.9% in an A/B test** (confidence: medium)
   - Cursor stores MCP tool descriptions in one folder per server and puts only names in the prompt; the agent reads a description when a task needs it. Statistically significant, high variance with the number of servers installed. Skills are handled the same way (name and description fixed, body found by grep).
   - https://cursor.com/blog/dynamic-context-discovery
   - Marks: vendor post, not retracted, not preprint, citations n/a; the survey reports deferred loading as "the dominant pattern" for skills and Claude Code as having 43 typed tools with deferred loading (arXiv:2609.00006 §8.3, §12.5), so 2 sources.
   - Grade: measured A/B, vendor-run, no confidence interval.
   - Compass part: Compass already measures that skill preloading is its largest startup cost (60% of a builder's first request, per [[research/whole-overhead/agent-context/REVIEW-agent-context-2026-11]]). The Cursor figure is a second data point for the same direction; the 15,000-token description threshold is in the prior-art review.

6. **Todo recitation: rewrite the plan at the end of the context so it sits in recent attention** (confidence: medium)
   - Manus keeps a `todo.md` it rewrites and ticks off across about 50 tool calls per task. Cline's Focus Chain injects a generated todo list every six turns and keeps it through summarization (v3.25, about 14-15 months old). Mechanism claimed: the plan stays out of the "lost in the middle" zone.
   - Manus URL above; https://cline.bot/blog/cline-v3-25 and https://cline.bot/blog/how-to-think-about-context-engineering-in-cline (search summaries, not read in full)
   - Marks: 2 vendor posts, not retracted, not preprint, citations n/a; neither gives a measurement.
   - Grade: vendor posts, asserted.
   - Compass part: `active.md` is read once at agent start (`.claude/rules/session-start.md`) and sits at the head of the context; nothing re-injects it later. grep for "recit" and "todo.md" in `plugin/` found only unrelated hits.

7. **Errors stay in context; uniform context makes agents brittle** (confidence: medium)
   - Manus: failed actions and stack traces stay visible so the model updates its beliefs; hiding them "removes evidence". It also adds small variation in serialization and wording to avoid few-shot ruts across batches of similar items. The 12-factor point that resolved errors may be hidden (prior-art review finding 5) pulls the other way.
   - Manus URL above. Marks: vendor post, asserted, 1 source against the 12-factor opposite.
   - Compass part: the builder fix loop respawns fresh fix builders that get "the specific FAIL, not the full task" (`plugin/skills/methodology/SKILL.md` parallel-execution rules), so failure evidence is passed forward in digest form. No doc states a retention rule.

8. **Durable project memory as four files drove a 25-hour, 13M-token Codex run** (confidence: medium)
   - OpenAI (developer blog): Prompt.md (goals, non-goals, constraints, "done when"), Plans.md (milestones with acceptance criteria and validation commands, a stop-and-fix rule, decision notes "so the agent doesn't keep switching approaches", intended architecture), Implement.md (runbook: plan is source of truth, validate after every milestone, narrow diffs), Documentation.md (live status and audit log). About 30k lines from an empty repo; the author calls the result "not perfect or production-ready".
   - https://developers.openai.com/blog/run-long-horizon-tasks-with-codex (read in full). A separate repo, friel-openai/plans.md, packages ExecPlans as a skill (search summary only).
   - Marks: vendor post, not retracted, not preprint, citations n/a; converges with Anthropic's NOTES.md and plan-to-memory advice (prior-art review findings 20, 24).
   - Grade: vendor post, one demonstration run, asserted.
   - Compass part: spec, plan with acceptance criteria and per-task validation, ADRs for decisions, handoff for status: all present (`plugin/skills/methodology/SKILL.md`). The named extra is a "stop-and-fix" validation rule per milestone and a runbook file; the build skill's fix loop (max 3 cycles) covers the first.

### C. Repository knowledge as a harness (AGENTS.md and enforcement)

9. **A 100-line AGENTS.md as a table of contents beat one large file; the repo docs are the system of record** (confidence: high that OpenAI reports it, medium on effect)
   - OpenAI (2026-02-11, Codex built about 1M lines, about 1,500 PRs, 3 to 7 engineers, "0 lines of manually-written code"): the single big AGENTS.md failed four ways: it eats context, everything-important means nothing is, it rots, and it cannot be checked mechanically. The fix: about 100 lines pointing into `docs/` (design-docs with verification status, exec-plans active/completed, product-specs, references, a quality score per domain).
   - https://openai.com/index/harness-engineering/ (read in full)
   - Marks: vendor post, not retracted, not preprint, citations n/a; converges with Compass's own index design and Anthropic's "lightweight identifiers" (prior-art review finding 4); the survey says LangChain Deep Agents and xAI Grok Build adopt AGENTS.md (arXiv:2609.00006 §9.7).
   - Grade: vendor post, asserted; outcome numbers are self-reported.
   - Compass part: already covered. Hot path of three pointer files with a 5,000-token cap enforced by `validate` (`plugin/cli/commands/hot_path.py` lines 1-30), [[SPEC-001-compass-vision-and-architecture]], [[ADR-004-hierarchical-specs-with-facets]]. Compass ships `AGENTS.md` only as a managed rules section for another host (`plugin/cli/hostlib.py` lines 216-240).

10. **Mechanical enforcement: lint error messages carry fix instructions that are fed to the agent** (confidence: high for the report, low for transfer)
   - OpenAI: custom linters and structural tests enforce a fixed layer order (Types, Config, Repo, Service, Runtime, UI) and taste rules (logging, naming, file size). "Lint error messages contain fix instructions that get fed into the agent's context." Rule of promotion: when docs fall short, "we promote the rule into code". Invariants are stated ("parse data at the boundary"), not implementations.
   - https://openai.com/index/harness-engineering/
   - Marks: vendor post, asserted, 1 source.
   - Compass part: `compass validate` fails the hot-path cap and reports taxonomy suggestions (`plugin/cli/commands/validate.py` around lines 212-260), and `compass guard` denies destructive calls, so mechanical enforcement exists. Whether each validate failure message tells the agent the fix was not checked across all checks (gap).

11. **Doc-gardening and golden-principle cleanup are recurring background agents that open fix-up PRs** (confidence: medium)
   - A recurring agent finds docs that no longer match code and opens PRs; background tasks scan for deviations from written "golden principles", update quality grades, open refactoring PRs, most auto-merged after under a minute of review. It replaced a manual Friday cleanup (20% of the week) that "did not scale". Rationale given: agents copy existing patterns, including bad ones, so drift compounds.
   - https://openai.com/index/harness-engineering/
   - Marks: vendor post, asserted, 1 source; same idea as Devin's "dreaming" (finding 12).
   - Compass part: `checkup`, `vault-health` and `consolidate` exist but run on demand or on a hard-cap warning (`plugin/skills/consolidate/SKILL.md` description: "Runs only when a hard-cap warning is present"). No scheduled or detached stale-doc sweep that compares docs to code; the closest, `compass doctor`, checks install state. The detached capture worker (ADR-013) is the existing pattern for a hook-spawned background pass.

12. **Devin "dreaming": a daily background pass merges, strips and prunes memory by use** (confidence: medium)
   - Memory is a git repo of markdown notes; MEMORY.md is the short index loaded at session start; notes are lessons, not session summaries, each linked to its source session. A daily pass merges overlapping notes, strips transient details, hunts lessons missed during the work, and deletes records "that weren't used by any sessions". Parallel sessions write through a revision check that rejects a stale write. No measurements; the staleness rule is stated only as "no session used it".
   - https://devin.ai/blog/memory-and-dreaming (2026-10-05, read in full)
   - Marks: vendor post, not retracted, not preprint, citations n/a; no measure.
   - Grade: vendor post, asserted.
   - Compass part: structurally near-identical to the lessons loop ([[ADR-016-capture-by-extraction]], capture opportunities, `consolidate`, lesson score and `seen` dates). Two differences: Devin prunes by session-use, and Compass's rule is never to destroy information (CLAUDE.md data rule), so prune-by-disuse conflicts with it by design. The revision-check write is not present; Compass writes are single-session.

### D. Compaction, handoff and long-running runs

13. **Amp removed compaction for goal-directed handoff** (confidence: high for what Amp did, low on outcome)
   - Amp (2025-10-23) found compaction "encourages long, meandering threads" and stacks summary on summary. Handoff takes a goal, drafts a new thread's starting prompt plus a file list from the old thread, and shows it as an editable draft. A third-party blog hints at a 2026 reversal; Amp's own page shows none.
   - https://ampcode.com/news/handoff (read in full)
   - Marks: vendor post, not retracted, not preprint, citations n/a; 1 source, a third-party mention of a reversal is unverified.
   - Grade: vendor post, asserted, no measurement.
   - Compass part: `/compass:handoff` writes a handoff on request and `context-check` suggests it at 80% and 95% ([[SPEC-025-stop-and-suggest-handoff-at-80-percent-context]]). The difference: Amp's draft is conditioned on the next goal; the Compass template is a fixed state snapshot (Task, References, Recent changes, Learnings, Artifacts, Action items). Whether `/compass:handoff resume` accepts a stated goal was not checked.

14. **Factory probes: a structured, incrementally merged summary beat Anthropic's and OpenAI's compaction, and every method lost file-trail detail** (confidence: medium)
   - Factory built a probe-based eval: four probe types (recall, artifact, continuation, decision) per compression point, an LLM judge (GPT-5.2, blind to method) over six 0-5 dimensions, across 36,611 messages from real sessions. Overall: Factory anchored-iterative 3.70, Anthropic 3.44, OpenAI 3.35. Artifact trail scored only 2.19 to 2.45 for all three, which Factory reads as needing a dedicated file index. Its method keeps a persistent summary with fixed sections (intent, file changes, decisions, next steps) and merges only the newly cut span into it.
   - https://factory.com/news/evaluating-compression (read in full; factory.ai redirects there). The vendor compares itself to rivals, so the ranking has a conflict of interest.
   - Marks: vendor post, not retracted, not preprint, citations n/a; judge-based scores, no human check reported on the page.
   - Grade: measured (large sample, probes), vendor-run, self-favoring.
   - Compass part: the probe format is a ready sufficiency test for a Compass handoff or any brief ("can the receiver answer recall, artifact, continuation, decision questions"), which the prior-art review's "Testable practices" left open. The artifact-trail gap lines up with the handoff template's "Artifacts (exhaustive paths)" section; not measured in Compass.

15. **Context anxiety and model self-awareness change harness needs** (confidence: medium)
   - Cognition on Sonnet 4.5 (late 2025): the model summarizes and rushes as it nears its window; Cognition enabled the 1M beta and capped use at 200k so the model "believes it has plenty of room". The model also writes its own notes (CHANGELOG.md, SUMMARY.md) unprompted but paraphrases and omits task details; relying on them alone, with no compaction system, lowered performance because the model "didn't know what it didn't know".
   - https://cognition.com/blog/devin-sonnet-4-5-lessons-and-challenges (read in full)
   - Marks: vendor post, not retracted, not preprint, citations n/a; 1 source; this is a model-specific observation (Sonnet 4.5) and may not hold for later models.
   - Grade: vendor post, observation, no numbers.
   - Compass part: `context_check.py` reads the window from a model table and treats native-1M models as 1M; the 80% stop depends on the true window. Whether a model's own awareness of a nearing window changes behavior before 80% is not covered by SPEC-025.

16. **Multi-agent that works: one writer, extra agents add intelligence; a clean-context reviewer catches about 2 bugs per PR** (confidence: medium)
   - Cognition (2026-04-22): "writes stay single-threaded". Devin Review, with no shared context with the coder, still finds about 2 bugs per Devin-written PR, about 58% severe; the coding agent decides which findings to act on using what it knows of the user's instructions (guards against loops and scope drift). Manager-and-children delegation is live but "mostly a distraction" when unstructured; agents assume they share state with children when they do not. Cognition's own June 2025 post says the opposite on parallel agents (see Contradictions).
   - https://cognition.com/blog/multi-agents-working (read in full)
   - Marks: vendor post, not retracted, not preprint, citations n/a; numbers are Cognition's own product telemetry.
   - Grade: vendor post, measured on its own PRs, not independently replicated.
   - Compass part: tester and validator already run as separate agents after the builder (`plugin/skills/methodology/SKILL.md` "Task execution"). Whether the validator receives the builder's reasoning or only the diff and plan was not checked here; the clean-context finding concerns exactly that choice. Axis 4 is the home for this.

17. **Cursor's long runs: shared-file coordination failed; planners, workers and a fresh-start judge worked** (confidence: medium)
   - Equal-standing agents on a shared task file became risk-averse. Locks: 20 agents did as much as 2 or 3. Optimistic concurrency was sturdier but agents stayed cautious. What worked: recursive planners, workers that "just grind" on one task in their own repo copy, a judge at each cycle's end, then "the next iteration would start fresh". A separate integrator role created bottlenecks. "The prompts matter more" than harness and model. Restarts fresh to fight drift were still needed.
   - https://cursor.com/blog/scaling-agents (read in full; the second post, Towards self-driving codebases, was read only through a search summary)
   - Marks: vendor post, not retracted, not preprint, citations n/a; scale numbers (1M-line browser, Solid-to-React migration over 3 weeks) are self-reported.
   - Grade: vendor post, outcomes asserted.
   - Compass part: builders already run in separate worktrees on non-overlapping files with the orchestrator merging (`plugin/skills/methodology/SKILL.md` "Parallel execution"), which matches the "no integrator, own your files" result; Compass's "fresh start per cycle" parallel is the fresh fix builder. The loop module (`plugin/cli/looplib.py`, `looprunner.py`) exists; whether it has a judge step was not read.

18. **Survey of 11 harnesses: no vector retrieval, hand-rolled loops, policy moving from prompt text to configuration** (confidence: medium)
   - A 83-page source-code study of Claude Code, Codex CLI, Gemini CLI, OpenHands, Aider, Hermes and others finds that none of about four million lines uses vector embeddings for code retrieval or imports a general agent framework; threshold compaction in 7 of 11; SKILL.md skills in 9 of 11, MCP in 8; Codex copies Claude Code's hook vocabulary "verbatim"; a 100-line loop (Mini-SWE-Agent) scores in OpenHands's range. 29 patterns and 18 recommendations, including a 90-line minimum harness.
   - https://arxiv.org/abs/2609.00006 (abstract) and https://arxiv.org/html/2609.00006v1 (first 100k of 295k characters). Observations 2-13 and §16 recommendations were not read. The arXiv listing shows submitted 2026-07-15 while the ID prefix is 2609 and one PDF metadata line said 2026-09-02; the date mismatch is unresolved.
   - Marks: preprint, not retracted, citations n/r, 1 source for each claim; the authors state a smaller April 2026 edition exists.
   - Grade: measured (source reading), preprint, field is moving fast.
   - Compass part: agrees with the vault's decision that RAG hurts goals 3 and 4 ([[research/vault-structure/RESEARCH-rag-fit-for-large-vaults]]). The "policy moves into configuration" note touches Compass's direction of putting behavior in CLI and hooks rather than skill prose (hooks.json description: every hook runs a command, never an agent).

19. **Hierarchical GEMINI.md and a roadmap for immutable state snapshots** (confidence: low)
   - Gemini CLI loads GEMINI.md from global, project and subdirectory levels with @imports; auto-compression at 0.5 of the window with the latest 30% kept verbatim (per the survey, not read from source). An open GitHub epic proposes a `checkpoint_state` tool whose snapshots the compressor must keep untouched. A separate issue asks for just-in-time loading of subdirectory files instead of eager load.
   - https://github.com/google-gemini/gemini-cli/issues/21792 ; https://github.com/google-gemini/gemini-cli/issues/11488 (search summaries; issues were not opened, and an issue is a proposal, not shipped behavior)
   - Marks: community issues, 2 sources, not peer reviewed.
   - Grade: proposals, asserted.
   - Compass part: the immutable-anchor idea matches Compass's hot path being re-read from disk after compaction (the prior-art review finding 23 says project CLAUDE.md is re-read; hot-path files loaded by `initialPrompt` are not CLAUDE.md, whether they survive compaction was not verified here).

20. **Small harness plus a trained model: an 8k-context model matches GPT-5.4 at 1M on OOLONG-synth** (confidence: low)
   - Trained Agentic Context Management: fine-tune a Qwen3.6-35B-A3B on a two-tool harness (call itself, read a token range). One author; under review; code public.
   - https://arxiv.org/abs/2610.02404 (abstract read)
   - Marks: preprint, not peer reviewed, citations n/r, 1 source; synthetic benchmark.
   - Grade: measured on one synthetic benchmark; Compass cannot train a model, so it informs direction only.

### E. Tool and interface design

21. **The agent-computer interface is a design surface with measured effect** (confidence: medium; older source)
   - SWE-agent argues LMs are a new kind of end user needing purpose-built interfaces for editing, navigating and running tests, and reports 12.5% pass@1 on SWE-bench and 87.7% on HumanEvalFix in 2024. The linter-guarded edit and history-processor details were not in the abstract page and were not read.
   - https://arxiv.org/abs/2405.15793 (abstract only; this is a 2024 paper)
   - Marks: peer-reviewed (NeurIPS 2024 per my recollection, not verified on this run), not retracted, citations n/r.
   - Grade: measured; older than the 2025-2026 window.
   - Compass part: the `compass` CLI is the ACI for vault work (commands such as `lessons`, `tree`, `sync`, `validate`). Compass has no measured comparison of command output shapes (for example how many tokens a failing `validate` costs an agent); not found in the vault.

22. **Mask tools, do not remove them mid-run; shared tool-name prefixes allow grouping** (confidence: medium)
   - Manus: adding or removing tools mid-iteration invalidates the cache and confuses earlier references; instead keep the tool set fixed and constrain choice through response prefill (auto, required, specified) and shared name prefixes (`browser_`, `shell_`). Needs decoding control that a Claude Code plugin does not have.
   - Manus URL above. Marks: vendor post, asserted, 1 source.
   - Compass part: Compass's tool surface per agent is a fixed list in each agent's frontmatter; it never changes tools mid-run. The prefill mechanism is not reachable from a plugin.

## Candidate changes for Compass

Ranked by effect on the north stars. "Covered" means a Compass doc or code already does it.

1. **Measure and order the hot path for the provider prompt cache.** Serves north star 3 and 4. Change: add a `compass hot-path` report line that flags the hot-path file with the highest write frequency (`active.md`), and an ordering rule (stable first: lessons index, then index, then active) in the `initialPrompt` of each agent file under `.claude/agents/` and `plugin/`; test with a paired run counting `cache_read_input_tokens` (the transcript field `context_check.py` already reads). Covered: no. Evidence for the effect on Compass is not measured (findings 1, 2); the ordering rule is a hypothesis, not a source claim.

2. **Recite the open-task list late in the context.** Serves north star 1 and 2. Change: a hook that appends the current in-progress lines of `active.md` as `additionalContext` at a fixed interval (Cline: every 6 turns), appended only, never rewritten, so the cache prefix holds. Covered: no (finding 6). Risk: adds tokens (north star 4) and neither source measured the effect.

3. **A scheduled doc-versus-code sweep in the detached-worker pattern.** Serves north star 1 and 2. Change: reuse the capture worker's hook-spawn path to run a bounded pass that lists vault documents whose `file:line` references no longer match the code and writes a report, never deleting (finding 11). Covered: partly (`checkup`, `consolidate` run on demand or on a cap warning; ADR-013 worker pattern exists). Conflict: Devin prunes by disuse, which Compass's data rule forbids, so only the "report" half carries over.

4. **Probe-based sufficiency test for handoffs and briefs.** Serves north star 1. Change: a `compass` check that asks a fresh agent four probe types (recall, artifact, continuation, decision) against a written handoff, scored by a judge, as the settling experiment the prior-art review left open (finding 14). Covered: no. Cost: judge tokens per run; Factory's judge was a vendor-run LLM with no human check reported.

5. **Goal-conditioned handoff.** Serves north star 1 and 4. Change: `/compass:handoff create` accepts the next goal and shapes the "Recent changes" and "References" sections around it, with a file list, as Amp's handoff does (finding 13). Covered: partly (handoff exists with fixed sections; goal parameter not found, not read in full).

6. **Spill a long CLI or subagent output to a file and return a pointer plus preview.** Serves north star 4. Change: cap `compass` command output and keep full text under `.compass/tmp/` (finding 4). Covered: partly (the hook cap on additionalContext is the host's; the launcher-options research already lists capped reports with spill).

7. **Fix-instruction text in every `compass validate` failure.** Serves north star 1 and 4. Change: audit each validate failure message for an explicit next action (finding 10). Covered: partly, not audited per message.

8. **Clean-context validation as a stated choice.** Serves north star 1. Change: record whether the validator sees the builder's reasoning or only plan and diff, and test the clean variant (finding 16). Covered: unknown; belongs to axis 4.

Not recommended for action from this axis: ACI redesign and tool masking (findings 21, 22; no plugin lever), trained context managers (finding 20; no lever), and recreating AGENTS.md-as-map (finding 9; Compass already does this).

## Contradictions

- Finding 7 (Manus: keep errors in context) against the 12-factor point in the prior-art review that resolved errors may be hidden. Neither source measured; Compass has no rule either way.
- Finding 16 (Cognition 2026: parallel writers lack adoption, one writer plus helpers works) against finding 17 (Cursor: hundreds of parallel writers on one branch worked at scale). Cognition's own text names the demos as having "a simple, checkable success criterion"; Cursor's browser and compiler-style runs fit that description. Compass's builders parallelize only on non-overlapping files, which sits between the two.
- Finding 13 (Amp: drop compaction) against finding 3 and 14 (OpenHands, Factory, Gemini CLI: compaction tuned and measured). One vendor removed it from its own UI; the others improve it. No source compares the two.
- Finding 15 (Cognition: model's own notes were insufficient) against Cursor's finding 4 (files recover details the summary lost). Both agree notes need a source of truth to read back; they differ on who writes it.
- Finding 18 gives two dates for the same arXiv paper (listing 2026-07-15; PDF metadata 2026-09-02; ID prefix 2609). Unresolved.

## Gaps

- No hit-rate or cache-read measurement of Compass sessions was made here; the transcript field exists in `context_check.py` but nobody has reported it per agent type. Whether the hot-path files that load by `initialPrompt` survive host compaction was not verified.
- Gemini CLI official docs, Aider's repo map and compression code, Sourcegraph beyond Amp's handoff, Google DeepMind blog posts, and the Cline source were not read; only search summaries or none. Factory's droid-level tool design posts were not reached.
- The survey arXiv:2609.00006: observations 2-13 and §16 recommendations (memory, tool design, multi-agent, anti-patterns, the 90-line harness) were not read; about two thirds of the HTML was unread.
- OpenHands: the condenser source and the blog were reached only through search summaries.
- Citation counts: not retrieved for any paper.
- SWE-agent's linter-guarded edit and history processor were not read; peer-review venue of SWE-agent is not verified on this run.
- Evaluation of agents (the brief's topic): only Factory's probe design and Cognition's reviewer telemetry were found; OpenAI's harness post gives no eval method; no source here gives an agent-evaluation protocol Compass could adopt beyond the probe format. This overlaps the earlier prior-art review's finding 28 (small eval, one judge call), which already covers the main practice.
- Whether `/compass:handoff` takes a goal, whether each `validate` message names a fix, and whether `looplib.py` has a judge step were not checked.
