---
title: "pipeline"
type: domain
status: active
tags: [pipeline]
summary: "how work passes the human's gates - adversarial review before approval, walkthroughs in his words, verifying reversibility before acting unasked"
created: 2026-09-05
updated: 2026-09-05
sizing_id: sz-2026-09-05-2
---

# pipeline

## Scope

Class here: how work passes the human's gates - adversarial review before approval, walkthroughs in his words, verifying reversibility before acting unasked

## Lessons

- [[lessons/pipeline/LESSON-adversarial-plan-review-before-build|LESSON-adversarial-plan-review-before-build]] - Review specs/plans with 3 adversarial lenses before approval, and have reviewers measure against the real corpus, not opine
- [[lessons/pipeline/LESSON-loop-auto-accepts-increments-matching-the-accepted-pattern|LESSON-loop-auto-accepts-increments-matching-the-accepted-pattern]] - Run a loop unattended by script-checking each increment against the pattern the human accepted; hold only the odd ones for him
- [[lessons/pipeline/LESSON-loop-limits-step-only-when-unsupervised-or-expensive|LESSON-loop-limits-step-only-when-unsupervised-or-expensive]] - A loop's step 7 (limits and escalation) is set when the loop runs unsupervised or each run is costly; a cheap hand-run loop keeps the defaults
- [[lessons/pipeline/LESSON-manual-verification-is-judgment-only|LESSON-manual-verification-is-judgment-only]] - Plan manual verification holds only judgment calls; mechanical checks go in automated verification or the orchestrator's own check
- [[lessons/pipeline/LESSON-stated-definitions-are-not-research-axes|LESSON-stated-definitions-are-not-research-axes]] - A definition the human stated in the request is settled; turning it into a research axis re-asks what they already said
- [[lessons/pipeline/LESSON-subscription-cost-is-an-estimate-not-a-budget|LESSON-subscription-cost-is-an-estimate-not-a-budget]] - On a Claude Code subscription total_cost_usd is an estimate, not a charge; loop flow control needs plan usage or rate-limit measures, not USD budgets
- [[lessons/pipeline/LESSON-ui-change-needs-agreed-mockup-before-build|LESSON-ui-change-needs-agreed-mockup-before-build]] - A UI change gets a mockup the human agrees on before any builder runs; a UI built without one gets the plan declined.
- [[lessons/pipeline/LESSON-walkthroughs-in-the-humans-words|LESSON-walkthroughs-in-the-humans-words]] - Jargon in walkthroughs and paraphrase in specs both erase the human's own words where they must recognize themselves
