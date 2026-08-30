---
title: "Domain Taxonomy (the folder is the listing, make-domain, link rules, suggestion surfacing, the migration)"
type: plan
status: draft
confidence: high
area: methodology
tags: [taxonomy, domains, sync, scope-notes, migration, per-folder-index]
created: 2026-08-30
updated: 2026-08-30
author: "orchestrator"
summary: "implement ADR-022 in two waves: mechanism (record-name and loop-guard fixes, make-domain with scope-note mandate, vault-unique names, ceiling and hint suggestions, link rules, folder-is-the-listing contracts, tree restored), then the human-approved migration with a hot-path pass bar and pre-registered falsifiable drills"
depends_on: ["[[SPEC-022-vault-organized-per-domain]]", "[[ADR-022-domains-scope-notes-shallow-when-unsure]]", "[[RESEARCH-taxonomy-for-unambiguous-placement]]"]
lessons: ["[[LESSON-adversarial-plan-review-before-build]]", "[[LESSON-wikilink-validator-skip-code]]", "[[LESSON-revert-to-prove-a-regression-test]]", "[[LESSON-blind-the-author-in-self-validation]]"]
---

# Domain Taxonomy

## Goal

The vault's filesystem becomes the taxonomy and placement becomes a mechanical procedure enforced by harness: domain lines at the root, scope notes at the point of doubt, the folder itself as the listing (`ls` for contents, index for meaning, `compass tree` for the whole picture), shallow-when-unsure, hints surfaced as suggestions everywhere. Implements every D of [[ADR-022-domains-scope-notes-shallow-when-unsure]].

## Ripple

From [[RESEARCH-taxonomy-for-unambiguous-placement]] (ripple axis, 19 findings): nesting classification, next-num, make-unit path checks, sizing reconciliation, and vaultgraph containment already tolerate arbitrary depth. Touched: `vaultlib.py` (record names), `sync.py` (loop guard, link forms, count refresh), `validate.py` (ceiling, empty_scope, hints-pending, domain fields), new `make_domain.py`, `make_unit.py` (stops writing Children), `tree.py` restored, and eight skills/rules. Inbound edges recorded in the research doc's Finding 19.

## What We're NOT Doing

- Materialized member listings anywhere (SPEC-022 D-08): no per-folder Children blocks, no type-dir indexes. The root `index.md` is the sole maintained listing - it is the preloaded boot map.
- LLM summaries (SPEC-005's held layer stays held; its non-LLM listing half is superseded by ADR-022 D-07's read-live design, recorded in TASK-112).
- Fully automatic moves - reorganization is suggested by the harness and applied only on Roger's approval (SPEC-022 D-07; ADR-021 D-03).
- SPEC-022 D-02 partially deferred: plans and decisions group in a later round once the spec shape settles; lessons are excluded by SPEC-022's own Non-Goals (catalog-indexed).
- Backfilling existing bare-stem links (ADR-022 D-08: they stay valid; only ambiguity warns).
- Poly-hierarchy. One home per document, ever.

## Wave 1 (detailed): mechanism

