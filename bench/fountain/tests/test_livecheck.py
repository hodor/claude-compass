"""Tests for bench/fountain/livecheck.py, the live-check kit.

Adversarial themes: the kit exists to say which bytes an editor changed, so
the defects that matter are a fingerprint that misses a change (false
`unchanged`), counts that confuse CRLF with lone CR, a variant file that
differs from the pilot in more than the one thing it names, a listing edit
that damages a file it could not parse, and a settings edit that disturbs
neighbouring keys. Every command is driven as a subprocess from a working
directory that is not the repo, in pytest tmp folders.
"""

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
LIVECHECK = REPO / "bench" / "fountain" / "livecheck.py"
PILOT = REPO / "plugin" / "cli" / "tests" / "fixtures" / "fountain" / "pilot.fountain"
SCENES_KEY = "fountain.general.numberScenesOnSave"
OFFLINE_SCRIPTS = [
    "pilot.fountain",
    "pilot-crlf.fountain",
    "pilot-bom.fountain",
    "pilot-no-final-newline.fountain",
]
BOM = b"\xef\xbb\xbf"


class Result:
    def __init__(self, proc):
        self.rc = proc.returncode
        self.out = proc.stdout.decode("utf-8", "replace")
        self.err = proc.stderr.decode("utf-8", "replace")
        self.text = self.out + self.err


def run(cwd, *args, timeout=60):
    proc = subprocess.run(
        [sys.executable, str(LIVECHECK), *[str(a) for a in args]],
        capture_output=True,
        cwd=str(cwd),
        timeout=timeout,
    )
    return Result(proc)


@pytest.fixture
def vault(tmp_path):
    target = tmp_path / "scratch"
    res = run(tmp_path, "setup", target, "--offline")
    assert res.rc == 0, res.text
    return target


def name_re(name):
    return re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])")


STATUS_RE = re.compile(r"(?<![A-Za-z])(unchanged|changed)(?![A-Za-z])")
LABEL_RE = re.compile(r"(?<![A-Za-z])(CRLF|LF|CR)(?![A-Za-z])", re.I)


def header_line(text, script):
    """First output line naming the script and carrying a status word."""
    pat = name_re(script)
    for line in text.splitlines():
        if pat.search(line) and STATUS_RE.search(line):
            return pat.sub("", line)
    return None


def status_of(header):
    return STATUS_RE.search(header).group(1)


def label_numbers(header):
    """Map each of CRLF, LF, CR to the integers printed after its label."""
    marks = list(LABEL_RE.finditer(header))
    found = {}
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(header)
        nums = [int(n) for n in re.findall(r"\d+", header[mark.end():end])]
        found.setdefault(mark.group(1).upper(), []).extend(nums)
    return found


def eol_counts(data):
    crlf = data.count(b"\r\n")
    return {
        "crlf": crlf,
        "lf_lone": data.count(b"\n") - crlf,
        "lf_total": data.count(b"\n"),
        "cr_lone": data.count(b"\r") - crlf,
    }


def nth_index(data, needle, n):
    idx = -1
    for _ in range(n):
        idx = data.index(needle, idx + 1)
    return idx


def change_char(data):
    """Change one letter in a plain text line; return (data, new line text)."""
    pat = re.compile(rb"(?m)^([A-Za-z])([A-Za-z ,.]{8,})(?=\r?$)")
    for m in pat.finditer(data):
        if m.start() < 4:
            continue
        new_first = b"Q" if m.group(1) != b"Q" else b"Z"
        mutated = data[: m.start()] + new_first + m.group(2) + data[m.end():]
        return mutated, (new_first + m.group(2)).decode("ascii")
    raise AssertionError("no plain letter line to change in the script")


def crlf_line_to_lf(data):
    idx = nth_index(data, b"\r\n", 3)
    return data[:idx] + b"\n" + data[idx + 2:]


def remove_bom(data):
    assert data.startswith(BOM)
    return data[len(BOM):]


def add_final_newline(data):
    assert not data.endswith(b"\n")
    return data + b"\n"


