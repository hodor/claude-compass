"""`compass guard`: the PreToolUse hook that keeps the Data rule mechanical.

Nothing in a Compass project destroys information. This command runs as a
PreToolUse hook before every tool call a subagent makes, whatever its
permission mode; the main agent, working with the human, is never judged.
It reads the event on stdin and denies a subagent call that would delete
or discard: a Bash command that
removes files or discards git state, a Write that empties an existing file
or guts a vault document, an Edit that blanks a long vault passage. A
denial is the JSON permission decision on stdout with exit 0 (the CLI never
exits 2); the reason names the rule and the colder home for the text.

Scratch areas stay open, so cleanup keeps working: `.compass/tmp/`, agent
worktrees under `.claude/worktrees/`, the session scratchpad and system
temp dirs, and Python bytecode caches.
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path

import vaultlib

DELETE_VERBS = {
    "rm", "rmdir", "unlink", "del", "erase", "rd", "remove-item", "ri",
    "trash", "trash-put", "shred", "truncate",
}
# Verbs whose first argument is the real command.
WRAPPERS = {"sudo", "command", "exec", "nohup", "time", "env", "doas", "busybox"}
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
PYTHON_VERBS = {"python", "python3", "python2", "py", "pythonw"}
PYTHON_DELETES = [
    (re.compile(r"\brmtree\s*\("), "rmtree"),
    (re.compile(r"\bunlink\s*\("), "unlink"),
    (re.compile(r"\bos\.remove\s*\("), "os.remove"),
    (re.compile(r"\bos\.rmdir\s*\("), "os.rmdir"),
    (re.compile(r"\bsend2trash\b"), "send2trash"),
]
SEPARATORS = {";", "&&", "||", "|", "&"}
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")

# Vault files an agent or the sweep rewrites wholesale by design; the shrink
# and blanking rules never judge them.
VAULT_REWRITABLE_NAMES = {"index.md", "active.md", "backlog.md"}
VAULT_REWRITABLE_DIRS = {"meta", "archive", "tmp", ".annotations", ".obsidian"}
SHRINK_KEEP_RATIO = 0.5
BLANK_LINES_FLOOR = 10

RULE = "nothing destroys information (the Data rule)"
COLDER = (
    "Move it colder instead: `git mv` into .compass/archive/ or a Record "
    "section, or ask the human; scratch stays deletable (.compass/tmp/, "
    ".claude/worktrees/, the session scratchpad)"
)


def _posix(path):
    return str(path).replace("\\", "/")


def _is_scratch(raw, project_root):
    """True when a path names a scratch area: deletable by design. Inside
    the project that is `.compass/tmp/`, `.claude/worktrees/`, and bytecode
    caches; outside it, the system temp dirs and the session scratchpad."""
    text = _posix(raw).strip().strip("'\"")
    low = text.lower()
    if low.startswith("/tmp/") or low.startswith("/var/folders/"):
        return True
    root = Path(project_root)
    try:
        resolved = (root / text).resolve()
        cand = _posix(resolved).lower()
        inside = resolved.is_relative_to(root.resolve())
    except (OSError, ValueError):
        cand, inside = low, True
    base = cand.rstrip("/").rsplit("/", 1)[-1]
    if base in {"__pycache__", ".pytest_cache"} or cand.endswith(".pyc"):
        return True
    if "/__pycache__/" in cand or "/.pytest_cache/" in cand:
        return True
    if "/.compass/tmp/" in cand or cand.endswith("/.compass/tmp"):
        return True
    if "/.claude/worktrees/" in cand:
        return True
    if not inside and ("/appdata/local/temp/" in cand or "/temp/claude/" in cand or "/tmp/" in cand):
        return True
    return False


def _in_vault(path, project_root):
    try:
        rel = Path(path).resolve().relative_to((Path(project_root) / ".compass").resolve())
    except (OSError, ValueError):
        return None
    return rel


def _vault_rewritable(rel):
    parts = rel.parts
    if not parts:
        return True
    if parts[0] in VAULT_REWRITABLE_DIRS:
        return True
    return parts[-1] in VAULT_REWRITABLE_NAMES


def _tokens(line):
    lexer = shlex.shlex(line, posix=False, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return [t.strip("'\"") for t in lexer]
    except ValueError:
        return [t.strip("'\"") for t in line.split()]


def _segments(command):
    """Yield (tokens, remainder_text) per simple command, one per line and
    per `;`, `&&`, `||`, `|`, `&` separator; heredoc bodies are skipped
    (their lines are data, not commands). `remainder_text` is the command
    text from the segment's line onward, for interpreter scans."""
    lines = command.split("\n")
    skip_until = None
    for i, line in enumerate(lines):
        if skip_until is not None:
            if line.strip() == skip_until:
                skip_until = None
            continue
        heredoc = HEREDOC.search(line)
        if heredoc:
            skip_until = heredoc.group(1)
        remainder = "\n".join(lines[i:])
        current = []
        for tok in _tokens(line):
            if tok in SEPARATORS:
                if current:
                    yield current, remainder
                current = []
            else:
                current.append(tok)
        if current:
            yield current, remainder


