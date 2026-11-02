"""Isolated `claude -p` sessions for the overhead measurement.

`run_session` starts one headless session in a project folder under the sandbox
Claude config, reads its `stream-json` output and classifies how it ended:

    done         exit 0 and the last `result` event is not an error
    usage-limit  a `rate_limit_event` with status `rejected`, a `result` event
                 whose `api_error` is `usage_limit_reached`, or exit 1 with
                 nothing on stdout while the newest transcript of the project
                 ends in an entry marked `isApiErrorMessage`
    failed       anything else

The classification never reads `subtype` and never searches text for limit
words: a model may quote them, and a limit result can carry any subtype.

A session starts only from a clean `plugin/` folder of the repository, so the
recorded commit describes the Compass that ran.
"""

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

CREDENTIAL_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
)

DONE = "done"
FAILED = "failed"
USAGE_LIMIT = "usage-limit"

LIMIT_API_ERROR = "usage_limit_reached"
REJECTED = "rejected"

# The returncode of a session killed at its timeout.
TIMED_OUT = -1

# A transcript last written longer before the session start than this belongs
# to an earlier session; the slack covers coarse file-system timestamps.
TRANSCRIPT_SLACK_SECONDS = 2.0

_COMPONENT_SPLIT = re.compile(r"[\\/]")
_EDITOR_FRAGMENTS = ("vs code", "vscode", "visual studio code")
_EDITOR_NAMES = ("cursor", "cursor.app")


class Refused(Exception):
    """The session was not started."""


@dataclass
class LaunchResult:
    status: str
    events: list
    returncode: int
    resets_at: float | None = None
    head_sha: str | None = None
    stderr: str = field(default="", repr=False)


def default_private_root():
    return Path.home() / ".compass" / "overhead"


def encode_cwd(cwd):
    """The folder name Claude Code gives a working directory under projects/."""
    return re.sub(r"[^a-zA-Z0-9]", "-", str(cwd))


def _is_editor_folder(entry):
    for component in _COMPONENT_SPLIT.split(entry.lower()):
        if component in _EDITOR_NAMES or any(part in component for part in _EDITOR_FRAGMENTS):
            return True
    return False


def session_environment(parent_env, private_root):
    """The environment of an isolated session, built from `parent_env`.

    Credentials are dropped; the Claude config, GitHub config and dsh home point
    into `private_root`; the editor folders leave `PATH`. `parent_env` is not
    modified.
    """
    private_root = Path(private_root)
    credentials = {name.upper() for name in CREDENTIAL_VARS}
    env = {key: value for key, value in parent_env.items() if key.upper() not in credentials}

    for key in list(env):
        if key.upper() == "PATH":
            entries = env[key].split(os.pathsep)
            env[key] = os.pathsep.join(entry for entry in entries if not _is_editor_folder(entry))

    config = private_root / "claude-config"
    gh_config = private_root / "gh-config"
    config.mkdir(parents=True, exist_ok=True)
    gh_config.mkdir(parents=True, exist_ok=True)

    env["CLAUDE_CONFIG_DIR"] = str(config)
    env["GH_CONFIG_DIR"] = str(gh_config)
    env["DSH_HOME"] = str(private_root / "dsh-home-absent")
    env["DISABLE_AUTOUPDATER"] = "1"
    env["PIP_REQUIRE_VIRTUALENV"] = "1"
    return env


def resolve_command(claude_cmd, env=None):
    """`claude_cmd` as an argument list with its executable found on `PATH`."""
    command = list(claude_cmd) if claude_cmd else ["claude"]
    found = shutil.which(command[0], path=(env or os.environ).get("PATH"))
    if found:
        command[0] = found
    return command


def _git(repo_root, *args):
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args], capture_output=True, text=True, encoding="utf-8",
        )
    except OSError as error:
        raise Refused(f"git cannot be run: {error}") from error


def check_plugin_clean(repo_root):
    """Return the repository's HEAD sha; raise Refused unless `plugin/` is clean.

    Staged, modified, deleted and untracked files under `plugin/` all count as
    changes; ignored files do not. A failure of git to report the state refuses.
    """
    prefix = _git(repo_root, "rev-parse", "--show-prefix")
    if prefix.returncode != 0 or prefix.stdout.strip() != "":
        raise Refused("the repository root is not the top of a git work tree")
    status = _git(repo_root, "status", "--porcelain", "--untracked-files=all", "--", "plugin")
    if status.returncode != 0:
        raise Refused("git cannot report the state of plugin/")
    if status.stdout.strip():
        raise Refused("plugin/ has uncommitted changes")
    head = _git(repo_root, "rev-parse", "HEAD")
    if head.returncode != 0:
        raise Refused("git cannot report the repository's HEAD")
    return head.stdout.strip()


