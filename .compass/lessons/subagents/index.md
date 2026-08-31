---
title: "subagents"
type: domain
status: active
tags: [domain, lessons, subagents, orchestration]
summary: "spawning, briefing, and supervising agents"
created: 2026-08-30
updated: 2026-08-30
sizing_id: sz-2026-08-30-20
---

# subagents

## Scope

Class here: spawning, briefing, and supervising agents

## Lessons

- [[lessons/subagents/LESSON-dont-strip-agent-quality-stations|LESSON-dont-strip-agent-quality-stations]] - A blanket no-sub-agents ban in a spawn brief strips the builder's review station; twice violated, both violations caught real bugs
- [[lessons/subagents/LESSON-headless-worker-denies-tools-silently|LESSON-headless-worker-denies-tools-silently]] - Headless claude -p runs deny Write/Bash by default; scope the worker's tools exactly, don't bypass
- [[lessons/subagents/LESSON-long-agents-stall-resume-them|LESSON-long-agents-stall-resume-them]] - A subagent completion notice whose final text reads like mid-task narration is a stall, not a result; resume it with 'continue from exactly where you stopped' instead of respawning
- [[lessons/subagents/LESSON-subagent-reports-need-sendmessage|LESSON-subagent-reports-need-sendmessage]] - A spawned agent's final plain text is invisible to its orchestrator; briefs must mandate an explicit SendMessage delivery
- [[lessons/subagents/LESSON-subagent-worktrees-fork-stale|LESSON-subagent-worktrees-fork-stale]] - Worktree-isolated subagents fork from a pre-session commit; without a fast-forward to master and committed prior waves, they see a world where earlier work does not exist
- [[lessons/subagents/LESSON-verify-worktree-isolation-is-real|LESSON-verify-worktree-isolation-is-real]] - Worktree isolation can silently not exist; confirm the path is in `git worktree list` before parallel writers run
