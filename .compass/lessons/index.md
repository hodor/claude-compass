---
title: "lessons"
type: domain
status: active
tags: [lessons, taxonomy]
summary: "lessons learned - 5-line bodies indexed by meta/lessons-catalog.yaml, files grouped per craft"
created: 2026-08-30
updated: 2026-08-30
---

# lessons

## Scope

Class here: lessons learned - 5-line bodies. This index and each domain's `index.md` are the surface agents grep first; `compass lessons` ranks via `meta/lessons-catalog.yaml`, the machine index off the hot path. The folders group the files by the craft each lesson teaches.

Domains: [[lessons/experiments/index|experiments]] (measurement design), [[lessons/hooks/index|hooks]], [[lessons/platform/index|platform]] (host and OS quirks), [[lessons/subagents/index|subagents]] (spawning and supervising agents), [[lessons/test-quality/index|test-quality]], [[lessons/vault-structure/index|vault-structure]] (vault mechanics). The root holds lessons whose craft has no second member yet, marked with a `taxonomy_hint` when one is plausible.

Archived lessons live in `archive/lessons/`.

## Lessons

- [[lessons/distribution/index|distribution]] (3 lessons) - installing, updating, and shipping Compass surfaces - what update owns, version lag, config copies in shipped prose
- [[lessons/experiments/index|experiments]] (6 lessons) - designing measurements and experiments that can actually falsify
- [[lessons/hooks/index|hooks]] (5 lessons) - hook registration, payloads, and firing semantics
- [[lessons/instructions/index|instructions]] (2 lessons) - writing instructions agents follow - prose economy, thresholds that become Goodhart targets
- [[lessons/pipeline/index|pipeline]] (3 lessons) - how work passes the human's gates - adversarial review before approval, walkthroughs in his words, verifying reversibility before acting unasked
- [[lessons/platform/index|platform]] (3 lessons) - host and OS quirks - line endings, shells, Windows
- [[lessons/subagents/index|subagents]] (7 lessons) - spawning, briefing, and supervising agents
- [[lessons/test-quality/index|test-quality]] (5 lessons) - what makes tests and their evaluation mean something
- [[lessons/vault-structure/index|vault-structure]] (11 lessons) - vault mechanics - indexes, links, discovery, placement
- [[LESSON-parallel-research-check-siblings-first]] - Research agents fanned out onto one spec should read sibling docs in the target domain folder first, and scope around what a sibling already owns
- [[LESSON-verify-exactness-past-a-compressing-layer]] - Headroom-compressed Bash output can drop words; verify exact text via Read or grep before judging it
- [[LESSON-verify-wiring-by-call-site-grep]] - A confident claim that a predicate or flag is wired up can be wrong from reading only its defining module; grep every call site first
