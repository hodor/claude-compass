---
title: Integrations and parsers are built against an observed emission, never an assumed one
type: lesson
status: active
category: process
area: workflow
tags: [hooks, payloads, parsing, tool-output, evidence]
created: 2026-08-08
updated: 2026-08-11
score: 5
summary: "Capture one real emission before parsing it; assumed payload or output shapes ship dead code under a green suite"
seen: []
---

Code keyed on an assumed emission shape - a hook payload, another tool's stdout - ships silently dead: the branch never fires and nothing reports it.
Three instances: TeammateIdle (carries only teammate_name), SubagentStop (agent_type an empty string, no name field), and a `unittest -v` parser that missed both real formats - the newer path repeats the test name, and a docstring-bearing test prints across two lines, so exactly the tests the test-design bar mandates were the unverifiable ones.
Hand-authored fixtures inherit the parser's own assumption, so the suite stays green while the shipped code cannot read reality.
Capture one real emission first - `tee -a file.jsonl` on the hook, the real command's output redirected to a file - and pin the regression test to that captured text.
