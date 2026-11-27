---
title: "Station ablation by planted defects: which checking station catches what"
type: research
status: complete
confidence: low
area: tooling
tags: [tokens, cost, verification, measurement, bench, tester, validator, ablation]
summary: "planted defects with every checking station replayed on each: on 44 defects builder review is the only station that catches defects alone (1 on S, 2 on M, 1 on L, so it is not lighter-eligible on any letter); the testers and the validator caught none alone, but no cell reaches the one-in-ten bound; the run stopped at the usage limit with 56 of 100 approved defects unread"
created: 2026-11-26
updated: 2026-11-26
author: "build-lead"
depends_on: ["[[PLAN-034-checking-cost-follows-task-and-model]]", "[[RESEARCH-checking-cost-pilot]]", "[[RESEARCH-letter-repeatability]]"]
---

# Station ablation by planted defects

```mermaid
flowchart LR
  D["11 planted defects<br/>3 S, 4 M, 4 L"] --> P["pre-build tester<br/>7 caught"]
  D --> R["builder review<br/>9 caught"]
  D --> T["post-build tester<br/>8 caught"]
  D --> V["validator<br/>10 caught"]
  D --> N["no station<br/>1 defect"]
```

> [!note] Decided 2026-11-26
> The full batch is approved: about 100 planted defects across S, M and L, about 350 sessions on the subscription, so that any station's lone catches are bounded below one in ten per letter. On the first 11 defects no station caught anything the others missed.

Measured for [[PLAN-034-checking-cost-follows-task-and-model]] TASK-353, which replaced a goal-share ablation after [[RESEARCH-checking-cost-pilot]] put that at about 316 builds per arm.

## How it ran

- **The tasks.** Finished tasks of the kept Compass-arm pilot builds, in Python and Go projects: each has a pre-build tester commit and exactly one builder commit, and its plan line carries a letter. The pool holds 23 S, 54 M and 13 L tasks. Two batches of two tasks per letter were drawn with seeds 0 and 1.
- **The defect.** One single-token mutation on a source line the builder's commit added: an integer constant raised by one (7 defects), `==` and `!=` swapped (4). The draw also allows comparison and `and`/`or` swaps; none came up. The builder's commit was rewritten to carry it, and a mutant that did not compile was dropped for the next site.
- **The stations,** each on its own copy so none saw another's work:
  - pre-build tester: its commit's tests, run on the clean and the planted state, mechanically;
  - builder review: the style and the correctness reviewer of the builder agent, one session each on the builder's model;
  - post-build tester: a `tester` session in post-build mode;
  - validator: a `validator` session on the task.
