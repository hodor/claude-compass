---
title: "hermes"
type: domain
status: active
tags: [domain, hermes, hosts, memory]
summary: "the hermes host - capabilities, memory mechanics, fit with Compass"
created: 2026-08-30
updated: 2026-11-04
sizing_id: sz-2026-08-30-14
---

# hermes

## Scope

Class here: the hermes host - capabilities, memory mechanics, fit with Compass

## Documents

- [[research/hermes/RESEARCH-hermes-skill-creation]] - How Hermes (commit a212421d, 2026-11-04) triggers, drafts, writes, dedups, indexes and retires skills; what changed since the 0.19.0 research; where a review hook already exists
- [[research/hermes/RESEARCH-hermes-skill-safety]] - what protects hermes from a bad automatic skill or memory change: write-approval staging, ledger, snapshots, guards, caps; compared with compass guard
- [[research/hermes/RESEARCH-hermes-skill-review-gate]] - what a person sees and approves before a Hermes skill or memory write lands (staged JSON, /skills diff, approve/reject, silent background staging), and how compass review could hold the same gate
- [[research/hermes/RESEARCH-hermes-changes-since-july]] - what changed in hermes from 760112a (July) to a212421d (Nov 4): four portable techniques re-checked, new skill ledger and staged-skill diff review
- [[research/hermes/RESEARCH-hermes-fit-2026-11]] - per-mechanism fit of Hermes learning and context features onto Compass hooks, skills, CLI and detached workers; token cost, goal served, ranked candidates
- [[research/hermes/REVIEW-hermes-skill-creation-2026-11]] - five Hermes axes consolidated: where they agree, conflicts settled, gaps, and ranked Compass changes for automatic skills reviewed in the md editor
