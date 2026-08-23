---
title: A reversibility premise is verified only by locating the inverse
type: lesson
status: active
category: process
area: methodology
tags: [reversibility, premises, decision-rationale, verification, two-way-door]
created: 2026-08-23
updated: 2026-08-23
score: 5
summary: "Cheap reversal licenses acting without asking; verify it on the inverse command, never by reading the forward one"
seen: []
---

[[ADR-011-sizing-is-a-procedure-not-a-score]] D-04 licensed sizing without asking on the ground that reversal is cheap, and [[RESEARCH-decomposition-criteria-for-sizing]] recorded that path as inspected rather than assumed, citing `make_unit.py`.
That file is the forward path: `plugin/cli/commands/` holds no `demote`, no `unmake-unit` and no `--undo` in any command, so reverting is a hand `git mv` plus manual index repair, and the load-bearing premise had never been checked in the direction it makes a claim about.
A premise about an inverse is verified only by locating the inverse; re-reading the cited forward command confirms the citation and says nothing about the cost of undoing it.
Before a cheap-reversal premise licenses anything, run the inverse once or at minimum find its command - an operation nobody built has an assumed cost, not a measured one (correction landed as D-11).
