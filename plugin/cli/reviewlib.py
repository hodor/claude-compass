"""The review protocol between Compass and any visual md interface.

A review is two JSON files in the Compass vault's `tmp/review/`:

- `<id>.request.json`, written here:
  `{"id", "surface", "file", "title", "return"}`. `surface` names the
  interface the request went to; `file` is the reviewed document's path
  relative to that surface's root, forward slashes. `return` asks the
  surface to step aside after the verdict, set when it did not have focus
  as the request was made.
- `<id>.verdict.json`, written by the surface on the human's answer:
  `{"id", "file", "verdict": "approved"|"changes", "notes", "at"}`.

A request with no verdict is pending; while it is pending the document
belongs to the human. The surfaces themselves live in `review_surfaces`.
"""

import json
import os
import secrets
import time
from pathlib import Path

import review_surfaces

REVIEW_DIR = ("tmp", "review")
VERDICTS = ("approved", "changes")


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


def write_request(compass_vault, surface, root, document, title=None, step_aside=True):
    """Write a request for `document` on `surface` (its `NAME`), `file`
    relative to `root`; return `(request, request_path)`."""
    rel = Path(document).resolve().relative_to(Path(root).resolve()).as_posix()
    rid = new_id()
    request = {"id": rid, "surface": surface, "file": rel, "title": title, "return": bool(step_aside)}
    directory = review_dir(compass_vault)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{rid}.request.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(request, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return request, path


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


def valid_verdict(verdict, request):
    return (
        isinstance(verdict, dict)
        and verdict.get("id") == request["id"]
        and verdict.get("verdict") in VERDICTS
    )


def pending(compass_vault):
    """Every request in the vault with no verdict file, oldest first."""
    directory = review_dir(compass_vault)
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.request.json")):
        request = read_json(path)
        if request is None or verdict_path(path).exists():
            continue
        out.append(request)
    return out


def _same_path(a, b):
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def under_review(compass_vault, target):
    """The pending request whose document is `target`, or None. A request
    naming no surface, or one that is not registered, is resolved by every
    registered surface."""
    target = Path(target).resolve()
    for request in pending(compass_vault):
        surface = review_surfaces.named(request.get("surface"))
        for candidate in [surface] if surface else review_surfaces.SURFACES:
            path = candidate.resolve(request, compass_vault)
            if path is not None and _same_path(Path(path).resolve(), target):
                return request
    return None


def install(compass_vault, shipped_root=None):
    """Run every surface's install; one `<name>: <what was done>` line each."""
    return [f"{s.NAME}: {s.install(compass_vault, shipped_root)}" for s in review_surfaces.SURFACES]


def doctor_rows(compass_vault):
    """`(name, status, detail, fix)` per surface, for `compass doctor`."""
    return [(s.NAME, *s.doctor(compass_vault)) for s in review_surfaces.SURFACES]
