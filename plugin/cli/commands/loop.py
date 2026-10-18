"""`compass loop new | status | activate | pause | resume | review | run | check | baseline`
- the project's control loops.

A loop is a folder `.compass/loops/LOOP-NNN-name/` (see `looplib`). `new <name>`
writes one from `loop_templates/`: a draft index, a `loop.json` with safe caps
and no sensor command, the actuator instructions, a feedback file, a golden
pattern template and a `state.json` at `idle`. A loop is addressed as
`LOOP-NNN`.

`status [LOOP-NNN]` prints the state, last reading, unreviewed increments,
today's and lifetime spend against their budgets and the last halt reason.
`activate` sets the index `status` to `active`, after printing one `warning:`
line on stderr for each part of the loop still unfilled (see `_unfilled_parts`)
and the sensor's reading; warnings never block and change no file. `pause` and `resume` apply the
transition table through `looplib.advance`. `review <LOOP-NNN> <run-id>
accept|reject [--reason TEXT]` appends one ledger row and moves no state; a
reject reason becomes one line of `feedback.md`.

`run [--dry-run]`, `check [--blocking]` and `baseline` belong to `looprunner`,
imported when one of them is used. It provides `run_iteration(loop_dir,
dry_run)`, `check(loop_dir, blocking)` and `write_baseline(loop_dir)`, each
returning the exit code (None reads as 0).

`new` serialises on a vault-wide lock. `pause`, `resume` and `review` hold the
loop's run lock while they read and write, and refuse with "a run is in
progress" when a live run holds it.

Every failure prints a message on stderr and returns 1; the command never
exits 2.
"""

import importlib
import json
import os
import re
import secrets
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import looplib
import sensorlib
import vaultlib

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "loop_templates"

LOOP_ID = re.compile(r"^LOOP-(\d+)$")
LOOP_FOLDER_NAME = re.compile(r"^LOOP-(\d+)-(.+)$")
LOOP_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MAX_NAME_LENGTH = 100

# `new` serialises on one vault-wide lock file; a lock older than this is
# taken to be left behind by a killed process.
NEW_LOCK_STALE_SECONDS = 60
NEW_LOCK_ATTEMPTS = 200
NEW_LOCK_RETRY_SECONDS = 0.05

# A command that changes a loop takes the loop's run lock and waits this
# long for a run (or another command) to release it.
RUN_LOCK_ATTEMPTS = 30
RUN_LOCK_RETRY_SECONDS = 0.05
DEFAULT_RUN_TIMEOUT_S = 1800

ACTIVE = "active"
DECISIONS = ("accept", "reject")
RUNNER_COMMANDS = ("run", "check", "baseline")

USAGE = (
    "usage: compass loop new <name>\n"
    "       compass loop status [LOOP-NNN]\n"
    "       compass loop activate <LOOP-NNN>\n"
    "       compass loop pause <LOOP-NNN>\n"
    "       compass loop resume <LOOP-NNN>\n"
    "       compass loop review <LOOP-NNN> <run-id> accept|reject [--reason TEXT]\n"
    "       compass loop run <LOOP-NNN> [--dry-run]\n"
    "       compass loop check <LOOP-NNN> [--blocking]\n"
    "       compass loop baseline <LOOP-NNN>\n"
)


class UsageError(Exception):
    """A bad argument or an unusable loop; the message goes to stderr and the
    exit code is 1."""


def _fail(message):
    sys.stderr.write(f"compass loop: {message}\n")
    return 1


def _loops_dir():
    return vaultlib.find_vault_root() / "loops"


def _loop_folders(loops_dir):
    """Every `LOOP-NNN-name` folder directly under `loops_dir` as
    (number, name, path), in number order."""
    if not loops_dir.is_dir():
        return []
    found = []
    for entry in loops_dir.iterdir():
        match = LOOP_FOLDER_NAME.match(entry.name)
        if entry.is_dir() and match:
            found.append((int(match.group(1)), match.group(2), entry))
    return sorted(found, key=lambda item: (item[0], item[1]))


