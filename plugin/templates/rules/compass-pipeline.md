---
paths:
  - "**"
---

# Compass Pipeline Rules

Hard constraints. If any of these are violated, STOP and tell the human.

## Specs

- If a spec contains implementation decisions (technology choices, architecture, API design), STOP. Specs are about the NEED, not the solution.
- If a spec's Problem section contains "and also" or describes multiple distinct problems, STOP. Split into multiple specs. One spec = one problem.
- If the Desired Outcome requires "and" to describe multiple unrelated successes, STOP. Split.
- If creating more than one spec in a single conversation, STOP. One spec, one interview, one approval.
- If a spec has `status: draft`, no research or planning may proceed based on it. Only `status: approved` specs drive the pipeline.
- If open questions exist in a spec and they were not asked to the human, STOP. Open questions are questions, not placeholders.

## Research

- If no approved spec exists for the research topic, STOP. Research must trace to a spec.
- If research findings have no confidence levels, the research is incomplete.

## Plans

- If no approved spec AND completed research exist for the plan, STOP.
- If tasks have no acceptance criteria (automated + manual verification), the plan is incomplete.
- If a task is larger than L complexity, it must be broken into subtasks.

## Build

- If no approved plan exists for the task, STOP. Do not improvise.
- If the codebase does not match what the plan describes, STOP. Do not work around mismatches.
- When executing planned tasks, spawn builder agents rather than coding in the main conversation. Builders run in isolated worktrees with automatic testing.
- When tasks have non-overlapping file ownership, spawn builders in parallel.
- Fix loop: if tests fail, respawn targeted fix builders (max 3 cycles). Then escalate.

## Testing

- Every code change gets tests. No exceptions.
- Tests must be adversarial — designed to break the code, not confirm it works.

## Validation

- Running commands is verification. Reading code is not.
- Every automated check must have a `Command run:` block with actual output.
- At least one adversarial probe is required before issuing PASS.

## Lessons

- Lessons have two categories: `process` (how to build) and `domain` (what to build).
- Spec-writers and planners should prioritize `domain` lessons.
- Builders should prioritize `process` lessons.
- Researchers should match lesson category to their research question type.

## Vault State

- After completing a task, update `.compass/active.md` — check off the task `[x]`. This is not optional.
- After creating any vault document (spec, plan, research, ADR, lesson), add it to `.compass/index.md`.
- These updates are as important as the work itself. An untracked task is invisible to the next session.

## Linking

- When mentioning a vault document in prose, ALWAYS use `[[wikilinks]]`. Not bare names, not file paths.
- This applies to every document you write: specs, research, plans, ADRs, lessons, handoffs.
- Frontmatter `depends_on` is for structured queries. Inline wikilinks are for navigation and context. Both matter.
