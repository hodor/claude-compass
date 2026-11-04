"""One build session held open and driven turn by turn.

`drive_build` starts `claude -p --input-format stream-json --output-format
stream-json --verbose` in a project, under the launch.py isolation, sends the
opening message and, at every end of turn, asks the simulated human for the next
message. The build ends when the human says it is done, when a cap is reached
(wall time, turns), when the session hits a usage limit, or when it fails.

While the session reports background tasks running (its latest
`system/background_tasks_changed` event lists any), an end of turn goes to no
one: the driver reads on, since the session starts a turn of its own when a task
finishes. After BACKGROUND_IDLE_SECONDS with no event the end of turn goes to
the human after all. The human reads the text of every turn since its last
message. A turn that ends with no text gets the continue message without the
human.

In the "compass" arm a setup session, started with `--plugin-dir`, runs
`/compass:setup` and is closed when its turn ends; the driver pins `commit:` in the project's
`.compass/meta/plugin.yaml` to the remote head of the repository, so Compass's
start-of-session self-update finds the install current, and starts the build
session without `--plugin-dir`, which loads Compass once, from the project's
`.claude/` install, and receives the opening message. The first and last
`system/init` events give the skill and agent counts before and after setup.

Before launch a PreToolUse command hook (`hooks/answer_question.py`) is merged
into the project's `.claude/settings.local.json`; it answers `AskUserQuestion`
through the human's answer command and fences Bash, Write and Edit calls into
the project. In the "compass" arm the plugin folder is also a read root: Bash
commands may name paths inside it (setup copies from it) but nothing may write
there, and the check after the build marks a build failed when `plugin/` of the
repository changed.

The session runs with HOME, USERPROFILE, APPDATA, LOCALAPPDATA, TEMP and TMP
inside a per-project home folder under the private root, holding a `.gitconfig`
with a build identity, so the real home folder is out of reach.

The setup and build sessions are recorded together as one role `build` row; the simulated human
records its own sessions, so its tokens stay out of the build's count.

    python drive.py PROJECT --arm {compass,baseline} --opening-file FILE
        --brief-file FILE --human-folder DIR [--max-minutes N] [--max-turns N]
        [--max-budget-usd N]
"""

import argparse
import hashlib
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import human as human_module
import launch
import records

HOOK_SCRIPT = Path(__file__).resolve().parent / "hooks" / "answer_question.py"
HOOK_MATCHER = "AskUserQuestion|Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit"
HOOK_TIMEOUT_SECONDS = 1800
# Exit codes of `main`: 0 human-done, 1 any other end, 2 refused, 3 usage limit.
EXIT_REFUSED = 2
EXIT_USAGE_LIMIT = 3
# Seconds one simulated-human session may run.
HUMAN_TIMEOUT_SECONDS = 900

SETUP_MESSAGE = "/compass:setup"
CONTINUE_MESSAGE = "continue"

HUMAN_DONE = "human-done"
WALL_TIME = "wall-time"
TURNS = "turns"

DEFAULT_MAX_WALL_SECONDS = 9000
DEFAULT_MAX_TURNS = 400
DEFAULT_MAX_BUDGET_USD = 50

# Seconds the reader waits on the session between checks of the wall clock.
POLL_SECONDS = 1.0
# Seconds with no event, background tasks listed, after which the end of turn
# goes to the human: a task the session never reports finished.
BACKGROUND_IDLE_SECONDS = 1200
# Seconds a session gets to exit after its input is closed.
EXIT_SECONDS = 60.0
# Seconds the output is read for after the session exited.
DRAIN_SECONDS = 10.0

# Folders of the sandbox home that the home-like variables name; the hook's
# HOME_SUBFOLDERS holds the same table.
HOME_VARIABLE_FOLDERS = {
    "APPDATA": "AppData/Roaming",
    "LOCALAPPDATA": "AppData/Local",
    "TEMP": "AppData/Local/Temp",
    "TMP": "AppData/Local/Temp",
}
HOME_VARIABLES_REMOVED = frozenset({"HOMEDRIVE", "HOMEPATH"})
BUILD_GITCONFIG = "[user]\n\tname = Overhead Build\n\temail = build@example.invalid\n"
PLUGIN_CHANGED = "plugin/ changed during the build"

