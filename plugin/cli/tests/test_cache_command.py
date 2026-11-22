"""Tests for `compass cache`: the prompt-cache report over host transcripts.

Command line (`plugin/cli/commands/cache.py`, registered in
`maincli.COMMAND_SPECS`):

    compass cache [--all-compass] [--days N] [--json] [--save [FILE]] [--compare FILE]

Every invocation here is a subprocess of `plugin/cli/compass`, so an argparse
exit 2 or a traceback is observable. Failures print on stderr and exit 1.

Scope and window
    Without `--all-compass` the command reads the transcript folder of the
    project whose vault holds the working directory
    (`sessionslib.transcripts_dir` of the main checkout). With it, every folder
    under `<CLAUDE_CONFIG_DIR>/projects` whose first recorded `cwd` is an
    existing directory holding a `.compass/` directory is read; the others are
    skipped, and only their count is reported. `--days N` (default 30, an
    integer of at least 1 that `now - N days` can represent) keeps main sessions whose `started_at` lies within
    the last N days; a subagent belongs to its parent session. Consecutive
    pairs are formed after the window is applied and never across projects.
    A missing or empty transcript folder reads as no data: exit 0, every `n` 0
    and every `value` null.

JSON schema (`--json` prints exactly one object; `--save` writes the same
object; both are deterministic for fixed transcripts, with no timestamp). A
measure `M` is `{"value": float | null, "n": int}`, ratios as fractions 0..1.

    {
      "version": 1,
      "days": <int>,
      "projects": <int with --all-compass, else null>,
      "main": {
        "whole_hit": M,                  # pooled over every request of the
                                         # sessions; n = sessions with a request
        "first_request_hit": M,          # tokens-weighted hit of the first
                                         # requests, pooled; n = sessions
        "first_request_read_median": M,  # median first-request
                                         # cache_read_input_tokens; n = sessions
        "next_session_read_share": M,    # among sessions starting 5 to 60
                                         # minutes (both inclusive) after the
                                         # previous session's last request, the
                                         # share whose first request read 60%
                                         # or more (inclusive) of its tokens;
                                         # n = qualifying sessions
        "cost_after_gap_share": M,       # modeled cost of requests that follow
                                         # a gap over 60 minutes (strictly)
                                         # since the previous request of the
                                         # same session, over the modeled cost
                                         # of every request; a session's first
                                         # request never counts as after a gap;
                                         # n = requests. Weights: input 1.0,
                                         # cache read 0.1, cache creation 1.25
                                         # (ephemeral 1h creation 2.0 when the
                                         # split is present)
        "first_difference": {"counts": {<every cachelib.KINDS entry>: int},
                             "n": <comparable pairs>, "pairs": <consecutive pairs>}
      },
      "subagents": {                     # one entry per agent type
        "<type>": {
          "whole_hit": M,
          "first_request_hit": M,        # tokens-weighted: the headline
          "first_request_read_share": M, # share of first requests reading > 0
          "first_difference": {...}      # same-type consecutive siblings of one
                                         # parent, ordered by started_at
        }
      },
      "loops": {"<LOOP folder name>": {"hit": M}},   # n = runs; every
                                         # `<vault>/loops/*/ledger.jsonl`
                                         # (not windowed), pooled by folder name
      "cache_writes": {
        "main": W, "subagent": W         # W = {"ephemeral_5m": int,
      }                                  #   "ephemeral_1h": int, "unsplit": int,
                                         #   "n": requests}; unsplit counts the
                                         # creation tokens of requests whose
                                         # split is absent
    }

Text report (one line per measure, `<label>: <value> (n=<n>)`; a ratio prints
as `{value * 100:.1f}%`, a null as `n/a`; the first-difference lines list only
nonzero kinds as `kind=count` joined by ", "):

    projects read: <int>                                  (--all-compass only)
    main whole-session hit
    main first-request hit
    main first-request read median                        (value `<int> tokens`)
    main next-session read share
    main cost after gaps over 1 hour
    main first differing block (n=<c> of <p> pairs): <kinds>
    subagent <type> first-request hit (tokens-weighted)   (headline, first
    subagent <type> first-request read share (any read)    line of the type)
    subagent <type> whole-session hit
    subagent <type> first differing block (n=<c> of <p> pairs): <kinds>
    loop <LOOP folder name> hit
    main cache writes: 5m=<int> 1h=<int> unsplit=<int> (n=<int>)
    subagent cache writes: 5m=<int> 1h=<int> unsplit=<int> (n=<int>)

`--save [FILE]` writes the JSON object to FILE (default
`<COMPASS_HOME or ~/.compass>/cache/<sensorlib.machine_id()>.json`), creating
parent folders, and prints `saved <path>` on stderr; stdout stays the report.
`--save` followed by another `--option` or by nothing takes the default path.
It refuses, exit 1 and nothing created, any path inside a git work tree.

`--compare FILE` reads a saved object and prints, per measure of `main` and the
subagent headlines present in both, `<label>: before <b> after <a> change <c>`
where ratios print as `{:.1f}%` and the change as `{:+.1f} points` (computed on
the unrounded fractions, rounded to one decimal), the median prints in tokens
(`change {:+d} tokens`). It exits 1 when the change of `first_request_hit` or
`next_session_read_share` rounds below -5.0 points; exactly -5.0 exits 0. A null
`before` value gives `n/a` and no failure. FILE must be a JSON object whose
`main` is an object whose `first_request_hit` and `next_session_read_share`
are `{"value": finite number | null, ...}` with a bool counted as invalid;
otherwise exit 1 with a message on stderr.

Fixtures are built by code under pytest's tmp_path with `CLAUDE_CONFIG_DIR`,
`COMPASS_HOME` and HOME pointed there; every path, session id and project name
carries a LEAK marker.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

CLI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLI_DIR))

import cachelib  # noqa: E402
import maincli  # noqa: E402
import sensorlib  # noqa: E402
import sessionslib  # noqa: E402

LAUNCHER = CLI_DIR / "compass"
LEAK_SID = "LEAKSID-5d1c"
LEAK_TEXT = "LEAKTEXT-77c4"
INTRO = "Codebase and user instructions are shown below. Be sure to adhere to these."
DESC = {
    "user": "user's private global instructions for all projects",
    "project": "project instructions, checked into the codebase",
    "rule": "project instructions, checked into the codebase",
    "memory": "user's auto-memory, persists across conversations",
}
DEFAULT_FILES = [("user", "u1"), ("project", "p1"), ("rule", "r1"), ("rule", "r2"),
                 ("memory", "m1")]
RULE_CHANGED = [("user", "u1"), ("project", "p1"), ("rule", "r1 changed"), ("rule", "r2"),
                ("memory", "m1")]

NOW = datetime.now(timezone.utc)
BASE = NOW.replace(minute=0, second=0, microsecond=0) - timedelta(days=3)


def at(minutes):
    return (BASE + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def use(read, create, inp, split=None):
    body = {"input_tokens": inp, "cache_creation_input_tokens": create,
            "cache_read_input_tokens": read, "output_tokens": 5}
    if split is not None:
        body["cache_creation"] = {"ephemeral_5m_input_tokens": split[0],
                                  "ephemeral_1h_input_tokens": split[1]}
    return body


def blob(role, texts):
    import hashlib
    message = {"role": role, "content": [{"type": "text", "text": t} for t in texts]}
    digest = hashlib.sha1(json.dumps(message, sort_keys=True).encode()).hexdigest()[:16]
    return {"type": "api-request-blob", "sessionId": LEAK_SID, "hash": digest, "message": message}


def blobs_for(files=None, git="status A"):
    files = DEFAULT_FILES if files is None else files
    parts = [f"<system-reminder>\n{INTRO}\n"]
    for index, (kind, body) in enumerate(files):
        name = {"user": "CLAUDE.md", "project": "CLAUDE.md", "memory": "MEMORY.md"}.get(
            kind, f"rule{index}.md")
        folder = {"user": "home/.claude", "project": "proj", "memory": "mem",
                  "rule": "proj/.claude/rules"}[kind]
        parts.append(f"Contents of /fx-LEAKPATH/{folder}/{name} ({DESC[kind]}):\n\n{body}\n")
    instructions = "\n".join(parts) + "</system-reminder>"
    git_block = ("<system-reminder>\nAs you answer the user's questions, you can use the "
                 f"following context:\n# gitStatus\n{git}\n</system-reminder>")
    return [blob("user", [instructions, git_block, f"{LEAK_TEXT} prompt"]),
            blob("system", ["# Environment\nenv A"])]


def transcript_records(cwd, start, minutes, uses, files=None, git="status A",
                       model="claude-test-1", sidechain=False):
    """A transcript: an attachment record at `start`, the request context, and
    one assistant request per entry of `minutes`/`uses`; the first links to
    its api-request."""
    blobs = blobs_for(files, git)
    ref = f"ref-{LEAK_SID}-{start}"
    records = [
        {"type": "attachment", "timestamp": at(start), "entrypoint": "cli",
         "sessionId": LEAK_SID, "cwd": str(cwd), "attachment": {"type": "environment"}},
        {"type": "api-request-shape", "shapeHash": "S1", "timestamp": at(start)},
        *blobs,
        {"type": "api-request", "id": ref, "timestamp": at(start), "shapeHash": "S1",
         "params": {"model": model, "max_tokens": 64000}, "tail": [b["hash"] for b in blobs],
         "keep": 0, "sessionId": LEAK_SID},
    ]
    for n, (minute, usage) in enumerate(zip(minutes, uses)):
        records.append({
            "type": "assistant", "isSidechain": sidechain, "timestamp": at(minute),
            "requestId": f"req-{start}-{n}", "requestRef": ref if n == 0 else None,
            "entrypoint": "cli", "cwd": str(cwd), "sessionId": LEAK_SID,
            "message": {"model": model, "role": "assistant",
                        "content": [{"type": "text", "text": LEAK_TEXT}], "usage": usage}})
    return records


def write_jsonl(path, records, tail=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("".join(json.dumps(r) + "\n" for r in records) + tail).encode("utf-8"))


class World:
    """A temporary machine: config dir, home, work folder and a command runner."""

    def __init__(self, tmp_path):
        self.root = tmp_path
        self.cfg = tmp_path / "cfg"
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.compass_home = self.home / ".compass"
        self.work = tmp_path / "work"
        self.work.mkdir()
        (self.cfg / "projects").mkdir(parents=True)

    def project(self, name, vault=True):
        path = self.work / name
        path.mkdir()
        if vault:
            (path / ".compass").mkdir()
        return path

    def folder(self, project_path):
        folder = self.cfg / "projects" / sessionslib.project_key(str(project_path))
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def session(self, project_path, name, start, minutes, uses, **kwargs):
        path = self.folder(project_path) / f"{name}.jsonl"
        write_jsonl(path, transcript_records(project_path, start, minutes, uses, **kwargs))
        return path

    def subagent(self, session_path, name, agent_type, start, minutes, uses, cwd, **kwargs):
        side = session_path.with_suffix("") / "subagents"
        write_jsonl(side / f"agent-{name}.jsonl",
                    transcript_records(cwd, start, minutes, uses, sidechain=True, **kwargs))
        if agent_type is not None:
            (side / f"agent-{name}.meta.json").write_text(
                json.dumps({"agentType": agent_type}), encoding="utf-8")

    def env(self, **extra):
        env = dict(os.environ)
        env.pop("CLAUDE_PROJECT_DIR", None)
        env.update(CLAUDE_CONFIG_DIR=str(self.cfg), COMPASS_HOME=str(self.compass_home),
                   HOME=str(self.home), USERPROFILE=str(self.home),
                   PYTHONIOENCODING="utf-8")
        env.update(extra)
        return env

    def run(self, cwd, *args, env=None):
        return subprocess.run(
            [sys.executable, str(LAUNCHER), "cache", *args], cwd=str(cwd),
            env=env or self.env(), capture_output=True, text=True, encoding="utf-8",
            timeout=180)

    def json(self, cwd, *args):
        result = self.run(cwd, "--json", *args)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def build_machine(world):
    """The main project (five in-window sessions, one 40 days old, subagents of
    three types, junk files, one loop ledger), a second vault project, a
    project folder without a vault, one whose cwd is gone and an empty one."""
    proj = world.project("LEAKPROJA-1f3d")
    # Folder names sort opposite to start order, so a name sort is visible.
    world.session(proj, "s-z", -40 * 1440, [1, 2], [use(1000, 0, 0), use(1000, 0, 0)])
    s1 = world.session(proj, "s-e", 0, [1, 2], [use(0, 1000, 0), use(900, 100, 0)])
    s2 = world.session(proj, "s-d", 10, [11, 12], [use(600, 300, 100), use(1000, 0, 0)])
    s3 = world.session(proj, "s-c", 16, [17, 18], [use(0, 500, 0), use(500, 0, 0)],
                       git="status B")
    world.session(proj, "s-b", 78, [79, 140], [use(550, 450, 0), use(0, 1000, 0)],
                       model="claude-test-2")
    world.session(proj, "s-a", 201, [202, 262], [use(400, 400, 200), use(1000, 0, 0)],
                       model="claude-test-2", files=RULE_CHANGED)
    world.subagent(s1, "zzz", "builder", 3, [4, 5], [use(0, 1000, 0), use(900, 100, 0)], proj)
    world.subagent(s1, "aaa", "builder", 8, [9, 10], [use(800, 200, 0), use(1000, 0, 0)], proj,
                   files=RULE_CHANGED)
    world.subagent(s1, "mmm", "tester", 5, [6, 7], [use(500, 500, 0), use(1000, 0, 0)], proj)
    world.subagent(s2, "bbb", "builder", 20, [21, 22], [use(0, 600, 400), use(500, 500, 0)], proj)
    world.subagent(s3, "ccc", None, 17, [18], [use(100, 100, 0)], proj)
    folder = world.folder(proj)
    (folder / "bad.jsonl").write_bytes(b"not json\n\x00\xff\xfe\n{broken")
    (folder / "notes.txt").write_text("hello", encoding="utf-8")
    (folder / "dir.jsonl").mkdir()
    loop = proj / ".compass" / "loops" / "LOOP-001-alpha"
    loop.mkdir(parents=True)
    rows = [{"type": "run", "cache_read_tokens": 900, "cache_creation_tokens": 100,
             "input_tokens": 0},
            {"type": "run", "cache_read_tokens": 100, "cache_creation_tokens": 700,
             "input_tokens": 100},
            {"type": "note", "cache_read_tokens": 99999}]
    write_jsonl(loop / "ledger.jsonl", rows)

    proj_b = world.project("LEAKPROJB-77aa")
    world.session(proj_b, "b1", 100, [101, 102], [use(900, 100, 0), use(900, 100, 0)])
    novault = world.project("LEAKNOVAULT-02", vault=False)
    world.session(novault, "n1", 50, [51, 52], [use(0, 9999, 1), use(0, 9999, 1)])
    gone = world.work / "LEAKGONE-9"
    world.session(gone, "g1", 60, [61], [use(5, 5, 5)])
    world.folder(world.work / "LEAKEMPTY-3")
    return proj, proj_b


def assert_failed(result, *words):
    """A real failure of the command: exit 1, a message naming each of `words` on
    stderr, no traceback and no "not implemented" or "unknown command" answer of the launcher."""
    assert result.returncode == 1, (result.stdout, result.stderr)
    message = result.stderr.lower()
    assert message.strip() and "traceback" not in message and "not implemented" not in message
    assert "unknown command" not in message
    for word in words:
        assert word in message, (word, result.stderr)


def approx(value):
    return pytest.approx(value, abs=1e-9)


def check(measure, value, n):
    assert set(measure) == {"value", "n"}, measure
    assert measure["n"] == n
    if value is None:
        assert measure["value"] is None
    else:
        assert measure["value"] == approx(value)


PROJECT_A_COST_AFTER_GAP = 1250 / 5482.5
KIND_ZERO = {kind: 0 for kind in cachelib.KINDS}


def counts(**kinds):
    return {**KIND_ZERO, **{k.replace("_", "-"): v for k, v in kinds.items()}}


# ---- registration ---------------------------------------------------------


def test_cache_is_registered_and_answers_help(world):
    """Adversarial where: a command missing from COMMAND_SPECS or whose
    `--help` is parsed by argparse (exit 2) would be invisible to the bare
    listing or violate the never-exit-2 rule."""
    assert "cache" in [name for name, _ in maincli.COMMAND_SPECS]
    helped = world.run(world.root, "--help")
    assert helped.returncode == 0
    for flag in ("--all-compass", "--days", "--json", "--save", "--compare"):
        assert flag in helped.stdout
    listing = subprocess.run([sys.executable, str(LAUNCHER)], capture_output=True, text=True,
                             encoding="utf-8", timeout=60)
    assert listing.returncode == 0
    assert re.search(r"^\s*cache\b", listing.stdout, re.MULTILINE)


# ---- the numbers ----------------------------------------------------------


def test_single_project_json_equals_hand_computed_values(world):
    """Adversarial where: pooled versus per-session averaging, the 5 to 60
    minute edges (gaps 4, 8, 60 and 61), a 40 day old session leaking into the
    window, junk files, a name-ordered instead of time-ordered session list and
    another project's folder being read all change one of these numbers."""
    proj, _ = build_machine(world)
    data = world.json(proj)
    assert set(data) == {"version", "days", "projects", "main", "subagents", "loops",
                         "cache_writes"}
    assert (data["version"], data["days"], data["projects"]) == (1, 30, None)
    main = data["main"]
    assert set(main) == {"whole_hit", "first_request_hit", "first_request_read_median",
                         "next_session_read_share", "cost_after_gap_share",
                         "first_difference"}
    check(main["whole_hit"], 4950 / 9000, 5)
    check(main["first_request_hit"], 1550 / 4500, 5)
    check(main["first_request_read_median"], 400, 5)
    check(main["next_session_read_share"], 1 / 2, 2)
    check(main["cost_after_gap_share"], PROJECT_A_COST_AFTER_GAP, 10)
    assert main["first_difference"] == {
        "counts": counts(none=1, git_snapshot=1, instruction_files=1), "n": 3, "pairs": 4}

    assert set(data["subagents"]) == {"builder", "tester", "unknown"}
    builder = data["subagents"]["builder"]
    assert set(builder) == {"whole_hit", "first_request_hit", "first_request_read_share",
                            "first_difference"}
    check(builder["whole_hit"], 3200 / 6000, 3)
    check(builder["first_request_hit"], 800 / 3000, 3)
    check(builder["first_request_read_share"], 1 / 3, 3)
    assert builder["first_difference"] == {"counts": counts(instruction_files=1), "n": 1,
                                           "pairs": 1}
    tester = data["subagents"]["tester"]
    check(tester["whole_hit"], 1500 / 2000, 1)
    check(tester["first_request_hit"], 0.5, 1)
    check(tester["first_request_read_share"], 1.0, 1)
    assert tester["first_difference"] == {"counts": counts(), "n": 0, "pairs": 0}
    check(data["subagents"]["unknown"]["whole_hit"], 0.5, 1)

    assert set(data["loops"]) == {"LOOP-001-alpha"}
    check(data["loops"]["LOOP-001-alpha"]["hit"], 1000 / 1900, 2)
    assert data["cache_writes"] == {
        "main": {"ephemeral_5m": 0, "ephemeral_1h": 0, "unsplit": 3750, "n": 10},
        "subagent": {"ephemeral_5m": 0, "ephemeral_1h": 0, "unsplit": 3000, "n": 9}}