def lone_cr_for_lf(data):
    idx = nth_index(data, b"\n", 3)
    return data[:idx] + b"\r" + data[idx + 1:]


def script_bytes(vault, name):
    return (vault / name).read_bytes()


def hash_vault(vault, step, cwd):
    res = run(cwd, "hash", vault, "--step", step)
    return res


def read_listing(vault):
    return json.loads((vault / ".obsidian" / "community-plugins.json").read_text("utf-8"))


def write_listing(vault, ids):
    (vault / ".obsidian" / "community-plugins.json").write_text(json.dumps(ids), "utf-8")


def test_setup_offline_builds_tree_and_listing(vault):
    """Adversarial where: setup forgets a piece of the scratch vault (a plugin
    folder, a link in links.md, the scenes-off setting, the baseline
    fingerprints), copies stale plugin bytes, or lets an offline run fetch
    the downloaded samples."""
    scripts = sorted(p.name for p in vault.glob("*.fountain"))
    assert scripts == sorted(OFFLINE_SCRIPTS)
    assert not [p for p in vault.rglob("*") if "big_fish" in p.name or "brick_and_steel" in p.name]

    links = (vault / "links.md").read_text("utf-8")
    for link in ("[[pilot.fountain]]", "[[pilot]]", "![[pilot.fountain]]", "[[missing.fountain]]"):
        assert link in links, link
    assert links.count("[[pilot.fountain]]") == 2  # the plain link and the embed

    for plugin in ("fountain", "compass-review"):
        src = REPO / "plugin" / "obsidian" / plugin
        dest = vault / ".obsidian" / "plugins" / plugin
        shipped = [p for p in src.iterdir() if p.is_file()]
        assert shipped, "bundle for %s missing in the repo" % plugin
        for file in shipped:
            assert (dest / file.name).read_bytes() == file.read_bytes(), (plugin, file.name)

    listing = read_listing(vault)
    assert sorted(listing) == ["compass-review", "fountain"]

    settings = json.loads((vault / ".vscode" / "settings.json").read_text("utf-8"))
    assert settings[SCENES_KEY] is False

    baseline = vault / ".livecheck"
    assert baseline.is_dir() and any(baseline.iterdir())


def test_setup_variants_differ_from_pilot_only_in_named_bytes(vault):
    """Adversarial where: a variant is built with more than its one byte
    change (a CRLF variant that also gains a BOM, a no-final-newline variant
    that loses a content line), so a later `changed` verdict cannot be
    traced to the editor."""
    pilot = PILOT.read_bytes()
    assert pilot.endswith(b"\n") and b"\r" not in pilot and not pilot.startswith(BOM)

    assert script_bytes(vault, "pilot.fountain") == pilot
    assert script_bytes(vault, "pilot-crlf.fountain") == pilot.replace(b"\n", b"\r\n")
    assert script_bytes(vault, "pilot-bom.fountain") == BOM + pilot

    stripped = script_bytes(vault, "pilot-no-final-newline.fountain")
    assert stripped and not stripped.endswith(b"\n")
    assert pilot.startswith(stripped)
    tail = pilot[len(stripped):]
    assert tail and set(tail) <= {10, 13}


def test_setup_folder_guard(tmp_path):
    """Adversarial where: setup writes into a folder holding someone else's
    files (even only a hidden one), or the guard over-refuses a folder it
    created itself, one that is empty, or an empty `.livecheck/` beside other
    files."""
    cases = []

    empty = tmp_path / "empty"
    empty.mkdir()
    cases.append(("empty folder", empty, True))

    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "notes.txt").write_text("mine", "utf-8")
    cases.append(("foreign file", foreign, False))

    hidden = tmp_path / "hidden"
    hidden.mkdir()
    (hidden / ".keep").write_text("x", "utf-8")
    cases.append(("only a hidden file", hidden, False))

    owned = tmp_path / "owned"
    (owned / ".livecheck").mkdir(parents=True)
    (owned / "left-over.txt").write_text("from an earlier run", "utf-8")
    cases.append((".livecheck present beside other content", owned, True))

    for label, folder, accepted in cases:
        before = sorted(p.name for p in folder.iterdir())
        res = run(tmp_path, "setup", folder, "--offline")
        if accepted:
            assert res.rc == 0, (label, res.text)
            assert (folder / "pilot.fountain").is_file(), label
        else:
            assert res.rc != 0, (label, res.text)
            assert sorted(p.name for p in folder.iterdir()) == before, label
    assert (foreign / "notes.txt").read_text("utf-8") == "mine"


