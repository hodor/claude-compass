"""A picked task with no compiling mutant is skipped and listed; the batch goes on."""

import json

import ablation
from fake_reply_claude import fake_reply  # noqa: F401  (pytest fixture)
from test_ablation import CLAMP, _commit, _git


PLAN = ("- [x] TASK-001: Clamp - complexity: S, files: [src/clamp.py]\n"
        "- [x] TASK-002: Names - complexity: M, files: [src/names.py]\n")


def test_a_task_with_no_site_is_skipped_and_the_rest_run(tmp_path, fake_reply, capsys):
    root = tmp_path / "projects"
    repo = root / "proj-eeeeee"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "--initial-branch=main")
    _commit(repo, {"pyproject.toml": "[project]\nname='p'\n", ".compass/plans/PLAN-001-x.md": PLAN,
                   "src/__init__.py": ""}, "Seed")
    _commit(repo, {"tests/test_clamp.py": "def test_x():\n    assert True\n"},
            "test(TASK-001): failing tests before implementation")
    _commit(repo, {"src/clamp.py": CLAMP}, "TASK-001: clamp")
    _commit(repo, {"tests/test_names.py": "def test_y():\n    assert True\n"},
            "test(TASK-002): failing tests before implementation")
    _commit(repo, {"src/names.py": 'NAME = "x"\n'}, "TASK-002: a name with no mutation site")
    fake_reply.reply("FINDING none\n")
    out = tmp_path / "out"
    argv = ["run", "--projects-root", str(root), "--out", str(out), "--per-letter", "1", "--seed", "0",
            "--private-root", str(tmp_path / "private")]
    assert ablation.main(argv, claude_cmd=fake_reply.command) == 0
    data = json.loads((out / "progress.json").read_text(encoding="utf-8"))
    assert list(data["skipped"]) == ["proj-eeeeee|TASK-002"]
    assert list(data["done"]) == ["proj-eeeeee|TASK-001"]
    printed = capsys.readouterr().out
    assert "skipped proj-eeeeee|TASK-002 (M)" in printed
    assert ablation.main(argv, claude_cmd=fake_reply.command) == 0
    assert len(fake_reply.calls()) == 4
