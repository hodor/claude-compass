"""`compass doctor [--json]` - install-drift and vault-health diagnosis.

Checks the drift classes RESEARCH-lesson-capture-failure Finding 5 found
across the vault fleet: a missing `plugin.yaml`, hooks that are not actually
registered where Claude Code reads them, a `.claude/cli/` missing a module
for a command the installed `maincli.py` declares, and missing or empty
agents/skills directories. Alongside install drift, it also surfaces
unit-promotion candidates - root-level artifact groups that have outgrown
the flat vault layout - as an advisory row, since `compass unit-check` exists
but nothing else prompts a human to run it, and reconciles the detached
capture worker's ledger (ADR-013 D-10): spawn/finish/failure counts, a
started worker with no end row past its grace period, fallback-channel
firings, the last failure reason, and the no-headless latch's date when set.

Claude Code loads hooks only from a settings file's `hooks` key
(`.claude/settings.json`, `.claude/settings.local.json`, `~/.claude/settings.json`)
or a registered plugin, never from a bare `.claude/hooks/hooks.json`. The hook
check therefore parses settings files for the three registered command
entries rather than checking file existence, so an installed-but-unregistered
hooks.json is reported as the defect it is.

Each check reports OK, WARN, or FAIL with a one-line fix command. WARN never
fails the run - it flags something worth knowing but not broken (TeammateIdle
registration, whose lifecycle may not exist in every harness; unit-promotion
candidates, which are the human's call to act on; worker-ledger conditions,
which reflect the capture worker's own health rather than an install defect).
Read-only: doctor mutates no file on disk. Exit 1 on any FAIL, 0 otherwise,
never 2.
"""

import importlib.util
import json
import re
import sys

import capturelib
import vaultlib
from commands import unit_check

OK, WARN, FAIL = "OK", "WARN", "FAIL"

# Event -> substring that must appear in a registered command for that event
# to count as wired. Matched against the command text with quote characters
# stripped, so both `"...compass" sync --hook` (the shipped hooks.json shape)
# and a bare `compass sync --hook` fixture match the same way.
REQUIRED_HOOK_EVENTS = {
    "PostToolUse": "compass sync",
    "Stop": "compass capture-check",
    "SubagentStop": "compass capture-signal",
}
# Not required: teammate lifecycles may never emit SubagentStop, so its
# absence is informational, never a FAIL.
OPTIONAL_HOOK_EVENT = ("TeammateIdle", "compass capture-signal")

SETTINGS_FILENAMES = ["settings.json", "settings.local.json"]


class Check:
    def __init__(self, name, status, detail, fix=None):
        self.name = name
        self.status = status
        self.detail = detail
        self.fix = fix

    def to_dict(self):
        row = {"check": self.name, "status": self.status, "detail": self.detail}
        if self.fix:
            row["fix"] = self.fix
        return row


def _plugin_yaml_check(vault_root):
    path = vault_root / "meta" / "plugin.yaml"
    fix = "run /compass:setup to install a versioned plugin.yaml"
    if not path.is_file():
        return Check("plugin.yaml", FAIL, f"{path} is missing", fix)
    text = vaultlib.read_vault_text(path)
    match = re.search(r"^\s*version:\s*(\S.*)$", text, re.MULTILINE)
    if not match or not match.group(1).strip():
        return Check("plugin.yaml", FAIL, f"{path} has no version field", fix)
    return Check("plugin.yaml", OK, f"version {match.group(1).strip()}")


def _load_json_best_effort(path):
    """`(data, error)`. `error` is None on success; a missing file is success
    with an empty dict, since a project running without settings.local.json is
    a normal state. A present-but-unparseable file reports the error string
    rather than raising."""
    if not path.is_file():
        return {}, None
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except ValueError as exc:
        return {}, str(exc)


def _collect_commands(hooks_by_event, event_name):
    commands = []
    for group in hooks_by_event.get(event_name) or []:
        if not isinstance(group, dict):
            continue
        for entry in group.get("hooks") or []:
            if isinstance(entry, dict) and isinstance(entry.get("command"), str):
                commands.append(entry["command"])
    return commands


def _event_registered(commands_by_event, event_name, needle):
    for command in commands_by_event.get(event_name, []):
        if needle in command.replace('"', ""):
            return True
    return False


