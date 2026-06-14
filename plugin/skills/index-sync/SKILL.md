---
name: index-sync
description: Sync .compass/index.md and lessons-catalog.yaml with on-disk artifacts. Pure mechanical glob plus diff plus append. Validates the just-written file's frontmatter and wikilinks. Deletes extraction logs older than 30 days. Invoked by the PostToolUse hook on any vault write. Safe to run any time.
version: 1.0.0
allowed-tools: [Read, Glob, Grep, Edit, Bash]
when_to_use: "Invoked automatically by the PostToolUse hook when any tool writes to .compass/**/*.md. Also safe to run manually for vault health checks."
---

# Index Sync

Keeps `index.md` and `lessons-catalog.yaml` aligned with the filesystem. Pure mechanical work. No model judgment. Cheap enough to run on every vault write.

## Scope

Touches:

- `.compass/index.md` - append missing entries
- `.compass/meta/lessons-catalog.yaml` - append missing rows for lesson files
- `.compass/tmp/extraction-log-*.md` - delete files older than 30 days

Reads but does not modify:

- `.compass/{specs,plans,research,decisions,lessons,handoffs,prs}/*.md`

Ignores entirely:

- `.compass/tmp/` (other than extraction logs)
- `.compass/meta/` (other than catalog)
- `.compass/.annotations/`
- `.compass/archive/` (archived docs do not appear in the current index)
- `.compass/index.md` and `.compass/meta/lessons-catalog.yaml` themselves (never recurse on own writes)

## Protocol

### 1. Glob vault artifacts

