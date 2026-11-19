"""Tests for the branches of bench/fountain/livecheck.py that only the code
reveals: how `open` builds the Obsidian URL and the VS Code argv, how
`versions` reads `code` output, the ways a vault changes after its baseline
(script added or deleted), re-running `setup`, no-op listing edits, an empty
report, and folders whose names hold spaces and non-ASCII characters.

Adversarial themes: a path that reaches an editor mangled, a decoy that is
reported as a version, a vault edit that leaves temp debris or rewrites more
than it was asked to, and a step log that crashes a report.
"""

import importlib.util
import json
import subprocess
import sys
import types
import urllib.parse
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
LIVECHECK = REPO / "bench" / "fountain" / "livecheck.py"
SCENES_KEY = "fountain.general.numberScenesOnSave"
ODD_NAME = "scratch vault éè 日本"

_spec = importlib.util.spec_from_file_location("livecheck_under_test", LIVECHECK)
livecheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(livecheck)


def run(cwd, *args, timeout=60):
    proc = subprocess.run(
        [sys.executable, str(LIVECHECK), *[str(a) for a in args]],
        capture_output=True,
        cwd=str(cwd),
        timeout=timeout,
    )
    return (
        proc.returncode,
        proc.stdout.decode("utf-8", "replace"),
        proc.stderr.decode("utf-8", "replace"),
    )


@pytest.fixture
def vault(tmp_path):
    target = tmp_path / ODD_NAME
    rc, out, err = run(tmp_path, "setup", target, "--offline")
    assert rc == 0, out + err
    return target


def args_ns(**kw):
    return types.SimpleNamespace(**kw)


@pytest.fixture
def launches(monkeypatch):
    """Record every external launch instead of performing it."""
    calls = {"startfile": [], "run": []}
    monkeypatch.setattr(
        livecheck.os, "startfile", lambda url: calls["startfile"].append(url), raising=False
    )

    def fake_run(argv, **kw):
        calls["run"].append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(livecheck.subprocess, "run", fake_run)
    monkeypatch.setattr(livecheck.shutil, "which", lambda name: "/fake/bin/code")
    return calls


def test_open_obsidian_url_encodes_spaces_and_non_ascii_and_roundtrips(
    vault, launches, monkeypatch
):
    """Adversarial where: a vault path with spaces and non-ASCII characters
    reaches Obsidian with a raw space or raw character in the URL, or with
    an encoding that does not decode back to the exact absolute path."""
    monkeypatch.setattr(livecheck.sys, "platform", "win32")
    livecheck.cmd_open(
        args_ns(dir=str(vault), script="pilot.fountain", editor="obsidian")
    )
    (url,) = launches["startfile"]
    assert url.startswith("obsidian://open?path=")
    encoded = url.split("?path=", 1)[1]
    assert url.isascii() and " " not in url
    assert urllib.parse.unquote(encoded) == str(vault.resolve() / "pilot.fountain")
    assert launches["run"] == []


@pytest.mark.parametrize(
    "platform,opener",
    [("darwin", "open"), ("linux", "xdg-open")],
)
def test_open_obsidian_hands_the_url_to_the_platform_opener(
    vault, launches, monkeypatch, platform, opener
):
    """Adversarial where: the non-Windows branch passes the URL to the wrong
    opener or as several arguments, so a path with a space is split."""
    monkeypatch.setattr(livecheck.sys, "platform", platform)
    livecheck.cmd_open(
        args_ns(dir=str(vault), script="pilot-bom.fountain", editor="obsidian")
    )
    (argv,) = launches["run"]
    assert argv[0] == opener and len(argv) == 2
    assert urllib.parse.unquote(argv[1].split("?path=", 1)[1]) == str(
        vault.resolve() / "pilot-bom.fountain"
    )


def test_open_vscode_passes_folder_then_goto_then_absolute_script_path(vault, launches):
    """Adversarial where: the folder is omitted or placed after `-g`, so VS
    Code opens the file alone and does not read the folder's settings; or a
    path with spaces and non-ASCII is split or relativised."""
    livecheck.cmd_open(
        args_ns(dir=str(vault), script="pilot.fountain", editor="vscode")
    )
    assert launches["run"] == [
        [
            "/fake/bin/code",
            str(vault.resolve()),
            "-g",
            str(vault.resolve() / "pilot.fountain"),
        ]
    ]
    assert launches["startfile"] == []


