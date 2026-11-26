"""Station ablation by planted defects: which checking station catches what.

A finished task of a kept pilot build gets one planted defect, and each
checking station of a Compass build is replayed on the planted state:

- `tester-pre`, mechanically: the test files of the task's pre-build tester
  commit (`test(TASK-NNN): failing tests before implementation`) run on the
  clean and the planted state; caught when a test fails on the planted state
  and not on the clean one.
- `builder-review`: the builder's two review sub-agents (the style and the
  correctness charter of the builder agent's code-review step), one session
  each on the builder's model, each ending in `FINDING <file>:<line>: ...`
  lines; caught when either names the planted site.
- `tester-post`: a `tester` agent session in post-build mode on the planted
  diff; caught when a test file it wrote or changed has a test that fails on
  the planted state and passes on the clean one.
- `validator`: a `validator` agent session on the task; caught when its report
  shows a failure and names the planted site.

Each station runs on its own copy, so no station sees another's work. A defect
is one mutation of a known class (`MUTATION_CLASSES`) on a non-test source line
the builder's commit added; the clone's builder commit is rewritten to carry
it, and a mutant that does not compile is dropped for the next site.

`eligibility` turns the per-defect results into, per `complexity:` letter and
station, the defects caught, those only that station caught, and whether the
station is lighter-eligible: it caught nothing no other station caught.

    python ablation.py pick --projects-root DIR --per-letter N --seed S
    python ablation.py run --projects-root DIR --out DIR --per-letter N --seed S [--jobs J] [--dry-run]
    python ablation.py report --out DIR

`run` keeps its progress in `<out>/progress.json`, one entry per task and
station, and resumes from it; a usage limit stops the batch with exit code 3.
Sessions start through `launch.run_session`, which isolates them in the
sandbox config with `--strict-mcp-config`. The report holds ids, letters,
classes and counts, never source or report text; each session's reply is kept
under `<out>/work/` for audit.
"""

import argparse
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import tokenize
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT / "plugin" / "cli") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "plugin" / "cli"))

import launch  # noqa: E402
import stationlib  # noqa: E402

MUTATION_CLASSES = ("comparison", "equality", "logic", "constant")
LETTERS = ("S", "M", "L")
STATIONS = ("tester-pre", "builder-review", "tester-post", "validator")
SESSIONS = ("review-style", "review-correctness", "tester-post", "validator")
LANGS = ("python", "go")

EXIT_USAGE_LIMIT = 3
SESSION_TIMEOUT = 2400
COMMAND_TIMEOUT = 900
LINE_WINDOW = 3
BUILDER_AGENT = REPO_ROOT / "plugin" / "templates" / "agents" / "builder.md"

PRE_SUBJECT = re.compile(r"^test\(([^)]*)\):\s*failing tests before implementation", re.IGNORECASE)
BUILD_SUBJECT = re.compile(r"^(TASK-\d+):")
TASK_ID = re.compile(r"TASK-\d+")
PLAN_LETTER = re.compile(r"^\s*- \[[ xX]\] (TASK-\d+):.*?\bcomplexity:\s*([A-Za-z]+)\b")


class Refused(Exception):
    """The operation was not carried out."""


class UsageLimit(Exception):
    """A session ended at the subscription's usage limit."""


class SessionFailed(Exception):
    """A session ended without a reply."""


@dataclass
class Site:
    path: str
    line: int
    cls: str
    col: int
    old: str
    new: str
    function: object = None


@dataclass
class Task:
    project: Path
    task: str
    letter: str
    lang: str
    pre_commit: str
    build_commit: str

    @property
    def key(self):
        return "%s|%s" % (Path(self.project).name, self.task)


# ------------------------------------------------------------ mutation sites


def _code_mask(text, lang):
    """A list of booleans, True where `text[i]` is code: not inside a string
    literal and not inside a trailing comment."""
    mask = [False] * len(text)
    i, quote = 0, None
    while i < len(text):
        ch = text[i]
        if quote is not None:
            if ch == "\\" and quote != "`":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if lang == "python" and ch == "#":
            break
        if lang == "go" and text.startswith("//", i):
            break
        if ch in ("'", '"') or (lang == "go" and ch == "`"):
            quote = ch
            i += 1
            continue
        mask[i] = True
        i += 1
    return mask


_COMPARISON = re.compile(r"(?<![<>=!\-:])(<=|>=|<|>)(?![<>=\-])")
_EQUALITY = re.compile(r"(==|!=)(?!=)")
_PY_LOGIC = re.compile(r"\b(and|or)\b")
_GO_LOGIC = re.compile(r"(&&|\|\|)")
_INTEGER = re.compile(r"(?<![\w.])(\d+)(?![\w.])")
_SWAP = {"<": "<=", "<=": "<", ">": ">=", ">=": ">", "==": "!=", "!=": "==",
         "and": "or", "or": "and", "&&": "||", "||": "&&"}


def _no_constant(text, lang):
    stripped = text.lstrip()
    if lang == "python":
        return stripped.startswith(("import ", "from ", "@"))
    return stripped.startswith("import ") or stripped.startswith("import(") or stripped == "import ("