def _resolve(loop_id):
    """The folder of `LOOP-NNN`, or UsageError when the id is malformed,
    unknown or held by more than one folder."""
    match = LOOP_ID.match(loop_id or "")
    if not match:
        raise UsageError(f"{loop_id!r} is not a loop id like LOOP-001")
    number = int(match.group(1))
    folders = [path for num, _name, path in _loop_folders(_loops_dir()) if num == number]
    if not folders:
        raise UsageError(f"no loop {loop_id}")
    if len(folders) > 1:
        names = ", ".join(path.name for path in folders)
        raise UsageError(f"{loop_id} is ambiguous: {names}")
    return folders[0]


def _loop_label(folder):
    match = LOOP_FOLDER_NAME.match(folder.name)
    return f"LOOP-{match.group(1)} {match.group(2)}"


def _single_id(args, command):
    if len(args) != 1:
        raise UsageError(f"{command} needs exactly one <LOOP-NNN>")
    return args[0]


# --- new ---------------------------------------------------------------


def _render(name, number, text):
    """`text` with the template placeholders filled in."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for key, value in (("{{name}}", name), ("{{id}}", f"LOOP-{number:03d}"), ("{{date}}", today)):
        text = text.replace(key, value)
    return text


def _stage_template(stage, name, number):
    """Write every file of the template tree under `stage`, LF-terminated."""
    for source in sorted(TEMPLATE_DIR.rglob("*")):
        if not source.is_file():
            continue
        target = stage / source.relative_to(TEMPLATE_DIR)
        target.parent.mkdir(parents=True, exist_ok=True)
        text = source.read_bytes().decode("utf-8")
        vaultlib.write_text_lf(target, _render(name, number, text))


@contextmanager
def _new_lock(created):
    """Hold the vault-wide lock that serialises numbering and the rename of a
    new loop folder. An exclusive-create lock file under `tmp/loops/`, retried
    briefly; one older than NEW_LOCK_STALE_SECONDS is removed. The
    directories the lock had to create are appended to `created`."""
    lock_dir = vaultlib.find_vault_root() / "tmp" / "loops"
    lock = lock_dir / "new.lock"
    created.extend(d for d in (lock_dir, lock_dir.parent) if not d.exists())
    lock_dir.mkdir(parents=True, exist_ok=True)
    for _attempt in range(NEW_LOCK_ATTEMPTS):
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileNotFoundError:
            lock_dir.mkdir(parents=True, exist_ok=True)
        except (FileExistsError, PermissionError):
            try:
                age = time.time() - lock.stat().st_mtime
            except FileNotFoundError:
                continue
            except OSError:
                age = 0
            if age > NEW_LOCK_STALE_SECONDS:
                lock.unlink(missing_ok=True)
                continue
            time.sleep(NEW_LOCK_RETRY_SECONDS)
    else:
        raise UsageError("another `compass loop new` is running; try again")
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def _require_name_free(loops_dir, name):
    """The existing loop folders as (number, name, path), when none is named
    `name`; otherwise a UsageError. Reads the disk and writes nothing."""
    existing = _loop_folders(loops_dir)
    for _number, existing_name, path in existing:
        if existing_name == name:
            raise UsageError(f"a loop named {name} already exists: {path.name}")
    return existing


def _remove_empty_dirs(directories):
    """Remove each directory in `directories` that is empty, deepest first."""
    for directory in sorted(directories, key=lambda d: len(d.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass


def _new(args):
    if len(args) != 1:
        raise UsageError("new needs exactly one <name>")
    name = args[0]
    if not LOOP_NAME.fullmatch(name) or len(name) > MAX_NAME_LENGTH:
        raise UsageError(
            f"{name[:40]!r} is not a loop name: use lowercase letters, digits and "
            f"single hyphens, at most {MAX_NAME_LENGTH} characters"
        )
    if not TEMPLATE_DIR.is_dir():
        raise UsageError(f"loop templates missing at {TEMPLATE_DIR}")
    loops_dir = _loops_dir()
    _require_name_free(loops_dir, name)
    stage = loops_dir / f".new-{os.getpid()}-{secrets.token_hex(4)}.tmp"
    created = []
    try:
        with _new_lock(created):
            existing = _require_name_free(loops_dir, name)
            number = max((num for num, _n, _p in existing), default=0) + 1
            folder = loops_dir / f"LOOP-{number:03d}-{name}"
            _stage_template(stage, name, number)
            stage.rename(folder)
    except OSError as exc:
        _remove_empty_dirs(created)
        raise UsageError(f"could not create loop {name}: {exc}") from exc
    except UsageError:
        _remove_empty_dirs(created)
        raise
    finally:
        if stage.exists():
            _remove_tree(stage)
    print(f"created {folder.name}")
    print(f"next: set sensor_command in {folder / 'loop.json'}, fill in {folder / 'index.md'}")
    return 0


def _remove_tree(directory):
    """Remove a scratch folder this command made, best effort."""
    for path in sorted(directory.rglob("*"), reverse=True):
        try:
            path.rmdir() if path.is_dir() else path.unlink()
        except OSError:
            pass
    try:
        directory.rmdir()
    except OSError:
        pass


# --- status ------------------------------------------------------------


def _money(value):
    """`value` with up to six decimals and no trailing zeros, or `?` when it
    cannot be shown as a number."""
    try:
        text = f"{round(value, 6):.6f}".rstrip("0").rstrip(".")
    except (OverflowError, ValueError, TypeError):
        return "?"
    return text or "0"


def _read_json_object(path):
    """The JSON object in `path`, or {} when it is missing or unreadable."""
    try:
        data = json.loads(path.read_bytes().decode("utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _last_halt_reason(rows):
    for row in reversed(rows):
        if row.get("type") == "transition" and row.get("to") == "halted":
            reason = row.get("reason")
            return reason if isinstance(reason, str) and reason else "no reason recorded"
    return None


def _last_reading(rows):
    """The `reading_after` of the most recent run row, or its `reading_before`
    when the run ended at a gate before re-sensing, or None."""
    for row in reversed(rows):
        if row.get("type") == "run":
            after = row.get("reading_after")
            return after if after is not None else row.get("reading_before")
    return None


def _reading_text(reading):
    """A reading as `value V, N items`, or `none` when the run took none."""
    if not isinstance(reading, dict):
        return "none"
    return f"value {reading.get('value')}, {reading.get('items_count')} items"


def _budget(definition, key):
    value = definition.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "?"
    return _money(value)


def _status_lines(folder, now):
    state_error = None
    try:
        state = looplib.read_state(folder)
    except looplib.StateError as exc:
        state, state_error = {"state": "damaged"}, str(exc)
    rows, skipped = looplib.read_ledger(folder)
    definition = _read_json_object(folder / looplib.DEFINITION_FILE)
    try:
        index_data, _error = vaultlib.parse_frontmatter(folder / "index.md")
    except (OSError, ValueError):
        index_data = None
    index_status = (index_data or {}).get("status", "unknown")
    counters = looplib.fold(rows)
    reading = _last_reading(rows)
    halt = _last_halt_reason(rows)
    lines = [
        f"{_loop_label(folder)}  state: {state['state']}  index status: {index_status}",
        f"  last reading: {_reading_text(reading)}",
        f"  wip: {counters['wip']} of {_budget(definition, 'wip_limit')} unreviewed increments",
        f"  spend today: {_money(sensorlib.spend_today(rows, now))} of {_budget(definition, 'daily_budget_usd')} usd",
        f"  spend lifetime: {_money(sensorlib.spend_lifetime(rows))} of {_budget(definition, 'total_budget_usd')} usd",
        f"  last halt: {halt if halt is not None else 'none'}",
    ]
    if state_error:
        lines.append(f"  state file: {state_error}")
    if skipped:
        lines.append(f"  ledger: {len(skipped)} unreadable line(s) skipped")
    return lines


def _status(args):
    if len(args) > 1:
        raise UsageError("status takes at most one <LOOP-NNN>")
    if args:
        folders = [_resolve(args[0])]
    else:
        folders = [path for _n, _name, path in _loop_folders(_loops_dir())]
        if not folders:
            print("no loops")
            return 0
    now = datetime.now(timezone.utc)
    for index, folder in enumerate(folders):
        if index:
            print()
        try:
            print("\n".join(_status_lines(folder, now)))
        except (OSError, ValueError) as exc:
            print(f"{_loop_label(folder)}  damaged: {exc}")
    return 0


# --- activate, pause, resume -------------------------------------------


def _with_status(text, status):
    """`text` with the frontmatter `status` field set to `status`, or None
    when the text has no closed frontmatter block or no `status` field. Lines
    outside the field are untouched."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            break
    else:
        return None
    for position in range(1, end):
        if lines[position].startswith("status:"):
            ending = lines[position][len(lines[position].rstrip("\r\n")):]
            lines[position] = f"status: {status}{ending}"
            return "".join(lines)
    return None