def test_open_both_launches_each_editor_once(vault, launches, monkeypatch):
    """Adversarial where: `--editor both` launches only one editor or the
    same editor twice."""
    monkeypatch.setattr(livecheck.sys, "platform", "win32")
    livecheck.cmd_open(
        args_ns(dir=str(vault), script="pilot.fountain", editor="both")
    )
    assert len(launches["startfile"]) == 1
    assert len(launches["run"]) == 1 and launches["run"][0][2] == "-g"


def test_open_missing_script_or_missing_code_launches_nothing_it_cannot_finish(
    vault, launches, monkeypatch
):
    """Adversarial where: a script name that is not in the vault, or `code`
    absent for a vscode-only request, still launches an editor before the
    error is raised."""
    with pytest.raises(livecheck.KitError):
        livecheck.cmd_open(
            args_ns(dir=str(vault), script="nope.fountain", editor="both")
        )
    nothing = {"startfile": [], "run": []}
    assert launches == nothing

    monkeypatch.setattr(livecheck.shutil, "which", lambda name: None)
    with pytest.raises(livecheck.KitError, match="code"):
        livecheck.cmd_open(
            args_ns(dir=str(vault), script="pilot.fountain", editor="vscode")
        )
    assert not launches["startfile"] and not launches["run"]


def test_versions_without_code_on_path_reports_not_found_and_succeeds(
    capsys, monkeypatch
):
    """Adversarial where: `code` missing from PATH raises (a traceback or
    KitError) instead of printing `not found` for BetterFountain while still
    printing the bundled Fountain version."""
    monkeypatch.setattr(livecheck.shutil, "which", lambda name: None)
    livecheck.cmd_versions(args_ns())
    out = capsys.readouterr().out
    bundled = json.loads(
        (livecheck.OBSIDIAN_SRC / "fountain" / "manifest.json").read_text("utf-8")
    )["version"]
    assert "Fountain (bundled): %s" % bundled in out
    assert "BetterFountain (VS Code): not found" in out


def test_versions_reads_betterfountain_version_and_survives_empty_listing(
    capsys, monkeypatch
):
    """Adversarial where: the version is taken from the wrong extension line,
    or a `code` that prints nothing (failed run) is reported as a version."""
    monkeypatch.setattr(livecheck.shutil, "which", lambda name: "/fake/code")
    listing = {"text": "ms-python.python@2024.1.0\npiersdeseilligny.betterfountain@1.2.3\n"}
    monkeypatch.setattr(
        livecheck.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout=listing["text"]),
    )
    livecheck.cmd_versions(args_ns())
    assert "BetterFountain (VS Code): 1.2.3" in capsys.readouterr().out

    listing["text"] = ""
    livecheck.cmd_versions(args_ns())
    assert "BetterFountain (VS Code): not found" in capsys.readouterr().out


@pytest.mark.xfail(
    strict=True,
    reason="versions matches any extension line containing 'betterfountain'",
)
def test_versions_ignores_another_extension_whose_id_contains_betterfountain(
    capsys, monkeypatch
):
    """Adversarial where: a different extension with `betterfountain` in its
    id, listed after the real one, is reported as BetterFountain's version."""
    monkeypatch.setattr(livecheck.shutil, "which", lambda name: "/fake/code")
    text = (
        "piersdeseilligny.betterfountain@1.2.3\n"
        "someone.betterfountain-snippets@9.9.9\n"
    )
    monkeypatch.setattr(
        livecheck.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout=text),
    )
    livecheck.cmd_versions(args_ns())
    assert "BetterFountain (VS Code): 1.2.3" in capsys.readouterr().out


def test_versions_with_unreadable_bundled_manifest_prints_unknown(capsys, monkeypatch, tmp_path):
    """Adversarial where: a missing bundled manifest raises instead of
    printing `unknown`."""
    monkeypatch.setattr(livecheck, "OBSIDIAN_SRC", tmp_path)
    monkeypatch.setattr(livecheck.shutil, "which", lambda name: None)
    livecheck.cmd_versions(args_ns())
    assert "Fountain (bundled): unknown" in capsys.readouterr().out


