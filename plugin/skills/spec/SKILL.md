---
name: spec
description: Interactive specification creation. Interviews the human one question at a time to capture the PROBLEM and the NEED, never the solution. Creates a draft spec in .compass/specs/ and gets human approval before marking it approved.
version: 1.0.0
allowed-tools: [Read, Grep, Glob, Write, Edit, Bash, AskUserQuestion]
when_to_use: "Use when the user wants to create a specification. Triggers: 'new spec', 'create a spec', 'write a spec', 'spec this', 'I want to spec'."
argument-hint: "<what to spec>"
---

You interview the human one question at a time to capture a single problem and its desired outcome. Specs describe the NEED, not the solution. Implementation decisions belong to research and planning, not here.

One spec captures one problem. If the Problem section needs "and also" or the Desired Outcome needs "and" to describe success, that's two specs. Split.

## Protocol

### 1. Read the hot path

`.compass/index.md`, `.compass/active.md`, `.compass/meta/lessons-catalog.yaml` (prioritize `category: domain` lessons), `.compass/meta/config.yaml` (for the spec counter), `.compass/vision.md` (if it exists — the spec roadmap should already include this concern).

If `vision.md` doesn't exist and the project has no specs yet, run `/compass:vision` first. Don't write a spec without a vision for a new project.

If vision exists and the requested spec isn't on the roadmap, note this in your draft and surface it at approval. Don't gate the interview on it.

### 2. Understand the intent

Ask the human:
> "What do you want to specify? Give me the one-sentence version."

If the answer describes multiple distinct problems ("users can do X and admins can do Y"):
> "That's two specs: [problem A] and [problem B]. I'll start with [problem A]."

Proceed with one. Don't ask permission; specs are single-problem by rule.

If the topic is genuinely embryonic and not ready to spec:
> "This sounds early-stage. A spec needs a clear problem. Want to talk it through first, or come back when the problem is clearer?"

### 3. Interview, one question at a time

Two questions are required. The rest are optional. Read the room — if the human gives short answers, says "whatever" / "continue" / "skip", or seems impatient, wrap up. A thin spec with a clear problem statement beats a thick spec the human didn't care to finish.

**Required:**
1. What problem does this solve? Why does it matter?
2. What does success look like?

**Optional:**
3. Who benefits? Walk me through a typical scenario.
4. What constraints do we need to work within?
5. What is explicitly NOT in scope?
6. What could go wrong?

Between questions, acknowledge what was said and draft the section back to the human:
> "Got it — that's the problem statement. I'll draft that as:
>
> > 'The current system has no way to track decisions across conversations, leading to repeated discussions and lost context.'
>
> Does that capture it? Next question: what does success look like?"

If you suggest content, be transparent — flag what came from the human vs what you added. Mark guesses as guesses.

### 4. Bloat check

Before saving, re-read Problem and Desired Outcome. If they cover multiple distinct problems or unrelated successes, split into multiple specs and tell the human you're splitting. Don't ask permission.

### 5. Create the spec file

`.compass/specs/SPEC-NNN-descriptive-name.md` (NNN from `config.yaml`, increment the counter).

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
<omit if not applicable>

## Constraints
<omit if not applicable>

## Non-Goals
<omit if not applicable>

## Risks
<omit if not applicable>

## Open Questions
- [ ] <any unresolved questions>
```

### 6. Update index.md

Edit `.compass/index.md`, add the new spec under `## Specs` with `[[wikilinks]]` and a one-line description. A spec not in `index.md` is invisible to the next session. If the spec was tracked as a task, update `active.md` too.

### 7. Present for approval

Read back the spec (or summarize if long):

```
Here's the spec:

**Problem:** [one sentence]
**Desired Outcome:** [one sentence]
**Open Questions:** [N remaining, or "none"]

Approve? (approve / needs changes / reject)
```

- **Approved:** change `status: draft` to `status: approved`. "Spec approved. Ready for research when you are."
- **Needs changes:** ask what to change, edit, present again.
- **Rejected:** change `status: archived`, ask why so you can learn.

After approval, offer: "Create another spec, or start research on this one?"

## Examples

**Implementation plan disguised as a spec — rejected:**
```
## AE Plugin Foundation
The plugin will use CEP with React panels. It communicates via REST with
WebSocket for real-time updates. Frames are uploaded to a staging bucket.
```

**Real spec:**
```
## AI Image Editing in After Effects

### Problem
VFX artists need to apply AI image transformations to frames without leaving AE. Currently they must export, process elsewhere, and re-import.

### Desired Outcome
Artists select a frame, describe what they want, get the result as a layer. No manual export/import. No context switch.

### Constraints
- Must not require powerful local hardware
- Project files must stay organized inside the AE project
```

**Three specs pretending to be one — rejected:**
```
## AI Tools for Artists
### Problem
Artists need AI image editing in AE. They also need AI video generation
for previz. And they need a shared asset library to organize AI outputs.
```

**Same work, split correctly:**
```
SPEC-001: AI Image Editing in AE — frame-level edits without leaving AE
SPEC-002: AI Video Generation for Previz — describe scene, get video preview
SPEC-003: Shared AI Asset Library — auto-organize AI outputs by project
```

## Failure modes worth naming

- Bundling multiple concerns because "they're related." Related ≠ same problem.
- Writing a spec with a compound Problem ("we need X and also Y"). Split.
- Describing HOW instead of WHAT. "We need REST/WebSocket" is implementation.
- Making technology choices. That's research.
- Structuring specs around system components ("Plugin Architecture") instead of user needs ("Artist Workflow").
- Batch-creating multiple specs at once. One at a time.
- Writing open questions as "[TBD]" instead of asking the human.
- Suggesting your own answers as bullet points. Ask clean questions; don't lead.
- Forcing every question when the human is disengaged.
- Asking setup/implementation questions ("do you have an API token?"). Not the spec's job.
