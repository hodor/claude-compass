---
title: "Domain Taxonomy"
type: plan
status: draft
confidence: high
area: methodology
tags: [taxonomy, domains, sync, scope-notes, migration, measurement]
created: 2026-08-30
updated: 2026-08-30
author: "orchestrator"
summary: "two waves: the mechanism (record-name and loop-guard fixes, make-domain, link rules, skill contracts, compass tree), then this vault's migration, gated on the human's diff approval and judged by the useless-token baseline and blind drills"
depends_on: ["[[SPEC-022-vault-organized-per-domain]]", "[[ADR-022-domains-scope-notes-shallow-when-unsure]]", "[[RESEARCH-taxonomy-for-unambiguous-placement]]"]
lessons: ["[[LESSON-adversarial-plan-review-before-build]]", "[[LESSON-wikilink-validator-skip-code]]", "[[LESSON-revert-to-prove-a-regression-test]]", "[[LESSON-blind-the-author-in-self-validation]]"]
---

# Domain Taxonomy

## Goal

Implement [[SPEC-022-vault-organized-per-domain]] and [[ADR-022-domains-scope-notes-shallow-when-unsure]], and migrate this vault first.

## The waves

1. **Mechanism** - the machinery the taxonomy needs: fixed record names and loop guard, `make-domain`, link rules, placement contracts in the skills, `compass tree`. Ends with everything live and tested, no file moved.
2. **This vault migrates** - baseline the useless-token measure, build the proposal by the atomic rule and score it against Wikipedia, the human approves the diff, files move domain-by-domain, and the blind drills plus the re-measure judge the result. Ends with the release on the fleet.

## Not in this plan

- SPEC-022 D-02 applies the taxonomy to everything in the vault; this plan covers specs and research, and defers grouping plans/ and decisions/ to a later round. Lessons are excluded by the spec's Non-Goals.

## Wave 1: mechanism

- [ ] TASK-109: vault-relative record names for nested artifacts (same-named branches stop cross-contaminating child counts), in-place `(folder, N children)` count refresh on root-index lines, the sync loop guard narrowed to exact root-relative paths, and generated links written as piped full paths (`[[specs/distribution/index|distribution]]`) - complexity: M, files: [plugin/cli/vaultlib.py, plugin/cli/commands/sync.py, plugin/cli/tests/test_sync.py, plugin/cli/tests/test_vaultlib.py], decisions: [SPEC-022-vault-organized-per-domain/D-03, ADR-022-domains-scope-notes-shallow-when-unsure/D-01]
  - Automated (red-first): same-named domains in specs/ and research/ get disjoint child counts; stale counts refresh in place without touching human descriptions; generated links are piped full paths that resolve; a nested index.md agent-write triggers sync and a capture signal (regression proven by revert); `reindex.md`-style near-name files no longer swallowed; full suite green.
  - Manual: run sync on this vault; folder-line counts correct, no other index line changed.
- [ ] TASK-110: `compass make-domain <type-dir>/<path>` - any depth, dry-run default, `--apply`, mandatory `--reason` and `--class-here`, sibling-collision refusal with name reuse across branches, sizing-logged, template = `index.md` with `status: active` frontmatter + `## Scope`; validate gains `EXPECTED_FIELDS["domain"]`, `folder_over_ceiling` (path-counted, taxonomy-governed dirs only, tunable default 12), `empty_scope`, and the `taxonomy_hints: N pending` suggestion line - complexity: M, after 109, files: [plugin/cli/commands/make_domain.py, plugin/cli/commands/validate.py, plugin/cli/maincli.py, plugin/cli/tests/test_make_domain.py], decisions: [SPEC-022-vault-organized-per-domain/D-02, SPEC-022-vault-organized-per-domain/D-04, SPEC-022-vault-organized-per-domain/D-07]
  - Automated (red-first): nested creation; refusal without --class-here; sibling collision refused while `specs/network/cache` and `specs/gpu-hardware/cache` coexist and resolve path-qualified; ceiling fires at 13 not 12, on type dirs themselves, never on lessons/plans/decisions; empty_scope on a Scope with no Class-here line; hints-pending names the files; a domainless small vault emits none of these; warnings never change the exit code.
  - Manual: create and `--undo` one scratch domain end to end; read the template as a human.
- [ ] TASK-111: link rules in code and prose - `_link_name` piped full paths for folder records; a red-first test reproducing the specs/research same-name collision proves the ambiguity warning fires; the bare-link warning limited to actually-ambiguous cases; obsidian + wikilinks rule carry the path-qualified convention for new links below domains (forward-only; existing links untouched) - complexity: M, after 109, files: [plugin/cli/commands/sync.py, plugin/cli/commands/validate.py, plugin/cli/tests/test_sync.py, plugin/skills/obsidian/SKILL.md, plugin/templates/rules/wikilinks.md], decisions: [ADR-022-domains-scope-notes-shallow-when-unsure/D-01]
  - Automated (red-first): the reproduced collision warns; path-qualified links below two same-numbered domain children validate clean; unique bare stems stay warning-free.
  - Manual: read the rewritten linking section for contradiction with its own examples.