def _hooks_checks(project_root):
    """Returns a list of one or two `Check`s: the required-events check
    (OK/FAIL, drives the exit code) and, only when TeammateIdle is absent, a
    second WARN-level informational check that never fails the run."""
    settings_dir = project_root / ".claude"
    commands_by_event = {}
    malformed = []
    any_hooks_key = False

    for filename in SETTINGS_FILENAMES:
        path = settings_dir / filename
        if not path.is_file():
            continue
        data, error = _load_json_best_effort(path)
        if error:
            malformed.append(filename)
            continue
        hooks = data.get("hooks")
        if not isinstance(hooks, dict):
            continue
        any_hooks_key = True
        for event_name, _needle in list(REQUIRED_HOOK_EVENTS.items()) + [OPTIONAL_HOOK_EVENT]:
            commands_by_event.setdefault(event_name, [])
            commands_by_event[event_name].extend(_collect_commands(hooks, event_name))

    hooks_json_path = settings_dir / "hooks" / "hooks.json"
    hooks_json_exists = hooks_json_path.is_file()

    missing = [
        event_name for event_name, needle in REQUIRED_HOOK_EVENTS.items()
        if not _event_registered(commands_by_event, event_name, needle)
    ]

    fix = (
        'register hooks in .claude/settings.json under a top-level "hooks" key '
        "(a bare .claude/hooks/hooks.json is never read by Claude Code)"
    )

    if missing:
        parts = []
        if malformed:
            parts.append(f"{', '.join(malformed)} is not valid JSON")
        if hooks_json_exists and not any_hooks_key:
            parts.append(
                f"{hooks_json_path} exists but no settings file registers its hooks; "
                "Claude Code never reads a bare hooks.json"
            )
        parts.append(f"missing registration for: {', '.join(missing)}")
        return [Check("hook registration", FAIL, "; ".join(parts), fix)]

    checks = [Check("hook registration", OK, "PostToolUse, Stop, SubagentStop all registered")]
    teammate_event, teammate_needle = OPTIONAL_HOOK_EVENT
    if not _event_registered(commands_by_event, teammate_event, teammate_needle):
        checks.append(Check(
            "hook registration (TeammateIdle)", WARN,
            "TeammateIdle not registered; teammate lifecycles may not emit SubagentStop, "
            "so this is informational, not a defect",
        ))
    return checks


def _cli_completeness_check(project_root):
    maincli_path = project_root / ".claude" / "cli" / "maincli.py"
    commands_dir = project_root / ".claude" / "cli" / "commands"
    fix = "run /compass:update (or copy plugin/cli/ into .claude/cli/) to refresh the installed CLI"

    if not maincli_path.is_file():
        return Check("CLI completeness", FAIL, f"{maincli_path} is missing", fix)

    spec = importlib.util.spec_from_file_location("compass_doctor_installed_maincli", maincli_path)
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        specs = list(getattr(module, "COMMAND_SPECS", []))
    except Exception as exc:
        return Check("CLI completeness", FAIL, f"cannot read COMMAND_SPECS from {maincli_path}: {exc}", fix)

    if not specs:
        return Check("CLI completeness", FAIL, f"{maincli_path} declares no COMMAND_SPECS", fix)

    missing = []
    for name, _help in specs:
        module_path = commands_dir / (name.replace("-", "_") + ".py")
        if not module_path.is_file():
            missing.append(name)

    if missing:
        return Check(
            "CLI completeness", FAIL,
            f"{commands_dir} is missing a module for: {', '.join(missing)}",
            fix,
        )
    return Check("CLI completeness", OK, f"{len(specs)} commands, all modules present")


def _dir_check(name, path, fix):
    if not path.is_dir():
        return Check(name, FAIL, f"{path} is missing", fix)
    entries = [p for p in path.iterdir() if not p.name.startswith(".") and p.name != "__pycache__"]
    if not entries:
        return Check(name, FAIL, f"{path} is empty", fix)
    return Check(name, OK, f"{len(entries)} present")


def _lessons_catalog_check(vault_root):
    path = vault_root / "meta" / "lessons-catalog.yaml"
    if not path.is_file():
        return Check("lessons-catalog.yaml", FAIL, f"{path} is missing", "run `compass sync` to regenerate the lessons catalog")
    return Check("lessons-catalog.yaml", OK, f"{path} present")


def _overlay_check(vault_root):
    """Advisory row for project-local overlays (ADR-020): OK naming how many
    are applied, WARN when one names a target that no longer ships - an
    overlay that matches nothing must not silently do nothing."""
    try:
        from commands import overlay as overlay_mod

        report = overlay_mod.apply_overlays(vault_root, apply=False)
    except Exception as exc:
        return Check("local overlays", WARN, f"overlay scan failed: {exc}")
    live = len(report["applied"]) + len(report["skipped"])
    if report["orphans"]:
        return Check(
            "local overlays", WARN,
            f"{len(report['orphans'])} overlay(s) name an uninstalled target: "
            f"{', '.join(report['orphans'])}",
            "run `compass overlay` to list them; rename or remove the stale file",
        )
    if not live:
        return Check("local overlays", OK, "none")
    return Check("local overlays", OK, f"{live} applied")


