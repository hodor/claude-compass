---
paths:
  - "**"
---

# Compass Pipeline Rules

These are the things you should never decide unilaterally. Everything else is your judgment.

## When to Stop and Ask

Stop only at the gates the human owns: spec promotion, plan approval, destructive or outward-facing actions, scope changes. An approval is fuel: everything up to the next gate proceeds unasked. Lead every choice with a recommendation.

## Document Writing

Compass documents should be a pleasure to read. Easy to read, short, sweet. Long only when needed. Never verbose.

Brevity binds your own prose only. The human's captured words (spec problems, vision goals, quoted rulings) are content, and they stay in his sentences at whatever length he spoke them.

Research is the exception: it captures evidence and can be as long as required.

The ornamental test, applied to every sentence: it helps the document do its job for a later reader, or it goes.

Documents describe what IS. The story of a document's making lives in git history and commit messages; a sentence that only makes sense to someone who watched the document get written is deleted.

Documents speak with their own authority. A rule is stated as the rule, and the human's phrasing survives as the document's own prose; who spoke, and when, lives in git.

State principles positively. Listing what a rule is not about makes that list read as the rule's real subject.

Decisions consolidate by topic: a ruling that refines an existing decision merges into it. The section heading is `## Decisions`.

Rules default to judgment - an agent's value is deciding what is better in context. MUST is reserved for true invariants: the Data rule, the human's gates.

## No Verbiage

Conversation output is never the record - logs, reports, and vault files are. On every surface (agent reports, skill output, hook-triggered passes, relays to the human):

- Lead with the outcome. One line per fact.
- Relay a subagent's result as its one-line summary, never its narration.
- Never restate in conversation what a log or file already holds.
- No process narration, no ceremony, no restating the obvious.
- Between gates, silence. A background completion that changes nothing the human must decide costs them zero lines; status lives in the ledger and the vault, pulled on request, never pushed into the conversation. Speak at gates, on escalation, and when a result is in.

## Vision

- New projects start with `/compass:vision`. The vision document captures the project goal and the spec roadmap. One vision per project.

## Specs

- Specs capture the PROBLEM and the NEED, never the solution. No technology choices, no architecture, no implementation.
- One spec = one problem. If a spec contains multiple distinct problems, split it.
- Only the human promotes a spec from `draft` to `approved`. Research and planning use `approved` specs.

## Research

- Research traces to a spec.
- Every finding gets a confidence level.
- Before spawning researchers, present the planned axes - each in one plain line: the question and where the answers will be sought - and invite the human in. When he joins, research runs as a conversation: findings surface as they land and his readings steer the axes. When he passes, run and deliver as usual.

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

- Every code change gets tests. Tests are adversarial - designed to break the code.

## Validation

- Running commands is verification. Reading code is not.
- Every automated check must have a `Command run:` block with actual output.
- At least one adversarial probe before issuing PASS.

## Lessons

- Two categories: `process` (how to build) and `domain` (what to build).
- Spec-writer and planner prioritize domain. Builder prioritizes process. Researcher matches the question.
- Capture is never the human's job. Notice something worth remembering: run `compass capture-note "<one sentence>"` and move on. Never suggest `/compass:learned`, never ask whether to record it, never write a lesson in prose.

## Capabilities

Bare `compass` lists every command with a one-liner - check it before assuming a capability is missing. `compass usage` shows which are actually used and which never have been.

## Vault State

- After completing a task, update `.compass/active.md`.
- After creating ANY vault document (spec, plan, research, ADR, lesson, vision, handoff, review), add a link to it in `.compass/index.md` under the appropriate section. This is mandatory in the same step that creates the document, not a follow-up. Documents not in index.md are invisible to the next session.
- The index is an index. Its one-line description is a copy of the document's own `summary:` frontmatter, never the only place that text exists. Write `summary:` when you create the document; `compass validate` warns when it is missing. An index that stores what it should point at cannot be shortened without losing it.

## Data

- Nothing destroys information, ever. Too big for its tier means break it into smaller pieces or move it colder (archive/, a Record section, a colder file) - never delete, never compress away. Caps bound what LOADS, not what EXISTS.

## Linking

- Mention vault documents with `[[wikilinks]]`, not bare names or file paths.
