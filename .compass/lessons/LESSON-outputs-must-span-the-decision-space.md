---
title: A procedure answering in fewer categories than the decision space makes users invent the mapping
type: lesson
status: active
category: process
area: methodology
tags: [decision-procedures, spec-defect, category-mapping, rater-bias, empirical]
created: 2026-08-23
updated: 2026-08-23
score: 5
summary: "A procedure answering in fewer categories than the decision space makes users invent the mapping, wrongly"
seen: []
---

ADR-011 D-02 answers depth-or-breadth for the three-way flat/folder/unit choice and states no mapping; raters bridged the gap unanimously (11/11 depth-only reasons chose folder, 3/3 breadth-only chose unit), and the breadth mapping contradicts D-06.
An output space narrower than the decision space is a spec defect: users fill the gap consistently, so the invented mapping looks like agreement and can drive a systematic bias.
Make a decision procedure's answers span the choices it decides; report an unmapped category, never bridge it.
