"""Reach: which changed lines a coverage report shows as run.

Intersects the added and changed lines of a unified diff with a coverage
report (LCOV or Cobertura XML) and names the changed lines that never ran,
along with functions that start on a changed line and were never called
(a one-line function can have every line counted as run while the function
itself never executed).

A measurement that did not happen is never a percentage: a missing, empty
or unreadable report, or one that names none of the changed files, yields a
SKIP verdict; a diff with no executable change yields N/A.

`coverage_rc`, `PTH_NAME` and `PTH_BODY` describe the measurement setup that
`compass reach --run` builds around a Python command: an rc file measuring
the files of the repository that run, and a startup file that makes every Python
process of one virtual environment measure itself.

Coverage shape, per repo-relative POSIX path:

    {"lines": {line number: hit count}, "functions": [(name, line, hits)]}
"""

import fnmatch
import re
import xml.etree.ElementTree as ET

TEST_DIRS = ("tests",)
TEST_NAME_PATTERNS = ("test_*", "*_test.*", "*.test.*", "*.spec.*")
SOURCE_EXTENSIONS = frozenset(
    "py pyw js mjs cjs jsx ts tsx mts cts vue svelte go rs java kt kts scala rb "
    "php c h cc cpp cxx hpp cs swift m mm lua sh bash ps1 pl r dart ex exs erl "
    "clj fs groovy".split()
)

PTH_NAME = "compass_reach_cov.pth"
PTH_BODY = "import coverage; coverage.process_startup()\n"
MIN_COVERAGE = (7, 10)
_NON_SOURCE_DIRS = (".venv", "venv", "site-packages", "node_modules")

_HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_DRIVE = re.compile(r"^[A-Za-z]:/")
_XML_DECLARATION = re.compile(r"^\s*<\?xml[^>]*\?>")
_FN_RANGE = re.compile(r"^(\d+),\d+,(.*)$")
_FN_PLAIN = re.compile(r"^(\d+),(.*)$")


def is_test_path(path):
    """True when the path is a test file: under a `tests/` directory, or named
    `test_*`, `*_test.*`, `*.test.*` or `*.spec.*`."""
    parts = path.replace("\\", "/").split("/")
    if any(part in TEST_DIRS for part in parts[:-1]):
        return True
    return any(fnmatch.fnmatchcase(parts[-1], pat) for pat in TEST_NAME_PATTERNS)


def changed_lines_from_diff(diff_text):
    """Added and changed new-side line numbers of non-test files, read from
    `git diff -U0` text. Returns {repo-relative POSIX path: [line numbers]}.
    Deleted files, pure deletions and test files contribute nothing."""
    lines = diff_text.split("\n")
    changed = {}
    current = None
    index = 0
    while index < len(lines):
        line = lines[index].rstrip("\r")
        index += 1
        if line.startswith("+++ "):
            current = _new_path(line[4:])
            continue
        match = _HUNK.match(line)
        if not match:
            continue
        old_left = 1 if match.group(1) is None else int(match.group(1))
        new_left = 1 if match.group(3) is None else int(match.group(3))
        new_line = int(match.group(2))
        while (old_left > 0 or new_left > 0) and index < len(lines):
            body = lines[index].rstrip("\r")
            index += 1
            if body.startswith("\\"):
                continue
            if body.startswith("-"):
                old_left -= 1
            elif body.startswith("+"):
                new_left -= 1
                if current is not None and not is_test_path(current):
                    changed.setdefault(current, []).append(new_line)
                new_line += 1
            else:
                old_left -= 1
                new_left -= 1
                new_line += 1
    return changed


def _new_path(header):
    path = header.rstrip("\t").strip()
    if path == "/dev/null":
        return None
    if len(path) >= 2 and path[0] == '"' and path[-1] == '"':
        path = path[1:-1]
    if path.startswith("b/"):
        path = path[2:]
    return path


