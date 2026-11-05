"""One-launch check: does a subagent's `initialPrompt` run when it is launched?

A fresh sandbox project gets Compass from `/compass:setup`, run in a session
started with `--plugin-dir`. A second session, started without `--plugin-dir` so
Compass loads once from the project's own `.claude/` install, asks the main
agent to launch one `builder` subagent with a two-line task that names no
start-here file. The builder's subagent transcript is then read and reduced to:

    start-here reads     the three files `initialPrompt` names, in the order the
                         builder Read them; the initial prompt "ran" when all
                         three are Read before the first tool call that is not
                         one of those Reads
    first user turn      the text of the transcript's first non-meta user entry
    tool-call outcomes   tool calls, and how many were refused by a permission
                         prompt or by the fence hook

The sessions run under the launch.py isolation with the drive.py fence hook, so
every fenced call is allowed headless and a refusal is the fence's or the
permission system's, never a prompt nobody can answer.

    python probe_initial_prompt.py [--projects-root DIR] [--private-root DIR]
        [--max-budget-usd N]
    python probe_initial_prompt.py --analyse TRANSCRIPT

The first form creates the project, runs both sessions and prints one JSON
object of aggregate facts plus the project folder, for `sandbox.py discard`.
The second reads one subagent transcript.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import drive
import launch
import sandbox

START_HERE = (".compass/index.md", ".compass/active.md", ".compass/lessons/index.md")
AGENT_TYPE = "builder"
BRIEF = "Create the file hello.txt containing the single word hello.\nThen reply with the single word done."
SETUP_MESSAGE = drive.SETUP_MESSAGE
OPENING_MESSAGE = (
    "Launch one `builder` subagent, with the Agent tool and subagent_type `builder`, "
    "and give it exactly this two-line task:\n\n"
    f"{BRIEF}\n\n"
    "Wait for it to finish, then reply with its one-line result."
)

DEFAULT_MAX_BUDGET_USD = 3.0
# Seconds each session may run.
SETUP_TIMEOUT_SECONDS = 1200
PROBE_TIMEOUT_SECONDS = 1800

RAN = "ran"
DID_NOT_RUN = "did not run"

# What a tool result says when the permission system refused the call.
_PERMISSION_DENIAL = re.compile(
    r"haven't granted it yet|doesn't want to proceed with this tool use", re.IGNORECASE,
)
# What a tool result says when a PreToolUse hook refused the call.
_HOOK_DENIAL = re.compile(r"hook error", re.IGNORECASE)

# What the answer command prints for a question the fence hook forwards to it.
ANSWER_COMMAND = [sys.executable, "-c", "print('{\"answers\": {}}')"]


def read_entries(path):
    """The JSON objects of a transcript file, in order; lines that do not parse are skipped."""
    entries = []
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for line in text.split("\n"):
        line = line.strip(" \t\r")
        if not line:
            continue
        try:
            entry = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def _blocks(entry):
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    return []


def _text_of(entry):
    """The text of a user entry: a string content, or its text blocks joined."""
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") for block in content
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
        )
    return ""


def first_user_turn(entries):
    """The text of the first user entry that is not a meta entry, or None."""
    for entry in entries:
        if entry.get("type") == "user" and not entry.get("isMeta"):
            return _text_of(entry)
    return None


def start_here_file(path):
    """The start-here file `path` names, or None."""
    if not isinstance(path, str):
        return None
    normal = path.replace("\\", "/")
    for name in START_HERE:
        if normal == name or normal.endswith("/" + name):
            return name
    return None


def tool_calls(entries):
    """(tool name, input) of every tool call of the assistant entries, in order."""
    calls = []
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        for block in _blocks(entry):
            if block.get("type") == "tool_use":
                tool_input = block.get("input")
                calls.append((str(block.get("name")), tool_input if isinstance(tool_input, dict) else {}))
    return calls


def _start_here_read(call):
    name, tool_input = call
    return start_here_file(tool_input.get("file_path")) if name == "Read" else None


def _result_text(block):
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(item.get("text", "") for item in content if isinstance(item, dict))
    return ""


def denials(entries):
    """(permission refusals, hook refusals) among the error tool results."""
    permission = hook = 0
    for entry in entries:
        if entry.get("type") != "user":
            continue
        for block in _blocks(entry):
            if block.get("type") != "tool_result" or block.get("is_error") is not True:
                continue
            text = _result_text(block).replace("’", "'")
            if _PERMISSION_DENIAL.search(text):
                permission += 1
            elif _HOOK_DENIAL.search(text):
                hook += 1
    return permission, hook


def analyse(entries, brief=BRIEF):
    """Aggregate facts of one subagent transcript, given its entries."""
    calls = tool_calls(entries)
    reads = []
    for call in calls:
        found = _start_here_read(call)
        if found is not None and found not in reads:
            reads.append(found)
    leading = []
    for call in calls:
        found = _start_here_read(call)
        if found is None:
            break
        if found not in leading:
            leading.append(found)
    first = first_user_turn(entries)
    permission, hook = denials(entries)
    return {
        "initial_prompt": RAN if set(leading) == set(START_HERE) else DID_NOT_RUN,
        "start_here_reads": reads,
        "leading_start_here_reads": leading,
        "first_tool_call": calls[0][0] if calls else None,
        "first_user_turn_is_brief": first is not None and first.strip() == brief.strip(),
        "first_user_turn_names_start_here": first is not None and any(name in first for name in START_HERE),
        "first_user_turn_characters": len(first) if first is not None else 0,
        "tool_calls": len(calls),
        "permission_denials": permission,
        "hook_denials": hook,
        "without_permission_denials": permission == 0,
    }


def find_subagent_transcript(private_root, project, started, agent_type=AGENT_TYPE):
    """The newest subagent transcript of `agent_type` written since `started`
    under the sandbox config's folder for `project`, or None."""
    projects = Path(private_root) / "claude-config" / "projects"
    names = {launch.encode_cwd(Path(project).absolute()), launch.encode_cwd(Path(project).resolve())}
    newest, newest_time = None, None
    for name in names:
        for path in (projects / name).glob("*/subagents/*.jsonl"):
            try:
                meta = json.loads(path.with_name(path.stem + ".meta.json").read_text(encoding="utf-8"))
                modified = path.stat().st_mtime
            except (OSError, ValueError):
                continue
            if not isinstance(meta, dict) or meta.get("agentType") != agent_type:
                continue
            if modified < started - launch.TRANSCRIPT_SLACK_SECONDS:
                continue
            if newest_time is None or modified > newest_time:
                newest, newest_time = path, modified
    return newest


