"""Tests for judge.py: the blinded copy of a finished project, the verdict parser
and the judge session.

The interface is documented at the top of `test_topics.py`. `judge_project`
returns the verdict and stores it as a new file under
`<private_root>/topics/verdicts/`:

    {"topic_id": str,
     "scores": {"g1": {"score": "met" | "partly met" | "not met", "reason": str}, ...},
     "counts": {"met": int, "partly met": int, "not met": int},
     "commands": {"g1": {"exit": int | None, "output": str, "timed_out": bool}, ...},
     "recorded": {"builder_tests": any, "validator_verdict": any},
     "file": str}

`commands` holds one entry per goal item that has a command, run through the
shell inside the copy. The judge reply is one JSON object
{"items": [{"id": "g1", "score": "met", "reason": "..."}]}.

Adversarial themes: a copy that still shows Compass lets the judge score the
arm instead of the project; a verdict that skips an item silently lowers or
raises the score; recorded signals that leak into the counts reintroduce the
success measures the plan refuses to count; goal commands run in the real
project or with the parent's credentials damage the measurement.
"""

import ast
import json
import os
import sys
from pathlib import Path

import pytest

import goals
import judge
import topic_helpers as helpers
import topics
from fake_reply_claude import fake_reply  # noqa: F401  (pytest fixture)

BLIND_NEEDLES = (".compass", "spec-", "task-", "compass")
BINARY = bytes(range(256)) + b"\r\n\r\n" + bytes(range(255, -1, -1))
GITIGNORE_KEPT = ["node_modules/", "*.pyc", "dist/"]
GITIGNORE_LINES = ["node_modules/", ".compass/", "*.pyc", "# Compass local install", ".compass/tmp/", "dist/"]


def python_command(code):
    return f'"{sys.executable}" -c "{code}"'


@pytest.fixture
def built(tmp_path, git):
    """A finished project that still shows its Compass install."""
    root = tmp_path / "work" / "proj-built"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("print('pitch')\n", encoding="utf-8")
    (root / "README.md").write_text("# Tuner\nTunes a harpsichord.\n", encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "logo.bin").write_bytes(BINARY)
    (root / ".gitignore").write_text("\n".join(GITIGNORE_LINES) + "\n", encoding="utf-8")
    (root / ".compass" / "specs").mkdir(parents=True)
    (root / ".compass" / "specs" / "SPEC-001-tuner.md").write_text("spec\n", encoding="utf-8")
    (root / ".claude" / "skills").mkdir(parents=True)
    (root / ".claude" / "settings.local.json").write_text("{}\n", encoding="utf-8")
    (root / "CLAUDE.md").write_text("project rules\n", encoding="utf-8")
    git(root, "init", "-q")
    return root


