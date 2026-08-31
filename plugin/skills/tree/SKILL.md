---
name: tree
description: Render the whole vault at a glance by running `compass tree` - every artifact under every type dir and unit, indented by depth, one line per artifact with its own summary, computed from the markdown at invocation so it can never be stale.
version: 1.0.0
allowed-tools: [Bash]
when_to_use: "Run when the human wants to see everything the vault holds in one view - the root index lists only the first level, so no single file shows the whole tree. Triggers: 'compass tree', 'show the vault tree', 'what does the vault contain', 'list all specs and research'."
---

# Tree

The root index speaks in domains - one line per broad area - so no single file lists every artifact. `compass tree` renders the whole vault on demand: every artifact under every type dir and unit, indented by depth, each line carrying the artifact's own `summary:`. Nothing is stored; the answer is derived from the markdown at the moment it is asked for.

## Run it

```bash
python3 "$CLAUDE_PLUGIN_ROOT/cli/compass" tree
```

Surface the output to the human verbatim. It is also the fastest greppable surface for a whole-vault search: pipe it through grep when the human is looking for something specific.

```bash
python3 "$CLAUDE_PLUGIN_ROOT/cli/compass" tree | grep -i "<term>"
```

## What it shows

- Top-level groups: each type dir (specs, research, decisions, lessons, ...) and each unit.
- Domain folders as `name/` lines with their scope-note summary; members indented beneath.
- Plain grouping folders (no index.md of their own) as bare `name/` header lines.
- Every artifact as `stem - summary`, falling back to its title when no summary exists.
