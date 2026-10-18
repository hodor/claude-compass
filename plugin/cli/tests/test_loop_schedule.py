"""Tests for `compass loop schedule`, `compass loop reconcile` and
`compass loop status LOOP-NNN --last-run`.

Contract choices these tests pin (the task leaves each open):

* The project root is the parent of the vault root (`.compass/`), found from
  `CLAUDE_PROJECT_DIR`; the working directory plays no part. Every test runs
  with the working directory set to an unrelated scratch folder.
* `schedule` takes exactly one of `--github` / `--local`. A missing or
  repeated lane, an unknown option, a `--cron` without a value, an unknown or
  missing loop id: exit 1, nothing written anywhere.
* `--cron EXPR` is five whitespace-separated fields with no quote, backslash
  or line break; anything else is exit 1 and nothing is written. The rendered
  `cron:` value is always a quoted scalar (a bare `*` opens a YAML alias).
* `schedule --github` needs a `repository:` line in `.compass/meta/plugin.yaml`;
  a missing file or missing key is exit 1 and nothing is written. The URL is
  either rendered into the workflow or read from `plugin.yaml` inside the
  install step; a URL hard-coded to this repository is a failure. Python comes
  from `actions/setup-python`, Claude Code from the npm package or
  `claude.ai/install`.
* An identical existing workflow is exit 0 with "unchanged" on stdout. A
  different one is exit 1 and nothing else is written, `.gitattributes`
  included. A missing `.gitattributes` is created holding the one line.
* Every `secrets.NAME` the workflow reads (other than `GITHUB_TOKEN`) appears
  on stdout. The `gh pr list --label compass-loop-LOOP-NNN --state open` line
  is printed when `wip_command` is missing or an empty string, and not when it
  holds a command. `loop.json` is never edited, and a draft loop (no sensor)
  schedules without a warning.
* The workflow's steps are located by content, not by name, and ordered by
  line number: install = the `self-update` line; existence check = the first
  later line naming `.claude/cli/compass` without `loop ` or `self-update`;
  snapshot = `git status --porcelain`; reconcile = `loop reconcile`; run =
  `loop run`; increment = `gh pr create`; state commit = the first `git add`
  naming `state.json`. The YAML is read line by line, because the standard
  library has no YAML parser: a step starts at a `- ` line at the step list's
  indent, and its block runs to the next such line. Backslash-continued shell
  lines are joined before matching.
* Every step that runs `gh` carries `GH_TOKEN` in its block or above `steps:`;
  `gh label create compass-loop-LOOP-NNN` runs before `gh pr create`; the
  `gh pr list` that feeds reconcile asks for `--state all` and for the loop's
  label or a limit of at least 100.
* `schedule --local` reads the operating system from `sys.platform` at call
  time (`win32` prints one `schtasks /Create` line, anything else one crontab
  line), needs no `plugin.yaml`, and prints the scheduler line on its own line.
  That line creates the log's directory (`mkdir`) before the redirect opens
  it, and the Desktop phrasing follows a line containing "Desktop".
* `reconcile LOOP-NNN --prs <file|->` prints one stdout line per pull request
  it decides or skips on this loop's branches, containing `#<number>`; a
  skipped one also contains "skip". Exit 0 whenever the input is well formed,
  even if nothing applies. Input is validated before anything is written: a
  non-list, a non-object entry, a non-string `headRefName`, a non-integer
  `number` or a `state` outside OPEN, CLOSED and MERGED is exit 1 with nothing
  applied. A UTF-8 BOM is tolerated. A run is decided at most once however many
  pull requests name its branch. A live run lock is exit 1 and changes nothing.
* `status LOOP-NNN --last-run` (flag in either position) needs an id and
  prints exactly `<run-id> <outcome>` of the last run row in file order, or
  exits 1 with empty stdout when there is none.

Adversarial themes: refusals that still half-write, branch names that match by
prefix or suffix, a second pass that repeats the first, a workflow that runs
before it is installed, and a scheduler line whose redirect cannot open its
file.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CLI_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import looplib  # noqa: E402
import maincli  # noqa: E402
from test_loop_command import LoopCommandCase, snapshot  # noqa: E402

COMPASS = os.path.join(CLI_DIR, "compass")
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gh_pr_list.json"

TARGET = "LOOP-003"
UNION_LINE = ".compass/loops/*/ledger.jsonl merge=union"
REPOSITORY = "https://github.com/acme-labs/compass-fork-7q"
PLUGIN_YAML = (
    "plugin:\n"
    "  name: compass\n"
    "  version: 7.4.2\n"
    "  commit: 0123456789abcdef0123456789abcdef01234567\n"
    "  source: /somewhere/else/plugin\n"
    f"  repository: {REPOSITORY}\n"
    "  installed_mode: auto-update\n"
)
WORKFLOW_PATH = Path(".github") / "workflows" / f"compass-loop-{TARGET}.yml"
WIP_LINE = f"gh pr list --label compass-loop-{TARGET} --state open"
CRON_FIELDS = r"\s*[\d*/,\-]+(\s+[\d*/,\-]+){4}\s+\S"

# The fixture's pull requests (fixtures/gh_pr_list.json) sit on LOOP-001's branches.
RECONCILED = "LOOP-001"
RUN_MERGED = "RUN-20261010T060012345678Z"
RUN_CLOSED = "RUN-20261011T060023456789Z"
RUN_OPEN = "RUN-20261012T060034567890Z"
PR_CLOSED, PR_OPEN, PR_UNKNOWN = 14713, 14727, 14714
CLOSED_REASON = f"pull request #{PR_CLOSED} closed without merge"


def norm(text):
    return text.replace("\\", "/").lower()


def code_lines(text):
    """(index, line) of every line that is not blank or a whole-line comment."""
    return [
        (i, line)
        for i, line in enumerate(text.split("\n"))
        if line.strip() and not line.strip().startswith("#")
    ]


def logical_lines(text):
    """(index of the first physical line, text) of every code line, with
    backslash-continued lines joined onto the line that starts them."""
    result, pending, start = [], "", None
    for i, line in code_lines(text):
        if not pending:
            start = i
        if line.rstrip().endswith("\\"):
            pending += line.rstrip()[:-1] + " "
            continue
        result.append((start, pending + line))
        pending = ""
    if pending:
        result.append((start, pending))
    return result


def first_line(text, match, after=-1):
    """Index of the first logical line after `after` that `match` accepts (a
    regex pattern, or a predicate on the line), or None."""
    accepts = match if callable(match) else (lambda line: re.search(match, line) is not None)
    for i, line in logical_lines(text):
        if i > after and accepts(line):
            return i
    return None


def is_existence_check(line):
    """A line that names the installed CLI without running a loop command or
    the update."""
    return ".claude/cli/compass" in line and "loop " not in line and "self-update" not in line


def split_steps(text):
    """Line-based reading of every `steps:` list: [(first, last_exclusive,
    name, block)]. A step starts at a `- ` line at the list's indent."""
    lines = text.split("\n")
    steps = []
    i = 0
    while i < len(lines):
        header = re.match(r"^(\s*)steps:\s*$", lines[i])
        if not header:
            i += 1
            continue
        base = len(header.group(1))
        end = len(lines)
        dash = None
        starts = []
        for j in range(i + 1, len(lines)):
            stripped = lines[j].strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(lines[j]) - len(lines[j].lstrip())
            if dash is None and stripped.startswith("- "):
                dash = indent
            if indent < base or (indent == base and not stripped.startswith("- ")):
                end = j
                break
            if dash is not None and indent == dash and stripped.startswith("- "):
                starts.append(j)
        for k, start in enumerate(starts):
            stop = starts[k + 1] if k + 1 < len(starts) else end
            block = "\n".join(lines[start:stop])
            named = re.search(r"^\s*(?:-\s+)?name:\s*(.+?)\s*$", block, re.M)
            steps.append((start, stop, named.group(1) if named else None, block))
        i = end
    return steps


