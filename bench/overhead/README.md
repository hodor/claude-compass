# Overhead harness

Repo-local tooling that measures how many tokens Compass adds to a real build. Not part of the plugin distribution; nothing here writes to `../../plugin/`.

## Modules

| File | Purpose |
|---|---|
| `sandbox.py` | Throwaway projects under a projects root: `new`, `list`, `keep PROJECT --to DIR`, `discard PROJECT [--config-dir DIR]`. |
| `launch.py` | One isolated headless `claude -p` session; reads `stream-json` and classifies the end as `done`, `failed` or `usage-limit`. |
| `records.py` | Counts a session's tokens, adds list-price weights, appends one allowlisted row to the private records. |
| `token_profile.py` | Where a build's tokens go, read from its session transcripts; `--by-agent` prints the mean and median weighted tokens per launch of each subagent type and each source family's share; `--json` saves the profile. |
| `compare.py` | `compare.py BEFORE AFTER`: per agent type, the mean weighted tokens per launch in two folders of saved profiles, the change and a bootstrap 95% interval over sessions (fixed seed). |
| `grade.py` | `prepare` copies four judged pilot builds (two per arm) under neutral names and writes a grading sheet for each; `score` compares the filled sheets with the judge. |
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

The private root is `~/.compass/overhead/`. `record_session` appends one row per session to `records/<machine id>.jsonl`, where the machine id is `sensorlib.machine_id()` from `plugin/cli`. A row holds a timestamp, the machine id, role (`build`, `human`, `topic`, `goal`, `judge`), outcome, arm (`compass`, `baseline` or null), commit id, Claude Code version, result count, summed duration, per-model counts of `input`, `output`, `cache_read` and `cache_write` tokens, a list-price weighted total and the list of unpriced models. No topic, path, prompt, session id or model output is stored. A records folder inside a git work tree is refused.

Counting takes each stretch's last `modelUsage` totals (a stretch ends at a `/clear`, which shows as a new `system/init` event) and sums the stretches. The weight of a token is its list price relative to fresh input of the same model: output 5, cache write 1.25, cache read 0.1 (0.05 for the Opus 5.5 and Sonnet 5.5 families, 0.025 for Fable 5.1 and Mythos 5.1). A model outside the table adds no weight; its tokens are counted and its id appears in `unpriced_models`.

## Comparing launches

`token_profile.py PROJECT --by-agent --json` saves one profile per build, with a `by_agent` table: for each `subagent:<type>` the session count, the mean and median weighted tokens per session, every session's weighted tokens, and the share of each source family. `compare.py BEFORE AFTER` pools the sessions of every profile in each folder and prints, per agent type, the launches and the mean weighted tokens in each set, the change, and a 95% bootstrap interval of the change in the mean (2000 resamples, seed fixed). A type seen in one set only shows no change, and an interval needs two sessions on each side. Agent types that Compass does not ship print as `(other)`.

Pass `--outcomes-before DIR --outcomes-after DIR` to guard the comparison with outcomes. Each folder holds one JSON file per build: a judge verdict (`counts` of goals scored `met`, `partly met`, `not met`) and the build's test result (`recorded.builder_tests`, or a top-level `tests`). When the sets' summed goal counts or test tallies differ, the report prints `outcome differs` and no token comparison.

## Grading by hand

`grade.py prepare` picks two builds per arm from the pilot run log (builds that ended human-done first, and one build stopped by a cap for the Compass arm when there is one), copies each as the judge's copy is made (no `.git`, `.compass`, `.claude`, `CLAUDE.md`, no Compass lines in `.gitignore`) without dependency and cache folders, with the text of every file scrubbed of document ids (`SPEC-`, `TASK-`, `PLAN-`, `ADR-`), `.compass`, `.claude`, `CLAUDE.md` and arm labels, and refuses a project with a file name that shows Compass. The copies are `<private root>/grading/grade-1` to `grade-4`, each with a sheet `grade-N.md` beside it listing the frozen goal items. The map from a name to its build is `<private root>/grading-key.json`; it is read only by `score`. Mark each item `met`, `partly met` or `not met` on its `mark gN:` line, write `yes` or `no` on the `keep:` line, then run `grade.py score`. It refuses a sheet with a blank or unknown mark, compares each mark with the judge's score for the same item, writes the section "Agreement with your grading" into the pilot report (counts only, topics by letter) and prints the projects marked keep. The per-item judge scores come from the verdict files under `<private root>/topics/verdicts/`, matched to the run log's judged events by counts and order.
