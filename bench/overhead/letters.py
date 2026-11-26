"""Letter repeatability: how steady the planner's `complexity:` letter is.

`load_pool` reads the detailed task lines of this vault's plans (lines under a
`## Later` heading are intent, not detail, and are left out) and groups them by
their `complexity:` letter. `sample` draws a stratified set. For each drawn
task, isolated `claude -p` sessions on a strong-tier and a balanced-tier model
see the task line without its `complexity:` field, the rubric table of
`plugin/templates/agents/planner.md` and the plan's Goal paragraph, from an
empty folder outside any git work tree with every tool switched off. Each reply
carries a `letter: X` line and a `words:` line quoting the rubric words relied
on.

`render_report` turns the assigned letters into the body of a research
document: agreement within a model (exact agreement and Fleiss' kappa), between
the two models, and against the original letter, plus the rubric words the
sessions cite where letters differ. It holds aggregates and task ids, never
task text.

    python letters.py run --out FILE [--n 30] [--sessions 3] [--seed 0] [--jobs 1] [--rubric FILE]
    python letters.py --dry-run [--n 30] [--seed 0]

`--rubric FILE` measures a candidate table (the `## Task Sizing` section of
FILE) in place of the shipped planner's; its hash joins the progress file's
configuration, so two rubrics never share progress.

`run` appends each finished session to a progress file under the private root
and resumes from it, so a usage-limit halt (exit code 3) continues where it
stopped. `--dry-run` prints the sampled task ids and the prompt of the first
one and launches nothing. Exit codes: 0 complete, 1 refused or failed, 3 usage
limit.
"""

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import tempfile
from collections import Counter, namedtuple
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT / "plugin" / "cli") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "plugin" / "cli"))

LETTERS = ("S", "M", "L")
PLANS_DIR = REPO_ROOT / ".compass" / "plans"
PLANNER = REPO_ROOT / "plugin" / "templates" / "agents" / "planner.md"

DEFAULT_COUNT = 30
DEFAULT_SESSIONS = 3
DEFAULT_SEED = 0
# Tries a session gets when its reply carries no `letter:` line.
ATTEMPTS = 3
# Seconds a single session may run.
SESSION_TIMEOUT = 600
EXIT_USAGE_LIMIT = 3

Task = namedtuple("Task", "id original line goal")


class Refused(RuntimeError):
    """The measurement will not start: a folder inside a git work tree, or a
    resumed progress file from a different configuration."""


class SessionFailed(RuntimeError):
    """A session ended with a nonzero exit code."""


class UsageLimit(SessionFailed):
    """A session stopped on the subscription's usage limit."""


# A `complexity:` field name, not part of a file name, a path or a word.
_FIELD = r"(?<![\w/.`-])complexity:[ \t]*\w+"
_FIELD_THEN_COMMA = re.compile(_FIELD + r"[ \t]*,[ \t]*")
_COMMA_THEN_FIELD = re.compile(r",[ \t]*" + _FIELD)
_DASH_THEN_FIELD_AT_END = re.compile(r"[ \t]+-[ \t]+" + _FIELD + r"[ \t]*$")
_FIELD_ANYWHERE = re.compile(_FIELD)
_FIELD_LETTER = re.compile(r"(?<![\w/.`-])complexity:[ \t]*([SML])\b")


def strip_letter(task_line):
    """`task_line` without its `complexity:` field, wherever the field sits."""
    out = _FIELD_THEN_COMMA.sub("", task_line)
    out = _COMMA_THEN_FIELD.sub("", out)
    out = _DASH_THEN_FIELD_AT_END.sub("", out)
    return _FIELD_ANYWHERE.sub("", out)


def parse_letter(task_line):
    """The letter in the `complexity:` field of `task_line`: S, M or L, else None."""
    found = _FIELD_LETTER.findall(task_line)
    return found[-1] if found else None


