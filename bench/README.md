# Compass Benchmark Harness

**Not part of the Compass plugin distribution.** This directory lives at the repo root so contributors can see and run it on GitHub. Users who install Compass via `/compass:bootstrap` get only `../plugin/`; this directory never reaches their projects.

Measures the Compass methodology layer against a plain-Claude-Code baseline on established coding agent benchmarks. The plugin source under `../plugin/` is treated as read-only input; the `../.compass/` vault is not touched.

## Layout

```
bench/
  agents/             Per-arm wrapper scripts that external benchmarks invoke
    compass-agent.sh  Workspace gets Compass scaffold; Claude runs with the methodology
    baseline-agent.sh Workspace gets nothing; Claude runs against the raw task
  configs/
    arm-compass.yaml  Arm metadata for replicability and result tagging
    arm-baseline.yaml
    benchmarks.yaml   Benchmark roster + smoke / mini / full task subsets
  scripts/
    setup.sh          Create venv, install Python deps, clone external benchmarks
    analyze.py        Pareto + summary over results/
  external/           Cloned benchmark repos (gitignored)
  results/            Per-run output (raw transcripts gitignored, summaries tracked)
  requirements.txt    Python deps for analyze.py
```

## Arms

Both arms call the same Claude Code binary against the same model with the same tool allowlist and the same turn budget. The only difference is what is installed in the workspace before the agent starts.

- **compass arm**: `agents/compass-agent.sh` scaffolds a fresh `.compass/` vault inside the task workspace and copies the plugin's templates and skills into `.claude/`. Claude Code then runs the task with the full methodology, the agent definitions, the skills, and the hooks.
- **baseline arm**: `agents/baseline-agent.sh` runs Claude Code directly against the task workspace with no methodology, no agent definitions, no skills, no hooks.

Both arms record the model, tool allowlist, turn budget, total tokens, wall-clock time, and the benchmark's own success score.

## Benchmarks

See `configs/benchmarks.yaml` for the roster. Initial set:

- **Terminal-Bench**: Claude Code is the reference harness. Cleanest signal isolation.
- **SWE-bench Pro**: Multi-file end-to-end issue resolution on private-repo tasks.
- **SWE-Lancer (managerial split)**: Pick-the-best-proposal tasks that directly score spec / plan quality.

Each is fetched into `external/` by `scripts/setup.sh`. Smoke subsets (3-5 tasks) for fast iteration; full runs for publishable numbers.

## Usage

```bash
cd bench
./scripts/setup.sh                                  # one-time
source .venv/bin/activate
# example - actual invocation depends on each benchmark's own harness
./external/terminal-bench/run.sh --agent agents/compass-agent.sh   --tasks smoke
./external/terminal-bench/run.sh --agent agents/baseline-agent.sh  --tasks smoke
python scripts/analyze.py results/<run-dir>
```

The exact invocation per benchmark harness varies; `scripts/setup.sh` prints the resolved commands after cloning each external repo.

## Reporting

`analyze.py` reports the Pareto front over (success rate, total tokens, total cost). The point of the Pareto framing is that Compass adds tokens (more agent hops, more reads); the value claim must net those costs. Raw `pass@1` alone is not enough.

## Reading the results

A run that shows higher success rate at equal or lower cost than baseline is a clean Compass win. A run that shows equal success at higher cost is a loss even if `pass@1` is unchanged. A run that shows higher cost AND lower success is what the field literature warns about - frameworks that consume tokens without delivering quality.

## Source separation

Nothing in `bench/` writes to `../plugin/` or `../.compass/`. The compass-agent wrapper copies plugin files into per-task scratch workspaces under the external benchmark's own scratch directories. Plugin source is read-only input. The dogfood vault is irrelevant to bench runs.
