---
name: handoff
description: Create a handoff at end of session, or resume from one at start. Create compresses context into a portable document. Resume verifies state and presents a situational report.
version: 1.0.0
allowed-tools: [Read, Grep, Glob, Write, Edit, Bash, AskUserQuestion]
when_to_use: "Use at session boundaries. Triggers: 'create handoff', 'end session', 'resume from handoff', 'continue from where we left off', 'what was I doing'."
argument-hint: "[create | resume <path | PLAN-NNN>]"
---

# Handoff

Two modes:
- `create` (or no argument when ending work): save context for next session.
- `resume <path>` or `resume <PLAN-NNN>` (or no arg to pick most recent): verify state and continue.

---

## Mode: Create

A handoff is read first by the next session. Keep it lean. Use `file:line` references, not code snippets. Failed approaches and uncommitted changes are the most valuable parts.

### Protocol

1. **Read hot path.** `.compass/index.md`, `.compass/active.md`, `.compass/meta/lessons-catalog.yaml`.

2. **Git state.**
   ```bash
   git rev-parse --abbrev-ref HEAD
   git rev-parse --short HEAD
   git log --oneline -5
   git status --short
   git diff --stat
   ```

3. **Meaningful-work check.** If no tasks advanced, no decisions made, no files modified: report "no meaningful work to hand off" and stop. Don't create empty handoffs.

4. **Reconcile index.md.** Walk the vault, find anything not yet linked in `index.md`, add it under the right section. This is the single most important step — the next session reads index.md first. A document not in it is invisible.

   ```bash
   find .compass -type f -name "*.md" -not -path "*/tmp/*" -not -path "*/archive/*" -not -path "*/handoffs/*"
   ```

5. **Pick a location for the handoff:**
   - If a plan is currently being executed: `.compass/handoffs/<PLAN-NNN>/YYYY-MM-DD_HH-MM-SS_description.md` (creates the subdirectory if needed). Plan-grouped handoffs make `resume <PLAN-NNN>` work.
   - Otherwise: `.compass/handoffs/YYYY-MM-DD_HH-MM-SS_description.md` (flat).

6. **Write the handoff:**

   ```markdown
   ---
   title: "Handoff: [brief description]"
   type: handoff
   status: active
   created: YYYY-MM-DD
   updated: YYYY-MM-DD
   git_branch: <branch>
   git_commit: <short hash>
   plan: [[PLAN-NNN-name]]  # if a plan is active
   ---

   # Handoff: [Description]

   ## Start Here

   Read these in order before doing anything else:
   1. [[SPEC-NNN-name]] — source spec
   2. [[PLAN-NNN-name]] — plan being executed (currently Phase N)
   3. [[RESEARCH-name]] — key findings
   4. `path/to/file.py:42` — [why this location matters]

   ## Session Summary
   [2-3 sentences: goal + progress]

   ## Tasks
   | Task | Status | Notes |
   |------|--------|-------|
   | [Task] | done/in-progress/blocked | [note] |

   ## Recent Changes
   - `file:line` — [what changed]

   ## Decisions
   - [Decision]: [Why] — consider ADR if significant

   ## Learnings
   - [Surprise/insight] — consider lesson if broadly applicable

   ## Blockers
   - [What stopped or slowed progress]

   ## Uncommitted Changes
   [git status --short and diff --stat output]

   ## Action Items
   1. [ ] [First thing]
   2. [ ] [Second thing]

   ## Context for Resuming
   [Nuance that would be lost — edge cases, abandoned approaches, almost-working state]
   ```

7. **Annotate the plan** (if one is active):
   ```
   > **Last session:** YYYY-MM-DD — ended mid-Phase N. See handoff [[YYYY-MM-DD_HH-MM-SS_description]] for context.
   ```

8. **Stage.** `git add` the handoff and any updated index/active/plan files. Tell the human to commit.

---

## Mode: Resume

The handoff is a snapshot. Trust current state over the handoff. Don't start work without verifying.

### Protocol

1. **Resolve the handoff.**
   - If no argument: `ls -t .compass/handoffs/**/*.md | head -5`, present, ask which.
   - If argument looks like a `PLAN-NNN`: `ls -t .compass/handoffs/<PLAN-NNN>/*.md | head -1` — most recent for that plan.
   - If argument is a path: use it directly.

2. **Read hot path.** `.compass/index.md`, `.compass/active.md`, `.compass/meta/lessons-catalog.yaml`.

3. **Read the handoff and its Start Here artifacts.** Load the spec, plan, and research in the main thread (not via sub-agent). Look for `> **Last session:**` breadcrumbs on plan files.

4. **Verify current state.**
   ```bash
   git rev-parse --abbrev-ref HEAD
   git rev-parse --short HEAD
   git log --oneline <handoff_commit>..HEAD
   git status --short
   ```

   Check each critical file: does it still exist? Modified since the handoff?

5. **Classify scenario:**
   - **A. Clean continuation** — same branch, same/ahead commit, no unexpected changes → resume from action items.
   - **B. Diverged** — different branch OR commits by others since handoff → flag, show what changed, ask how to reconcile.
   - **C. Incomplete work** — uncommitted changes not in handoff → flag, present, ask for intent.
   - **D. Stale** — >7 days old OR >20 commits since handoff → treat handoff as historical context only, recommend fresh summary.

6. **Present the situational report:**

   ```markdown
   ## Handoff Resume: [handoff title]

   ### State
   - Scenario: [A/B/C/D]
   - Handoff age: [N days]
   - Branch: [current] (handoff: [branch])
   - Commit: [current] (handoff: [hash])
   - Commits since handoff: N
   - Plan breadcrumb: [if found]

   ### Divergences
   [What changed that the handoff didn't expect]

   ### File Verification
   | File | Handoff State | Current | Match? |
   |------|---------------|---------|--------|
   | `file.py` | Modified at :42 | Unchanged | Yes |

   ### Action Items from Handoff
   1. [ ] [Item] — [still relevant?]

   ### Recommended Approach
   [Based on scenario]

   ### Relevant Lessons
   [Lessons that apply]
   ```

7. **After human confirms:** mark handoff `status: done`, update `active.md` if statuses need correction, proceed with the first action item.