def mutation_sites(text, lang):
    """Every mutation site of one source line: `(cls, col, old, new)` tuples,
    in column order within each class."""
    mask = _code_mask(text, lang)

    def in_code(start, end):
        return all(mask[start:end])

    sites = []
    for match in _COMPARISON.finditer(text):
        token = match.group(1)
        before = text[match.start() - 1] if match.start() > 0 else ""
        if token == ">" and before == "=":
            continue
        if in_code(match.start(), match.end()):
            sites.append(("comparison", match.start(), token, _SWAP[token]))
    for match in _EQUALITY.finditer(text):
        before = text[match.start() - 1] if match.start() > 0 else ""
        if before and before in "=!<>":
            continue
        if in_code(match.start(), match.end()):
            sites.append(("equality", match.start(), match.group(1), _SWAP[match.group(1)]))
    logic = _PY_LOGIC if lang == "python" else _GO_LOGIC
    for match in logic.finditer(text):
        if in_code(match.start(), match.end()):
            sites.append(("logic", match.start(), match.group(1), _SWAP[match.group(1)]))
    if not _no_constant(text, lang):
        for match in _INTEGER.finditer(text):
            token = match.group(1)
            start = match.start()
            if start > 0 and text[start - 1] in "+-" and start > 1 and text[start - 2] in "eE":
                continue
            if lang == "go" and token.startswith("0") and len(token) > 1:
                continue
            if in_code(start, match.end()):
                sites.append(("constant", start, token, str(int(token) + 1)))
    return sites


def apply_site(text, col, old, new):
    """`text` with the token `old` at `col` replaced by `new`."""
    if text[col:col + len(old)] != old:
        raise ValueError("no %r at column %d" % (old, col))
    return text[:col] + new + text[col + len(old):]


# ---------------------------------------------------------- paths and diffs


def is_test_path(path, lang):
    parts = Path(path).as_posix().split("/")
    name = parts[-1]
    if lang == "go":
        return name.endswith("_test.go") or "testdata" in parts[:-1]
    if any(part in ("tests", "test") for part in parts[:-1]):
        return True
    return name == "conftest.py" or (name.startswith("test_") and name.endswith(".py")) or name.endswith("_test.py")


def is_source_path(path, lang):
    suffix = ".py" if lang == "python" else ".go"
    return Path(path).suffix == suffix and not is_test_path(path, lang)


_HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def added_lines(diff_text):
    """`{path: [(new line number, text), ...]}` of the `+` lines of a unified diff."""
    added, path = {}, None
    old_left = new_left = 0
    number = 0
    for raw in diff_text.split("\n"):
        line = raw.rstrip("\r")
        if old_left > 0 or new_left > 0:
            if line.startswith("+"):
                if path is not None:
                    added.setdefault(path, []).append((number, line[1:]))
                number += 1
                new_left -= 1
            elif line.startswith("-"):
                old_left -= 1
            elif line.startswith("\\"):
                pass
            else:
                number += 1
                old_left -= 1
                new_left -= 1
            continue
        if line.startswith("+++ "):
            target = line[4:].strip()
            path = None if target == "/dev/null" else (target[2:] if target.startswith("b/") else target)
            continue
        hunk = _HUNK.match(line)
        if hunk:
            old_left = int(hunk.group(1)) if hunk.group(1) is not None else 1
            number = int(hunk.group(2))
            new_left = int(hunk.group(3)) if hunk.group(3) is not None else 1
    return added


_PY_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)")
_GO_FUNC = re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?(\w+)\s*[\[(]")


def enclosing_function(lines, lineno, lang):
    pattern = _PY_DEF if lang == "python" else _GO_FUNC
    for index in range(min(lineno, len(lines)) - 1, -1, -1):
        match = pattern.match(lines[index])
        if match:
            return match.group(1)
    return None


# -------------------------------------------------------------- git helpers


def _git_env():
    return launch.git_environment()


def _run(argv, cwd, *, timeout=COMMAND_TIMEOUT, env=None):
    """`(returncode, stdout + stderr)` of a command, never raising on a
    failing exit or a timeout."""
    try:
        done = subprocess.run(
            [str(a) for a in argv], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, env=env, **launch.NO_WINDOW,
        )
    except subprocess.TimeoutExpired as error:
        return 124, "%s%s" % (error.stdout or "", error.stderr or "")
    except OSError as error:
        return 127, str(error)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def _git(repo, *args, check=True):
    code, out = _run(["git", *args], repo, env=_git_env())
    if check and code != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), out.strip()[-400:]))
    return out.strip()


def _git_raw(repo, *args):
    done = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, env=_git_env(), **launch.NO_WINDOW,
    )
    if done.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), done.stderr.decode("utf-8", "replace")[-400:]))
    return done.stdout.decode("utf-8", "replace")


def _inside_work_tree(folder):
    here = Path(os.path.abspath(folder))
    return any((parent / ".git").exists() for parent in (here, *here.parents))


# ---------------------------------------------------------- task discovery


def project_lang(project):
    project = Path(project)
    if (project / "pyproject.toml").is_file():
        return "python"
    if (project / "go.mod").is_file():
        return "go"
    return None


def plan_letters(project):
    letters = {}
    plans = Path(project) / ".compass" / "plans"
    for path in sorted(plans.rglob("*.md")) if plans.is_dir() else []:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = PLAN_LETTER.match(line)
            if match and match.group(2).upper() in LETTERS and len(match.group(2)) == 1:
                letters[match.group(1)] = match.group(2).upper()
    return letters


