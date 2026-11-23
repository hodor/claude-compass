# Overhead harness

Repo-local tooling that measures how many tokens Compass adds to a real build. Not part of the plugin distribution; nothing here writes to `../../plugin/`.

## Modules

| File | Purpose |
|---|---|
| `sandbox.py` | Throwaway projects under a projects root: `new`, `list`, `keep PROJECT --to DIR`, `discard PROJECT [--config-dir DIR]`. |
| `launch.py` | One isolated headless `claude -p` session; reads `stream-json` and classifies the end as `done`, `failed` or `usage-limit`. |
| `records.py` | Counts a session's tokens, adds list-price weights, appends one allowlisted row to the private records. |
| `variants.py` | `make <part>` creates a git worktree of HEAD with `variants/<part>.patch` applied and committed and prints its path; `discard <part>` removes it. |
| `pilot.py` | The pilot: probe, frozen topics, judged builds, report; `--arms` and `--topics` replay pool topics in chosen arms, variants included. |
| `token_profile.py` | Where a build's tokens go, read from its session transcripts; `--by-agent` prints the mean and median weighted tokens per launch of each subagent type and each source family's share; `--json` saves the profile. |
| `compare.py` | `compare.py BEFORE AFTER`: per agent type, the mean weighted tokens per launch in two folders of saved profiles, the change and a bootstrap 95% interval over sessions (fixed seed). |
| `grade.py` | `prepare` copies four judged pilot builds (two per arm) under neutral names and writes a grading sheet for each; `score` compares the filled sheets with the judge. |
| `attribute.py` | Reconciles each pilot build's run-log total with the sessions' `cost-state` totals and the deduplicated assistant records and names the cause of each gap; lists the attachment kinds that reached the model; rebuilds one session's requests; runs the ablation calls and the console exporter probe; writes the report section and discards the pilot projects. |
| `probe.py` | Ground-truth probes over recorded compaction points: `find`, `build`, `ask`, `grade`, `report`. |
| `tests/` | pytest suite. `tests/fake_claude.py` replays canned `stream-json` in place of `claude`. |

Standard library only. Run the suite from the repository root:

```bash
python -m pytest bench/overhead/tests -q -p no:cacheprovider
```

## Projects

`sandbox.py` keeps projects in `C:\compass-overhead\projects` on Windows and `/var/tmp/compass-overhead/projects` elsewhere (`--projects-root` overrides). `new` refuses a root that has a `CLAUDE.md` in it or in any folder above it, since that file would load into every session below, and a root that holds entries but no marker. A project is a folder named `proj-` and six hexadecimal digits, its own git repository.

`keep` and `discard` act only on a project folder that is a direct child of a projects root: a folder holding the marker `new` writes, and the named root when `--projects-root` is given. A link is refused. Anything else is refused before the disk is touched. `discard` deletes the folder (read-only git objects included) and runs `claude purge <path> --yes` under the sandbox Claude config.

## Isolation

Every session runs with:

