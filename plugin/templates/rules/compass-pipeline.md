---
paths:
  - "**"
---

# Compass Pipeline Rules

These are the things you should never decide unilaterally. Everything else is your judgment.

## When to Stop and Ask

Only stop for strategic decisions the human owns. Don't ask permission for things within your scope. Don't ask permission twice for things the human already approved.

## Document Writing

Compass documents should be a pleasure to read. Easy to read, short, sweet. Long only when needed. Never verbose.

Research is the exception: it captures evidence and can be as long as required.

## Vision

- New projects start with `/compass:vision`. The vision document captures the project goal and the spec roadmap. One vision per project.

## Specs

- Specs capture the PROBLEM and the NEED, never the solution. No technology choices, no architecture, no implementation.
- One spec = one problem. If a spec contains multiple distinct problems, split it.
- Only the human promotes a spec from `draft` to `approved`. Research and planning use `approved` specs.

## Research

- Research traces to a spec.
- Every finding gets a confidence level.

## Plans

- Plans trace to an approved spec and completed research.
- Tasks have automated AND manual verification criteria.
- Tasks larger than L get broken into subtasks.
- Only the human approves a plan. Tasks are not distributed to `active.md`/`backlog.md` before approval.

## Build

- Builders execute approved planned tasks. If no approved plan exists, ask the human what to do instead of improvising.
- If the codebase contradicts what the plan describes, stop and report the mismatch.
- When tasks have non-overlapping file ownership, builders can run in parallel.
- Fix loop: if tests fail, respawn targeted fix builders up to 3 cycles, then escalate.

## Testing

- Every code change gets tests. Tests are adversarial — designed to break the code.

## Validation

- Running commands is verification. Reading code is not.
- Every automated check must have a `Command run:` block with actual output.
- At least one adversarial probe before issuing PASS.

## Lessons

- Two categories: `process` (how to build) and `domain` (what to build).
- Spec-writer and planner prioritize domain. Builder prioritizes process. Researcher matches the question.

## Vault State

- After completing a task, update `.compass/active.md`.
- After creating ANY vault document (spec, plan, research, ADR, lesson, vision, handoff, review), add a link to it in `.compass/index.md` under the appropriate section. This is mandatory in the same step that creates the document, not a follow-up. Documents not in index.md are invisible to the next session.

## Linking

- Mention vault documents with `[[wikilinks]]`, not bare names or file paths.
