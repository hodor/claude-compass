"""`compass test-checkpoint record | verify | open-ids | cycle` - tamper-evident
checkpoints for pre-build failing tests, and the fix loop's cycle ledger.

A checkpoint records that a set of test files, in a specific state, existed
and failed before the implementation they test was written. `record` stores
an index at `.compass/tmp/test-checkpoints/TASK-NNN.json`, but git is the
authority: the index carries only a commit SHA, per-file SHA-256 hashes, and
the `(class, test_name)` ids extracted from the file at that commit.
`verify` never trusts the index for content - it re-reads every checkpointed
file's baseline text with `git show <sha>:<path>`, so editing the index
cannot launder a modification (SPEC-013-test-quality D-04, D-06). Membership
of `.py` files is likewise git-authoritative: every `.py` path touched by
the checkpointed commit is classified regardless of what the index's `files`
list says, so deleting an entry from the index cannot hide that file from
verification either. A commit routinely carries files with no bearing on
the checkpoint at all - a plan or spec edited in the same commit as the
tests it plans - and a non-`.py` path is classified only when it was itself
passed to `record`; otherwise it produces no finding, since AST-classifying
prose was never what the checkpoint was protecting.

Classification of a changed file is AST-based, not line-based: a
checkpointed function must still exist exactly once and be byte-identical
including its decorator list to count `unchanged`; new top-level or
class-level statements are tolerated only when every one of them is a new
`FunctionDef`/`AsyncFunctionDef`/`ClassDef` that does not rebind a name
already bound in the checkpointed content, in which case the file is
`added-only`; anything else - a changed assertion, an appended skip
decorator, a second definition shadowing a checkpointed test's name, a new
class-level assignment, a rebound module-level name - is `modified`, naming
the changed function or the rebound/shadowed symbol when the cause is one
of those. A file absent from the current tree is `missing`. `record` also
hashes the
fixtures, `__init__.py`, and other non-`test_*` modules living alongside
the checkpointed files (the "test-support surface"), since editing a
fixture is as much a change to what the tests assert as editing the test
itself; `verify` reports a hash mismatch there as `modified` too.

`verify --against-run <evidence>` additionally requires every checkpointed
test id to appear as a pass in the supplied run output - unittest `-v`
transcripts (`test_name (module.Class) ... ok`) and pytest `-v`
transcripts (`path.py::Class::test_name PASSED`, one line per
parametrized case) are both understood; anything else - skipped, failed,
errored, or simply absent - is a finding. A `verify --against-run` call that finds
nothing wrong marks the checkpoint `landed`, which is what `open-ids`
excludes: it prints the checkpointed ids of every task whose checkpoint is
recorded, not `not_required`, and not yet landed - the mechanical
definition of "no failures outside the open checkpoint set" that this
plan's suite-green rule depends on everywhere else.

A test skipped by design on the machine that produced the evidence (a
POSIX-only test run on Windows) would otherwise keep its checkpoint unlanded.
`--accept-skip Class.test_name --reason "..."` (repeatable, valid only with
`--against-run`) counts a named test as accepted when the evidence shows it
SKIPPED. A failed, errored, or absent test is never accepted, nor is a skip
that was not named, nor a name that is not a checkpointed test. When the
checkpoint lands, each acceptance (test id, reason, evidence path, UTC time)
is stored in the record's `accepted_skips`, and every later `verify` prints
it as an `accepted-skip` line.

The git repository is the one holding the checkpointed files, so a workspace
of nested repositories works: `record` asks git for the top level containing
the files (all must share one), and the index stores it as `repo`, relative
to the workspace (`.` for the workspace's own repo). Paths in the index,
`--commit`, and `verify --tree` are all relative to that repository; an
index without `repo` means the workspace's own.

`cycle TASK-NNN --evidence PATH` judges one fix-loop cycle. It parses the
run evidence, keys every test by class and name, drops the tests of open
checkpoints, and compares the remaining failing set with the previous cycle
recorded in `.compass/tmp/test-checkpoints/TASK-NNN.cycles.jsonl`. The first
call for a task is cycle 0, the state at fix-loop entry. Later cycles are
`helpful` (something fixed, nothing new, nothing gone), `harmful` (a new
failure, or a previously failing test that is no longer present and passing,
since a vanished or skipped test proves nothing fixed), or `neutral`. The
command prints the verdict line and `escalate: yes|no`, yes at cycle 3 or on
a harmful cycle. An unreadable or testless evidence file exits 1 and appends
nothing.

`record --commit` is resolved to a full SHA, so a symbolic name such as
`HEAD` never drifts. A first record names only files the commit touched; a
`--supersede` record may also name a file tracked in that commit's tree that
the commit left unchanged, and `verify` classifies every recorded file.

Vault root resolution goes through `vaultlib.find_vault_root`
(LESSON-scratch-vaults-need-compass-dir). Never exits 2; a missing git
binary, a detached or non-repository working tree, and a corrupt index all
report a message on stderr and exit 1 rather than raising.
"""

import ast
import codecs
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

import vaultlib

try:
    import msvcrt
except ImportError:
    msvcrt = None
    import fcntl

CHECKPOINTS_DIR = ("tmp", "test-checkpoints")

USAGE = (
    "usage: compass test-checkpoint record TASK-NNN <file>... --commit SHA "
    "[--red-evidence PATH] [--supersede TASK-NNN --reason \"...\"] [--not-required]\n"
    "       compass test-checkpoint verify TASK-NNN [--tree PATH] "
    "[--against-run EVIDENCE [--accept-skip Class.test_name --reason \"...\"]...] "
    "[--expect-checkpoint]\n"
    "       compass test-checkpoint open-ids\n"
    "       compass test-checkpoint cycle TASK-NNN --evidence PATH"
)