def test_text_report_prints_hand_computed_numbers_each_with_n(world):
    """Adversarial where: the text path formatting its own numbers (rounding,
    n, kinds listed) differently from the JSON path; and the tokens-weighted
    headline of a subagent type must lead its diagnostic."""
    proj, _ = build_machine(world)
    result = world.run(proj)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    by_label = {}
    for line in lines:
        label, _, rest = line.partition(": ")
        by_label[label] = rest
    assert "projects read" not in by_label
    assert by_label["main whole-session hit"] == "55.0% (n=5)"
    assert by_label["main first-request hit"] == "34.4% (n=5)"
    assert by_label["main first-request read median"] == "400 tokens (n=5)"
    assert by_label["main next-session read share"] == "50.0% (n=2)"
    assert by_label["main cost after gaps over 1 hour"] == "22.8% (n=10)"
    diff = next(line for line in lines if line.startswith("main first differing block"))
    assert "(n=3 of 4 pairs)" in diff
    for kind in ("git-snapshot=1", "instruction-files=1", "none=1"):
        assert kind in diff
    assert "environment" not in diff and "other=" not in diff
    headline = "subagent builder first-request hit (tokens-weighted)"
    diagnostic = "subagent builder first-request read share (any read)"
    assert by_label[headline] == "26.7% (n=3)"
    assert by_label[diagnostic] == "33.3% (n=3)"
    assert by_label["subagent builder whole-session hit"] == "53.3% (n=3)"
    builder_lines = [i for i, line in enumerate(lines) if line.startswith("subagent builder ")]
    assert lines[builder_lines[0]].startswith(headline)
    assert by_label["loop LOOP-001-alpha hit"] == "52.6% (n=2)"
    assert by_label["main cache writes"] == "5m=0 1h=0 unsplit=3750 (n=10)"
    assert by_label["subagent cache writes"] == "5m=0 1h=0 unsplit=3000 (n=9)"


