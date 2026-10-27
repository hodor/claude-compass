"""`compass review <file>... [--why <path>=<line>]... [--title T] [--timeout S]
[--no-wait]` and `compass review --status`, `compass review --cancel <id>` and
`compass review --install` - put documents in front of the human in a visual
md interface and wait for the verdict.

`review <file>...` writes one request (see `reviewlib`) for the files in the
order given, delivers it to the first review surface configured for them (see
`review_surfaces`), and waits. Every file must be committed, sit in the same
`.compass` vault and the same git repository, and be shown by the same
surface; the first file that fails names the refusal. A repeated path counts
once. With several files the request also carries `session` (the
`CLAUDE_CODE_SESSION_ID` value, empty when unset), `project` (the name of the
folder holding the vault) and, per file, an optional one-line reason given by
`--why <path>=<line>`, repeatable. A one-file request carries none of these,
and `--why` needs several files.

When the surface writes the verdict, it prints the verdict JSON, then
one `comment <file>: <note>` line per note the human left on another file,
one `edited <file>` line per file the human changed, and, for a several-file
review, one `file <path> read|unread [note: <note>]` line per listed file in
request order (a file the verdict does not mark counts as unread), then a
`--- changes since <short sha> ---` line followed by `git diff <sha>` for the
whole repository and one `untracked <path>` line per untracked file, and the
current text of the documents under a `--- <file> as the human left it ---`
line each: the one file of a one-file review, and in a several-file review
only the files with a note or an edit, in request order. The caller thus
reads the human's notes and edits and every change made during the review.
`<sha>` is the commit the request was sent at, recorded in the request as
`commit`.

A document goes out only when it is committed: one with uncommitted changes,
one outside a git repository, a repository with no commits, and a machine
without git all print `not configured: <why>`.

The first stdout line is always one of:
  `requested <id> <file>`   the request went out
  `not configured: <why>`   nothing was sent; ask in the terminal instead

The request goes to the `.compass` vault that holds the documents. A new
request for a document already waiting withdraws the older request, several
files or not, whose waiter ends with `withdrawn <id>`.

`--no-wait` returns after the request line. The wait has no limit: the
human may answer hours later. `--timeout S` bounds it and prints
`timeout <id>` when it runs out. `--status`
prints one `pending <id> <file>` line per request still waiting, the first
file followed by `(+N more)` when the request lists N more.
`--cancel <id>` withdraws that pending request (removes its request file),
which ends its waiter with `withdrawn <id>` and clears the review in the
surface; an id that is not pending prints a message on stderr.
`--install` runs every surface's install, printing one `<surface>: <what was
done>` line each. A surface may need a step only the human can take, such
as turning community plugins on in Obsidian; `compass doctor` names it.

Exit 0 on a verdict, on `--no-wait`, `--status`, `--cancel` and `--install`;
1 when not configured, on timeout, on a withdrawn request, on a usage error,
on a `--cancel` of an id that is not pending, or when `--status`, `--cancel`
or `--install` finds no `.compass` vault; never 2.
"""

import json
import os
import sys
import time
from pathlib import Path

import reviewlib
import vaultlib

POLL_SECONDS = 0.5

USAGE = ("usage: compass review <file>... [--why <path>=<line>]... [--title T] [--timeout S] [--no-wait]\n"
         "       compass review --status\n"
         "       compass review --cancel <id>\n"
         "       compass review --install\n")


