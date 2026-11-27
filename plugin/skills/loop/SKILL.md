---
name: loop
description: Create a control loop with the human, step by step from the end state to a dry run - sensor, dampener, controller, actuator, schedule, human review and flow control - reading the repository before asking and trying every part on its own before the loop is activated.
version: 1.0.0
allowed-tools: [Read, Grep, Glob, Bash, Write, Edit, AskUserQuestion]
when_to_use: "Use when the human wants work to run as a control loop that measures itself and stops on its own. Triggers: 'make a loop', 'create a control loop', 'set up a loop', 'keep driving X down', 'automate this until it is done'."
argument-hint: "[what the loop should achieve]"
---

# Loop - Guided Creation

A control loop is a folder `.compass/loops/LOOP-NNN-name/` that `compass loop run` drives through a state machine: sense the gap, pick one small piece of work, let an agent do it, sense again, and classify the change as helpful, neutral or harmful. This skill walks the human from an end state to a dry run, one step at a time.

`compass` below stands for `python3 .claude/cli/compass` (`python .claude/cli/compass` where `python3` is absent).

## How every step runs

- **Read before asking.** Each step first reads the repository (code, tests, CI files, the vault) for what answers it. The human is asked only what the code cannot answer, through `AskUserQuestion`, exactly one question per call, the recommended option first and labelled "(Recommended)".
- **Write as you go.** `compass loop new <name>` scaffolds the folder; the skill fills its documents and `loop.json`. Each step writes its choice into the matching `## Step N` section of the loop's `index.md` in a sentence or two, and the machine form into `loop.json`, `actuator.md`, `golden/` or `feedback.md`.
- **Defaults live in the template.** `.claude/cli/loop_templates/loop.json` holds every default. Read it there; a key the human does not decide keeps its template value.
- **Caps.** Each iteration is a fresh session, never a resume. `max_turns` bounds the actuator's tool rounds: cap N allows N tool rounds. `max_budget_usd` bounds one run and can be overshot by one response; the daily and total budgets catch the rest.
- A step is finished only when its `Done when:` line holds. Check it before moving on.

## Step 0: End state

Ask what is true of the project when the loop is finished, phrased so a reader could check it ("no file imports the legacy client", "every public function has a docstring"). Read the repository for the code the end state is about. Create the folder with `compass loop new <name>`, then write the end state into step 0 of the loop's `index.md` and the `## End state` of `actuator.md`, and set the index `summary:`.

**Done when:** the loop folder exists, its index step 0 names a checkable end state, and its `summary:` states it.

## Step 1: Sensor

The sensor is a command run from the project root that prints `{"valid": true, "value": <number>, "items": [<identities>]}`. An item names a file and the matched text, never a line number, so it survives unrelated edits.

- **A structural code pattern** (a call, an import, a missing docstring): draft an ast-grep rule with the ast-grep author's recipe. Restate what the rule allows and forbids; write a sample snippet holding violations and near-misses that must not match; write the rule (`id`, `language`, `rule`, `severity: error`, `message`) into the loop folder; test it against the snippet with `ast-grep scan --rule <file> <snippet>`, revising at most three times; then scan the repository once. Show the human the match count and a sample of the matches, and revise until he confirms they are what he means. Wire it as `sensor_command`: `python .claude/cli/compass loop sense-ast-grep --rule .compass/loops/LOOP-NNN-name/<rule file>` (add `--bin <path>` when `ast-grep` is not on PATH; it is installed with `pip install ast-grep-cli` inside a virtual environment, never into the system Python, after asking the human).
- **Anything else:** ask the human for the rule, then write a small script beside `loop.json` that prints the reading.
- **Nothing evident measures the gap:** run `/compass:research` with the end state as the question, to find what can.

