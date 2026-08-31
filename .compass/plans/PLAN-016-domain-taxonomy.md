---
title: "Domain Taxonomy"
type: plan
status: approved
approved: 2026-08-30
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

1. **Build the organizing tools.** The vault is getting organized into topic folders, and this wave builds what that needs: a command that creates a topic folder and makes it say what belongs inside; checks that suggest a split when a folder grows too big and that keep reminding about documents waiting to be filed; link handling so everything stays clickable and unambiguous once files live in folders; updates to the document-creating skills so new documents get filed into the right topic from birth; and a command that prints the whole tree at a glance. Nothing in the vault moves yet - this wave ends with the tools built and tested.

2. **Organize this vault with them.** First, measure how much irrelevant material tasks currently drag into context - that number is what the whole effort exists to shrink. Then propose the actual grouping of this vault's documents into topics, check the proposal against how Wikipedia organizes the same subjects, and stop: the human approves the grouping before a single file moves. After approval, files move group by group, and the result is tested by strangers - fresh agents must find documents on the first try and agree on where new ones go - and by re-measuring the number. Ends with the release shipped to every project.

## Not in this plan

- SPEC-022 D-02 applies the taxonomy to everything in the vault; this plan covers specs and research, and defers grouping plans/ and decisions/ to a later round. Lessons are excluded by the spec's Non-Goals.

## Wave 1: mechanism

- [x] TASK-109: vault-relative record names for nested artifacts (same-named branches stop cross-contaminating child counts), in-place `(folder, N children)` count refresh on root-index lines, the sync loop guard narrowed to exact root-relative paths, and generated links written as piped full paths (`[[specs/distribution/index|distribution]]`) - complexity: M, files: [plugin/cli/vaultlib.py, plugin/cli/commands/sync.py, plugin/cli/tests/test_sync.py, plugin/cli/tests/test_vaultlib.py], decisions: [SPEC-022-vault-organized-per-domain/D-03, ADR-022-domains-scope-notes-shallow-when-unsure/D-01]
  - Automated (red-first): same-named domains in specs/ and research/ get disjoint child counts; stale counts refresh in place without touching human descriptions; generated links are piped full paths that resolve; a nested index.md agent-write triggers sync and a capture signal (regression proven by revert); `reindex.md`-style near-name files no longer swallowed; full suite green.
  - Manual: run sync on this vault; folder-line counts correct, no other index line changed.
- [x] TASK-110: `compass make-domain <type-dir>/<path>` - any depth, dry-run default, `--apply`, mandatory `--reason` and `--class-here`, sibling-collision refusal with name reuse across branches, sizing-logged, template = `index.md` with `status: active` frontmatter + `## Scope`; validate gains `EXPECTED_FIELDS["domain"]`, `folder_over_ceiling` (path-counted, taxonomy-governed dirs only, tunable default 12), `empty_scope`, and the `taxonomy_hints: N pending` suggestion line - complexity: M, after 109, files: [plugin/cli/commands/make_domain.py, plugin/cli/commands/validate.py, plugin/cli/maincli.py, plugin/cli/tests/test_make_domain.py], decisions: [SPEC-022-vault-organized-per-domain/D-02, SPEC-022-vault-organized-per-domain/D-04, SPEC-022-vault-organized-per-domain/D-07]
  - Automated (red-first): nested creation; refusal without --class-here; sibling collision refused while `specs/network/cache` and `specs/gpu-hardware/cache` coexist and resolve path-qualified; ceiling fires at 13 not 12, on type dirs themselves, never on lessons/plans/decisions; empty_scope on a Scope with no Class-here line; hints-pending names the files; a domainless small vault emits none of these; warnings never change the exit code.
  - Manual: create and `--undo` one scratch domain end to end; read the template as a human.
- [x] TASK-111: link rules in code and prose - `_link_name` piped full paths for folder records; a red-first test reproducing the specs/research same-name collision proves the ambiguity warning fires; the bare-link warning limited to actually-ambiguous cases; obsidian + wikilinks rule carry the path-qualified convention for new links below domains (forward-only; existing links untouched) - complexity: M, after 109, files: [plugin/cli/commands/sync.py, plugin/cli/commands/validate.py, plugin/cli/tests/test_sync.py, plugin/skills/obsidian/SKILL.md, plugin/templates/rules/wikilinks.md], decisions: [ADR-022-domains-scope-notes-shallow-when-unsure/D-01]
  - Automated (red-first): the reproduced collision warns; path-qualified links below two same-numbered domain children validate clean; unique bare stems stay warning-free.
  - Manual: read the rewritten linking section for contradiction with its own examples.
