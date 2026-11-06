"""The visual md interfaces a review can open in.

Each surface is a module (or an object) with:

- `NAME`: the surface's word in output and in a request's `surface` field.
- `label`: the surface's name as a person reads it, such as `VS Code`.
- `configuration(document)`: `(context, None)` when the surface can show
  `document`, else `(None, reason)`. `context["root"]` is the directory the
  request's `file` is relative to. A surface whose add-on is missing or out of
  date installs it here, before a request is written, unless `may_install()`
  is False; a check or an install that fails is the reason.
- `deliver(context, request_path)`: put the request in front of the human.
- `has_focus()`: True when the surface is the foreground window, so the
  request asks it to stay in front after the verdict.
- `resolve(request, compass_vault)`: the absolute path of the document a
  request names, or None.
- `unconfirmed_fix()`: one line saying what to do when a delivered request
  was not claimed (the add-on writes `<id>.seen` beside the request when it
  takes it up), such as reloading the editor so it loads the add-on.
- `install(compass_vault, shipped_root=None)`: install what the surface
  needs into the project; one line saying what was done.
- `doctor(compass_vault)`: `(status, detail, fix)`, status `OK` or `WARN`.

Three more answers are used when a surface has them (every shipped surface
does); one without them is never selected for being installable, has no step
for the human, and has nothing to prepare:

- `installable(compass_vault)`: True when a review can set the surface up for
  the project on first use.
- `pending_step(compass_vault)`: the one line of a step only the human can
  take before reviews open here, or None.
- `prepare(compass_vault)`: what `compass review --editor` does for the
  surface beyond naming it; one line saying what was done.

`SURFACES` lists them in the order a review prefers them when no editor is named.
"""

from contextlib import contextmanager

from review_surfaces import obsidian, vscode

SURFACES = [obsidian, vscode, vscode.CURSOR]

_check_only = 0


@contextmanager
def check_only():
    """While active, `configuration` only inspects: it installs nothing.
    Reports such as `compass doctor` read surfaces this way."""
    global _check_only
    _check_only += 1
    try:
        yield
    finally:
        _check_only -= 1


def may_install():
    """False inside `check_only()`."""
    return not _check_only


_listings = None


@contextmanager
def shared_listings():
    """While active, a surface keeps what it learned from its editor in one
    dictionary (see `listing_cache`), so checking several documents asks the
    editor once. Nested uses share the outermost dictionary."""
    global _listings
    outer = _listings
    _listings = {} if outer is None else outer
    try:
        yield
    finally:
        _listings = outer


def listing_cache():
    """The dictionary of `shared_listings()`, or None outside it."""
    return _listings


def named(name):
    """The registered surface called `name`, or None."""
    return next((s for s in SURFACES if s.NAME == name), None)
