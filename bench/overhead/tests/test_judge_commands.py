"""Tests for how judge.judge_project runs the goal list's shell commands: hung
trees, output size and encoding, stdin, side effects and the environment.

Adversarial themes: a command is code the builder wrote, so it may hang, flood,
emit bytes that are not text, read a terminal, delete files or write beside the
copy; none of that may stall, bloat or corrupt the measurement, or reach the
machine outside the throwaway copy.
"""

import json
import os
import time
from pathlib import Path

import judge
import topic_helpers as helpers
from fake_reply_claude import fake_reply  # noqa: F401  (pytest fixture)
from judge_edge_helpers import (
    all_met_reply,
    python_command,
    run_judge,
    seed_goal_list,
    write_tree,
)

# Seconds the harness may spend on a 1 second timeout: the timeout, the pipe drain
# and slack for process start.
HUNG_TREE_BUDGET = 1 + 5 + 9


def built_project(tmp_path):
    return write_tree(
        tmp_path / "proj", {"src/app.py": "print('pitch')\n", "README.md": "r\n"}
    )


def test_a_hung_process_tree_is_cut_and_its_partial_output_kept(
    tmp_path, repo, private_root, fake_reply
):
    """Adversarial where: a goal command that starts a long-lived child (a server)
    and keeps the output pipe open stalls the judge until the child exits, or loses
    what the command had printed before the cut."""
    spawn = (
        "import subprocess,sys,time;"
        "subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
        "print('listening');sys.stdout.flush();time.sleep(60)"
    )
    seed_goal_list(
        private_root,
        ["It serves", "It exits"],
        {0: python_command(spawn), 1: python_command("print('ok')")},
    )
    fake_reply.reply(all_met_reply(2))

    started = time.monotonic()
    verdict = run_judge(
        built_project(tmp_path), repo, private_root, fake_reply, command_timeout=1
    )
    elapsed = time.monotonic() - started

    assert elapsed < HUNG_TREE_BUDGET + 10
    assert verdict["commands"]["g1"]["timed_out"] is True
    assert verdict["commands"]["g1"]["exit"] is None
    assert "listening" in verdict["commands"]["g1"]["output"]
    assert verdict["commands"]["g2"]["output"].strip() == "ok"


def test_command_output_is_cut_exactly_at_the_limit(
    tmp_path, repo, private_root, fake_reply
):
    """Adversarial where: output of exactly the limit loses a character, output one
    past it is kept whole, or a multi-megabyte flood reaches the stored verdict and
    the judge's prompt unbounded."""
    limit = judge.OUTPUT_LIMIT
    flood = python_command(f"import sys; sys.stdout.write('z'*{limit * 150})")
    seed_goal_list(
        private_root,
        ["at the limit", "one past", "a flood"],
        {
            0: python_command(f"import sys; sys.stdout.write('a'*{limit})"),
            1: python_command(f"import sys; sys.stdout.write('b'*{limit + 1})"),
            2: flood,
        },
    )
    fake_reply.reply(all_met_reply(3))
    verdict = run_judge(built_project(tmp_path), repo, private_root, fake_reply)

    assert verdict["commands"]["g1"]["output"] == "a" * limit
    assert verdict["commands"]["g2"]["output"] == "b" * limit
    assert verdict["commands"]["g3"]["output"] == "z" * limit
    assert len(fake_reply.calls()[0]["stdin"]) < 10 * limit
    assert Path(verdict["file"]).stat().st_size < 10 * limit


