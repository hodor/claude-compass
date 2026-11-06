# Obsidian skill: decisions and documents the human reads

The decision bullet convention, the forms of a document a person decides on, an agent-written view, and the plain-word table.

## Decision bullets (the D-NN convention)

A ruling made in a spec or ADR is written as a discrete, referenceable bullet, not left buried in prose, so later stages can check it was carried through rather than silently dropped.

- **Unit:** `- **D-NN:** text` under a `## Decisions` (spec) or `## Decision` (ADR) heading, the bullets sitting in a `> [!NOTE]` callout so the rulings stand apart from the prose (every line of the callout starts with `> `) - the regex is `^#{2,3}\s*Decisions?\b`, case-insensitive, so `## Decisions (made by the human)` and `## Decision` both match. Continuation lines are indented under the bullet. IDs are plain `D-NN`, local to the document - the same number recurs across different documents by design.
- **Opt-out tags:** a `[informational]` or `[deferred]` bracket tag right after the ID marks the decision non-trackable. It is still parsed and recorded, just never required by the coverage gate. Example: `- **D-07 [deferred]:** revisit connection pooling after the migration lands.`
- **Discretion subheading:** bullets placed under a subheading whose text ends in "Discretion" (`### Builder discretion`, `### Claude's Discretion`) are non-trackable as a group, without tagging each one.
- **Citation form:** a plan or task claims a decision with a source-qualified citation, `<doc-stem>/D-NN` (e.g. `SPEC-007-decision-coverage-tracing/D-03`), resolved the same way a wikilink resolves. A bare `D-NN` claims nothing - local IDs collide across documents, so the source name is required.
- **Link form:** a document citing a decision links the Decisions heading, `[[SPEC-007-decision-coverage-tracing#Decisions]]`, because a callout cannot carry a block id a link could reach. See file `documents.md`, section "Documents the human reads".
- **Coverage:** `compass decisions <doc>` lists a document's decisions and exits 1 on a format mismatch (`could-not-parse`). `compass coverage <plan> [--against <doc>...]` checks that a plan covers every trackable decision of its `depends_on` spec and decision sources, and exits 1 on any gap. Documents predating this convention parse as `none-present` and are not retrofitted.

## Documents the human reads

A spec, plan or research document is read by a person who decides. It opens under its title with a picture of what is approved, then a callout saying what the person decides, then its text in plain words. The sentence-level writing principles (ornamental test, summaries, what a document carries, describing what IS, own authority, positive statements) are in `writing-principles.md` beside this file.