def find_tasks(project):
    project = Path(project)
    lang = project_lang(project)
    if lang is None or not (project / ".git").exists():
        return []
    letters = plan_letters(project)
    log = _git(project, "log", "--format=%H%x09%s", check=False)
    pre, build = {}, {}
    for line in log.splitlines():
        sha, _tab, subject = line.partition("\t")
        found = PRE_SUBJECT.match(subject)
        if found:
            for task in TASK_ID.findall(found.group(1)):
                pre.setdefault(task, sha)
            continue
        found = BUILD_SUBJECT.match(subject)
        if found:
            build.setdefault(found.group(1), []).append(sha)
    tasks = []
    for task, shas in sorted(build.items()):
        if len(shas) != 1 or task not in pre or task not in letters:
            continue
        code, _out = _run(["git", "merge-base", "--is-ancestor", pre[task], shas[0]], project, env=_git_env())
        if code != 0:
            continue
        tasks.append(Task(project=project, task=task, letter=letters[task], lang=lang,
                          pre_commit=pre[task], build_commit=shas[0]))
    return tasks


def pick(tasks, per_letter, seed):
    """At most `per_letter` tasks per letter, drawn round-robin over projects
    in a seeded order, so a project gives a second task of a letter only once
    every other project with that letter has given one."""
    rng = random.Random(seed)
    ordered = sorted(tasks, key=lambda t: (t.letter, Path(t.project).name, t.task))
    picked = []
    for letter in LETTERS:
        by_project = {}
        for task in ordered:
            if task.letter == letter:
                by_project.setdefault(Path(task.project).name, []).append(task)
        names = sorted(by_project)
        rng.shuffle(names)
        for name in names:
            rng.shuffle(by_project[name])
        chosen = []
        while len(chosen) < per_letter and any(by_project[n] for n in names):
            for name in names:
                if by_project[name] and len(chosen) < per_letter:
                    chosen.append(by_project[name].pop(0))
        picked.extend(chosen)
    return picked


# ------------------------------------------------------------------ planting


def default_compile_check(dest, site, lang):
    if lang == "python":
        code, _out = _run([sys.executable, "-m", "py_compile", Path(dest) / site.path], dest)
        return code == 0
    code, _out = _run(["go", "build", "./..."], dest)
    return code == 0


def multiline_text_lines(source, lang):
    """The 1-based numbers of the lines a string literal or comment spanning
    more than one line touches (a Python docstring or triple-quoted string, a
    Go raw string or block comment). A line-by-line reading cannot tell their
    inner lines from code."""
    lines = set()
    if lang == "python":
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        except (tokenize.TokenError, SyntaxError, IndentationError):
            return set(range(1, source.count("\n") + 2))
        starts = []
        for token in tokens:
            name = tokenize.tok_name[token.type]
            if name in ("FSTRING_START", "TSTRING_START"):
                starts.append(token.start[0])
            elif name in ("FSTRING_END", "TSTRING_END") and starts:
                first = starts.pop()
                if token.end[0] > first:
                    lines.update(range(first, token.end[0] + 1))
            elif token.type == tokenize.STRING and token.end[0] > token.start[0]:
                lines.update(range(token.start[0], token.end[0] + 1))
        return lines
    i, line, n = 0, 1, len(source)
    while i < n:
        ch = source[i]
        if ch == "\n":
            line += 1
            i += 1
        elif source.startswith("//", i):
            while i < n and source[i] != "\n":
                i += 1
        elif ch == '"' or ch == "'":
            i += 1
            while i < n and source[i] not in (ch, "\n"):
                i += 2 if source[i] == "\\" else 1
            i += 1
        elif ch == "`" or source.startswith("/*", i):
            end_mark = "`" if ch == "`" else "*/"
            end = source.find(end_mark, i + (1 if ch == "`" else 2))
            end = n if end < 0 else end + len(end_mark)
            last = line + source.count("\n", i, end)
            if last > line:
                lines.update(range(line, last + 1))
            line, i = last, end
        else:
            i += 1
    return lines


def _candidate_sites(diff_text, lang, cls, read=None):
    """`(path, line, cls, col, old, new)` for every site on an added source
    line; `read(path)` gives a file's text, whose multi-line strings and
    comments are left out."""
    found = []
    for path, lines in sorted(added_lines(diff_text).items()):
        if not is_source_path(path, lang):
            continue
        skip = multiline_text_lines(read(path), lang) if read is not None else set()
        for number, text in lines:
            if number in skip:
                continue
            for kind, col, old, new in mutation_sites(text, lang):
                if cls is None or kind == cls:
                    found.append((path, number, kind, col, old, new))
    return found


