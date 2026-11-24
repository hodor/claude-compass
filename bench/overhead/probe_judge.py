"""A judge for the probes' free-text answers, and its agreement with hand grading.

The script grader of `probe.py` scores recall, continuation and decision answers
by exact match: a paraphrased option or an error line cut short scores 0. The
judge is one tool-less session per point that sees each of these questions, its
reference answer (the frozen expected value) and every distinct answer the
point's current replies give to it, labelled by number in an order fixed per
point, with no arm named. It grades each answer `right` (1.0), `partly` (0.5) or
`wrong` (0.0). Everything is stored under the probe's private root:

    <point dir>/judge.json        the judged items, answers included, and one
                                  verdict per arm and probe; an earlier one moves
                                  to superseded/<n>/ as ask files do
    probe-judge-sample/sheet.md   a sample of judged answers for hand grading,
                                  one `mark N:` line each, no arm and no verdict
    probe-judge-sample-key.json   the map from a sheet number to its point,
                                  probe and arms, outside the sheet's folder

`report` prints, per arm and probe type, the judged mean beside the script's
mean over the same answers, the paired intervals against host-summary, and how
often the judge and the script agree; it prints no answer, reference or path.
`agreement` compares the marks on the sheet with the judge's verdicts.
"""

import argparse
import hashlib
import json
import random
import shutil
import sys
from pathlib import Path

import compare
import launch
import probe
import records
import sandbox
import topics
from launch import default_private_root
from topics import SessionError

MODEL = "claude-opus-5-5"
VERDICTS = {"right": 1.0, "partly": 0.5, "wrong": 0.0}
NO_ANSWER = "(no answer)"
SAMPLE_FOLDER = "probe-judge-sample"
SAMPLE_KEY = "probe-judge-sample-key.json"
JUDGED_TYPES = probe.STATE_TYPES
SESSION_TIMEOUT = probe.SESSION_TIMEOUT

INSTRUCTIONS = """\
You grade answers to questions about a coding session. Each question comes with a
reference answer taken from the session's own record, and one or more numbered
answers to grade against it:

- right: the answer gives the same fact as the reference. Wording, case, quoting and
  formatting may differ; an id must be the same id, an option the same choice, an
  error line the same error name with the same message.
- partly: the answer gives part of the reference, such as the error name without its
  message, or the message without the error name.
- wrong: anything else, including a different value, several competing values, a
  guess that does not match, or no answer.

Grade each answer on its own against its question's reference."""


class JudgeError(Exception):
    """The judge's reply cannot be read, or a sample step cannot proceed."""


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _answer_text(value):
    if isinstance(value, str):
        return value.strip() or NO_ANSWER
    if value is None:
        return NO_ANSWER
    return json.dumps(value, ensure_ascii=False)


def _current_replies(folder):
    """{arm: (reply text, reply object or None)} of the arms with a current reply."""
    found = {}
    for arm in probe.ARMS:
        path = folder / f"ask-{arm}.json"
        if not path.is_file():
            continue
        stored = topics.read_json(path)
        if stored.get("no_state") is True:
            continue
        text = stored.get("reply") if isinstance(stored.get("reply"), str) else ""
        try:
            reply = topics.reply_object(text)
        except ValueError:
            reply = None
        found[arm] = (text, reply)
    return found


def items_of(point, *, private_root=None):
    """The judged items of `point`: one per distinct answer to each recall,
    continuation and decision probe, labelled 1..n in prompt order. Within a probe
    the answers are shuffled by a generator seeded with the point, so a label never
    tells which arm gave it."""
    key = probe._load_key(point, private_root)
    replies = _current_replies(probe._point_dir(point, private_root))
    rng = random.Random(_sha(str(point)))
    items = []
    for item in key["probes"]:
        if item.get("type") not in JUDGED_TYPES:
            continue
        groups = {}
        for arm, (_, reply) in replies.items():
            answer = _answer_text(reply.get(item["id"]) if reply is not None else None)
            groups.setdefault(answer, []).append(arm)
        ordered = sorted(groups.items())
        rng.shuffle(ordered)
        for answer, arms in ordered:
            items.append({"probe": item["id"], "type": item["type"], "arms": arms, "answer": answer})
    for number, item in enumerate(items, start=1):
        item["label"] = str(number)
    return [{"label": i["label"], "probe": i["probe"], "type": i["type"], "arms": i["arms"], "answer": i["answer"]}
            for i in items]