def step_of(steps, index):
    """The block of the step holding line `index`, or None."""
    for first, stop, _name, block in steps:
        if first <= index < stop:
            return block
    return None


def step_start(steps, index):
    for first, stop, _name, _block in steps:
        if first <= index < stop:
            return first
    return -1


def joined_code(block):
    return " ".join(line for _i, line in logical_lines(block))


class ScheduleCase(LoopCommandCase):
    """A scratch project with three loops (`LOOP-003` is the target) and a
    working directory that is not the project."""

    def setUp(self):
        super().setUp()
        self.elsewhere = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.elsewhere, True)
        previous = os.getcwd()
        os.chdir(self.elsewhere)
        self.addCleanup(os.chdir, previous)
        (self.root / "meta" / "plugin.yaml").write_text(PLUGIN_YAML, encoding="utf-8", newline="\n")
        for name in ("alpha", "beta", "gamma"):
            self.new_loop(name)
        self.folder = self.folder_for("gamma")
        self.assertTrue(self.folder.name.startswith(TARGET))

    def schedule(self, *args):
        return self.loop("schedule", TARGET, *args)

    def render(self, *extra):
        code, _out, err = self.schedule("--github", *extra)
        self.assertEqual(code, 0, err)
        path = self.project / WORKFLOW_PATH
        self.assertTrue(path.is_file(), f"{path} was not written")
        return path.read_bytes().decode("utf-8")

    def clear_github(self):
        shutil.rmtree(self.project / ".github", ignore_errors=True)

    def cli_in(self, cwd, *args, stdin=None):
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.project)
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [sys.executable, COMPASS, "loop", *args],
            capture_output=True, text=True, encoding="utf-8", env=env,
            cwd=str(cwd), input=stdin, timeout=120,
        )
        return proc.returncode, proc.stdout, proc.stderr


