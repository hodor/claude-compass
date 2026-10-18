---
title: "Control Theory for Compass Loops"
type: spec
status: approved
confidence: low
area: pipeline
tags: [loops, control-theory, feedback, sensors, incremental-change]
summary: "Compass loops, its own and the ones it builds for users' tasks, measure something, apply changes incrementally, and get feedback on the quality of those changes, so they stay stable amid disturbances and remain steerable"
created: 2026-10-17
updated: 2026-10-18
approved: 2026-10-17
---

# Control Theory for Compass Loops

## Problem

We want to add control theory to our loops. We need to ensure that we drive incremental change amid disturbances, that we maintain system stability, that it's incremental and low-risk, and that it's feedback-driven and steerable.

The main thing is we find something we can measure: can we apply changes incrementally, and can we get feedback on the quality of those changes?

## Desired Outcome

Compass loops have a sensor. The sensor could be deterministic: the amount of calls that it took, how many tokens and how much money we are spending, how long it took. It can also be non-deterministic, like an agent, a skill, and a bunch of natural language rules.

Compass has features that can create those control loops for the tasks of the users. Imagine a user trying to make an animation out of Maya: this can be done through our new loop system.

### How a control loop gets made

HumanLayer's example of how they make a control loop; then that loop will be running:

- **Step 0: define the end state.** Example: incrementally migrating to Effect on a codebase.
- **Step 1: build your sensor.** Example: finding deviations (un-migrated code). We could also do research here dynamically when we get to this step.
- **Step 2: stabilize the system.** Example: it's an insane amount of work in their case and it breaks a bunch of stuff, so first they had to prevent the problem from getting worse, and ensure we're not undoing our loop work. A disturbance dampener.
- **Step 3: build the controller.** Example: deciding how to incrementally change the system. In their case they used ast-grep to find the smallest thing, to minimize the risk. We could look in our telemetries to find out which procedures have the most errors, etc. (fantastic for projects that use PostHog, sentry.io, etc.). Sending a control signal to the actuator agent is something to research and do; they do this to ensure the actuator agent can do the thing better.
- **Step 4: build our actuator.** Example: your agent of choice plus a custom skill. At HumanLayer they build "golden patterns" by hand before setting the agents loose: idiomatic handwritten examples for the agents to follow, because they are just pattern replicators. The agents will work, make the commit, the PR.
- **Step 5: build the loop.** Example: GitHub Actions is your friend; you can schedule this loop to run every day, for example.
- **Step 6: put a human on the loop.** We need to keep the loop on the right track. A human on the loop to re-steer it when it goes wrong is low friction. It can be a feedback file that is tracked in version control, which we can load in our actuator agent's context.
- **Step 7: add flow control, limiting in-progress work.** If this thing is running without human supervision, we have to ensure it doesn't go crazy.

All control loops are also FSMs.

## Decisions

- **D-01:** A loop is its own artifact type in the vault, `.compass/loops/LOOP-NNN-name/`, holding everything the loop needs to keep running: its end state, sensor, controller, actuator, golden patterns, feedback file and state.

## User Scenarios

Examples of things we can measure:

- Eradicate bad patterns.
- Adopt new frameworks incrementally.
- Maintain a fork against an upstream.
- Mirror a project into another language.
- Keep integrations up to date.
- Ensure compliance with a third-party spec.
- Resolve system anomalies.
- A user makes an animation out of Maya through a Compass loop.