# unittest -v line: "test_name (module.path.ClassName) ... ok" (also FAIL,
# ERROR, or "skipped '<reason>'").
_RUN_LINE_RE = re.compile(
    r"^(?P<name>\w+)\s+\((?P<path>[\w.]+)\)\s+\.\.\.\s+(?P<status>ok|FAIL|ERROR|skipped.*)\s*$"
)

# pytest -v line: "path/to/test_file.py::Class::test_name PASSED [ 10%]" -
# class segments optional and nestable, an optional [param] suffix on the
# name. Short-summary lines (-rA) put the status first instead. A param id
# may hold spaces, `]` and `::`: in a `-v` line it runs to the last `]`
# that precedes the status; in a summary line, to the first `]` followed by
# whitespace or the end, since a failure message trails it.
_PYTEST_NODE_BASE = r"\S+?\.py(?:::\w+)*::\w+"
_PYTEST_STATUS = r"PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS"
_PYTEST_LINE_RE = re.compile(
    rf"^(?P<nodeid>{_PYTEST_NODE_BASE}(?:\[.*\])?)\s+(?P<status>{_PYTEST_STATUS})\b"
)
_PYTEST_SUMMARY_RE = re.compile(
    rf"^(?P<status>{_PYTEST_STATUS})\s+(?P<nodeid>{_PYTEST_NODE_BASE}(?:\[.*?\](?=\s|$))?)(?=\s|$)"
)

# A test's status is not always on its own line. A docstring prints the
# header `name (path)` alone with the status trailing the docstring's first
# line; a test that writes to stderr interleaves that output after `... `
# and the bare status token lands alone on a later line. Headers, trailers,
# and bare status lines are matched separately and joined by the parser.
_RUN_HEADER_RE = re.compile(
    r"^(?P<name>\w+)\s+\((?P<path>[\w.]+)\)(?:\s+\.\.\..*)?$"
)
_RUN_TRAILER_RE = re.compile(r"\.\.\.\s+(?P<status>ok|FAIL|ERROR|skipped.*)\s*$")
_RUN_BARE_STATUS_RE = re.compile(r"^(?P<status>ok|FAIL|ERROR|skipped.*)\s*$")


# --------------------------------------------------------------------------
# git access - the sole source of truth for checkpointed content and
# membership.
# --------------------------------------------------------------------------

def _run_git(repo_root, args):
    """Run `git <args>` in `repo_root`. Returns `(returncode, stdout, stderr)`
    decoded as UTF-8 with replacement, never raising: a missing `git` binary
    reports as return code 127 rather than propagating `FileNotFoundError`."""
    try:
        result = subprocess.run(["git", *args], cwd=str(repo_root), capture_output=True)
    except FileNotFoundError:
        return 127, "", "git not found on PATH"
    return (
        result.returncode,
        result.stdout.decode("utf-8", errors="replace"),
        result.stderr.decode("utf-8", errors="replace"),
    )


def _require_git_repo(repo_root):
    code, out, _ = _run_git(repo_root, ["rev-parse", "--is-inside-work-tree"])
    return code == 0 and out.strip() == "true"


def _git_commit_exists(repo_root, sha):
    if not sha:
        return False
    code, _, _ = _run_git(repo_root, ["cat-file", "-e", f"{sha}^{{commit}}"])
    return code == 0


def _git_resolve_commit(repo_root, name):
    """The full SHA that `name` (a SHA, a branch, `HEAD`) names, or None."""
    if not name or name.startswith("-"):
        return None
    code, out, _ = _run_git(repo_root, ["rev-parse", "--verify", f"{name}^{{commit}}"])
    sha = out.strip()
    return sha if code == 0 and sha else None


