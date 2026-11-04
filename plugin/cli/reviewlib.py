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
  files the human changed, and `files`, `{"file", "read", "note", "verdict"}`
  entries marking each listed file read or unread (`read` a boolean, `note` a
  string or absent). In a several-file review each entry's `verdict` is
  `"approved"` or `"changes"`, that file's own answer, and the top-level
  `verdict` is `"approved"` when every file is approved, else `"changes"`. An
  entry without a `verdict` takes the top-level one.

- `<id>.changes.diff`, written here beside the request when the review lists
  a document an earlier review in the vault already listed: `git diff <sha>
  -- <file>` for each listed file whose content differs from the commit its
  own latest earlier review was sent at (`commit` in that request), run from
  the repository top and joined in listed order. A first review, and a file
  that equals what the earlier review showed, add nothing; with nothing to
  add no file is written. It is written before the request, and removing the
  request removes it.

- `<id>.seen`, an empty file written by the surface beside the request when it
  takes the request up. Its presence tells `compass review` the add-on is
  loaded and has the request; a request without one after the
  acknowledgement window makes the waiter print one `waiting:` line and keep
  waiting. Removing the request removes it, and
  writing a request removes every `.seen` older than `ORPHAN_SECONDS` (an
  hour) whose request is gone. It does not make the request answered.

