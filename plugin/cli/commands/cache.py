"""`compass cache [--all-compass] [--days N] [--json] [--save [FILE]] [--compare FILE]`
- how well the host's prompt cache served the sessions of a project.

The command reads Claude Code session transcripts (through `cachelib`, which
only opens them for reading) and the loop ledgers under `<vault>/loops/` and
prints aggregates: counts, ratios, token sums and the kind of the first block
that differs between two consecutive requests. No path, session id, project
name or message text reaches the output, a saved file included.

Scope. Without `--all-compass` the command reads the transcript folder of the
project whose vault holds the working directory (the main checkout's folder
when run from a linked git worktree). With it, every folder under
`<CLAUDE_CONFIG_DIR>/projects` whose first recorded `cwd` is an existing
directory holding a `.compass/` directory is read; the other folders are
skipped and only the number read is reported. `--days N` (default 30, an
integer of at least 1 that `now - N days` can represent) keeps the main
sessions whose first record lies within the last N days; a subagent belongs to
its parent session. Consecutive session pairs are formed after the window is
applied and never across projects. A missing or empty transcript folder reads
as no data: every `n` is 0 and every `value` null.

Measures. Each is `{"value": float | null, "n": int}` with ratios as fractions
between 0 and 1, pooled over all requests in scope (tokens-weighted), never an
average of per-session ratios. A request's hit is `cache read / (cache read +
cache creation + input)` tokens.

- `main.whole_hit`: every request of the main sessions; n is the sessions.
- `main.first_request_hit`: the first request of each session; n is the sessions.
- `main.first_request_read_median`: median cache-read tokens of the first requests.
- `main.next_session_read_share`: among sessions that start 5 to 60 minutes
  (inclusive) after the previous session's last request, the share whose first
  request read 60% or more (inclusive) of its tokens; n is those sessions.
- `main.cost_after_gap_share`: modeled cost of requests that follow a gap over
  60 minutes (strictly) since the previous request of the same session, over
  the modeled cost of every request; n is the requests. Weights: input 1.0,
  cache read 0.1, cache creation 1.25, 1-hour cache creation 2.0.
- `main.first_difference`: for each consecutive pair of sessions whose first
  requests are comparable (same parameters and shape), the kind of the first
  differing block; `counts` has every `cachelib.KINDS` entry, `n` is the
  comparable pairs and `pairs` all pairs.
- `subagents.<type>`: one entry per known agent type: the agent files shipped
  in `templates/agents/`, the host's built-in types and `unknown` (a transcript
  without a type); any other type name is counted under `other`, so no
  project-derived name reaches the output. `first_request_hit` (tokens-weighted, the headline),
  `first_request_read_share` (the share of first requests that read anything),
  `whole_hit`, and `first_difference` over consecutive same-type siblings of
  one parent ordered by start.
- `loops.<folder name>.hit`: cache read over read + creation + input tokens of
  the ledger's `run` rows, pooled by folder name; n is the runs.
- `cache_writes.main` / `cache_writes.subagent`: cache-creation tokens written
  with a 5-minute lifetime, a 1-hour lifetime, or without a split, and the
  number of requests.

Output. The text report prints one line per measure as `<label>: <value>
(n=<n>)`. `--json` prints the whole object (`version`, `days`, `projects`,
`main`, `subagents`, `loops`, `cache_writes`) as one line instead; it is the
same for fixed transcripts. `--save [FILE]` writes that object to FILE (default
`<COMPASS_HOME or ~/.compass>/cache/<machine id>.json`), creating parent
folders, and prints `saved <path>` on stderr; a path inside a git work tree is
refused. `--compare FILE` reads a saved object and prints, per measure present
in both, `<label>: before <b> after <a> change <c>` instead of the text report
(on stderr when `--json` is given); it exits 1 when the first-request hit or
the next-session read share fell by more than 5.0 points, the change taken
from the unrounded values and rounded to one decimal, or when one of the two
has a value in the saved object and none now (a window without data), naming
the measure on stderr. A saved object whose
`main.first_request_hit` or `main.next_session_read_share` is not a measure
with a finite number or null value is refused.

Every failure prints a message on stderr and returns 1; the command never
exits 2.
"""

import json
import math
import re
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cachelib
import sensorlib
import sessionslib
import vaultlib

