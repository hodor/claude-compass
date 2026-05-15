---
paths:
  - "**"
---

# Following Wikilinks in the Compass Vault

When you see a wikilink like `[[SPEC-001]]` or `[[vision]]` in a vault file and need to read the target:

1. Strip `#heading` and `^block-id` suffixes from the link.
2. Glob for the file: `Glob: .compass/**/<linkname>*.md`
3. If multiple matches, prefer the shortest path.
4. Read the file.

Example: `[[SPEC-001]]` -> `Glob: .compass/**/SPEC-001*.md` -> `.compass/specs/SPEC-001-roblox-ingestion.md` -> Read.

This is the convention for the entire vault. No special tool needed.