_COMMIT_LINE = re.compile(r"^(\s*)commit:.*$", re.MULTILINE)


@dataclass
class DriveResult:
    end: str
    turns: int
    resets_at: float | None = None
    init_counts: dict | None = None
    events: list = field(default_factory=list, repr=False)
    stderr: str = field(default="", repr=False)
    reason: str = ""


class _Idle(Exception):
    """No event arrived for BACKGROUND_IDLE_SECONDS while background tasks were listed."""


class _Ended(Exception):
    """The build session ended before the turn finished; carries the end."""

    def __init__(self, end, resets_at=None):
        super().__init__(end)
        self.end = end
        self.resets_at = resets_at


def _command_for_hook():
    python = Path(sys.executable).as_posix()
    return f'"{python}" "{HOOK_SCRIPT.as_posix()}"'


def install_hook(project):
    """Merge the hook entry into `<project>/.claude/settings.local.json`,
    keeping every other setting and replacing an earlier entry of this hook."""
    path = Path(project) / ".claude" / "settings.local.json"
    settings = {}
    if path.exists():
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            raise launch.Refused(f"{path.name} is not valid JSON: {error}") from error
        if not isinstance(settings, dict):
            raise launch.Refused(f"{path.name} does not hold a JSON object")
    hooks = settings.setdefault("hooks", {})
    existing = hooks.get("PreToolUse", []) if isinstance(hooks, dict) else None
    shaped = isinstance(existing, list) and all(
        isinstance(group, dict)
        and isinstance(group.get("hooks", []), list)
        and all(isinstance(hook, dict) for hook in group.get("hooks", []))
        for group in existing
    )
    if not shaped:
        raise launch.Refused(f"the hooks in {path.name} do not have the expected shape")
    groups = [
        group for group in existing
        if not any(HOOK_SCRIPT.name in str(hook.get("command", "")) for hook in group.get("hooks", []))
    ]
    groups.append({
        "matcher": HOOK_MATCHER,
        "hooks": [{"type": "command", "command": _command_for_hook(), "timeout": HOOK_TIMEOUT_SECONDS}],
    })
    hooks["PreToolUse"] = groups
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def project_key(project):
    """A file-name stem for `project`: its folder name and a hash of its resolved path."""
    resolved = os.path.normcase(os.path.realpath(project))
    return f"{Path(project).name}-{hashlib.sha256(resolved.encode('utf-8')).hexdigest()[:12]}"


def write_hook_config(project, private_root, answer_command, read_roots=None, home=None):
    """The JSON file the hook reads; returns its path. `read_roots` (a list of
    folders) and `home` are written when given."""
    folder = Path(private_root) / "hook-config"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{project_key(project)}.json"
    config = {"project": str(project), "answer_command": list(answer_command)}
    if read_roots is not None:
        config["read_roots"] = [str(root) for root in read_roots]
    if home is not None:
        config["home"] = str(home)
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def sandbox_home(project, private_root):
    """The home folder of `project`'s build, created with its `.gitconfig` and
    the folders the home-like variables name."""
    home = Path(private_root) / "homes" / project_key(project)
    home.mkdir(parents=True, exist_ok=True)
    for sub in HOME_VARIABLE_FOLDERS.values():
        (home / sub).mkdir(parents=True, exist_ok=True)
    (home / ".gitconfig").write_text(BUILD_GITCONFIG, encoding="utf-8")
    return home


def apply_home(env, home):
    """`env` with the home-like variables pointing into `home`; HOMEDRIVE and
    HOMEPATH are removed."""
    names = {"HOME", "USERPROFILE", *HOME_VARIABLE_FOLDERS, *HOME_VARIABLES_REMOVED}
    env = {key: value for key, value in env.items() if key.upper() not in names}
    env["HOME"] = env["USERPROFILE"] = str(home)
    for name, sub in HOME_VARIABLE_FOLDERS.items():
        env[name] = str(Path(home) / sub)
    return env


def plugin_changes(repo_root):
    """Lines of `git status --porcelain` for `plugin/` of `repo_root`; a line
    saying so when git cannot report."""
    done = launch._git(repo_root, "status", "--porcelain", "--untracked-files=all", "--", "plugin")
    if done.returncode != 0:
        return ["git cannot report the state of plugin/"]
    return [line for line in done.stdout.splitlines() if line.strip()]


