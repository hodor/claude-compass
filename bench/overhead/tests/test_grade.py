"""Tests for grade.py: the grading copies, the sheets and the judge's agreement.

Adversarial themes: a copy that shows the arm or Compass lets the grader guess
the arm; a mismatched verdict file gives the wrong agreement; a sheet with a
blank or unknown mark must not count; the report section must hold counts only.
"""

import json
import os
from pathlib import Path

import pytest

import grade
import topic_helpers as helpers

TOPIC_A = "t-aaaaaaaa"
TOPIC_B = "t-bbbbbbbb"
GOAL_TEXTS = {
    TOPIC_A: ["Zebra mode prints stripes", "Quokka flag is accepted", "Narwhal export works"],
    TOPIC_B: ["Okapi reader parses input", "Axolotl output is sorted"],
}
FORBIDDEN_NAMES = {".git", ".compass", ".claude", "CLAUDE.md"}
DASHES = (chr(0x2013), chr(0x2014))


def write_project(folder, extra=None):
    """A finished project plus every trace a Compass build leaves."""
    folder = Path(folder)
    (folder / ".git").mkdir(parents=True)
    (folder / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (folder / ".compass" / "specs").mkdir(parents=True)
    (folder / ".compass" / "specs" / "SPEC-001-x.md").write_text("TASK-001 body", encoding="utf-8")
    (folder / ".claude").mkdir()
    (folder / ".claude" / "settings.local.json").write_text("{}", encoding="utf-8")
    (folder / "CLAUDE.md").write_text("compass rules", encoding="utf-8")
    (folder / ".gitignore").write_text("build/\n.compass/\n.claude/\nnotes.txt\n", encoding="utf-8")
    (folder / "src").mkdir()
    (folder / "src" / "main.py").write_text("print('stripes')\n", encoding="utf-8")
    (folder / "src" / ".claude").mkdir()
    (folder / "src" / ".claude" / "deep.json").write_text("{}", encoding="utf-8")
    (folder / "node_modules" / "pkg").mkdir(parents=True)
    (folder / "node_modules" / "pkg" / "index.js").write_text("compass SPEC-9", encoding="utf-8")
    (folder / ".venv").mkdir()
    (folder / ".venv" / "pyvenv.cfg").write_text("compass", encoding="utf-8")
    for name, text in (extra or {}).items():
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
    return folder


def tree_text(root):
    """Every relative path and every file's text under `root`, lower-cased."""
    parts = []
    for folder, dirs, files in os.walk(root):
        for name in (*dirs, *files):
            parts.append(os.path.relpath(Path(folder) / name, root).lower())
        for name in files:
            parts.append((Path(folder) / name).read_text(encoding="utf-8", errors="replace").lower())
    return "\n".join(parts)


def names_under(root):
    return {name for _, dirs, files in os.walk(root) for name in (*dirs, *files)}


def judged_scores(topic_id, marks):
    return {
        f"g{n}": {"score": mark, "reason": "reason text"} for n, mark in enumerate(marks, start=1)
    }


def counts_of(marks):
    return {name: marks.count(name) for name in grade.SCORES}


class World:
    """A private root with a pilot run log, goals, verdict files and projects."""

    def __init__(self, private_root, tmp_path):
        self.root = Path(private_root)
        self.tmp = tmp_path
        self.log = []
        self.projects = {}
        self.stamp = 0
        helpers.write_pool(self.root, [
            helpers.topic_entry(TOPIC_A), helpers.topic_entry(TOPIC_B, title="Other"),
        ])
        for topic_id, texts in GOAL_TEXTS.items():
            helpers.write_goal_files(self.root, topic_id, helpers.goal_items(texts))
            self.log.append({"event": "picked", "stage": "pilot", "topic": topic_id, "form": "seeded", "seed": 1})

    def add_verdict(self, topic_id, marks):
        self.stamp += 1
        path = self.root / "topics" / "verdicts" / f"{topic_id}-20261105T{self.stamp:06d}Z-abc{self.stamp:03d}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "topic_id": topic_id, "scores": judged_scores(topic_id, marks), "counts": counts_of(marks),
        }), encoding="utf-8")
        return path

    def add_build(self, topic_id, arm, run, marks, end="human-done", leaky=False, judged=True):
        project = write_project(
            self.tmp / "projects" / f"proj-{len(self.projects):06x}",
            {"docs/SPEC-004.md": "details"} if leaky else None,
        )
        self.projects[(topic_id, arm, run)] = project
        self.log.append({
            "event": "build-closed", "topic": topic_id, "arm": arm, "run": run,
            "exit": 0 if end == "human-done" else 1, "end": end, "project": str(project),
        })
        if judged:
            self.add_verdict(topic_id, marks)
            self.log.append({
                "event": "judged", "topic": topic_id, "arm": arm, "run": run, "counts": counts_of(marks),
            })
        return project

    def write_log(self):
        path = self.root / "pilot" / "run-log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(event) + "\n" for event in self.log), encoding="utf-8")
        return path