def test_command_output_that_is_not_text_still_makes_a_storable_verdict(
    tmp_path, repo, private_root, fake_reply
):
    """Adversarial where: bytes that are not UTF-8, a NUL byte or CRLF line ends in
    a command's output crash the decode, corrupt the stored JSON, or mangle genuine
    UTF-8 text that follows an invalid byte."""
    seed_goal_list(
        private_root,
        ["bytes", "text"],
        {
            0: python_command(
                "import sys; sys.stdout.buffer.write(b'ok\\xff\\xfe\\x00end\\r\\n')"
            ),
            1: python_command(
                "import sys; sys.stdout.buffer.write('café 日本'.encode('utf-8'))"
            ),
        },
    )
    fake_reply.reply(all_met_reply(2))
    verdict = run_judge(built_project(tmp_path), repo, private_root, fake_reply)

    first = verdict["commands"]["g1"]
    assert first["exit"] == 0
    assert first["output"].startswith("ok") and first["output"].rstrip().endswith("end")
    assert verdict["commands"]["g2"]["output"] == "café 日本"
    stored = json.loads(Path(verdict["file"]).read_text(encoding="utf-8"))
    assert stored["commands"] == verdict["commands"]


def test_command_cannot_read_a_terminal_and_stderr_joins_its_output(
    tmp_path, repo, private_root, fake_reply
):
    """Adversarial where: a command that reads stdin (a prompt, `cat`) waits forever
    for a terminal instead of seeing end of input; stderr kept apart from stdout
    leaves the judge without the error text; an exit code is clipped or lost."""
    seed_goal_list(
        private_root,
        ["reads stdin", "fails loudly"],
        {
            0: python_command("import sys; print(repr(sys.stdin.read()))"),
            1: python_command(
                "import sys; sys.stderr.write('traceback text'); sys.exit(255)"
            ),
        },
    )
    fake_reply.reply(all_met_reply(2))
    started = time.monotonic()
    verdict = run_judge(
        built_project(tmp_path), repo, private_root, fake_reply, command_timeout=20
    )

    assert time.monotonic() - started < 20
    assert verdict["commands"]["g1"]["exit"] == 0
    assert verdict["commands"]["g1"]["output"].strip() == "''"
    assert verdict["commands"]["g2"]["exit"] == 255
    assert "traceback text" in verdict["commands"]["g2"]["output"]


def test_a_destructive_command_changes_neither_the_source_nor_the_judges_copy(
    tmp_path, repo, private_root, fake_reply
):
    """Adversarial where: a command that deletes the sources, or writes beside its
    working folder, damages the finished project, or the folder the judge session
    inspects, or leaves files next to the copy after the run."""
    wipe = "import shutil,pathlib; shutil.rmtree('src'); pathlib.Path('../beside.txt').write_text('x')"
    project = built_project(tmp_path)
    seed_goal_list(private_root, ["wipes"], {0: python_command(wipe)})
    fake_reply.reply(all_met_reply(1))
    verdict = run_judge(project, repo, private_root, fake_reply)

    assert verdict["commands"]["g1"]["exit"] == 0
    assert (project / "src" / "app.py").read_text(
        encoding="utf-8"
    ) == "print('pitch')\n"
    assert "src/app.py" in fake_reply.calls()[0]["listing"]
    assert not list(tmp_path.rglob("beside.txt"))
    assert list((private_root / "sessions").iterdir()) == []


def test_goal_commands_see_no_home_folder_of_the_user(
    tmp_path, repo, private_root, fake_reply
):
    """Adversarial where: a command that writes under the home folder (a package
    manager cache, `--user` installs, dotfiles) lands in the real home of the user
    running the measurement, outside the copy; the home and temp folders a command
    sees must lie inside the private root."""
    real_home = tmp_path / "real-home"
    real_home.mkdir()
    show = (
        "import os; print('|'.join(os.environ.get(k, 'unset') "
        "for k in ('HOME', 'USERPROFILE', 'APPDATA', 'XDG_CACHE_HOME')))"
    )
    seed_goal_list(private_root, ["shows its home"], {0: python_command(show)})
    fake_reply.reply(all_met_reply(1))
    parent = {
        **os.environ,
        "HOME": str(real_home),
        "USERPROFILE": str(real_home),
        "APPDATA": str(real_home / "AppData"),
        "XDG_CACHE_HOME": str(real_home / ".cache"),
    }
    verdict = run_judge(
        built_project(tmp_path), repo, private_root, fake_reply, parent_env=parent
    )

    for seen in verdict["commands"]["g1"]["output"].strip().split("|"):
        if seen != "unset":
            assert str(real_home) not in seen, seen