def _session_facts(result):
    return {"status": result.status, "returncode": result.returncode}


def run_probe(
    project,
    *,
    repo_root,
    private_root=None,
    claude_cmd=None,
    parent_env=None,
    remote_sha=None,
    max_budget_usd=DEFAULT_MAX_BUDGET_USD,
):
    """Run the setup session and the launch session in `project`; return the facts.

    `remote_sha` is the commit pinned in the project's `plugin.yaml` after setup,
    so the next session's start-of-session self-update finds the install current;
    by default the repository's remote head. Raises launch.Refused, before
    anything starts, when `plugin/` of `repo_root` has uncommitted changes.
    """
    project = Path(project)
    repo_root = Path(repo_root)
    private_root = Path(private_root) if private_root is not None else launch.default_private_root()
    launch.check_plugin_clean(repo_root, require_plugin=True)
    pinned = remote_sha if remote_sha is not None else drive.remote_head(repo_root)

    parent = os.environ if parent_env is None else parent_env
    home = drive.sandbox_home(project, private_root)
    env = drive.apply_home(dict(parent), home)
    drive.install_hook(project)
    env["OVERHEAD_HOOK_CONFIG"] = str(
        drive.write_hook_config(project, private_root, ANSWER_COMMAND, read_roots=[str(repo_root / "plugin")], home=home)
    )
    budget = ["--max-budget-usd", drive._budget_argument(max_budget_usd)]

    def session(prompt, plugin, timeout):
        return launch.run_session(
            project, prompt, repo_root=repo_root, private_root=private_root, plugin=plugin,
            claude_cmd=claude_cmd, parent_env=env, extra_args=budget, timeout=timeout,
        )

    facts = {"setup": None, "launch": None, "transcript_found": False, "analysis": None}
    setup = session(SETUP_MESSAGE, True, SETUP_TIMEOUT_SECONDS)
    facts["setup"] = _session_facts(setup)
    if setup.status != launch.DONE:
        return facts
    if not drive.pin_commit(project, pinned):
        facts["setup"]["status"] = launch.FAILED
        facts["setup"]["reason"] = "setup left no plugin.yaml"
        return facts

    started = time.time()
    launched = session(OPENING_MESSAGE, False, PROBE_TIMEOUT_SECONDS)
    facts["launch"] = _session_facts(launched)
    transcript = find_subagent_transcript(private_root, project, started)
    if transcript is not None:
        facts["transcript_found"] = True
        facts["analysis"] = analyse(read_entries(transcript))
    return facts


def _build_parser():
    parser = argparse.ArgumentParser(description="Does a launched subagent run its initialPrompt?")
    parser.add_argument("--projects-root", default=str(sandbox.DEFAULT_PROJECTS_ROOT))
    parser.add_argument("--private-root")
    parser.add_argument("--max-budget-usd", type=float, default=DEFAULT_MAX_BUDGET_USD)
    parser.add_argument("--analyse", metavar="TRANSCRIPT", help="read one subagent transcript and print its facts")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.analyse:
        try:
            entries = read_entries(args.analyse)
        except OSError as error:
            sys.stderr.write(f"refused: {error}\n")
            return drive.EXIT_REFUSED
        print(json.dumps(analyse(entries)))
        return 0
    repo_root = Path(__file__).resolve().parents[2]
    private_root = Path(args.private_root) if args.private_root else launch.default_private_root()
    try:
        project = sandbox.new_project(args.projects_root)
        facts = run_probe(
            project, repo_root=repo_root, private_root=private_root, max_budget_usd=args.max_budget_usd,
        )
    except (launch.Refused, sandbox.Refused, OSError, RuntimeError) as error:
        sys.stderr.write(f"refused: {error}\n")
        return drive.EXIT_REFUSED
    facts["project"] = str(project)
    print(json.dumps(facts))
    return 0 if facts["analysis"] is not None else 1


if __name__ == "__main__":
    sys.exit(main())
