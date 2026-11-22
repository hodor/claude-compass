---
title: "Which part of the session-start prefix breaks cache reuse between sessions, isolated by controlled launches"
type: research
status: complete
confidence: medium
area: tooling
tags: [research, prompt-caching, session-start, git-status, measurement, claude-code]
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "6faced1"
author: researcher
summary: "Controlled claude -p pairs on host 2.1.330: a changed git-status path set, auto-memory index, project CLAUDE.md or rule file each cut the first-request read to the prefix before it; skills do not; 89% of comparable consecutive sessions here differ first at the snapshot; turning the snapshot off held a full read"
depends_on: ["[[SPEC-033-prompt-cache-is-a-design-input]]", "[[RESEARCH-cache-hit-baseline]]", "[[RESEARCH-session-start-prefix]]"]
---

# Prefix break, isolated

From [[SPEC-033-prompt-cache-is-a-design-input]]. Closes the gap left by [[RESEARCH-cache-hit-baseline]] finding 5 and [[RESEARCH-session-start-prefix]] findings 7 and 7a.

### Question
Which part of the session-start prefix breaks cache reuse between consecutive sessions, and which part does Compass own?

### Methodology
Technology landscape / comparative evaluation in DESMET's case-study mode: controlled pairs of headless launches changing one factor, plus a diff of the host's own request records (feature analysis by tool trial). It fits "which of several candidate factors" better than mining because the history confounds launches.

Grading allowed by the brief. Marks on every finding: measured local telemetry; not retracted; not a preprint; 0 citations; one host version (2.1.330) and one machine. Numbers are first-request `usage` from `claude -p --output-format json` and agree with the per-request records in the transcript.

### Findings

1. **The request is a prefix chain; a change at any block rewrites every block after it and leaves the blocks before it read.** (confidence: high)
   In the recorded first request the order is: system block 0 (62 chars), system block 1 (about 9,700 chars), tool definitions, user message block 0 (every instruction file plus the auto-memory index), block 1 (user email, git-status snapshot), block 2 (attribution), block 3 (the prompt), then a system-role message (about 46,000 chars: environment, deferred-tool and MCP/agent/skill listings). Breakpoints (1h TTL) sit on both system blocks and on the prompt block.
   - Controlled run, same prompt, nothing changed between runs: read 14,459, write 0, twice. Cost per run about 0.00015 USD against 0.0008 when the read breaks.
   - Marks: measured; one host; single machine
   - Grade: high (direct trial, repeated)

2. **A changed git-status snapshot alone breaks reuse after the instruction block: read fell from 14.46k to 8.85k and 5.6k tokens were rewritten, every time, in 3 of 3 changes.** (confidence: high)
   Adding an untracked file, then modifying a tracked file, each changed only the `Status:` lines of block 1 (954 to 958 characters; every other block byte-identical, params and tool shape hash equal). A repeat with the same status read the full 14.46k. The system prefix (5.8k) plus instruction block (3.0k) stayed read; the snapshot block, the system-role message with listings, and the prompt were rewritten.
   - Block-level diff of two consecutive requests, only difference the `Status:` lines.
   - Marks: measured; n=3 changes, 3 repeats; single source
   - Grade: high

3. **A changed auto-memory index (MEMORY.md) breaks reuse the same way: read 14.46k to 8.85k, 5.8k rewritten; adding and editing each did it, and the repeat read in full.** (confidence: high)
   The index text sits in user block 0, so everything after it (snapshot, listings, prompt) is rewritten. The user's own MEMORY.md is a host feature Compass does not write.
   - Marks: measured; n=2 changes; single source
   - Grade: high

4. **Adding a skill did not change the cached prefix: read stayed 14.46k, write 0, and the skill appeared in the recorded request.** (confidence: medium)
   The skill listing reaches the request behind the last breakpoint, so its arrival is uncached but does not invalidate earlier blocks. This matches the docs' "skills append as conversation messages".
   - Marks: measured; n=1 skill added; single source
   - Grade: medium