def plant(task, dest, *, seed, cls=None, compile_check=None):
    dest = Path(os.path.abspath(dest))
    if _inside_work_tree(dest.parent) or _inside_work_tree(dest):
        raise Refused("%s is inside a git work tree" % dest)
    if dest.exists() and any(dest.iterdir()):
        raise Refused("%s is not empty" % dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", "-q", "--no-hardlinks", "--no-checkout", Path(task.project).resolve(), dest],
         dest.parent, env=_git_env())
    if not (dest / ".git").exists():
        raise RuntimeError("git clone of %s failed" % Path(task.project).name)
    _git(dest, "branch", "-f", "clean", task.build_commit)
    _git(dest, "checkout", "-q", "-f", "clean")
    diff = _git_raw(dest, "diff", "--no-color", "--no-ext-diff", "-U0", task.build_commit + "^", task.build_commit)
    candidates = _candidate_sites(
        diff, task.lang, cls, read=lambda path: (dest / path).read_bytes().decode("utf-8", "replace"))
    random.Random(seed).shuffle(candidates)
    check = compile_check or (lambda d, s: default_compile_check(d, s, task.lang))
    for path, number, kind, col, old, new in candidates:
        file = dest / path
        raw = file.read_bytes().decode("utf-8")
        lines = raw.split("\n")
        if number > len(lines):
            continue
        text = lines[number - 1]
        ending = "\r" if text.endswith("\r") else ""
        body = text[:-1] if ending else text
        if body[col:col + len(old)] != old:
            continue
        site = Site(path=path, line=number, cls=kind, col=col, old=old, new=new,
                    function=enclosing_function([ln.rstrip("\r") for ln in lines], number, task.lang))
        lines[number - 1] = apply_site(body, col, old, new) + ending
        file.write_bytes("\n".join(lines).encode("utf-8"))
        if check(dest, site):
            _commit_planted(dest, task, path)
            return site
        file.write_bytes(raw.encode("utf-8"))
    raise Refused("no compiling mutant on the added source lines of %s" % task.task)


def _commit_planted(dest, task, path):
    meta = _git(dest, "log", "-1", "--format=%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI", task.build_commit).split("\x00")
    message = _git_raw(dest, "log", "-1", "--format=%B", task.build_commit)
    _git(dest, "add", "--", path)
    tree = _git(dest, "write-tree")
    env = dict(_git_env())
    env.update({"GIT_AUTHOR_NAME": meta[0], "GIT_AUTHOR_EMAIL": meta[1], "GIT_AUTHOR_DATE": meta[2],
                "GIT_COMMITTER_NAME": meta[3], "GIT_COMMITTER_EMAIL": meta[4], "GIT_COMMITTER_DATE": meta[5]})
    done = subprocess.run(
        ["git", "commit-tree", tree, "-p", task.build_commit + "^"], cwd=str(dest), input=message.encode("utf-8"),
        capture_output=True, env=env, **launch.NO_WINDOW,
    )
    if done.returncode != 0:
        raise RuntimeError("git commit-tree failed: %s" % done.stderr.decode("utf-8", "replace"))
    sha = done.stdout.decode().strip()
    _git(dest, "checkout", "-q", "-f", "-B", "planted", sha)


# -------------------------------------------------------------- test outputs


_PYTEST_FAIL = re.compile(r"^(?:FAILED|ERROR) (\S.*?)(?: - .*)?$")
_GO_FAIL = re.compile(r"^\s*--- FAIL: (\S+)")


def failing_tests(output, lang):
    found = set()
    pattern = _PYTEST_FAIL if lang == "python" else _GO_FAIL
    for line in (output or "").splitlines():
        match = pattern.match(line.rstrip("\r"))
        if match:
            found.add(match.group(1).strip())
    return found


def caught_by_tests(clean_failing, planted_failing):
    return bool(set(planted_failing) - set(clean_failing))


# The name a test run that produced no test result is filed under: a
# missing test runner, an import or build error, a timeout.
RUN_ERROR = "<run %s exit %d>"


def run_errors(failing):
    return sorted(name for name in failing if name.startswith("<run "))


_GO_TEST_FUNC = re.compile(r"^func (Test\w+)\(", re.MULTILINE)


def _uses_uv(tree):
    """Whether `tree`'s Python runs through uv: uv is installed and the
    project has a lock file or names pytest in its `pyproject.toml`."""
    if shutil.which("uv") is None:
        return False
    if (Path(tree) / "uv.lock").is_file():
        return True
    if requirement_files(tree):
        return True
    pyproject = Path(tree) / "pyproject.toml"
    return pyproject.is_file() and "pytest" in pyproject.read_text(encoding="utf-8", errors="replace")


def _uv_python(tree):
    """The command that runs the project's Python in `tree`: `uv run` (with
    `--frozen` when the project has a lock file), so the project's own
    dependencies are present, else the running interpreter."""
    if not _uses_uv(tree):
        return [sys.executable]
    frozen = ["--frozen"] if (Path(tree) / "uv.lock").is_file() else []
    return ["uv", "run", *frozen, "--quiet", "python"]


def run_tests(tree, files, lang):
    """The failing tests of `files` (paths relative to `tree`) run in `tree`.
    A collection or build error counts as a failure of the files' tests."""
    files = [f for f in files if (Path(tree) / f).is_file()]
    if not files:
        return set()
    if lang == "python":
        argv = _uv_python(tree)
        argv += ["-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider", *files]
        env = {k: v for k, v in os.environ.items() if k.upper() != "VIRTUAL_ENV"}
        code, out = _run(argv, tree, env=env)
        failing = failing_tests(out, lang)
        if code != 0 and not failing:
            failing = {RUN_ERROR % (",".join(files), code)}
        return failing
    names = set()
    for f in files:
        names.update(_GO_TEST_FUNC.findall((Path(tree) / f).read_text(encoding="utf-8", errors="replace")))
    packages = sorted({"./" + Path(f).parent.as_posix() for f in files})
    code, out = _run(["go", "test", "-count=1", "-v", *packages], tree)
    failing = {name for name in failing_tests(out, lang) if name.split("/")[0] in names}
    if code != 0 and not failing and "--- FAIL" not in out:
        failing = {RUN_ERROR % (",".join(packages), code)}
    return failing


# ------------------------------------------------------------ the judges


def _basename(path):
    return Path(path).name


