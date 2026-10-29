---
title: "Loop: visual-questions"
type: loop
status: active
area: workflow
tags: [loop, questions, ui, human-gates]
created: 2026-10-19
updated: 2026-10-19
summary: "Control loop for SPEC-029: drives every point where Compass asks the human something to one AskUserQuestion call per question."
---

# Loop: visual-questions

Serves [[SPEC-029-questions-to-the-human-are-clear-and-visual]]. `loop.json`, `actuator.md`, `golden/` and `feedback.md` hold the machine form of the choices below; `sensor-notes.md` records how the sensor was calibrated.

## Step 0: End state

Every point in the shipped skills, agent templates and rules where the agent asks the human something tells the agent to ask through `AskUserQuestion`, one question per call, with the recommended option first. An agent template returns its question to the orchestrator, which asks it.

## Step 1: Sensor

`python .compass/loops/LOOP-001-visual-questions/sensor.py` scans `plugin/skills/*/SKILL.md`, `plugin/templates/agents/*.md` and `plugin/templates/rules/*.md` for asking points (phrases such as "ask the human", "Approve?", "Block on the reply", quoted questions in blockquotes and fenced prompts). A point is satisfied when its section, from its heading to the next heading of the same or higher level, names `AskUserQuestion` with one question per call, or, in an agent template, returns the question to the orchestrator. The value is the count of unsatisfied points; `target` 0, direction `down`. Item identity is `<path>:<heading>:<matched text, 80 chars>`. `--list` prints every match with its line and state.

## Step 2: Stabilize (dampener)

`compass loop baseline LOOP-001` records today's items; `compass loop check LOOP-001` lists asking points added since, run by hand after editing a skill or template.

## Step 3: Controller

`first`: the first sorted item no unreviewed increment holds. One item is one section of one file, a few sentences of prose.

## Step 4: Actuator

Sonnet with Read, Edit, Glob and Grep, following `actuator.md` and `golden/one-question-through-the-ui.md`. It edits only the selected section of the selected file, plus the skill's `allowed-tools` line, and never changes what is asked or what an answer leads to.

## Step 5: Schedule

Run by hand while the human watches; no schedule.

## Step 6: Human on the loop

The human reviews each increment right after the run with `compass loop review LOOP-001 <run-id> accept|reject --reason "..."`; a reject reason joins `feedback.md`.

## Step 7: Flow control

At most 2 unreviewed increments, $0.40 per run, $2 per day, $5 in total; the halt limits keep their defaults (3 actuator failures, 2 harmful runs, 5 runs without progress).