def _strip_wrappers(tokens):
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if ENV_ASSIGNMENT.match(tok) or tok.lower() in WRAPPERS:
            i += 1
            continue
        break
    return tokens[i:]


def _verb(token):
    name = _posix(token).rsplit("/", 1)[-1]
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name


def _path_args(tokens, verb):
    args = []
    for tok in tokens[1:]:
        if tok == "--":
            continue
        if tok.startswith("-"):
            continue
        if verb in {"del", "erase", "rd"} and re.fullmatch(r"/[a-zA-Z]", tok):
            continue
        args.append(tok)
    return args


def _deny_paths(label, paths, project_root):
    if paths and all(_is_scratch(p, project_root) for p in paths):
        return None
    return f"compass guard: `{label}` deletes files in the project; {RULE}. {COLDER}."


def _git_reason(tokens):
    args = [t for t in tokens[1:] if not t.startswith("-")]
    flags = [t for t in tokens[1:] if t.startswith("-")]
    if not args:
        return None
    sub = args[0]
    label = None
    if sub == "rm":
        label = "git rm"
    elif sub == "clean":
        label = "git clean"
    elif sub == "checkout" and "--" in tokens:
        label = "git checkout --"
    elif sub == "restore" and "--staged" not in flags:
        label = "git restore"
    elif sub == "reset" and ("--hard" in flags or "--merge" in flags):
        label = "git reset --hard"
    elif sub == "branch" and ("-D" in flags or ("--delete" in flags and "--force" in flags)):
        label = "git branch -D"
    elif sub == "stash" and len(args) > 1 and args[1] in {"drop", "clear"}:
        label = f"git stash {args[1]}"
    elif sub == "push" and ("--force" in flags or "-f" in flags or "--delete" in flags):
        label = "git push --force"
    if label is None:
        return None
    return f"compass guard: `{label}` discards files or history; {RULE}. {COLDER}."


def _find_reason(tokens, project_root):
    roots = []
    for tok in tokens[1:]:
        if tok.startswith("-") or tok in {"(", "!", ")"}:
            break
        roots.append(tok)
    label = None
    if "-delete" in tokens:
        label = "find -delete"
    for flag in ("-exec", "-execdir", "-ok"):
        if flag in tokens:
            nxt = tokens[tokens.index(flag) + 1:]
            if nxt and _verb(nxt[0]).lower() in DELETE_VERBS:
                label = _verb(nxt[0])
    if label is None:
        return None
    return _deny_paths(label, roots, project_root)


def _truncation_reason(tokens, project_root):
    for i, tok in enumerate(tokens):
        if tok == ">" and i + 1 < len(tokens):
            target = tokens[i + 1]
            path = Path(project_root) / target
            if _is_scratch(target, project_root):
                continue
            if _in_vault(path, project_root) is not None and path.is_file() and path.stat().st_size > 0:
                return (
                    f"compass guard: `> {target}` truncates an existing vault file; "
                    f"{RULE}. Append with `>>` or write the file with its text kept."
                )
    return None


