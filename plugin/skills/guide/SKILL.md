---
name: guide
description: Interactive guide for working with Compass. Detects where you are in the workflow, explains what to do next, and can spawn the right agents for you. Also helps port existing projects into Compass.
version: 1.0.0
allowed-tools: [Read, Glob, Grep, Bash, Agent]
when_to_use: "Use when learning Compass, unsure what to do next, starting a new task, or porting an existing project. Triggers: 'how do I use compass', 'what do I do next', 'compass help', 'guide me', 'port this project'."
---

# Guide — Compass Workflow Assistant

Detects where the user is and points them at the right next step. Knows the full pipeline and every agent.

## Protocol

### 1. Detect current state

```
Glob: .compass/          — vault exists?
Glob: .claude/agents/    — agents installed?
Read: .compass/active.md — current tasks?
Read: .compass/index.md  — what exists?
```

| Situation | Trigger |
|-----------|---------|
| A. No Compass | No `.compass/`, no agents |
| B. Empty vault | Vault exists, no specs/plans/tasks |
| C. Active work | Tasks in active.md |
| D. Porting | User has an existing project to bring in |
| E. Stuck | User doesn't know what to do |

### 2. Respond

---

## A — No Compass

```
I see this project doesn't have Compass set up yet.

Compass gives you a structured workflow:
  Vision → Spec → Research → Plan → Build → Test → Validate

To get started: /compass:bootstrap

After bootstrap, run /compass:vision to capture the project's goal
and the roadmap of specs you'll create.

Bootstrap will:
1. Install 15 specialized agents to .claude/agents/
2. Create the .compass/ knowledge vault
3. Set up hooks (auto-testing after builds)
4. Propose additions to your CLAUDE.md

Want me to run bootstrap?
```

If yes, invoke `/compass:bootstrap`.

---

## B — Empty vault

If no `.compass/vision.md`:

```
Compass is set up. Before specs, let's capture the vision — the overall
goal and the landscape of needs. This prevents your first spec from
absorbing everything.

Run /compass:vision and I'll interview you, then propose a spec list
to create one at a time.

Want to start?
```

If vision exists but no specs:

```
Vision is captured. Time to write specs from the roadmap.

Your roadmap:
1. [SPEC name 1]
2. [SPEC name 2]
...

Which one should we start with? I'll spawn /compass:spec for it.
```

If the user wants to document existing work, point to `/compass:retroactive`.

---

## C — Active work

Read `active.md` and present:

```
**In Progress:**
- [ ] TASK-005: Add auth endpoint — Phase 2 of PLAN-002
  → Next: spawn the builder

**Blocked:**
- [ ] TASK-007: Deploy to staging — blocked by TASK-005

**Recently Completed:**
- [x] TASK-004: Database schema migration

What would you like to do?
1. Continue building TASK-005 → spawn builder
2. Review what was built → spawn validator
3. Start something new
4. Create a handoff → spawn handoff-create
5. Check project health → /compass:checkup
```

---

## D — Port an existing project

```
Here's how porting works:

1. Bootstrap sets up the vault and agents
2. Retroactive agent documents existing work from git history
3. Spec-writer captures the project's goals and constraints
4. From there, normal pipeline for new work

Let me check what you have...
```

1. If bootstrap hasn't run, run it.
2. `git log --oneline -20` to show recent work.
3. Ask which commits to document.
4. Spawn retroactive per piece.
5. Offer a forward-looking spec for the next piece.

---

## E — Stuck

```
**The Pipeline:**
  Spec → Research → Plan → Build → Test → Validate

| Step | Agent | What it does |
|------|-------|-------------|
| Spec | spec-writer | Interviews you for WHAT and WHY |
| Research | researcher | Investigates unknowns (spawn N in parallel) |
| Review | reviewer | Consolidates parallel research |
| Plan | planner | Proposes implementation with ordered tasks |
| Iterate | planner-iterate | Surgically edits plans |
| Build | builder | Writes code (auto-triggers tester) |
| Test | tester | Adversarial tests |
| Validate | validator | Final quality gate |

**Session:**
| Agent | What it does |
|-------|-------------|
| handoff-create | Save context for next session |
| handoff-resume | Restore context, check for drift |

**Utilities:**
| Agent | What it does |
|-------|-------------|
| debug | Investigate errors (read-only, isolated context) |
| pattern-finder | Find existing code patterns |
| autopilot | Full pipeline for small tasks |
| retroactive | Document past work |
| pr-describe | Create PR descriptions |

**Skills:**
- /compass:bootstrap — set up
- /compass:guide — this guide
- /compass:checkup — find problems
- /compass:vault-health — vault integrity
- /compass:annotate — sidecar annotations

The vault (.compass/) is your knowledge base: specs, plans, research,
decisions, lessons, handoffs — Obsidian-compatible markdown with YAML
frontmatter.

What would you like to do?
```

---

## After any action

Offer the next logical step:

- After spec-writer → "Spec done. Research next?"
- After researcher → "Research done. Review or plan?"
- After planner → "Plan approved. Start building?"
- After builder → "Build done. Tester ran. Validate?"
- After validator → "Validation done. PR description?"
- After handoff-create → "Handoff saved. Safe to end."
- After checkup → "Here are the issues. Help fix them?"

## Failure modes worth naming

- Assuming the user knows Compass terminology. Explain as you go.
- Dumping the full pipeline on someone who just wants to continue a task.
- Skipping state detection.
- Spawning agents without confirmation. Present, let the user pick.
- Being condescending to experienced users. Specific question → direct answer.
