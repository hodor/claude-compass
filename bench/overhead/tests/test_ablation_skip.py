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


def test_a_station_judging_error_leaves_the_rest_of_the_batch_running(tmp_path, fake_reply, capsys, monkeypatch):
    root = tmp_path / "projects"
    repo = root / "proj-ffffff"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "--initial-branch=main")
    _commit(repo, {"pyproject.toml": "[project]\nname='p'\n", ".compass/plans/PLAN-001-x.md": PLAN,
                   "src/__init__.py": ""}, "Seed")
    _commit(repo, {"tests/test_clamp.py": "def test_x():\n    assert True\n"},
            "test(TASK-001): failing tests before implementation")
    _commit(repo, {"src/clamp.py": CLAMP}, "TASK-001: clamp")
    fake_reply.reply("FINDING none\n")
    real = ablation._judge_station

    def flaky(station, *args):
        if station == "tester-post":
            raise FileNotFoundError("gone")
        return real(station, *args)

    monkeypatch.setattr(ablation, "_judge_station", flaky)
    out = tmp_path / "out"
    argv = ["run", "--projects-root", str(root), "--out", str(out), "--per-letter", "1", "--seed", "0",
            "--private-root", str(tmp_path / "private")]
    assert ablation.main(argv, claude_cmd=fake_reply.command) == 0
    sessions = json.loads((out / "progress.json").read_text(encoding="utf-8"))["done"]["proj-ffffff|TASK-001"]["sessions"]
    assert sorted(sessions) == ["review-correctness", "review-style", "validator"]
    assert "station error: FileNotFoundError" in capsys.readouterr().err


def test_a_kept_reply_is_judged_again_without_a_new_session(tmp_path, fake_reply, monkeypatch):
    root = tmp_path / "projects"
    repo = root / "proj-abcdef"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "--initial-branch=main")
    _commit(repo, {"pyproject.toml": "[project]\nname='p'\n", ".compass/plans/PLAN-001-x.md": PLAN,
                   "src/__init__.py": ""}, "Seed")
    _commit(repo, {"tests/test_clamp.py": "def test_x():\n    assert True\n"},
            "test(TASK-001): failing tests before implementation")
    _commit(repo, {"src/clamp.py": CLAMP}, "TASK-001: clamp")
    fake_reply.reply("FINDING none\n")
    real = ablation._judge_station
    calls = {"n": 0}

    def once_broken(station, *args):
        if station == "validator" and calls["n"] == 0:
            calls["n"] += 1
            raise RuntimeError("judging broke")
        return real(station, *args)

    monkeypatch.setattr(ablation, "_judge_station", once_broken)
    out = tmp_path / "out"
    argv = ["run", "--projects-root", str(root), "--out", str(out), "--per-letter", "1", "--seed", "0",
            "--private-root", str(tmp_path / "private")]
    assert ablation.main(argv, claude_cmd=fake_reply.command) == 0
    assert len(fake_reply.calls()) == 4
    assert ablation.main(argv, claude_cmd=fake_reply.command) == 0
    assert len(fake_reply.calls()) == 4
    entry = json.loads((out / "progress.json").read_text(encoding="utf-8"))["done"]["proj-abcdef|TASK-001"]
    assert entry["sessions"]["validator"]["judged_from_saved_reply"] is True
    assert set(entry["caught"]) == set(ablation.STATIONS)