- `CLAUDE_CONFIG_DIR` set to `<private root>/claude-config` and `--setting-sources project,local --strict-mcp-config`.
- `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, `GH_TOKEN` and `GITHUB_TOKEN` removed from the environment, with every variable that selects another provider, endpoint or model (`ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_*_MODEL`, `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`, `AWS_*`) and the variables that point git at a repository (`GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE` and kin), so a build bills the subscription and acts on its own project.
- `DISABLE_AUTOUPDATER=1`, `PIP_REQUIRE_VIRTUALENV=1`, `GH_CONFIG_DIR` set to an empty sandbox folder and `DSH_HOME` set to a path that does not exist.
- The VS Code and Cursor install folders (matched by whole folder name) removed from `PATH`.

A session starts only when `git status` reports `plugin/` clean (and, with `plugin=True`, present); a `timeout` kills the session's whole process tree; the result carries the repository's HEAD sha. With `plugin=True` the session loads `<repo>/plugin`.

## Ending a session

| Status | Evidence |
|---|---|
| `usage-limit` | a `rate_limit_event` with status `rejected`; or a `result` event with `api_error` `usage_limit_reached`; or exit 1 with empty stdout and a newest project transcript, written since the session started, whose last entry has `isApiErrorMessage` true |
| `done` | exit 0 and the last `result` event is not an error |
| `failed` | anything else |

`subtype` is never consulted, and text is never searched for limit words.

## Records

The private root is `~/.compass/overhead/`. `record_session` appends one row per session to `records/<machine id>.jsonl`, where the machine id is `sensorlib.machine_id()` from `plugin/cli`. A row holds a timestamp, the machine id, role (`build`, `human`, `topic`, `goal`, `judge`), outcome, arm (`compass`, `baseline`, a variant id `compass-minus-<part>` or null), `variant` (the id for a variant arm, else null), `build_model` (the model with the most output tokens over the session, null when no result event arrived), commit id, Claude Code version, result count, summed duration, per-model counts of `input`, `output`, `cache_read` and `cache_write` tokens, a list-price weighted total and the list of unpriced models. No topic, path, prompt, session id or model output is stored. A records folder inside a git work tree is refused.

Counting takes each stretch's last `modelUsage` totals (a stretch ends at a `/clear`, which shows as a new `system/init` event) and sums the stretches. The weight of a token is its list price relative to fresh input of the same model: output 5, cache write 1.25, cache read 0.1 (0.05 for the Opus 5.5 and Sonnet 5.5 families, 0.025 for Fable 5.1 and Mythos 5.1). A model outside the table adds no weight; its tokens are counted and its id appears in `unpriced_models`.

## Variant arms

A variant is Compass with one harness part removed, built under the arm `compass-minus-<part>` (`<part>` is `[a-z][a-z0-9-]*`). Its patch lives in `bench/overhead/variants/<part>.patch`; the first, `post-tester.patch`, removes the post-build and post-merge tester spawns from `plugin/skills/build/SKILL.md` and the "It always runs" line from `plugin/skills/autopilot/SKILL.md`, and keeps the pre-build tester.

```bash
python bench/overhead/variants.py make post-tester      # prints <variants root>/post-tester
python bench/overhead/variants.py discard post-tester
```

`make` creates a detached worktree of HEAD under `~/.compass/overhead/variants/<part>` (`--variants-root` overrides), applies the patch and commits it, so the worktree is one commit above HEAD, its `plugin/` is clean and its HEAD is what `check_plugin_clean` and `pin_commit` use. The repository's own work tree, index, HEAD and `plugin/` are never touched. A part name outside the pattern, a missing or empty patch and a patch that does not apply are refused, and a failed `make` leaves no folder and no worktree registration. Generate a patch with `git diff` against HEAD in a scratch clone, never in this checkout.

`drive.py PROJECT --arm compass-minus-<part> --repo-root <worktree> ...` runs a variant build like a Compass build from that worktree; `--repo-root` is required for a variant arm.

`pilot.py --arms ARM [ARM ...]` names the arms to build (default `compass baseline`). For each variant arm the pilot replaces any worktree left by an earlier run with a fresh one under `<private root>/variants` and passes it to `drive.py` as `--repo-root`. `pilot.py --topics ID [ID ...]` replays pool topics with their frozen goals: no probe, pick or freeze runs, an id outside the pool or without frozen goals is refused before any session, and builds already closed in the run log are not built again, so a variant replay pairs with the Compass builds a first run logged: with a variant arm named, the aggregates read those logged `compass` builds as the variant's pairs even when `compass` is not in `--arms`, without building them again. `make` first prunes stale worktree registrations, so a crash that left one does not block the next `make`.

```bash
python bench/overhead/pilot.py --arms compass compass-minus-post-tester --topics t-1a2b3c4d t-5e6f7a8b
```

`stats.variant_pairs(topics, variant)` pairs run i of the variant with run i of the full Compass arm of the same topic; the pilot's aggregates report each variant's weighted and raw share against Compass over those pairs.

## Comparing launches

`token_profile.py PROJECT --by-agent --json` saves one profile per build, with a `by_agent` table: for each `subagent:<type>` the session count, the mean and median weighted tokens per session, every session's weighted tokens, and the share of each source family. `compare.py BEFORE AFTER` pools the sessions of every profile in each folder and prints, per agent type, the launches and the mean weighted tokens in each set, the change, and a 95% bootstrap interval of the change in the mean (2000 resamples, seed fixed). A type seen in one set only shows no change, and an interval needs two sessions on each side. Agent types that Compass does not ship print as `(other)`.

Pass `--outcomes-before DIR --outcomes-after DIR` to guard the comparison with outcomes. Each folder holds one JSON file per build: a judge verdict (`counts` of goals scored `met`, `partly met`, `not met`) and the build's test result (`recorded.builder_tests`, or a top-level `tests`). When the sets' summed goal counts or test tallies differ, the report prints `outcome differs` and no token comparison.

Add `--margin FRACTION` to replace that exact-equality check with a noninferiority check. The two outcome folders pair their builds by file name (`--outcomes-before` holds the full arm, `--outcomes-after` the variant). Per pair the difference is the share of goal items met in the variant minus the share met in the full arm. The report prints a one-sided 95% bootstrap lower bound of the mean difference (2000 resamples, seed fixed) and the pair count: `not worse` when the bound is strictly above minus the margin, otherwise `worse` and no token comparison. Fewer than two pairs, folders that name different builds, and a margin outside 0 to 1 are refused. Without `--margin` the exact-equality check above applies unchanged.

## Grading by hand

`grade.py prepare` picks two builds per arm from the pilot run log (builds that ended human-done first, and one build stopped by a cap for the Compass arm when there is one), copies each as the judge's copy is made (no `.git`, `.compass`, `.claude`, `CLAUDE.md`, no Compass lines in `.gitignore`) without dependency and cache folders, with the text of every file scrubbed of document ids (`SPEC-`, `TASK-`, `PLAN-`, `ADR-`), `.compass`, `.claude`, `CLAUDE.md` and arm labels, and refuses a project with a file name that shows Compass. The copies are `<private root>/grading/grade-1` to `grade-4`, each with a sheet `grade-N.md` beside it listing the frozen goal items. The map from a name to its build is `<private root>/grading-key.json`; it is read only by `score`. Mark each item `met`, `partly met` or `not met` on its `mark gN:` line, write `yes` or `no` on the `keep:` line, then run `grade.py score`. It refuses a sheet with a blank or unknown mark, compares each mark with the judge's score for the same item, writes the section "Agreement with your grading" into the pilot report (counts only, topics by letter) and prints the projects marked keep. The per-item judge scores come from the verdict files under `<private root>/topics/verdicts/`, matched to the run log's judged events by counts and order.

## Reconciling the records

`attribute.py measure` reads the pilot run log and each build's transcripts and stores aggregates under `<private root>/attribution/result.json`. Per build it sets three totals side by side: the run log's, the sessions' `cost-state` totals, and the sum of assistant records deduplicated by message id over the session, its `subagents/` files and its setup session (capture workers are listed apart). A gap is named when the transcript shows its cause: an unfinished turn (a session killed at a cap writes no `cost-state`, and its last turn never reached a `result` event), an auxiliary request (a model's input and output tokens in `cost-state` that no assistant record carries; inferred when the build wrote no `cost-state` and made web calls), a compaction, or a resume. A build agrees when what remains is within 0.5% of the logged total.

`ablate` runs `claude -p "hi"` in a bare project and in projects holding one Compass file each (a rules file, a skill, an agent definition) and gives each file's real first-request tokens beside its bytes divided by 4; `otel` tries the console OpenTelemetry exporter once; `report` writes the results as one section of the pilot report; `discard` removes every project under the projects root except those named with `--keep`, and only when that section is committed.

## Compaction probes

`probe.py` measures what a compaction keeps. It reads Claude Code transcripts (never writes them) and stores everything under `<private root>/probes/`, a folder refused inside a git work tree. Its transcript readers are its own code, apart from `plugin/cli/sessionslib.py`, so the readers that build the carried session state never grade it. A POINT is `<transcript path>#<boundary line index>`.

