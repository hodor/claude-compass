"""Review requests between Compass and the Compass Review Obsidian plugin.

A review is two JSON files in the Compass vault's `tmp/review/`:

- `<id>.request.json`, written here: `{"id", "file", "title", "return"}`.
  `file` is the reviewed document's path relative to the Obsidian vault
  root (the nearest ancestor holding `.obsidian/`), forward slashes.
  `return` asks the plugin to step Obsidian aside after the verdict, set
  when Obsidian did not have focus as the request was made.
- `<id>.verdict.json`, written by the plugin on a click:
  `{"id", "file", "verdict": "approved"|"changes", "notes", "at"}`.

The request is delivered by opening
`obsidian://compass-review?vault=<vault id>&request=<request path>`, the
request path relative to the Obsidian vault root. A request with no verdict
is pending; while it is pending the document belongs to the human.

A project is configured for review in Obsidian when the document sits in an
Obsidian vault that Obsidian's own vault list knows and whose
`community-plugins.json` enables the plugin with its files present.
"""

import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

PLUGIN_ID = "compass-review"
REVIEW_DIR = ("tmp", "review")
VERDICTS = ("approved", "changes")


def obsidian_config_path():
    """Obsidian's global `obsidian.json` (the vault list) for this OS.
    `COMPASS_OBSIDIAN_CONFIG` overrides it."""
    override = os.environ.get("COMPASS_OBSIDIAN_CONFIG")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "obsidian" / "obsidian.json"


def find_obsidian_vault(path):
    """The nearest ancestor directory of `path` holding `.obsidian/`, or None."""
    current = Path(path).resolve()
    if current.is_file() or not current.exists():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".obsidian").is_dir():
            return candidate
    return None


def _same_path(a, b):
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def vault_id(vault_root, config_path=None):
    """Obsidian's id for `vault_root`, or None when Obsidian does not list it
    or its vault list is missing or unreadable."""
    path = Path(config_path) if config_path else obsidian_config_path()
    try:
        vaults = json.loads(path.read_text(encoding="utf-8")).get("vaults", {})
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(vaults, dict):
        return None
    for vid, entry in vaults.items():
        if isinstance(entry, dict) and entry.get("path") and _same_path(entry["path"], vault_root):
            return vid
    return None


