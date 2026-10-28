---
title: Subscription total_cost_usd paces a loop but does not cap it
type: lesson
status: active
category: domain
area: architecture
tags: [loops, budget, cost, subscription, flow-control]
created: 2026-10-19
updated: 2026-10-19
score: 5
summary: "On a Claude Code subscription total_cost_usd is an estimate, not a charge; loop flow control needs plan usage or rate-limit measures, not USD budgets"
source: extract-lessons:signal
seen: []
---

On a Claude Code subscription, `total_cost_usd` is an estimate rather than a charge, so a loop's USD budgets only pace it.
Flow control for subscription users needs a measure of plan usage or rate limits instead.
