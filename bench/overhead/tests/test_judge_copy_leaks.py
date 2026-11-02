"""Tests for how judge.make_copy hides Compass from the judge, at depths and in
shapes the flat fixture of test_judge.py does not reach.

Adversarial themes: a trace that survives in a nested folder, a `.gitignore`
variant, a link that leads back to the original project, or a file that cannot be
cleaned up, shows the judge the arm that built the project.
"""

import os
import stat
from pathlib import Path

import pytest

import judge
import topic_helpers as helpers
from fake_reply_claude import fake_reply  # noqa: F401  (pytest fixture)
from judge_edge_helpers import all_met_reply, run_judge, seed_goal_list, write_tree

OMITTED = {".git", ".compass", ".claude", "CLAUDE.md"}
SECRET = "SECRET-SPEC-BODY"


def files_under(root):
    return sorted(
        p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
    )


def make_link(link, target, directory=False):
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links cannot be created here")


def test_make_copy_drops_traces_at_every_depth(tmp_path):
    """Adversarial where: a copy that filters only the top level keeps a nested
    .compass folder, a CLAUDE.md in a subfolder, or a .git file (the marker of a
    linked checkout), each of which names the arm."""
    project = tmp_path / "proj"
    write_tree(
        project,
        {
            "keep.txt": "k",
            "pkg/.compass/specs/SPEC-001.md": SECRET,
            "pkg/sub/CLAUDE.md": SECRET,
            "pkg/sub/deep/.claude/settings.json": "{}",
            "pkg/sub/deep/code.py": "print(1)",
            "vendored/.git": "gitdir: ../elsewhere",
            "vendored/lib.py": "x = 1",
            ".hidden/notes.txt": "n",
        },
    )
    (project / "pkg" / "empty").mkdir()
    judge.make_copy(project, tmp_path / "copy")
    copy = tmp_path / "copy"

    assert files_under(copy) == [
        ".hidden/notes.txt",
        "keep.txt",
        "pkg/sub/deep/code.py",
        "vendored/lib.py",
    ]
    assert not [p for p in copy.rglob("*") if p.name in OMITTED]
    assert (copy / "pkg" / "empty").is_dir()


GITIGNORE_ROWS = {
    "double-star claude folder": ["**/.claude/"],
    "CLAUDE.md named": ["CLAUDE.md", "/CLAUDE.md"],
    "mixed case folder": [".CLAUDE/", ".Compass/"],
    "negated and padded": ["!.compass/", "   .compass   "],
    "compass inside a glob": ["*/.compass/*", "docs/compass-notes/"],
    "comment naming compass": ["# Compass local install"],
}


@pytest.mark.parametrize("name", sorted(GITIGNORE_ROWS))
def test_make_copy_removes_every_gitignore_variant_naming_the_arm(tmp_path, name):
    """Adversarial where: a `.gitignore` line that names Compass or Claude Code in
    a spelling the filter does not expect (glob prefix, case, padding, the
    CLAUDE.md file) survives into the copy and tells the judge which arm built it,
    in the top-level file and in a nested one alike."""
    leaking = GITIGNORE_ROWS[name]
    kept = ["node_modules/", "*.pyc", "dist/"]
    body = "\n".join([kept[0], *leaking, *kept[1:]]) + "\n"
    project = write_tree(
        tmp_path / "proj", {".gitignore": body, "web/ui/.gitignore": body}
    )
    judge.make_copy(project, tmp_path / "copy")

    for relative in (".gitignore", "web/ui/.gitignore"):
        text = (tmp_path / "copy" / relative).read_text(encoding="utf-8")
        assert text.splitlines() == kept, relative


def test_make_copy_keeps_the_other_gitignore_lines_byte_for_byte(tmp_path):
    """Adversarial where: rewriting the `.gitignore` through a text codec turns CRLF
    into LF, drops a final line without a newline, loses a non-UTF-8 byte, or
    deletes the line after a removed one."""
    original = b"\xef\xbb\xbfbuild/\r\ncaf\xe9.tmp\r\n.compass/\r\n*.log\r\n.claude\r\nlast-line"
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".gitignore").write_bytes(original)
    judge.make_copy(project, tmp_path / "copy")

    kept = b"\xef\xbb\xbfbuild/\r\ncaf\xe9.tmp\r\n*.log\r\nlast-line"
    assert (tmp_path / "copy" / ".gitignore").read_bytes() == kept
    assert (project / ".gitignore").read_bytes() == original


