"""Frozen goal lists and hidden briefs for the pool's topics.

`write_goals` runs a goal session, separate from any build, that turns a pool
entry into a list of items checkable in the finished project (with a command to
run where one exists) and a hidden brief for the simulated human. Both are
stored under `<private root>/topics/` before any build of the topic:

    goals/<topic id>.json    {"topic_id": str, "items": [{"id", "text", "command"}, ...]}
    briefs/<topic id>.json   {"topic_id": str, "brief": str}

Once either file exists the topic is frozen: `write_goals` refuses to run again.
A build and a judgement of a topic start from `require_goals`.
"""

import argparse
import sys
from pathlib import Path

import launch
import topics
from topics import MODEL, Refused, SessionError, TOPIC_ID  # noqa: F401  (re-exported)


class UnknownTopic(LookupError):
    """The topic id is not in the pool."""


class AlreadyFrozen(Exception):
    """The topic already has a goal list or a brief."""


class GoalsMissing(LookupError):
    """The topic lacks its goal list or its brief."""


def _goals_path(topic_id, private_root):
    return topics.topics_dir(private_root) / "goals" / f"{topic_id}.json"


def _brief_path(topic_id, private_root):
    return topics.topics_dir(private_root) / "briefs" / f"{topic_id}.json"


def _load(path, topic_id, what):
    if not isinstance(topic_id, str) or not TOPIC_ID.fullmatch(topic_id) or not path.is_file():
        raise GoalsMissing(f"topic {topic_id!r} has no {what}")
    try:
        data = topics.read_json(path)
    except (ValueError, OSError) as error:
        raise GoalsMissing(f"topic {topic_id!r} has an unreadable {what}") from error
    if not isinstance(data, dict):
        raise GoalsMissing(f"topic {topic_id!r} has an unreadable {what}")
    return data


def load_goals(topic_id, private_root=None):
    """{"topic_id", "items"} of a frozen goal list; GoalsMissing when absent."""
    return _load(_goals_path(topic_id, private_root), topic_id, "goal list")


def load_brief(topic_id, private_root=None):
    """The hidden brief text; GoalsMissing when absent."""
    data = _load(_brief_path(topic_id, private_root), topic_id, "brief")
    brief = data.get("brief")
    if not isinstance(brief, str):
        raise GoalsMissing(f"topic {topic_id!r} has an unreadable brief")
    return brief


def require_goals(topic_id, private_root=None):
    """The goal dict of `topic_id`; GoalsMissing unless the list and the brief both exist."""
    goals = load_goals(topic_id, private_root)
    load_brief(topic_id, private_root)
    return goals


def _goal_prompt(entry):
    return (
        "A person asked for the software project described below, and an engineer will build it.\n"
        "\n"
        f"Title: {entry['title']}\n"
        f"Description: {entry['description']}\n"
        f"Kind: {entry['kind']}; size: {entry['size']}; language: {entry['language']}\n"
        "\n"
        "Write two things.\n"
        "\n"
        "1. A goal list: the things the finished project must do, each checkable by reading the "
        "files or running the project. Write each as one plain sentence stating a result. Where "
        "a shell command run in the project folder shows the result, give it as the item's "
        "command; otherwise leave the command null. Cover the whole project, in about five to "
        "twelve items.\n"
        "2. A brief: the person's private notes for answering the engineer's questions. For each "
        "goal item, say in the person's own words what they want and why, so a question about "
        "that item can be answered from the notes. Add the person's preferences and anything "
        "they do not care about. The notes hold no instructions on how to build.\n"
        "\n"
        "Reply with one JSON object and nothing else:\n"
        '  {"items": [{"text": "...", "command": "..." or null}, ...], "brief": "..."}\n'
    )


def _text(value, what):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} is not a non-blank string")
    return value.strip()


def _parse_goals(text):
    """([{"id", "text", "command"}], brief) from a goal session's reply."""
    reply = topics.reply_object(text)
    raw = reply.get("items")
    if not isinstance(raw, list) or not raw:
        raise ValueError("the reply has no goal items")
    items = []
    for number, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"goal item {number} is not an object")
        command = item.get("command")
        if command is not None:
            command = _text(command, f"the command of goal item {number}") if command != "" else None
        items.append({"id": f"g{number}", "text": _text(item.get("text"), f"goal item {number}"), "command": command})
    return items, _text(reply.get("brief"), "the brief")


def write_goals(topic_id, *, repo_root, private_root=None, claude_cmd=None, parent_env=None):
    """Freeze the goal list and brief of `topic_id` and return {"items", "brief"}.

    Raises UnknownTopic for an id outside the pool, AlreadyFrozen when either
    file exists, Refused inside a git work tree (all before a session starts),
    SessionError when the session does not end `done`, and ValueError for a
    reply that does not give a usable list and brief (nothing is stored).
    """
    entry = None
    if isinstance(topic_id, str) and TOPIC_ID.fullmatch(topic_id):
        entry = next((e for e in topics.load_pool(private_root) if e["id"] == topic_id), None)
    if entry is None:
        raise UnknownTopic(f"topic {topic_id!r} is not in the pool")
    topics.check_private_root(private_root)
    if _goals_path(topic_id, private_root).exists() or _brief_path(topic_id, private_root).exists():
        raise AlreadyFrozen(f"topic {topic_id} already has frozen goals")

    text = topics.run_text_session(
        "goal", _goal_prompt(entry), repo_root=repo_root, private_root=private_root,
        claude_cmd=claude_cmd, parent_env=parent_env, model=MODEL,
    )
    items, brief = _parse_goals(text)
    topics.write_json(_brief_path(topic_id, private_root), {"topic_id": topic_id, "brief": brief}, exclusive=True)
    topics.write_json(_goals_path(topic_id, private_root), {"topic_id": topic_id, "items": items}, exclusive=True)
    return {"items": items, "brief": brief}


def main(argv, *, claude_cmd=None, repo_root=None, parent_env=None):
    parser = argparse.ArgumentParser(prog="goals", description="Freeze the goals of a topic.")
    parser.add_argument("--private-root", default=None)
    parser.add_argument("topic_id")
    args = parser.parse_args(argv)
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    try:
        result = write_goals(
            args.topic_id, repo_root=root, private_root=args.private_root,
            claude_cmd=claude_cmd, parent_env=parent_env,
        )
    except SessionError as error:
        print(f"goal session ended {error.status}", file=sys.stderr)
        return 1
    except (UnknownTopic, AlreadyFrozen, Refused, launch.Refused, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(len(result["items"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
