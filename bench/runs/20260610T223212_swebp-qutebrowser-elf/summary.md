# SWE-bench Pro: qutebrowser ELF parser

**Benchmark:** SWE-bench Pro (ScaleAI/SWE-bench_Pro on HuggingFace, leaderboard at https://scale.com/leaderboard/swe_bench_pro_public)
**Instance:** `instance_qutebrowser__qutebrowser-34a13afd36b5e529d553892b1cd8b9d5ce8881c4-vafb3e8e01b31319c66c4e666b8a3b1d8ba55db24`
**Task:** Make ELF parser handle file read and seek errors more safely; raise `ParseError` for `OSError`/`OverflowError`; emit one debug log on success.
**Date:** 2026-06-10
**Harness:** Official SWE-bench Pro Docker eval against the ScaleAI image. Frontier-model SOTA on this benchmark is ~15-18%, so this is a real task.

## Results

| Metric | baseline | compass | Delta |
|---|---|---|---|
| **SWE-bench Pro score** | **PASS (1.0)** | **PASS (1.0)** | tie |
| Tests passed | 6/6 (1 skipped on Linux env) | 6/6 (1 skipped) | tie |
| Generation tokens | 42,354 | 58,797 | +39% |
| Tool uses | 17 | 35 | +106% |
| Wall (generation) | 172s (2m 52s) | 515s (8m 35s) | +200% |
| Patch size | 88 lines / 2832 chars | 84 lines / 2772 chars | -5% smaller |

## Per-test detail (identical for both arms)

```
tests/unit/misc/test_elf.py::test_format_sizes[<4sBBBBB7x-16]   PASSED
tests/unit/misc/test_elf.py::test_format_sizes[<HHIQQQIHHHHHH-48]   PASSED
tests/unit/misc/test_elf.py::test_format_sizes[<HHIIIIIHHHHHH-36]   PASSED
tests/unit/misc/test_elf.py::test_format_sizes[<IIQQQQIIQQ-64]   PASSED
tests/unit/misc/test_elf.py::test_format_sizes[<IIIIIIIIII-40]   PASSED
tests/unit/misc/test_elf.py::test_result   SKIPPED
tests/unit/misc/test_elf.py::test_hypothesis   PASSED
```

## Process delta (where methodology actually showed)

Both arms passed the benchmark. The compass arm spent 2x the tool calls and 3x the wall time on:
- More thorough file reading during the "research" phase (locating elf.py, reading the test file structure, reading utility modules)
- Building a stub-loaded module harness to verify behavior when pytest couldn't run locally (qutebrowser's test suite needs pytest-qt + 5 other plugins not in our env)
- Running a 10,000-trial fuzz verification (hypothesis-equivalent) before declaring done
- Explicit enumeration of the behavioral contract in the report

The baseline arm went with manual reasoning ("by inspection the changes satisfy each test condition") and didn't build the fuzz verifier. Both produced correct patches that passed the benchmark's hidden tests.

## What this single data point tells us

On a real peer-reviewed multi-step benchmark task, Compass methodology added ~40% token overhead and 3x wall time for an identical outcome score. The overhead bought "more thorough verification" that the benchmark didn't reward because the benchmark only measures the patch's correctness, not the process that produced it.

This is N=1, so no claim about averages. But it is consistent with the lighter-fixture runs (binary-search, merge-sorted-lists) where methodology also produced equal-or-better solutions at higher cost.

## Why the patch worked at all when neither arm could run pytest locally

Both agents read the qutebrowser source and the test file, understood the contract from problem statement + tests + interface spec, and produced syntactically correct patches that did the right things. Compass arm's extra fuzz verification didn't change the patch content, just gave more confidence in it.

## Caveats and known bugs encountered

This run uncovered three real bugs in the SWE-bench Pro Windows integration, all captured separately:
1. Docker tag length: 146-char tag truncated to 128; SDK's pull() recovers, but local image listing shows the truncated tag (cosmetic).
2. Encoding: dataset's `selected_test_files_to_run` is already a JSON-string; do NOT `json.dumps()` again or the eval gets character-split garbage.
3. Windows CRLF: `write_files_local` uses text-mode `open()` which writes CRLF on Windows, breaking bash inside the Linux container. Captured as [[LESSON-windows-crlf-breaks-linux-container-scripts]].

## Next discriminating signals to look for

- **Sample size**: N=1 is anecdote, not data. Run 5-10 tasks for a directional signal.
- **Harder tasks**: the qutebrowser ELF task was the smallest Python task in the dataset (10 fail_to_pass tests). Most SWE-bench Pro tasks have 50-200 tests and span 5+ files. Compass's planning might matter more there.
- **Cost-normalized accuracy**: at the SOTA's ~15-18% pass rate, a methodology that wins 1-2pp on accuracy at 2x cost might still be Pareto-positive if the cost is amortized over fewer wasted runs.
