"""The pool of build topics, and the isolated-session plumbing goals.py and judge.py share.

`pick_topic` asks an isolated session to choose one project it would build and
appends the pick to `<private root>/topics/pool.json` under a random topic id.
The pick is seeded or unseeded. A seeded pick puts attributes chosen by
`seed_attributes` (kind of program, size class, language) in the prompt and the
entry carries those attributes; an unseeded pick lets the reply choose them from
the code-defined classes.

Every session of the three modules goes through `launch.run_session`, starts
from a fresh empty folder under the private root, runs on a pinned model and
appends one `records` row whose role names the module. A session that does not
end `done` raises `SessionError` after its row is written.
"""

import argparse
import json
import os
import random
import re
import secrets
import shutil
import sys
import tempfile
from pathlib import Path

import launch
import records
from launch import default_private_root
from records import Refused

MODEL = "claude-sonnet-4-6"

KINDS = ("cli-tool", "web-service", "library", "game", "data-processing", "automation-script")
SIZES = ("small", "medium", "large")
LANGUAGES = ("python", "typescript", "go", "rust", "java", "csharp")

FORMS = ("seeded", "unseeded")
TOPIC_ID = re.compile(r"t-[0-9a-f]{8}")

# Seconds a topic, goal or judge session may run before it is killed.
SESSION_TIMEOUT = 1800

_FIELDS = ("title", "description", "kind", "size", "language")
_FENCE = re.compile(r"```[a-zA-Z]*\s*\n(.*?)```", re.DOTALL)


class SessionError(Exception):
    """A session ended other than `done`; `status` is `failed` or `usage-limit`."""

    def __init__(self, status, message=None):
        super().__init__(message or f"the session ended {status}")
        self.status = status


def private_dir(private_root=None):
    return Path(private_root) if private_root is not None else default_private_root()


def topics_dir(private_root=None):
    return private_dir(private_root) / "topics"


def check_private_root(private_root=None):
    """Raise Refused when the topics folder would sit inside a git work tree."""
    if records._inside_work_tree(topics_dir(private_root)):
        raise Refused("topic files stay outside git work trees")


def write_json(path, data, exclusive=False):
    """Write `data` as JSON at `path`, whole or not at all. With `exclusive` an
    existing file is an error."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2) + "\n"
    if exclusive:
        with open(path, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        return
    partial = path.with_name(path.name + ".part")
    partial.write_text(text, encoding="utf-8", newline="\n")
    os.replace(partial, path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _reply_text(events):
    """The text of the last `result` event, or an empty string."""
    for event in reversed(events):
        if event.get("type") == "result":
            text = event.get("result")
            return text if isinstance(text, str) else ""
    return ""


def reply_object(text):
    """The first JSON object in `text`: inside a fenced block, else anywhere.
    Raises ValueError when there is none."""
    candidates = [block for block in _FENCE.findall(text)] + [text]
    decoder = json.JSONDecoder()
    for candidate in candidates:
        start = candidate.find("{")
        while start != -1:
            try:
                value, _ = decoder.raw_decode(candidate, start)
            except (ValueError, RecursionError):
                value = None
            if isinstance(value, dict):
                return value
            start = candidate.find("{", start + 1)
    raise ValueError("the reply holds no JSON object")


def run_text_session(
    role, prompt, *, repo_root, private_root=None, claude_cmd=None, parent_env=None,
    model=MODEL, extra_args=(), cwd=None,
):
    """Run one session of `role` and return the text of its final reply.

    The session starts in `cwd`, or in a fresh empty folder under the private
    root that is removed afterwards. Its tokens are recorded whatever the
    outcome; an outcome other than `done` raises SessionError.
    """
    root = private_dir(private_root)
    scratch = None
    if cwd is None:
        parent = root / "sessions"
        parent.mkdir(parents=True, exist_ok=True)
        scratch = Path(tempfile.mkdtemp(prefix=f"{role}-", dir=parent))
        cwd = scratch
    try:
        result = launch.run_session(
            cwd, prompt, repo_root=repo_root, private_root=root, claude_cmd=claude_cmd,
            parent_env=parent_env, extra_args=["--model", model, *extra_args],
            timeout=SESSION_TIMEOUT,
        )
    finally:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
    records.record_session(
        result.events, role=role, outcome=result.status, plugin_sha=result.head_sha, private_root=root,
    )
    if result.status != launch.DONE:
        raise SessionError(result.status)
    return _reply_text(result.events)


def seed_attributes(seed):
    """The kind, size and language a seed stands for; a pure function of `seed`."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("a seed is an integer")
    rng = random.Random(seed)
    return {
        "kind": rng.choice(KINDS),
        "size": rng.choice(SIZES),
        "language": rng.choice(LANGUAGES),
    }


