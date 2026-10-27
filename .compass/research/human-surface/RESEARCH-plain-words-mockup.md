---
title: "Plain Words: Mockup"
type: research
status: complete
confidence: low
area: methodology
tags: [jargon, plain-language, mockup, cli, documents, human-surface]
depends_on: ["[[PLAN-024-working-in-compass-is-visual]]"]
summary: "every house term a person reads in Compass, with the plain word proposed in its place or a first-use gloss, and three real lines shown before and after"
created: 2026-10-27
updated: 2026-10-27
git_branch: "master"
git_commit: "8025594"
author: "builder"
---

# Plain Words: Mockup

Compass talks in words it coined itself. This page lists each one a person reads, the plain word proposed instead, and three real lines rewritten as samples. Under [[specs/human-surface/SPEC-031-working-in-compass-is-visual]]; the term counts come from [[research/human-surface/RESEARCH-working-in-compass-is-visual]]. Edit the third column of any row, or write `keep`, and the words are settled.

Where a program reads a word (a field name, a warning code), the file keeps it and the view shows the plain word. A term that is truly technical stays and is explained once, where it first appears.

## Terms

| Term | Where you see it | Say instead | Why |
|---|---|---|---|
| SPEC-031, ADR-017, PLAN-024, TASK-194 | `tree`, `index.md`, `active.md`, plans | keep, with gloss: title first, id after, "Working in Compass Is Visual (SPEC-031)" | the id is the address, the title is the meaning |
| spec, plan, research, vision, lesson, handoff, vault | everywhere | keep, with gloss: "spec (what we need)", "handoff (notes to resume next session)" at first use in each document | core nouns, few and stable |
| ADR | `tree`, `index.md` | keep, with gloss: "decision record (ADR-017)" | it names a thing the reader opens |
| frontmatter | templates, `validate` | properties | Obsidian already calls it that |
| wikilink | `validate`, templates | link | what it is to a reader |
| hot path | `hot-path`, `validate`, `index.md` | start-here files | says what the files are for |
| warm, cold, hot tier | method docs | start-here files, folder summaries, full documents | names each by its use |
| unit, unit folder, `make-unit`, `unit-check` | help, `tree`, `doctor` | workstream folder | what a person calls a big piece of work |
| unit-promotion candidates | `doctor` | workstreams that could get their own folder | says the action |
| domain, domain folder | `tree`, `index.md` | topic folder | domain is overloaded |
| scope note, "Class here:", "Class elsewhere:" | topic folder `index.md` | "What belongs here:", "Goes instead to:" | tells a filer what to do |
| promote, demote | help | turn into a folder, turn back into a file | says the result |
| sweep | help, `active.md`, `doctor` | move to the done list | says where it goes |
| elaborate, elaboration | plans, `active.md` | add detail | plain verb |
| rolling wave | plans, research | staged plan | detail now, sketch later |
| Wave 1, Wave 2 | plans, `active.md` | Stage 1, Stage 2 | wave is a metaphor |
| facet | skills, specs | topic tag | same thing as a tag |
| folksonomy | skills, research | free-form tags | plain phrase |
| admission control, `admit-check` | help | start-here size check | says what it guards |
| overlay | help, `doctor` | local additions | what they are |
| ledger | `doctor`, loops, reviews | run log | familiar word |
| escalated | lessons, session start | flagged: came back three times, needs your review | says why |
| capture opportunity | help, `doctor` | a moment to record a lesson | what happens |
| capture signal, strong signal | help, hooks | hint that a lesson is worth recording, strong hint | what it is |
| detached worker | help, `doctor` | background helper | plain |
| hook | help, `doctor` | automatic step | plain |
| gate | rules, questions | approval point | plain |
| changeability walk | specs, vision | split check: what must change together | says the question asked |
| taxonomy_hint | `validate`, `placement` | filing hint | plain |
| type-spread | `unit-check` | kinds of document tied to one spec | says what is counted |
| sizing_id, sizing log | `validate`, properties | shape record | what the log records |
| materialization, host | `doctor` | install for each tool (Claude Code and others) | names the act |
| D-NN | specs, plans, `coverage` | keep, with gloss: "decision D-01 (a numbered ruling)" | plans cite the number |
| trackable | `coverage`, `decisions` | the plan must cover it | says the duty |
| surfaced-but-uncited | `lesson-coverage` | relevant lesson, not cited | says the state |
| RAPTOR, MemGPT, Reinertsen, DESMET, PRISMA | research, ADRs, lessons | keep, with gloss: name plus one clause at first use, "Reinertsen (product-flow author)" | a name is a source, dropping it breaks the trail |
| complexity: S, M, L | plans, `active.md` | size: small, medium, large | plain words |
| depends_on: | plans, `active.md` | needs first: | plain |
| files: [...] | plans, `active.md` | touches: | plain |
| decisions: [...] | plans, `active.md` | carries decisions: | plain |
| lessons: [...] | plans, `active.md` | applies lessons: | plain |
| commit-upfront: | `active.md` | decided now because: | plain |
| Automated verification, Manual verification | plans | Checks Compass runs, Checks for you | says who acts |
| Convergence matrix | research | Where the sources agree | plain |
| Marks, Grade | research findings | Source checks, Weight of evidence | plain |
| covered, scoped, uncovered, PASS | `coverage` | carried in the plan, left for a later stage, missing; result ok or gap | plain |
| source-qualified citation | `coverage` | cite as document-name/D-01 | shows the form |
| capability usage, NEVER USED | `doctor`, `usage` | commands you have not run | plain |
| worker ledger | `doctor` | background helper log | plain |
| capture posture | `doctor` | how lesson recording is set up | plain |