@pytest.fixture
def world(private_root, tmp_path):
    w = World(private_root, tmp_path)
    w.add_build(TOPIC_A, "compass", 1, ["met", "partly met", "not met"])
    w.add_build(TOPIC_A, "baseline", 1, ["met", "met", "partly met"])
    w.add_build(TOPIC_A, "baseline", 2, ["met", "partly met", "partly met"])
    w.add_build(TOPIC_A, "compass", 2, ["not met", "partly met", "not met"], end="wall-time")
    w.add_build(TOPIC_B, "baseline", 1, ["met", "met"])
    w.add_build(TOPIC_B, "compass", 1, ["met", "not met"], end="wall-time")
    w.write_log()
    return w


# the copy


def test_copy_carries_no_trace_of_compass_or_the_arm(tmp_path):
    project = write_project(tmp_path / "proj-1")
    copy = grade.make_grading_copy(project, tmp_path / "copy")
    assert not (names_under(copy) & FORBIDDEN_NAMES)
    text = tree_text(copy)
    for word in ("compass", ".claude", "claude.md", "baseline", "spec-", "task-"):
        assert word not in text
    assert (copy / "src" / "main.py").read_text(encoding="utf-8") == "print('stripes')\n"


def test_copy_keeps_the_clean_lines_of_gitignore(tmp_path):
    copy = grade.make_grading_copy(write_project(tmp_path / "proj-1"), tmp_path / "copy")
    assert (copy / ".gitignore").read_text(encoding="utf-8") == "build/\nnotes.txt\n"


def test_copy_leaves_dependency_folders_out(tmp_path):
    copy = grade.make_grading_copy(write_project(tmp_path / "proj-1"), tmp_path / "copy")
    assert not (copy / "node_modules").exists() and not (copy / ".venv").exists()


def test_the_project_is_not_modified(tmp_path):
    project = write_project(tmp_path / "proj-1")
    before = tree_text(project)
    grade.make_grading_copy(project, tmp_path / "copy")
    assert tree_text(project) == before


@pytest.mark.parametrize("name", ["docs/SPEC-1.md", "TASK-2/readme.txt", "src/CLAUDE.MD", "x/.Compass/y.txt"])
def test_a_file_name_that_shows_compass_refuses_the_copy_before_writing(tmp_path, name):
    folder = tmp_path / "proj-1"
    project = write_project(folder)
    if name.startswith("x/"):
        (project / "x").mkdir()
        (project / "x" / ".Compass").write_text("x", encoding="utf-8")
    else:
        target = project / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("plain", encoding="utf-8")
    with pytest.raises(grade.Leaky) as caught:
        grade.make_grading_copy(project, tmp_path / "copy")
    assert caught.value.paths
    assert not (tmp_path / "copy").exists()