def _names_function(text, site):
    return bool(site.function) and re.search(r"(?<!\w)" + re.escape(site.function) + r"(?!\w)", text) is not None


def names_site(text, site, window=LINE_WINDOW):
    """Whether `text` points at the planted site: the site's file with a line
    within `window` of it, or the site's file together with the name of the
    function enclosing it (a function name alone, such as `handle`, is too
    common a word to credit)."""
    text = text or ""
    base = re.escape(_basename(site.path))
    named_file = False
    for match in re.finditer(r"(?<![\w.\-])(?:[\w.\-]+[/\\])*" + base + r"(?!\w)(?::(\d+))?", text):
        named_file = True
        if match.group(1) is not None and abs(int(match.group(1)) - site.line) <= window:
            return True
    return named_file and _names_function(text, site)


_FINDING = re.compile(r"^[\s>*_\-]*\**FINDING\**[\s*`]+(?!none\b)([^\s`*:]+):(\d+)[`*]*\s*:\s*(.+?)\s*$",
                      re.IGNORECASE)


def parse_findings(text):
    found = []
    for line in (text or "").splitlines():
        match = _FINDING.match(line.rstrip("\r"))
        if match:
            found.append((match.group(1), int(match.group(2)), match.group(3)))
    return found


def review_caught(report, site):
    for path, line, sentence in parse_findings(report):
        if _basename(path) == _basename(site.path) and abs(line - site.line) <= LINE_WINDOW:
            return True
        if _basename(path) == _basename(site.path) and _names_function(sentence, site):
            return True
    return False


def bugs_section(report):
    """The text under the tester report's `Bugs Found` heading, up to the next
    heading of the same or a higher level; empty when there is none."""
    match = re.search(r"^(#{2,6})\s*Bugs Found[^\n]*\n(.*?)(?=^#{2,6}\s|\Z)", report or "",
                      re.MULTILINE | re.DOTALL)
    return match.group(2) if match else ""


def tester_caught(report, site, tests_caught):
    """Whether the post-build tester caught the planted defect: a test it
    wrote or changed tells the planted state from the clean one, or its
    report counts a bug (`stationlib`) whose Bugs Found entry names the site."""
    if tests_caught:
        return True
    parsed = stationlib.parse_report("tester", report)
    return (parsed.get("bugs") or 0) > 0 and names_site(bugs_section(report), site)


def validator_failed(report):
    parsed = stationlib.parse_report("validator", report)
    if parsed.get("station") != "validator":
        return False
    return parsed.get("result") in ("FAIL", "PARTIAL") or (parsed.get("fails") or 0) > 0


def validator_caught(report, site):
    return validator_failed(report) and names_site(report, site)


# ---------------------------------------------------------- the eligibility


def eligibility(results):
    table = {}
    for result in results:
        letter = result["letter"]
        cell = table.setdefault(letter, {"defects": 0, "none": 0,
                                         **{s: {"caught": 0, "only": 0, "eligible": False} for s in STATIONS}})
        caught = [s for s in STATIONS if result["caught"].get(s)]
        cell["defects"] += 1
        if not caught:
            cell["none"] += 1
        for station in caught:
            cell[station]["caught"] += 1
        if len(caught) == 1:
            cell[caught[0]]["only"] += 1
    for cell in table.values():
        any_caught = cell["defects"] > cell["none"]
        for station in STATIONS:
            cell[station]["eligible"] = any_caught and cell[station]["only"] == 0
    return table


# -------------------------------------------------------------- sessions


def session_extra_args(station):
    if station in ("review-style", "review-correctness"):
        return ["--model", "sonnet", "--allowedTools", "Read,Grep,Glob"]
    if station == "tester-post":
        return ["--agent", "tester", "--allowedTools", "Read,Grep,Glob,Bash,Write,Edit"]
    if station == "validator":
        return ["--agent", "validator", "--allowedTools", "Read,Grep,Glob,Bash"]
    raise ValueError("%s runs no session" % station)


def run_station_session(station, folder, prompt, *, private_root=None, claude_cmd=None, timeout=SESSION_TIMEOUT):
    """The reply text of one station session in `folder`."""
    result = launch.run_session(
        folder, prompt, repo_root=REPO_ROOT, private_root=private_root, claude_cmd=claude_cmd,
        extra_args=session_extra_args(station), timeout=timeout,
    )
    if result.status == launch.USAGE_LIMIT:
        raise UsageLimit("usage limit reached%s" % (" (resets at %s)" % result.resets_at if result.resets_at else ""))
    if result.status != launch.DONE:
        raise SessionFailed("%s session exited %s" % (station, result.returncode))
    finals = [event for event in result.events if event.get("type") == "result"]
    reply = finals[-1].get("result") if finals else None
    return reply if isinstance(reply, str) else ""


def _review_charters():
    """(style charter, correctness charter) from the builder agent's code-review step."""
    text = BUILDER_AGENT.read_text(encoding="utf-8")
    match = re.search(r"^### 8\. Code review\s*\n(.*?)(?=^### )", text, re.MULTILINE | re.DOTALL)
    section = match.group(1).strip() if match else ""
    style, _sep, rest = section.partition("Then spawn a second sub-agent")
    correctness = rest.split("\n\nFix any issues")[0]
    return style.strip(), ("Then spawn a second sub-agent" + correctness).strip()


FINDING_RULE = (
    "End your reply with one line per finding, each in the form `FINDING <file>:<line>: <one sentence>`, "
    "the file path relative to the project root; write `FINDING none` when you have no finding."
)


