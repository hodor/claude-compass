---
title: "Capture Documents Keep the Human's Own Words"
type: spec
status: approved
approved: 2026-08-28
confidence: high
area: methodology
tags: [capture, interviews, verbatim, voice, spec-writing, vision, verbosity]
created: 2026-08-28
updated: 2026-08-28
depends_on: ["[[SPEC-018-scaffolding-invisible-to-the-human]]"]
summary: "spec/vision interviews rewrite what the human said into polished agent prose; the human's own sentences must survive into the documents, with agent additions marked (approved 2026-08-28)"
---

# Capture Documents Keep the Human's Own Words

## Problem

Compass's capture surfaces (the vision braindump, the spec interview) take what the human says and hand back a synthesis. The skills instruct it: "just dump it - I'll organize it after", "draft the section back", one-line problem statements. Nothing anywhere says the Problem and Desired Outcome should be built from the human's own sentences. The document-brevity rules ("short, sweet, never verbose") add compression pressure, the one-spec-one-problem rules dissect an answer and reroute pieces into documents the human is not looking at, and voice-transcribed input gives the agent a license to fix words that slides into replacing sentences.

The human's experience, in his words: "I went and explained everything and got something that I was not expecting back", "I felt like a big disconnect", and the instruction the skills were missing: "try to paraphrase me as much as you can because I don't want you changing my words." On the general failure: "AI is usually fucking awful in writing stuff because it's always so insanely verbose."

**Motivating datum** (pinned per [[LESSON-pin-the-motivating-datum]]): the knowledge-curation project's vision + SPEC-001 interview session, F:\Projects\knowledge-curation, 2026-08-28 morning, this machine - where "Claude Code, on Permis" became "any other AI agent tool" and most of a dictated answer was rerouted to other specs as agent summaries.

## Desired Outcome

What the human said is what the documents hold.

- Capture sections (Problem, Desired Outcome, goals, needs) are assembled from the human's own sentences, cleaned only for obvious speech-to-text errors. An uncertain word is flagged, never silently replaced with something generic.
- Anything the agent adds is visibly marked as the agent's, the way the spec skill's [guess] brackets already work.
- When part of an answer is routed to another document, the human's words travel there verbatim - not as the agent's summary of them.
- Brevity rules bind the agent's own prose, never license compressing the human's words.
- The human reads the document back and recognizes himself in it - no disconnect between what was said and what was written.

## Non-Goals

- Changing what specs capture (problem/need, never solution) or how they split - only whose words carry it.
- Transcript-grade fidelity of filler and repetition; cleaning stammer and transcription noise stays fine.
- The agent's own reports, plans, and research prose - those stay terse agent writing.
