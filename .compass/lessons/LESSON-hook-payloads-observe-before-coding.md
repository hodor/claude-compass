---
title: Code and fixes alike are built against an observed reality, never a described one
type: lesson
status: active
category: process
area: workflow
tags: [hooks, payloads, parsing, tool-output, evidence]
created: 2026-08-08
updated: 2026-08-30
score: 5
summary: "Observe the real emission or code path first; assumed shapes and reported causes ship dead work under a green suite"
seen: []
---

Code keyed on an assumed emission shape - a hook payload, another tool's stdout - ships silently dead: the branch never fires and nothing reports it. A fix keyed on a bug report's stated root cause fails the same way. The same holds for a skill's prose claim about another command's behavior.
Instances: TeammateIdle (carries only teammate_name), SubagentStop (agent_type an empty string), a `unittest -v` parser that missed both real formats, issue #8 (blamed CRLF where `Path.read_text` already normalizes it, real cause a UTF-8 BOM), and `promote-spec/SKILL.md`'s claimed CLI refusal of non-spec artifacts (a live dry-run showed `compass promote` already accepts them).
Hand-authored fixtures inherit the assumption, so the suite stays green while the shipped code cannot read reality; the CRLF-targeted fix passed its own new tests while fixing nothing.
Capture one real emission first - `tee -a file.jsonl` on the hook, the real command's output to a file - or reproduce the bug through its real code path, then pin the regression test to what you observed.
