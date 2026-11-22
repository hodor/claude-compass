"""Post-build tests for the variant arms: variants.py, the drive path that reads a
variant's repository root, the shipped post-tester patch and the pilot's pairing.

Adversarial themes only the implementation reveals: a worktree registration a
crash left behind, a git identity that does not exist, paths with spaces, the
launch checks reading the parent repository instead of the variant root, a
patch that leaves the build skill with a broken step list, and a replay whose
arm list drops the Compass builds it must pair with.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import human
import launch
import records
import variants
from conftest import OVERHEAD_DIR, REPO_ROOT, run_git
from test_drive import ScriptedHuman, build, messages, read_records, start_entries
from test_pilot import World, go, log_events, seed_pool

PART = "demo"
VARIANT = f"compass-minus-{PART}"
SKILL = "plugin/skills/demo/SKILL.md"


def make_patch(repo, patch_dir, part=PART):
    """`<patch_dir>/<part>.patch`: removes the SKILL line `demo skill` of the `repo` fixture."""
    patch_dir.mkdir(parents=True, exist_ok=True)
    (repo / SKILL).write_text("demo skill\nsecond line\n", encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "two lines")
    (repo / SKILL).write_text("demo skill\n", encoding="utf-8")
    done = subprocess.run(["git", "diff"], cwd=repo, capture_output=True, check=True)
    run_git(repo, "checkout", "--", SKILL)
    (patch_dir / f"{part}.patch").write_bytes(done.stdout)
    return patch_dir


def registered(repo):
    return [
        line
        for line in run_git(repo, "worktree", "list", "--porcelain").splitlines()
        if line.startswith("worktree ")
    ]


def test_make_survives_a_registration_left_behind_by_a_crash_and_stays_repeatable(
    repo, tmp_path
):
    """Adversarial where: a crash (or a manual delete) that removes the worktree
    folder but not its registration makes the next `make` die on git's "missing
    but already registered worktree" refusal; the variant could then never be
    rebuilt from the command line without a hand-run `git worktree prune`."""
    patches = make_patch(repo, tmp_path / "patches")
    vroot = tmp_path / "variant-roots"
    first = variants.make(PART, repo_root=repo, variants_root=vroot, patch_dir=patches)
    shutil.rmtree(first)
    stale = registered(repo)

    again = variants.make(PART, repo_root=repo, variants_root=vroot, patch_dir=patches)

    assert (
        again == first and (again / SKILL).read_text(encoding="utf-8") == "demo skill\n"
    )
    assert len(registered(repo)) == len(stale)


def test_make_commits_with_its_own_identity_when_git_has_none_and_the_parent_signs_commits(
    repo, tmp_path, monkeypatch
):
    """Adversarial where: a commit that relies on the user's git identity fails
    on a machine with no `user.name` (or hangs on a signing key the parent
    repository's config demands) and a commit hook of the parent repository that
    exits non-zero; the variant commit must still be made, under a fixed identity."""
    patches = make_patch(repo, tmp_path / "patches")
    empty_home = tmp_path / "empty-home"
    empty_home.mkdir()
    for name in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(name, str(empty_home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "no-such-config"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
        "EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)
    run_git(repo, "config", "commit.gpgsign", "true")
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)

    tree = variants.make(
        PART,
        repo_root=repo,
        variants_root=tmp_path / "variant-roots",
        patch_dir=patches,
    )

    log = subprocess.run(
        ["git", "log", "-1", "--format=%an|%ae|%cn"],
        cwd=tree,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert log == "compass-variants|variants@compass.invalid|compass-variants"
    assert (tree / SKILL).read_text(encoding="utf-8") == "demo skill\n"


def test_make_and_discard_work_when_every_folder_name_holds_a_space(tmp_path):
    """Adversarial where: an unquoted path in a git invocation or a string-built
    patch path breaks on a space (a Windows user folder such as `Jane Doe`), in
    the repository, the patch folder or the variants root, and the launch check
    must read the variant's own commit."""
    repo = tmp_path / "my repo"
    (repo / "plugin").mkdir(parents=True)
    (repo / "plugin" / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    run_git(repo, "init", "-q")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-q", "-m", "initial")
    (repo / "plugin" / "a.txt").write_text("one\n", encoding="utf-8")
    patches = tmp_path / "my patches"
    patches.mkdir()
    (patches / "p.patch").write_bytes(
        subprocess.run(
            ["git", "diff"], cwd=repo, capture_output=True, check=True
        ).stdout
    )
    run_git(repo, "checkout", "--", "plugin")

    tree = variants.make(
        "p", repo_root=repo, variants_root=tmp_path / "my variants", patch_dir=patches
    )

    assert (tree / "plugin" / "a.txt").read_text(encoding="utf-8") == "one\n"
    assert (
        launch.check_plugin_clean(tree)
        == run_git(tree, "rev-parse", "HEAD")
        != run_git(repo, "rev-parse", "HEAD")
    )
    variants.discard("p", repo_root=repo, variants_root=tmp_path / "my variants")
    assert not tree.exists() and len(registered(repo)) == 1


def pushed(repo, tmp_path):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    run_git(remote, "init", "-q", "--bare")
    run_git(repo, "remote", "add", "origin", str(remote))
    run_git(repo, "push", "-q", "origin", "HEAD")
    return run_git(repo, "rev-parse", "HEAD")


def test_a_variant_build_runs_from_the_variant_root_not_the_parent_repository(
    project, repo, private_root, tmp_path
):
    """Adversarial where: the launch checks and the plugin folder read from the
    parent repository instead of the variant root: the row's `plugin_sha` would
    name the unpatched commit, `--plugin-dir` would load the unpatched plugin,
    and a clean parent would hide a dirty variant."""
    patches = make_patch(repo, tmp_path / "patches")
    remote_head = pushed(repo, tmp_path)
    tree = variants.make(
        PART,
        repo_root=repo,
        variants_root=tmp_path / "variant-roots",
        patch_dir=patches,
    )
    plugin_yaml = "source: somewhere\ncommit: 0000000\n"
    spec = {
        "turns": [
            {
                "text": "setup finished",
                "write": {".compass/meta/plugin.yaml": plugin_yaml},
            },
            {"text": "T2"},
        ]
    }
    who = ScriptedHuman([human.Reply(text="done", done=True)])

    result, cmd = build(project, tree, private_root, tmp_path, spec, who, arm=VARIANT)

    assert result.end == "human-done"
    assert messages(cmd) == ["/compass:setup", "OPENING"]
    setup_argv = start_entries(cmd)[0]["argv"]
    assert setup_argv[setup_argv.index("--plugin-dir") + 1] == str(tree / "plugin")
    row = [r for r in read_records(private_root) if r["role"] == "build"][0]
    assert row["arm"] == VARIANT and row["variant"] == VARIANT
    assert (
        row["plugin_sha"]
        == run_git(tree, "rev-parse", "HEAD")
        != run_git(repo, "rev-parse", "HEAD")
    )
    pinned = (project / ".compass" / "meta" / "plugin.yaml").read_text(encoding="utf-8")
    assert f"commit: {remote_head}" in pinned


def test_a_dirty_variant_plugin_is_refused_even_when_the_parent_repository_is_clean(
    project, repo, private_root, tmp_path
):
    """Adversarial where: `check_plugin_clean` run on the parent repository lets
    a variant whose plugin/ was edited by hand after `make` be measured as the
    committed variant."""
    patches = make_patch(repo, tmp_path / "patches")
    pushed(repo, tmp_path)
    tree = variants.make(
        PART,
        repo_root=repo,
        variants_root=tmp_path / "variant-roots",
        patch_dir=patches,
    )
    (tree / "plugin" / "keep.txt").write_text("edited after make\n", encoding="utf-8")
    who = ScriptedHuman([])

    with pytest.raises(launch.Refused):
        build(project, tree, private_root, tmp_path, {"turns": [{}]}, who, arm=VARIANT)

    assert read_records(private_root) == []
    assert not (project / ".claude" / "settings.local.json").exists()


# the shipped patch

BUILD_SKILL = "plugin/skills/build/SKILL.md"
PATCH = OVERHEAD_DIR / "variants" / "post-tester.patch"


@pytest.fixture(scope="module")
def patched_build_skill(tmp_path_factory):
    """(text before, text after) of the build skill in a clone of HEAD with the patch applied."""
    target = tmp_path_factory.mktemp("patched") / "head"
    done = subprocess.run(
        ["git", "clone", "-q", "--no-hardlinks", str(REPO_ROOT), str(target)],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    before = (target / BUILD_SKILL).read_text(encoding="utf-8")
    applied = subprocess.run(
        ["git", "apply", str(PATCH)], cwd=target, capture_output=True, text=True
    )
    assert applied.returncode == 0, applied.stderr
    return before, (target / BUILD_SKILL).read_text(encoding="utf-8")


def test_the_patched_build_skill_keeps_its_structure_and_only_the_pre_build_tester_instruction(
    patched_build_skill,
):
    """Adversarial where: a patch that drops a numbered step or a code fence
    with the tester sentence (the model then reads a broken workflow), leaves a
    dangling reference to a "post-merge tester" or "post-build mode", or removes
    the pre-build station the variant must keep."""
    before, after = patched_build_skill
    steps = lambda text: re.findall(r"^(\d+)\. \*\*([^*]+)\*\*", text, re.M)  # noqa: E731

    assert steps(after) == steps(before)
    assert [s[0] for s in steps(after)] == [
        str(n) for n in range(1, len(steps(after)) + 1)
    ]
    assert after.count("```") == before.count("```") and after.count("```") % 2 == 0
    assert after.startswith("---\nname: build\n") and after.index(
        "\n---\n", 4
    ) == before.index("\n---\n", 4)
    for phrase in (
        "post-build mode",
        "post-merge tester",
        "spawn the `tester` agent",
        "post-build tester",
        "confirm the fix",
    ):
        assert phrase not in after, phrase
    assert "Spawn the `tester` in pre-build mode" in after
    assert "compass test-checkpoint verify TASK-NNN` against the merged branch" in after
    assert "compass test-checkpoint cycle TASK-NNN --evidence" in after


def pilot_with_variant(world, repo, private_root, projects_root, tmp_path, **kwargs):
    make_patch(repo, repo / "bench" / "overhead" / "variants", part=PART)
    return go(world, repo, private_root, projects_root, **kwargs)


def test_a_replay_naming_compass_and_the_variant_builds_only_the_variant_and_pairs_every_run(
    repo, private_root, projects_root, tmp_path
):
    """Adversarial where: a replay that rebuilds the Compass builds the run log
    already closed (double the cost, and a second set of Compass runs that
    shifts the pairing), or that builds the variant but pairs it with nothing;
    every (topic, run) of the first run must pair once and only the variant
    slots are driven."""
    world = World(private_root)
    ids = seed_pool(world, repo, private_root, 2)
    first = pilot_with_variant(
        world,
        repo,
        private_root,
        projects_root,
        tmp_path,
        topic_ids=ids,
        arms=("compass", "baseline"),
    )
    assert first.status == "complete"
    world.drives.clear()
    report = tmp_path / "report.md"

    second = go(
        world,
        repo,
        private_root,
        projects_root,
        topic_ids=ids,
        arms=("compass", VARIANT),
        report_path=report,
    )

    assert second.status == "complete"
    assert {d["arm"] for d in world.drives} == {VARIANT} and len(world.drives) == 4
    found = second.aggregates["variants"][VARIANT]
    assert found["pairs"] == 4
    assert found["weighted_share"] is not None and found["raw_share"] is not None
    assert VARIANT in report.read_text(encoding="utf-8")


def test_a_variant_build_that_failed_leaves_its_run_unpaired_without_breaking_the_rest(
    repo, private_root, projects_root, tmp_path
):
    """Adversarial where: a crashed variant build counted as a finished pair
    (a zero total against a Compass total), or a missing variant run raising in
    the pairing instead of dropping that one (topic, run); the surviving runs
    still pair and the crash is counted as a failed build."""
    world = World(private_root)
    ids = seed_pool(world, repo, private_root, 2)
    pilot_with_variant(
        world,
        repo,
        private_root,
        projects_root,
        tmp_path,
        topic_ids=ids,
        arms=("compass",),
    )
    world.drives.clear()
    world.exits[3] = 1

    result = go(
        world,
        repo,
        private_root,
        projects_root,
        topic_ids=ids,
        arms=("compass", VARIANT),
    )

    assert result.status == "complete"
    found = result.aggregates["variants"][VARIANT]
    assert found["pairs"] == 3
    assert result.aggregates["failed_builds"] == 1
    assert (
        sum(1 for e in log_events(private_root, "build-closed") if e["arm"] == VARIANT)
        == 4
    )


def test_only_variant_slots_get_a_repo_root_and_it_is_a_patched_worktree_of_head(
    repo, private_root, projects_root, tmp_path
):
    """Adversarial where: `--repo-root` handed to the Compass and baseline
    builds (they would run from a variant) or withheld from the variant (drive
    refuses it, or builds the unpatched Compass); the worktree it names must be
    the HEAD of the repository plus the patch."""
    world = World(private_root)
    ids = seed_pool(world, repo, private_root, 1)
    make_patch(repo, repo / "bench" / "overhead" / "variants", part=PART)
    head = run_git(repo, "rev-parse", "HEAD")

    result = go(
        world,
        repo,
        private_root,
        projects_root,
        topic_ids=ids,
        arms=("compass", VARIANT, "baseline"),
        runs_per_arm=1,
    )

    assert result.status == "complete"
    by_arm = {d["arm"]: d["argv"] for d in world.drives}
    assert set(by_arm) == {"compass", VARIANT, "baseline"}
    assert (
        "--repo-root" not in by_arm["compass"]
        and "--repo-root" not in by_arm["baseline"]
    )
    tree = by_arm[VARIANT][by_arm[VARIANT].index("--repo-root") + 1]
    assert run_git(tree, "rev-parse", "HEAD~1") == head
    assert (Path(tree) / SKILL).read_text(encoding="utf-8") == "demo skill\n"


def test_a_bad_topic_id_is_refused_before_any_variant_worktree_is_made(
    repo, private_root, projects_root, tmp_path
):
    """Adversarial where: the variant worktree made before the topic ids are
    checked leaves a registered worktree of the repository behind a refused run."""
    world = World(private_root)
    seed_pool(world, repo, private_root, 1)
    make_patch(repo, repo / "bench" / "overhead" / "variants", part=PART)
    before = registered(repo)

    with pytest.raises(Exception) as caught:
        go(
            world,
            repo,
            private_root,
            projects_root,
            topic_ids=["t-deadbeef"],
            arms=("compass", VARIANT),
        )

    assert type(caught.value).__name__ == "PilotError"
    assert registered(repo) == before
    assert not (private_root / "variants" / PART).exists()


def test_a_variant_row_carries_no_station_text_beyond_counts(project, private_root):
    """Adversarial where: the variant arm taking a different row path than
    `compass` so a hostile station log (a model name holding text) reaches the
    private record in a variant row as it must not in a compass row."""
    log = project / ".compass" / "meta" / "station-log.jsonl"
    log.parent.mkdir(parents=True)
    hostile = {
        "station": "post-build-tester",
        "model": "claude opus SECRET TEXT",
        "bugs": 2,
        "fails": "x",
    }
    log.write_text(json.dumps(hostile) + "\n", encoding="utf-8")
    events = [
        {
            "type": "result",
            "modelUsage": {"claude-opus-5-5": {"inputTokens": 1, "outputTokens": 2}},
        }
    ]

    variant_row = records.record_session(
        events,
        role="build",
        outcome="done",
        arm=VARIANT,
        private_root=private_root,
        project_dir=project,
    )
    compass_row = records.record_session(
        events,
        role="build",
        outcome="done",
        arm="compass",
        private_root=private_root,
        project_dir=project,
    )

    assert variant_row["stations"] == compass_row["stations"]
    assert "SECRET" not in json.dumps(variant_row)