def test_all_compass_reads_only_vault_projects_and_reports_their_count(world):
    """Adversarial where: a folder whose cwd has no `.compass/`, one whose cwd no
    longer exists and an empty folder must be skipped, and a pair or next-session
    gap must never join sessions of two projects."""
    proj, _ = build_machine(world)
    data = world.json(proj, "--all-compass")
    assert data["projects"] == 2
    main = data["main"]
    check(main["whole_hit"], 6750 / 11000, 6)
    check(main["first_request_hit"], 2450 / 5500, 6)
    check(main["first_request_read_median"], 475, 6)
    check(main["next_session_read_share"], 1 / 2, 2)
    check(main["cost_after_gap_share"], 1250 / 5912.5, 12)
    assert main["first_difference"]["pairs"] == 4
    assert main["first_difference"]["n"] == 3
    assert data["cache_writes"]["main"] == {
        "ephemeral_5m": 0, "ephemeral_1h": 0, "unsplit": 3950, "n": 12}
    check(data["loops"]["LOOP-001-alpha"]["hit"], 1000 / 1900, 2)

    text = world.run(proj, "--all-compass")
    assert text.returncode == 0, text.stderr
    assert "projects read: 2" in text.stdout.splitlines()
    for marker in ("LEAK", world.root.name):
        assert marker not in text.stdout


