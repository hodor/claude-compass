"""Hand grading of four pilot builds, and the judge's agreement with it.

`prepare` picks four finished, judged builds from the pilot's run log (two per
arm), copies each the way the judge's copy is made (no `.git`, `.compass`,
`.claude`, `CLAUDE.md`, no Compass lines in `.gitignore`, no links) under the
neutral names `grade-1` to `grade-4` in `<private root>/grading/`, and writes
one sheet per copy, `grade-N.md`, listing the topic's frozen goal items with a
blank mark per item and a blank keep line. Dependency and cache folders are
left out of a copy, and the text of every file is scrubbed of Compass's document
ids (`SPEC-`, `TASK-`, `PLAN-`, `ADR-`), folder and file names and arm labels.
The map from a neutral name to its build is kept in
`<private root>/grading-key.json`, outside the grading folder.

`score` reads the filled sheets, compares each mark with the judge's score for
the same goal item, and writes the section "### Agreement with your grading"
into the pilot report: counts only, topics by letter, no goal text and no
path. It prints the projects marked keep.

Matching a judged event to its verdict file: the run log's `judged` events
carry the score counts and the verdict files under `<private root>/topics/
verdicts/` carry the per-item scores, so for each topic the events, newest
first, are matched to the newest verdict file with the same counts that is
older than the one matched before.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

import goals
import judge
import pilot
import topics
from topics import Refused

SCORES = judge.SCORES
HEADING = "### Agreement with your grading"
KEY_NAME = "grading-key.json"
PER_ARM = 2
NAME_PATTERN = re.compile(r"grade-[1-4]")

# Folders of installed dependencies, build output and caches, left out of a copy.
SKIP_FOLDERS = frozenset({
    "node_modules", ".venv", "venv", "target", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", ".tox", ".tools", ".hypothesis",
})

# Names and text that show the arm that built a project, or that Compass was used.
_NAME_EXACT = frozenset({".git", ".compass", ".claude", "claude.md"})
_ID_PREFIXES = ("SPEC-", "TASK-")
_ID_PATTERN = re.compile(rb"\b(?:SPEC|TASK|PLAN|ADR)-[0-9A-Za-z][\w-]*(?:/D-\d+)?")
_ID_PREFIX = re.compile(rb"(?:SPEC|TASK)-")
_COMPASS_FOLDER = re.compile(rb"\.compass", re.IGNORECASE)
_CLAUDE_FOLDER = re.compile(rb"\.claude", re.IGNORECASE)
_CLAUDE_FILE = re.compile(rb"claude\.md", re.IGNORECASE)
_ARM_LABEL = re.compile(
    rb"\b(?:compass|baseline)[ -]arm\b|\barm[ :=-]+(?:compass|baseline)\b", re.IGNORECASE,
)

_MARK_LINE = re.compile(r"^mark\s+(\S+?)\s*:\s*(.*?)\s*$", re.IGNORECASE)
_KEEP_LINE = re.compile(r"^keep\s*:\s*(.*?)\s*$", re.IGNORECASE)

_RANK = {"not met": 0, "partly met": 1, "met": 2}


class GradeError(Exception):
    """A grading step cannot proceed: the data is missing, mismatched or refused."""


class SheetError(GradeError):
    """A grading sheet is not filled in correctly."""


class Leaky(GradeError):
    """A grading copy would show its arm or Compass."""

    def __init__(self, paths):
        super().__init__(f"{len(paths)} file(s) would show the arm or Compass")
        self.paths = paths


def _grading_dir(private_root):
    return topics.private_dir(private_root) / "grading"


def _key_path(private_root):
    return topics.private_dir(private_root) / KEY_NAME


def _verdicts_dir(private_root):
    return topics.topics_dir(private_root) / "verdicts"


# the run log


def _events(log_path):
    path = Path(log_path)
    if not path.is_file():
        raise GradeError("there is no pilot run log")
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            found.append(event)
    return found


def _slot(event):
    return (event.get("topic"), event.get("arm"), event.get("run"))


def topic_letters(events):
    """{topic id: "A", "B", ...} in the order the pilot's topics were picked."""
    ids = [e["topic"] for e in events if e.get("event") == "picked" and e.get("stage") == "pilot"]
    return {topic_id: chr(ord("A") + number) for number, topic_id in enumerate(ids)}


