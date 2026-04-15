---
name: specs
description: Capture a braindump of ideas, break them into separate specs, and write them all in batch with minimal repeated questioning. Use when you have multiple specs in your head at once.
version: 1.0.0
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, Agent]
when_to_use: "Use when the user has multiple specs to create. Triggers: 'I have a bunch of specs', 'multiple specs', 'braindump', 'organize my ideas into specs'."
---

# Specs — Braindump to Multiple Specs

For when you have many ideas at once and don't want to be asked the same setup questions N times.

=== CRITICAL: BATCH THE SHARED CONTEXT — ASK SHARED QUESTIONS ONCE, NOT PER SPEC ===
=== CRITICAL: ONE SPEC PER CONCERN — DON'T COLLAPSE UNRELATED IDEAS INTO ONE SPEC ===

## Protocol

### Step 1: Capture the Braindump

Ask the user to dump everything:
> "Tell me everything you have in your head about what you want to build. Don't worry about structure or completeness — just get it all out. I'll organize it into specs after."

Wait for the response. Don't interrupt with questions.

### Step 2: Propose the Spec List

Read the braindump. Identify distinct concerns — each becomes one spec. Present the list:

```
I see N specs in here:

1. **SPEC: [name]** — [one-line description of the problem/need]
2. **SPEC: [name]** — [one-line description]
3. **SPEC: [name]** — [one-line description]

Each follows single responsibility — they could be worked on in parallel.

Confirm the list, or tell me what to merge/split/remove?
```

Iterate until the human approves the list.

### Step 3: Capture Shared Context Once

Ask shared questions ONCE for the whole batch (not per spec):

> "Before I write each spec, a few shared questions that apply to all of them:
> 
> 1. Who is the user/audience for these?
> 2. Are there shared constraints (deadlines, budget, infrastructure)?
> 3. Are there shared non-goals?
> 
> (Skip any that don't apply.)"

Save these as shared context for all specs.

### Step 4: Write Each Spec (Lightweight)

For EACH approved spec, write a draft using the shared context PLUS the braindump content for that spec. Do NOT spawn the full spec-writer interview per spec — that would be hundreds of repeated questions.

For each spec, ask only the spec-SPECIFIC questions that aren't already answered:
- What's the desired outcome for THIS spec?
- Anything specific to THIS spec that's not covered by shared context?

Save each as `status: draft`.

### Step 5: Batch Review

After all drafts are written, present them together:

```
N specs drafted (all status: draft):

1. [[SPEC-NNN-name]] — [problem statement summary]
2. [[SPEC-NNN-name]] — [problem statement summary]
...

Want to:
- Approve all → I'll mark them all status: approved
- Review one by one → I'll show you each
- Approve some, refine others → tell me which
```

Update statuses based on the human's response. Update `index.md` with all new specs.

### Step 6: Suggest Order

Based on dependencies between specs (read each spec's content), suggest a sequence:

```
Suggested order based on dependencies:
1. SPEC-NNN — foundation, others depend on it
2. SPEC-NNN, SPEC-NNN — can run in parallel after #1
3. SPEC-NNN — depends on #2
```

This gives the human a roadmap without forcing them to figure out dependencies themselves.

## Know Your Failure Modes

You WILL be tempted to:
- Ask the same setup questions for each spec — DON'T. Capture shared context ONCE in Step 3.
- Spawn the full spec-writer for each spec — DON'T. That's hundreds of questions for the user.
- Collapse multiple concerns into one spec to be efficient — DON'T. Single responsibility.
- Make implementation decisions in any of the specs — DON'T. Same rule as spec-writer: NEED, not solution.
- Skip the braindump and start asking structured questions immediately — DON'T. Let the human dump first.
- Force the human to approve specs one at a time when they want to batch-approve — let them approve all at once.

## When NOT to Use This Skill

- Single spec → use `/compass:spec` (deep interview)
- Need deep clarity on each spec → use `/compass:spec` per spec
- Specs are deeply interconnected and can't be cleanly separated → use `/compass:spec` for the parent concept first

=== REMINDER: BATCH SHARED CONTEXT. ONE SPEC PER CONCERN. NEVER SPAWN FULL SPEC-WRITER PER SPEC. ===
