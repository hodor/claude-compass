"""`compass self-update` - refresh this project's Compass install (ADR-015).

Run by the SessionStart(startup) hook, so every session begins on the current
Compass with no human action (SPEC-020; updating is mandatory, D-01 - no
opt-out, no pin). Also runnable by hand; `--force` bypasses the throttle and
the sha gate.

The check is cheap by design: a sentinel gives rapid restarts a 1-hour floor,
and `plugin.yaml`'s recorded `commit:` lets `git ls-remote` decide "current"
without cloning. Only a moved sha clones (shallow, to a temp dir, verified
before a single installed file is touched) and applies the same file set
`/compass:update` copies: agents, rules, skills, the CLI, the hooks manifest,
hook registration merged into `.claude/settings.json`, model policy applied,
`plugin.yaml` rewritten in place with unknown lines preserved.

A `source:` that resolves inside the project root is the dev repo
bootstrapping itself: the local `plugin/` dir is the canonical source there,
so it is applied directly and the network is never consulted.

Every path exits 0 and stays silent unless an update landed - SessionStart
stdout enters model context, so the single "updated X -> Y" line reaches the
session exactly when its tooling changed. Updates and failures append to
`.compass/tmp/self-update.log`; no-op checks are not logged.
"""

import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import vaultlib

SENTINEL = "tmp/.self-update-check"
LOG_FILE = "tmp/self-update.log"
RECHECK_FLOOR_SECONDS = 3600
NETWORK_TIMEOUT = 15

# Compass skills that no longer exist; their installed dirs are removed on
# update so a stale command does not linger. User-authored skills are never
# touched - only these exact names.
RETIRED_SKILLS = ["bootstrap", "taxonomize", "tree"]


def _read_plugin_yaml(vault_root):
    """Parse the flat `key: value` lines of meta/plugin.yaml into a dict.
    Returns (fields, raw_text); ({}, None) when the file is missing."""
    path = Path(vault_root) / "meta" / "plugin.yaml"
    if not path.is_file():
        return {}, None
    text = vaultlib.read_vault_text(path)
    fields = {}
    for line in text.split("\n"):
        stripped = line.strip()
        if ":" in stripped and not stripped.startswith(("#", "-", "|")):
            key, _, value = stripped.partition(":")
            if key not in fields and value.strip():
                fields[key.strip()] = value.strip()
    return fields, text


def _write_plugin_yaml(vault_root, raw, updates):
    """Rewrite known `key: value` lines in place, preserving every other line
    (notes blocks included) verbatim. A key absent from the file is inserted
    after `version:`."""
    lines = raw.split("\n")
    seen = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        key = stripped.partition(":")[0].strip()
        if key in updates and not stripped.startswith(("#", "-", "|")):
            indent = line[: len(line) - len(line.lstrip())]
            lines[i] = f"{indent}{key}: {updates[key]}"
            seen.add(key)
    missing = [k for k in updates if k not in seen]
    if missing:
        for i, line in enumerate(lines):
            if line.strip().startswith("version:"):
                indent = line[: len(line) - len(line.lstrip())]
                for offset, key in enumerate(missing, start=1):
                    lines.insert(i + offset, f"{indent}{key}: {updates[key]}")
                break
    vaultlib.write_text_lf(
        Path(vault_root) / "meta" / "plugin.yaml", "\n".join(lines)
    )


def _log(vault_root, message):
    try:
        path = Path(vault_root) / LOG_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{stamp} {message}\n")
    except OSError:
        pass