def _task_body(project, task):
    plans = Path(project) / ".compass" / "plans"
    for path in sorted(plans.rglob("*.md")):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for index, line in enumerate(lines):
            if re.match(r"^\s*- \[[ xX]\] %s:" % re.escape(task), line):
                body = [line]
                for follow in lines[index + 1:]:
                    if re.match(r"^\s*- \[[ xX]\] TASK-\d+:", follow) or follow.startswith("#"):
                        break
                    if follow.strip() == "" and body and body[-1].strip() == "":
                        break
                    body.append(follow)
                return path.relative_to(project).as_posix(), "\n".join(body).strip()
    return None, ""


def requirements_text(tree, plan_rel, task):
    if not plan_rel:
        return ""
    plan_text = (Path(tree) / plan_rel).read_text(encoding="utf-8", errors="replace")
    head = plan_text.split("\n---", 2)[1] if plan_text.startswith("---") else ""
    parts = []
    for name in dict.fromkeys(re.findall(r"\[\[(?:[^\]|#]*/)?(SPEC-[^\]|#/]+)", head)):
        found = sorted((Path(tree) / ".compass" / "specs").rglob(name + "*.md"))
        if not found:
            continue
        rel = found[0].relative_to(tree).as_posix()
        code, text = _run([sys.executable, ".claude/cli/compass", "requirements", rel, "--for-task", task,
                           "--plan", plan_rel], tree)
        if code == 0 and text.strip():
            parts.append("%s:\n%s" % (rel, text.strip()))
    return "\n\n".join(parts)


def prompts(tree, task, site_diff, plan_rel, body):
    style, correctness = _review_charters()
    common = (
        "You review the builder's change for %s of `%s` in this project. The change is the diff below "
        "(`git diff %s..HEAD`). Read any file you need.\n\nThe task:\n%s\n\nThe diff:\n```diff\n%s\n```\n\n"
        % (task.task, plan_rel, task.pre_commit[:12], body, site_diff)
    )
    requirements = requirements_text(tree, plan_rel, task.task)
    return {
        "review-style": common + "Your charter:\n" + style + "\n\n" + FINDING_RULE,
        "review-correctness": (
            common + "Your charter:\n" + correctness + "\n\nThe output of `compass requirements`:\n"
            + (requirements or "(no requirement rows for this task)") + "\n\n" + FINDING_RULE
        ),
        "tester-post": (
            "You are in post-build mode for %s of `%s`. The builder has finished; its diff is "
            "`git diff %s..HEAD` in this folder, shown below. In this project `compass` means "
            "`python .claude/cli/compass`.\n\nThe task:\n%s\n\nThe builder's diff:\n```diff\n%s\n```\n"
            % (task.task, plan_rel, task.pre_commit[:12], body, site_diff)
        ),
        "validator": (
            "Validate %s of `%s` as a phase of one task. The diff baseline is commit %s, the commit before "
            "the builder's; the builder's commit is HEAD. Check only this task; the plan's other tasks are "
            "already validated. In this project `compass` means `python .claude/cli/compass`. End with your "
            "report in your report format, with its VERDICT line." % (task.task, plan_rel, task.pre_commit[:12])
        ),
    }


# ------------------------------------------------------------------- run


def _install(tree):
    agents = Path(tree) / ".claude" / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    for name in ("tester.md", "validator.md"):
        shutil.copyfile(REPO_ROOT / "plugin" / "templates" / "agents" / name, agents / name)
    cli = Path(tree) / ".claude" / "cli"
    if not cli.exists():
        shutil.copytree(REPO_ROOT / "plugin" / "cli", cli,
                        ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"))


def _changed_test_files(tree, lang):
    out = _git(tree, "status", "--porcelain", "--untracked-files=all")
    files = []
    for line in out.splitlines():
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path.startswith((".claude/", ".compass/")):
            continue
        if is_test_path(path, lang) and Path(path).suffix in (".py", ".go"):
            files.append(path)
    return sorted(files)


def _progress(out, config):
    path = Path(out) / "progress.json"
    if not path.is_file():
        return {"config": config, "done": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("config") != config:
        raise Refused("%s belongs to a different configuration; give a new --out" % path)
    return data


_LOCK = threading.Lock()


def _save(out, data):
    with _LOCK:
        path = Path(out) / "progress.json"
        scratch = path.with_suffix(".tmp")
        scratch.write_text(json.dumps(data, indent=1), encoding="utf-8")
        scratch.replace(path)


def _all_projects(root):
    root = Path(root)
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / ".git").exists()) if root.is_dir() else []


def _pool(projects_root):
    tasks = []
    for project in _all_projects(projects_root):
        tasks.extend(find_tasks(project))
    return tasks


def _prepare(task, work, seed):
    """Plant `task` under `work` and make the station copies. Returns the
    entry stored in the progress file."""
    repo = work / "repo"
    site = plant(task, repo, seed=seed)
    for name, ref in (("clean", "clean"), ("review", "planted"), ("validate", "planted")):
        _git(repo, "worktree", "add", "-q", "--detach", str(work / name), ref)
    for tree in (repo, work / "review", work / "validate"):
        _install(tree)
    text = (repo / site.path).read_text(encoding="utf-8").split("\n")[site.line - 1]
    return {
        "project": Path(task.project).name, "task": task.task, "letter": task.letter, "lang": task.lang,
        "pre": task.pre_commit, "build": task.build_commit,
        "site": {**asdict(site), "text": text.rstrip("\r")}, "caught": {}, "rows": {},
    }


