"""The visual md interfaces a review can open in.

Each surface is a module (or an object) with:

- `NAME`: the surface's word in output and in a request's `surface` field.
- `configuration(document)`: `(context, None)` when the surface can show
  `document`, else `(None, reason)`. `context["root"]` is the directory the
  request's `file` is relative to.
- `deliver(context, request_path)`: put the request in front of the human.
- `has_focus()`: True when the surface is the foreground window, so the
  request asks it to stay in front after the verdict.
- `resolve(request, compass_vault)`: the absolute path of the document a
  request names, or None.
- `install(compass_vault, shipped_root=None)`: install what the surface
  needs into the project; one line saying what was done.
- `doctor(compass_vault)`: `(status, detail, fix)`, status `OK` or `WARN`.

`SURFACES` lists them in the order a review tries them.
"""

from review_surfaces import obsidian, vscode

SURFACES = [obsidian, vscode, vscode.CURSOR]


def named(name):
    """The registered surface called `name`, or None."""
    return next((s for s in SURFACES if s.NAME == name), None)