def _verdict_files(private_root, topic_id):
    folder = _verdicts_dir(private_root)
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob(f"{topic_id}-*.json")):
        try:
            data = topics.read_json(path)
        except (ValueError, OSError):
            continue
        if isinstance(data, dict) and isinstance(data.get("scores"), dict):
            found.append((path, data))
    return found


def match_verdicts(events, private_root):
    """{slot: (verdict file, verdict)} for the judged builds of the run log.

    A slot without a verdict file whose counts equal its judged event's counts
    is absent from the result.
    """
    matched = {}
    by_topic = {}
    for event in events:
        if event.get("event") == "judged":
            by_topic.setdefault(event.get("topic"), []).append(event)
    for topic_id, judged in by_topic.items():
        files = _verdict_files(private_root, topic_id)
        position = len(files)
        for event in reversed(judged):
            index = position - 1
            while index >= 0 and files[index][1].get("counts") != event.get("counts"):
                index -= 1
            if index < 0:
                break
            position = index
            matched.setdefault(_slot(event), files[index])
    return matched


def collect_builds(events, private_root):
    """The finished builds of the run log that were judged and whose verdict
    file is found, in log order, one per (topic, arm, run) slot."""
    verdicts = match_verdicts(events, private_root)
    letters = topic_letters(events)
    closed = {}
    for event in events:
        if event.get("event") == "build-closed":
            closed[_slot(event)] = event
    builds = []
    for slot, event in closed.items():
        if slot not in verdicts or slot[0] not in letters:
            continue
        path, verdict = verdicts[slot]
        capped = event.get("exit") != 0 and event.get("end") in pilot.CAPPED_ENDS
        builds.append({
            "topic": slot[0], "arm": slot[1], "run": slot[2], "project": event.get("project"),
            "human_done": event.get("exit") == 0 and event.get("end") == "human-done",
            "capped": capped, "verdict_file": path.name, "verdict": verdict,
        })
    return builds


# choosing


def _distinct_topics_first(builds):
    seen, first, rest = set(), [], []
    for build in builds:
        (rest if build["topic"] in seen else first).append(build)
        seen.add(build["topic"])
    return first + rest


def select_builds(builds, usable):
    """Four builds, two per arm, in a deterministic order.

    Builds that ended human-done come first, from topics the arm has not taken
    yet where possible; the Compass arm takes one capped build before them when
    there is one. `usable(build)` is false for a build that cannot be graded.
    """
    order = {}
    for n, build in enumerate(builds):
        order.setdefault(build["topic"], n)
    ranked = sorted(builds, key=lambda b: (order[b["topic"]], b["run"] if isinstance(b["run"], int) else 0))
    chosen = []
    for arm in ("compass", "baseline"):
        mine = [b for b in ranked if b["arm"] == arm]
        done = _distinct_topics_first([b for b in mine if b["human_done"]])
        capped = [b for b in mine if b["capped"]]
        other = [b for b in mine if not b["human_done"] and not b["capped"]]
        taken = []
        pools = [capped[:], done, capped, other] if arm == "compass" else [done, capped, other]
        for index, pool in enumerate(pools):
            held = {taken_build["topic"] for taken_build in taken}
            for build in sorted(pool, key=lambda b: b["topic"] in held):
                if len(taken) == PER_ARM:
                    break
                if build in taken or not usable(build):
                    continue
                taken.append(build)
                if arm == "compass" and index == 0:
                    break
        chosen += taken
    return chosen


def neutral_order(builds):
    """`builds` ordered by a hash of their slot, so the number a copy gets does not follow the arm."""
    def digest(build):
        text = f"{build['topic']}|{build['arm']}|{build['run']}"
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    return sorted(builds, key=digest)


