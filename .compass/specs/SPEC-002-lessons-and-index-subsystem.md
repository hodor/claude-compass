---
title: Lessons & Index Subsystem
type: spec
status: approved
confidence: high
area: methodology
tags: [lessons, index, memory, hooks, dedup, retrospective]
created: 2026-05-24
updated: 2026-05-24
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]", "[[RESEARCH-lessons-and-index-architecture]]"]
---

# Lessons & Index Subsystem

## Problem

The current lessons subsystem produces approximately zero lessons in practice. Evidence: the Compass project's own vault has 0 lesson files and `lessons-catalog.yaml: []` after multiple development sessions. The `index.md` also drifts stale: handoffs and other artifacts get written but the index isn't updated, breaking the "documents not in index.md are invisible to the next session" rule the methodology depends on.

Root causes, identified across the agent templates:

1. **In-flight capture asks the wrong question at the wrong time.** Agents are told "if something surprised you, create a lesson." Mid-task the model doesn't yet know what was important. Asking for introspective surprise produces either nothing (most common) or fabrication.
2. **Lesson creation appears only as the last optional step** in `builder.md`, `validator.md`, `reviewer.md`. Last conditional steps are the first thing dropped under turn-budget pressure.
3. **Three-file ceremony** (lesson file + catalog row + index line) creates friction. Even when an agent decides a lesson is worth writing, the ceremony invites partial completion.
4. **No deduplication.** Nothing prevents two near-identical lessons being written, so the lesson set would degrade into noise even if capture worked.
5. **Index updates rely on per-agent discipline.** No mechanism enforces freshness; agents skip the trailing bullet.

Five reference codebases were investigated (see [[RESEARCH-lessons-and-index-architecture]]). Strong convergence findings:

- Zero of five do per-agent in-flight introspective capture. Compass's current design is an outlier.
- Automation beats agent discipline for both capture and index freshness.
- Pre-write dedup via injected manifest is reliable; post-write similarity scoring is not needed.

## Vision

Lessons get written at a natural retrospective boundary, by an extractor that runs only when objective signals fired, filtered through an anti-list so that "nothing notable happened" produces zero output. The lesson body is free-form and short (5 lines max) so writing is cheap. The index is kept fresh by a reactive sweep that runs on every vault write, eliminating the dependency on per-agent diligence. Long-horizon merging and pruning happens automatically when bloat thresholds are hit, never as routine overhead.

## Desired Outcomes

1. **Lessons get written when they should.** Phases that produced a real surprise (fix-loop, validator deviation, debug invocation, plan revision, STOP-and-report) produce at most one lesson per surprise type. Phases that ran cleanly produce nothing.
2. **Lessons do not get written when they shouldn't.** "Standard patterns," "things obvious once you know the tech," and other anti-list items never appear, even when a binary trigger fired.
3. **Humans can capture in-the-moment lessons** without ceremony, via `/compass:learned <one-line>` that goes through the same writer (dedup + anti-list) as the auto path.
4. **No duplicate lessons accumulate.** Overlap is detected at write time; recurrence bumps a counter on the existing entry instead of creating a new file.
5. **Index and lessons-catalog never go stale between sessions.** A vault write that bypasses the documented path still gets indexed.
6. **Lesson bodies stay readable.** Hard cap of 5 lines per body. Verbose lessons get reshaped during consolidation.
7. **The system self-heals when it bloats.** When `index.md` hits its size cap or `lessons/` exceeds a file-count threshold, consolidation is required before the next session.

## Design Constraints

### Capture timing
Lessons are extracted at **phase boundaries** (the existing pause point in `/compass:build` step 6), never per-turn and never mid-task. Rationale: only after a phase completes does the model have full signal about what was hard, what recurred, and what was redundant.

### Trigger model
Hybrid: a **binary gate** checks whether any of these fired in the just-completed phase:
- Builder fix-loop ran >=2 cycles in any task
- Validator classified a Deviation (problem)
- Debug agent was invoked
- A builder hit STOP-and-report
- The plan was revised mid-phase

If none fired, the extractor does not run. If at least one fired, the extractor runs with **model judgment + anti-list** filtering. It may still write nothing.

### Manual path
The `/compass:learned <one-line>` slash command is the in-the-moment human path. It uses the same writer (dedup manifest + anti-list + writer skill) as the auto extractor.

### Body shape
Free-form markdown, **5 lines maximum**. No enforced template. Authors write whatever shape best communicates the lesson within the cap.

### Frontmatter
Required: `name`, `description`, `status` (active|archived), `category` (process|domain), `area`, `tags`, `score` (1-10, default 5), `summary`. Optional: `seen: [dates]` (added when extractor detects recurrence).

### Anti-list (the filter that does the real work)
Adapted from `hodor/ccode`. The extractor and `/compass:learned` writer reject content that falls in any of these buckets:

- Code patterns, conventions, architecture, file paths, project structure (readable from the codebase)
- Git history or recent changes (git log and git blame are authoritative)
- Debugging recipes whose fix is in the code (commit message is the right home)
- Anything already documented in a spec, ADR, plan, vision, or CLAUDE.md
- Standard patterns from framework or library official docs
- Personal style preferences
- Things obvious once you know the technology
- Ephemeral session state (handoffs are the right home)

**These exclusions apply even when the user explicitly says to save.** Adapted verbatim from `memdir/memoryTypes.ts:183-195` in the `hodor/ccode` reference.

### Dedup mechanics
Before any write, the writer is given a **pre-injected manifest** of all existing lessons:

```
- LESSON-foo.md (process / workflow, score 8): YAML values with colons must be quoted
- LESSON-bar.md (domain / backend, score 5): Users need batch export not single-file
```

The writer judges overlap and takes one of three actions:
- **Pure recurrence** (same rule, new instance): bump `score` by +1, append today's date to `seen: [...]`, body unchanged
- **Refinement** (rule generalizes or adds nuance): edit body in place, still bounded by 5-line cap
- **Genuinely new rule**: create new file, append catalog row, append index line

### Invocation
**Primary path:** the `/compass:build` skill calls the extractor as a step at the phase pause (current build skill step 6 / 7).

**Backstop path:** a `Stop` hook also fires the extractor when the main agent ends a turn, in case work bypassed `/compass:build`. The two paths use a mutex (matching `hodor`'s `extractMemories.ts:121-148` pattern) so a single phase produces at most one extraction attempt.

### Index and catalog freshness
A `PostToolUse` hook fires `index-sync` whenever a tool writes to `.compass/**/*.md`. The hook filter excludes:
- `tmp/`, `meta/`, `.annotations/` directories
- `index.md` and `lessons-catalog.yaml` themselves (prevents the sync looping on its own writes)

`index-sync` is pure mechanical: glob the vault, read frontmatter `type`, diff against `index.md` sections, auto-append missing entries with format `- [[NAME]] - <description from frontmatter>`. For `lessons/*.md` files, also verify each has a `lessons-catalog.yaml` row; append defaults if missing.

### Hard caps with self-warning
- `index.md`: 200 lines or 25 KB, whichever first.
- `lessons-catalog.yaml`: 200 lines or 25 KB.
- `lessons/` directory: 50 files.

On cap hit, the loader writes `<!-- WARNING: cap exceeded, run /compass:consolidate before next session -->` into the relevant file. Agents reading that file in subsequent sessions see the warning and surface it. Matches `hodor`'s `memdir/memdir.ts:35-103` self-healing pattern.

### Consolidation
The `/compass:consolidate` command runs **only on bloat trigger**: when any cap above has been hit since the last consolidation. There is no fixed cadence. The pass:

- Merges near-duplicates that pre-write dedup missed
- Rewrites verbose lesson bodies to fit the 5-line cap
- Archives lessons whose `score` stayed at 5 (baseline, never reinforced) after N sessions
- Trims old `seen: [...]` dates beyond a retention window
- Rebuilds `lessons-catalog.yaml` from the resulting set
- Rebuilds the `## Lessons` section of `index.md`

## Success Criteria

1. After a development session that hit at least one binary trigger, at least one lesson is written (or, if the anti-list filtered it out, that filtering is auditable in the extractor's report).
2. After 10 sessions, the lessons-catalog has no two entries that the extractor would judge as duplicates (verifiable by re-running dedup judgment over the catalog).
3. At session start, every `.md` file in `.compass/specs|plans|research|decisions|lessons|handoffs/` is linked from `index.md`. No orphans.
4. No lesson file exceeds 5 lines of body content.
5. When any cap is exceeded, the next session surfaces the warning before any other work proceeds.

## Non-Goals

- Embedding-based similarity scoring for dedup. Pre-write manifest + model judgment is sufficient.
- Lesson versioning or history. Git already provides this for the file; in-file changelog is bloat.
- Cross-project lesson sharing. Each project's vault is independent for this iteration.
- Automatic consolidation on cadence. Bloat-only trigger keeps cost zero in low-usage projects.
- Per-agent in-flight capture in any form. Removed deliberately.

## Risks

- **Hook reliability.** The whole architecture leans on `Stop` and `PostToolUse` hooks firing. If a Claude Code install has hooks disabled or hooks misfire, the primary `/compass:build` skill-step path keeps lessons working; index sync would regress to manual. Mitigation: document hook setup as part of `/compass:bootstrap`; add a `/compass:vault-health` check that verifies index freshness.
- **Anti-list does too much filtering.** If the anti-list is too aggressive, the extractor writes nothing even when it should. Mitigation: the extractor's report logs what it considered and rejected, so misses are auditable and the anti-list is tunable.
- **Score field still goes unmaintained.** Score gets bumped on recurrence detection, but isolated lessons stay at 5 forever. Mitigation: this is intentional. Score signals recurrence, not authored importance.

## Open Questions

- Should the extractor's "considered but rejected" log be persisted, and if so where? (Proposed: `.compass/tmp/extraction-log-YYYY-MM-DD.md`, retained 30 days.)
- Should `/compass:learned` accept a category hint (e.g. `/compass:learned --domain "users need batch export"`), or always infer from content?
- What is the retention window for `seen: [...]` dates? (Proposed: keep last 10 entries.)

## What to delete from the current design

When the implementing plan executes, the following must be removed:

- `builder.md` step 10: "Create a lesson in `.compass/lessons/` if something surprised you. Append to `lessons-catalog.yaml`. Add to `index.md` under `## Lessons`."
- `builder.md` step 12: "Lesson feedback" entirely.
- `validator.md` step 10: "Lessons and annotations" - keep annotations, remove lesson creation.
- `reviewer.md` step 7: "If you noticed a systematic pattern across agents... create a lesson."
- `debug.md` "Related Lessons" stays (it's read-only), but no lesson-creation language is added.
- `builder.md` step 10 line: "Every new vault document must be linked in `index.md` in the same step." This rule is no longer load-bearing; the PostToolUse hook handles it.
- `lessons/SKILL.md` sections "When to create," "Catalog update protocol," "Score adjustment" - all replaced by the writer skill the extractor and `/compass:learned` both call.
