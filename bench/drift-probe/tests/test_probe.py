"""Tests for the seeded-staleness probe: `seed.py` and `score.py`.

Adversarial themes: a frozen seed list that can be rewritten moves the target
after the first scan; a draw that depends on hash order or global random state
gives a different list for the same seed; a seeder that accepts a folder inside
the repo (or a non-empty one) damages the repo or mixes the probe with foreign
files; a scorer that matches by file and line alone credits the wrong item, and
one that hardcodes 20 and 80 passes lists of any other size.

Module contract the tests pin
-----------------------------
seed.py   (importable from bench/drift-probe/)
    draw_seeds(candidates, seed) -> dict
        candidates   {"refs": [...], "index": [...], "catalog": [...]}: each a
                     list of baseline-clean items, dicts holding at least
                     "file" (str) and "line" (int); refs also hold "ref_path".
                     Further keys are carried into the drawn items unchanged.
        seed         int; the same seed and candidates give an equal result.
        returns      the seed list: {"seed": int, "items": [item, ...]}
        item         {"id": str unique in the list,
                      "kind": "ref" | "index" | "catalog",
                      "stale": bool,
                      "change": str | None,
                      "expected_class": str | None,
                      "file": str, "line": int, ...carried keys}
        counts       refs 40 items (8 stale), index 30 (6 stale), catalog 30
                     (6 stale): 100 items, 20 stale, 80 controls. Every item is
                     a distinct candidate. Controls have stale False and
                     change None and expected_class None.
        change       refs: "shifted" x3, "edited" x3, "moved" x1, "deleted" x1
                     (expected_class "shifted", "changed", "moved", "missing");
                     index: "summary-edited" x3, "text-edited" x3; catalog:
                     "score" x3, "summary" x3. A stale index or catalog item
                     carries a non-empty str expected_class.
        raises       ValueError when a kind has fewer candidates than it needs.
    check_target(target, repo_root) -> None
        raises Refused when `target` (resolved, `..` and symlinks followed) is
        `repo_root` or inside it, or is an existing folder holding any entry
        (hidden files included). A missing folder or an empty one outside the
        repo passes. A sibling whose name only starts with the repo folder's
        name is outside the repo.
    write_frozen(path, seed_list) -> None
        writes the list as UTF-8 JSON; raises AlreadyFrozen when `path` exists,
        even as an empty file, and leaves the existing bytes untouched.
    main(argv, *, repo_root=None) -> int
        argv: [TARGET, "--seed", N, "--list", PATH]. Exit 0 on success, 1 when
        the list at PATH is already frozen, 2 when the target is refused. The
        frozen check and the target check both run before any clone, so a
        refused run leaves the target and the list as they were.
    AlreadyFrozen, Refused   exception classes.

score.py  (importable from bench/drift-probe/)
    score(seed_list, records) -> dict
        records   the scan result: a list of dicts shaped like the records of
                  `compass drift --print`: {"file", "line", "class", ...} with
                  "ref_path" on reference records. An item is matched by
                  (file, line) and, for kind "ref", also ref_path. A record
                  whose class is "unchanged" or "changed-elsewhere" does not
                  report its item; neither does a missing record.
        returns   {"seeded": stale items, "detected": stale items reported in
                   any class, "wrong_class": detected items whose class differs
                   from expected_class, "missed": seeded - detected,
                   "controls": non-stale items, "false_positives": controls
                   reported, "passed": detected == seeded and
                   false_positives == 0}
        wrong_class is tracked apart and does not block `passed`.
    main(argv, *, scan=None) -> int
        argv: [TARGET, "--seeds", PATH]; scan(TARGET) -> records (the default
        runs `compass drift --print` in TARGET). Prints `pass` or `fail` as the
        first stdout line, then the counts; exit 0 on pass, 1 on fail.
"""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PROBE_DIR = TESTS_DIR.parent
if str(PROBE_DIR) not in sys.path:
    sys.path.insert(0, str(PROBE_DIR))

import score  # noqa: E402
import seed  # noqa: E402

