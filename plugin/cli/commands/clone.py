"""`compass clone <session-id>... [--jobs N] [--timeout S] [--discard]
[--prompt-file P] [--run-id R]` - run a headless, non-persisted fork of old
Claude Code sessions so each one writes down the lessons it learned.

Each session is resumed with `claude -p --resume <id> --fork-session
--no-session-persistence`, which forks the history in memory and leaves no
session file behind. The fork runs with cwd at the project root (the main
checkout when run from a linked git worktree, where its sessions live), the
inherited environment plus `DISABLE_AUTO_COMPACT=1` and
`COMPASS_WORKER_SESSION=1`, and only the tools `Read,Glob,Grep,Write,Edit`
(`--tools` removes every other tool, MCP servers included). `--add-dir` gives
it write access to its run folder. The prompt goes to the child's stdin as
UTF-8 and stdin then closes; a Windows `.cmd` launcher cuts a multi-line
argument and every argument after it, so no prompt text is ever in argv.

Everything a run writes lives in the central run folder
`<COMPASS_HOME>/sessions/<project-key>/<run-id>/`: `run.json`, each clone's
lesson file `<session-id>.md` and, unless `--discard`, its transcript
`<session-id>.jsonl` (the child's stdout, saved line by line as it arrives).
The only file written elsewhere is one text-free row per clone appended to
`<project>/.compass/meta/clone-log.jsonl`. Transcripts under
`~/.claude/projects` are opened read-only; their hash, size and modification
time are recorded before and after each clone.

Output: `run-id: <id>` and `run-dir: <path>` first, then one
`<session-id> <status>` line per session as it ends, followed by
`original_changed` when the original transcript changed.

Statuses (the last stream line of type `result` decides):
`done`, `context-full` (an error result containing `Prompt is too long`),
`failed`, `timeout` (the whole process tree was killed), `missing` (no
transcript) and `active` (modified within 10 minutes). The last two never run.

Exit 1 for a refusal before the run folder exists (bad arguments, a dsh
binary, no vault, an existing run folder), with a message on stderr and
nothing written. Once the run folder exists the exit is 0 whatever the
clones' statuses; `run.json` is the record. Never exit 2. The command never
reads its own stdin.
"""

import concurrent.futures
import datetime
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import proctree
import sessionslib
import vaultlib
from commands import capture_worker

DEFAULT_JOBS = 3
DEFAULT_TIMEOUT = 1800
TOOLS = "Read,Glob,Grep,Write,Edit"
CONTEXT_FULL_PHRASE = "Prompt is too long"
LOG_NAME = "clone-log.jsonl"

SESSION_ID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
JOBS_RE = re.compile(r"[0-9]{1,9}")
TIMEOUT_RE = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")

# Longest wait on a child or on the pool before a stop request is rechecked.
POLL_SECONDS = 0.2
# Largest `--timeout` accepted: seven days.
MAX_TIMEOUT_SECONDS = 7 * 24 * 3600
# How long the stdout reader may outlive its child (an orphan can hold the
# pipe open) before the clone is classified from what was read.
READER_GRACE_SECONDS = 10
STDERR_TAIL_BYTES = 2000
RENAME_ATTEMPTS = 100
# How long an interrupted run waits for its killed clones to record their rows.
INTERRUPT_GRACE_SECONDS = 15

USAGE = (
    "usage: compass clone <session-id>... [--jobs N] [--timeout S] [--discard]\n"
    "                     [--prompt-file P] [--run-id R]\n"
)

DEFAULT_PROMPT = """\
You are a fork of a finished working session. The conversation above is that session's whole history. This fork exists only to record what the session learned.

First, say in one line which feature or task the session finished.

Then write down every lesson the session taught: a mistake made and corrected, a surprise in a tool or in the codebase, a plan step that proved wrong, a rule worth following next time. Leave out anything the code or the git history already shows, and anything that mattered only at one moment.

Write each lesson to {output} the moment you have it. Append it as a short entry of at most five lines that states the rule, the reason and when it applies, and mark it `process` (how to build) or `domain` (what to build). Do not wait for the end: if this session stops early, what is already in the file is what is kept.

Change no other file. Run no commands. Use Read, Glob and Grep to check a claim against the code, and use Write or Edit only on {output}.
"""