Run these globs in parallel. The leading `**/` prefix is required - the Glob tool does NOT traverse hidden directories (those starting with `.`) without it. The recursive `**` in the middle catches BOTH flat specs (`SPEC-001-foo.md`) AND hierarchical folder specs (the folder's `index.md` is the spec):

```
**/.compass/specs/**/*.md
**/.compass/plans/**/*.md
**/.compass/research/**/*.md
**/.compass/decisions/**/*.md
**/.compass/lessons/**/*.md
**/.compass/handoffs/**/*.md
**/.compass/prs/**/*.md
```

Collect every result with its full path. For each path, classify:

- **Flat spec/plan/etc**: matches `TYPE-NNN-name.md` directly in the type root.
- **Folder spec/plan**: matches `*/index.md` inside the type root. The folder is the spec; its name carries the SPEC-NNN-name identity.
- **Child of folder spec**: matches `TYPE-NNN-name.md` inside a folder spec, possibly nested.

Skip `.compass/meta/` paths even if globbed - they are auto-maintained config files, not vault artifacts.

### 2. Read frontmatter for each

For each file, read just the frontmatter block (lines between the first two `---` markers). Extract `type`, `title` or `summary`, `status`.

If a file has no frontmatter or the frontmatter is malformed, record it as a malformed-file finding. Do not halt - keep going.

### 3. Build the expected index map

Group files by their `type` field. Standard mapping:

| type | index.md section |
|---|---|
| spec | `## Specs` |
| plan | `## Plans` |
| research | `## Research` |
| decision | `## Decisions` |
| lesson | `## Lessons` |
| handoff | `## Handoffs` |
| pr | `## PRs` |

Skip files with `status: archived` - they belong in archive and should not appear in the current index.

### 4. Diff against index.md

Read `.compass/index.md`. For each section above, parse existing wikilinks (pattern `\[\[([^\]]+)\]\]`). Compare against the expected set for that type.

For every file in the expected set not present in the index:

- Determine the entry format: `- [[<wikilink-target>]] - <summary or title>`
- For folder specs, the wikilink target is the folder name (e.g. `[[SPEC-002-tile-editor]]`), which Obsidian resolves to its `index.md`.
- For children of folder specs, the wikilink target is the full path inside the type root (e.g. `[[SPEC-002-tile-editor/SPEC-001-master-material]]`).
- For the summary, prefer the frontmatter `summary` field; if absent, fall back to `title`; if absent, use the filename.

### Hierarchical rendering

The root `index.md` renders the tree compactly. Each section shows entries indented to reflect their folder depth:

```markdown
## Specs

- [[SPEC-001-flat-thing]] - one-line summary
- [[SPEC-002-tile-editor]] (folder, 3 children) - parent summary
  - [[SPEC-002-tile-editor/SPEC-001-master-material]] - one-line
  - [[SPEC-002-tile-editor/SPEC-002-brush-system]] (folder, 2 children) - parent summary
    - [[SPEC-002-tile-editor/SPEC-002-brush-system/SPEC-001-stroke-rendering]] - one-line
    - [[SPEC-002-tile-editor/SPEC-002-brush-system/SPEC-002-blending-modes]] - one-line
  - [[SPEC-002-tile-editor/SPEC-003-tile-grid]] - one-line
```

Indent two spaces per depth level. Append `(folder, N children)` to any folder-spec entry; the count comes from the folder's `index.md` frontmatter `children_count`.

If a section does not exist in `index.md`, create it. Insert after the last existing `##` section, before any closing content.

Do NOT remove entries from `index.md` that are not in the expected set. The user may have written context lines; only append, never delete. Stale entries are surfaced separately as a finding.

### 4b. Update folder index.md children_count

For every folder spec, count the number of child files (depth 1, excluding sub-folders' children). Edit the folder's `index.md` frontmatter `children_count: N`. If `children_count` is missing or stale, this is the sync. Do NOT touch the body; the `## Children` section in the body is refreshed by `/compass:consolidate`, not by `index-sync`.

### 5. Diff lessons-catalog.yaml

Read `.compass/meta/lessons-catalog.yaml`. Parse the `lessons:` list. Extract every `file:` value.

For every file in `.compass/lessons/*.md` whose name is not in the catalog file list:

- Read the lesson's frontmatter
- Append a row to the catalog with: `file`, `status`, `category`, `area`, `tags`, `score`, `summary` pulled from the lesson's own frontmatter
- If any required field is missing from the lesson, record as a malformed-lesson finding and skip the row append

Never reorder existing rows. Append only.

### 5b. Build / update the tag index

The tag index (`.compass/meta/tag-index.yaml`) is the multi-parent retrieval primitive. Regenerate from scratch every sync (it is small and fully derived):

For every globbed vault file from step 1, read frontmatter `tags`. For each tag in any file, accumulate `tag -> [list of file paths]`. Sort tags alphabetically, sort each tag's file list alphabetically. Write:

```yaml
# Generated by index-sync. Do not hand-edit; changes will be overwritten.
# To merge / rename / retire tags, run /compass:consolidate.
tags:
  rendering:
    - specs/SPEC-002-tile-editor/SPEC-001-master-material.md
    - specs/SPEC-002-tile-editor/SPEC-002-brush-system/SPEC-001-stroke-rendering.md
  tile-editor:
    - specs/SPEC-002-tile-editor/index.md
    - specs/SPEC-002-tile-editor/SPEC-001-master-material.md
```

Skip files in `.compass/meta/`, `.compass/tmp/`, `.compass/archive/`, `.compass/.annotations/`.

The tag index is NOT loaded in the hot path. Agents read it on demand for multi-tag queries.

### 6. Check hard caps

After step 5, check three caps. When any cap is exceeded and no existing warning is present, prepend a single-line HTML comment to the relevant file.

- **`index.md` size cap (hot path):** 5,000 tokens OR 250 lines. The hot path is loaded on every agent turn; exceeding cap blows the agent's budget. Warning at top: `<!-- WARNING: index.md exceeded hot-path cap. Run /compass:consolidate before next session. -->` Per [[ADR-004-hierarchical-specs-with-facets]].
- **`lessons-catalog.yaml` size cap:** 200 lines OR 25 KB. Warning above the `lessons:` key: `# WARNING: catalog exceeded cap. Run /compass:consolidate before next session.`
- **`lessons/` directory count cap:** 50 files (status: active, excluding archived). Warning above the `lessons:` key in `lessons-catalog.yaml`: `# WARNING: lesson count exceeded 50. Run /compass:consolidate before next session.`

If a warning is already present, do not duplicate it. If consolidation has run (warning removed) and the cap is no longer exceeded, do not re-add.

The warning is the self-healing signal. The next session's hot-path read sees it; the methodology forces consolidation before any other work.

### 7. Validate the just-written file (only if hook-invoked with a path)

When the PostToolUse hook fires, it passes the just-written file path as `$ARGUMENTS`. Run two cheap checks on that single file (skip if invoked manually without a path):

**7a. Frontmatter schema check.** Read the file's frontmatter. Verify required fields per type:

| type | required |
|---|---|
| spec | title, type, status, area, tags, created, updated |
| plan | title, type, status, area, tags, created, updated, depends_on |
| research | title, type, status, area, tags, created, updated |
| decision | title, type, status, confidence, area, tags, created, updated |
| lesson | title, type, status, category, area, tags, created, updated, score, summary |
| handoff | title, type, status, area, tags, created, updated |

For any missing required field, record as finding `frontmatter_missing_field: <file>:<field>`.

**7b. Wikilink resolution check.** Grep the file for `\[\[([^\]]+)\]\]`. Skip any match that falls inside:

- A fenced code block (between ```` ``` ```` markers)
- An inline code span (between single backticks on the same line)

These are illustrative examples like `[[NAME]]`, `[[link]]`, `[[wikilinks]]`, not real references. For each remaining link target:

- Strip any `#Section` suffix and any `|Display Text` suffix
- Glob `**/.compass/**/<target>.md`. Also accept the special targets `active`, `backlog`, `index`, `vision` (top-level vault files).
- If no file matches, record as finding `broken_wikilink: <file>:<line>: [[<target>]]`

Both checks are warnings, not blockers. Continue to step 8 regardless.

### 8. Clean extraction logs

```bash
find .compass/tmp -name 'extraction-log-*.md' -type f -mtime +30 -delete
```

If `find` is not available (Windows without bash), use the equivalent:

```powershell
Get-ChildItem .compass/tmp -Filter 'extraction-log-*.md' -File | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item
```

Record the count of deleted files.

### 9. Report

Return a structured report:

```
## Index Sync Report

Specs:      <expected>/<linked> | added: <N>
Plans:      <expected>/<linked> | added: <N>
Research:   <expected>/<linked> | added: <N>
Decisions:  <expected>/<linked> | added: <N>
Lessons:    <expected>/<linked> | added: <N>
Handoffs:   <expected>/<linked> | added: <N>
PRs:        <expected>/<linked> | added: <N>

Catalog rows added: <N>
Caps exceeded: [index.md | catalog | lesson count] - warnings written
Extraction logs deleted: <N>

Findings:
- Malformed frontmatter: <file>:<reason>
- Stale index entry: <wikilink in index but file missing>
- Malformed lesson (skipped catalog row): <file>:<missing field>
- Frontmatter missing field: <file>:<field>
- Broken wikilink: <file>:<line>: [[<target>]]
```

Omit any line that is zero. Omit Findings if empty.

## Performance

This skill runs on every vault write via PostToolUse. Keep it cheap:

- Glob is one parallel batch
- Frontmatter read is the first 20 lines per file, not the whole file
- Index edit uses targeted append, not full rewrite
- Catalog edit uses targeted append

For a vault with 100 documents, total runtime should stay under 2 seconds. If it exceeds this regularly, the bottleneck is likely repeated full-file reads - switch to head-style reads of the first 20 lines.

## Loop prevention

The PostToolUse hook that fires this skill must filter out writes to:

- `.compass/index.md`
- `.compass/meta/lessons-catalog.yaml`

Otherwise this skill's own writes would re-trigger it. The filter belongs in the hook config, not in this skill. If you observe runaway behavior, check the hook matcher first.

## Failure modes worth naming

- Removing entries from `index.md`. Append-only. The user owns deletion.
- Reordering catalog rows. Append-only.
- Rewriting the index from scratch instead of targeted appends. Loses any human-authored context lines.
- Halting on a single malformed file. Record the finding, keep going.
- Re-firing on the index sync's own writes. The hook matcher must exclude index.md and lessons-catalog.yaml.
