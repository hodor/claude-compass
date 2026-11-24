"""Tests for variants.py: a Compass arm with one harness part removed, built as
a git worktree of HEAD with a committed patch applied.

Interface the tests pin (variants.py)
-------------------------------------
    make(part, *, repo_root, variants_root, patch_dir=None) -> Path
        Creates `<variants_root>/<part>` as a git worktree of the repository's HEAD,
        applies `<patch_dir>/<part>.patch` (default `<repo_root>/bench/overhead/variants`),
        commits it on top of HEAD and returns the worktree path. The worktree is a
        complete repository root: `launch.check_plugin_clean(worktree)` returns its
        HEAD sha. The repository's own work tree, index, HEAD and plugin/ are never
        touched. A failed make leaves no worktree folder and no worktree
        registration behind.
    discard(part, *, repo_root, variants_root) -> None
        Removes the worktree folder and its registration so `make` can run again.
    VariantError
        Raised for a part that is not `[a-z][a-z0-9-]*`, a part with no patch file,
        and a patch that does not apply.

Adversarial themes: a part name that walks out of the variants root, a failed
apply that leaves half a worktree, a worktree taken from the working tree
instead of HEAD, a discard that removes more than its own worktree, and a
shipped patch that no longer applies to HEAD or edits more than the tester spawns.
"""

import subprocess

import pytest

import launch
import variants
from conftest import OVERHEAD_DIR, REPO_ROOT, run_git

SKILL = "plugin/skills/demo/SKILL.md"
OTHER = "plugin/skills/other/NOTES.md"


def sh(cwd, *args):
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


def diff_text(cwd, *args):
    code, out, err = sh(cwd, "diff", *args)
    assert code == 0, err
    return out


def worktrees(repo):
    return [line for line in run_git(repo, "worktree", "list", "--porcelain").splitlines() if line.startswith("worktree ")]


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


@pytest.fixture
def vrepo(tmp_path):
    """A committed repository whose plugin/ holds two files, plus a patch dir
    with `alpha.patch` (edits SKILL) and `beta.patch` (edits OTHER) made by `git diff`."""
    root = tmp_path / "vrepo"
    root.mkdir()
    run_git(root, "init", "-q")
    run_git(root, "config", "core.autocrlf", "false")
    write(root / SKILL, "one\ntwo\nthree\n")
    write(root / OTHER, "alpha\nbeta\n")
    write(root / "README.md", "readme\n")
    run_git(root, "add", ".")
    run_git(root, "commit", "-q", "-m", "initial")
    patches = tmp_path / "patches"
    patches.mkdir()
    for name, path, text in (("alpha", SKILL, "one\nthree\n"), ("beta", OTHER, "alpha\n")):
        write(root / path, text)
        (patches / f"{name}.patch").write_bytes(diff_text(root).encode("utf-8"))
        run_git(root, "checkout", "--", path)
    return root, patches, tmp_path / "variant-roots"


def test_make_yields_a_worktree_one_commit_above_head_that_differs_by_exactly_the_patch(vrepo):
    """Adversarial where: a worktree built from the working tree or a branch tip
    other than HEAD, a patch applied but left uncommitted (so `check_plugin_clean`
    refuses the variant), or extra edits beside the patch; the variant HEAD must
    be the parent HEAD plus one commit whose diff is the patch text itself."""
    root, patches, vroot = vrepo
    parent_head = run_git(root, "rev-parse", "HEAD")

    tree = variants.make("alpha", repo_root=root, variants_root=vroot, patch_dir=patches)

    assert tree == vroot / "alpha"
    assert run_git(tree, "rev-parse", "HEAD~1") == parent_head
    assert diff_text(tree, "HEAD~1", "HEAD") == (patches / "alpha.patch").read_text(encoding="utf-8")
    assert sh(tree, "status", "--porcelain")[1] == ""
    assert sh(tree, "status", "--porcelain", "plugin/")[1] == ""
    assert (tree / SKILL).read_text(encoding="utf-8") == "one\nthree\n"
    assert (tree / OTHER).read_text(encoding="utf-8") == "alpha\nbeta\n"
    assert launch.check_plugin_clean(tree) == run_git(tree, "rev-parse", "HEAD") != parent_head


