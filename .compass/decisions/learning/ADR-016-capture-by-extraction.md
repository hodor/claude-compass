---
title: "Capture Sections Are Assembled from the Human's Sentences; Agent Words Are Bracketed; Cleaning Is Clean-Verbatim Only"
type: decision
status: accepted
confidence: high
area: methodology
tags: [verbatim, capture, interviews, spec-writing, vision, prompting]
created: 2026-08-29
updated: 2026-08-29
author: "orchestrator"
summary: "interview skills switch from synthesize-a-draft to extract-and-arrange: the human's sentences carry Problem/Desired Outcome, agent additions live in brackets, uncertain words are flagged never substituted, rerouted content travels verbatim, brevity binds only agent prose"
depends_on: ["[[SPEC-021-capture-in-the-humans-words]]", "[[RESEARCH-humans-words-fidelity]]"]
---

# Capture by Extraction, Not Synthesis

## Context

[[SPEC-021-capture-in-the-humans-words]]: the human's sentences must survive into capture documents. [[RESEARCH-humans-words-fidelity]]: extraction is measurably more faithful than abstraction; every source-word discipline shares one grammar (verbatim layer, bracketed insertions, declared cleaning tier, speaker sign-off); positive "copy exactly" instructions enforce better than "do not paraphrase" prohibitions; LLMs silently normalize words, so uncertain terms must be flagged, not fixed.

## Decision

Instruction-level change to the interview skills (spec, vision, specs, retroactive) plus one scope sentence in the pipeline rules. Positively phrased throughout, per the research.

- **D-01: Extract and arrange.** Problem, Desired Outcome, goals, and needs are assembled from the human's own sentences - quoted or lightly stitched; the agent writes connective tissue between his sentences, never replacements for them. The in-vivo test applies: whose words is this section in?
- **D-02: Clean verbatim is the declared cleaning tier.** Drop filler, stammer, and false starts; fix obvious speech-to-text errors. Grammar, word choice, and enumeration stay his. A word the transcript garbles is flagged `[unclear: heard "X"]` and asked about - never replaced with something generic.
- **D-03: Agent words are bracketed.** Anything the agent adds inside a capture section is `[guess: ...]`-marked, in every interview skill.
- **D-04: Rerouted content travels verbatim.** When part of an answer belongs to another spec or a note, his sentences are quoted there - the routing moves words, it never summarizes them.
- **D-05: The approval walkthrough is member checking.** Reading the document back in the human's own words is what the gate is for; he holds final sign-off on any departure ([[LESSON-walkthroughs-in-the-humans-words]]).
- **D-06: Brevity binds agent prose only.** One sentence lands in the pipeline rules' Document Writing section: the human's captured words are never the verbiage to cut.

## Consequences

- Capture documents read like the human, including his framing ("a simple version of USD for knowledge") - the framing often IS the requirement.
- Documents get slightly longer where his answers were long; that is the point, and the research says the concision pressure was a fidelity risk anyway on ambiguous content.
- Verbatim fidelity is instruction-level, not enforced by machinery; the human's sign-off gate is the backstop, matching every surveyed discipline.
