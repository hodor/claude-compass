# Sensor calibration

`python .compass/loops/LOOP-001-visual-questions/sensor.py --list` prints every match with its line and state. Calibrated on 2026-10-18 against 34 skills, 13 agent templates and 4 rules: 76 asking points, 0 satisfied (no section yet names `AskUserQuestion` with one question per call; five skills list the tool in `allowed-tools` only).

## Kept (true points)

- Explicit asks: "ask the human which one" (learned), "Block on the reply" (research gate), "Present and wait for approval" (setup), "ask once before overwriting" (setup), "ask whether to force-refresh" (update), "Always confirm before bulk fixes" (vault-health), "only his approval moves files" (consolidate S3).
- Quoted questions: blockquotes ending in `?` (guide, research-codebase, research-papers, setup, vision, retroactive, builder), braindump prompts `> "Tell me everything...` (vision, specs), `**Q1:** "...?"` (retroactive), numbered `**Users:** "...?"` (vision).
- Fenced prompts shown to the human: lines ending in `?` or `? (a / b / c)` (autopilot checkpoint, build report, specs list and batch review, vision merge/split list).
- Headings that are themselves the asking point: "Present for approval" (spec, planner), "When to Stop and Ask" (pipeline rule).
- Agent templates: builder mismatch report, planner existing-plan check, researcher missing spec, reviewer partial/divergent, validator missing baseline.

## Dropped (false positives)

22 matches dropped by exclusions:

- Negations: "Do not ask the human which hosts" (setup), "don't stop and ask" (setup).
- Not the human: "For each Need, ask how it would be met" (research, the agent asks itself), "things the asker didn't think to ask" (research-codebase), "They wait for human review" (consolidate, lessons waiting).
- Fenced tool checklists ending in `?` ("Glob: .compass/ - vault exists?", 4 in guide and 4 in setup) and report checkboxes ("- [ ] Create retroactive plan?").
- `plugin/skills/obsidian/SKILL.md` fenced document templates (8 lines such as "What problem does this solve?"), which are prompts for the document author.
- Table rows are skipped outright.
- Plan template text inside a fence ("wait for the human to confirm manual verification" in planner), which is plan content the build skill acts on; build's own "Wait for human confirmation" is kept.

## Known limits

- One section with several matches yields several items; fixing the section clears them all.
- Satisfaction is section-level text: `AskUserQuestion` plus a one-per-call phrase ("one question per call", "exactly one question", "one question at a time", "never batch"), or for agents "return ... orchestrator".
