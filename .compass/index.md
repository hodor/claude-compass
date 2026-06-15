---
title: Compass Plugin — Project Index
project: compass
created: 2026-03-12
updated: 2026-05-24
status: active
---

# Compass — Project Index

Compass is a Claude Code plugin that provides an AI-guided development workflow with per-project Obsidian-compatible knowledge vaults.

## Project Structure

- `plugin/` — the installable plugin source (agents, skills, plugin.json)
- `.compass/` — this vault, the project's own development context

## Specs

- [[SPEC-001-compass-vision-and-architecture]] — Core vision, principles, architecture, and resolved design decisions
- [[SPEC-002-lessons-and-index-subsystem]] - Lessons capture, dedup, anti-list, and index freshness mechanism (approved)
- [[SPEC-003-hierarchical-vault-organization]] - Hierarchical folders + faceted tags + MemGPT 3-tier model, with falsifiable 30% read-reduction hypothesis (approved)
- [[SPEC-004-mechanical-work-off-the-agent-budget]] - Deterministic vault upkeep must run as a program, not in agent tokens; falsifiable 80% bookkeeping-token reduction (approved)

## Research

- [[RESEARCH-lessons-and-index-architecture]] - literature review across 5 reference codebases on capture timing, index freshness, dedup, and lesson shape
- [[RESEARCH-evaluation-benchmarks]] - benchmarks for evaluating Compass methodology layer; A/B pitfalls; field-gap analysis
- [[RESEARCH-scientific-method-in-compass]] - does Compass actually embody the scientific method, or only borrow the vocabulary; 8 specific gaps with file:line evidence
- [[RESEARCH-hierarchical-knowledge-base-design]] - MemGPT + RAPTOR + Ranganathan + Denning synthesis with 11 verified findings and 4 open questions, informs hierarchical specs design
- [[RESEARCH-cli-and-hook-command-contract]] - Claude Code CLI dispatch pattern + the exact command-hook contract (exit-2 blocks writes, stdin JSON, loop guard); grounds SPEC-004/ADR-005
- [[RESEARCH-cli-token-reduction-measurement]] - SPEC-004's 80% hypothesis confirmed: ~99.8% bookkeeping-token reduction, integrity preserved and improved (found a defect the LLM hook missed)

## Plans

- [[PLAN-001-lessons-and-index-implementation]] - 12 tasks across 6 phases implementing SPEC-002 (done 2026-05-24)
- [[PLAN-002-compass-cli-implementation]] - 12 tasks across 3 dependency-driven phases building the Python `compass` CLI + command-hook cutover; implements SPEC-004 (approved)

## Decisions

- [[ADR-001-methodology-as-skill-with-vault]] - Methodology lives in a skill; project state in per-project `.compass/` Obsidian-compatible vault
- [[ADR-002-retrospective-lessons-subsystem]] - Retrospective lesson capture at phase boundary with binary triggers, anti-list, and single writer
- [[ADR-003-drop-counter-file-jit-compute]] - Drop `meta/config.yaml` counter file; compute next artifact number JIT from filesystem
- [[ADR-004-hierarchical-specs-with-facets]] - 3-tier MemGPT memory + folder hierarchy + faceted tags + admission control; hot path at prompt start
- [[ADR-005-compass-cli-for-mechanical-work]] - A Python `compass` CLI owns mechanical vault work; PostToolUse hook becomes a command, not an agent; MCP rejected (approved)

## Active Work

See [[active]].

## Backlog

See [[backlog]].

## Handoffs

- [[2026-03-12_review-all-plugin-files]] — File-by-file review of all 21 plugin files (active)
- [[2026-03-12_23-50-59_session-3-skills-approved]] — All 3 skills approved, duplication audit complete
- [[2026-03-12_session-2-obsidian-approved]] - Handoff: Obsidian skill fully reviewed, HumanLayer insights adopted
- [[2026-06-10_23-00-00_python-cli-next-up]] - Handoff: Python busywork CLI is next; everything through ADR-004 shipped

## Lessons

- [[LESSON-glob-hidden-dirs-prefix]] - Glob tool needs `**/` prefix to traverse hidden dirs like .compass/
- [[LESSON-hook-if-clause-no-or]] - Hook `if` does not support `||`; split into N entries or use matcher for multi-tool
- [[LESSON-hook-type-prompt-no-skills]] - Hook `type: prompt` is single-shot; cannot call Skill tool; use `type: agent` instead
- [[LESSON-no-agent-bookkeeping]] - Mechanical bookkeeping (counters, indexes, catalogs) belongs in scripts/hooks/JIT, not agent steps
- [[LESSON-wikilink-validator-skip-code]] - Wikilink validators must skip fenced code blocks AND inline code spans; example refs in docs are noise
- [[LESSON-test-driven-tasks-dont-discriminate]] - When tests fully encode the spec, frontier models already read-tests-first; methodology can't be measured on such tasks
- [[LESSON-windows-crlf-breaks-linux-container-scripts]] - Python `open(p, 'w')` on Windows writes CRLF; mount that into a Linux container and bash chokes on $'\r'
- [[LESSON-tag-index-trades-cost-for-directed-retrieval]] - Tag index gives directed retrieval and faster wall-time; token cost depends on query shape; SPEC-003's 30% claim falsified on N=1
- [[LESSON-autocrlf-churns-lf-writers]] - With core.autocrlf=true and no .gitattributes, git checks files out as CRLF; a tool that writes LF rewrites them every run, causing perpetual diffs
- [[LESSON-hook-cli-gate-stdin-on-flag]] - Gate hook-stdin reads behind an explicit flag (--hook), not isatty probing; probing blocks forever in a non-interactive shell with no piped input
- [[LESSON-type-dir-discovery-needs-content-signal]] - Treating every .compass subdir as an artifact type dir breaks on vaults that store non-artifact dirs there; require the known core dirs OR a typed-artifact signal
- [[LESSON-installer-removes-only-what-it-installed]] - A tool that installs into a shared dir must delete only its own named artifacts on cleanup; 'remove anything not in my source' destroys user files
