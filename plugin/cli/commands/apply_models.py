"""`compass apply-models [--dir DIR]` - write the resolved model policy into
the installed Compass agent files.

Rewrites only the `model:` and `effort:` frontmatter lines of the known
Compass agent filenames (`modelslib.AGENT_FILES`); any other file in the
target directory is user-authored and is never read or written. A model
resolving to `inherit` is written as no `model:` line at all - omission
inherits on every host. Files are written LF; a run over an already-applied
tree changes nothing. Default target is the project's `.claude/agents/`.
Exit 0 always (a missing target directory is a warning, not a failure).
"""

import re
import sys
from pathlib import Path

import modelslib
import vaultlib


def _find_key(lines, key):
    """Index of the frontmatter line for `key`, or None."""
    pattern = re.compile(rf"^{key}:")
    for i, line in enumerate(lines):
        if pattern.match(line):
            return i
    return None


def rewrite_frontmatter(text, model, effort):
    """Return `(new_text, error)` with the frontmatter `model:` and `effort:`
    lines set to the resolved values.

    A present line is replaced in place; a missing one is inserted (model
    directly above effort when effort exists, effort directly below model
    when model exists, otherwise at the end of the block). `model == "inherit"`
    removes the model line. Every other byte of frontmatter and body is
    preserved, modulo CRLF normalization to LF.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if not lines or lines[0].strip() != "---":
        return text, "no frontmatter"
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return text, "unterminated frontmatter"

    block = lines[1:end]
    model_idx = _find_key(block, "model")
    if model == "inherit":
        if model_idx is not None:
            del block[model_idx]
    elif model_idx is not None:
        block[model_idx] = f"model: {model}"
    else:
        effort_idx = _find_key(block, "effort")
        block.insert(effort_idx if effort_idx is not None else len(block), f"model: {model}")

    effort_idx = _find_key(block, "effort")
    if effort_idx is not None:
        block[effort_idx] = f"effort: {effort}"
    else:
        model_idx = _find_key(block, "model")
        block.insert(model_idx + 1 if model_idx is not None else len(block), f"effort: {effort}")

    return "\n".join([lines[0]] + block + lines[end:]), None


def _target_dir(args):
    """Resolve the target directory from `--dir` or the project default.

    Returns `(path, error)`; exactly one is None.
    """
    if args and args[0] == "--dir":
        if len(args) != 2:
            return None, "usage: compass apply-models [--dir DIR]"
        return Path(args[1]), None
    if args:
        return None, "usage: compass apply-models [--dir DIR]"
    try:
        vault_root = vaultlib.find_vault_root()
    except Exception:
        return None, "apply-models: no .compass vault found; pass --dir"
    return vault_root.parent / ".claude" / "agents", None


def run(args):
    target, usage_error = _target_dir(args)
    if usage_error:
        sys.stderr.write(usage_error + "\n")
        # Malformed invocations exit 1; a missing vault warns and exits 0,
        # matching the missing-target-dir behavior below.
        return 1 if usage_error.startswith("usage") else 0

    warnings = []
    config, config_warnings = modelslib.load_project_config()
    warnings.extend(config_warnings)

    updated = unchanged = absent = 0
    if not target.is_dir():
        warnings.append(f"apply-models: target dir not found: {target}")
    else:
        for filename in modelslib.AGENT_FILES:
            path = target / filename
            if not path.is_file():
                absent += 1
                continue
            agent = path.stem
            model, effort, _source = modelslib.resolve(agent, config=config, warnings=warnings)
            original = path.read_text(encoding="utf-8")
            new_text, error = rewrite_frontmatter(original, model, effort)
            if error:
                warnings.append(f"apply-models: {filename}: {error}; skipped")
                continue
            if new_text != original:
                vaultlib.write_text_lf(path, new_text)
                updated += 1
                model_note = "model omitted (inherit)" if model == "inherit" else f"model {model}"
                sys.stdout.write(f"updated {filename}: {model_note}, effort {effort}\n")
            else:
                unchanged += 1

    sys.stdout.write(
        f"apply-models: {updated} updated, {unchanged} unchanged, {absent} absent\n"
    )
    for warning in warnings:
        sys.stderr.write(warning + "\n")
    return 0