STEP_HEADINGS = (
    ("end state", re.compile(r"^##[ \t]+Step[ \t]+0\b")),
    ("sensor", re.compile(r"^##[ \t]+Step[ \t]+1\b")),
)
DEFAULT_SENSOR_TIMEOUT_S = 120


def _one_line(text):
    return " ".join(str(text).split())


def _section_body(text, heading):
    """The whitespace-normalised body under the first `## ` heading matching
    the `heading` pattern, up to the next `## ` heading, or None when no
    heading matches."""
    lines = text.splitlines()
    for start, line in enumerate(lines):
        if heading.match(line):
            break
    else:
        return None
    body = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        body.append(line)
    return " ".join(" ".join(body).split())


def _template_text(relative, folder):
    """The template file `relative` rendered for the loop in `folder`, with
    LF line endings."""
    match = LOOP_FOLDER_NAME.match(folder.name)
    text = (TEMPLATE_DIR / relative).read_bytes().decode("utf-8")
    return _render(match.group(2), int(match.group(1)), text).replace("\r\n", "\n")


def _unfilled_parts(folder, index_text):
    """One message for each part of the loop still holding template text: a
    `loop.json` that fails `looplib.load_definition`, an `actuator.md` equal to
    the template, and a missing, empty or template-text end state (step 0) or
    sensor (step 1) section."""
    problems = []
    try:
        looplib.load_definition(folder)
    except looplib.DefinitionError as exc:
        problems.append(_one_line(exc))
    try:
        actuator = (folder / "actuator.md").read_bytes().decode("utf-8-sig")
    except OSError:
        problems.append("actuator.md is missing")
    else:
        if actuator.replace("\r\n", "\n") == _template_text("actuator.md", folder):
            problems.append("actuator.md is still the template")
    template_index = _template_text("index.md", folder)
    for label, heading in STEP_HEADINGS:
        body = _section_body(index_text, heading)
        if body is None:
            problems.append(f"index.md has no {label} section")
        elif not body or body == _section_body(template_index, heading):
            problems.append(f"index.md {label} section is still the template text")
    return problems


