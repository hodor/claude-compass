"""Probes for human.py that only the implementation reveals.

The interface is described at the top of test_drive.py.

Adversarial themes: several hook processes reading and writing the same budget
file at once, an item name that occurs inside an unrelated longer word and so
reveals a goal nobody asked about, and the word "done" appearing in the reply
text without being the done flag.
"""

import json
import os
import subprocess
import sys

import pytest

import fake_session_claude as fake
import human
from conftest import OVERHEAD_DIR, REPO_ROOT, TESTS_DIR

WORKERS = 12

WORKER_SCRIPT = """import os, sys, time
import human
import launch

class _Done:
    status = launch.DONE
    events = [{"type": "result", "result": "ok"}]

human.launch.run_session = lambda *a, **k: _Done()
human.records.record_session = lambda *a, **k: None
go, state, rounds = sys.argv[1], sys.argv[2], int(sys.argv[3])
who = human.SimulatedHuman.from_state_file(state)
while not os.path.exists(go):
    time.sleep(0.001)
for _ in range(rounds):
    who.reply("Do you want csv export?")
"""

ROUNDS = 40


def make(tmp_path, repo, private_root, brief, replies, *, budget=100, name="human"):
    cmd = fake.command({"mode": "oneshot", "replies": replies}, tmp_path / f"{name}-specs")
    folder = tmp_path / f"{name}-folder"
    folder.mkdir(exist_ok=True)
    return human.SimulatedHuman(
        brief, folder=folder, repo_root=repo, arm="baseline", state_file=tmp_path / f"{name}-state.json",
        private_root=private_root, claude_cmd=cmd, budget=budget,
    ), cmd


def test_concurrent_answer_processes_all_count_against_the_question_budget(tmp_path, repo, private_root):
    """Adversarial where: every hook call starts its own `human.py answer`
    process, and a count read, incremented in memory and written back without a
    lock lets two processes both read 3 and both write 4; the budget then
    under-counts and the build gets more revealing questions than the brief
    allows. Twelve processes each making 40 revealing replies at once must leave 480 counted."""
    brief = {"items": [{"id": "G1", "name": "csv export", "detail": "header row"}]}
    who, _ = make(tmp_path, repo, private_root, brief, [json.dumps({"text": "yes", "done": False})],
                budget=WORKERS * ROUNDS * 2)
    script = tmp_path / "worker.py"
    script.write_text(WORKER_SCRIPT, encoding="utf-8")
    go = tmp_path / "go"
    env_path = str(OVERHEAD_DIR) + ";" + str(TESTS_DIR) + ";" + str(REPO_ROOT / "plugin" / "cli")
    env = dict(os.environ, PYTHONPATH=env_path.replace(";", os.pathsep))
    workers = [
        subprocess.Popen(
            [sys.executable, str(script), str(go), str(who.state_file), str(ROUNDS)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
        )
        for _ in range(WORKERS)
    ]
    go.write_text("go", encoding="utf-8")
    outputs = [worker.communicate(timeout=300) for worker in workers]

    failures = [stderr for (_, stderr), worker in zip(outputs, workers) if worker.returncode != 0]
    assert not failures, [text[-300:] for text in failures[:2]]
    assert who.questions_used == WORKERS * ROUNDS


@pytest.mark.parametrize(
    "case",
    [
        {"name": "log-in-catalog", "item": "log", "message": "Which catalog format do you want?"},
        {"name": "api-in-capital", "item": "api", "message": "What should the capital letter rule be?"},
    ],
    ids=lambda case: case["name"],
)
def test_an_item_name_inside_a_longer_word_is_not_revealed(tmp_path, repo, private_root, case):
    """Adversarial where: matching the name as a raw substring reveals the
    detail of `log` to a question about a "catalog" and spends a budget unit,
    leaking a goal nobody asked about into a session that must see only what the
    message names."""
    brief = {"items": [{"id": "G1", "name": case["item"], "detail": "DETAIL-HIDDEN-" + case["item"]}]}
    who, cmd = make(tmp_path, repo, private_root, brief, [json.dumps({"text": "ok", "done": False})])

    who.reply(case["message"])

    prompts = [entry["text"] for entry in fake.read_log(cmd) if entry["kind"] == "stdin"]
    assert len(prompts) == 1
    assert "DETAIL-HIDDEN" not in prompts[0]
    assert who.questions_used == 0


@pytest.mark.parametrize(
    "case",
    [
        {"name": "word-done-in-text", "result": '{"text": "done with the header, now the footer", "done": false}',
         "text": "done with the header, now the footer", "done": False},
        {"name": "plain-prose-with-done", "result": "I am done reviewing, please continue",
         "text": "I am done reviewing, please continue", "done": False},
        {"name": "done-key-inside-text-value", "result": '{"text": "{\\"done\\": true}", "done": false}',
         "text": '{"done": true}', "done": False},
        {"name": "fenced-true-flag", "result": '```json\n{"text": "ship it", "done": true}\n```',
         "text": "ship it", "done": True},
    ],
    ids=lambda case: case["name"],
)
def test_done_comes_only_from_the_flag_never_from_the_words_of_the_text(case):
    """Adversarial where: scanning the reply for the word "done" (or for a
    `done: true` embedded in the text value) would end a build the human only
    described as partly finished; only the top-level JSON value true counts."""
    text, done = human.parse_reply(case["result"])

    assert (text, done) == (case["text"], case["done"])
