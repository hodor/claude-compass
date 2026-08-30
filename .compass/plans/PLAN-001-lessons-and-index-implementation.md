---
title: Lessons & Index Implementation
type: plan
status: done
confidence: high
area: methodology
tags: [lessons, index, hooks, skills, dedup]
created: 2026-05-24
updated: 2026-05-24
completed: 2026-05-24
depends_on: ["[[SPEC-002-lessons-and-index-subsystem]]", "[[RESEARCH-lessons-and-index-architecture]]"]
summary: "12 tasks across 6 phases implementing SPEC-002 (done 2026-05-24)"
---

# Lessons & Index Implementation

## Goal

Replace per-agent in-flight lesson capture with retrospective phase-boundary extraction + manual `/compass:learned`, automate index freshness via PostToolUse hook, and add bloat-triggered consolidation. Implements [[SPEC-002-lessons-and-index-subsystem]] based on findings from [[RESEARCH-lessons-and-index-architecture]].

## Prerequisites

- SPEC-002 approved (done)
- Hook config convention for Compass plugin TBD - resolved as part of TASK-004

## Desired End State

- 4 new skills: `lesson-write`, `extract-lessons`, `index-sync`, `consolidate`
- 2 new slash commands: `/compass:learned`, `/compass:consolidate`
- 2 hooks: `Stop` (extract-lessons backstop), `PostToolUse` (index-sync + extraction-log cleanup)
- 4 agent templates trimmed (lesson-creation and per-agent index-update removed)
- `lessons/SKILL.md` reduced to search and apply only
- `build/SKILL.md` invokes extract-lessons at phase pause
- SPEC-002 success criteria 1-5 all hold

## What We're NOT Doing

- Embedding-based dedup (manifest + model judgment is sufficient)
- Cross-project lesson sharing
- Per-agent in-flight capture in any form
- Fixed-cadence consolidation (bloat-only trigger)
- Full plugin test harness (mechanical pieces get fixture tests; model-judgment pieces get manual verification scripts)

## Resolved decisions (from spec inherited questions)

1. **Extraction log persistence:** logs go to `.compass/tmp/extraction-log-YYYY-MM-DD.md`, retained 30 days. Cleanup is folded into `index-sync` (glob `tmp/extraction-log-*.md`, delete by mtime). No agent involvement, no extra tokens.
2. **`/compass:learned` category:** accepts `--process` / `--domain` flag. If absent, agent infers using Reinertsen split already documented in `lessons/SKILL.md:10-16` (process = how to build; domain = what to build).
3. **`seen: [...]` retention:** cap at **3 dates**. When a 4th recurrence would be added, the writer instead sets `escalated: <date>` + `escalation_reason: "recurred 3 times despite being captured"` in frontmatter. Escalated lessons surface in hot-path read with a flag prompting human review (lesson is worded too vaguely OR search retrieval is failing). `/compass:consolidate` does not archive escalated lessons. Human clears the flag after reviewing; `seen` resets.

## Phases

### Phase 1 - Foundation

- [ ] TASK-001: Build `lesson-write` skill - complexity: M, depends_on: none, files: [`plugin/skills/lesson-write/SKILL.md`]
 - Inputs: `category` (optional), `area`, `tags`, `summary`, `body` (<=5 lines)
 - Behavior: read `lessons-catalog.yaml`, inject as manifest into reasoning prompt, run 3-branch dedup judgment (recurrence/refinement/new). Recurrence: bump score, append date to `seen` (cap 3 - escalate on 4th). Refinement: edit body (5-line cap). New: write file + catalog row + index line atomically. Anti-list filter applied before any write.
 - Automated verification: fixture test - seed `.compass/` with 3 lessons; invoke with duplicate content, assert score bumped + seen appended; invoke 4 times, assert escalation flag set on 4th; invoke with new content, assert 3-file atomic write; invoke with anti-list-matched content (e.g. "Python list comprehensions are concise"), assert no write
 - Manual verification: invoke against real vault with a borderline duplicate, confirm extractor judgment is reasonable

- [ ] TASK-002: Trim `lessons/SKILL.md` - complexity: S, depends_on: TASK-001, files: [`plugin/skills/lessons/SKILL.md`]
 - Remove: "When to create" section, "Catalog update protocol" section, "Score adjustment" section. Add: pointer to `lesson-write` skill for creation. Keep: "When to search," "Search algorithm," "Catalog" structure description (for readers).
 - Automated verification: grep returns 0 hits for "Catalog update protocol", "Score adjustment", "When to create" headings
 - Manual verification: read end-to-end, confirm coherence

**Phase pause:** wait for human confirmation that Phase 1 outputs meet expectations before Phase 2.

### Phase 2 - Index sync (independent track, can run parallel to Phase 1)