| Command | What it does |
|---|---|
| `--private-root DIR find --project-dir DIR` | Lists the compaction points of a project folder, its session transcripts and the subagent transcripts under each session's `subagents/` folder: POINT, trigger, pre tokens, post tokens (tab separated). A point's history is the records on its boundary's side, so a subagent transcript, whose records are all sidechain records, builds from its own records. |
| `build POINT` | Freezes the probe set from the history before the boundary: the edited paths (`artifact`, with `expected_recent`, the paths edited after the last earlier boundary on the point's side, or all of them when there is none), up to two literals from failing tool results (`recall`: the last exception line and the last `N failed` count), the last `TASK-N` or `PLAN-N` id the assistant named (`continuation`), and the last `AskUserQuestion` with the option chosen (`decision`). A probe with no source is absent. A second build of a point is refused, except for a key frozen without `expected_recent`: that build adds the field and changes nothing else. |
| `ask POINT --arm host-summary\|none` | Runs one `--tools ""` session on the point's model in a fresh sandbox project. `host-summary` carries the `isCompactSummary` record after the boundary; `none` carries nothing. The reply and the session's token counts are stored. |
| `grade POINT` | Scores each stored reply: artifact precision and recall over normalized paths (`./` and slash direction ignored, a reply path below the point's working folder read relative to it, the folder frozen in the key or read from the transcript), the same reply scored again as `artifact-recent` against `expected_recent` (no score when that set is empty), continuation by exact id, decision by normalized whole-word substring, and recall by normalized substring. A recall literal of the form `<Name>: <message>` scores 1 when the reply holds `<Name>` as a whole word and the first clause of the message, which is the message up to its first `,`, `;`, `: ` (a colon followed by a space or ending the message; one inside a token such as `C:\data` does not end it), ` (` or ` - ` (a message with none of these must appear whole); the `N failed` literal is matched as a count, so `13 failed` never matches `3 failed`. A reply that is no JSON object scores 0 everywhere and counts as unparsed. |
| `report` | A markdown table per arm and probe type: points, mean score, unparsed points of the arm, and mean carried tokens (a session's input-side tokens minus the `none` arm's at the same point). Its probe types are `artifact`, `artifact-recent`, `recall`, `continuation`, `decision` and `state`; `state` is, per point, the mean of its recall, continuation and decision scores (the three types are too scarce for an interval of their own) and is absent for a point with none of them. One more table per arm other than `host-summary` follows, after a blank line: for each probe type, the points graded in both arms, the mean of (arm score minus `host-summary` score) over them, and its 95% paired bootstrap interval (resampling points with replacement, `compare.SEED` and `compare.RESAMPLES`). Under 10 pairs the interval reads `too few points`. The report holds no path, prompt, id or answer text. |

Exit status is 0, 1 for a session that did not end `done`, 2 for a refusal or a bad argument.