class WorkflowRenderTests(ScheduleCase):
    def test_workflow_is_lf_complete_and_names_only_its_own_loop(self):
        """Adversarial where: CRLF written on Windows (a Linux runner then
        chokes on every shell line), a placeholder left unreplaced, the loop
        id hard-coded to another loop, or the file written relative to the
        working directory instead of the project root."""
        text = self.render()
        data = (self.project / WORKFLOW_PATH).read_bytes()
        self.assertNotIn(b"\r", data)
        self.assertTrue(data.endswith(b"\n"))
        self.assertNotIn("LOOP-NNN", text)
        self.assertEqual(re.findall(r"(?<!\$)\{\{[^}]*\}\}", text), [])
        self.assertEqual(re.findall(r"__[A-Z][A-Z_]+__|@[A-Z_]+@|<%", text), [])
        self.assertIn(TARGET, text)
        for other in ("LOOP-001", "LOOP-002"):
            self.assertNotIn(other, text)
        self.assertEqual(list(self.elsewhere.iterdir()), [])

    def test_schedule_from_a_subdirectory_writes_under_the_project_root(self):
        """Adversarial where: resolving `.github/workflows` and `.gitattributes`
        against the working directory, so a run from a subfolder scatters
        files outside the repository root."""
        sub = self.project / "deep" / "sub"
        sub.mkdir(parents=True)
        code, _out, err = self.cli_in(sub, "schedule", TARGET, "--github")
        self.assertEqual(code, 0, err)
        self.assertTrue((self.project / WORKFLOW_PATH).is_file())
        self.assertTrue((self.project / ".gitattributes").is_file())
        self.assertEqual(list(sub.iterdir()), [])

    def test_triggers_concurrency_permissions_and_toolchain(self):
        """Adversarial where: a missing `workflow_dispatch` (no manual run), a
        concurrency group shared by every loop or one that cancels a run in
        progress, read-only permissions, a shallow checkout, or no Python or
        Claude Code installed."""
        text = self.render()
        lines = text.split("\n")
        on_at = next(i for i, l in enumerate(lines) if re.match(r"^[\"']?on[\"']?:\s*$", l))
        jobs_at = next(i for i, l in enumerate(lines) if re.match(r"^jobs:\s*$", l))
        for trigger in ("schedule", "workflow_dispatch"):
            with self.subTest(trigger):
                at = first_line(text, rf"^\s+{trigger}:", on_at)
                self.assertIsNotNone(at)
                self.assertLess(at, jobs_at)
        group = re.search(r"^\s*group:\s*(.+?)\s*$", text, re.M)
        self.assertIsNotNone(group)
        self.assertIn(f"compass-loop-{TARGET}", group.group(1))
        self.assertRegex(text, r"(?m)^\s*cancel-in-progress:\s*false\s*$")
        self.assertRegex(text, r"(?m)^\s*contents:\s*write\s*$")
        self.assertRegex(text, r"(?m)^\s*pull-requests:\s*write\s*$")
        checkout = [b for _f, _s, _n, b in split_steps(text) if "actions/checkout" in b]
        self.assertEqual(len(checkout), 1)
        self.assertRegex(checkout[0], r"fetch-depth:\s*0\b")
        self.assertIn("actions/setup-python", text)
        self.assertRegex(text, r"@anthropic-ai/claude-code|claude\.ai/install")

    def test_cron_default_override_and_refusals(self):
        """Adversarial where: an unquoted cron (a `*`-led scalar is a YAML
        alias and the workflow never parses), the override ignored in favour
        of the default, or an expression that closes the quote and injects
        YAML being written instead of refused."""
        default = self.render()
        self.assertEqual(
            [m[1] for m in re.findall(r"""cron:\s*(['"])([^'"]*)\1""", default)], ["0 6 * * *"]
        )
        self.assertNotRegex(default, r"cron:\s*[^'\"\s]")
        self.clear_github()
        custom = self.render("--cron", "*/15 3 * * 1")
        self.assertEqual(
            [m[1] for m in re.findall(r"""cron:\s*(['"])([^'"]*)\1""", custom)], ["*/15 3 * * 1"]
        )
        self.assertNotRegex(custom, r"cron:\s*[^'\"\s]")

        self.clear_github()
        (self.project / ".gitattributes").unlink()
        before = snapshot(self.project)
        refused = {
            "empty": "",
            "four fields": "0 6 * *",
            "six fields": "0 6 * * * *",
            "line break": "0 6 * * *\n  - cron: '* * * * *'",
            "single quote": "0 6 * * *' # ",
            "double quote": '0 6 * * *" #',
        }
        for label, expression in refused.items():
            with self.subTest(label):
                code, _out, err = self.schedule("--github", "--cron", expression)
                self.assertEqual(code, 1)
                self.assertTrue(err.strip())
                self.assertEqual(snapshot(self.project), before)


