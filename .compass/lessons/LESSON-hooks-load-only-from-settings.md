---
title: Claude Code hooks load only from settings files or registered plugins
type: lesson
status: active
category: process
area: workflow
tags: [hooks, settings, install-drift, registration, claude-code]
created: 2026-08-06
updated: 2026-08-06
score: 5
summary: "Hooks load only from settings-file hooks keys or registered plugins; a bare .claude/hooks/hooks.json never fires"
seen: []
---

Claude Code reads hooks from settings files (~/.claude/settings.json, .claude/settings.json, .claude/settings.local.json) and registered plugins only.
A hooks.json copied anywhere else is inert: it fails silently, with every hook simply never firing.
Install verification must check registration (a `hooks` key in a settings file Claude Code reads), never file existence.
Settings hook changes reload live in a running session; no restart needed.