def remote_head(repo_root):
    """The sha `git ls-remote origin HEAD` reports for `repo_root`."""
    done = launch._git(repo_root, "ls-remote", "origin", "HEAD")
    words = done.stdout.split()
    if done.returncode != 0 or not words or not re.fullmatch(r"[0-9a-f]{7,64}", words[0]):
        raise launch.Refused("git cannot report the remote head of the repository")
    return words[0]


def pin_commit(project, sha):
    """Set `commit:` in the project's plugin.yaml to `sha`; False when the file is missing."""
    path = Path(project) / ".compass" / "meta" / "plugin.yaml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if _COMMIT_LINE.search(text):
        text = _COMMIT_LINE.sub(lambda match: f"{match.group(1)}commit: {sha}", text, count=1)
    else:
        text = text.rstrip("\n") + f"\ncommit: {sha}\n"
    path.write_text(text, encoding="utf-8")
    return True


def _size(value):
    if isinstance(value, (list, tuple, dict)):
        return len(value)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def init_counts(events):
    """{"before": {"skills", "agents"}, "after": {...}} from the first and last
    `system/init` events, or None when there are none."""
    inits = [e for e in events if e.get("type") == "system" and e.get("subtype") == "init"]
    if not inits:
        return None

    def counts(event):
        return {"skills": _size(event.get("skills")), "agents": _size(event.get("agents"))}

    return {"before": counts(inits[0]), "after": counts(inits[-1])}


def _assistant_text(event):
    if event.get("parent_tool_use_id") is not None:
        return ""
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "".join(
        block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"
    )


def _message_line(text):
    return json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}) + "\n"


def _budget_argument(value):
    return str(int(value)) if value == int(value) else str(value)


class _Session:
    """A running build process with its output read on a thread."""

    def __init__(self, command, cwd, env):
        self.stderr = tempfile.TemporaryFile()
        try:
            self.process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                cwd=cwd, env=env, **launch._group_options(),
            )
        except BaseException:
            self.stderr.close()
            raise
        self.lines = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for raw in self.process.stdout:
                self.lines.put(raw.decode("utf-8", errors="replace"))
        finally:
            self.lines.put(None)

    def send(self, text):
        """True when the message was written."""
        try:
            self.process.stdin.write(_message_line(text).encode("utf-8"))
            self.process.stdin.flush()
            return True
        except (OSError, ValueError):
            return False

    def close_input(self):
        try:
            self.process.stdin.close()
        except (OSError, ValueError):
            pass

    def kill(self):
        launch._kill_tree(self.process)

    def close_output(self):
        """Close the output pipe once the reader thread has finished with it."""
        self.reader.join(timeout=DRAIN_SECONDS)
        if not self.reader.is_alive():
            try:
                self.process.stdout.close()
            except (OSError, ValueError):
                pass

    def wait_exit(self):
        """The exit code; the process tree is killed when it outlives EXIT_SECONDS."""
        try:
            return self.process.wait(timeout=EXIT_SECONDS)
        except subprocess.TimeoutExpired:
            self.kill()
            return self.process.wait()

    def drain(self):
        """Lines left in the output after the process ended."""
        lines = []
        end = time.monotonic() + DRAIN_SECONDS
        while time.monotonic() < end:
            try:
                item = self.lines.get(timeout=0.2)
            except queue.Empty:
                if not self.reader.is_alive():
                    break
                continue
            if item is None:
                break
            lines.append(item)
        return lines

    def stderr_text(self):
        """The session's stderr; the temporary file is closed."""
        try:
            self.stderr.seek(0)
            return self.stderr.read().decode("utf-8", errors="replace")
        except (OSError, ValueError):
            return ""
        finally:
            self.stderr.close()


def _turn_status(turn_events):
    """(end, resets_at) when a turn's events show a bad end, else None."""
    rejected = launch._rejected_events(turn_events)
    if rejected or launch._limit_result(turn_events):
        return launch.USAGE_LIMIT, launch._reset_time(rejected)
    results = [event for event in turn_events if event.get("type") == "result"]
    if results and results[-1].get("is_error") is not False:
        return launch.FAILED, None
    return None


