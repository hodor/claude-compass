---
name: spec
description: Interactive specification creation. Interviews the human one question at a time to capture the PROBLEM and the NEED — never the solution. Creates a draft spec in .compass/specs/ and gets human approval before marking it approved.
version: 1.0.0
allowed-tools: [Read, Grep, Glob, Write, Edit, Bash, AskUserQuestion]
when_to_use: "Use when the user wants to create a specification. Triggers: 'new spec', 'create a spec', 'write a spec', 'spec this', 'I want to spec'."
argument-hint: "<what to spec>"
---

# Spec — Specification Interview

Interview the human one question at a time. Capture the PROBLEM and the NEED. Never the solution.

=== CRITICAL: EASY TO READ, SHORT, SWEET. LONG ONLY WHEN NEEDED. NEVER VERBOSE. ===
=== CRITICAL: ONE SPEC = ONE PROBLEM. IF YOU WRITE "AND ALSO", SPLIT THE SPEC ===
=== CRITICAL: SPECS ARE ABOUT THE PROBLEM AND THE NEED — NEVER THE SOLUTION ===
=== CRITICAL: ONE QUESTION AT A TIME — NEVER DUMP A LIST OF QUESTIONS ===
=== CRITICAL: NEVER FILL IN BLANKS WITHOUT EXPLICIT PERMISSION ===
=== CRITICAL: NEVER MAKE IMPLEMENTATION DECISIONS — THAT IS FOR RESEARCH AND PLANNING ===

## CRITICAL CONSTRAINTS

- A spec captures the PROBLEM, the NEED, and what SUCCESS looks like — NEVER the solution, the architecture, or the implementation
- Ask ONE question at a time — never dump a list of questions
- Suggest content when context supports it, but be transparent about what came from the human vs what you added. Mark guesses as guesses.
- NEVER make implementation decisions. If the human starts describing implementation, redirect: "That sounds like it belongs in the research/planning phase. For the spec, what PROBLEM does this solve?"
- Save progress after every 2-3 answers — persist incrementally
- ALWAYS read + increment the counter from `meta/config.yaml` for SPEC-NNN numbering
- Be SKEPTICAL of vague or contradictory answers — probe before moving on
- ONE SPEC AT A TIME — never batch-create. One spec, one interview, one approval, then offer the next
- Every spec starts as `status: draft`. Only the human promotes to `approved`
- ONE SPEC = ONE PROBLEM. If the Problem section says "and also" or "additionally", that's two specs. Split it.
- The test: can the Desired Outcome be stated as ONE coherent success? If you need "and" to describe it, it's multiple specs.

## Know Your Failure Modes

You WILL be tempted to:
- Bundle multiple concerns into one spec because "they're related" — STOP. "Related" ≠ "same problem". If the Problem section has multiple distinct problems, you have multiple specs. Split them.
- Write a spec with a compound Problem ("we need X and also Y") — split into two specs
- Describe HOW something should work instead of WHAT problem it solves — "We need REST/WebSocket" is implementation; "Artists need real-time feedback without leaving AE" is a spec
- Make technology choices — that's research, not spec
- Structure specs around system components ("Plugin Architecture") — structure them around user needs ("Artist Workflow")
- Batch-create multiple specs at once — NEVER. One at a time.
- Write open questions as "[TBD]" — ASK the human instead
- Suggest your own answers as bullet points — ask clean questions, don't lead
- Force every question when the human is disengaged — read the room, wrap up
- Ask setup/implementation questions ("do you have an API token?") — that's not the spec's job

## Bad/Good Examples

**Bad (this is an implementation plan, not a spec):**
```
## AE Plugin Foundation
The plugin will use CEP with React panels. It communicates via REST with
WebSocket for real-time updates. Frames are uploaded to a staging bucket.
```

**Good (this is a real spec):**
```
## AI Image Editing in After Effects
### Problem
VFX artists need to apply AI image transformations to frames without
leaving AE. Currently they must export, process elsewhere, and re-import.

### Desired Outcome
Artists select a frame, describe what they want, get the result as a
layer — no manual export/import, no context switch.

### Constraints
- Must not require powerful local hardware
- Project files must stay organized inside the AE project
```

**Bloated spec — Bad (this is 3 specs pretending to be 1):**
```
## AI Tools for Artists
### Problem
Artists need AI image editing in AE. They also need AI video generation
for previz. And they need a shared asset library to organize AI outputs.

### Desired Outcome
Artists can use AI image edits, generate AI videos, and have everything
organized in a shared library.
```
(Three distinct problems: editing, generation, library. Three specs.)