def _parse_events(text):
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _event_field(event, name):
    """`name` from the top level of a rate-limit event or from `rate_limit_info`."""
    if name in event:
        return event[name]
    info = event.get("rate_limit_info")
    return info.get(name) if isinstance(info, dict) else None


def _rejected_events(events):
    return [
        event for event in events
        if event.get("type") == "rate_limit_event" and _event_field(event, "status") == REJECTED
    ]


def _limit_result(events):
    return any(
        event.get("type") == "result" and event.get("api_error") == LIMIT_API_ERROR for event in events
    )


def _reset_time(rejected):
    for event in reversed(rejected):
        value = _event_field(event, "resetsAt")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None


def _transcript_tail_is_api_error(private_root, project, started):
    """True when the newest transcript written since `started` ends in an
    entry marked `isApiErrorMessage`."""
    projects = Path(private_root) / "claude-config" / "projects"
    names = {encode_cwd(os.path.abspath(project)), encode_cwd(os.path.realpath(project))}
    newest, newest_time = None, None
    for name in names:
        for path in (projects / name).glob("*.jsonl"):
            try:
                modified = path.stat().st_mtime
            except OSError:
                continue
            if modified < started - TRANSCRIPT_SLACK_SECONDS:
                continue
            if newest_time is None or modified > newest_time:
                newest, newest_time = path, modified
    if newest is None:
        return False
    try:
        text = newest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    try:
        tail = json.loads(lines[-1])
    except (ValueError, RecursionError):
        return False
    return isinstance(tail, dict) and tail.get("isApiErrorMessage") is True


def _last_result_succeeded(events):
    results = [event for event in events if event.get("type") == "result"]
    return bool(results) and results[-1].get("is_error") is False


def classify(events, returncode, stdout_empty, tail_is_api_error):
    """(status, resets_at) for a finished session.

    `tail_is_api_error` is a callable, read only when the session exited 1 with
    nothing on stdout.
    """
    rejected = _rejected_events(events)
    if rejected or _limit_result(events):
        return USAGE_LIMIT, _reset_time(rejected)
    if returncode == 1 and stdout_empty and tail_is_api_error():
        return USAGE_LIMIT, None
    if returncode == 0 and _last_result_succeeded(events):
        return DONE, None
    return FAILED, None


def _decode(output):
    if output is None:
        return ""
    return output.decode("utf-8", errors="replace") if isinstance(output, bytes) else output


def run_session(
    project,
    prompt,
    *,
    repo_root,
    private_root=None,
    plugin=False,
    claude_cmd=None,
    parent_env=None,
    extra_args=(),
    timeout=None,
):
    """Run one headless session in `project` and return a LaunchResult.

    `prompt` goes to the session on stdin. With `plugin` the session loads
    `<repo_root>/plugin`. `extra_args` are appended to the command line.
    A session that outlives `timeout` seconds is killed and returned as `failed`
    with returncode `TIMED_OUT`. Raises Refused when `plugin/` of `repo_root` has
    uncommitted changes.
    """
    repo_root = Path(repo_root)
    private_root = Path(private_root) if private_root is not None else default_private_root()
    head_sha = check_plugin_clean(repo_root)

    parent = os.environ if parent_env is None else parent_env
    env = session_environment(parent, private_root)
    command = resolve_command(claude_cmd, parent)
    command += [
        "-p",
        "--output-format", "stream-json",
        "--verbose",
        "--setting-sources", "project,local",
        "--strict-mcp-config",
    ]
    if plugin:
        command += ["--plugin-dir", str(repo_root / "plugin")]
    command += list(extra_args)

    started = time.time()
    try:
        done = subprocess.run(
            command, input=prompt, cwd=str(project), env=env, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired as expired:
        return LaunchResult(
            status=FAILED, events=_parse_events(_decode(expired.stdout)), returncode=TIMED_OUT,
            head_sha=head_sha, stderr=_decode(expired.stderr),
        )
    events = _parse_events(done.stdout)
    status, resets_at = classify(
        events,
        done.returncode,
        not done.stdout.strip(),
        lambda: _transcript_tail_is_api_error(private_root, project, started),
    )
    return LaunchResult(
        status=status, events=events, returncode=done.returncode,
        resets_at=resets_at, head_sha=head_sha, stderr=done.stderr,
    )
