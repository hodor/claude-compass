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

- [[lessons/subagents/LESSON-agents-never-stash-the-shared-tree|LESSON-agents-never-stash-the-shared-tree]] - A subagent that runs git stash in a shared checkout reverts the human's uncommitted files; brief agents to never stash, reset or checkout there
- [[lessons/subagents/LESSON-dont-strip-agent-quality-stations|LESSON-dont-strip-agent-quality-stations]] - A blanket no-sub-agents ban in a spawn brief strips the builder's review station; twice violated, both violations caught real bugs
- [[lessons/subagents/LESSON-headless-worker-denies-tools-silently|LESSON-headless-worker-denies-tools-silently]] - Headless claude -p runs deny Write/Bash by default; scope the worker's tools exactly, don't bypass
- [[lessons/subagents/LESSON-long-agents-stall-resume-them|LESSON-long-agents-stall-resume-them]] - A subagent completion notice whose final text reads like mid-task narration is a stall, not a result; resume it with 'continue from exactly where you stopped' instead of respawning
- [[lessons/subagents/LESSON-orchestrating-briefs-require-foreground-spawns|LESSON-orchestrating-briefs-require-foreground-spawns]] - A lead agent that spawns background children ends its turn 'waiting' with no live children and stalls; briefs must require foreground spawns
- [[lessons/subagents/LESSON-parallel-builders-share-one-git-index|LESSON-parallel-builders-share-one-git-index]] - Builders sharing one worktree share one index; a sibling's commit takes your staged files under its message
- [[lessons/subagents/LESSON-parallel-research-check-siblings-first|LESSON-parallel-research-check-siblings-first]] - Research agents fanned out onto one spec should read sibling docs in the target domain folder first, and scope around what a sibling already owns
- [[lessons/subagents/LESSON-research-briefs-forbid-local-paths|LESSON-research-briefs-forbid-local-paths]] - Researchers copy home paths, session ids and work project names into vault files; brief them to write none of these
- [[lessons/subagents/LESSON-researcher-briefs-demand-early-output-file|LESSON-researcher-briefs-demand-early-output-file]] - Researchers on broad web axes exhaust their 30-turn limit before writing; briefs must say to write the output file early and append per finding
- [[lessons/subagents/LESSON-subagent-reports-need-sendmessage|LESSON-subagent-reports-need-sendmessage]] - A spawned agent's final plain text is invisible to its orchestrator; briefs must mandate an explicit SendMessage delivery
- [[lessons/subagents/LESSON-subagent-worktrees-fork-stale|LESSON-subagent-worktrees-fork-stale]] - Worktree subagents fork from the remote default branch unless worktree.baseRef is "head"; uncommitted files are always invisible
- [[lessons/subagents/LESSON-teammate-spawn-omit-name|LESSON-teammate-spawn-omit-name]] - A teammate's Agent-tool call with `name` set fails outright; the roster is flat, so spawn plain subagents by omitting `name`
- [[lessons/subagents/LESSON-verify-worktree-isolation-is-real|LESSON-verify-worktree-isolation-is-real]] - Worktree isolation can silently not exist; confirm the path is in `git worktree list` before parallel writers run