- [ ] TASK-109: vault-relative record names for nested artifacts (same-named domains across type dirs stop cross-contaminating child counts), in-place `(folder, N children)` count refresh on root-index lines, the sync loop guard narrowed to exact root-relative paths, and folder marker docs named after their folder (`<folder>/<folder>.md` recognized alongside `index.md` in vaultlib; promote/make-unit emit the new name; the compass-cli unit's marker renamed) so Obsidian resolves folder links by basename instead of spawning stray notes - complexity: L, files: [plugin/cli/vaultlib.py, plugin/cli/commands/sync.py, plugin/cli/tests/test_sync.py, plugin/cli/tests/test_vaultlib.py], decisions: [SPEC-022-vault-organized-per-domain/D-03, ADR-022-domains-scope-notes-shallow-when-unsure/D-08, ADR-022-domains-scope-notes-shallow-when-unsure/D-10]
  - Automated (red-first): same-named domains in specs/ and research/ get disjoint child counts; stale counts on existing folder lines refresh in place without touching human descriptions; nested index.md agent-write now triggers sync and a capture signal (regression proven by revert); `reindex.md`-style near-name files no longer swallowed; full suite green.
  - Manual: run sync on this vault; confirm folder-line counts correct and no other index line changed.
- [ ] TASK-110: `compass make-domain <type-dir>/<path>` (any depth, dry-run default, `--apply`, mandatory `--reason` and `--class-here`, vault-wide domain-name collision refusal, sizing-logged, template = frontmatter with `status: active`, an `aliases: ["<folder-name>"]` entry so Obsidian resolves the bare link to the index instead of spawning an empty stray note, + `## Scope` only); validate gains `EXPECTED_FIELDS["domain"]`, `folder_over_ceiling` (path-counted, taxonomy-governed dirs only, tunable default 12), `empty_scope`, and the `taxonomy_hints: N pending` suggestion line - complexity: M, after 109, files: [plugin/cli/commands/make_domain.py, plugin/cli/commands/validate.py, plugin/cli/maincli.py, plugin/cli/tests/test_make_domain.py], decisions: [SPEC-022-vault-organized-per-domain/D-02, SPEC-022-vault-organized-per-domain/D-07, ADR-022-domains-scope-notes-shallow-when-unsure/D-01, ADR-022-domains-scope-notes-shallow-when-unsure/D-02, ADR-022-domains-scope-notes-shallow-when-unsure/D-05, ADR-022-domains-scope-notes-shallow-when-unsure/D-06, ADR-022-domains-scope-notes-shallow-when-unsure/D-09]
  - Automated (red-first): nested creation (`specs/vault-structure/sync-machinery`); refusal without --class-here; refusal of a name used as a domain in another type dir; ceiling fires at 13 not 12, on type dirs themselves (path-counted), never on lessons/plans/decisions; empty_scope on a Scope with no Class-here line; hints-pending line appears when hints exist and names the files; a validate run on a domainless small vault emits none of these; warnings never change the exit code.
  - Manual: create and `--undo`-inspect one scratch domain end to end; read the template as a human.
- [ ] TASK-111: link rules land in code and prose - `_link_name` vault-relative for root folder-index records; a red-first test reproducing the specs/research same-name collision proves the ambiguity warning actually fires (research rated this code-traced only); validate's bare-link warning limited to actually-ambiguous cases; obsidian + wikilinks rule state D-08's forward-only convention - complexity: M, after 109, files: [plugin/cli/commands/sync.py, plugin/cli/commands/validate.py, plugin/cli/tests/test_sync.py, plugin/skills/obsidian/SKILL.md, plugin/templates/rules/wikilinks.md], decisions: [ADR-022-domains-scope-notes-shallow-when-unsure/D-08]
  - Automated (red-first): the reproduced collision warns; path-qualified links below two same-numbered domain children validate clean; bare stems that are unique stay warning-free.
  - Manual: read the rewritten linking section start to finish for contradiction with the examples it shows.
- [ ] TASK-112: skill and record contracts - spec/specs/vision place into the taxonomy at creation with the shallow-when-unsure rule, the small-vault do-nothing path, and `taxonomy_hint:` on genuine doubt; consolidate S1 takes hints as queue and clears on move or confirm-fine; obsidian gains scope-note authoring, the folder-is-the-listing convention (ls for contents, index for meaning; Children mandate retired, `make_unit.py` stops writing the section, existing sections removed when their folder is next touched), and the folder-alias convention (every folder artifact's index.md carries `aliases: ["<folder-name>"]`, stamped by the spec-skill template, `promote`, and `make-unit`, so Obsidian click-through works instead of spawning empty stray notes); promote-spec's false refusal claim corrected; methodology/setup trees rewritten; ADR-021 stamped `amended_by` with D-01/D-04 annotations; SPEC-005 status updated (listing half superseded by ADR-022 D-07's read-live design, LLM layer still held) - complexity: M, after 110, files: [plugin/skills/spec/SKILL.md, plugin/skills/specs/SKILL.md, plugin/skills/vision/SKILL.md, plugin/skills/consolidate/SKILL.md, plugin/skills/obsidian/SKILL.md, plugin/skills/promote-spec/SKILL.md, plugin/skills/methodology/SKILL.md, plugin/skills/setup/SKILL.md, plugin/cli/commands/make_unit.py, .compass/decisions/ADR-021-index-speaks-in-domains.md, .compass/specs/SPEC-005-index-auto-maintained-and-mirrored-per-folder.md], decisions: [SPEC-022-vault-organized-per-domain/D-01, SPEC-022-vault-organized-per-domain/D-04, SPEC-022-vault-organized-per-domain/D-05, SPEC-022-vault-organized-per-domain/D-08, ADR-022-domains-scope-notes-shallow-when-unsure/D-03, ADR-022-domains-scope-notes-shallow-when-unsure/D-04, ADR-022-domains-scope-notes-shallow-when-unsure/D-07, ADR-022-domains-scope-notes-shallow-when-unsure/D-09, ADR-022-domains-scope-notes-shallow-when-unsure/D-11]
  - Automated: grep gates - no skill claims "flat, one file each", the promote refusal, or mandates a Children section; hint field named in spec skill AND both consumers; make-unit's template test updated to the listing-free index.
  - Manual: read the spec skill's placement step as the busy-agent walkthrough; confirm the obvious case costs zero extra reads.
- [ ] TASK-116: restore `compass tree` as the whole-tree view with per-entry summaries, computed at invocation (git revert of the ADR-017 retirement plus the summary column, registered in maincli and named in the pipeline-rules Capabilities line) - complexity: S, after 109, files: [plugin/cli/commands/tree.py, plugin/cli/maincli.py, plugin/templates/rules/compass-pipeline.md], decisions: [ADR-022-domains-scope-notes-shallow-when-unsure/D-11]
  - Automated: tree renders nested domains with summaries (fixture with a two-level domain); usage record counts it.
  - Manual: run it on this vault; the output answers "what specs exist" in one command.

## Wave 2 (after Roger approves the migration diff): this vault

- [ ] TASK-113: regenerate the domain proposal under ADR-022 - vault-unique bare names (the distribution collision renamed), scope notes drafted per domain with class-here digests as the domain summaries, orthogonality and the depth-generality gradient demonstrated against the corpus (count unforced), expected root-index token delta computed - and present as a diff for approval - complexity: S, after 112, decisions: [SPEC-022-vault-organized-per-domain/D-06, SPEC-022-vault-organized-per-domain/D-09]
  - Automated: proposal names pass make-domain's collision check in dry-run.
  - Manual: Roger approves the diff - the explicit gate; nothing in Wave 2 proceeds without it.
- [ ] TASK-114: apply the approved migration domain-by-domain (make-domain / promote / git mv), replace each migrated member line in the root index with its domain line, `compass validate` 0 errors after each domain, sizing rows for every shape change - complexity: L, after 113
  - Automated: hot path measured before/after with a stated pass bar - under 5,000 tokens after migration; if the bar cannot be met because the remainder is catalog weight, the wave is not done: the result is reported with the named follow-up decision (catalog tiering), not declared passed. Never-destroy audit: every root-index line removed has its artifact present at its new path with `summary:` frontmatter intact (the removed line was a copy of that summary).
  - Manual (pre-registered, blind per [[LESSON-blind-the-author-in-self-validation]]): finder drill - 10 MOVED documents sampled mechanically, each given to a fresh subagent holding only the root index and the doc's summary line, first-click domain recorded, bar >= 8/10; filer drill - the Problem paragraphs of the 5 most recent specs, each to 3 fresh agents with only root index + scope notes, bar unanimous on >= 4/5. Every miss produces a Class-here or Class-elsewhere line and the failing item re-runs once. Results recorded in the plan as the first LLM-filer consistency datum.
- [ ] TASK-115: version bump, push, fleet self-update verify on one vault; handoff naming the drill numbers - complexity: S, after 114
  - Automated: fleet vault pulls the release; doctor 0 FAIL there.
  - Manual: handoff read-through.

## Verification gates

Suite green at every task; `compass validate` 0 errors after every migration step; `compass decisions ADR-022-domains-scope-notes-shallow-when-unsure` parses 11 trackable rows; `compass coverage PLAN-016-domain-taxonomy` passes with every ADR-022 D claimed and SPEC-022 D-02's partial deferral stated above; the never-destroy audit on the migration diff.
