---
name: learned
description: Capture an in-the-moment lesson the human just noticed. One-line argument; the skill infers category (process or domain via Reinertsen) plus area and tags, then hands off to lesson-write. Use when the human types /compass:learned to record a discovery before they forget.
version: 1.0.0
allowed-tools: [Read, Glob, Grep]
argument-hint: "<lesson text> [--process|--domain] [--area <area>] [--tags tag1,tag2]"
when_to_use: "Use only when the human explicitly invokes /compass:learned. Never suggest it to the human and never run it on their behalf: an agent that notices something worth remembering runs compass capture-note with one sentence instead, and the auto-extraction path judges the note at the next capture opportunity."
---

# /compass:learned - Manual Lesson Capture

The human just noticed something worth remembering. Capture it cheap, before they forget.

This skill does NOT decide whether the content is worth saving. It hands every input to `lesson-write`, which applies the anti-list. The human's `/compass:learned` is a signal of intent, not a guarantee of write.

## Argument parsing

Arguments arrive as a single string. Parse in order:

1. **Flags** (any order, may appear anywhere): `--process`, `--domain`, `--area <name>`, `--tags tag1,tag2`
2. **Body text**: everything else, joined into the lesson body

If both `--process` and `--domain` are passed, ask the human which one.

## Protocol

### 1. Read context

Read `.compass/meta/lessons-catalog.yaml` for area conventions in use, and `.compass/active.md` for current task context.

### 2. Determine category

If `--process` or `--domain` flag is set, use it. Otherwise infer using Reinertsen split:

- **Process** - the content describes a build technique, a tooling gotcha, a testing strategy, a refactoring pattern, anything about *how* to build. "X technique works better than Y for case Z."
- **Domain** - the content describes a user reality, a business rule, a regulatory constraint, an integration quirk, anything about *what* to build. "Users actually need X, not Y."

If the content is genuinely ambiguous (e.g. "Always check the OAuth refresh token expiry" - both how to build AND what the system must do), ask the human one question: "Process (how to build it) or Domain (what users need)?"

### 3. Determine area

If `--area` flag is set, use it.

Otherwise infer from content keywords against the standard areas: `architecture`, `frontend`, `backend`, `testing`, `devops`, `infra`, `docs`, `workflow`, `methodology`.

If multiple plausible areas, pick the one most cited in the current `active.md` task context. If still ambiguous, ask the human: "Which area? (a) backend (b) testing (c) other".

### 4. Determine tags

If `--tags` flag is set, use it (split on comma, strip whitespace).

Otherwise infer 2-4 short tags from the content. Prefer reusing tags already in the catalog (read it for vocabulary). Do not invent verbose tags; keep them short.

### 5. Build summary

Summary is one line, <=120 characters. If the body is one short line, summary = body. Otherwise compress the body into a one-line gist.

### 6. Build body

Body is free-form, <=5 lines. If the human's input is already <=5 lines, use it verbatim. If longer, compress to fit. Do not add template sections.

### 7. Call lesson-write

Hand the payload to the `lesson-write` skill:

```
category: <process|domain>
area: <area>
tags: [<tag1>, <tag2>, ...]
summary: <one-line>
body: <free-form, <=5 lines>
source: /compass:learned
```

### 8. Report

Surface the `lesson-write` return value to the human as one line:

- `created: LESSON-foo.md` - "Saved as [[LESSON-foo]]."
- `recurrence: LESSON-foo.md` - "Already captured as [[LESSON-foo]]; bumped score and recorded today's date."
- `escalated: LESSON-foo.md` - "Already captured as [[LESSON-foo]]; this is the 4th recurrence and the lesson has been escalated for human review (it may be too vague or the search is failing)."
- `refined: LESSON-foo.md` - "Refined [[LESSON-foo]] with new context."
- `rejected: <bucket>` - "Not saved (matched anti-list bucket: <bucket>). The content fits a different home: <suggested>." Where suggested is one of: codebase, git history, commit message, spec/ADR/plan, framework docs, handoff.
- `body_too_long: N` - "Body has N lines; needs <=5. Compress and re-run /compass:learned."

## Failure modes worth naming

- Saving the content yourself instead of calling `lesson-write`. The single-write path is the only path.
- Skipping the anti-list because "the human said to save it." `lesson-write` enforces this; if it rejects, surface honestly.
- Inventing an area or category to avoid asking. Ask one short question if genuinely unclear.
- Padding the body with template sections. Free-form, <=5 lines.
- Suggesting the user retry with `--area` etc. when `lesson-write` succeeded - do not nag.