def repo_relative(report_path, repo_root=None):
    """Map a path from a coverage report to a repo-relative POSIX path.
    Backslashes become slashes, a leading `./` is dropped and, when the path
    sits under `repo_root`, the root prefix is removed. A path outside the
    root is returned normalized but otherwise unchanged."""
    path = report_path.replace("\\", "/")
    if repo_root:
        root = repo_root.replace("\\", "/").rstrip("/")
        fold = bool(_DRIVE.match(path + "/")) or bool(_DRIVE.match(root + "/"))
        probe, base = (path.lower(), root.lower()) if fold else (path, root)
        if base and probe.startswith(base + "/"):
            path = path[len(root) + 1:]
    while path.startswith("./"):
        path = path[2:]
    return path


def _merge_file(coverage, path, lines, functions):
    entry = coverage.setdefault(path, {"lines": {}, "functions": {}})
    for number, hits in lines.items():
        entry["lines"][number] = max(hits, entry["lines"].get(number, 0))
    for key, hits in functions.items():
        entry["functions"][key] = max(hits, entry["functions"].get(key, 0))


def _finish(coverage):
    return {
        path: {
            "lines": entry["lines"],
            "functions": [(n, line, h) for (n, line), h in entry["functions"].items()],
        }
        for path, entry in coverage.items()
    }


def _hits(value):
    """Hit count as an int; a value that is not a finite number raises
    ValueError."""
    try:
        return int(float(value))
    except OverflowError as exc:
        raise ValueError(f"hit count {value!r} is not a finite number") from exc


def parse_lcov(text, repo_root=None):
    """Parse LCOV text (`SF`, `DA`, `FN`, `FNDA` records). Repeated records for
    one file keep the highest hit count per line and per function."""
    coverage = {}
    path = None
    lines, fn_lines, fn_hits = {}, {}, {}

    def flush():
        if path is None:
            return
        functions = {
            (name, line): fn_hits.get(name, 0) for name, line in fn_lines.items()
        }
        _merge_file(coverage, path, lines, functions)

    for raw in text.splitlines():
        record = raw.strip()
        if record.startswith("SF:"):
            flush()
            path = repo_relative(record[3:], repo_root)
            lines, fn_lines, fn_hits = {}, {}, {}
        elif path is None:
            continue
        elif record == "end_of_record":
            flush()
            path = None
        elif record.startswith("DA:"):
            fields = record[3:].split(",")
            if len(fields) >= 2:
                lines[int(fields[0])] = _hits(fields[1])
        elif record.startswith("FNDA:"):
            hits, _, name = record[5:].partition(",")
            fn_hits[name] = _hits(hits)
        elif record.startswith("FN:"):
            body = record[3:]
            match = _FN_RANGE.match(body) or _FN_PLAIN.match(body)
            if match:
                fn_lines[match.group(2)] = int(match.group(1))
    flush()
    return _finish(coverage)


def _cobertura_path(filename, sources, repo_root, changed):
    """Repo-relative path of a class file. A `filename` is relative to one of
    the report's `<source>` directories; when the bare path is not a changed
    path, the first source prefix that makes it one is used."""
    bare = repo_relative(filename, repo_root)
    if not changed or bare in changed:
        return bare
    for source in sources:
        joined = source.replace("\\", "/").rstrip("/") + "/" + filename.replace("\\", "/")
        candidate = repo_relative(joined, repo_root)
        if candidate in changed:
            return candidate
    return bare


def parse_cobertura(text, repo_root=None, changed=None):
    """Parse Cobertura XML. Every `<class>` contributes its `<lines>` to the
    file named by its `filename`, resolved against the `<source>` directories
    when `changed` (a collection of repo-relative paths) is given; a `<method>`
    contributes a function whose hit count is that of its first line."""
    if isinstance(text, str):
        text = _XML_DECLARATION.sub("", text, count=1)
    root = ET.fromstring(text)
    sources = [
        (node.text or "").strip() for node in root.iter("source") if (node.text or "").strip()
    ]
    coverage = {}
    for cls in root.iter("class"):
        filename = cls.get("filename")
        if not filename:
            continue
        path = _cobertura_path(filename, sources, repo_root, changed)
        lines = {}
        for line in cls.findall("lines/line"):
            lines[int(line.get("number"))] = _hits(line.get("hits", "0"))
        functions = {}
        for method in cls.iter("method"):
            numbered = [
                (int(ln.get("number")), _hits(ln.get("hits", "0")))
                for ln in method.findall("lines/line")
            ]
            if numbered:
                first, hits = min(numbered)
                functions[(method.get("name", ""), first)] = hits
        _merge_file(coverage, path, lines, functions)
    return _finish(coverage)


