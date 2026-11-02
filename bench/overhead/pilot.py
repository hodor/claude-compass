"""The pilot: a topic probe, three frozen topics and twelve judged builds.

`run_pilot` runs the stages in order and skips each stage the run log and the
private files show finished, so running the same command again resumes after a
usage-limit halt:

1. Probe. Unseeded and seeded topic picks go into the pool; the pool takes the
   form (seeded or unseeded) whose probe picks fill more distinct classes.
2. Topics. Further picks in that form are frozen with goal lists and briefs.
3. Builds. Every pilot topic is built `runs_per_arm` times in each arm, one
   build at a time, each in a fresh project. The first topic's first run in each
   arm comes first; a failed build there blocks the pilot.
4. Judging. Every closed build is scored against its topic's frozen goals.
5. Report. A complete pilot writes aggregates only: no topic text, goal or
   brief text, path, project name, session id or model output.

The run log, the pool, the goals and the records live under the private root;
a private root inside a git work tree is refused.

    python pilot.py --private-root DIR --projects-root DIR [--report FILE]

Exit codes: 0 complete, 1 blocked or refused, 3 usage limit.
"""

import argparse
import contextlib
import datetime
import io
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import drive as drive_module
import goals
import judge as judge_module
import launch
import records
import sandbox
import stats
import topics

ARMS = records.ARMS
WINDOW_HOURS = stats.WINDOW_SECONDS / 3600
# Tries a pick, a freeze or a judgement gets when its reply is unusable.
ATTEMPTS = 3
# Seed of the bootstrap over topics.
BOOTSTRAP_SEED = 0

_WORD = re.compile(r"\w+")
# Words separated by white space only.
_RUN = re.compile(r"\w+(?:[^\S\n]+\w+)*")
_STOPWORDS = frozenset(
    "a an the of to and or in on for with as at by is are be it its this that from into".split()
)
_NAME_SIZES = (2, 3, 4)
_NODE_LIMIT = 200000


class PilotError(Exception):
    """The run log and the private files disagree."""


class _Halt(Exception):
    """A stage stopped the pilot with `status`."""

    def __init__(self, status, resets_at=None):
        super().__init__(status)
        self.status = status
        self.resets_at = resets_at


@dataclass
class PilotResult:
    status: str
    resets_at: float | None = None
    form: str | None = None
    topics: list = field(default_factory=list)
    probe: dict = field(default_factory=dict)
    closed: int = 0
    refused: int = 0
    aggregates: dict | None = None


def _tokens(text):
    return _WORD.findall(text)


def _overlaps(first, second):
    """True when one lower-case phrase occurs inside the other as whole words."""
    return f" {first} " in f" {second} " or f" {second} " in f" {first} "


def _candidates(text, frequency):
    """Name candidates for one item text, best first: phrases of two to four
    consecutive words that no punctuation separates, so each name occurs in the
    item's wording exactly as written. Phrases without filler words rank first,
    then those with words no other item uses, then shorter ones."""
    found = {}
    for run in _RUN.finditer(text):
        words = list(_WORD.finditer(run.group()))
        for size in _NAME_SIZES:
            for start in range(len(words) - size + 1):
                span = words[start:start + size]
                name = run.group()[span[0].start():span[-1].end()]
                lowered = [word.group().lower() for word in span]
                key = " ".join(lowered)
                if key in found:
                    continue
                filler = sum(1 for word in lowered if word in _STOPWORDS)
                unique = sum(1 for word in lowered if frequency[word] == 1)
                rank = (
                    filler, -unique, size, sum(frequency[word] for word in lowered),
                    run.start() + span[0].start(),
                )
                found[key] = (rank, name)
    return [(key, name) for key, (_, name) in sorted(found.items(), key=lambda pair: pair[1][0])]