def _pre_tests(work, task):
    files = [f for f in _git(work / "repo", "diff", "--name-only", task.pre_commit + "^", task.pre_commit).splitlines()
             if is_test_path(f, task.lang)]
    clean = run_tests(work / "clean", files, task.lang)
    planted = run_tests(work / "repo", files, task.lang)
    return caught_by_tests(clean, planted), {"files": len(files), "clean_failing": len(clean),
                                             "planted_failing": len(planted),
                                             "run_errors": len(run_errors(clean)) + len(run_errors(planted))}


def _station(entry, station, work, task, private_root, claude_cmd, prompt_set):
    site = Site(**{k: v for k, v in entry["site"].items() if k != "text"})
    replies = work / "replies"
    replies.mkdir(exist_ok=True)
    folder = {"review-style": work / "review", "review-correctness": work / "review",
              "tester-post": work / "repo", "validator": work / "validate"}[station]
    reply = run_station_session(station, folder, prompt_set[station], private_root=private_root,
                                claude_cmd=claude_cmd)
    (replies / (station + ".md")).write_text(reply, encoding="utf-8")
    if station.startswith("review-"):
        return {"caught": review_caught(reply, site), "findings": len(parse_findings(reply))}
    if station == "validator":
        parsed = stationlib.parse_report("validator", reply)
        return {"caught": validator_caught(reply, site), "row": {k: parsed.get(k) for k in
                                                                ("station", "result", "fails", "verdict")}}
    files = _changed_test_files(work / "repo", task.lang)
    for rel in files:
        target = work / "clean" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(work / "repo" / rel, target)
    planted = run_tests(work / "repo", files, task.lang)
    clean = run_tests(work / "clean", files, task.lang)
    parsed = stationlib.parse_report("tester", reply)
    tests = caught_by_tests(clean, planted)
    return {"caught": tester_caught(reply, site, tests), "tests_caught": tests, "files": len(files),
            "row": {k: parsed.get(k) for k in ("station", "bugs", "verdict")}}


def requirement_files(tree):
    """The `requirements*.txt` files at the root of `tree`, sorted."""
    return sorted(p.name for p in Path(tree).glob("requirements*.txt") if p.is_file())


def setup_commands(tree):
    """The commands that give `tree` its own environment: `uv sync` with every
    group and extra, then `uv pip install -r` of each root requirements file,
    since some projects list their test tools only there."""
    if not _uses_uv(tree):
        return []
    frozen = ["--frozen"] if (Path(tree) / "uv.lock").is_file() else []
    commands = [["uv", "sync", *frozen, "--all-groups", "--all-extras", "--quiet"]]
    for name in requirement_files(tree):
        commands.append(["uv", "pip", "install", "--quiet", "--python", ".venv", "-r", name])
    return commands


def _setup_env(work, lang):
    if lang != "python":
        return
    env = {k: v for k, v in os.environ.items() if k.upper() != "VIRTUAL_ENV"}
    for name in ("repo", "clean", "validate"):
        for argv in setup_commands(work / name):
            _run(argv, work / name, env=env)


def run(args, *, claude_cmd=None):
    out = Path(os.path.abspath(args.out))
    if _inside_work_tree(out):
        raise Refused("--out %s is inside a git work tree" % out)
    config = {"seed": args.seed, "per_letter": args.per_letter}
    if args.dry_run:
        if (out / "progress.json").is_file():
            _progress(out, config)
        for task in pick(_pool(args.projects_root), args.per_letter, args.seed):
            print("%s %s %s %s" % (Path(task.project).name, task.task, task.letter, task.lang))
        return 0
    out.mkdir(parents=True, exist_ok=True)
    data = _progress(out, config)
    private_root = Path(args.private_root) if args.private_root else None
    tasks = pick(_pool(args.projects_root), args.per_letter, args.seed)
    jobs = []
    prompt_sets = {}
    for index, task in enumerate(tasks):
        work = out / "work" / ("%s-%s" % (Path(task.project).name, task.task))
        entry = data["done"].get(task.key)
        if task.key in data.get("skipped", {}):
            continue
        if entry is None:
            if work.exists():
                shutil.rmtree(work, ignore_errors=True)
            try:
                entry = _prepare(task, work, args.seed + index)
            except Refused as error:
                data.setdefault("skipped", {})[task.key] = {"letter": task.letter, "reason": str(error)}
                _save(out, data)
                print("skipped %s: %s" % (task.key, error), file=sys.stderr)
                continue
            _setup_env(work, task.lang)
            data["done"][task.key] = entry
            _save(out, data)
        if "tester-pre" not in entry["caught"] or args.recheck_pre:
            caught, counts = _pre_tests(work, task)
            entry["caught"]["tester-pre"] = caught
            entry["rows"]["tester-pre"] = counts
            _save(out, data)
        diff = _git_raw(work / "repo", "diff", "--no-color", task.pre_commit, "planted", "--", ".",
                        ":(exclude).compass")
        plan_rel, body = _task_body(work / "repo", task.task)
        prompt_sets[task.key] = prompts(work / "repo", task, diff, plan_rel, body)
        for station in SESSIONS:
            if station not in entry.get("sessions", {}):
                jobs.append((task, work, entry, station))

    def one(item):
        task, work, entry, station = item
        result = _station(entry, station, work, task, private_root, claude_cmd, prompt_sets[task.key])
        with _LOCK:
            entry.setdefault("sessions", {})[station] = result
            _fold(entry)
        _save(out, data)
        print("%s %s %s caught=%s" % (task.key, task.letter, station, result["caught"]), file=sys.stderr)

    halted = None
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = [pool.submit(one, item) for item in jobs]
        for future in futures:
            try:
                future.result()
            except UsageLimit as error:
                halted = error
            except SessionFailed as error:
                print("session failed: %s" % error, file=sys.stderr)
    if halted is not None:
        print("usage limit: %s; run the same command again to resume" % halted, file=sys.stderr)
        return EXIT_USAGE_LIMIT
    print(render_report(data))
    return 0