class Refusal(Exception):
    pass


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_run_id():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _parse_args(args):
    """Parse `args` into an options dict, or raise Refusal. No argparse: its
    error path exits 2."""
    opts = {
        "ids": [],
        "jobs": DEFAULT_JOBS,
        "timeout": DEFAULT_TIMEOUT,
        "discard": False,
        "prompt_file": None,
        "run_id": None,
    }
    valued = {"--jobs", "--timeout", "--prompt-file", "--run-id"}
    tokens = list(args)
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token.startswith("-") or token == "-":
            opts["ids"].append(token)
            continue
        name, equals, inline = token.partition("=")
        if name == "--discard" and not equals:
            opts["discard"] = True
            continue
        if name not in valued:
            raise Refusal(f"unknown option {token}")
        if equals:
            value = inline
        elif index < len(tokens):
            value = tokens[index]
            index += 1
        else:
            raise Refusal(f"{name} needs a value")
        if name == "--jobs":
            if not JOBS_RE.fullmatch(value) or int(value) < 1:
                raise Refusal("--jobs needs an integer of 1 or more")
            opts["jobs"] = int(value)
        elif name == "--timeout":
            seconds = float(value) if TIMEOUT_RE.fullmatch(value) else math.nan
            if not 0 < seconds <= MAX_TIMEOUT_SECONDS:
                raise Refusal(
                    f"--timeout needs a number of seconds above 0 and at most {MAX_TIMEOUT_SECONDS}"
                )
            opts["timeout"] = int(seconds) if value.isdigit() else seconds
        elif name == "--prompt-file":
            opts["prompt_file"] = value
        else:
            if not RUN_ID_RE.fullmatch(value):
                raise Refusal("--run-id must match [A-Za-z0-9][A-Za-z0-9._-]*")
            opts["run_id"] = value

    if not opts["ids"]:
        raise Refusal("no session ids given")
    for sid in opts["ids"]:
        if not SESSION_ID_RE.fullmatch(sid):
            raise Refusal(f"not a session id (8-4-4-4-12 hex digits): {sid!r}")
    seen = set()
    unique = []
    for sid in opts["ids"]:
        if sid.lower() not in seen:
            seen.add(sid.lower())
            unique.append(sid)
    opts["ids"] = unique
    return opts


def _read_prompt_template(path):
    if path is None:
        return DEFAULT_PROMPT
    try:
        return Path(path).read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise Refusal(f"cannot read prompt file {path}: {exc}")


