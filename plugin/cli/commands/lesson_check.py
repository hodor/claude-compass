"""`compass lesson-check <lesson> [--base REV]` - mechanical admission check
for an edited lesson.

A lesson file is frontmatter, a body, and an optional `## Record (preserved)`
section. The body is the text between the frontmatter and that heading,
without its leading and trailing blank lines; a `Superseded:` line an archive
step appended is retired reference material and does not count toward the
cap. The Record section is exempt from the cap.

The command compares the working file against the committed version at `REV`
(default `HEAD`) and exits 1, printing one line per finding, when:

- the body has more than 5 lines (the first line over the cap is named);
- a non-blank line below the frontmatter at `REV` is no longer anywhere below
  the frontmatter of the file, so a body line dropped, or moved into the Record
  section with a character changed, is named verbatim;
- `seen` or `tags` lost an entry;
- `score` fell;
- `created` changed.

A lesson with no version at `REV` (untracked, a repository with no commit, a
revision that predates the file) is checked for the cap only. A file with no
readable frontmatter, or one that does not exist, exits 1 naming the cause.
Never exits 2.
"""

import os
import re
import subprocess
import sys

import vaultlib

BODY_CAP = 5
RECORD_HEADING = "## Record (preserved)"
SUPERSEDED_PREFIX = "Superseded:"
DEFAULT_BASE = "HEAD"

USAGE = """usage: compass lesson-check <lesson> [--base REV]

Check an edited lesson against its version at REV (default HEAD): body within
5 lines, no body or Record text lost, no seen or tags entry removed, score not
lowered, created unchanged. A lesson with no version at REV gets the cap check
only. Exit 1 on any finding, one line each.
"""


def split_lesson(text):
    """Split lesson text into (data, error, after) - the parsed frontmatter,
    a parse error or None, and the lines below the closing fence (empty when
    the frontmatter cannot be read)."""
    data, error = vaultlib.parse_frontmatter_text(text)
    if error:
        return data, error, []
    lines = text.split("\n")
    end = next(i for i in range(1, len(lines)) if lines[i].rstrip() == "---")
    return data, None, lines[end + 1:]


def body_lines(after):
    """The lines that count toward the cap: everything above the Record
    heading, minus leading and trailing blank lines and `Superseded:` lines."""
    body = []
    for line in after:
        if line.strip() == RECORD_HEADING:
            break
        body.append(line)
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return [ln for ln in body if not ln.startswith(SUPERSEDED_PREFIX)]


def content_lines(after):
    """The non-blank lines below the frontmatter, trailing whitespace
    removed, excluding the Record heading itself."""
    kept = set()
    for line in after:
        line = line.rstrip()
        if line and line != RECORD_HEADING:
            kept.add(line)
    return kept


def _git(cwd, *args):
    """Run git in `cwd`; return (returncode, stdout bytes). A missing git
    binary reads as a failed command."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        done = subprocess.run(["git", *args], cwd=cwd, env=env,
                              capture_output=True)
    except OSError:
        return 1, b""
    return done.returncode, done.stdout


def base_text(path, base):
    """The lesson text committed at `base`, or None when the repository, the
    revision or the file at that revision does not exist."""
    folder = os.path.dirname(os.path.abspath(path))
    code, out = _git(folder, "show", f"{base}:./{os.path.basename(path)}")
    if code != 0:
        return None
    return out.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def base_resolves(path, base):
    """True when `base` names a commit in the repository holding `path`."""
    folder = os.path.dirname(os.path.abspath(path))
    code, _ = _git(folder, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}")
    return code == 0


def _as_list(value):
    if isinstance(value, list):
        return [str(v) for v in value]
    return [] if value in (None, "") else [str(value)]


def _as_int(value):
    match = re.fullmatch(r"-?\d+", str(value).strip())
    return int(match.group()) if match else None


def frontmatter_findings(old, new):
    """Findings for the frontmatter fields that may grow but never shrink."""
    found = []
    for field in ("seen", "tags"):
        lost = [v for v in _as_list(old.get(field)) if v not in _as_list(new.get(field))]
        if lost:
            found.append(f"{field} lost {', '.join(lost)}")
    old_score, new_score = _as_int(old.get("score", "")), _as_int(new.get("score", ""))
    if old_score is not None and (new_score is None or new_score < old_score):
        now = "removed" if new_score is None else str(new_score)
        found.append(f"score fell from {old_score} to {now}")
    if "created" in old and str(old["created"]) != str(new.get("created", "")):
        found.append(f"created changed from {old['created']} to {new.get('created', '(removed)')}")
    return found


def check(path, base):
    """Return the list of findings for one lesson file. Raises `ValueError`
    with the cause when the file cannot be checked at all."""
    if not os.path.isfile(path):
        raise ValueError("file not found")
    text = vaultlib.read_vault_text(path)
    new_data, error, after = split_lesson(text)
    if error:
        raise ValueError(f"{error}; a lesson starts with a --- frontmatter block")

    findings = []
    body = body_lines(after)
    if len(body) > BODY_CAP:
        findings.append(
            f"body has {len(body)} lines, cap is {BODY_CAP}; first line over the cap: "
            f"{body[BODY_CAP]}")

    old_text = base_text(path, base)
    if old_text is None:
        return findings
    old_data, old_error, old_after = split_lesson(old_text)
    if old_error:
        return findings

    present = content_lines(after)
    for line in old_after:
        line = line.rstrip()
        if line and line != RECORD_HEADING and line not in present:
            findings.append(f"line present at {base} is gone: {line}")
            present.add(line)
    findings.extend(frontmatter_findings(old_data, new_data))
    return findings


def _fail(message):
    sys.stderr.write(f"compass lesson-check: {message}\n")
    return 1


def parse_args(args):
    """Return (path, base) or raise `ValueError` with the usage problem."""
    path, base, rest = None, DEFAULT_BASE, list(args)
    while rest:
        arg = rest.pop(0)
        if arg == "--base":
            if not rest:
                raise ValueError("--base needs a revision")
            base = rest.pop(0)
        elif arg.startswith("--base="):
            base = arg[len("--base="):]
        elif arg.startswith("-"):
            raise ValueError(f"unknown option {arg}")
        elif path is None:
            path = arg
        else:
            raise ValueError(f"unexpected argument {arg}")
    if path is None:
        raise ValueError("missing lesson path")
    if not base:
        raise ValueError("--base needs a revision")
    return path, base


def run(args):
    try:
        path, base = parse_args(args)
    except ValueError as exc:
        return _fail(f"{exc}\n{USAGE.rstrip()}")
    if base != DEFAULT_BASE and os.path.isfile(path) and not base_resolves(path, base):
        return _fail(f"{path}: base revision {base} does not name a commit")
    try:
        findings = check(path, base)
    except ValueError as exc:
        return _fail(f"{path}: {exc}")
    if findings:
        for finding in findings:
            sys.stderr.write(f"compass lesson-check: {path}: {finding}\n")
        return 1
    return 0