def test_hash_untouched_vault_reads_unchanged_and_logs_the_step(vault, tmp_path):
    """Adversarial where: hash reports `changed` on a vault nobody touched
    (a fingerprint that includes mtime or line-ending normalisation), skips a
    script, or fails to append the step so `report` has no column."""
    steps = vault / ".livecheck" / "steps.jsonl"
    before = steps.read_text("utf-8").splitlines() if steps.exists() else []

    for step in ("after-open", "after-close"):
        res = hash_vault(vault, step, tmp_path)
        assert res.rc == 0, res.text
        for script in OFFLINE_SCRIPTS:
            header = header_line(res.text, script)
            assert header is not None, (step, script, res.text)
            assert status_of(header) == "unchanged", (step, script, header)

    lines = steps.read_text("utf-8").splitlines()
    assert len(lines) == len(before) + 2
    for line in lines:
        json.loads(line)
    assert "after-open" in lines[-2] and "after-close" in lines[-1]


def test_hash_reads_each_mutation_as_changed_with_matching_counts(tmp_path):
    """Adversarial where: one of the four byte edits slips past the
    fingerprint (BOM removal, final newline added, a single CRLF turned LF,
    one changed letter), the counts follow the wrong convention (a lone CR
    counted inside CRLF, LF and CR swapped), or a neighbouring script is
    reported changed with it. BOM and final-newline rows also need their
    header to differ from a neutral one-letter edit of the same file."""
    rows = [
        ("crlf-line-to-lf", "pilot-crlf.fountain", crlf_line_to_lf, None),
        ("bom-removed", "pilot-bom.fountain", remove_bom, "bom"),
        ("final-newline-added", "pilot-no-final-newline.fountain", add_final_newline, "newline"),
        ("one-letter", "pilot.fountain", None, None),
        ("lone-cr", "pilot.fountain", lone_cr_for_lf, None),
    ]
    flag_label = {
        "bom": re.compile(r"bom|byte[ -]order", re.I),
        "newline": re.compile(r"final[ _-]?newline|final[ _-]?nl", re.I),
    }

    for row_name, script, mutate, flag in rows:
        folder = tmp_path / row_name
        assert run(tmp_path, "setup", folder, "--offline").rc == 0
        target = folder / script
        original = target.read_bytes()
        new_line = None
        if mutate is None:
            mutated, new_line = change_char(original)
        else:
            mutated = mutate(original)
        assert mutated != original, row_name
        target.write_bytes(mutated)

        res = hash_vault(folder, "after-edit", tmp_path)
        header = header_line(res.text, script)
        assert header is not None, (row_name, res.text)
        assert status_of(header) == "changed", (row_name, header)

        want = eol_counts(mutated)
        found = label_numbers(header)
        assert want["crlf"] in found.get("CRLF", []), (row_name, header)
        assert (
            want["lf_lone"] in found.get("LF", [])
            or want["lf_total"] in found.get("LF", [])
        ), (row_name, header)
        assert want["cr_lone"] in found.get("CR", []), (row_name, header)

        if new_line is not None:
            assert new_line in res.text, row_name

        for other in OFFLINE_SCRIPTS:
            if other == script:
                continue
            other_header = header_line(res.text, other)
            assert other_header is not None, (row_name, other)
            assert status_of(other_header) == "unchanged", (row_name, other, other_header)

        if flag:
            assert flag_label[flag].search(header), (row_name, header)
            neutral = tmp_path / (row_name + "-neutral")
            assert run(tmp_path, "setup", neutral, "--offline").rc == 0
            neutral_data, _ = change_char(original)
            (neutral / script).write_bytes(neutral_data)
            neutral_header = header_line(hash_vault(neutral, "after-edit", tmp_path).text, script)
            assert neutral_header is not None
            assert header != neutral_header, (row_name, header)


