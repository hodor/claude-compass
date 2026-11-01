The ornamental test, applied to every sentence: it helps the document do its job for a later reader, or it goes.

Summaries explain - what happens and why, in words a newcomer understands. An enumeration of internal names is not a summary: "grappling hook, boss key, shield; ends with the tree dying" tells nothing to someone who has not played the game.

A document carries only what its own job needs. What another document already holds is a wikilink, never a restatement - a plan holds what to do, a spec holds the need, research holds the evidence.

Documents describe what IS. The story of a document's making lives in git history and commit messages; a sentence that only makes sense to someone who watched the document get written is deleted.

Documents speak with their own authority. A rule is stated as the rule, and the human's phrasing survives as the document's own prose; who spoke, and when, lives in git.

State principles positively. Listing what a rule is not about makes that list read as the rule's real subject.

Brevity binds your own prose only. The human's captured words (spec problems, vision goals, quoted rulings) are content, and they stay in his sentences at whatever length he spoke them.

Research is the exception: it captures evidence and can be as long as required.

Decisions consolidate by topic: a ruling that refines an existing decision merges into it. The section heading is `## Decisions`.

## Scope of the reader test

The test binds everything an agent writes, not only vault documents: code comments, test names and assertion messages, commit bodies, skill and agent text. Each must make sense to a first-time reader who has only the file. State what the thing is, positively; a sentence that only makes sense to someone who watched it get written goes.

Compass documents should be a pleasure to read. Easy to read, short, sweet. Long only when needed. Never verbose. The `obsidian` skill holds the forms (opening picture, callouts, embeds) and the plain words a human reads.

## Indexing a new vault document

After creating ANY vault document (spec, plan, research, ADR, lesson, vision, handoff, review), add a link to it in `.compass/index.md` under the appropriate section. This is mandatory in the same step that creates the document, not a follow-up. Documents not in index.md are invisible to the next session.

The index is an index. Its one-line description is a copy of the document's own `summary:` frontmatter, never the only place that text exists. Write `summary:` when you create the document; `compass validate` warns when it is missing. An index that stores what it should point at cannot be shortened without losing it.
