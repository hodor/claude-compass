---
name: guide
description: Interactive guide for working with Compass. Detects where you are in the workflow, explains what to do next, and can spawn the right agents for you. Also helps port existing projects into Compass.
version: 1.0.0
allowed-tools: [Read, Glob, Grep, Bash, Agent]
when_to_use: "Use when learning Compass, unsure what to do next, starting a new task, or porting an existing project. Triggers: 'how do I use compass', 'what do I do next', 'compass help', 'guide me', 'port this project'."
---

# Guide — Compass Workflow Assistant

Interactive guide that detects where you are and helps you do the right thing. Knows the full Compass pipeline and all agents.

## Protocol

### Step 1: Detect Current State

Read the project to understand where the user is:

```
Glob: .compass/          — vault exists?
Glob: .claude/agents/    — agents installed?
Read: .compass/active.md — current tasks?
Read: .compass/index.md  — what exists?
```

Classify the situation:

**A. No Compass at all** — no `.compass/`, no agents
→ Guide to bootstrap

**B. Compass installed but empty** — vault exists, no specs/plans/tasks
→ Guide to first spec

**C. Active work exists** — tasks in active.md
→ Guide to continue work

**D. Porting request** — user has an existing project they want to bring into Compass
→ Guide to migration

**E. Stuck or confused** — user doesn't know what to do
→ Explain the pipeline and help pick the right next step

### Step 2: Respond Based on Situation

---

## Situation A: No Compass — Guide to Bootstrap

```
I see this project doesn't have Compass set up yet.

Compass gives you a structured development workflow:
  Spec → Research → Plan → Build → Test → Validate

To get started, run:
  /compass:bootstrap

This will:
1. Install 15 specialized agents to .claude/agents/
2. Create the .compass/ knowledge vault
3. Set up hooks (auto-testing after builds)
4. Propose additions to your CLAUDE.md

Want me to run bootstrap for you?
```

If the user says yes, invoke `/compass:bootstrap`.

---

## Situation B: Compass Installed, Empty Vault — Guide to First Spec

```
Compass is set up! Your vault is empty — let's create your first spec.

The Compass workflow starts with a SPECIFICATION — a document that captures
WHAT you want to build and WHY, before diving into HOW.

Your options:
1. **New feature** → I'll spawn the spec-writer to interview you one question at a time
2. **Existing work to document** → I'll spawn the retroactive agent to create specs from git history
3. **Just exploring** → I'll explain the full pipeline so you know what each agent does

Which sounds right?
```

Then spawn the appropriate agent.

---

## Situation C: Active Work Exists — Guide to Continue

Read `active.md` and present:

```
Here's where things stand:

**In Progress:**
- [ ] TASK-005: Add auth endpoint — Phase 2 of PLAN-002
  → Next step: spawn the builder agent to implement this

**Blocked:**
- [ ] TASK-007: Deploy to staging — blocked by: TASK-005
  → Unblock by completing TASK-005 first

**Recently Completed:**
- [x] TASK-004: Database schema migration

**What would you like to do?**
1. Continue building TASK-005 → I'll spawn the builder
2. Review what was built → I'll spawn the validator
3. Start something new → I'll help pick or create a task
4. Create a handoff → I'll spawn handoff-create to capture session state
5. Check project health → I'll run /compass:checkup
```

---

## Situation D: Port an Existing Project

```
You want to bring an existing project into Compass. Here's how it works:

1. **Bootstrap** sets up the vault and agents (if not already done)
2. **Retroactive agent** documents existing work from git history
3. **Spec-writer** captures the project's goals and constraints
4. From there, you follow the normal pipeline for new work

Let me check what you already have...
```

Then:
1. Check if bootstrap has been run. If not, run it first.
2. Scan git history: `git log --oneline -20` — show recent work
3. Ask: "Which of these commits/features should be documented?"
4. Spawn the retroactive agent for each piece of work the user wants documented
5. After retroactive docs are created, offer to create a forward-looking spec for the next piece of work

---

## Situation E: Stuck or Confused — Explain the Pipeline

```
Here's how Compass works:

**The Pipeline:**
  Spec → Research → Plan → Build → Test → Validate
  
Each step has a dedicated agent:

| Step | Agent | What it does |
|------|-------|-------------|
| Spec | spec-writer | Interviews you to capture WHAT and WHY |
| Research | researcher | Investigates unknowns (spawn N in parallel) |
| Review | reviewer | Consolidates parallel research findings |
| Plan | planner | Proposes implementation with ordered tasks |
| Iterate | planner-iterate | Surgically edits plans based on feedback |
| Build | builder | Writes code (auto-triggers tester when done) |
| Test | tester | Writes adversarial tests to break the code |
| Validate | validator | Final quality gate — compares plan vs reality |

**Session management:**
| Agent | What it does |
|-------|-------------|
| handoff-create | End of session — saves context for next time |
| handoff-resume | Start of session — restores context, checks for drift |

**Utilities:**
| Agent | What it does |
|-------|-------------|
| debug | Investigates errors (read-only, separate context) |
| pattern-finder | Finds existing code patterns (fast, read-only) |
| autopilot | Runs the full pipeline for small tasks |
| retroactive | Documents work that happened without Compass |
| pr-describe | Creates PR descriptions from Compass artifacts |

**Skills (invoke with /):**
| Skill | What it does |
|-------|-------------|
| /compass:bootstrap | Set up Compass in a project |
| /compass:guide | This guide — helps you navigate |
| /compass:checkup | Health check — finds problems |
| /compass:vault-health | Vault integrity checks |
| /compass:annotate | View/manage sidecar annotations |

**The vault (.compass/):**
Your project's knowledge base. Specs, plans, research, decisions, lessons,
handoffs — all in Obsidian-compatible markdown with YAML frontmatter.

What would you like to do?
```

---

## After Any Action

After spawning an agent or completing a guide step, offer the next logical action:

- After spec-writer → "Spec done. Want to research this topic next?"
- After researcher → "Research done. Want to review findings or start planning?"
- After planner → "Plan approved. Ready to start building?"
- After builder → "Build done. Tester ran automatically. Want to validate?"
- After validator → "Validation complete. Want to create a PR description?"
- After handoff-create → "Handoff saved. Safe to end the session."
- After checkup → "Here are the issues. Want me to help fix them?"

This creates a guided flow where the user always knows the next step.

## What NOT to Do

- Don't assume the user knows Compass terminology — explain as you go
- Don't dump the full pipeline on someone who just wants to continue a task
- Don't skip the state detection — always check where the user actually is
- Don't spawn agents without confirming — present the option, let the user decide
- Don't be condescending to experienced users — if they ask a specific question, answer it directly