def test_make_leaves_the_parent_repository_untouched_even_when_it_is_dirty(vrepo):
    """Adversarial where: the variant carrying the parent's uncommitted plugin/
    edits (a build of work nobody committed), or the parent's HEAD, index or work
    tree moving; the parent keeps its dirt and the variant starts from HEAD."""
    root, patches, vroot = vrepo
    write(root / OTHER, "dirty parent edit\n")
    write(root / "plugin" / "untracked.txt", "x\n")
    head = run_git(root, "rev-parse", "HEAD")
    status = sh(root, "status", "--porcelain", "--untracked-files=all")[1]

    tree = variants.make("alpha", repo_root=root, variants_root=vroot, patch_dir=patches)

    assert run_git(root, "rev-parse", "HEAD") == head
    assert sh(root, "status", "--porcelain", "--untracked-files=all")[1] == status
    assert (root / OTHER).read_text(encoding="utf-8") == "dirty parent edit\n"
    assert (tree / OTHER).read_text(encoding="utf-8") == "alpha\nbeta\n"
    assert not (tree / "plugin" / "untracked.txt").exists()


def test_discard_removes_the_worktree_and_its_registration_so_make_can_run_again(vrepo):
    """Adversarial where: a folder deleted but still registered (or a branch left
    behind) makes the next `make` of the same part fail on a name collision, and
    a discard that removes the parent's other worktrees or the variants root."""
    root, patches, vroot = vrepo
    first = variants.make("alpha", repo_root=root, variants_root=vroot, patch_dir=patches)
    second = variants.make("beta", repo_root=root, variants_root=vroot, patch_dir=patches)

    variants.discard("alpha", repo_root=root, variants_root=vroot)

    assert not first.exists()
    assert second.is_dir() and (second / OTHER).read_text(encoding="utf-8") == "alpha\n"
    assert len(worktrees(root)) == 2
    again = variants.make("alpha", repo_root=root, variants_root=vroot, patch_dir=patches)
    assert again == first and (again / SKILL).read_text(encoding="utf-8") == "one\nthree\n"
    variants.discard("alpha", repo_root=root, variants_root=vroot)
    variants.discard("beta", repo_root=root, variants_root=vroot)
    assert len(worktrees(root)) == 1


def test_discarding_a_part_that_was_never_made_removes_nothing_else(vrepo):
    """Adversarial where: a discard of a missing part resolving to the variants
    root itself (or deleting a sibling) when its own folder is absent."""
    root, patches, vroot = vrepo
    kept = variants.make("alpha", repo_root=root, variants_root=vroot, patch_dir=patches)

    try:
        variants.discard("beta", repo_root=root, variants_root=vroot)
    except variants.VariantError:
        pass

    assert kept.is_dir() and (kept / SKILL).is_file()
    assert root.is_dir()


@pytest.mark.parametrize(
    "part",
    ["../patches/alpha", "a/b", "a\\b", "", ".", "..", "Alpha", "al pha", "alpha\n", "-alpha", "1alpha"],
)
def test_make_refuses_a_part_that_is_not_a_plain_lowercase_name(part, vrepo):
    """Adversarial where: a part with separators or dots resolving a worktree
    outside the variants root (`../patches/alpha` would even find the real
    patch), an empty part resolving to the root itself, a newline or space that
    survives a `$`-anchored check; nothing may be created or registered."""
    root, patches, vroot = vrepo
    before = set(patches.parent.rglob("*"))

    with pytest.raises(variants.VariantError):
        variants.make(part, repo_root=root, variants_root=vroot, patch_dir=patches)

    assert not vroot.exists() or list(vroot.iterdir()) == []
    assert set(patches.parent.rglob("*")) - before == set()
    assert len(worktrees(root)) == 1


