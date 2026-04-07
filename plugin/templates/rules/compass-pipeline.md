---
paths:
  - "**"
---

# Compass Pipeline Rules

Hard constraints. If any of these are violated, STOP and tell the human.

## Delegation

- Do NOT write code directly in the main conversation. Spawn the builder agent.
- Do NOT write specs directly. Spawn the spec-writer agent.
- Do NOT do research directly. Spawn the researcher agent.
- Do NOT create plans directly. Spawn the planner agent.
- The main conversation is an ORCHESTRATOR. It delegates to agents, reviews their output, and makes decisions. It does not do the work itself.

## Specs

- If a spec contains implementation decisions (technology choices, architecture, API design), STOP. Specs are about the NEED, not the solution.
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