def test_listing_add_remove_keeps_other_entries(vault, tmp_path):
    """Adversarial where: `--add` drops or reorders existing ids, duplicates
    an id already listed, or fails on an empty list; `--remove` removes more
    than the one id or errors on an absent id; the atomic write leaves a
    temp file in .obsidian; plain `listing` prints nothing useful."""
    shown = run(tmp_path, "listing", vault)
    assert shown.rc == 0
    assert "fountain" in shown.out and "compass-review" in shown.out

    seed = ["dataview", "fountain", "compass-review"]
    rows = [
        ("add new id", seed, ["--add", "zz-extra"], seed + ["zz-extra"]),
        ("add id already listed", seed, ["--add", "fountain"], seed),
        ("add to empty list", [], ["--add", "zz-extra"], ["zz-extra"]),
        ("remove listed id", seed, ["--remove", "fountain"], ["dataview", "compass-review"]),
        ("remove absent id", seed, ["--remove", "zz-absent"], seed),
    ]
    obsidian_dir = vault / ".obsidian"
    for label, start, args, expected in rows:
        write_listing(vault, start)
        names = sorted(p.name for p in obsidian_dir.iterdir())
        res = run(tmp_path, "listing", vault, *args)
        assert res.rc == 0, (label, res.text)
        assert read_listing(vault) == expected, label
        assert sorted(p.name for p in obsidian_dir.iterdir()) == names, label


def test_listing_unparseable_file_stays_byte_identical_and_is_named(vault, tmp_path):
    """Adversarial where: an edit rewrites a listing it could not parse
    (truncated JSON, an empty file, an object instead of a list, a valid list
    followed by junk), destroying the user's plugin list, or silently
    succeeds without naming the file."""
    path = vault / ".obsidian" / "community-plugins.json"
    bodies = [
        ("truncated", b'["fountain", "compass-review"'),
        ("empty", b""),
        ("object not list", b'{"fountain": true}'),
        ("list then junk", b'["fountain"] trailing'),
    ]
    for label, body in bodies:
        for args in (["--add", "zz-extra"], ["--remove", "fountain"]):
            path.write_bytes(body)
            res = run(tmp_path, "listing", vault, *args)
            assert path.read_bytes() == body, (label, args)
            assert "community-plugins.json" in res.text, (label, args, res.text)


def test_scenes_on_then_off_changes_only_its_own_key(vault, tmp_path):
    """Adversarial where: `scenes` rewrites the settings file and loses
    neighbouring keys (flat or nested), leaves the key on after `off`, or
    accepts a value other than on/off and corrupts the file."""
    path = vault / ".vscode" / "settings.json"
    base = json.loads(path.read_text("utf-8"))
    base["editor.fontSize"] = 17
    base["files.exclude"] = {"**/.livecheck": True, "**/zz": False}
    base[SCENES_KEY] = False
    path.write_text(json.dumps(base, indent=4), "utf-8")

    assert run(tmp_path, "scenes", vault, "on").rc == 0
    on = json.loads(path.read_text("utf-8"))
    assert on[SCENES_KEY] is True
    assert {k: v for k, v in on.items() if k != SCENES_KEY} == {
        k: v for k, v in base.items() if k != SCENES_KEY
    }

    assert run(tmp_path, "scenes", vault, "off").rc == 0
    assert json.loads(path.read_text("utf-8")) == base

    frozen = path.read_bytes()
    bad = run(tmp_path, "scenes", vault, "maybe")
    assert bad.rc != 0
    assert path.read_bytes() == frozen