def _parse(args):
    opts = {"files": [], "whys": [], "title": None, "timeout": None, "wait": True,
            "status": False, "install": False, "cancel": None}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--status":
            opts["status"] = True
        elif arg == "--install":
            opts["install"] = True
        elif arg == "--cancel":
            if i + 1 >= len(args):
                raise ValueError("--cancel needs a request id")
            i += 1
            opts["cancel"] = args[i]
        elif arg == "--no-wait":
            opts["wait"] = False
        elif arg in ("--title", "--timeout", "--why"):
            if i + 1 >= len(args):
                raise ValueError(f"{arg} needs a value")
            i += 1
            if arg == "--title":
                opts["title"] = args[i]
            elif arg == "--why":
                opts["whys"].append(args[i])
            else:
                try:
                    opts["timeout"] = float(args[i])
                except ValueError:
                    raise ValueError(f"--timeout needs a number of seconds, got {args[i]!r}")
                if opts["timeout"] <= 0:
                    raise ValueError("--timeout must be more than 0")
        elif arg.startswith("--"):
            raise ValueError(f"unknown flag {arg}")
        else:
            opts["files"].append(arg)
        i += 1
    modes = [opts["status"], opts["install"], opts["cancel"] is not None]
    if sum(modes) > 1:
        raise ValueError("--status, --cancel and --install are separate runs")
    if not any(modes) and not opts["files"]:
        raise ValueError("name the file to review")
    return opts


def _one_line(text):
    return " ".join(text.split()) if isinstance(text, str) else ""


def _reasons(files, whys):
    """`{file argument: one-line reason}` from the `--why <path>=<line>`
    values. A value names the file it belongs to by the path as given on the
    command line or as it resolves; the path ends at the `=` that follows it,
    so a reason may contain `=`."""
    reasons = {}
    for raw in whys:
        for given in sorted(files, key=len, reverse=True):
            matched = next((name for name in (given, str(Path(given).resolve()))
                            if raw.startswith(name + "=")), None)
            if matched:
                reasons[given] = _one_line(raw[len(matched) + 1:])
                break
        else:
            raise ValueError(f"--why needs <path>=<line> with a path among the files, got {raw!r}")
    return reasons


def _status():
    try:
        vault = vaultlib.find_vault_root()
    except FileNotFoundError:
        print("no .compass vault found")
        return 1
    for request in reviewlib.pending(vault):
        extra = len(reviewlib.request_files(request)) - 1
        more = f" (+{extra} more)" if extra > 0 else ""
        print(f"pending {request.get('id')} {request.get('file')}{more}")
    return 0


def _cancel(request_id):
    try:
        vault = vaultlib.find_vault_root()
    except FileNotFoundError:
        sys.stderr.write("compass review: no .compass vault found\n")
        return 1
    if not reviewlib.cancel(vault, request_id):
        sys.stderr.write(f"compass review: no pending review with id {request_id!r}\n")
        return 1
    return 0


def _print_carried(verdict):
    for comment in verdict.get("comments", []):
        if isinstance(comment, dict):
            print(f"comment {_one_line(comment.get('file', ''))}: {_one_line(comment.get('note', ''))}")
    for path in verdict.get("edited", []):
        if isinstance(path, str):
            print(f"edited {_one_line(path)}")


def _marks(verdict):
    """`{file: (read, note)}` from a verdict's `files` list."""
    return {entry["file"]: (entry["read"], entry.get("note") or "")
            for entry in verdict.get("files") or []}


def _print_file_lines(documents, marks):
    for rel, _ in documents:
        read, note = marks.get(rel, (False, ""))
        suffix = f" note: {_one_line(note)}" if _one_line(note) else ""
        print(f"file {rel} {'read' if read else 'unread'}{suffix}")


def _print_changes(root, commit, skip):
    for line in reviewlib.changes_since(root, commit, skip):
        print(line)


def _print_document(rel, path, newline):
    print(f"--- {rel} as the human left it ---")
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"(the document can no longer be read: {exc})")
        return
    print(text, end="")
    if newline and text and not text.endswith("\n"):
        print()


def _print_answer(request, verdict, documents, root, vault):
    print(json.dumps(verdict, indent=2))
    _print_carried(verdict)
    several = len(documents) > 1
    marks = _marks(verdict)
    if several:
        _print_file_lines(documents, marks)
    _print_changes(root, request["commit"], reviewlib.review_dir(vault))
    if not several:
        _print_document(request["file"], documents[0][1], newline=False)
        return
    edited = {path for path in verdict.get("edited", []) if isinstance(path, str)}
    for rel, path in documents:
        if _one_line(marks.get(rel, (False, ""))[1]) or rel in edited:
            _print_document(rel, path, newline=True)


