---
title: "Compass Uses Fewer Tokens"
type: spec
status: approved
confidence: low
area: tooling
tags: [tokens, cost, loops, measurement]
summary: "minimize the amount of tokens Compass uses, driven by a control loop in this repo"
created: 2026-10-18
updated: 2026-10-29
approved: 2026-10-18
---

# Compass Uses Fewer Tokens

> [!question] You decide
> Approve the added Problem paragraph (your words: Claude Code's context, efficiency and quality) and the KPI's new guess that quality does not fall.

## Problem

I want to minimize the amount of tokens that Compass uses.

We bloat the context of Claude Code, etc. when we use Compass; we should minimize the token usage while ensuring maximum efficiency and quality.

## Desired Outcome

This is done here, through a Compass control loop, so the token use keeps going down while the plugin keeps changing.

KPI: [guess: the tokens Compass spends on the same benchmark work, measured the same way every run, go down and stay down, while the quality of that work does not fall.]