## Warning codes

`compass validate` prints a code first. The proposal leads with a sentence and ends with the code in brackets, so tools and searches still find it.

| Code | Say instead |
|---|---|
| `broken_wikilink` | A link points to a document that does not exist. (broken_wikilink) |
| `ambiguous_wikilink` | A link could mean more than one document; write the longer form. (ambiguous_wikilink) |
| `frontmatter_error` | The properties at the top of a document cannot be read. (frontmatter_error) |
| `frontmatter_missing_field` | A document lacks a property its type needs. (frontmatter_missing_field) |
| `cap_exceeded` | The start-here files are over their size limit. (cap_exceeded) |
| `active_done` | Finished tasks are still in the active list; `compass sync` moves them. (active_done) |
| `sizing_unrecorded` | This workstream folder was made before the shape record existed. (sizing_unrecorded) |
| `sizing_orphaned_id` | A document names a shape record that is missing. (sizing_orphaned_id) |
| `folder_over_ceiling` | A folder holds more than 12 items; Compass will propose topic folders. (folder_over_ceiling) |
| `empty_scope` | A topic folder says nothing about what belongs in it. (empty_scope) |
| `taxonomy_hints` | Some documents carry filing hints waiting for a decision. (taxonomy_hints) |
| `unclassified_root_folder` | A top-level folder holds notes but is not marked as a workstream; Compass skips it. (unclassified_root_folder) |
| `loop_misshapen` | A loop folder is not laid out as expected; Compass skips it. (loop_misshapen) |

## Agents only, unchanged

Read by agents and hooks, never by a person deciding: `PreToolUse`, `PostToolUse`, `SubagentStop` and `Stop` events; hook output fields `additionalContext` and `stopReason`; subagent; orchestrator; worktree.

## Three real lines

A warning from `compass validate`:

```text
  warning folder_over_ceiling: research/pipeline: 16 direct children (ceiling 12) - propose the grouping; the ceiling only triggers the proposal, domains form at their second member
```

```text
  warning: research/pipeline holds 16 items, more than the 12 that read easily. Compass will propose topic folders; a topic folder needs at least two items. (folder_over_ceiling)
```

A line from `compass tree`:

```text
  ADR-017-capability-index-and-usage-record - the existing help listing is the progressive-disclosure index, made reachable by one resident rule line; maincli dispatch records every invocation to meta/usage.yaml; compass usage lists never-used commands explicitly; clean-tmp retires; the admission-control pair's fate is decided by the usage record
```

```text
  ADR-017 Finding commands - the help list is the guide to what Compass can do, one line in the always-loaded rules points to it, and every command run is counted so unused ones can be retired
```

A task line from `active.md`:

```text
- [ ] TASK-131: Exercise every shipped retriever against its live source and record the result beside the entry - complexity: S, depends_on: none, files: [plugin/cli/sources.yaml, plugin/cli/tests/test_sourceslib.py], decisions: [SPEC-023-research-covers-the-whole-spec/D-09, SPEC-023-research-covers-the-whole-spec/D-03]
```

```text
- [ ] TASK-131 (small, needs nothing first): Try each source fetcher that ships with Compass against its real site and note the result in that source's entry. Touches: plugin/cli/sources.yaml, plugin/cli/tests/test_sourceslib.py. Carries decisions D-09 and D-03 of SPEC-023.
```
