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

Each update records the sha256 of every agent, rule, and skill file it
installs in `.compass/meta/installed.json`. The next update compares each
installed file with that record before replacing or retiring it, and saves a
file that differs byte-for-byte under `.compass/meta/local/kept/`, naming it
in the notice. Its own local-addition block, its line endings and trailing
newlines, and the `model:` and `effort:` lines `apply-models` writes into an
agent are not differences. A project with no record counts every file as
unedited.
`--keep-edits <src>` does the same save and record without copying
anything; `/compass:update` runs it before its own copy step, and it exits
1 when `src` holds no plugin.

Every path exits 0 and stays silent unless an update landed - SessionStart
stdout enters model context, so the single "updated X -> Y" line reaches the
session exactly when its tooling changed. Updates and failures append to
`.compass/tmp/self-update.log`; no-op checks are not logged.
"""

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import vaultlib
from commands import overlay as overlay_mod

SENTINEL = "tmp/.self-update-check"
INSTALLED_FILE = "meta/installed.json"
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


# A hook command that runs Compass's CLI, installed in the project
# (`.claude/cli/compass`) or run from the plugin (`$CLAUDE_PLUGIN_ROOT/cli/compass`).
COMPASS_HOOK_COMMAND = re.compile(
    r"(?:\.claude|CLAUDE_PLUGIN_ROOT\}?)[/\\]+cli[/\\]+compass(?![\w.-])"
)


def merge_settings(project_root, manifest_path):
    """Register the hooks manifest in `.claude/settings.json`: replace only
    hook groups whose commands the manifest ships or that run Compass's CLI,
    preserve every user-owned group and unrelated top-level key, collapse
    the manifest's three
    per-tool PostToolUse entries (the groups carrying `if`) into one
    `Write|Edit|MultiEdit|write|edit` matcher
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

    shipped = {
        h.get("command")
        for groups in manifest.values()
        for g in groups
        for h in g.get("hooks", [])
    }

    def is_compass_group(group):
        return any(
            (h.get("command") or "") in shipped
            or COMPASS_HOOK_COMMAND.search(h.get("command") or "")
            for h in group.get("hooks", [])
        )

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
        # The per-tool split groups are the ones carrying `if`; every other
        # PostToolUse group registers as it stands.
        split = [g for g in posttool if any("if" in h for h in g.get("hooks", []))]
        whole = [clean_group(g) for g in posttool if g not in split]
        if split:
            whole.append(clean_group(split[0], "Write|Edit|MultiEdit|write|edit"))
        translated["PostToolUse"] = whole
    for event in manifest:
        if event != "PostToolUse":
            translated[event] = [clean_group(g) for g in manifest[event]]

    for event, new_groups in translated.items():
        kept = [g for g in hooks.get(event, []) if not is_compass_group(g)]
        hooks[event] = kept + new_groups

    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _comparable(rel, data):
    """The bytes of an installed or shipped file as a hand-edit check
    compares them: LF line endings, trailing newlines trimmed, and for an
    agent the frontmatter `model:` and `effort:` lines dropped, since
    `compass apply-models` writes those from the project's model policy.
    Bytes that are not UTF-8 compare as they are."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if rel.startswith("agents/"):
        lines = text.split("\n")
        if lines and lines[0].strip() == "---":
            for end in range(1, len(lines)):
                if lines[end].strip() == "---":
                    head = [
                        line for line in lines[1:end]
                        if not re.match(r"(model|effort):", line)
                    ]
                    lines = [lines[0]] + head + lines[end:]
                    break
        text = "\n".join(lines)
    return text.rstrip("\n").encode("utf-8")


def _fingerprint(rel, data):
    return _sha256(_comparable(rel, data))


def _shipped_files(src, claude):
    """Return [(rel, shipped path, installed path)] for every agent, rule,
    and skill file `src` ships. `rel` is the file's path under `.claude/`
    (`agents/builder.md`, `skills/sweeping/SKILL.md`)."""
    found = []
    for kind in ("agents", "rules"):
        for f in sorted((src / "templates" / kind).glob("*.md")):
            found.append((f"{kind}/{f.name}", f, claude / kind / f.name))
    for skill_dir in sorted((src / "skills").iterdir()):
        if skill_dir.is_dir():
            for f in sorted(skill_dir.glob("*.md")):
                found.append(
                    (
                        f"skills/{skill_dir.name}/{f.name}",
                        f,
                        claude / "skills" / skill_dir.name / f.name,
                    )
                )
    return found


def _read_installed(vault_root):
    """The record of what an update installed: {path under `.claude/`:
    fingerprint of the shipped bytes}. None when the vault has no readable
    record."""
    try:
        data = json.loads((vault_root / INSTALLED_FILE).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_installed(vault_root, files):
    """Record the fingerprint of each shipped file just installed. A vault
    that refuses the write leaves the older record, which can only make a
    later update save a copy it did not need."""
    record = {rel: _fingerprint(rel, shipped.read_bytes()) for rel, shipped, _ in files}
    try:
        path = vault_root / INSTALLED_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        vaultlib.write_text_lf(path, json.dumps(record, indent=2, sort_keys=True) + "\n")
    except OSError:
        pass


def _save_kept(vault_root, name, data):
    """Write `data` byte-for-byte under `meta/local/kept/` as `name`, or as
    `<stem>.2.md`, `<stem>.3.md` when an earlier copy holds the name. An
    existing copy is never replaced. Returns the name written, or None when
    an earlier copy already holds these exact bytes."""
    n = 1
    while True:
        saved = name if n == 1 else f"{name[: -len('.md')]}.{n}.md"
        path = vault_root / overlay_mod.KEPT_DIR / saved
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and path.read_bytes() == data:
            return None
        try:
            with open(path, "xb") as handle:
                handle.write(data)
            return saved
        except FileExistsError:
            n += 1


def _retired_files(claude):
    """Return [(rel, None, installed path)] for every file in an installed
    skill folder that an update removes (`RETIRED_SKILLS`)."""
    found = []
    for retired in RETIRED_SKILLS:
        for f in sorted((claude / "skills" / retired).glob("*.md")):
            found.append((f"skills/{retired}/{f.name}", None, f))
    return found


def _keep_hand_edits(vault_root, files):
    """Save every installed file whose bytes differ from the shipped text
    the last update recorded for it, before the update replaces or removes
    it. `files` lists the shipped files and the retired skill files the
    update removes. The file's own local addition block, its line endings,
    its trailing newlines and an agent's model policy are not edits. A file
    that is missing or already equals what is about to ship is not saved, a
    retired file with no recorded fingerprint cannot be judged, and a vault
    with no record has nothing to compare against, so every file counts as
    unedited. Returns the names saved; a save that fails raises, so no edit
    is replaced unsaved."""
    recorded = _read_installed(vault_root)
    if recorded is None:
        return []
    kept = []
    for rel, shipped, installed in files:
        if not installed.is_file() or (shipped is None and rel not in recorded):
            continue
        current = installed.read_bytes()
        known = {recorded.get(rel)}
        if shipped is not None:
            known.add(_fingerprint(rel, shipped.read_bytes()))
        name = overlay_mod.addition_name(rel)
        forms = overlay_mod.shipped_forms(name, current)
        if any(_fingerprint(rel, form) in known for form in forms):
            continue
        saved = _save_kept(vault_root, name, current)
        if saved is not None:
            kept.append(saved)
    return kept


def _apply(src, project_root, apply_models):
    """Refresh every effective host's materialization from `src` in one run
    (SPEC-006 D-03/D-04/D-05): the Claude Code file set into `.claude/`
    (mirroring /compass:update step 4-5), and on a machine with dsh, the
    generated dsh materializations - detected, never asked. One run, every
    host - two hosts of one project can never sit on different Compass
    versions. Installed agents, rules, and skills that were edited by hand
    are saved under `meta/local/kept/` first, and the hash of each shipped
    file is recorded in `meta/installed.json`. Returns the overlay report of
    the project's local additions (see overlay.apply_overlays) with a `kept`
    list of the saved names; a raise while applying the additions is
    reported as a `failed` entry."""
    src = Path(src)
    claude = Path(project_root) / ".claude"
    vault_root = Path(project_root) / ".compass"
    files = _shipped_files(src, claude)
    if vault_root.is_dir():
        kept = _keep_hand_edits(vault_root, files + _retired_files(claude))
    else:
        kept = []
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
    if vault_root.is_dir():
        _write_installed(vault_root, files)
    for retired in RETIRED_SKILLS:
        retired_dir = claude / "skills" / retired
        if retired_dir.is_dir():
            shutil.rmtree(retired_dir, ignore_errors=True)
    _copy_tree_best_effort(src / "cli", claude / "cli")
    review_assets = [name for name in ("obsidian", "vscode") if (src / name).is_dir()]
    for name in review_assets:
        _copy_tree_best_effort(src / name, claude / name)
    if review_assets:
        # Each review surface installs what it needs, from the files just
        # copied; best-effort, so an odd vault never fails the apply.
        try:
            import reviewlib

            reviewlib.install(Path(project_root) / ".compass", claude, automatic=True)
        except Exception:
            pass
    hooks_dir = claude / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "hooks" / "hooks.json", hooks_dir / "hooks.json")
    merge_settings(project_root, hooks_dir / "hooks.json")
    import hostlib
    if "dsh" in hostlib.effective_hosts(Path(project_root) / ".compass"):
        hostlib.materialize_dsh_hooks(project_root, src / "hooks" / "hooks.json")
        hostlib.materialize_dsh_skills(project_root, src / "skills")
        hostlib.materialize_dsh_instructions(
            project_root, src / "templates" / "rules")
        # The bundle is global and project-agnostic: generated once under
        # the harness home and copied into every profile there, so the user
        # starts dsh in any Compass project and it just works. Best-effort:
        # a missing or odd harness home must never fail the apply.
        try:
            home = hostlib.dsh_home()
            hostlib.materialize_dsh_bundle(home, src)
            hostlib.install_dsh_bundle(home)
        except OSError:
            pass
    # The shipped files above were just replaced wholesale; re-apply the
    # project's own additions on top of them (ADR-020). A raise is recorded
    # as a failure in the returned report.
    try:
        from commands import overlay

        additions = overlay.apply_overlays(Path(project_root) / ".compass")
    except Exception as exc:
        additions = {"failed": {"*": str(exc) or type(exc).__name__}}
    additions = dict(additions, kept=kept)
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
    return additions


def _one_line(name):
    """`name` with each control character (C0 and DEL) written as a visible
    backslash-x escape, so it cannot split a notice or log row."""
    return "".join(
        f"\\x{ord(c):02x}" if ord(c) < 0x20 or ord(c) == 0x7F else c
        for c in name
    )


def _additions_clause(report):
    """The `; `-prefixed notice text for an overlay report: the additions
    re-applied, those with no shipped file, a pointer to `compass doctor`
    when any failed, and the hand-edited files saved before replacement.
    Empty when there is nothing to say."""
    report = report or {}
    clause = ""
    if report.get("applied"):
        names = ", ".join(map(_one_line, report["applied"]))
        clause += "; local additions re-applied: " + names
    if report.get("orphans"):
        names = ", ".join(map(_one_line, report["orphans"]))
        clause += "; no shipped file: " + names
    if report.get("failed"):
        clause += "; local additions not applied (run compass doctor)"
    if report.get("kept"):
        names = ", ".join(map(_one_line, report["kept"]))
        clause += "; hand edits saved to meta/local/kept: " + names
    return clause


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
            additions = _apply(src_dir, project_root, apply_models)
            _normalize_flat_specs(vault_root)
            notice = None
            if new_version == installed and additions.get("kept"):
                clause = _additions_clause(additions)
                notice = f"Compass refreshed from local source{clause}"
                _log(vault_root, f"refreshed-local{clause}")
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
                clause = _additions_clause(additions)
                notice = (
                    f"Compass updated {installed} -> {new_version} (local source)"
                    + clause
                )
                _log(vault_root, f"applied-local {installed} -> {new_version}{clause}")
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
        additions = _apply(src, project_root, apply_models)
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
        clause = _additions_clause(additions)
        _log(vault_root, f"updated {installed} -> {new_version} ({sha[:12]}){clause}")
        return {
            "status": "updated",
            "notice": f"Compass updated {installed} -> {new_version}{clause}",
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def keep_edits(project_root, src):
    """Save every hand-edited agent, rule, and skill file under
    `meta/local/kept/` and record the hashes `src` ships, without copying
    anything. `/compass:update` runs this before its own copy step. Returns
    the names saved."""
    project_root = Path(project_root)
    vault_root = project_root / ".compass"
    claude = project_root / ".claude"
    files = _shipped_files(Path(src), claude)
    kept = _keep_hand_edits(vault_root, files + _retired_files(claude))
    _write_installed(vault_root, files)
    return kept


def run(args):
    if "--keep-edits" in args:
        i = args.index("--keep-edits")
        src = Path(args[i + 1]) if i + 1 < len(args) else None
        if src is None or not (src / ".claude-plugin" / "plugin.json").is_file():
            sys.stderr.write("compass self-update --keep-edits: no plugin at that path\n")
            return 1
        try:
            vault_root = vaultlib.find_vault_root()
        except Exception:
            sys.stderr.write("compass self-update --keep-edits: no vault here\n")
            return 1
        kept = keep_edits(vault_root.parent, src)
        if kept:
            sys.stdout.write(
                "hand edits saved to meta/local/kept: "
                + ", ".join(map(_one_line, kept))
                + "\n"
            )
        return 0
    force = "--force" in args
    try:
        vault_root = vaultlib.find_vault_root()
    except Exception:
        return 0
    result = perform(vault_root, force=force)
    if result.get("notice"):
        sys.stdout.write(result["notice"] + "\n")
    return 0