def _prompt(key, items):
    lines = [INSTRUCTIONS, ""]
    for probe_item in key["probes"]:
        mine = [item for item in items if item["probe"] == probe_item["id"]]
        if not mine:
            continue
        lines += [f"Question: {probe_item['question']}", f"Reference answer: {probe_item['expected']}", "Answers:"]
        lines += [f"[{item['label']}] {item['answer']}" for item in mine]
        lines.append("")
    labels = ", ".join(f'"{item["label"]}"' for item in items)
    lines.append(f"Reply with one JSON object and nothing else. Its keys are {labels}; each value is "
                 "right, partly or wrong.")
    return "\n".join(lines) + "\n"


def _parse(text, items):
    try:
        reply = topics.reply_object(text)
    except ValueError:
        raise JudgeError("the judge's reply holds no JSON object") from None
    verdicts = {}
    for item in items:
        value = reply.get(item["label"])
        word = value.strip().lower() if isinstance(value, str) else None
        if word not in VERDICTS:
            raise JudgeError(f"the judge's reply has no usable verdict for answer {item['label']}")
        verdicts[item["label"]] = word
    return verdicts


def _supersede(folder):
    current = folder / "judge.json"
    if not current.is_file():
        return
    used = [int(p.parent.name) for p in (folder / "superseded").glob("*/judge.json") if p.parent.name.isdigit()]
    target = folder / "superseded" / str(max(used, default=0) + 1)
    target.mkdir(parents=True, exist_ok=True)
    shutil.move(str(current), str(target / "judge.json"))


def judge(point, *, repo_root, private_root=None, claude_cmd=None, parent_env=None):
    """Judge the free-text answers of `point` in one tool-less session and store
    judge.json; None when the point has no free-text probe. Raises probe.Refused,
    probe.NotBuilt, SessionError and JudgeError (nothing stored)."""
    probe._check_private_root(private_root)
    key = probe._load_key(point, private_root)
    items = items_of(point, private_root=private_root)
    if not items:
        return None
    folder = probe._point_dir(point, private_root)
    replies = _current_replies(folder)
    root = Path(private_root) if private_root is not None else default_private_root()
    project = sandbox.new_project(root / "probe-projects")
    result = launch.run_session(
        project, _prompt(key, items), repo_root=repo_root, private_root=root, claude_cmd=claude_cmd,
        parent_env=parent_env, extra_args=["--tools", "", "--model", MODEL], timeout=SESSION_TIMEOUT,
    )
    if result.status != launch.DONE:
        raise SessionError(result.status)
    verdicts = _parse(probe._reply_text(result.events), items)
    judged = []
    for item in items:
        word = verdicts[item["label"]]
        item["verdict"] = word
        for arm in item["arms"]:
            judged.append({"arm": arm, "probe": item["probe"], "verdict": word, "score": VERDICTS[word]})
    stored = {
        "point": point, "model": MODEL, "items": items, "verdicts": judged,
        "replies": {arm: _sha(text) for arm, (text, _) in replies.items()},
        "tokens": records.count_tokens(result.events),
    }
    _supersede(folder)
    topics.write_json(folder / "judge.json", stored)
    return stored


# report ---------------------------------------------------------------------


def _judged_folders(private_root):
    base = probe._probes_dir(private_root)
    if not base.is_dir():
        return []
    return sorted(p for p in base.glob("*") if (p / "judge.json").is_file() and (p / "key.json").is_file())


def _fresh_verdicts(folder):
    """(verdicts whose arm's reply is the one judged, count of the others)."""
    stored = topics.read_json(folder / "judge.json")
    replies = {arm: _sha(text) for arm, (text, _) in _current_replies(folder).items()}
    judged = stored.get("replies", {})
    fresh, stale = [], 0
    for verdict in stored.get("verdicts", []):
        if replies.get(verdict["arm"]) == judged.get(verdict["arm"]):
            fresh.append(verdict)
        else:
            stale += 1
    return fresh, stale


def _type_means(pairs):
    """{type: mean} over (type, score) pairs, with `state` the mean of the types."""
    grouped = {}
    for kind, score in pairs:
        grouped.setdefault(kind, []).append(score)
    means = {kind: sum(v) / len(v) for kind, v in grouped.items()}
    if means:
        means["state"] = sum(means.values()) / len(means)
    return means