REF_CHANGES = {"shifted": 3, "edited": 3, "moved": 1, "deleted": 1}
REF_CLASSES = {"shifted": "shifted", "edited": "changed", "moved": "moved", "deleted": "missing"}
INDEX_CHANGES = {"summary-edited": 3, "text-edited": 3}
CATALOG_CHANGES = {"score": 3, "summary": 3}
NEED = {"ref": 40, "index": 30, "catalog": 30}


def make_candidates(refs=60, index=45, catalog=50):
    return {
        "refs": [
            {"file": f".compass/research/R{i}.md", "line": 10 + i, "ref_path": f"plugin/mod{i}.py"}
            for i in range(refs)
        ],
        "index": [{"file": f".compass/specs/s{i}/index.md", "line": 5 + i} for i in range(index)],
        "catalog": [{"file": ".compass/meta/lessons-catalog.yaml", "line": 3 * i + 2} for i in range(catalog)],
    }


def key_of(item):
    return (item["kind"], item["file"], item["line"], item.get("ref_path"))


def candidate_keys(candidates):
    kinds = {"refs": "ref", "index": "index", "catalog": "catalog"}
    return {
        (kinds[group], c["file"], c["line"], c.get("ref_path"))
        for group, entries in candidates.items()
        for c in entries
    }


def hand_item(kind, i, change=None, expected=None):
    item = {
        "id": f"{kind[0]}{i:02d}",
        "kind": kind,
        "stale": change is not None,
        "change": change,
        "expected_class": expected,
    }
    if kind == "ref":
        item.update(file=f".compass/research/R{i}.md", line=10 + i, ref_path=f"plugin/mod{i}.py")
    elif kind == "index":
        item.update(file=f".compass/specs/s{i}/index.md", line=5 + i)
    else:
        item.update(file=".compass/meta/lessons-catalog.yaml", line=3 * i + 2)
    return item


def hand_list():
    """The 100-item list: 40 refs (8 stale), 30 index (6), 30 catalog (6)."""
    items = []
    ref_changes = [c for c, n in REF_CHANGES.items() for _ in range(n)]
    for i in range(40):
        change = ref_changes[i] if i < 8 else None
        items.append(hand_item("ref", i, change, REF_CLASSES[change] if change else None))
    for i in range(30):
        stale = i < 6
        items.append(hand_item("index", i, "text-edited" if stale else None, "index-text" if stale else None))
    for i in range(30):
        stale = i < 6
        items.append(hand_item("catalog", i, "score" if stale else None, "catalog-row" if stale else None))
    return {"seed": 1, "items": items}


def record_for(item, cls):
    rec = {"file": item["file"], "line": item["line"], "class": cls, "base": None, "old_text": "a", "current_text": "b"}
    if item["kind"] == "ref":
        rec["ref_path"] = item["ref_path"]
    return rec


def exact_records(seed_list):
    return [record_for(i, i["expected_class"]) for i in seed_list["items"] if i["stale"]]


def item_by_id(seed_list, item_id):
    return next(i for i in seed_list["items"] if i["id"] == item_id)


# ---------------------------------------------------------------- seed.py


def test_write_frozen_refuses_any_existing_file_and_keeps_its_bytes(tmp_path):
    """Adversarial where: a second write (or a write over an empty placeholder)
    replaces the frozen list, so the scored target differs from the one
    seeded; the first write must be readable JSON equal to its input."""
    path = tmp_path / "seeds.json"
    first = {"seed": 1, "items": [{"id": "r00"}]}
    seed.write_frozen(path, first)
    assert json.loads(path.read_text(encoding="utf-8")) == first
    frozen = path.read_bytes()

    with pytest.raises(seed.AlreadyFrozen):
        seed.write_frozen(path, {"seed": 2, "items": []})
    assert path.read_bytes() == frozen

    empty = tmp_path / "empty.json"
    empty.write_bytes(b"")
    with pytest.raises(seed.AlreadyFrozen):
        seed.write_frozen(empty, first)
    assert empty.read_bytes() == b""


