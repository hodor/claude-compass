---
name: research
description: Research entry point. A plainly code-shaped or paper-shaped question dispatches straight to research-codebase or research-papers. Anything naming a spec runs full scope derivation - the whole spec becomes the axis list, the human's own questions lead, grading is disclosed and gated, and one researcher per axis feeds a reviewer that consolidates.
version: 2.0.0
allowed-tools: [Read, Grep, Glob, Bash, Agent]
when_to_use: "Use to research a spec, or to research anything else. Triggers: 'research this spec', 'research this', 'investigate', 'do some research', 'find out how X works'. A question that plainly names a codebase location or a paper/algorithm dispatches directly; anything naming a spec runs the derivation below."
argument-hint: "<spec name> | codebase <question> | papers <topic>"
---

# Research - Scope Derivation and Dispatch

Two shapes. A plain code or paper question dispatches straight through. A spec runs the full derivation: the whole spec sets the scope, never its Open Questions list; the human's own questions lead; and every researcher's grading is disclosed and gated before anything runs.

## Direct dispatch

| Skill | When | What it spawns |
|-------|------|----------------|
| `research-codebase` | "How does X work in the codebase?", "Where is Y handled?", "Trace this flow" | codebase-locator, codebase-analyzer, pattern-finder |
| `research-papers` | "Explain this paper", "What's the prior art for X", an arXiv ID or paper title | Three researchers (Current / Backward / Forward) plus a reviewer |

`codebase <question>` or a plainly code-shaped question (a file path, function name, "where", "trace") dispatches to `research-codebase`. `papers <topic>` or a plainly paper-shaped question (an arXiv ID, paper title, "algorithm", "technique") dispatches to `research-papers`. If neither prefix is given and the question is genuinely ambiguous, ask once whether it is code, papers, or a spec to derive from. Don't reimplement either skill's logic here.

## Deriving scope from a spec

### 1. Read the whole spec

Read every section in full, not only Open Questions. An axis answers an Open Question where it happens to touch one; the questions never set the scope.

### 2. Decompose the spec's own structure

For each Need, ask how it would be met and write the axis that investigates it. For each Decision, ask why it was made and write the axis that investigates the concern standing above it. This turns the spec's own shape into the first pass of the axis list, per [[research/pipeline/RESEARCH-scope-derivation-from-a-spec]].

### 3. Audit against completeness facets

Check the resulting list against a fixed set of facets, so a whole category does not go unchecked the way an unstructured list tends to: functional behavior, non-functional quality (performance, security, usability, reliability), interfaces and integration points, constraints, and stakeholder context. Add an axis for any facet the decomposition left untouched.

### 4. Fold in the human's own questions

If the human has questions about this spec, they enter the axis list first, with no judgment on whether to accept them, and the rest of the list regenerates around them. The spec's own Open Questions stay answered-where-touched and never lead.

### 5. Enumerate the session

Run `claude mcp list` and `claude plugin list --json`. Dedupe plugins by name, since the same plugin can register separately at user, project, and local scope, and read `enabled` per scope for whichever entry wins. Run `python .claude/cli/compass sources` and read its rows for the curated source list every axis starts from; run it with `--check --live` to confirm reachability before the run.

### 6. Grading disclosure

State which grading the run intends to apply to evidence and on what basis, and that the human can refuse it without stopping the run. A refusal turns grading off for every researcher spawned below; it never blocks the research itself.

### 7. The gate

Present the axis list, one plain line per axis naming where its answer will be sought, alongside the grading disclosure. Block on the reply.

- Approval, accepting or ignoring the grading disclosure: proceed, every brief below carries `grading: allowed`.
- Approval with grading explicitly refused: proceed, every brief below carries `grading: refused`.
- A named change: fold it in, regenerate the axis it touches, and present again.

Cap regeneration at three passes; past that, escalate to the human directly instead of presenting again.

### 8. Spawn one researcher per axis

Each brief carries the axis, the sources to check first (from `plugin/cli/sources.yaml` and anything session enumeration surfaced), the `research-methods` skill to choose a methodology from, and the `grading:` field the gate settled on (`allowed` or `refused`). Spawn every axis in parallel.

### 9. Consolidate with the reviewer

Spawn `reviewer` with every researcher's output. It builds the convergence matrix and writes the consolidated `REVIEW-*.md` to `.compass/research/`.

### 10. A gap becomes another research pass

If the review names a gap it cannot close, spawn another research pass on that gap. An unclosed gap never goes to a plan.

## Failure modes worth naming

- Letting the spec's Open Questions set the scope instead of the whole spec.
- Skipping the facet audit and shipping whatever the decomposition happened to produce.
- Presenting the gate without the grading disclosure, or treating silence on grading as a refusal instead of `allowed`.
- Reimplementing `research-codebase` or `research-papers` inline instead of dispatching.
- Spawning researchers before the gate returns approval.
- Forcing the user to name a spec when the question is clearly a plain code or paper question.