class WorkflowStepTests(ScheduleCase):
    def test_steps_run_in_the_declared_order(self):
        """Adversarial where: the actuator launching before Compass is
        installed or checked, a snapshot taken after the run (every change the
        run made then counts as already held), reconcile after the run, or
        the state committed before the pull request step."""
        text = self.render()
        install = first_line(text, r"self-update")
        self.assertIsNotNone(install, "no self-update line in the workflow")
        named = dict(
            install=install,
            check=first_line(text, is_existence_check, install),
            snapshot=first_line(text, r"git status --porcelain"),
            reconcile=first_line(text, r"loop reconcile"),
            run=first_line(text, r"loop run"),
            increment=first_line(text, r"gh pr create"),
            state=first_line(text, r"git add\b.*state\.json"),
        )
        for role, at in named.items():
            self.assertIsNotNone(at, f"no {role} line in the workflow")
        order = list(named.values())
        self.assertEqual(order, sorted(set(order)), f"order is {named}")

    def test_install_clones_the_plugin_repository_unpinned_and_updates_first(self):
        """Adversarial where: the install step hard-coding this repository's
        URL instead of `plugin.yaml`'s, cloning a pinned branch or tag
        (updating is mandatory and unpinned), a full-depth clone, a missing
        `--force`, `CLAUDE_PROJECT_DIR` unset (the update then lands outside
        the workspace), or any `claude` or `.claude/cli/compass` line running
        before the update."""
        text = self.render()
        install_at = first_line(text, r"self-update")
        block = step_of(split_steps(text), install_at)
        self.assertIsNotNone(block)
        joined = joined_code(block)
        self.assertRegex(joined, r"git clone\b")
        self.assertRegex(joined, r"--depth[ =]1\b")
        reads_at_run_time = "plugin.yaml" in joined and "repository" in joined
        self.assertTrue(REPOSITORY in joined or reads_at_run_time, joined)
        self.assertNotIn("hodor/claude-compass", text)
        self.assertNotRegex(joined, r"--branch|\s-b\s|--revision|checkout ")
        self.assertRegex(joined, r"plugin/cli/compass[\"']?\s+self-update\b[^\n]*--force")
        self.assertIn("CLAUDE_PROJECT_DIR", block)
        self.assertRegex(block, r"github\.workspace|GITHUB_WORKSPACE")
        for at, line in logical_lines(text):
            if re.search(r"(?<![\w/@.-])claude(?![\w.-])|\.claude/cli/compass", line):
                self.assertLessEqual(install_at, at, f"line {at + 1} runs before the update: {line.strip()}")

    def test_existence_check_fails_the_job_and_the_version_is_logged(self):
        """Adversarial where: `self-update` exiting 0 on a bad repository URL
        and the job going on with no Compass installed (the check absent, or
        present but not failing), or the installed version and commit never
        reaching the log, so a run cannot be traced to the Compass it ran."""
        text = self.render()
        steps = split_steps(text)
        install_at = first_line(text, r"self-update")
        check_at = first_line(text, is_existence_check, install_at)
        self.assertIsNotNone(check_at)
        self.assertRegex(step_of(steps, check_at), r"exit 1|test -[fxe]|\[\[? .*-[fxe] ")
        run_at = first_line(text, r"loop run")
        logged = [
            block for first, _stop, _name, block in steps
            if step_start(steps, install_at) <= first < run_at
            and "plugin.yaml" in block and "version" in block and "commit" in block
        ]
        self.assertTrue(logged, "no step between install and run prints plugin.yaml's version and commit")

    def test_run_is_invoked_once_and_reconcile_sees_every_pull_request_state(self):
        """Adversarial where: two `loop run` lines (two iterations a run),
        `--resume` resuming a session instead of a fresh one, a `gh pr list`
        that omits `--state all` (merged and closed pull requests never reach
        reconcile) or can lose the loop's pull requests to the default limit
        of 30, or a bare `compass` that is not on the runner's PATH."""
        text = self.render()
        runs = [l for _i, l in logical_lines(text) if "loop run" in l]
        self.assertEqual(len(runs), 1, runs)
        self.assertIn(TARGET, runs[0])
        self.assertNotIn("--resume", text)

        reconcile_at = first_line(text, r"loop reconcile")
        joined = joined_code(step_of(split_steps(text), reconcile_at))
        self.assertIn(f"reconcile {TARGET}", joined)
        self.assertIn("--prs", joined)
        listing = re.search(r"gh pr list\b[^|;&]*", joined)
        self.assertIsNotNone(listing, joined)
        listing = listing.group(0)
        self.assertRegex(listing, r"--state[ =]['\"]?all\b")
        fields = re.search(r"--json[ =]['\"]?([\w,]+)", listing)
        self.assertIsNotNone(fields, listing)
        self.assertEqual(set(fields.group(1).split(",")), {"number", "headRefName", "state", "mergedAt"})
        limit = re.search(r"--limit[ =](\d+)", listing)
        self.assertTrue(
            re.search(rf"--label[ =]['\"]?compass-loop-{TARGET}\b", listing)
            or (limit is not None and int(limit.group(1)) >= 100),
            listing,
        )

        run_at = first_line(text, r"loop run")
        on_path = first_line(text, r"PATH.*\.claude/cli|\.claude/cli.*PATH")
        self.assertTrue(
            ".claude/cli/compass" in runs[0] or (on_path is not None and on_path < run_at),
            "the run line is neither a path to the installed CLI nor preceded by a PATH entry for it",
        )

    def test_secrets_and_gh_token_reach_the_steps_that_need_them(self):
        """Adversarial where: the API key missing from the run step's
        environment (the actuator fails to authenticate), or a `gh` step with
        no `GH_TOKEN` (gh refuses to run in Actions without it)."""
        text = self.render()
        steps = split_steps(text)
        above = "\n".join(text.split("\n")[: min(s[0] for s in steps)])
        key = re.compile(r"ANTHROPIC_API_KEY:\s*\$\{\{\s*secrets\.ANTHROPIC_API_KEY\s*\}\}")
        run_block = step_of(steps, first_line(text, r"loop run"))
        self.assertTrue(key.search(run_block) or key.search(above))
        for _first, _stop, name, block in steps:
            if re.search(r"(?m)(?:^|[\s|;&(])gh (?:pr|label)\b", block):
                with self.subTest(step=name):
                    self.assertTrue("GH_TOKEN" in block or "GH_TOKEN" in above)

    def test_no_git_command_can_stage_plugin_yaml_dot_claude_or_everything(self):
        """Adversarial where: a `git add` of `.`, `-A`, `-u`, `.compass`,
        `.claude` or `plugin.yaml` (the install rewrote all three, so they
        would ride into the loop's pull request or the state commit), or a
        `git commit -a` that stages them without any add."""
        text = self.render()
        forbidden = {".", "-A", "--all", "-u", "--update", "*", ".compass", ".compass/",
                     ".compass/meta", ".compass/meta/", ".claude", ".claude/"}
        saw_add = False
        for at, line in logical_lines(text):
            for command in re.findall(r"git add\b([^|;&]*)", line):
                saw_add = True
                for token in command.split():
                    token = token.strip("'\"")
                    with self.subTest(line=at + 1, token=token):
                        self.assertNotIn(token, forbidden)
                        self.assertNotIn("plugin.yaml", token)
                        self.assertFalse(token.startswith(".claude/"), token)
            self.assertNotRegex(line, r"git commit\b[^|;&]*\s-[a-zA-Z]*a[a-zA-Z]*(\s|$)")
            self.assertNotRegex(line, r"git commit\b[^|;&]*--all\b")
        self.assertTrue(saw_add)

    def test_pull_request_and_state_commit_protocol(self):
        """Adversarial where: `gh pr create --label` on a label the repository
        does not have (the first run fails), a pull request opened for a run
        that never reached `verifying`, the state committed to the default
        branch without switching back or rebasing, a push refusal that is
        swallowed instead of failing the job, or a fallback branch that does
        not name the loop."""
        text = self.render()
        create = first_line(text, r"gh pr create")
        label = first_line(text, rf"gh label create\b.*compass-loop-{TARGET}")
        self.assertIsNotNone(label)
        self.assertLess(label, create)
        create_line = next(l for i, l in logical_lines(text) if i == create)
        self.assertRegex(create_line, rf"--label[ =]['\"]?compass-loop-{TARGET}\b")
        self.assertIn("--title", create_line)
        self.assertIsNotNone(first_line(text, rf"compass-loop/{TARGET}/(?!state-)"))

        run_at = first_line(text, r"loop run")
        last_run = first_line(text, r"--last-run")
        self.assertIsNotNone(last_run)
        self.assertLess(run_at, last_run)
        gate = first_line(text, r"helpful|neutral|harmful|verifying", last_run)
        self.assertIsNotNone(gate)
        self.assertLess(gate, create)

        switch = first_line(text, r"git (checkout|switch)\b", create)
        self.assertIsNotNone(switch)
        added = " ".join(
            l for i, l in logical_lines(text) if i > switch and re.search(r"git add\b", l)
        )
        for name in ("state.json", "ledger.jsonl", "feedback.md"):
            self.assertIn(name, added)
        self.assertIsNotNone(first_line(text, r"rebase", switch))
        fallback = first_line(text, rf"compass-loop/{TARGET}/state-")
        self.assertIsNotNone(fallback)
        self.assertIsNotNone(first_line(text, r"exit 1|::error", fallback - 1))


