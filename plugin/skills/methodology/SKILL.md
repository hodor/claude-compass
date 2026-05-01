---
name: methodology
description: The Compass development workflow pipeline — Spec, Research, Plan, Tasks, Build, Validate — with human involvement gradient, status transitions, testing mandate, and required artifacts enforcement
version: 1.0.0
allowed-tools: [Read, Glob, Grep]
---

# Methodology — The Compass Workflow

Compass provides a structured development pipeline that ensures humans own strategic decisions while AI handles execution. Every agent in the Compass system follows this methodology.

## The Pipeline

```
Vision → Spec → Research → Plan → Tasks → Build → Validate
```

Each stage produces artifacts that feed the next. Stages can be revisited, but never skipped.

**Vision** captures the project's overall goal and the landscape of needs (run once per project, or per major pivot). It produces `.compass/vision.md` and a roadmap of specs to write.

**Specs** are SINGLE-PROBLEM. One spec = one problem = one outcome. The vision step prevents the natural tendency to bundle multiple needs into a single spec.

Without vision, projects either get crammed into one giant spec or fragmented into incoherent specs without shared direction.

## Hot Path

Every agent MUST read the hot path first, before doing any other work:

1. `.compass/index.md` — Master map of all project documents
2. `.compass/active.md` — Current tasks (in-progress + blocked)
3. `.compass/meta/lessons-catalog.yaml` — Scan for relevant lessons

This is the "cache line" — the minimum context needed to orient. Only after reading the hot path should an agent load additional documents (specs, research, plans) as needed.

## Human Involvement Gradient

| Level | Human Role | AI Role | Autonomy |
|-------|-----------|---------|----------|
| Specs | Human models, makes decisions | Ask questions one at a time, structure answers | LOW — agent never fills blanks without permission |
| Research | Human reviews findings, redirects | Execute autonomously, present evidence with confidence | MEDIUM — agent works independently but never decides |
| Plans | Human approves before tasks are created | Propose based on specs + research | MEDIUM — agent proposes, human approves |
| Tasks | Human reviews output | Execute autonomously, write tests, update status | HIGH — agent works independently within defined scope |
| Decisions (ADRs) | Human approves | Present options with evidence | LOW — agent presents, human decides |

**CRITICAL: Agents must FORCE humans to make decisions.** Never decide silently at strategic levels. If unsure, ask. If the decision has architectural implications, create an ADR.

## Decision Recording (ADRs)

Architecture Decision Records are **orthogonal to the pipeline** — they can be created at any stage when a significant decision is made.

When to create an ADR:
- Choosing between competing approaches with meaningful trade-offs
- Adopting or abandoning a technology, pattern, or convention
- Any decision that would surprise a future team member

ADRs live in `.compass/decisions/` and follow the `ADR-NNN-descriptive-name.md` naming convention.

## Testing Mandate

**Non-negotiable.** Every agent that writes code MUST:

1. **Determine test type**: Analyze the project and code to decide between property-based tests, unit tests, or integration tests. The agent decides — this is not prescribed.
2. **Set up test location**: Tests live OUTSIDE `.compass/`, integrated with the project's own code. The agent defines a centralized test structure appropriate for the project's language and framework.
3. **Write tests**: Cover the code being written or modified.
4. **Run full test suite**: Execute ALL existing tests to ensure nothing is broken.

Tests are the safety net that allows humans to trust AI-written code. Skipping tests is never acceptable.

## Task Execution

When a plan has approved tasks in `active.md`, they should be executed by **builder agents**, not by the main conversation writing code inline. This is important because:
- Builders run in isolated worktrees (changes are reviewable before merge)
- Builders auto-trigger the tester agent via SubagentStop hook
- Builders follow the full protocol (scope check, smoke test, code review)
- The main conversation loses none of this if it codes directly

The main conversation's job during execution is **orchestration**: spawn builders, review their output, handle failures, update vault state.

## Parallel Execution Pattern

When a plan has multiple tasks that can run in parallel (non-overlapping file ownership), use this pattern:

```
Phase 1: PARALLEL BUILDERS
  ├── Builder A (files: X, Y) — isolated worktree
  ├── Builder B (files: Z, W) — isolated worktree
  └── Builder C (files: V) — isolated worktree
         ↓ all complete, tester auto-runs on each
Phase 2: QA REVIEW (validator agent)
  → Structured report: PASS / FAIL / PARTIAL per task
         ↓
Phase 3: TARGETED FIXES (conditional)
  ├── Fix Builder 1 (FAIL items from task A)
  └── Fix Builder 2 (FAIL items from task B)
         ↓ re-test
Phase 4: RE-REVIEW (loop back to Phase 3, max 3 iterations)
         ↓ all PASS or stuck
Phase 5: HANDOFF TO HUMAN
  → Final report, diff summary, manual verification guide
```

