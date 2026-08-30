---
title: "Domain Taxonomy (marker docs, make-domain, link rules, suggestion surfacing, the useless-token measure, the migration)"
type: plan
status: draft
confidence: high
area: methodology
tags: [taxonomy, domains, sync, scope-notes, migration, measurement]
created: 2026-08-30
updated: 2026-08-30
author: "orchestrator"
summary: "two waves implementing ADR-022: mechanism (record-name and loop-guard fixes, folder-named marker docs, make-domain with scope-note mandate, ceiling and hint suggestions, link rules, tree restored), then the approved migration measured against the useless-tokens-per-task baseline"
depends_on: ["[[SPEC-022-vault-organized-per-domain]]", "[[ADR-022-domains-scope-notes-shallow-when-unsure]]", "[[RESEARCH-taxonomy-for-unambiguous-placement]]"]
lessons: ["[[LESSON-adversarial-plan-review-before-build]]", "[[LESSON-wikilink-validator-skip-code]]", "[[LESSON-revert-to-prove-a-regression-test]]", "[[LESSON-blind-the-author-in-self-validation]]"]
---

# Domain Taxonomy

## Goal

The vault's filesystem is the taxonomy and placement is a mechanical procedure enforced by harness: domain lines at the root, scope notes at the point of doubt, the folder itself as the listing (`ls` for contents, the marker doc for meaning, `compass tree` for the whole picture), shallow-when-unsure, hints surfaced as suggestions everywhere, and the spec's metric - useless tokens loaded per task - defined, baselined, and driven down by the migration. Implements every D of [[ADR-022-domains-scope-notes-shallow-when-unsure]].

## Ripple

From [[RESEARCH-taxonomy-for-unambiguous-placement]] (ripple axis): nesting classification, next-num, make-unit path checks, sizing reconciliation, and vaultgraph containment already tolerate arbitrary depth. Touched: `vaultlib.py` (record names, marker-doc recognition), `sync.py` (loop guard, link forms, count refresh), `validate.py` (ceiling, empty_scope, hints-pending, domain fields), new `make_domain.py`, `make_unit.py` (stops writing Children), `tree.py` restored, and eight skills/rules. Inbound edges recorded in the research doc's ripple findings.

## What We're NOT Doing