# the copy


def _is_binary(data):
    return b"\0" in data[:8192]


def _walk(project):
    """(relative path, absolute path) of every file a grading copy would hold."""
    project = Path(project)
    for folder, dirs, files in os.walk(project):
        dirs[:] = sorted(
            name for name in dirs
            if name not in judge._OMITTED and name not in SKIP_FOLDERS
            and not judge._is_link(Path(folder) / name)
        )
        for name in sorted(files):
            absolute = Path(folder) / name
            if name in judge._OMITTED or judge._is_link(absolute):
                continue
            yield absolute.relative_to(project), absolute


def _name_leak(relative):
    """True when a path component is a reserved name or holds `SPEC-` or `TASK-`."""
    return any(
        part.lower() in _NAME_EXACT or any(marker in part for marker in _ID_PREFIXES)
        for part in relative.parts
    )


def scrub(data):
    """`data` (bytes of a text file) with Compass's document ids, folder and
    file names and arm labels replaced by neutral words."""
    data = _ID_PATTERN.sub(b"REF", data)
    data = _ID_PREFIX.sub(b"REF-", data)
    data = _COMPASS_FOLDER.sub(b".notes", data)
    data = _CLAUDE_FOLDER.sub(b".agent", data)
    data = _CLAUDE_FILE.sub(b"NOTES.md", data)
    return _ARM_LABEL.sub(b"arm", data)


def _text_leak(data):
    return bool(
        _COMPASS_FOLDER.search(data) or _CLAUDE_FOLDER.search(data) or _CLAUDE_FILE.search(data)
        or _ID_PREFIX.search(data) or _ARM_LABEL.search(data)
    )


def find_leaks(project):
    """Relative paths in `project` whose names would show Compass in a grading
    copy: a reserved name or `SPEC-` or `TASK-` in a name. Text is scrubbed, not refused."""
    return [relative.as_posix() for relative, _ in _walk(project) if _name_leak(relative)]


def copy_leaks(copy):
    """Relative paths in a finished grading copy that show Compass or the arm,
    by name or in a text file."""
    found = []
    for relative, absolute in _walk(copy):
        if _name_leak(relative):
            found.append(relative.as_posix())
            continue
        data = absolute.read_bytes()
        if not _is_binary(data) and _text_leak(data):
            found.append(relative.as_posix())
    return found


def make_grading_copy(project, dest):
    """Copy `project` to `dest` the way the judge's copy is made, without
    dependency and cache folders and with the text of every file scrubbed of
    Compass's ids, names and arm labels; return `dest`.

    Raises Refused as `judge.make_copy` does, and Leaky, before anything is
    written, when a file name would show Compass, or after the copy when a file
    still shows it.
    """
    project, dest = Path(project), Path(dest)
    if not project.is_dir():
        raise Refused("the project is not a folder")
    if judge._inside(dest, project):
        raise Refused("the copy cannot sit inside the project")
    if dest.exists() and any(dest.iterdir()):
        raise Refused("the copy's folder is not empty")
    leaks = find_leaks(project)
    if leaks:
        raise Leaky(leaks)
    dest.mkdir(parents=True, exist_ok=True)
    for relative, absolute in _walk(project):
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if relative.name == ".gitignore":
            judge._clean_gitignore(absolute, target)
        else:
            shutil.copy2(absolute, target, follow_symlinks=False)
        data = target.read_bytes()
        if not _is_binary(data):
            target.write_bytes(scrub(data))
    leaks = copy_leaks(dest)
    if leaks:
        raise Leaky(leaks)
    return dest


def residual_mentions(copy):
    """The number of text files in `copy` that still hold the word compass."""
    count = 0
    for _, absolute in _walk(copy):
        data = absolute.read_bytes()
        if not _is_binary(data) and b"compass" in data.lower():
            count += 1
    return count


# the sheet


def _flat(text):
    return " ".join(str(text).split())