def _fold(entry):
    sessions = entry.get("sessions", {})
    if "review-style" in sessions and "review-correctness" in sessions:
        entry["caught"]["builder-review"] = bool(sessions["review-style"]["caught"]
                                                 or sessions["review-correctness"]["caught"])
    for station in ("tester-post", "validator"):
        if station in sessions:
            entry["caught"][station] = bool(sessions[station]["caught"])
            if "row" in sessions[station]:
                entry["rows"][station] = sessions[station]["row"]


def rejudge(out):
    """Judge every saved session reply again with the current judges and
    rewrite the verdicts in `<out>/progress.json`. The test-run results of
    the tester are kept as recorded; no session or test runs."""
    out = Path(out)
    data = json.loads((out / "progress.json").read_text(encoding="utf-8"))
    for entry in data.get("done", {}).values():
        site = Site(**{k: v for k, v in entry["site"].items() if k != "text"})
        replies = out / "work" / ("%s-%s" % (entry["project"], entry["task"])) / "replies"
        for station, result in entry.get("sessions", {}).items():
            path = replies / (station + ".md")
            if not path.is_file():
                continue
            reply = path.read_text(encoding="utf-8")
            if station.startswith("review-"):
                result["caught"] = review_caught(reply, site)
            elif station == "validator":
                result["caught"] = validator_caught(reply, site)
            else:
                tests = result.get("tests_caught", result["caught"])
                result["tests_caught"] = tests
                result["caught"] = tester_caught(reply, site, tests)
        _fold(entry)
    _save(out, data)
    return data


def _complete(entry):
    return all(station in entry.get("caught", {}) for station in STATIONS)


def render_report(data):
    entries = [e for e in data.get("done", {}).values() if _complete(e)]
    lines = ["defects with every station read: %d of %d" % (len(entries), len(data.get("done", {})))]
    for key, skipped in sorted(data.get("skipped", {}).items()):
        lines.append("skipped %s (%s): no compiling mutant" % (key, skipped["letter"]))
    table = eligibility([{"letter": e["letter"], "caught": e["caught"]} for e in entries])
    lines.append("")
    lines.append("| Letter | Defects | Caught by none | " + " | ".join(STATIONS) + " |")
    lines.append("|---|---|---|" + "---|" * len(STATIONS))
    for letter in LETTERS:
        if letter not in table:
            continue
        cell = table[letter]
        parts = ["%d caught, %d only, %s" % (cell[s]["caught"], cell[s]["only"],
                                             "eligible" if cell[s]["eligible"] else "not eligible") for s in STATIONS]
        lines.append("| %s | %d | %d | %s |" % (letter, cell["defects"], cell["none"], " | ".join(parts)))
    lines.append("")
    lines.append("| Task | Letter | Lang | Class | " + " | ".join(STATIONS) + " |")
    lines.append("|---|---|---|---|" + "---|" * len(STATIONS))
    for key, entry in sorted(data.get("done", {}).items()):
        marks = [{True: "caught", False: "missed"}.get(entry["caught"].get(s), "pending") for s in STATIONS]
        lines.append("| %s | %s | %s | %s | %s |" % (key, entry["letter"], entry["lang"], entry["site"]["cls"],
                                                    " | ".join(marks)))
    return "\n".join(lines)


def main(argv=None, *, claude_cmd=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("pick", "run"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--projects-root", required=True)
        cmd.add_argument("--per-letter", type=int, required=True)
        cmd.add_argument("--seed", type=int, default=0)
    run_cmd = sub.choices["run"]
    run_cmd.add_argument("--out", required=True)
    run_cmd.add_argument("--jobs", type=int, default=1)
    run_cmd.add_argument("--private-root")
    run_cmd.add_argument("--dry-run", action="store_true")
    run_cmd.add_argument("--recheck-pre", action="store_true",
                         help="run the pre-build tester's tests again for defects already planted")
    report = sub.add_parser("report")
    report.add_argument("--out", required=True)
    report.add_argument("--rejudge", action="store_true",
                        help="judge the saved replies again before reporting")
    args = parser.parse_args(argv)
    try:
        if args.command == "pick":
            for task in pick(_pool(args.projects_root), args.per_letter, args.seed):
                print("%s %s %s %s" % (Path(task.project).name, task.task, task.letter, task.lang))
            return 0
        if args.command == "report":
            path = Path(args.out) / "progress.json"
            if not path.is_file():
                print("ablation: no progress file in %s" % args.out, file=sys.stderr)
                return 1
            data = rejudge(args.out) if args.rejudge else json.loads(path.read_text(encoding="utf-8"))
            print(render_report(data))
            return 0
        return run(args, claude_cmd=claude_cmd)
    except Refused as error:
        print("ablation: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
