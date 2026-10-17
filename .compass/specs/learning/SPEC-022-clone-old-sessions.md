---
title: "Clone Old Sessions to Advise or Work"
type: spec
status: approved
confidence: low
area: learning
tags: [sessions, lessons, context-window, fork, harvest]
summary: "find a project's past Claude sessions, run temporary copies of them to advise or do work until their context runs out, and keep the originals untouched"
created: 2026-10-16
updated: 2026-10-16
approved: 2026-10-16
---

# Clone Old Sessions to Advise or Work

## Problem

A skill or a tool that would allow us to find from all sessions in Claude from that project, make a temporary COPY of those sessions, get them to advise or do some work until they run out of context while still preserving the main sessions. Think of it like cloning old experienced people who only have short to live to get them to do more stuff on the short time they have.

[guess: the knowledge a past session built up stays in its transcript, and nothing in Compass puts it back to work once the session ends.]

## Desired Outcome

Really easy for the user, like `/clone-old`: find all sessions where we finished doing a big feature, get them to write lessons that they learned while doing that feature, and present me an aggregated result. The skill does all that.

KPI: [guess: one command takes the human from the request to the aggregated result with no manual step in between, and every original session is unchanged afterward.]

## User Scenarios

- `/clone-old` finds the sessions where a big feature was finished; each copy writes the lessons it learned doing that feature; the human gets one aggregated set.

## Decisions

- **D-01:** The main sessions are preserved. Only temporary copies do the work.
- **D-02:** The copies go as far as they can with no autocompact.
- **D-03:** When the work is done, the temp sessions are deleted, or kept as different sessions INSIDE COMPASS for the project so that we can review them when needed.
