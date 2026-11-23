"""Ground-truth probes over recorded compaction points.

A compaction point is one `system/compact_boundary` record of a Claude Code
transcript. `find` lists the points of a project folder; `build` freezes, from
the history before a boundary, a set of questions with their expected answers;
`ask` puts the questions to a fresh tool-less session that carries one arm's
text: the host's own summary (the `isCompactSummary` record after the boundary),
the state block `compass session-state` renders at the boundary, both (summary
first), or nothing; `grade` scores the reply against the frozen answers;
`report` aggregates the grades per arm and probe type.

Transcripts are read and never written. Everything else is stored under
`<private root>/probes/<point key>/`:

    key.json            the frozen probe set (questions and expected answers)
    ask-<arm>.json      the raw reply, the session's token counts and, for an arm
                        carrying a state block, that block; a point with no commit
                        to read the state at holds `"no_state": true` and no reply
    grade-<arm>.json    the scores of that reply

The transcript readers in this file are separate from the ones that build the
carried session state, so the code that builds that state never grades it.
"""

import argparse
import hashlib
import json
import posixpath
import random
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import compare
import launch
import records
import sandbox
import topics
from launch import default_private_root
from topics import SessionError

ARMS = ("host-summary", "none", "mechanical", "compass")
# The arms whose carried text includes the state block.
BLOCK_ARMS = ("mechanical", "compass")
EDIT_TOOLS = ("Edit", "Write", "MultiEdit")
RECALL_CAP = 2
PROBE_TYPES = ("artifact", "artifact-recent", "recall", "continuation", "decision", "state")
# The probe types whose scores pool into the per point `state` score.
STATE_TYPES = ("recall", "continuation", "decision")
# The reference arm of the paired tables and the fewest pairs that get an interval.
REFERENCE_ARM = "host-summary"
MIN_PAIRS = 10

# Seconds a probe session may run before it is killed.
SESSION_TIMEOUT = 600
# Seconds `git` and `compass session-state` may run before the point has no state.
STATE_TIMEOUT = 120

_ID = re.compile(r"\b(?:TASK|PLAN)-\d+\b")
_ID_ANY_CASE = re.compile(r"\b(?:task|plan)-\d+\b", re.IGNORECASE)
_ERROR_LINE = re.compile(r"^\s*(?:E\s+)?([A-Za-z_][\w.]*(?:Error|Exception):\s*\S.*?)\s*$")
_ERROR_LITERAL = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception)):\s*(\S.*)$", re.DOTALL)
_CLAUSE_END = re.compile(r",|;|:(?=\s|$)| \(| - ")
_FAILED_COUNT = re.compile(r"\b\d+ failed\b")
_ANSWER_PAIR = re.compile(r'"(.*?)"="(.*?)"(?=, "|\.\s|\.$|$)', re.DOTALL)
_MODEL_ID = re.compile(r"claude-[A-Za-z0-9.\-]+(\[[A-Za-z0-9]+\])?")
_BOUNDARY = ("system", "compact_boundary")


class Refused(Exception):
    """The probes folder would sit inside a git work tree."""


class AlreadyFrozen(Exception):
    """The point already has a frozen probe set."""


class NotBuilt(LookupError):
    """The point has no frozen probe set."""


class NoSummary(LookupError):
    """The transcript holds no compact summary after the point's boundary."""


# Transcript reading ---------------------------------------------------------


def _lines(path):
    return Path(path).read_bytes().decode("utf-8", errors="replace").split("\n")