class ScheduleOutputTests(ScheduleCase):
    def test_prints_every_secret_and_the_wip_line_only_when_there_is_no_wip_command(self):
        """Adversarial where: a secret the workflow reads but the output never
        names (the human sets up the repository without it), the open-pull-
        request count printed for a loop that already has a `wip_command`, not
        printed for a missing or an empty one, or `loop.json` rewritten."""
        text = self.render()
        secrets_read = set(re.findall(r"secrets\.([A-Z][A-Z0-9_]*)", text)) - {"GITHUB_TOKEN"}
        self.assertIn("ANTHROPIC_API_KEY", secrets_read)
        path = self.folder / "loop.json"
        base = json.loads(path.read_text(encoding="utf-8"))
        cases = {"missing key": (None, True), "empty string": ("", True), "a command": ("echo 2", False)}
        for label, (value, printed) in cases.items():
            with self.subTest(label):
                definition = dict(base)
                definition.pop("wip_command", None)
                if value is not None:
                    definition["wip_command"] = value
                path.write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8", newline="\n")
                before = path.read_bytes()
                self.clear_github()
                code, out, err = self.schedule("--github")
                self.assertEqual(code, 0, err)
                for secret in secrets_read:
                    self.assertIn(secret, out)
                self.assertEqual(WIP_LINE in out, printed, out)
                self.assertEqual(path.read_bytes(), before)

    def test_a_draft_loop_is_scheduled_without_warnings(self):
        """Adversarial where: `schedule` re-running `activate`'s completeness
        check and refusing, or warning about, a draft loop the human has not
        filled in yet."""
        code, _out, err = self.schedule("--github")
        self.assertEqual(code, 0, err)
        self.assertNotIn("warning", err.lower())


class ScheduleFileTests(ScheduleCase):
    def test_existing_workflow_identical_is_unchanged_different_is_refused(self):
        """Adversarial where: a hand-edited workflow overwritten, a refusal
        that still appends the union line to `.gitattributes` first (a half
        write), a different `--cron` regenerating over the file, or an
        identical file reported as written."""
        original = self.render().encode("utf-8")
        workflow = self.project / WORKFLOW_PATH

        code, out, err = self.schedule("--github")
        self.assertEqual(code, 0, err)
        self.assertIn("unchanged", out.lower())
        self.assertEqual(workflow.read_bytes(), original)

        attributes = self.project / ".gitattributes"
        other = b"*.txt text\n"
        edits = {
            "edited by hand": (original + b"# edited\n", []),
            "different cron": (original, ["--cron", "5 4 * * 2"]),
        }
        for label, (content, extra) in edits.items():
            with self.subTest(label):
                workflow.write_bytes(content)
                attributes.write_bytes(other)
                code, _out, err = self.schedule("--github", *extra)
                self.assertEqual(code, 1)
                self.assertTrue(err.strip())
                self.assertEqual(workflow.read_bytes(), content)
                self.assertEqual(attributes.read_bytes(), other)

    def test_gitattributes_gains_the_union_line_once_and_keeps_every_other_line(self):
        """Adversarial where: a file with no trailing newline getting the line
        glued onto its last line, CRLF lines rewritten, the line appended again
        on a second run or when CRLF-terminated, a commented-out copy taken
        for the real line, or an existing file replaced instead of extended."""
        attributes = self.project / ".gitattributes"
        union = UNION_LINE.encode()
        # label: (existing bytes or None, the union line already present)
        existing = {
            "absent": (None, False),
            "no trailing newline": (b"* text=auto eol=lf\n*.png binary", False),
            "crlf lines": (b"* text=auto\r\n*.png binary\r\n", False),
            "commented out copy": (b"# " + union + b"\n", False),
            "present": (b"*.png binary\n" + union + b"\n", True),
            "present with crlf": (b"*.png binary\r\n" + union + b"\r\n*.jpg binary\r\n", True),
        }
        for label, (content, present) in existing.items():
            with self.subTest(label):
                if content is None:
                    attributes.unlink(missing_ok=True)
                else:
                    attributes.write_bytes(content)
                for _pass in range(2):
                    self.clear_github()
                    code, _out, err = self.schedule("--github")
                    self.assertEqual(code, 0, err)
                after = attributes.read_bytes()
                lines = [l.strip() for l in after.decode("utf-8").splitlines()]
                self.assertEqual(lines.count(UNION_LINE), 1, after)
                if content is not None:
                    self.assertTrue(after.startswith(content), after)
                    if present:
                        self.assertEqual(after, content)
                    else:
                        self.assertEqual(after[len(content):].strip(), union)

    def test_invocations_that_name_no_single_lane_write_nothing(self):
        """Adversarial where: both lanes at once, no lane at all, an unknown
        option, a `--cron` with no value, an unknown loop, or a repository
        `plugin.yaml` does not name producing a workflow with an empty or
        placeholder clone URL."""
        before = snapshot(self.project)
        cases = {
            "no id": ["schedule"],
            "no lane": ["schedule", TARGET],
            "both lanes": ["schedule", TARGET, "--github", "--local"],
            "unknown loop": ["schedule", "LOOP-099", "--github"],
            "unknown loop local": ["schedule", "LOOP-099", "--local"],
            "cron without value": ["schedule", TARGET, "--github", "--cron"],
            "unknown option": ["schedule", TARGET, "--github", "--bogus"],
        }
        for label, args in cases.items():
            with self.subTest(label):
                code, _out, err = self.loop(*args)
                self.assertEqual(code, 1)
                self.assertTrue(err.strip())
                self.assertEqual(snapshot(self.project), before)
        plugin = self.root / "meta" / "plugin.yaml"
        variants = {
            "no plugin.yaml": None,
            "no repository key": PLUGIN_YAML.replace(f"  repository: {REPOSITORY}\n", ""),
        }
        for label, content in variants.items():
            with self.subTest(label):
                if content is None:
                    plugin.unlink()
                else:
                    plugin.write_text(content, encoding="utf-8", newline="\n")
                before = snapshot(self.project)
                code, _out, err = self.schedule("--github")
                self.assertEqual(code, 1)
                self.assertTrue(err.strip())
                self.assertEqual(snapshot(self.project), before)