def _bash_reason(command, project_root):
    for tokens, remainder in _segments(command):
        tokens = _strip_wrappers(tokens)
        if not tokens:
            continue
        verb = _verb(tokens[0])
        low = verb.lower()
        if low in DELETE_VERBS:
            reason = _deny_paths(verb, _path_args(tokens, low), project_root)
            if reason:
                return reason
        elif low == "git":
            reason = _git_reason(tokens)
            if reason:
                return reason
        elif low == "find":
            reason = _find_reason(tokens, project_root)
            if reason:
                return reason
        elif low == "xargs":
            for tok in tokens[1:]:
                if _verb(tok).lower() in DELETE_VERBS:
                    return _deny_paths(_verb(tok), [], project_root)
        elif low in PYTHON_VERBS:
            for pattern, label in PYTHON_DELETES:
                if pattern.search(remainder):
                    return (
                        f"compass guard: inline Python calls `{label}`, which deletes "
                        f"files; {RULE}. {COLDER}."
                    )
        reason = _truncation_reason(tokens, project_root)
        if reason:
            return reason
    return None


def _write_reason(tool_input, project_root):
    file_path = tool_input.get("file_path") or ""
    if not file_path:
        return None
    path = Path(file_path)
    if not path.is_absolute():
        path = Path(project_root) / path
    if not path.is_file() or _is_scratch(path, project_root):
        return None
    content = tool_input.get("content")
    if content is None:
        return None
    try:
        old = vaultlib.read_vault_text(path)
    except OSError:
        return None
    if old.strip() and not content.strip():
        return (
            f"compass guard: this Write empties an existing file ({_posix(path)}); "
            f"{RULE}. {COLDER}."
        )
    rel = _in_vault(path, project_root)
    if rel is None or _vault_rewritable(rel):
        return None
    if len(old) and len(content) < len(old) * SHRINK_KEEP_RATIO:
        return (
            f"compass guard: this Write keeps less than half of {_posix(rel)}; "
            f"{RULE}. Keep the text and move what no longer belongs into "
            f".compass/archive/ or a Record section."
        )
    return None


def _edit_reason(tool_input, project_root):
    file_path = tool_input.get("file_path") or ""
    if not file_path:
        return None
    path = Path(file_path)
    if not path.is_absolute():
        path = Path(project_root) / path
    rel = _in_vault(path, project_root)
    if rel is None or _vault_rewritable(rel) or _is_scratch(path, project_root):
        return None
    old = tool_input.get("old_string") or ""
    new = tool_input.get("new_string") or ""
    if new.strip():
        return None
    lines = len([l for l in old.split("\n") if l.strip()])
    if lines < BLANK_LINES_FLOOR:
        return None
    return (
        f"compass guard: this Edit blanks {lines} lines of {_posix(rel)}; {RULE}. "
        f"Move the passage into .compass/archive/ or a Record section instead."
    )


def decide(tool_name, tool_input, project_root):
    """Return (denied, reason) for one tool call."""
    tool_input = tool_input or {}
    reason = None
    if tool_name == "Bash":
        reason = _bash_reason(str(tool_input.get("command") or ""), project_root)
    elif tool_name == "Write":
        reason = _write_reason(tool_input, project_root)
    elif tool_name in {"Edit", "MultiEdit"}:
        reason = _edit_reason(tool_input, project_root)
    return (reason is not None, reason)


def _project_root():
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    try:
        return vaultlib.find_vault_root().parent
    except Exception:
        return Path.cwd()


def _read_stdin():
    data = sys.stdin.read().strip()
    if not data:
        return {}
    try:
        obj = json.loads(data)
    except ValueError:
        return {}
    return obj if isinstance(obj, dict) else {}


def run(args):
    if "--hook" in args:
        try:
            event = _read_stdin()
            if not (event.get("agent_id") or event.get("agent_type")):
                return 0  # the main agent's own call
            denied, reason = decide(
                event.get("tool_name") or "", event.get("tool_input") or {}, _project_root()
            )
            if denied:
                sys.stdout.write(json.dumps({
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                }))
            return 0
        except Exception as exc:  # a guard fault must not stall the session
            try:
                import bugs
                bugs.capture_exception(vaultlib.find_vault_root(), "guard", exc)
            except Exception:
                pass
            return 0
    command = " ".join(args).strip()
    if not command:
        sys.stdout.write(
            "compass guard: PreToolUse hook on subagent calls. Denies a Bash delete or git discard, a Write "
            "that empties a file or guts a vault document, and an Edit that blanks a long "
            "vault passage. Pass a shell command to see its verdict.\n"
        )
        return 0
    denied, reason = decide("Bash", {"command": command}, _project_root())
    sys.stdout.write((reason if denied else "allow") + "\n")
    return 0
