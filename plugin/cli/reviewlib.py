"""The review protocol between Compass and any visual md interface.

A review is two JSON files in the Compass vault's `tmp/review/`:

- `<id>.request.json`, written here:
  `{"id", "surface", "file", "title", "return", "commit"}`. `surface` names
  the interface the request went to; `file` is the reviewed document's path
  relative to that surface's root, forward slashes. A request for several
  files also carries `files`, `[{"file", "why"}]` in the order given, `why`
  being a one-line reason or null and `files[0].file` equal to `file`;
  `session`, the id of the session that asked (empty when unknown); and
  `project`, the name of the folder holding the vault. `return` asks the
  surface to step aside after the verdict, set when it did not have focus
  as the request was made. `commit` is the full sha of the git HEAD the
  document was committed at when the request went out; the changes made
  during the review are everything that differs from it.
- `<id>.verdict.json`, written by the surface on the human's answer:
  `{"id", "file", "verdict": "approved"|"changes", "notes", "at"}`, plus
  three optional lists: `comments`, `{"file", "note"}` entries for notes the
  human left on other files while reviewing, `edited`, the paths of other
  files the human changed, and `files`, `{"file", "read", "note"}` entries
  marking each listed file read or unread (`read` a boolean, `note` a string
  or absent).

A request with no verdict is pending; while it is pending every file it
lists belongs to the human. Removing a pending request's file withdraws it: its
waiter ends and the surface drops the review. The surfaces themselves live
in `review_surfaces`.
"""

import json
import os
import secrets
import subprocess
import time
from pathlib import Path

import review_surfaces

REVIEW_DIR = ("tmp", "review")
VERDICTS = ("approved", "changes")
CARRIED_LISTS = ("comments", "edited")
SHORT_SHA = 10
MAX_DIFF_LINES = 2000


class GitUnavailable(Exception):
    """The review cannot be tied to a commit; the message is the reason."""


def choose(document):
    """`(surface, context, None)` for the first surface configured for
    `document`, else `(None, None, reason)` joining every surface's reason."""
    reasons = []
    for surface in review_surfaces.SURFACES:
        context, reason = surface.configuration(document)
        if context is not None:
            return surface, context, None
        reasons.append(reason)
    return None, None, "; ".join(reasons) or "no review surface is registered"


def review_dir(compass_vault):
    return Path(compass_vault).joinpath(*REVIEW_DIR)


def new_id():
    return time.strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3)


def _relative(document, root):
    return Path(document).resolve().relative_to(Path(root).resolve()).as_posix()


def write_request(compass_vault, surface, root, document, title=None, step_aside=True, commit=None,
                  documents=None, session="", project=""):
    """Write a request for `document` on `surface` (its `NAME`), `file`
    relative to `root`, recording the git `commit` it was sent at; return
    `(request, request_path)`. `documents`, a list of `(path, why)` starting
    with `document`, makes it a request for several files that also carries
    `files`, `session` and `project`."""
    rid = new_id()
    request = {"id": rid, "surface": surface, "file": _relative(document, root)}
    if documents:
        request["files"] = [{"file": _relative(path, root), "why": why or None} for path, why in documents]
        request["session"] = session or ""
        request["project"] = project or ""
    request.update({"title": title, "return": bool(step_aside), "commit": commit})
    directory = review_dir(compass_vault)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{rid}.request.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(request, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return request, path


def _git(root, *args):
    """The completed `git` run (bytes output) with `root` as the working
    directory; raises `GitUnavailable` when git cannot be started."""
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True)
    except OSError as exc:
        raise GitUnavailable(f"git cannot be run ({exc})")


def _text(data):
    return data.decode("utf-8", errors="replace")