def render_sheet(name, items):
    """The text of a grading sheet for the copy `name`, a folder beside the sheet."""
    lines = [
        f"# Grading sheet {name}",
        "",
        f"Project folder: {name}, beside this sheet.",
        "",
        "Read the files in the project folder, or run the item's command there, and mark each goal "
        f"item: {', '.join(SCORES)}. Write the mark after `mark gN:` and write yes or no after "
        "`keep:` to say whether the project is to be kept.",
    ]
    for item in items:
        lines += ["", f"## {item['id']}", "", f"> {_flat(item['text'])}"]
        if item.get("command"):
            lines += ["", f"command: `{_flat(item['command'])}`"]
        lines += ["", f"mark {item['id']}:"]
    lines += ["", "## Keep", "", "keep:", ""]
    return "\n".join(lines)


def parse_sheet(text, goal_ids):
    """({goal id: mark}, keep) from a filled sheet.

    Raises SheetError for a goal item without a mark, a mark outside `SCORES`,
    a mark for an unknown or repeated item, or a keep line that is not yes or no.
    """
    marks, keeps = {}, []
    for line in text.splitlines():
        found = _MARK_LINE.match(line)
        if found:
            goal_id, mark = found.group(1), " ".join(found.group(2).lower().split())
            if goal_id not in goal_ids:
                raise SheetError(f"the sheet marks {goal_id}, which is not a goal item")
            if goal_id in marks:
                raise SheetError(f"the sheet marks {goal_id} twice")
            if mark not in SCORES:
                raise SheetError(f"the mark of {goal_id} is not one of {', '.join(SCORES)}")
            marks[goal_id] = mark
            continue
        found = _KEEP_LINE.match(line)
        if found:
            keeps.append(found.group(1).lower())
    missing = [goal_id for goal_id in goal_ids if goal_id not in marks]
    if missing:
        raise SheetError(f"the sheet does not mark {', '.join(missing)}")
    if len(keeps) != 1 or keeps[0] not in ("yes", "no"):
        raise SheetError("the sheet needs one keep line holding yes or no")
    return marks, keeps[0] == "yes"


# prepare


def prepare(*, private_root=None, log_path=None):
    """Copy four builds and write their sheets; return the chosen entries.

    Raises GradeError when the grading folder already holds a copy or sheet, or
    when fewer than two usable builds exist for an arm.
    """
    topics.check_private_root(private_root)
    root = topics.private_dir(private_root)
    grading = _grading_dir(private_root)
    held = grading.is_dir() and any(NAME_PATTERN.match(path.name) for path in grading.iterdir())
    if held or _key_path(private_root).exists():
        raise GradeError("the grading folder or its key already exists; move them aside first")
    events = _events(log_path or pilot.run_log_path(root))
    builds = collect_builds(events, private_root)
    letters = topic_letters(events)

    leaky = {}

    def usable(build):
        project = build["project"]
        if not isinstance(project, str) or not Path(project).is_dir():
            return False
        if project not in leaky:
            leaky[project] = bool(find_leaks(project))
        return not leaky[project]

    chosen = select_builds(builds, usable)
    for arm in ("compass", "baseline"):
        if sum(1 for build in chosen if build["arm"] == arm) < PER_ARM:
            raise GradeError(f"fewer than {PER_ARM} usable {arm} builds in the run log")

    entries = []
    for number, build in enumerate(neutral_order(chosen), start=1):
        name = f"grade-{number}"
        goal_list = goals.require_goals(build["topic"], private_root)
        make_grading_copy(build["project"], grading / name)
        (grading / f"{name}.md").write_text(
            render_sheet(name, goal_list["items"]), encoding="utf-8", newline="\n",
        )
        entries.append({
            "name": name, "topic": build["topic"], "arm": build["arm"], "run": build["run"],
            "letter": letters[build["topic"]], "capped": build["capped"],
            "verdict_file": build["verdict_file"], "project": build["project"],
        })
    topics.write_json(_key_path(private_root), {"builds": entries}, exclusive=True)
    return entries


# score


