---
paths:
  - "**"
---

# Following Wikilinks in the Compass Vault

When you see a wikilink like `[[SPEC-001]]` or `[[vision]]` in a vault file and need to read the target:

1. Strip `#heading` and `^block-id` suffixes from the link.
2. Glob for the file: `Glob: .compass/**/<linkname>*.md`
3. If multiple matches, the link is ambiguous: prefer the shortest path, but check whether the linking document sits inside a unit folder - a link authored inside `.compass/<unit>/` most likely targets that unit's own artifact.
4. Read the file.

Example: `[[SPEC-001]]` -> `Glob: .compass/**/SPEC-001*.md` -> `.compass/specs/SPEC-001-roblox-ingestion.md` -> Read.

## Path-qualified links (unit artifacts and domain members)

Artifacts inside a unit folder (a root folder whose `index.md` declares `type: unit`) and artifacts below a domain folder (a topic folder inside `specs/` or `research/`) are linked path-qualified: the vault-relative path without extension, e.g. `[[compass-cli/specs/SPEC-001-name]]` or `[[specs/network/cache/SPEC-001-eviction]]`. Numbering is local per folder, and domain names reuse across branches, so bare stems are genuinely ambiguous; the path is the identity. Generated surfaces link a folder as the piped full path to its index (`[[specs/network/index|network]]`) because Obsidian opens files, never folders.

- Resolving: a path-qualified link maps straight to one file - `.compass/<link>.md` (a folder spec resolves to `.compass/<link>/index.md`). No search needed.
- Authoring: always write the path-qualified form for unit artifacts. Bare stems are for root artifacts only. A root doc nested in a plain grouping subfolder (its parent has no index.md) is also linked by its full vault-relative path, e.g. `[[research/sub/note]]`.
- Ambiguity: if a bare-stem glob returns more than one match, prefer the path-qualified form - resolve using the linking document's own location (step 3), and write any link you author with the full vault-relative path.

This is the convention for the entire vault. No special tool needed.
