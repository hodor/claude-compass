---
title: "platform"
type: domain
status: active
tags: [domain, lessons, windows, platform]
summary: "host and OS quirks - line endings, shells, Windows"
created: 2026-08-30
updated: 2026-08-30
sizing_id: sz-2026-08-30-24
---

# platform

## Scope

Class here: host and OS quirks - line endings, shells, Windows

## Lessons

- [[lessons/platform/LESSON-autocrlf-churns-lf-writers|LESSON-autocrlf-churns-lf-writers]] - With core.autocrlf=true and no .gitattributes, git checks files out as CRLF; a tool that writes LF rewrites them every run, causing perpetual diffs
- [[lessons/platform/LESSON-windows-crlf-breaks-linux-container-scripts|LESSON-windows-crlf-breaks-linux-container-scripts]] - Python `open(p, 'w')` on Windows writes CRLF; mount that into a Linux container and bash chokes on $'\\\\r'
- [[lessons/platform/LESSON-windows-heredoc-backslash-escapes|LESSON-windows-heredoc-backslash-escapes]] - Git Bash heredocs on Windows collapse backslash escapes; scratchpad script files carry code patches instead