@pytest.mark.parametrize("part", ["../vrepo", "..", "a/../../vrepo"])
def test_discard_refuses_a_part_that_walks_to_the_repository(part, vrepo):
    """Adversarial where: discard resolving `<variants_root>/<part>` to the
    parent repository and deleting it."""
    root, patches, vroot = vrepo
    vroot.mkdir()

    with pytest.raises(variants.VariantError):
        variants.discard(part, repo_root=root, variants_root=vroot)

    assert (root / SKILL).is_file() and (root / ".git").exists()


def test_a_missing_patch_file_is_refused_and_leaves_nothing_behind(vrepo):
    """Adversarial where: creating the worktree before looking for the patch
    leaves an unpatched copy of the full Compass that a run would then measure
    as the variant."""
    root, patches, vroot = vrepo

    with pytest.raises(variants.VariantError):
        variants.make("gamma", repo_root=root, variants_root=vroot, patch_dir=patches)

    assert not (vroot / "gamma").exists()
    assert len(worktrees(root)) == 1


@pytest.mark.parametrize(
    "name, body",
    [
        ("stale context", "--- a/plugin/skills/demo/SKILL.md\n+++ b/plugin/skills/demo/SKILL.md\n@@ -1,3 +1,2 @@\n nope\n-two\n three\n"),
        ("garbage", "this is not a patch\n"),
        ("empty", ""),
    ],
)
def test_a_patch_that_does_not_apply_is_refused_and_leaves_no_worktree(name, body, vrepo):
    """Adversarial where: a failed `git apply` after `git worktree add` leaves a
    registered, unpatched worktree (or a half-applied one) that the next make
    collides with and a run could measure as the variant; an empty patch would
    otherwise yield a variant identical to the full arm."""
    root, patches, vroot = vrepo
    write(patches / "broken.patch", body)

    with pytest.raises(variants.VariantError):
        variants.make("broken", repo_root=root, variants_root=vroot, patch_dir=patches)

    assert not (vroot / "broken").exists()
    assert len(worktrees(root)) == 1
    good = variants.make("alpha", repo_root=root, variants_root=vroot, patch_dir=patches)
    assert (good / SKILL).read_text(encoding="utf-8") == "one\nthree\n"


# the shipped patch, against this repository's HEAD

PATCH = OVERHEAD_DIR / "variants" / "post-tester.patch"
BUILD_SKILL = "plugin/skills/build/SKILL.md"
AUTOPILOT_SKILL = "plugin/skills/autopilot/SKILL.md"
BUILDER_AGENT = "plugin/templates/agents/builder.md"
TESTER_AGENT = "plugin/templates/agents/tester.md"
METHODOLOGY_SKILL = "plugin/skills/methodology/SKILL.md"
PATCHED = {BUILD_SKILL, AUTOPILOT_SKILL, BUILDER_AGENT, TESTER_AGENT, METHODOLOGY_SKILL}
# Sentences that tell the orchestrator a post-build or post-merge tester runs;
# a variant holding any of them still spawns one.
POST_TESTER_CUES = (
    "post-build mode against its diff",
    "spawn the `tester` agent on the merged state",
    "post-build mode against your diff",
    "tester auto-runs on each",
    "spawning the tester after each merge",
    "and post-build, after the builder finishes",
    "and **post-build**, after the builder finishes",
)


@pytest.fixture(scope="module")
def head_clone(tmp_path_factory):
    """A clone holding exactly the committed HEAD of this repository."""
    target = tmp_path_factory.mktemp("clone") / "head"
    done = subprocess.run(
        ["git", "clone", "-q", "--no-hardlinks", str(REPO_ROOT), str(target)], capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr
    return target


def test_the_post_tester_patch_applies_to_head_and_touches_only_the_tester_text(head_clone):
    """Adversarial where: a patch that no longer applies to HEAD after the
    skills moved, or one that also edits other files, so the variant differs
    from the full arm in more than the tester spawns."""
    check = subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=head_clone, capture_output=True, text=True)
    stat = subprocess.run(["git", "apply", "--numstat", str(PATCH)], cwd=head_clone, capture_output=True, text=True)

    assert check.returncode == 0, check.stderr
    touched = {line.split("\t")[2] for line in stat.stdout.splitlines()}
    assert touched == PATCHED


