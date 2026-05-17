---
name: vision
description: Capture the project's overall goal, scope, and the full set of needs that will become specs. Run BEFORE creating individual specs to avoid bundling unrelated needs into one giant spec. Output is a vision document and a proposed spec list.
version: 1.0.0
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion]
when_to_use: "Use at the start of a project, or whenever the user has multiple ideas to spec. Triggers: 'what should we build', 'capture the vision', 'I have a bunch of ideas', 'plan the project', 'I'm starting a new project'. Bootstrap calls this automatically for new projects."
argument-hint: "[brief project description]"
---

# Vision — Capture the Big Picture Before Specs

The Compass pipeline is Spec → Research → Plan → Build. Specs are single-problem. Without a vision step first, projects get crammed into one giant spec or fragmented into incoherent ones.

This skill captures the vision (overall goal + landscape of needs) and produces a proposed spec list. Then `/compass:spec` runs once per spec.

A vision is the project's purpose, its users, the shape of the problem space, project-wide constraints, and what success looks like. It is not a spec (those are per-problem), not an implementation plan (no tech choices), and not a roadmap with dates.

## Protocol

### 1. Braindump

Ask the human:
> "Tell me everything about what you want to build. Don't worry about structure — just dump it. Goals, problems, users, ideas. I'll organize it after."

Wait. Don't interrupt. Don't ask questions yet.

### 2. Targeted questions, one at a time

Required:
1. **Overall goal:** "In one sentence, what's the goal of this project?"
2. **Users:** "Who uses this? What do they currently do without it?"
3. **Success:** "If this is wildly successful, what's true that wasn't true before?"

Optional, ask if not covered:
4. **Hard constraints:** budget, infrastructure, regulatory, team.
5. **Non-goals at project level:** what this project is NOT trying to do.
6. **Existing context:** what exists today, what's been tried, what's in the way.

Read the room. Don't force every question.

### 3. Identify distinct needs

Each distinct need becomes one spec. Use the spec rule: if you write "and also" between two needs, they're separate.

Present:

```
Based on what you've described, I see N distinct needs that would each become a spec:

1. **[Need name]** — [one-line problem statement]
   - User: [who needs this]
   - Success: [what success looks like]

2. ...

Does this list cover everything? Should I:
- merge any of these (if they're really one problem)?
- split any (if I bundled distinct concerns)?
- add any I missed?
- remove any (out of scope)?
```

Iterate until the human approves.

### 4. Write the vision document

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
[Project-level success criteria — not per-spec]

## Project-Level Constraints
[Constraints that apply across all specs]

## Non-Goals
[What this project explicitly is NOT]

## Spec Roadmap
The following specs will be created from this vision (one at a time):

1. [[SPEC-001-name]] — [one-line problem statement] — status: not yet created
2. [[SPEC-002-name]] — [one-line problem statement] — status: not yet created

## Suggested Order
[Which spec to write first, what can parallelize later]
```

### 5. Update index.md — REQUIRED

Add a `## Vision` section to `.compass/index.md` (above Specs) with `[[vision]]` and a one-line summary. `index.md` is what the next session reads first.

### 6. Hand off

> "Vision captured. The spec roadmap has N items.
>
> Next: pick one need and run `/compass:spec` to interview deeply on just that one.
>
> Want to start with [first item], or pick a different one?"

Don't auto-spawn the spec writer. The human chooses.

## Examples

**Bloated single spec — bad:**
```
SPEC-001: Build the AE plugin
  - AI image editing
  - AI video generation
  - Asset library
  - User auth
  - Billing
```

**Vision + spec list — good:**
```
vision.md
  Goal: Bring AI natively into After Effects so artists never leave AE
  Users: VFX artists working on production shots
  Success: Artists complete AI-assisted edits in AE without context switching

Spec Roadmap:
  1. SPEC-001: AI image editing in AE
  2. SPEC-002: AI video generation for previz
  3. SPEC-003: Shared AI asset library
  4. SPEC-004: User authentication
  5. SPEC-005: Usage-based billing
```

## When to re-run vision

- New major direction (rethink, not just add).
- Pivot — the original vision no longer applies.
- After a milestone — vision evolves with learning.

For "just add one more spec," skip vision and run `/compass:spec` directly.

## Failure modes worth naming

- Treating the vision as a pitch deck instead of an agent-readable landscape.
- Asking targeted questions before the braindump finishes.
- Letting implementation details slip in — vision is about the WHAT, not the HOW.
- Skipping the distinct-needs check and producing one giant spec list with everything fused.
- Forgetting to update `index.md` — the vision becomes invisible next session.
- Auto-spawning the spec writer instead of letting the human pick the first need.
