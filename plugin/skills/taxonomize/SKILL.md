---
name: taxonomize
description: Bulk-migrate a flat vault to the hierarchical+faceted scheme. Analyzes existing specs, proposes a faceted tag vocabulary and a folder hierarchy, presents the proposal as a diff, executes after human approval. Non-destructive - existing tags and references survive.
version: 1.0.0
allowed-tools: [Read, Glob, Grep, Edit, Write, Bash, Agent]
argument-hint: "[--specs | --plans | --all] [--apply]"
when_to_use: "Run /compass:taxonomize when an established vault has accumulated flat specs that should be grouped, or when starting hierarchical conventions on an existing project. Two modes: proposal-only (default, prints the plan) and apply (executes after explicit human approval)."
---

# /compass:taxonomize - Bulk migrate to hierarchical + faceted vault

Analyzes the current vault, proposes faceted tags and folder groupings, executes the migration after human approval. Used once at the transition; rarely after that.

## Protocol

### 1. Argument parsing

- `--specs` - only operate on `.compass/specs/`
- `--plans` - only operate on `.compass/plans/`
- `--all` - operate on specs AND plans (default)
- `--apply` - execute the migration after presenting it (default is proposal-only)

If `--apply` is not set, this skill is read-only.

### 2. Inventory

Glob every flat spec/plan in scope. Read frontmatter (title, area, tags, summary, status). Read the first 200 lines of body. Record:

- Existing tags per file
- Title and summary
- Body length (lines and rough token count)
- Wikilinks the file emits (outbound references)
- Backlinks the file receives (inbound, via grep)

### 3. Analyze tag vocabulary

Aggregate all tags. Identify:

- **Synonyms** - tags that mean the same thing (`tile-editor`, `tileEditor`, `tile_editor`). Propose canonical form.
- **Sparse tags** - tags on a single spec only. Candidates for removal or merger.
- **Implicit tags** - words that appear in many titles but are not in any frontmatter. Candidates for addition.
- **Missing tags** - specs with empty or absent `tags:` field.

Produce a tag-vocabulary proposal.

### 4. Analyze folder groupings

For specs with body exceeding ~2,000 tokens, or with 3+ sub-concerns identifiable in the body, propose folder promotion via `/compass:promote-spec`.

For groups of related flat specs that share multiple tags AND a common title prefix or theme, propose grouping them under a new parent folder. This is the rarer case. Example: if `SPEC-005-brush-strokes.md`, `SPEC-006-brush-radius.md`, `SPEC-007-brush-opacity.md` all carry `tags: [brush]` and have body sizes under the threshold, propose grouping them into `SPEC-NNN-brush/` with each becoming a child.

Spawn an Agent sub-task to judge groupings - this is heuristic work and benefits from a fresh context. Have the agent return a structured list of proposed groupings with the rationale.

### 5. Present the proposal

Print a structured diff for human review. Do NOT execute yet.

```
## Tag vocabulary changes
- merge: tileEditor + tile_editor -> tile-editor (affects N specs)
- retire: foo (used by 1 spec, no clear meaning)
- add: rendering tag to specs/SPEC-007-shaders.md (inferred from title and body)

## Folder promotions
- SPEC-002-tile-editor.md -> SPEC-002-tile-editor/index.md
  Reason: body 3,400 tokens, 4 sub-concerns identified (material, brush, grid, palette)
  After promotion, expect to create:
    - SPEC-001-master-material.md (from sub-concern in body)
    - SPEC-002-brush-system.md
    - SPEC-003-tile-grid.md
    - SPEC-004-palette.md
  (Child creation is NOT done by taxonomize. Done by the spec/plan skills after promotion.)

## Folder groupings (new parent folder for related specs)
- group: SPEC-005-brush-strokes.md + SPEC-006-brush-radius.md + SPEC-007-brush-opacity.md
  Proposed parent: SPEC-NNN-brush-system/
  Rationale: all carry tags [brush, rendering]; titles share prefix
  After grouping, children numbering resets to 1, 2, 3 within the new folder.

## Files that will be modified
- 3 frontmatter tag rewrites (synonym merges, additions)
- 1 folder promotion (1 file moved)
- 1 folder grouping (3 files moved into new parent)
- 0 file deletions (this skill never deletes content)

Run with --apply to execute. Without --apply, exits here.
```

### 6. Execute on --apply

If `--apply` is present and the human has reviewed the proposal:

For each tag-vocabulary change, run an Edit pass across the affected files (single-file Edit calls in series, NOT a `replace_all` sweep - we are operating on YAML frontmatter and must preserve format).

For each folder promotion, call `/compass:promote-spec SPEC-NNN-name`. That skill handles the file move and the `children_count: 0` marker.

For each folder grouping, create the parent folder, write a parent `index.md` skeleton (frontmatter + body containing the rationale; the human will fill in real parent-level content later), `git mv` the children into the folder, renumber the children locally (1, 2, 3, ...).

After all operations, the PostToolUse hook fires `index-sync`, regenerating the tag index and refreshing the root `index.md` tree view.

### 7. Report

```
taxonomize complete:
  tag vocabulary merges: 2
  tags added: 5
  tags retired: 1
  folder promotions: 1
  folder groupings: 1 (3 specs grouped)
  wikilinks reverified: N (Y still resolve, 0 broken)
  next steps:
    - flesh out SPEC-NNN-brush-system/index.md (parent body is currently a skeleton)
    - run /compass:checkup to validate vault integrity
```

## Failure modes worth naming

- Auto-renaming tags without human approval. Tag vocabulary is the human's call. Surface, do not execute, unless `--apply`.
- Bulk grouping that loses sub-concerns. If a flat spec was actually a coherent single concern with theme, do NOT promote it. Only promote when the body has multiple sub-concerns OR exceeds the size threshold.
- Renumbering wikilinks. After folder grouping, children get new local numbers. Wikilinks across the vault may need updates. Verify with grep after migration; surface any that did not resolve.
- Skipping inbound wikilink verification. Every migration must pass: pre-grep count of `[[name]]` references equals post-grep count of resolved targets.
- Promoting then deleting the original. This skill is non-destructive. `git mv` only.