def test_all_compass_without_any_vault_project_reads_zero(world):
    """Adversarial where: no qualifying folder must give projects 0 and empty
    measures, not a crash on an empty collection."""
    novault = world.project("LEAKNOVAULT-02", vault=False)
    world.session(novault, "n1", 50, [51], [use(0, 9, 1)])
    anchor = world.project("LEAKANCHOR-1")
    data = world.json(anchor, "--all-compass")
    assert data["projects"] == 0
    check(data["main"]["first_request_hit"], None, 0)
    assert data["subagents"] == {} and data["loops"] == {}


def test_days_window_applies_before_pairing(world):
    """Adversarial where: a 40 day old session counted at the default window, or
    paired with the first in-window session, or dropped by a wider one; a window
    shorter than the data age must leave n 0 rather than fail."""
    proj, _ = build_machine(world)
    wide = world.json(proj, "--days", "60")
    assert wide["days"] == 60
    check(wide["main"]["first_request_hit"], 2550 / 5500, 6)
    assert wide["main"]["first_difference"]["pairs"] == 5
    assert wide["main"]["first_difference"]["counts"]["none"] == 2
    check(wide["main"]["next_session_read_share"], 1 / 2, 2)
    narrow = world.json(proj, "--days", "2")
    check(narrow["main"]["whole_hit"], None, 0)
    check(narrow["main"]["first_request_read_median"], None, 0)
    assert narrow["subagents"] == {}
    default_equivalent = world.json(proj, "--days", "4")
    check(default_equivalent["main"]["first_request_hit"], 1550 / 4500, 5)