def test_main_second_write_exits_1_before_touching_target(tmp_path):
    """Adversarial where: the already-frozen check runs after the clone, so a
    rerun clobbers the scratch folder or exits 0 over a frozen list."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    target = tmp_path / "scratch"
    target.mkdir()
    path = tmp_path / "seeds.json"
    path.write_bytes(b'{"seed": 9, "items": []}\n')
    before = path.read_bytes()

    code = seed.main([str(target), "--seed", "3", "--list", str(path)], repo_root=repo)

    assert code == 1
    assert path.read_bytes() == before
    assert list(target.iterdir()) == []


def test_same_seed_same_list_whatever_the_process(tmp_path):
    """Adversarial where: the draw leans on set order, hash order or the
    global random state, so one seed gives different lists in two runs."""
    candidates = make_candidates()
    first = seed.draw_seeds(copy.deepcopy(candidates), 7)
    import random

    random.seed(123)
    random.random()
    second = seed.draw_seeds(copy.deepcopy(candidates), 7)
    assert first == second

    script = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(PROBE_DIR)!r})\n"
        "import seed\n"
        "print(json.dumps(seed.draw_seeds(json.load(sys.stdin), 7), sort_keys=True))\n"
    )
    outputs = []
    for hash_seed in ("1", "2"):
        env = dict(os.environ, PYTHONHASHSEED=hash_seed)
        done = subprocess.run(
            [sys.executable, "-c", script], input=json.dumps(candidates),
            capture_output=True, text=True, env=env, check=True,
        )
        outputs.append(json.loads(done.stdout))
    assert outputs[0] == outputs[1] == json.loads(json.dumps(first))

    assert seed.draw_seeds(copy.deepcopy(candidates), 8) != first


def test_draw_has_the_specified_counts_and_only_baseline_clean_candidates():
    """Adversarial where: a draw that miscounts a change type, picks a
    candidate twice, draws a control outside the baseline-clean pool or labels
    a control stale gives a probe whose 20 and 80 mean something else."""
    candidates = make_candidates()
    allowed = candidate_keys(candidates)
    for number in range(1, 13):
        result = seed.draw_seeds(copy.deepcopy(candidates), number)
        items = result["items"]
        assert result["seed"] == number
        assert len(items) == 100
        assert len({i["id"] for i in items}) == 100
        keys = [key_of(i) for i in items]
        assert len(set(keys)) == 100
        assert set(keys) <= allowed
        stale = [i for i in items if i["stale"]]
        assert len(stale) == 20
        for i in items:
            if not i["stale"]:
                assert i["change"] is None and i["expected_class"] is None
        by_kind = {k: [i for i in items if i["kind"] == k] for k in NEED}
        assert {k: len(v) for k, v in by_kind.items()} == NEED
        for kind, want_stale, changes in (
            ("ref", 8, REF_CHANGES), ("index", 6, INDEX_CHANGES), ("catalog", 6, CATALOG_CHANGES),
        ):
            kind_stale = [i for i in by_kind[kind] if i["stale"]]
            assert len(kind_stale) == want_stale
            counted = {}
            for i in kind_stale:
                counted[i["change"]] = counted.get(i["change"], 0) + 1
                if kind == "ref":
                    assert i["expected_class"] == REF_CLASSES[i["change"]]
                else:
                    assert isinstance(i["expected_class"], str) and i["expected_class"]
            assert counted == changes


def test_draw_pool_boundary_exactly_enough_works_one_short_raises():
    """Adversarial where: a pool that is exactly the needed size is rejected
    (off by one), or a pool one short is accepted and silently yields a
    smaller probe."""
    exact = make_candidates(refs=40, index=30, catalog=30)
    result = seed.draw_seeds(exact, 4)
    assert {key_of(i) for i in result["items"]} == candidate_keys(exact)

    for short in (
        make_candidates(refs=39, index=30, catalog=30),
        make_candidates(refs=40, index=29, catalog=30),
        make_candidates(refs=40, index=30, catalog=29),
    ):
        with pytest.raises(ValueError):
            seed.draw_seeds(short, 4)


def test_check_target_accepts_outside_empty_and_refuses_the_rest(tmp_path):
    """Adversarial where: a prefix match on the repo path refuses a sibling or
    accepts a `..` path that resolves into the repo; a hidden file or the repo
    root itself is taken for an empty outside folder."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "bench").mkdir()
    sibling = tmp_path / "repo-scratch"
    sibling.mkdir()
    outside_empty = tmp_path / "work" / "empty"
    outside_empty.mkdir(parents=True)
    hidden = tmp_path / "work" / "hidden"
    hidden.mkdir()
    (hidden / ".keep").write_text("", encoding="utf-8")
    inside_empty = repo / "bench" / "empty"
    inside_empty.mkdir()
    dotdot = Path(os.path.join(str(tmp_path / "work"), "..", "repo", "bench", "new"))

    for name, target in (
        ("sibling sharing the repo name prefix", sibling),
        ("empty folder outside the repo", outside_empty),
        ("missing folder outside the repo", tmp_path / "work" / "not-yet"),
    ):
        seed.check_target(target, repo)

    refused = (
        ("the repo root", repo),
        ("empty folder inside the repo", inside_empty),
        ("missing folder inside the repo", repo / "bench" / "later"),
        ("dotdot path resolving into the repo", dotdot),
        ("outside folder holding one hidden file", hidden),
    )
    for name, target in refused:
        with pytest.raises(seed.Refused):
            seed.check_target(target, repo)