USAGE = """\
usage: compass cache [--all-compass] [--days N] [--json] [--save [FILE]] [--compare FILE]

Report how well the host's prompt cache served the project's sessions.

  --all-compass   read every project whose vault holds the transcripts' cwd
  --days N        keep sessions started within the last N days (default 30)
  --json          print the aggregates as one JSON object
  --save [FILE]   write the JSON object to FILE (default under ~/.compass/cache/)
  --compare FILE  print before, after and change against a saved object; exit 1
                  when the first-request hit or next-session read share fell
                  by more than 5 points
"""

VERSION = 1
DEFAULT_DAYS = 30
# A day count longer than this is refused before int() sees it.
MAX_DIGITS = 9
GAP_NEXT_MIN = 5
GAP_NEXT_MAX = 60
GAP_COST_MINUTES = 60
READ_SHARE_NUM, READ_SHARE_DEN = 3, 5
FALL_LIMIT_POINTS = 5.0
WEIGHT_INPUT = 1.0
WEIGHT_READ = 0.1
WEIGHT_CREATE = 1.25
WEIGHT_CREATE_1H = 2.0
GUARDED = (("first_request_hit", "main first-request hit"),
           ("next_session_read_share", "main next-session read share"))
# (JSON key, label, kind) of the main measures a comparison prints.
MAIN_ROWS = (
    ("whole_hit", "main whole-session hit", "ratio"),
    ("first_request_hit", "main first-request hit", "ratio"),
    ("first_request_read_median", "main first-request read median", "tokens"),
    ("next_session_read_share", "main next-session read share", "ratio"),
    ("cost_after_gap_share", "main cost after gaps over 1 hour", "ratio"),
)
SUBAGENT_HEADLINE = "first_request_hit"
BUILT_IN_AGENTS = ("general-purpose", "Explore", "Plan", "statusline-setup",
                   "claude-code-guide", "fork")
OTHER_AGENT = "other"
UNKNOWN_AGENT = "unknown"


class UsageError(Exception):
    """A bad argument or file; the message goes to stderr and the exit code is 1."""


def _fail(message):
    sys.stderr.write(f"compass cache: {message}\n")
    return 1


# ---- arguments --------------------------------------------------------------


def _days(raw):
    """The day count of `raw`, or UsageError."""
    if raw is None or not re.fullmatch(r"[0-9]{1,%d}" % MAX_DIGITS, raw) or int(raw) < 1:
        shown = "missing" if raw is None else repr(raw[:40])
        raise UsageError(f"--days needs an integer of 1 or more, got {shown}")
    days = int(raw)
    try:
        datetime.now(timezone.utc) - timedelta(days=days)
    except (OverflowError, ValueError):
        raise UsageError(f"--days {days} reaches back past the earliest date") from None
    return days


def _parse(args):
    options = {"all": False, "days": DEFAULT_DAYS, "json": False, "save": False,
               "compare": None, "help": False}
    index = 0
    while index < len(args):
        arg = args[index]
        following = args[index + 1] if index + 1 < len(args) else None
        if arg == "--all-compass":
            options["all"] = True
        elif arg == "--json":
            options["json"] = True
        elif arg in ("-h", "--help"):
            options["help"] = True
        elif arg == "--days":
            options["days"] = _days(following)
            index += 1
        elif arg == "--compare":
            if following is None or not following:
                raise UsageError("--compare needs a file")
            options["compare"] = following
            index += 1
        elif arg == "--save":
            if following is not None and following and not following.startswith("--"):
                options["save"] = following
                index += 1
            else:
                options["save"] = True
        else:
            raise UsageError(f"unknown argument {arg[:40]!r} (see compass cache --help)")
        index += 1
    return options


# ---- accumulators -----------------------------------------------------------


class _Ratio:
    """A pooled ratio: numerator and denominator sums and a count of items."""

    def __init__(self):
        self.num = 0
        self.den = 0
        self.n = 0

    def add(self, num, den, n=1):
        self.num += num
        self.den += den
        self.n += n

    def measure(self):
        return {"value": self.num / self.den if self.den else None, "n": self.n}


class _Diff:
    """First-differing-block counts over consecutive pairs."""

    def __init__(self):
        self.counts = {kind: 0 for kind in cachelib.KINDS}
        self.n = 0
        self.pairs = 0

    def add(self, comparison):
        self.pairs += 1
        if comparison.comparable:
            self.n += 1
            kind = comparison.first_difference
            self.counts[kind if kind in self.counts else "unknown"] += 1

    def result(self):
        return {"counts": dict(self.counts), "n": self.n, "pairs": self.pairs}