def test_empty_and_missing_transcript_folders_read_as_no_data(world):
    """Adversarial where: a project that has a vault but no transcripts yet must
    print n=0 and exit 0, not crash on max/median of an empty list."""
    empty = world.project("LEAKEMPTYA-1")
    world.folder(empty)
    missing = world.project("LEAKMISSING-2")
    for project in (empty, missing):
        data = world.json(project)
        for name in ("whole_hit", "first_request_hit", "first_request_read_median",
                     "next_session_read_share", "cost_after_gap_share"):
            check(data["main"][name], None, 0)
        assert data["main"]["first_difference"] == {"counts": counts(), "n": 0, "pairs": 0}
        assert data["cache_writes"]["main"] == {
            "ephemeral_5m": 0, "ephemeral_1h": 0, "unsplit": 0, "n": 0}
        text = world.run(project)
        assert text.returncode == 0
        assert "main first-request hit: n/a (n=0)" in text.stdout


def test_cache_write_split_separates_five_minute_one_hour_and_unsplit(world):
    """Adversarial where: an absent split coerced to zero hides unsplit tokens,
    and main and subagent writes must be summed apart."""
    proj = world.project("LEAKSPLIT-1")
    main = world.session(proj, "m", 0, [1, 2, 3],
                         [use(0, 100, 0, split=(60, 40)), use(0, 50, 0),
                          use(0, 30, 0, split=(30, 0))])
    world.subagent(main, "x", "builder", 4, [5, 6], [use(0, 200, 0, split=(0, 200)),
                                                    use(0, 10, 0)], proj)
    data = world.json(proj)
    assert data["cache_writes"] == {
        "main": {"ephemeral_5m": 90, "ephemeral_1h": 40, "unsplit": 50, "n": 3},
        "subagent": {"ephemeral_5m": 0, "ephemeral_1h": 200, "unsplit": 10, "n": 2}}