def drive_brief(items, brief_text):
    """The brief the simulated human reads: {"context", "items": [{"id", "name", "detail"}]}.

    Each item gets a name of two to four consecutive words of its text with no
    punctuation between them, unique in the list and not a whole-word phrase of any other name, so a message
    that names one item names that item alone. Raises ValueError for an item
    text of fewer than two words and for items that cannot be named apart.
    """
    token_lists = [[word.lower() for word in _tokens(item["text"])] for item in items]
    if any(len(words) < 2 for words in token_lists):
        raise ValueError("an item text needs at least two words to be named")
    if len({tuple(words) for words in token_lists}) != len(token_lists):
        raise ValueError("two items have the same text")
    frequency = {}
    for words in token_lists:
        for word in set(words):
            frequency[word] = sum(1 for other in token_lists if word in other)
    options = [_candidates(item["text"], frequency) for item in items]

    chosen = []
    visited = 0

    def place(index):
        nonlocal visited
        if index == len(options):
            return True
        for key, name in options[index]:
            visited += 1
            if visited > _NODE_LIMIT:
                raise ValueError("the items cannot be named apart")
            if not any(_overlaps(key, other) for other, _ in chosen):
                chosen.append((key, name))
                if place(index + 1):
                    return True
                chosen.pop()
        return False

    if not place(0):
        raise ValueError("the items cannot be named apart")
    return {
        "context": brief_text,
        "items": [
            {"id": item["id"], "name": name, "detail": item["text"]}
            for item, (_, name) in zip(items, chosen)
        ],
    }


def run_log_path(private_root):
    return Path(private_root) / "pilot" / "run-log.jsonl"


def _opening_message(entry):
    return (
        "I would like you to build a software project for me.\n\n"
        f"{entry['title']}\n\n{entry['description']}\n"
    )


def _last_json_line(text):
    """The last line of `text` that is a JSON object, or {}."""
    for line in reversed(text.splitlines()):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _raw_total(row):
    return sum(sum(counts.values()) for counts in row.get("models", {}).values())


def _mean(values):
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