def repo_of(document, label=None):
    """`(root, relative_path)` of `document` inside its git repository: the
    repository's top directory and the document's path from it, forward
    slashes. Raises `GitUnavailable` outside a repository or without git;
    `label` is how its message names the document."""
    document = Path(document)
    try:
        result = subprocess.run(
            ["git", "-C", str(document.parent), "rev-parse", "--show-toplevel", "--show-prefix"],
            capture_output=True)
    except OSError as exc:
        raise GitUnavailable(f"git cannot be run ({exc})")
    if result.returncode != 0:
        raise GitUnavailable(f"{label or document} is not in a git repository")
    lines = _text(result.stdout).splitlines()
    if not lines:
        raise GitUnavailable(f"{label or document} is not in a git repository")
    prefix = lines[1] if len(lines) > 1 else ""
    return lines[0], prefix + document.name


def committed_head(root, rel, label=None):
    """The full sha of HEAD when `rel` (a path from `root`) is tracked and
    equals its committed content in both the index and the worktree; raises
    `GitUnavailable` naming the problem otherwise, `label` being how it
    names the document."""
    status = _git(root, "--literal-pathspecs", "status", "--porcelain", "-z",
                  "--untracked-files=all", "--", rel)
    if status.returncode != 0:
        raise GitUnavailable(f"git status failed: {_text(status.stderr).strip()}")
    tracked = _git(root, "--literal-pathspecs", "ls-files", "--error-unmatch", "-z", "--", rel)
    if status.stdout or tracked.returncode != 0:
        raise GitUnavailable(f"{label or rel} has uncommitted changes; commit first")
    head = _git(root, "rev-parse", "--verify", "HEAD")
    sha = _text(head.stdout).strip()
    if head.returncode != 0 or not sha:
        raise GitUnavailable("the repository has no commits yet; commit first")
    return sha


def _inside(root, directory):
    """`directory`'s path from `root` as git names it, with a trailing slash,
    or None when it is not an existing directory in the repository."""
    if not Path(directory).is_dir():
        return None
    result = _git(root, "-C", str(directory), "rev-parse", "--show-prefix")
    prefix = _text(result.stdout).strip()
    return prefix if result.returncode == 0 and prefix else None


def repo_paths(root, base, names):
    """The entries of `names`, paths relative to the directory `base`, as
    paths relative to the repository `root`, forward slashes, in order and
    without repeats; an absolute entry is taken as it is. An entry that is not
    a string or leads outside the repository is left out."""
    top = Path(root).resolve()
    found = []
    for name in names:
        if not isinstance(name, str) or not name:
            continue
        try:
            rel = (Path(base) / name).resolve().relative_to(top).as_posix()
        except (OSError, ValueError):
            continue
        if rel != "." and rel not in found:
            found.append(rel)
    return found


def changes_since(root, commit, show=(), skip=None):
    """The lines that report what differs from `commit` in the repository:
    the `--- changes since <short sha> ---` header; `git diff <commit>` for
    the repository-relative paths in `show`, up to MAX_DIFF_LINES lines and a
    line naming the rest; `changed <path>` for every other changed path; then
    `untracked <path>` for each untracked file. Paths inside the directory
    `skip`, where the review's own request and verdict files sit, are left
    out of the `changed` and `untracked` lines. Diff lines split on newlines
    only, so a carriage return or a Unicode separator stays inside its
    line."""
    lines = [f"--- changes since {commit[:SHORT_SHA]} ---"]
    failure = None
    if show:
        diff = _git(root, "--literal-pathspecs", "-c", "color.ui=never", "diff", "--no-ext-diff",
                    commit, "--", *show)
        if diff.returncode == 0:
            body = _text(diff.stdout).split("\n")
            if body and body[-1] == "":
                body.pop()
            lines.extend(body[:MAX_DIFF_LINES])
            if len(body) > MAX_DIFF_LINES:
                lines.append(f"({len(body) - MAX_DIFF_LINES} more diff lines: git diff {commit[:SHORT_SHA]})")
        else:
            failure = f"(git diff failed: {_text(diff.stderr).strip()})"
            lines.append(failure)
    hidden = _inside(root, skip) if skip else None
    shown = {os.path.normcase(path) for path in show}
    changed = _git(root, "-c", "core.quotepath=false", "diff", "--name-only", "-z", commit)
    if changed.returncode == 0:
        names = [name for name in _text(changed.stdout).split("\0") if name]
        lines.extend(f"changed {name}" for name in names
                     if os.path.normcase(name) not in shown and not (hidden and name.startswith(hidden)))
    elif failure is None:
        lines.append(f"(git diff failed: {_text(changed.stderr).strip()})")
    others = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    if others.returncode == 0:
        names = [name for name in _text(others.stdout).split("\0") if name]
        lines.extend(f"untracked {name}" for name in names if not (hidden and name.startswith(hidden)))
    else:
        lines.append(f"(untracked files unavailable: {_text(others.stderr).strip()})")
    return lines


