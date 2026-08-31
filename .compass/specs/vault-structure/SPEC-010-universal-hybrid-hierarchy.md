---
title: Any Artifact and Any Unit of Work Can Nest (Hybrid Hierarchy)
type: spec
status: approved
confidence: high
area: methodology
tags: [hierarchy, hybrid, units-of-work, co-location, nesting, vault-structure, migration]
created: 2026-07-22
updated: 2026-07-23
approved: 2026-07-23
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]", "[[SPEC-003-hierarchical-vault-organization]]", "[[ADR-004-hierarchical-specs-with-facets]]"]
summary: "any artifact and unit of work can nest; unit folders (approved 2026-07-23)"
---

# Any Artifact and Any Unit of Work Can Nest (Hybrid Hierarchy)

## Problem

The vault is flat by type, and only specs are allowed to grow into folders ([[ADR-004-hierarchical-specs-with-facets]]). Two consequences follow:

1. **A large unit of work is scattered.** A whole tool or subsystem produces specs, research, plans, and decisions, and today each lands in a different flat type folder with nothing but wikilinks tying them together. The compass CLI work in this vault is exactly this: five files across four folders (`specs/`, `decisions/`, `plans/`, `research/`) that are really one body of work. Opening any one folder never shows you "the CLI" as a thing.

2. **Nesting is a spec-only privilege.** Research, plans, and decisions cannot become folders even when they have sub-parts, so hierarchy is available to one artifact type and denied to the rest. The structure does not reflect how work is actually organized.

The flat scheme scales badly (the failure mode [[SPEC-003-hierarchical-vault-organization]] fights) and it hides the unit of work, which is the thing humans actually reason about.

## Who is affected

- The human, who thinks in units of work (a tool, a feature, a migration) but finds them dissolved across flat type folders.
- Agents navigating the vault, which cannot open a unit and see all of its artifacts in one place.
- Any artifact type other than spec, which is denied hierarchy it sometimes needs.

## Desired Outcome

The vault is hybrid: type-first at the root for small, standalone work, and feature-first for large units of work. A small spec stays a file in `specs/`. A large unit of work earns its own folder at the vault root, named for the work itself (no wrapper container), co-locating all of its own artifact types (its specs, research, plans, decisions), with local numbering, and a folder index that presents the unit as one thing. Any root folder that is not a reserved type name is a unit of work. Nesting is available to every artifact type, not just specs, and can go deeper than one level when the work warrants it.

## Needs (what a solution must satisfy)

- Small, standalone artifacts remain flat at the root (no forced ceremony for small work).
- A large unit of work can become a folder co-locating all its artifact types together.
- Any artifact type (not only specs) can grow into a folder of children.
- Nesting can recurse where the work is genuinely nested, while respecting the hot-path/cache bounds from [[ADR-004-hierarchical-specs-with-facets]] (depth-capped navigation, warm-tier folder indexes).
- A clear, mechanical rule for when work earns its own unit folder (a promotion trigger), so the choice is not arbitrary.
- A migration path from today's flat vault to the hybrid scheme that is non-destructive and preserves existing wikilinks and numbering history.
- The index and per-folder indexes reflect the hierarchy and stay machine-maintained (composes with [[SPEC-005-index-auto-maintained-and-mirrored-per-folder]]).

## Hypothesis (falsifiable)

If small work stays flat and large work co-locates its artifacts in a nestable unit folder available to every type, then a human can open a single folder and see a whole unit of work, the vault reflects how work is actually organized, and this holds without breaking the hot-path/cache bounds or existing references.

## Falsification criteria

The premise is wrong if any hold after implementation:
- A large unit of work still cannot co-locate its own specs/research/plans/decisions in one folder.
- Only specs (not research, plans, decisions) can become folders.
- Small standalone work is forced into folder ceremony it does not need.
- Nesting breaks the depth-capped navigation or the bounded hot path from [[ADR-004-hierarchical-specs-with-facets]].
- Migrating the existing flat vault destroys or orphans wikilinks or numbering history.
- There is no rule for when work earns a unit folder, so placement is arbitrary and inconsistent.

## Success criteria

- Small artifacts live flat at the root; large units live in co-located folders.
- Any artifact type can become a folder of children; nesting recurses where warranted.
- Opening a unit folder shows all of that unit's artifacts and a folder index presenting it as one thing.
- A stated promotion trigger decides when work earns a unit folder.
- Navigation stays within the depth cap and the hot path stays bounded.
- The existing flat vault migrates non-destructively, references intact.

## Constraints

- Hot path stays bounded and navigation stays depth-capped ([[ADR-004-hierarchical-specs-with-facets]], [[SPEC-003-hierarchical-vault-organization]]).
- Numbering is JIT max+1, local per folder ([[ADR-003-drop-counter-file-jit-compute]]); a unit folder numbers its children locally.
- Index maintenance is mechanical and machine-only ([[SPEC-005-index-auto-maintained-and-mirrored-per-folder]], [[ADR-005-compass-cli-for-mechanical-work]]); per-folder indexes regenerate from disk.
- Wikilink resolution must keep working across the hierarchy (glob-by-name, shortest path), per the vault's linking convention.
- Cross-platform, LF, `python`/`python3`.

## Non-Goals

- The exact promotion trigger threshold or the migration tooling - that is the research/ADR/plan phase. (Decided: a unit of work is a folder at the vault root named for the work itself, with no wrapper container; the root's reserved type-folder names distinguish type folders from unit folders.)
- Forcing existing flat artifacts to migrate; migration is offered, not mandatory.
- Changing the facet/tag system, which remains the multi-parent overlay orthogonal to the folder tree.
- A new file format or query language.

## Open questions (for research, after approval)

- The reserved type-folder name set that distinguishes a type folder from a unit folder at the root (`specs`, `research`, `plans`, `decisions`, `lessons`, `handoffs`, `meta`, `archive`), and how tooling enforces it safely - see [[LESSON-type-dir-discovery-needs-content-signal]].
- The promotion trigger: when does scattered work become a unit folder (an artifact-count threshold, a body-size threshold like the existing ~2K-token spec-folder rule, or human choice)?
- How a unit's `index.md` combines its authored parent content with the machine-regenerated contents listing (shares the mechanism from [[SPEC-005-index-auto-maintained-and-mirrored-per-folder]]).
- The migration approach: how existing flat artifacts fold into unit folders non-destructively, and whether it is a `compass` subcommand.
- How deep nesting is allowed to go before it fights the depth cap, and how the warm-tier folder indexes summarize a nested unit.
- Whether the hybrid scheme changes anything in how `compass tree`/`hot-path` render the vault.