5. **Scratch directories inside a session scratchpad load no project CLAUDE.md, rules or local CLAUDE.md; the debug log states "not loading ... it is in a session's scratchpad".** (confidence: high)
   So in the earlier trial ([[RESEARCH-session-start-prefix]] 7a) the 14,882-character "instruction block" was the user-level files, not the scratch project's CLAUDE.md, and its 3,023-token extra read is the user-level instruction block, not a project block. Project CLAUDE.md and rule trials need a directory outside any scratchpad.
   - Debug log of a launch in a scratchpad directory (`[CLAUDE.md] not loading ...`); instruction attachment lists only user-level files
   - Marks: measured; single source
   - Grade: high (host's own log)

6. **Outside a scratchpad, editing the project CLAUDE.md or adding or editing a rule file each breaks reuse at the start of the project-instruction text: read 24.0k to 8.8k, 15.1k to 15.2k rewritten; the repeat read in full.** (confidence: high)
   Second scratch repo outside any scratchpad, the host loaded the project CLAUDE.md and `.claude/rules`. Order of reads: base 23,923; after CLAUDE.md edit 8,800 (system 5,827 plus the user-level instruction block 2,973 stay read); after a rule added 8,800; after the rule edited 8,800. Each repeat 23.9k-24.0k.
   - Marks: measured; n=3 changes with repeats, haiku; single source
   - Grade: high

7. **The snapshot lists file paths and status letters, not file contents: changing the set of listed paths breaks reuse, editing an already-listed file again does not.** (confidence: high)
   A tracked vault file modified once changed the snapshot (read 8,800, 15.2k rewritten). A second content edit of the same file left `M path` unchanged: read 24,023, write 0, twice. A new untracked file changed it again each time it was tried, on both haiku and the larger model.
   - Marks: measured; several snapshot changes, 2 no-change edits; single source
   - Grade: high

8. **Turning the snapshot off holds the full read through snapshot-changing events: with `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS=1` and 2 new untracked files in turn, read stayed 23,407, write 0.** (confidence: high)
   The first launch after the switch reads 0 and writes 23.4k, because the Bash tool description (part of the tool block) loses its commit and PR instructions, which changes the tool block ahead of everything. That is a one-time cost per switch, then the prefix no longer depends on repository state.
   - Marks: measured; n=1 switch, 3 launches; single source
   - Grade: high

9. **`--exclude-dynamic-system-prompt-sections` does not protect the prefix: after it moved cwd, environment and git status out of the system prompt, a new untracked file still dropped the read from 23,974 to 7,976.** (confidence: high)
   The flag changes the layout (first launch read 5,827, wrote 18,147) but the git status stays in the user turn ahead of the cached text.
   - Marks: measured; n=1; single source
   - Grade: medium (one change event)

10. **The MCP server set changes the prefix from where MCP text sits in the request: with the same snapshot, a launch without MCP servers read 21,650 of the 24,068 cached by a launch with them, and a launch with them read it all again.** (confidence: medium)
    So adding or removing servers costs only the part after their text, about 2,400 tokens here with the user's servers; the server set is stable across consecutive sessions unless it is changed. A user-level server created an untracked `.serena/` folder on the first launch in a new directory (the first launch's snapshot read `(clean)`, later ones listed the folder), a one-time snapshot change per directory.
    - Marks: measured; n=1 set change; single source
    - Grade: medium

11. **A larger model shows the same break: on sonnet the full read is 42.0k; a new untracked file dropped it to 8.0k and rewrote 34.0k.** (confidence: high)
    The first launch after a model switch wrote 36.2k and read the 5.8k system prefix; a model change is a documented invalidator and the transcript records model and beta strings in the request parameters.
    - Marks: measured; n=1 event; single source
    - Grade: high

12. **Real consecutive sessions differ first at the snapshot in 89% of comparable pairs in this project's history and 59% in others.** (confidence: medium)
    Of 224 consecutive pairs in this project's local transcripts, 79 differ in model or request parameters and 7 in system prompt or tools, leaving 138 comparable (same parameters, system, tools). The first differing block of the 138: git snapshot 123 (89%), the pipeline rule file 7, environment system-role message 5, MEMORY.md 2, none 1. Other projects (449 pairs; 193 comparable): snapshot 113 (59%), MEMORY.md 27 (14%), environment message 22, other instruction files 14, none 17; 166 pairs differ in system prompt or tools and 90 in parameters. The prompt text, which holds the last breakpoint, is excluded from "first differing block".
    - Marks: measured over local transcripts; aggregate only; first-request read values not recoverable per pair in this pass
    - Grade: medium
    - Aggregate scripted over transcript request records; not in the repo

13. **Heterogeneous launches in a project history, not a single factor, make "consecutive session" comparisons noisy.** (confidence: medium)
    Of 224 pairs in this project, 35% change model or request parameters (3 parameter sets; sonnet, haiku, opus, one with a beta header added) and 5 distinct system-prompt variants appear in 60 sessions, with model, tool and prompt differences between interactive and headless launches. Any pair crossing a model or system-prompt change reads only the part before it, regardless of the snapshot.
    - Marks: measured; aggregate
    - Grade: medium

### Which part Compass owns

- Snapshot path set: owned in effect. Compass's sync and capture hooks rewrite vault files that are tracked (`index.md`, `active.md`, `meta/*.yaml`, lesson indexes), so `M` lines appear after the first write of a session; archive logs and new documents add `??` lines. The listing is a host feature; the paths in it come from Compass's vault layout.
- Project CLAUDE.md and rule files: Compass owns the rule files it installs and `self-update` rewrites; in this project's history a rule file differed first in 7 of 138 comparable pairs.
- Auto-memory MEMORY.md, model, system-prompt variant, MCP set: owned by the user or the launcher, not by the plugin (a loop launcher chooses a model and prompt for its workers).
- Skills, agent and plugin listings: no break measured (finding 4).

### Contradictions
- [[RESEARCH-session-start-prefix]] 7a read the extra 3,023 tokens as the project CLAUDE.md block; finding 5 shows that block was user-level files and the project file was never loaded.
- [[RESEARCH-session-start-prefix]] finding 7 reports the same median 7,800 read when the snapshot matched; finding 13 here shows many of those consecutive pairs crossed a model or system-prompt change, which would also stop reuse at the system prefix.

### Gaps
- Interactive versus `-p` launch, the beta-header set and the date or environment announcement were not isolated: the harness cannot start an interactive session, and the date line was not changed between launches.
- Plugin and agent listing changes were not trialled (the skill listing alone was).
- Per-pair first-request reads in the real history could not be recovered with the script used, so the "first differing block" shares in finding 12 are not tied to measured reads.
- Controlled trials use small scratch projects (24k-42k tokens); the 28k-35k tokens a real session writes are larger, so the break-point positions are the transferable result, not the token counts.
- Whether any Compass agent or skill reads the snapshot's branch line (the cost of turning it off) was not checked here.