def _sensor_notes(folder):
    """A (warning, line) pair from running the loop's sensor command once: the
    warning when the reading is invalid, the reading line when valid, both
    None when `loop.json` names no sensor command or no `looprunner` exists."""
    definition = _read_json_object(folder / looplib.DEFINITION_FILE)
    command = definition.get("sensor_command")
    if not isinstance(command, str) or not command.strip():
        return None, None
    sense = _runner_function("_sense")
    if sense is None:
        return None, None
    timeout = definition.get("sensor_timeout_s")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        definition["sensor_timeout_s"] = DEFAULT_SENSOR_TIMEOUT_S
    reading = sense(definition, folder.parents[2])
    if not reading.valid:
        return f"sensor reading is invalid: {_one_line(reading.reason)}", None
    return None, f"sensor reading: value {_money(reading.value)}, {len(reading.items)} items"


def _activate(args):
    folder = _resolve(_single_id(args, "activate"))
    index = folder / "index.md"
    try:
        text = vaultlib.read_vault_text(index)
    except OSError as exc:
        raise UsageError(f"cannot read {index}: {exc}") from exc
    updated = _with_status(text, ACTIVE)
    if updated is None:
        raise UsageError(f"{index} has no closed frontmatter with a status field")
    warnings = _unfilled_parts(folder, text)
    warning, reading_line = _sensor_notes(folder)
    if warning:
        warnings.append(warning)
    for message in warnings:
        sys.stderr.write(f"compass loop: warning: {message}\n")
    if reading_line:
        print(reading_line)
    if updated != text:
        vaultlib.write_text_lf(index, updated)
    print(f"{_loop_label(folder)} is active")
    return 0


