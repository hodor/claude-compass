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

- [[lessons/experiments/index|experiments]] (6 lessons) - designing measurements and experiments that can actually falsify
- [[lessons/hooks/index|hooks]] (5 lessons) - hook registration, payloads, and firing semantics
- [[lessons/platform/index|platform]] (3 lessons) - host and OS quirks - line endings, shells, Windows
- [[lessons/subagents/index|subagents]] (6 lessons) - spawning, briefing, and supervising agents
- [[lessons/test-quality/index|test-quality]] (4 lessons) - what makes tests and their evaluation mean something
- [[lessons/vault-structure/index|vault-structure]] (10 lessons) - vault mechanics - indexes, links, discovery, placement
- [[LESSON-adversarial-plan-review-before-build]] - Review specs/plans with 3 adversarial lenses before approval, and have reviewers measure against the real corpus, not opine
- [[LESSON-installer-removes-only-what-it-installed]] - Delete only what you installed or planned, by name; 'everything else here' always holds files that are not yours
- [[LESSON-remove-context-before-adding]] - Fix a behavior bug by removing the prose that trains it or adding a harness gate; added prose is the last resort and must be net-negative
- [[LESSON-self-update-corrections-lag-one-version]] - Self-update correction logic shipped in version N runs under the N-1 updater; it first fires on the following update
- [[LESSON-verify-the-inverse-not-the-forward-path]] - Cheap reversal licenses acting without asking; verify it on the inverse command, never by reading the forward one
- [[LESSON-walkthroughs-in-the-humans-words]] - Jargon in walkthroughs and paraphrase in specs both erase the human's own words where they must recognize themselves
