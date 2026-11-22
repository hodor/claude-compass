"""Compass arms with one harness part removed, each a git worktree of HEAD.

`make(part)` creates `<variants root>/<part>` as a detached worktree of the
repository's HEAD, applies `bench/overhead/variants/<part>.patch` and commits it,
so the worktree is one commit above HEAD and a complete repository root: its
`plugin/` is clean and `launch.check_plugin_clean` returns the variant's commit.
The repository's own work tree, index, HEAD and `plugin/` are never touched. A
part with no patch, an empty patch, or a patch that does not apply to HEAD
raises `VariantError` and leaves no folder and no worktree registration behind.
`discard(part)` removes the worktree and its registration, so `make` can run
again.

The variants root defaults to `~/.compass/overhead/variants`. A part name is
`[a-z][a-z0-9-]*`; the arm a variant builds under is `compass-minus-<part>`.

    python variants.py make PART [--variants-root DIR]    prints the worktree path
    python variants.py discard PART [--variants-root DIR]
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import launch

PART = re.compile(r"[a-z][a-z0-9-]*")
PATCH_DIR_NAME = Path("bench") / "overhead" / "variants"
COMMIT_IDENTITY = (
    "-c", "user.name=compass-variants", "-c", "user.email=variants@compass.invalid", "-c", "commit.gpgsign=false",
)


class VariantError(Exception):
    """A variant could not be made or discarded."""


def default_variants_root():
    return launch.default_private_root() / "variants"


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
        env=launch.git_environment(),
    )


def _check_part(part):
    if not isinstance(part, str) or PART.fullmatch(part) is None:
        raise VariantError("a part name is a lower-case letter followed by lower-case letters, digits and hyphens")


def _target(part, variants_root):
    """`<variants_root>/<part>`, checked to sit directly inside the variants root."""
    _check_part(part)
    root = Path(os.path.realpath(variants_root))
    target = root / part
    if Path(os.path.realpath(target)).parent != root:
        raise VariantError(f"{part} resolves outside the variants root")
    return target


def _registered(repo_root, target):
    """True when git lists `target` as a worktree of the repository."""
    done = _git(repo_root, "worktree", "list", "--porcelain")
    wanted = os.path.normcase(os.path.realpath(target))
    return any(
        line.startswith("worktree ") and os.path.normcase(os.path.realpath(line[len("worktree "):])) == wanted
        for line in done.stdout.splitlines()
    )


def _remove(repo_root, target):
    """Remove the worktree folder and its registration."""
    _git(repo_root, "worktree", "remove", "--force", str(target))
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    _git(repo_root, "worktree", "prune")
    if target.exists():
        raise VariantError(f"the worktree folder {target} could not be removed")


def make(part, *, repo_root, variants_root, patch_dir=None):
    """Create the worktree of `part` and return its path."""
    _check_part(part)
    repo_root = Path(repo_root)
    patch_dir = Path(patch_dir) if patch_dir is not None else repo_root / PATCH_DIR_NAME
    patch = patch_dir / f"{part}.patch"
    if not patch.is_file():
        raise VariantError(f"no patch file {patch}")
    if not patch.read_bytes().strip():
        raise VariantError(f"the patch file {patch} is empty")
    target = _target(part, variants_root)
    if target.exists():
        raise VariantError(f"{target} exists; discard it first")

    target.parent.mkdir(parents=True, exist_ok=True)
    _git(repo_root, "worktree", "prune")
    added = _git(repo_root, "worktree", "add", "--detach", str(target), "HEAD")
    if added.returncode != 0:
        _remove(repo_root, target)
        raise VariantError(f"git cannot create the worktree: {added.stderr.strip()}")
    try:
        applied = _git(target, "apply", "--index", str(patch.resolve()))
        if applied.returncode != 0:
            raise VariantError(f"the patch {patch.name} does not apply to HEAD: {applied.stderr.strip()}")
        committed = _git(
            target, *COMMIT_IDENTITY, "commit", "--no-verify", "-q", "-m", f"Apply the {part} variant patch",
        )
        if committed.returncode != 0:
            raise VariantError(f"git cannot commit the patch: {committed.stderr.strip()}")
    except BaseException:
        _remove(repo_root, target)
        raise
    return target


def discard(part, *, repo_root, variants_root):
    """Remove the worktree of `part` and its registration; nothing else is removed.
    A part with no worktree only has stale registrations pruned."""
    repo_root = Path(repo_root)
    target = _target(part, variants_root)
    if target.exists():
        if not _registered(repo_root, target):
            raise VariantError(f"{target} is not a worktree of {repo_root}; it is left in place")
        _remove(repo_root, target)
    else:
        _git(repo_root, "worktree", "prune")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Make or discard a Compass variant worktree.")
    parser.add_argument("verb", choices=("make", "discard"))
    parser.add_argument("part")
    parser.add_argument("--variants-root", default=None)
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    variants_root = Path(args.variants_root) if args.variants_root else default_variants_root()
    try:
        if args.verb == "make":
            print(make(args.part, repo_root=repo_root, variants_root=variants_root))
        else:
            discard(args.part, repo_root=repo_root, variants_root=variants_root)
    except VariantError as error:
        sys.stderr.write(f"refused: {error}\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
