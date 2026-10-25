"""`compass review <file> [--title T] [--timeout S] [--no-wait]` and
`compass review --status` and `compass review --install` - put a document in
front of the human in a visual md interface and wait for the verdict.

`review <file>` writes a request (see `reviewlib`), delivers it to the first
review surface configured for the document (see `review_surfaces`), and
waits. When the surface writes the verdict, it prints the verdict JSON, then
a `--- <file> as the human left it ---` line and the document's current
text, so the caller reads the human's edits.

The first stdout line is always one of:
  `requested <id> <file>`   the request went out
  `not configured: <why>`   nothing was sent; ask in the terminal instead

`--no-wait` returns after the request line. `--timeout S` bounds the wait
(default 4 hours) and prints `timeout <id>` when it runs out. `--status`
prints one `pending <id> <file>` line per request still waiting.
`--install` runs every surface's install, printing one `<surface>: <what was
done>` line each. A surface may need a step only the human can take, such
as turning community plugins on in Obsidian; `compass doctor` names it.

Exit 0 on a verdict, on `--no-wait`, `--status` and `--install`; 1 when not
configured, on timeout, on a usage error, or when `--status` or `--install`
finds no `.compass` vault; never 2.
"""

import json
import sys
import time
from pathlib import Path

import reviewlib
import vaultlib

DEFAULT_TIMEOUT = 4 * 3600
POLL_SECONDS = 0.5

USAGE = ("usage: compass review <file> [--title T] [--timeout S] [--no-wait]\n"
         "       compass review --status\n"
         "       compass review --install\n")


def _parse(args):
    opts = {"file": None, "title": None, "timeout": DEFAULT_TIMEOUT, "wait": True,
            "status": False, "install": False}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--status":
            opts["status"] = True
        elif arg == "--install":
            opts["install"] = True
        elif arg == "--no-wait":
            opts["wait"] = False
        elif arg in ("--title", "--timeout"):
            if i + 1 >= len(args):
                raise ValueError(f"{arg} needs a value")
            i += 1
            if arg == "--title":
                opts["title"] = args[i]
            else:
                try:
                    opts["timeout"] = float(args[i])
                except ValueError:
                    raise ValueError(f"--timeout needs a number of seconds, got {args[i]!r}")
                if opts["timeout"] <= 0:
                    raise ValueError("--timeout must be more than 0")
        elif arg.startswith("--"):
            raise ValueError(f"unknown flag {arg}")
        elif opts["file"] is None:
            opts["file"] = arg
        else:
            raise ValueError(f"one file per review, got a second: {arg}")
        i += 1
    if opts["status"] and opts["install"]:
        raise ValueError("--status and --install are separate runs")
    if not (opts["status"] or opts["install"]) and opts["file"] is None:
        raise ValueError("name the file to review")
    return opts


def _status():
    try:
        vault = vaultlib.find_vault_root()
    except FileNotFoundError:
        print("no .compass vault found")
        return 1
    for request in reviewlib.pending(vault):
        print(f"pending {request.get('id')} {request.get('file')}")
    return 0


def _wait(request, request_path, document, timeout):
    target = reviewlib.verdict_path(request_path)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if target.exists():
            verdict = reviewlib.read_json(target)
            if reviewlib.valid_verdict(verdict, request):
                print(json.dumps(verdict, indent=2))
                print(f"--- {request['file']} as the human left it ---")
                try:
                    print(Path(document).read_text(encoding="utf-8"), end="")
                except OSError as exc:
                    print(f"(the document can no longer be read: {exc})")
                return 0
        time.sleep(POLL_SECONDS)
    print(f"timeout {request['id']}")
    return 1


def run(args):
    try:
        opts = _parse(list(args))
    except ValueError as exc:
        sys.stderr.write(f"compass review: {exc}\n{USAGE}")
        return 1
    if opts["status"]:
        return _status()
    if opts["install"]:
        try:
            vault = vaultlib.find_vault_root()
        except FileNotFoundError:
            print("no .compass vault found")
            return 1
        for line in reviewlib.install(vault):
            print(line)
        return 0

    document = Path(opts["file"]).resolve()
    if not document.is_file():
        print(f"not configured: {opts['file']} is not a file")
        return 1
    surface, context, reason = reviewlib.choose(document)
    if reason:
        print(f"not configured: {reason}")
        return 1
    try:
        compass_vault = vaultlib.find_vault_root(document.parent)
    except FileNotFoundError:
        print(f"not configured: {opts['file']} is outside a .compass vault")
        return 1

    request, request_path = reviewlib.write_request(
        compass_vault, surface.NAME, context["root"], document, opts["title"],
        step_aside=not surface.has_focus())
    surface.deliver(context, request_path)
    print(f"requested {request['id']} {request['file']}", flush=True)
    if not opts["wait"]:
        return 0
    return _wait(request, request_path, document, opts["timeout"])