SCRUBBED = (
    "TASK-009 checks the README (SPEC-002-floor-generation/D-01), see PLAN-001 and ADR-005.\r\n"
    "State lives in .compass/tmp and .claude/worktrees, rules in CLAUDE.md or claude.md.\r\n"
    "Built in the compass arm, not the Baseline-arm; arm: compass; SPEC-NNN and TASK- remain.\r\n"
    "A baseline bot walks a compass rose.\r\n"
)


def test_text_in_kept_files_is_scrubbed_of_ids_names_and_arm_labels(tmp_path):
    project = write_project(tmp_path / "proj-1", {"docs/notes.md": SCRUBBED, "src/a.py": "# TASK-1\n"})
    copy = grade.make_grading_copy(project, tmp_path / "copy")
    text = (copy / "docs" / "notes.md").read_bytes().decode("utf-8")
    for marker in ("SPEC-", "TASK-", "PLAN-", "ADR-", ".compass", ".claude", "claude.md", "compass arm",
                   "baseline-arm", "arm: compass"):
        assert marker.lower() not in text.lower()
    assert "REF" in text and "\r\n" in text and "baseline bot walks a compass rose" in text
    assert (copy / "src" / "a.py").read_text(encoding="utf-8") == "# REF\n"
    assert grade.copy_leaks(copy) == []


def test_the_project_itself_keeps_its_text(tmp_path):
    project = write_project(tmp_path / "proj-1", {"docs/notes.md": SCRUBBED})
    grade.make_grading_copy(project, tmp_path / "copy")
    assert (project / "docs" / "notes.md").read_bytes().decode("utf-8") == SCRUBBED


def test_a_trace_in_an_omitted_place_is_not_a_leak(tmp_path):
    project = write_project(tmp_path / "proj-1")
    assert grade.find_leaks(project) == []


def test_copy_leaks_finds_a_trace_the_scrub_would_miss(tmp_path):
    copy = tmp_path / "copy"
    copy.mkdir()
    (copy / "a.txt").write_text("fine", encoding="utf-8")
    (copy / "b.txt").write_text("built in the compass arm", encoding="utf-8")
    (copy / "c.bin").write_bytes(b"\x00SPEC-1")
    assert grade.copy_leaks(copy) == ["b.txt"]


def test_a_binary_file_is_copied_unchanged(tmp_path):
    project = write_project(tmp_path / "proj-1")
    payload = b"\x00\x01C:\\compass-overhead\\SPEC-1"
    (project / "tool.bin").write_bytes(payload)
    copy = grade.make_grading_copy(project, tmp_path / "copy")
    assert (copy / "tool.bin").read_bytes() == payload


def test_residual_mentions_counts_files_holding_the_word_compass(tmp_path):
    project = write_project(tmp_path / "proj-1", {"a.md": "A Compass rose", "b.md": "nothing"})
    copy = grade.make_grading_copy(project, tmp_path / "copy")
    assert grade.residual_mentions(copy) == 1


def test_a_copy_inside_the_project_or_into_a_full_folder_is_refused(tmp_path):
    project = write_project(tmp_path / "proj-1")
    with pytest.raises(grade.Refused):
        grade.make_grading_copy(project, project / "copy")
    full = tmp_path / "full"
    full.mkdir()
    (full / "x").write_text("x", encoding="utf-8")
    with pytest.raises(grade.Refused):
        grade.make_grading_copy(project, full)
    with pytest.raises(grade.Refused):
        grade.make_grading_copy(tmp_path / "missing", tmp_path / "copy")


def test_links_are_not_copied(tmp_path):
    project = write_project(tmp_path / "proj-1")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside", encoding="utf-8")
    try:
        os.symlink(outside, project / "linked", target_is_directory=True)
        os.symlink(outside / "secret.txt", project / "secret-link.txt")
    except (OSError, NotImplementedError):
        pytest.skip("links cannot be made here")
    copy = grade.make_grading_copy(project, tmp_path / "copy")
    assert not (copy / "linked").exists() and not (copy / "secret-link.txt").exists()