def hash_lines(vault, step):
    rc, out, err = run(vault.parent, "hash", vault, "--step", step)
    assert rc == 0, out + err
    return {
        ln.split(":", 1)[0]: ln
        for ln in out.splitlines()
        if ".fountain:" in ln
    }


def test_hash_reports_a_script_added_after_baseline_as_new_not_changed(vault):
    """Adversarial where: a script added after the baseline is dropped from
    the output, crashes the baseline lookup, or is mislabelled `changed`
    or `unchanged`; and the untouched scripts stay `unchanged`."""
    (vault / "added.fountain").write_bytes(b"INT. NEW - DAY\n")
    lines = hash_lines(vault, "added")
    assert " new " in lines["added.fountain"] + " "
    assert "unchanged" in lines["pilot.fountain"]
    assert "unchanged" in lines["pilot-crlf.fountain"]


def test_hash_reports_a_deleted_script_as_missing_and_logs_it(vault):
    """Adversarial where: a script deleted after the baseline crashes the
    read, or vanishes from the output and the step log so the report cannot
    show the deletion."""
    (vault / "pilot-bom.fountain").unlink()
    lines = hash_lines(vault, "deleted")
    assert "missing" in lines["pilot-bom.fountain"]
    logged = json.loads(
        (vault / ".livecheck" / "steps.jsonl").read_text("utf-8").splitlines()[-1]
    )
    assert logged["scripts"]["pilot-bom.fountain"]["status"] == "missing"
    rc, out, err = run(vault.parent, "report", vault)
    assert rc == 0, out + err
    row = next(ln for ln in out.splitlines() if "pilot-bom.fountain" in ln)
    assert "missing" in row


def test_hash_diff_is_capped_and_survives_bytes_that_are_not_utf8(vault):
    """Adversarial where: a script rewritten with invalid UTF-8 crashes the
    diff, or the diff for a fully rewritten script floods the output past
    the 20-line cap."""
    body = b"".join(b"line %d \xe9\n" % i for i in range(200))
    (vault / "pilot.fountain").write_bytes(body)
    rc, out, err = run(vault.parent, "hash", vault, "--step", "binary")
    assert rc == 0, out + err
    block = [ln for ln in out.splitlines() if ln.startswith("    ")]
    assert 0 < len(block) <= livecheck.DIFF_LINES


def test_hash_without_a_baseline_exits_one_with_a_message_not_a_traceback(tmp_path):
    """Adversarial where: `hash` on a folder that was never set up raises an
    uncaught exception instead of a one-line error and exit 1."""
    rc, out, err = run(tmp_path, "hash", tmp_path, "--step", "x")
    assert rc == 1 and "Traceback" not in err and "setup" in err


def test_setup_rerun_on_its_own_vault_resets_scripts_and_clears_the_step_log(vault):
    """Adversarial where: re-running `setup` on its own vault leaves an
    edited script edited (so a later baseline `unchanged` is false), keeps
    steps from the previous run, or refuses its own folder."""
    (vault / "pilot.fountain").write_bytes(b"edited\n")
    hash_lines(vault, "before-rerun")
    rc, out, err = run(vault.parent, "setup", vault, "--offline")
    assert rc == 0, out + err
    assert not (vault / ".livecheck" / "steps.jsonl").exists()
    lines = hash_lines(vault, "after-rerun")
    assert lines and all("unchanged" in ln for ln in lines.values())


def test_setup_rerun_leaves_foreign_notes_and_reports_extra_scripts_as_new(vault):
    """Adversarial where: re-running `setup` deletes a note or script the
    human added to the scratch vault, or silently absorbs an extra script
    into the baseline so a later change to it reads `unchanged`."""
    (vault / "mine.fountain").write_bytes(b"mine\n")
    (vault / "notes.md").write_text("keep", encoding="utf-8")
    rc, out, err = run(vault.parent, "setup", vault, "--offline")
    assert rc == 0, out + err
    assert (vault / "notes.md").read_text("utf-8") == "keep"
    assert (vault / "mine.fountain").read_bytes() == b"mine\n"
    assert " new " in hash_lines(vault, "x")["mine.fountain"] + " "


