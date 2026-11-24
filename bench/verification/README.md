# Verification probe

`planted.py` measures whether the verification checks (`compass reach`, `compass ablate`, and the validator's step 4j) flag defects that a green test suite lets through. It builds a small project with known defects and reports, per defect, which check flagged it.

## What it measures

The seeded project is `tally`, a word counter run as `python -m tally <command> <text>`. It holds a spec with seven requirement rows (`O-1`, `O-2`, `O-3`, `K-1`, `C-1`, `C-2`, `C-3`), a three-task plan, and three `Merge TASK-NNN:` commits. The suite is green after every merge.

| Task | Planted failure | Check that should flag it |
|---|---|---|
| A (TASK-001) | `format_total` is added and no command calls it | `reach` |
| B (TASK-002) | one line of `count` changes, and its tests pass without the change | `ablate` |
| C (TASK-003) | `tally top` returns the first word of a tie, where the spec says the alphabetically first | step 4j (`--judge`) |

The unplanted controls are the other checks: `reach` on B and C, `ablate` on A and C. Each must say `PASS`. A `FINDING` there is a false positive. The plain suite is also reported per task, so the report shows that it flagged nothing while the defects were present.

Every check runs through `compass evidence run`, its record is committed, and each record is run again with `compass evidence rerun`.

## Running it

```
python bench/verification/planted.py [--root DIR] [--judge] [--json FILE]
```

- Needs `uv` and `git` on `PATH`. The project gets its own `.venv` holding `coverage` and `pytest`.
- `--root DIR` builds in `DIR`, which must be missing or empty and outside any git work tree. Without it the probe builds in a new temp folder and deletes it after a passing run; after a failing run it keeps the folder and names it on stderr.
- `--judge` also starts one headless `claude` session as the `validator` agent, limited to step 4j for TASK-003. It uses the subscription and takes minutes. `plugin/` of the repository must have no uncommitted changes.
- `--json FILE` writes every result (suite, checks, judge rows, scores, tokens, wall time). It holds no answer text.

Without `--judge` no model is called.

## Output

```
suite: green              the suite at HEAD passes (red if it does not)
suite A: flagged nothing  per task: what the suite said ("flagged" when it is red)
reach A: FINDING          check <reach|ablate>, task letter, verdict
rerun reach A: match      the record rerun: match, mismatch or error
4j C-3: missing           with --judge: the judge's status per requirement row
4j planted C-3: flagged   with --judge: whether C-3 was judged partial, missing or contradicts
4j false positives: 0     with --judge: rows that are met but were judged unmet
wall: 27.3s               seconds from start to the last line
```

Expected verdicts:

| | A | B | C |
|---|---|---|---|
| reach | FINDING | PASS | PASS |
| ablate | PASS | FINDING | PASS |

The judge's rows `O-3`, `K-1`, `C-1` and `C-2` are met, and `C-3` is unmet. Rows `O-1` and `O-2` belong to other tasks and are listed without scoring. A reply with no `REQ <id>: <status>` line is a failed measurement, not a miss.

## Exit code

- `0`: the suite is green, every check equals the expected verdict, every rerun is `match`, and (with `--judge`) the judge session returned rows.
- `1`: any of those does not hold. The judge's `planted` and `false positives` lines are reported, never part of the exit code.
- `2`: the build was refused (non-empty `--root`, or a folder inside a git work tree).

## Tests

```
python -m pytest bench/verification/tests/test_planted.py -q
```

The tests that build a project need `uv`; they are skipped without it.
