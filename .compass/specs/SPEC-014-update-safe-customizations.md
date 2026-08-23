---
title: Project-Local Workflow Customizations Survive Update
type: spec
status: draft
confidence: high
area: methodology
tags: [update, customization, overlays, install, drift, local]
created: 2026-08-09
updated: 2026-08-09
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]"]
summary: "Project-Local Workflow Customizations Survive Update"
---

# Project-Local Workflow Customizations Survive Update

## Problem

Projects customize the Compass workflow - extra protocol steps in agents, project-specific rules, modified skill orchestration - and the only place those customizations can live is the installed copies under `.claude/`, which `/compass:update` overwrites wholesale. The Defold project's upstream-contribution workflow (a mandatory upstream issue/PR sweep in the researcher, a contribution-path stop in autopilot, PR-body rules in pr-describe) has been wiped by update twice and re-applied by hand from an ADR both times. The current best practice is literally "document your customizations so you can retype them after every update." (GitHub issue #6.)

The model policy already solved this for one surface: `.compass/meta/models.yaml` survives update and `compass apply-models` re-applies it. Every other customization surface has no equivalent.

## Who is affected

- Any project whose workflow extends the shipped one: its edits are silently destroyed by the next update, or it stops updating and loses shipped fixes.
- The human, who must remember what was customized and re-apply it manually - forgetting means the workflow silently reverts.
- update itself, which cannot be run confidently in a customized project.

## Decisions (made by the human)

- **D-01:** This is separate from [[SPEC-009-configurable-pipeline-workflows]]: SPEC-009 configures the pipeline's shape (phases, order) and stays deferred; this spec is only about local modifications - whatever their content - surviving update. Shipping this first gives SPEC-009 a substrate to live on later. (Roger, 2026-08-09.)

## Desired Outcome

A project's workflow customizations live in dedicated local files that update never touches, and they are re-applied to the refreshed install automatically - the same way the model policy already survives. After any update, the customized workflow is intact and the update report says which customizations were re-applied.

## Needs

- A reserved project-local location for customizations that `/compass:update` and `/compass:setup` treat as untouchable and never overwrite or delete.
- Customizations to shipped agents, rules, and skills coexist with shipped updates: a shipped protocol fix arrives via update AND the local addition persists, without hand-merging.
- Re-application is mechanical and automatic at update time, off the agent token budget, following the `apply-models` precedent.
- The update report names every customization it re-applied; `compass doctor` detects a customization that failed to apply or references a shipped anchor that no longer exists.
- A customization is expressible without copying the whole shipped file - additions and targeted modifications, so local content does not fork the shipped surface and rot.
- Existing hand-edited installs can migrate: their diffs against shipped files are extractable into the local form.

## Hypothesis (falsifiable)

If customizations live in update-untouchable local files with mechanical re-application, then customized projects run `/compass:update` without losing workflow behavior, and re-applying after update requires zero human memory or manual editing.

## Falsification criteria

- A customization is still lost or silently broken by an update (including via a shipped-file change that invalidates it without any report).
- Expressing a real customization (the Defold set is the benchmark) requires forking whole shipped files.
- Re-application costs agent tokens or manual steps.

## Success criteria

- The Defold customization set survives a real `/compass:update` round-trip intact, with the report naming what was re-applied.
- A shipped update to a customized file lands alongside the local additions without conflict on the benchmark set.
- doctor flags a stale or unapplicable customization with an actionable message.

## Non-Goals

- Pipeline shape configuration (phases, ordering, subsetting) - [[SPEC-009-configurable-pipeline-workflows]], deferred.
- Choosing the overlay mechanism (append vs anchor-splice vs patch; file layout; which surfaces first) - research/ADR territory.
- Sharing customizations between projects or upstreaming them.
- Protecting hand edits made directly to shipped files outside the reserved location - those remain fair game for update, by design.

## Open questions (for research, after approval)

- Overlay mechanics: append-only sections vs anchor-based splicing vs unified-diff patches, and what happens when a shipped anchor moves or disappears.
- Which surfaces are overlayable first (agents and rules are the proven need; skills orchestrate and may need stricter forms).
- Where local files live (`.claude/*/local/` vs `.compass/meta/customizations/`) given `.claude/` is gitignored in some projects and the customization deserves version control.
- How doctor verifies applied overlays (marker comments, a manifest, content hashes).