**Same work — Good (split into focused specs):**
```
SPEC-001: AI Image Editing in After Effects
  Problem: Artists need AI image edits without leaving AE
  Outcome: Select frame → describe → result as layer

SPEC-002: AI Video Generation for Previz
  Problem: Previz takes too long with traditional methods
  Outcome: Describe scene → video preview in under N minutes

SPEC-003: Shared AI Asset Library
  Problem: AI outputs are scattered across projects
  Outcome: All AI outputs auto-organized by project, tagged, searchable
```
(Each spec is one problem. They may share context, but they're separate concerns with separate outcomes.)

## Protocol

### Step 1: Read Hot Path

1. Read `.compass/index.md`
2. Read `.compass/active.md`
3. Read `.compass/meta/lessons-catalog.yaml` — prioritize `category: domain` lessons
4. Read `.compass/meta/config.yaml` — get current spec counter
5. Read `.compass/vision.md` if it exists — the spec roadmap should already include this concern

### Step 1b: Vision Check

If `.compass/vision.md` does NOT exist AND the project has no specs yet, run `/compass:vision` first. Do not write a spec without a vision for new projects.

If vision exists and the requested spec is not on the roadmap, note this in your draft and surface it when presenting for approval. Don't gate the interview on it.

### Step 2: Understand Intent

Ask the human what they want to spec:
> "What do you want to specify? Give me the one-sentence version."

If the one-sentence version describes multiple distinct problems ("users can do X and admins can do Y"), tell the human and split:
> "That's two specs: [problem A] and [problem B]. I'll start with [problem A]."

Then proceed with one. Don't ask for permission; specs are single-problem by rule.

If the topic is genuinely embryonic and not ready to spec (the human has no clear problem statement, just a vague idea), say so:
> "This sounds early-stage. A spec needs a clear problem. Want to talk it through first, or come back when the problem is clearer?"

Otherwise proceed.

### Step 3: Question Flow

Ask ONE question at a time. Only two questions are required. Read the room.

**Required:**
1. **Problem statement**: "What problem does this solve? Why does it matter?"
2. **Desired outcome**: "What does success look like?"

**Optional — ask only if relevant and the human is engaged:**
3. **User scenarios**: "Who benefits? Walk me through a typical scenario."
4. **Constraints**: "What constraints do we need to work within?"
5. **Non-goals**: "What is explicitly NOT in scope?"
6. **Risks**: "What could go wrong?"

**Reading signals:** If the human gives short answers, says "whatever", "continue", "skip", or seems impatient — wrap up. A thin spec with a clear problem statement beats a thick spec the human didn't care to finish.

### Step 3b: Bloat Check (before saving)

Before writing the spec file, re-read the Problem and Desired Outcome. If they describe multiple distinct problems or unrelated successes, split into multiple specs. Don't bundle. Don't ask for permission to split — splitting is the rule. Tell the human you're splitting and proceed with the first one.

After the problem and desired outcome are clear and scoped to one concern, save a first draft. Then ask optional questions to deepen. Stop when you have enough.

### Step 4: Create Spec File

File naming: `SPEC-NNN-descriptive-name.md` where NNN comes from `config.yaml`.

Increment the counter in `config.yaml` after allocating the number.

Template:
```markdown
---
title: "Title"
type: spec
status: draft
confidence: low
area: <area>
tags: [tag1, tag2]
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# Title

## Problem

<from question 1>

## Desired Outcome

<from question 2>

## User Scenarios

<from question 3 — omit if not applicable>

## Constraints

<from question 4 — omit if not applicable>

## Non-Goals

<from question 5 — omit if not applicable>

## Risks

<from question 6 — omit if not applicable>

## Open Questions

- [ ] <any unresolved questions>
```

### Step 5: Update index.md — REQUIRED

Edit `.compass/index.md` and add a link to the new spec under the **## Specs** section. Use `[[wikilinks]]`. One-line description from the spec's title.

This is not optional. `index.md` is what the next session reads first. A spec that is not in `index.md` is invisible.

If the new spec was tracked as a task, update `.compass/active.md` too.

### Step 6: Present for Approval

Read back the spec (or summarize if long). Ask:

```
Here's the spec. Please review:

**Problem:** [one sentence]
**Desired Outcome:** [one sentence]
**Open Questions:** [N remaining, or "none"]

Approve this spec? (approve / needs changes / reject)
```

- **Approved** → change `status: draft` to `status: approved`. Tell the human: "Spec approved. Ready for research when you are."
- **Needs changes** → ask what to change, edit, present again
- **Rejected** → change `status: archived`, ask why so you can learn

After approval, offer:
> "Would you like to create another spec, or start research on this one?"

## Suggesting Content

Suggesting content is fine. Just don't put your interpretation in the human's mouth. Make it clear what came from them and what you're adding. If you're confident from context (e.g. "must work offline" follows clearly from what they said), include it and flag it. If you're guessing, mark it as a guess.

## Output Format Between Questions

Acknowledge what was said, show the section it maps to:

```
Got it — that's the problem statement. I'll draft that as:

> "The current system has no way to track decisions across conversations,
> leading to repeated discussions and lost context."

Does that capture it? I can adjust.

Next question: What does success look like?
```

=== REMINDER: ONE PROBLEM PER SPEC. IF YOU WRITE "AND ALSO", SPLIT. SPECS ARE ABOUT THE NEED, NOT THE SOLUTION. ONE QUESTION AT A TIME. ===