def sample(lines_by_letter, n, seed):
    """`n` items drawn without repeats, spread evenly over the letters.

    Each letter gets `n // letters` items and the remainder goes to letters
    chosen by the seeded draw; a letter whose pool is smaller than its share
    gives everything it has and the shortfall moves to letters with spare
    items. The input lists are not modified.
    """
    rng = random.Random(seed)
    keys = list(lines_by_letter)
    base, extra = divmod(n, len(keys))
    bumped = set(rng.sample(keys, extra))
    quota = {key: base + (key in bumped) for key in keys}
    shortfall = 0
    for key in keys:
        size = len(lines_by_letter[key])
        if quota[key] > size:
            shortfall += quota[key] - size
            quota[key] = size
    while shortfall:
        spare = [key for key in keys if quota[key] < len(lines_by_letter[key])]
        if not spare:
            break
        for key in spare:
            if not shortfall:
                break
            quota[key] += 1
            shortfall -= 1
    drawn = []
    for key in keys:
        drawn.extend(rng.sample(list(lines_by_letter[key]), quota[key]))
    return drawn


def _counts(ratings, categories):
    index = {category: i for i, category in enumerate(categories)}
    rows = []
    for item in ratings:
        row = [0] * len(categories)
        for rating in item:
            if rating not in index:
                raise ValueError("rating %r is not one of %r" % (rating, tuple(categories)))
            row[index[rating]] += 1
        rows.append(row)
    return rows


def fleiss_kappa(ratings, categories):
    """Fleiss' kappa of `ratings`: one list of letters per item, the same
    number of raters per item. NaN when every rating is one category, where
    chance agreement is total and kappa is 0/0."""
    if not ratings:
        raise ValueError("no items to rate")
    raters = len(ratings[0])
    if raters < 2 or any(len(item) != raters for item in ratings):
        raise ValueError("every item needs the same number of raters, at least two")
    rows = _counts(ratings, categories)
    items = len(rows)
    observed = sum((sum(c * c for c in row) - raters) / (raters * (raters - 1)) for row in rows) / items
    shares = [sum(row[j] for row in rows) / (items * raters) for j in range(len(categories))]
    chance = sum(share * share for share in shares)
    if chance == 1:
        return math.nan
    return (observed - chance) / (1 - chance)


def exact_agreement(ratings):
    """Share of items on which every rater gave the same letter."""
    if not ratings:
        raise ValueError("no items to rate")
    return sum(len(set(item)) == 1 for item in ratings) / len(ratings)


def session_command(model, prompt):
    """The argv of one `claude -p` session on `model`: no tool, no saved
    session, no MCP server, no user settings, structured `stream-json` output;
    `prompt` is the last argument, after `--`, so a leading dash cannot be read
    as a flag."""
    return [
        "claude", "-p",
        "--model", model,
        "--tools", "",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--setting-sources", "project,local",
        "--output-format", "stream-json",
        "--verbose",
        "--",
        prompt,
    ]


def _inside_work_tree(folder):
    return any((parent / ".git").exists() for parent in [Path(folder).resolve(), *Path(folder).resolve().parents])


def _fresh_folder():
    """A new empty folder under the temporary directory. Returns a context
    manager yielding the path."""
    return tempfile.TemporaryDirectory(prefix="letters-")


def run_session(model, prompt, *, runner, cwd_factory=None):
    """Run one session through `runner(argv, cwd=folder)` and return its reply.

    The folder is `cwd_factory()` when given, else a new empty temporary
    folder removed afterwards. A folder inside a git work tree is refused.
    """
    argv = session_command(model, prompt)
    if cwd_factory is not None:
        folder = Path(cwd_factory())
        if _inside_work_tree(folder):
            raise Refused("the session folder %s is inside a git work tree" % folder)
        return runner(argv, cwd=folder)
    with _fresh_folder() as name:
        folder = Path(name)
        if _inside_work_tree(folder):
            raise Refused("the session folder %s is inside a git work tree" % folder)
        return runner(argv, cwd=folder)


