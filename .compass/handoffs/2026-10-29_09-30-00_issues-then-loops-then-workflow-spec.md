---
title: "Handoff: GitHub issues, then control loops, then a workflow-scripts spec"
type: handoff
status: active
created: 2026-10-29
updated: 2026-10-29
git_branch: master
area: methodology
tags: [handoff, release, issues, loops, workflow-scripts]
git_commit: 42a52b5
summary: "PLAN-026 shipped as 0.34.0 and pushed; next: fix the four open GitHub issues, finish PLAN-021 Wave 2 (control loops), then spec Claude Code workflow scripts to keep Compass runs off the context"
---

# Handoff: GitHub issues, then control loops, then a workflow-scripts spec

## Start Here
1. `gh issue list --state open` - four open `compass-bug` issues, the first job
2. [[PLAN-021-control-loops]] - Wave 2 is the second job (TASK-161, 160, 162, 163)
3. [[specs/pipeline/SPEC-026-control-theory-for-loops]] - the need the loops serve
4. `plugin/cli/commands/test_checkpoint.py:885` - the BrokenPipeError in issue 48

## Session Summary
PLAN-024 (visual Compass) and PLAN-026 (local additions tell the truth) are done; 0.34.0 is released, installed here, and pushed (GitHub at `42a52b5`). An update now saves hand-edited agents, rules and skills under `.compass/meta/local/kept/`, and `compass overlay --extract` turns them into local additions. TASK-168 and TASK-169 of [[PLAN-022-review-in-obsidian]] were closed as already shipped.

## Tasks
| Task | Status | Notes |
|------|--------|-------|
| Issue 49: `test-checkpoint verify --against-run` misreads parametrize ids with brackets | open | test-checkpoint |
| Issue 48: BrokenPipeError at `test_checkpoint.py:885` | open | output piped to a closed reader |
| Issue 47: capture worker's headless `claude -p` opens a visible Windows Terminal | open | Windows only |
| Issue 46: `/clone-old`, `compass clone` / `compass sessions` on Windows | open | filed 2026-10-21 |
| TASK-161: ast-grep sensor and a code loop on a real repository | open | blocked on the human naming the repository |
| TASK-160: `/compass:loop` guided creation | open | after TASK-161 |
| TASK-162: Maya recipe on the local lane, marked untested | open | after TASK-160 |
| TASK-163: vault conventions for loops, then a minor release | open | last of Wave 2 |
| Spec: Claude Code workflow scripts run Compass with less context | not started | after Wave 2 |

## Decisions
- `.compass/meta/installed.json` is gitignored here: it describes the machine's own `.claude/` install, so a committed copy would make another clone save files nobody edited.

## Learnings
- A subagent can stop on a usage limit or its turn cap mid-task; SendMessage resumes it, and when the builder is gone the orchestrator finishes the fix itself.
- `self-update` takes a local `source:` only when it lies inside the project; a scratch project needs its own copy of `plugin/`.

## Uncommitted Changes
Only Obsidian's own state and the usage counter (`.compass/.obsidian/app.json`, `workspace.json`, `.compass/meta/usage.yaml`), as all session; never commit them.

## Action Items
1. [x] Read each open issue (`gh issue view <n>`), reproduce, fix with a failing test first, close it with the fixing commit.
2. [ ] Ask the human which repository TASK-161's loop runs on, then build PLAN-021 Wave 2 in order: 161, 160, 162, 163.
3. [ ] Write the spec with `/compass:spec`: Compass uses Claude Code features such as workflow scripts so a run fills less context and agents need fewer instructions. Problem and need only, no solution.

## Context for Resuming
- The human's manual check on [[loops/LOOP-001-visual-questions/index|LOOP-001]] charts at pane width is still open.
- 31 merged builder worktrees sit under `.claude/worktrees/`; removing them is scratch cleanup, offered and not yet answered.
- Agents never run git stash, reset, checkout or restore; the guard denies `git stash` for subagents.
