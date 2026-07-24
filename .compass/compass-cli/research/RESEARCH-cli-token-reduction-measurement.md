---
title: Measuring SPEC-004's 80% Bookkeeping-Token Reduction
type: research
status: active
confidence: high
area: methodology
tags: [token-efficiency, measurement, hooks, cli, hypothesis-confirmed]
created: 2026-06-14
updated: 2026-06-14
depends_on: ["[[SPEC-004-mechanical-work-off-the-agent-budget]]", "[[ADR-005-compass-cli-for-mechanical-work]]"]
---

# Measuring SPEC-004's 80% Bookkeeping-Token Reduction

SPEC-004 hypothesized that moving vault bookkeeping from an LLM hook to a deterministic CLI cuts per-session bookkeeping tokens by **at least 80%** with **zero loss of vault integrity**. Both halves are confirmed.

## The token half: ~99.8% reduction (confirmed, exceeds 80%)

Every fire of the old `type: agent` PostToolUse hook forced the model to read, before doing any work:

| Input the agent hook loaded per fire | Tokens (chars/4) |
|---|---|
| Hook prompt (`hooks.json`) | 94 |
| `index-sync` skill body (the agent must read it to execute) | 3,051 |
| **Floor per fire (before reading any vault file or reasoning)** | **3,145** |

The agent then additionally read `index.md`, each changed file's frontmatter, and emitted tool calls and reasoning to do the edits - realistically another 1,000-3,000 tokens per fire. So a real per-fire cost is ~4,000-6,000 tokens.

The `type: command` hook produces `{"suppressOutput": true}` (24 bytes, ~6 tokens) and, because of `suppressOutput`, the agent sees nothing. Per-fire agent cost: ~0.

Reduction on the floor alone: (3,145 - 6) / 3,145 = **99.8%**. A full session amplifies this: this very session fired the agent hook ~8 times on vault edits, a floor of ~25,000 tokens of bookkeeping context that the command hook removes entirely.

### Why the estimate is safe

The 3,051 figure is a chars/4 approximation, not a real tokenizer count. It does not matter: the reduction is ~99.8%, so even a 30% tokenizer error leaves the result far above the 80% threshold. The comparison is also a per-fire structural floor, not a full two-session A/B - but that is conservative, because the unmeasured part (the agent's variable reasoning) belongs to the *baseline* arm only. Adding it makes the reduction larger, never smaller. The 80% bar is robustly cleared.

## The integrity half: zero loss, net positive (confirmed)

`compass validate` is clean on the real vault (zero false positives). `compass sync` is idempotent across runs (byte-identical `tag-index.yaml`). Golden behaviors are pinned in the test suite (49 tests): append-only index, archived-skip, human-description preservation, tag-index format, cap warnings, log cleanup, loop guard, vault guard, never-exit-2.

The CLI is not merely equal to the LLM hook - it is **more correct**. On first run against the real vault it found and fixed a defect the LLM hook had left: the `2026-06-10` handoff existed on disk but was never linked in `index.md`. A probabilistic hook had silently missed it; the deterministic scan caught it.

## Caveat retained

A live two-session A/B (one arm each, identical task) would convert the structural floor into an end-to-end measured number. It is not required to accept the hypothesis here - the per-fire floor alone exceeds the threshold by more than two orders of magnitude - but it is the cleanest possible confirmation and is worth running opportunistically. Logged so the claim is not overstated, in the spirit of the falsified SPEC-003 30% number (`[[LESSON-tag-index-trades-cost-for-directed-retrieval]]`).

## Verdict

SPEC-004 hypothesis: **confirmed.** Token reduction ~99.8% (target >=80%); integrity preserved and improved.
