---
name: consolidate-memory
description: Condense this project's file-based memory (the ~/.claude/projects/<project>/memory/ store) - merge duplicates, prune one-session and stale facts, condense verbose bodies, and rebuild MEMORY.md to one line per memory. Cuts the per-session context the memory loads.
version: 1.0.0
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
when_to_use: "Use when a project's memory has grown - many memory files, or a MEMORY.md index that is no longer one line per memory - and is inflating every session's starting context. Triggers: 'consolidate memory', 'condense memory', 'clean up memory', 'memory is bloated'."
---

# /compass:consolidate-memory - Condense the project memory store

The file-based memory at `~/.claude/projects/<this-project>/memory/` loads into every session's context (the `MEMORY.md` index always; recalled files on top). It grows unbounded because memories are written but rarely pruned. This skill is the consolidation pass - the memory analogue of `/compass:consolidate` for lessons.

This is judgment work: you read the memory, decide what is durable, and rewrite it tighter. Be conservative with durable facts; aggressive with noise.

## 1. Locate the memory directory

```bash
ENC=$(cygpath -w "$(pwd)" 2>/dev/null | sed 's#[:\\/]#-#g' || pwd | sed 's#[:/]#-#g')
MEMDIR="$HOME/.claude/projects/$ENC/memory"
ls -la "$MEMDIR" 2>/dev/null || { echo "no memory dir found for this project; try: ls ~/.claude/projects/"; }
```

If that path is empty, `ls ~/.claude/projects/` and pick the entry matching this project's absolute path (separators replaced by `-`).

## 2. Measure the starting point

Count files and total tokens (chars/4) so you can report before/after:

```bash
python -c "import glob,os;d=os.path.expanduser(r'$MEMDIR');fs=glob.glob(os.path.join(d,'*.md'));print(len(fs),'files,',sum(len(open(f,encoding='utf-8',errors='ignore').read()) for f in fs)//4,'tokens')"
```

## 3. Read everything

Read `MEMORY.md` and every memory file. Group them by `metadata.type` (user / feedback / project / reference) and by topic.

## 4. Consolidate, by the memory rules

- **Merge duplicates and near-duplicates** into one file. Several files about the same decision, build quirk, or component become one.
- **Delete one-session / ephemeral content** - "session-details", "phase1-followups", "what we did today" notes, anything that reads like a diary rather than a durable fact.
- **Delete the contradicted** - verify any `file:line`, flag, or code claim against the actual repo; if it no longer holds, cut it.
- **Condense verbose bodies HARD** to the single durable fact in 1-5 dense lines. Strip examples, restated context, and narration; keep `**Why:**` / `**How to apply:**` for feedback/project only when they carry real signal. A body over ~120 tokens almost always has cuttable verbosity - aim for the fact, not the story. A well-condensed store lands near 1-3K tokens total, not 10K+; if you only cut ~half, you stopped at pruning and skipped condensing.
- **Fold small always-relevant memories into the index.** If a memory is short and used every session (build/test commands, operating rules, hard constraints), put it directly in `MEMORY.md` as a dense bullet rather than a separate file - fewer files, and it should always load anyway. Keep separate files for larger or topic-specific facts that genuinely benefit from recall-on-demand.
- **Never delete a durable `user` or `feedback` fact** (who the human is, how they want you to work). Those are the highest-value, lowest-churn memories.
- `project` memories: keep only if the work is ongoing; archive/delete when shipped. `reference`: keep only if the pointer is still live.

## 5. Rebuild the index

Rewrite `MEMORY.md` so it is **one line per surviving memory** (`- [Title](file.md) - hook`), grouped by type. The index is loaded every session; keep it lean. No memory bodies in the index.

## 6. Report

State: files before -> after, tokens before -> after, what was merged, what was deleted and why. Do not touch anything outside the memory directory.

## Failure modes worth naming

- Deleting a durable user/feedback fact because it looked redundant. When unsure, keep and merge, do not delete.
- Leaving the index fat - the whole point is to shrink what loads every session; an un-rebuilt `MEMORY.md` defeats it.
- Trusting a stale `file:line` claim instead of checking the repo.