- Materialized member listings anywhere: no per-folder Children blocks, no type-dir marker docs. The root `index.md` is the sole maintained listing - the preloaded boot map.
- LLM summaries (the held layer of [[SPEC-005-index-auto-maintained-and-mirrored-per-folder]] stays held; its listing half is superseded by ADR-022 D-04's read-live design, recorded in TASK-112).
- Fully automatic moves - reorganization is suggested by the harness and applied only on the human's approval.
- SPEC-022 D-02 partially deferred: plans and decisions group in a later round once the spec shape settles; lessons are excluded by SPEC-022's own Non-Goals (catalog-indexed).
- Backfilling existing bare-stem links (they stay valid; only ambiguity warns).
- Poly-hierarchy. One home per document, ever.

## Wave 1 (detailed): mechanism

- [ ] TASK-109: vault-relative record names for nested artifacts (same-named domains across type dirs stop cross-contaminating child counts), in-place `(folder, N children)` count refresh on root-index lines, the sync loop guard narrowed to exact root-relative paths, and folder marker docs named after their folder (`<folder>/<folder>.md` recognized alongside `index.md` in vaultlib; promote/make-unit emit the new name; the compass-cli unit's marker renamed) so folder links resolve by basename - complexity: L, files: [plugin/cli/vaultlib.py, plugin/cli/commands/sync.py, plugin/cli/commands/promote.py, plugin/cli/commands/make_unit.py, plugin/cli/tests/test_sync.py, plugin/cli/tests/test_vaultlib.py], decisions: [SPEC-022-vault-organized-per-domain/D-03, ADR-022-domains-scope-notes-shallow-when-unsure/D-02, ADR-022-domains-scope-notes-shallow-when-unsure/D-05]
  - Automated (red-first): same-named domains in specs/ and research/ get disjoint child counts; stale counts on existing folder lines refresh in place without touching human descriptions; a nested marker-doc agent-write triggers sync and a capture signal (regression proven by revert); `reindex.md`-style near-name files no longer swallowed; both marker names classify identically; full suite green.
  - Manual: run sync on this vault; confirm folder-line counts correct and no other index line changed.
- [ ] TASK-110: `compass make-domain <type-dir>/<path>` (any depth, dry-run default, `--apply`, mandatory `--reason` and `--class-here`, vault-wide domain-name collision refusal, sizing-logged, template = a marker doc named after its folder with `status: active` frontmatter + `## Scope` only); validate gains `EXPECTED_FIELDS["domain"]`, `folder_over_ceiling` (path-counted, taxonomy-governed dirs only, tunable default 12), `empty_scope`, and the `taxonomy_hints: N pending` suggestion line - complexity: M, after 109, files: [plugin/cli/commands/make_domain.py, plugin/cli/commands/validate.py, plugin/cli/maincli.py, plugin/cli/tests/test_make_domain.py], decisions: [SPEC-022-vault-organized-per-domain/D-02, SPEC-022-vault-organized-per-domain/D-07, ADR-022-domains-scope-notes-shallow-when-unsure/D-01, ADR-022-domains-scope-notes-shallow-when-unsure/D-03]
  - Automated (red-first): nested creation; refusal without --class-here; refusal of a name used as a domain in another type dir; ceiling fires at 13 not 12, on type dirs themselves, never on lessons/plans/decisions; empty_scope on a Scope with no Class-here line; hints-pending names the files; a domainless small vault emits none of these; warnings never change the exit code.
  - Manual: create and `--undo`-inspect one scratch domain end to end; read the template as a human.
- [ ] TASK-111: link rules in code and prose - `_link_name` vault-relative for root folder-marker records; a red-first test reproducing the specs/research same-name collision proves the ambiguity warning fires; the bare-link warning limited to actually-ambiguous cases; obsidian + wikilinks rule carry the forward-only path-qualified convention - complexity: M, after 109, files: [plugin/cli/commands/sync.py, plugin/cli/commands/validate.py, plugin/cli/tests/test_sync.py, plugin/skills/obsidian/SKILL.md, plugin/templates/rules/wikilinks.md], decisions: [ADR-022-domains-scope-notes-shallow-when-unsure/D-05]
  - Automated (red-first): the reproduced collision warns; path-qualified links below two same-numbered domain children validate clean; unique bare stems stay warning-free.
  - Manual: read the rewritten linking section start to finish for contradiction with its own examples.
- [ ] TASK-112: skill and record contracts - spec/specs/vision place into the taxonomy at creation with shallow-when-unsure, the small-vault do-nothing path, and `taxonomy_hint:` on genuine doubt; consolidate takes hints as its queue and clears on move or confirm-fine; obsidian carries scope-note authoring, the folder-is-the-listing convention, and the marker-naming convention (Children mandate retired; existing sections removed as folders are touched); promote-spec's false refusal claim corrected; methodology/setup trees rewritten; ADR-021 stamped `amended_by`; SPEC-005 status updated (listing half superseded, LLM layer held) - complexity: M, after 110, files: [plugin/skills/spec/SKILL.md, plugin/skills/specs/SKILL.md, plugin/skills/vision/SKILL.md, plugin/skills/consolidate/SKILL.md, plugin/skills/obsidian/SKILL.md, plugin/skills/promote-spec/SKILL.md, plugin/skills/methodology/SKILL.md, plugin/skills/setup/SKILL.md, .compass/decisions/ADR-021-index-speaks-in-domains.md, .compass/specs/SPEC-005-index-auto-maintained-and-mirrored-per-folder.md], decisions: [SPEC-022-vault-organized-per-domain/D-01, SPEC-022-vault-organized-per-domain/D-04, SPEC-022-vault-organized-per-domain/D-05, ADR-022-domains-scope-notes-shallow-when-unsure/D-04]
  - Automated: grep gates - no skill claims "flat, one file each", the promote refusal, or mandates a Children section; the hint field named in the spec skill and both consumers.
  - Manual: read the spec skill's placement step as the busy-agent walkthrough; the obvious case costs zero extra reads.
- [ ] TASK-116: restore `compass tree` as the whole-tree view with per-entry summaries, computed at invocation, registered in maincli and named in the pipeline-rules Capabilities line - complexity: S, after 109, files: [plugin/cli/commands/tree.py, plugin/cli/maincli.py, plugin/templates/rules/compass-pipeline.md], decisions: [ADR-022-domains-scope-notes-shallow-when-unsure/D-04]
  - Automated: tree renders nested domains with summaries (fixture with a two-level domain); the usage record counts it.
  - Manual: run it on this vault; the output answers "what specs exist" in one command.

## Wave 2 (after the human approves the migration diff): this vault

- [ ] TASK-117: define and baseline the useless-token measure - per task, tokens of vault content loaded into context versus tokens whose content the task's output used; instrumented over the 5 most recent real tasks in this vault before any file moves, re-measured on equivalent tasks after TASK-114 - complexity: M, after 112, decisions: [ADR-022-domains-scope-notes-shallow-when-unsure/D-06]
  - Automated: the measure's definition and per-task numbers recorded in the plan; baseline complete before 114 begins.
  - Manual: the definition survives one adversarial read - a token the output paraphrases counts as used, a token merely loaded does not.
- [ ] TASK-113: regenerate the domain proposal under ADR-022 - vault-unique bare names, scope notes drafted per domain with class-here digests as the domain summaries, orthogonality and the depth gradient demonstrated against the corpus (count unforced), expected useless-token and root-index deltas computed - presented as a diff for approval - complexity: S, after 117, decisions: [SPEC-022-vault-organized-per-domain/D-06, SPEC-022-vault-organized-per-domain/D-09]
  - Automated: proposal names pass make-domain's collision check in dry-run.
  - Manual: the human approves the diff - the explicit gate; nothing further in Wave 2 proceeds without it.
- [ ] TASK-114: apply the approved migration domain-by-domain (make-domain / promote / git mv), replace each migrated member line in the root index with its domain line, `compass validate` 0 errors after each domain, sizing rows for every shape change - complexity: L, after 113
  - Automated: the useless-token measure re-run against the baseline - the migration passes when the useless share drops and the hot path clears its cap; a shortfall is reported with the named follow-up decision, never declared passed. Data audit: every root-index line removed has its artifact present at its new path with `summary:` intact.
  - Manual (pre-registered, blind): finder drill - 10 moved documents sampled mechanically, each to a fresh subagent holding only the root index and the doc's summary line, first-click domain recorded, bar >= 8/10; filer drill - the Problem paragraphs of the 5 most recent specs, each to 3 fresh agents with only root index + scope notes, bar unanimous on >= 4/5. Every miss produces a Class-here or Class-elsewhere line and the failing item re-runs once. Results recorded as the first LLM-filer consistency datum.
- [ ] TASK-115: version bump, push, fleet self-update verify on one vault; handoff naming the drill and token numbers - complexity: S, after 114
  - Automated: a fleet vault pulls the release; doctor 0 FAIL there.
  - Manual: handoff read-through.

## Verification gates

Suite green at every task; `compass validate` 0 errors after every migration step; `compass decisions ADR-022-domains-scope-notes-shallow-when-unsure` parses 6 trackable rows; `compass coverage PLAN-016-domain-taxonomy` passes with SPEC-022 D-02's partial deferral stated above; the Data-rule audit on the migration diff.
