---
title: Hybrid Hierarchy Implementation (Unit Folders)
type: plan
status: done
confidence: high
area: architecture
tags: [hierarchy, units, cli, wikilinks, migration, sync, validate, lessons]
created: 2026-07-24
updated: 2026-07-24
approved: 2026-07-24
git_branch: "master"
git_commit: "7b5b5a8"
author: "planner agent"
depends_on: ["[[SPEC-010-universal-hybrid-hierarchy]]", "[[ADR-006-hybrid-hierarchy-implementation]]", "[[RESEARCH-hybrid-hierarchy-impl]]"]
summary: "Hybrid Hierarchy Implementation (Unit Folders)"
---

# Hybrid Hierarchy Implementation (Unit Folders)

## Goal

Make the vault hybrid: type-first at the root for small work, root-level unit folders (own type subdirs, local numbering, own `index.md`) for large units. Implements [[SPEC-010-universal-hybrid-hierarchy]] per the rulings of [[ADR-006-hybrid-hierarchy-implementation]], grounded in the live-verified findings of [[RESEARCH-hybrid-hierarchy-impl]]. Ends by migrating the compass-cli artifact set as the first real unit.

## Prerequisites

- SPEC-010 approved, ADR-006 approved (both done 2026-07-23/24).
- Research verified current: baseline `fbc32c5`, HEAD `7b5b5a8` differs only by a vault checkpoint commit; no `plugin/` code changed.
- This plan runs ALONE and FIRST. It owns `plugin/cli/` core ([[PLAN-004-decision-coverage]] and [[PLAN-005-model-table]] start only after it completes).

## Desired End State

- `discover_type_dirs`/`scan_artifacts` classify root folders as reserved-type, reserved-infra, unit (`type: unit` marker), custom-type (content signal), or incidental - no guessing.
- `sync` and `validate` share one link identity (vault-relative); sync emits path-qualified wikilinks for unit artifacts; the live sync-writes-links-validate-flags contradiction is gone.
- `validate` warns `ambiguous_wikilink` on stem collisions and reports unmarked non-reserved root folders.
- Unit lessons reach `meta/lessons-catalog.yaml`; `tree`, `next-num`, `fix-frontmatter` are unit-aware.
- `compass unit-check` reports promotion candidates (type-spread >= 3); `compass make-unit` performs the migration via git-move, rewriting root index entries.
- The wikilinks rule and obsidian skill teach path-qualified links for unit artifacts.
- The compass-cli set lives in `.compass/compass-cli/`; `compass validate` is clean on the migrated vault.

## What We're NOT Doing

- SPEC-005's fully-regenerated per-folder indexes (on hold). Root `index.md` stays append-only; `make-unit` edits it surgically because sync cannot heal it (ADR-006 D-06). The unit `index.md` children listing is authored at creation and refreshed by `/compass:consolidate` until SPEC-005 lands.
- Per-skill "resolve the destination root" prose edits across spec/retroactive/research skills and builder/researcher agent templates (research Finding 16). One shared destination paragraph lands in the obsidian skill (the canonical layout doc); the per-skill rollout is deferred to backlog.
- Depth-cap reconciliation with SPEC-005's 3-step rule (research Finding 27) - that belongs to SPEC-005's ADR when it comes off hold. Nesting inside units follows existing ADR-004 folder-spec rules.
- Migrating anything beyond the compass-cli set. Migration is offered, never forced (D-06).

## Constraints (all tasks)

- CLI never exits 2; LF endings via `write_text_lf`; `python`/`python3`; stdlib only.
- Tests: stdlib `unittest`, in `plugin/cli/tests/`, matching the existing suite style. Full suite run per task: `python -m unittest discover -s plugin/cli/tests` (use `python3` on POSIX).
- Flat vaults must not regress: sync/validate output on a units-free vault stays byte-identical (ADR-006 consequence; TASK-013 is the guard).

## Phases

### Phase 1 - Golden baseline, then the core data model

Golden fixtures MUST land before any link-identity code changes, or the tests enshrine drift (ADR-006 load-bearing risk).

