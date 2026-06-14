---
name: promote-spec
description: Surgically promote a flat spec into a folder spec. Converts SPEC-NNN-name.md into SPEC-NNN-name/index.md, updates all inbound wikilinks across the vault, preserves the spec's frontmatter and body verbatim. Non-destructive - existing tags and content survive.
version: 1.0.0
allowed-tools: [Read, Glob, Grep, Edit, Write, Bash]
argument-hint: "<SPEC-NNN-name | path-to-spec>"
when_to_use: "Run /compass:promote-spec when a flat spec needs to grow children. Common cause: the spec body exceeded ~2,000 tokens, or you identified 3+ sub-concerns that deserve their own files. Pre-validates that the wikilink rewrites will not break anything."
---

# /compass:promote-spec - Convert a flat spec to a folder spec

A flat spec is one file: `specs/SPEC-002-tile-editor.md`. A folder spec is a directory whose `index.md` IS that spec, with child specs inside.

This skill does the migration in one atomic operation. The spec body is preserved verbatim; only its filesystem location changes. Wikilinks pointing at the spec continue to work because Obsidian resolves `[[SPEC-002-tile-editor]]` to the folder's `index.md`.

## Protocol

### 1. Resolve the target

Argument is either a spec ID (e.g. `SPEC-002-tile-editor`) or a path (e.g. `specs/SPEC-002-tile-editor.md`). Glob to find the actual file. If not found, exit with `error: spec not found`.

The target must be a flat `.md` file directly inside a type root (`specs/`, `plans/`, `decisions/`, etc.). If the target is already a folder, exit with `error: spec is already a folder`.

### 2. Verify wikilink safety

Grep the entire vault for `[[<spec-id>]]` and `[[<spec-id>/...]]`. Count matches. These wikilinks will continue to resolve after the promotion (Obsidian resolves `[[name]]` to either `name.md` OR `name/index.md`, same target).

If any wikilink uses an unexpected form (e.g. `[[<spec-id>.md]]` with explicit extension), flag and ask the human whether to rewrite. Default: do not rewrite, let Obsidian handle it.

### 3. Perform the promotion

This is the load-bearing step. Two file operations, both atomic:

```bash
# Create the folder
mkdir -p .compass/specs/SPEC-002-tile-editor
# Move the spec to index.md - preserves frontmatter, body, and git history (git mv)
git mv .compass/specs/SPEC-002-tile-editor.md .compass/specs/SPEC-002-tile-editor/index.md
```

If `git mv` is not available (no git, or file is untracked), fall back to `mv`. Either way, the file is renamed, not copied.

### 4. Update the promoted file's frontmatter

Add `children_count: 0` to the frontmatter. This is the marker that says "this is a folder spec." `index-sync` will keep it accurate as children arrive.

### 5. Verify

- The folder `.compass/specs/SPEC-002-tile-editor/` exists.
- The file `.compass/specs/SPEC-002-tile-editor/index.md` exists with the original frontmatter (plus `children_count: 0`) and body.
- The flat file `.compass/specs/SPEC-002-tile-editor.md` no longer exists.
- Grep for `[[SPEC-002-tile-editor]]` across the vault - count should match the pre-migration count.

### 6. Report

```
promoted: SPEC-002-tile-editor (flat -> folder)
  old path: .compass/specs/SPEC-002-tile-editor.md
  new path: .compass/specs/SPEC-002-tile-editor/index.md
  inbound wikilinks: N (unchanged, Obsidian auto-resolves)
  children_count: 0
  next: create children with the spec-write or planner agent
```

The PostToolUse hook fires `index-sync` automatically after the writes complete; the tag index and root `index.md` will reflect the new structure on the next sync.

## Failure modes worth naming

- Trying to promote a folder spec - already a folder. Refuse.
- Trying to promote a non-spec/plan/decision file. Refuse.
- Leaving the flat file behind after creating the folder - that creates two artifacts with the same identity. The `git mv` / `mv` is non-negotiable.
- Forgetting to add `children_count: 0` - then `index-sync` cannot distinguish folder-spec from a top-level subfolder.
- Manually rewriting wikilinks to new paths - unnecessary, Obsidian resolves the short form to either flat or folder. Only rewrite if the existing wikilink used an unusual form (explicit `.md` extension).
