"""The control-loop runner: one iteration of a loop, its dry run, and the
dampener (`write_baseline`, `check`).

    run_iteration(loop_dir, dry_run=False, *, now=None) -> int
    write_baseline(loop_dir) -> int
    check(loop_dir, blocking=False) -> int

`loop_dir` is `<project>/.compass/loops/LOOP-NNN-name/`. Each function prints
for the human and returns an exit code: 0 for an iteration that completed
(verified or failed actuator run, throttled, done, dry run), 1 for a refusal,
a halted ending or an unreadable input. Nothing returns 2.

An iteration walks the state machine of `looplib` through `looplib.advance`:
lock, recover, sense, gate (budget, then work in progress), control, assemble
the prompt, actuate, re-sense, judge, record, unlock. Every real iteration
appends one `run` row to the ledger, written before the transition that ends
the run so a cost is never lost to a crash between the two. The run lock is
held from before the first transition to after the last.

A dry run follows the same path with the state held in memory: it senses,
gates and selects, prints the prompt the actuator would receive and stops.
It takes no lock, launches nothing and writes no file.

The actuator is `claude -p --output-format json` with the caps from
`loop.json`; the prompt arrives on stdin and the environment carries
`COMPASS_WORKER_SESSION=1`. Each iteration is a fresh session. The prompt
holds the actuator's instructions, the golden patterns, the selected work and
the feedback, and none of the budget or cap numbers.

`loop.json`, `state.json`, `ledger.jsonl`, `baseline.json` and, for a loop
with a `judge`, its rules file are fingerprinted before the actuator starts.
When any differs afterwards the run is recorded with its real cost and the
loop halts with `controls-changed`.

A loop with a `judge` object runs the judge `runs` times after the
deterministic re-sense, each a fresh headless session launched like the
actuator with the judge's own model and caps, `--allowedTools Read,Glob,Grep`
and the rules file plus a checklist as the prompt. The votes of the valid runs
become the `judge` record of the run row, and the judge's spend joins the
row's `cost_usd`. The gate budgets, and a crash charges, the actuator plus
`runs` judge budgets. The next run's prompt carries the kept findings of the
last judged run after the controller's pick. The reading is advisory: it
reaches no transition and no exit code.
"""

import functools
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import looplib
import proctree
import sensorlib
import vaultlib
from commands import capture_worker

BASELINE_FILE = "baseline.json"
CONTROL_FILES = ("loop.json", "state.json", "ledger.jsonl", BASELINE_FILE)
STARTABLE = ("idle", "throttled")
NOT_RUNNABLE = ("paused", "halted", "done")

# Tries at taking the run lock, a short pause apart, before the run refuses.
LOCK_ATTEMPTS = 5
LOCK_RETRY_SECONDS = 0.05

# A judge answer keeps at most this many findings in the ledger and the next
# prompt.
MAX_KEPT_FINDINGS = 200

# A directory-walk snapshot stops after this many entries and carries the
# key PARTIAL.
SNAPSHOT_ENTRIES = 200_000
PARTIAL = "<partial>"

# Seconds allowed to `git ls-files` when the project is snapshotted around
# the judge.
SNAPSHOT_SECONDS = 120

# Spend sums are floats; a budget met exactly must still fit.
BUDGET_EPSILON = 1e-9


class _Refusal(Exception):
    """A run that stops before changing anything on disk."""


class _Process:
    """What a launched command left behind."""

    def __init__(self, returncode=None, stdout=b"", stderr=b"", timed_out=False, error=None):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.error = error


def _write(stream, text):
    """Write `text` to `stream`; characters the stream's encoding cannot
    hold are replaced rather than raised."""
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        stream.write(text.encode(encoding, errors="replace").decode(encoding))


def _say(message):
    _write(sys.stdout, message + "\n")


def _complain(message):
    _write(sys.stderr, f"compass loop: {message}\n")


def _exit_code(function):
    """Make a public entry point return 1 with a message for any failure it
    did not handle itself, never a traceback."""

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception as exc:
            _complain(f"{type(exc).__name__}: {exc}")
            return 1

    return wrapper


