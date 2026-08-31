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

- [[lessons/hooks/LESSON-hook-cli-gate-stdin-on-flag|LESSON-hook-cli-gate-stdin-on-flag]] - Gate hook-stdin reads behind an explicit flag (--hook), not isatty probing; probing blocks forever in a non-interactive shell with no piped input
- [[lessons/hooks/LESSON-hook-if-clause-no-or|LESSON-hook-if-clause-no-or]] - Settings hook entries have no `if` clause; select tools via matcher, filter paths in the command
- [[lessons/hooks/LESSON-hook-payloads-observe-before-coding|LESSON-hook-payloads-observe-before-coding]] - Observe the real emission or code path first; assumed shapes and reported causes ship dead work under a green suite
- [[lessons/hooks/LESSON-hooks-load-only-from-settings|LESSON-hooks-load-only-from-settings]] - Hooks load only from settings-file hooks keys or registered plugins; a bare .claude/hooks/hooks.json never fires
- [[lessons/hooks/LESSON-spawned-sessions-inherit-project-hooks|LESSON-spawned-sessions-inherit-project-hooks]] - A spawned claude session inherits the project's hooks; a hook-spawned worker fires its own machinery unless gated