def test_main_refusal_exits_2_and_writes_nothing(tmp_path):
    """Adversarial where: the refusal is raised as a traceback or exit 0, or
    only after the seed list was written for a target that was never seeded."""
    repo = tmp_path / "repo"
    (repo / "bench").mkdir(parents=True)
    non_empty = tmp_path / "work" / "full"
    non_empty.mkdir(parents=True)
    (non_empty / "a.txt").write_text("a", encoding="utf-8")
    for name, target in (
        ("inside the repo", repo / "bench" / "scratch"),
        ("non-empty", non_empty),
    ):
        path = tmp_path / f"seeds-{target.name}.json"
        code = seed.main([str(target), "--seed", "1", "--list", str(path)], repo_root=repo)
        assert code == 2, name
        assert not path.exists(), name
    assert [p.name for p in non_empty.iterdir()] == ["a.txt"]
    assert not (repo / "bench" / "scratch").exists()


# --------------------------------------------------------------- score.py


def test_hand_list_has_the_probe_shape():
    """Adversarial where: the fixture itself drifts from the 20 and 80 split,
    so the scoring rows below would pass on the wrong totals."""
    items = hand_list()["items"]
    assert sum(i["stale"] for i in items) == 20
    assert sum(not i["stale"] for i in items) == 80