A request with no verdict is pending; while it is pending every file it
lists belongs to the human. Removing a pending request's file withdraws it: its
waiter ends and the surface drops the review. The surfaces themselves live
in `review_surfaces`.
"""

import json
import os
import re
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
ORPHAN_SECONDS = 3600
EDITOR_SETTING = "review_editor"
PER_USER_EDITORS = ("vscode", "cursor")
YAML_NULLS = ("null", "Null", "NULL", "~")
_SETTING_LINE = re.compile(rf"^{EDITOR_SETTING}[ \t]*:[ \t]*(.*)$")
_SHA = re.compile(r"[0-9a-fA-F]{7,64}")


class GitUnavailable(Exception):
    """The review cannot be tied to a commit; the message is the reason."""


def _setting_value(text):
    """The `review_editor` value in the text of a plugin.yaml: the first
    top-level line naming it, with its quotes and trailing comment removed;
    None when absent, empty or a YAML null written without quotes."""
    for line in text.splitlines():
        found = _SETTING_LINE.match(line)
        if not found:
            continue
        value = found.group(1).strip()
        if value[:1] in ("'", '"'):
            end = value.find(value[0], 1)
            value = value[1:end] if end > 0 else value[1:]
        else:
            value = re.split(r"(?:^|\s)#", value, maxsplit=1)[0].strip()
            if value in YAML_NULLS:
                return None
        return value.strip() or None
    return None


def review_editor(compass_vault):
    """The surface name `review_editor` gives in the vault's
    `meta/plugin.yaml`, or None when the file or the setting is missing or
    unreadable."""
    try:
        data = (Path(compass_vault) / "meta" / "plugin.yaml").read_bytes()
    except OSError:
        return None
    return _setting_value(data.decode("utf-8-sig", errors="replace"))


def _vault_of(document):
    """The `.compass` directory holding `document`, or None when it sits in
    none."""
    try:
        parents = Path(document).resolve().parents
    except OSError:
        return None
    return next((parent for parent in parents if parent.name == ".compass"), None)


def _ready_surface(probe):
    """The first registered surface that can show `probe` as things stand,
    installing nothing, or None."""
    with review_surfaces.check_only():
        return next((s for s in review_surfaces.SURFACES if s.configuration(probe)[0] is not None), None)


def _installable(surface, compass_vault):
    """True when the surface says it can be set up for the vault, which a
    review then does on first use. A surface that gives no such answer
    cannot."""
    check = getattr(surface, "installable", None)
    return bool(check and check(compass_vault))


def pending_step(surface, compass_vault):
    """The one step only the human can take before `surface` shows reviews
    for the vault, or None when it has none."""
    step = getattr(surface, "pending_step", None)
    return step(compass_vault) if step else None


def selected_surface(compass_vault, probe=None):
    """The surface reviews of the vault go to, by one rule for delivery, the
    automatic install and the doctor report: the surface `review_editor`
    names; else the first registered surface that is ready without
    installing anything; else the first one that can be installed. None when
    the setting names no registered surface or nothing qualifies. `probe` is
    the document a surface is asked about; it defaults to the vault's
    `index.md`."""
    named = review_editor(compass_vault)
    if named:
        return review_surfaces.named(named)
    ready = _ready_surface(probe or Path(compass_vault) / "index.md")
    if ready is not None:
        return ready
    return next((s for s in review_surfaces.SURFACES if _installable(s, compass_vault)), None)


def known_editors():
    """The registered surface names, comma separated."""
    return ", ".join(s.NAME for s in review_surfaces.SURFACES) or "none"


def choose(document):
    """`(surface, context, None)` for the surface that shows `document`, else
    `(None, None, reason)`. The surface is `selected_surface` of the
    document's own vault, and the reason names what stops it, with the step
    the human takes when there is one. A document in no vault, or a vault
    where no surface is ready or installable, is offered to every surface in
    turn and the reasons are joined."""
    vault = _vault_of(document)
    if vault is not None:
        named = review_editor(vault)
        if named and review_surfaces.named(named) is None:
            return None, None, f"{EDITOR_SETTING} names {named}, which is not a review editor (known: {known_editors()})"
        surface = selected_surface(vault, document)
        if surface is not None:
            context, reason = surface.configuration(document)
            if context is not None:
                return surface, context, None
            step = pending_step(surface, vault)
            lead = f"{EDITOR_SETTING} names {surface.NAME}: " if named else ""
            return None, None, lead + reason + (f"; {step}" if step else "")
    reasons = []
    for surface in review_surfaces.SURFACES:
        context, reason = surface.configuration(document)
        if context is not None:
            return surface, context, None
        reasons.append(reason)
    return None, None, "; ".join(reasons) or "no review surface is registered"


def editor_report(compass_vault):
    """`(status, detail, fix)` saying which editor reviews open in, status
    `OK`, `WARN` or `FAIL`, from the same `selected_surface` delivery uses.
    No editor set up is `OK`, since reviews then go through the terminal. A
    selected editor that cannot show reviews yet is a `WARN` when the setting
    names it or a step only the human can take is waiting; one that the first
    review will install is `OK` when nothing names it. A `review_editor`
    naming no registered surface is a `FAIL`."""
    named = review_editor(compass_vault)
    where = f"set {EDITOR_SETTING} in .compass/meta/plugin.yaml"
    if named and review_surfaces.named(named) is None:
        known = known_editors()
        return ("FAIL", f"{EDITOR_SETTING} names {named}, which is not a review editor (known: {known})",
                f"{where} to one of: {known}")
    chosen = selected_surface(compass_vault)
    if chosen is None:
        return "OK", "no review editor is set up; reviews are asked in the terminal", None
    with review_surfaces.check_only():
        ready = chosen.configuration(Path(compass_vault) / "index.md")[0] is not None
    if ready:
        if named:
            return "OK", f"reviews open in {named} ({EDITOR_SETTING} in plugin.yaml)", None
        return "OK", f"reviews open in {chosen.NAME}", None
    source = f" ({EDITOR_SETTING} in plugin.yaml)" if named else ""
    step = pending_step(chosen, compass_vault)
    if step:
        return "WARN", f"reviews are meant to open in {chosen.NAME}{source}, which is not set up yet", step
    if _installable(chosen, compass_vault):
        if named:
            return ("WARN", f"{EDITOR_SETTING} names {chosen.NAME}; its add-on is not installed yet and the first "
                    "review installs it", "run compass review --install to install it now")
        return "OK", f"reviews open in {chosen.NAME}; its add-on installs on the first review", None
    return ("WARN", f"{EDITOR_SETTING} names {chosen.NAME}, which is not set up; reviews are asked in the terminal",
            f"run compass review --install, or {where}")


def _with_setting(text, name):
    """`text` of a plugin.yaml with the first top-level `review_editor` line
    set to `name`, every other line kept as it is; the line is appended when
    the text has none. A replaced line keeps its line ending and a leading
    byte-order mark."""
    lines = re.findall(r"[^\n]*\n|[^\n]+", text)
    for i, line in enumerate(lines):
        bom = "\ufeff" if line.startswith("\ufeff") else ""
        body = line[len(bom):]
        bare = body.rstrip("\r\n")
        if _SETTING_LINE.match(bare):
            lines[i] = f"{bom}{EDITOR_SETTING}: {name}{body[len(bare):]}"
            return "".join(lines)
    newline = "\r\n" if "\r\n" in text else "\n"
    if lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] += newline
    return "".join(lines) + f"{EDITOR_SETTING}: {name}{newline}"


def set_editor(compass_vault, name):
    """Make `name` the vault's review editor: write the `review_editor` line
    in `meta/plugin.yaml` and let the surface prepare itself for the project.
    Returns `(lines, step)`: what was done, one line each, and the step only
    the human can take before reviews open there, or None. A line starting
    `<name>: failed` or `<name>: skipped` says the surface could not be
    prepared. Raises ValueError for a name no registered surface has and
    OSError when plugin.yaml cannot be written."""
    name = (name or "").strip().lower()
    surface = review_surfaces.named(name)
    if surface is None:
        raise ValueError(f"{name or 'an empty name'} is not a review editor (known: {known_editors()})")
    path = Path(compass_vault) / "meta" / "plugin.yaml"
    try:
        text = path.read_bytes().decode("utf-8", errors="surrogateescape")
    except FileNotFoundError:
        text = ""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(_with_setting(text, name).encode("utf-8", errors="surrogateescape"))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    lines = [f"{EDITOR_SETTING} set to {name} in {path}"]
    prepare = getattr(surface, "prepare", None)
    if prepare:
        try:
            lines.append(f"{name}: {prepare(compass_vault)}")
        except OSError as exc:
            lines.append(f"{name}: failed: {exc}")
    return lines, pending_step(surface, compass_vault)


def shared_checks():
    """A `with` block inside which the surfaces keep what they learn from their
    editors, so checking several documents asks each editor once."""
    return review_surfaces.shared_listings()


def review_dir(compass_vault):
    return Path(compass_vault).joinpath(*REVIEW_DIR)


def new_id():
    return time.strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3)


def _relative(document, root):
    return Path(document).resolve().relative_to(Path(root).resolve()).as_posix()


def changes_path(request_path):
    """The `<id>.changes.diff` file beside a request file."""
    name = Path(request_path).name.replace(".request.json", ".changes.diff")
    return Path(request_path).with_name(name)


def seen_path(request_path):
    """The `<id>.seen` file beside a request file."""
    name = Path(request_path).name.replace(".request.json", ".seen")
    return Path(request_path).with_name(name)


def _drop_orphan_claims(directory):
    """Remove every `<id>.seen` in `directory` older than `ORPHAN_SECONDS`
    whose `<id>.request.json` is gone: a claim written after its request was
    withdrawn. A newer one stays, since its request may still be on its way."""
    now = time.time()
    for claim in Path(directory).glob("*.seen"):
        request = claim.with_name(claim.name[: -len(".seen")] + ".request.json")
        try:
            if not request.exists() and now - claim.stat().st_mtime > ORPHAN_SECONDS:
                claim.unlink(missing_ok=True)
        except OSError:
            continue


def _write_atomic(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def write_request(compass_vault, surface, root, document, title=None, step_aside=True, commit=None,
                  documents=None, session="", project="", changes=b""):
    """Write a request for `document` on `surface` (its `NAME`), `file`
    relative to `root`, recording the git `commit` it was sent at; return
    `(request, request_path)`. `documents`, a list of `(path, why)` starting
    with `document`, makes it a request for several files that also carries
    `files`, `session` and `project`. Non-empty `changes` (bytes, see
    `changes_record`) is saved beside the request, ahead of it."""
    rid = new_id()
    request = {"id": rid, "surface": surface, "file": _relative(document, root)}
    if documents:
        request["files"] = [{"file": _relative(path, root), "why": why or None} for path, why in documents]
        request["session"] = session or ""
        request["project"] = project or ""
    request.update({"title": title, "return": bool(step_aside), "commit": commit})
    directory = review_dir(compass_vault)
    directory.mkdir(parents=True, exist_ok=True)
    _drop_orphan_claims(directory)
    path = directory / f"{rid}.request.json"
    record = changes_path(path)
    try:
        if changes:
            _write_atomic(record, changes)
        _write_atomic(path, json.dumps(request, indent=2).encode("utf-8"))
    except OSError:
        record.unlink(missing_ok=True)
        raise
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
    a string, names a directory, or leads outside the repository is left
    out."""
    top = Path(root).resolve()
    found = []
    for name in names:
        if not isinstance(name, str) or not name:
            continue
        try:
            full = (Path(base) / name).resolve()
            rel = full.relative_to(top).as_posix()
        except (OSError, ValueError):
            continue
        if rel != "." and not full.is_dir() and rel not in found:
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
                    "--no-renames", commit, "--", *show)
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
    changed = _git(root, "-c", "core.quotepath=false", "diff", "--name-only", "--no-renames", "-z", commit)
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