def visible_paths(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def verdict_reply(scores=("met", "partly met", "not met"), reasons=None):
    reasons = reasons or ["src/app.py prints a pitch zzquux", "tests absent zzquux", "readme lists no options zzquux"]
    return helpers.reply_json({"items": [
        {"id": f"g{n}", "score": score, "reason": reason}
        for n, (score, reason) in enumerate(zip(scores, reasons), start=1)]})


def seed_goals(private_root, commands=None):
    helpers.write_pool(private_root, [helpers.topic_entry()])
    return helpers.write_goal_files(
        private_root,
        items=helpers.goal_items(["It prints a pitch", "It has tests", "It documents options"], commands),
    )


def run(built, repo, private_root, fake_reply, **extra):
    return judge.judge_project(
        built, helpers.TOPIC_ID, repo_root=repo, private_root=private_root,
        claude_cmd=fake_reply.command, **extra)


def verdict_files(private_root):
    return sorted((helpers.topics_dir(private_root) / "verdicts").glob("*.json"))


def test_make_copy_leaves_no_trace_of_compass_and_spares_the_source(built, tmp_path):
    """Adversarial where: a copy that keeps any of .git, .compass, .claude,
    CLAUDE.md or Compass lines in .gitignore lets the judge see the arm; a copy
    made in place, or one that mangles bytes, damages the finished project."""
    dest = tmp_path / "copy"
    result = judge.make_copy(built, dest)

    assert Path(result) == dest
    assert visible_paths(dest) == [".gitignore", "README.md", "assets/logo.bin", "src/app.py"]
    assert not any((dest / name).exists() for name in (".git", ".compass", ".claude", "CLAUDE.md"))
    assert (dest / ".gitignore").read_text(encoding="utf-8").splitlines() == GITIGNORE_KEPT
    assert (dest / "assets" / "logo.bin").read_bytes() == BINARY

    for path in dest.rglob("*"):
        assert not any(needle in path.name.lower() for needle in BLIND_NEEDLES), path
        if path.is_file():
            text = path.read_bytes().decode("latin-1").lower()
            assert not any(needle in text for needle in BLIND_NEEDLES), path

    assert (built / ".git").is_dir()
    assert (built / ".compass" / "specs" / "SPEC-001-tuner.md").exists()
    assert (built / ".claude" / "settings.local.json").exists()
    assert (built / "CLAUDE.md").read_text(encoding="utf-8") == "project rules\n"
    assert (built / ".gitignore").read_text(encoding="utf-8").splitlines() == GITIGNORE_LINES


def test_make_copy_refuses_a_destination_inside_the_project(built):
    """Adversarial where: copying a folder into itself recurses until the disk
    fills."""
    with pytest.raises(judge.Refused):
        judge.make_copy(built, built / "src" / "copy")
    assert not (built / "src" / "copy").exists()


def test_parse_verdict_scores_every_goal_item_exactly_once():
    """Adversarial where: a verdict that skips an item, repeats one, names an
    unknown one, uses a score outside the three, or gives no reason would be scored
    as if complete."""
    ids = ["g1", "g2", "g3"]

    def reply(items):
        return helpers.reply_json({"items": items})

    def item(n, score="met", reason="src/app.py line 1"):
        return {"id": f"g{n}", "score": score, "reason": reason}

    parsed = judge.parse_verdict(
        reply([item(3, "not met"), item(1), item(2, "partly met", "output: 2 passed")]), ids)
    assert parsed == {
        "g1": {"score": "met", "reason": "src/app.py line 1"},
        "g2": {"score": "partly met", "reason": "output: 2 passed"},
        "g3": {"score": "not met", "reason": "src/app.py line 1"},
    }

    bad = {
        "prose": "I think it is fine.",
        "not-an-object": "[1]",
        "items-not-a-list": helpers.reply_json({"items": "g1 met"}),
        "skips-last": reply([item(1), item(2)]),
        "skips-middle": reply([item(1), item(3)]),
        "empty": reply([]),
        "duplicate": reply([item(1), item(2), item(3), item(2)]),
        "unknown-id": reply([item(1), item(2), item(3), item(9)]),
        "unknown-instead-of-known": reply([item(1), item(2), item(9)]),
        "score-partial": reply([item(1), item(2), item(3, "partial")]),
        "score-capitalised": reply([item(1), item(2), item(3, "Met")]),
        "score-missing": reply([item(1), item(2), {"id": "g3", "reason": "r"}]),
        "reason-blank": reply([item(1), item(2), item(3, reason="  ")]),
        "reason-missing": reply([item(1), item(2), {"id": "g3", "score": "met"}]),
    }
    assert issubclass(judge.InvalidVerdict, ValueError)
    for name, text in bad.items():
        with pytest.raises(judge.InvalidVerdict):
            judge.parse_verdict(text, ids)


def test_judge_project_scores_a_blinded_copy_and_stores_the_verdict(built, repo, private_root, fake_reply):
    """Adversarial where: a judge session started in the real project, shown the
    hidden brief or Compass, or counts that let recorded builder tests or the
    validator verdict move the score, or a second verdict overwriting the first,
    or reasons reaching the record row."""
    seed_goals(private_root)
    fake_reply.reply(verdict_reply())

    first = run(built, repo, private_root, fake_reply, builder_tests="12 passed", validator_verdict="PASS")
    second = run(built, repo, private_root, fake_reply, builder_tests="0 passed", validator_verdict="FAIL")

    call = fake_reply.calls()[0]
    cwd = Path(call["cwd"])
    assert cwd.resolve() != built.resolve()
    assert cwd.resolve().is_relative_to(private_root.resolve())
    assert "src/app.py" in call["listing"]
    assert not [n for n in call["listing"] if n.split("/")[0] in (".git", ".compass", ".claude", "CLAUDE.md")]
    for text in ("It prints a pitch", "It has tests", "It documents options"):
        assert text in call["stdin"]
    assert helpers.BRIEF_TEXT not in call["stdin"]
    assert "compass" not in call["stdin"].lower()
    argv = call["argv"]
    assert argv[argv.index("--model") + 1] == judge.MODEL

    assert first["scores"]["g2"] == {"score": "partly met", "reason": "tests absent zzquux"}
    assert first["counts"] == {"met": 1, "partly met": 1, "not met": 1}
    assert second["counts"] == first["counts"]
    assert first["recorded"] == {"builder_tests": "12 passed", "validator_verdict": "PASS"}
    assert second["recorded"] == {"builder_tests": "0 passed", "validator_verdict": "FAIL"}
    assert first["topic_id"] == helpers.TOPIC_ID

    files = verdict_files(private_root)
    assert len(files) == 2
    stored = {json.loads(p.read_text(encoding="utf-8"))["recorded"]["validator_verdict"] for p in files}
    assert stored == {"PASS", "FAIL"}
    assert Path(first["file"]) in files

    assert (built / ".compass").is_dir() and (built / ".git").is_dir()
    assert [(r["role"], r["outcome"]) for r in helpers.read_records(private_root)] == [("judge", "done")] * 2
    assert "zzquux" not in helpers.records_text(private_root)


def test_goal_commands_run_in_the_copy_with_a_clean_environment(built, repo, private_root, fake_reply):
    """Adversarial where: a goal command run in the real project, with the parent's
    credentials, with no time limit, or whose failure is hidden, distorts the
    measurement or leaks secrets into builder-written scripts."""
    commands = {
        0: python_command("import os; print(sorted(os.listdir('.')))"),
        1: python_command("import sys; print('boom'); sys.exit(3)"),
        2: python_command("import os; print(os.environ.get('ANTHROPIC_API_KEY', 'absent'))"),
    }
    seed_goals(private_root, commands)
    fake_reply.reply(verdict_reply())
    parent = {**os.environ, "ANTHROPIC_API_KEY": "sk-should-not-travel"}
    verdict = run(built, repo, private_root, fake_reply, parent_env=parent)

    listing = ast.literal_eval(verdict["commands"]["g1"]["output"].strip())
    assert listing == [".gitignore", "README.md", "assets", "src"]
    assert verdict["commands"]["g2"]["exit"] == 3
    assert "boom" in verdict["commands"]["g2"]["output"]
    assert verdict["commands"]["g2"]["timed_out"] is False
    assert verdict["commands"]["g3"]["output"].strip() == "absent"
    assert verdict["commands"]["g1"]["exit"] == 0


def test_goal_command_that_outlives_its_timeout_is_cut_and_marked(built, repo, private_root, fake_reply):
    """Adversarial where: a hung goal command (a server that never exits) must not
    stall the judge; it is recorded as timed out, not as a pass or a missing
    entry, and the other commands still run."""
    commands = {
        0: python_command("import time; time.sleep(8)"),
        1: python_command("print('after')"),
    }
    seed_goals(private_root, commands)
    fake_reply.reply(verdict_reply())
    verdict = run(built, repo, private_root, fake_reply, command_timeout=1)

    assert verdict["commands"]["g1"]["timed_out"] is True
    assert verdict["commands"]["g1"]["exit"] is None
    assert verdict["commands"]["g2"]["output"].strip() == "after"
    assert verdict["commands"]["g2"]["timed_out"] is False
    assert "g3" not in verdict["commands"]


def test_commands_never_touch_the_source_project(built, repo, private_root, fake_reply):
    """Adversarial where: a goal command that writes a file lands it in the finished
    project instead of the throwaway copy."""
    seed_goals(private_root, {0: python_command("open('ran.txt', 'w').write('x')")})
    fake_reply.reply(verdict_reply())
    before = visible_paths(built)
    verdict = run(built, repo, private_root, fake_reply)
    assert verdict["commands"]["g1"]["exit"] == 0
    assert visible_paths(built) == before
    assert not (built / "ran.txt").exists()


def test_an_invalid_verdict_stores_nothing_but_the_session_is_recorded(built, repo, private_root, fake_reply):
    """Adversarial where: a verdict that skips an item and is stored anyway is
    scored as if the item had not been asked; the tokens it cost still count."""
    seed_goals(private_root)
    fake_reply.reply(verdict_reply(scores=("met", "met"), reasons=["a", "b"]))
    with pytest.raises(judge.InvalidVerdict):
        run(built, repo, private_root, fake_reply)
    assert verdict_files(private_root) == []
    assert [r["role"] for r in helpers.read_records(private_root)] == ["judge"]


@pytest.mark.parametrize("mode, status", [("limit", "usage-limit"), ("crash", "failed")])
def test_judge_session_failure_raises_with_its_status(built, repo, private_root, fake_reply, mode, status):
    """Adversarial where: a usage-limit session must not become a verdict of
    nothing met."""
    seed_goals(private_root)
    fake_reply.mode(mode)
    with pytest.raises(topics.SessionError) as raised:
        run(built, repo, private_root, fake_reply)
    assert raised.value.status == status
    assert verdict_files(private_root) == []


def test_judging_needs_a_frozen_goal_list(built, repo, private_root, fake_reply):
    """Adversarial where: judging a topic whose goal list was never frozen would
    invent the target after the build."""
    helpers.write_pool(private_root, [helpers.topic_entry()])
    fake_reply.reply(verdict_reply())
    with pytest.raises(goals.GoalsMissing):
        run(built, repo, private_root, fake_reply)
    assert fake_reply.calls() == []


def test_verdicts_are_refused_inside_a_git_work_tree(built, repo, tmp_path, git, fake_reply):
    """Adversarial where: a verdict stored under a git work tree can be committed
    by accident; the refusal comes before the session is paid for."""
    work_tree = tmp_path / "wt"
    work_tree.mkdir()
    git(work_tree, "init", "-q")
    inside = work_tree / "overhead"
    seed_goals(inside)
    fake_reply.reply(verdict_reply())
    with pytest.raises(judge.Refused):
        run(built, repo, inside, fake_reply)
    assert fake_reply.calls() == []
    assert verdict_files(inside) == []
