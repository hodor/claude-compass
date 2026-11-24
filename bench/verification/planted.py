"""Planted-defect probe for the verification checks.

`build` writes a small Python project (`tally`, a word counter) with its own
virtual environment, a one-spec vault and a three-task plan, and lands each
task as a `Merge TASK-NNN:` commit on `main`. Every task keeps the suite green
and carries one planted shape:

    A  adds `format_total`, a helper no command line path calls
    B  changes one line of `count`, behind tests that pass without the change
    C  adds `tally top`, which meets two of the spec's three Constraints and
       breaks the third (a tie returns the first word of the text, not the
       alphabetically first one)

`run_checks` runs `compass reach` and `compass ablate` for every task, each
through `compass evidence run`, commits the records and reruns each one. The
expected verdicts are in `EXPECTED`: reach flags A, ablate flags B, and every
other check passes. `judge` starts one headless validator session limited to
step 4j for task C and scores its requirement rows against `JUDGE_OWNED`.

    python bench/verification/planted.py [--lang python|node] [--root DIR] [--judge] [--json FILE]

The exit code is 0 when the suite is green, every check equals `EXPECTED` and
every record reruns to `match`.

`--lang node` builds the same spec, plan and three tasks on a Node package
(`src/core.js`, `bin/tally.js`, tests under `node:test`) and measures with c8,
installed from npm into `<root>/.tools`. Task C adds an HTTP route and the
driver `scripts/drive.js` that exercises it; task A's helper is one arrow line.
The Node project has no judge run.
"""

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "bench" / "overhead"))

import launch  # noqa: E402
import records  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

TASKS = [("A", "TASK-001"), ("B", "TASK-002"), ("C", "TASK-003")]
EXPECTED = {
    "reach": {"A": "FINDING", "B": "PASS", "C": "PASS"},
    "ablate": {"A": "PASS", "B": "FINDING", "C": "PASS"},
}
JUDGE_OWNED = {"O-3": "met", "K-1": "met", "C-1": "met", "C-2": "met", "C-3": "unmet"}
UNMET = {"partial", "missing", "contradicts"}
JUDGE_STATUSES = ("met", "partial", "missing", "contradicts", "unrequested")
JUDGED_TASK = "TASK-003"
JUDGE_TIMEOUT_SECONDS = 1800

SPEC_PATH = ".compass/specs/SPEC-001-word-tally.md"
PLAN_PATH = ".compass/plans/PLAN-001-word-tally.md"

TASK_TITLES = {
    "TASK-001": "Thousands separators for a total, per O-2",
    "TASK-002": "Punctuation around a word is ignored, per O-1",
    "TASK-003": "`tally top` prints the most frequent word, per O-3 and the Constraints",
}
LANGUAGES = ("python", "node")
TASK_FILES = {
    "python": {
        "TASK-001": ["tally/core.py", "tests/test_fmt.py"],
        "TASK-002": ["tally/core.py", "tests/test_punct.py"],
        "TASK-003": ["tally/core.py", "tally/__main__.py", "tests/test_top.py"],
    },
    "node": {
        "TASK-001": ["src/core.js", "tests/fmt.test.js"],
        "TASK-002": ["src/core.js", "tests/punct.test.js"],
        "TASK-003": ["src/core.js", "src/server.js", "scripts/drive.js", "tests/top.test.js"],
    },
}
ENTRY_POINTS = {
    "python": {
        "TASK-001": 'python -m tally count "one two three"',
        "TASK-002": 'python -m tally count "Hello, world!"',
        "TASK-003": 'python -m tally top "The cat saw the dog"',
    },
    "node": {
        "TASK-001": 'node bin/tally.js count "one two three"',
        "TASK-002": 'node bin/tally.js count "Hello, world!"',
        "TASK-003": "node scripts/drive.js",
    },
}
SUITE_COMMANDS = {"python": "python -m pytest -q", "node": "node --test"}
NODE_TEST_COMMAND = "node --test --test-reporter=tap {tests}"
NODE_TOOLS = ".tools"

PROBE_NAME = "probe"
PROBE_EMAIL = "probe@example.invalid"


class Refused(Exception):
    """The build was not started: the folder is not empty or sits in a git work tree."""


class JudgeError(Exception):
    """The judge session did not finish, or its reply holds no requirement row."""


