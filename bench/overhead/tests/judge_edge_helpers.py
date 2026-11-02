"""Builders shared by the judge, topics and goals edge tests.

Each helper writes the private files in the shapes documented at the top of
`test_topics.py`, and runs the judge against the fake reply `claude`.
"""

import sys

import judge
import topic_helpers as helpers


def python_command(code):
    return f'"{sys.executable}" -c "{code}"'


def seed_goal_list(private_root, texts, commands=None):
    """Freeze a pool entry, a goal list of `texts` and a brief; return the items."""
    helpers.write_pool(private_root, [helpers.topic_entry()])
    return helpers.write_goal_files(
        private_root, items=helpers.goal_items(texts, commands)
    )


def all_met_reply(count):
    return helpers.reply_json(
        {
            "items": [
                {"id": f"g{n}", "score": "met", "reason": f"file {n} shows it"}
                for n in range(1, count + 1)
            ]
        }
    )


def run_judge(project, repo, private_root, fake_reply, **extra):
    return judge.judge_project(
        project,
        helpers.TOPIC_ID,
        repo_root=repo,
        private_root=private_root,
        claude_cmd=fake_reply.command,
        **extra,
    )


def write_tree(root, files):
    """Create `files` ({relative posix path: text or bytes}) under `root`."""
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    return root