def test_cost_after_gap_counts_a_gap_over_an_hour_not_exactly_an_hour(world):
    """Adversarial where: gap boundaries 60 (not after a gap) and 61 (after a
    gap) inside one session, with the 1 hour cache write weighted above the
    5 minute one."""
    proj = world.project("LEAKGAP-1")
    world.session(proj, "a", 0, [1, 61, 122],
                  [use(0, 100, 0, split=(0, 100)), use(0, 100, 0, split=(100, 0)),
                   use(100, 0, 0)])
    data = world.json(proj)
    total = 200 + 125 + 10
    check(data["main"]["cost_after_gap_share"], 10 / total, 3)


# ---- privacy and read-only ------------------------------------------------


def test_json_text_and_saved_file_hold_no_path_session_id_or_project_name(world):
    """Adversarial where: an aggregate that echoes a cwd, project folder, session
    id, file name or message text would leak the project into a saved baseline."""
    proj, _ = build_machine(world)
    saved = world.root / "out" / "baseline.json"
    outputs = [world.run(proj, "--json").stdout, world.run(proj, "--all-compass", "--json").stdout,
               world.run(proj).stdout, world.run(proj, "--all-compass").stdout]
    assert world.run(proj, "--save", str(saved)).returncode == 0
    outputs.append(saved.read_text(encoding="utf-8"))
    for text in outputs:
        assert text.strip()
        for marker in ("LEAK", "fx-LEAKPATH", world.root.name, "claude-test"):
            assert marker not in text, marker
    for text in (outputs[0], outputs[1], outputs[4]):
        assert "/" not in text and "\\" not in text


def test_transcripts_and_ledgers_are_only_read(world):
    """Adversarial where: a reader that rewrites, truncates or adds files in the
    transcript tree or a loop folder breaks the host's own data."""
    proj, _ = build_machine(world)

    def snapshot():
        found = {}
        for base in (world.cfg, proj / ".compass" / "loops"):
            for path in base.rglob("*"):
                found[str(path)] = path.read_bytes() if path.is_file() else None
        return found

    before = snapshot()
    for args in ((), ("--all-compass",), ("--json",), ("--days", "60")):
        assert world.run(proj, *args).returncode == 0
    assert snapshot() == before


# ---- --save ---------------------------------------------------------------


def test_save_writes_the_json_object_to_an_explicit_file_and_creates_parents(world):
    """Adversarial where: the saved file differing from `--json`, missing parent
    folders failing the write, or `--save` leaking the path into stdout JSON."""
    proj, _ = build_machine(world)
    target = world.root / "deep" / "er" / "baseline.json"
    result = world.run(proj, "--json", "--save", str(target))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == json.loads(target.read_text(encoding="utf-8"))
    assert str(target) not in result.stdout