def read_json(path):
    """The parsed object at `path`, or None when absent or not yet a whole
    JSON object (the surface may be mid-write)."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def verdict_path(request_path):
    name = Path(request_path).name.replace(".request.json", ".verdict.json")
    return Path(request_path).with_name(name)


def _valid_mark(entry):
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("file"), str)
        and isinstance(entry.get("read"), bool)
        and (entry.get("note") is None or isinstance(entry["note"], str))
    )


def valid_verdict(verdict, request):
    return (
        isinstance(verdict, dict)
        and verdict.get("id") == request["id"]
        and verdict.get("verdict") in VERDICTS
        and all(isinstance(verdict.get(key, []), list) for key in CARRIED_LISTS)
        and isinstance(verdict.get("files", []), list)
        and all(_valid_mark(entry) for entry in verdict.get("files", []))
    )


def _pending_entries(compass_vault):
    """`(path, request)` for every request file with no verdict, oldest first."""
    directory = review_dir(compass_vault)
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.request.json")):
        request = read_json(path)
        if request is None or verdict_path(path).exists():
            continue
        out.append((path, request))
    return out


def pending(compass_vault):
    """Every request in the vault with no verdict file, oldest first."""
    return [request for _, request in _pending_entries(compass_vault)]


def cancel(compass_vault, request_id):
    """Withdraw the pending request whose id is exactly `request_id` by
    removing its request file; True when one was withdrawn."""
    for path, request in _pending_entries(compass_vault):
        if request_id and request.get("id") == request_id:
            try:
                path.unlink()
            except FileNotFoundError:
                return False
            return True
    return False


def _same_path(a, b):
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def request_files(request):
    """The paths a request lists, in order: its `files` entries, else its
    `file`."""
    entries = request.get("files")
    if isinstance(entries, list):
        names = [e.get("file") for e in entries if isinstance(e, dict) and isinstance(e.get("file"), str)]
        if names:
            return names
    return [request["file"]] if isinstance(request.get("file"), str) else []


def under_review(compass_vault, target):
    """The pending request that lists `target` among its documents, or None.
    A request naming no surface, or one that is not registered, is resolved
    by every registered surface."""
    target = Path(target).resolve()
    for request in pending(compass_vault):
        surface = review_surfaces.named(request.get("surface"))
        for name in request_files(request):
            for candidate in [surface] if surface else review_surfaces.SURFACES:
                path = candidate.resolve({**request, "file": name}, compass_vault)
                if path is not None and _same_path(Path(path).resolve(), target):
                    return request
    return None


def install(compass_vault, shipped_root=None):
    """Run every surface's install; one `<name>: <what was done>` line each."""
    return [f"{s.NAME}: {s.install(compass_vault, shipped_root)}" for s in review_surfaces.SURFACES]


def doctor_rows(compass_vault):
    """`(name, status, detail, fix)` per surface, for `compass doctor`."""
    return [(s.NAME, *s.doctor(compass_vault)) for s in review_surfaces.SURFACES]