class ProbeError(RuntimeError):
    """A command the probe depends on failed."""


# --------------------------------------------------------------- seeded sources

GITIGNORE = ".venv/\n.claude/\n.compass/tmp/\n.compass/meta/\n__pycache__/\n.pytest_cache/\n"

CORE_SEED = "def count(text):\n    return len(text.split())\n"

CORE_A = CORE_SEED + '\n\ndef format_total(n):\n    return f"{n:,}"\n'

CORE_B = CORE_A.replace(
    "    return len(text.split())\n",
    '    return len([word for word in (raw.strip(".,!?;:") for raw in text.split()) if word])\n',
)

CORE_C = CORE_B + (
    "\n\ndef top(text):\n"
    "    from collections import Counter\n"
    '    counts = Counter(word for word in (raw.strip(".,!?;:") for raw in text.lower().split()) if word)\n'
    '    return max(counts, key=counts.get) if counts else ""\n'
)

MAIN_SEED = '''import sys

from tally import core

USAGE = "usage: python -m tally count <text>"


def main(argv):
    command = argv[0] if argv else ""
    text = " ".join(argv[1:])
    if command == "count":
        print(core.count(text))
        return 0
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

MAIN_C = MAIN_SEED.replace(
    'USAGE = "usage: python -m tally count <text>"',
    'USAGE = "usage: python -m tally count|top <text>"',
).replace(
    "    print(USAGE, file=sys.stderr)\n",
    '    if command == "top":\n'
    "        word = core.top(text)\n"
    "        if word:\n"
    "            print(word)\n"
    "        return 0\n"
    "    print(USAGE, file=sys.stderr)\n",
)

TEST_CORE = 'from tally.core import count\n\n\ndef test_count_words():\n    assert count("one two three") == 3\n'

TEST_FMT = (
    "from tally.core import format_total\n\n\n"
    "def test_format_total_groups_thousands():\n"
    '    assert format_total(1234) == "1,234"\n'
)

TEST_PUNCT = (
    "from tally.core import count\n\n\n"
    "def test_two_words():\n"
    '    assert count("one two") == 2\n\n\n'
    "def test_three_words():\n"
    '    assert count("a b c") == 3\n'
)

TEST_TOP = (
    "from tally.core import top\n\n\n"
    "def test_top_ignores_letter_case():\n"
    '    assert top("The cat the dog") == "the"\n\n\n'
    "def test_top_of_an_empty_text_is_empty():\n"
    '    assert top("") == ""\n'
)

SPEC_TEXT = """---
title: "Word Tally"
type: spec
status: approved
---

# Word Tally

## Problem

A person who holds a text has no command that counts its words or names its most frequent word.

## Desired Outcome

- `tally count <text>` prints how many words the text holds, a word being a run of characters between spaces, with any of `.,!?;:` around it ignored.
- A total can be written with thousands separators, as `1,234`.
- `tally top <text>` prints the most frequent word of the text.
- KPI: `tally top` answers on a 1,000-word text in one command.

## Constraints

- `tally top` counts words without regard to letter case: `The` and `the` are one word.
- `tally top` on an empty text prints nothing and exits 0.
- On a tie, `tally top` prints the tied word that sorts first alphabetically.
"""

NODE_GITIGNORE = ".tools/\nnode_modules/\ncoverage/\n.claude/\n.compass/tmp/\n.compass/meta/\n"

NODE_PACKAGE = '{\n  "name": "tally",\n  "version": "1.0.0",\n  "private": true\n}\n'

NODE_COUNT_SEED = "exports.count = (text) => text.split(/\\s+/).filter(Boolean).length;\n"

NODE_CORE_SEED = NODE_COUNT_SEED

NODE_CORE_A = NODE_CORE_SEED + '\nexports.formatTotal = (n) => n.toLocaleString("en-US");\n'

NODE_COUNT_B = (
    "exports.count = (text) => text.split(/\\s+/)"
    '.map((raw) => raw.replace(/^[.,!?;:]+|[.,!?;:]+$/g, "")).filter(Boolean).length;\n'
)

NODE_CORE_B = NODE_CORE_A.replace(NODE_COUNT_SEED, NODE_COUNT_B)

NODE_CORE_C = NODE_CORE_B + """
exports.top = (text) => {
  const words = text.toLowerCase().split(/\\s+/).map((raw) => raw.replace(/^[.,!?;:]+|[.,!?;:]+$/g, "")).filter(Boolean);
  const counts = new Map();
  for (const word of words) counts.set(word, (counts.get(word) || 0) + 1);
  return words.length ? [...counts].reduce((best, entry) => (entry[1] > best[1] ? entry : best))[0] : "";
};
"""

NODE_TALLY_BIN = """const core = require("../src/core.js");

const COMMANDS = new Set(["count", "top"]);
const USAGE = "usage: node bin/tally.js count|top <text>";

function main(argv) {
  const command = argv[0] || "";
  const run = COMMANDS.has(command) ? core[command] : undefined;
  if (typeof run !== "function") {
    console.error(USAGE);
    return 2;
  }
  const answer = String(run(argv.slice(1).join(" ")));
  if (answer !== "") console.log(answer);
  return 0;
}

process.exitCode = main(process.argv.slice(2));
"""

NODE_SERVER = """const http = require("node:http");
const core = require("./core.js");

const routes = { "/top": (text) => core.top(text) };

exports.createServer = () =>
  http.createServer((req, res) => {
    const url = new URL(req.url, "http://localhost");
    const route = routes[url.pathname];
    res.statusCode = route ? 200 : 404;
    res.end(route ? route(url.searchParams.get("text") || "") : "");
  });
"""

NODE_DRIVE = """const http = require("node:http");
const { createServer } = require("../src/server.js");

const server = createServer();
server.listen(0, "127.0.0.1", () => {
  const { port } = server.address();
  const text = encodeURIComponent("The cat saw the dog");
  http.get(`http://127.0.0.1:${port}/top?text=${text}`, { agent: false }, (res) => {
    let body = "";
    res.setEncoding("utf8");
    res.on("data", (chunk) => {
      body += chunk;
    });
    res.on("end", () => {
      console.log(body);
      server.close();
    });
  });
});
"""

NODE_TEST_HEAD = 'const test = require("node:test");\nconst assert = require("node:assert");\n'

NODE_TEST_CORE = (
    NODE_TEST_HEAD + 'const { count } = require("../src/core.js");\n\n'
    'test("count words", () => {\n  assert.strictEqual(count("one two three"), 3);\n});\n'
)

NODE_TEST_FMT = (
    NODE_TEST_HEAD + 'const { formatTotal } = require("../src/core.js");\n\n'
    'test("formatTotal groups thousands", () => {\n  assert.strictEqual(formatTotal(1234), "1,234");\n});\n'
)

NODE_TEST_PUNCT = (
    NODE_TEST_HEAD + 'const { count } = require("../src/core.js");\n\n'
    'test("two words", () => {\n  assert.strictEqual(count("one two"), 2);\n});\n\n'
    'test("three words", () => {\n  assert.strictEqual(count("a b c"), 3);\n});\n'
)

NODE_TEST_TOP = (
    NODE_TEST_HEAD + 'const { top } = require("../src/core.js");\n\n'
    'test("top ignores letter case", () => {\n  assert.strictEqual(top("The cat the dog"), "the");\n});\n\n'
    'test("top of an empty text is empty", () => {\n  assert.strictEqual(top(""), "");\n});\n'
)


def _plan_text(lang="python"):
    blocks = []
    for _, task in TASKS:
        files = ", ".join(TASK_FILES[lang][task])
        blocks.append(
            f"- [x] {task}: {TASK_TITLES[task]} - complexity: S, depends_on: none, files: [{files}]\n"
            f"  - Automated verification: {SUITE_COMMANDS[lang]}\n"
            f"  - Entry point: {ENTRY_POINTS[lang][task]}\n"
        )
    return (
        "---\n"
        'title: "Word Tally"\n'
        "type: plan\n"
        "status: approved\n"
        'depends_on: ["[[SPEC-001-word-tally]]"]\n'
        "---\n\n"
        "# Word Tally\n\n"
        "## Tasks\n\n" + "\n".join(blocks)
    )


# ------------------------------------------------------------------- processes


def _clean_env():
    return launch.git_environment()


def _run(argv, cwd, *, what, check=True, env=None):
    """Run `argv` with no console window; returns the CompletedProcess (text output).

    `env` is the whole environment of the process; without it the caller's own
    environment minus the git location variables.
    """
    try:
        done = subprocess.run(
            [str(a) for a in argv], cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env or _clean_env(), creationflags=NO_WINDOW,
        )
    except OSError as error:
        raise ProbeError(f"{what}: cannot run {argv[0]}: {error}") from error
    if check and done.returncode != 0:
        detail = (done.stderr or done.stdout).strip()
        raise ProbeError(f"{what} failed (exit {done.returncode}): {detail}")
    return done


def _git(project, *args, check=True):
    return _run(
        ["git", "-c", f"user.name={PROBE_NAME}", "-c", f"user.email={PROBE_EMAIL}",
         "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false", "-C", project, *args],
        project, what=f"git {args[0]}", check=check,
    )


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _check_lang(lang):
    if lang not in LANGUAGES:
        raise ValueError(f"lang must be one of {', '.join(LANGUAGES)}, not {lang!r}")


def _node_env(project):
    """The environment of every Node command: npm's global prefix is the project's c8 folder.

    Both spellings of the variable are replaced, so the c8 that `build` installed
    is found from any folder, a scratch worktree included.
    """
    env = {k: v for k, v in _clean_env().items() if k.upper() != "NPM_CONFIG_PREFIX"}
    env["npm_config_prefix"] = str(Path(project) / NODE_TOOLS)
    return env


def _npm():
    found = shutil.which("npm")
    if found is None:
        raise ProbeError("npm is not installed: c8 cannot be installed")
    return found


def venv_python(project):
    folder, name = ("Scripts", "python.exe") if sys.platform == "win32" else ("bin", "python")
    return Path(project) / ".venv" / folder / name


# ----------------------------------------------------------------------- build


def _existing_ancestor(path):
    current = Path(path).absolute()
    while not current.exists():
        if current.parent == current:
            break
        current = current.parent
    return current


def _check_target(root):
    if root.exists():
        if not root.is_dir():
            raise Refused(f"{root} is not a folder")
        if any(root.iterdir()):
            raise Refused(f"{root} is not empty")
    ancestor = _existing_ancestor(root)
    inside = _run(["git", "-C", ancestor, "rev-parse", "--is-inside-work-tree"], ancestor,
                  what="git rev-parse", check=False)
    if inside.returncode == 0 and inside.stdout.strip() == "true":
        raise Refused(f"{root} is inside a git work tree")


def _land(project, task, files, message_title):
    """Commit `files` on a branch for `task` and merge it into main with a merge commit."""
    branch = task.lower()
    _git(project, "switch", "-q", "-c", branch)
    for name, text in files.items():
        _write(project / name, text)
    _git(project, "add", *files)
    _git(project, "commit", "-q", "-m", f"{task}: {message_title}")
    _git(project, "switch", "-q", "main")
    _git(project, "merge", "-q", "--no-ff", "-m", f"Merge {task}: {message_title}", branch)


def build(root, *, repo_root, uv="uv", lang="python"):
    """Create the seeded project in `root` and return it.

    `root` must be missing or an empty folder outside every git work tree;
    otherwise Refused is raised before anything is written. A build that fails
    after writing leaves `root` as it found it: missing, or empty. `lang` is
    `python` (own virtual environment) or `node` (c8 installed into `.tools`).
    """
    _check_lang(lang)
    root = Path(root)
    _check_target(root)
    existed = root.exists()
    root.mkdir(parents=True, exist_ok=True)
    try:
        return _build_in(root, Path(repo_root), uv, lang)
    except BaseException:
        _remove_tree(root)
        if existed:
            root.mkdir()
        raise


def _python_project():
    seed = {
        ".gitignore": GITIGNORE,
        "tally/__init__.py": "",
        "tally/core.py": CORE_SEED,
        "tally/__main__.py": MAIN_SEED,
        "tests/test_core.py": TEST_CORE,
    }
    tasks = {
        "TASK-001": {"tally/core.py": CORE_A, "tests/test_fmt.py": TEST_FMT},
        "TASK-002": {"tally/core.py": CORE_B, "tests/test_punct.py": TEST_PUNCT},
        "TASK-003": {"tally/core.py": CORE_C, "tally/__main__.py": MAIN_C,
                     "tests/test_top.py": TEST_TOP},
    }
    return seed, tasks


def _node_project():
    seed = {
        ".gitignore": NODE_GITIGNORE,
        "package.json": NODE_PACKAGE,
        "src/core.js": NODE_CORE_SEED,
        "bin/tally.js": NODE_TALLY_BIN,
        "tests/core.test.js": NODE_TEST_CORE,
    }
    tasks = {
        "TASK-001": {"src/core.js": NODE_CORE_A, "tests/fmt.test.js": NODE_TEST_FMT},
        "TASK-002": {"src/core.js": NODE_CORE_B, "tests/punct.test.js": NODE_TEST_PUNCT},
        "TASK-003": {"src/core.js": NODE_CORE_C, "src/server.js": NODE_SERVER,
                     "scripts/drive.js": NODE_DRIVE, "tests/top.test.js": NODE_TEST_TOP},
    }
    return seed, tasks


def _build_in(root, repo_root, uv, lang):
    if lang == "node":
        _run([_npm(), "install", "-g", "--prefix", root / NODE_TOOLS, "--no-audit", "--no-fund",
              "--loglevel=error", "c8"], root, what="npm install c8")
        seed, tasks = _node_project()
    else:
        _run([uv, "venv", "--quiet", root / ".venv"], root, what="uv venv")
        _run([uv, "pip", "install", "--quiet", "--python", venv_python(root), "coverage", "pytest"],
             root, what="uv pip install")
        seed, tasks = _python_project()
    seed = {**seed, SPEC_PATH: SPEC_TEXT, PLAN_PATH: _plan_text(lang)}
    for name, text in seed.items():
        _write(root / name, text)
    _git(root, "init", "-q", "--initial-branch=main")
    _git(root, "add", *seed)
    _git(root, "commit", "-q", "-m", "Seed the word tally")

    for task, files in tasks.items():
        _land(root, task, files, TASK_TITLES[task])

    shutil.copytree(
        repo_root / "plugin" / "cli", root / ".claude" / "cli",
        ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"),
    )
    agents = root / ".claude" / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(repo_root / "plugin" / "templates" / "agents" / "validator.md",
                    agents / "validator.md")
    return root


# --------------------------------------------------------------- suite, history


def merges(project):
    """`{task: sha}` of the first-parent `Merge TASK-NNN:` commits of the current branch."""
    done = _git(project, "log", "--first-parent", "--format=%H%x00%s")
    found = {}
    for line in done.stdout.splitlines():
        sha, _, subject = line.partition("\x00")
        match = re.match(r"Merge (TASK-\d{3}): ", subject)
        if match and match.group(1) not in found:
            found[match.group(1)] = sha
    return dict(sorted(found.items()))


def run_suite(project, lang="python"):
    """`(green, last output line)` of the project's test suite at HEAD."""
    _check_lang(lang)
    if lang == "node":
        done = _run(["node", "--test"], project, what="node --test", check=False,
                    env=_node_env(project))
    else:
        done = _run([venv_python(project), "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                    project, what="pytest", check=False)
    lines = [line.strip() for line in (done.stdout + "\n" + done.stderr).splitlines() if line.strip()]
    return done.returncode == 0, lines[-1] if lines else ""


# ---------------------------------------------------------------------- checks


def verdict(output, prefix):
    """The word after the last line of `output` that starts `<prefix>: `, else None."""
    pattern = re.compile(re.escape(prefix) + r": ([^\s:]+)")
    found = None
    for line in output.split("\n"):
        match = pattern.match(line.rstrip("\r"))
        if match:
            found = match.group(1)
    return found


def _compass(cli, *args):
    return [sys.executable, "-B", str(cli), *args]


def _check_command(project, cli, check, task, merge, lang="python"):
    if lang == "node":
        if check == "reach":
            return _compass(cli, "reach", "--run", ENTRY_POINTS["node"][task], "--lang", "node",
                            "--diff", f"{merge}^1..{merge}")
        return _compass(cli, "ablate", task, "--cmd", NODE_TEST_COMMAND)
    python = venv_python(project)
    if check == "reach":
        entry = ENTRY_POINTS["python"][task]
        command = f'"{python}"' + entry[len("python"):]
        return _compass(cli, "reach", "--run", command, "--lang", "python",
                        "--diff", f"{merge}^1..{merge}", "--python", python)
    return _compass(cli, "ablate", task, "--cmd", f'"{python}" -m pytest -v {{tests}}')


def _record_line(stdout):
    found = None
    for line in stdout.splitlines():
        if line.startswith("record: "):
            found = line[len("record: "):].strip()
    return found


def _commit_record(project, record, task, check):
    json_path = project / record
    _git(project, "add", record, json_path.with_suffix(".out").relative_to(project).as_posix())
    _git(project, "commit", "-q", "-m", f"Record {task} {check} evidence")


def _rerun(project, cli, record, env=None):
    done = _run(_compass(cli, "evidence", "rerun", project / record), project,
                what="evidence rerun", check=False, env=env)
    words = done.stdout.split()
    return words[0] if words and words[0] in ("match", "mismatch") else "error"


def run_checks(project, *, cli, lang="python"):
    """Run reach and ablate for every task through `compass evidence run`.

    Returns one dict per check in `TASKS` order, reach before ablate, with the
    keys letter, task, check, verdict, expected, record and rerun. A Node run
    and its reruns carry the project's c8 prefix in their environment.
    """
    _check_lang(lang)
    project = Path(project)
    env = _node_env(project) if lang == "node" else None
    found = merges(project)
    rows = []
    for letter, task in TASKS:
        for check in ("reach", "ablate"):
            inner = _check_command(project, cli, check, task, found[task], lang)
            done = _run(_compass(cli, "evidence", "run", "--task", task, "--check", check, "--", *inner),
                        project, what=f"evidence run {task} {check}", check=False, env=env)
            record = _record_line(done.stdout)
            word = None
            if record:
                out_path = (project / record).with_suffix(".out")
                text = out_path.read_bytes().decode("utf-8", errors="replace") if out_path.is_file() else done.stdout
                word = verdict(text, check.upper())
                _commit_record(project, record, task, check)
            rows.append({
                "letter": letter, "task": task, "check": check, "verdict": word,
                "expected": EXPECTED[check][letter], "record": record or "", "rerun": "error",
            })
    for row in rows:
        if row["record"]:
            row["rerun"] = _rerun(project, cli, row["record"], env)
    return rows


def format_lines(green, suite_line, checks):
    """The report lines: suite, per-task suite flags, check verdicts, rerun results."""
    lines = ["suite: green" if green else "suite: red"]
    flag = "flagged nothing" if green else "flagged"
    lines.extend(f"suite {letter}: {flag}" for letter, _ in TASKS)
    lines.extend(f"{row['check']} {row['letter']}: {row['verdict']}" for row in checks)
    lines.extend(f"rerun {row['check']} {row['letter']}: {row['rerun']}" for row in checks)
    return lines


# ----------------------------------------------------------------------- judge


def judge_prompt(project):
    return (
        f"Run only step 4j (spec conformance) of your validation, for {JUDGED_TASK} of "
        f"`{PLAN_PATH}` against `{SPEC_PATH}`. Skip every other step. "
        "In this project `compass` means `python .claude/cli/compass`. "
        "The merged code is at HEAD of the current folder. "
        "End your reply with one line per requirement row of the spec, in the form "
        "`REQ <id>: <met|partial|missing|contradicts|unrequested>`."
    )


_REQ_LINE = re.compile(r"^REQ ([A-Z]+-\d+):[ \t]*(\S+)")


def parse_judge(text):
    """`{id: status}` from the `REQ <id>: <status>` lines of `text`; the last of a repeated id wins."""
    statuses = {}
    for line in text.split("\n"):
        match = _REQ_LINE.match(line.rstrip("\r"))
        if match:
            statuses[match.group(1)] = match.group(2).rstrip(".,;").lower()
    return statuses


def score_judge(statuses):
    """Score a judge's rows against `JUDGE_OWNED`."""
    false_positives = [
        row for row, expected in JUDGE_OWNED.items()
        if expected == "met" and statuses.get(row) in UNMET
    ]
    return {
        "planted_flagged": statuses.get("C-3") in UNMET,
        "false_positives": false_positives,
        "missing_rows": [row for row in JUDGE_OWNED if row not in statuses],
        "other_rows": {row: status for row, status in statuses.items() if row not in JUDGE_OWNED},
    }


def judge(project, *, repo_root, private_root=None, claude_cmd=None):
    """Run one headless validator session for step 4j and score its rows."""
    started = time.monotonic()
    result = launch.run_session(
        project, judge_prompt(project), repo_root=repo_root, private_root=private_root,
        claude_cmd=claude_cmd,
        extra_args=["--agent", "validator", "--allowedTools", "Read,Grep,Glob,Bash"],
        timeout=JUDGE_TIMEOUT_SECONDS,
    )
    seconds = time.monotonic() - started
    if result.status != launch.DONE:
        raise JudgeError(f"the judge session ended {result.status} (exit {result.returncode})")
    finals = [event for event in result.events if event.get("type") == "result"]
    reply = finals[-1].get("result") if finals else None
    statuses = parse_judge(reply if isinstance(reply, str) else "")
    if not statuses:
        raise JudgeError("the judge reply holds no REQ line")
    turns = finals[-1].get("num_turns")
    return {
        "statuses": statuses,
        "score": score_judge(statuses),
        "tokens": records.count_tokens(result.events),
        "turns": turns if isinstance(turns, int) else None,
        "seconds": seconds,
    }


# ------------------------------------------------------------------------ main


def _forget_readonly(function, path, _excinfo):
    os.chmod(path, stat.S_IWRITE)
    function(path)


def _remove_tree(path):
    """Delete a scratch folder, clearing the read-only flag git sets on object files."""
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_forget_readonly)
    else:
        shutil.rmtree(path, onerror=_forget_readonly)


def _judge_lines(result):
    statuses = result["statuses"]
    order = list(JUDGE_OWNED) + sorted(row for row in statuses if row not in JUDGE_OWNED)
    lines = [f"4j {row}: {statuses.get(row, 'absent')}" for row in order]
    score = result["score"]
    lines.append(f"4j planted C-3: {'flagged' if score['planted_flagged'] else 'missed'}")
    lines.append(f"4j false positives: {len(score['false_positives'])}")
    return lines


def _parse_args(argv):
    parser = argparse.ArgumentParser(prog="planted.py", description="Planted-defect probe.")
    parser.add_argument("--lang", choices=LANGUAGES, default="python",
                        help="language of the seeded project (default python)")
    parser.add_argument("--root", help="folder to build the project in (missing or empty)")
    parser.add_argument("--judge", action="store_true", help="also run the 4j validator session")
    parser.add_argument("--json", metavar="FILE", help="write every result to FILE")
    args = parser.parse_args(argv)
    if args.judge and args.lang != "python":
        parser.error("--judge runs on the python project only")
    return args


def main(argv=None):
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    started = time.monotonic()
    lang_kwargs = {} if args.lang == "python" else {"lang": args.lang}
    if args.json and not Path(args.json).absolute().parent.is_dir():
        print(f"the folder of --json {args.json} does not exist", file=sys.stderr)
        return 2
    made_here = args.root is None
    root = Path(tempfile.mkdtemp(prefix="tally-probe-")) if made_here else Path(args.root)
    try:
        project = build(root, repo_root=REPO_ROOT, **lang_kwargs)
    except Refused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    except ProbeError as error:
        print(f"build failed: {error}", file=sys.stderr)
        if made_here:
            print(f"probe folder kept: {root}", file=sys.stderr)
        return 1
    green, suite_line = run_suite(project, **lang_kwargs)
    cli = project / ".claude" / "cli" / "compass"
    checks = run_checks(project, cli=cli, **lang_kwargs)
    lines = format_lines(green, suite_line, checks)

    judged = None
    judge_failed = False
    if args.judge:
        try:
            judged = judge(project, repo_root=REPO_ROOT)
            lines.extend(_judge_lines(judged))
        except JudgeError as error:
            judge_failed = True
            lines.append(f"4j: failed: {error}")
    wall = time.monotonic() - started
    lines.append(f"wall: {wall:.1f}s")
    print("\n".join(lines))

    ok = (
        green
        and all(row["verdict"] == EXPECTED[row["check"]][row["letter"]] for row in checks)
        and all(row["rerun"] == "match" for row in checks)
        and not judge_failed
    )
    if args.json:
        Path(args.json).write_text(json.dumps({
            "suite": {"green": green, "last_line": suite_line},
            "checks": checks,
            "judge": judged,
            "wall_seconds": wall,
        }, indent=2) + "\n", encoding="utf-8")
    if made_here:
        if ok:
            _remove_tree(root)
        else:
            print(f"probe folder kept: {root}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
