---
title: Unit Folders at the Vault Root, Classified by Reserved Names Plus a Marker
type: decision
status: approved
confidence: high
area: methodology
tags: [hierarchy, units, classification, wikilinks, migration, lessons, sync, validate]
created: 2026-07-24
updated: 2026-07-24
author: "roger + claude"
depends_on: ["[[SPEC-010-universal-hybrid-hierarchy]]", "[[RESEARCH-hybrid-hierarchy-impl]]", "[[ADR-004-hierarchical-specs-with-facets]]", "[[LESSON-type-dir-discovery-needs-content-signal]]"]
---

## Status

Approved. Implements [[SPEC-010-universal-hybrid-hierarchy]].

## Context

SPEC-010 decided the shape: a large unit of work is a folder at the vault root named for the work itself, holding its own type subfolders with local numbering. [[RESEARCH-hybrid-hierarchy-impl]] verified the CLI live against a scratch vault with unit folders and found: discovery misclassifies or hides unit folders; sync and validate disagree on link identity (sync writes type-dir-relative wikilinks, validate resolves stems and vault-relative paths); stem collisions across units are undetectable (name set, not map); path-qualified links already resolve end-to-end; migration of the compass-cli set breaks zero inbound wikilinks; nested lessons would vanish from the hot-path catalog.

## Decision

- **D-01:** Root folders are classified by a reserved-name list PLUS an explicit unit marker. The reserved type dirs are `specs`, `research`, `plans`, `decisions`, `lessons`, `handoffs`, `meta`, `archive`, `prs`, `tmp` (reconciling SPEC-010's list, which omitted `prs` and `tmp`, with the CLI's actual sets). A unit folder declares itself with `type: unit` frontmatter in its `index.md`. The content-signal rule for custom type dirs is preserved per [[LESSON-type-dir-discovery-needs-content-signal]]; an unmarked, unreserved root folder is ignored and reported by `validate`, never guessed at.
- **D-02:** Sync emits path-qualified wikilinks (`[[<unit>/specs/SPEC-001-name]]`) for unit artifacts, and sync's link identity is unified with validate's resolution (vault-relative), removing the latent contradiction between `sync` link emission and `validate` resolution.
- **D-03:** `validate` gains an `ambiguous_wikilink` warning: the resolvable-name set becomes a name-to-paths map, and a stem that resolves to more than one path is flagged instead of silently collapsing to one.
- **D-04:** Units can hold `lessons/`. The catalog build in `sync` aggregates lessons from unit lesson dirs into `meta/lessons-catalog.yaml`, so nested lessons stay on the hot path. (Human decision: units hold lessons because the hierarchy is about organization.)
- **D-05:** The unit-promotion trigger is mechanical detection plus human approval: the CLI reports when 3 or more artifact types trace to one spec via `depends_on` (type-spread), and the human decides whether to promote. Same detection/decision split as flat-to-folder spec promotion.
- **D-06:** Migration is a CLI operation (`compass` reuses the existing git-move helper from `promote`), non-destructive, offered never forced. The first migration is the compass-cli set (SPEC-004, ADR-005, PLAN-002, the two CLI research docs). Root `index.md` entries are rewritten as part of the operation, because sync is append-only and cannot heal them.
- **D-07:** Unit numbering is local: `next-num` computes max+1 within the unit's own type dir, per [[ADR-003-drop-counter-file-jit-compute]].

## Alternatives considered

- **Pure name-list classification (no marker).** Rejected: any stray root folder with markdown becomes a unit; this is the exact overfit failure mode of [[LESSON-type-dir-discovery-needs-content-signal]].
- **Content-signal-only classification.** Rejected: a unit before its first typed artifact is invisible, and the research showed exactly this hidden-folder failure live.
- **Keeping stem-only wikilinks with shortest-path tiebreak.** Rejected: silently picks the wrong file on cross-unit collisions; path-qualified links are already supported and unambiguous.
- **Lessons stay root-global.** Rejected by the human in favor of organizational co-location; the cost is catalog aggregation in sync, which is bounded.

## Consequences

**Easier:** a unit is one folder a human or agent opens and sees whole; deletes/renames inside units heal on regeneration; hooks need zero changes (matchers are depth-agnostic).

**Harder:** `scan_artifacts`, sync link emission, validate resolution, `tree`, `fix-frontmatter`, and the catalog build all need unit-awareness; the sync/validate link-identity unification must land together with emission or flat vaults regress; ambiguity warnings may surface pre-existing collisions the vault never noticed.

## Load-bearing risks

- The sync/validate link change touches every generated index line; golden fixtures from the current vault must be captured before the change, or the tests enshrine drift.
- Local numbering makes bare stems genuinely ambiguous across units; agent conventions (wikilinks rule file) must teach path-qualified links for unit artifacts or agents will author ambiguous references.