def _ls_remote(repository, timeout=NETWORK_TIMEOUT):
    """Return the remote HEAD sha, or None when unreachable (offline, no
    git, bad URL - all the same silent skip)."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", repository, "HEAD"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.split()[0]


def _clone(repository, dest):
    """Shallow-clone into dest/clone; the plugin dir is dest/clone/plugin.
    Returns False when the clone fails."""
    try:
        result = subprocess.run(
            ["git", "clone", "--depth=1", repository, str(Path(dest) / "clone")],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _plugin_version(src):
    try:
        data = json.loads(
            (Path(src) / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        return data.get("version")
    except (OSError, ValueError):
        return None


def _copy_tree_best_effort(src, dest):
    """Replace dest's contents with src's, tolerating per-file failures (a
    transiently locked file on Windows must not abort the whole apply)."""
    dest.mkdir(parents=True, exist_ok=True)
    for entry in dest.iterdir():
        try:
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        except OSError:
            pass
    for entry in Path(src).iterdir():
        if entry.name == "__pycache__":
            continue
        try:
            if entry.is_dir():
                shutil.copytree(
                    entry,
                    dest / entry.name,
                    ignore=shutil.ignore_patterns("__pycache__"),
                )
            else:
                shutil.copy2(entry, dest / entry.name)
        except OSError:
            pass


def merge_settings(project_root, manifest_path):
    """Register the hooks manifest in `.claude/settings.json`: replace only
    hook groups whose commands mention `compass`, preserve every user-owned
    group and unrelated top-level key, collapse the manifest's three
    PostToolUse entries into one `Write|Edit|MultiEdit|write|edit` matcher
    (the lowercase names are dsh's; inert under Claude Code), and strip
    the `if` field the settings schema does not carry. Idempotent."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))["hooks"]
    settings_path = Path(project_root) / ".claude" / "settings.json"
    settings = (
        json.loads(settings_path.read_text(encoding="utf-8"))
        if settings_path.is_file()
        else {}
    )
    hooks = settings.setdefault("hooks", {})

    def is_compass_group(group):
        return any("compass" in (h.get("command") or "") for h in group.get("hooks", []))

    def clean_group(group, matcher_override=None):
        cleaned = dict(group)
        if matcher_override is not None:
            cleaned["matcher"] = matcher_override
        cleaned["hooks"] = [
            {k: v for k, v in h.items() if k != "if"} for h in group.get("hooks", [])
        ]
        return cleaned

    translated = {}
    posttool = manifest.get("PostToolUse") or []
    if posttool:
        translated["PostToolUse"] = [
            clean_group(posttool[0], "Write|Edit|MultiEdit|write|edit")
        ]
    for event in manifest:
        if event != "PostToolUse":
            translated[event] = [clean_group(g) for g in manifest[event]]

    for event, new_groups in translated.items():
        kept = [g for g in hooks.get(event, []) if not is_compass_group(g)]
        hooks[event] = kept + new_groups

    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def _apply(src, project_root, apply_models):
    """Refresh every rostered host's materialization from `src` in one run
    (SPEC-006 D-03/D-04): the Claude Code file set into `.claude/`
    (mirroring /compass:update step 4-5), and for a project whose
    plugin.yaml roster lists `dsh`, the generated `.dsh/hooks.json`. One
    run, every host - two hosts of one project can never sit on different
    Compass versions."""
    src = Path(src)
    claude = Path(project_root) / ".claude"
    agents = claude / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    for f in (src / "templates" / "agents").glob("*.md"):
        shutil.copy2(f, agents / f.name)
    rules = claude / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    for f in (src / "templates" / "rules").glob("*.md"):
        shutil.copy2(f, rules / f.name)
    commands_src = src / "templates" / "commands"
    if commands_src.is_dir():
        commands = claude / "commands"
        commands.mkdir(parents=True, exist_ok=True)
        for f in commands_src.glob("*.md"):
            shutil.copy2(f, commands / f.name)
    for skill_dir in (src / "skills").iterdir():
        if not skill_dir.is_dir():
            continue
        dest = claude / "skills" / skill_dir.name
        dest.mkdir(parents=True, exist_ok=True)
        for f in skill_dir.glob("*.md"):
            shutil.copy2(f, dest / f.name)
    for retired in RETIRED_SKILLS:
        retired_dir = claude / "skills" / retired
        if retired_dir.is_dir():
            shutil.rmtree(retired_dir, ignore_errors=True)
    _copy_tree_best_effort(src / "cli", claude / "cli")
    hooks_dir = claude / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "hooks" / "hooks.json", hooks_dir / "hooks.json")
    merge_settings(project_root, hooks_dir / "hooks.json")
    import hostlib
    if "dsh" in hostlib.read_hosts(Path(project_root) / ".compass"):
        hostlib.materialize_dsh_hooks(project_root, src / "hooks" / "hooks.json")
        hostlib.materialize_dsh_skills(project_root, src / "skills")
        hostlib.materialize_dsh_bundle(project_root, src)
        hostlib.materialize_dsh_instructions(
            project_root, src / "templates" / "rules")
    # The shipped files above were just replaced wholesale; re-apply the
    # project's own additions on top of them (ADR-020).
    try:
        from commands import overlay

        overlay.apply_overlays(Path(project_root) / ".compass")
    except Exception:
        pass
    if apply_models:
        python = sys.executable or "python"
        try:
            subprocess.run(
                [python, str(claude / "cli" / "compass"), "apply-models"],
                capture_output=True,
                timeout=60,
                cwd=str(project_root),
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def _normalize_flat_specs(vault_root):
    """A spec is a file until its second member: any folder spec holding
    nothing but its own index.md flattens back to `<name>.md`, with a
    sizing correction row under the id the promotion minted. Domains and
    units keep their folders - a domain is a topic, not a spec shape."""
    flattened = 0
    try:
        records = vaultlib.scan_artifacts(vault_root)
    except Exception:
        return 0
    for record in records:
        try:
            if record["kind"] != "folder-index":
                continue
            data, error = vaultlib.parse_frontmatter(record["path"])
            if error or data.get("type") != "spec":
                continue
            folder = record["path"].parent
            members = [p for p in folder.iterdir() if p != record["path"]]
            if members:
                continue
            target = folder.parent / f"{folder.name}.md"
            if target.exists():
                continue
            text = vaultlib.read_vault_text(record["path"])
            lines = [l for l in text.split("\n") if not l.startswith("children_count:")]
            vaultlib.write_text_lf(target, "\n".join(lines))
            shutil.rmtree(folder)
            flattened += 1
            try:
                from commands import sizing as _sizing
                rel = target.relative_to(vault_root).as_posix()[:-3]
                _sizing.append_row(vault_root, {
                    "id": data.get("sizing_id") or _sizing.mint_id(vault_root),
                    "action": "correction", "shape": "folder", "subject": rel,
                    "reason": "folder held only its own index; a spec is a file until its second member",
                    "by": "agent", "at": datetime.date.today().isoformat(),
                    "volatile": [],
                })
            except Exception:
                pass
        except Exception:
            continue
    return flattened


def perform(vault_root, force=False, apply_models=True):
    """The whole check-and-update. Returns a dict with `status` and, when a
    notice belongs in context, `notice`. Never raises."""
    vault_root = Path(vault_root)
    project_root = vault_root.parent
    try:
        return _perform(vault_root, project_root, force, apply_models)
    except Exception as exc:  # session start must never depend on this
        _log(vault_root, f"error {exc}")
        return {"status": "error", "notice": None}


def _perform(vault_root, project_root, force, apply_models):
    sentinel = vault_root / SENTINEL
    if not force and sentinel.is_file():
        if time.time() - sentinel.stat().st_mtime < RECHECK_FLOOR_SECONDS:
            return {"status": "throttled", "notice": None}
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("", encoding="utf-8")

    fields, raw = _read_plugin_yaml(vault_root)
    installed = fields.get("version", "?")
    source = fields.get("source")
    repository = fields.get("repository")

    # Dev repo bootstrapping itself: the local plugin dir is canonical.
    if source:
        src_dir = Path(source)
        try:
            inside = src_dir.resolve().is_relative_to(project_root.resolve())
        except (OSError, ValueError):
            inside = False
        if inside and (src_dir / ".claude-plugin" / "plugin.json").is_file():
            new_version = _plugin_version(src_dir) or "?"
            _apply(src_dir, project_root, apply_models)
            _normalize_flat_specs(vault_root)
            notice = None
            if new_version != installed:
                if raw:
                    _write_plugin_yaml(
                        vault_root,
                        raw,
                        {
                            "version": new_version,
                            "installed_at": datetime.date.today().isoformat(),
                            "installed_mode": "auto-update",
                        },
                    )
                notice = f"Compass updated {installed} -> {new_version} (local source)"
                _log(vault_root, f"applied-local {installed} -> {new_version}")
            return {"status": "applied-local", "notice": notice}

    if not repository or raw is None:
        return {"status": "no-config", "notice": None}

    sha = _ls_remote(repository)
    if sha is None:
        return {"status": "offline", "notice": None}
    if not force and sha == fields.get("commit"):
        return {"status": "current", "notice": None}

    tmp = tempfile.mkdtemp(prefix="compass-self-update-")
    try:
        if not _clone(repository, tmp):
            _log(vault_root, f"clone-failed {repository}")
            return {"status": "clone-failed", "notice": None}
        src = Path(tmp) / "clone" / "plugin"
        new_version = _plugin_version(src)
        if new_version is None:
            _log(vault_root, f"bad-source {repository}")
            return {"status": "bad-source", "notice": None}
        _apply(src, project_root, apply_models)
        _normalize_flat_specs(vault_root)
        _write_plugin_yaml(
            vault_root,
            raw,
            {
                "version": new_version,
                "commit": sha,
                "installed_at": datetime.date.today().isoformat(),
                "installed_mode": "auto-update",
            },
        )
        _log(vault_root, f"updated {installed} -> {new_version} ({sha[:12]})")
        return {
            "status": "updated",
            "notice": f"Compass updated {installed} -> {new_version}",
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run(args):
    force = "--force" in args
    try:
        vault_root = vaultlib.find_vault_root()
    except Exception:
        return 0
    result = perform(vault_root, force=force)
    if result.get("notice"):
        sys.stdout.write(result["notice"] + "\n")
    return 0