def test_save_without_file_uses_the_machine_file_under_compass_home(world):
    """Adversarial where: the default path must be `<compass home>/cache/<machine
    id>.json`, and a following `--json` must not be swallowed as the file name."""
    proj, _ = build_machine(world)
    result = world.run(proj, "--save", "--json")
    assert result.returncode == 0, result.stderr
    default = world.compass_home / "cache" / f"{sensorlib.machine_id()}.json"
    assert json.loads(result.stdout) == json.loads(default.read_text(encoding="utf-8"))
    assert not (proj / "--json").exists()
    tail = world.run(proj, "--save")
    assert tail.returncode == 0 and "saved" in tail.stderr


def _git_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    return path


def test_save_into_a_git_work_tree_is_refused(world):
    """Adversarial where: a baseline written under a repo would be committed with
    the next `git add`; the refusal must hold for a new nested folder and for a
    default path that resolves into a repo, and must create nothing."""
    proj, _ = build_machine(world)
    assert world.run(proj, "--save", str(world.root / "ok.json")).returncode == 0
    repo = _git_repo(world.root / "repo")
    nested = repo / "new" / "dir" / "out.json"
    result = world.run(proj, "--save", str(nested))
    assert_failed(result, "git")
    assert not (repo / "new").exists()
    inside = _git_repo(world.root / "home2")
    env = world.env(COMPASS_HOME=str(inside / ".compass"))
    default = world.run(proj, "--save", env=env)
    assert_failed(default, "git")
    assert not (inside / ".compass" / "cache").exists()


@pytest.mark.parametrize("kind", ["existing-directory", "parent-is-a-file"])
def test_save_to_an_unwritable_target_exits_one_with_a_message(world, kind):
    """Adversarial where: an OSError from the write must become a stderr message
    and exit 1, never a traceback or exit 2."""
    proj, _ = build_machine(world)
    if kind == "existing-directory":
        target = world.root / "adir"
        target.mkdir()
    else:
        (world.root / "afile").write_text("x", encoding="utf-8")
        target = world.root / "afile" / "out.json"
    assert_failed(world.run(proj, "--save", str(target)))


# ---- --compare ------------------------------------------------------------


def _saved(world, proj, **mutations):
    """Save the current aggregates, apply `{(measure): value}` mutations to the
    `main` object and return the path of the changed copy."""
    base = world.root / "base.json"
    assert world.run(proj, "--save", str(base)).returncode == 0
    data = json.loads(base.read_text(encoding="utf-8"))
    for name, value in mutations.items():
        data["main"][name]["value"] = value
    changed = world.root / "before.json"
    changed.write_text(json.dumps(data), encoding="utf-8")
    return changed


COMPARE_ROWS = [
    ("equal", {}, 0),
    ("first-request-hit-fell-10-points", {"first_request_hit": 0.3444444444444444 + 0.10}, 1),
    ("first-request-hit-fell-4-points", {"first_request_hit": 0.3444444444444444 + 0.04}, 0),
    ("next-session-share-fell-10-points", {"next_session_read_share": 0.6}, 1),
    ("improved", {"first_request_hit": 0.1, "next_session_read_share": 0.1}, 0),
    ("whole-hit-fell-30-points-is-not-guarded", {"whole_hit": 0.85}, 0),
    ("before-value-null", {"first_request_hit": None, "next_session_read_share": None}, 0),
]


@pytest.mark.parametrize("name,mutations,expected", COMPARE_ROWS, ids=[r[0] for r in COMPARE_ROWS])
def test_compare_exit_code_follows_the_two_guarded_measures(world, name, mutations, expected):
    """Adversarial where: the failing condition applied to the wrong measure, the
    wrong direction (an improvement failing) or a null baseline value failing or
    crashing."""
    proj, _ = build_machine(world)
    before = _saved(world, proj, **mutations)
    result = world.run(proj, "--compare", str(before))
    assert result.returncode == expected, result.stderr
    assert "Traceback" not in result.stderr


def test_compare_prints_before_after_and_change_per_measure(world):
    """Adversarial where: the change printed with the wrong sign, taken from
    rounded values or missing for a measure."""
    proj, _ = build_machine(world)
    before = _saved(world, proj, first_request_hit=0.3444444444444444 + 0.10, whole_hit=0.65)
    result = world.run(proj, "--compare", str(before))
    assert result.returncode == 1
    lines = result.stdout.splitlines()
    first = next(line for line in lines if line.startswith("main first-request hit:"))
    assert first == "main first-request hit: before 44.4% after 34.4% change -10.0 points"
    whole = next(line for line in lines if line.startswith("main whole-session hit:"))
    assert whole == "main whole-session hit: before 65.0% after 55.0% change -10.0 points"
    same = next(line for line in lines if line.startswith("main next-session read share:"))
    assert same == "main next-session read share: before 50.0% after 50.0% change +0.0 points"
    median = next(line for line in lines if line.startswith("main first-request read median:"))
    assert median == "main first-request read median: before 400 after 400 change +0 tokens"