class _Writes:
    """Cache-creation tokens by lifetime, over requests."""

    def __init__(self):
        self.five = 0
        self.hour = 0
        self.unsplit = 0
        self.n = 0

    def add(self, request):
        self.n += 1
        five, hour = request.ephemeral_5m_input_tokens, request.ephemeral_1h_input_tokens
        if five is None and hour is None:
            self.unsplit += request.cache_creation_input_tokens
        else:
            self.five += five or 0
            self.hour += hour or 0

    def result(self):
        return {"ephemeral_5m": self.five, "ephemeral_1h": self.hour,
                "unsplit": self.unsplit, "n": self.n}


class _SubagentType:
    def __init__(self):
        self.whole = _Ratio()
        self.first_hit = _Ratio()
        self.first_read = _Ratio()
        self.diff = _Diff()

    def result(self):
        return {"whole_hit": self.whole.measure(),
                "first_request_hit": self.first_hit.measure(),
                "first_request_read_share": self.first_read.measure(),
                "first_difference": self.diff.result()}


class _Tally:
    """Everything read from the projects in scope."""

    def __init__(self):
        self.whole = _Ratio()
        self.first_hit = _Ratio()
        self.first_reads = []
        self.next_share = _Ratio()
        self.gap_cost = _Ratio()
        self.diff = _Diff()
        self.subagents = {}
        self.loops = {}
        self.main_writes = _Writes()
        self.subagent_writes = _Writes()


# ---- reading ----------------------------------------------------------------


def _when(value):
    """A timezone-aware datetime for an ISO timestamp string, else None."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _tokens(request):
    return (request.cache_read_input_tokens + request.cache_creation_input_tokens
            + request.input_tokens)


def _cost(request):
    """Modeled cost of a request in input-token units."""
    creation = request.cache_creation_input_tokens
    hour = min(request.ephemeral_1h_input_tokens or 0, creation)
    return (WEIGHT_INPUT * request.input_tokens + WEIGHT_READ * request.cache_read_input_tokens
            + WEIGHT_CREATE * (creation - hour) + WEIGHT_CREATE_1H * hour)


def _transcripts(folder):
    """The top-level `*.jsonl` files of a transcript folder; none when the
    folder is missing or not a folder."""
    try:
        return sorted(p for p in folder.glob("*.jsonl") if p.is_file())
    except OSError:
        return []


def _started(path):
    return _when(cachelib.session_summary(path).started_at)


def _known_agent_types():
    """The agent type names a subagent row may carry: the agent files shipped
    beside the CLI (`templates/agents/*.md` of the plugin, or `agents/*.md` of
    an install), the host's built-in types and `unknown`."""
    root = Path(__file__).resolve().parents[2]
    names = set(BUILT_IN_AGENTS) | {UNKNOWN_AGENT}
    for folder in (root / "templates" / "agents", root / "agents"):
        try:
            names.update(p.stem for p in folder.glob("*.md") if p.is_file())
        except OSError:
            continue
    return names


def _row_type(kind, known):
    """The key a subagent of type `kind` is counted under."""
    return kind if kind in known else OTHER_AGENT


def _agent_type(path):
    meta = path.with_name(path.name[: -len(".jsonl")] + ".meta.json")
    try:
        data = json.loads(meta.read_bytes().decode("utf-8-sig"))
    except (OSError, ValueError, RecursionError):
        return "unknown"
    kind = data.get("agentType") if isinstance(data, dict) else None
    return kind if isinstance(kind, str) and kind else "unknown"


def _read_main(tally, sessions):
    """Fold the main sessions (path, start, requests), already in start
    order, into `tally`."""
    previous = None
    for path, _, reqs in sessions:
        first = reqs[0]
        tally.whole.add(sum(r.cache_read_input_tokens for r in reqs),
                        sum(_tokens(r) for r in reqs))
        tally.first_hit.add(first.cache_read_input_tokens, _tokens(first))
        tally.first_reads.append(first.cache_read_input_tokens)
        last_time = None
        for request in reqs:
            tally.main_writes.add(request)
            moment = _when(request.timestamp)
            cost = _cost(request)
            after_gap = (moment is not None and last_time is not None
                         and (moment - last_time).total_seconds() > GAP_COST_MINUTES * 60)
            tally.gap_cost.add(cost if after_gap else 0, cost)
            last_time = moment
        if previous is not None:
            comparison = cachelib.compare_first_requests(previous, path)
            tally.diff.add(comparison)
            gap = comparison.gap_minutes
            if gap is not None and GAP_NEXT_MIN <= gap <= GAP_NEXT_MAX:
                tally.next_share.add(
                    1 if first.cache_read_input_tokens * READ_SHARE_DEN
                    >= READ_SHARE_NUM * _tokens(first) else 0, 1, 1)
        previous = path


