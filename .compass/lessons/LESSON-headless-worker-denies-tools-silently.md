---
title: Headless `claude -p` denies Write/Bash silently; scope the worker's tools exactly
type: lesson
status: active
category: process
area: workflow
tags: [headless, permissions, tool-scoping, background-worker, silent-failure]
created: 2026-08-24
updated: 2026-08-24
score: 5
summary: "Headless claude -p runs deny Write/Bash by default; scope the worker's tools exactly, don't bypass"
seen: []
---

Run 1 of the detached capture worker (haiku, headless `claude -p`) exited 0 and logged worker-failed "opportunity not closed" because every Write and the capture-close Bash call was silently denied by the default headless permission mode.
Headless mode's default denial fails tool calls quietly rather than refusing to start, so a worker can look like it ran to completion while doing nothing.
Grant the worker exactly the tools its pass needs instead of a blanket bypass flag, and verify via a ledger row that the intended write actually landed.
A blanket bypass would also reopen the recursive-hook and lock risks ADR-013 D-06/D-11 close; explicit scoping keeps a headless run's silence diagnosable instead of catastrophic.
