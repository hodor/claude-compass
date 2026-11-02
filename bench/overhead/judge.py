"""The judge: scores a finished project against its topic's frozen goal list.

`make_copy` copies a project without `.git`, `.compass`, `.claude`, `CLAUDE.md`
and the lines of any `.gitignore` that name Compass or the Claude folder, so
the judge sees the project and not the arm that built it. `judge_project` runs
the goal list's commands in one such copy, runs a judge session in another that
inspects the files and scores each goal item `met`, `partly met` or `not met`
with a reason, and stores the verdict as a new file under
`<private root>/topics/verdicts/`.

The builder's own tests and the validator verdict are stored beside the scores
under `recorded`; they take no part in the counts and are not shown to the judge.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import goals
import launch
import topics
from goals import GoalsMissing  # noqa: F401  (re-exported)
from topics import Refused, SessionError  # noqa: F401  (re-exported)

MODEL = "claude-opus-5-5"

SCORES = ("met", "partly met", "not met")

# Folder and file names left out of a copy, at any depth.
_OMITTED = frozenset({".git", ".compass", ".claude", "CLAUDE.md"})

# The tools a judge session may use: reading only.
JUDGE_TOOLS = "Read,Glob,Grep"

# Characters of a goal command's output kept in a verdict and shown to the judge.
OUTPUT_LIMIT = 20000


class InvalidVerdict(ValueError):
    """The judge's reply does not score every goal item exactly once."""


def _inside(path, folder):
    try:
        Path(path).resolve().relative_to(Path(folder).resolve())
    except ValueError:
        return False
    return True


def _names_compass_or_claude(line):
    lowered = line.lower()
    return "compass" in lowered or ".claude" in lowered or "claude.md" in lowered


def _clean_gitignore(source, target):
    text = Path(source).read_bytes().decode("utf-8", errors="surrogateescape")
    kept = [line for line in text.splitlines(keepends=True) if not _names_compass_or_claude(line)]
    Path(target).write_bytes("".join(kept).encode("utf-8", errors="surrogateescape"))


def _is_link(path):
    """True for a symbolic link or, on Windows, a junction."""
    return os.path.islink(path) or getattr(os.path, "isjunction", lambda _: False)(path)


def make_copy(project, dest):
    """Copy `project` to `dest` without any trace of Compass and return `dest`.

    Links are not copied. Raises Refused when `project` is not a folder or
    `dest` lies inside `project` or already holds files. The project is not
    modified.
    """
    project, dest = Path(project), Path(dest)
    if not project.is_dir():
        raise Refused("the project is not a folder")
    if _inside(dest, project):
        raise Refused("the copy cannot sit inside the project")
    if dest.exists() and any(dest.iterdir()):
        raise Refused("the copy's folder is not empty")
    dest.mkdir(parents=True, exist_ok=True)
    for folder, dirs, files in os.walk(project):
        dirs[:] = [
            name for name in dirs
            if name not in _OMITTED and not _is_link(Path(folder) / name)
        ]
        target = dest / Path(folder).relative_to(project)
        target.mkdir(parents=True, exist_ok=True)
        for name in dirs:
            (target / name).mkdir(exist_ok=True)
        for name in files:
            if name in _OMITTED or _is_link(Path(folder) / name):
                continue
            if name == ".gitignore":
                _clean_gitignore(Path(folder) / name, target / name)
            else:
                shutil.copy2(Path(folder) / name, target / name, follow_symlinks=False)
    return dest


def parse_verdict(text, goal_ids):
    """{goal id: {"score", "reason"}} from a judge reply.

    Raises InvalidVerdict unless every id in `goal_ids` is scored exactly once,
    with one of `SCORES` and a non-blank reason, and no other id appears.
    """
    try:
        reply = topics.reply_object(text)
    except ValueError as error:
        raise InvalidVerdict(str(error)) from error
    items = reply.get("items")
    if not isinstance(items, list):
        raise InvalidVerdict("the reply has no list of items")
    parsed = {}
    for item in items:
        if not isinstance(item, dict):
            raise InvalidVerdict("a scored item is not an object")
        goal_id, score, reason = item.get("id"), item.get("score"), item.get("reason")
        if goal_id not in goal_ids:
            raise InvalidVerdict(f"the reply scores {goal_id!r}, which is not a goal item")
        if goal_id in parsed:
            raise InvalidVerdict(f"the reply scores {goal_id} twice")
        if score not in SCORES:
            raise InvalidVerdict(f"the score of {goal_id} is not one of {', '.join(SCORES)}")
        if not isinstance(reason, str) or not reason.strip():
            raise InvalidVerdict(f"the score of {goal_id} has no reason")
        parsed[goal_id] = {"score": score, "reason": reason}
    missing = [goal_id for goal_id in goal_ids if goal_id not in parsed]
    if missing:
        raise InvalidVerdict(f"the reply does not score {', '.join(missing)}")
    return parsed


def _shell_run(command, cwd, env, timeout):
    """({"exit", "output", "timed_out"}) of one shell command in `cwd`."""
    process = subprocess.Popen(
        command, shell=True, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **launch._group_options(),
    )
    timed_out = False
    try:
        out, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as expired:
        timed_out = True
        out = expired.output
        launch._kill_tree(process)
        try:
            out, _ = process.communicate(timeout=launch.DRAIN_SECONDS)
        except subprocess.TimeoutExpired as again:
            out = again.output or out
    output = launch._decode(out)
    return {
        "exit": None if timed_out else process.returncode,
        "output": output[:OUTPUT_LIMIT],
        "timed_out": timed_out,
    }


