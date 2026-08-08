"""Test-smell checks: the decidable admission filter (SPEC-013-test-quality
D-01, D-03, D-06).

A stdlib-`ast` walk over Python test files, scoped strictly to what can be
decided with no judgment. Four checks, three gate and one advisory:

- **empty-test** (gate) - a test body of only `pass`, `...`, a docstring,
  or a bare `return`.
- **duplicate-assert** (gate) - two assertion statements in one test, at
  the top level of its body, whose `ast.unparse` output is identical, with
  no intervening top-level statement that rebinds a name the assertion
  reads. The rebinding clause exists so a test that re-checks the same
  invariant across a deliberate state change is not flagged; a statement
  that only mutates a name in place (`lst.append(x)`) is not a rebind by
  this definition, which is a scope limit, not an oversight - telling a
  mutating call from a non-mutating one needs a method-name allowlist,
  which is exactly the kind of judgment this mechanism avoids.
- **literal-only** (gate) - the test never calls into the code under test;
  it only reads imported names and asserts them against literals or
  against each other. A call counts as "into the code" unless it is a
  Python builtin call (`len`, `set`, `sorted`, ...) or a call whose
  receiver is neither `self` nor a name this file binds to a module - a
  plain `import x` always binds a module, and a `from x import y` binds a
  module only when `y` is not written in `ALL_CAPS` (the constant-naming
  convention is what tells `TIER_EFFORT.keys()`, a container read, apart
  from `sync_cmd.sync(...)`, a call into the imported `sync` module -
  neither is resolvable from the AST alone). This is what excludes a
  method call on a value the test already holds (`some_dict.items()`,
  `a_list.append(x)`) without needing to enumerate every builtin container
  method. A call to `self.<x>` counts unless `<x>` is itself an assertion
  method; a call to `<imported_module>.<x>` or to any bare non-builtin
  name (a same-module helper) always counts - helper-method calls count as
  calls into the code, same as a call into the module under test directly.
- **assertion-free** (advisory) - a `test_*` function with no `assert`, no
  `self.assert*` call, no `self.fail(...)`, no `assertRaises`/`pytest.raises`
  call, and no call to a same-module or same-class helper whose name begins
  with `assert`, `_assert`, or `check`.

File discovery: a file argument is always checked, regardless of content,
even when it also appears inside a directory argument scanned in the same
run. A directory argument is walked, and a `.py` file inside it is checked
only when it carries a content signal - it defines at least one top-level
(or top-level-class-method) `test_*` function, or a top-level class whose
base list contains a name ending in `TestCase` - never merely because it
sits under a directory shaped like `tests/` (LESSON-type-dir-discovery-
needs-content-signal: a test directory commonly also holds fixtures and
helpers that are not themselves test files). The content signal uses the
same top-level scope the checks below use, so a file admitted as a test
file always has at least one function the checks actually examine. A `.py`
file that fails to parse, or that cannot be read at all, is always
reported as a `parse-error` finding (gate) rather than silently dropped or
crashing the walk - a broken file is exactly the kind of thing this filter
exists to surface.

Every check below excludes a test function's decorator list, argument
defaults, and return annotation from its call/assertion scan; only
`node.body` and everything nested inside it (an `if`, a `for`, a `with`)
is examined. A call inside `@mock.patch(...)` is never mistaken for a call
the test body makes. `duplicate-assert` narrows this further to the
body's direct top-level statements only, not descending into nested
blocks - a flat, no-judgment AST read rather than a partial data-flow
analysis, at the cost of missing an assertion buried inside an `if` or a
`for` loop.
"""

import ast
import builtins
from pathlib import Path

GATE = "gate"
ADVISORY = "advisory"

_HELPER_PREFIXES = ("assert", "_assert", "check")
_BUILTIN_NAMES = frozenset(dir(builtins))


# --------------------------------------------------------------------------
# shared AST helpers
# --------------------------------------------------------------------------

def _iter_test_functions(tree):
    """Yield `(class_name_or_None, func_name, node)` for every top-level
    `test_*` function and every `test_*` method of a top-level class."""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            yield None, node.name, node
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name.startswith("test_"):
                    yield node.name, sub.name, sub


def _iter_body_nodes(node):
    """Every descendant reachable from `node.body` - the function's actual
    statements and everything nested inside them - excluding its decorator
    list, argument defaults, and return annotation."""
    for stmt in node.body:
        yield from ast.walk(stmt)


def _is_assertion_attr(attr):
    return attr.startswith("assert") or attr == "fail"


