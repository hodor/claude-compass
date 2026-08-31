---
title: "Self-Update Surfaces: What /compass:update Does Today and the Harness Channels a Zero-Token Updater Can Use"
type: research
status: complete
confidence: high
area: methodology
tags: [update, hooks, session-start, cli, plugin-yaml, distribution]
created: 2026-08-28
updated: 2026-08-28
author: "orchestrator"
summary: "the whole update flow is already mechanical (clone, copy, settings merge, apply-models, plugin.yaml record); SessionStart startup-matcher is the right trigger; a stored commit sha makes the current-check one ls-remote"
depends_on: ["[[SPEC-020-compass-updates-itself]]", "[[RESEARCH-active-set-prior-art]]"]
---

# Self-Update Surfaces

## Question

[[SPEC-020-compass-updates-itself]] needs the update to run itself at session start with zero agent tokens. What does `/compass:update` mechanically do today, and which harness channels carry it? Codebase research; sources are this repo's files, read directly.

## Findings

1. **The update flow is already 100% mechanical.** Confidence: high. `plugin/skills/update/SKILL.md` steps 2-7 are bash + inline python with no judgment anywhere: shallow-clone the repo from `.compass/meta/plugin.yaml` `repository:`, copy `templates/agents`, `templates/rules`, `skills/*`, `cli/`, `hooks/hooks.json` from the clone, remove retired skills (list currently: `bootstrap`), merge-register hooks into `.claude/settings.json` (replace only groups whose commands mention `compass`; preserve everything else; never touch `settings.local.json`), run `compass apply-models`, rewrite `plugin.yaml` version/installed_at/installed_mode, verify with `compass doctor`. An LLM executes it today only because it lives in a skill.

2. **SessionStart is the trigger with the right properties.** Confidence: high. Verified in [[RESEARCH-active-set-prior-art]] Findings 6/9/10: SessionStart hooks cannot block session start; matcher values (`startup`, `resume`, `clear`, `compact`, `fork`) let the updater fire on fresh starts only; stdout on SessionStart is one of only three events that ENTERS model context - silent-when-current costs nothing, and the one-line "updated X -> Y" notice reaches the session exactly when true. A timed-out or crashed hook cancels harmlessly. Compass already registers a SessionStart entry (capture-check), so the channel is proven in every installed vault.

3. **A stored commit sha makes the no-op path one network round trip.** Confidence: high. `plugin.yaml` records `version` but not the source commit; `git ls-remote <repo> HEAD` returns the remote sha without cloning. Recording `commit:` at install time turns every current-check into ls-remote + string compare; the clone happens only when the sha moved. Offline or git-missing degrades to a silent skip.

4. **The dev repo is a real special case.** Confidence: high. This vault's `plugin.yaml` has `source: F:/claude/plugins/compass/plugin` - the plugin source lives inside the same repo, and `.claude/` is rebuilt from it (CLAUDE.md). Pulling GitHub over a dev tree that is ahead of GitHub would clobber in-flight work every session. Detectable mechanically: `source` resolves to a directory inside the project root. In that case the current source of truth is the local `plugin/` dir itself.

5. **Bootstrap is one manual generation.** Confidence: high. Existing fleet installs lack both the new CLI command and the new hook entry; they receive them through one ordinary `/compass:update` (step 5 translates the whole hooks manifest, including new entries). After that generation, the updater carries itself forward: its own apply step re-registers hooks.

6. **Settings hot-reload means no restart.** Confidence: medium (documented in the update skill's step 8, not re-verified live). `.claude/settings.json` hooks and `.claude/agents/` reload live in a running session, so an update applied by a SessionStart hook is fully in effect for that same session.

## Contradiction noted

`CLAUDE.md` says `.claude/` "is rebuilt from `plugin/` by `/compass:update`" while the update skill says it "always pulls from git, never from a local copy". Finding 4's local-source detection is the reconciliation: the dev repo updates from its own `plugin/`, every other install from git.
