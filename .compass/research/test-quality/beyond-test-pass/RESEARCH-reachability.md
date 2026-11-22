---
title: "Reachability: checking that a task's new code is reached from a real entry point"
type: research
status: complete
confidence: medium
area: testing
tags: [testing, verification, reachability, validator, coverage, call-graph]
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "6faced1"
author: researcher
summary: "run-the-real-entry-point under coverage and intersect with diff lines is the one language-agnostic-in-shape, low-false-positive check; static dead-code tools are cheap but blind to dispatch and tests; worked on the compass CLI in under 1 s"
---

# Reachability: checking that a task's new code is reached from a real entry point

From [[SPEC-034-verification-beyond-test-pass]]. Prior evidence reused, not redone: [[research/llm-research/REVIEW-llm-research-for-compass]] row 7 and section A3 candidate (reachability probe, no-op ablation, requirement check), and finding 17 of [[research/llm-research/RESEARCH-axis-4-multi-agent-verification]]. [[research/test-quality/RESEARCH-test-quality-synthesis]] was read for context; it holds no reachability measurement.

## Question

How can Compass check cheaply, across languages, that code a task adds is reached from the deliverable's real entry points (a CLI command, a user action, an exported API) and not only from tests?

## Methodology

Technology landscape / comparative evaluation (DESMET feature analysis in case-study mode): the axis asks which of several concrete check styles to use, so the candidates were compared on cost, false-positive behavior and per-language setup, with documentation review (primary tool docs and source repos) plus a worked trial on `plugin/cli`. Brief carried `grading: allowed`: each finding carries a grade (weight of its evidence type for this topic) separate from its confidence.

## Findings

1. **Compass already has no reachability check; the gap is confirmed in code** (confidence: high)
   - `.claude/agents/validator.md:112-126` step 5 re-runs the suite and step 6 lists adversarial probes by change type; no row asks whether new code is reached from an entry point.
   - Grep of `plugin/templates`, `plugin/cli`, `plugin/skills` for reachab / entry point / diff-cover / coverage run / vulture finds only the unrelated `compass coverage` (decision traceability) and prose uses of "entry point" (`plugin/templates/agents/codebase-analyzer.md:31`, a research-reading aid).
   - `plugin/templates/agents/builder.md` review charter is style-level (REVIEW row 7, "Touches").
   - Marks: code read; no retraction applicable; not a preprint; 0 citations; 3 greps and 2 files agree
   - Grade: high (direct code evidence)