@pytest.mark.parametrize(
    "name, mutate, want",
    [
        ("all detected exactly", lambda s, r: None,
         dict(detected=20, wrong_class=0, missed=0, false_positives=0, passed=True)),
        ("no records at all", lambda s, r: r.clear(),
         dict(detected=0, wrong_class=0, missed=20, false_positives=0, passed=False)),
        ("19 of 20 detected", lambda s, r: r.pop(0),
         dict(detected=19, wrong_class=0, missed=1, false_positives=0, passed=False)),
        ("stale item reported only as unchanged", lambda s, r: r[0].update({"class": "unchanged"}),
         dict(detected=19, wrong_class=0, missed=1, false_positives=0, passed=False)),
        ("stale item reported only as changed-elsewhere",
         lambda s, r: r[0].update({"class": "changed-elsewhere"}),
         dict(detected=19, wrong_class=0, missed=1, false_positives=0, passed=False)),
        ("wrong class is detected and tracked apart", lambda s, r: r[6].update({"class": "missing"}),
         dict(detected=20, wrong_class=1, missed=0, false_positives=0, passed=True)),
        ("one control reported", lambda s, r: r.append(record_for(item_by_id(s, "r20"), "changed")),
         dict(detected=20, wrong_class=0, missed=0, false_positives=1, passed=False)),
        ("control recorded as unchanged is not reported",
         lambda s, r: r.append(record_for(item_by_id(s, "r20"), "unchanged")),
         dict(detected=20, wrong_class=0, missed=0, false_positives=0, passed=True)),
        ("control recorded as changed-elsewhere is not reported",
         lambda s, r: r.append(record_for(item_by_id(s, "c20"), "changed-elsewhere")),
         dict(detected=20, wrong_class=0, missed=0, false_positives=0, passed=True)),
        ("record at a location outside the list is ignored",
         lambda s, r: r.append({"file": "elsewhere.md", "line": 1, "class": "changed", "ref_path": "x.py"}),
         dict(detected=20, wrong_class=0, missed=0, false_positives=0, passed=True)),
        ("all 80 controls reported",
         lambda s, r: r.extend(record_for(i, "changed") for i in s["items"] if not i["stale"]),
         dict(detected=20, wrong_class=0, missed=0, false_positives=80, passed=False)),
    ],
)
def test_score_counts_detected_wrong_class_and_false_positives(name, mutate, want):
    """Adversarial where: the scorer miscounts a case of the pass rule (a clean
    class taken as a report, a wrong class dropped or blocking, a missing
    record taken as detection), so the probe passes or fails wrongly."""
    seeds = hand_list()
    records = exact_records(seeds)
    mutate(seeds, records)

    result = score.score(seeds, records)

    assert result["seeded"] == 20
    assert result["controls"] == 80
    assert {k: result[k] for k in want} == want


def test_score_matches_by_ref_path_line_and_file_and_sizes_come_from_the_list():
    """Adversarial where: matching on file and line alone credits a record for
    a neighbouring reference or line, and fixed totals pass any list size."""
    stale = hand_item("ref", 0, "edited", "changed")
    control = hand_item("ref", 0)
    control.update(id="r99", ref_path="plugin/other.py")
    other_line = hand_item("ref", 1)
    seeds = {"seed": 1, "items": [stale, control, other_line]}

    only_control = score.score(seeds, [record_for(control, "changed")])
    assert (only_control["detected"], only_control["missed"], only_control["false_positives"]) == (0, 1, 1)
    assert only_control["passed"] is False

    only_stale = score.score(seeds, [record_for(stale, "changed")])
    assert (only_stale["seeded"], only_stale["controls"]) == (1, 2)
    assert (only_stale["detected"], only_stale["false_positives"], only_stale["passed"]) == (1, 0, True)

    for name, record in (
        ("line one below", dict(record_for(stale, "changed"), line=stale["line"] + 1)),
        ("line one above", dict(record_for(stale, "changed"), line=stale["line"] - 1)),
        ("other file", dict(record_for(stale, "changed"), file="other/doc.md")),
    ):
        off = score.score(seeds, [record])
        assert off["detected"] == 0 and off["passed"] is False, name

    catalog_stale = hand_item("catalog", 1, "score", "catalog-row")
    catalog_next = hand_item("catalog", 2)
    rows = {"seed": 1, "items": [catalog_stale, catalog_next]}
    hit = score.score(rows, [record_for(catalog_stale, "catalog-row")])
    assert (hit["detected"], hit["false_positives"], hit["passed"]) == (1, 0, True)


def test_main_prints_pass_or_fail_first_and_exits_accordingly(tmp_path, capsys):
    """Adversarial where: the verdict line is not first or not the bare word
    `pass`, a failing run exits 0, or the scan result is not what decides."""
    seeds = hand_list()
    path = tmp_path / "seeds.json"
    path.write_text(json.dumps(seeds), encoding="utf-8")
    target = tmp_path / "scratch"
    target.mkdir()

    good = exact_records(seeds)
    code = score.main([str(target), "--seeds", str(path)], scan=lambda t: good)
    out = capsys.readouterr().out
    assert code == 0
    assert out.splitlines()[0] == "pass"

    bad = good[1:]
    code = score.main([str(target), "--seeds", str(path)], scan=lambda t: bad)
    out = capsys.readouterr().out
    assert code == 1
    assert out.splitlines()[0] == "fail"
