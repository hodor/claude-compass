---
title: "Callout Decisions Fixture"
type: spec
status: draft
summary: "a spec whose decisions sit in a callout, with tags, a discretion group, a block id and nested quotes"
---

# Callout Decisions Fixture

## Problem

People lose track of rulings.

A second paragraph of the problem, with a [[link]] and `code`.

### A sub-heading inside the problem

Still the problem.

## Desired Outcome

Every ruling is a card.

```text
## Decisions
- **D-99:** this one sits in a fence and is never a decision
```

## Decisions (made by the human)

Some prose that is not a decision.

> [!NOTE]
> - **D-01:** First ruling, in a callout.
> - **D-02 [deferred]:** Second ruling, tagged deferred.
>   continued on an indented line.
> - **D-03:** Third ruling with a block id. ^d-03
>
> > - **D-04:** Fourth ruling, nested one level deeper.

- **D-05:** Fifth ruling, a plain bullet after the callout.

### Builder discretion

- **D-06:** Sixth ruling, in a discretion group.

## Open Questions

- [ ] Is a fifth question open?