class _Pilot:
    def __init__(
        self, *, repo_root, private_root, projects_root, claude_cmd, parent_env, probe_size,
        topic_count, runs_per_arm, pick, freeze, judge, drive, new_project, clock,
    ):
        self.repo_root = Path(repo_root)
        self.private_root = Path(private_root)
        self.projects_root = projects_root
        self.claude_cmd = claude_cmd
        self.parent_env = parent_env
        self.probe_size = probe_size
        self.topic_count = topic_count
        self.runs_per_arm = runs_per_arm
        self.pick, self.freeze, self.judge = pick, freeze, judge
        self.drive, self.new_project, self.clock = drive, new_project, clock
        self.log_path = run_log_path(self.private_root)

    def session_options(self):
        return {
            "repo_root": self.repo_root, "private_root": self.private_root,
            "claude_cmd": self.claude_cmd, "parent_env": self.parent_env,
        }

    # run log

    def log(self, **event):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        lead = "" if self._ends_cleanly() else "\n"
        with open(self.log_path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(lead + json.dumps(event) + "\n")

    def _ends_cleanly(self):
        """True when the log is absent, empty or ends in a newline."""
        try:
            with open(self.log_path, "rb") as handle:
                handle.seek(0, 2)
                if handle.tell() == 0:
                    return True
                handle.seek(-1, 2)
                return handle.read(1) == b"\n"
        except FileNotFoundError:
            return True

    def events(self, name=None):
        if not self.log_path.exists():
            return []
        found = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and name in (None, event.get("event")):
                found.append(event)
        return found

    # sessions with retries

    def attempt(self, call):
        """Run `call`, trying again when the session failed or its reply was unusable."""
        for number in range(1, ATTEMPTS + 1):
            try:
                return call()
            except ValueError:
                if number == ATTEMPTS:
                    raise
            except topics.SessionError as error:
                if error.status == launch.USAGE_LIMIT or number == ATTEMPTS:
                    raise

    # stages

    def pilot_topics(self):
        return [e["topic"] for e in self.events("picked") if e["stage"] == "pilot"]

    def probe_topics(self):
        return [e["topic"] for e in self.events("picked") if e["stage"] == "probe"]

    def pick_stage(self):
        plan = [(False, None)] * self.probe_size + [(True, seed) for seed in range(self.probe_size)]
        for seeded, seed in plan[len(self.probe_topics()):]:
            self.pick_one("probe", seeded, seed)
        form = self.form()
        if form is None:
            pool = {entry["id"]: entry for entry in topics.load_pool(self.private_root)}
            form = topics.choose_form([pool[t] for t in self.probe_topics() if t in pool])
            self.log(event="form-chosen", form=form)
        seeded = form == "seeded"
        for number in range(len(self.pilot_topics()), self.topic_count):
            self.pick_one("pilot", seeded, self.probe_size + number if seeded else None)

    def pick_one(self, stage, seeded, seed):
        entry = self.attempt(lambda: self.pick(seeded=seeded, seed=seed, **self.session_options()))
        self.log(
            event="picked", stage=stage, topic=entry["id"],
            form="seeded" if seeded else "unseeded", seed=seed,
        )

    def form(self):
        chosen = self.events("form-chosen")
        return chosen[-1]["form"] if chosen else None

    def freeze_stage(self):
        for topic_id in self.pilot_topics():
            try:
                goals.require_goals(topic_id, self.private_root)
                continue
            except goals.GoalsMissing:
                pass
            self.attempt(lambda: self.freeze(topic_id, **self.session_options()))
            self.log(event="frozen", topic=topic_id)

    def slots(self):
        slots = []
        for index, topic_id in enumerate(self.pilot_topics()):
            for run in range(1, self.runs_per_arm + 1):
                arms = ARMS if (index + run) % 2 == 1 else tuple(reversed(ARMS))
                slots.extend((topic_id, arm, run) for arm in arms)
        return slots

    @staticmethod
    def key(event):
        return (event["topic"], event["arm"], event["run"])

    def build_stage(self):
        slots = self.slots()
        smoke = set(slots[:2])
        closed = {self.key(e): e for e in self.events("build-closed")}
        refused = {self.key(e) for e in self.events("build-refused")}
        if any(slot in closed and closed[slot]["exit"] != 0 for slot in smoke):
            raise _Halt("blocked")
        judged = {self.key(e) for e in self.events("judged")}
        for slot in slots:
            if slot in closed and slot not in judged:
                self.judge_build(closed[slot])
        for slot in slots:
            if slot in closed or slot in refused:
                continue
            event = self.run_build(slot)
            if slot in smoke and event["exit"] != 0:
                self.log(event="blocked", topic=slot[0], arm=slot[1], run=slot[2], exit=event["exit"])
                raise _Halt("blocked")
            self.judge_build(event)

    def record_marks(self):
        """{records file name: line count} before a build."""
        folder = self.private_root / "records"
        if not folder.is_dir():
            return {}
        return {
            path.name: len(path.read_text(encoding="utf-8").splitlines())
            for path in sorted(folder.glob("*.jsonl"))
        }

    def new_rows(self, marks, arm):
        """The role `build` rows of `arm` appended since `marks`."""
        folder = self.private_root / "records"
        rows = []
        for path in sorted(folder.glob("*.jsonl")) if folder.is_dir() else []:
            lines = path.read_text(encoding="utf-8").splitlines()
            for line in lines[marks.get(path.name, 0):]:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and row.get("role") == "build" and row.get("arm") == arm:
                    rows.append(row)
        return rows

    def run_build(self, slot):
        topic_id, arm, run = slot
        entry = next((e for e in topics.load_pool(self.private_root) if e["id"] == topic_id), None)
        if entry is None:
            raise PilotError(f"pilot topic {topic_id} is in the run log but not in the pool")
        goal_list = goals.require_goals(topic_id, self.private_root)
        project = self.new_project(self.projects_root)

        folder = self.private_root / "pilot" / "builds" / Path(project).name
        folder.mkdir(parents=True, exist_ok=True)
        opening, brief = folder / "opening.txt", folder / "brief.json"
        opening.write_text(_opening_message(entry), encoding="utf-8")
        brief.write_text(
            json.dumps(drive_brief(goal_list["items"], goals.load_brief(topic_id, self.private_root))),
            encoding="utf-8",
        )
        argv = [
            str(project), "--arm", arm, "--opening-file", str(opening), "--brief-file", str(brief),
            "--human-folder", str(folder / "human"), "--private-root", str(self.private_root),
        ]

        marks = self.record_marks()
        printed = io.StringIO()
        started = self.clock()
        with contextlib.redirect_stdout(printed):
            code = self.drive(argv)
        seconds = self.clock() - started
        summary = _last_json_line(printed.getvalue())

        if code == drive_module.EXIT_USAGE_LIMIT:
            resets_at = summary.get("resets_at")
            self.log(event="usage-limit", resets_at=resets_at)
            raise _Halt("usage-limit", resets_at)
        if code == drive_module.EXIT_REFUSED:
            self.log(event="build-refused", topic=topic_id, arm=arm, run=run)
            raise _Halt("refused")
        rows = self.new_rows(marks, arm)
        event = {
            "event": "build-closed", "topic": topic_id, "arm": arm, "run": run,
            "exit": 0 if code == 0 else 1, "seconds": seconds, "turns": summary.get("turns"),
            "weighted": sum(row.get("weighted", 0) for row in rows),
            "raw": sum(_raw_total(row) for row in rows),
            "project": str(project),
        }
        self.log(**event)
        return event

    def judge_build(self, event):
        verdict = self.attempt(
            lambda: self.judge(event["project"], event["topic"], **self.session_options())
        )
        self.log(
            event="judged", topic=event["topic"], arm=event["arm"], run=event["run"],
            counts=verdict.get("counts"),
        )

    # results

    def probe_summary(self):
        pool = {entry["id"]: entry for entry in topics.load_pool(self.private_root)}
        summary = {}
        for event in self.events("picked"):
            if event["stage"] == "probe" and event["topic"] in pool:
                summary.setdefault(event["form"], []).append(pool[event["topic"]])
        return {
            form: {"picks": len(entries), "classes": topics.distinct_classes(entries)}
            for form, entries in summary.items()
        }

    def result(self, status, resets_at=None):
        closed = self.events("build-closed")
        done = status == "complete"
        return PilotResult(
            status=status, resets_at=resets_at, form=self.form(), topics=self.pilot_topics(),
            probe=self.probe_summary(), closed=len(closed), refused=len(self.events("build-refused")),
            aggregates=self.aggregates(closed) if done else None,
        )

    def aggregates(self, closed):
        """Aggregates over the closed builds. Only builds that ended done and
        have a judged verdict enter the shares; failed builds are counted."""
        judged = {self.key(e) for e in self.events("judged")}
        counted = [e for e in closed if e["exit"] == 0 and self.key(e) in judged]
        by_column = {"weighted": {}, "raw": {}}
        for event in counted:
            for column, groups in by_column.items():
                arms = groups.setdefault(event["topic"], {"compass": {}, "baseline": {}})
                arms[event["arm"]][event["run"]] = event[column]
        paired = {}
        for column, groups in by_column.items():
            paired[column] = {}
            for topic_id, arms in groups.items():
                runs = sorted(set(arms["compass"]) & set(arms["baseline"]))
                if runs:
                    paired[column][topic_id] = {
                        arm: [arms[arm][run] for run in runs] for arm in ARMS
                    }
        out = {"weighted_share": None, "raw_share": None, "topic_shares": {}, "within_sd": None,
               "df": None, "between_sd": None, "interval": None, "batch": None}
        for column in ("weighted", "raw"):
            with contextlib.suppress(ValueError):
                out[f"{column}_share"] = stats.overall_share(paired[column])
            with contextlib.suppress(ValueError):
                out["topic_shares"][column] = stats.topic_shares(paired[column])
        weighted = paired["weighted"]
        with contextlib.suppress(ValueError):
            out["within_sd"], out["df"] = stats.pooled_within_sd(weighted)
        with contextlib.suppress(ValueError):
            out["between_sd"] = stats.between_topic_sd(weighted)
        out["skipped_resamples"] = 0
        with contextlib.suppress(ValueError):
            low, high, out["skipped_resamples"] = stats.bootstrap_summary(weighted, seed=BOOTSTRAP_SEED)
            out["interval"] = None if low is None else (low, high)
        out["failed_builds"] = sum(1 for e in closed if e["exit"] != 0)
        out["unjudged_builds"] = sum(1 for e in closed if e["exit"] == 0 and self.key(e) not in judged)
        if out["within_sd"] is not None and out["weighted_share"] is not None:
            with contextlib.suppress(ValueError):
                out["batch"] = stats.batch_plan(out["weighted_share"], out["within_sd"], out["df"])
        seconds = [event["seconds"] for event in closed]
        out["mean_seconds"] = _mean(seconds)
        out["mean_turns"] = _mean([event.get("turns") for event in closed])
        out["builds_per_window"] = None
        with contextlib.suppress(ValueError):
            out["builds_per_window"] = stats.builds_per_window(seconds)
        out["mean_weighted_by_arm"] = {
            arm: _mean([e["weighted"] for e in closed if e["arm"] == arm]) for arm in ARMS
        }
        out["mean_raw_by_arm"] = {
            arm: _mean([e["raw"] for e in closed if e["arm"] == arm]) for arm in ARMS
        }
        out["judged"] = self.judged_counts()
        return out

    def judged_counts(self):
        totals = {arm: {} for arm in ARMS}
        for event in self.events("judged"):
            for name, count in (event.get("counts") or {}).items():
                totals[event["arm"]][name] = totals[event["arm"]].get(name, 0) + count
        return totals


def run_pilot(
    *, repo_root, private_root, projects_root, report_path=None, claude_cmd=None, parent_env=None,
    probe_size=10, topic_count=3, runs_per_arm=2, pick=topics.pick_topic, freeze=goals.write_goals,
    judge=judge_module.judge_project, drive=drive_module.main, new_project=sandbox.new_project,
    clock=time.monotonic,
):
    """Run the pilot, or resume it from its run log, and return a PilotResult.

    Topic, goal and judge sessions get `claude_cmd` and `parent_env`; builds go
    through `drive`, which runs the real claude command. Raises records.Refused,
    before any session or file write, when `private_root` is inside a git work tree.
    """
    topics.check_private_root(private_root)
    pilot = _Pilot(
        repo_root=repo_root, private_root=private_root, projects_root=projects_root,
        claude_cmd=claude_cmd, parent_env=parent_env, probe_size=probe_size,
        topic_count=topic_count, runs_per_arm=runs_per_arm, pick=pick, freeze=freeze,
        judge=judge, drive=drive, new_project=new_project, clock=clock,
    )
    try:
        try:
            pilot.pick_stage()
            pilot.freeze_stage()
            pilot.build_stage()
        except topics.SessionError as error:
            if error.status != launch.USAGE_LIMIT:
                raise
            pilot.log(event="usage-limit", resets_at=None)
            raise _Halt("usage-limit") from error
    except _Halt as halt:
        return pilot.result(halt.status, halt.resets_at)
    result = pilot.result("complete")
    if report_path is not None:
        write_report(report_path, result, pilot)
    return result


# report

def _missing(reason):
    return f"not computable ({reason})"


def _percent(value, reason="no finished pair of builds"):
    return _missing(reason) if value is None else f"{value * 100:.1f}%"


def _number(value, digits=1, reason="no finished build"):
    return _missing(reason) if value is None else f"{value:.{digits}f}"


def _git_line(repo_root, *args):
    try:
        done = subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 and done.stdout.strip() else None


def render_report(result, repo_root):
    agg = result.aggregates or {}
    batch = agg.get("batch")
    letters = {topic_id: chr(ord("A") + n) for n, topic_id in enumerate(result.topics)}
    today = datetime.date.today().isoformat()
    branch = _git_line(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    commit = _git_line(repo_root, "rev-parse", "--short", "HEAD")
    head = [
        "---", 'title: "Whole overhead pilot"', "type: research", "status: draft",
        "confidence: low", "area: workflow",
        "summary: \"Overhead share of Compass over twelve builds on three topics, its spread, the batch size it implies, and the cost of one build\"",
        "tags: [overhead, pilot, measurement]", f"created: {today}", f"updated: {today}",
    ]
    if branch:
        head.append(f'git_branch: "{branch}"')
    if commit:
        head.append(f'git_commit: "{commit}"')
    head += ['author: "pilot.py"', "---", ""]

    lines = head + [
        "# Whole overhead pilot",
        "",
        "```mermaid",
        "flowchart LR",
        f"  P[\"probe: {sum(p['picks'] for p in result.probe.values())} picks\"] --> T[\"{len(result.topics)} frozen topics\"]",
        f"  T --> B[\"{result.closed} judged builds\"] --> S[\"share and batch size\"]",
        "```",
        "",
        "> [!IMPORTANT]",
        "> You decide: whether the batch size and the cost of one build below are a pace your subscription can carry.",
        "",
        "## Question",
        "",
        "How much of a build's weighted tokens does Compass add, how much does that share vary between and within topics, and how many builds per arm does a 10% relative drop in it take to see at 95% confidence and 80% power? Related: [[SPEC-032-whole-overhead-measured-on-real-projects]].",
        "",
        "## Findings",
        "",
        "### The pilot",
        "",
        f"- Topic form chosen: {result.form}.",
    ]
    for form in ("seeded", "unseeded"):
        info = result.probe.get(form)
        if info:
            lines.append(f"- Probe, {form}: {info['picks']} picks in {info['classes']} distinct kind and language classes.")
    lines += [
        f"- Builds closed: {result.closed}; refused: {result.refused}.",
        f"- Failed builds, left out of the shares: {agg.get('failed_builds', 0)}; "
        f"finished builds without a judged verdict, also left out: {agg.get('unjudged_builds', 0)}.",
        "",
        "### Overhead share",
        "",
        "Share = (Compass-arm tokens minus without-Compass tokens, summed over builds) over Compass-arm tokens summed.",
        "",
        "| Topic | Weighted share | Raw share |",
        "|---|---|---|",
    ]
    shares = agg.get("topic_shares", {})
    for topic_id, letter in letters.items():
        weighted = shares.get("weighted", {}).get(topic_id)
        raw = shares.get("raw", {}).get(topic_id)
        lines.append(f"| {letter} | {_percent(weighted)} | {_percent(raw)} |")
    lines.append(f"| All | {_percent(agg.get('weighted_share'))} | {_percent(agg.get('raw_share'))} |")
    interval = agg.get("interval")
    lines += [
        "",
        "- Bootstrap interval of the weighted share over topics (95%): "
        + (_missing("needs two topics with finished pairs") if interval is None
           else f"{_percent(interval[0])} to {_percent(interval[1])}")
        + (f"; {agg['skipped_resamples']} resamples skipped for a zero Compass total"
           if agg.get("skipped_resamples") else "")
        + ".",
        "- Spread between topics (standard deviation of topic shares): "
        f"{_number(agg.get('between_sd'), 4, 'needs two topics with finished pairs')}.",
        "- Spread within a topic, between its runs (pooled standard deviation of pair shares"
        + (f", {agg['df']} degrees of freedom" if agg.get("df") else "")
        + f"): {_number(agg.get('within_sd'), 4, 'needs a topic with two finished runs per arm')}.",
        "",
        "### Batch size",
        "",
    ]
    if agg.get("within_sd") == 0:
        lines += [
            "The within-topic spread was zero in the pilot, so the batch size below is the floor of "
            f"{stats.MIN_BATCH} builds per arm and says nothing about the spread of a larger sample.",
            "",
        ]
    if batch:
        lines += [
            "Builds per arm to see a 10% relative drop in the weighted share at 95% confidence and 80% power:",
            "",
            f"- From the point estimate of the within-topic spread: {batch['point']}.",
            f"- From its upper 80% chi-square bound: {batch['upper']}.",
        ]
        per_window = agg.get("builds_per_window")
        if per_window:
            for name in ("point", "upper"):
                windows = -(-2 * batch[name] // per_window)
                lines.append(f"- Windows of {WINDOW_HOURS:g} hours for the {name} batch (both arms): {windows}.")
    else:
        lines.append(
            _missing("it needs a nonzero share and a spread within topics from repeated finished runs")
            + "."
        )
    lines += [
        "",
        "### Cost and time of one build",
        "",
        f"- Mean wall time: {_number(agg.get('mean_seconds'), 0)} seconds; mean turns: {_number(agg.get('mean_turns'), 1)}.",
        f"- Builds that fit one {WINDOW_HOURS:g}-hour window: "
        f"{_number(agg.get('builds_per_window'), 0, 'no build with a positive duration')}.",
    ]
    for arm in ARMS:
        lines.append(
            f"- Mean weighted tokens, {arm} arm: {_number(agg.get('mean_weighted_by_arm', {}).get(arm), 0)};"
            f" mean raw tokens: {_number(agg.get('mean_raw_by_arm', {}).get(arm), 0)}."
        )
    lines += ["", "### Judge", ""]
    for arm in ARMS:
        counts = agg.get("judged", {}).get(arm, {})
        text = ", ".join(f"{name} {count}" for name, count in sorted(counts.items())) or "none judged"
        lines.append(f"- Goal items, {arm} arm: {text}.")
    lines += [
        "",
        "### Headless checks",
        "",
        "Read from the session transcripts after the run; the pilot's run log does not hold them.",
        "",
        "- TODO: Compass's hooks under the flags.",
        "- TODO: a review gate falling back to a picker with no window opened.",
        "- TODO: whether `--plugin-dir` and setup together load Compass twice (the `system/init` counts).",
        "- TODO: which built-in plugins loaded.",
        "- TODO: `.claude/` unchanged by self-update.",
        "- TODO: capture workers counted.",
        "- TODO: how many frozen goal items the Compass arm's own spec dropped.",
        "",
    ]
    return "\n".join(lines)


def write_report(report_path, result, pilot):
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(result, pilot.repo_root), encoding="utf-8", newline="\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the overhead pilot, or resume it.")
    parser.add_argument("--private-root", default=None)
    parser.add_argument("--projects-root", default=None)
    parser.add_argument("--report", default=None)
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    private_root = Path(args.private_root) if args.private_root else topics.private_dir()
    try:
        result = run_pilot(
            repo_root=repo_root, private_root=private_root,
            projects_root=args.projects_root or sandbox.DEFAULT_PROJECTS_ROOT, report_path=args.report,
        )
    except (records.Refused, launch.Refused, sandbox.Refused) as error:
        sys.stderr.write(f"refused: {error}\n")
        return 2
    print(json.dumps({
        "status": result.status, "closed": result.closed, "refused": result.refused,
        "resets_at": result.resets_at,
    }))
    return {"complete": 0, "usage-limit": 3}.get(result.status, 1)


if __name__ == "__main__":
    sys.exit(main())
