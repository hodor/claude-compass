---
name: guide
description: Interactive guide for working with Compass. Detects where you are in the workflow, explains what to do next, and can spawn the right agents for you. Also helps port existing projects into Compass.
version: 1.0.0
allowed-tools: [Read, Glob, Grep, Bash, Agent, AskUserQuestion]
when_to_use: "Use when learning Compass, unsure what to do next, starting a new task, or porting an existing project. Triggers: 'how do I use compass', 'what do I do next', 'compass help', 'guide me', 'port this project'."
---

# Guide - Compass Workflow Assistant

Detects where the user is and points them at the right next step.

## Protocol

### 1. Detect current state

```
Glob: .compass/          - vault exists?
Glob: .claude/agents/    - agents installed?
Read: .compass/active.md - current tasks?
Read: .compass/index.md  - what exists?
```

| Situation | Trigger |
|-----------|---------|
| A. No Compass | No `.compass/`, no agents |
| B. Empty vault | Vault exists, no specs |
| C. Active work | Tasks in active.md |
| D. Porting | Existing project to bring in |
| E. Stuck | User doesn't know what to do |

### 2. Respond

Each response that ends in a question asks it through `AskUserQuestion`, one question per call, never batched.

**A - No Compass:**
> Compass isn't set up. Run `/compass:setup` (installs 13 agents, scaffolds `.compass/`, sets up hooks, proposes CLAUDE.md additions), then `/compass:vision` to capture the project goal and spec roadmap. Want me to run setup?

**B - Empty vault, no vision:**
> Compass is set up. Run `/compass:vision` to capture the project goal and a spec roadmap before writing individual specs. Want to start?

**B - Vision but no specs:** the roadmap items in `vision.md` are the options.
> Vision is captured. Which roadmap item first? I'll spawn `/compass:spec` for it.

**B - Documenting existing work:**
> Point to `/compass:retroactive`.

**C - Active work:** read `active.md`, present in-progress + blocked + recently completed, then ask what next, the options being continue building, validate, new task, handoff and checkup.

**D - Port an existing project:** if setup hasn't run, run it. Then `git log --oneline -20` to show recent work. Ask which commits to document through `AskUserQuestion`: the recommended option first, labelled "(Recommended)", each option one short line saying what choosing it does, "Other" left open for free text. Run `/compass:retroactive` per piece, then ask one more question, in the same form: "Write a forward-looking spec?", with "Yes, start the spec (Recommended)" and "Not now".

**E - Stuck:** show the pipeline table.

```
Pipeline: Spec → Research → Plan → Build → Test → Validate

| Step | Where | What |
|------|-------|------|
| Spec | /compass:spec | Capture a single problem |
| Research | /compass:research-codebase or /compass:research-papers | Investigate code or papers |
| Review | reviewer agent | Consolidate parallel research |
| Plan | /compass:plan or planner agent | Order tasks |
| Build | /compass:build or builder agent | Write code |
| Test | tester agent | Auto-spawned after builder |
| Validate | /compass:validate or validator agent | Final quality gate |

Research sub-agents: codebase-locator (where in code), codebase-analyzer (how code works), vault-locator (where in vault), vault-analyzer (what vault says), pattern-finder (code examples)
Session: /compass:handoff (create | resume)
Utilities: debug agent (errors), pr-describe (PRs)
Skills: /compass:setup, /compass:guide, /compass:checkup, /compass:vault-health, /compass:annotate, /compass:autopilot, /compass:vision, /compass:retroactive, /compass:papers
```

### 3. After any action

Offer the next step: spec → research, research → plan, plan → build, build → validate (the tester already ran), validate → PR description, checkup → help fix the issues. After handoff create, it is safe to end.

## Failure modes worth naming

- Assuming the user knows Compass terminology.
- Dumping the full pipeline on someone who just wants to continue a task.
- Skipping state detection.
- Spawning agents without confirmation.