- [x] TASK-112: skill and record contracts - spec/specs/vision place into the taxonomy at creation, file shallower when unsure, small vaults do nothing, `taxonomy_hint:` on genuine doubt; consolidate takes hints as its queue and clears on move or confirm-fine; obsidian carries scope-note authoring and the folder-is-the-listing convention (Children mandate retired, existing sections removed as folders are touched, index.md is every folder's doc, type dirs included); promote-spec's false refusal claim corrected; methodology/setup trees updated; ADR-021 stamped `amended_by`; SPEC-005 status updated - complexity: M, after 110, files: [plugin/skills/spec/SKILL.md, plugin/skills/specs/SKILL.md, plugin/skills/vision/SKILL.md, plugin/skills/consolidate/SKILL.md, plugin/skills/obsidian/SKILL.md, plugin/skills/promote-spec/SKILL.md, plugin/skills/methodology/SKILL.md, plugin/skills/setup/SKILL.md, .compass/decisions/ADR-021-index-speaks-in-domains.md, .compass/specs/SPEC-005-index-auto-maintained-and-mirrored-per-folder.md], decisions: [SPEC-022-vault-organized-per-domain/D-01, SPEC-022-vault-organized-per-domain/D-05, SPEC-022-vault-organized-per-domain/D-08]
  - Automated: grep gates - no skill claims "flat, one file each", the promote refusal, or mandates a Children section; the hint field named in the spec skill and both consumers.
  - Manual: walk the spec skill's placement step as a busy agent; a spec whose domain is unambiguous is placed without opening any domain index.
- [x] TASK-116: `compass tree` - the whole-tree view with per-entry summaries, computed at invocation, registered in maincli and named in the pipeline-rules Capabilities line - complexity: S, after 109, files: [plugin/cli/commands/tree.py, plugin/cli/maincli.py, plugin/templates/rules/compass-pipeline.md], decisions: [SPEC-022-vault-organized-per-domain/D-08]
  - Automated: tree renders nested domains with summaries (two-level domain fixture); the usage record counts it.
  - Manual: run it on this vault; the output answers "what specs exist" in one command.

- [x] TASK-118: born flat - a spec is a file until its second member: spec/obsidian/methodology/CLAUDE contracts rewritten, `make-unit` stops writing a Children listing, and `self-update` normalizes any folder spec holding only its own index back to a flat file (sizing-logged correction, domains and units untouched) - complexity: M, after 110, files: [plugin/cli/commands/self_update.py, plugin/cli/commands/make_unit.py, plugin/cli/tests/test_self_update.py, plugin/skills/spec/SKILL.md, plugin/skills/obsidian/SKILL.md, plugin/skills/methodology/SKILL.md], decisions: [SPEC-022-vault-organized-per-domain/D-10]
  - Automated (red-first): a lone-index folder spec flattens on update with a correction row; a folder spec with a child is untouched; a domain index is untouched; make-unit's template carries no Children listing; full suite green.
  - Manual: run self-update on this vault; any over-shaped spec comes back flat.

## Wave 2: this vault (after the human approves the migration diff)

This wave tests one hypothesis: domains plus scope notes plus hints let a filer place documents where a finder looks for them, and cut the share of loaded-but-unused vault tokens. A scope note is a short section in a folder's index.md: `Class here:` names what belongs, `Class elsewhere: X -> [[domain]]` redirects, `See also:` points sideways. The judges are TASK-114's drill bars and TASK-117's measure; a mechanism that proves itself gets its ADR then, one that does not is dropped.

- [x] TASK-117: define and baseline the useless-token measure - per task, vault tokens loaded into context versus tokens the task's output used; instrumented over the 5 most recent real tasks (real work loads the vault as synthetic probes cannot; 5 bounds the cost) before any file moves, re-measured on equivalent tasks after TASK-114 - complexity: M, after 112
  - Automated: definition and per-task numbers recorded in this plan; baseline complete before 114 begins.
  - Manual: the definition survives one adversarial read - a token counts as used when the output restates its content (quote, synonym, or derivation); a token merely loaded for context is unused.
- [x] TASK-113 (diff approved by the human 2026-08-30): build the domain proposal by running the atomic rule - place each artifact under the deepest folder whose fixed values apply; factor on the second value; one characteristic per level - with scope notes per domain (class-here digests as the summaries) and expected useless-token and root-index deltas. Score against Wikipedia: for each artifact's nearest subject, compare our chain of divisions to the dominant chain in that subject's category path; register the prediction before scoring (dimension-set agreement high, citation-order agreement partial). Present proposal plus score as a diff - complexity: M, after 117, decisions: [SPEC-022-vault-organized-per-domain/D-06, SPEC-022-vault-organized-per-domain/D-09]
  - Automated: proposal names pass make-domain's collision check in dry-run.
  - Manual: the human approves the diff; nothing further proceeds without it.
- [x] TASK-114 (bars in the TASK-114 record; cap shortfall reported with named follow-up): apply the approved migration domain-by-domain (make-domain / promote / git mv), create `specs/index.md` and `research/index.md` (identity plus cross-domain scope pointers), replace each migrated member line in the root index with its domain line, `compass validate` 0 errors after each domain, sizing rows for every shape change - complexity: L, after 113
  - Automated: the useless-token measure re-run against baseline - pass when the useless share drops and the hot path clears its cap; a shortfall is reported with the named follow-up decision, never declared passed. Data audit: every removed root-index line's artifact present at its new path with `summary:` intact.
  - Manual (pre-registered, blind): finder drill - 10 moved documents sampled mechanically, each to a fresh subagent holding only the root index and the doc's summary line, first-click domain recorded, bar >= 8/10; filer drill - the Problem paragraphs of the 5 most recent specs, each to 3 fresh agents with only root index + scope notes, bar unanimous on >= 4/5. Every miss produces a Class-here or Class-elsewhere line; the failing item re-runs once. Results recorded here.
- [x] TASK-115 (v0.16.0; knowledge-curation pulled 0.14.0 -> 0.16.0, doctor 0 FAIL; handoff [[2026-08-30_17-31-12_v0.16-vault-migrated]]): version bump, push, fleet self-update verified on one vault; handoff naming the drill and token numbers - complexity: S, after 114
  - Automated: a fleet vault pulls the release; doctor 0 FAIL there.
  - Manual: handoff read-through.
- [x] TASK-120 (diff approved and applied 2026-08-30: 10 domains, 19 ADRs + 33 lessons moved, validate 0 errors, catalog untouched and `compass lessons` verified, root index 2,340 tokens - from 4,214 at session start; hot path 6,054, the catalog its last block): taxonomize decisions/ and lessons/ per SPEC-022 D-12 ("lessons and ADRs should also be taxonomized the same way") - same atomic rule, same proposal-diff shape; lessons need one design decision first (the catalog stays the hot-path index; what folding lesson files into domains means for capture, dedup, and the 5-line cap) - complexity: M, after 114
  - Automated: proposal passes make-domain collision dry-run; validate 0 errors after each move.
  - Manual: the human approves the diff before any file moves - same gate as TASK-113.
- [ ] TASK-119: taxonomy optimized by measured efficiency (SPEC-022 D-11) - "optimize our taxonomy/categorization by measuring against the unrelated token consumption of subagents"; first "ensure our measurement is 100% accurate" and "figure out ways to empirically prove that it is"; after that "the strategy we use to organize will be 100% dependent on the efficiency of it" - complexity: L, after 115
  - Automated: an accuracy validation of the useless-token measure runs against constructed ground truth (probes whose truly-relevant token set is known by construction); accuracy numbers recorded in this plan before any strategy binds to the measure.
  - Manual: the human rules the measurement accurate; only then does measured efficiency start driving organization moves.

## TASK-117: the useless-token measure

Registered before any grading ran.

- **Loaded:** per task, the vault files its session's protocol and plan citations put in context - `index.md`, `active.md`, `meta/lessons-catalog.yaml`, this plan, and the spec/ADR the task's `decisions:` field cites - as committed at the task's parent commit, token-counted by `vaultlib.count_tokens`.
- **Used:** the tokens of exactly those lines whose content the task's commit diff restates - by quote, synonym, or derivation; a line the diff itself edits inside a loaded document counts. Graded line-by-line by a fresh agent holding only the documents and the diff, never the session that produced them.
- **Useless share:** `1 - used/loaded`. The output is the commit diff; conversation text is not measured.
- **Baseline tasks** (5 most recent real commits): TASK-109 `aef3868`, TASK-110 `377ce87`, TASK-111 `c4d2a27`, TASK-112+118 `4de7996`, TASK-116 `0e95258`.

### Baseline (recorded 2026-08-30)

| Task | Commit | Loaded | Used | Useless share |
|---|---|---|---|---|
| TASK-109 | `aef3868` | 12,687 | 1,165 | 90.8% |
| TASK-110 | `377ce87` | 12,156 | 1,091 | 91.0% |
| TASK-111 | `c4d2a27` | 11,236 | 615 | 94.5% |
| TASK-112+118 | `4de7996` | 12,156 | 1,163 | 90.4% |
| TASK-116 | `0e95258` | 12,376 | 2,258 | 81.8% |

Mean useless share: **89.7%**. Per-doc pattern, stable across all five tasks: `index.md` loads ~4,150 tokens and at most 3 lines (38-174 tokens) are ever used; `lessons-catalog.yaml` loads 3,205 with 0-127 used; the plan itself is the most-used document (207-1,904). TASK-114's re-measure passes when the mean useless share on equivalent tasks drops below this baseline.

### Retrieval probes

The build-task measure above catches what a working session drags in; this catches what a searching agent wades through. Per probe: a fresh agent holds only a question, starts at `.compass/index.md`, navigates by Read only (follow index lines, folder indexes, links - no content grep), and reports the answer plus every vault file it read. Useless = tokens of the files it read minus the tokens of the documents its answer used. Five questions, targets sampled mechanically (seed 22) from the artifacts the migration will move; the same five questions re-run on the migrated vault in TASK-114, pass = probe useless tokens drop.

| Probe question | Target doc | Pre-migration read / useless | Post-migration read / useless |
|---|---|---|---|
| What did the GSD research recommend Compass adopt? | RESEARCH-gsd-core-improvements-for-compass | 7,010 / 4,214 | 19,696 / 16,900; re-run after scope repair: 5,767 / 2,971 |
| Do detached hook-spawned workers survive; which channel wakes the model silently? | RESEARCH-invisible-scaffolding | 6,053 / 4,214 | 4,807 / 2,968 |
| Why can a hardware cache miss never cost correctness; implication for context tiers? | RESEARCH-cache-theory-for-context-tiers | 8,735 / 4,214 | 6,603 / 2,862 (answered from ADR-010/ADR-004 instead) |
| Which agent CLIs beyond Claude Code; what problem does that spec capture? | SPEC-006-multi-host-agent-cli-support | 6,025 / 4,214 | 4,779 / 2,968 |
| How was the test admission bar validated; what did it show? | RESEARCH-test-quality-bar-validation | 8,168 / 4,214 | 25,266 / 2,862 (routed via the 18,450-token PLAN-007, counted an answer source) |

Pre-migration (2026-08-30): every probe answered in exactly two reads - root index, then target - first click 5/5. The useless load is the whole root index (4,214 tokens), identical across probes. The detached-workers probe's subagent tripped a harness security classifier mid-run; its answer was verified against the target doc and kept.

### TASK-114 record (2026-08-30)

Migration applied domain by domain (commit `4888644`): 10 domains, 50 moves, validate 0 errors throughout, data audit 50/50 present with summaries intact. Root index 4,214 -> ~2,880 tokens.

- **Finder drill: 8/10 first run - bar met.** Misses: RESEARCH-hermes-vs-compass-fit (its summary named no subject; summary repaired) and SPEC-015-rolling-wave-planning (sent to research/rolling-wave, a research domain, for a spec). Re-run: hermes hit; SPEC-015 missed again - same-name-across-type-dirs confusion, the live datum behind the domain-name-alignment KPI idea in [[backlog]]. Final 9/10.
- **Filer drill: unanimous on 4/5 - bar met.** SPEC-018 split 2-1 in both runs (pipeline/root); its root-plus-hint placement stands and specs/pipeline's scope note now redirects.
- **Retrieval probes: pass.** 4/5 dropped ~30% useless immediately; the GSD probe wandered (its subject was named in no scope note; 16,900 useless), one Class-here line repaired it to 2,971. All 5 finish at 2,862-2,971 useless vs the uniform 4,214 pre-migration. Two caveats feed TASK-119: the cache-theory probe answered from ADRs without reaching the target doc, and the test-bar probe routed through the 18,450-token PLAN-007 that the doc-granular rule counts as fully used.
- **Build-measure re-run: pending, not passed.** No post-migration build task exists yet to measure; the next real task's commit is the first candidate.
- **Hot path: 6,578 / 5,000 - cap NOT cleared**, as the approved proposal predicted. Named follow-up: a consolidate lessons pass on `meta/lessons-catalog.yaml` (3,283 tokens, the dominant remaining block).

## Verification gates

Suite green at every task; `compass validate` 0 errors after every migration step; `compass coverage PLAN-016-domain-taxonomy` passes with the D-02 deferral stated under Not in this plan; the Data-rule audit on the migration diff.
