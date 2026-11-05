---
title: "Skills Created Automatically, Reviewed in the md Editor"
type: spec
status: approved
approved: 2026-11-05
confidence: low
area: learning
tags: [skills, skill-creation, review, md-editor, learning-loop]
summary: "Compass creates skills automatically, and the developer gets a review opportunity for each skill at the md editor"
created: 2026-11-04
updated: 2026-11-04
depends_on: ["[[research/hermes/REVIEW-hermes-skill-creation-2026-11]]", "[[SPEC-012-learning-loop]]"]
---

# Skills Created Automatically, Reviewed in the md Editor

```mermaid
flowchart LR
  A["A session learns something"] --> B["Compass creates or changes a skill"]
  B --> C["The developer reviews it at the md editor"]
  C -->|approved| D["The skill takes effect"]
  C -->|changes| B
```

## Problem

Ideally I like the thing about creating skills automatically. What a session learns becomes at most a lesson of five lines; Compass creates no skills. Hermes creates skills automatically (see [[research/hermes/REVIEW-hermes-skill-creation-2026-11]]).

## Desired Outcome

Creating skills automatically, and we should give the developer a review opportunity for the skill at the md editor. Every skill Compass creates or changes reaches the developer this way before it takes effect. Compass changes only the skills it created itself; shipped Compass skills and the developer's own skills stay as they are.
