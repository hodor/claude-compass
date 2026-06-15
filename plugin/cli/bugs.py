"""Local capture of Compass bugs, deduplicated by fingerprint.

A bug is recorded as one JSON file per fingerprint under
`.compass/tmp/compass-bugs/`. The same bug seen many times (across writes or
sessions) collapses to one record with an occurrence count - that is the local
half of "do not duplicate". The remote half (one GitHub issue per fingerprint)
lives in the file-bugs command. `tmp/` is gitignored, so the queue is local.
"""

import datetime
import hashlib
import json
import re
import traceback as traceback_mod
from pathlib import Path


def _bugs_dir(vault_root):
    return Path(vault_root) / "tmp" / "compass-bugs"


def _today():
    return datetime.date.today().isoformat()


def fingerprint(command, signature):
    """Stable short id for a (command, signature) pair, normalized so the same
    bug from different sessions or repos produces the same fingerprint."""
    norm = re.sub(r"\s+", " ", f"{command}|{signature}".strip().lower())
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:8]


def _write(path, record):
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")


def capture(vault_root, command, signature, detail, version=None):
    """Record a bug. `signature` drives the fingerprint (so duplicates merge);
    `detail` is the human-readable body (a message or a traceback)."""
    directory = _bugs_dir(vault_root)
    directory.mkdir(parents=True, exist_ok=True)
    fp = fingerprint(command, signature)
    path = directory / f"{fp}.json"
    if path.is_file():
        record = json.loads(path.read_text(encoding="utf-8"))
        record["count"] = record.get("count", 1) + 1
        record["last_seen"] = _today()
    else:
        record = {
            "fingerprint": fp,
            "command": command,
            "signature": signature,
            "detail": detail,
            "version": version,
            "count": 1,
            "first_seen": _today(),
            "last_seen": _today(),
            "filed": False,
            "issue_url": None,
        }
    _write(path, record)
    return fp


def capture_exception(vault_root, command, exc, version=None):
    """Capture an unexpected CLI exception. The signature is the exception type
    plus its last traceback frame, so the same crash dedups regardless of the
    incidental message."""
    frames = traceback_mod.extract_tb(exc.__traceback__)
    frame = frames[-1] if frames else None
    where = f"{Path(frame.filename).name}:{frame.lineno}" if frame else "?"
    signature = f"{type(exc).__name__} at {where}"
    return capture(vault_root, command, signature, traceback_mod.format_exc(), version)


def load_all(vault_root):
    directory = _bugs_dir(vault_root)
    if not directory.is_dir():
        return []
    records = []
    for path in sorted(directory.glob("*.json")):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return records


def mark_filed(vault_root, fp, issue_url):
    path = _bugs_dir(vault_root) / f"{fp}.json"
    if path.is_file():
        record = json.loads(path.read_text(encoding="utf-8"))
        record["filed"] = True
        record["issue_url"] = issue_url
        _write(path, record)
