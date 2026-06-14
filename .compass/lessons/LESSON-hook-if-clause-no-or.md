---
title: Hook `if` clause does not support `||` boolean OR
type: lesson
status: active
category: process
area: workflow
tags: [hooks, if-clause, permission-rules, plugin-config]
created: 2026-05-24
updated: 2026-05-24
score: 5
summary: "Hook `if` does not support `||`; split into N entries or use matcher for multi-tool"
seen: []
---

Hook `if` clause does NOT support `||` boolean OR; it is parsed as one permission rule.
For multi-tool matching, use the `matcher` field with pipe-separated tools (`Write|Edit|MultiEdit`).
For multi-path matching, split into N hook entries, each with its own `if`.
`isHookEqual` keys on `if`, so split entries do not deduplicate.
Source: `utils/hooks.ts:1411-1420` in the Claude Code TypeScript source.
