---
title: Benchmarks for Evaluating Compass
type: research
status: complete
confidence: medium
area: methodology
tags: [evaluation, benchmarks, ablation, methodology-layer]
created: 2026-06-10
updated: 2026-06-10
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]"]
---

## Question

Which established benchmarks should we use to evaluate whether Compass-driven workflows produce better outcomes than plain Claude Code, and how should we structure the A/B comparison so the methodology layer (not the model) is what is measured?

## Scope

Coding agent benchmarks, long-horizon multi-step task benchmarks, and methodology-evaluation methodology. Excludes pure single-function code completion (HumanEval / MBPP / similar): the methodology layer adds no value to 30-line problems, so they cannot reveal Compass's contribution.

## Methodology

Three parallel general-purpose research agents, each scoped to one angle:

1. **SWE-style coding benchmarks** - what exists, what's contaminated, what's runnable.
2. **Long-horizon / multi-step agent benchmarks** - tasks taking >1 hour human-equivalent.
3. **Methodology-layer evaluation** - how to A/B test a wrapper layer; what the academic field actually does.

Convergence taken as strong signal. Single-source claims flagged.

## Findings

### 1. Tier-1 benchmarks (high convergence, runnable)

- **Terminal-Bench** (Stanford + Laude). Both agents A and B picked this primary. Multi-step terminal workflows (compile, train, sysadmin, security). Claude Code is the native reference harness, so Compass-vs-plain isolates the methodology delta cleanly. Open Docker harness. SOTA Claude Sonnet ~0.50 (confidence: medium - this is a moving target).
  - https://www.tbench.ai/ , https://github.com/harbor-framework/terminal-bench
- **SWE-bench Pro**. Replacement for SWE-bench Verified (which OpenAI audited and found contaminated: gold patches leaked, 59% of hardest items had flawed tests). Pro is 1,865 multi-language tasks on private enterprise repos, harder and cleaner. Best for measuring multi-file end-to-end issue resolution.
  - https://scale.com/blog/swe-bench-pro , arxiv 2509.16941
- **SWE-Lancer** (OpenAI). 1,400+ real Upwork freelance tasks with **two splits**: IC (implement code) AND **managerial** (pick best proposal from candidates). The managerial split directly tests spec / plan quality, not just code - the best public match to what Compass's spec and planner agents produce. Diamond split is open-sourced.
  - https://openai.com/index/swe-lancer/ , arxiv 2502.12115

### 2. Tier-2 benchmarks (run after Tier 1 confirms value)

- **SWE-EVO** (Dec 2025). 48 long-horizon software-evolution tasks built from real release notes; avg 21 files modified, 874 tests per instance. Frontier models score ~25% vs ~73% on Verified, so the gap is exactly the multi-step regime Compass targets.
  - arxiv 2512.18470
- **METR RE-Bench**. 7 open-ended ML R&D environments at ~8 hours human-equivalent time. Continuous scoring vs human baseline, not pass/fail. Highly relevant for Compass's longer-horizon claim. Access may be gated (METR collaboration). Backs the well-cited "task length doubles every ~7 months" finding.
  - https://metr.org/blog/ , arxiv 2411.15114
- **AppWorld** (multi-API planning, 9 apps, 457 APIs, avg 42 API calls / task). Tests planning + tool coordination at minutes-to-hours scale. Public.
  - arxiv 2407.18901

### 3. What NOT to use as the primary signal

- **SWE-bench Verified**: contaminated, saturated, no longer discriminating.
- **LiveCodeBench / BigCodeBench / HumanEval+ / MBPP+**: single-shot algorithmic problems. Useful only as a no-regression floor (does Compass make pure coding worse?), not as the value signal.
- **AgentBench (2023)**: older suite; newer benchmarks have superseded it.

### 4. The published gap (potential Compass contribution)

**No standardized benchmark measures "process" metrics**: was a spec written first, was the plan reviewed before build, were lessons captured at phase boundaries, was the index kept fresh. The ICSE 2026 *Catalogue of Evaluation Metrics for LLM-Based Multi-Agent Frameworks* (37 metrics) formalizes Outcome / Process / Product / Framework buckets but the actual process-measuring benchmarks do not exist yet. Compass could publish them.