def _run_timeout(folder):
    """The loop's wall-clock run limit from `loop.json`, or the default when
    the file does not give a usable one."""
    value = _read_json_object(folder / looplib.DEFINITION_FILE).get("timeout_s")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
        return DEFAULT_RUN_TIMEOUT_S
    return value


@contextmanager
def _loop_lock(folder):
    """Hold the loop's run lock while a command changes its state, ledger or
    feedback, so a runner and the command never interleave. A lock left by a
    dead run is cleared; a live one is waited for briefly, then refused."""
    match = LOOP_FOLDER_NAME.match(folder.name)
    lock = vaultlib.find_vault_root() / "tmp" / "loops" / f"LOOP-{match.group(1)}.lock"
    timeout = _run_timeout(folder)
    for _attempt in range(RUN_LOCK_ATTEMPTS):
        try:
            looplib.acquire_lock(lock, timeout)
            break
        except (looplib.LockHeld, PermissionError):
            try:
                stale = looplib.is_stale(lock, timeout)
                if stale:
                    looplib.release_lock(lock)
            except PermissionError:
                stale = False
            if not stale:
                time.sleep(RUN_LOCK_RETRY_SECONDS)
    else:
        raise UsageError(f"{_loop_label(folder)}: a run is in progress")
    try:
        yield
    finally:
        _release_run_lock(lock)


def _release_run_lock(lock):
    """Remove the run lock, retrying while Windows reports the file busy
    because another process is reading it."""
    for attempt in range(RUN_LOCK_ATTEMPTS):
        try:
            looplib.release_lock(lock)
            return
        except PermissionError:
            if attempt == RUN_LOCK_ATTEMPTS - 1:
                raise
            time.sleep(RUN_LOCK_RETRY_SECONDS)


def _advance(args, command, reason):
    folder = _resolve(_single_id(args, command))
    try:
        with _loop_lock(folder):
            new = looplib.advance(folder, command, reason)
    except looplib.TransitionError as exc:
        raise UsageError(f"{_loop_label(folder)}: {exc}") from exc
    except looplib.StateError as exc:
        raise UsageError(str(exc)) from exc
    print(f"{_loop_label(folder)} is {new}")
    return 0


def _pause(args):
    return _advance(args, "pause", "paused by the human")


def _resume(args):
    return _advance(args, "resume", "resumed by the human")


# --- review ------------------------------------------------------------


def _parse_review(args):
    """(loop id, run id, decision, reason) from the arguments."""
    positional, reason = [], None
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--reason":
            index += 1
            if index >= len(args):
                raise UsageError("--reason needs a value")
            reason = args[index]
        elif arg.startswith("--reason="):
            reason = arg[len("--reason="):]
        elif arg.startswith("--"):
            raise UsageError(f"unknown option {arg[:40]!r}")
        else:
            positional.append(arg)
        index += 1
    if len(positional) != 3:
        raise UsageError("review needs <LOOP-NNN> <run-id> accept|reject")
    loop_id, run_id, decision = positional
    if decision not in DECISIONS:
        raise UsageError(f"the decision must be accept or reject, got {decision[:40]!r}")
    return loop_id, run_id, decision, reason


def _require_unreviewed(rows, run_id):
    """Raise a UsageError when a review row already names `run_id`."""
    if any(r.get("type") == "review" and r.get("run_id") == run_id for r in rows):
        raise UsageError(f"run {run_id!r} is already reviewed")


def _require_verified_run(rows, run_id):
    """Return when `run_id` names a run that reached `verifying`; otherwise
    raise a UsageError saying why not."""
    matches = [r for r in rows if r.get("type") == "run" and r.get("run_id") == run_id]
    if not matches or not run_id:
        raise UsageError(f"no run {run_id!r} in the ledger")
    outcome = matches[-1].get("outcome")
    if outcome not in ("helpful", "neutral", "harmful"):
        raise UsageError(
            f"run {run_id!r} ended {outcome!r} and left no increment to review"
        )