- [ ] TASK-003: Build `index-sync` skill - complexity: M, depends_on: none, files: [`plugin/skills/index-sync/SKILL.md`]
 - Behavior: glob `.compass/**/*.md` excluding `tmp/`, `meta/`, `.annotations/`. Read frontmatter `type` for each. Diff against `index.md` section for that type. Append missing entries as `- [[NAME]] - <description from frontmatter>`. For `lessons/*.md` also verify `lessons-catalog.yaml` has a row; append defaults if missing. Final step: glob `.compass/tmp/extraction-log-*.md`, delete files with mtime older than 30 days.
 - Automated verification: fixture with 2 orphan files - run sync - assert both linked in `index.md`. Fixture with 35-day-old extraction log - run sync - assert deleted.
 - Manual verification: run against the real `.compass/handoffs/` (one handoff was missing from index per earlier investigation), confirm auto-added without disturbing existing entries

- [ ] TASK-004: Configure PostToolUse hook + decide hook config location - complexity: M, depends_on: TASK-003, files: [hook config file - location TBD]
 - First: spike to decide where Compass plugin hooks are configured (check Claude Code plugin docs; likely `plugin/.claude-plugin/hooks.json` or similar). Document the decision in TASK-004's notes.
 - Hook: matcher fires on `Write` or `Edit` tools when target path matches `.compass/**/*.md`, excluding `index.md`, `lessons-catalog.yaml`, `tmp/`, `meta/`, `.annotations/`. Action: invoke `index-sync` skill.
 - Automated verification: write a `.compass/decisions/ADR-test.md`, confirm `index.md` gets the link within one turn. Write to `index.md` itself, confirm hook does NOT fire (no loop).
 - Manual verification: write via Edit (not Write), confirm same behavior

**Phase pause.**

### Phase 3 - Manual capture path

- [ ] TASK-005: Build `/compass:learned` slash command skill - complexity: S, depends_on: TASK-001, files: [`plugin/skills/learned/SKILL.md`]
 - Argument: one-line lesson content, optional `--process` / `--domain` flag.
 - Behavior: parse argument. If category flag given, use it. Else infer via Reinertsen split (the content describes a build technique = process; describes a user/business reality = domain). Construct lesson payload, call `lesson-write`. If `lesson-write` returns ambiguity (e.g. category unclear, summary too long), interactive fallback: ask the user one question.
 - Automated verification: invoke `/compass:learned --process "test about X"`, assert lesson written with category=process. Invoke without flag with clear process content, assert correct inference.
 - Manual verification: invoke with ambiguous content, confirm interactive fallback works

**Phase pause.**

### Phase 4 - Auto-extraction

- [ ] TASK-006: Build `extract-lessons` skill - complexity: L, depends_on: TASK-001, files: [`plugin/skills/extract-lessons/SKILL.md`]
 - Inputs: phase artifact set (build reports, test reports, validator report, plan deviation log).
 - Binary trigger check: any of {fix-loop >=2 in any task, validator Deviation problem, debug agent invoked, STOP-and-report fired, plan revised mid-phase}? If none, exit silently.
 - If at least one trigger: scan artifacts for candidate findings. Apply anti-list to each. Survivors go through `lesson-write`. Write a record of all considered + rejected candidates to `.compass/tmp/extraction-log-YYYY-MM-DD.md` (one entry per candidate: source artifact, the finding, whether written/rejected, reason).
 - Automated verification: synthetic phase with fix-loop=3, assert extractor runs and writes >=1 lesson + extraction-log entry. Synthetic clean phase, assert extractor runs but writes nothing + extraction-log records "no triggers fired". Synthetic phase with trigger fired but only anti-list-matched candidates, assert no lessons written but log shows rejected candidates with reasons.
 - Manual verification: run on a real completed phase, audit extraction log against the anti-list

- [ ] TASK-007: Modify `build/SKILL.md` to invoke extract-lessons at phase pause - complexity: S, depends_on: TASK-006, files: [`plugin/skills/build/SKILL.md`]
 - Insert extract-lessons invocation between "all phase tasks done + post-merge tester passed" and the human-verification pause. Extractor runs in the same context, lessons are available for human to review during the pause.
 - Automated verification: diff shows the invocation added in the right place
 - Manual verification: run a full `/compass:build` cycle, confirm extraction fires at the right moment

- [ ] TASK-008: Configure Stop hook backstop for extract-lessons - complexity: S, depends_on: TASK-006 TASK-004, files: [hook config file from TASK-004]
 - Hook: on `Stop` of main agent, check `active.md` for "phase just completed" marker (a marker the build skill must also write). If present and no extract-lessons run recorded for this phase (mutex via `.compass/tmp/phase-extract-marker-<phase-id>`), invoke extract-lessons.
 - Automated verification: simulate phase-complete turn outside `/compass:build`, confirm extraction fires. Run `/compass:build` to completion, confirm Stop hook sees the mutex marker and skips.
 - Manual verification: trigger both paths in sequence, confirm exactly one extraction per phase