# Flags `launch.run_session` adds to every session; `default_runner` leaves
# them out of the extra arguments it passes on, with the value of each flag
# that takes one.
_LAUNCH_FLAGS = {"-p": 0, "--print": 0, "--verbose": 0, "--strict-mcp-config": 0,
                 "--output-format": 1, "--setting-sources": 1}


def _split_command(argv):
    """(extra arguments, prompt) of a `session_command` argv: the flags that
    `launch.run_session` does not add itself, and the text after `--`."""
    if "--" not in argv:
        raise ValueError("the session command has no `--` before its prompt")
    cut = argv.index("--")
    head, prompt = list(argv[1:cut]), " ".join(argv[cut + 1:])
    extra, i = [], 0
    while i < len(head):
        token = head[i]
        if token in _LAUNCH_FLAGS:
            i += 1 + _LAUNCH_FLAGS[token]
            continue
        extra.append(token)
        i += 1
    return extra, prompt


def default_runner(argv, cwd, *, private_root=None, parent_env=None):
    """Run `argv` in `cwd` as an isolated Claude Code session through
    `launch.run_session` and return the reply text of its final `result`
    event.

    The launcher sends the prompt on stdin, starts the process with no
    console window on Windows, kills its whole tree at `SESSION_TIMEOUT`, and
    classifies the end from the `stream-json` events, never by searching text
    for limit words: a usage limit raises UsageLimit, any other failure
    SessionFailed.
    """
    import launch

    private_root = Path(private_root) if private_root is not None else launch.default_private_root()
    extra, prompt = _split_command(argv)
    try:
        result = launch.run_session(
            cwd, prompt, repo_root=REPO_ROOT, private_root=private_root,
            claude_cmd=[argv[0]], parent_env=parent_env, extra_args=extra, timeout=SESSION_TIMEOUT,
        )
    except launch.Refused as error:
        raise Refused(str(error)) from error
    if result.status == launch.USAGE_LIMIT:
        resets = result.resets_at
        raise UsageLimit("usage limit reached%s" % (" (resets at %s)" % resets if resets else ""))
    if result.status != launch.DONE:
        raise SessionFailed("claude exited %d: %s" % (result.returncode, (result.stderr or "").strip()[-300:]))
    results = [event for event in result.events if event.get("type") == "result"]
    reply = results[-1].get("result")
    return reply if isinstance(reply, str) else ""


_REPLY_LETTER = re.compile(r"^[ \t>*_`]*letter[ \t*_`]*:[ \t*_`]*([SML])\b", re.IGNORECASE | re.MULTILINE)
_REPLY_WORDS = re.compile(r"^[ \t>*_`]*words[ \t*_`]*:[ \t*_]*(.+)$", re.IGNORECASE | re.MULTILINE)


def parse_reply(text):
    """(letter, words) from a session reply: the last `letter: X` line, and
    the text of the last `words:` line; the letter is None when absent."""
    letters_found = _REPLY_LETTER.findall(text or "")
    words_found = _REPLY_WORDS.findall(text or "")
    return (
        letters_found[-1].upper() if letters_found else None,
        words_found[-1].strip() if words_found else "",
    )


_TASK_LINE = re.compile(r"^- \[[ xX]\] (TASK-\d+):")
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.*?)\s*$")
# A Later section title: the word `Later` then a word boundary, so `Lateral`
# does not match and `Later (intent only)` does.
_LATER_TITLE = re.compile(r"Later\b", re.IGNORECASE)
_FENCE = re.compile(r"^\s*(```|~~~)")


def _frontmatter_summary(text):
    match = re.match(r"---\r?\n(.*?)\r?\n---", text, re.DOTALL)
    if not match:
        return ""
    found = re.search(r"^summary:[ \t]*(.+)$", match.group(1), re.MULTILINE)
    return found.group(1).strip().strip("\"'") if found else ""


