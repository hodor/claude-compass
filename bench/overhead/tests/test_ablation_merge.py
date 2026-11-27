"""Several batches report as one, a defect planted twice counts once, and
each session's tokens are recorded."""

import json

import ablation
from fake_reply_claude import fake_reply  # noqa: F401  (pytest fixture)


def _entry(project, task, line, letter="L", caught=None):
    caught = caught or {s: s == "validator" for s in ablation.STATIONS}
    return {"project": project, "task": task, "letter": letter, "lang": "python",
            "site": {"path": "a.py", "line": line, "cls": "constant", "col": 4, "old": "1", "new": "2",
                     "function": None, "text": "x = 1"},
            "caught": caught, "rows": {}, "sessions": {}}


def test_a_defect_in_two_batches_counts_once_and_a_second_site_is_kept():
    first = {"done": {"p|TASK-001": _entry("p", "TASK-001", 3)}}
    second = {"done": {"p|TASK-001": _entry("p", "TASK-001", 3), "q|TASK-002": _entry("q", "TASK-002", 5)}}
    third = {"done": {"p|TASK-001": _entry("p", "TASK-001", 9)}, "skipped": {"r|TASK-003": {"letter": "S"}}}
    merged = ablation.merge_batches([first, second, third])
    assert merged["duplicates"] == 1
    assert sorted(merged["done"]) == ["p|TASK-001", "p|TASK-001#2", "q|TASK-002"]
    assert merged["done"]["p|TASK-001#2"]["site"]["line"] == 9
    assert list(merged["skipped"]) == ["r|TASK-003"]
    text = ablation.render_report(merged)
    assert "defects with every station read: 3 of 3" in text
    assert "duplicate defects left out: 1" in text


def test_tokens_by_station_sums_models_and_skips_missing_counts():
    entry = _entry("p", "TASK-001", 3)
    entry["sessions"] = {
        "validator": {"caught": True, "tokens": {"m1": {"input": 2, "output": 5}, "m2": {"output": 1}}},
        "review-style": {"caught": False},
    }
    other = _entry("q", "TASK-002", 3)
    other["sessions"] = {"validator": {"caught": True, "tokens": {"m1": {"output": 4}}}}
    totals = ablation.tokens_by_station([entry, other])
    assert totals["validator"] == {"input": 2, "output": 10}
    assert totals["review-style"] == {}


def test_report_command_takes_several_out_folders(tmp_path, capsys):
    for name, line in (("a", 3), ("b", 3), ("c", 7)):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "progress.json").write_text(
            json.dumps({"config": {}, "done": {"p|TASK-001": _entry("p", "TASK-001", line)}}), encoding="utf-8")
    argv = ["report"] + sum((["--out", str(tmp_path / n)] for n in "abc"), [])
    assert ablation.main(argv) == 0
    out = capsys.readouterr().out
    assert "defects with every station read: 2 of 2" in out
    assert "| L | 2 | 0 |" in out


def test_report_refuses_a_folder_without_progress(tmp_path, capsys):
    assert ablation.main(["report", "--out", str(tmp_path)]) == 1


def test_a_session_records_its_tokens(fake_reply, tmp_path):
    fake_reply.reply("FINDING none\n")
    folder = tmp_path / "work"
    folder.mkdir()
    tokens = {}
    ablation.run_station_session("review-style", folder, "x", private_root=tmp_path / "private",
                                 claude_cmd=fake_reply.command, tokens=tokens)
    assert tokens and all(isinstance(v, dict) for v in tokens.values())
    assert sum(counts.get("output", 0) for counts in tokens.values()) > 0


def test_changed_test_files_keeps_the_first_letter_of_a_modified_tracked_file(tmp_path):
    from test_ablation import _commit, _git

    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    _commit(repo, {"tests/core/test_a.py": "def test_a():\n    pass\n", "src/a.py": "A = 1\n",
                   "tests/old_test.py": "x = 1\n"}, "seed")
    (repo / "tests" / "core" / "test_a.py").write_text("def test_a():\n    assert 0\n", encoding="utf-8")
    (repo / "tests" / "test_b c.py").write_text("def test_b():\n    pass\n", encoding="utf-8")
    _git(repo, "mv", "tests/old_test.py", "tests/new_test.py")
    found = ablation._changed_test_files(repo, "python")
    assert found == ["tests/core/test_a.py", "tests/new_test.py", "tests/test_b c.py"]
