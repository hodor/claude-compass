---
title: git core.autocrlf=true churns against tools that deliberately write LF
type: lesson
status: active
category: process
area: workflow
tags: [git, autocrlf, line-endings, gitattributes, churn, hooks]
created: 2026-06-14
updated: 2026-06-14
score: 5
summary: "With core.autocrlf=true and no .gitattributes, git checks files out as CRLF; a tool that writes LF rewrites them every run, causing perpetual diffs"
seen: []
---

When `git config core.autocrlf` is `true` and the repo has no `.gitattributes`, git stores LF but checks text files out as CRLF on Windows.
A tool that deliberately writes LF (correct per [[LESSON-windows-crlf-breaks-linux-container-scripts]]) then rewrites those files to LF on every run, so git shows a perpetual diff and any file-watch hook (e.g. a PostToolUse sync) re-fires on its own output.
Fix: add `.gitattributes` with `* text=auto eol=lf`; attribute rules override `core.autocrlf` and keep the working tree LF, matching the tool's output.
Verify with `git check-attr text eol -- <file>` (expect `text: auto`, `eol: lf`) and confirm the "LF will be replaced by CRLF" warning is gone.
Caught building the compass CLI: `compass sync` writes LF, the repo had autocrlf=true and no .gitattributes, so every sync would have churned the index and re-fired the hook.
