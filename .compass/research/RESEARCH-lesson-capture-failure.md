---
title: Why Lesson Capture Almost Never Happens (40-Vault Fleet Diagnosis)
type: research
status: complete
confidence: high
area: methodology
tags: [lessons, capture, diagnosis, fleet-audit, build-skill, triggers, install-drift]
created: 2026-07-26
updated: 2026-07-26
depends_on: ["[[SPEC-002-lessons-and-index-subsystem]]", "[[ADR-002-retrospective-lessons-subsystem]]"]
summary: "why capture almost never happens (40-vault diagnosis)"
---

## Question

Roger's observation: "Compass is REALLY BAD at capturing lessons - it almost never happens." Verified against every `.compass` vault on F:. Is it true, and what is the root cause?

## Methodology

Two independent read-only investigations over the full fleet: a mechanism audit scripting checks across all 40 vaults (install state, hook presence, phase-report/audit-log traces, catalog consistency), and forensics on the two high-lesson outliers plus four heavy-usage zero-lesson vaults (formats, git dates, creation routes). Other projects' vaults were treated as read-only fixtures throughout.

## Headline finding

Confirmed, decisively. Across 40 vaults, the designed automatic capture path has fired organically **exactly once, ever** (ai-songwriting, 2026-07-25). When it fired, it worked flawlessly: phase-summary written, STOP-and-report trigger detected, 5/5 candidates through the anti-list, 5 canonical lessons with matching catalog rows. **The mechanism is correct; its trigger point is unreachable.** Capture is wired exclusively to `/compass:build` phase boundaries, and real sessions almost never cross one.

## Findings

1. **The fleet numbers (HIGH).** 40 vaults; 26 (65%) hold zero lessons; ~153 lesson-shaped files total, 87 (57%) in two outlier vaults. Heavily-used vaults capture nothing: product-owner (12 specs, 6 handoffs, 0), pg-cinematics-pipeline (16 specs, 0), storylab (12 specs, v0.4.0 installed 2026-07-24, 0), cure-pancreas (277 files, 0), iwyc-unreal (196 files, 50 specs, 26 handoffs, 2).

2. **Neither outlier used the system (HIGH).** ue5-editor-mcp (54): bulk migration of a pre-Compass `ai/discoveries/` folder (`migrated_from:` frontmatter, dated 2026-05-24), extended by hand in the legacy schema; had the compliant mechanism installed for weeks during heavy crash-debugging and produced zero mechanism-originated lessons. ae-postvis-ai (33): a homegrown numbered `LESSON-NNN` prose template running ~3.5 months, with `## Surprise` headers from the pre-ADR-002 design; compliant tooling arrived the day of its newest lesson.

3. **Exactly one organic firing, and it proves the pipeline (HIGH).** ai-songwriting: `phase-summary.yaml` -> `extraction-log-2026-07-25.md` (5 candidates, all passed, all created) -> 5 canonical lessons -> catalog in sync. The dogfood repo's only phase-report is a synthetic `TEST-PLAN` dry-run from the subsystem's own construction day.

4. **Root cause: the trigger point, not the triggers (HIGH).** Literal `/compass:build` appears in the vault docs of 1/40 projects (the dogfood repo, referencing itself). Fleet-wide subagent captures show researcher/planner/reviewer activity but essentially zero builder/tester captures - sessions run Vision/Spec/Research/Plan with Compass, then implement conversationally, outside the only workflow where capture fires. "Triggers too strict" is falsified: no rejection logs exist anywhere because phase-summary.yaml almost never gets created; the bottleneck is entirely upstream of the trigger check.

5. **Contributing cause: install drift (HIGH).** 19/40 vaults categorically cannot run the Stop-hook backstop (13 have no plugin.yaml; 3 v0.2.0 installs have skills but no hooks dir; assorted partials). 21/40 have everything installed and still show zero firings. The backstop also only fires when a phase-summary exists - so it inherits the same upstream gate.

6. **Contributing cause: bypass routes and schema drift (HIGH).** Where canonical-format lessons exist outside the dogfood (internal-plugins, wt-spec056, recruiting, snooker-bot), they trace to manual `/compass:learned`, not auto-extraction. The outliers' bespoke schemas produce catalog mismatches (ue5's catalog rows point at `domain/*.md` files; ae-postvis-ai's numbered files violate the 5-line cap and lack required fields).

7. **The historical irony (HIGH).** ADR-002's redesign was motivated by "0 lessons after 3 months" under prose-based capture. The redesign moved capture to a phase boundary real work does not visit; the failure mode changed from "agents never bother" to "the trigger never fires." Same outcome. This very session repeated the pattern: the v0.4.0 build ran research -> ADRs -> plans -> builders -> validator orchestrated conversationally, and its two lessons had to be written manually.

## Root-cause statement

Lesson capture fails because it is coupled to a single rare event (the `/compass:build` phase pause) rather than to the events that actually occur in real sessions (session end/handoff, validation completion, debugging resolution, conversational build waves). Install drift and bypass schemas are secondary compounders. The extraction/dedup/anti-list core is proven good and should be preserved; the trigger topology must change.

## Implications for the learning-loop work

- Capture must attach to events that demonstrably happen: the audit's trace data shows handoffs (26 per heavy vault) and research/plan activity are frequent; phase pauses are not.
- The Stop-hook backstop needs a trigger source that exists without `/compass:build` (it currently keys on phase-summary.yaml).
- Retrieval/application investment (graph queries, coverage-style lesson audit) is worthless until capture produces input; sequence capture-fix first.
- Fleet install drift argues for `compass doctor`-style verification in update/checkup, and the distribution pass should reconcile versions.
- The one organic firing is the falsification benchmark: any redesign must keep its quality (binary triggers, anti-list, 5-line canonical output) while multiplying its opportunities to run.

## Gaps

- No positive evidence yet on whether looser trigger points would preserve precision (the anti-list has only one real-world exercise).
- Windows-only fleet, one user's workflow; other users' build-skill usage rates unknown.

## Sources

Full per-vault table and raw outputs: scratchpad `audit.sh`, `audit_table.tsv`, `audit_detail.txt`, `subagent_captures_report.txt` (session-temporary). Key evidence files: `F:\AI\_Tools\ai-songwriting\.compass\tmp\extraction-log-2026-07-25.md` (the one organic firing); `F:\Heirloom\iwyc-unreal\Plugins\ue5-editor-mcp\.compass\lessons\_overview.md` (migration marker); `F:\Halon\AI\ae-postvis-ai\.compass\lessons\` (bespoke template); [[ADR-002-retrospective-lessons-subsystem]] (the prior diagnosis this one supersedes in scope).