def test_make_copy_holds_no_link_that_leads_out_of_the_copy(tmp_path):
    """Adversarial where: a symbolic link kept as a link points back at the original
    project (its .compass spec) or at a file outside it, so the judge reads Compass
    files through a path inside its own folder; a looping directory link must not
    hang the copy either."""
    outside = tmp_path / "outside.txt"
    outside.write_text(SECRET, encoding="utf-8")
    project = write_tree(
        tmp_path / "proj",
        {
            ".compass/specs/SPEC-001-x.md": SECRET,
            ".compass/notes/n.md": SECRET,
            "src/app.py": "print(1)",
        },
    )
    make_link(project / "docs.md", project / ".compass" / "specs" / "SPEC-001-x.md")
    make_link(project / "src" / "out.txt", outside)
    make_link(project / "notes", project / ".compass" / "notes", directory=True)
    make_link(project / "src" / "loop", project / "src", directory=True)
    judge.make_copy(project, tmp_path / "copy")
    copy = (tmp_path / "copy").resolve()

    for path in (tmp_path / "copy").rglob("*"):
        reaches = Path(os.path.realpath(path))
        assert reaches == copy or copy in reaches.parents, f"{path} leads to {reaches}"
        if path.is_file():
            assert SECRET not in path.read_text(encoding="utf-8", errors="replace"), (
                path
            )
    assert (tmp_path / "copy" / "src" / "app.py").read_text(
        encoding="utf-8"
    ) == "print(1)"


def test_make_copy_of_a_missing_project_is_refused(tmp_path):
    """Adversarial where: a mistyped or already-discarded project path yields an
    empty copy, and a paid judge session then scores nothing as `not met`."""
    with pytest.raises((judge.Refused, OSError)):
        judge.make_copy(tmp_path / "no-such-project", tmp_path / "copy")


def test_judge_project_refuses_a_missing_project_before_any_session(
    tmp_path, repo, private_root, fake_reply
):
    """Adversarial where: the judge session starts on an empty folder when the
    project path is wrong, costing a session and storing a verdict of nothing met."""
    seed_goal_list(private_root, ["It prints a pitch"])
    fake_reply.reply(all_met_reply(1))
    with pytest.raises((judge.Refused, OSError)):
        run_judge(tmp_path / "gone", repo, private_root, fake_reply)
    assert fake_reply.calls() == []
    assert not list((helpers.topics_dir(private_root) / "verdicts").glob("*.json"))


@pytest.mark.parametrize("ending", ["verdict", "unscoreable", "session-crash"])
def test_judge_project_removes_its_copies_even_when_files_are_read_only(
    tmp_path, repo, private_root, fake_reply, ending
):
    """Adversarial where: a read-only file in the project is copied read-only, the
    scratch folder cannot be deleted on Windows, and full copies of every judged
    project pile up under the private root, on a successful run and on each way a
    run can end early."""
    project = write_tree(
        tmp_path / "proj", {"src/app.py": "print(1)", "docs/readme.txt": "r"}
    )
    for name in ("src/app.py", "docs/readme.txt"):
        os.chmod(project / name, stat.S_IREAD)
    seed_goal_list(private_root, ["It prints a pitch"])
    if ending == "session-crash":
        fake_reply.mode("crash")
    elif ending == "unscoreable":
        fake_reply.reply("no verdict here")
    else:
        fake_reply.reply(all_met_reply(1))
    try:
        try:
            run_judge(project, repo, private_root, fake_reply)
        except (judge.SessionError, judge.InvalidVerdict):
            assert ending != "verdict"
        sessions = private_root / "sessions"
        left = sorted(p.name for p in sessions.iterdir()) if sessions.exists() else []
        assert left == []
    finally:
        for name in ("src/app.py", "docs/readme.txt"):
            os.chmod(project / name, stat.S_IREAD | stat.S_IWRITE)
        for scratch in (private_root / "sessions").glob("judge-*"):
            for path in scratch.rglob("*"):
                if path.is_file():
                    os.chmod(path, stat.S_IREAD | stat.S_IWRITE)


def test_judge_session_can_only_read(tmp_path, repo, private_root, fake_reply):
    """Adversarial where: a judge session granted a shell or a write tool can run
    or edit the project it is scoring, or touch the machine; the tool list on its
    command line must be exactly the reading tools."""
    project = write_tree(tmp_path / "proj", {"src/app.py": "print(1)"})
    seed_goal_list(private_root, ["It prints a pitch"])
    fake_reply.reply(all_met_reply(1))
    run_judge(project, repo, private_root, fake_reply)

    argv = fake_reply.calls()[0]["argv"]
    assert argv[argv.index("--allowedTools") + 1] == "Read,Glob,Grep"
    assert not [
        a for a in argv if a in ("--dangerously-skip-permissions", "bypassPermissions")
    ]
    assert argv.count("--allowedTools") == 1