def _load_key(private_root):
    path = _key_path(private_root)
    if not path.is_file():
        raise GradeError("there is no grading key; run prepare first")
    try:
        data = topics.read_json(path)
    except (ValueError, OSError) as error:
        raise GradeError("the grading key cannot be read") from error
    entries = data.get("builds") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise GradeError("the grading key holds no builds")
    return entries


def _grade_one(entry, private_root):
    """The comparison of one graded build: its pairs and keep mark."""
    sheet = _grading_dir(private_root) / f"{entry['name']}.md"
    if not sheet.is_file():
        raise SheetError(f"{entry['name']} has no sheet")
    goal_ids = [item["id"] for item in goals.require_goals(entry["topic"], private_root)["items"]]
    marks, keep = parse_sheet(sheet.read_text(encoding="utf-8"), goal_ids)
    verdict_path = _verdicts_dir(private_root) / entry["verdict_file"]
    try:
        scores = topics.read_json(verdict_path)["scores"]
    except (ValueError, OSError, KeyError, TypeError) as error:
        raise GradeError(f"the verdict of {entry['name']} cannot be read") from error
    pairs = {}
    for goal_id in goal_ids:
        entry_score = scores.get(goal_id)
        score = entry_score.get("score") if isinstance(entry_score, dict) else None
        if score not in SCORES:
            raise GradeError(f"the verdict of {entry['name']} has no score for {goal_id}")
        pairs[goal_id] = (marks[goal_id], score)
    return {"entry": entry, "pairs": pairs, "keep": keep}


def agreement(graded):
    """Counts of agreement between the human's marks and the judge's scores.

    `graded` is a list of `{"entry", "pairs", "keep"}`; `pairs` maps a goal item
    to its (human mark, judge score). Returns the totals, the counts by arm and
    by topic letter and goal item, the human-by-judge table, and the builds kept.
    """
    total = {"items": 0, "agree": 0, "judge_more_lenient": 0, "judge_stricter": 0}
    by_arm, by_item = {}, {}
    table = {human: dict.fromkeys(SCORES, 0) for human in SCORES}
    kept = 0
    for build in graded:
        arm = build["entry"]["arm"]
        arm_counts = by_arm.setdefault(arm, {"builds": 0, "items": 0, "agree": 0})
        arm_counts["builds"] += 1
        kept += bool(build["keep"])
        for goal_id, (human, judged) in build["pairs"].items():
            total["items"] += 1
            arm_counts["items"] += 1
            item = by_item.setdefault((build["entry"]["letter"], goal_id), {"graded": 0, "agree": 0})
            item["graded"] += 1
            table[human][judged] += 1
            if human == judged:
                total["agree"] += 1
                arm_counts["agree"] += 1
                item["agree"] += 1
            elif _RANK[judged] > _RANK[human]:
                total["judge_more_lenient"] += 1
            else:
                total["judge_stricter"] += 1
    return {
        "total": total, "by_arm": by_arm, "by_item": by_item, "table": table,
        "builds": len(graded), "kept": kept,
    }


def _share(part, whole):
    return f"{part / whole:.1%}" if whole else "n/a"


def _item_key(key):
    letter, goal_id = key
    digits = re.sub(r"\D", "", goal_id)
    return (letter, int(digits) if digits else 0, goal_id)