def _order(path):
    """Sort key for request files, oldest first: the timestamp in the id, then
    the time the file was written, which orders requests made in one second."""
    try:
        written = path.stat().st_mtime_ns
    except OSError:
        written = 0
    return (path.name[:15], written, path.name)


def _earlier_commits(compass_vault, documents):
    """`{index: commit}` for each of `documents` (resolved paths) that a
    request in the vault lists: the `commit` of the newest such request."""
    directory = review_dir(compass_vault)
    found = {}
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.request.json"), key=_order):
        request = read_json(path)
        if request is None or not isinstance(request.get("commit"), str) or not _SHA.fullmatch(request["commit"]):
            continue
        surface = review_surfaces.named(request.get("surface"))
        for name in request_files(request):
            for candidate in [surface] if surface else review_surfaces.SURFACES:
                listed = candidate.resolve({**request, "file": name}, compass_vault)
                if listed is None:
                    continue
                for i, document in enumerate(documents):
                    if _same_path(Path(listed).resolve(), document):
                        found[i] = request["commit"]
    return found


def changes_record(compass_vault, root, documents):
    """The bytes of a `<id>.changes.diff`: `git diff <sha> -- <file>` run in
    the repository `root` for each of `documents` (paths, in listed order)
    that an earlier request in the vault listed, `<sha>` being the commit
    that newest request was sent at, and that differs from it. Empty when no
    listed file qualifies. A diff git cannot produce (the commit is gone)
    adds nothing."""
    resolved = [Path(document).resolve() for document in documents]
    record = b""
    for i, commit in sorted(_earlier_commits(compass_vault, resolved).items()):
        names = repo_paths(root, root, [str(resolved[i])])
        if not names:
            continue
        diff = _git(root, "--literal-pathspecs", "-c", "color.ui=never", "-c", "core.quotepath=false",
                    "diff", "--no-ext-diff", "--src-prefix=a/", "--dst-prefix=b/", "--end-of-options", commit,
                    "--", names[0])
        if diff.returncode == 0:
            record += diff.stdout
    return record


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
        and ("verdict" not in entry or entry["verdict"] in VERDICTS)
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
    removing its request file and the changes record and claim beside it; True
    when one was withdrawn."""
    for path, request in _pending_entries(compass_vault):
        if request_id and request.get("id") == request_id:
            changes_path(path).unlink(missing_ok=True)
            seen_path(path).unlink(missing_ok=True)
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


def install(compass_vault, shipped_root=None, automatic=False):
    """Run every surface's install; one `<name>: <what was done>` line each.
    The line for an editor that installs its extension once per user says so.
    An `automatic` install, run by an update rather than asked for, installs a
    per-user editor's extension only when that editor is the vault's
    `selected_surface`, since the extension lands in the user's editor for
    every project."""
    lines = []
    picked = selected_surface(compass_vault) if automatic else None
    for surface in review_surfaces.SURFACES:
        if automatic and surface.NAME in PER_USER_EDITORS and surface is not picked:
            lines.append(f"{surface.NAME}: installed nothing (reviews of this project do not open in it)")
            continue
        line = f"{surface.NAME}: {surface.install(compass_vault, shipped_root)}"
        if surface.NAME in PER_USER_EDITORS:
            line += " (the extension installs once per user)"
        lines.append(line)
    return lines


def doctor_rows(compass_vault):
    """`(name, status, detail, fix)` per surface, for `compass doctor`."""
    return [(s.NAME, *s.doctor(compass_vault)) for s in review_surfaces.SURFACES]
