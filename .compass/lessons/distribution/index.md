---
title: "distribution"
type: domain
status: active
tags: [distribution]
summary: "installing, updating, and shipping Compass surfaces - what update owns, version lag, config copies in shipped prose"
created: 2026-09-05
updated: 2026-09-05
sizing_id: sz-2026-09-05-1
---

# distribution

## Scope

Class here: installing, updating, and shipping Compass surfaces - what update owns, version lag, config copies in shipped prose

## Lessons

- [[lessons/distribution/LESSON-hook-guards-on-cli-command-it-calls|LESSON-hook-guards-on-cli-command-it-calls]] - Hooks ship with the plugin install but each project's .claude/cli updates separately; a hook calling a new CLI command must skip when the local CLI lacks it
- [[lessons/distribution/LESSON-self-update-corrections-lag-one-version|LESSON-self-update-corrections-lag-one-version]] - Self-update correction logic shipped in version N runs under the N-1 updater; it first fires on the following update
- [[lessons/distribution/LESSON-self-update-silent-on-bad-repository-url|LESSON-self-update-silent-on-bad-repository-url]] - A bad repository URL in plugin.yaml makes self-update look permanently offline; doctor should verify it resolves
- [[lessons/distribution/LESSON-sweep-misses-config-in-skill-prose|LESSON-sweep-misses-config-in-skill-prose]] - A code sweep for a duplicated config value misses copies embedded in skill prose or templates