MEASUREMENT_WINDOW_DAYS = 14


def _usage_check(vault_root):
    """Advisory row for the invocation record (ADR-017). A zero minutes into
    measurement is not a finding, so never-used commands WARN only once the
    record is at least MEASUREMENT_WINDOW_DAYS old; younger records and a
    missing file report OK with the state named. Scan failure degrades to
    WARN, never FAIL."""
    try:
        import datetime

        import maincli
        from commands import usage as usage_mod

        path = vault_root / usage_mod.RECORD_FILE
        if not path.is_file():
            return Check(
                "capability usage", OK,
                "no invocation record yet; it starts with the next compass command",
            )
        since, rows = usage_mod._parse(vaultlib.read_vault_text(path))
        dead = [
            name for name, _ in maincli.COMMAND_SPECS
            if rows.get(name, {"count": 0})["count"] == 0
        ]
        if not dead:
            return Check("capability usage", OK, "every command has recorded usage")
        try:
            age = (datetime.date.today() - datetime.date.fromisoformat(since)).days
        except (TypeError, ValueError):
            age = 0
        if age < MEASUREMENT_WINDOW_DAYS:
            return Check(
                "capability usage", OK,
                f"measuring since {since}; {len(dead)} command(s) unused so far",
            )
    except Exception as exc:
        return Check("capability usage", WARN, f"usage scan failed: {exc}")
    return Check(
        "capability usage", WARN,
        f"{len(dead)} command(s) never used in {age} days of measurement",
        "run `compass usage` for the NEVER USED list",
    )


def _unit_candidates_check(vault_root):
    """Advisory row for `unit_check.find_candidates`: WARN naming the
    candidates when any exist, OK when the vault has none. `find_candidates`
    decodes every root-level artifact, far more file-system exposure than any
    other check here, so this function keeps its own try/except - an
    unreadable artifact degrades to a WARN naming the scan failure instead of
    reaching the outer handler and turning every other row into one FAIL."""
    try:
        candidates = unit_check.find_candidates(vault_root)
    except Exception as exc:
        return Check(
            "unit-promotion candidates", WARN,
            f"unit-promotion scan failed: {exc}",
        )
    if not candidates:
        return Check("unit-promotion candidates", OK, "no unit-promotion candidates")
    labels = sorted(
        unit_check._suggested_name(vault_root / spec_rel)
        for spec_rel, _members, _types in candidates
    )
    detail = f"{len(candidates)} candidate(s): {', '.join(labels)}"
    fix = "run `compass unit-check` for the member list"
    return Check("unit-promotion candidates", WARN, detail, fix)


def _flatten(value):
    """`str(value)` with embedded newlines collapsed to spaces. Ledger rows
    are hand-editable JSON (`LedgerReadFailureTests`/`CorruptLogLineTests`
    exercise this file's tolerance of exactly that), so any field spliced
    into a one-line `detail` string - an id, a failure reason, a fallback
    channel - must not be trusted to already be single-line."""
    return " ".join(str(value).split())


