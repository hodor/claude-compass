"""`compass test-checkpoint record | verify | open-ids` - tamper-evident
checkpoints for pre-build failing tests.

A checkpoint records that a set of test files, in a specific state, existed
and failed before the implementation they test was written. `record` stores
an index at `.compass/tmp/test-checkpoints/TASK-NNN.json`, but git is the
authority: the index carries only a commit SHA, per-file SHA-256 hashes, and
the `(class, test_name)` ids extracted from the file at that commit.
`verify` never trusts the index for content or membership - it re-derives
the checkpointed file list from `git diff-tree` on the recorded commit and
re-reads every file's baseline text with `git show <sha>:<path>`, so editing
or deleting the index cannot launder a modification (SPEC-013-test-quality
D-04, D-06).

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
test id to appear as `ok` (unittest's verbose-mode marker for a pass) in
the supplied run output; anything else - skipped, failed, errored, or
simply absent - is a finding. A `verify --against-run` call that finds
nothing wrong marks the checkpoint `landed`, which is what `open-ids`
excludes: it prints the checkpointed ids of every task whose checkpoint is
recorded, not `not_required`, and not yet landed - the mechanical
definition of "no failures outside the open checkpoint set" that this
plan's suite-green rule depends on everywhere else.

Vault root resolution goes through `vaultlib.find_vault_root`
(LESSON-scratch-vaults-need-compass-dir). Never exits 2; a missing git
binary, a detached or non-repository working tree, and a corrupt index all
report a message on stderr and exit 1 rather than raising.
"""

import ast
import datetime
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path, PurePosixPath

import vaultlib

CHECKPOINTS_DIR = ("tmp", "test-checkpoints")

USAGE = (
    "usage: compass test-checkpoint record TASK-NNN <file>... --commit SHA "
    "[--red-evidence PATH] [--supersede TASK-NNN --reason \"...\"] [--not-required]\n"
    "       compass test-checkpoint verify TASK-NNN [--tree PATH] "
    "[--against-run EVIDENCE] [--expect-checkpoint]\n"
    "       compass test-checkpoint open-ids"
)