def _goal_paragraph(lines):
    """The first paragraph under a `## Goal` heading, or ''."""
    for i, line in enumerate(lines):
        heading = _HEADING.match(line)
        if heading and heading.group(1) == "##" and heading.group(2).lower() == "goal":
            paragraph = []
            for follow in lines[i + 1:]:
                if _HEADING.match(follow):
                    break
                if follow.strip():
                    paragraph.append(follow.strip())
                elif paragraph:
                    break
            return " ".join(paragraph)
    return ""


def plan_tasks(path):
    """The detailed task lines of one plan file as Task tuples: lines outside
    code fences and outside a `## Later` section whose `complexity:` field
    holds S, M or L."""
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    plan_id = re.match(r"(PLAN-\d+)", Path(path).stem)
    plan_id = plan_id.group(1) if plan_id else Path(path).stem
    goal = _goal_paragraph(lines) or _frontmatter_summary(text)
    tasks = []
    in_fence = False
    later_level = None
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = _HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            if later_level is not None and level <= later_level:
                later_level = None
            if later_level is None and _LATER_TITLE.match(heading.group(2)):
                later_level = level
            continue
        if later_level is not None:
            continue
        task = _TASK_LINE.match(line)
        letter = parse_letter(line) if task else None
        if letter:
            tasks.append(Task("%s/%s" % (plan_id, task.group(1)), letter, line.rstrip(), goal))
    return tasks


def load_pool(plans_dir=None):
    """Detailed task lines of every plan under `plans_dir`, grouped by letter."""
    pool = {letter: [] for letter in LETTERS}
    for path in sorted(Path(plans_dir or PLANS_DIR).rglob("*.md")):
        for task in plan_tasks(path):
            pool[task.original].append(task)
    return pool


def rubric_table(planner_text):
    """The rubric rows of the `## Task Sizing` section: the table and the line
    after it, as written in the planner."""
    section = re.search(r"^## Task Sizing\s*\n(.*?)(?=^## |\Z)", planner_text, re.DOTALL | re.MULTILINE)
    if not section:
        raise Refused("the planner has no `## Task Sizing` section")
    body = [line for line in section.group(1).splitlines() if line.strip()]
    if not any(line.startswith("|") for line in body):
        raise Refused("the `## Task Sizing` section holds no table")
    return "\n".join(body)


def rubric_terms(table):
    """Lower-cased phrases of the table's Scope column, one per clause: the
    words a session can cite."""
    terms = []
    for line in table.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] not in LETTERS:
            continue
        for part in re.split(r",| or ", cells[1]):
            part = part.strip().lower()
            if part and part not in terms:
                terms.append(part)
    return terms


def build_prompt(task, table):
    """The prompt of one task: instruction, rubric, Goal paragraph, and the
    task line without its `complexity:` field."""
    line = strip_letter(task.line)
    if parse_letter(line) is not None or re.search(r"complexity:[ \t]*[SML]\b", line):
        raise Refused("the original letter is still in the prompt of %s" % task.id)
    if task.goal and _FIELD_ANYWHERE.search(task.goal):
        raise Refused("the plan goal of %s carries a `complexity:` field" % task.id)
    parts = [
        "You are a planner giving one task its complexity letter, S, M or L, "
        "using only the rubric below. Do not use tools.",
        "Rubric:\n" + table,
    ]
    if task.goal:
        parts.append("The plan's goal:\n" + task.goal)
    parts.append("The task:\n" + line)
    parts.append(
        "Reply with exactly two lines. The first is `letter: X` with X one of S, M or L. "
        "The second is `words: ` followed by the rubric words you relied on, quoted from the rubric."
    )
    return "\n\n".join(parts)


def default_models():
    """The strong-tier and balanced-tier model names of the Claude Code host,
    from the model table."""
    import modelslib

    catalog = modelslib.HOST_CATALOGS["claude-code"]
    return catalog["strong"], catalog["balanced"]