**Phase pause.**

### Phase 5 - Cleanup of old design

- [ ] TASK-009: Remove lesson-creation language from 4 agent templates - complexity: S, depends_on: TASK-006, files: [`plugin/templates/agents/builder.md`, `validator.md`, `reviewer.md`, `debug.md`]
 - `builder.md`: delete step 10 "Create a lesson..." bullet and step 12 "Lesson feedback" entirely. Keep step 10's other bullets (active.md/plan checkoffs, ADR creation, annotations).
 - `validator.md`: delete the "Create a lesson" sentence in step 10. Keep annotations.
 - `reviewer.md`: delete step 7 "If you noticed a systematic pattern..." lesson-creation bullet. Keep annotations.
 - `debug.md`: no changes needed (already read-only, only references existing lessons).
 - Automated verification: grep `"create a lesson"`, `"if something surprised"`, `"Lesson feedback"` returns 0 hits across the 4 files
 - Manual verification: read each agent's protocol, confirm coherence

- [ ] TASK-010: Remove per-agent index-update instructions - complexity: S, depends_on: TASK-004, files: [`plugin/templates/agents/builder.md`, `planner.md`, `researcher.md`, `reviewer.md`, `validator.md`]
 - Delete bullets like "add to `index.md` under `## Decisions`", "Add to `index.md` under `## Research`", "Documents not in index.md are invisible to the next session" sentences. Replace with one sentence: "Vault sync is automatic via the PostToolUse hook."
 - Automated verification: grep `"add to.*index.md"`, `"Documents not in index.md"` returns 0 hits in agent files
 - Manual verification: read each agent end-to-end, confirm no orphan references

**Phase pause.**

### Phase 6 - Self-healing

- [ ] TASK-011: Hard-cap detection with self-warning - complexity: M, depends_on: TASK-003, files: [`plugin/skills/index-sync/SKILL.md` (extend), or new `plugin/skills/vault-loader/SKILL.md` if cleaner]
 - On `index-sync` runs, after the sweep: check `index.md` line count and byte size. If exceeded (200 lines OR 25 KB), prepend `<!-- WARNING: index cap exceeded, run /compass:consolidate before next session -->`. Same check for `lessons-catalog.yaml`. Same check for `lessons/` directory file count (50 files); warning written to `lessons-catalog.yaml`.
 - Automated verification: fixture with 201-line `index.md`, run sync, assert warning present at top
 - Manual verification: hit cap on real vault, confirm warning surfaces in next session's hot-path read

- [ ] TASK-012: Build `/compass:consolidate` command skill - complexity: L, depends_on: TASK-001 TASK-011, files: [`plugin/skills/consolidate/SKILL.md`]
 - Pre-check: only runs if a warning is present in `index.md` or `lessons-catalog.yaml` (proves bloat triggered). If no warning, exits with "no consolidation needed."
 - Behavior: load all lessons. Use model judgment to merge near-duplicates the per-phase dedup missed. Rewrite verbose bodies to fit 5-line cap. Archive lessons whose `score` stayed at 5 (baseline, never reinforced) for >=N sessions (N=10 starting). Trim `seen: [...]` to last 3 across all lessons. Do NOT archive escalated lessons; flag them for human review instead. Rebuild `lessons-catalog.yaml` from resulting set. Rebuild `## Lessons` section of `index.md`. Remove warning comments.
 - Automated verification: fixture with 2 near-duplicate lessons, assert merged. Fixture with 7-line body, assert rewritten to <=5 lines. Fixture with score=5 + age>=10 sessions + not escalated, assert archived.
 - Manual verification: run on real bloated vault, audit merge/prune decisions before letting consolidation commit

**Phase pause.**

## Phasing logic

- Phases 1 and 2 are independent (different file sets) - can run parallel.
- Phase 3 depends on Phase 1 (uses `lesson-write`).
- Phase 4 depends on Phases 1 and 3.
- Phase 5 depends on Phase 4 (don't break old design before replacements work).
- Phase 6 depends on everything else.

## Risks

- **Hook config convention unknown:** TASK-004 spikes this. If Compass's hook surface differs from what we assume, Phase 4 (TASK-008) may need rework. Mitigation: do TASK-004 spike before TASK-008.
- **TASK-006 model judgment risk:** the anti-list is load-bearing. First real-world phase extraction will likely surface anti-list gaps. Mitigation: extraction log makes this auditable; plan for one tuning iteration after first use.
- **Bloat triggers may never fire on small projects:** TASK-012 may sit unused. Acceptable - this is a "scales gracefully" property, not a "must use" property.

## Inherited Questions

All resolved in the "Resolved decisions" section above.
