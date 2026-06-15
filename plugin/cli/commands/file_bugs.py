"""`compass file-bugs [--apply]` - file captured bugs as GitHub issues.

Turns the local bug queue into one GitHub issue per fingerprint, against the
Compass repository (from `.compass/meta/plugin.yaml`). Before filing, it
searches existing issues for the fingerprint and skips any already open - that
is the no-duplicates guarantee across sessions and repos. Filing is
outward-facing, so it is dry-run by default; `--apply` actually creates issues.
Requires `gh` authenticated.
"""

import json
import re
import subprocess
import sys

import bugs
import vaultlib


def _repo_slug(vault_root):
    path = vault_root / "meta" / "plugin.yaml"
    if not path.is_file():
        return None
    match = re.search(r"repository:\s*(\S+)", path.read_text(encoding="utf-8"))
    if not match:
        return None
    owner_repo = re.search(r"github\.com[/:]([^/]+)/([^/.\s]+)", match.group(1).strip().strip('"'))
    return f"{owner_repo.group(1)}/{owner_repo.group(2)}" if owner_repo else None


def _gh(args):
    """Run a gh command -> (returncode, stdout, stderr). Mockable in tests."""
    try:
        result = subprocess.run(["gh", *args], capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", "gh not found on PATH"


def _existing_issue(slug, fp):
    code, out, _ = _gh([
        "issue", "list", "-R", slug, "--search", fp,
        "--state", "all", "--json", "url,title", "--limit", "10",
    ])
    if code != 0:
        return None
    try:
        items = json.loads(out or "[]")
    except ValueError:
        return None
    for item in items:
        if fp in (item.get("title") or ""):
            return item.get("url")
    return None


def _issue_title(bug):
    return f"[compass-bug {bug['fingerprint']}] {bug['command']}: {bug['signature'][:80]}"


def _issue_body(bug):
    detail = (bug.get("detail") or "").strip()[:4000]
    return (
        "Auto-reported by `compass file-bugs`.\n\n"
        f"- fingerprint: `{bug['fingerprint']}`\n"
        f"- command: `{bug['command']}`\n"
        f"- occurrences: {bug.get('count', 1)} (first {bug.get('first_seen')}, last {bug.get('last_seen')})\n"
        f"- compass version: {bug.get('version')}\n\n"
        f"```\n{detail}\n```\n"
    )


def _create_issue(slug, bug):
    code, out, err = _gh([
        "issue", "create", "-R", slug,
        "--title", _issue_title(bug), "--body", _issue_body(bug),
    ])
    if code != 0:
        return None, (err.strip() or "gh issue create failed")
    return out.strip(), None


def run(args):
    apply = "--apply" in args
    vault_root = vaultlib.find_vault_root()
    slug = _repo_slug(vault_root)
    if not slug:
        sys.stderr.write("compass file-bugs: no repository in .compass/meta/plugin.yaml\n")
        return 1

    pending = [b for b in bugs.load_all(vault_root) if not b.get("filed")]
    if not pending:
        sys.stdout.write("compass file-bugs: no unfiled bugs\n")
        return 0

    new, dup, filed = 0, 0, 0
    for bug in pending:
        existing = _existing_issue(slug, bug["fingerprint"])
        if existing:
            bugs.mark_filed(vault_root, bug["fingerprint"], existing)
            sys.stdout.write(f"  already open {bug['fingerprint']}: {existing}\n")
            dup += 1
            continue
        if apply:
            url, err = _create_issue(slug, bug)
            if url:
                bugs.mark_filed(vault_root, bug["fingerprint"], url)
                sys.stdout.write(f"  filed {bug['fingerprint']}: {url}\n")
                filed += 1
            else:
                sys.stderr.write(f"  FAILED {bug['fingerprint']}: {err}\n")
        else:
            sys.stdout.write(f"  would file {bug['fingerprint']}: {_issue_title(bug)}\n")
            new += 1

    if apply:
        sys.stdout.write(f"compass file-bugs: filed {filed}, already-open {dup}\n")
    else:
        sys.stdout.write(
            f"compass file-bugs: {new} new to file (dry-run; pass --apply), {dup} already open\n"
        )
    return 0
