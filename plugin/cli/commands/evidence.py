"""`compass evidence run|rerun|show` - keep a check rerunnable.

    compass evidence run --task TASK-NNN --check <slug> -- <command...>
    compass evidence rerun <record>
    compass evidence show TASK-NNN

`run` executes the command from the current directory without streaming,
writes `.compass/evidence/<TASK-NNN>/<slug>.json` and `<slug>.out` at the
repository root, prints the last 40 lines of the combined output and a final
`record: <repo-relative path>` line, and exits with the command's exit code.

`rerun` runs the record's command again at the recorded commit in a scratch
worktree. The first output line is `match` or `mismatch`; a mismatch lists the
recorded and the rerun exit code and verdict line. Exit code 0 on a match, 1
on a mismatch. A record made on a dirty tree warns on stderr.

`show` prints one line per record of the task, sorted by check.
"""

import os
import sys

import evidencelib

USAGE = """usage:
  compass evidence run --task TASK-NNN --check <slug> -- <command...>
  compass evidence rerun <record>
  compass evidence show TASK-NNN

run     run the command and keep its record and full output under
        .compass/evidence/TASK-NNN/; exit with the command's exit code
rerun   run a record's command again at its recorded commit; print match or
        mismatch (exit 0 or 1)
show    list the records of a task
"""

TAIL_LINES = 40


def _fail(message):
    print(f"compass evidence: {message}", file=sys.stderr)
    return 2


def _parse_run(args):
    if "--" not in args:
        raise evidencelib.EvidenceError("run needs `--` before the command")
    split = args.index("--")
    flags, command = args[:split], args[split + 1:]
    values = {}
    index = 0
    while index < len(flags):
        flag = flags[index]
        name, equals, inline = flag.partition("=")
        if name not in ("--task", "--check"):
            raise evidencelib.EvidenceError(f"unknown argument {flag!r}")
        if equals:
            value = inline
            index += 1
        elif index + 1 < len(flags):
            value = flags[index + 1]
            index += 2
        else:
            raise evidencelib.EvidenceError(f"{name} needs a value")
        values[name] = value
    for name in ("--task", "--check"):
        if name not in values:
            raise evidencelib.EvidenceError(f"run needs {name}")
    if not command:
        raise evidencelib.EvidenceError("run needs a command after `--`")
    return values["--task"], values["--check"], command


def _run(args):
    task, slug, command = _parse_run(args)
    cwd = os.getcwd()
    record, json_path = evidencelib.run_check(cwd, task, slug, command)
    root, _ = evidencelib.repo_root(cwd)
    output = json_path.with_suffix(".out").read_bytes()
    tail = evidencelib.tail_text(output, TAIL_LINES)
    if tail:
        print(tail)
    print(f"record: {json_path.relative_to(root).as_posix()}")
    return record["exit_code"]


def _rerun(args):
    if len(args) != 1:
        raise evidencelib.EvidenceError("rerun takes one record path")
    result = evidencelib.rerun(args[0])
    print(result["verdict"])
    if result["dirty_warning"]:
        print(
            "warning: the tree held uncommitted changes when this record was "
            "made; the rerun uses the committed sha",
            file=sys.stderr,
        )
    if result["verdict"] == "match":
        return 0
    none = "(none)"
    print(f"recorded exit code: {result['recorded_exit_code']}")
    print(f"rerun exit code: {result['exit_code']}")
    print(f"recorded verdict line: {result['recorded_last_line'] or none}")
    print(f"rerun verdict line: {result['last_line'] or none}")
    return 1


def _show(args):
    if len(args) != 1:
        raise evidencelib.EvidenceError("show takes one task id")
    task = args[0]
    records = evidencelib.list_records(os.getcwd(), task)
    if not records:
        print(f"no records for {task}")
        return 0
    for record in records:
        if record.get("unreadable"):
            print(f"{record['check']}  unreadable")
        else:
            sha = str(record.get("sha", ""))[:12]
            print(
                f"{record.get('check')}  exit={record.get('exit_code')}  "
                f"{sha}  {record.get('tree')}"
            )
    return 0


_COMMANDS = {"run": _run, "rerun": _rerun, "show": _show}


def run(args):
    args = list(args)
    if args and args[0] in ("-h", "--help"):
        print(USAGE, end="")
        return 0
    if not args or args[0] not in _COMMANDS:
        print(USAGE, end="", file=sys.stderr)
        return _fail("expected run, rerun or show")
    try:
        return _COMMANDS[args[0]](args[1:])
    except evidencelib.EvidenceError as error:
        return _fail(str(error))