def _read_subagents(tally, session_path, known):
    """Fold the subagents of one parent session into `tally`."""
    try:
        paths = sessionslib.subagent_transcripts(session_path)
    except OSError:
        return
    by_type = {}
    for path in paths:
        reqs = cachelib.requests(path)
        if not reqs:
            continue
        kind = _agent_type(path)
        stats = tally.subagents.setdefault(_row_type(kind, known), _SubagentType())
        first = reqs[0]
        stats.whole.add(sum(r.cache_read_input_tokens for r in reqs),
                        sum(_tokens(r) for r in reqs))
        stats.first_hit.add(first.cache_read_input_tokens, _tokens(first))
        stats.first_read.add(1 if first.cache_read_input_tokens > 0 else 0, 1, 1)
        for request in reqs:
            tally.subagent_writes.add(request)
        started = _started(path)
        by_type.setdefault(kind, []).append((started is None, started, path.name, path))
    for kind, rows in by_type.items():
        rows.sort(key=lambda row: (row[0], row[1] or datetime.min.replace(tzinfo=timezone.utc),
                                   row[2]))
        for (_, _, _, earlier), (_, _, _, later) in zip(rows, rows[1:]):
            tally.subagents[_row_type(kind, known)].diff.add(cachelib.compare_first_requests(earlier, later))


def _read_loops(tally, vault):
    """Fold every `<vault>/loops/*/ledger.jsonl` into `tally`, pooled by folder name."""
    try:
        folders = sorted(p for p in (vault / "loops").iterdir() if p.is_dir())
    except OSError:
        return
    for folder in folders:
        if not (folder / "ledger.jsonl").is_file():
            continue
        totals = cachelib.ledger_totals(folder)
        pool = tally.loops.setdefault(folder.name, _Ratio())
        pool.add(totals.cache_read_tokens,
                 totals.cache_read_tokens + totals.cache_creation_tokens + totals.input_tokens,
                 totals.run_count)


def _read_project(tally, folders, vault, cutoff):
    """Fold one project's transcript folders and loop ledgers into `tally`."""
    sessions = []
    in_window = []
    for path in [p for folder in folders for p in _transcripts(folder)]:
        started = _started(path)
        if started is None or started < cutoff:
            continue
        in_window.append(path)
        reqs = cachelib.requests(path)
        if reqs:
            sessions.append((path, started, reqs))
    sessions.sort(key=lambda row: (row[1], str(row[0])))
    _read_main(tally, sessions)
    known = _known_agent_types()
    for path in in_window:
        _read_subagents(tally, path, known)
    _read_loops(tally, vault)


def _first_cwd(folder):
    """The first `cwd` recorded in a transcript folder's top-level files."""
    for path in _transcripts(folder):
        try:
            for record in sessionslib.records(path):
                cwd = record.get("cwd")
                if isinstance(cwd, str) and cwd:
                    return cwd
        except (OSError, ValueError):
            continue
    return None


def _project_of(start, honor_env=False):
    """(transcript folder, vault) of the project whose vault is the nearest
    `.compass/` at or above `start`, read from its main checkout; raises
    FileNotFoundError when there is none."""
    found = vaultlib.find_vault_root(start, honor_env=honor_env)
    main = sessionslib.main_checkout(found.parent)
    vault = main / ".compass"
    return sessionslib.transcripts_dir(main), vault if vault.is_dir() else found


def _vault_projects():
    """([transcript folders], vault) of every project whose vault lies at or
    above the first recorded cwd of a transcript folder, that cwd being an
    existing directory. A project's folders are those of its root and of the
    subfolders sessions started in; folders recording one cwd count once."""
    root = sessionslib.config_dir() / "projects"
    try:
        folders = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        return []
    projects = {}
    seen = set()
    for folder in folders:
        cwd = _first_cwd(folder)
        if cwd is None:
            continue
        try:
            if not Path(cwd).is_dir():
                continue
            _, vault = _project_of(cwd)
            vault_key, cwd_key = vault.resolve(), Path(cwd).resolve()
        except (OSError, ValueError, FileNotFoundError):
            continue
        if cwd_key in seen:
            continue
        seen.add(cwd_key)
        projects.setdefault(vault_key, (vault, []))[1].append(folder)
    return [(group, vault) for vault, group in projects.values()]