def _append_guidance(folder, line):
    """Add `line` as a bullet at the end of `feedback.md`. Returns the file's
    earlier text, or None when the file did not exist, for `_restore_guidance`."""
    path = folder / "feedback.md"
    try:
        earlier = vaultlib.read_vault_text(path)
    except FileNotFoundError:
        earlier = None
    text = "# Feedback\n\n## Guidance\n" if earlier is None else earlier
    if not text.endswith("\n"):
        text += "\n"
    vaultlib.write_text_lf(path, f"{text}- {line}\n")
    return earlier


def _restore_guidance(folder, earlier):
    """Put `feedback.md` back as `_append_guidance` found it."""
    path = folder / "feedback.md"
    if earlier is None:
        path.unlink(missing_ok=True)
    else:
        vaultlib.write_text_lf(path, earlier)


def _review(args):
    loop_id, run_id, decision, reason = _parse_review(args)
    folder = _resolve(loop_id)
    line = " ".join(reason.split()) if reason is not None else ""
    row = {"type": "review", "run_id": run_id, "decision": decision}
    if line:
        row["reason"] = line
    with _loop_lock(folder):
        rows, _skipped = looplib.read_ledger(folder)
        _require_verified_run(rows, run_id)
        _require_unreviewed(rows, run_id)
        earlier, guided = None, False
        if decision == "reject" and line:
            earlier, guided = _append_guidance(folder, line), True
        try:
            looplib.append_ledger(folder, row)
        except BaseException:
            if guided:
                _restore_guidance(folder, earlier)
            raise
    print(f"{_loop_label(folder)}: run {run_id} {decision}ed")
    return 0


# --- run, check, baseline ----------------------------------------------


def _runner_flags(args, flag):
    """(loop id, flag present) from `<LOOP-NNN> [flag]`."""
    positional = [a for a in args if a != flag]
    if len(positional) != 1 or any(a.startswith("--") for a in positional):
        raise UsageError(f"needs exactly one <LOOP-NNN> and at most {flag}")
    return positional[0], flag in args


def _runner_function(name):
    """The `looprunner` function `name`, or None when no `looprunner` module
    exists (a different missing module is a real error and propagates)."""
    try:
        module = importlib.import_module("looprunner")
    except ModuleNotFoundError as exc:
        if exc.name == "looprunner":
            return None
        raise
    function = getattr(module, name, None)
    if function is None:
        raise UsageError(f"looprunner has no {name}")
    return function


def _exit_code(result):
    """The exit code a runner function returned: None is 0, and 2 (the code
    that blocks a hook's write) is reported as 1."""
    code = 0 if result is None else int(result)
    return 1 if code == 2 else code


def _run_runner(command, args):
    flag = {"run": "--dry-run", "check": "--blocking", "baseline": None}[command]
    if flag is None:
        loop_id, flagged = _single_id(args, command), False
    else:
        loop_id, flagged = _runner_flags(args, flag)
    folder = _resolve(loop_id)
    name = {"run": "run_iteration", "check": "check", "baseline": "write_baseline"}[command]
    function = _runner_function(name)
    if function is None:
        return _fail(f"{command}: not implemented yet")
    if command == "run":
        return _exit_code(function(folder, dry_run=flagged))
    if command == "check":
        return _exit_code(function(folder, blocking=flagged))
    return _exit_code(function(folder))


COMMANDS = {
    "new": _new,
    "status": _status,
    "activate": _activate,
    "pause": _pause,
    "resume": _resume,
    "review": _review,
}


def run(args):
    if not args or (args[0] not in COMMANDS and args[0] not in RUNNER_COMMANDS):
        sys.stderr.write(USAGE)
        return 1
    command, rest = args[0], args[1:]
    try:
        if command in RUNNER_COMMANDS:
            return _run_runner(command, rest)
        return COMMANDS[command](rest)
    except UsageError as exc:
        return _fail(str(exc))
    except (OSError, ValueError, looplib.LockHeld, TimeoutError) as exc:
        return _fail(str(exc))
