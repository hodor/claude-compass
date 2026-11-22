---
title: "What Recent Anthropic and LLM Research Says Compass Should Change"
type: research
status: draft
confidence: low
area: methodology
tags: [research, prior-art, anthropic, agents, memory, multi-agent, evals]
created: 2026-11-21
updated: 2026-11-21
author: "orchestrator"
summary: "planned axes for surveying Anthropic's engineering posts and 2025-2026 LLM agent research for changes Compass should make, awaiting the human's go"
---

# What Recent Anthropic and LLM Research Says Compass Should Change

Seven axes, run in parallel, each returning findings mapped to Compass's four north stars ([[SPEC-001-compass-vision-and-architecture]]): accuracy, perfect memory, near-zero cache misses, low token usage. A reviewer merges them into a ranked list of candidate changes, each naming the spec it touches or the new spec it needs.

> [!question] You decide
> Run research on these seven axes? Add your own questions below; they lead the list.

## Your questions

-

## Axes

1. **Every Anthropic engineering post, measured against Compass.** Sought in the full list at anthropic.com/engineering. Six posts are already cited in the vault (multi-agent research system, effective context engineering, demystifying evals, infrastructure noise, building effective agents); this axis reads every other post and rereads those six for parts no Compass document used.
2. **Claude Code and Agent SDK features that replace Compass machinery.** Sought in the Claude Code docs, changelog and Agent SDK docs: hooks, skills, subagents, the memory tool, plugins, `claude plugin eval`, context editing, compaction. The question is which Compass scripts or prompts the host now does natively.
3. **Agent memory and long-horizon context.** Sought in arXiv, OpenReview and Semantic Scholar, 2025-2026: memory architectures, compaction, retrieval over notes, sleep-time consolidation, context rot. Measured against the vault's tiers and hot path.
4. **Multi-agent orchestration and verification.** Sought in arXiv, OpenReview and lab posts: when spawning subagents helps or hurts, LLM-as-judge reliability, self-verification, blinded review. Measured against builder, tester, validator and reviewer.
5. **Spec-driven and plan-first coding agents.** Sought in GitHub and arXiv: rival frameworks (spec-kit, Kiro, BMAD, Agent OS and others not yet reviewed; GSD is covered in [[research/distribution/index|distribution]]) and benchmark evidence on planning, test-first and specs for coding agents.
6. **Other labs' and agent vendors' harness engineering.** Sought in engineering posts from OpenAI, Google DeepMind, Cognition, Cursor, Sourcegraph and Factory: harness design, tool design, context management, evaluation of agents.
7. **Gap mapping.** Sought in the vault itself: every finding from axes 1-6 checked against existing specs, research and lessons, so the result names only what Compass does not already do or decide.

## Grading

- [x] Findings are graded by source type (peer-reviewed, preprint, vendor post, practitioner post) and by whether a claim is measured or asserted. Unticking turns grading off; the research still runs.
