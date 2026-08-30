---
title: "Compass Updates Itself at Session Start"
type: spec
status: approved
approved: 2026-08-28
confidence: high
area: methodology
tags: [update, hooks, session-start, fleet, zero-touch, distribution]
created: 2026-08-28
updated: 2026-08-28
depends_on: ["[[compass-cli/specs/SPEC-004-mechanical-work-off-the-agent-budget]]", "[[SPEC-018-scaffolding-invisible-to-the-human]]"]
summary: "a project's Compass install refreshes itself from the canonical repo at session start - mandatory, zero tokens, silent when current (approved 2026-08-28)"
aliases: ["SPEC-020-compass-updates-itself"]
---

# Compass Updates Itself at Session Start

## Problem

Keeping a project's Compass install current is a human chore. `/compass:update` works, but only when someone remembers to run it - and across ~50 fleet vaults nobody does. Installs drift for weeks; fixes ship to GitHub and sit undeployed; every distribution wave is a manual sweep across projects. The human is the update mechanism, which is exactly the class of job [[compass-cli/specs/SPEC-004-mechanical-work-off-the-agent-budget]] says machinery must own.

## Desired Outcome

Every session starts on the current Compass, with the human doing nothing - the way Claude Code itself updates.

- At session start the install refreshes itself from the canonical repository: agents, rules, skills, CLI, hooks, model policy - everything `/compass:update` refreshes today.
- Zero agent tokens and zero human attention. Silent when already current; when an update landed, one line in context says so, so the session knows its tooling changed.
- Session start is never blocked or broken: offline, no git, no network - the session runs on what is installed and tries again next time.
- The vault is never touched; only the install is.

## Decisions (made by the human)

- **D-01:** Updating is mandatory. No opt-out flag, no version pin, no `update: manual` escape hatch - the same contract as Claude Code's own updater. A bad release is fixed by pushing a good release, not by pinning.

## Non-Goals

- Vault content migration or schema upgrades.
- `CLAUDE.md` edits.
- Packaging Compass as a marketplace plugin (separate concern; today's install channel is the file copy).
