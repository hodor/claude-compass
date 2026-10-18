---
title: "Loop: {{name}}"
type: loop
status: draft
area: workflow
tags: [loop]
created: {{date}}
updated: {{date}}
summary: "Draft control loop {{name}}: describe the end state it drives the project toward."
---

# Loop: {{name}}

Answer each section in a sentence or two, then bring the parts to life: `loop.json`, `actuator.md`, `golden/` and `feedback.md` hold the machine form of these choices. Run `compass loop activate {{id}}` once every part has been tried by hand and the sensor reads correctly.

## Step 0: End state

What is true of the project when this loop is finished? Name it as something a reader could check, for example "no file imports the legacy client".

## Step 1: Sensor

What command measures the gap between the project today and the end state? It prints JSON `{"valid": true, "value": <number>, "items": [<sorted identities>]}`. Which number counts as done (`target`), and does the loop push it `down` or `up`? An item keeps its identity under unrelated edits: a file and the matched text, never a line number.

## Step 2: Stabilize (dampener)

How do you stop the problem from growing while the loop works? Run `compass loop baseline {{id}}` to commit today's items as the baseline, and `compass loop check {{id}}` to list items that are new since. Where does that check run so new violations are caught before they merge?

## Step 3: Controller

How does the loop choose the next small piece of work? `first` takes the first sorted item no unreviewed increment holds. A `controller_command` prints the piece to work on, for example the smallest or the most-failing one. What makes a piece small and low-risk here?

## Step 4: Actuator

Which agent does one piece of work, with which tools and which instructions? Write the instructions in `actuator.md` and the hand-made before/after examples in `golden/`. What should the actuator never touch?

## Step 5: Schedule

What runs `compass loop run {{id}}` and how often? Any scheduler works: a CI schedule, cron, or a person. How is a run's result delivered, for example a branch or a pull request?

## Step 6: Human on the loop

Who reads the increments and how do they steer? `compass loop review {{id}} <run-id> accept|reject --reason "..."` records the verdict, and a reject reason joins `feedback.md`, which every run reads. How often will that review happen?

## Step 7: Flow control

Needed when the loop runs unsupervised, on a schedule with nobody watching, or when a run is expensive, for example one that rents cloud GPUs; a cheap loop you run by hand can keep the defaults in `loop.json`. How much unreviewed work may pile up (`wip_limit`)? How much may the loop spend per day (`daily_budget_usd`) and in total (`total_budget_usd`)? After how many failed, harmful or unproductive runs should it halt and wait for a human?
