---
title: "Hook `type: prompt` cannot invoke skills; use `type: agent`"
type: lesson
status: archived
category: process
area: workflow
tags: [hooks, hook-type, skills, plugin-config]
created: 2026-05-24
updated: 2026-05-24
score: 5
summary: "Hook `type: prompt` is single-shot; cannot call Skill tool; use `type: agent` instead"
seen: []
---

`type: prompt` is single-shot via `queryModelWithoutStreaming`; tool calls in the model output are discarded.
Skill IS in the prompt hook's tool list but the agent loop that would execute it does not run.
Use `type: agent` to invoke skills from a hook; it runs a multi-turn loop with full tool access.
Default model is Haiku for both; override via `model` field. Default agent timeout 60s, cap 50 turns.
Source: `utils/hooks/execPromptHook.ts` vs `utils/hooks/execAgentHook.ts`.
