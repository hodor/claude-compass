---
title: Env-var vault redirection falls back to the enclosing vault when the target has no .compass
type: lesson
status: active
category: process
area: workflow
tags: [cli, vault-root, isolation, probes, hooks, env-var]
created: 2026-08-06
updated: 2026-08-06
score: 5
summary: "CLAUDE_PROJECT_DIR redirects the compass CLI only when it contains .compass; otherwise cwd-walk silently targets the enclosing vault"
seen: []
---

find_vault_root honors CLAUDE_PROJECT_DIR only when $CLAUDE_PROJECT_DIR/.compass exists; otherwise it walks up from cwd and can resolve to the enclosing repo's vault.
A probe pointing the env var at an empty scratch dir therefore mutates the real vault silently - one such probe opened a live capture opportunity during a read-only validation.
Isolating any compass CLI call requires creating .compass inside the scratch dir first.
The same edge exists in production: a hook firing in a nested non-Compass directory writes to the parent repo's vault.