def _tiny_projects(world):
    one = world.project("LEAKTINY-ONE")
    world.session(one, "a", 0, [1], [use(500, 500, 0)])
    three = world.project("LEAKTINY-THREE")
    world.session(three, "a", 0, [1], [use(0, 1000, 0)])
    world.session(three, "b", 10, [11], [use(600, 400, 0)])
    world.session(three, "c", 22, [23], [use(0, 1000, 0)])
    return one, three


BOUNDARY_ROWS = [
    ("first-hit-exactly-5-points", "one", "first_request_hit", 0.55, 0),
    ("first-hit-6-points", "one", "first_request_hit", 0.56, 1),
    ("next-share-exactly-5-points", "three", "next_session_read_share", 0.55, 0),
    ("next-share-6-points", "three", "next_session_read_share", 0.56, 1),
]


@pytest.mark.parametrize("name,which,measure,before_value,expected", BOUNDARY_ROWS,
                         ids=[r[0] for r in BOUNDARY_ROWS])
def test_compare_band_edge_is_five_points_not_more(world, name, which, measure, before_value,
                                                   expected):
    """Adversarial where: 0.5 against 0.55 differs by 0.050000000000000044 in
    floating point, so an unrounded comparison fails a fall of exactly 5 points."""
    one, three = _tiny_projects(world)
    proj = {"one": one, "three": three}[which]
    current = world.json(proj)["main"][measure]["value"]
    assert current == approx(0.5)
    before = _saved(world, proj, **{measure: before_value})
    assert world.run(proj, "--compare", str(before)).returncode == expected


def _write_before(world, text):
    path = world.root / "before.json"
    path.write_text(text, encoding="utf-8")
    return path


def test_compare_rejects_a_file_that_is_not_a_saved_report(world):
    """Adversarial where: a missing, empty, non-JSON, wrongly shaped or
    non-finite compare file must exit 1 with a stderr message, never a traceback,
    exit 2, or a silent exit 0 that hides a lost baseline."""
    proj, _ = build_machine(world)
    good = json.loads(_saved(world, proj).read_text(encoding="utf-8"))

    def mutated(edit):
        data = json.loads(json.dumps(good))
        edit(data)
        return json.dumps(data)

    cases = {
        "missing-file": None,
        "empty-file": "",
        "not-json": "this is not json",
        "list": "[]",
        "no-main": "{}",
        "main-is-list": '{"main": []}',
        "measure-not-object": '{"main": {"first_request_hit": 5}}',
        "value-is-string": mutated(lambda d: d["main"]["first_request_hit"].update(value="high")),
        "value-is-bool": mutated(lambda d: d["main"]["first_request_hit"].update(value=True)),
        "value-is-nan": mutated(lambda d: d["main"]["next_session_read_share"].update(
            value=float("nan"))),
    }
    for name, text in cases.items():
        path = world.root / "missing.json" if text is None else _write_before(world, text)
        result = world.run(proj, "--compare", str(path))
        assert_failed(result, "compare")


# ---- argument errors -------------------------------------------------------


@pytest.mark.parametrize("days", ["0", "-3", "abc", "1.5", "", "99999999999999999999"])
def test_days_must_be_a_positive_integer_that_fits(world, days):
    """Adversarial where: zero, negative, fractional, empty and absurdly large
    day counts must exit 1 with a message; a huge count overflows `timedelta`
    unless guarded, and argparse would exit 2."""
    proj, _ = build_machine(world)
    assert_failed(world.run(proj, "--days", days), "days")


@pytest.mark.parametrize("args", [["--days"], ["--compare"], ["--bogus"], ["extra-positional"],
                                  ["--days", "3", "--days"]],
                         ids=["days-missing", "compare-missing", "unknown-flag", "positional",
                              "trailing-days"])
def test_malformed_command_line_exits_one_never_two(world, args):
    """Adversarial where: argparse's exit 2 for a missing value or an unknown
    flag would block the caller; every failure must be exit 1 on stderr."""
    proj, _ = build_machine(world)
    assert_failed(world.run(proj, *args))


def test_transcript_folder_that_is_a_file_does_not_crash(world):
    """Adversarial where: the project's transcript path existing as a plain file
    must end in a message and exit 0 or 1, not a traceback."""
    proj = world.project("LEAKFILEFOLDER-1")
    folder = world.cfg / "projects" / sessionslib.project_key(str(proj))
    folder.write_text("not a folder", encoding="utf-8")
    result = world.run(proj)
    assert result.returncode in (0, 1)
    assert "traceback" not in result.stderr.lower()
    assert "unknown command" not in result.stderr and "not implemented" not in result.stderr
