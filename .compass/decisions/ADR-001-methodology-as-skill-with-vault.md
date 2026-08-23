---
title: Methodology as a skill, project state in an Obsidian-compatible vault
type: decision
status: approved
confidence: high
area: architecture
tags: [methodology, skill, vault, obsidian, foundational]
created: 2026-05-24
updated: 2026-05-24
git_branch: "master"
git_commit: "pending"
author: "roger + claude"
summary: "Methodology lives in a skill; project state in per-project `.compass/` Obsidian-compatible vault"
---

## Status

Approved. Foundational decision; supersedes nothing.

## Context

Claude Code agents need a development methodology (spec to research to plan to build to validate) and persistent project knowledge between sessions. Two questions had to be answered together:

1. **Where does the methodology live?** CLAUDE.md per project bloats fast and duplicates across projects. Inlined into each agent's prompt repeats the same rules N times. An external rulebook the agent has to fetch is brittle.
2. **Where does project state live?** A structured DB requires infrastructure no developer wants. A pile of markdown files with no schema becomes unreadable. The state must be agent-readable AND human-readable.

These questions are coupled: the methodology has to know where state lives, and the state shape has to match what the methodology operates on.

## Decision

**The Compass methodology lives in a skill (`plugin/skills/methodology/SKILL.md`) installed via a Claude Code plugin.** Agents in the plugin reference the skill rather than carrying the rules inline. CLAUDE.md per project stays thin (a 10-line pointer to "this project uses Compass; read methodology skill"). The methodology is reusable across projects without copy/paste.

**Project state lives in a per-project `.compass/` directory, Obsidian-compatible markdown with YAML frontmatter.** Subdirectories by artifact type: `specs/`, `plans/`, `research/`, `decisions/`, `lessons/`, `handoffs/`, `prs/`, `archive/`. The "hot path" (`index.md` + `active.md` + relevant lessons) is always loaded; everything else is fetched on demand.

The two choices reinforce each other. The methodology skill knows the vault layout, and the vault layout is shaped by what the methodology consumes.

## Alternatives considered

- **Methodology in CLAUDE.md.** Rejected: CLAUDE.md bloats; rules duplicate per project; no reuse.
- **Methodology as per-agent inline rules.** Rejected: the same rules get repeated across builder, planner, researcher, etc. Drift is inevitable.
- **Structured database for state.** Rejected: infrastructure burden; not git-versionable; not human-editable.
- **Single CLAUDE.md or single project-state.md.** Rejected: cache-line thinking - everything loads every turn, even cold artifacts.
- **External notes app (Notion, Linear).** Rejected: agents can't read it without API plumbing; not in-repo; not git-versioned.

## Consequences

**Easier:**

- Methodology iterates centrally; one edit propagates to all projects on plugin update.
- Vault is git-versioned alongside the project code.
- Human can open `.compass/` in Obsidian and navigate the wikilink graph.
- New agents inherit the methodology by referencing the skill; no copy/paste.
- The hot-path/cold-path split keeps every agent's context tight.

**Harder:**

- Plugin installation becomes a prerequisite. Anyone cloning the project without the plugin sees an unannotated `.compass/`.
- Methodology changes must remain backward-compatible with existing `.compass/` vaults, or a migration path must ship.
- The vault structure is opinionated; projects with very different shapes (e.g. ML research with notebook-heavy artifacts) may need extensions.

**Load-bearing for later decisions:** [[ADR-002-retrospective-lessons-subsystem]] sits on top of this. The lessons subsystem assumes the vault structure and the methodology-as-skill packaging.
