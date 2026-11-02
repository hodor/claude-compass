"""Shared builders for the topics, goals and judge tests.

They write the private files in the shapes documented at the top of
`test_topics.py`, so a test of one module does not depend on another module to
set up its input.
"""

import json
from pathlib import Path

TOPIC_ID = "t-0a1b2c3d"
TOPIC_TITLE = "Harpsichord tuner"
TOPIC_TEXT = "A command line tool that tunes a harpsichord from a recorded note"
BRIEF_TEXT = "You want the tuner to also print the beat rate between two strings"


def topic_entry(topic_id=TOPIC_ID, **overrides):
    entry = {
        "id": topic_id,
        "form": "unseeded",
        "seed": None,
        "title": TOPIC_TITLE,
        "description": TOPIC_TEXT,
        "kind": "cli-tool",
        "size": "small",
        "language": "python",
    }
    entry.update(overrides)
    return entry


def topics_dir(private_root):
    return Path(private_root) / "topics"


def write_pool(private_root, entries):
    folder = topics_dir(private_root)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pool.json").write_text(json.dumps({"topics": list(entries)}), encoding="utf-8")


def read_pool(private_root):
    path = topics_dir(private_root) / "pool.json"
    return json.loads(path.read_text(encoding="utf-8"))["topics"] if path.exists() else []


def goal_items(texts, commands=None):
    commands = commands or {}
    return [
        {"id": f"g{index}", "text": text, "command": commands.get(index - 1)}
        for index, text in enumerate(texts, start=1)
    ]


def write_goal_files(private_root, topic_id=TOPIC_ID, items=None, brief=BRIEF_TEXT):
    """Write a frozen goal list and a hidden brief the way goals.py stores them."""
    items = items if items is not None else goal_items(["It prints a pitch", "It accepts a wav file"])
    folder = topics_dir(private_root)
    (folder / "goals").mkdir(parents=True, exist_ok=True)
    (folder / "briefs").mkdir(parents=True, exist_ok=True)
    (folder / "goals" / f"{topic_id}.json").write_text(
        json.dumps({"topic_id": topic_id, "items": items}), encoding="utf-8")
    (folder / "briefs" / f"{topic_id}.json").write_text(
        json.dumps({"topic_id": topic_id, "brief": brief}), encoding="utf-8")
    return items


def reply_json(payload):
    """A model reply: prose around a fenced JSON object."""
    return "Here is my answer.\n```json\n" + json.dumps(payload) + "\n```\n"


def read_records(private_root):
    folder = Path(private_root) / "records"
    return [
        json.loads(line)
        for path in sorted(folder.glob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def records_text(private_root):
    folder = Path(private_root) / "records"
    return "".join(path.read_text(encoding="utf-8") for path in sorted(folder.glob("*.jsonl")))
