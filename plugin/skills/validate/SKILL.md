---
name: validate
description: Run the validator agent as the final quality gate. Compares plan against actual implementation, runs adversarial probes, issues VERDICT.
version: 1.0.0
allowed-tools: [Agent]
when_to_use: "Use after building is complete and you want the final quality gate. Triggers: 'validate', 'final check', 'verify implementation', 'run the validator'."
argument-hint: "[PLAN-NNN]"
---

# Validate — Spawn the Validator

Spawn the `validator` agent to compare the plan against the actual implementation.

## Protocol

1. Parse the argument (plan number) or find the active plan from `active.md`
2. Spawn the `validator` agent with the plan file path
3. The validator handles the rest — diff computation, automated checks with evidence, adversarial probes, VERDICT

That's it. This skill is just the entry point. All the logic lives in the agent.