- [x] TASK-013: Capture golden fixtures of current sync/validate behavior - complexity: S, depends_on: none, files: [plugin/cli/tests/fixtures/golden/, plugin/cli/tests/test_golden_flat.py], decisions: [ADR-006-hybrid-hierarchy-implementation/D-02]
 - Build a representative flat fixture vault (flat specs, one folder spec with children, lessons, handoffs, tags) mirroring the real dogfood vault's shapes. Run the CURRENT `sync` and `validate` against it; pin `index.md`, `meta/tag-index.yaml`, `meta/lessons-catalog.yaml`, and the validate report as golden files. Add a test asserting current code reproduces them byte-identically.
 - Automated verification: `python -m unittest discover -s plugin/cli/tests` green; new golden test passes against unmodified code.
 - Manual verification: human reviews the pinned golden files for correctness before they become the contract (the ADR's stated mitigation).

- [x] TASK-014: Unit-aware discovery and artifact records in vaultlib - complexity: L, depends_on: TASK-013, files: [plugin/cli/vaultlib.py, plugin/cli/tests/test_vaultlib.py], decisions: [ADR-006-hybrid-hierarchy-implementation/D-01, ADR-006-hybrid-hierarchy-implementation/D-02, ADR-006-hybrid-hierarchy-implementation/D-03]
 - Reserved root names: type dirs `specs, plans, research, decisions, lessons, handoffs, prs` + infra `meta, tmp, archive, .annotations` and dot-dirs (the union D-01 states). A non-reserved root folder is a unit iff its `index.md` frontmatter has `type: unit`; else custom-type via the existing content signal ([[LESSON-type-dir-discovery-needs-content-signal]] preserved); else incidental - skipped, surfaced to `validate` (TASK-016). `scan_artifacts` gains a `unit` field (None at root) and recurses into a unit's own type dirs; a unit artifact's `name` (link identity) is its vault-relative path without extension. Add `resolvable_names_map(vault_root) -> {name: [paths]}` to vaultlib - the ONE resolution both sync and validate consume (stems, folder names, path-qualified names), replacing validate's private set.
 - Automated verification: unittest classification matrix - marked unit discovered with correct per-artifact `unit`/`type_dir`/`name`; unmarked non-reserved folder with typed depth-2 files NOT treated as unit (returned as unclassified for validate); custom type dir (`retro/` with typed depth-1 md) still discovered; stray folder ignored; flat-vault `scan_artifacts` records identical to pre-change output; `resolvable_names_map` maps a colliding stem to 2 paths.
 - Manual verification: run discovery against the real vault; confirm the discovered dir list is unchanged.

**Phase boundary (dependency + checkpoint):** every consumer builds on the new records and resolution map. Confirm the classification matrix and golden test before three parallel tracks compound on it.

### Phase 2 - Consumers (three parallel tracks, disjoint files)

- [x] TASK-015: `sync` unit-awareness: path-qualified emission, unit sections, lessons aggregation - complexity: L, depends_on: TASK-014, files: [plugin/cli/commands/sync.py, plugin/cli/tests/test_sync.py], decisions: [ADR-006-hybrid-hierarchy-implementation/D-02, ADR-006-hybrid-hierarchy-implementation/D-04]
 - Index entries for unit artifacts are path-qualified `[[<unit>/<type>/<stem>]]` under one `## <Unit title>` section per unit (no more fake title-cased type sections); existing-entry matching uses the vaultlib resolution identity so sync never re-appends what validate already resolves. Root flat artifacts keep bare-stem links (zero flat regression). Lessons catalog: aggregate `*/lessons/` inside units into `meta/lessons-catalog.yaml` (filename stays the key; collision on duplicate filenames reported, not overwritten); `_check_caps` lesson count includes unit lessons. Tag index already vault-relative - assert, don't change.
 - Automated verification: unit fixture - sync writes path-qualified entries and a subsequent `validate` reports ZERO broken links on sync-written lines (the live contradiction, now a regression test); unit lesson appears as a catalog row; TASK-013 golden test still byte-identical; sync idempotent (second run adds nothing).
 - Manual verification: run sync on a scratch vault containing a unit; eyeball the index section.

- [x] TASK-016: `validate` ambiguity detection + unified resolution + unclassified-folder report - complexity: M, depends_on: TASK-014, files: [plugin/cli/commands/validate.py, plugin/cli/tests/test_commands.py], decisions: [ADR-006-hybrid-hierarchy-implementation/D-01, ADR-006-hybrid-hierarchy-implementation/D-02, ADR-006-hybrid-hierarchy-implementation/D-03]
 - Replace `_resolvable_names` with vaultlib's map. New warning `ambiguous_wikilink` when a link stem resolves to >1 path (set-to-map, D-03). New warning `unclassified_root_folder` for a non-reserved, unmarked, non-content-signal root folder holding markdown (D-01: reported, never guessed). Path-qualified links keep resolving unambiguously.
 - Automated verification: cross-unit stem-collision fixture -> `ambiguous_wikilink` warned with both paths listed; same link path-qualified -> clean; unmarked `bare-unit/` fixture -> `unclassified_root_folder` warned; real vault -> exit 0, no new findings; golden flat validate output unchanged.
 - Manual verification: run `compass validate` on the real vault, confirm clean.

- [x] TASK-017: `tree`, `next-num`, `fix-frontmatter` unit-awareness - complexity: M, depends_on: TASK-014, files: [plugin/cli/commands/tree.py, plugin/cli/commands/next_num.py, plugin/cli/commands/fix_frontmatter.py, plugin/cli/tests/test_fix_frontmatter.py, plugin/cli/tests/test_commands.py], decisions: [ADR-006-hybrid-hierarchy-implementation/D-01, ADR-006-hybrid-hierarchy-implementation/D-07]
 - `tree`: render units as top-level branches (unit name, then its type subtrees) alongside root `specs`. `next-num`: accept a unit scope - `compass next-num spec <unit>` computes max+1 inside `<unit>/specs/` (D-07, ADR-003 local numbering); the accidental `../` traversal path is no longer needed and rejected. `fix-frontmatter`: derive `type` from the artifact's type dir inside the unit (`<unit>/specs/` -> `spec`), never the unit name (kills the bogus `type: compass-cli` failure).
 - Automated verification: tree fixture output shows the unit branch; `next-num spec <unit>` returns unit-local max+1 and root `next-num spec` is unaffected; fix-frontmatter on a typeless unit spec inserts `type: spec`.
 - Manual verification: `compass tree` on a scratch unit vault, eyeball the shape.

**Phase boundary (dependency):** the migration operation writes what sync/validate must then verify, so Phase 3's `make-unit` needs Tracks 015 and 016 landed.

### Phase 3 - New operations

- [x] TASK-018: `compass unit-check` - mechanical promotion detection, report-only - complexity: M, depends_on: TASK-014, files: [plugin/cli/commands/unit_check.py, plugin/cli/maincli.py, plugin/cli/tests/test_commands.py], decisions: [ADR-006-hybrid-hierarchy-implementation/D-05]
 - Group root-level artifacts by the spec they reach via `depends_on` wikilinks; when >= 3 distinct artifact types trace to one spec (type-spread), print the candidate unit with its member list and suggested `make-unit` invocation. Always exit 0 - detection is mechanical, promotion is the human's (D-05). Registers in `COMMAND_SPECS` (this plan owns maincli during its window).
 - Automated verification: fixture with spec+plan+ADR+research chained via depends_on -> candidate reported; spec with 5 research docs only (type-spread 2) -> NOT reported; real vault -> reports the compass-cli set.
 - Manual verification: run on the real vault; confirm the compass-cli candidate matches ADR-006 D-06's named set.

- [x] TASK-019: `compass make-unit <name> <artifact>...` - the migration operation - complexity: L, depends_on: TASK-015, TASK-016, TASK-018, files: [plugin/cli/commands/make_unit.py, plugin/cli/commands/promote.py, plugin/cli/maincli.py, plugin/cli/tests/test_commands.py], decisions: [ADR-006-hybrid-hierarchy-implementation/D-06]
 - Dry-run by default, `--apply` to execute (mirrors fix-frontmatter; non-destructive, offered never forced). For each artifact: git-move into `<unit>/<type-dir>/` reusing promote's `_git_mv` helper (extracted to shared scope, rename fallback kept). Create `<unit>/index.md` with `type: unit` frontmatter (the D-01 marker) + title + one-line-per-member children listing. Rewrite root `index.md`: remove the moved artifacts' entries from their type sections (sync is append-only and cannot heal them, D-06), then run sync so the unit section appears. Filenames and numbers unchanged - stems keep resolving (research Finding 23).
 - Automated verification: fixture migration - files moved with git history (`git log --follow` non-empty), unit index created with `type: unit`, old root-index entries gone, new unit section present, `validate` clean after; dry-run makes zero filesystem changes.
 - Manual verification: dry-run output review on a throwaway fixture.

**Phase boundary (dependency):** conventions must be documented before the dogfood migration, so agents reading the migrated vault author correct links.

### Phase 4 - Conventions + dogfood migration

- [x] TASK-020: Teach path-qualified unit links in the rule file and skills - complexity: M, depends_on: TASK-016, files: [plugin/templates/rules/wikilinks.md, plugin/skills/obsidian/SKILL.md, plugin/skills/methodology/SKILL.md], decisions: [ADR-006-hybrid-hierarchy-implementation/D-02, ADR-006-hybrid-hierarchy-implementation/D-07]
 - `wikilinks.md`: resolution keeps glob + shortest-path tie-break, but ADD: artifacts inside a unit are AUTHORED path-qualified (`[[compass-cli/specs/SPEC-001-name]]`); on multiple glob matches treat the link as ambiguous and prefer the path-qualified form (ADR-006 load-bearing risk 2: without this, agents author ambiguous references). `obsidian/SKILL.md`: hybrid layout section (unit folder anatomy, `type: unit` marker, local numbering via `compass next-num <type> <unit>`), unit wikilink examples, one shared destination-resolution paragraph (vault root vs current unit). `methodology/SKILL.md`: file-organization diagram gains the unit-folder branch.
 - Automated verification: grep each file for the path-qualified convention and `type: unit` -> present; `compass validate` on the real vault stays clean (docs use fenced examples, which validate skips).
 - Manual verification: read the three edited docs end-to-end for coherence; confirm no contradiction with the flat-vault instructions that remain.

- [x] TASK-021: Migrate the compass-cli set (dogfood, final validation) - complexity: M, depends_on: TASK-019, TASK-020, files: [.compass/specs/SPEC-004-mechanical-work-off-the-agent-budget.md, .compass/decisions/ADR-005-compass-cli-for-mechanical-work.md, .compass/plans/PLAN-002-compass-cli-implementation.md, .compass/research/RESEARCH-cli-and-hook-command-contract.md, .compass/research/RESEARCH-cli-token-reduction-measurement.md, .compass/index.md, .compass/compass-cli/], decisions: [ADR-006-hybrid-hierarchy-implementation/D-05, ADR-006-hybrid-hierarchy-implementation/D-06]
 - Run `compass unit-check` (detection), then `compass make-unit compass-cli` with the five files ADR-006 D-06 names. Borderline members (SPEC-005, the two CLI handoffs) stay put per research Finding 22 unless the human says otherwise at execution. This is the acceptance test of the whole plan on real data.
 - Automated verification: `compass validate` exit 0 with zero broken and zero ambiguous links; `compass sync` idempotent (second run changes nothing); `git log --follow .compass/compass-cli/specs/SPEC-004-*.md` shows pre-move history; full unittest suite green.
 - Manual verification: human opens `.compass/compass-cli/` and confirms the unit reads as one body of work; reviews the rewritten root index and the unit index; confirms in-Obsidian link navigation works.

## Phasing logic

Dependency-driven, mirroring [[PLAN-002-compass-cli-implementation]]: Phase 1 before everything because all consumers read the new records and the golden baseline must predate any link change; Phase 2 tracks are parallel (disjoint files); Phase 3 sequential on maincli.py registration (018 -> 019); Phase 4 last because the dogfood migration exercises everything.

## Ownership boundary

This plan runs alone. It owns `plugin/cli/` (including `maincli.py` and `vaultlib.py`), `plugin/templates/rules/wikilinks.md`, `plugin/skills/obsidian/SKILL.md`, `plugin/skills/methodology/SKILL.md`, and the vault moves. [[PLAN-004-decision-coverage]] and [[PLAN-005-model-table]] begin only after TASK-021 completes; their later edits to `vaultlib.py` (new function only), `maincli.py` (registration lines), and the obsidian/methodology skills build on this plan's landed state.

## Decision coverage (by hand)

| ADR-006 ruling | Claimed by |
|---|---|
| D-01 reserved names + unit marker | TASK-014, TASK-016, TASK-017 |
| D-02 path-qualified emission + link-identity unification | TASK-013, TASK-014, TASK-015, TASK-016, TASK-020 |
| D-03 ambiguous_wikilink (set to map) | TASK-014, TASK-016 |
| D-04 unit lessons aggregate to catalog | TASK-015 |
| D-05 type-spread detection, human decides | TASK-018, TASK-021 |
| D-06 git-move migration + root index rewrite + compass-cli first | TASK-019, TASK-021 |
| D-07 unit-local numbering | TASK-017, TASK-020 |

All 7 rulings claimed. [[SPEC-010-universal-hybrid-hierarchy]] carries no D-NN decision bullets (parses none-present).

## Risks

- **Golden fixture pins a wrong current state.** Mitigation: TASK-013's manual hand-verify before pinning (the ADR's stated mitigation), and it lands before any behavior change.
- **Ambiguity warnings surface pre-existing collisions** the vault never noticed (ADR-006 consequence). Mitigation: warnings not errors; TASK-021 resolves any found in the dogfood vault as part of migration.
- **Sync emission and validate resolution land apart, regressing flat vaults.** Mitigation: single shared `resolvable_names_map` in vaultlib (TASK-014) consumed by both; golden flat test enforced in both TASK-015 and TASK-016.
- **Dogfood PostToolUse hook fires during migration writes.** Mitigation: make-unit's own writes go through the CLI in-process (no hook), and the hook self-filters generated outputs; verify idempotency in TASK-021.

## Inherited Questions (from spec)

All six SPEC-010 open questions were resolved by [[ADR-006-hybrid-hierarchy-implementation]]: reserved-name set (D-01), promotion trigger (D-05), unit index content (D-06 + SPEC-005 deferral stated in Not Doing), migration approach (D-06), nesting depth (existing ADR-004 rules; SPEC-005 reconciliation deferred with SPEC-005), tree/hot-path rendering (tree yes via TASK-017; hot-path unaffected per research Finding 12). None remain open.