**Key rules:**
- **File exclusivity**: each builder owns non-overlapping files. The planner assigns `files:` per task.
- **QA as gate**: the validator runs AFTER all builders finish, not during.
- **Targeted fixes**: fix builders get the specific FAIL diagnosis, not the full task. Surgical fixes.
- **Loop cap**: max 3 QA cycles. If issues persist, escalate to human with remaining FAILs.
- **Integration testing**: when a test environment exists, QA should deploy and test, not just static analysis.

**When to use:**
- Plan has 3+ tasks that touch non-overlapping files
- Tasks are well-specified (not exploratory)
- A checkpoint exists to rollback to

**When NOT to use:**
- Exploratory work where requirements are unclear
- Single-file changes (just run one builder)
- Tasks with heavy file overlap (serialize instead)

This pattern also applies to **research**: spawn N researchers in parallel → reviewer consolidates → targeted follow-up researchers for gaps → re-review. Same structure, different agents.

## Deep Research Pattern (Citation Graph)

When researching a technique, paper, algorithm, or implementation — going deep requires three perspectives:

```
        (Backward — why it works)
              ↓
    ┌─────────────────────┐
    │ The thing itself    │   (Current — what it is)
    └─────────────────────┘
              ↓
        (Forward — how it evolved)
```

Spawn three researchers in parallel:

1. **Deep researcher (Current)**: read the original paper and source code. Understand exactly what it does, how it works, and the authors' claims.

2. **Backward researcher (Ancestors)**: find the papers, references, and prior work that the original cites or builds on. This answers "why does it work the way it works?" Critical for understanding trade-offs and knowing what breaks if you change something.

3. **Forward researcher (Descendants)**: find newer work that built on the original — papers that cite it, implementations that extend it, real-world usage. This answers "what have others done with this?" Provides inspiration for the plan.

Then the reviewer consolidates all three perspectives.

**When to use this pattern:**
- Implementing a specific technique from a paper
- Adopting an algorithm or approach
- Working with a technology whose internals matter (not just its API)
- High-stakes decisions where understanding foundations matters

**When NOT to use:**
- Quick feasibility checks
- Looking up syntax or API usage
- Short-term implementation details

## TODO Priority Annotations

Use a priority-based TODO annotation system throughout the codebase. These are greppable and can be enforced by CI:

| Annotation | Severity | Meaning |
|------------|----------|---------|
| `TODO(0)` | Critical | Never merge — must be resolved before PR |
| `TODO(1)` | High | Architectural flaw or major bug — fix before release |
| `TODO(2)` | Medium | Minor bug or missing feature — fix soon |
| `TODO(3)` | Low | Polish, tests, documentation — fix when convenient |
| `TODO(4)` | Question | Investigation needed — resolve before finalizing design |
| `PERF` | Performance | Optimization opportunity — not a bug, but worth revisiting |

Rules:
- `TODO(0)` and `TODO(1)` are merge blockers — agents MUST resolve them before marking a task done
- `TODO(2)` and `TODO(3)` are acceptable in merged code but should be tracked
- `TODO(4)` should be converted to a research question or resolved before the plan is finalized
- Always include a brief description: `TODO(2): handle edge case where input is empty`

## Commit Conventions

When an agent is instructed to commit:

- Always use `git add <specific-file>` — never `git add -A` or `git add .`
- Never commit `.compass/tmp/` contents or draft handoffs not ready for source control
- Commit messages use imperative mood and explain *why* (from conversation context), not just *what* (from diff)
- After committing, run `git log --oneline -3` to confirm
- Agents should only commit when explicitly instructed — never auto-commit without human approval

## Status Transitions

```
draft → review → approved → active → done → archived
```

| Transition | Who | When |
|-----------|-----|------|
| draft → review | Agent | Work is complete, ready for human review |
| review → approved | Human | Human has reviewed and approved |
| approved → active | Agent/Human | Work has begun |
| active → done | Agent | Task completed, tests pass |
| done → archived | Agent/Human | Moved out of hot path |

## Required Artifacts Enforcement

A Compass project is not properly set up unless it has:

- [ ] At least one **spec** (the vision/purpose of the project)
- [ ] At least one **ADR** (a recorded decision)
- [ ] An `index.md` with links to all documents
- [ ] An `active.md` tracking current work
- [ ] A `meta/config.yaml` with numbering counters
- [ ] A `meta/lessons-catalog.yaml` (can be empty)

**If any of these are missing, the agent MUST flag this and request their creation.** These are not optional — they are the minimum viable vault.

## Compass Uses Compass

When bootstrapping a new project, Compass applies its own methodology:
- Bootstrap creates `SPEC-001` for the project setup itself
- Tasks for onboarding are tracked in `active.md`
- Decisions about project setup become ADRs

This is not a special case — it's the standard workflow applied to itself.

## Handoffs (Session Continuity)

When a conversation ends with work in progress, create a handoff document to preserve context for the next session.

**Creating a handoff** (use the `handoff-create` agent):
- Compress session state into a portable document
- Capture git state (branch, commit hash), task progress, file references, decisions, blockers
- Use `file:line` references, never copy large code blocks
- Save to `.compass/handoffs/YYYY-MM-DD_HH-MM-SS_description.md`