def _wait(request, request_path, documents, timeout, root, vault):
    target = reviewlib.verdict_path(request_path)
    deadline = None if timeout is None else time.monotonic() + timeout
    while deadline is None or time.monotonic() < deadline:
        if target.exists():
            verdict = reviewlib.read_json(target)
            if reviewlib.valid_verdict(verdict, request):
                _print_answer(request, verdict, documents, root, vault)
                return 0
        if not Path(request_path).exists():
            print(f"withdrawn {request['id']}")
            return 1
        time.sleep(POLL_SECONDS)
    print(f"timeout {request['id']}")
    return 1


def _same(a, b):
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def _prepare(given):
    """Check every file named on the command line, in order, and return
    `(documents, surface, context, vault, root, commit)`; raises
    `reviewlib.GitUnavailable` naming the first file that cannot go out.
    All files must sit in one vault and one git repository and be shown by
    one surface."""
    documents, first = [], None
    for name in given:
        document = Path(name).resolve()
        if not document.is_file():
            raise reviewlib.GitUnavailable(f"{name} is not a file")
        surface, context, reason = reviewlib.choose(document)
        if reason:
            raise reviewlib.GitUnavailable(reason)
        try:
            vault = vaultlib.find_vault_root(document.parent, honor_env=False)
        except FileNotFoundError:
            raise reviewlib.GitUnavailable(f"{name} is outside a .compass vault")
        root, rel = reviewlib.repo_of(document, name)
        commit = reviewlib.committed_head(root, rel, name)
        if first is None:
            first = (surface, context, vault, root, commit)
        elif (surface is not first[0] or not _same(context["root"], first[1]["root"])
              or not _same(vault, first[2]) or not _same(root, first[3])):
            raise reviewlib.GitUnavailable(f"{name} is not in the same vault and repository as {given[0]}")
        documents.append(document)
    return (documents, *first)


def run(args):
    try:
        opts = _parse(list(args))
        given = list(dict.fromkeys(opts["files"]))
        reasons = _reasons(given, opts["whys"])
        if reasons and len(given) < 2:
            raise ValueError("--why needs several files")
    except ValueError as exc:
        sys.stderr.write(f"compass review: {exc}\n{USAGE}")
        return 1
    if opts["status"]:
        return _status()
    if opts["cancel"] is not None:
        return _cancel(opts["cancel"])
    if opts["install"]:
        try:
            vault = vaultlib.find_vault_root()
        except FileNotFoundError:
            print("no .compass vault found")
            return 1
        for line in reviewlib.install(vault):
            print(line)
        return 0

    try:
        documents, surface, context, compass_vault, root, commit = _prepare(given)
    except reviewlib.GitUnavailable as exc:
        print(f"not configured: {exc}")
        return 1

    # A newer request for a document replaces the pending one; its waiter
    # sees the request file gone and reports it withdrawn.
    for document in documents:
        while (older := reviewlib.under_review(compass_vault, document)) is not None:
            if not reviewlib.cancel(compass_vault, older.get("id")):
                break
    several = len(documents) > 1
    request, request_path = reviewlib.write_request(
        compass_vault, surface.NAME, context["root"], documents[0], opts["title"],
        step_aside=not surface.has_focus(), commit=commit,
        documents=[(d, reasons.get(g)) for d, g in zip(documents, given)] if several else None,
        session=os.environ.get("CLAUDE_CODE_SESSION_ID") or "",
        project=Path(compass_vault).parent.name)
    surface.deliver(context, request_path)
    print(f"requested {request['id']} {request['file']}", flush=True)
    if not opts["wait"]:
        return 0
    rels = [entry["file"] for entry in request["files"]] if several else [request["file"]]
    return _wait(request, request_path, list(zip(rels, documents)), opts["timeout"], root, compass_vault)