def _share(count, total):
    return "%.2f (%d of %d)" % (count / total, count, total)


def _kappa_text(value):
    return "undefined (every session gave one letter)" if math.isnan(value) else "%.3f" % value


def _cross_pairs(first, second):
    equal = total = 0
    for a, b in zip(first, second):
        for x in a:
            for y in b:
                total += 1
                equal += x == y
    return equal, total


def render_report(results, terms=()):
    """The research document body for `results`, a list of
    {"task", "original", "ratings": {model: [letter, ...]}, "words": {model: [text, ...]}}
    with exactly two models; `words` is optional. `terms` are the rubric
    phrases to count in the `words` lines. Holds ids and aggregates only."""
    if not results:
        raise ValueError("no results to report")
    models = list(results[0]["ratings"])
    if len(models) != 2:
        raise ValueError("a report compares exactly two models")
    first, second = models
    by_model = {m: [r["ratings"][m] for r in results] for m in models}
    originals = [r["original"] for r in results]
    out = ["# Letter repeatability", ""]
    out += [
        "%d tasks, %d sessions per model per task. Models: `%s` and `%s`."
        % (len(results), len(results[0]["ratings"][first]), first, second),
        "",
        "## Agreement within a model",
        "",
        "| Model | Exact agreement | Fleiss' kappa |",
        "|---|---|---|",
    ]
    for m in models:
        agree = exact_agreement(by_model[m])
        unanimous = round(agree * len(results))
        out.append("| %s | %s | %s |" % (m, _share(unanimous, len(results)), _kappa_text(fleiss_kappa(by_model[m], LETTERS))))
    pooled = [a + b for a, b in zip(by_model[first], by_model[second])]
    equal, total = _cross_pairs(by_model[first], by_model[second])
    out += [
        "",
        "## Agreement between the two models",
        "",
        "- Session pairs, one from each model, giving the same letter: %s" % _share(equal, total),
        "- Fleiss' kappa over all sessions of both models: %s" % _kappa_text(fleiss_kappa(pooled, LETTERS)),
        "",
        "## Agreement with the original letter",
        "",
        "| Model | Sessions giving the original letter |",
        "|---|---|",
    ]
    for m in models:
        same = sum(letter == original for original, item in zip(originals, by_model[m]) for letter in item)
        out.append("| %s | %s |" % (m, _share(same, sum(len(item) for item in by_model[m]))))
    out += ["", "## Assigned letters against the original letter", ""]
    for m in models:
        out += [
            "`%s`, sessions by assigned letter:" % m,
            "",
            "| Original | " + " | ".join(LETTERS) + " |",
            "|---|" + "---|" * len(LETTERS),
        ]
        for original in LETTERS:
            seen = Counter(letter for o, item in zip(originals, by_model[m]) for letter in item if o == original)
            out.append("| %s | " % original + " | ".join(str(seen[letter]) for letter in LETTERS) + " |")
        out.append("")
    out += _words_section(results, models, terms)
    out += [
        "## Per task",
        "",
        "Original letter, then the letters each session of `%s`, then of `%s`, gave." % (first, second),
        "",
        "| Task | Original | %s | %s |" % ("Strong sessions", "Balanced sessions"),
        "|---|---|---|---|",
    ]
    for r in results:
        out.append(
            "| %s | %s | %s | %s |"
            % (r["task"], r["original"], " ".join(r["ratings"][first]), " ".join(r["ratings"][second]))
        )
    return "\n".join(out) + "\n"


def _disagrees(result):
    every = [letter for item in result["ratings"].values() for letter in item]
    return len(set(every)) > 1


