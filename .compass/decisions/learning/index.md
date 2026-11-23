---
title: "learning"
type: domain
status: active
tags: [domain, decisions, lessons, capture]
summary: "rulings on capture and feedback - lessons, workers, signal handling, source-word fidelity"
created: 2026-08-30
updated: 2026-08-30
sizing_id: sz-2026-08-30-16
---

# learning

## Scope

Class here: rulings on capture and feedback - lessons, workers, signal handling, source-word fidelity

## Contents

- [[ADR-025-drift-recheck-runs-outside-consolidation-cadence]] - the zero-token drift scan sits outside consolidation's trigger-only rule: it runs detached from the session-start hook when HEAD has moved, writes a new report only when findings change, and code applies a fix alone only where git proves it