def _this_project():
    """([transcript folder], vault) of the project holding the working directory."""
    folder, vault = _project_of(None, honor_env=True)
    return [folder], vault


def collect(options, cutoff):
    """The report object for the options and window start."""
    tally = _Tally()
    if options["all"]:
        projects = _vault_projects()
    else:
        projects = [_this_project()]
    for folders, vault in projects:
        _read_project(tally, folders, vault, cutoff)
    reads = sorted(tally.first_reads)
    median = float(statistics.median(reads)) if reads else None
    return {
        "version": VERSION,
        "days": options["days"],
        "projects": len(projects) if options["all"] else None,
        "main": {
            "whole_hit": tally.whole.measure(),
            "first_request_hit": tally.first_hit.measure(),
            "first_request_read_median": {"value": median, "n": len(reads)},
            "next_session_read_share": tally.next_share.measure(),
            "cost_after_gap_share": tally.gap_cost.measure(),
            "first_difference": tally.diff.result(),
        },
        "subagents": {kind: tally.subagents[kind].result() for kind in sorted(tally.subagents)},
        "loops": {name: {"hit": tally.loops[name].measure()} for name in sorted(tally.loops)},
        "cache_writes": {"main": tally.main_writes.result(),
                         "subagent": tally.subagent_writes.result()},
    }


# ---- text report ------------------------------------------------------------


def _pct(value):
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _tok(value):
    return "n/a" if value is None else f"{round(value)}"


def _measure_line(label, measure, shown):
    return f"{label}: {shown(measure['value'])} (n={measure['n']})"


def _diff_line(label, diff):
    kinds = ", ".join(f"{kind}={diff['counts'][kind]}" for kind in cachelib.KINDS
                      if diff["counts"].get(kind))
    return f"{label} (n={diff['n']} of {diff['pairs']} pairs): {kinds or 'n/a'}"


def _writes_line(label, writes):
    return (f"{label}: 5m={writes['ephemeral_5m']} 1h={writes['ephemeral_1h']} "
            f"unsplit={writes['unsplit']} (n={writes['n']})")


def report_lines(data):
    main = data["main"]
    lines = []
    if data["projects"] is not None:
        lines.append(f"projects read: {data['projects']}")
    lines.append(_measure_line("main whole-session hit", main["whole_hit"], _pct))
    lines.append(_measure_line("main first-request hit", main["first_request_hit"], _pct))
    median = main["first_request_read_median"]
    lines.append(f"main first-request read median: "
                 f"{'n/a' if median['value'] is None else _tok(median['value']) + ' tokens'} "
                 f"(n={median['n']})")
    lines.append(_measure_line("main next-session read share", main["next_session_read_share"],
                               _pct))
    lines.append(_measure_line("main cost after gaps over 1 hour", main["cost_after_gap_share"],
                               _pct))
    lines.append(_diff_line("main first differing block", main["first_difference"]))
    for kind, stats in data["subagents"].items():
        prefix = f"subagent {kind}"
        lines.append(_measure_line(f"{prefix} first-request hit (tokens-weighted)",
                                   stats["first_request_hit"], _pct))
        lines.append(_measure_line(f"{prefix} first-request read share (any read)",
                                   stats["first_request_read_share"], _pct))
        lines.append(_measure_line(f"{prefix} whole-session hit", stats["whole_hit"], _pct))
        lines.append(_diff_line(f"{prefix} first differing block", stats["first_difference"]))
    for name, loop in data["loops"].items():
        lines.append(_measure_line(f"loop {name} hit", loop["hit"], _pct))
    lines.append(_writes_line("main cache writes", data["cache_writes"]["main"]))
    lines.append(_writes_line("subagent cache writes", data["cache_writes"]["subagent"]))
    return lines


# ---- save -------------------------------------------------------------------


def _inside_git_work_tree(path):
    """True when `path` or any folder above it holds a `.git` entry."""
    try:
        probe = Path(path).resolve()
    except (OSError, ValueError):
        probe = Path(path).absolute()
    return any((folder / ".git").exists() for folder in probe.parents)


