---
title: "Checking cost follows task and model: research"
type: research
status: complete
confidence: low
area: tooling
tags: [tokens, cost, harness, verification, models, measurement]
summary: "research for SPEC-034: how Compass sizes tasks, what its checking stations cost per task, and how a part-by-part re-baseline on a model change would run"
created: 2026-11-21
updated: 2026-11-26
spec: "[[SPEC-034-checking-cost-follows-task-and-model]]"
---

# Checking cost follows task and model: research

Research for [[SPEC-034-checking-cost-follows-task-and-model]]. Prior evidence: [[research/llm-research/REVIEW-llm-research-for-compass]] and the axis files it cites; the axes below cover only what that survey leaves open.

## Axes

1. **Task difficulty signal.** How Compass sizes tasks today (complexity S/M/L in plans, the sizing log, any other difficulty field) and whether that signal is recorded early enough and reliably enough to key a checking level on. Sought in plugin/ agents, skills and CLI, and the vault's sizing log. Output: [[RESEARCH-axis-1-task-difficulty-signal]].
2. **What the checking stations cost.** Tokens the post-build tester, the validator and the builder's own review spend per task in past runs, and what they caught, aggregates only. Sought in bench/ run records and the vault's usage data. Output: [[RESEARCH-axis-2-checking-station-cost]].
3. **Part-by-part re-baseline.** How a with-against-without measurement of each harness part (thresholds, phase splits, validator cadence, prompt rules, emphasis markers) would run on the existing bench harness after a model or host change, and what the harness lacks for it. Sought in bench/ code and docs. Output: [[RESEARCH-axis-3-part-by-part-rebaseline]].
4. **The rule and its record.** Prior art on choosing verification depth from task difficulty and model (where checks pay off, how "inside the model's ability" is estimated), and how the choice could be recorded so the same task on the same model gets the same answer. Sought in the prior survey's sources, 2025-2026 papers and vendor posts, and Compass's existing decision records. Output: [[RESEARCH-axis-4-difficulty-keyed-checking-rule]].

5. **Gap pass.** Where the builder's self-review tokens land, and whether existing build records can count defects caught per station. Output: [[RESEARCH-axis-5-gap-pass]].

## Review

[[REVIEW-checking-cost]] consolidates axes 1 to 4; the gap pass closes the two gaps it names.

## Measurements

- [[RESEARCH-letter-repeatability]] - blind raters give the same complexity letter to a task almost every time (kappa 0.88 on the strong model, 0.84 on the balanced one, 0.70 across the two), yet agree with the letter the planner wrote on fewer than half the sessions; a rubric counting a task's tests apart raised cross-model kappa to 0.84 but lowered agreement with planners to 41-42%, so the shipped rubric stays
- [[RESEARCH-checking-cost-pilot]] - 12 pilot builds, 8 stopped by the 150-minute cap: the per-part goal effect varies so much within a topic (SD 0.45 of the goal share) that detecting a drop of one goal item in ten needs about 316 builds per arm (941 at the upper bound); removing the post-build tester did not save tokens
- [[RESEARCH-station-ablation]] - planted defects with every checking station replayed on each: on 44 defects builder review is the only station that catches defects alone (1 on S, 2 on M, 1 on L, so it is not lighter-eligible on any letter); the testers and the validator caught none alone, but no cell reaches the one-in-ten bound; the run stopped at the usage limit with 56 of 100 approved defects unread
