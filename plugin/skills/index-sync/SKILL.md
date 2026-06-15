---
name: index-sync
description: Refresh .compass derived state (root index, tag index, catalog rows, cap warnings, log cleanup) by running `compass sync`. The mechanical work lives in the CLI; this skill invokes it and surfaces findings.
version: 2.0.0
allowed-tools: [Bash]
when_to_use: "Run manually for an on-demand index refresh or health check. The PostToolUse hook already runs `compass sync` as a command on every vault write, so routine syncing is automatic - invoke this skill only when you want an explicit sync outside that path."
---

# Index Sync

All index, catalog, and tag-index regeneration, cap detection, and extraction-log cleanup is done by the `compass` CLI. The PostToolUse command hook runs it automatically on every vault write; this skill is the manual entry point.

## Run it

```bash
python3 "$CLAUDE_PLUGIN_ROOT/cli/compass" sync
```

Surface the report to the human verbatim. It lists entries added to the index, catalog rows added, the indexed tag count, any caps exceeded (a warning was written into the affected file), and extraction logs deleted.

## What it does

`compass sync` (`plugin/cli/commands/sync.py`):

- Appends missing artifacts to `index.md` under their type section, append-only so human-authored descriptions survive.
- Appends missing lesson rows to `meta/lessons-catalog.yaml`.
- Regenerates `meta/tag-index.yaml` from every artifact's `tags`.
- Updates folder-spec `children_count`.
- Writes a cap warning when the hot path, the catalog, or the lesson count exceeds its limit.
- Deletes `tmp/extraction-log-*.md` older than 30 days.

The CLI writes LF on every platform and never exits 2, so a sync can neither block nor corrupt a write.

## Validating instead of syncing

To check integrity (broken wikilinks, missing frontmatter, cap breaches) rather than regenerate, run `compass validate`. It exits non-zero and prints a per-defect report when the vault has problems.