def drive_build(
    project,
    opening_message,
    *,
    human,
    repo_root,
    arm,
    private_root=None,
    claude_cmd=None,
    parent_env=None,
    max_wall_seconds=DEFAULT_MAX_WALL_SECONDS,
    max_turns=DEFAULT_MAX_TURNS,
    max_budget_usd=DEFAULT_MAX_BUDGET_USD,
    clock=time.monotonic,
):
    """Drive one build to its end and return a DriveResult.

    Raises launch.Refused, before anything starts, when `plugin/` of `repo_root`
    has uncommitted changes (or, in the "compass" arm, the remote head cannot be
    read).
    """
    if arm not in records.ARMS:
        raise ValueError(f"arm is not one of {', '.join(records.ARMS)}")
    project = Path(project)
    repo_root = Path(repo_root)
    private_root = Path(private_root) if private_root is not None else launch.default_private_root()
    compass = arm == "compass"

    head_sha = launch.check_plugin_clean(repo_root, require_plugin=compass)
    pinned_sha = remote_head(repo_root) if compass else None

    parent = os.environ if parent_env is None else parent_env
    home = sandbox_home(project, private_root)
    env = apply_home(launch.session_environment(parent, private_root), home)
    command = launch.resolve_command(claude_cmd, parent)
    command += [
        "-p",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--verbose",
        "--setting-sources", "project,local",
        "--strict-mcp-config",
        "--max-budget-usd", _budget_argument(max_budget_usd),
    ]

    install_hook(project)
    read_roots = [str(repo_root / "plugin")] if compass else []
    env["OVERHEAD_HOOK_CONFIG"] = str(
        write_hook_config(project, private_root, human.answer_command, read_roots=read_roots, home=home)
    )

    events = []
    turns = 0
    end, resets_at = launch.FAILED, None
    started_at = time.time()
    start = clock()
    background = {"running": False}
    setup_stderr = ""
    plugin_args = ["--plugin-dir", str(repo_root / "plugin")]
    session = _Session(command + plugin_args if compass else command, str(project), env)

    def read_turn(idle_limit=None):
        """Read events up to the turn's `result`; return (assistant text, the turn's events).

        With `idle_limit`, raises _Idle when that many seconds pass with no event
        before the turn's first one."""
        turn_events = []
        text = ""
        waiting_since = clock()
        while True:
            try:
                line = session.lines.get(timeout=POLL_SECONDS)
            except queue.Empty:
                now = clock()
                if now - start > max_wall_seconds:
                    raise _Ended(WALL_TIME) from None
                if idle_limit is not None and not turn_events and now - waiting_since > idle_limit:
                    raise _Idle() from None
                continue
            if line is None:
                code = session.wait_exit()
                status, reset = launch.classify(
                    turn_events, code, not turn_events,
                    lambda: launch._transcript_tail_is_api_error(private_root, project, started_at),
                )
                raise _Ended(launch.USAGE_LIMIT if status == launch.USAGE_LIMIT else launch.FAILED, reset)
            for event in launch._parse_events(line):
                turn_events.append(event)
                events.append(event)
                if event.get("type") == "system" and event.get("subtype") == "background_tasks_changed":
                    background["running"] = bool(event.get("tasks"))
                elif event.get("type") == "assistant":
                    said = _assistant_text(event)
                    if said.strip():
                        text = said
                elif event.get("type") == "result":
                    if not text and isinstance(event.get("result"), str):
                        text = event["result"]
                    return text, turn_events

    def close_session():
        session.close_input()
        if session.process.poll() is None:
            try:
                session.wait_exit()
            except OSError:
                pass
        for line in session.drain():
            events.extend(launch._parse_events(line))
        if session.process.poll() is None:
            session.kill()
        session.close_output()

    def check_caps():
        if turns >= max_turns:
            raise _Ended(TURNS)
        if clock() - start > max_wall_seconds:
            raise _Ended(WALL_TIME)

    def run_turns():
        """Read turns until no background task runs; return the texts they ended with."""
        nonlocal turns
        texts = []
        idle_limit = None
        while True:
            try:
                text, turn_events = read_turn(idle_limit)
            except _Idle:
                background["running"] = False
                return "\n\n".join(texts)
            idle_limit = BACKGROUND_IDLE_SECONDS
            turns += 1
            bad = _turn_status(turn_events)
            if bad is not None:
                raise _Ended(*bad)
            if text.strip():
                texts.append(text)
            if not background["running"]:
                return "\n\n".join(texts)
            check_caps()

    try:
        if compass:
            if not session.send(SETUP_MESSAGE):
                raise _Ended(launch.FAILED)
            run_turns()
            close_session()
            setup_stderr = session.stderr_text()
            if not pin_commit(project, pinned_sha):
                raise _Ended(launch.FAILED)
            check_caps()
            background["running"] = False
            session = _Session(command, str(project), env)
        pending = opening_message
        while True:
            if not session.send(pending):
                raise _Ended(launch.FAILED)
            text = run_turns()
            check_caps()
            if not text.strip():
                pending = CONTINUE_MESSAGE
                continue
            reply = human.reply(text)
            if reply.outcome != launch.DONE:
                end = reply.outcome
                break
            if reply.done:
                end = HUMAN_DONE
                break
            pending = reply.text if reply.text.strip() else CONTINUE_MESSAGE
    except _Ended as ended:
        end, resets_at = ended.end, ended.resets_at
        if end == WALL_TIME:
            session.kill()
    finally:
        close_session()

    reason = ""
    changed = plugin_changes(repo_root)
    if changed:
        end, reason = launch.FAILED, f"{PLUGIN_CHANGED}: {'; '.join(changed[:5])}"

    outcome = {HUMAN_DONE: launch.DONE, launch.USAGE_LIMIT: launch.USAGE_LIMIT}.get(end, launch.FAILED)
    records.record_session(events, role="build", outcome=outcome, arm=arm, plugin_sha=head_sha, private_root=private_root)
    return DriveResult(
        end=end, turns=turns, resets_at=resets_at, init_counts=init_counts(events),
        events=events, stderr=setup_stderr + session.stderr_text(), reason=reason,
    )