**Resuming from a handoff** (use the `handoff-resume` agent):
- Read the handoff, verify current state matches (git branch, commit, file existence)
- Classify scenario: clean continuation, diverged codebase, incomplete work, or stale handoff
- Present situational report before taking any action
- Never blindly trust a handoff — always verify

## Debug Isolation

When investigating errors, test failures, or unexpected behavior, use the `debug` agent instead of debugging in the main conversation. This:
- Preserves the main conversation's context window for implementation
- Keeps the investigation scope focused
- Produces a structured report that the builder can act on
- Is read-only — the debug agent never edits files

## Autopilot Mode

For well-scoped S/M tasks, the `autopilot` agent can run the full pipeline (research → plan → build) in a single session. Constraints:
- Only for S or M complexity tasks
- Pauses for human confirmation after research and after planning
- Follows all standard rules (testing mandate, ADRs, lessons)
- Never appropriate for L+ tasks, sensitive systems, or ambiguous requirements

## Validation

After the builder marks tasks done, the `validator` agent can verify that the implementation matches the plan:
- Reads the plan and diffs git history against it
- Classifies changes as "matches plan", "deviation (improvement)", or "deviation (problem)"
- Audits checkbox state — flags items marked done with no corresponding changes
- Compiles manual verification steps into a final checklist
- Read-only: reports findings, does not edit files

Invoke the validator before creating a handoff or PR for any non-trivial implementation.

## Retroactive Entry

`status: done` is a valid initial status for retroactively documented work. When a commit exists without Compass artifacts, the `retroactive` agent can create minimal vault entries:
- A SPEC with status: done capturing what was built and why
- A pre-checked task in active.md under "Recently Completed"
- Optional ADR if the implementation involved a significant decision

This is not a shortcut around the pipeline — it's a recovery path for work that preceded the vault.

## Plan Iteration

Plans are living documents. When feedback requires updating an approved plan, use the `planner-iterate` agent — not the planner (which creates new plans). Plan iteration follows these principles:
- Surgical edits only — never rewrite the plan wholesale
- Confirm understanding before making changes
- Check consistency ripples — a change in one section may require updates in others
- No unresolved questions — resolve before closing the iteration

## Tool Availability

Agents that depend on external tools (MCP servers, CLI tools like `gh`, specific runtimes) should verify availability as Step 0 before beginning work. If a required tool is unavailable, present a clear message with recovery instructions rather than failing mid-execution.

## File Organization

```
.compass/
├── index.md              — HOT: master map with 1-line summaries + [[links]]
├── active.md             — HOT: current tasks (in-progress + blocked + next up)
├── backlog.md            — Cold: future tasks
├── meta/
│   ├── config.yaml       — Counters for SPEC/ADR/TASK numbering
│   └── lessons-catalog.yaml — O(1) tag lookup for lessons
├── specs/                — Specifications
├── research/             — Research findings
├── plans/                — Implementation plans
├── decisions/            — Architecture Decision Records
├── lessons/              — Lessons learned
├── handoffs/             — Session continuity documents
├── prs/                  — PR descriptions
└── archive/              — Completed/retired documents
```

## Pattern Discovery

When implementing new code, use the `pattern-finder` agent to see how existing code handles similar patterns before writing your own. The pattern-finder:
- Returns concrete code snippets with `file:line` references
- Shows multiple variations if they exist
- Is a documentarian — it does not critique or recommend, only shows what exists
- Runs on the `sonnet` model for speed — it's a lightweight lookup, not deep analysis

Use it when: "How does this codebase handle X?" before implementing your own version of X.

## Artifact Traceability

All research, handoff, plan, and decision documents MUST include git traceability in their frontmatter:

```yaml
git_branch: "branch-name"     # Current branch when document was created
git_commit: "abc1234"         # Short commit hash at creation time
author: "human or agent name" # Who created the document
```

This enables:
- Detecting when a document was written against a different state of the codebase
- Tracing decisions back to the code they were based on
- Knowing who (or what agent) produced each artifact

## Two-Tier Success Criteria

Every task in a plan MUST have two types of verification:

1. **Automated verification**: Commands, tests, or scripts that an agent can run to verify the task is complete. Examples: `pytest tests/`, `npm run lint`, `curl localhost:3000/health`.
2. **Manual verification**: Checks that require a human to perform. Examples: "UI renders correctly on mobile", "error message is user-friendly", "flow matches the spec's intent".

After each phase's automated verification passes, **pause for the human to perform manual verification** before proceeding to the next phase.

Agents MUST NOT check off manual verification items in a plan or active.md until the human explicitly confirms those checks passed. Automated verification items may be checked off by the agent after the command succeeds.

## Agent Protocol (Common to All Agents)

0. Verify tool availability (if the agent depends on external tools)
1. Read the hot path (index.md, active.md, lessons catalog)
2. Identify what you're here to do
3. Load additional context as needed (specific specs, research, plans)
4. Search for relevant lessons
5. Do the work
6. Update vault state (active.md, index.md) to reflect changes
7. Create lessons if you encountered something surprising