def _record(line):
    try:
        value = json.loads(line)
    except (ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _is_boundary(record):
    return (record.get("type"), record.get("subtype")) == _BOUNDARY


def _int_or_none(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _blocks(record):
    content = (record.get("message") or {}).get("content")
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    return []


def _text_of(content):
    """The plain text of a message or tool-result content value."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return ""


def _assistant_texts(record):
    return [b["text"] for b in _blocks(record) if b.get("type") == "text" and isinstance(b.get("text"), str)]


def _tool_uses(record):
    return [b for b in _blocks(record) if b.get("type") == "tool_use"]


def _tool_results(record):
    return [b for b in _blocks(record) if b.get("type") == "tool_result"]


def _point_parts(point):
    transcript, separator, number = str(point).rpartition("#")
    if not separator or not number.isdigit() or not transcript:
        raise ValueError("a point reads <transcript path>#<boundary index>")
    return transcript, int(number)


def _history(point):
    """(records before the boundary, the boundary record, the records after it)."""
    transcript, index = _point_parts(point)
    lines = _lines(transcript)
    boundary = _record(lines[index]) if index < len(lines) else None
    if boundary is None or not _is_boundary(boundary):
        raise ValueError("the point is not a compaction boundary")
    # A subagent's own transcript marks every record, its boundary included, as a
    # sidechain; the history of a point is the records on the boundary's side.
    side = boundary.get("isSidechain") is True
    before, after = [], []
    for position, line in enumerate(lines):
        record = _record(line)
        if record is None or (record.get("isSidechain") is True) != side:
            continue
        if position < index:
            before.append(record)
        elif position > index:
            after.append(record)
    return before, boundary, after


# find -----------------------------------------------------------------------


def _transcripts(folder):
    """The session transcripts directly inside `folder` and the subagent
    transcripts in each session's `subagents/` folder."""
    return sorted(folder.glob("*.jsonl")) + sorted(folder.glob("*/subagents/*.jsonl"))


def find(project_dir):
    """The compaction points of the session and subagent transcripts of `project_dir`."""
    folder = Path(project_dir)
    if not folder.is_dir():
        raise ValueError(f"{folder} is not a folder")
    found = []
    for path in _transcripts(folder):
        if not path.is_file():
            continue
        for index, line in enumerate(_lines(path)):
            record = _record(line)
            if record is None or not _is_boundary(record):
                continue
            meta = record.get("compactMetadata")
            meta = meta if isinstance(meta, dict) else {}
            trigger = meta.get("trigger")
            found.append({
                "point": f"{path.resolve()}#{index}",
                "transcript": str(path.resolve()),
                "boundary": index,
                "trigger": trigger if isinstance(trigger, str) else "unknown",
                "pre_tokens": _int_or_none(meta.get("preTokens")) or 0,
                "post_tokens": _int_or_none(meta.get("postTokens")),
            })
    return found


# storage --------------------------------------------------------------------


def _probes_dir(private_root):
    root = Path(private_root) if private_root is not None else default_private_root()
    return root / "probes"


def _check_private_root(private_root):
    if records._inside_work_tree(_probes_dir(private_root)):
        raise Refused("probe files stay outside git work trees")


def _point_dir(point, private_root):
    return _probes_dir(private_root) / hashlib.sha256(str(point).encode("utf-8")).hexdigest()[:16]


def _load_key(point, private_root):
    path = _point_dir(point, private_root) / "key.json"
    try:
        key = topics.read_json(path)
    except FileNotFoundError:
        raise NotBuilt("the point has no frozen probe set") from None
    except (ValueError, OSError) as error:
        raise NotBuilt(f"the point's probe set cannot be read: {error}") from error
    if not isinstance(key, dict) or not isinstance(key.get("probes"), list):
        raise NotBuilt("the point's probe set is damaged")
    return key


# build ----------------------------------------------------------------------


def _slash(path):
    return str(path).replace("\\", "/")


def _relative_to(path, cwd):
    """`path` relative to `cwd` when it lies below it, else `path` with forward slashes."""
    path = _slash(path)
    if isinstance(cwd, str) and cwd:
        base = _slash(cwd).rstrip("/") + "/"
        if path.casefold().startswith(base.casefold()):
            return path[len(base):]
    return path


def _edited_paths(history):
    paths = []
    for record in history:
        if record.get("type") != "assistant":
            continue
        for use in _tool_uses(record):
            target = (use.get("input") or {}).get("file_path") if isinstance(use.get("input"), dict) else None
            if use.get("name") in EDIT_TOOLS and isinstance(target, str) and target.strip():
                path = _relative_to(target.strip(), record.get("cwd"))
                if path not in paths:
                    paths.append(path)
    return paths


def _recall_literals(history):
    """Up to RECALL_CAP literals from error tool results: the last exception
    line, then the last failing-test count."""
    last_error, last_failed = None, None
    for record in history:
        if record.get("type") != "user":
            continue
        for result in _tool_results(record):
            if result.get("is_error") is not True:
                continue
            text = _text_of(result.get("content"))
            for line in text.split("\n"):
                match = _ERROR_LINE.match(line)
                if match:
                    last_error = match.group(1)
            counts = _FAILED_COUNT.findall(text)
            if counts:
                last_failed = counts[-1]
    return [literal for literal in (last_error, last_failed) if literal][:RECALL_CAP]


def _last_id(history):
    found = None
    for record in history:
        if record.get("type") != "assistant":
            continue
        for text in _assistant_texts(record):
            ids = _ID.findall(text)
            if ids:
                found = ids[-1]
    return found


def _answers_of(record, result):
    """{question: answer} of one AskUserQuestion result."""
    structured = record.get("toolUseResult")
    answers = structured.get("answers") if isinstance(structured, dict) else None
    if isinstance(answers, dict):
        return {q: a for q, a in answers.items() if isinstance(q, str) and isinstance(a, str)}
    text = _text_of(result.get("content"))
    return dict(_ANSWER_PAIR.findall(text))


def _last_decision(history):
    """(question, chosen option) of the last answered AskUserQuestion."""
    asked, answered = {}, []
    for record in history:
        if record.get("type") == "assistant":
            for use in _tool_uses(record):
                if use.get("name") == "AskUserQuestion" and isinstance(use.get("id"), str):
                    asked[use["id"]] = use
        elif record.get("type") == "user":
            for result in _tool_results(record):
                if result.get("tool_use_id") in asked and result.get("is_error") is not True:
                    answered.append(_answers_of(record, result))
    for answers in reversed(answered):
        for question, answer in reversed(list(answers.items())):
            if question.strip() and answer.strip():
                return question.strip(), answer.strip()
    return None


def _without_answer(question, answer):
    """`question` with every occurrence of `answer` replaced by a gap, so a question
    that lists its own options never carries the chosen one."""
    gapped = re.sub(re.escape(answer), "[...]", question, flags=re.IGNORECASE)
    return gapped if answer.casefold() not in gapped.casefold() else "(the question text is withheld)"


def _last_cwd(history):
    """The working folder of the last record before the boundary that names one."""
    cwd = None
    for record in history:
        if isinstance(record.get("cwd"), str) and record["cwd"].strip():
            cwd = record["cwd"]
    return cwd


def _last_model(history):
    model = None
    for record in history:
        if record.get("type") == "assistant":
            value = (record.get("message") or {}).get("model")
            if isinstance(value, str) and _MODEL_ID.fullmatch(value):
                model = value
    return model


def _since_last_boundary(history):
    """The records of `history` after its last compaction boundary, or all of them
    when it holds none."""
    start = 0
    for position, record in enumerate(history):
        if _is_boundary(record):
            start = position + 1
    return history[start:]


def _probe_set(history):
    probes = []
    paths = _edited_paths(history)
    if paths:
        probes.append({
            "id": "artifact", "type": "artifact", "expected": paths,
            "expected_recent": _edited_paths(_since_last_boundary(history)),
            "question": "Which files did the assistant create or modify with its edit tools in "
                        "this session? List every path.",
        })
    questions = (
        "Quote, as exactly as you can, the last exception line (a line of the form "
        "`<Name>Error: <message>`) that a failing command printed, message included.",
        "A failing test run printed a summary count of the form `N failed`. Quote that count.",
    )
    literals = _recall_literals(history)
    for number, literal in enumerate(literals, start=1):
        question = questions[0] if _ERROR_LINE.match(literal) else questions[1]
        probes.append({"id": f"recall-{number}", "type": "recall", "question": question, "expected": literal})
    identifier = _last_id(history)
    if identifier:
        probes.append({
            "id": "continuation", "type": "continuation", "expected": identifier,
            "question": "Which task or plan id (of the form TASK-N or PLAN-N) did the assistant "
                        "name most recently as the work in hand or the next step? Give the id alone.",
        })
    decision = _last_decision(history)
    if decision:
        question, answer = decision
        probes.append({
            "id": "decision", "type": "decision", "expected": answer,
            "question": f'The user was asked: "{_without_answer(question, answer)}" '
                        "Which option did the user choose? Give the option text alone.",
        })
    return probes


def _add_expected_recent(point, path, private_root):
    """Add `expected_recent` to the artifact probe of a key frozen without it, leaving
    every other field as it was. Raises AlreadyFrozen when there is nothing to add."""
    try:
        key = _load_key(point, private_root)
    except NotBuilt:
        raise AlreadyFrozen("the point already has a frozen probe set") from None
    artifact = next((p for p in key["probes"] if isinstance(p, dict) and p.get("type") == "artifact"), None)
    if artifact is None or "expected_recent" in artifact:
        raise AlreadyFrozen("the point already has a frozen probe set")
    history, _, _ = _history(point)
    artifact["expected_recent"] = _edited_paths(_since_last_boundary(history))
    topics.write_json(path, key)
    return key


def build(point, *, private_root=None):
    """Freeze the probe set of `point` and return it; a key frozen without the
    artifact probe's `expected_recent` gains it and nothing else. Raises Refused for
    a private root inside a git work tree, AlreadyFrozen for a second build of a
    point, and ValueError for a point that is no boundary or has no probe source."""
    _check_private_root(private_root)
    path = _point_dir(point, private_root) / "key.json"
    if path.exists():
        return _add_expected_recent(point, path, private_root)
    history, _, _ = _history(point)
    model = _last_model(history)
    probes = _probe_set(history)
    if model is None or not probes:
        raise ValueError("the history before the boundary holds no assistant model or no probe source")
    key = {"point": point, "model": model, "cwd": _last_cwd(history), "probes": probes}
    try:
        topics.write_json(path, key, exclusive=True)
    except FileExistsError:
        raise AlreadyFrozen("the point already has a frozen probe set") from None
    return key


# ask ------------------------------------------------------------------------


def _carried_text(point):
    _, _, after = _history(point)
    for record in after:
        if _is_boundary(record):
            break
        if record.get("isCompactSummary") is True:
            text = _text_of((record.get("message") or {}).get("content"))
            if text.strip():
                return text
    raise NoSummary("the transcript holds no compact summary after the boundary")


def _run_quiet(command, *, cwd=None, env=None):
    """(exit code, stdout) of `command`, or None when it cannot start or times out."""
    try:
        done = subprocess.run(
            command, cwd=cwd, env=env, capture_output=True, timeout=STATE_TIMEOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.returncode, done.stdout.decode("utf-8", errors="replace")


def _epoch_second(stamp):
    """The whole second of an ISO 8601 `stamp` as epoch seconds, or None."""
    if not isinstance(stamp, str):
        return None
    try:
        moment = datetime.fromisoformat(stamp.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp())


def _commit_at_boundary(cwd, boundary):
    """The last commit of the boundary record's `gitBranch` committed at or before
    the boundary's `timestamp`, read in `cwd`; HEAD stands in for a branch that is
    no longer there. None when no commit qualifies or git cannot say."""
    second = _epoch_second(boundary.get("timestamp"))
    if second is None or not isinstance(cwd, str) or not cwd.strip():
        return None
    branch = boundary.get("gitBranch")
    ref = "HEAD"
    if isinstance(branch, str) and branch.strip() and branch != "HEAD":
        candidate = f"refs/heads/{branch.strip()}"
        found = _run_quiet(["git", "-C", cwd, "rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}"])
        if found is not None and found[0] == 0:
            ref = candidate
    found = _run_quiet(["git", "-C", cwd, "log", "-1", f"--before={second}", "--format=%H", ref, "--"])
    if found is None or found[0] != 0:
        return None
    return found[1].strip() or None


def _state_block(point, key, repo_root, parent_env):
    """The block `compass session-state` renders for `point` at the boundary and at
    the last commit before it, or None when the point has no commit or the command
    prints nothing or fails."""
    transcript, index = _point_parts(point)
    _, boundary, _ = _history(point)
    cwd = key.get("cwd")
    commit = _commit_at_boundary(cwd, boundary)
    if commit is None:
        return None
    env = dict(os.environ if parent_env is None else parent_env)
    env.pop("CLAUDE_PROJECT_DIR", None)
    command = [
        sys.executable, str(Path(repo_root) / "plugin" / "cli" / "compass"), "session-state",
        "--transcript", transcript, "--until", str(index), "--at", commit, "--format", "block",
    ]
    done = _run_quiet(command, cwd=cwd, env=env)
    if done is None or done[0] != 0 or not done[1].strip():
        return None
    return done[1].strip()


def _is_subagent_point(point):
    """Whether the boundary belongs to a subagent transcript, where a SessionStart
    event carries `agent_id` and the hook prints nothing."""
    _, boundary, _ = _history(point)
    return boundary.get("isSidechain") is True


def _prompt(carried, probes):
    lines = []
    if carried is not None:
        lines += [carried.rstrip(), "", "---", ""]
    lines += [
        "Answer the questions below about a coding session. You have no tools; answer from "
        "what you were given, and give your best guess where you do not know.",
        "",
    ]
    for item in probes:
        lines.append(f"[{item['id']}] {item['question']}")
    keys = ", ".join(
        f'"{item["id"]}" ({"a list of file paths" if item["type"] == "artifact" else "a string"})'
        for item in probes
    )
    lines += ["", f"Reply with one JSON object and nothing else. Its keys are: {keys}."]
    return "\n".join(lines) + "\n"


def _reply_text(events):
    for event in reversed(events):
        if event.get("type") == "result":
            text = event.get("result")
            return text if isinstance(text, str) else ""
    return ""


def ask(point, arm, *, repo_root, private_root=None, claude_cmd=None, parent_env=None):
    """Run one tool-less session over the frozen questions of `point` and store its
    reply. A block arm (`mechanical`, `compass`) carries the state block of the
    boundary; a point with no block to carry stores `"no_state": true` and starts no
    session. Raises ValueError for an arm outside ARMS, Refused, NotBuilt, NoSummary
    (arms carrying the host summary) and SessionError when the session does not end
    `done`."""
    if arm not in ARMS:
        raise ValueError(f"the arm is one of {', '.join(ARMS)}")
    _check_private_root(private_root)
    key = _load_key(point, private_root)
    model = key.get("model")
    if not isinstance(model, str) or not _MODEL_ID.fullmatch(model):
        raise NotBuilt("the point's probe set names no usable model")
    summary = _carried_text(point) if arm in ("host-summary", "compass") else None
    block = None
    if arm in BLOCK_ARMS and not (arm == "compass" and _is_subagent_point(point)):
        block = _state_block(point, key, repo_root, parent_env)
        if block is None:
            stored = {"point": point, "arm": arm, "no_state": True}
            topics.write_json(_point_dir(point, private_root) / f"ask-{arm}.json", stored)
            return stored
    parts = [part.rstrip() for part in (summary, block) if part is not None]
    carried = "\n\n".join(parts) if parts else None
    root = Path(private_root) if private_root is not None else default_private_root()
    project = sandbox.new_project(root / "probe-projects")
    result = launch.run_session(
        project, _prompt(carried, key["probes"]), repo_root=repo_root, private_root=root,
        claude_cmd=claude_cmd, parent_env=parent_env,
        extra_args=["--tools", "", "--model", model], timeout=SESSION_TIMEOUT,
    )
    if result.status != launch.DONE:
        raise SessionError(result.status)
    stored = {
        "point": point, "arm": arm, "reply": _reply_text(result.events),
        "tokens": records.count_tokens(result.events),
    }
    if block is not None:
        stored["block"] = block
    topics.write_json(_point_dir(point, private_root) / f"ask-{arm}.json", stored)
    return stored


# grade ----------------------------------------------------------------------


def _norm_path(path):
    text = _slash(path).strip()
    while text.startswith("./"):
        text = text[2:]
    return posixpath.normpath(text) if text else ""


def _norm_text(text):
    return " ".join(str(text).split()).casefold()


def _score_artifact(value, expected, cwd=None):
    """Precision and recall of the paths in `value`; a reply path below `cwd`
    counts in its cwd-relative form, the form the expected paths are frozen in."""
    wanted = {_norm_path(p) for p in expected}
    if not isinstance(value, list):
        return {"precision": 0.0, "recall": 0.0}
    given = {_norm_path(_relative_to(p.strip(), cwd)) for p in value if isinstance(p, str) and p.strip()}
    hits = len(given & wanted)
    return {
        "precision": hits / len(given) if given else 0.0,
        "recall": hits / len(wanted) if wanted else 0.0,
    }


def _score_text(value, expected, whole_words):
    if not isinstance(value, str):
        return 0.0
    given, wanted = _norm_text(value), _norm_text(expected)
    if not wanted:
        return 0.0
    if whole_words:
        return 1.0 if re.search(rf"(?<!\w){re.escape(wanted)}(?!\w)", given) else 0.0
    before = r"(?<!\d)(?<!\d[.,])" if wanted[0].isdigit() else ""
    after = r"(?!\d)" if wanted[-1].isdigit() else ""
    return 1.0 if re.search(f"{before}{re.escape(wanted)}{after}", given) else 0.0


def _has_phrase(given, phrase):
    """True when the normalized `phrase` occurs in `given`, not inside a longer word."""
    before = r"(?<!\w)" if phrase[0].isalnum() or phrase[0] == "_" else ""
    after = r"(?!\w)" if phrase[-1].isalnum() or phrase[-1] == "_" else ""
    return re.search(f"{before}{re.escape(phrase)}{after}", given) is not None


def _score_error(value, expected):
    """1 when the reply holds the exception name as a whole word and the first clause
    of the message (the message up to its first `,`, `;`, `: `, ` (` or ` - `); a
    message with no such separator must appear whole. `expected` is `<Name>: <message>`."""
    if not isinstance(value, str):
        return 0.0
    match = _ERROR_LITERAL.match(expected)
    name = _norm_text(match.group(1))
    message = _norm_text(match.group(2))
    clause = _CLAUSE_END.split(message, maxsplit=1)[0].strip() or message
    given = _norm_text(value)
    return 1.0 if _has_phrase(given, name) and _has_phrase(given, clause) else 0.0


def _score_id(value, expected):
    if not isinstance(value, str):
        return 0.0
    ids = {found.upper() for found in _ID_ANY_CASE.findall(value)}
    return 1.0 if ids == {str(expected).upper()} else 0.0


def _score(item, value, cwd=None):
    kind = item.get("type")
    if kind == "artifact":
        return _score_artifact(value, item["expected"], cwd)
    if kind == "continuation":
        return _score_id(value, item["expected"])
    if kind == "recall" and _ERROR_LITERAL.match(str(item["expected"])):
        return _score_error(value, item["expected"])
    return _score_text(value, item["expected"], whole_words=kind == "decision")


def _input_tokens(tokens):
    if not isinstance(tokens, dict):
        return 0
    return sum(
        counts.get(kind, 0) for counts in tokens.values() if isinstance(counts, dict)
        for kind in ("input", "cache_read", "cache_write")
        if isinstance(counts.get(kind), int)
    )


def _key_cwd(key):
    """The point's working folder: the one frozen in its key, else the last one
    its transcript names before the boundary, else None."""
    if isinstance(key.get("cwd"), str):
        return key["cwd"]
    try:
        history, _, _ = _history(key.get("point"))
    except (OSError, ValueError, TypeError):
        return None
    return _last_cwd(history)


def _grade_reply(key, stored):
    try:
        reply = topics.reply_object(stored.get("reply") if isinstance(stored.get("reply"), str) else "")
    except ValueError:
        reply = None
    cwd = _key_cwd(key)
    scores = {}
    for item in key["probes"]:
        value = reply.get(item["id"]) if reply is not None else None
        scores[item["id"]] = _score(item, value, cwd)
        recent = item.get("expected_recent")
        if item.get("type") == "artifact" and isinstance(recent, list) and recent:
            scores[f"{item['id']}-recent"] = _score_artifact(value, recent, cwd)["recall"]
    return {
        "point": stored.get("point"), "arm": stored.get("arm"), "unparsed": reply is None,
        "scores": scores, "input_tokens": _input_tokens(stored.get("tokens")),
    }


def grade(point, *, private_root=None):
    """Score every stored reply of `point`; {arm: grade}. Raises Refused and NotBuilt."""
    _check_private_root(private_root)
    key = _load_key(point, private_root)
    folder = _point_dir(point, private_root)
    graded = {}
    for arm in ARMS:
        path = folder / f"ask-{arm}.json"
        if not path.is_file():
            continue
        stored = topics.read_json(path)
        if stored.get("no_state") is True:
            continue
        result = _grade_reply(key, stored)
        topics.write_json(folder / f"grade-{arm}.json", result)
        graded[arm] = result
    return graded


# report ---------------------------------------------------------------------


def _type_of(probe_id):
    return probe_id if probe_id == "artifact-recent" else probe_id.split("-")[0]


def _point_scores(scores):
    """{probe type: score} of one graded point; recall's probes are averaged and
    artifact's score is its recall. `state` is the mean of the recall, continuation
    and decision scores the point has, absent when it has none of them."""
    grouped = {}
    for probe_id, score in scores.items():
        value = score["recall"] if isinstance(score, dict) else score
        grouped.setdefault(_type_of(probe_id), []).append(float(value))
    means = {kind: sum(values) / len(values) for kind, values in grouped.items()}
    pooled = [means[kind] for kind in STATE_TYPES if kind in means]
    if pooled:
        means["state"] = sum(pooled) / len(pooled)
    return means


def _mean(values):
    return sum(values) / len(values)


def _paired_interval(differences):
    """(low, high) of the 95% bootstrap interval of the mean of `differences`,
    resampling the points with replacement from a generator seeded with compare.SEED."""
    rng = random.Random(compare.SEED)
    means = sorted(
        sum(rng.choices(differences, k=len(differences))) / len(differences)
        for _ in range(compare.RESAMPLES)
    )
    low = means[int(0.025 * (compare.RESAMPLES - 1))]
    high = means[int(round(0.975 * (compare.RESAMPLES - 1)))]
    return float(low), float(high)


def _paired_table(arm, points):
    """The rows comparing `arm` with the reference arm: per probe type, the points
    scored in both arms, the mean of (arm minus reference) and its paired interval."""
    lines = []
    for kind in PROBE_TYPES:
        differences = [
            scores[arm][kind] - scores[REFERENCE_ARM][kind] for scores in points
            if kind in scores.get(arm, {}) and kind in scores.get(REFERENCE_ARM, {})
        ]
        if not differences:
            continue
        if len(differences) < MIN_PAIRS:
            interval = "too few points"
        else:
            low, high = _paired_interval(differences)
            interval = f"[{low:.2f}, {high:.2f}]"
        lines.append(f"| {arm} | {kind} | {len(differences)} | {_mean(differences):.2f} | {interval} |")
    if not lines:
        return []
    header = [
        f"| arm | probe | pairs | mean difference from {REFERENCE_ARM} | 95% paired interval |",
        "|---|---|---|---|---|",
    ]
    return header + lines


def report(*, private_root=None):
    """A markdown table of the stored grades, per arm and probe type, followed by one
    table per arm other than the reference arm holding its paired differences."""
    folders = sorted(p for p in _probes_dir(private_root).glob("*") if p.is_dir())
    per_arm = {}
    points = []
    for folder in folders:
        grades = {}
        for arm in ARMS:
            path = folder / f"grade-{arm}.json"
            if path.is_file():
                grades[arm] = topics.read_json(path)
        floor = grades.get("none", {}).get("input_tokens")
        point_scores = {}
        for arm, graded in grades.items():
            entry = per_arm.setdefault(arm, {"scores": {}, "unparsed": 0, "carried": []})
            entry["unparsed"] += 1 if graded.get("unparsed") else 0
            point_scores[arm] = _point_scores(graded.get("scores", {}))
            for kind, score in point_scores[arm].items():
                entry["scores"].setdefault(kind, []).append(score)
            if arm == "none":
                entry["carried"].append(0)
            elif isinstance(floor, int):
                entry["carried"].append(max(0, graded.get("input_tokens", 0) - floor))
        points.append(point_scores)
    lines = [
        "| arm | probe | points | mean score | unparsed | mean carried tokens |",
        "|---|---|---|---|---|---|",
    ]
    for arm in sorted(per_arm):
        entry = per_arm[arm]
        carried = f"{_mean(entry['carried']):.0f}" if entry["carried"] else "-"
        for kind in PROBE_TYPES:
            values = entry["scores"].get(kind)
            if values:
                lines.append(
                    f"| {arm} | {kind} | {len(values)} | {_mean(values):.2f} | {entry['unparsed']} | {carried} |"
                )
    for arm in sorted(per_arm):
        if arm != REFERENCE_ARM:
            table = _paired_table(arm, points)
            if table:
                lines += ["", *table]
    no_state = {arm: 0 for arm in ARMS}
    for folder in folders:
        for arm in ARMS:
            path = folder / f"ask-{arm}.json"
            if path.is_file() and topics.read_json(path).get("no_state") is True:
                no_state[arm] += 1
    lines += [""] if any(no_state.values()) else []
    lines += [f"no-state points, {arm}: {count}" for arm, count in sorted(no_state.items()) if count]
    return "\n".join(lines) + "\n"


# command line ---------------------------------------------------------------


def _parser():
    parser = argparse.ArgumentParser(prog="probe", description="Ground-truth probes over compaction points.")
    parser.add_argument("--private-root", default=None)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("find", help="list the compaction points of a project folder").add_argument(
        "--project-dir", required=True)
    commands.add_parser("build", help="freeze the probe set of a point").add_argument("point")
    ask_parser = commands.add_parser("ask", help="put a point's questions to a tool-less session")
    ask_parser.add_argument("point")
    ask_parser.add_argument("--arm", choices=ARMS, required=True)
    commands.add_parser("grade", help="score the stored replies of a point").add_argument("point")
    commands.add_parser("report", help="print the per arm and probe type table")
    return parser


def main(argv, *, claude_cmd=None, repo_root=None, parent_env=None):
    args = _parser().parse_args(argv)
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    try:
        if args.command == "find":
            for item in find(args.project_dir):
                post = "-" if item["post_tokens"] is None else item["post_tokens"]
                print(f"{item['point']}\t{item['trigger']}\t{item['pre_tokens']}\t{post}")
        elif args.command == "build":
            print(len(build(args.point, private_root=args.private_root)["probes"]))
        elif args.command == "ask":
            ask(
                args.point, args.arm, repo_root=root, private_root=args.private_root,
                claude_cmd=claude_cmd, parent_env=parent_env,
            )
        elif args.command == "grade":
            for arm, graded in grade(args.point, private_root=args.private_root).items():
                print(f"{arm}\t{'unparsed' if graded['unparsed'] else 'parsed'}")
        else:
            print(report(private_root=args.private_root), end="")
    except SessionError as error:
        print(f"probe session ended {error.status}", file=sys.stderr)
        return 1
    except (
        Refused, AlreadyFrozen, NotBuilt, NoSummary, ValueError,
        launch.Refused, sandbox.Refused, records.Refused, OSError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
