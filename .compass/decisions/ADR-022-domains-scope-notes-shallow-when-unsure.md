---
title: "Domain Taxonomy: One Characteristic Per Level, index.md as Every Folder's Doc, the Folder as the Listing, Useless-Tokens as the Metric"
type: decision
status: accepted
confidence: high
area: methodology
tags: [taxonomy, domains, scope-notes, namespaces, wikilinks, measurement]
created: 2026-08-30
updated: 2026-08-30
author: "orchestrator"
summary: "one characteristic per level with factoring on the second value, index.md in every folder carrying identity and scope only, generated links written as piped full paths so they click, the folder as the listing with compass tree as the JIT whole-view, hints and splits surfaced as suggestions, and useless-tokens-per-task defined fresh as the metric"
depends_on: ["[[SPEC-022-vault-organized-per-domain]]", "[[RESEARCH-taxonomy-for-unambiguous-placement]]", "[[ADR-021-index-speaks-in-domains]]", "[[ADR-006-hybrid-hierarchy-implementation]]"]
---

# Domain Taxonomy

## Context

[[SPEC-022-vault-organized-per-domain]]: the filesystem is the taxonomy; the folder is the listing and the index carries the meaning; complexity grows with depth; reorganization is suggested, and most cases are done behind the scenes when the obvious need arrives; the goal metric is useless tokens loaded per task going to zero. [[RESEARCH-taxonomy-for-unambiguous-placement]]: CS applies classification as delegated namespaces - hop count is the cost unit, a folder's doc is a RAPTOR-style summary node (answer or descend), generality belongs at the parent and autonomy at the child, names are load-bearing; the human-classification literature supplies scope notes, one-home-plus-facets, shallow-when-unsure, warrant, and the 10-60% filer disagreement every mechanism must tolerate.

## Decisions

- **D-01:** One characteristic per level ([[SPEC-022-vault-organized-per-domain]] D-09). A folder's name states the value it fixes and reads as the shared subject of everything below it; siblings are values of one characteristic - orthogonal by construction. A folder factors when the second value arrives: `live-jazz` recordings split into a setting level (live, studio) and a genre level (jazz, rock) the day the first studio-jazz or live-rock item exists, never before. Depth is free; a name widens only when its contents widen. No forced count. Names are unique among siblings and may recur on other branches (`network/cache`, `gpu-hardware/cache`) - the path identifies a domain. Domain names stay the human's call; grouping moves are suggested, and the obvious ones run behind the scenes (SPEC-022 D-07).
- **D-02:** Every folder's doc is `index.md` - domains, folder specs, units, and the type dirs themselves (SPEC-022 D-05) - one predictable location, carrying identity and scope only: frontmatter plus a `## Scope` section (SPEC-022 D-08: the index is the meaning). Links that generated surfaces emit are piped full paths - `[[specs/distribution/index|distribution]]` - so they click through in Obsidian, which resolves basenames and paths but never a bare folder name; hand-written links resolve by the existing glob rule.
- **D-03:** Scope notes answer placement doubt where it occurs ([[RESEARCH-taxonomy-for-unambiguous-placement]]: DDC class-here/class-elsewhere, MSC's binding and advisory tiers): `Class here:` lines, `Class elsewhere: X -> [[domain]]` redirects, `See also:` pointers - authored judgment, never regenerated. One physical home per document; tags are the cross-cutting axis ([[ADR-004-hierarchical-specs-with-facets]]). Under doubt, filing stops at the certain ancestor (research: top-down error propagation), and genuine uncertainty is recorded as a `taxonomy_hint:` in frontmatter at creation (SPEC-022 D-04), surfaced as a pending-hints suggestion by validate and checkup in every vault and consumed as consolidate's work queue (SPEC-022 D-07).
- **D-04:** The folder is the listing; no index materializes members (SPEC-022 D-08). Listings are read live; `compass tree` is the whole-view with summaries, computed at invocation ([[ADR-018-graph-queries-jit-over-markdown]]'s principle applied to listings); the `## Children` convention retires. The root `index.md` keeps its entry lines: it is the map preloaded into every session's context, the one surface a tool call cannot precede. A childless spec stays flat, gaining the folder shape with its first child.
- **D-05:** Nested records carry vault-relative names, and the sync loop guard matches exact root-relative paths ([[RESEARCH-taxonomy-for-unambiguous-placement]] ripple findings: same-named branches cross-contaminate child counts, and the endswith guard silently swallows every nested index.md write, costing sync runs and capture signals). New links below a domain are written path-qualified ([[ADR-006-hybrid-hierarchy-implementation]]'s rule, extended); existing bare-stem links stay valid, warned only on real ambiguity.
- **D-06:** The metric is useless tokens loaded per task, driven toward zero; the hot-path cap is only a trigger (SPEC-022 Desired Outcome). No literature instrument measures load-versus-use, so the measure is defined fresh - per task, vault tokens brought into context versus tokens the task's output used - baselined before the migration and re-measured after. A migration that shrinks the root index but not the useless-token share is not done.

## Open choices (proposed, decided at plan review)

- `compass make-domain` refuses creation without a `--class-here` scope line, and validate warns `empty_scope` - so no domain is born with a blank promise at the point of doubt. Recommendation: yes; an empty Scope reads as "nothing belongs here".
- Folder split suggestions trigger at a child-count ceiling, default 12, tunable. The number is a practitioner heuristic (Johnny.Decimal's ceilings), not research-derived. Recommendation: keep as a tunable default.
- A `taxonomy_hint` clears either by a move or by "confirmed fine where it sits". Recommendation: yes; otherwise hints accumulate as permanent noise.
- Citation order (which characteristic divides first) is chosen most-stable-first and refactored by suggestion when misfit shows. A heuristic, not a rule; the Wikipedia comparison in the plan tests it.

## Consequences

- Filing is a procedure: root lines, then a domain's Scope on doubt, then shallower, then a hint. Finding is the same walk down, one index.md per hop, `ls` between hops.
- One write point per change: the file moves, nothing else updates; nothing but the root map is maintained, so nothing else can go stale.
- The type-dir-first shape with domains nested inside is package-by-layer, which the software literature associates with lower cohesion than package-by-feature; the tag-index is the cross-cutting compensation, and the tension is recorded, not resolved.
- Nothing depends on filers agreeing; the migration's blind drills produce the first LLM-filer consistency datum.