def _capture_config(vault_root):
    """The capture config's `claude_bin` lives in `meta/capture.json`. It is
    read when present and never created, so a clone writes nothing in the
    vault but its log row."""
    try:
        data = json.loads((Path(vault_root) / "meta" / "capture.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _fingerprint(path):
    stat = os.stat(path)
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return {"sha256": digest.hexdigest(), "size": stat.st_size, "mtime": stat.st_mtime}


def _atomic_write(path, text):
    """Replace `path` with `text` through a temp file in the same folder.
    Windows refuses the rename while a reader holds the target open, so the
    rename is retried briefly."""
    path = Path(path)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(text.encode("utf-8", errors="replace"))
    for attempt in range(RENAME_ATTEMPTS):
        try:
            os.replace(temp, path)
            return
        except PermissionError:
            if attempt == RENAME_ATTEMPTS - 1:
                raise
            time.sleep(0.02)


def _append_log_row(log_path, row):
    """Append one JSON line, first closing an existing last line that lacks
    its newline so rows never run together."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row) + "\n"
    prefix = b""
    try:
        with open(log_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            if fh.tell() > 0:
                fh.seek(-1, os.SEEK_END)
                if fh.read(1) != b"\n":
                    prefix = b"\n"
    except OSError:
        pass
    with open(log_path, "ab") as fh:
        fh.write(prefix + line.encode("utf-8", errors="replace"))


class _StreamReader(threading.Thread):
    """Copies the child's stdout to the transcript one line at a time as the
    lines arrive, and remembers the last `result` record."""

    def __init__(self, stream, transcript_path):
        super().__init__(daemon=True)
        self.stream = stream
        self.transcript_path = transcript_path
        self.result = None
        self.error = None

    def run(self):
        sink = None
        try:
            if self.transcript_path is not None:
                sink = open(self.transcript_path, "wb")
            for line in self.stream:
                if sink is not None:
                    sink.write(line)
                    sink.flush()
                if b'"result"' in line:
                    self._note_result(line)
        except (OSError, ValueError) as exc:
            self.error = exc
        finally:
            if sink is not None:
                try:
                    sink.close()
                except OSError:
                    pass

    def _note_result(self, line):
        text = line.decode("utf-8", errors="replace").strip()
        if not text.startswith("{"):
            return
        try:
            record = json.loads(text)
        except ValueError:
            return
        if isinstance(record, dict) and record.get("type") == "result":
            self.result = record


class _StderrDrain(threading.Thread):
    """Reads the child's stderr to the end so a chatty child never fills the
    pipe, keeping only the tail for a failure reason."""

    def __init__(self, stream):
        super().__init__(daemon=True)
        self.stream = stream
        self.tail = b""

    def run(self):
        try:
            while True:
                chunk = self.stream.read1(65536)
                if not chunk:
                    break
                self.tail = (self.tail + chunk)[-STDERR_TAIL_BYTES:]
        except (OSError, ValueError):
            pass


def _feed_stdin(stream, data):
    try:
        stream.write(data)
    except OSError:
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _wait_for_child(proc, timeout, stop):
    """`"exited"`, `"timeout"` or `"interrupted"`: how the wait for the child
    ended. The wait polls in short slices so a stop request is seen at once."""
    deadline = time.monotonic() + timeout
    while True:
        if stop.is_set():
            return "interrupted"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "exited" if proc.poll() is not None else "timeout"
        try:
            proc.wait(timeout=min(remaining, POLL_SECONDS))
            return "exited"
        except subprocess.TimeoutExpired:
            continue


def _wait_for(futures, limit):
    """Poll until every future is done (a cancelled one counts), or `limit`
    seconds pass. Polling keeps the main thread able to receive Ctrl-C, which
    a blocking wait does not on Windows."""
    deadline = None if limit is None else time.monotonic() + limit
    while not all(future.done() for future in futures):
        if deadline is not None and time.monotonic() >= deadline:
            return
        time.sleep(POLL_SECONDS)


def _classify(reader, outcome, exit_code, timeout, stderr_tail):
    """`(status, reason, cost)` for a clone that ran."""
    result = reader.result
    cost = None
    if result is not None:
        value = result.get("total_cost_usd")
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            cost = value
    if outcome == "interrupted":
        return "failed", "interrupted", cost
    if outcome == "timeout":
        return "timeout", f"killed after {timeout:g} seconds", cost
    if result is not None:
        if not result.get("is_error"):
            return "done", None, cost
        text = result.get("result")
        text = text if isinstance(text, str) else ""
        if CONTEXT_FULL_PHRASE in text:
            return "context-full", None, cost
        return "failed", text.strip() or f"error result ({result.get('subtype')})", cost
    tail = stderr_tail.decode("utf-8", errors="replace").strip()
    reason = f"exit {exit_code} with no result line"
    if tail:
        reason += f"; stderr: {tail}"
    return "failed", reason, cost


class _Run:
    def __init__(self, opts, project, vault_root, run_id, run_folder, binary, prompt_template):
        self.opts = opts
        self.project = project
        self.vault_root = Path(vault_root)
        self.run_id = run_id
        self.run_folder = run_folder
        self.binary = binary
        self.prompt_template = prompt_template
        self.started_at = _now_iso()
        self.rows = []
        self.state_lock = threading.Lock()
        self.print_lock = threading.Lock()
        self.procs_lock = threading.Lock()
        self.live = {}
        self.stop = threading.Event()

    def _record_json(self, finished_at):
        return json.dumps(
            {
                "run_id": self.run_id,
                "project_path": str(self.project),
                "project_key": sessionslib.project_key(self.project),
                "started_at": self.started_at,
                "finished_at": finished_at,
                "discard": self.opts["discard"],
                "jobs": self.opts["jobs"],
                "timeout": self.opts["timeout"],
                "clones": self.rows,
            },
            ensure_ascii=False,
            indent=2,
        )

    def write_record(self, finished_at=None):
        with self.state_lock:
            _atomic_write(self.run_folder / "run.json", self._record_json(finished_at))

    def say(self, text):
        with self.print_lock:
            print(text, flush=True)

    def finish_clone(self, row):
        with self.state_lock:
            self.rows.append(row)
            _atomic_write(self.run_folder / "run.json", self._record_json(None))
        suffix = " original_changed" if row["original_changed"] else ""
        self.say(f"{row['session_id']} {row['status']}{suffix}")
        if row["status"] in ("done", "context-full", "timeout", "failed"):
            self._log(row)

    def _log(self, row):
        entry = {
            "event": "clone",
            "at": _now_iso(),
            "run_id": self.run_id,
            "session_id": row["session_id"],
            "status": row["status"],
            "cost_usd": row["cost_usd"],
            "kept": row["kept"],
            "transcript": row["transcript"],
        }
        try:
            with self.state_lock:
                _append_log_row(self.vault_root / "meta" / LOG_NAME, entry)
        except OSError:
            pass

    def _row(self, sid, status, reason, **fields):
        row = {
            "session_id": sid,
            "status": status,
            "reason": reason,
            "exit_code": None,
            "cost_usd": None,
            "used": None,
            "lesson_file": str(self.run_folder / f"{sid}.md"),
            "kept": False,
            "transcript": None,
            "original_before": None,
            "original_after": None,
            "original_changed": False,
        }
        row.update(fields)
        return row

    def clone_one(self, sid):
        try:
            row = self._clone(sid)
        except Exception as exc:  # one clone's failure never ends the run
            row = self._row(sid, "failed", f"{type(exc).__name__}: {exc}")
        try:
            self.finish_clone(row)
        except Exception:
            pass

    def close_interrupted(self):
        """Give every session without a row an `interrupted` failure and write
        the final record."""
        try:
            with self.state_lock:
                have = {row["session_id"] for row in self.rows}
                for sid in self.opts["ids"]:
                    if sid not in have:
                        self.rows.append(self._row(sid, "failed", "interrupted before it started"))
                _atomic_write(self.run_folder / "run.json", self._record_json(_now_iso()))
        except Exception as exc:
            sys.stderr.write(f"compass clone: {type(exc).__name__}: {exc}\n")

    def _argv(self, sid, model):
        argv = [
            self.binary, "-p",
            "--resume", sid,
            "--fork-session",
            "--no-session-persistence",
            "--verbose",
            "--output-format", "stream-json",
        ]
        if model is not None:
            argv += ["--model", model]
        argv += [
            "--tools", TOOLS,
            "--allowedTools", TOOLS,
            "--strict-mcp-config",
            "--add-dir", str(self.run_folder),
        ]
        return argv

    def stop_all(self):
        """Stop launching and kill every live child's process tree."""
        with self.procs_lock:
            self.stop.set()
            live = list(self.live.items())
        for proc, job in live:
            proctree.kill(proc, job)

    def _clone(self, sid):
        original = sessionslib.transcripts_dir(self.project) / f"{sid}.jsonl"
        if not original.is_file():
            return self._row(sid, "missing", f"no transcript at {original}")
        if sessionslib.is_active(original):
            return self._row(
                sid, "active", "modified within the last 10 minutes; the session may still be open"
            )

        before = _fingerprint(original)
        model = sessionslib.model_id(original)
        used = sessionslib.used_tokens(original)
        note = None
        if model is None:
            note = "no model found in the session; Claude Code's default model was used"

        lesson_file = self.run_folder / f"{sid}.md"
        prompt = self.prompt_template.replace("{output}", str(lesson_file)).encode("utf-8")
        transcript = None if self.opts["discard"] else self.run_folder / f"{sid}.jsonl"

        env = dict(os.environ)
        env["DISABLE_AUTO_COMPACT"] = "1"
        env["COMPASS_WORKER_SESSION"] = "1"

        try:
            with self.procs_lock:
                if self.stop.is_set():
                    return self._row(sid, "failed", "interrupted before it started")
                proc = subprocess.Popen(
                    self._argv(sid, model),
                    cwd=str(self.project),
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    **proctree.popen_kwargs(),
                )
                job = proctree.assign(proc)
                self.live[proc] = job
        except OSError as exc:
            return self._row(
                sid, "failed", f"could not start {self.binary}: {exc}",
                original_before=before, original_after=before,
            )

        reader = _StreamReader(proc.stdout, transcript)
        drain = _StderrDrain(proc.stderr)
        feeder = threading.Thread(target=_feed_stdin, args=(proc.stdin, prompt), daemon=True)
        for thread in (reader, drain, feeder):
            thread.start()

        outcome = _wait_for_child(proc, self.opts["timeout"], self.stop)
        if outcome != "exited":
            proctree.kill(proc, job)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass
        with self.procs_lock:
            self.live.pop(proc, None)
        proctree.release(job)
        reader.join(READER_GRACE_SECONDS)
        drain.join(READER_GRACE_SECONDS)
        for stream, thread in ((proc.stdout, reader), (proc.stderr, drain)):
            if not thread.is_alive():
                try:
                    stream.close()
                except OSError:
                    pass

        status, reason, cost = _classify(
            reader, outcome, proc.returncode, self.opts["timeout"], drain.tail
        )
        if note:
            reason = f"{reason}; {note}" if reason else note

        try:
            after = _fingerprint(original)
        except OSError:
            after = None
        changed = after is None or any(after[key] != before[key] for key in ("sha256", "size", "mtime"))
        return self._row(
            sid, status, reason,
            exit_code=proc.returncode,
            cost_usd=cost,
            used=used,
            kept=transcript is not None,
            transcript=str(transcript) if transcript is not None else None,
            original_before=before,
            original_after=after,
            original_changed=changed,
        )


def _refuse(message):
    sys.stderr.write(f"compass clone: {message}\n{USAGE}")
    return 1


def _start(args):
    """Validate everything and create the run folder. Raises Refusal before
    anything is written."""
    opts = _parse_args(args)
    prompt_template = _read_prompt_template(opts["prompt_file"])
    try:
        vault_root = vaultlib.find_vault_root()
    except FileNotFoundError as exc:
        raise Refusal(str(exc))
    project = sessionslib.main_checkout(vault_root.parent)

    binary, host_kind = capture_worker._resolve_binary(_capture_config(vault_root), vault_root)
    if host_kind == "dsh":
        raise Refusal("the resolved binary is dsh, which cannot resume a Claude Code session")

    if opts["run_id"] is not None:
        run_id = opts["run_id"]
        run_folder = Path(os.path.abspath(sessionslib.run_dir(project, run_id)))
        if run_folder.exists():
            raise Refusal(f"run folder already exists: {run_folder}")
    else:
        for _ in range(20):
            run_id = _default_run_id()
            run_folder = Path(os.path.abspath(sessionslib.run_dir(project, run_id)))
            if not run_folder.exists():
                break
            time.sleep(0.001)
        else:
            raise Refusal("could not pick an unused run id")

    try:
        run_folder.parent.mkdir(parents=True, exist_ok=True)
        run_folder.mkdir()
    except OSError as exc:
        raise Refusal(f"cannot create run folder {run_folder}: {exc}")
    return _Run(opts, project, vault_root, run_id, run_folder, binary, prompt_template)


def run(args):
    try:
        job = _start(args)
    except Refusal as exc:
        return _refuse(str(exc))
    except Exception as exc:
        return _refuse(f"{type(exc).__name__}: {exc}")

    job.say(f"run-id: {job.run_id}")
    job.say(f"run-dir: {job.run_folder}")
    try:
        job.write_record()
    except OSError as exc:
        sys.stderr.write(f"compass clone: cannot write run.json: {exc}\n")
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=job.opts["jobs"])
    futures = [pool.submit(job.clone_one, sid) for sid in job.opts["ids"]]
    try:
        _wait_for(futures, None)
    except KeyboardInterrupt:
        job.stop_all()
        pool.shutdown(wait=False, cancel_futures=True)
        _wait_for(futures, INTERRUPT_GRACE_SECONDS)
        job.close_interrupted()
        raise
    pool.shutdown(wait=True)
    try:
        job.write_record(_now_iso())
    except Exception as exc:  # the run folder exists: the exit stays 0
        sys.stderr.write(f"compass clone: {type(exc).__name__}: {exc}\n")
    return 0