def _words_section(results, models, terms):
    """Counts of rubric phrases cited by sessions on tasks where the letters
    differ, by the letter the citing session assigned."""
    disagreeing = [r for r in results if _disagrees(r)]
    out = ["## Rubric words cited where sessions disagree", ""]
    out.append(
        "%d of %d tasks drew more than one letter across the sessions of both models."
        % (len(disagreeing), len(results))
    )
    out.append("")
    if not terms or not any(r.get("words") for r in disagreeing):
        out += ["No rubric phrase counts to report.", ""]
        return out
    cited = {term: Counter() for term in terms}
    for r in disagreeing:
        for m in models:
            for letter, text in zip(r["ratings"][m], r.get("words", {}).get(m, [])):
                lowered = (text or "").lower()
                for term in terms:
                    if term in lowered:
                        cited[term][letter] += 1
    out += ["| Rubric phrase | " + " | ".join("Cited with %s" % x for x in LETTERS) + " |", "|---|" + "---|" * len(LETTERS)]
    for term in terms:
        out.append("| %s | " % term + " | ".join(str(cited[term][x]) for x in LETTERS) + " |")
    out.append("")
    return out


def _load_planner_table(path=None):
    """The sizing table of `path` (a markdown file with a `## Task Sizing`
    section), the shipped planner's by default."""
    return rubric_table(Path(path or PLANNER).read_text(encoding="utf-8"))


def _progress_path(private_root):
    return Path(private_root) / "letters-progress.json"


