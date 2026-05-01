---
name: vision
description: Capture the project's overall goal, scope, and the full set of needs that will become specs. Run BEFORE creating individual specs to avoid bundling unrelated needs into one giant spec. Output is a vision document and a proposed spec list.
version: 1.0.0
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion]
when_to_use: "Use at the start of a project, or whenever the user has multiple ideas to spec. Triggers: 'what should we build', 'capture the vision', 'I have a bunch of ideas', 'plan the project', 'I'm starting a new project'. Bootstrap calls this automatically for new projects."
argument-hint: "[brief project description]"
---

# Vision — Capture the Big Picture Before Specs

The Compass pipeline is Spec → Research → Plan → Build. But specs are SINGLE-PROBLEM. Without a vision step first, projects get crammed into one giant spec or fragmented into specs without coherence.

This skill captures the vision (overall goal + landscape of needs) and produces a proposed spec list. Then `/compass:spec` runs once per spec.

=== CRITICAL: VISION CAPTURES THE WHOLE; SPECS CAPTURE INDIVIDUAL PROBLEMS ===
=== CRITICAL: NO IMPLEMENTATION DETAILS — SAME RULE AS SPECS ===
=== CRITICAL: ONE INTERVIEW, ONE VISION DOCUMENT, MULTIPLE PROPOSED SPECS ===

## What a Vision Is

- The project's overall purpose
- The user/audience
- The shape of the problem space (the multiple needs)
- High-level constraints that apply to everything
- What success looks like at the project level

## What a Vision Is NOT

- A spec (specs are per-problem)
- An implementation plan (no tech choices)
- A roadmap with dates (just the landscape)
- A pitch deck (terse, structured, written for agents to read)

## Protocol

### Phase 1: Braindump

Ask the human:
> "Tell me everything about what you want to build. Don't worry about structure — just dump it. Goals, problems, users, ideas. I'll organize it after."

Wait. Don't interrupt. Don't ask questions yet.

### Phase 2: Targeted Questions

After the braindump, ask ONE question at a time. Required:

1. **Overall goal**: "In one sentence, what's the goal of this project?"
2. **Users**: "Who uses this? What do they currently do without it?"
3. **What success looks like**: "If this is wildly successful, what's true that wasn't true before?"

Optional, ask if not covered:

4. **Hard constraints**: "What constraints apply to the whole project? (budget, infrastructure, regulatory, team)"
5. **Non-goals at project level**: "What is this project NOT trying to do?"
6. **Existing context**: "What exists today? What have you tried? What's in the way?"

Read the room. Don't force every question.

### Phase 3: Identify Distinct Needs

From the braindump and answers, identify the distinct user needs. Each becomes ONE spec. Use the same rule as the spec skill: if you write "and also" between two needs, they're separate.

Present:

```
Based on what you've described, I see N distinct needs that would each become a spec:

1. **[Need name]** — [one-line problem statement]
   - User: [who needs this]
   - Success: [what success looks like]

2. **[Need name]** — [one-line problem statement]
   - User: [who needs this]
   - Success: [what success looks like]

3. **[Need name]** — ...

Does this list cover everything? Should I:
- merge any of these (if they're really one problem)?
- split any (if I bundled distinct concerns)?
- add any I missed?
- remove any (out of scope)?
```

Iterate until the human approves the list.

### Phase 4: Write the Vision Document

Save to `.compass/vision.md`:

```markdown
---
title: "Vision: [Project Name]"
type: vision
status: approved
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# Vision: [Project Name]

## Goal

[One paragraph — overall purpose and what the world looks like with this project succeeding]

## Users

[Who uses this and what they currently do without it]

## Success

[Project-level success criteria — not per-spec, but for the whole thing]

## Project-Level Constraints

[Constraints that apply across all specs — infrastructure, budget, regulatory, team]

## Non-Goals

[What this project explicitly is NOT]

## Spec Roadmap

The following specs will be created from this vision (one at a time):

1. [[SPEC-001-name]] — [one-line problem statement] — status: not yet created
2. [[SPEC-002-name]] — [one-line problem statement] — status: not yet created
3. [[SPEC-003-name]] — [one-line problem statement] — status: not yet created

## Suggested Order

[Based on dependencies and priorities — which spec to write first, what can run in parallel later]
```

### Phase 5: Update index.md

Add the vision document to `.compass/index.md` as a top-level entry (above Specs).

### Phase 6: Hand Off

Tell the human:

> "Vision captured. The spec roadmap has N items.
>
> Next: pick one need from the list and run `/compass:spec` to interview deeply on just that one.
>
> Want to start with [first item], or pick a different one?"

DO NOT spawn the spec writer automatically. The human chooses.

## Bad/Good Examples

**Bloated single spec — Bad:**
```
SPEC-001: Build the AE plugin
  - AI image editing
  - AI video generation
  - Asset library
  - User auth
  - Billing
```
(Five problems crammed into one spec.)

**Vision + spec list — Good:**
```
vision.md
  Goal: Bring AI capabilities natively into After Effects so artists never leave AE
  Users: VFX artists working on production shots
  Success: Artists complete AI-assisted edits in AE without context switching

Spec Roadmap:
  1. SPEC-001: AI image editing in AE
  2. SPEC-002: AI video generation for previz
  3. SPEC-003: Shared AI asset library
  4. SPEC-004: User authentication
  5. SPEC-005: Usage-based billing
```
(Each spec captures one need. They share the vision but have separate problems and outcomes.)

## When to Re-Run Vision

- New major direction (re-think the project, not just add a spec)
- Pivot (the original vision no longer applies)
- After a project milestone (vision evolves with learning)

For "I just want to add one more spec," skip vision and run `/compass:spec` directly.

=== REMINDER: VISION IS THE LANDSCAPE. SPECS ARE INDIVIDUAL PROBLEMS. NEVER SKIP VISION FOR NEW PROJECTS. ===