def _worker_ledger_check(vault_root):
    """Advisory row reconciling `capturelib.read_log`'s worker vocabulary
    (`worker-started`, `worker-finished`, `worker-failed`, `fallback-fired`)
    against `load_config`'s `worker_grace_seconds` and the state's
    `no_headless_at` latch (ADR-013 D-10). Reports started/finished/failed
    counts, any started row whose id has no later finished or failed row and
    is aged past grace (naming the id and age), fallback firings by channel,
    the most recently logged failure reason, and the no-headless latch's date
    when set - a worker path silently latched off is exactly what this row
    exists to surface. WARNs on an unfinished spawn past grace, the latch
    being set, or the last three completed spawns all failing; OK otherwise;
    never FAIL, since the invisible machinery's own health never moves
    doctor's exit code. Kept in its own try/except like
    `_unit_candidates_check` - `read_log`, `load_config`, and `load_state` are
    each best-effort inside `capturelib` but a caller-side failure (a stubbed
    `read_log` raising, a hand-edited state file) must still degrade to WARN
    rather than reaching `_run_checks`'s outer bare `except` and collapsing
    every other row into one generic FAIL."""
    try:
        rows = capturelib.read_log(vault_root)
        config = capturelib.load_config(vault_root)
        grace = config.get("worker_grace_seconds", capturelib.DEFAULT_CONFIG["worker_grace_seconds"])
        state = capturelib.load_state(vault_root)

        started = finished = failed = 0
        open_spawns = {}
        last_failure_reason = None
        channel_counts = {}
        terminal_sequence = []

        for row in rows:
            event = row.get("event")
            row_id = row.get("id")
            if event == "worker-started":
                started += 1
                if row_id is not None:
                    open_spawns[row_id] = row
            elif event == "worker-finished":
                finished += 1
                if row_id is not None:
                    open_spawns.pop(row_id, None)
                terminal_sequence.append(("finished", None))
            elif event == "worker-failed":
                failed += 1
                if row_id is not None:
                    open_spawns.pop(row_id, None)
                last_failure_reason = row.get("reason")
                terminal_sequence.append(("failed", last_failure_reason))
            elif event == "fallback-fired":
                channel = row.get("channel")
                if channel:
                    channel = _flatten(channel)
                    channel_counts[channel] = channel_counts.get(channel, 0) + 1

        now = capturelib._now()
        unfinished = None
        for row_id, started_row in open_spawns.items():
            at = capturelib.parse_iso(started_row.get("at"))
            if at is None:
                continue
            age = (now - at).total_seconds()
            if age >= grace and (unfinished is None or age > unfinished[1]):
                unfinished = (row_id, age)

        last_three = terminal_sequence[-3:]
        last_three_failed = len(last_three) == 3 and all(kind == "failed" for kind, _reason in last_three)

        parts = [f"{started} started, {finished} finished, {failed} failed"]
        status = OK

        if unfinished:
            row_id, age = unfinished
            parts.append(f"unfinished past grace: {_flatten(row_id)} (age {int(age)}s)")
            status = WARN

        if channel_counts:
            channel_text = ", ".join(
                f"{count} {channel}" for channel, count in sorted(channel_counts.items())
            )
            parts.append(f"fallback firings: {channel_text}")

        if last_failure_reason:
            parts.append(f"last failure: {_flatten(last_failure_reason)}")

        if last_three_failed:
            parts.append(f"last three spawns all failed ({_flatten(last_failure_reason)})")
            status = WARN

        latch_at = state.get("no_headless_at")
        if latch_at:
            parsed_latch = capturelib.parse_iso(latch_at)
            date_text = parsed_latch.date().isoformat() if parsed_latch else _flatten(latch_at)
            parts.append(f"no-headless latch set since {date_text}")
            status = WARN

        detail = "; ".join(parts)
        fix = "check .compass/tmp/worker-logs/<opp-id>.log; re-run by hand with `compass capture-worker <opp-id>`"
        return Check("worker ledger", status, detail, fix if status != OK else None)
    except Exception as exc:
        return Check("worker ledger", WARN, f"ledger reconciliation failed: {_flatten(exc)}")


def _run_checks():
    try:
        vault_root = vaultlib.find_vault_root()
    except FileNotFoundError as exc:
        return [Check("vault", FAIL, str(exc), "run /compass:setup to create a .compass vault")]

    project_root = vault_root.parent
    checks = [_plugin_yaml_check(vault_root)]
    checks.extend(_hooks_checks(project_root))
    checks.append(_cli_completeness_check(project_root))
    checks.append(_dir_check(
        "agents", project_root / ".claude" / "agents",
        "run /compass:setup or /compass:update to install agent templates",
    ))
    checks.append(_dir_check(
        "skills", project_root / ".claude" / "skills",
        "run /compass:setup or /compass:update to install skills",
    ))
    checks.append(_lessons_catalog_check(vault_root))
    checks.append(_unit_candidates_check(vault_root))
    checks.append(_usage_check(vault_root))
    checks.append(_overlay_check(vault_root))
    checks.append(_worker_ledger_check(vault_root))
    return checks


def _format_table(checks):
    rows = [("status", "check", "detail")]
    for check in checks:
        rows.append((check.status, check.name, check.detail))
    widths = [max(len(row[col]) for row in rows) for col in range(3)]
    lines = [
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip()
        for row in rows
    ]
    fixes = [check for check in checks if check.fix and check.status != OK]
    if fixes:
        lines.append("")
        lines.append("fixes:")
        for check in fixes:
            lines.append(f"  {check.name}: {check.fix}")
    return "\n".join(lines)


def run(args):
    as_json = "--json" in args
    try:
        checks = _run_checks()
    except Exception as exc:  # doctor is a diagnostic; it must never crash the caller
        checks = [Check("doctor", FAIL, f"internal error: {exc}")]

    if as_json:
        sys.stdout.write(json.dumps({"checks": [check.to_dict() for check in checks]}) + "\n")
    else:
        sys.stdout.write(_format_table(checks) + "\n")

    return 1 if any(check.status == FAIL for check in checks) else 0