def _load_progress(path, config):
    if not path.is_file():
        return {"config": config, "done": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("config") != config:
        raise Refused("%s belongs to a different configuration; pass --progress with a new path" % path)
    return data


def _save_progress(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_suffix(".tmp")
    scratch.write_text(json.dumps(data, indent=1), encoding="utf-8")
    scratch.replace(path)


def run_batch(tasks, models, sessions, table, *, runner, progress_path, config, report_progress=None, jobs=1):
    """Run `sessions` sessions per model on every task and return the results
    list for `render_report`. Finished sessions are read from and written to
    `progress_path`, so a halted batch resumes.

    Up to `jobs` sessions run at once. When one stops the batch (a usage
    limit, a refusal, a reply without a letter), no further session starts,
    the ones already running finish and are saved, and the first error is
    raised."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    progress = _load_progress(progress_path, config)
    done = progress["done"]
    lock = threading.Lock()
    stop = threading.Event()
    pending = []
    for task in tasks:
        prompt = build_prompt(task, table)
        for model in models:
            for k in range(sessions):
                key = "%s|%s|%d" % (task.id, model, k)
                if key not in done:
                    pending.append((key, task, model, prompt))

    def one(item):
        key, task, model, prompt = item
        if stop.is_set():
            return None
        try:
            letter, words = None, ""
            for _ in range(ATTEMPTS):
                reply = run_session(model, prompt, runner=runner)
                letter, words = parse_reply(reply)
                if letter:
                    break
            if letter is None:
                raise SessionFailed("%s gave no `letter:` line in %d tries for %s" % (model, ATTEMPTS, task.id))
        except BaseException:
            stop.set()
            raise
        with lock:
            done[key] = {"letter": letter, "words": words}
            _save_progress(progress_path, progress)
        if report_progress:
            report_progress(key, letter)
        return None

    errors = []
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        for future in [pool.submit(one, item) for item in pending]:
            try:
                future.result()
            except BaseException as error:
                errors.append(error)
    if errors:
        limits = [error for error in errors if isinstance(error, UsageLimit)]
        raise (limits or errors)[0]

    results = []
    for task in tasks:
        ratings, words = {}, {}
        for model in models:
            rows = [done["%s|%s|%d" % (task.id, model, k)] for k in range(sessions)]
            ratings[model] = [row["letter"] for row in rows]
            words[model] = [row["words"] for row in rows]
        results.append({"task": task.id, "original": task.original, "ratings": ratings, "words": words})
    return results


def _draw(args):
    pool = load_pool(Path(args.plans) if args.plans else None)
    return sample(pool, args.n, args.seed)


def _add_common(parser, inherited=False):
    """The drawing options. On the `run` subparser they keep the value given
    before the command unless repeated after it."""
    default = argparse.SUPPRESS if inherited else None
    parser.add_argument(
        "--n", type=int, default=default if inherited else DEFAULT_COUNT,
        help="tasks to draw (default %d)" % DEFAULT_COUNT,
    )
    parser.add_argument("--seed", type=int, default=default if inherited else DEFAULT_SEED)
    parser.add_argument("--plans", default=default, help="plans folder (default: this repo's .compass/plans)")


def main(argv=None, *, runner=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print the sampled ids and one prompt; launch nothing")
    _add_common(parser)
    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("run", help="run the batch and write the report")
    _add_common(run, inherited=True)
    run.add_argument("--out", required=True, help="where the report is written")
    run.add_argument("--sessions", type=int, default=DEFAULT_SESSIONS, help="sessions per model per task")
    run.add_argument("--jobs", type=int, default=1, help="sessions run at once (default 1)")
    run.add_argument("--strong", help="strong-tier model (default: the model table's)")
    run.add_argument("--balanced", help="balanced-tier model (default: the model table's)")
    run.add_argument("--private-root", help="folder of the sandbox config (default ~/.compass/overhead)")
    run.add_argument("--progress", help="progress file (default <private root>/letters-progress.json)")
    run.add_argument("--rubric", help="markdown file whose `## Task Sizing` table the sessions see (default: the planner's)")
    run.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS, help="same as the top-level --dry-run")
    args = parser.parse_args(argv)
    sessions = getattr(args, "sessions", DEFAULT_SESSIONS)
    if args.n < 1 or sessions < 2:
        print("letters: --n must be at least 1 and --sessions at least 2 (kappa needs two raters)", file=sys.stderr)
        return 1
    if getattr(args, "jobs", 1) < 1:
        print("letters: --jobs must be at least 1", file=sys.stderr)
        return 1
    if args.command is None and not args.dry_run:
        parser.error("give the `run` command or --dry-run")
    dry = args.dry_run

    try:
        tasks = _draw(args)
        table = _load_planner_table(getattr(args, "rubric", None))
        if dry:
            print("sampled %d tasks:" % len(tasks))
            for task in tasks:
                print(task.id)
            print("\nprompt of %s:\n\n%s" % (tasks[0].id, build_prompt(tasks[0], table)))
            return 0

        import launch

        strong, balanced = default_models()
        models = [args.strong or strong, args.balanced or balanced]
        if models[0] == models[1]:
            raise Refused("the strong and balanced models are both %s" % models[0])
        private_root = Path(args.private_root) if args.private_root else launch.default_private_root()
        progress_path = Path(args.progress) if args.progress else _progress_path(private_root)
        if _inside_work_tree(progress_path.parent):
            raise Refused("the progress file would sit inside a git work tree")
        config = {"ids": [t.id for t in tasks], "models": models, "sessions": args.sessions, "seed": args.seed}
        if args.rubric:
            config["rubric"] = hashlib.sha256(table.encode("utf-8")).hexdigest()

        def real_runner(argv, cwd):
            return default_runner(argv, cwd, private_root=private_root)

        results = run_batch(
            tasks, models, args.sessions, table,
            runner=runner or real_runner, progress_path=progress_path, config=config,
            report_progress=lambda key, letter: print("%s -> %s" % (key, letter), file=sys.stderr),
            jobs=args.jobs,
        )
    except UsageLimit as error:
        print("usage limit: %s; run the same command again to resume" % error, file=sys.stderr)
        return EXIT_USAGE_LIMIT
    except (Refused, SessionFailed) as error:
        print("letters: %s" % error, file=sys.stderr)
        return 1

    Path(args.out).write_text(render_report(results, rubric_terms(table)), encoding="utf-8")
    print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