def render_section(result):
    """The report section, from counts only."""
    total = result["total"]
    lines = [
        HEADING,
        "",
        f"{result['builds']} builds, two per arm, were graded by hand against the frozen goal items, "
        "without knowing the arm, and each of your marks was compared with the judge's score for the same item.",
        "",
        f"- Goal items graded: {total['items']}; judge and human gave the same mark on {total['agree']} "
        f"({_share(total['agree'], total['items'])}).",
        f"- Where they differ, the judge was more lenient on {total['judge_more_lenient']} and stricter on "
        f"{total['judge_stricter']}.",
        f"- Builds marked to keep: {result['kept']} of {result['builds']}.",
        "",
        "| Arm | Builds | Items | Agree | Agreement |",
        "|---|---|---|---|---|",
    ]
    for arm in sorted(result["by_arm"]):
        counts = result["by_arm"][arm]
        lines.append(
            f"| {arm} | {counts['builds']} | {counts['items']} | {counts['agree']} "
            f"| {_share(counts['agree'], counts['items'])} |"
        )
    lines += ["", "| Human \\ Judge | " + " | ".join(SCORES) + " |", "|---|" + "---|" * len(SCORES)]
    for human in SCORES:
        lines.append(f"| {human} | " + " | ".join(str(result["table"][human][score]) for score in SCORES) + " |")
    lines += ["", "| Topic | Goal item | Builds graded | Judge agrees |", "|---|---|---|---|"]
    for key in sorted(result["by_item"], key=_item_key):
        counts = result["by_item"][key]
        lines.append(f"| {key[0]} | {key[1]} | {counts['graded']} | {counts['agree']} |")
    return "\n".join(lines) + "\n"


def replace_section(report_text, section):
    """`report_text` with the agreement section replaced by `section`, or added
    before the headless checks (or at the end) when the report has none."""
    lines = report_text.splitlines(keepends=True)
    start = next((n for n, line in enumerate(lines) if line.rstrip() == HEADING), None)
    if start is not None:
        end = next(
            (n for n in range(start + 1, len(lines)) if re.match(r"#{1,3} ", lines[n])), len(lines),
        )
        return "".join(lines[:start]) + section + ("\n" if end < len(lines) else "") + "".join(lines[end:])
    insert = next((n for n, line in enumerate(lines) if line.rstrip() == "### Headless checks"), None)
    if insert is None:
        base = report_text if report_text.endswith("\n") or not report_text else report_text + "\n"
        return base + ("\n" if base else "") + section
    return "".join(lines[:insert]) + section + "\n" + "".join(lines[insert:])


def score(*, private_root=None, report_path):
    """Compare the filled sheets with the judge, write the report section and
    return `(result, kept entries)`. Raises SheetError, naming the sheet, for any
    sheet not filled in correctly, before the report is touched."""
    topics.check_private_root(private_root)
    entries = _load_key(private_root)
    graded, problems = [], []
    for entry in entries:
        try:
            graded.append(_grade_one(entry, private_root))
        except SheetError as error:
            problems.append(f"{entry['name']}: {error}")
    if problems:
        raise SheetError("; ".join(problems))
    result = agreement(graded)
    report = Path(report_path)
    if not report.is_file():
        raise GradeError("the pilot report does not exist")
    text = report.read_text(encoding="utf-8")
    report.write_text(replace_section(text, render_section(result)), encoding="utf-8", newline="\n")
    return result, [build["entry"] for build in graded if build["keep"]]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="grade", description="Grade four pilot builds by hand.")
    parser.add_argument("--private-root", default=None)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare", help="copy four builds and write their grading sheets")
    scoring = commands.add_parser("score", help="compare the filled sheets with the judge")
    default_report = (
        Path(__file__).resolve().parents[2] / ".compass" / "research" / "whole-overhead"
        / "RESEARCH-whole-overhead-pilot.md"
    )
    scoring.add_argument("--report", default=str(default_report))
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            entries = prepare(private_root=args.private_root)
            grading = _grading_dir(args.private_root)
            for entry in entries:
                kind = "capped" if entry["capped"] else "human-done"
                mentions = residual_mentions(grading / entry["name"])
                print(
                    f"{entry['name']}: {entry['arm']}, topic {entry['letter']}, {kind}, "
                    f"{mentions} text file(s) still hold the word compass"
                )
            print(f"sheets: {grading}")
            return 0
        result, kept = score(private_root=args.private_root, report_path=args.report)
    except (GradeError, Refused, ValueError, goals.GoalsMissing) as error:
        print(str(error), file=sys.stderr)
        return 2
    total = result["total"]
    print(f"agreement {total['agree']} of {total['items']} items; report updated")
    for entry in kept:
        print(f"keep {entry['name']}: {entry['project']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