A judge sensor, an agent reading rules written in plain language, may be offered as an advisory reading only, always beside a deterministic sensor: its findings reach the run row and the next actuator prompt and never stop the loop or decide a run's outcome. It is configured as the `judge` object in `loop.json` with its rules in `judge-rules.md`, one `- R<n>: text` bullet per rule.

Set `target` (the value at which the loop is done) and `direction` (`down` or `up`).

**Done when:** run the sensor command alone from the project root and it prints a valid reading whose items the human recognises, and `target` and `direction` are set in `loop.json`.

## Step 2: Stabilize (dampener)

Stop the problem from growing while the loop works. `compass loop baseline LOOP-NNN` commits today's items to `baseline.json`; `compass loop check LOOP-NNN` lists the items new since the baseline and the items fixed. The check is advisory; `--blocking` makes it exit 1 on a new item. Read the CI configuration and ask where the check should run (a CI step, a pre-commit hook, or by hand).

**Done when:** `baseline.json` exists, `compass loop check LOOP-NNN` lists no new item, and the index step 2 says where the check runs.

## Step 3: Controller

The controller picks the next small piece of work. `first` takes the first sorted item that no unreviewed increment holds; `command` runs a `controller_command` script whose output is the piece, for example the smallest file or the most-failing test. Ask what makes a piece small and low-risk here.

**Done when:** `controller` is set in `loop.json`, and for `command` the script runs alone and prints one piece of work.

## Step 4: Actuator

The actuator is a headless agent session given `actuator.md`, then the golden patterns, then the controller's pick, then `feedback.md`. Fill `actuator.md`: how to do one piece of work, how to check it, and what never to touch. Write at least one hand-made before/after pair into `golden/` from a real example in the repository, replacing the template file. Set `model`, `allowed_tools` (a headless session denies every tool not listed) and the caps.

**Done when:** `actuator.md` and `golden/` hold no template text, and `allowed_tools` names every tool the instructions need.

## Step 5: Schedule

What runs `compass loop run LOOP-NNN`, and how often? `compass loop schedule LOOP-NNN --github [--cron EXPR]` writes a GitHub Actions workflow that installs Compass, runs one iteration, opens a pull request for the increment and keeps the ledger on the default branch; `compass loop schedule LOOP-NNN --local` prints the line for a local scheduler. A person running it by hand is also a schedule.

**Done when:** the index step 5 names the schedule, and for `--github` the workflow file exists and the human has the secrets it printed.

## Step 6: Human on the loop

Every run that reaches a verdict leaves an increment awaiting review. `compass loop review LOOP-NNN <run-id> accept|reject --reason "..."` records the verdict, and a reject reason becomes a line of `feedback.md`, which every run reads. Write the human's standing guidance into the `## Guidance` list of `feedback.md`, and ask who reviews and how often.

**Done when:** `feedback.md` holds the guidance the human gave, and the index step 6 names the reviewer and the review rhythm.

## Step 7: Flow control

Set how much unreviewed work may pile up (`wip_limit`), how much the loop may spend per UTC day (`daily_budget_usd`) and in total (`total_budget_usd`), and after how many failed, harmful or unproductive runs it halts (`max_actuator_failures`, `max_harmful_runs`, `max_runs_without_help`). A loop that runs unsupervised or spends real money gets limits the human states; a cheap loop run by hand may keep the template's.

**Done when:** every budget and limit in `loop.json` is one the human chose or accepted.

## Before activating

Fill every field the template leaves empty. Then, in this order:

1. Run the sensor command alone from the project root; it prints a valid reading.
2. `compass loop baseline LOOP-NNN` succeeds.
3. `compass loop run LOOP-NNN --dry-run` prints the assembled prompt; read it for anything missing or wrong.

Only then run `compass loop activate LOOP-NNN`. Every warning it prints names a part still unfilled: treat it as a step left undone, go back to that step, and activate again until no warning remains. `compass loop status LOOP-NNN` shows the state afterwards.

For animation work, [maya-recipe.md](maya-recipe.md) maps each step to a shot in Maya.
