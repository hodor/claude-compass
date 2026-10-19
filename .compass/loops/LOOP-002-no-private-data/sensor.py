"""Sensor for LOOP-002-no-private-data.

Scans the content and path of every file `git ls-files` lists for private data:

- denylist: terms from a private deny-list file, one case-insensitive term per
  line, blank lines and `#` comments skipped. The file lives outside the
  repository; its path is the COMPASS_PRIVATE_DENYLIST environment variable,
  defaulting to ~/.compass/private/denylist.txt. A missing deny-list makes the
  reading invalid. A term matches when no letter or digit touches either end.
- home-path: the current user's home directory, built at run time from
  os.path.expanduser("~"), in backslash, forward-slash, Git Bash (/c/...) and
  Claude Code project-folder (C--Users-name) forms.
- session-uuid: a Claude Code session UUID inside a path: next to a path
  separator, before `.jsonl`, or inside an encoded `-<uuid>-scratchpad` folder.
- token: credential shapes (Anthropic, OpenAI-style, GitHub, Slack, AWS access
  keys, PEM private keys).

Item identity: `<posix path>:<category>:<term or pattern name>`. The matched
secret text and line numbers never appear in an item.

Prints {"valid": true, "value": N, "items": [...]} or {"valid": false, "reason": ...}.

--staged scans only the lines the staged diff adds, plus the staged paths,
for the pre-commit hook. It prints the same JSON, writes one line per item to
stderr, and exits 1 when the reading is invalid or holds any item.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DENYLIST = Path("~/.compass/private/denylist.txt")
MAX_BYTES = 5_000_000

UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
SESSION_PATTERNS = [
    re.compile(r"(?<=[\\/])" + UUID),
    re.compile(UUID + r"(?=[\\/]|\.jsonl\b)"),
    re.compile(r"-" + UUID + r"-scratchpad\b"),
]

_EDGE_L = r"(?<![A-Za-z0-9])"
_EDGE_R = r"(?![A-Za-z0-9])"
TOKEN_PATTERNS = [
    ("anthropic-key", re.compile(_EDGE_L + r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("sk-key", re.compile(_EDGE_L + r"sk-(?!ant-)[A-Za-z0-9_\-]{20,}")),
    ("github-pat-classic", re.compile(_EDGE_L + r"ghp_[A-Za-z0-9]{30,}")),
    ("github-oauth", re.compile(_EDGE_L + r"gho_[A-Za-z0-9]{30,}")),
    ("github-pat", re.compile(_EDGE_L + r"github_pat_[A-Za-z0-9_]{22,}")),
    ("slack-token", re.compile(_EDGE_L + r"xox[bp]-[A-Za-z0-9\-]{10,}")),
    ("aws-access-key", re.compile(_EDGE_L + r"AKIA[0-9A-Z]{16}" + _EDGE_R)),
    ("private-key", re.compile("-" * 5 + r"BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY" + "-" * 5)),
]


class Invalid(Exception):
    pass


def denylist_path():
    raw = os.environ.get("COMPASS_PRIVATE_DENYLIST")
    return Path(raw).expanduser() if raw else DEFAULT_DENYLIST.expanduser()


def load_denylist():
    path = denylist_path()
    if not path.is_file():
        raise Invalid(f"deny-list not found at {path}; set COMPASS_PRIVATE_DENYLIST")
    terms = []
    for line in path.read_text(encoding="utf-8").splitlines():
        term = line.strip()
        if term and not term.startswith("#"):
            terms.append(term.lower())
    return [
        (term, re.compile(_EDGE_L + re.escape(term) + _EDGE_R, re.IGNORECASE))
        for term in sorted(set(terms))
    ]


def home_patterns():
    home = os.path.expanduser("~")
    drive, rest = os.path.splitdrive(home)
    parts = [p for p in re.split(r"[\\/]+", rest) if p]
    if not parts:
        return []
    sep = r"[\\/]+"
    body = sep.join(re.escape(p) for p in parts)
    patterns = []
    if drive:
        letter = re.escape(drive.rstrip(":"))
        patterns.append(("home-drive-path", letter + r":" + sep + body))
        patterns.append(("home-gitbash-path", r"/" + letter + r"/" + body))
        patterns.append(("home-encoded-path", letter + r"--" + "-".join(re.escape(p) for p in parts)))
    else:
        patterns.append(("home-path", sep + body))
    return [(name, re.compile(rx + _EDGE_R, re.IGNORECASE)) for name, rx in patterns]


def scan_text(path, text, denylist, homes):
    found = set()
    for term, rx in denylist:
        if rx.search(text):
            found.add(f"{path}:denylist:{term}")
    for name, rx in homes:
        if rx.search(text):
            found.add(f"{path}:home-path:{name}")
    if any(rx.search(text) for rx in SESSION_PATTERNS):
        found.add(f"{path}:session-uuid:session-uuid-in-path")
    for name, rx in TOKEN_PATTERNS:
        if rx.search(text):
            found.add(f"{path}:token:{name}")
    return found


def git(*args):
    proc = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=str(ROOT), capture_output=True,
    )
    if proc.returncode != 0:
        raise Invalid(f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout.decode("utf-8", "replace")


def scan_tracked(denylist, homes):
    items = set()
    for rel in git("ls-files", "-z").split("\0"):
        if not rel:
            continue
        items |= scan_text(rel, rel, denylist, homes)
        path = ROOT / rel
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue
        items |= scan_text(rel, data.decode("utf-8", "replace"), denylist, homes)
    return items


def scan_staged(denylist, homes):
    added = {}
    current = None
    in_header = False
    diff = git("diff", "--cached", "--no-color", "--no-ext-diff", "-U0", "--diff-filter=ACMR")
    for line in diff.split("\n"):
        if line.startswith("diff --git "):
            in_header = True
            current = None
            continue
        if in_header:
            if line.startswith("+++ "):
                target = line[4:]
                current = target[2:] if target.startswith("b/") else None
                if current is not None:
                    added.setdefault(current, [])
            elif line.startswith("@@"):
                in_header = False
            continue
        if current is not None and line.startswith("+"):
            added[current].append(line[1:])
    items = set()
    for rel, lines in added.items():
        items |= scan_text(rel, rel, denylist, homes)
        items |= scan_text(rel, "\n".join(lines), denylist, homes)
    return items


def main():
    staged = "--staged" in sys.argv[1:]
    try:
        denylist = load_denylist()
        homes = home_patterns()
        items = sorted(scan_staged(denylist, homes) if staged else scan_tracked(denylist, homes))
        reading = {"valid": True, "value": len(items), "items": items}
    except Exception as exc:  # noqa: BLE001 - any failure is an invalid reading
        reading = {"valid": False, "reason": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(reading))
    if not staged:
        return 0
    if not reading["valid"]:
        print(f"privacy check could not run: {reading['reason']}", file=sys.stderr)
        return 1
    for item in reading["items"]:
        print(f"private data staged: {item}", file=sys.stderr)
    return 1 if reading["items"] else 0


if __name__ == "__main__":
    sys.exit(main())