def parse_report(text, repo_root=None, changed=None):
    """Parse a coverage report, choosing XML or LCOV from the content."""
    stripped = text.lstrip("\ufeff \t\r\n")
    if stripped.startswith("<"):
        return parse_cobertura(stripped, repo_root, changed)
    return parse_lcov(text, repo_root)


def _is_source(path):
    name = path.rsplit("/", 1)[-1]
    return "." in name and name.rsplit(".", 1)[1].lower() in SOURCE_EXTENSIONS


def evaluate(coverage, changed):
    """Verdict for a diff against a coverage mapping.

    `coverage` is None when no report exists. A changed file counts only when
    it is a source-code file or the report names it. Returns
    {"verdict": PASS | FINDING | SKIP | N/A, "reason": str | None, "files": [...]}
    where each file entry carries path, run, total, unrun, unreached_functions
    and measured (False for a changed file the report does not name)."""
    named = coverage or {}
    changed = {
        path: sorted(set(nums))
        for path, nums in changed.items()
        if nums and (path in named or _is_source(path))
    }
    if not changed:
        return {"verdict": "N/A", "reason": None, "files": []}
    if not coverage:
        return {"verdict": "SKIP", "reason": "no measurement", "files": []}
    if not any(path in coverage for path in changed):
        return {
            "verdict": "SKIP",
            "reason": "measurement missed the changed files",
            "files": [],
        }
    files = []
    for path in sorted(changed):
        if path not in coverage:
            files.append(
                {
                    "path": path,
                    "run": 0,
                    "total": 0,
                    "unrun": [],
                    "unreached_functions": [],
                    "measured": False,
                }
            )
            continue
        measured = coverage[path]
        executable = [n for n in changed[path] if n in measured["lines"]]
        unrun = [n for n in executable if measured["lines"][n] == 0]
        spans = set(changed[path])
        unreached = sorted(
            {
                name
                for name, line, hits in measured["functions"]
                if hits == 0 and line in spans
            }
        )
        files.append(
            {
                "path": path,
                "run": len(executable) - len(unrun),
                "total": len(executable),
                "unrun": unrun,
                "unreached_functions": unreached,
                "measured": True,
            }
        )
    if any(
        not f["measured"] or f["unrun"] or f["unreached_functions"] for f in files
    ):
        verdict = "FINDING"
    elif any(f["total"] for f in files):
        verdict = "PASS"
    else:
        verdict = "N/A"
    return {"verdict": verdict, "reason": None, "files": files}


def coverage_version(text):
    """`(major, minor)` read from a coverage version string such as `7.10.2`,
    or None when the text does not start with two numbers."""
    match = re.match(r"\s*(\d+)\.(\d+)", text or "")
    return (int(match.group(1)), int(match.group(2))) if match else None


def coverage_rc(repo, data_file):
    """Text of a coverage rc file measuring the files under `repo`, omitting
    test files and installed packages beneath the repository (patterns are
    anchored at `repo`, so a repository inside a folder named `tests` or `venv`
    is still measured), writing one data file per process next to `data_file`
    and following threads and multiprocessing workers."""
    root = str(repo).replace("\\", "/").rstrip("/")
    omit = [f"{root}/**/{part}/**" for part in TEST_DIRS]
    omit += [f"{root}/**/{pat}" for pat in TEST_NAME_PATTERNS]
    omit += [f"{root}/**/{part}/**" for part in _NON_SOURCE_DIRS]
    posix = lambda path: str(path).replace("\\", "/")
    lines = [
        "[run]",
        f"include = {posix(repo)}/**",
        "parallel = true",
        "concurrency = thread, multiprocessing",
        f"data_file = {posix(data_file)}",
        "omit =",
    ]
    lines += [f"    {pattern}" for pattern in omit]
    return "\n".join(lines) + "\n"