def _git_commit_files(repo_root, sha):
    """Every file path touched by `sha`, git-authoritative and independent
    of anything recorded in the checkpoint index. `--root` makes this work
    identically for a commit with no parent."""
    code, out, _ = _run_git(
        repo_root, ["diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha]
    )
    if code != 0:
        return []
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def _git_show(repo_root, sha, path):
    code, out, _ = _run_git(repo_root, ["show", f"{sha}:{path}"])
    return out if code == 0 else None


def _git_ls_dir(repo_root, sha, dirpath):
    """Direct file entries of `dirpath` as it existed at `sha`, full paths
    relative to the repo root."""
    if dirpath in ("", "."):
        code, out, _ = _run_git(repo_root, ["ls-tree", "--name-only", sha])
    else:
        code, out, _ = _run_git(repo_root, ["ls-tree", "--name-only", sha, "--", dirpath + "/"])
    if code != 0:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _resolve_arg(workspace, given):
    """A file argument as an absolute path: absolute as given, else under
    the workspace when it exists there, else under the cwd, else under the
    workspace."""
    path = Path(given)
    if path.is_absolute():
        return path
    for base in (workspace, Path.cwd()):
        if (base / path).exists():
            return base / path
    return workspace / path


def _repo_containing(path):
    """The top level of the git repository holding `path` (the nearest
    existing directory at or above it), or None outside any repository.
    A nested repository - one the workspace's own repo ignores - wins over
    the workspace repo, as git itself resolves it."""
    directory = path if path.is_dir() else path.parent
    while not directory.exists() and directory != directory.parent:
        directory = directory.parent
    code, out, _ = _run_git(directory, ["rev-parse", "--show-toplevel"])
    top = out.strip()
    return Path(top).resolve() if code == 0 and top else None


def _repo_label(workspace, repo_root):
    """How a checkpoint names its repository: POSIX path relative to the
    workspace (`.` for the workspace's own repo), absolute when outside it."""
    try:
        rel = repo_root.resolve().relative_to(workspace.resolve())
    except ValueError:
        return repo_root.resolve().as_posix()
    return rel.as_posix() or "."


def _to_posix_rel(repo_root, given):
    """Resolve a file argument (relative to cwd, or already relative to
    `repo_root`) to a repo-root-relative POSIX path, matching the form git
    reports paths in."""
    path = Path(given)
    candidate = path if path.is_absolute() else (repo_root / path)
    try:
        rel = candidate.resolve().relative_to(repo_root.resolve())
    except ValueError:
        rel = path
    return str(rel).replace("\\", "/")


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iso_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------
# AST classification
# --------------------------------------------------------------------------

def _parse_source(text):
    """Returns `(tree, error)`, `error` a short string on a `SyntaxError`
    rather than a raised exception."""
    try:
        return ast.parse(text), None
    except SyntaxError as exc:
        return None, str(exc)


def _function_occurrences(tree):
    """`{(class_name_or_None, func_name): [unparsed segment, ...]}` for every
    module-level function and every method of a module-level class. Segment
    text comes from `ast.unparse` on the def node itself, which renders its
    decorator list, so a decorator-only edit (e.g. an appended
    `@unittest.skip`) changes the segment. Multiple entries for one key mean
    the name is defined more than once - a later definition shadows an
    earlier one at runtime."""
    occurrences = {}

    def add(key, node):
        occurrences.setdefault(key, []).append(ast.unparse(node))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add((None, node.name), node)
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add((node.name, sub.name), sub)
    return occurrences


def _bound_names(body):
    """Names bound directly by a sequence of statements (a module or class
    body): function/class definitions, and `Assign`/`AnnAssign`/`AugAssign`
    targets that are plain names."""
    names = set()
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names |= _assign_target_names(node)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            names |= _assign_target_names(node)
    return names


def _assign_target_names(node):
    """Plain `Name` targets of an `Assign`/`AnnAssign`/`AugAssign` node, or
    an empty set for any other statement kind."""
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        targets = [node.target]
    else:
        return set()
    return {t.id for t in targets if isinstance(t, ast.Name)}


def _statement_segments(body):
    return Counter(ast.unparse(node) for node in body)


def _added_statement_violation(baseline_body, current_body, baseline_bound, label_prefix):
    """Statements present in `current_body` that were not in `baseline_body`
    (by unparsed text, so a reordering is not itself an addition). Every
    addition must be a new `FunctionDef`/`AsyncFunctionDef`/`ClassDef` that
    does not rebind a name already bound in `baseline_bound`. Returns a
    detail string naming the offending symbol or statement on the first
    violation found, or None when every addition is legitimate."""
    added = _statement_segments(current_body) - _statement_segments(baseline_body)
    for segment in added:
        node = ast.parse(segment).body[0]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in baseline_bound:
                where = f"{label_prefix}{node.name}" if label_prefix else node.name
                return f"{where}: rebound by an added definition"
            continue
        rebinds = _assign_target_names(node) & baseline_bound
        if rebinds:
            name = sorted(rebinds)[0]
            where = f"{label_prefix}{name}" if label_prefix else name
            return f"{where}: rebound by an added statement"
        scope = "module level" if not label_prefix else f"{label_prefix.rstrip('.')} body"
        return f"a non-definition statement was added at {scope}"
    return None


def _classify_file(baseline_src, current_src):
    """Classify one checkpointed file's current content against its
    baseline. Returns `{"status": ..., "detail": ...}` with status one of
    `unchanged`, `added-only`, `modified`."""
    baseline_tree, base_err = _parse_source(baseline_src)
    if base_err:
        return {"status": "modified", "detail": f"checkpointed baseline fails to parse: {base_err}"}
    current_tree, cur_err = _parse_source(current_src)
    if cur_err:
        return {"status": "modified", "detail": f"current file fails to parse: {cur_err}"}

    if ast.unparse(current_tree) == ast.unparse(baseline_tree):
        return {"status": "unchanged", "detail": None}

    baseline_funcs = _function_occurrences(baseline_tree)
    current_funcs = _function_occurrences(current_tree)

    for (class_name, func_name), segments in baseline_funcs.items():
        label = f"{class_name}.{func_name}" if class_name else func_name
        current_segments = current_funcs.get((class_name, func_name), [])
        if not current_segments:
            return {"status": "modified", "detail": f"{label}: removed or renamed"}
        if len(current_segments) > 1:
            return {
                "status": "modified",
                "detail": f"{label}: shadowed by a later definition of the same name",
            }
        if current_segments[0] != segments[0]:
            return {"status": "modified", "detail": f"{label}: body or decorators changed"}

    baseline_module_bound = _bound_names(baseline_tree.body)
    baseline_classes = {n.name: n for n in baseline_tree.body if isinstance(n, ast.ClassDef)}
    current_classes = {n.name: n for n in current_tree.body if isinstance(n, ast.ClassDef)}

    # Class bodies are compared separately below, statement by statement, so
    # a class present in both trees is excluded here even when its body
    # changed - otherwise its whole (now-different) unparsed text would look
    # like a brand-new top-level statement that "rebinds" its own name on
    # every legitimate addition inside it (e.g. a new test method).
    baseline_non_class = [n for n in baseline_tree.body if not isinstance(n, ast.ClassDef)]
    current_non_class = [n for n in current_tree.body if not isinstance(n, ast.ClassDef)]
    detail = _added_statement_violation(
        baseline_non_class, current_non_class, baseline_module_bound, ""
    )
    if detail:
        return {"status": "modified", "detail": detail}

    for name in current_classes:
        if name not in baseline_classes and name in baseline_module_bound:
            return {"status": "modified", "detail": f"{name}: rebound by an added definition"}

    for class_name, base_class_node in baseline_classes.items():
        current_class_node = current_classes.get(class_name)
        if current_class_node is None:
            continue  # a removed class with checkpointed methods was already caught above
        class_bound = _bound_names(base_class_node.body)
        detail = _added_statement_violation(
            base_class_node.body, current_class_node.body, class_bound, f"{class_name}."
        )
        if detail:
            return {"status": "modified", "detail": detail}

    return {"status": "added-only", "detail": None}


# --------------------------------------------------------------------------
# checkpoint index
# --------------------------------------------------------------------------

def _checkpoint_path(vault_root, task):
    return Path(vault_root).joinpath(*CHECKPOINTS_DIR) / f"{task}.json"


def _write_record(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    vaultlib.write_text_lf(path, json.dumps(record, indent=2) + "\n")


def _load_record(path):
    """Returns `(record, error)`. `error` is a short message on missing or
    unparseable JSON, never a raised exception."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, str(exc)
    try:
        record = json.loads(raw)
    except ValueError as exc:
        return None, f"corrupt checkpoint JSON: {exc}"
    if not isinstance(record, dict):
        return None, "corrupt checkpoint JSON: not an object"
    return record, None


def _supersede_entry(prior, reason):
    return {
        "prior_version": prior.get("version", 1),
        "reason": reason,
        "prior_recorded_at": prior.get("recorded_at"),
        "prior_commit": prior.get("commit"),
        "prior": prior,
    }


def _collect_support_surface(repo_root, commit, dirs, exclude_paths):
    """Fixtures, `__init__.py`, and other non-`test_*` `.py` modules living
    in the same directories as the checkpointed files, at `commit`. A change
    to one of these later is a change to what the checkpointed tests assert,
    even though the file itself was never named in `record`."""
    surface = []
    seen = set()
    for directory in sorted(dirs):
        for rel in _git_ls_dir(repo_root, commit, directory):
            if rel in exclude_paths or rel in seen:
                continue
            name = PurePosixPath(rel).name
            if not name.endswith(".py") or name.startswith("test_"):
                continue
            content = _git_show(repo_root, commit, rel)
            if content is None:
                continue
            surface.append({"path": rel, "sha256": _sha256_text(content)})
            seen.add(rel)
    return surface


# --------------------------------------------------------------------------
# record
# --------------------------------------------------------------------------

def _parse_record(args):
    """Returns `(options, error)`."""
    if not args:
        return None, "a task id is required"
    task = args[0]
    rest = args[1:]
    files, commit, red_evidence, supersede, reason, not_required = [], None, None, None, None, False
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg in ("--commit", "--red-evidence", "--supersede", "--reason"):
            if i + 1 >= len(rest):
                return None, f"{arg} expects a value"
            value = rest[i + 1]
            if arg == "--commit":
                commit = value
            elif arg == "--red-evidence":
                red_evidence = value
            elif arg == "--supersede":
                supersede = value
            else:
                reason = value
            i += 2
            continue
        if arg == "--not-required":
            not_required = True
            i += 1
            continue
        if arg.startswith("--"):
            return None, f"unknown flag {arg}"
        files.append(arg)
        i += 1

    if not_required and (files or commit):
        return None, "--not-required takes no files and no --commit"
    if not not_required and not files:
        return None, "at least one test file is required (or pass --not-required)"
    if not not_required and not commit:
        return None, "--commit is required for a code task"
    if supersede is not None and reason is None:
        return None, "--supersede requires --reason"
    if reason is not None and supersede is None:
        return None, "--reason requires --supersede"
    if supersede is not None and supersede != task:
        return None, f"--supersede {supersede} does not match task id {task}"

    return {
        "task": task, "files": files, "commit": commit, "red_evidence": red_evidence,
        "supersede": supersede, "reason": reason, "not_required": not_required,
    }, None


def _run_record(args):
    options, error = _parse_record(args)
    if error:
        sys.stderr.write(f"compass test-checkpoint record: {error}\n{USAGE}\n")
        return 1

    task = options["task"]
    vault_root = vaultlib.find_vault_root()
    workspace = Path(vault_root).parent
    repo_root = workspace
    path = _checkpoint_path(vault_root, task)

    prior = None
    if path.is_file():
        if not options["supersede"]:
            sys.stderr.write(
                f"compass test-checkpoint record: a checkpoint already exists for {task}; "
                "use --supersede TASK-NNN --reason \"...\" to version it\n"
            )
            return 1
        prior, load_error = _load_record(path)
        if load_error:
            sys.stderr.write(f"compass test-checkpoint record: existing checkpoint for {task}: {load_error}\n")
            return 1
    elif options["supersede"]:
        sys.stderr.write(f"compass test-checkpoint record: nothing to supersede for {task}\n")
        return 1

    version = (prior.get("version", 1) + 1) if prior else 1
    supersedes = _supersede_entry(prior, options["reason"]) if prior else None

    if options["not_required"]:
        record = {
            "task": task, "version": version, "recorded_at": _iso_now(),
            "commit": None, "red_evidence": None, "not_required": True,
            "landed": False, "landed_at": None,
            "files": [], "support_surface": [], "supersedes": supersedes,
        }
        _write_record(path, record)
        sys.stdout.write(f"compass test-checkpoint record: {task} not-required\n")
        return 0

    resolved = [_resolve_arg(workspace, given) for given in options["files"]]
    repos = {_repo_containing(p) for p in resolved}
    if len(repos) > 1:
        names = ", ".join(sorted(_repo_label(workspace, r) if r else "(none)" for r in repos))
        sys.stderr.write(
            f"compass test-checkpoint record: the files span more than one git repository ({names}); "
            "record each repository's files as its own checkpoint\n"
        )
        return 1
    repo_root = repos.pop() or workspace

    if not _require_git_repo(repo_root):
        sys.stderr.write("compass test-checkpoint record: not a git repository (or git is unavailable)\n")
        return 1

    commit = _git_resolve_commit(repo_root, options["commit"])
    if commit is None:
        sys.stderr.write(f"compass test-checkpoint record: commit {options['commit']} not found in git log\n")
        return 1

    commit_files = set(_git_commit_files(repo_root, commit))
    file_records = []
    dirs = set()
    for given in resolved:
        rel = _to_posix_rel(repo_root, given)
        in_commit = rel in commit_files
        if not in_commit and options["supersede"] and _git_show(repo_root, commit, rel) is not None:
            in_commit = True  # a superseding record may carry a file tracked in the commit's tree
        if not in_commit:
            sys.stderr.write(f"compass test-checkpoint record: {rel} is not part of commit {commit}\n")
            return 1
        content = _git_show(repo_root, commit, rel)
        if content is None:
            sys.stderr.write(f"compass test-checkpoint record: could not read {rel} at {commit}\n")
            return 1
        if rel.endswith(".py"):
            tree, parse_error = _parse_source(content)
            if parse_error:
                sys.stderr.write(f"compass test-checkpoint record: {rel} does not parse: {parse_error}\n")
                return 1
            ids = sorted(
                [class_name, func_name]
                for (class_name, func_name) in _function_occurrences(tree)
                if func_name.startswith("test")
            )
        else:
            # A recorded non-Python file (a JS harness, a data fixture)
            # carries no test ids; its hash is its whole identity and
            # verify compares it byte-wise.
            ids = []
        file_records.append({"path": rel, "sha256": _sha256_text(content), "ids": ids})
        dirs.add(str(PurePosixPath(rel).parent))

    exclude = {fr["path"] for fr in file_records}
    support_surface = _collect_support_surface(repo_root, commit, dirs, exclude)

    record = {
        "task": task, "version": version, "recorded_at": _iso_now(),
        "commit": commit, "repo": _repo_label(workspace, repo_root),
        "red_evidence": options["red_evidence"], "not_required": False,
        "landed": False, "landed_at": None,
        "files": file_records, "support_surface": support_surface, "supersedes": supersedes,
    }
    _write_record(path, record)
    sys.stdout.write(
        f"compass test-checkpoint record: {task} checkpointed {len(file_records)} file(s) at {commit[:12]}\n"
    )
    return 0


# --------------------------------------------------------------------------
# verify
# --------------------------------------------------------------------------

def _parse_verify(args):
    """Returns `(options, error)`."""
    if not args:
        return None, "a task id is required"
    task = args[0]
    rest = args[1:]
    tree_opt = against_run = None
    expect_checkpoint = False
    accept_skips = []  # [{"id": ..., "reason": ... or None}]
    leading_reason = None  # a --reason given before its --accept-skip
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg in ("--accept-skip", "--reason"):
            if i + 1 >= len(rest):
                return None, f"{arg} expects a value"
            value = rest[i + 1]
            if not value.strip():
                return None, f"{arg} expects a non-empty value"
            if arg == "--accept-skip":
                accept_skips.append({"id": value.strip(), "reason": leading_reason})
                leading_reason = None
            elif accept_skips and accept_skips[-1]["reason"] is None:
                accept_skips[-1]["reason"] = value
            elif leading_reason is None:
                leading_reason = value
            else:
                return None, "--reason given twice without an --accept-skip"
            i += 2
            continue
        if arg in ("--tree", "--against-run"):
            if i + 1 >= len(rest):
                return None, f"{arg} expects a value"
            if arg == "--tree":
                tree_opt = rest[i + 1]
            else:
                against_run = rest[i + 1]
            i += 2
            continue
        if arg == "--expect-checkpoint":
            expect_checkpoint = True
            i += 1
            continue
        return None, f"unknown flag {arg}"
    if (accept_skips or leading_reason is not None) and against_run is None:
        return None, "--accept-skip requires --against-run"
    if leading_reason is not None:
        return None, "--reason has no --accept-skip to attach to"
    for entry in accept_skips:
        if entry["reason"] is None:
            return None, f"--accept-skip {entry['id']} needs a --reason"
    return {
        "task": task, "tree": tree_opt, "against_run": against_run,
        "expect_checkpoint": expect_checkpoint, "accept_skips": accept_skips,
    }, None


def _read_evidence(path):
    """The text of a saved test run. A PowerShell `>` redirect writes UTF-16
    with a byte-order mark, and a Windows console saves its own code page,
    so bytes outside UTF-8 decode as cp1252; test ids are ASCII either way."""
    data = path.read_bytes()
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _parse_run_evidence(text):
    """`{(class_name, test_name): status}` from unittest `-v` or pytest
    `-v` output, status one of `ok`, `fail`, `error`, `skipped` (plus
    pytest's `xfail`/`xpass`). A test id absent from the evidence is simply
    absent from this map - callers treat that as "not proven passed", the
    same as any status other than `ok`. An id that appears more than once
    (a parametrized pytest test, one line per case) counts `ok` only when
    every occurrence passed."""
    statuses = {}
    pending = None  # (name, path) header awaiting its docstring-line trailer
    for line in text.splitlines():
        stripped = line.strip()
        pytest_match = (_PYTEST_LINE_RE.match(stripped)
                        or _PYTEST_SUMMARY_RE.match(stripped))
        if pytest_match:
            pending = None
            _record_pytest_status(
                statuses, pytest_match.group("nodeid"), pytest_match.group("status")
            )
            continue
        match = _RUN_LINE_RE.match(stripped)
        if not match:
            header = _RUN_HEADER_RE.match(stripped)
            if header:
                pending = (header.group("name"), header.group("path"))
                continue
            if pending is not None:
                trailer = _RUN_TRAILER_RE.search(stripped) or _RUN_BARE_STATUS_RE.match(stripped)
                if trailer:
                    name, path = pending
                    pending = None
                    _record_run_status(statuses, name, path, trailer.group("status"))
            continue
        pending = None
        _record_run_status(
            statuses, match.group("name"), match.group("path"), match.group("status")
        )
    return statuses


def _record_pytest_status(statuses, nodeid, raw_status):
    """Fold one pytest node id into the status map. A `[param]` suffix
    identifies one case of a parametrized test and is stripped first, since
    checkpoint ids carry the bare name and a param id may itself hold `::`.
    The remaining id's last `::` segment is the test name; the segment
    before it, when it is not the file path, is the class."""
    segments = nodeid.split("[", 1)[0].split("::")
    name = segments[-1]
    class_name = segments[-2] if len(segments) >= 3 else None
    status = {"PASSED": "ok", "FAILED": "fail", "ERROR": "error",
              "SKIPPED": "skipped"}.get(raw_status, raw_status.lower())
    _fold_status(statuses, class_name, name, status)


def _record_run_status(statuses, name, path, raw_status):
    # unittest -v prints the parenthesized path as `pkg.Class` on older
    # Pythons and `pkg.Class.test_name` on newer ones; when the last
    # segment repeats the test name, the class is the segment before it.
    parts = path.split(".")
    if parts[-1] == name and len(parts) >= 2:
        class_name = parts[-2]
    else:
        class_name = parts[-1] if "." in path else None
    status = "ok" if raw_status == "ok" else ("skipped" if raw_status.startswith("skipped") else raw_status.lower())
    _fold_status(statuses, class_name, name, status)


def _fold_status(statuses, class_name, name, status):
    """Record `status` under both the class-qualified and bare keys. A key
    already holding a non-`ok` status keeps it: a test id proven failed
    once is not laundered by a later passing occurrence of the same id."""
    for key in ((class_name, name), (None, name)):
        if statuses.get(key, "ok") == "ok":
            statuses[key] = status


def _print_report(task, record, findings, accepted_skips=()):
    lines = [f"compass test-checkpoint verify: {task}"]
    supersedes = record.get("supersedes")
    if supersedes:
        prior_commit = (supersedes.get("prior_commit") or "")[:12]
        lines.append(
            f"  supersedes v{supersedes['prior_version']} ({prior_commit}): {supersedes['reason']}"
        )
    if not findings:
        lines.append("  (no checkpointed files)")
    for finding in findings:
        detail = f" - {finding['detail']}" if finding.get("detail") else ""
        lines.append(f"  {finding['status']:<12} {finding['file']}{detail}")
    for skip in accepted_skips:
        lines.append(
            f"  {'accepted-skip':<12} {skip['id']} - {skip['reason']} "
            f"(evidence {skip['evidence']}, {skip['accepted_at']})"
        )
    sys.stdout.write("\n".join(lines) + "\n")


def _recorded_paths_across_versions(record):
    """Every file path named by `record` or by any prior version in its
    `supersedes` chain. A superseding record can carry a file its commit left
    unchanged, which no commit diff names; the union with the earlier versions
    keeps that file under verification when its entry is dropped from the
    current index."""
    paths = set()
    seen = 0
    while isinstance(record, dict) and seen < 1000:
        files = record.get("files")
        if isinstance(files, list):
            paths |= {
                entry["path"] for entry in files
                if isinstance(entry, dict) and isinstance(entry.get("path"), str)
            }
        supersedes = record.get("supersedes")
        record = supersedes.get("prior") if isinstance(supersedes, dict) else None
        seen += 1
    return paths


def _run_verify(args):
    options, error = _parse_verify(args)
    if error:
        sys.stderr.write(f"compass test-checkpoint verify: {error}\n{USAGE}\n")
        return 1

    task = options["task"]
    vault_root = vaultlib.find_vault_root()
    workspace = Path(vault_root).parent
    path = _checkpoint_path(vault_root, task)

    if not path.is_file():
        suffix = " (expected one per --expect-checkpoint)" if options["expect_checkpoint"] else ""
        sys.stderr.write(f"compass test-checkpoint verify: no checkpoint recorded for {task}{suffix}\n")
        return 1

    record, load_error = _load_record(path)
    if load_error:
        sys.stderr.write(f"compass test-checkpoint verify: {task}: {load_error}\n")
        return 1

    if record.get("not_required"):
        sys.stdout.write(f"compass test-checkpoint verify: {task} not-required\n")
        return 0

    repo_label = record.get("repo") if isinstance(record.get("repo"), str) else "."
    repo_root = workspace / repo_label
    if not _require_git_repo(repo_root):
        sys.stderr.write("compass test-checkpoint verify: not a git repository (or git is unavailable)\n")
        return 1

    sha = record.get("commit")
    if not _git_commit_exists(repo_root, sha):
        sys.stderr.write(f"compass test-checkpoint verify: commit {sha} for {task} not found in git log\n")
        return 1

    tree_root = Path(options["tree"]) if options["tree"] else repo_root
    commit_files = _git_commit_files(repo_root, sha)
    recorded_paths = _recorded_paths_across_versions(record)

    findings = []
    accepted_now = []
    ok = True
    for rel in commit_files + sorted(recorded_paths - set(commit_files)):
        if not rel.endswith(".py") and rel not in recorded_paths:
            continue
        baseline = _git_show(repo_root, sha, rel)
        if baseline is None:
            continue
        current_path = tree_root / rel
        if not current_path.is_file():
            findings.append({"file": rel, "status": "missing", "detail": None})
            ok = False
            continue
        current_src = current_path.read_text(encoding="utf-8")
        if rel.endswith(".py"):
            result = _classify_file(baseline, current_src)
        elif current_src == baseline:
            # A recorded non-Python file (a JS harness, a data fixture) is
            # not AST material; byte equality is its whole verdict.
            result = {"status": "unchanged", "detail": None}
        else:
            result = {"status": "modified", "detail": "recorded non-Python file changed"}
        findings.append({"file": rel, **result})
        if result["status"] not in ("unchanged", "added-only"):
            ok = False

    for surface in record.get("support_surface", []):
        surface_path = tree_root / surface["path"]
        if not surface_path.is_file():
            findings.append({"file": surface["path"], "status": "missing", "detail": "support surface file removed"})
            ok = False
            continue
        current_hash = _sha256_text(surface_path.read_text(encoding="utf-8"))
        if current_hash != surface["sha256"]:
            findings.append({"file": surface["path"], "status": "modified", "detail": "support surface changed"})
            ok = False

    if options["against_run"]:
        evidence_path = Path(options["against_run"])
        if not evidence_path.is_file():
            sys.stderr.write(
                f"compass test-checkpoint verify: --against-run evidence not found: {options['against_run']}\n"
            )
            return 1
        statuses = _parse_run_evidence(_read_evidence(evidence_path))
        requested = {entry["id"]: entry["reason"] for entry in options["accept_skips"]}
        checkpointed = {
            f"{class_name}.{test_name}" if class_name else test_name
            for file_record in record.get("files", [])
            for class_name, test_name in file_record.get("ids", [])
        }
        for skip_id in requested:
            if skip_id not in checkpointed:
                findings.append({
                    "file": skip_id, "status": "bad-accept-skip",
                    "detail": "not a checkpointed test",
                })
                ok = False
        for file_record in record.get("files", []):
            for class_name, test_name in file_record.get("ids", []):
                status = statuses.get((class_name, test_name))
                label = f"{class_name}.{test_name}" if class_name else test_name
                if status == "skipped" and label in requested:
                    accepted_now.append({
                        "id": label, "reason": requested[label],
                        "evidence": str(evidence_path), "accepted_at": _iso_now(),
                    })
                    continue
                if status != "ok":
                    findings.append({
                        "file": label, "status": "not-passed",
                        "detail": status or "not present in run evidence",
                    })
                    ok = False

    accepted = {
        skip["id"]: skip for skip in record.get("accepted_skips", [])
        if isinstance(skip, dict) and isinstance(skip.get("id"), str)
    }
    accepted.update({skip["id"]: skip for skip in accepted_now})
    _print_report(task, record, findings, list(accepted.values()))

    if ok and options["against_run"]:
        if accepted:
            record["accepted_skips"] = list(accepted.values())
        record["landed"] = True
        record["landed_at"] = _iso_now()
        _write_record(path, record)

    return 0 if ok else 1


# --------------------------------------------------------------------------
# open-ids
# --------------------------------------------------------------------------

def _dotted_module(path):
    return str(PurePosixPath(path).with_suffix("")).replace("/", ".")


def _open_test_ids(vault_root, label="open-ids", exclude_task=None):
    """`[(module, class_name_or_None, test_name)]` for every checkpointed test
    of a task whose checkpoint is recorded, not `not_required`, and not yet
    landed, leaving out the checkpoint of `exclude_task`. An unreadable index
    is reported on stderr and skipped."""
    checkpoints_dir = Path(vault_root).joinpath(*CHECKPOINTS_DIR)
    found = []
    if not checkpoints_dir.is_dir():
        return found
    for entry in sorted(checkpoints_dir.glob("TASK-*.json")):
        if entry.stem == exclude_task:
            continue
        record, load_error = _load_record(entry)
        if load_error:
            sys.stderr.write(f"compass test-checkpoint {label}: skipping {entry.name}: {load_error}\n")
            continue
        if record.get("landed") or record.get("not_required"):
            continue
        for file_record in record.get("files", []):
            module = _dotted_module(file_record["path"])
            for class_name, test_name in file_record.get("ids", []):
                found.append((module, class_name, test_name))
    return found


def _run_open_ids(args):
    if args:
        sys.stderr.write(f"compass test-checkpoint open-ids: unexpected argument(s): {' '.join(args)}\n")
        return 1

    ids = [
        f"{module}.{class_name}.{test_name}" if class_name else f"{module}.{test_name}"
        for module, class_name, test_name in _open_test_ids(vaultlib.find_vault_root())
    ]
    if ids:
        sys.stdout.write("\n".join(ids) + "\n")
    return 0


# --------------------------------------------------------------------------
# cycle
# --------------------------------------------------------------------------

CYCLE_ESCALATION = 3
_FAILING_STATUSES = ("fail", "error")


def _parse_cycle(args):
    """Returns `(task, evidence_path, error)`."""
    if not args or args[0].startswith("--"):
        return None, None, "a task id is required"
    task, rest = args[0], args[1:]
    if not re.fullmatch(r"TASK-[0-9]+", task):
        return None, None, f"{task!r} is not a task id (TASK-NNN)"
    evidence = None
    i = 0
    while i < len(rest):
        if rest[i] != "--evidence":
            return None, None, f"unknown argument {rest[i]}"
        if i + 1 >= len(rest) or rest[i + 1].startswith("--"):
            return None, None, "--evidence expects a value"
        evidence = rest[i + 1]
        i += 2
    if evidence is None:
        return None, None, "--evidence is required"
    return task, evidence, None


def _tests_by_class_and_name(statuses):
    """`{(class_name, test_name): status}` with one entry per test.
    `_parse_run_evidence` also files every test under a bare-name key; that
    alias is dropped whenever a class-qualified test of the same name exists,
    so a name shared by two classes counts as two tests."""
    qualified_names = {name for (class_name, name) in statuses if class_name is not None}
    return {
        key: status for key, status in statuses.items()
        if key[0] is not None or key[1] not in qualified_names
    }


def _load_cycle_log(path):
    """Returns `(rows, error)`: every logged cycle in order."""
    if not path.is_file():
        return [], None
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except (OSError, ValueError) as exc:
        return None, f"unreadable cycle log {path.name}: {exc}"
    if not all(isinstance(row, dict) and _is_test_pair_list(row.get("failing")) for row in rows):
        return None, f"unreadable cycle log {path.name}: a row is not a cycle record"
    return rows, None


def _is_test_pair_list(value):
    """A cycle row's `failing` entry: a list of `[class_or_null, name]` pairs."""
    return isinstance(value, list) and all(
        isinstance(item, list) and len(item) == 2
        and (item[0] is None or isinstance(item[0], str)) and isinstance(item[1], str)
        for item in value
    )


CYCLE_LOCK_ATTEMPTS = 2000
CYCLE_LOCK_RETRY_SECONDS = 0.005


@contextmanager
def _cycle_log_lock(log_path):
    """Hold an exclusive OS lock on a sidecar file of `log_path`, retrying
    briefly while another process holds it. The OS drops the lock when the
    holder dies. TimeoutError when it stays held."""
    lock_path = log_path.with_suffix(".lock")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o666)
    try:
        for attempt in range(CYCLE_LOCK_ATTEMPTS):
            try:
                if msvcrt:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if attempt == CYCLE_LOCK_ATTEMPTS - 1:
                    raise TimeoutError(f"cycle log lock {lock_path.name} stayed held") from None
                time.sleep(CYCLE_LOCK_RETRY_SECONDS)
        try:
            yield
        finally:
            if msvcrt:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _format_tests(tests):
    ordered = sorted(tests, key=lambda test: (test[0] or "", test[1]))
    return ", ".join(f"{class_name}.{name}" if class_name else name for class_name, name in ordered)


def _run_cycle(args):
    task, evidence, error = _parse_cycle(args)
    if error:
        sys.stderr.write(f"compass test-checkpoint cycle: {error}\n{USAGE}\n")
        return 1

    evidence_path = Path(evidence)
    if not evidence_path.is_file():
        sys.stderr.write(f"compass test-checkpoint cycle: evidence not found: {evidence}\n")
        return 1
    try:
        statuses = _tests_by_class_and_name(_parse_run_evidence(_read_evidence(evidence_path)))
    except OSError as exc:
        sys.stderr.write(f"compass test-checkpoint cycle: cannot read evidence {evidence}: {exc}\n")
        return 1
    if not statuses:
        sys.stderr.write(f"compass test-checkpoint cycle: no test results found in {evidence}\n")
        return 1

    vault_root = vaultlib.find_vault_root()
    log_path = Path(vault_root).joinpath(*CHECKPOINTS_DIR) / f"{task}.cycles.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _cycle_log_lock(log_path):
            result = _append_cycle(task, statuses, vault_root, log_path)
    except TimeoutError as exc:
        sys.stderr.write(f"compass test-checkpoint cycle: {exc}\n")
        return 1
    report, problem = result
    if problem:
        sys.stderr.write(f"compass test-checkpoint cycle: {problem}\n")
        return 1
    sys.stdout.write(report)
    return 0


def _append_cycle(task, statuses, vault_root, log_path):
    """Judge `statuses` against the task's last logged cycle and append the
    new cycle. Returns `(report, None)`, or `(None, error)` with the log left
    untouched. Runs under the log's lock, so reading the count and writing the
    row are one step."""
    rows, load_error = _load_cycle_log(log_path)
    if load_error:
        return None, load_error

    open_pairs = {(class_name, test) for _, class_name, test in _open_test_ids(vault_root, "cycle", exclude_task=task)}
    failing = {
        key for key, status in statuses.items()
        if status in _FAILING_STATUSES and key not in open_pairs
    }

    number = len(rows)
    previous = {tuple(item) for item in rows[-1]["failing"]} - open_pairs if rows else set()
    fixed = {key for key in previous if statuses.get(key) == "ok"}
    gone = {key for key in previous if statuses.get(key) not in ("ok", *_FAILING_STATUSES)}
    new = failing - previous if rows else set()
    still = failing & previous if rows else failing

    if new or gone:
        verdict = "harmful"
    elif fixed:
        verdict = "helpful"
    else:
        verdict = "neutral"
    escalate = number >= CYCLE_ESCALATION or verdict == "harmful"

    rows.append({
        "cycle": number, "recorded_at": _iso_now(), "verdict": verdict,
        "failing": [list(key) for key in sorted(failing, key=lambda test: (test[0] or "", test[1]))],
    })
    vaultlib.write_text_lf(log_path, "".join(json.dumps(row) + "\n" for row in rows))

    lines = [f"cycle {number}: {verdict} - fixed {len(fixed)}, new {len(new)}, still failing {len(still)}"]
    if new:
        lines.append(f"  new failures: {_format_tests(new)}")
    if gone:
        lines.append(f"  failing tests no longer passing or present: {_format_tests(gone)}")
    lines.append(f"escalate: {'yes' if escalate else 'no'}")
    return "\n".join(lines) + "\n", None


# --------------------------------------------------------------------------
# dispatch
# --------------------------------------------------------------------------

def run(args):
    if not args:
        sys.stderr.write(f"compass test-checkpoint: a subcommand is required\n{USAGE}\n")
        return 1
    sub, rest = args[0], args[1:]
    if sub == "record":
        return _run_record(rest)
    if sub == "verify":
        return _run_verify(rest)
    if sub == "open-ids":
        return _run_open_ids(rest)
    if sub == "cycle":
        return _run_cycle(rest)
    sys.stderr.write(f"compass test-checkpoint: unknown subcommand {sub}\n{USAGE}\n")
    return 1
