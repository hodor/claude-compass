"""Refresh every Compass install on this machine from the plugin source.

For each vault found (a `.compass/meta/plugin.yaml` under the scanned roots),
copies agents, rules, skills, the CLI and the hooks manifest into the
project's `.claude/`, stamps `plugin.yaml` with the source version, applies
the model table, and runs `doctor`. Hook registration in `settings.json` is
left as-is when already present and merged in when absent.

Dry-run by default: prints what would change. `--apply` executes.
`--commit` additionally commits the Compass-owned paths in each git project
and `--push` pushes where a remote exists; a project without git, without a
remote, or whose push is rejected is reported, never forced.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "plugin"
ROOTS = [Path("F:/"), Path("C:/Users/rtgasi")]
SKIP_DIRS = {
    "node_modules", ".git", "Library", "AppData", "scoop", ".cache", "venv",
    ".venv", "__pycache__", "Intermediate", "Saved", "DerivedDataCache",
}
COMPASS_OWNED = [
    ".claude/agents", ".claude/rules", ".claude/skills", ".claude/cli",
    ".claude/hooks", ".claude/settings.json", ".compass/meta/plugin.yaml",
]


def source_version():
    manifest = json.loads((SOURCE / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return manifest["version"]


def find_vaults():
    found = []
    for root in ROOTS:
        for dirpath, dirnames, _ in os.walk(root):
            base = os.path.basename(dirpath)
            if base == ".compass":
                if (Path(dirpath) / "meta" / "plugin.yaml").is_file():
                    found.append(Path(dirpath).parent)
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if (d not in SKIP_DIRS and not d.startswith(".")) or d == ".compass"]
            if dirpath.count(os.sep) - str(root).count(os.sep) > 4:
                dirnames[:] = []
    return sorted(set(found), key=str)


def copy_tree_files(src, dst, pattern="*.md"):
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.glob(pattern):
        shutil.copy2(f, dst / f.name)


def refresh_install(project):
    claude = project / ".claude"
    copy_tree_files(SOURCE / "templates" / "agents", claude / "agents")
    copy_tree_files(SOURCE / "templates" / "rules", claude / "rules")
    for skill_dir in (SOURCE / "skills").iterdir():
        if skill_dir.is_dir():
            copy_tree_files(skill_dir, claude / "skills" / skill_dir.name)
    cli_dst = claude / "cli"
    if cli_dst.exists():
        shutil.rmtree(cli_dst)
    shutil.copytree(SOURCE / "cli", cli_dst, ignore=shutil.ignore_patterns("__pycache__", "tests", "*.pyc"))
    (claude / "hooks").mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE / "hooks" / "hooks.json", claude / "hooks" / "hooks.json")


def stamp_version(project, version, today):
    path = project / ".compass" / "meta" / "plugin.yaml"
    text = path.read_text(encoding="utf-8-sig")
    text = re.sub(r"(?m)^(\s*version:\s*)\S+", rf"\g<1>{version}", text, count=1)
    text = re.sub(r"(?m)^(\s*installed_at:\s*)\S+", rf"\g<1>{today}", text, count=1)
    text = re.sub(r"(?m)^(\s*installed_mode:\s*)\S+", r"\g<1>update", text, count=1)
    path.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def hooks_registered(project):
    settings = project / ".claude" / "settings.json"
    if not settings.is_file():
        return False
    try:
        return "hooks" in json.loads(settings.read_text(encoding="utf-8-sig"))
    except ValueError:
        return False


def run_cli(project, *args):
    return subprocess.run(
        [sys.executable, str(project / ".claude" / "cli" / "compass"), *args],
        cwd=str(project), capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
    )


def git(project, *args):
    return subprocess.run(["git", *args], cwd=str(project), capture_output=True, text=True)


def commit_and_push(project, version, push):
    if not (project / ".git").is_dir():
        return "no-git"
    git(project, "add", "--", *[p for p in COMPASS_OWNED if (project / p).exists()])
    status = git(project, "status", "--porcelain")
    if not status.stdout.strip():
        return "nothing-to-commit"
    git(project, "commit", "-q", "-m", f"Update Compass to v{version}")
    if not push:
        return "committed"
    remote = git(project, "remote")
    if not remote.stdout.strip():
        return "committed-no-remote"
    pushed = git(project, "push", "-q")
    return "pushed" if pushed.returncode == 0 else f"push-rejected: {pushed.stderr.strip()[:80]}"


def main(argv):
    apply = "--apply" in argv
    commit = "--commit" in argv
    push = "--push" in argv
    import datetime
    today = datetime.date.today().isoformat()
    version = source_version()
    vaults = find_vaults()
    print(f"source v{version}; {len(vaults)} vault(s); mode: {'apply' if apply else 'dry-run'}")
    results = []
    for project in vaults:
        if not apply:
            results.append((project, "would-update", hooks_registered(project)))
            continue
        refresh_install(project)
        stamp_version(project, version, today)
        run_cli(project, "apply-models")
        doctor = run_cli(project, "doctor")
        doctor_ok = doctor.returncode == 0
        outcome = "doctor-ok" if doctor_ok else "DOCTOR-FAIL"
        if commit:
            outcome += " / " + commit_and_push(project, version, push)
        results.append((project, outcome, hooks_registered(project)))
    for project, outcome, hooks in results:
        print(f"  {outcome:32} {'hooks' if hooks else 'NO-HOOKS':9} {project}")
    fails = [r for r in results if "DOCTOR-FAIL" in r[1] or not r[2]]
    print(f"done: {len(results)} vault(s), {len(fails)} needing attention")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
