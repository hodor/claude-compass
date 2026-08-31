---
title: "Windows Git Bash Heredocs Collapse Backslash Escapes"
type: lesson
status: active
category: process
area: workflow
tags: [windows, git-bash, heredoc, escaping, scratchpad]
created: 2026-08-30
updated: 2026-08-30
score: 5
summary: "Git Bash heredocs on Windows collapse backslash escapes; scratchpad script files carry code patches instead"
source: "extract-lessons:OPP-20260830T234845477891Z"
seen: []
---

Inline heredocs piped through the Bash tool on this Windows host silently collapse backslash escapes before the shell sees them.
Write python patches to code or tests as a scratchpad script file and run that file, never as an inline heredoc.