def _utc(moment):
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _split_command(command):
    """The argv of a command string. A quoted token keeps its spaces; on
    Windows a backslash stays an ordinary character."""
    if os.name != "nt":
        return shlex.split(command)
    tokens = shlex.split(command, posix=False)
    return [
        t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'" else t
        for t in tokens
    ]


def _run_process(argv, cwd, timeout, stdin_bytes=None, env=None):
    """Run `argv` from `cwd` and return a `_Process`. The child roots its own
    process tree (see proctree), so a run past `timeout` seconds, or an
    interrupt, kills it together with everything it started."""
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL if stdin_bytes is None else subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **proctree.popen_kwargs(),
        )
    except (OSError, ValueError, TypeError, IndexError) as exc:
        name = argv[0] if argv else "(empty command)"
        return _Process(error=f"could not start {name}: {exc}")
    job = proctree.assign(proc)
    timed_out = False
    try:
        try:
            stdout, stderr = proc.communicate(input=stdin_bytes, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            proctree.kill(proc, job)
            try:
                stdout, stderr = proc.communicate(timeout=proctree.KILL_WAIT_SECONDS)
            except (subprocess.TimeoutExpired, OSError, ValueError):
                stdout = stderr = b""
        except (OSError, ValueError) as exc:
            proctree.kill(proc, job)
            try:
                proc.wait(timeout=proctree.KILL_WAIT_SECONDS)
            except (subprocess.TimeoutExpired, OSError):
                pass
            return _Process(error=f"could not read the output of {argv[0]}: {exc}")
        except BaseException:
            proctree.kill(proc, job)
            raise
    finally:
        proctree.release(job)
    return _Process(returncode=proc.returncode, stdout=stdout or b"", stderr=stderr or b"",
                    timed_out=timed_out)


def _text(data):
    return data.decode("utf-8", errors="replace")


def _read_text(path):
    """The file's text with LF line endings, a leading byte order mark
    dropped; "" when the file is absent."""
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        return ""
    return raw.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def _number(value):
    return repr(value) if isinstance(value, float) else str(value)


def _reading_summary(reading):
    if reading is None or not reading.valid:
        return None
    return {"value": reading.value, "items_count": len(reading.items)}


def _control_files(definition):
    """The files that bind the actuator: the loop's own and, with a judge,
    its rules file."""
    names = list(CONTROL_FILES)
    judge = definition.get(looplib.JUDGE_KEY)
    if judge:
        names.append(Path(looplib.judge_rules_file(judge)).as_posix())
    return names


def _fingerprints(loop_dir, definition):
    prints = {}
    for name in _control_files(definition):
        path = Path(loop_dir) / name
        try:
            if path.is_dir():
                prints[name] = "<directory>"
            else:
                prints[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        except FileNotFoundError:
            prints[name] = None
        except OSError:
            prints[name] = "<unreadable>"
    return prints


def _git_snapshot(project):
    """`{path: (size, mtime_ns) or None}` for every file git reports modified
    or untracked, outside `.compass/tmp`; None when the project is not a git
    work tree or git cannot be run."""
    proc = _run_process(
        ["git", "ls-files", "-m", "-o", "--exclude-standard", "-z"], project, SNAPSHOT_SECONDS
    )
    if proc.error or proc.timed_out or proc.returncode != 0:
        return None
    snapshot = {}
    for name in _text(proc.stdout).split("\0"):
        if not name or name.startswith(".compass/tmp/"):
            continue
        try:
            stat = (Path(project) / name).stat()
            snapshot[name] = (stat.st_size, stat.st_mtime_ns)
        except OSError:
            snapshot[name] = None
    return snapshot


def _walk_snapshot(project, loop_dir):
    """`{relative path: (size, mtime_ns)}` for the files under the project,
    walked in sorted order and skipping `.git`, `.compass/tmp` and the loop's
    own ledger and state files. After SNAPSHOT_ENTRIES entries the walk stops
    and the snapshot carries the key PARTIAL."""
    project, loop_dir = Path(project), Path(loop_dir)
    skip_dirs = {project / ".git", project / ".compass" / "tmp"}
    skip_files = {loop_dir / name for name in ("ledger.jsonl", "ledger.jsonl.lock", "state.json")}
    snapshot = {}
    for root, dirs, files in os.walk(project):
        dirs[:] = sorted(d for d in dirs if Path(root, d) not in skip_dirs)
        for name in sorted(files):
            path = Path(root, name)
            if path in skip_files or (path.parent == loop_dir and name.startswith(".state.json.")):
                continue
            if len(snapshot) >= SNAPSHOT_ENTRIES:
                snapshot[PARTIAL] = True
                return snapshot
            key = path.relative_to(project).as_posix()
            try:
                stat = path.stat()
                snapshot[key] = (stat.st_size, stat.st_mtime_ns)
            except OSError:
                snapshot[key] = None
    return snapshot


def _project_snapshot(project, loop_dir):
    """A snapshot of the project's files that tells a later snapshot what
    changed: git's modified and untracked files, or a directory walk when the
    project is not a git work tree."""
    snapshot = _git_snapshot(project)
    return snapshot if snapshot is not None else _walk_snapshot(project, loop_dir)


def _new_run_id():
    return "RUN-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _loop_paths(loop_dir):
    loop_dir = Path(os.path.abspath(loop_dir))
    return loop_dir, loop_dir.parents[1], loop_dir.parents[2]


def _loop_id(loop_dir):
    match = re.match(r"LOOP-[0-9]+", Path(loop_dir).name)
    return match.group(0) if match else Path(loop_dir).name


def _sense(definition, project):
    try:
        argv = _split_command(definition["sensor_command"])
    except ValueError as exc:
        return sensorlib.Reading(valid=False, reason=f"cannot parse sensor_command: {exc}")
    return sensorlib.run_sensor(argv, project, definition["sensor_timeout_s"])


def _command_text(command, project, timeout):
    """`(stdout text, None)` of a loop-owned command, or `(None, reason)`."""
    try:
        argv = _split_command(command)
    except ValueError as exc:
        return None, f"cannot parse the command: {exc}"
    proc = _run_process(argv, project, timeout)
    if proc.error:
        return None, proc.error
    if proc.timed_out:
        return None, f"timed out after {timeout:g} seconds"
    if proc.returncode != 0:
        return None, f"exit {proc.returncode}"
    return _text(proc.stdout), None


def _status(loop_dir):
    data, _error = vaultlib.parse_frontmatter_text(_read_text(Path(loop_dir) / "index.md"))
    return data.get("status")


def _section(title, body):
    return f"## {title}\n\n{body}" if body else f"## {title}"


JUDGE_CHECKLIST = (
    "## Checklist\n\n"
    "Go rule by rule. For each rule, go over every file it applies to and check "
    "the file against the rule, reading with Read, Glob and Grep.\n\n"
    "Answer with one JSON line per violation, in this shape and nothing else:\n\n"
    '{"rule": "<rule id>", "file": "<path relative to the project root>", '
    '"line": <line number>}\n\n'
    "Write no prose, no code fences and no summary. When no rule is violated, "
    "answer with nothing.\n"
)
JUDGE_TOOLS = "Read,Glob,Grep"


def _judge_prompt(rules_text):
    """The judge prompt: the rules file verbatim, then the checklist."""
    return rules_text.strip() + "\n\n" + JUDGE_CHECKLIST


def _kept_findings(rows):
    """`(findings, total)`: the kept findings, at most MAX_KEPT_FINDINGS, of
    the last run row that carries a `judge` record, and how many the judge
    kept in all."""
    for row in reversed(rows):
        record = row.get("judge") if row.get("type") == "run" else None
        if isinstance(record, dict):
            kept = record.get("kept")
            kept = [k for k in kept if isinstance(k, dict)] if isinstance(kept, list) else []
            total = record.get("kept_total")
            if not isinstance(total, int) or isinstance(total, bool) or total < len(kept):
                total = len(kept)
            return kept[:MAX_KEPT_FINDINGS], total
    return [], 0


def _findings_block(findings, total):
    """The findings as a fenced block, one ASCII-escaped JSON object per line,
    so no file name can open a heading or a section of the prompt."""
    heading = "Judge findings from the last run (advisory)"
    if total > len(findings):
        heading += f", {len(findings)} of {total}"
    lines = [json.dumps(
        {"rule": k.get("rule"), "file": k.get("file"), "line": k.get("line")}, ensure_ascii=True
    ) for k in findings]
    return f"{heading}:\n\n```\n" + "\n".join(lines) + "\n```"


def _assemble_prompt(loop_dir, item, findings=(), total=0):
    """The actuator prompt: instructions, golden patterns, selected work
    (followed by the judge's kept findings, when there are any), feedback."""
    loop_dir = Path(loop_dir)
    golden = [
        _read_text(path).strip()
        for path in sorted((loop_dir / "golden").glob("*.md"))
        if path.is_file()
    ]
    parts = [
        _read_text(loop_dir / "actuator.md").strip(),
        _section("Golden patterns", "\n\n".join(g for g in golden if g)),
        _section(
            "Selected work (controller output)",
            f"{item}\n\n{_findings_block(findings, total)}" if findings else item,
        ),
        _section("Feedback", _read_text(loop_dir / "feedback.md").strip()),
    ]
    return "\n\n".join(parts) + "\n"


class _Run:
    """One iteration over a loop folder."""

    def __init__(self, loop_dir, definition, dry_run, now):
        self.dir, self.vault, self.project = _loop_paths(loop_dir)
        self.loop_id = _loop_id(self.dir)
        self.defn = definition
        self.dry = dry_run
        self.started = _utc(now) if now is not None else datetime.now(timezone.utc)
        self.run_id = _new_run_id()
        self.lock_path = self.vault / "tmp" / "loops" / f"{self.loop_id}.lock"
        self.locked = False
        self.state = looplib.read_state(self.dir)["state"]
        if self.dry and self.state in looplib.WORKING:
            self.state = "idle"
        self.row = {
            "type": "run",
            "run_id": self.run_id,
            "reading_before": None,
            "reading_after": None,
        }
        self.binary = None

    # ---- lock and recovery ------------------------------------------------

    def acquire(self):
        """Take the run lock, then recover a loop a crashed run left in a
        working state. The lock comes first so that exactly one process
        recovers. A lock held by a live run, or a state another command moved
        on in the meantime, is a refusal.

        A lock found stale is taken over; when the takeover loses to another
        process the acquire is retried a few times, so the loser meets the
        winner's live lock and refuses on it."""
        timeout_s = self.defn["timeout_s"]
        for attempt in range(LOCK_ATTEMPTS):
            try:
                looplib.acquire_lock(self.lock_path, timeout_s)
                break
            except looplib.LockHeld as exc:
                if looplib.take_stale_lock(self.lock_path, timeout_s):
                    continue
                if attempt == LOCK_ATTEMPTS - 1:
                    raise _Refusal(str(exc)) from None
                time.sleep(LOCK_RETRY_SECONDS)
        else:
            raise _Refusal(f"run lock {self.lock_path} stays contended")
        self.locked = True
        looplib.recover(self.dir, self.lock_path, self.defn, lock_held=True)
        self.state = looplib.read_state(self.dir)["state"]
        if self.state not in STARTABLE:
            raise _Refusal(f"loop is {self.state}, not idle or throttled")

    def release(self):
        if self.locked:
            looplib.release_lock(self.lock_path)
            self.locked = False

    # ---- transitions and records -------------------------------------------

    def step(self, event, reason):
        """Apply `event`: on disk and in the ledger, or in memory for a dry
        run."""
        if self.dry:
            self.state = looplib.transition(self.state, event)
        else:
            self.state = looplib.advance(self.dir, event, reason)

    def mark(self, **fields):
        """Record `fields` in the state file so a crash-recovery names the
        run and its item."""
        if not self.dry:
            looplib.write_state(self.dir, {**looplib.read_state(self.dir), **fields})

    def end(self, outcome, event, reason, code, **fields):
        """Close the iteration: the run row, then the ending transition."""
        row = {"cost_usd": 0.0, **self.row, "outcome": outcome, "reason": reason, **fields}
        if self.dry:
            to = looplib.transition(self.state, event)
            _say(f"dry run: {self.loop_id} would end {to} ({event}): {reason}")
            return code
        row["ts"] = self.started.isoformat(timespec="seconds")
        looplib.append_ledger(self.dir, row)
        self.step(event, reason)
        state = looplib.read_state(self.dir)
        looplib.write_state(
            self.dir, {k: v for k, v in state.items() if k not in ("run_id", "item")}
        )
        _say(f"{self.loop_id} {self.run_id}: {outcome}, now {self.state}: {reason}")
        return code

    def ledger_rows(self):
        return looplib.read_ledger(self.dir)[0]

    # ---- the iteration -----------------------------------------------------

    def execute(self):
        defn = self.defn
        self.mark(run_id=self.run_id)
        self.step("start", f"run {self.run_id}")

        before = _sense(defn, self.project)
        if not before.valid:
            return self.end("halted", "invalid-reading", before.reason, 1)
        self.row["reading_before"] = _reading_summary(before)
        on_target = (
            before.value <= defn["target"]
            if defn["direction"] == "down"
            else before.value >= defn["target"]
        )
        if on_target:
            return self.end(
                "done", "at-set-point",
                f"reading {before.value:g} is at the set point {defn['target']:g}", 0,
            )
        self.step("off-set-point", f"reading {before.value:g}")

        rows = self.ledger_rows()
        counters = looplib.fold(rows)
        gate = self.gate(rows, counters)
        if gate is not None:
            outcome, event, reason, code = gate
            return self.end(outcome, event, reason, code)
        self.step("clear", "budget and work in progress allow a run")

        item, why = self.select(before, counters)
        if item is None:
            return self.end("halted", "nothing-selected", why, 1)
        self.row["item"] = item
        findings, total = _kept_findings(rows) if defn.get(looplib.JUDGE_KEY) else ([], 0)
        prompt = _assemble_prompt(self.dir, item, findings, total)
        if self.dry:
            self.step("selected", f"selected {item}")
            _write(sys.stdout, prompt)
            return 0
        self.mark(item=item)
        self.step("selected", f"selected {item}")
        return self.actuate_and_judge(before, prompt, item)

    def gate(self, rows, counters):
        """`(outcome, event, reason, code)` for a run the budget or the work
        in progress stops, or None."""
        defn = self.defn
        run_budget = looplib.run_budget(defn)
        lifetime = sensorlib.spend_lifetime(rows)
        if lifetime + run_budget > defn["total_budget_usd"] + BUDGET_EPSILON:
            return (
                "halted", "total-budget-spent",
                f"lifetime spend {lifetime:.4f} plus the run budget {run_budget:g} "
                f"exceeds the total budget {defn['total_budget_usd']:g}", 1,
            )
        today = sensorlib.spend_today(rows, self.started)
        if today + run_budget > defn["daily_budget_usd"] + BUDGET_EPSILON:
            return (
                "throttled", "daily-budget-spent",
                f"today's spend {today:.4f} plus the run budget {run_budget:g} "
                f"exceeds the daily budget {defn['daily_budget_usd']:g}", 0,
            )
        wip, problem = counters["wip"], None
        if "wip_command" in defn:
            text, problem = _command_text(
                defn["wip_command"], self.project, defn["sensor_timeout_s"]
            )
            if problem is None:
                try:
                    wip = int(text.strip())
                except ValueError:
                    problem = f"printed {text.strip()[:80]!r}, not an integer"
        if problem is not None:
            return ("throttled", "wip-full", f"wip_command failed: {problem}", 0)
        if wip >= defn["wip_limit"]:
            return (
                "throttled", "wip-full",
                f"{wip} unreviewed increments reach the limit {defn['wip_limit']}", 0,
            )
        return None

    def select(self, reading, counters):
        """`(item, None)` or `(None, why)`: the controller's selection."""
        defn = self.defn
        if defn["controller"] == "command":
            text, problem = _command_text(
                defn["controller_command"], self.project, defn["sensor_timeout_s"]
            )
            if problem is not None:
                return None, f"controller_command failed: {problem}"
            text = text.strip()
            return (text, None) if text else (None, "controller_command printed nothing")
        held = {str(i) for i in counters["held_items"]}
        for candidate in sorted(reading.items):
            if candidate not in held:
                return candidate, None
        return None, "every sensor item is held by an unreviewed increment or none was reported"

    def actuate_and_judge(self, before, prompt, item):
        defn = self.defn
        scratch = self.vault / "tmp" / "loops" / self.loop_id / self.run_id
        scratch.mkdir(parents=True, exist_ok=True)
        vaultlib.write_text_lf(scratch / "prompt.md", prompt)

        state_in_memory = looplib.read_state(self.dir)
        judge = defn.get(looplib.JUDGE_KEY)
        rules_text = (
            looplib.read_rules_text(looplib.judge_rules_path(self.dir, judge)) if judge else None
        )
        prints = _fingerprints(self.dir, defn)
        proc = self.launch(prompt)
        (scratch / "actuator-stdout.json").write_bytes(proc.stdout)
        if proc.stderr:
            (scratch / "actuator-stderr.txt").write_bytes(proc.stderr)

        event, failure = None, None
        if proc.error:
            failure = proc.error
        elif proc.timed_out:
            failure = f"timed out after {defn['timeout_s']:g} seconds"
        else:
            try:
                event = sensorlib.parse_result(_text(proc.stdout))
            except sensorlib.NoResultEvent as exc:
                failure = f"{exc} (exit {proc.returncode})"
        if event is not None:
            cost = event.cost_usd
            if proc.returncode != 0 or event.is_error or event.subtype != "success":
                failure = (
                    f"actuator ended with subtype {event.subtype or 'none'}, "
                    f"is_error {str(event.is_error).lower()} (exit {proc.returncode})"
                )
        else:
            cost = defn["max_budget_usd"]
        fields = {"cost_usd": cost}
        if event is not None:
            fields.update(
                num_turns=event.num_turns,
                duration_ms=event.duration_ms,
                subtype=event.subtype,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                cache_read_tokens=event.cache_read_tokens,
                cache_creation_tokens=event.cache_creation_tokens,
            )

        changed = [n for n, digest in _fingerprints(self.dir, defn).items() if digest != prints[n]]
        if changed:
            # The actuator rewrote what binds it; the state file is put back
            # so the halting transition applies to the state the run was in.
            looplib.write_state(self.dir, state_in_memory)
            return self.end(
                "failed", "controls-changed",
                "the actuator changed " + ", ".join(changed), 1, **fields,
            )

        if failure is not None:
            row = {**self.row, **fields, "outcome": "failed"}
            counters = looplib.fold(self.ledger_rows() + [row])
            limit = counters["consecutive_failures"] >= defn["max_actuator_failures"]
            return self.end(
                "failed", "failed-limit" if limit else "failed", failure, 1 if limit else 0,
                **fields,
            )
        self.step("finished", f"actuator finished {self.run_id}")

        after = _sense(defn, self.project)
        if after.valid:
            self.row["reading_after"] = _reading_summary(after)
            outcome = sensorlib.judge(before, after, defn["direction"])
            reason = f"{before.value:g} -> {after.value:g}"
        else:
            # The transition table has no event for an invalid reading while
            # verifying. The run counts as a neutral one, with the reason
            # recorded, and ends through the same limit checks; the next run's
            # first sense halts on the invalid reading before any spend.
            outcome = "neutral"
            reason = f"re-sense invalid: {after.reason}"
        if defn.get(looplib.JUDGE_KEY):
            judged_prints = _fingerprints(self.dir, defn)
            judged_tree = _project_snapshot(self.project, self.dir)
            record = self.run_judge(scratch, after, rules_text)
            fields["judge"] = record
            fields["cost_usd"] = fields["cost_usd"] + record["cost_usd"]
            touched = [
                n for n, digest in _fingerprints(self.dir, defn).items()
                if digest != judged_prints[n]
            ]
            tree_after = _project_snapshot(self.project, self.dir)
            if PARTIAL in judged_tree or PARTIAL in tree_after:
                record["snapshot_partial"] = True
            touched += sorted(
                n for n in judged_tree.keys() | tree_after.keys()
                if n != PARTIAL and judged_tree.get(n) != tree_after.get(n)
            )
            if touched:
                # The judge may read and nothing else.
                return self.end(
                    "failed", "controls-changed",
                    "the judge changed " + ", ".join(touched[:20]), 1, **fields,
                )
        row = {**self.row, **fields, "outcome": outcome}
        counters = looplib.fold(self.ledger_rows() + [row])
        event_name, code = outcome, 0
        if outcome == "harmful" and counters["consecutive_harmful"] >= defn["max_harmful_runs"]:
            event_name, code = "harmful-limit", 1
        elif outcome != "helpful" and counters["runs_without_help"] >= defn["max_runs_without_help"]:
            event_name, code = "no-progress-limit", 1
        return self.end(outcome, event_name, reason, code, **fields)

    def launch(self, prompt):
        """Run the actuator with the prompt on stdin."""
        return self.launch_session(prompt, self.defn, self.defn["allowed_tools"])

    def launch_session(self, prompt, caps, tools):
        """Run a fresh headless session with the model, caps and timeout of
        `caps` (the definition or its judge object) and the tool names
        `tools`, the prompt on stdin."""
        argv = [
            self.binary, "-p", "--output-format", "json",
            "--model", caps["model"],
            "--max-turns", str(caps["max_turns"]),
            "--max-budget-usd", _number(caps["max_budget_usd"]),
            "--strict-mcp-config",
        ]
        if tools:
            argv += ["--allowedTools", ",".join(tools)]
        env = dict(os.environ)
        env["COMPASS_WORKER_SESSION"] = "1"
        env.setdefault("CLAUDE_PROJECT_DIR", str(self.project))
        return _run_process(argv, self.project, caps["timeout_s"], prompt.encode("utf-8"), env)

    def run_judge(self, scratch, after, rules_text):
        """Launch the judge `runs` times and return the run row's `judge`
        record. A run with no usable answer is invalid, votes for nothing and
        is charged the event's cost, or the judge's full budget when no
        result event arrived."""
        judge = self.defn[looplib.JUDGE_KEY]
        rule_ids = [rule_id for rule_id, _text in looplib.parse_rules(rules_text)]
        prompt = _judge_prompt(rules_text)
        voting, invalid, discarded, cost = [], 0, 0, 0.0
        for number in range(1, judge["runs"] + 1):
            proc = self.launch_session(prompt, judge, JUDGE_TOOLS.split(","))
            (scratch / f"judge-{number}-stdout.json").write_bytes(proc.stdout)
            event = None
            if not proc.error and not proc.timed_out:
                try:
                    event = sensorlib.parse_result(_text(proc.stdout))
                except sensorlib.NoResultEvent:
                    pass
            if event is None:
                cost += judge["max_budget_usd"]
                invalid += 1
                continue
            cost += event.cost_usd
            if (
                proc.returncode != 0 or event.is_error or event.subtype != "success"
                or event.result is None
            ):
                invalid += 1
                continue
            parsed = sensorlib.parse_judge_lines(event.result, rule_ids)
            discarded += parsed.discarded
            voting.append(parsed.findings)
        kept = sensorlib.vote_findings(voting, judge["runs"])
        record = {
            "kept": kept[:MAX_KEPT_FINDINGS],
            "kept_total": len(kept),
            "valid_runs": len(voting),
            "invalid_runs": invalid,
            "discarded": discarded,
            "cost_usd": cost,
        }
        anchor = judge.get("anchor_rule")
        if anchor and after.valid:
            delta = sum(1 for k in kept if k["rule"] == anchor) - after.value
            record["anchor_delta"] = int(delta) if float(delta).is_integer() else delta
        return record

    def resolve_binary(self):
        config = {}
        try:
            data = json.loads((self.vault / "meta" / "capture.json").read_text(encoding="utf-8"))
            if isinstance(data, dict):
                config = data
        except (OSError, ValueError):
            pass
        binary, kind = capture_worker._resolve_binary(config, self.vault)
        if kind == "dsh":
            raise _Refusal("the resolved binary is dsh, which cannot run the actuator")
        self.binary = binary


def _open(loop_dir, dry_run, now):
    """A `_Run` over a loop that may start, or `_Refusal`."""
    loop_dir = Path(os.path.abspath(loop_dir))
    try:
        definition = looplib.load_definition(loop_dir)
        state = looplib.read_state(loop_dir)
    except (looplib.DefinitionError, looplib.StateError) as exc:
        raise _Refusal(str(exc)) from None
    status = _status(loop_dir)
    if status != "active" and not dry_run:
        raise _Refusal(f"{loop_dir.name} has status {status or 'unset'}, not active")
    if not (loop_dir / "actuator.md").is_file():
        raise _Refusal(f"{loop_dir / 'actuator.md'} does not exist")
    if state["state"] in NOT_RUNNABLE:
        raise _Refusal(f"{loop_dir.name} is {state['state']}")
    return _Run(loop_dir, definition, dry_run, now)


@_exit_code
def run_iteration(loop_dir, dry_run=False, *, now=None):
    """One iteration of the loop; see the module docstring."""
    run = None
    try:
        run = _open(loop_dir, dry_run, now)
        if not dry_run:
            run.resolve_binary()
            run.acquire()
        return run.execute()
    except _Refusal as exc:
        _complain(str(exc))
        return 1
    except (looplib.TransitionError, looplib.StateError, OSError) as exc:
        _complain(f"{type(exc).__name__}: {exc}")
        if run is not None and not dry_run:
            try:
                looplib.append_ledger(
                    run.dir,
                    {"type": "error", "run_id": run.run_id, "reason": f"{type(exc).__name__}: {exc}"},
                )
            except OSError:
                pass
        return 1
    finally:
        if run is not None:
            run.release()


def _sensor_for(loop_dir):
    """`(reading, project)` from the loop's domain sensor, or `(None, reason)`
    when the definition cannot be read."""
    loop_dir, _vault, project = _loop_paths(loop_dir)
    try:
        definition = looplib.load_definition(loop_dir)
    except looplib.DefinitionError as exc:
        return None, str(exc)
    return _sense(definition, project), None


@_exit_code
def write_baseline(loop_dir):
    """Commit the sensor's sorted items to `baseline.json`."""
    reading, problem = _sensor_for(loop_dir)
    if reading is None:
        _complain(problem)
        return 1
    if not reading.valid:
        _complain(f"invalid sensor reading, baseline unchanged: {reading.reason}")
        return 1
    items = sorted(reading.items)
    vaultlib.write_text_lf(
        Path(os.path.abspath(loop_dir)) / BASELINE_FILE,
        json.dumps({"items": items}, indent=2) + "\n",
    )
    _say(f"baseline holds {len(items)} items")
    return 0


@_exit_code
def check(loop_dir, blocking=False):
    """Print the sensor items absent from the baseline (new) and the baseline
    items the sensor no longer reports (fixed). Returns 1 for a new item under
    `blocking`, or when the reading or the baseline is unusable."""
    reading, problem = _sensor_for(loop_dir)
    if reading is None:
        _complain(problem)
        return 1
    if not reading.valid:
        _complain(f"invalid sensor reading: {reading.reason}")
        return 1
    path = Path(os.path.abspath(loop_dir)) / BASELINE_FILE
    try:
        baseline = json.loads(_read_text(path))["items"]
        if not isinstance(baseline, list) or not all(isinstance(i, str) for i in baseline):
            raise ValueError("items must be a list of strings")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        _complain(f"cannot read the baseline {path}: {exc}; run the baseline command first")
        return 1
    new = sorted((Counter(reading.items) - Counter(baseline)).elements())
    fixed = sorted((Counter(baseline) - Counter(reading.items)).elements())
    for item in new:
        _say(f"new: {item}")
    for item in fixed:
        _say(f"fixed: {item}")
    _say(f"{len(new)} new, {len(fixed)} fixed")
    return 1 if blocking and new else 0