def _is_assertion_call(node):
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and _is_assertion_attr(node.func.attr)
    )


def _finding(class_name, func_name, line, check, severity, detail=None):
    test = f"{class_name}.{func_name}" if class_name else func_name
    return {"line": line, "test": test, "check": check, "severity": severity, "detail": detail}


# --------------------------------------------------------------------------
# file discovery
# --------------------------------------------------------------------------

def _has_content_signal(tree):
    """True when `tree` has at least one function `_iter_test_functions`
    would examine, or a top-level class whose base list contains a name
    ending in `TestCase`. Sharing `_iter_test_functions`'s scope keeps
    discovery and checking consistent: a file admitted here always has a
    function the checks below actually look at."""
    for _, _, _ in _iter_test_functions(tree):
        return True
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                try:
                    text = ast.unparse(base)
                except Exception:
                    continue
                if text.endswith("TestCase"):
                    return True
    return False


def _parse_error_finding(file, detail):
    entry = _finding(None, None, 1, "parse-error", GATE, detail)
    entry["file"] = file
    return entry


def discover(paths):
    """Resolve CLI path arguments to the parsed test files to check.

    Returns `(parsed, findings)`. `parsed` is a list of `(path, tree)`
    pairs, one per file that will be checked. `findings` carries one
    `parse-error` entry (gate, `test` is `None`) per path that does not
    exist or fails to parse - explicit file arguments and directory-
    discovered files are treated identically here, since a broken file is
    reported either way rather than silently skipped.

    A file named directly as a path argument is always parsed and checked,
    even when a directory argument scanned in the same run also reaches
    it and would otherwise have rejected it for lacking a content signal:
    every path argument is collected and classified as explicit-or-not
    before any file is skipped, so argument order never changes the
    result. A directory argument is walked recursively; each `.py` file
    found is parsed and kept only when `_has_content_signal` is true for
    it - the directory walk itself applies no path-shape heuristic.
    """
    explicit_keys = set()
    candidates = []
    seen_candidates = set()
    for given in paths:
        base = Path(given)
        if base.is_dir():
            for candidate in sorted(base.rglob("*.py")):
                key = str(candidate)
                if key not in seen_candidates:
                    seen_candidates.add(key)
                    candidates.append(candidate)
        else:
            key = str(base)
            explicit_keys.add(key)
            if key not in seen_candidates:
                seen_candidates.add(key)
                candidates.append(base)

    parsed = []
    findings = []
    for candidate in candidates:
        key = str(candidate)
        explicit = key in explicit_keys
        if not candidate.is_file():
            findings.append(_parse_error_finding(key, "path not found"))
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (OSError, ValueError, SyntaxError) as exc:
            findings.append(_parse_error_finding(key, str(exc)))
            continue
        if explicit or _has_content_signal(tree):
            parsed.append((candidate, tree))
    return parsed, findings


# --------------------------------------------------------------------------
# empty-test
# --------------------------------------------------------------------------

def _strip_leading_docstring(body):
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _check_empty(class_name, func_name, node):
    body = _strip_leading_docstring(node.body)
    is_empty = (
        not body
        or (len(body) == 1 and isinstance(body[0], ast.Pass))
        or (
            len(body) == 1
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and body[0].value.value is Ellipsis
        )
        or (len(body) == 1 and isinstance(body[0], ast.Return) and body[0].value is None)
    )
    if is_empty:
        yield _finding(class_name, func_name, node.lineno, "empty-test", GATE)


# --------------------------------------------------------------------------
# duplicate-assert
# --------------------------------------------------------------------------

def _assertion_statements(body):
    """Top-level statements of a test body that are assertions: an `assert`
    statement, or a bare expression statement calling an assertion method
    (`<anything>.assert*` or `<anything>.fail`)."""
    stmts = []
    for stmt in body:
        if isinstance(stmt, ast.Assert):
            stmts.append(stmt)
        elif isinstance(stmt, ast.Expr) and _is_assertion_call(stmt.value):
            stmts.append(stmt)
    return stmts