def report(*, private_root=None):
    """The judged means per arm and probe type beside the script's, the paired
    intervals against host-summary, and the judge's agreement with the script."""
    kinds = (*JUDGED_TYPES, "state")
    per_arm, points = {}, []
    agree = total = credits = withdraws = partly = stale = 0
    for folder in _judged_folders(private_root):
        key = topics.read_json(folder / "key.json")
        types = {p["id"]: p["type"] for p in key["probes"]}
        fresh, old = _fresh_verdicts(folder)
        stale += old
        judged_pairs, script_pairs = {}, {}
        for verdict in fresh:
            grade_path = folder / f"grade-{verdict['arm']}.json"
            script = topics.read_json(grade_path).get("scores", {}).get(verdict["probe"]) if grade_path.is_file() else None
            kind = types.get(verdict["probe"])
            judged_pairs.setdefault(verdict["arm"], []).append((kind, verdict["score"]))
            if isinstance(script, (int, float)):
                script_pairs.setdefault(verdict["arm"], []).append((kind, float(script)))
                total += 1
                agree += float(script) == verdict["score"]
                credits += verdict["score"] > 0 and float(script) == 0
                withdraws += verdict["score"] < 1 and float(script) == 1
            partly += verdict["verdict"] == "partly"
        point_scores = {}
        for arm, pairs in judged_pairs.items():
            judged_means, script_means = _type_means(pairs), _type_means(script_pairs.get(arm, []))
            point_scores[arm] = judged_means
            entry = per_arm.setdefault(arm, {})
            for kind, value in judged_means.items():
                entry.setdefault(kind, {"judged": [], "script": []})["judged"].append(value)
                if kind in script_means:
                    entry[kind]["script"].append(script_means[kind])
        points.append(point_scores)
    lines = ["| arm | probe | points | judged mean | script mean |", "|---|---|---|---|---|"]
    for arm in sorted(per_arm):
        for kind in kinds:
            cell = per_arm[arm].get(kind)
            if cell:
                script = f"{probe._mean(cell['script']):.2f}" if cell["script"] else "-"
                lines.append(f"| {arm} | {kind} | {len(cell['judged'])} | {probe._mean(cell['judged']):.2f} | {script} |")
    reference = probe.REFERENCE_ARM
    for arm in sorted(per_arm):
        if arm == reference:
            continue
        rows = []
        for kind in kinds:
            differences = [s[arm][kind] - s[reference][kind] for s in points
                           if kind in s.get(arm, {}) and kind in s.get(reference, {})]
            if not differences:
                continue
            if len(differences) < probe.MIN_PAIRS:
                interval = "too few points"
            else:
                low, high = probe._paired_interval(differences)
                interval = f"[{low:.2f}, {high:.2f}]"
            rows.append(f"| {arm} | {kind} | {len(differences)} | {probe._mean(differences):.2f} | {interval} |")
        if rows:
            lines += ["", f"| arm | probe | pairs | judged mean difference from {reference} | 95% paired interval |",
                      "|---|---|---|---|---|", *rows]
    lines += [
        "",
        f"judge and script agree on {agree} of {total} answers",
        f"judge credits, script scores 0: {credits}",
        f"judge scores below 1, script scores 1: {withdraws}",
        f"partly verdicts: {partly}",
    ]
    if stale:
        lines.append(f"verdicts left out because their reply changed since judging: {stale}")
    return "\n".join(lines) + "\n"


# hand-graded agreement sample -----------------------------------------------


def _sample_paths(private_root):
    root = Path(private_root) if private_root is not None else default_private_root()
    return root / SAMPLE_FOLDER / "sheet.md", root / SAMPLE_KEY


