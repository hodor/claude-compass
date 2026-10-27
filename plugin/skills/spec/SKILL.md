---
name: spec
description: Specification creation. Drafts the spec from what the human already said, asks only where two readings of his words would produce different specs, and reads the draft back in his sentences for approval. Specs capture the PROBLEM and the NEED, never the solution.
version: 1.0.0
allowed-tools: [Read, Grep, Glob, Write, Edit, Bash, AskUserQuestion]
when_to_use: "Use when the user wants to create a specification. Triggers: 'new spec', 'create a spec', 'write a spec', 'spec this', 'I want to spec'."
argument-hint: "<what to spec>"
---

You capture a single problem and its desired outcome in the human's own words. Specs describe the NEED, not the solution. Implementation decisions belong to research and planning, not here.

One spec captures one problem. If the Problem section needs "and also" or the Desired Outcome needs "and" to describe success, that's two specs. Split.

## Protocol

### 1. Read the hot path

`.compass/index.md`, `.compass/active.md`, `.compass/meta/lessons-catalog.yaml` (prioritize `category: domain` lessons), `.compass/vision.md` (if it exists - the spec roadmap should already include this concern).

If `vision.md` doesn't exist and the project has no specs yet, run `/compass:vision` first. Don't write a spec without a vision for a new project.

If vision exists and the requested spec isn't on the roadmap, note this in your draft and surface it at approval. Don't gate the interview on it.

### 2. Draft from what he already said

The vision, the roadmap entry, and every sentence he has said about this need are the interview. Draft the spec from them before asking anything. If he named the need in one line and nothing else exists, ask for the one-sentence version through `AskUserQuestion`, exactly one question per call: "What is the need, in one sentence?". Offer the best reading of his one line first, labelled "(Recommended)", each option one short line saying what choosing it does, and leave "Other" open for his own sentence. Never put several questions in one message or one call. Draft from his answer.

If the material describes multiple distinct problems ("users can do X and admins can do Y"):
> "That's two specs: [problem A] and [problem B]. I'll start with [problem A]."

Proceed with one. Don't ask permission; specs are single-problem by rule.

### 3. Ask only at a fork

A question is earned by a fork: two readings of his words that would produce different specs. Show both readings, say which one the draft takes, and what the choice decides downstream (what research looks at, what the planner measures). He answers with a word, or says nothing and the stated reading stands.

Ask each question through `AskUserQuestion`, exactly one question per call. The recommended option (the reading the draft takes) comes first, labelled "(Recommended)"; each option is one short line saying what choosing it does; "Other" stays open for free text. Several questions are never batched in one message or one call: ask them one per call, in order, each waiting on the previous answer.

Anything else is not asked. What research can settle is left to research; what changes nothing in Problem or Desired Outcome is not a question. Zero questions is the expected case for a need on the roadmap.

**The section is assembled from the human's own sentences.** Extract his words and arrange them; write connective tissue between his sentences, never replacements for them. The test for every line: whose words is this? Cleaning is clean-verbatim only - drop filler, stammer, and false starts, fix obvious speech-to-text errors; his grammar, word choice, and enumerations stay his. When the transcript garbles a word, flag it `[unclear: heard "X"]` and ask - a garbled word is a question for the human, and he will have the real one. Ask it through `AskUserQuestion`, exactly one question per call, with the most likely reading first as "(Recommended)" and "Other" open for the real word. Mark anything you added as a guess in brackets: `[guess: ...]`. His framing is often the requirement itself - a phrase like "a simple USD for knowledge" carries more design information than any paraphrase of it.

When part of an answer belongs to a different spec or a captured note, quote his sentences there verbatim - routing moves his words, it never summarizes them.

If the human states an explicit ruling during the interview (a trade-off resolved, an approach chosen over an alternative), record it as a `- **D-NN:** text` bullet under `## Decisions`, not as prose folded into Problem or Desired Outcome - see the "Decision bullets" convention in the `obsidian` skill. This makes the ruling a checkable claim later plans must cite. Decisions consolidate by topic: when a new ruling refines an existing bullet, merge it there rather than minting another number.

Somewhere in the interview, look for the spec's KPI: the measurable number that says this worked (a rate reaching a bar, a cost reaching zero). Brainstorm it with the human rather than inventing it - a short research pass is fine when neither of you knows what is measurable - and record it in Desired Outcome. It guides every agent downstream: the planner's pass bars and the validator's probes come from it. Not every spec has one; skip without ceremony when it does not.

### 4. Bloat check

Before saving, re-read Problem and Desired Outcome. Multiple distinct problems or unrelated successes split into separate sibling specs - tell the human you're splitting, don't ask permission. One problem with many parts stays one spec, its parts added as children inside its own folder.

### 5. Create the spec file and review its taxonomy

