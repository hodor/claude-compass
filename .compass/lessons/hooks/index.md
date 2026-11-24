---
title: "hooks"
type: domain
status: active
tags: [domain, lessons, hooks]
summary: "hook registration, payloads, and firing semantics"
created: 2026-08-30
updated: 2026-08-30
sizing_id: sz-2026-08-30-21
---

# hooks

## Scope

Class here: hook registration, payloads, and firing semantics

## Lessons

- [[lessons/hooks/LESSON-hook-if-clause-no-or|LESSON-hook-if-clause-no-or]] - Settings-file hooks support an `if` clause (verified on 2.1.330); `||` inside it is untested, use a pipe matcher
- [[lessons/hooks/LESSON-hook-payloads-observe-before-coding|LESSON-hook-payloads-observe-before-coding]] - Observe the real emission or code path first; assumed shapes and reported causes ship dead work under a green suite
- [[lessons/hooks/LESSON-hooks-load-only-from-settings|LESSON-hooks-load-only-from-settings]] - Hooks load only from settings-file hooks keys or registered plugins; a bare .claude/hooks/hooks.json never fires
- [[lessons/hooks/LESSON-plugin-dir-plus-setup-double-registers-hooks|LESSON-plugin-dir-plus-setup-double-registers-hooks]] - --plugin-dir plus /compass:setup in one session registers each hook twice and lists skills twice; capture-check and sync run twice per event
