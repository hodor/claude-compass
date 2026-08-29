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

`.compass/index.md`, `.compass/active.md`, `.compass/meta/lessons-catalog.yaml` (prioritize `category: domain` lessons), `.compass/vision.md` (if it exists - the spec roadmap should already include this concern).

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

Two questions are required. The rest are optional. Read the room - if the human gives short answers, says "whatever" / "continue" / "skip", or seems impatient, wrap up. A thin spec with a clear problem statement beats a thick spec the human didn't care to finish.

**Required:**
1. What problem does this solve? Why does it matter?
2. What does success look like?

**Optional:**
3. Who benefits? Walk me through a typical scenario.
4. What constraints do we need to work within?
5. What is explicitly NOT in scope?
6. What could go wrong?

Between questions, read the section back as a single block quote (no acknowledgement preamble) and ask the next question.

**The section is assembled from the human's own sentences.** Extract his words and arrange them; write connective tissue between his sentences, never replacements for them. The test for every line: whose words is this? Cleaning is clean-verbatim only - drop filler, stammer, and false starts, fix obvious speech-to-text errors; his grammar, word choice, and enumerations stay his. When the transcript garbles a word, flag it `[unclear: heard "X"]` and ask - a garbled word is a question for the human, and he will have the real one. Mark anything you added as a guess in brackets: `[guess: ...]`. His framing is often the requirement itself - a phrase like "a simple USD for knowledge" carries more design information than any paraphrase of it.

When part of an answer belongs to a different spec or a captured note, quote his sentences there verbatim - routing moves his words, it never summarizes them.

If the human states an explicit ruling during the interview (a trade-off resolved, an approach chosen over an alternative), record it as a `- **D-NN:** text` bullet under `## Decisions (made by the human)`, not as prose folded into Problem or Desired Outcome - see the "Decision bullets" convention in the `obsidian` skill. This makes the ruling a checkable claim later plans must cite.

### 4. Bloat check

Before saving, re-read Problem and Desired Outcome. Multiple distinct problems or unrelated successes split into separate sibling specs - tell the human you're splitting, don't ask permission. One problem with many parts stays one spec, its parts added as children inside its own folder.

### 5. Create the spec file

Before creating the spec file, resolve its destination per the `obsidian` skill's "Where a new artifact goes" rule - the owning unit's `specs/` dir, or the root. Every spec is a folder: `.compass/specs/SPEC-NNN-descriptive-name/index.md`, NNN from `compass next-num spec`. A child spec is created the same way inside its parent's folder, at any depth - `compass next-num spec <parent-path>` numbers it locally. Required sections: Problem and Desired Outcome. Optional: User Scenarios, Constraints, Decisions, Non-Goals, Risks, Open Questions. Omit any optional section if empty - don't include a heading with no content.

```markdown
---
title: "Title"
type: spec
status: draft
confidence: low
area: <area>
tags: [tag1, tag2]
summary: "<one line - the index copies this>"
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# Title

## Problem
[from question 1]

## Desired Outcome
[from question 2]
```

### 6. Update index.md

Edit `.compass/index.md`, add the new spec under `## Specs` with `[[wikilinks]]` and a one-line description. A spec not in `index.md` is invisible to the next session. If the spec was tracked as a task, update `active.md` too.

### 7. Present for approval

This read-back is the human validating that the document says what he said - so it shows him his own words, and he holds final say on any departure from them.

Read back the spec (or summarize if long - the summary lines below may compress, the spec body itself keeps his sentences):

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

## Failure modes worth naming

- Bundling multiple concerns ("we need X and also Y"). Split.
- Rewriting the human into polished agent prose. He reads the spec back and does not recognize himself; his framing - which was the requirement - is gone. Extract and arrange his sentences instead.
- Substituting a generic for a word the transcript garbled ("Permis" becoming "any other tool"). Flag `[unclear: heard "X"]` and ask.
- Describing HOW instead of WHAT ("we need REST/WebSocket" is implementation).
- Structuring around system components ("Plugin Architecture") instead of user needs.
- Writing open questions as "[TBD]" instead of asking the human.
- Forcing every question when the human is disengaged.