**No RCT compares "vibe coding" to "spec-driven AI coding" with the same model and same tools**. Spec-driven advocates (GitHub Spec Kit, AWS Kiro) cite "10x fewer regeneration cycles" but there is no peer-reviewed controlled study. This is the clearest hole in the field.

### 5. A/B methodology (the harder problem than picking benchmarks)

- **Anthropic skill-creator** ships a blind A/B + Benchmark mode (60% train / 40% held-out, 3 reps per query, variance analysis, no selection on test). Closest published reference implementation. Worth cloning the pattern.
  - https://github.com/anthropics/claude-plugins-official skill-creator SKILL.md
- **Recurring pitfalls** (from Holistic Agent Leaderboard arxiv 2510.11977 and SWE-Bench Pro paper):
  - **Scaffold-vs-model confound**: same model + different scaffold gives huge swings. Compass arm and baseline arm must use identical model, tools, turn budget.
  - **Prompt asymmetry**: framework runs often have hand-tuned system prompts the baseline lacks. Baseline arm must get the same tools and a comparable system prompt.
  - **Self-defined metrics inflate SOTA**. Use external benchmarks, not custom-scored.
  - **Test contamination on Verified subsets**.
- **Cost / quality Pareto, not raw pass rate**. arxiv 2508.02694 (Efficient Agents) recommends reporting `accuracy @ $1` and `accuracy @ 10k tokens`, not pass@1. Compass adds tokens (more agent hops, more reads); the value claim must net those costs.

### 6. Anthropic-specific signal

- Anthropic publicly evaluates Claude Code on SWE-bench Verified, Terminal-Bench, and internal "Real-World Finance" (rubric + preference). They flag that autonomous-mode results may not reflect interactive token usage.
- No public Anthropic paper on evaluating *methodology layers*. The skill-creator A/B pattern is the closest reference.

## Recommended approach for Compass evaluation

**Phase A (validation):** Run Terminal-Bench Compass-vs-baseline. Identical model (Sonnet or Opus 4.7), identical tool set, identical turn budget. Report `pass@1`, `tokens / task`, `$ / task`. If Compass shows a Pareto improvement (better quality OR same quality at lower cost), proceed.

**Phase B (depth):** Add SWE-bench Pro and SWE-Lancer (both splits, especially managerial). The managerial split is the singular existing signal that hits spec / plan quality, not just code.

**Phase C (longer horizon):** SWE-EVO once Tier 1 confirms value. RE-Bench if METR access is available.

**Phase D (publishable contribution):** Design and run the structured-vs-vibe RCT that the field has not yet done. Same tasks, same model, same tools - only the methodology layer varies. Report process metrics (spec-first rate, plan-approval rate, lesson capture rate, escalation rate) alongside outcome metrics.

## Confidence and gaps

- HIGH confidence: Terminal-Bench, SWE-bench Pro, SWE-Lancer existence and general shape; A/B pitfalls; Pareto framing is the right metric.
- MEDIUM confidence: specific SOTA numbers cited above are moving targets; verify against the live leaderboard before quoting.
- UNCERTAIN: some 2025-2026 arxiv IDs returned by web search may be speculative; verify the paper exists before citing. Flagged inline.
- GAP: no published methodology-layer A/B with the rigor Compass would need. Compass would be defining its own reproducible protocol.

## Sources

Coding benchmarks: SWE-bench Pro arxiv 2509.16941, SWE-Lancer arxiv 2502.12115, LiveCodeBench leaderboard at artificialanalysis.ai, BigCodeBench arxiv 2406.15877.

Long-horizon: METR HCAST + RE-Bench at metr.org/blog and arxiv 2411.15114, Terminal-Bench at tbench.ai, SWE-EVO arxiv 2512.18470, AppWorld arxiv 2407.18901.

Methodology evaluation: ACM SIGKDD survey 10.1145/3711896.3736570, Holistic Agent Leaderboard arxiv 2510.11977, A Comprehensive Empirical Evaluation of Agent Frameworks arxiv 2511.00872, Catalogue of Evaluation Metrics ICSE 2026, Efficient Agents arxiv 2508.02694, Anthropic skill-creator on github.com/anthropics/claude-plugins-official, Anthropic engineering blog "Demystifying evals for AI agents" on anthropic.com/engineering.