def test_report_renders_one_row_per_script_with_a_column_per_step(vault, tmp_path):
    """Adversarial where: `report` drops a script, repeats one, omits a step
    column, or renders a ragged table (a row with a different cell count than
    the header)."""
    for step in ("after-open", "after-edit"):
        assert hash_vault(vault, step, tmp_path).rc == 0
    res = run(tmp_path, "report", vault)
    assert res.rc == 0, res.text

    table = [ln for ln in res.out.splitlines() if ln.strip().startswith("|")]
    header = next(ln for ln in table if "after-open" in ln)
    assert "after-edit" in header
    assert any(re.fullmatch(r"\|[\s:\-|]+\|", ln.strip()) for ln in table)
    for script in OFFLINE_SCRIPTS:
        rows = [ln for ln in table if name_re(script).search(ln)]
        assert len(rows) == 1, (script, rows)
        assert rows[0].count("|") == header.count("|"), (script, rows[0])


def test_fixture_pilot_holds_every_named_construct():
    """Adversarial where: the pilot lacks a construct the live checks rely on
    (so an editor behaviour on it is never exercised), or has the construct
    in a form that does not trigger it (a boneyard that is not nested, a
    two-space line that is blank-adjacent so it does not hold a block)."""
    text = PILOT.read_text("utf-8")
    lines = text.split("\n")

    def title_page_has_continuation():
        block = []
        for ln in lines:
            if not ln.strip():
                break
            block.append(ln)
        keyed = [i for i, ln in enumerate(block) if re.match(r"^[A-Za-z][A-Za-z ]*:", ln)]
        return bool(keyed) and keyed[0] == 0 and any(
            re.match(r"^[ \t]+\S", ln) for ln in block[1:]
        )

    def nested_boneyard():
        depth = best = 0
        i = 0
        while i < len(text):
            if text.startswith("/*", i):
                depth += 1
                best = max(best, depth)
                i += 2
            elif text.startswith("*/", i) and depth:
                depth -= 1
                i += 2
            else:
                i += 1
        return best >= 2 and depth == 0

    def two_space_line_inside_dialogue():
        return any(
            ln == "  " and lines[i - 1].strip() and lines[i + 1].strip()
            for i, ln in enumerate(lines)
            if 0 < i < len(lines) - 1
        )

    constructs = {
        "title page with continuation": title_page_has_continuation(),
        "# Snippets section": any(ln.strip() == "# Snippets" for ln in lines),
        "nested boneyard": nested_boneyard(),
        "[[>links]] link": "[[>links]]" in text,
        "fountain note [[a note]]": "[[a note]]" in text,
        "= synopsis": bool(re.search(r"(?m)^=(?!==)\s*\S", text)),
        "dual dialogue ^": bool(re.search(r"(?m)\S\^[ \t]*$", text)),
        "#1# scene number": "#1#" in text,
        "transition": bool(
            re.search(r"(?m)^[A-Z][A-Z .]* TO:[ \t]*$", text)
            or re.search(r"(?m)^>(?!.*<[ \t]*$)[ \t]*\S", text)
        ),
        ">THE END< centered": ">THE END<" in text,
        "two-space line inside dialogue": two_space_line_inside_dialogue(),
    }
    missing = [name for name, present in constructs.items() if not present]
    assert not missing, missing


def _github_reachable():
    try:
        urllib.request.urlopen("https://github.com", timeout=5).close()
        return True
    except OSError:
        return False


@pytest.mark.skipif(not _github_reachable(), reason="GitHub is unreachable")
def test_setup_online_downloads_samples_and_makes_crlf_copies(tmp_path):
    """Adversarial where: an online setup skips a sample, saves a download
    already converted, or makes the CRLF copy without CRLF (or with mixed
    endings), so the CRLF round-trip check runs on LF bytes."""
    target = tmp_path / "scratch"
    res = run(tmp_path, "setup", target, timeout=180)
    assert res.rc == 0, res.text

    for stem in ("big_fish", "brick_and_steel"):
        files = [p for p in target.glob("*.fountain") if p.name.startswith(stem)]
        assert len(files) >= 2, (stem, [p.name for p in target.glob("*")])
        normalised = {p.read_bytes().replace(b"\r\n", b"\n") for p in files}
        assert len(normalised) == 1, stem

        pure_crlf = [
            p for p in files
            if b"\r\n" in p.read_bytes() and p.read_bytes().count(b"\n") == p.read_bytes().count(b"\r\n")
        ]
        assert pure_crlf, stem