def sample(*, private_root=None, size=40, replace=False):
    """Write a hand-grading sheet of up to `size` judged answers, drawn round robin
    over the probe types from a generator seeded with compare.SEED. Raises
    JudgeError when a sheet exists and `replace` is false."""
    probe._check_private_root(private_root)
    sheet, key_path = _sample_paths(private_root)
    if sheet.exists() and not replace:
        raise JudgeError("a grading sheet already exists; pass --replace to write a new one")
    pools = {}
    for folder in _judged_folders(private_root):
        key = topics.read_json(folder / "key.json")
        probes = {p["id"]: p for p in key["probes"]}
        for item in topics.read_json(folder / "judge.json").get("items", []):
            if item["probe"] in probes:
                pools.setdefault(item["type"], []).append((folder.name, item, probes[item["probe"]]))
    rng = random.Random(compare.SEED)
    for kind in sorted(pools):
        rng.shuffle(pools[kind])
    chosen = []
    while len(chosen) < size and any(pools.values()):
        for kind in sorted(pools):
            if pools[kind] and len(chosen) < size:
                chosen.append(pools[kind].pop())
    rng.shuffle(chosen)
    lines = [
        "# Grading sheet: free-text probe answers",
        "",
        "For each item, compare the answer with the reference answer and write one word after",
        "its `mark N:` line: right, partly or wrong. The rules the judge followed:",
        "",
        INSTRUCTIONS,
        "",
    ]
    mapping = []
    for number, (folder_name, item, probe_item) in enumerate(chosen, start=1):
        lines += [
            f"## Item {number}", "",
            f"Question: {probe_item['question']}",
            f"Reference answer: {probe_item['expected']}",
            f"Answer: {item['answer']}", "",
            f"mark {number}:", "",
        ]
        mapping.append({"n": number, "point_dir": folder_name, "probe": item["probe"], "type": item["type"],
                        "arms": item["arms"], "label": item["label"]})
    sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet.write_text("\n".join(lines), encoding="utf-8")
    topics.write_json(key_path, {"items": mapping})
    return sheet


def agreement(*, private_root=None):
    """{"marked", "agree", "agree_right", "unreadable", "items", "pending"}: the sheet's
    readable marks compared with the judge's verdicts; pending while none is marked."""
    sheet, key_path = _sample_paths(private_root)
    if not sheet.is_file() or not key_path.is_file():
        raise JudgeError("no grading sheet; run `sample` first")
    mapping = {entry["n"]: entry for entry in topics.read_json(key_path)["items"]}
    marked = agree = agree_right = unreadable = 0
    base = probe._probes_dir(private_root)
    for line in sheet.read_text(encoding="utf-8").splitlines():
        head, _, mark = line.partition(":")
        parts = head.split()
        if len(parts) != 2 or parts[0] != "mark" or not parts[1].isdigit():
            continue
        entry = mapping.get(int(parts[1]))
        word = mark.strip().lower()
        if entry is None or not word:
            continue
        if word not in VERDICTS:
            unreadable += 1
            continue
        stored = topics.read_json(base / entry["point_dir"] / "judge.json")
        verdict = next((i.get("verdict") for i in stored.get("items", [])
                        if i["probe"] == entry["probe"] and i["label"] == entry["label"]), None)
        if verdict is None:
            unreadable += 1
            continue
        marked += 1
        agree += word == verdict
        agree_right += (word == "right") == (verdict == "right")
    return {"marked": marked, "agree": agree, "agree_right": agree_right, "unreadable": unreadable,
            "items": len(mapping), "pending": marked == 0}


# command line ---------------------------------------------------------------


def _parser():
    parser = argparse.ArgumentParser(prog="probe_judge", description="Judge the probes' free-text answers.")
    parser.add_argument("--private-root", default=None)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("judge", help="judge the free-text answers of a point").add_argument("point")
    commands.add_parser("report", help="print the judged means and the agreement with the script")
    sample_parser = commands.add_parser("sample", help="write a hand-grading sheet of judged answers")
    sample_parser.add_argument("--size", type=int, default=40)
    sample_parser.add_argument("--replace", action="store_true")
    commands.add_parser("agreement", help="compare the sheet's marks with the judge's verdicts")
    return parser


def main(argv, *, claude_cmd=None, repo_root=None, parent_env=None):
    args = _parser().parse_args(argv)
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    try:
        if args.command == "judge":
            stored = judge(args.point, repo_root=root, private_root=args.private_root,
                           claude_cmd=claude_cmd, parent_env=parent_env)
            print("no free-text probe" if stored is None else f"judged {len(stored['items'])} answers")
        elif args.command == "report":
            print(report(private_root=args.private_root), end="")
        elif args.command == "sample":
            sheet = sample(private_root=args.private_root, size=args.size, replace=args.replace)
            print(sheet)
        else:
            result = agreement(private_root=args.private_root)
            if result["pending"]:
                print(f"pending: 0 of {result['items']} items marked")
            else:
                print(f"marked {result['marked']} of {result['items']}: judge agrees on {result['agree']}, "
                      f"on right or not on {result['agree_right']}; unreadable marks {result['unreadable']}")
    except SessionError as error:
        print(f"judge session ended {error.status}", file=sys.stderr)
        return 1
    except (JudgeError, probe.Refused, probe.NotBuilt, ValueError, launch.Refused, sandbox.Refused, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