# choosing and matching


def test_prepare_makes_four_neutral_copies_two_per_arm(world, private_root):
    entries = grade.prepare(private_root=private_root)
    assert sorted(e["name"] for e in entries) == ["grade-1", "grade-2", "grade-3", "grade-4"]
    assert sorted(e["arm"] for e in entries) == ["baseline", "baseline", "compass", "compass"]
    grading = private_root / "grading"
    assert sorted(p.name for p in grading.iterdir()) == [
        "grade-1", "grade-1.md", "grade-2", "grade-2.md", "grade-3", "grade-3.md", "grade-4", "grade-4.md",
    ]
    for entry in entries:
        copy = grading / entry["name"]
        assert not (names_under(copy) & FORBIDDEN_NAMES)
        text = tree_text(copy)
        for word in ("compass", "baseline", "spec-", "task-", ".claude"):
            assert word not in text


def test_prepare_takes_one_capped_compass_build_and_prefers_human_done(world, private_root):
    entries = grade.prepare(private_root=private_root)
    compass = [e for e in entries if e["arm"] == "compass"]
    assert sorted(e["capped"] for e in compass) == [False, True]
    assert all(not e["capped"] for e in entries if e["arm"] == "baseline")
    assert {e["topic"] for e in entries if e["arm"] == "baseline"} == {TOPIC_A, TOPIC_B}