def test_the_post_tester_patch_leaves_no_cue_to_spawn_a_post_build_tester(tmp_path):
    """Adversarial where: the builder agent, the tester agent or the
    methodology skill still tells the orchestrator a post-build tester runs,
    so a variant build spawns one anyway and the arm measures less than the
    part's removal."""
    target = tmp_path / "head"
    done = subprocess.run(
        ["git", "clone", "-q", "--no-hardlinks", str(REPO_ROOT), str(target)], capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr
    before = {name: (target / name).read_text(encoding="utf-8") for name in PATCHED}
    assert any(cue in text for cue in POST_TESTER_CUES for text in before.values())
    applied = subprocess.run(["git", "apply", str(PATCH)], cwd=target, capture_output=True, text=True)
    assert applied.returncode == 0, applied.stderr
    for name in sorted(PATCHED):
        after = (target / name).read_text(encoding="utf-8")
        for cue in POST_TESTER_CUES:
            assert cue not in after, (name, cue)
    assert "pre-build" in (target / TESTER_AGENT).read_text(encoding="utf-8")
    assert "You never run a test command yourself." in (target / BUILDER_AGENT).read_text(encoding="utf-8")


def test_the_post_tester_patch_removes_the_post_build_and_post_merge_spawns_and_keeps_pre_build(head_clone):
    """Adversarial where: a patch that also removes the pre-build tester spawn
    (the variant would drop a station it must keep), leaves the post-merge
    spawn, or leaves the autopilot line that says the tester always runs."""
    build = head_clone / BUILD_SKILL
    autopilot = head_clone / AUTOPILOT_SKILL
    before_build = build.read_text(encoding="utf-8")
    before_autopilot = autopilot.read_text(encoding="utf-8")
    assert "It always runs" in before_autopilot
    assert "post-build mode against its diff" in before_build
    assert "spawn the `tester` agent on the merged state" in before_build

    done = subprocess.run(["git", "apply", str(PATCH)], cwd=head_clone, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr

    after_build = build.read_text(encoding="utf-8")
    after_autopilot = autopilot.read_text(encoding="utf-8")
    assert "post-build mode against its diff" not in after_build
    assert "spawn the `tester` agent on the merged state" not in after_build
    assert "Spawn the `tester` in pre-build mode" in after_build
    assert "It always runs" not in after_autopilot


def test_making_the_shipped_variant_of_this_repository_leaves_master_plugin_untouched(tmp_path):
    """Adversarial where: the variant built in place (editing this checkout's
    plugin/), or a worktree registration left behind in this repository after
    discard; master's plugin/ must show no diff and no extra worktree remains."""
    vroot = tmp_path / "variant-roots"
    registered = worktrees(REPO_ROOT)
    parent_head = run_git(REPO_ROOT, "rev-parse", "HEAD")

    tree = variants.make("post-tester", repo_root=REPO_ROOT, variants_root=vroot)
    try:
        assert run_git(tree, "rev-parse", "HEAD~1") == parent_head
        assert sh(tree, "status", "--porcelain", "plugin/")[1] == ""
        assert "It always runs" not in (tree / AUTOPILOT_SKILL).read_text(encoding="utf-8")
        assert launch.check_plugin_clean(tree) == run_git(tree, "rev-parse", "HEAD")
    finally:
        variants.discard("post-tester", repo_root=REPO_ROOT, variants_root=vroot)

    assert sh(REPO_ROOT, "diff", "--stat", "HEAD", "--", "plugin/")[1] == ""
    assert worktrees(REPO_ROOT) == registered
    assert not (vroot / "post-tester").exists()