class ScheduleLocalTests(ScheduleCase):
    def local(self, loop_id, platform):
        with mock.patch.object(sys, "platform", platform):
            return self.loop("schedule", loop_id, "--local")

    def test_local_writes_nothing_and_prints_the_scheduler_line_for_each_os(self):
        """Adversarial where: `--local` writing a file or creating the log
        directory, a crontab line on Windows or a `schtasks` line elsewhere,
        a relative path (the scheduler's working directory is not the
        project), a `>` that truncates the log on every run, a redirect into a
        directory that does not exist yet (the run never starts), a task name
        shared by every loop, or a Desktop phrasing missing."""
        (self.root / "meta" / "plugin.yaml").unlink()
        before = snapshot(self.project)
        roots = {norm(str(self.project)), norm(str(self.project.resolve()))}
        log_tail = f".compass/tmp/loops/{TARGET}/schedule.log".lower()
        for platform in ("win32", "linux", "darwin"):
            with self.subTest(platform):
                code, out, err = self.local(TARGET, platform)
                self.assertEqual(code, 0, err)
                self.assertEqual(snapshot(self.project), before)
                self.assertEqual(list(self.elsewhere.iterdir()), [])
                lines = out.splitlines()
                schtasks = [l for l in lines if re.match(r"\s*schtasks /Create\b", l)]
                crontab = [l for l in lines if re.match(CRON_FIELDS, l) and "loop run" in l]
                if platform == "win32":
                    self.assertEqual((len(schtasks), len(crontab)), (1, 0), out)
                    primary = schtasks[0]
                    name = re.search(r"/TN\s+(\"[^\"]*\"|\S+)", primary)
                    self.assertIsNotNone(name, primary)
                    self.assertIn(TARGET, name.group(1))
                    self.assertIn("/TR", primary)
                else:
                    self.assertEqual((len(schtasks), len(crontab)), (0, 1), out)
                    primary = crontab[0]
                line = norm(primary)
                run_at = line.index(f"loop run {TARGET.lower()}")
                self.assertTrue(any(root in line[:run_at] for root in roots), line)
                self.assertTrue(any(f"{root}/{log_tail}" in line for root in roots), line)
                redirects = line.replace("2>&1", "")
                self.assertNotRegex(redirects, r"(?<!>)>(?!>)")
                self.assertIn(">>", redirects)
                make = re.search(r"mkdir|\bmd\b", line)
                self.assertIsNotNone(make, "nothing creates the log's directory before the redirect")
                self.assertLess(make.start(), line.index(">>"))
                self.assertLess(make.start(), run_at)
                desktop_at = next((i for i, l in enumerate(lines) if "Desktop" in l), None)
                self.assertIsNotNone(desktop_at, out)
                run_lines = [i for i, l in enumerate(lines) if f"loop run {TARGET}" in l]
                self.assertGreaterEqual(len(run_lines), 2, out)
                self.assertTrue(any(i >= desktop_at for i in run_lines), out)

    def test_local_lines_of_two_loops_do_not_collide(self):
        """Adversarial where: a task name or log path that omits the loop id,
        so scheduling a second loop replaces the first loop's task or mixes
        their logs."""
        for platform in ("win32", "linux"):
            with self.subTest(platform):
                _c, third, _e = self.local(TARGET, platform)
                _c, first, _e = self.local("LOOP-001", platform)
                self.assertNotIn("LOOP-001", third)
                self.assertNotIn(TARGET, first)
                self.assertIn("LOOP-001", first)


class ReconcileCase(ScheduleCase):
    def setUp(self):
        super().setUp()
        self.folder = self.folder_for("alpha")
        self.assertTrue(self.folder.name.startswith(RECONCILED))
        for run_id in (RUN_MERGED, RUN_CLOSED, RUN_OPEN):
            self.add_run(self.folder, run_id, "helpful")
        self.prs_file = self.elsewhere / "prs.json"

    def write_prs(self, payload):
        """Write `payload` (text, bytes or a JSON value) to the prs file."""
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        elif not isinstance(payload, bytes):
            payload = json.dumps(payload).encode("utf-8")
        self.prs_file.write_bytes(payload)
        return str(self.prs_file)

    def reconcile(self, source=str(FIXTURE)):
        return self.loop("reconcile", RECONCILED, "--prs", source)

    def reviews(self):
        return [r for r in self.ledger(self.folder) if r.get("type") == "review"]

    def guidance(self):
        return (self.folder / "feedback.md").read_text(encoding="utf-8").splitlines()

    def restore(self, saved):
        for name in ("ledger.jsonl", "feedback.md"):
            (self.folder / name).write_bytes(saved[name])