def test_listing_remove_of_an_absent_id_keeps_every_entry(vault):
    """Adversarial where: removing an id that is not listed drops another
    entry, duplicates one, or fails instead of printing the unchanged list."""
    listing = vault / ".obsidian" / "community-plugins.json"
    listing.write_text('["fountain","compass-review","xé"]', encoding="utf-8")
    rc, out, err = run(vault.parent, "listing", vault, "--remove", "not-there")
    assert rc == 0, out + err
    assert json.loads(listing.read_text("utf-8")) == ["fountain", "compass-review", "xé"]
    assert json.loads(out) == ["fountain", "compass-review", "xé"]


def test_listing_edits_leave_no_temp_file_beside_the_listing(vault):
    """Adversarial where: the atomic write leaves a `.tmp` sibling in
    `.obsidian/` that Obsidian or a later step then trips over."""
    folder = vault / ".obsidian"
    for flag in (("--add", "extra"), ("--remove", "extra"), ("--remove", "absent")):
        rc, out, err = run(vault.parent, "listing", vault, *flag)
        assert rc == 0, out + err
    assert sorted(p.name for p in folder.iterdir() if p.is_file()) == [
        "community-plugins.json"
    ]


def test_scenes_leaves_no_temp_file_and_refuses_jsonc_without_touching_it(vault):
    """Adversarial where: VS Code settings with a comment (valid for VS Code,
    not for JSON) are overwritten or truncated by the toggle, or the toggle
    leaves a `.tmp` sibling."""
    settings = vault / ".vscode" / "settings.json"
    rc, out, err = run(vault.parent, "scenes", vault, "on")
    assert rc == 0, out + err
    assert [p.name for p in settings.parent.iterdir()] == ["settings.json"]

    original = b'{\n  // keep me\n  "editor.fontSize": 14\n}\n'
    settings.write_bytes(original)
    rc, out, err = run(vault.parent, "scenes", vault, "off")
    assert rc == 1 and settings.read_bytes() == original
    assert sorted(p.name for p in settings.parent.iterdir()) == ["settings.json"]


def test_scenes_keeps_non_ascii_values_of_other_keys(vault):
    """Adversarial where: re-serialising the settings file corrupts a
    non-ASCII value of a neighbouring key."""
    settings = vault / ".vscode" / "settings.json"
    settings.write_text(
        json.dumps({SCENES_KEY: False, "files.exclude": {"é日": True}}),
        encoding="utf-8",
    )
    rc, out, err = run(vault.parent, "scenes", vault, "on")
    assert rc == 0, out + err
    assert json.loads(settings.read_text("utf-8")) == {
        SCENES_KEY: True,
        "files.exclude": {"é日": True},
    }


def test_report_with_zero_steps_is_a_valid_table_with_a_row_per_script(vault):
    """Adversarial where: a report before any `hash` crashes on the empty
    step list, or prints a table whose separator or rows disagree with the
    header column count."""
    rc, out, err = run(vault.parent, "report", vault)
    assert rc == 0, out + err
    lines = out.splitlines()
    assert lines[0] == "| script |"
    assert lines[1] == "|---|"
    rows = [ln for ln in lines[2:] if ln.strip()]
    assert sorted(r.strip("| ") for r in rows) == [
        "pilot-bom.fountain",
        "pilot-crlf.fountain",
        "pilot-no-final-newline.fountain",
        "pilot.fountain",
    ]


@pytest.mark.xfail(
    strict=True,
    reason="report lets json.loads raise on a truncated steps.jsonl line",
)
def test_report_with_a_truncated_last_step_line_exits_one_not_a_traceback(vault):
    """Adversarial where: a step log cut off mid-line (a crash during the
    append) makes `report` die with a traceback instead of an error line."""
    hash_lines(vault, "good")
    with (vault / ".livecheck" / "steps.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"step": "half", "scripts": {')
    rc, out, err = run(vault.parent, "report", vault)
    assert rc == 1 and "Traceback" not in err


def test_cli_commands_work_in_a_folder_whose_name_has_spaces_and_non_ascii(vault):
    """Adversarial where: a vault path with spaces and non-ASCII characters
    breaks any command (unquoted path, ASCII-only stdout) while a plain path
    works."""
    assert " " in str(vault) and not str(vault).isascii()
    assert hash_lines(vault, "baseline")
    for cmd in (("listing", vault), ("report", vault), ("scenes", vault, "off")):
        rc, out, err = run(vault.parent, *cmd)
        assert rc == 0, (cmd, out, err)
