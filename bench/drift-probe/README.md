# Drift probe

Measures whether the drift scan finds staleness that is known to be there and stays quiet about everything else.

## What it measures

The drift scan (`plugin/cli/driftlib.py`, behind `compass drift`) compares three kinds of vault text with the source each restates:

- code references (`path:N`) against the git history of the cited file,
- index lines against the `summary` of the document they link,
- lesson-catalog rows against their lesson files.

The probe plants staleness in a scratch clone and checks the scan against a list it froze before scanning.

| Kind | Items | Stale | How a stale item is made |
|---|---|---|---|
| code references | 40 | 8 | 3 shifted (a line inserted above the cited range), 3 edited (a cited line changed), 1 moved (`git mv` of the cited file), 1 deleted (`git rm`) |
| index lines | 30 | 6 | 3 with the target's `summary` edited, 3 with the index line's own text edited |
| catalog rows | 30 | 6 | 3 with the lesson file's `score` changed, 3 with its `summary` edited |

That is 100 items: 20 seeded stale and 80 controls. Controls are drawn only from items the baseline scan of the clone reports as clean, and are never touched.

## Pass rule

20 of 20 seeded items reported, and 0 of 80 controls reported. A control counts as reported when the scan returns any record for it other than `unchanged` or `changed-elsewhere`.

A seeded item reported under a different class than expected still counts as detected; it is counted apart as `wrong_class` and does not fail the probe. Records for items outside the list (other drift that was already in the repository) are ignored.

The rule is the spec's KPI: the stale ones and no fresh ones.

## How to run

Run from the repository root. `TARGET` is a missing or empty folder outside the repository; the seeder refuses a folder inside the repository or one that holds anything.

```
python bench/drift-probe/seed.py TARGET --seed N
python bench/drift-probe/score.py TARGET
```

Use N = 1, 2 and 3 for the three draws, each with its own `TARGET`. The first line `score.py` prints is `pass` or `fail`, followed by the counts and the ids of missed items, wrong-class items and reported controls. The exit code is 0 on pass and 1 on fail.

`seed.py`:

1. clones the repository with `git clone --local` into `TARGET`,
2. scans the clone for the baseline,
3. draws the 100 items from the baseline-clean candidates with `random.Random(N)`,
4. makes the 20 stale items stale in the clone and commits the changes there,
5. freezes the list in `TARGET.seeds.json` beside the target (`--list PATH` picks another path).

The list is written once. A second run against an existing list exits 1 and leaves it byte-identical; a refused target exits 2. Both checks run before the clone is made. The same seed over the same repository gives the same list.

No `compass sync` runs between the seeding commit and the scan, so the scan sees exactly what the seeder wrote.

## The scan

The probe imports `driftlib` from the clone's own `plugin/cli` (in a subprocess) and calls `scan_refs`, `scan_index_lines` and `scan_catalog`, instead of parsing the output of `compass drift --print`, which is a report written for a human. The code under test is therefore the code committed at the repository's HEAD when `seed.py` ran.

## Candidates

To keep one seeded change from landing on a second item:

- each cited path is the candidate of one reference at most,
- cited paths under `.compass/`, `.claude/`, `plugin/cli/` (the scanner itself) and `bench/drift-probe/` are skipped,
- a reference whose citing line is a line another item edits is skipped,
- index targets under `lessons/`, and targets linked from more than one index line, are skipped,
- catalog rows need a lesson file with a one-line `score` and `summary`.

Catalog controls alternate between watching the `score` line and the `summary` line of the row.

## Tests

```
python -m pytest -q -p no:cacheprovider bench/drift-probe/tests
```

The tests cover the draw (counts, determinism, pool boundaries), the target and frozen-list refusals, and the scorer on hand-built results.