def _build_parser():
    parser = argparse.ArgumentParser(description="Drive one build session with a simulated human.")
    parser.add_argument("project")
    parser.add_argument("--arm", required=True, choices=records.ARMS)
    parser.add_argument("--opening-file", required=True)
    parser.add_argument("--brief-file", required=True)
    parser.add_argument("--human-folder", required=True)
    parser.add_argument("--max-minutes", type=float, default=DEFAULT_MAX_WALL_SECONDS / 60)
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument("--max-budget-usd", type=float, default=DEFAULT_MAX_BUDGET_USD)
    parser.add_argument("--private-root")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    private_root = Path(args.private_root) if args.private_root else launch.default_private_root()
    project = Path(args.project)
    try:
        opening = Path(args.opening_file).read_text(encoding="utf-8")
        brief = json.loads(Path(args.brief_file).read_text(encoding="utf-8"))
        readme = None
        if args.arm == "compass":
            readme = (repo_root / "README.md").read_text(encoding="utf-8")
        folder = Path(args.human_folder)
        folder.mkdir(parents=True, exist_ok=True)
        who = human_module.SimulatedHuman(
            brief, folder=folder, repo_root=repo_root, arm=args.arm,
            state_file=private_root / "human-state" / f"{project_key(project)}.json",
            private_root=private_root, readme=readme, timeout=HUMAN_TIMEOUT_SECONDS,
        )
        result = drive_build(
            project, opening, human=who, repo_root=repo_root, arm=args.arm, private_root=private_root,
            max_wall_seconds=args.max_minutes * 60, max_turns=args.max_turns,
            max_budget_usd=args.max_budget_usd,
        )
    except (launch.Refused, records.Refused, OSError, ValueError) as error:
        sys.stderr.write(f"refused: {error}\n")
        return EXIT_REFUSED
    print(json.dumps({
        "end": result.end, "turns": result.turns, "resets_at": result.resets_at, "reason": result.reason,
        "init_counts": result.init_counts,
    }))
    if result.end == HUMAN_DONE:
        return 0
    return EXIT_USAGE_LIMIT if result.end == launch.USAGE_LIMIT else 1


if __name__ == "__main__":
    sys.exit(main())
