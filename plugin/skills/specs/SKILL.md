---
name: specs
description: Capture a braindump of ideas, break them into separate specs, and write them all in batch with minimal repeated questioning. Use when you have multiple specs in your head at once.
version: 1.0.0
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, Agent]
when_to_use: "Use when the user has multiple specs to create. Triggers: 'I have a bunch of specs', 'multiple specs', 'braindump', 'organize my ideas into specs'."
---

# Specs - Braindump to Multiple Specs

For when the human has many ideas at once and shouldn't be asked the same setup questions N times. Batch shared context. One spec per concern. Never run the full spec interview per spec.

## Protocol

### 1. Capture the braindump

> "Tell me everything you have in your head about what you want to build. Don't worry about structure - just get it all out. I'll organize it into specs after."

Wait for the response. Don't interrupt.

### 2. Propose the spec list

Identify distinct concerns from the braindump. Each becomes one spec.

```
I see N specs:

1. **SPEC: [name]** - [one-line problem]
2. **SPEC: [name]** - [one-line problem]
...

Confirm, or tell me what to merge / split / remove?
```

Iterate until approved.

### 3. Capture shared context once

> "Shared questions for the whole batch:
> 1. Who is the user/audience?
> 2. Shared constraints (deadlines, budget, infrastructure)?
> 3. Shared non-goals?
>
> (Skip any that don't apply.)"

Save as shared context.

### 4. Write each spec lightweight

For each approved spec, write a draft using shared context + the braindump content for that spec. Ask only spec-specific questions that aren't already answered:
- What's the desired outcome for THIS spec?
- Anything specific to THIS spec not covered by shared context?

Save each as `status: draft`.

### 5. Batch review

```
N specs drafted (all status: draft):

1. [[SPEC-NNN-name]] - [one line]
2. [[SPEC-NNN-name]] - [one line]
...

Approve all / review one by one / approve some refine others?
```

Update statuses. Update `index.md` with all new specs.

### 6. Suggest order

```
Suggested order:
1. SPEC-NNN - foundation
2. SPEC-NNN, SPEC-NNN - parallel after #1
3. SPEC-NNN - depends on #2
```

## When NOT to use

- Single spec → `/compass:spec` (deep interview).
- Need deep clarity per spec → `/compass:spec` per spec.
- Specs are deeply interconnected → `/compass:spec` for the parent first.

## Failure modes worth naming

- Asking shared setup questions per spec instead of once.
- Spawning the full spec-writer per spec (hundreds of repeated questions).
- Collapsing multiple concerns into one spec to be efficient.
- Making implementation decisions in any spec.
- Skipping the braindump and starting structured questions immediately.
