---
title: "Local Overlays Live in .compass/meta/local and Are Appended to Freshly-Copied Shipped Files; CLAUDE.md Is Never Touched"
type: decision
status: accepted
confidence: high
area: methodology
tags: [update, customization, overlays, concatenation, doctor]
created: 2026-08-30
updated: 2026-08-30
author: "orchestrator"
summary: "concatenation over splicing: update copies the shipped file pristine then appends the project's local addendum, so no anchor can drift and no block can be orphaned; CLAUDE.md stays untouched and is proven so by test"
depends_on: ["[[SPEC-014-update-safe-customizations]]", "[[RESEARCH-update-safe-customization]]", "[[ADR-015-self-update-on-session-start]]"]
lessons: ["[[LESSON-installer-removes-only-what-it-installed]]"]
---

# Local Overlays Appended After Refresh

## Context

[[SPEC-014-update-safe-customizations]] D-02, in Roger's words: "as long as we don't make projects lose their own claude.md and their agents know how to use compass I'm good", and on the vanished Defold customizations, "those were wiped." [[RESEARCH-update-safe-customization]]: update wholesale-replaces `.claude/agents`, `rules`, `skills`, and `cli`, and since [[ADR-015-self-update-on-session-start]] it fires at every session start; drop-in directories dominate the prior art; marker splicing (Ansible `blockinfile`) fails silently by orphaning blocks when the surrounding file moves; Claude Code's own `CLAUDE.md` solves shipped-plus-local by plain concatenation with no merge logic at all.

## Decision

- **D-01: Overlays live in `.compass/meta/local/`**, mirroring the shipped layout: `agents/<name>.md`, `rules/<name>.md`, `skills/<name>.md`. That directory is inside the vault, which update never touches, and it is version-controlled wherever the project tracks `.compass/` - unlike `.claude/`, which is excluded in some projects and therefore cannot hold anything worth keeping.
- **D-02: Application is append-after-refresh, never splice.** Update copies the shipped file pristine, then appends the local addendum under a provenance comment. Because the base is regenerated every time, there is no previous block to find, so the Ansible orphaning failure mode cannot occur and no anchor can drift. Concatenation is the `CLAUDE.md` precedent, and it needs no diff, no fuzz tolerance, and no conflict resolution.
- **D-03: The provenance comment is an idempotence guard, not an anchor.** A standalone `compass overlay --apply` on an already-overlaid file finds its own marker and skips, so a hand-run outside the update path cannot double-append.
- **D-04: `CLAUDE.md` is never read, written, or moved by any Compass command.** It is already untouched; a test now pins it so no future change can quietly break the guarantee Roger named first.
- **D-05: An overlay naming a shipped file that no longer exists is an orphan** - reported by `compass overlay` and by a `doctor` advisory row, never applied and never fatal. A local file that matches nothing must not silently do nothing.
- **D-06: Whole new local files are out of scope.** A local-only skill Compass does not ship already survives update, since `_apply` copies shipped skills and deletes only names in `RETIRED_SKILLS` ([[LESSON-installer-removes-only-what-it-installed]]). The `sync-forks` skill in both Defold clones is that case, already safe.

## Consequences

- A customization is expressed as the addition itself, never a fork of the shipped file, so shipped fixes and local additions both land on every update.
- Order is fixed: shipped content first, local addendum last. A local instruction that contradicts shipped prose wins by position, which is the same rule `CLAUDE.md` concatenation already uses.
- The first update that installs overlay support does not itself apply overlays: the running process holds the previous `_apply`, and only the next refresh executes the new one. Same one-generation lag the self-update rollout had; verified live 2026-08-30.
- Overlays are prose-shaped only. Nothing here rewrites CLI code or hook JSON; a project needing that forks a skill and accepts the drift.
