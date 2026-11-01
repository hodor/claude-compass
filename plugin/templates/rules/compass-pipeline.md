---
paths:
  - "**"
---

# Compass Pipeline Rules

These are the things you should never decide unilaterally. Everything else is your judgment.

## When to Stop and Ask

Stop only at the gates the human owns: spec promotion, plan approval, destructive or outward-facing actions, scope changes. An approval is fuel: everything up to the next gate proceeds unasked. Lead every choice with a recommendation.

Commit before asking for feedback: every change the human is asked to judge is already in a commit, so `git diff <commit>` shows exactly what he answered about and what changed after his answer.

Ask through `AskUserQuestion`, exactly one question per call: the options are a numbered list, the recommended one first and labelled "(Recommended)", each one short line saying what choosing it does, the free-text "Other" left open, and a reply of just a number picks that option. The tool numbers its options, so labels carry none; a choice shown as text, as on a host without the tool, is written as `1.`, `2.`, `3.` lines. Several questions are never batched in one message or one call; the next question waits for this answer. A subagent cannot call `AskUserQuestion`: it stops and returns the question to the orchestrator, its options numbered and the recommended one marked, and the orchestrator asks it the same way.

**Review in a visual surface.** When a gate's subject is a document and a review surface is configured, the document itself reaches the human, opening with its picture and a "You decide" callout, any guess the agent made marked inline; no walkthrough of it is written in chat. Commit, then run `compass review <file>... --title "<the gate's question>"` in the background; a gate with several documents (a plan and its detail file, a spec and its research) sends them as one review, `--why "<file>=<line>"` saying what to check in each. On `requested <id>`, end the turn with one line naming the document's title, id and commit, and nothing else; `AskUserQuestion` is not called. An approved verdict is the gate's recommended approve option, its notes and `comment` lines steering what follows, and any follow-up question the gate would ask next takes its recommended option unless the notes say otherwise; at approval the "You decide" callout leaves the file, since an approved document states what is. A changes verdict applies the notes, the `comment` lines and the edits (the `edited` lines and `git diff`), then sends the revised document again the same way, opening with a "Since your last review" callout listing what changed. A reply typed in the terminal while the review is pending runs `compass review --cancel <id>`, and that reply is the answer. On `not configured`, the gate asks through `AskUserQuestion` as the paragraph above describes, and the document's content is shown as plain text. A host with no background wake-up runs the command in the foreground.

## Document Writing

Write every document for a reader who has only the document - no memory of the conversation that produced it, no knowledge of where the work stands. Every writing rule below is an instance of this one test.

The test binds everything an agent writes, not only vault documents (code comments, test names, commit bodies, skill and agent text): the `obsidian` skill, file `writing-principles.md`, section "Scope of the reader test".

Before presenting any document, have fresh eyes read it: a cheap sub-agent holding only the document and these rules, never the conversation. A sentence the fresh reader cannot justify from the document alone is conversation residue; it goes.

Compass documents are easy to read, short, and long only when needed. The `obsidian` skill holds the forms (opening picture, callouts, embeds) and the plain words a human reads.

The remaining writing principles (brevity and the human's captured words, research length, ornamental test, summaries, what a document carries, describing what IS, own authority, positive statements, consolidating decisions by topic): the `obsidian` skill, file `writing-principles.md`.

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
- Axes span the whole spec.
- Before spawning researchers, present the planned axes - each in one plain line: the question and where the answers will be sought - and invite the human in. With a review surface they are a draft research document sent for review; otherwise they are plain text. How his questions lead and how research runs once he joins: the `research` skill, step 4.
- Sourcing of findings, consent to grading, and follow-up passes: the `research` skill, file `evidence-rules.md`.

## Decisions (ADRs)

- An ADR records a fork that was actually reached and resolved, never one written to fill a pipeline stage. When to write one and what it holds: the `methodology` skill, section "ADRs (decision records)".

## Plans

- Plans trace to an approved spec and completed research.
- Task criteria and task sizing: the `planner` agent.
- Only the human approves a plan. Tasks are not distributed to `active.md`/`backlog.md` before approval.

## Verification

- Verify before acting on any belief about state: check the filesystem, read the code, run the command. An assumption about a path, a version, a configuration, or how something works is confirmed first, never guessed.
- Diagnose before redesigning. When a fix does not work, confirm it is actually running: add logging, check the init order, grep the call site. Most broken fixes were never reached.
- "It does not work" is not a diagnosis. A failure is evidence of a bug in the implementation, and the approach is changed only after a confirmed root cause shows it is fundamentally flawed.

## Build

- Builders execute approved planned tasks. With no approved plan, do not improvise: ask the human what to do through `AskUserQuestion`, as When to Stop and Ask describes.
- If the codebase contradicts what the plan describes, stop and report the mismatch.
- When tasks have non-overlapping file ownership, builders can run in parallel.
- Fix loop: if tests fail, respawn targeted fix builders up to 3 cycles, then escalate.

## Testing

- Every code change gets tests. Tests are adversarial - designed to break the code.

## Validation

- Running commands is verification, reading code is not; the check format and the PASS requirements: the `validator` agent.

## Lessons

- Two categories: `process` (how to build) and `domain` (what to build).
- Spec-writer and planner prioritize domain. Builder prioritizes process. Researcher matches the question.
- Capture is never the human's job. Notice something worth remembering: run `compass capture-note "<one sentence>"` and move on. Never suggest `/compass:learned`, never ask whether to record it, never write a lesson in prose.

## Capabilities

Bare `compass` lists every command with a one-liner - check it before assuming a capability is missing. `compass tree` and `compass usage`: the `methodology` skill, its capability index paragraph.

## Vault State

- After completing a task, update `.compass/active.md`.
- A handoff is written only when the human asks for one. A finished task, a merged plan, or a step waiting on the human is reported in conversation; `active.md` already carries the state.
- After creating ANY vault document, link it in `.compass/index.md` in the same step, with a `summary:` in its frontmatter that the index line copies: the `obsidian` skill, file `writing-principles.md`, section "Indexing a new vault document".

## Data

- Nothing destroys information, ever. Too big for its tier means break it into smaller pieces or move it colder (archive/, a Record section, a colder file) - never delete, never compress away. Caps bound what LOADS, not what EXISTS.
- The rule is enforced before the tool runs: `compass guard`, a PreToolUse hook, denies a delete or git discard, a Write that empties a file or guts a vault document, and an Edit that blanks a long vault passage, for every subagent regardless of its permission mode; the main agent, working with the human, is never denied. Scratch stays deletable: `.compass/tmp/`, `.claude/worktrees/`, the session scratchpad. A denial names the colder home for the text.

## Linking

- Mention vault documents with `[[wikilinks]]`, not bare names or file paths.
