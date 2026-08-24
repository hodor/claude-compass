"""`compass capture-worker <opp-id>` - the detached worker's own entry
point (ADR-013 D-01/D-02).

Runs the extract-lessons pass against one opportunity in a spawned headless
`claude` child, then writes exactly one end row to the capture ledger:
`worker-finished` on a clean success or `worker-failed` naming a reason.
The row that announces the attempt (`worker-started`) belongs to the caller
(`capture-check`, TASK-092) - by the time this process exists, the spawn
already happened, so writing a started row here would be a second, redundant
announcement of an event that has already occurred.

**The worker lock.** One worker per vault: `tmp/capture-worker.lock` holds
`{"pid": int, "started_at": <iso>}`. Contention gets one bounded retry after
a short sleep, then fails with reason `lock-held` and exit 0 - never a hang,
never a spent attempt (the fallback ladder in TASK-092 respawns on the next
check without penalty). A lock older than `worker_grace_seconds` is a dead
holder's; it is broken and this run takes over. Release is owner-checked: a
lock now holding a different pid than the one that wrote it survives this
run's `finally` untouched, since deleting it would silently steal a live
worker's mutex.

**The child.** The binary resolves `COMPASS_CLAUDE_BIN` (env) -> the
`claude_bin` capture-config key -> `claude` on `PATH`. The model resolves
through `modelslib.resolve("capture-worker")` - never `inherit`. The child
runs with cwd at the project root, stdin closed (`DEVNULL`, per
[[LESSON-hook-cli-gate-stdin-on-flag]] - a headless child must never block
on a read nothing will ever satisfy), and the inherited environment plus
`COMPASS_WORKER_SESSION=1` - added, never replacing what it inherited, since
`CLAUDE_PROJECT_DIR` and auth surviving is what lets the child's own capture
hooks recognize the marker and gate themselves (ADR-013 D-11) instead of
losing the identity that makes them work at all. Both stdout and stderr are
captured and written to `.compass/tmp/worker-logs/<opp-id>.log`.

**Failure classification.** `no-headless` is a two-axis boundary, both axes
required: the binary is missing, OR the child exits nonzero inside 5 seconds
AND its stderr carries an auth-shaped token (`auth`, `login`, `credential`,
case-insensitive). A slow failure or a fast failure with no such token is a
plain `worker-failed` naming the exit code and the log's last line - the
child ran, it just did not succeed, which is a different fact from "this
host cannot run headless children at all". `no_headless_at` (a state latch)
is set on the `no-headless` path and cleared on any later run that finishes
clean, so a host that gains auth recovers on its own without a code change.

Args are hand-parsed (a single opportunity id, nothing else); the module
never raises past `run()` and never returns exit code 2 - a malformed
invocation is a refusal, not a partial attempt, and leaves no ledger row.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import capturelib
import modelslib
import vaultlib

OPPORTUNITIES_DIR = ("tmp", "capture-opportunities")
WORKER_LOGS_DIR = ("tmp", "worker-logs")

# The shape `capturelib.open_opportunity` mints: `OPP-<UTC digits>Z`. Not a
# strict timestamp parse - just narrow enough to reject path traversal and
# shell-metacharacter garbage before it ever reaches a filesystem lookup.
OPP_ID_RE = re.compile(r"^OPP-[0-9A-Za-z]+Z$")

# One short, bounded retry on lock contention - long enough to let a
# same-instant race resolve, never long enough to feel like a hang.
LOCK_RETRY_SLEEP_SECONDS = 0.05

# The no-headless classifier's fast-failure boundary (mechanism decisions,
# PLAN-010): a nonzero exit inside this many seconds is "fast".
NO_HEADLESS_FAST_SECONDS = 5

AUTH_TOKEN_RE = re.compile(r"auth|login|credential", re.IGNORECASE)

EXTRACTED_LINE_RE = re.compile(r"^extracted:.*$", re.MULTILINE)

# The worker prompt, verbatim (PLAN-010's "Mechanism decisions" section),
# with the opportunity's absolute path substituted for the plan's
# `<absolute path>` placeholder.
WORKER_PROMPT_TEMPLATE = (
    "Run the extract-lessons skill against the opportunity directory at "
    "`{opp_path}`. You are the disposable context: do not spawn subagents. "
    "Apply the skill's full contract - triggers, anti-list, dedup against "
    "the catalog, lesson-write for survivors, audit log - and close the "
    "opportunity via `compass capture-close`. Print exactly one final line "
    "in the form `extracted: <N written, N revised, N rejected> - "
    "<phrase>`."
)


def _opportunity_dir(vault_root, opp_id):
    return Path(vault_root).joinpath(*OPPORTUNITIES_DIR) / opp_id


def _lock_path(vault_root):
    return Path(vault_root) / "tmp" / "capture-worker.lock"


def _worker_log_path(vault_root, opp_id):
    return Path(vault_root).joinpath(*WORKER_LOGS_DIR) / f"{opp_id}.log"


def _valid_opp_id_shape(opp_id):
    return bool(OPP_ID_RE.match(opp_id))


def _acquire_lock(vault_root, grace_seconds):
    """Take the worker lock, or return `False` after one bounded retry when
    another run still holds it. A lock older than `grace_seconds` is a dead
    holder's and is broken and taken over in the same pass.

    Creation is atomic (`O_CREAT | O_EXCL`, the same primitive
    `capturelib.acquire_run_lock` uses): two processes racing the same
    instant can never both observe an absent lock and both write one, since
    the OS grants the exclusive create to exactly one of them."""
    path = _lock_path(vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"pid": os.getpid(), "started_at": capturelib._iso(capturelib._now())}
    ).encode("utf-8")
    for attempt in (1, 2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, payload)
            finally:
                os.close(fd)
            return True
        except FileExistsError:
            try:
                age = capturelib._now().timestamp() - path.stat().st_mtime
            except OSError:
                age = None
            if age is not None and age > grace_seconds:
                try:
                    path.unlink()
                except OSError:
                    pass
                continue  # retry the atomic create now that the stale lock is gone
            if attempt == 1:
                time.sleep(LOCK_RETRY_SLEEP_SECONDS)
                continue
            return False
        except OSError:
            return False
    return False


def _release_lock(vault_root):
    """Remove the worker lock only when it still names this process's pid.
    A lock that now names a different pid belongs to a run that started
    after this one and must survive - deleting it would steal a live
    worker's mutex."""
    path = _lock_path(vault_root)
    try:
        if not path.is_file():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(data, dict) or data.get("pid") != os.getpid():
        return
    try:
        path.unlink()
    except OSError:
        pass