- **Opening picture.** A Mermaid diagram sized to one glance: for a spec the problem, the outcome and the rulings; for a plan its stages and the task dependencies; for research the findings by confidence and what they mean for the spec.
- **You decide callout.** Directly under the picture, a `> [!IMPORTANT]` callout whose text begins `You decide:` and asks the one question approving answers, naming what becomes binding. The callout leaves the file at approval, since an approved document states what is.
- **Callout types.** Five types, the ones GitHub draws as well as Obsidian: `[!NOTE]` for background (`[!NOTE]-` folds it), `[!TIP]` for a suggestion, `[!IMPORTANT]` for what the reader must decide, `[!WARNING]` for a risk, `[!CAUTION]` for harm that cannot be undone. Any other type shows on GitHub as a plain quote, so documents use these five.
- **Decisions in a callout.** The `- **D-NN:**` bullets sit in a callout under the Decisions heading. A callout cannot hold a block id a link could reach, so a document citing a decision links that heading (`[[SPEC-001-name#Decisions]]`).
- **Block ids.** A line cited from another document that sits outside a callout gets a block id, ` ^d-01`, at its end, and the citation links `[[doc#^d-01]]`. A block id inside a callout is not reachable by a link; link the heading instead.
- **Embed, never copy.** A section another document holds appears through `![[doc#Heading]]`, never copied, so one source stays true. A folded `> [!NOTE]-` callout holding embeds carries the rest of a long document below its opening.
- **Code blocks.** Every fence names the language of what it holds (` ```python`, ` ```cpp`, ` ```json`, ` ```markdown`, ` ```text` for plain output), so Obsidian and GitHub highlight it; a language that only a plugin draws is kept for blocks that plugin renders.
- **Bytes.** A visual stays when it removes as many bytes as it adds, or when the human keeps it knowing its cost. A visual that only decorates is cut. A table that replaces prose passes this test; a diagram that restates a paragraph the reader still needs does not. A mockup of a document carries a byte table: bytes added against bytes removed.

### A view an agent writes

The Compass view panel draws a ready-made view for a plan, spec, research or loop document. A document whose properties carry `view: views/<name>.js` gets that script's drawing instead.

- **Order of choice.** A ready-made view comes first. An agent writes its own view only for a picture none of them draws.
- **Where it lives.** The script sits in the vault's `views/` folder and exports one function taking `{app, file, text, el, open}`; `open(path, line)` opens a document at a line. The panel shows the script's path above the drawing.
- **Full access.** The script runs with the vault's full access, so it is written plainly and kept short.
- **Committed with the document.** The script is committed in the same commit as the document that names it, so the human reads it in the review's `git diff`.

### Plain words

Coined terms reach the human as plain words. Where a program reads a word, the files that hold it stay unchanged: field names (`complexity:`, `depends_on:`), warning codes, heading grammar (`## Decisions`, `Automated verification`) and command names. A view or a report shows the plain word; the file keeps the one the program parses. A warning prints as a sentence first and its code last in brackets: "A link points to a document that does not exist. (broken_wikilink)".

Some terms stay, explained once at first use in each document: ids lead with the title and follow with the id ("Working in Compass Is Visual (SPEC-031)"); the core nouns spec, plan, research, vision, lesson, handoff and vault carry a gloss ("spec (what we need)", "handoff (notes to resume next session)"); ADR reads "decision record (ADR-017)"; D-NN reads "decision D-01 (a numbered ruling)"; a source name takes one clause ("Reinertsen (product-flow author)"). Events and roles that only agents and hooks read (`PreToolUse`, `PostToolUse`, `SubagentStop`, `Stop`, `additionalContext`, `stopReason`, subagent, orchestrator, worktree) stay as written.

| Coined term | Say instead |
|---|---|
| frontmatter | properties |
| wikilink | link |
| hot path | start-here files |
| warm, cold, hot tier | start-here files, folder summaries, full documents |
| unit, unit folder, `make-unit`, `unit-check` | workstream folder |
| unit-promotion candidates | workstreams that could get their own folder |
| domain, domain folder | topic folder |
| scope note, "Class here:", "Class elsewhere:" | "What belongs here:", "Goes instead to:" |
| promote, demote | turn into a folder, turn back into a file |
| sweep | move to the done list |
| elaborate, elaboration | add detail |
| rolling wave | staged plan |
| Wave 1, Wave 2 | Stage 1, Stage 2 |
| facet | topic tag |
| folksonomy | free-form tags |
| admission control, `admit-check` | start-here size check |
| overlay | local additions |
| ledger | run log |
| escalated | flagged: came back three times, needs your review |
| capture opportunity | a moment to record a lesson |
| capture signal, strong signal | hint that a lesson is worth recording, strong hint |
| detached worker | background helper |
| hook | automatic step |
| gate | approval point |
| changeability walk | split check: what must change together |
| taxonomy_hint | filing hint |
| type-spread | kinds of document tied to one spec |
| sizing_id, sizing log | shape record |
| materialization, host | install for each tool (Claude Code and others) |
| trackable | the plan must cover it |
| surfaced-but-uncited | relevant lesson, not cited |
| complexity: S, M, L | size: small, medium, large |
| depends_on: | needs first: |
| files: [...] | touches: |
| decisions: [...] | carries decisions: |
| lessons: [...] | applies lessons: |
| commit-upfront: | decided now because: |
| Automated verification, Manual verification | Checks Compass runs, Checks for you |
| Convergence matrix | Where the sources agree |
| Marks, Grade | Source checks, Weight of evidence |
| covered, scoped, uncovered, PASS | carried in the plan, left for a later stage, missing; result ok or gap |
| source-qualified citation | cite as document-name/D-01 |
| capability usage, NEVER USED | commands you have not run |
| worker ledger | background helper log |
| capture posture | how lesson recording is set up |