def plugin_state(vault_root):
    """`absent`, `off`, or `on` for the Compass Review plugin in this vault."""
    obsidian = Path(vault_root) / ".obsidian"
    if not (obsidian / "plugins" / PLUGIN_ID / "main.js").is_file():
        return "absent"
    try:
        enabled = json.loads((obsidian / "community-plugins.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "off"
    return "on" if isinstance(enabled, list) and PLUGIN_ID in enabled else "off"


def configuration(document):
    """`(vault_root, vault_id, None)` when `document` can be reviewed in
    Obsidian, else `(None, None, reason)` naming what is missing."""
    root = find_obsidian_vault(document)
    if root is None:
        return None, None, f"no Obsidian vault contains {document}"
    vid = vault_id(root)
    if vid is None:
        return None, None, f"Obsidian does not list the vault {root}; open it once in Obsidian"
    state = plugin_state(root)
    if state != "on":
        return None, None, f"the Compass Review plugin is {state} in {root}; `compass doctor` shows how to turn it on"
    return root, vid, None


def review_dir(compass_vault):
    return Path(compass_vault).joinpath(*REVIEW_DIR)


def new_id():
    return time.strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3)


def write_request(compass_vault, obsidian_root, document, title=None, step_aside=True):
    """Write a request for `document`; return `(request, request_path)`."""
    rel = Path(document).resolve().relative_to(Path(obsidian_root).resolve()).as_posix()
    rid = new_id()
    request = {"id": rid, "file": rel, "title": title, "return": bool(step_aside)}
    directory = review_dir(compass_vault)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{rid}.request.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(request, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return request, path


def read_json(path):
    """The parsed object at `path`, or None when absent or not yet a whole
    JSON object (the plugin may be mid-write)."""
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


def under_review(compass_vault, obsidian_root, target):
    """The pending request whose document is `target`, or None."""
    try:
        rel = Path(target).resolve().relative_to(Path(obsidian_root).resolve()).as_posix()
    except ValueError:
        return None
    for request in pending(compass_vault):
        if request.get("file") == rel:
            return request
    return None


def obsidian_has_focus():
    """True when the foreground window belongs to Obsidian. Windows only;
    elsewhere False, so the plugin always steps aside after a verdict."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
        handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(len(buf))
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return False
            return os.path.basename(buf.value).lower() == "obsidian.exe"
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError):
        return False


def open_uri(uri):
    """Hand `uri` to the OS handler for its scheme."""
    if sys.platform == "win32":
        os.startfile(uri)
    elif sys.platform == "darwin":
        subprocess.run(["open", uri], check=False)
    else:
        subprocess.run(["xdg-open", uri], check=False)


PLUGIN_FILES = ("main.js", "manifest.json", "styles.css")
BASE_FILES = ("review-inbox.base", "lessons.base")
ENABLE_STEPS = (
    "in Obsidian, open Settings, then Community plugins; if it shows "
    "\"Turn on community plugins\" (restricted mode), click it; then switch "
    "on Compass Review"
)


def shipped_plugin_dir():
    """The plugin files shipped beside this CLI: `plugin/obsidian/compass-review`
    in the source tree, `.claude/obsidian/compass-review` in an install."""
    return Path(__file__).resolve().parent.parent / "obsidian" / PLUGIN_ID


def shipped_bases_dir():
    """The Bases views shipped beside the plugin: `obsidian/bases/`."""
    return Path(__file__).resolve().parent.parent / "obsidian" / "bases"


def install_bases(compass_vault, src=None):
    """Copy each shipped Bases view into `compass_vault` when it is absent;
    a base the human has edited is never replaced. Returns the names written."""
    src = Path(src) if src else shipped_bases_dir()
    written = []
    for name in BASE_FILES:
        source, target = src / name, Path(compass_vault) / name
        if source.is_file() and not target.exists():
            target.write_bytes(source.read_bytes())
            written.append(name)
    return written


def install_plugin(compass_vault, src=None, bases_src=None):
    """Copy the plugin into the project's Obsidian vault - `.compass` itself
    or the project root around it, never a vault further up - list it in
    `community-plugins.json`, and add the shipped Bases views to `.compass`
    (see `install_bases`). Returns one line saying what was done. Never
    creates `.obsidian/`: a vault Obsidian has not opened is left alone.
    Other plugins in the list are kept; a list that does not parse is left
    untouched and named."""
    compass_vault = Path(compass_vault)
    root = next((d for d in (compass_vault, compass_vault.parent) if (d / ".obsidian").is_dir()), None)
    if root is None:
        return "skipped: no Obsidian vault holds this project"
    src = Path(src) if src else shipped_plugin_dir()
    missing = [n for n in PLUGIN_FILES if not (src / n).is_file()]
    if missing:
        return f"skipped: shipped plugin files missing from {src}: {', '.join(missing)}"
    dest = root / ".obsidian" / "plugins" / PLUGIN_ID
    dest.mkdir(parents=True, exist_ok=True)
    for name in PLUGIN_FILES:
        data = (src / name).read_bytes()
        target = dest / name
        if not target.is_file() or target.read_bytes() != data:
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, target)
    listing = root / ".obsidian" / "community-plugins.json"
    if listing.exists():
        try:
            enabled = json.loads(listing.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return f"installed into {dest}; {listing} does not parse, so it was not changed"
        if not isinstance(enabled, list):
            return f"installed into {dest}; {listing} is not a list, so it was not changed"
    else:
        enabled = []
    if PLUGIN_ID not in enabled:
        enabled.append(PLUGIN_ID)
        tmp = listing.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(enabled, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, listing)
    bases = install_bases(compass_vault, bases_src)
    return f"installed into {dest}" + (f"; added {', '.join(bases)}" if bases else "")