def _names_read(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def _target_names(target):
    return {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}


def _names_rebound(stmt):
    """Names a single top-level statement rebinds: assignment targets, a
    `for` loop's target, a `with ... as` target, and a walrus (`:=`)
    target reached anywhere inside the statement."""
    names = set()
    for node in ast.walk(stmt):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                names |= _target_names(t)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            names |= _target_names(node.target)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            names |= _target_names(node.target)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    names |= _target_names(item.optional_vars)
    return names


def _check_duplicate_assert(class_name, func_name, node):
    body = node.body
    assertions = _assertion_statements(body)
    flagged_lines = set()
    for j in range(len(assertions)):
        later = assertions[j]
        for i in range(j):
            earlier = assertions[i]
            if ast.unparse(earlier) != ast.unparse(later):
                continue
            start, end = body.index(earlier) + 1, body.index(later)
            between = body[start:end]
            read_names = _names_read(later)
            rebound = set()
            for stmt in between:
                rebound |= _names_rebound(stmt)
            if read_names & rebound:
                continue
            if later.lineno not in flagged_lines:
                flagged_lines.add(later.lineno)
                yield _finding(
                    class_name, func_name, later.lineno, "duplicate-assert", GATE,
                    f"identical to line {earlier.lineno}",
                )
            break


# --------------------------------------------------------------------------
# literal-only
# --------------------------------------------------------------------------

def _imported_module_names(tree):
    """Local names this file binds to a module: every name a top-level
    `import` statement binds, and every name a top-level `from ... import`
    statement binds whose spelling is not `ALL_CAPS` - the constant-naming
    convention is the only AST-visible signal that distinguishes a
    from-imported module (`from commands import sync as sync_cmd`) from a
    from-imported constant (`from modelslib import TIER_EFFORT`); nothing
    else here can tell `sync_cmd.sync(...)` (a call into the code under
    test) apart from `TIER_EFFORT.keys()` (a container read on an imported
    constant)."""
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = alias.asname or alias.name
                if not bound.isupper():
                    names.add(bound)
    return names


def _is_code_call(call, imported_modules):
    """True when `call` reaches into the code under test rather than a
    builtin or a method invoked on a value the test already holds."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id not in _BUILTIN_NAMES
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        base = func.value.id
        if base == "self":
            return not _is_assertion_attr(func.attr)
        return base in imported_modules
    return False


def _check_literal_only(class_name, func_name, node, imported_modules):
    calls = [n for n in _iter_body_nodes(node) if isinstance(n, ast.Call)]
    if any(_is_code_call(c, imported_modules) for c in calls):
        return
    has_assertion = (
        any(isinstance(n, ast.Assert) for n in _iter_body_nodes(node))
        or any(_is_assertion_call(c) for c in calls)
    )
    if has_assertion:
        yield _finding(class_name, func_name, node.lineno, "literal-only", GATE)


# --------------------------------------------------------------------------
# assertion-free
# --------------------------------------------------------------------------

def _module_level_function_names(tree):
    return {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _is_helper_call(call, module_functions):
    func = call.func
    if isinstance(func, ast.Name):
        return func.id in module_functions and func.id.startswith(_HELPER_PREFIXES)
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "self":
        return func.attr.startswith(_HELPER_PREFIXES)
    return False


def _is_raises_call(call):
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr == "raises"
    if isinstance(func, ast.Name):
        return func.id == "raises"
    return False


def _check_assertion_free(class_name, func_name, node, module_functions):
    calls = [n for n in _iter_body_nodes(node) if isinstance(n, ast.Call)]
    has_assert_stmt = any(isinstance(n, ast.Assert) for n in _iter_body_nodes(node))
    has_assert_call = any(_is_assertion_call(c) for c in calls)
    has_raises_call = any(_is_raises_call(c) for c in calls)
    has_helper_call = any(_is_helper_call(c, module_functions) for c in calls)
    if not (has_assert_stmt or has_assert_call or has_raises_call or has_helper_call):
        yield _finding(class_name, func_name, node.lineno, "assertion-free", ADVISORY)


# --------------------------------------------------------------------------
# dispatch
# --------------------------------------------------------------------------

def run_checks(paths):
    """Run all four checks over the test files resolved from `paths`
    (file and/or directory arguments). Returns the full finding list
    sorted by `(file, line, check)`, each entry a dict with `file`, `line`,
    `test`, `check`, `severity`, and `detail` (may be `None`)."""
    parsed, findings = discover(paths)
    for path, tree in parsed:
        imported_modules = _imported_module_names(tree)
        module_functions = _module_level_function_names(tree)
        for class_name, func_name, node in _iter_test_functions(tree):
            for check_fn, extra in (
                (_check_empty, ()),
                (_check_duplicate_assert, ()),
                (_check_literal_only, (imported_modules,)),
                (_check_assertion_free, (module_functions,)),
            ):
                for entry in check_fn(class_name, func_name, node, *extra):
                    entry["file"] = str(path)
                    findings.append(entry)
    findings.sort(key=lambda f: (f["file"], f["line"], f["check"]))
    return findings