Resolve the destination per the `obsidian` skill's "Where a new artifact goes" rule: the owning unit's `specs/` dir, or the root. Write the draft at its best-fit domain, the domain folder whose Scope fits it (a vault with no domains files at the root), as `.compass/specs/SPEC-NNN-descriptive-name.md`, NNN from `compass next-num spec`.

Then run `compass placement <path-to-draft>`. It prints where the spec could live, each candidate with the evidence that put it there: existing specs it could sit under (`parents:`), same-level specs it would pair with (`pairs:`), domains whose scope fits (`domains:`), and where its own `taxonomy_hint` points (`hint:`). The ranking is an evidence count, not a validated measure. Apply the parent test to each candidate:

- **Child:** the candidate's decisions hold for the new spec, and the new spec diverges on something the candidate left open.
- **Pair:** the two share a subject only; they form a domain.
- **Neither:** the spec stays where it is.

Propose any child or pair through `AskUserQuestion`, exactly one question per call: "Where should this spec live?". The recommended option, the best-fitting candidate, comes first, labelled "(Recommended)"; each option is one short line saying what choosing it does; "Stay at `<current path>`" is an option; "Other" stays open for free text. Never put several questions in one message or one call. Nothing moves without his answer.

An approved move runs in this step, so no folder is left holding only its index. A child: `compass promote <parent>` turns the parent into `SPEC-NNN-name/index.md`, then `compass move <draft> <parent-folder>` files the spec inside it. A pair: `compass make-domain specs/<path>` creates the domain, then `compass move` files both specs into it. A candidate parent or pair is always proposed; the spec stays shallow with `taxonomy_hint: "<one line: where this might belong>"` in the frontmatter only when the human declines or nothing fits. Validate surfaces pending hints on every run, and consolidate consumes them.

Required sections: Problem and Desired Outcome. Optional: User Scenarios, Constraints, Decisions, Risks. Open Questions holds only a question the human himself left open, in his words; the agent never mints one. Omit any optional section if empty - don't include a heading with no content.

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

### 6b. Cheap review pass

Before presenting, spawn a reviewer sub-agent on the cheap model tier with exactly this brief: the draft spec's path, and the Document Writing rules from the pipeline rules (the ornamental test, direct statement, decisions consolidated by topic, a KPI where one exists, resident invariants cited where the work touches them - the Data rule above all). It returns a findings list; apply the edits, don't debate them. This pass exists so nothing falls through the cracks between the rules and the draft - it reviews writing, never substance: the problem and rulings are the human's.

### 7. Present for approval

With a review surface configured, the spec file goes through the review rule in the pipeline rules (`compass review <spec file> --title "Approve this spec?"`) and nothing is shown or asked here: the file opens with its picture and "You decide" callout, any guess marked inline where it sits.

Without a review surface, show the Problem and Desired Outcome as they will be saved, his sentences with any guess bracketed inline where it sits; no summary, no counts, no section list; after "needs changes", only the lines that changed. Then ask through `AskUserQuestion`, exactly one question per call: "Approve this spec?". The recommended option comes first, labelled "(Recommended)"; each option is one short line saying what choosing it does; "Other" stays open for free text:

- **Approve (Recommended):** marks the spec approved; research can start.
- **Needs changes:** you say what to change; I edit and show the changed lines.
- **Reject:** archives the spec.

Never put several questions in one message or one call; the next question waits for this answer.

- **Approved:** change `status: draft` to `status: approved` and remove the "You decide" callout. "Spec approved. Ready for research when you are."
- **Needs changes:** ask what to change, edit, present again.
- **Rejected:** change `status: archived`, ask why so you can learn.

After approval, ask one more question the same way: "What next?", with "Start research on this spec (Recommended)" and "Create another spec".

## Failure modes worth naming

- Bundling multiple concerns ("we need X and also Y"). Split.
- Rewriting the human into polished agent prose. He reads the spec back and does not recognize himself; his framing - which was the requirement - is gone. Extract and arrange his sentences instead.
- Substituting a generic for a word the transcript garbled ("Permis" becoming "any other tool"). Flag `[unclear: heard "X"]` and ask through `AskUserQuestion`, exactly one question per call, with the most likely reading first labelled "(Recommended)", each option one short line saying what choosing it does, and "Other" left open for free text. Several garbled words are asked one per call, in order, never batched.
- Describing HOW instead of WHAT ("we need REST/WebSocket" is implementation).
- Structuring around system components ("Plugin Architecture") instead of user needs.
- Minting open questions. A question the human did not leave open is settled by research or dropped; the section carries his questions only.
- Inventing non-goals. A spec is one problem; its boundary is the problem statement.
- Asking from a list. A question that cannot name the two readings it decides between is not asked.