- [ ] TASK-112: skill and record contracts - spec/specs/vision place into the taxonomy at creation, file shallower when unsure, small vaults do nothing, `taxonomy_hint:` on genuine doubt; consolidate takes hints as its queue and clears on move or confirm-fine; obsidian carries scope-note authoring and the folder-is-the-listing convention (Children mandate retired, existing sections removed as folders are touched, index.md is every folder's doc, type dirs included); promote-spec's false refusal claim corrected; methodology/setup trees updated; ADR-021 stamped `amended_by`; SPEC-005 status updated - complexity: M, after 110, files: [plugin/skills/spec/SKILL.md, plugin/skills/specs/SKILL.md, plugin/skills/vision/SKILL.md, plugin/skills/consolidate/SKILL.md, plugin/skills/obsidian/SKILL.md, plugin/skills/promote-spec/SKILL.md, plugin/skills/methodology/SKILL.md, plugin/skills/setup/SKILL.md, .compass/decisions/ADR-021-index-speaks-in-domains.md, .compass/specs/SPEC-005-index-auto-maintained-and-mirrored-per-folder.md], decisions: [SPEC-022-vault-organized-per-domain/D-01, SPEC-022-vault-organized-per-domain/D-05, SPEC-022-vault-organized-per-domain/D-08]
  - Automated: grep gates - no skill claims "flat, one file each", the promote refusal, or mandates a Children section; the hint field named in the spec skill and both consumers.
  - Manual: walk the spec skill's placement step as a busy agent; a spec whose domain is unambiguous is placed without opening any domain index.
- [ ] TASK-116: `compass tree` - the whole-tree view with per-entry summaries, computed at invocation, registered in maincli and named in the pipeline-rules Capabilities line - complexity: S, after 109, files: [plugin/cli/commands/tree.py, plugin/cli/maincli.py, plugin/templates/rules/compass-pipeline.md], decisions: [SPEC-022-vault-organized-per-domain/D-08]
  - Automated: tree renders nested domains with summaries (two-level domain fixture); the usage record counts it.
  - Manual: run it on this vault; the output answers "what specs exist" in one command.

## Wave 2: this vault (after the human approves the migration diff)

This wave tests one hypothesis: domains plus scope notes plus hints let a filer place documents where a finder looks for them, and cut the share of loaded-but-unused vault tokens. A scope note is a short section in a folder's index.md: `Class here:` names what belongs, `Class elsewhere: X -> [[domain]]` redirects, `See also:` points sideways. The judges are TASK-114's drill bars and TASK-117's measure; a mechanism that proves itself gets its ADR then, one that does not is dropped.

- [ ] TASK-117: define and baseline the useless-token measure - per task, vault tokens loaded into context versus tokens the task's output used; instrumented over the 5 most recent real tasks (real work loads the vault as synthetic probes cannot; 5 bounds the cost) before any file moves, re-measured on equivalent tasks after TASK-114 - complexity: M, after 112
  - Automated: definition and per-task numbers recorded in this plan; baseline complete before 114 begins.
  - Manual: the definition survives one adversarial read - a token counts as used when the output restates its content (quote, synonym, or derivation); a token merely loaded for context is unused.
- [ ] TASK-113: build the domain proposal by running the atomic rule - place each artifact under the deepest folder whose fixed values apply; factor on the second value; one characteristic per level - with scope notes per domain (class-here digests as the summaries) and expected useless-token and root-index deltas. Score against Wikipedia: for each artifact's nearest subject, compare our chain of divisions to the dominant chain in that subject's category path; register the prediction before scoring (dimension-set agreement high, citation-order agreement partial). Present proposal plus score as a diff - complexity: M, after 117, decisions: [SPEC-022-vault-organized-per-domain/D-06, SPEC-022-vault-organized-per-domain/D-09]
  - Automated: proposal names pass make-domain's collision check in dry-run.
  - Manual: the human approves the diff; nothing further proceeds without it.
- [ ] TASK-114: apply the approved migration domain-by-domain (make-domain / promote / git mv), create `specs/index.md` and `research/index.md` (identity plus cross-domain scope pointers), replace each migrated member line in the root index with its domain line, `compass validate` 0 errors after each domain, sizing rows for every shape change - complexity: L, after 113
  - Automated: the useless-token measure re-run against baseline - pass when the useless share drops and the hot path clears its cap; a shortfall is reported with the named follow-up decision, never declared passed. Data audit: every removed root-index line's artifact present at its new path with `summary:` intact.
  - Manual (pre-registered, blind): finder drill - 10 moved documents sampled mechanically, each to a fresh subagent holding only the root index and the doc's summary line, first-click domain recorded, bar >= 8/10; filer drill - the Problem paragraphs of the 5 most recent specs, each to 3 fresh agents with only root index + scope notes, bar unanimous on >= 4/5. Every miss produces a Class-here or Class-elsewhere line; the failing item re-runs once. Results recorded here.
- [ ] TASK-115: version bump, push, fleet self-update verified on one vault; handoff naming the drill and token numbers - complexity: S, after 114
  - Automated: a fleet vault pulls the release; doctor 0 FAIL there.
  - Manual: handoff read-through.

## Verification gates

Suite green at every task; `compass validate` 0 errors after every migration step; `compass coverage PLAN-016-domain-taxonomy` passes with the D-02 deferral stated under Not in this plan; the Data-rule audit on the migration diff.