def command_environment(env, sandbox):
    """`env` with the home, application-data, XDG and temporary folders moved
    into `sandbox`, so a command cannot reach the running user's own folders."""
    sandbox = Path(sandbox)
    home = sandbox / "home"
    temp = sandbox / "tmp"
    moved = {
        "HOME": home,
        "USERPROFILE": home,
        "APPDATA": home / "AppData" / "Roaming",
        "LOCALAPPDATA": home / "AppData" / "Local",
        "XDG_CONFIG_HOME": home / ".config",
        "XDG_CACHE_HOME": home / ".cache",
        "XDG_DATA_HOME": home / ".local" / "share",
        "XDG_STATE_HOME": home / ".local" / "state",
        "TMPDIR": temp,
        "TEMP": temp,
        "TMP": temp,
    }
    result = {
        key: value for key, value in env.items()
        if key.upper() not in moved and not key.upper().startswith("XDG_")
        and key.upper() not in ("HOMEDRIVE", "HOMEPATH")
    }
    for key, folder in moved.items():
        folder.mkdir(parents=True, exist_ok=True)
        result[key] = str(folder)
    return result


def _run_commands(items, folder, env, timeout):
    return {
        item["id"]: _shell_run(item["command"], folder, env, timeout)
        for item in items if item.get("command")
    }


def _judge_prompt(items, commands):
    lines = [
        "You are judging a finished software project. Its files are in the current folder.",
        "Inspect the files and score each goal item below as exactly one of: "
        + ", ".join(f'"{score}"' for score in SCORES) + ".",
        "Give for each score a reason that names the file, or quotes the command output, "
        "that shows it. Score what the project does, from the files; do not assume that "
        "something works because a document says it does.",
        "",
        "Goal items:",
    ]
    for item in items:
        lines.append(f"{item['id']}: {item['text']}")
        run = commands.get(item["id"])
        if run is None:
            continue
        status = "timed out" if run["timed_out"] else f"exit {run['exit']}"
        lines.append(f"  command: {item['command']}")
        lines.append(f"  command result: {status}")
        lines.append("  command output:")
        lines += [f"    {line}" for line in run["output"].splitlines()]
    lines += [
        "",
        "Reply with one JSON object and nothing else, scoring every goal item exactly once:",
        '  {"items": [{"id": "g1", "score": "met", "reason": "..."}, ...]}',
    ]
    return "\n".join(lines) + "\n"


def _counts(scores):
    counts = dict.fromkeys(SCORES, 0)
    for entry in scores.values():
        counts[entry["score"]] += 1
    return counts


def _store(verdict, private_root, topic_id):
    folder = topics.topics_dir(private_root) / "verdicts"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    while True:
        path = folder / f"{topic_id}-{stamp}-{os.urandom(3).hex()}.json"
        verdict["file"] = str(path)
        try:
            topics.write_json(path, verdict, exclusive=True)
        except FileExistsError:
            continue
        return path


def judge_project(
    project, topic_id, *, repo_root, builder_tests=None, validator_verdict=None,
    command_timeout=60, private_root=None, claude_cmd=None, parent_env=None,
):
    """Score the finished `project` against the frozen goals of `topic_id`.

    Returns the verdict dict and stores it as a new file. Raises Refused inside
    a git work tree and GoalsMissing without a frozen goal list (both before a
    session starts), SessionError when the judge session does not end `done`,
    and InvalidVerdict when its reply does not score every item exactly once.
    """
    topics.check_private_root(private_root)
    if not Path(project).is_dir():
        raise Refused("the project is not a folder")
    goal_list = goals.require_goals(topic_id, private_root)
    items = goal_list["items"]

    root = topics.private_dir(private_root)
    sessions = root / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="judge-", dir=sessions))
    try:
        run_copy = make_copy(project, scratch / "run")
        judged_copy = make_copy(project, scratch / "judged")
        env = command_environment(
            launch.session_environment(os.environ if parent_env is None else parent_env, root),
            scratch / "sandbox",
        )
        commands = _run_commands(items, run_copy, env, command_timeout)
        reply = topics.run_text_session(
            "judge", _judge_prompt(items, commands), repo_root=repo_root, private_root=root,
            claude_cmd=claude_cmd, parent_env=parent_env, model=MODEL,
            extra_args=["--allowedTools", JUDGE_TOOLS], cwd=judged_copy,
        )
    finally:
        topics.remove_tree(scratch)

    scores = parse_verdict(reply, [item["id"] for item in items])
    verdict = {
        "topic_id": topic_id,
        "scores": scores,
        "counts": _counts(scores),
        "commands": commands,
        "recorded": {"builder_tests": builder_tests, "validator_verdict": validator_verdict},
    }
    _store(verdict, private_root, topic_id)
    return verdict


def main(argv, *, claude_cmd=None, repo_root=None, parent_env=None):
    parser = argparse.ArgumentParser(prog="judge", description="Score a finished project.")
    parser.add_argument("--private-root", default=None)
    parser.add_argument("--builder-tests", default=None)
    parser.add_argument("--validator-verdict", default=None)
    parser.add_argument("project")
    parser.add_argument("topic_id")
    args = parser.parse_args(argv)
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    try:
        verdict = judge_project(
            args.project, args.topic_id, repo_root=root, private_root=args.private_root,
            builder_tests=args.builder_tests, validator_verdict=args.validator_verdict,
            claude_cmd=claude_cmd, parent_env=parent_env,
        )
    except SessionError as error:
        print(f"judge session ended {error.status}", file=sys.stderr)
        return 1
    except (GoalsMissing, InvalidVerdict, Refused, launch.Refused) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(verdict["counts"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