2. **Run-the-entry-point-under-coverage, then intersect with the diff, works and is fast** (confidence: high)
   - Worked case on a scratch copy of `plugin/cli`: `coverage run --source=cli --omit="*/tests/*" cli/compass tree` took 0.60 s wall; `coverage xml` plus `diff-cover cov.xml --diff-file d.diff` took 0.42 s.
   - Seeded 2 changes: one added line inside `commands/tree.py:run` (the real command body) and two unreferenced helpers appended to `looprunner.py`. Output: `commands/tree.py (100%)`, `looprunner.py (0.0%): Missing lines 932-933,936-937`, total 20% of 5 changed lines. The reached change passed and the unreached code was named by line.
   - Setup per language is a coverage tool plus a Cobertura XML or LCOV report; `diff-cover` (v11.0.4, pushed 2026-11-19, 851 stars) reads Cobertura, JaCoCo, Clover and LCOV and is language-neutral. Needs a git repo even with `--diff-file` (it calls `git rev-parse` at start; raised `CommandError: not a git repository` in an uninitialised directory).
   - Marks: code run and measured; not retracted; not a preprint; diff-cover 851 stars; 1 trial, matches tool docs (Cobertura/JaCoCo/LCOV list taken from the tool's own `--help` and package, not re-verified in its README)
   - Grade: high (measured locally, direct)

3. **Static call-graph and dead-code tools miss dispatch-by-string, which the compass CLI uses for every command** (confidence: high)
   - `plugin/cli/maincli.py:126-129` builds `module_name = "commands." + name.replace("-", "_")` and calls `__import__(module_name, fromlist=["run"])`, then `module.run(args)` at `:137`.
   - `pyan3` (call graph, 0.375 s on maincli + 3 modules, 60 edges) drew `maincli.dispatch -> commands.usage.record` (static import) but no edge to any `commands.<name>.run`. A static root-at-`main` reachability check would call every command body unreachable.
   - Coverage-from-entry-point found `commands/tree.py` run body reached (finding 2).
   - Marks: code run; not retracted; not a preprint; 0 citations; 1 trial, agrees with the general dynamic-dispatch limit in findings 6 and 7
   - Grade: high (measured)

4. **vulture is cheap but name-based, so it is blind in both directions on this codebase** (confidence: high)
   - Whole `plugin/cli`: 0.74 s excluding tests, 2.4 s including tests. Excluding tests it reports 8 items at 60% confidence (e.g. `looprunner.py:843 run_iteration`, `looprunner.py:883 write_baseline`, `commands/sweep.py:30 ANY_TASK`); none is a `run` function.
   - Seeded `seeded_test_only_helper` (called only from a test) and `seeded_dead_helper` (called by nothing) in a copy: with tests excluded vulture flagged both (`looprunner.py:932`, `:936`); with tests included it flagged only the dead one. So running it twice (with and without tests) and diffing separates "dead" from "reached only by tests".
   - vulture matches by name, so a method named `run` called anywhere satisfies every `run`; a name collision hides dead code.
   - vulture 2.16, pushed 2026-11-16, ~5.0k stars.
   - Marks: code run; not retracted; not a preprint; ~5k stars; 1 trial
   - Grade: medium-high (measured on one codebase)

5. **A task-scoped reachability check needs a named entry point; the plan schema has no field for it** (confidence: medium)
   - Plan task lines carry `files:`, `complexity:`, `depends_on:`, `decisions:`, `lessons:` and `Automated verification:` bullets (`.claude/skills/obsidian/templates.md:198-203`, Plan template). Nothing names the command or user action that must reach the code.
   - Two naming forms exist in the artifacts as they are: a runnable command in the task's "Automated verification" bullet (what the validator already executes under the `Command / Output / Result` block, `validator.md:58`), or a spec-level statement of the deliverable's entry (the spec forbids solution detail, so the entry belongs in plan or research, not spec).
   - Whether a new `entry:` task field is warranted is a planner/human choice, not tested here.
   - Marks: code and template read; not retracted; not a preprint; 0 citations; 2 files agree
   - Grade: medium (documents current state; the design choice is untested)

6. **Static tools by language: what each roots from and what each cannot see** (confidence: medium)
   - **Go `deadcode`** (official, x/tools): RTA from `main` plus package initializers; `-test` adds test mains; `-whylive` prints the call chain that keeps a function live; claims soundness for dynamic calls ("cannot be called even through these dynamic mechanisms") but may miss some dead code, and cannot see assembly or `go:linkname`; reflection is assumed to reach any method of any type converted to an interface (https://go.dev/blog/deadcode, fetched). Zero per-project setup beyond `go install`.
   - **JS/TS `knip`** (12.7k stars, pushed 2026-11-21): entry files default to `index|main|cli` in root and `src/`, plus every `package.json` `main/module/bin/types/exports`, scripts, CI `run` commands, framework plugins, and `import()`/`require()`/`new Worker()`/`child_process` targets; custom `entry` replaces the default (https://knip.dev/explanations/entry-files, fetched). False-positive handling is configuration (`entry`, `project`, `ignore`); the page says nothing on false-positive rates.
   - **`ts-prune`** (repo not archived, last pushed 2026-10-31): finds unused exports only; README not retrievable (404 on the guessed URL), so its relation to knip is unverified here.
   - **Python**: `vulture` (name-based, finding 4), `pyan3` (call graph, no dynamic import edges, finding 3), `PyCG` (call-graph generator; repository path not reachable from the guessed GitHub slug, so its current state is a gap).
   - **Rust**: `rustc`'s `dead_code` lint "detects unused, unexported items" (warn by default; doc fetched); an item that is `pub` in a library crate is not flagged. `cargo-udeps` finds unused dependencies in `Cargo.toml`, not unused functions, and needs `cargo +nightly udeps` (README fetched), so it does not answer this axis.
   - **JVM and C#**: not investigated (gap).
   - Marks: official docs and source repos fetched; not retracted; not preprints; stars as listed; 2 of 4 tools verified at first hand by fetch, others by repo metadata only
   - Grade: medium (vendor/maintainer docs, asserted not measured)

7. **Static reachability has the same two failure shapes everywhere: roots and dynamic edges** (confidence: medium)
   - The root set is a configuration input in every tool (knip `entry`, deadcode `main` plus `-test`, vulture whole-tree names); a wrong or missing root makes live code look dead or test-only code look live.
   - Dynamic edges (string dispatch, reflection, plugins, decorators, DI) are either over-approximated (deadcode reflection rule, vulture name matching: dead code hidden) or dropped (pyan3, finding 3: live code flagged).
   - Marks: derived from findings 3, 4, 6; not retracted; not a preprint; 0 citations; 3 findings agree
   - Grade: medium (synthesis across tools)

8. **LSP find-references is a possible language-agnostic fallback; not tried** (confidence: low)
   - The session already lists Serena (`find_symbol`, `get_symbols_overview`) and the research skill points at it for symbol-level navigation (`plugin/skills/research-codebase/SKILL.md:194`). A references query returns callers, including test files, so "callers outside tests" would be the filter.
   - It resolves symbols, not runtime dispatch, so it shares findings 3 and 7. It is a per-symbol, agent-token query (one call per new symbol), against the script-only cost of findings 2 and 4.
   - Not run in this pass; no timing or accuracy measured.
   - Marks: inference from tool documentation in the repo; not retracted; not a preprint; 0 citations; 1 source
   - Grade: low (untested)

9. **Reachability is a necessary check, not sufficient: reached from the entry is not the same as used by the deliverable** (confidence: medium)
   - Finding 17 of the axis-4 research (preprint Jun 2026, https://arxiv.org/abs/2606.28430, abstract only) reports agents implementing tested behavior in a demo app and leaving the library unused, caught by "a mechanical audit and a no-op ablation". The audit is the reachability half; ablation (stub the diff's behavior, see which tests flip) is the sibling check and is covered by the sibling axis file [[RESEARCH-change-ablation]].
   - An entry-point run exercises the lines it executes, not whether those lines produce the result the spec names; line coverage from one command says "executed", never "correct".
   - Marks: preprint 2026-06, no published version known; not retracted; 0 citations known; 1 source (reused from prior research)
   - Grade: low-medium (measured, two agents, one task)

## Comparison (what each check costs and needs)

| Check | Measured cost on `plugin/cli` | Per-language setup | Sees tests-only use | Dynamic dispatch | Needs entry named |
|---|---|---|---|---|---|
| Coverage from a real command + diff-cover | 0.60 s run + 0.42 s diff (one command) | coverage tool + XML/LCOV export per language; git repo | yes (tests not in the run) | handled (code actually runs) | yes, a runnable command |
| vulture, tests excluded vs included, diffed | 0.74 s and 2.4 s | Python only | yes (via the diff of the two runs) | blind (name match hides dead code) | no |
| pyan3 / static call graph from `main` | 0.38 s | per language | yes | drops dynamic edges (false dead) | root `main` |
| Go `deadcode -test` | not run | none beyond Go | yes | RTA, sound claim | `main` |
| knip | not run | JS/TS config tuning | yes | follows `import()` etc. | package.json plus config |
| LSP find-references | not run | LSP per language (a session tool) | yes | no | per symbol |

## Contradictions

- Findings 3 and 4 disagree about direction of error on the same codebase: pyan3 drops the dispatch edge (would flag live code), vulture's name matching keeps `run` alive (would hide dead code). Both are wrong in different directions; coverage (finding 2) is the check that sees the dispatch.

## Gaps

- JVM (e.g. JaCoCo plus diff-cover), C# (Roslyn analyzers, coverlet) and Rust function-level reachability were not investigated or run; only dependency-level `cargo-udeps` and the `dead_code` lint were checked from docs.
- Coverage-from-entry for a non-CLI deliverable (a UI action, a web route) needs a driver such as Playwright or an HTTP request; not tried. The compass CLI case is the easy one (a command is one process).
- diff-cover run used a hand-built unified diff in a scratch git repo; behavior against a real branch diff (`--compare-branch`) was not run.
- Coverage for a hook-fired or multi-process entry (compass runs hooks as subprocesses) needs `coverage` subprocess configuration; not tried.
- `ts-prune` README and PyCG repository status were not reachable.
- False-positive rate of knip and `deadcode` on real projects: only the maintainers' descriptions were read, no measurement.

## Gap pass: non-CLI entry points

Closes two gaps listed above: a web route or UI action driven from outside, and a subprocess fired by a hook. Methodology as above (comparative evaluation, case-study mode); `grading: allowed`. All cases ran in a scratch directory with a uv venv (coverage 7.17.4, diff-cover) and Node 22 (c8, Playwright with Chromium), Windows 11, one machine, one run each; wall times include interpreter start. Same pipeline as finding 2: coverage data, XML or LCOV export, `diff-cover <report> --diff-file d.diff`.

### Findings

10. **A server started under coverage and hit with a plain HTTP request reaches the diff check; about 0.5 s over a bare run** (confidence: high)
   - Python stdlib `http.server` handler calling `app.greet`; the diff added `route_new` (called by the handler) and `route_dead` (called by nothing). Command: `coverage run --data-file=.cov --source=. server.py <port>` in the background, a `urllib` client, then a `/shutdown` route calling `server.shutdown()`.
   - Result: `app.py (80.0%): Missing lines 8` (the dead function body); the reached route passed. Wall 0.90 s against 0.37 s for the same server and client with no coverage.
   - Marks: code run and measured; not retracted; not a preprint; 0 citations; 1 trial, agrees with finding 2 (CLI case)
   - Grade: high (measured locally, direct)

11. **The server's data file is written only on a normal exit; a killed server loses it with no error** (confidence: high)
   - Server under coverage, one request served, then `kill -9`: no data file existed and nothing was printed. Same shape in Node: a hard-killed `node` server under `NODE_V8_COVERAGE` left no file mentioning `route.js`; a graceful `/shutdown` left one.
   - The report from that state says 0% for the whole diff, indistinguishable from "code not reached". The check needs a guard that the data file exists and names the server's source files before it reads 0% as a verdict.
   - Docs: `[run] sigterm = true` writes data on SIGTERM, but "On Windows, this setting has no effect" (https://coverage.readthedocs.io/en/7.17.4/config.html, fetched). `coverage run --save-signal=SIGBREAK` on Windows was rejected: valid choices are `USR1` and `USR2` (meant for servers that never end: https://coverage.readthedocs.io/en/7.17.4/subprocess.html). Neither option was run on Linux or macOS.
   - Marks: code run; docs fetched; not retracted; not preprints; 0 citations; trial and docs agree
   - Grade: high (measured plus maintainer docs)

12. **A child process is not measured unless coverage is told; the missing child reads as an unreached diff** (confidence: high)
   - Parent runs `subprocess.run([sys.executable, "child.py"])`; the child imports the changed `lib.py`. `coverage run parent.py` alone: `lib.py (0.0%): Missing lines 2,4-5,7-8`, child output normal, no warning. Wall 0.46 s.
   - With `.coveragerc` `[run] patch = subprocess`, `source = .`, a `data_file`: two parallel data files (one per process), `coverage combine` merged them, diff-cover gave `lib.py (80.0%): Missing lines 8`. Wall 0.75 s against 0.17 s with no coverage.
   - Docs: `patch = subprocess` was added in coverage 7.10; it covers `subprocess`, `os.system`, `execv` and `spawnv` started from the measured process, sets `parallel = True`, so combining before reporting is required (https://coverage.readthedocs.io/en/7.17.4/config.html). Python processes only.
   - Marks: code run; docs fetched; not retracted; not preprints; 0 citations; trial and docs agree
   - Grade: high (measured plus maintainer docs)

13. **A hook launched by a host, with no measured Python parent, needs the `.pth` plus `COVERAGE_PROCESS_START` route; it worked through a shell wrapper** (confidence: medium)
   - Compass hooks are shell command strings ending in `python3 .claude/cli/compass <name> --hook` (`plugin/hooks/hooks.json:13`, `:37`, `:84`, `:108`), started by Claude Code, so no measured parent exists for `patch = subprocess` to hook.
   - Stand-in: `sh hookwrap.sh <venv python>` piping JSON into `python child.py`. With a `zz_cov.pth` holding `import coverage; coverage.process_startup()` in the venv site-packages and `COVERAGE_PROCESS_START=<absolute path to an rc with parallel = true>` in the environment: one data file, diff-cover `lib.py (80.0%): Missing lines 8`. Wall 0.52 s against 0.33 s without. Variable unset: no data file, no message (silent miss).
   - Docs describe the same two steps and say the `.pth` file "must go in a system-defined directory, so you may need extra permissions" (https://coverage.readthedocs.io/en/7.17.4/subprocess.html). The scratch run used a venv, so no permission was needed.
   - Not tested: a real Claude Code hook launch inheriting the variable, and whether the `python3` found first on PATH is the interpreter carrying the `.pth` (the hook command prefers `python3`, falls back to `python`, `hooks.json:13`).
   - Marks: code run on a stand-in, docs fetched; not retracted; not preprints; 0 citations; trial and docs agree on mechanism; real host untested
   - Grade: medium (measured on a stand-in)

14. **Pooled Python workers need `concurrency = multiprocessing`; without it they are missed silently** (confidence: high)
   - `multiprocessing.Pool` worker calling `lib.hook_new()`: default config `lib.py 50% Missing 2, 5, 8` (worker line 5 missed); with `concurrency = multiprocessing`, `parallel = true` and combine: `67% Missing 2, 8` (worker line counted). Docs add that the pool must be closed and joined or the child "won't record" its data (https://coverage.readthedocs.io/en/7.17.4/subprocess.html).
   - `patch = fork`, `_exit` and `execv` exist for other process endings; `execv` is "Not available on Windows" (config page). Pre-fork gunicorn or uvicorn workers were not run.
   - Marks: code run; docs fetched; not retracted; not preprints; 0 citations; trial and docs agree
   - Grade: high for Pool, low for ASGI/WSGI servers (not run)

15. **JS/TS: c8 on a Node server works the same way, children inherit measurement through the environment, and function coverage shows what line coverage hides** (confidence: high)
   - `c8 --reporter=lcov --include=app.js node server.js <port>` plus an HTTP client and `/shutdown`: 0.70 s against 0.27 s bare; setup `npm i -D c8` (2.3 s here). diff-cover read c8's `lcov.info`: `app.js (100%)`.
   - The seeded dead function was a one-line arrow assigned at load (`exports.routeDead = (x) => ...`): its line runs at module load, so line coverage called the diff fully covered while LCOV `FNDA:0,exports.routeDead` named it unreached. diff-cover reads only `DA` records. A multi-line version showed the dead body as `DA:5,0`. A one-line-function blind spot belongs to any line-based intersection in any language.
   - Children: `spawnSync(process.execPath, ["child.js"])` under c8 and `c8 sh -c "node child.js"` both recorded the child's call (`FNDA:1,exports.routeNew`) with no extra setup, since c8 sets `NODE_V8_COVERAGE`, which child Node processes inherit. A non-Node child in the chain is not measured by it.
   - Marks: code run; not retracted; not preprints; 0 citations; 1 trial each
   - Grade: high (measured)

16. **UI action: Playwright `page.coverage` measures only browser JS and CSS, Chromium only; the server side needs its own coverage; combined 1.9 s** (confidence: medium)
   - Docs: "Coverage APIs are only supported on Chromium-based browsers"; it returns V8 function ranges with counts per script URL, and the page shows conversion to Istanbul via `v8-to-istanbul`; it says nothing about server code (https://playwright.dev/docs/api/class-coverage, fetched).
   - Run: c8 around the Node server, one Playwright script doing `startJSCoverage`, load, click, wait for result, `stopJSCoverage`, then `/shutdown`. Total 1.87 s with Chromium launch. One-time `npm i playwright` 2.8 s, `npx playwright install chromium` 12.1 s. Server side: `FNDA:1,exports.apiNew`, `FNDA:0,exports.apiDead`. Client side: `clickNew [1]`, `clickDead [0]` from V8 ranges.
   - One click reached server code through a real `fetch("/api")`, so one UI action covered a browser function and a server route in one run. Client V8 data was read as raw function counts; it was not converted to LCOV or passed through diff-cover.
   - Marks: code run, docs fetched; not retracted; not preprints; 0 citations; trial and docs agree
   - Grade: medium-high (server side measured end to end, client side raw, conversion not run)

17. **A runnable driver per task is where the cost sits, not the coverage tooling** (confidence: medium)
   - Every working case had a driver written for it: a client script, a shutdown route, a Playwright script. Tooling overhead measured 0.2 to 0.5 s per case; the driver is task-specific work, which an agent would author or take from the task's "Automated verification" command (finding 5).
   - For a UI action with no existing end-to-end test, no driver exists until someone writes it; the plan holds a driver-authoring step or states the task is not covered.
   - Marks: inference from the cases above; 0 citations; 1 source (this pass)
   - Grade: low-medium (inference from measured cases)

### What a plan can rely on, and what stays a stated limitation

| Case | Rely on | Setup | Silent failure | State as limitation |
|---|---|---|---|---|
| Web route, Python | coverage on the server plus HTTP driver plus diff-cover: measured, 0.9 s | venv with coverage and diff-cover; a graceful stop path (route or SIGINT) | killed server: no data file, reads 0% | no `sigterm` handler on Windows; `--save-signal` is USR1/USR2 only |
| Web route, Node | c8 LCOV into diff-cover: measured, 0.7 s | `npm i -D c8` | killed server: no data; one-line functions read as covered | read `FNDA` as well as `DA` |
| UI action | Playwright `page.coverage` plus server coverage in one script: measured, 1.9 s | `playwright` plus `npx playwright install chromium` | non-Chromium browsers give no coverage | client V8 to LCOV to diff-cover untested; a driver must exist |
| Hook-fired subprocess | `.pth` plus `COVERAGE_PROCESS_START` (absolute rc, `parallel`) then `combine`: measured on a stand-in, 0.5 s | `.pth` in the interpreter site-packages | variable unset or wrong interpreter: no data, reads 0% | real host launch not tested |
| Python child of a measured parent | `patch = subprocess`: measured, 0.75 s | `.coveragerc` with `patch`, `source`, `data_file`, then `combine` | parent-only run: child unmeasured, reads 0% | Python children only |
| Python Pool worker | `concurrency = multiprocessing`, `parallel`, `combine` | rc file | default config: worker unmeasured | pre-fork ASGI/WSGI not run |

### Contradictions

- Finding 2 treats diff-cover as language-neutral, which holds for the report format; findings 11, 12 and 15 show the report can be a false 0% or a false 100% when the measurement step (killed server, unmeasured child, one-line function) fails upstream of it. The format is neutral, the measurement is not uniform.

### Gaps

- A real Claude Code hook launch (inheritance of `COVERAGE_PROCESS_START`, which `python3` runs): only a shell stand-in ran.
- Client-side V8 data converted to LCOV and passed through diff-cover: not run.
- Linux and macOS behavior of `sigterm = true` and `--save-signal`: read from docs, not run (host was Windows).
- Pre-fork ASGI/WSGI servers (gunicorn, uvicorn workers) and `patch = fork`: not run.
- Hot-reload or bundler front ends (Vite, webpack dev server, Next.js): not run; source maps would sit between V8 ranges and diff lines.
- Istanbul instrumentation (`nyc`, babel plugin) as an alternative to V8 coverage: not run.