def _resolve_binary(config):
    env_bin = os.environ.get("COMPASS_CLAUDE_BIN")
    if env_bin:
        return env_bin
    cfg_bin = config.get("claude_bin")
    if cfg_bin:
        return cfg_bin
    return shutil.which("claude") or "claude"


def _worker_prompt(opp_dir):
    return WORKER_PROMPT_TEMPLATE.format(opp_path=str(opp_dir.resolve()))


def _opportunity_closed(opp_path):
    try:
        record = json.loads(opp_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(record, dict) and record.get("outcome") is not None


def _extracted_line(stdout_text):
    """The last `extracted: ...` line in the child's stdout. `claude
    --output-format json` wraps its final answer in a JSON envelope; when
    stdout parses as JSON with a string `result`, that text is searched
    first, falling back to the raw stdout otherwise (a plain-text stub, or a
    harness shape that changes)."""
    text = stdout_text or ""
    candidates = [text]
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict) and isinstance(parsed.get("result"), str):
        candidates.insert(0, parsed["result"])
    for candidate in candidates:
        match = None
        for match in EXTRACTED_LINE_RE.finditer(candidate):
            pass
        if match:
            return match.group(0).strip()
    return None


def _last_log_line(stdout_text, stderr_text):
    combined = (stdout_text or "") + (stderr_text or "")
    lines = [line for line in combined.splitlines() if line.strip()]
    return lines[-1] if lines else None


def _write_worker_log(vault_root, opp_id, stdout_text, stderr_text):
    path = _worker_log_path(vault_root, opp_id)
    content = stdout_text or ""
    if stderr_text:
        if content and not content.endswith("\n"):
            content += "\n"
        content += stderr_text
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        vaultlib.write_text_lf(path, content)
    except OSError:
        pass


def _set_no_headless_latch(vault_root):
    state = capturelib.load_state(vault_root)
    state["no_headless_at"] = capturelib._iso(capturelib._now())
    capturelib.save_state(vault_root, state)


def _clear_no_headless_latch(vault_root):
    state = capturelib.load_state(vault_root)
    if state.get("no_headless_at") is not None:
        state["no_headless_at"] = None
        capturelib.save_state(vault_root, state)


def _is_no_headless(returncode, elapsed, stderr_text):
    return (
        returncode != 0
        and elapsed <= NO_HEADLESS_FAST_SECONDS
        and bool(AUTH_TOKEN_RE.search(stderr_text or ""))
    )


