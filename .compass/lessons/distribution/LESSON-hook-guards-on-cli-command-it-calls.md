---
title: A plugin hook calling a new CLI command must guard on that command existing
type: lesson
status: active
category: process
area: devops
tags: [hooks, cli, install-drift, versioning, plugin-update]
created: 2026-11-24
updated: 2026-11-24
score: 5
summary: "Hooks ship with the plugin install but each project's .claude/cli updates separately; a hook calling a new CLI command must skip when the local CLI lacks it"
source: extract-lessons:OPP-20261124T050555619740Z
seen: []
---

plugin/hooks/hooks.json updates with the plugin install; each project's `.claude/cli` updates on its own `/compass:update`.
A hook invoking a command added in a newer CLI fails at startup in every project whose CLI predates it.
Guard the hook on the command's presence in the local CLI so an older install skips it instead of erroring.