def _save_path(choice):
    if choice is True:
        return sessionslib.compass_home() / "cache" / f"{sensorlib.machine_id()}.json"
    return Path(choice)


def save(data, choice):
    """Write `data` to the chosen file; the path written, or UsageError."""
    path = _save_path(choice)
    if _inside_git_work_tree(path):
        raise UsageError(f"--save refuses {path}: it is inside a git work tree")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data) + "\n", encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"cannot write {path}: {exc.strerror or exc}") from None
    return path


# ---- compare ----------------------------------------------------------------


def _valid_value(measure):
    """(True, value) when `measure` is a dict whose `value` is a finite
    number or null; a bool is not a number."""
    if not isinstance(measure, dict) or "value" not in measure:
        return False, None
    value = measure["value"]
    if value is None:
        return True, None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return False, None
    return True, float(value)


def _load_before(path):
    try:
        data = json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    except (OSError, ValueError, RecursionError) as exc:
        reason = getattr(exc, "strerror", None) or "not a JSON file"
        raise UsageError(f"--compare cannot read {path}: {reason}") from None
    main = data.get("main") if isinstance(data, dict) else None
    if not isinstance(main, dict):
        raise UsageError(f"--compare file {path} is not a saved report: no `main` object")
    for key, label in GUARDED:
        if not _valid_value(main.get(key))[0]:
            raise UsageError(f"--compare file {path} is not a saved report: "
                             f"`main.{key}` is not a measure with a finite value or null")
    return data


def _points(before, after):
    """The change in percentage points, rounded to one decimal; None when
    either value is missing."""
    if before is None or after is None:
        return None
    return round((after - before) * 100, 1) + 0.0


def _compare_row(label, kind, before, after):
    if kind == "tokens":
        shown = _tok
        change = "n/a" if before is None or after is None else f"{round(after) - round(before):+d} tokens"
    else:
        shown = _pct
        points = _points(before, after)
        change = "n/a" if points is None else f"{points:+.1f} points"
    return f"{label}: before {shown(before)} after {shown(after)} change {change}"


def compare(before_data, data):
    """(lines, failures) of a comparison against a saved report."""
    lines = []
    failures = []
    before_main = before_data["main"]
    for key, label, kind in MAIN_ROWS:
        ok, before = _valid_value(before_main.get(key))
        if not ok:
            continue
        after = data["main"][key]["value"]
        lines.append(_compare_row(label, kind, before, after))
        if key in dict(GUARDED):
            points = _points(before, after)
            if before is not None and after is None:
                failures.append(f"{label} has no data in this window")
            elif points is not None and points < -FALL_LIMIT_POINTS:
                failures.append(f"{label} fell {-points:.1f} points (limit {FALL_LIMIT_POINTS})")
    before_agents = before_data.get("subagents")
    for kind, stats in data["subagents"].items():
        if not isinstance(before_agents, dict) or not isinstance(before_agents.get(kind), dict):
            continue
        ok, before = _valid_value(before_agents[kind].get(SUBAGENT_HEADLINE))
        if ok:
            lines.append(_compare_row(f"subagent {kind} first-request hit (tokens-weighted)",
                                      "ratio", before, stats[SUBAGENT_HEADLINE]["value"]))
    return lines, failures


# ---- entry ------------------------------------------------------------------


def _run(args):
    options = _parse(args)
    if options["help"]:
        sys.stdout.write(USAGE)
        return 0
    before = _load_before(options["compare"]) if options["compare"] else None
    cutoff = datetime.now(timezone.utc) - timedelta(days=options["days"])
    try:
        data = collect(options, cutoff)
    except FileNotFoundError as exc:
        raise UsageError(str(exc)) from None
    if options["save"]:
        sys.stderr.write(f"saved {save(data, options['save'])}\n")
    failures = []
    if before is not None:
        lines, failures = compare(before, data)
    else:
        lines = report_lines(data)
    if options["json"]:
        sys.stdout.write(json.dumps(data) + "\n")
        if before is not None:
            sys.stderr.write("\n".join(lines) + "\n")
    else:
        sys.stdout.write("\n".join(lines) + "\n")
    for failure in failures:
        sys.stderr.write(f"compass cache: --compare: {failure}\n")
    return 1 if failures else 0


def run(args):
    try:
        return _run(list(args))
    except UsageError as exc:
        return _fail(str(exc))
    except OSError as exc:
        return _fail(str(exc))
