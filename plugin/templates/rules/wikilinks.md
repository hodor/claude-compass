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

Links to unit artifacts and domain members are path-qualified (e.g. `[[compass-cli/specs/SPEC-001-name]]`) and resolve straight to `.compass/<link>.md`; the full convention (resolving, authoring, ambiguity): the `obsidian` skill, file `path-qualified-links.md`.