- **Caught** means: a test failing only on the planted state (testers), or a report pointing at the planted line within three lines, or at its file together with its enclosing function (review, the tester's Bugs Found list, and a validator report whose verdict is a failure).
- **The rule.** For a letter, a station is lighter-eligible when every defect it caught was caught by another station too.

## Results

| Letter | Defects | Pre-build tester | Builder review | Post-build tester | Validator | No station |
|---|---|---|---|---|---|---|
| S | 3 | 3 | 3 | 3 | 3 | 0 |
| M | 4 | 3 | 3 | 4 | 4 | 0 |
| L | 4 | 1 | 3 | 1 | 3 | 1 |
| All | 11 | 7 | 9 | 8 | 10 | 1 |

No station caught a defect alone, on any letter. By the rule, every station is lighter-eligible on every letter of this batch.

| Defect | Letter | Language | Class | Pre-build tester | Builder review | Post-build tester | Validator |
|---|---|---|---|---|---|---|---|
| D1 | S | Go | equality | caught | caught | caught | caught |
| D2 | S | Go | equality | caught | caught | caught | caught |
| D3 | S | Python | constant | caught | caught | caught | caught |
| D4 | M | Go | constant | caught | missed | caught | caught |
| D5 | M | Python | constant | caught | caught | caught | caught |
| D6 | M | Python | equality | missed | caught | caught | caught |
| D7 | M | Python | equality | caught | caught | caught | caught |
| D8 | L | Python | constant | missed | missed | missed | missed |
| D9 | L | Python | constant | missed | caught | missed | caught |
| D10 | L | Python | constant | missed | caught | missed | caught |
| D11 | L | Python | constant | caught | caught | caught | caught |

D1 and D2 sit in the same task at two different lines.

### What the batch shows

- **The validator caught every defect any station caught** (10 of 10). Each time its report named the planted file and line, or the file and the function, and described the planted change.
- **On L tasks the testers fell behind.** Both testers caught 1 of 4 L defects, while review and the validator caught 3. The two L defects that only review and the validator caught each changed a bound in game input handling (a movement step and a cursor edge). The pre-build tests did not cover the first; for the second, the pre-build test file meant to catch it failed to load on the clean code as well. The post-build tester did not name either.
- **Review missed one defect the tests caught at once:** a field width raised by one in a timestamp parser (D4), where 44 pre-build tests failed.
- **D8, caught by no station,** raised a default value from 0 to 1 on a data class field. No test, review or validator check looked at that default; it may change no behaviour the task asks for.
- **No false credit was found by hand.** Every credited catch was read against its report: each names the planted line and describes the planted change.

### What it cost

- About 19,000 output tokens per defect over its four sessions. The validator wrote about half (it runs on `opus`), each tester session about a quarter, the two review sessions together about a quarter.
- About 3 minutes of wall time per defect with three sessions at once; the pre-build tester is a test run and spends no session.

## The batch a lighter-checking claim needs

A station is dropped for a letter only if it almost never catches a defect alone. With zero lone catches among n caught defects, the 95% upper bound on a station's lone-catch share is about 3/n (the rule of three). Bounding it below one in ten needs n of about 30 caught defects per letter. One defect in eleven was caught by no station, so that is about 33 planted per letter, about 100 in all, 88 more than this batch: about 350 sessions and about 1.7 million output tokens. The pool holds only 13 L tasks, so the L defects would include two or three sites per task. Defects in one task are not independent, so the bound would be optimistic for L.

## Limits

- **The stations were replayed, not run inside builds.** In a real build the builder fixes what its review finds before any tester runs, so the testers never meet those defects. The replay counts what each station would catch alone, which is the question the rule asks, not what each station catches in sequence.
- **The defects are single-token mutations** of two classes. Planted bugs of the kinds builders really make (a missed case, a wrong rule) may split the stations differently.
- **The letters are the planners' letters,** which [[RESEARCH-letter-repeatability]] found blind raters reproduce less than half the time. A per-letter result here is per planner letter, not per rubric letter.
- **A report is credited when it points at the planted line or at its file and function.** A report that describes the defect in words without naming either is not credited, so the counts are a floor.
- **Two defects of the first batch landed inside docstrings.** They were set aside, kept with the batch's private records, and the same two tasks were planted again with lines inside multi-line strings and comments excluded.
- **11 defects, 10 tasks and 2 languages.** The results are indicative only.

## The full batch, stopped at the usage limit

Run 2026-11-26 under the approval above: three more seeds of ten tasks per letter, on the harness of this page plus three fixes made during the run (git status read record by record, one station's judging error no longer stops the batch, a reply already kept is judged again rather than paid for twice). The subscription's usage limit ended the run after 44 of the planned 100 defects had every station read; the limit resets on 2026-11-30, and the same commands resume the 47 defects already planted.

| Letter | Defects | Caught by a station | Pre-build tester | Builder review | Post-build tester | Validator | No station |
|---|---|---|---|---|---|---|---|
| S | 16 | 14 | 7 (0 alone) | 14 (1 alone) | 13 (0 alone) | 11 (0 alone) | 2 |
| M | 14 | 12 | 6 (0 alone) | 11 (2 alone) | 10 (0 alone) | 9 (0 alone) | 2 |
| L | 14 | 10 | 6 (0 alone) | 10 (1 alone) | 6 (0 alone) | 7 (0 alone) | 4 |

The 44 defects span 34 tasks in 14 pilot projects: 30 integer constants, 9 equality swaps, 3 `and`/`or` swaps and 2 comparison swaps; 34 in Python and 10 in Go. Eight plants repeated a site an earlier seed had already drawn and are counted once.

### Verdict per cell

| Station | S | M | L |
|---|---|---|---|
| Pre-build tester | no lone catch; bound 0.21, not yet below 0.10 | no lone catch; bound 0.25 | no lone catch; bound 0.30 |
| Builder review | not eligible: 1 lone catch | not eligible: 2 lone catches | not eligible: 1 lone catch |
| Post-build tester | no lone catch; bound 0.21 | no lone catch; bound 0.25 | no lone catch; bound 0.30 |
| Validator | no lone catch; bound 0.21 | no lone catch; bound 0.25 | no lone catch; bound 0.30 |

The bound is the 95% upper limit on a station's lone-catch share given zero lone catches among the defects some station caught (3 divided by that count). No cell has reached the one-in-ten bound the approval set, so no checking level is lowered on this evidence.

### What the larger batch adds

- **Builder review is the one station that catches alone.** Its four lone catches were each read by hand: an inverted position check, a loop bound one past a room's edge, an exit code changed from 2 to 3, and an error path returning 1 where it returned 0. Each review finding names the planted line and describes the change. No test reached any of the four.
- **The validator no longer catches everything.** On the first 11 defects it caught all that any station caught; over 44 it caught 27 of the 36, missing defects whose effect no command it ran made visible.
- **On L tasks the testers stay behind review.** Both testers caught 6 of 14 L defects; review caught 10.
- **10 of 44 defects were caught by no station.** Most change a constant no test or check reads, such as a default field value; some may change no behaviour the task asks for.

### What it cost

The 33 defects whose sessions recorded their tokens used about 18,000 output tokens each over four sessions: the validator about half, the post-build tester about a fifth, the two reviews together about a quarter.

### Limits of this run

- **For part of the run six sessions ran at once, not three.** A first copy of the run that was stopped to load a fix kept a second seed going beside the restarted one, so two seeds ran side by side until the usage limit. Its results were judged by the same rules and are kept; the overlap raised the run's pace on the subscription.
- **56 planned defects are not yet read,** so every cell's count is below the 30 caught defects the bound needs.
