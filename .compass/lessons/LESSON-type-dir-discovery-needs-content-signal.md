---
title: Vault type-dir discovery must be content-aware, not "any subdirectory"
type: lesson
status: active
category: process
area: methodology
tags: [cli, vault, discovery, overfit, false-positives, validation]
created: 2026-06-15
updated: 2026-06-15
score: 5
summary: "Treating every .compass subdir as an artifact type dir breaks on vaults that store non-artifact dirs there; require the known core dirs OR a typed-artifact signal"
seen: []
---

Auto-discovering "every subdirectory of `.compass/` is an artifact type directory" is too permissive: real vaults keep non-artifact folders inside `.compass/`.
iwyc-unreal symlinks `.claude` -> `.compass/claude/` so the whole install (agents, cli, hooks, skills) rides inside the committed vault; scanning it as artifacts produced 148 false frontmatter errors.
Fix: always scan the known core dirs (specs, plans, research, decisions, lessons, handoffs, prs), and include an extra dir only when it holds a markdown file with a top-level `type:` frontmatter field (checked shallowly: depth-1 `*.md` and folder-spec `*/index.md`). That keeps custom artifact dirs like `retro/` working while skipping installs and config folders.
Consequence: a brand-new custom dir whose first file has no frontmatter is not auto-discovered until one file carries `type:` - acceptable, since that is exactly how you tell an artifact dir from an incidental one.
General pattern: "discover from the filesystem" needs a positive signal for what counts, or it scoops up whatever a user parks nearby. Relates to [[LESSON-tag-index-trades-cost-for-directed-retrieval]] and the dogfood-overfit fix in the CLI.