def load_pool(private_root=None):
    path = topics_dir(private_root) / "pool.json"
    if not path.exists():
        return []
    return list(read_json(path)["topics"])


def distinct_classes(entries):
    """The number of distinct (kind, language) pairs among `entries`."""
    return len({(entry["kind"], entry["language"]) for entry in entries})


def choose_form(entries):
    """The form whose entries fill more distinct classes; unseeded on a tie."""
    seeded = distinct_classes([e for e in entries if e["form"] == "seeded"])
    unseeded = distinct_classes([e for e in entries if e["form"] == "unseeded"])
    return "seeded" if seeded > unseeded else "unseeded"


def _pick_prompt(attributes):
    lines = [
        "Pick one software project that you would like to build from nothing, and describe it.",
        "The project is for a person who will use it; it can be built and checked in one working session.",
    ]
    if attributes is None:
        lines.append("Choose the project freely. Place it in the classes below.")
    else:
        lines.append(
            f"The project must be a {attributes['kind']} of {attributes['size']} size written in "
            f"{attributes['language']}. Choose the project inside those attributes and repeat "
            "them in the reply."
        )
    lines += [
        "",
        "Reply with one JSON object and nothing else, with these string fields:",
        '  "title": a short name for the project',
        '  "description": two to four sentences on what the finished project does for its user',
        f'  "kind": one of {", ".join(KINDS)}',
        f'  "size": one of {", ".join(SIZES)}',
        f'  "language": one of {", ".join(LANGUAGES)}',
    ]
    return "\n".join(lines) + "\n"


def _parse_pick(text, seeded):
    reply = reply_object(text)
    for name in _FIELDS:
        value = reply.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"the reply has no usable {name}")
    if not seeded:
        for name, allowed in (("kind", KINDS), ("size", SIZES), ("language", LANGUAGES)):
            if reply[name] not in allowed:
                raise ValueError(f"the reply's {name} is outside the {name} classes")
    return reply


def _new_id(pool):
    taken = {entry["id"] for entry in pool}
    while True:
        topic_id = "t-" + secrets.token_hex(4)
        if topic_id not in taken:
            return topic_id


def pick_topic(*, seeded, seed=None, repo_root, private_root=None, claude_cmd=None, parent_env=None):
    """Run a topic session, append its pick to the pool and return the entry.

    Raises ValueError for a seeded pick without an integer seed or a reply that
    is not a usable pick (the pool is left unchanged), SessionError when the
    session does not end `done`, and Refused when the pool would be written
    inside a git work tree.
    """
    attributes = seed_attributes(seed) if seeded else None
    check_private_root(private_root)
    text = run_text_session(
        "topic", _pick_prompt(attributes), repo_root=repo_root, private_root=private_root,
        claude_cmd=claude_cmd, parent_env=parent_env,
    )
    reply = _parse_pick(text, seeded)
    pool = load_pool(private_root)
    entry = {
        "id": _new_id(pool),
        "form": "seeded" if seeded else "unseeded",
        "seed": seed if seeded else None,
        "title": reply["title"],
        "description": reply["description"],
        "kind": attributes["kind"] if seeded else reply["kind"],
        "size": attributes["size"] if seeded else reply["size"],
        "language": attributes["language"] if seeded else reply["language"],
    }
    write_json(topics_dir(private_root) / "pool.json", {"topics": [*pool, entry]})
    return entry


def main(argv, *, claude_cmd=None, repo_root=None, parent_env=None):
    parser = argparse.ArgumentParser(prog="topics", description="The pool of build topics.")
    parser.add_argument("--private-root", default=None)
    commands = parser.add_subparsers(dest="command", required=True)
    pick = commands.add_parser("pick", help="pick one topic and add it to the pool")
    pick.add_argument("--form", choices=FORMS, required=True)
    pick.add_argument("--seed", type=int, default=None)
    commands.add_parser("list", help="print the topic ids of the pool")
    args = parser.parse_args(argv)

    if args.command == "list":
        for entry in load_pool(args.private_root):
            print(entry["id"])
        return 0

    seeded = args.form == "seeded"
    if seeded and args.seed is None:
        print("a seeded pick needs --seed", file=sys.stderr)
        return 2
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    try:
        entry = pick_topic(
            seeded=seeded, seed=args.seed, repo_root=root, private_root=args.private_root,
            claude_cmd=claude_cmd, parent_env=parent_env,
        )
    except SessionError as error:
        print(f"topic session ended {error.status}", file=sys.stderr)
        return 1
    except (Refused, launch.Refused, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(entry["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