class ReconcileTests(ReconcileCase):
    def test_merged_accepts_closed_rejects_open_and_unknown_are_skipped_and_reported(self):
        """Adversarial where: the open pull request or the unknown run id
        decided anyway, the closed one accepted (state read as 'not open'),
        the reject reason lost or placed anywhere but one `feedback.md` line,
        a moved loop state, a skipped pull request left out of the report,
        another loop's or a non-loop pull request applied, or a second pass
        that repeats the first."""
        before = snapshot(self.folder)
        feedback_before = self.guidance()
        code, out, err = self.reconcile()
        self.assertEqual(code, 0, err)

        rows = self.reviews()
        self.assertEqual(len(rows), 2, rows)
        self.assertEqual({r["run_id"]: r["decision"] for r in rows},
                         {RUN_MERGED: "accept", RUN_CLOSED: "reject"})
        self.assertEqual({r["run_id"]: r.get("reason") for r in rows}[RUN_CLOSED], CLOSED_REASON)
        self.assertEqual(self.guidance(), feedback_before + [f"- {CLOSED_REASON}"])
        self.assertEqual((self.folder / "state.json").read_bytes(), before["state.json"])
        for number in (PR_OPEN, PR_UNKNOWN):
            lines = [l for l in out.splitlines() if f"#{number}" in l]
            self.assertEqual(len(lines), 1, out)
            self.assertIn("skip", lines[0].lower())
        after_first = snapshot(self.folder)

        code, _out, err = self.reconcile()
        self.assertEqual(code, 0, err)
        self.assertEqual(snapshot(self.folder), after_first)

    def test_a_run_with_a_local_review_row_is_left_alone(self):
        """Adversarial where: reconcile overriding the human's own `loop
        review` (a local accept turned into a reject by a closed pull
        request), or appending a second review row for a run already
        reviewed."""
        self.loop("review", RECONCILED, RUN_MERGED, "reject", "--reason", "rejected by hand")
        self.loop("review", RECONCILED, RUN_CLOSED, "accept")
        before = snapshot(self.folder)
        code, _out, err = self.reconcile()
        self.assertEqual(code, 0, err)
        self.assertEqual(snapshot(self.folder), before)

    def test_only_this_loops_exact_run_branches_count(self):
        """Adversarial where: matching a branch by prefix or suffix, so
        another loop's pull request, `LOOP-0010`, a longer or shorter run id,
        the fallback `state-<run-id>` branch, an extra path segment or a fork
        prefix decides a run it does not name."""
        branches = {
            "another loop, same run id": f"compass-loop/LOOP-002/{RUN_OPEN}",
            "loop number with a longer tail": f"compass-loop/{RECONCILED}0/{RUN_OPEN}",
            "loop number with a shorter tail": f"compass-loop/LOOP-00/{RUN_OPEN}",
            "run id with a suffix": f"compass-loop/{RECONCILED}/{RUN_OPEN}0",
            "run id truncated": f"compass-loop/{RECONCILED}/{RUN_OPEN[:-1]}",
            "state fallback branch": f"compass-loop/{RECONCILED}/state-{RUN_OPEN}",
            "extra path segment": f"compass-loop/{RECONCILED}/{RUN_OPEN}/extra",
            "fork prefix": f"someone/compass-loop/{RECONCILED}/{RUN_OPEN}",
            "no loop segment": f"compass-loop/{RUN_OPEN}",
        }
        saved = {n: (self.folder / n).read_bytes() for n in ("ledger.jsonl", "feedback.md")}
        for state, merged_at in (("MERGED", "2026-10-16T21:43:26Z"), ("CLOSED", None)):
            for label, branch in branches.items():
                with self.subTest(label, state=state):
                    self.restore(saved)
                    payload = [{"headRefName": branch, "mergedAt": merged_at, "number": 901, "state": state}]
                    code, _out, err = self.reconcile(self.write_prs(payload))
                    self.assertEqual(code, 0, err)
                    self.assertEqual(self.reviews(), [])

    def test_several_pull_requests_on_one_branch_decide_the_run_once(self):
        """Adversarial where: a closed pull request and a later merged one on
        the same branch both applied, so the review path refuses the second
        and the command exits 1 half way through (or writes two rows)."""
        branch = f"compass-loop/{RECONCILED}/{RUN_OPEN}"
        orders = {
            "closed then merged": [("CLOSED", None, 41), ("MERGED", "2026-10-16T21:00:15Z", 42)],
            "merged then closed": [("MERGED", "2026-10-16T21:00:15Z", 42), ("CLOSED", None, 41)],
        }
        saved = {n: (self.folder / n).read_bytes() for n in ("ledger.jsonl", "feedback.md")}
        for label, listed in orders.items():
            with self.subTest(label):
                self.restore(saved)
                payload = [{"headRefName": branch, "mergedAt": m, "number": n, "state": s} for s, m, n in listed]
                code, _out, err = self.reconcile(self.write_prs(payload))
                self.assertEqual(code, 0, err)
                self.assertEqual([r["run_id"] for r in self.reviews()], [RUN_OPEN])

    def test_malformed_input_is_refused_before_anything_is_applied(self):
        """Adversarial where: a list whose first entry is good and a later one
        broken applying the good one before dying (a half applied reconcile),
        a non-list, an empty file or a missing file crashing, or `--prs`
        omitted being read as stdin."""
        good = {"headRefName": f"compass-loop/{RECONCILED}/{RUN_MERGED}",
                "mergedAt": "2026-10-16T21:43:26Z", "number": 1, "state": "MERGED"}
        broken = {
            "not json": "not json",
            "empty file": "",
            "an object": {"number": 1},
            "an entry that is not an object": [good, 7],
            "a later entry without headRefName": [good, {"number": 2, "state": "OPEN", "mergedAt": None}],
            "a later entry with a text number": [good, {**good, "number": "2"}],
            "a later entry with an unknown state": [good, {**good, "number": 2, "state": "WAT"}],
            "a later entry with a numeric branch": [good, {**good, "number": 2, "headRefName": 5}],
        }
        before = snapshot(self.folder)
        for label, content in broken.items():
            with self.subTest(label):
                code, _out, err = self.reconcile(self.write_prs(content))
                self.assertEqual(code, 1)
                self.assertTrue(err.strip())
                self.assertEqual(snapshot(self.folder), before)
        valid = self.write_prs([])
        invocations = {
            "missing file": ["reconcile", RECONCILED, "--prs", str(self.elsewhere / "absent.json")],
            "no --prs": ["reconcile", RECONCILED],
            "--prs without value": ["reconcile", RECONCILED, "--prs"],
            "unknown loop": ["reconcile", "LOOP-099", "--prs", valid],
            "no id": ["reconcile", "--prs", valid],
        }
        for label, args in invocations.items():
            with self.subTest(label):
                code, _out, err = self.loop(*args)
                self.assertEqual(code, 1)
                self.assertTrue(err.strip())
                self.assertEqual(snapshot(self.folder), before)

    def test_inputs_that_apply_nothing_succeed_and_a_bom_or_stdin_is_read(self):
        """Adversarial where: an empty list (what `gh` prints for a repository
        with no pull requests) treated as an error, a UTF-8 BOM (Windows
        redirection writes one) breaking the parse, or `-` not reading
        standard input."""
        before = snapshot(self.folder)
        code, _out, err = self.reconcile(self.write_prs([]))
        self.assertEqual(code, 0, err)
        self.assertEqual(snapshot(self.folder), before)

        expected = {RUN_MERGED, RUN_CLOSED}
        code, _out, err = self.reconcile(self.write_prs(b"\xef\xbb\xbf" + FIXTURE.read_bytes()))
        self.assertEqual(code, 0, err)
        self.assertEqual({r["run_id"] for r in self.reviews()}, expected)

        self.restore(before)
        code, _out, err = self.cli_in(
            self.elsewhere, "reconcile", RECONCILED, "--prs", "-",
            stdin=FIXTURE.read_text(encoding="utf-8"),
        )
        self.assertEqual(code, 0, err)
        self.assertCountEqual([r["run_id"] for r in self.reviews()], expected)

    def test_reconcile_refuses_while_a_run_holds_the_lock(self):
        """Adversarial where: reconcile writing review rows and guidance in
        the middle of a run, interleaving with the runner's own ledger
        appends, or disturbing the lock."""
        number = self.folder.name.split("-")[1]
        lock = self.root / "tmp" / "loops" / f"LOOP-{number}.lock"
        looplib.acquire_lock(lock, 60)
        held = lock.read_bytes()
        before = snapshot(self.folder)
        code, _out, err = self.reconcile()
        self.assertEqual(code, 1)
        self.assertTrue(err.strip())
        self.assertEqual(snapshot(self.folder), before)
        self.assertEqual(lock.read_bytes(), held)