# unittest -v line: "test_name (module.path.ClassName) ... ok" (also FAIL,
# ERROR, or "skipped '<reason>'").
_RUN_LINE_RE = re.compile(
    r"^(?P<name>\w+)\s+\((?P<path>[\w.]+)\)\s+\.\.\.\s+(?P<status>ok|FAIL|ERROR|skipped.*)\s*$"
)


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
    repo_root = Path(vault_root).parent
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

    if not _require_git_repo(repo_root):
        sys.stderr.write("compass test-checkpoint record: not a git repository (or git is unavailable)\n")
        return 1

    commit = options["commit"]
    if not _git_commit_exists(repo_root, commit):
        sys.stderr.write(f"compass test-checkpoint record: commit {commit} not found in git log\n")
        return 1

    commit_files = set(_git_commit_files(repo_root, commit))
    file_records = []
    dirs = set()
    for given in options["files"]:
        rel = _to_posix_rel(repo_root, given)
        if rel not in commit_files:
            sys.stderr.write(f"compass test-checkpoint record: {rel} is not part of commit {commit}\n")
            return 1
        content = _git_show(repo_root, commit, rel)
        if content is None:
            sys.stderr.write(f"compass test-checkpoint record: could not read {rel} at {commit}\n")
            return 1
        tree, parse_error = _parse_source(content)
        if parse_error:
            sys.stderr.write(f"compass test-checkpoint record: {rel} does not parse: {parse_error}\n")
            return 1
        ids = sorted(
            [class_name, func_name]
            for (class_name, func_name) in _function_occurrences(tree)
            if func_name.startswith("test")
        )
        file_records.append({"path": rel, "sha256": _sha256_text(content), "ids": ids})
        dirs.add(str(PurePosixPath(rel).parent))

    exclude = {fr["path"] for fr in file_records}
    support_surface = _collect_support_surface(repo_root, commit, dirs, exclude)

    record = {
        "task": task, "version": version, "recorded_at": _iso_now(),
        "commit": commit, "red_evidence": options["red_evidence"], "not_required": False,
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
    i = 0
    while i < len(rest):
        arg = rest[i]
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
    return {
        "task": task, "tree": tree_opt, "against_run": against_run,
        "expect_checkpoint": expect_checkpoint,
    }, None


def _parse_run_evidence(text):
    """`{(class_name, test_name): status}` from unittest `-v` output, status
    one of `ok`, `fail`, `error`, `skipped`. A test id absent from the
    evidence is simply absent from this map - callers treat that as "not
    proven passed", the same as any status other than `ok`."""
    statuses = {}
    for line in text.splitlines():
        match = _RUN_LINE_RE.match(line.strip())
        if not match:
            continue
        name, path, raw_status = match.group("name"), match.group("path"), match.group("status")
        class_name = path.rsplit(".", 1)[-1] if "." in path else None
        status = "ok" if raw_status == "ok" else ("skipped" if raw_status.startswith("skipped") else raw_status.lower())
        statuses[(class_name, name)] = status
        statuses[(None, name)] = status
    return statuses


def _print_report(task, record, findings):
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
    sys.stdout.write("\n".join(lines) + "\n")


def _run_verify(args):
    options, error = _parse_verify(args)
    if error:
        sys.stderr.write(f"compass test-checkpoint verify: {error}\n{USAGE}\n")
        return 1

    task = options["task"]
    vault_root = vaultlib.find_vault_root()
    repo_root = Path(vault_root).parent
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

    if not _require_git_repo(repo_root):
        sys.stderr.write("compass test-checkpoint verify: not a git repository (or git is unavailable)\n")
        return 1

    sha = record.get("commit")
    if not _git_commit_exists(repo_root, sha):
        sys.stderr.write(f"compass test-checkpoint verify: commit {sha} for {task} not found in git log\n")
        return 1

    tree_root = Path(options["tree"]) if options["tree"] else repo_root
    commit_files = _git_commit_files(repo_root, sha)

    findings = []
    ok = True
    for rel in commit_files:
        baseline = _git_show(repo_root, sha, rel)
        if baseline is None:
            continue
        current_path = tree_root / rel
        if not current_path.is_file():
            findings.append({"file": rel, "status": "missing", "detail": None})
            ok = False
            continue
        current_src = current_path.read_text(encoding="utf-8")
        result = _classify_file(baseline, current_src)
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
        statuses = _parse_run_evidence(evidence_path.read_text(encoding="utf-8"))
        for file_record in record.get("files", []):
            for class_name, test_name in file_record.get("ids", []):
                status = statuses.get((class_name, test_name))
                label = f"{class_name}.{test_name}" if class_name else test_name
                if status != "ok":
                    findings.append({
                        "file": label, "status": "not-passed",
                        "detail": status or "not present in run evidence",
                    })
                    ok = False

    _print_report(task, record, findings)

    if ok and options["against_run"]:
        record["landed"] = True
        record["landed_at"] = _iso_now()
        _write_record(path, record)

    return 0 if ok else 1


# --------------------------------------------------------------------------
# open-ids
# --------------------------------------------------------------------------

def _dotted_module(path):
    return str(PurePosixPath(path).with_suffix("")).replace("/", ".")


def _run_open_ids(args):
    if args:
        sys.stderr.write(f"compass test-checkpoint open-ids: unexpected argument(s): {' '.join(args)}\n")
        return 1

    vault_root = vaultlib.find_vault_root()
    checkpoints_dir = Path(vault_root).joinpath(*CHECKPOINTS_DIR)
    ids = []
    if checkpoints_dir.is_dir():
        for entry in sorted(checkpoints_dir.glob("TASK-*.json")):
            record, load_error = _load_record(entry)
            if load_error:
                sys.stderr.write(f"compass test-checkpoint open-ids: skipping {entry.name}: {load_error}\n")
                continue
            if record.get("landed") or record.get("not_required"):
                continue
            for file_record in record.get("files", []):
                module = _dotted_module(file_record["path"])
                for class_name, test_name in file_record.get("ids", []):
                    ids.append(f"{module}.{class_name}.{test_name}" if class_name else f"{module}.{test_name}")

    if ids:
        sys.stdout.write("\n".join(ids) + "\n")
    return 0


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
    sys.stderr.write(f"compass test-checkpoint: unknown subcommand {sub}\n{USAGE}\n")
    return 1
