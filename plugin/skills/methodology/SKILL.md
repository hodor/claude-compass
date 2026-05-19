---
name: methodology
description: The Compass development workflow pipeline - Spec, Research, Plan, Tasks, Build, Validate - with human involvement gradient, status transitions, testing mandate, and required artifacts enforcement
version: 1.0.0
allowed-tools: [Read, Glob, Grep]
---

# Methodology - The Compass Workflow

Compass is a structured development pipeline. Humans own strategic decisions; AI handles execution. Every Compass agent follows this methodology.

## The pipeline

```
Vision → Spec → Research → Plan → Tasks → Build → Validate
```

Each stage produces artifacts that feed the next. Stages can be revisited, but never skipped.

## Document writing

Compass documents are a pleasure to read. Short, sweet, long only when needed, never verbose. Research is the exception: it captures evidence and can be as long as required.

- **Vision** captures the overall project goal and the landscape of needs (once per project, or per major pivot). Produces `vision.md` and a spec roadmap.
- **Specs** are single-problem. One spec = one problem = one outcome. Vision prevents bundling.

Without vision, projects get crammed into one giant spec or fragmented into incoherent ones.

## Hot path

Every agent reads first, before anything else:

1. `.compass/index.md` - master map.
2. `.compass/active.md` - current tasks.
3. `.compass/meta/lessons-catalog.yaml` - scan for relevant lessons.

This is the cache line - minimum context to orient. Load specific specs/research/plans only after.

## Human involvement gradient

| Level | Human role | AI role | Autonomy |
|-------|-----------|---------|----------|
| Specs | Models and decides | Asks one question at a time, structures answers | LOW |
| Research | Reviews, redirects | Executes autonomously, presents evidence | MEDIUM |
| Plans | Approves before tasks are created | Proposes from spec + research | MEDIUM |
| Tasks | Reviews output | Executes autonomously, writes tests | HIGH |
| ADRs | Approves | Presents options with evidence | LOW |

Agents own execution. Humans own strategy. Strategic gates (spec approval, plan approval, CLAUDE.md changes, project migration) require human approval. Everything else is the agent's judgment. Don't ask for permission inside your scope.

If a decision has architectural implications and you proceed, record it as an ADR.

## ADRs (decision records)

Orthogonal to the pipeline - create at any stage when a significant decision is made:
- Choosing between approaches with meaningful trade-offs.
- Adopting or abandoning a technology, pattern, or convention.
- Anything that would surprise a future team member.

Live in `.compass/decisions/`, named `ADR-NNN-descriptive-name.md`.

## Testing mandate

Non-negotiable. Every agent that writes code:

1. Picks the test type (property-based, unit, integration - agent's call).
2. Tests live outside `.compass/`, in the project's normal test directory.
3. Covers the code being written or modified.
4. Runs the full suite to ensure nothing is broken.

Tests are the safety net that lets humans trust AI-written code.

## Task execution

When `active.md` has approved tasks, execute via **builder agents**, not inline in the main conversation. Builders run in isolated worktrees (reviewable before merge), auto-trigger the tester via SubagentStop, and follow the full protocol (scope check, smoke test, code review).

The main conversation's job during execution: orchestration - spawn builders, review output, handle failures, update vault state.

## Parallel execution

When a plan has multiple tasks with non-overlapping file ownership:

```
Phase 1: PARALLEL BUILDERS (each in its own worktree)
  ├── Builder A (files: X, Y) - branch builder-task-001
  ├── Builder B (files: Z, W) - branch builder-task-002
  └── Builder C (files: V)    - branch builder-task-003
         ↓ all complete, tester auto-runs on each
Phase 2: QA REVIEW (validator) - PASS / FAIL / PARTIAL per task
         ↓
Phase 3: TARGETED FIXES (conditional)
  ├── Fix Builder 1 (FAIL items from task A, same branch)
  └── Fix Builder 2 (FAIL items from task B, same branch)
         ↓ re-test
Phase 4: RE-REVIEW (max 3 iterations)
         ↓ all PASS or stuck
Phase 5: MERGE BACK - orchestrator (`/compass:build`) merges each task
         branch into the working branch in depends_on order,
         re-running the smoke check after each merge
Phase 6: HANDOFF TO HUMAN
```

Rules: file exclusivity (planner assigns `files:` per task); validator runs AFTER all builders, not during; fix builders get the specific FAIL, not the full task; loop cap 3, then escalate; merge-back is the orchestrator's job (builders never merge their own branch); a merge conflict halts and escalates - it means file ownership was wrong.

Use when: 3+ tasks on non-overlapping files, well-specified, rollback point exists. Skip for: exploratory work, single-file changes, heavy file overlap.

This pattern applies to research too: N researchers parallel → reviewer consolidates → targeted follow-up → re-review.

## Deep research (citation graph)

When the technique/paper/algorithm matters deeply, three perspectives:

```
        (Backward - why it works)
              ↓
    ┌─────────────────────┐
    │ The thing itself    │   (Current - what it is)
    └─────────────────────┘
              ↓
        (Forward - how it evolved)
```

1. **Current:** read the paper and source. Understand exactly what it does.
2. **Backward:** read references and prior work. Answers "why does it work the way it works?"
3. **Forward:** newer work that built on it. Answers "what have others done with this?"

Reviewer consolidates all three.

Use for: implementing a paper's technique, adopting an algorithm, technologies whose internals matter. Skip for: feasibility checks, API lookups, short-term details.

## TODO priorities

| Annotation | Severity | Meaning |
|------------|----------|---------|
| `TODO(0)` | Critical | Never merge - resolve before PR |
| `TODO(1)` | High | Major bug or architectural flaw - fix before release |
| `TODO(2)` | Medium | Minor bug or missing feature - fix soon |
| `TODO(3)` | Low | Polish, tests, docs - fix when convenient |
| `TODO(4)` | Question | Investigation - resolve before finalizing design |
| `PERF` | Performance | Optimization opportunity |

`TODO(0)` and `TODO(1)` are merge blockers. `TODO(4)` should become a research question or resolve before plan finalization. Always include a brief description: `TODO(2): handle empty input`.

## Commits

When an agent is instructed to commit:

- `git add <specific-file>` - never `-A` or `.`.
- Never commit `.compass/tmp/` or draft handoffs not ready for source control.
- Imperative mood. Explain *why* (from conversation), not just *what* (from diff).
- After committing: `git log --oneline -3` to confirm.
- Only commit when explicitly instructed.

## Status transitions

```
draft → review → approved → active → done → archived
```

| Transition | Who | When |
|-----------|-----|------|
| draft → review | Agent | Ready for human review |
| review → approved | Human | Reviewed and approved |
| approved → active | Agent/Human | Work begun |
| active → done | Agent | Task complete, tests pass |
| done → archived | Agent/Human | Moved out of hot path |

## Required artifacts

A Compass project isn't properly set up without:

- [ ] At least one **spec** (project vision/purpose).
- [ ] At least one **ADR** (recorded decision).
- [ ] `index.md` linking all documents.
- [ ] `active.md` tracking current work.
- [ ] `meta/config.yaml` with counters.
- [ ] `meta/lessons-catalog.yaml` (can be empty).

If any are missing, flag and request creation.

## Compass uses Compass

Bootstrapping a new project applies the same methodology - Bootstrap creates `SPEC-001` for project setup, tasks tracked in `active.md`, decisions become ADRs. Not a special case; the standard workflow applied to itself.

## Handoffs

When a session ends with work in progress, create a handoff via `/compass:handoff create`:
- Compress session state into a portable document.
- Capture git state (branch, commit), task progress, file references, decisions, blockers.
- Use `file:line` references, never copy large code blocks.
- Save to `.compass/handoffs/YYYY-MM-DD_HH-MM-SS_description.md`.

When resuming, `/compass:handoff resume <path | PLAN-NNN>`:
- Verify git branch, commit, file existence.
- Classify scenario: clean continuation, diverged codebase, incomplete work, or stale handoff.
- Present situational report before acting.
- Never blindly trust a handoff.

## Debug isolation

For errors and test failures, use the `debug` agent, not the main conversation. Preserves the main context window, keeps scope focused, produces a structured report. Read-only.

## Autopilot

For well-scoped S/M tasks, `/compass:autopilot` runs the full pipeline in one session. Pauses for human confirmation after research and after planning. Never use for L+, sensitive systems, or ambiguous requirements.

## Validation

After the builder marks tasks done, the `validator` verifies that implementation matches plan:
- Reads the plan and diffs git history.
- Classifies as "matches plan," "deviation (improvement)," or "deviation (problem)."
- Audits checkbox state - flags items marked done with no changes.
- Compiles a manual verification checklist.
- Read-only.

Run before any handoff or PR on non-trivial work.

## Retroactive entry

`status: done` is valid as an initial status for retroactively documented work. When a commit exists without Compass artifacts, `/compass:retroactive` creates minimal entries: a spec with status `done (retroactive)`, a pre-checked task under "Recently Completed", optionally an ADR. Recovery path, not a shortcut.

## Plan iteration

Plans are living. When feedback requires updating an approved plan, use `/compass:plan iterate <PLAN-NNN>`, not `/compass:plan new`. Surgical edits only, confirm understanding, ripple-check across sections, no unresolved questions at close.

## Tool availability

Agents depending on external tools (MCP, `gh`, specific runtimes) verify availability as step 0. If unavailable, present a clear recovery message rather than failing mid-execution.

## File organization

```
.compass/
├── index.md              - HOT: master map with 1-line summaries + [[links]]
├── active.md             - HOT: current tasks
├── backlog.md            - Cold: future tasks
├── meta/
│   ├── config.yaml       - Counters for SPEC/ADR/TASK numbering
│   └── lessons-catalog.yaml - O(1) tag lookup
├── specs/                - Specifications
├── research/             - Research findings
├── plans/                - Implementation plans
├── decisions/            - ADRs
├── lessons/              - Lessons
├── handoffs/             - Session continuity
├── prs/                  - PR descriptions
└── archive/              - Completed/retired
```

## Pattern discovery

Use the `pattern-finder` agent before writing new code to see how existing code handles similar patterns. Returns snippets with `file:line` references, shows variations, documents rather than critiques. Runs on `sonnet` for speed.

Use it when: "How does this codebase handle X?" before implementing X.

## Artifact traceability

All research, handoff, plan, and decision documents include in frontmatter:

```yaml
git_branch: "branch-name"
git_commit: "abc1234"
author: "human or agent name"
```

Enables detecting documents written against different code states, tracing decisions to the code they were based on, and knowing who produced each artifact.

## Two-tier success criteria

Every task has two verification types:

1. **Automated:** commands an agent can run (`pytest tests/`, `npm run lint`, `curl localhost:3000/health`).
2. **Manual:** checks requiring a human ("UI renders correctly on mobile", "error message is user-friendly").

After each phase's automated checks pass, pause for the human to confirm manual checks before moving to the next phase.

Agents may check off automated items after the command succeeds. They must NOT check off manual items until the human explicitly confirms.

## Common agent protocol

0. Verify tool availability (if dependent on external tools).
1. Read the hot path.
2. Identify what you're here to do.
3. Load additional context as needed.
4. Search lessons.
5. Do the work.
6. Update vault state (active.md, index.md) to reflect changes.
7. Create lessons for surprises.