class StatusLastRunTests(ScheduleCase):
    def write_ledger(self, rows, tail=""):
        text = "".join(json.dumps(r) + "\n" for r in rows) + tail
        (self.folder / "ledger.jsonl").write_bytes(text.encode("utf-8"))

    def run_row(self, run_id, outcome):
        return {"type": "run", "run_id": run_id, "outcome": outcome, "item": "a.py:x", "cost_usd": 0.0}

    def test_last_run_prints_the_final_run_row_and_nothing_else(self):
        """Adversarial where: the highest run id or the last helpful run
        printed instead of the last run row in file order, a review or error
        row after it taken for a run, a torn trailing line failing the
        command, or extra status lines the workflow would have to parse
        around."""
        review = {"type": "review", "run_id": "RUN-B", "decision": "accept"}
        error = {"type": "error", "run_id": "RUN-C", "reason": "boom"}
        cases = {
            "one run": ([self.run_row("RUN-A", "helpful")], "", "RUN-A helpful"),
            "ids out of order": (
                [self.run_row("RUN-9", "helpful"), self.run_row("RUN-1", "neutral")], "", "RUN-1 neutral"),
            "review and error rows after it": (
                [self.run_row("RUN-A", "helpful"), self.run_row("RUN-B", "neutral"), review, error],
                "", "RUN-B neutral"),
            "torn last line": (
                [self.run_row("RUN-A", "helpful"), self.run_row("RUN-B", "harmful")],
                '{"type": "run", "run_id": "RUN-C", "outc', "RUN-B harmful"),
            "unverified last run": (
                [self.run_row("RUN-A", "helpful"), self.run_row("RUN-B", "throttled")], "", "RUN-B throttled"),
        }
        for label, (rows, tail, expected) in cases.items():
            with self.subTest(label):
                self.write_ledger(rows, tail)
                for args in (("status", TARGET, "--last-run"), ("status", "--last-run", TARGET)):
                    code, out, err = self.loop(*args)
                    self.assertEqual(code, 0, err)
                    self.assertEqual(out.splitlines(), [expected])

    def test_last_run_exits_1_with_empty_stdout_when_there_is_no_run_row(self):
        """Adversarial where: an empty ledger, one holding only transitions,
        reviews and errors, or a missing one, printing a blank or placeholder
        run line (the workflow would read it as a run), or exiting 0."""
        cases = {
            "no ledger file": None,
            "empty ledger": [],
            "no run rows": [
                {"type": "transition", "from": "idle", "event": "activate", "to": "sensing"},
                {"type": "review", "run_id": "RUN-A", "decision": "accept"},
                {"type": "error", "run_id": "RUN-A", "reason": "boom"},
            ],
        }
        for label, rows in cases.items():
            with self.subTest(label):
                (self.folder / "ledger.jsonl").unlink(missing_ok=True)
                if rows is not None:
                    self.write_ledger(rows)
                code, out, _err = self.loop("status", TARGET, "--last-run")
                self.assertEqual(code, 1)
                self.assertEqual(out.strip(), "")

    def test_last_run_needs_a_known_loop_id(self):
        """Adversarial where: `status --last-run` with no id falling through to
        the all-loops listing and exiting 0, or an unknown id printing a run."""
        before = snapshot(self.project)
        for label, args in {"no id": ("status", "--last-run"),
                            "unknown id": ("status", "LOOP-099", "--last-run")}.items():
            with self.subTest(label):
                code, out, _err = self.loop(*args)
                self.assertEqual(code, 1)
                self.assertEqual(out.strip(), "")
                self.assertEqual(snapshot(self.project), before)


class RegistrationTests(ScheduleCase):
    def test_help_line_and_usage_name_the_new_subcommands_beside_the_old(self):
        """Adversarial where: `schedule` or `reconcile` working but absent
        from the `loop` help line and the usage text (undiscoverable), or
        added by replacing an existing subcommand name."""
        help_line = dict(maincli.COMMAND_SPECS)["loop"]
        code, _out, usage = self.loop()
        self.assertEqual(code, 1)
        for name in ("new", "status", "activate", "pause", "resume", "review",
                     "run", "check", "baseline", "schedule", "reconcile"):
            with self.subTest(name):
                self.assertIn(name, help_line)
                self.assertIn(name, usage)


if __name__ == "__main__":
    import unittest

    unittest.main()