def test_prepare_is_deterministic_and_the_number_does_not_follow_the_arm(world, private_root):
    first = [(e["name"], e["topic"], e["arm"], e["run"]) for e in grade.prepare(private_root=private_root)]
    other = private_root.parent / "other-root"
    clone = World(other, world.tmp)
    clone.log = world.log
    helpers.write_pool(other, [helpers.topic_entry(TOPIC_A), helpers.topic_entry(TOPIC_B, title="Other")])
    for topic_id in (TOPIC_A, TOPIC_B):
        helpers.write_goal_files(other, topic_id, helpers.goal_items(GOAL_TEXTS[topic_id]))
    verdicts = private_root / "topics" / "verdicts"
    (other / "topics" / "verdicts").mkdir(parents=True)
    for path in verdicts.iterdir():
        (other / "topics" / "verdicts" / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    clone.write_log()
    second = [(e["name"], e["topic"], e["arm"], e["run"]) for e in grade.prepare(private_root=other)]
    assert first == second


def test_the_sheet_and_the_copy_name_neither_arm_topic_nor_build(world, private_root):
    entries = grade.prepare(private_root=private_root)
    for entry in entries:
        sheet = (private_root / "grading" / f"{entry['name']}.md").read_text(encoding="utf-8")
        lowered = sheet.lower()
        for secret in ("compass", "baseline", entry["topic"], "proj-", "wall-time", "human-done"):
            assert secret not in lowered
        assert "mark g1:" in sheet and "keep:" in sheet
        for text in GOAL_TEXTS[entry["topic"]]:
            assert text in sheet


def test_the_key_maps_each_name_to_its_build(world, private_root):
    entries = grade.prepare(private_root=private_root)
    key = json.loads((private_root / "grading-key.json").read_text(encoding="utf-8"))["builds"]
    assert key == entries
    by_slot = {(e["topic"], e["arm"], e["run"]): e for e in entries}
    for slot, entry in by_slot.items():
        assert entry["project"] == str(world.projects[slot])


def test_prepare_refuses_a_second_run(world, private_root):
    grade.prepare(private_root=private_root)
    with pytest.raises(grade.GradeError):
        grade.prepare(private_root=private_root)


def test_prepare_skips_a_leaky_project_for_the_next_candidate(private_root, tmp_path):
    w = World(private_root, tmp_path)
    w.add_build(TOPIC_A, "baseline", 1, ["met", "met", "met"], leaky=True)
    w.add_build(TOPIC_A, "baseline", 2, ["met", "met", "met"])
    w.add_build(TOPIC_B, "baseline", 1, ["met", "met"])
    w.add_build(TOPIC_A, "compass", 1, ["met", "met", "met"])
    w.add_build(TOPIC_B, "compass", 1, ["met", "met"])
    w.write_log()
    entries = grade.prepare(private_root=private_root)
    assert (TOPIC_A, "baseline", 1) not in {(e["topic"], e["arm"], e["run"]) for e in entries}


def test_prepare_fails_when_an_arm_has_too_few_usable_builds(private_root, tmp_path):
    w = World(private_root, tmp_path)
    w.add_build(TOPIC_A, "baseline", 1, ["met", "met", "met"])
    w.add_build(TOPIC_A, "baseline", 2, ["met", "met", "met"])
    w.add_build(TOPIC_A, "compass", 1, ["met", "met", "met"])
    w.write_log()
    with pytest.raises(grade.GradeError):
        grade.prepare(private_root=private_root)
    assert not (private_root / "grading").exists()


def test_a_build_without_a_judged_event_or_a_project_folder_is_not_chosen(private_root, tmp_path):
    w = World(private_root, tmp_path)
    w.add_build(TOPIC_A, "baseline", 1, ["met", "met", "met"], judged=False)
    w.add_build(TOPIC_A, "baseline", 2, ["met", "met", "met"])
    w.add_build(TOPIC_B, "baseline", 1, ["met", "met"])
    gone = w.add_build(TOPIC_A, "compass", 1, ["met", "met", "met"])
    w.add_build(TOPIC_A, "compass", 2, ["met", "met", "met"])
    w.add_build(TOPIC_B, "compass", 1, ["met", "met"])
    for path in sorted(gone.rglob("*"), reverse=True):
        path.unlink() if path.is_file() or path.is_symlink() else path.rmdir()
    gone.rmdir()
    w.write_log()
    entries = grade.prepare(private_root=private_root)
    slots = {(e["topic"], e["arm"], e["run"]) for e in entries}
    assert (TOPIC_A, "baseline", 1) not in slots and (TOPIC_A, "compass", 1) not in slots


def test_verdicts_match_judged_events_by_counts_and_order_among_stale_files(private_root, tmp_path):
    w = World(private_root, tmp_path)
    w.add_verdict(TOPIC_A, ["not met", "not met", "not met"])
    w.add_verdict(TOPIC_A, ["met", "met", "met"])
    w.add_build(TOPIC_A, "compass", 1, ["met", "partly met", "not met"])
    w.add_verdict(TOPIC_A, ["partly met", "partly met", "partly met"])
    w.add_build(TOPIC_A, "baseline", 1, ["met", "met", "partly met"])
    w.write_log()
    events = grade._events(private_root / "pilot" / "run-log.jsonl")
    matched = grade.match_verdicts(events, private_root)
    assert matched[(TOPIC_A, "compass", 1)][1]["scores"]["g2"]["score"] == "partly met"
    assert matched[(TOPIC_A, "compass", 1)][1]["scores"]["g1"]["score"] == "met"
    assert matched[(TOPIC_A, "baseline", 1)][1]["scores"]["g2"]["score"] == "met"
    assert matched[(TOPIC_A, "baseline", 1)][0].name > matched[(TOPIC_A, "compass", 1)][0].name


def test_a_judged_event_with_no_verdict_of_equal_counts_is_unmatched(private_root, tmp_path):
    w = World(private_root, tmp_path)
    w.add_build(TOPIC_A, "compass", 1, ["met", "met", "met"])
    w.log[-1]["counts"] = {"met": 0, "partly met": 0, "not met": 3}
    w.write_log()
    events = grade._events(private_root / "pilot" / "run-log.jsonl")
    assert (TOPIC_A, "compass", 1) not in grade.match_verdicts(events, private_root)


def test_topic_letters_follow_the_pick_order(world):
    assert grade.topic_letters(world.log) == {TOPIC_A: "A", TOPIC_B: "B"}


# the sheet


def sheet_text(marks, keep="no", ids=("g1", "g2", "g3")):
    body = "".join(f"## {i}\n\n> text\n\nmark {i}: {m}\n\n" for i, m in zip(ids, marks))
    return f"# Grading sheet grade-1\n\n{body}## Keep\n\nkeep: {keep}\n"


def test_parse_sheet_reads_marks_and_keep():
    marks, keep = grade.parse_sheet(sheet_text(["met", "Partly  Met", "NOT MET"], "Yes"), ["g1", "g2", "g3"])
    assert marks == {"g1": "met", "g2": "partly met", "g3": "not met"}
    assert keep is True


@pytest.mark.parametrize("mark", ["maybe", "", "mostly met", "partly", "met!", "yes", "1"])
def test_a_sheet_with_an_unknown_or_blank_mark_is_refused(mark):
    with pytest.raises(grade.SheetError):
        grade.parse_sheet(sheet_text(["met", mark, "met"]), ["g1", "g2", "g3"])


def test_a_sheet_missing_a_mark_a_keep_or_with_extras_is_refused():
    ids = ["g1", "g2", "g3"]
    with pytest.raises(grade.SheetError):
        grade.parse_sheet(sheet_text(["met", "met"], ids=("g1", "g2")), ids)
    with pytest.raises(grade.SheetError):
        grade.parse_sheet(sheet_text(["met", "met", "met"], keep=""), ids)
    with pytest.raises(grade.SheetError):
        grade.parse_sheet(sheet_text(["met", "met", "met"], keep="maybe"), ids)
    with pytest.raises(grade.SheetError):
        grade.parse_sheet(sheet_text(["met", "met", "met"]) + "keep: yes\n", ids)
    with pytest.raises(grade.SheetError):
        grade.parse_sheet(sheet_text(["met", "met", "met"]) + "mark g1: met\n", ids)
    with pytest.raises(grade.SheetError):
        grade.parse_sheet(sheet_text(["met", "met", "met", "met"], ids=("g1", "g2", "g3", "g9")), ids)


def test_a_blank_sheet_from_prepare_is_refused(world, private_root):
    grade.prepare(private_root=private_root)
    report = private_root.parent / "report.md"
    report.write_text("# Report\n\n### Judge\n\ntext\n", encoding="utf-8")
    with pytest.raises(grade.SheetError):
        grade.score(private_root=private_root, report_path=report)
    assert report.read_text(encoding="utf-8") == "# Report\n\n### Judge\n\ntext\n"


# agreement


def graded_entry(letter, arm, pairs, keep=False):
    return {
        "entry": {"letter": letter, "arm": arm, "name": "grade-1"},
        "pairs": {f"g{n}": pair for n, pair in enumerate(pairs, start=1)},
        "keep": keep,
    }


def test_agreement_is_computed_per_goal_item_against_a_hand_made_fixture():
    graded = [
        graded_entry("A", "compass", [("met", "met"), ("partly met", "met"), ("not met", "partly met")], True),
        graded_entry("A", "baseline", [("not met", "partly met"), ("met", "met"), ("partly met", "partly met")]),
        graded_entry("B", "baseline", [("met", "not met"), ("met", "met")], True),
    ]
    result = grade.agreement(graded)
    assert result["total"] == {"items": 8, "agree": 4, "judge_more_lenient": 3, "judge_stricter": 1}
    assert result["by_arm"] == {
        "compass": {"builds": 1, "items": 3, "agree": 1},
        "baseline": {"builds": 2, "items": 5, "agree": 3},
    }
    assert result["by_item"] == {
        ("A", "g1"): {"graded": 2, "agree": 1},
        ("A", "g2"): {"graded": 2, "agree": 1},
        ("A", "g3"): {"graded": 2, "agree": 1},
        ("B", "g1"): {"graded": 1, "agree": 0},
        ("B", "g2"): {"graded": 1, "agree": 1},
    }
    table = result["table"]
    assert table["met"] == {"met": 3, "partly met": 0, "not met": 1}
    assert table["partly met"] == {"met": 1, "partly met": 1, "not met": 0}
    assert table["not met"] == {"met": 0, "partly met": 2, "not met": 0}
    assert result["builds"] == 3 and result["kept"] == 2


def test_agreement_of_nothing_graded_is_zero():
    result = grade.agreement([])
    assert result["total"]["items"] == 0 and result["kept"] == 0


# score and the report


REPORT = (
    "# Whole overhead pilot\n\n## Findings\n\n### Judge\n\n- Goal items, compass arm: met 27.\n\n"
    "### Headless checks\n\n- TODO: hooks.\n"
)


def fill_sheets(private_root, marks_for):
    """Fill every sheet with marks from `marks_for(name, goal ids)`; keep the first and the third."""
    key = json.loads((private_root / "grading-key.json").read_text(encoding="utf-8"))["builds"]
    for number, entry in enumerate(key):
        path = private_root / "grading" / f"{entry['name']}.md"
        text = path.read_text(encoding="utf-8")
        marks = marks_for(entry)
        for goal_id, mark in marks.items():
            text = text.replace(f"mark {goal_id}:", f"mark {goal_id}: {mark}")
        text = text.replace("keep:", "keep: yes" if number in (0, 2) else "keep: no")
        path.write_text(text, encoding="utf-8")
    return key


def judge_marks(private_root, entry):
    path = private_root / "topics" / "verdicts" / entry["verdict_file"]
    scores = json.loads(path.read_text(encoding="utf-8"))["scores"]
    return {goal_id: value["score"] for goal_id, value in scores.items()}


def test_score_writes_a_section_of_counts_only(world, private_root):
    grade.prepare(private_root=private_root)
    key = fill_sheets(private_root, lambda entry: judge_marks(private_root, entry))
    report = private_root.parent / "report.md"
    report.write_text(REPORT, encoding="utf-8")
    result, kept = grade.score(private_root=private_root, report_path=report)
    assert result["total"]["agree"] == result["total"]["items"]
    assert [e["name"] for e in kept] == [key[0]["name"], key[2]["name"]]
    text = report.read_text(encoding="utf-8")
    section = text[text.index(grade.HEADING):text.index("### Headless checks")]
    assert "Builds marked to keep: 2 of 4" in section
    assert "100.0%" in section
    assert text.index("### Judge") < text.index(grade.HEADING) < text.index("### Headless checks")
    private = [
        TOPIC_A, TOPIC_B, "proj-", str(private_root), str(world.tmp), "grade-", "reason text",
        *GOAL_TEXTS[TOPIC_A], *GOAL_TEXTS[TOPIC_B], "verdicts", ".json", "wall-time",
    ]
    for secret in private:
        assert secret not in section
    assert not any(dash in text for dash in DASHES)
    assert "| A | g1 |" in section and "| B | g2 |" in section


def test_score_counts_a_disagreement_and_names_no_project(world, private_root):
    grade.prepare(private_root=private_root)

    def marks(entry):
        mine = judge_marks(private_root, entry)
        first = next(iter(mine))
        mine[first] = "not met" if mine[first] == "met" else "met"
        return mine

    fill_sheets(private_root, marks)
    report = private_root.parent / "report.md"
    report.write_text(REPORT, encoding="utf-8")
    result, _ = grade.score(private_root=private_root, report_path=report)
    assert result["total"]["items"] - result["total"]["agree"] == 4
    assert result["total"]["judge_more_lenient"] + result["total"]["judge_stricter"] == 4


def test_score_replaces_its_section_and_keeps_the_rest(world, private_root):
    grade.prepare(private_root=private_root)
    fill_sheets(private_root, lambda entry: judge_marks(private_root, entry))
    report = private_root.parent / "report.md"
    report.write_text(REPORT, encoding="utf-8")
    grade.score(private_root=private_root, report_path=report)
    once = report.read_text(encoding="utf-8")
    grade.score(private_root=private_root, report_path=report)
    assert report.read_text(encoding="utf-8") == once
    assert once.count(grade.HEADING) == 1
    assert once.startswith("# Whole overhead pilot\n\n## Findings\n\n### Judge\n")
    assert once.endswith("### Headless checks\n\n- TODO: hooks.\n")


def test_score_appends_the_section_when_the_report_has_no_headless_checks(world, private_root):
    grade.prepare(private_root=private_root)
    fill_sheets(private_root, lambda entry: judge_marks(private_root, entry))
    report = private_root.parent / "report.md"
    report.write_text("# Report\n\n### Judge\n\ntext\n", encoding="utf-8")
    grade.score(private_root=private_root, report_path=report)
    text = report.read_text(encoding="utf-8")
    assert text.startswith("# Report\n\n### Judge\n\ntext\n\n" + grade.HEADING)


def test_score_refuses_a_sheet_with_an_unknown_mark_and_leaves_the_report(world, private_root):
    grade.prepare(private_root=private_root)
    fill_sheets(private_root, lambda entry: {**judge_marks(private_root, entry), "g1": "great"})
    report = private_root.parent / "report.md"
    report.write_text(REPORT, encoding="utf-8")
    with pytest.raises(grade.SheetError) as caught:
        grade.score(private_root=private_root, report_path=report)
    assert "grade-" in str(caught.value) and "g1" in str(caught.value)
    assert report.read_text(encoding="utf-8") == REPORT


def test_score_without_prepare_or_report_is_an_error(world, private_root):
    report = private_root.parent / "report.md"
    report.write_text(REPORT, encoding="utf-8")
    with pytest.raises(grade.GradeError):
        grade.score(private_root=private_root, report_path=report)
    grade.prepare(private_root=private_root)
    fill_sheets(private_root, lambda entry: judge_marks(private_root, entry))
    with pytest.raises(grade.GradeError):
        grade.score(private_root=private_root, report_path=private_root.parent / "missing.md")


def test_score_refuses_a_verdict_that_lacks_an_item(world, private_root):
    entries = grade.prepare(private_root=private_root)
    fill_sheets(private_root, lambda entry: judge_marks(private_root, entry))
    path = private_root / "topics" / "verdicts" / entries[0]["verdict_file"]
    data = json.loads(path.read_text(encoding="utf-8"))
    data["scores"].pop("g1")
    path.write_text(json.dumps(data), encoding="utf-8")
    report = private_root.parent / "report.md"
    report.write_text(REPORT, encoding="utf-8")
    with pytest.raises(grade.GradeError):
        grade.score(private_root=private_root, report_path=report)


# the command line


def test_main_prepare_then_score(world, private_root, capsys):
    assert grade.main(["--private-root", str(private_root), "prepare"]) == 0
    printed = capsys.readouterr().out
    assert "grade-1" in printed and "sheets:" in printed
    fill_sheets(private_root, lambda entry: judge_marks(private_root, entry))
    report = private_root.parent / "report.md"
    report.write_text(REPORT, encoding="utf-8")
    assert grade.main(["--private-root", str(private_root), "score", "--report", str(report)]) == 0
    printed = capsys.readouterr().out
    assert printed.count("keep grade-") == 2


def test_main_reports_a_refusal_with_exit_2(world, private_root, capsys):
    assert grade.main(["--private-root", str(private_root), "prepare"]) == 0
    capsys.readouterr()
    assert grade.main(["--private-root", str(private_root), "prepare"]) == 2
    assert "already exists" in capsys.readouterr().err


def test_a_private_root_inside_a_git_work_tree_is_refused(tmp_path, git):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    with pytest.raises(grade.Refused):
        grade.prepare(private_root=repo / "private")
