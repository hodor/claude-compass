"""`compass retention [--set N]` - the session retention setting.

Claude Code deletes session transcripts older than `cleanupPeriodDays`
(default 30 when unset). The effective value is the first layer that sets
the key: `<project>/.claude/settings.local.json`, then
`<project>/.claude/settings.json`, then `settings.json` under
`CLAUDE_CONFIG_DIR` (default `~/.claude`). A layer whose file exists but
lacks the key falls through to the next.

Bare `compass retention` reports the effective value on the first stdout
line (an integer, or `unset`) and names the source layer on the next. With
`--set N` (an integer, 1 or more) it writes the key into the user's
`settings.json` only: every other key and its order are kept, the key is
replaced in place or appended last, and the file is replaced atomically
through a temp file. A value under 1, a non-integer, or a user settings file
that is not a JSON object is refused with a message and nothing is written.
Exit 0 on success, 1 on any refusal or failure, never 2.
"""

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import vaultlib

KEY = "cleanupPeriodDays"
SHORT_RETENTION_DAYS = 30

USAGE = "usage: compass retention [--set N]   (N: integer, 1 or more)\n"


def user_settings_path():
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(config) if config else Path.home() / ".claude"
    return base / "settings.json"


def project_root():
    """The project directory: `CLAUDE_PROJECT_DIR`, else the parent of the
    vault found from the working directory, else None."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    try:
        return vaultlib.find_vault_root().parent
    except FileNotFoundError:
        return None


def layer_paths():
    """`[(label, path)]` in precedence order, highest first."""
    layers = []
    root = project_root()
    if root is not None:
        layers.append(("local", root / ".claude" / "settings.local.json"))
        layers.append(("project", root / ".claude" / "settings.json"))
    layers.append(("user", user_settings_path()))
    return layers


def read_settings(path):
    """The parsed settings object. A missing file is `{}`. A file that is
    unreadable, not valid JSON, or not a JSON object raises ValueError."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_bytes().decode("utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path} does not parse as JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def _is_days(value):
    return isinstance(value, int) and not isinstance(value, bool)


def effective():
    """`(days, label, path, problems)`. `days` and `label` are None when no
    layer sets the key; `problems` lists the layer files that could not be
    read, which are skipped."""
    problems = []
    for label, path in layer_paths():
        try:
            data = read_settings(path)
        except ValueError as exc:
            problems.append((path, str(exc)))
            continue
        if _is_days(data.get(KEY)):
            return data[KEY], label, path, problems
    return None, None, None, problems


def _report():
    days, label, path, problems = effective()
    if days is None:
        sys.stdout.write(f"{KEY}: unset\n")
        sys.stdout.write("Claude Code keeps sessions for 30 days when this is unset.\n")
    else:
        sys.stdout.write(f"{KEY}: {days}\n")
        sys.stdout.write(f"source: {label} settings ({path})\n")
    for _path, message in problems:
        sys.stdout.write(f"skipped: {message}\n")
    return 0


def _parse_days(raw):
    if raw is None or not re.fullmatch(r"[0-9]+", raw):
        return None
    value = int(raw)
    return value if value >= 1 else None


def _indent_of(text):
    """The indent string of the first indented line, or two spaces."""
    match = re.search(r"\n([ \t]+)\S", text)
    return match.group(1) if match else "  "


def _write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".settings-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode("utf-8"))
        if path.exists():
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _set(raw):
    days = _parse_days(raw)
    if days is None:
        sys.stderr.write(f"compass retention: --set needs an integer of 1 or more, got {raw!r}\n")
        return 1
    path = user_settings_path()
    indent = "  "
    data = {}
    if path.is_file():
        try:
            data = read_settings(path)
            indent = _indent_of(path.read_bytes().decode("utf-8-sig"))
        except ValueError as exc:
            sys.stderr.write(f"compass retention: {exc}; nothing written\n")
            return 1
    data[KEY] = days
    text = json.dumps(data, indent=indent, ensure_ascii=False) + "\n"
    try:
        _write_atomic(path, text)
    except OSError as exc:
        sys.stderr.write(f"compass retention: could not write {path}: {exc}\n")
        return 1
    sys.stdout.write(f"{KEY} set to {days} in {path}\n")
    top_days, label, top_path, _problems = effective()
    if label is not None and label != "user":
        sys.stdout.write(
            f"note: the {label} settings ({top_path}) set {top_days} and outrank the user file\n"
        )
    return 0


def run(args):
    if not args:
        return _report()
    if args[0] == "--set" and len(args) <= 2:
        return _set(args[1] if len(args) == 2 else None)
    if args[0].startswith("--set=") and len(args) == 1:
        return _set(args[0][len("--set="):])
    sys.stderr.write(USAGE)
    return 1