# The tools an extraction pass needs and nothing more: reading the vault,
# writing lessons and logs, the skills that define the pass, and the compass
# CLI through the interpreter. A headless session approves only what is
# listed here; every other tool request is refused without a human.
WORKER_ALLOWED_TOOLS = "Read,Write,Edit,Glob,Grep,Skill,Bash(python:*),Bash(python3:*)"


def _grace_seconds(config):
    return config.get(
        "worker_grace_seconds", capturelib.DEFAULT_CONFIG["worker_grace_seconds"]
    )


def _run_child(vault_root, opp_id, opp_dir, opp_path, config):
    binary = _resolve_binary(config)
    model, _effort, _source = modelslib.resolve("capture-worker")
    prompt = _worker_prompt(opp_dir)
    argv = [
        binary, "-p", prompt, "--model", model, "--output-format", "json",
        "--allowedTools", WORKER_ALLOWED_TOOLS,
    ]

    env = dict(os.environ)
    env["COMPASS_WORKER_SESSION"] = "1"

    # Bounded by the same grace window that marks a started-but-unfinished
    # row dead elsewhere in this mechanism: a child that outlives it is
    # killed and classified rather than left to block this process (and its
    # held lock) forever.
    grace_seconds = _grace_seconds(config)
    start = time.monotonic()
    try:
        result = subprocess.run(
            argv,
            cwd=str(Path(vault_root).parent),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=grace_seconds,
        )
    except OSError:
        # The binary itself could not be launched - the same signal as an
        # auth-less host, without a child process to classify at all.
        _write_worker_log(vault_root, opp_id, "", "")
        capturelib.log_event(vault_root, "worker-failed", id=opp_id, reason="no-headless")
        _set_no_headless_latch(vault_root)
        return
    except subprocess.TimeoutExpired as exc:
        stdout_text, stderr_text = exc.stdout or "", exc.stderr or ""
        _write_worker_log(vault_root, opp_id, stdout_text, stderr_text)
        capturelib.log_event(
            vault_root, "worker-failed", id=opp_id,
            reason=f"timeout after {grace_seconds}s",
            last_log_line=_last_log_line(stdout_text, stderr_text),
        )
        return

    elapsed = time.monotonic() - start
    stdout_text = result.stdout or ""
    stderr_text = result.stderr or ""
    _write_worker_log(vault_root, opp_id, stdout_text, stderr_text)

    if result.returncode == 0 and _opportunity_closed(opp_path):
        extracted = _extracted_line(stdout_text)
        fields = {"extracted": extracted} if extracted else {}
        capturelib.log_event(vault_root, "worker-finished", id=opp_id, **fields)
        _clear_no_headless_latch(vault_root)
        return

    if _is_no_headless(result.returncode, elapsed, stderr_text):
        capturelib.log_event(vault_root, "worker-failed", id=opp_id, reason="no-headless")
        _set_no_headless_latch(vault_root)
        return

    if result.returncode == 0:
        reason = "exit 0 (opportunity not closed)"
    else:
        reason = f"exit {result.returncode}"
    capturelib.log_event(
        vault_root, "worker-failed", id=opp_id,
        reason=reason, last_log_line=_last_log_line(stdout_text, stderr_text),
    )


USAGE = "usage: compass capture-worker <opp-id>"


def _run(args):
    if len(args) != 1:
        sys.stderr.write(
            f"compass capture-worker: expected exactly one opportunity id\n{USAGE}\n"
        )
        return 1
    opp_id = args[0]
    if not _valid_opp_id_shape(opp_id):
        sys.stderr.write(f"compass capture-worker: malformed opportunity id {opp_id!r}\n")
        return 1

    vault_root = vaultlib.find_vault_root()
    opp_dir = _opportunity_dir(vault_root, opp_id)
    opp_path = opp_dir / "opportunity.json"
    if not opp_path.is_file():
        sys.stderr.write(f"compass capture-worker: unknown opportunity {opp_id!r}\n")
        return 1

    config = capturelib.load_config(vault_root)
    grace_seconds = _grace_seconds(config)

    if not _acquire_lock(vault_root, grace_seconds):
        capturelib.log_event(vault_root, "worker-failed", id=opp_id, reason="lock-held")
        return 0

    try:
        _run_child(vault_root, opp_id, opp_dir, opp_path, config)
    finally:
        _release_lock(vault_root)
    return 0


def run(args):
    try:
        return _run(args)
    except Exception:
        # Best-effort like every other command on the capture hook path:
        # an internal error here must never surface as exit 2 or a crash.
        return 1
