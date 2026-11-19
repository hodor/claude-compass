#!/usr/bin/env python3
"""Live-check kit for Fountain scripts in Obsidian and VS Code.

Builds a scratch vault, opens scripts in the editors, fingerprints every
script's bytes after each step and reports which steps changed which script.
Standard library only.

    livecheck.py setup <dir> [--offline]
    livecheck.py open <dir> <script> [--editor obsidian|vscode|both]
    livecheck.py scenes <dir> on|off
    livecheck.py hash <dir> --step <name>
    livecheck.py listing <dir> [--add <id> | --remove <id>]
    livecheck.py report <dir>
    livecheck.py versions
"""

import argparse
import datetime
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PILOT = REPO / "plugin" / "cli" / "tests" / "fixtures" / "fountain" / "pilot.fountain"
OBSIDIAN_SRC = REPO / "plugin" / "obsidian"
PLUGIN_IDS = ("fountain", "compass-review")

SAMPLES_COMMIT = "4f109ec"
SAMPLES_URL = (
    "https://raw.githubusercontent.com/piersdeseilligny/betterfountain/"
    + SAMPLES_COMMIT
    + "/src/test/scripts/{name}"
)
SAMPLES = ("big_fish_crlf.fountain", "brick_and_steel_crlf.fountain")

SCENES_KEY = "fountain.general.numberScenesOnSave"
BOM = b"\xef\xbb\xbf"
DIFF_LINES = 20
LINKS_NOTE = (
    "# Link checks\n"
    "\n"
    "[[pilot.fountain]]\n"
    "\n"
    "[[pilot]]\n"
    "\n"
    "![[pilot.fountain]]\n"
    "\n"
    "[[missing.fountain]]\n"
)


class KitError(Exception):
    """A failure to report on one line and exit nonzero."""


def write_atomic(path, data):
    """Write `data` (bytes) to `path` through a temp file in the same folder."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def fingerprint(data):
    """Digest and line-ending facts for a script's bytes. CRLF counts
    `\\r\\n` pairs; LF and CR count the lone `\\n` and lone `\\r` left over."""
    crlf = data.count(b"\r\n")
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "crlf": crlf,
        "lf": data.count(b"\n") - crlf,
        "cr": data.count(b"\r") - crlf,
        "bom": data.startswith(BOM),
        "final_newline": data.endswith(b"\n"),
    }


def yes_no(flag):
    return "yes" if flag else "no"


def livecheck_dir(vault):
    return vault / ".livecheck"


def scripts_in(vault):
    return sorted(p.name for p in vault.glob("*.fountain") if p.is_file())


def load_baseline(vault):
    path = livecheck_dir(vault) / "baseline.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise KitError("no baseline at %s; run setup first" % path)


def visible(text):
    """A line with the invisible bytes spelled out, for the diff."""
    return text.replace("﻿", "<BOM>").replace("\r", "\\r")


def diff_lines(old, new, name):
    old_lines = [visible(x) for x in old.decode("utf-8", "replace").split("\n")]
    new_lines = [visible(x) for x in new.decode("utf-8", "replace").split("\n")]
    diff = difflib.unified_diff(
        old_lines, new_lines, "baseline/" + name, "current/" + name, n=1, lineterm=""
    )
    return list(diff)[:DIFF_LINES]


def download(name):
    url = SAMPLES_URL.format(name=name)
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            return resp.read()
    except (urllib.error.URLError, OSError) as exc:
        raise KitError("could not download %s: %s" % (url, exc))


def to_crlf(data):
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def check_target(vault):
    """A folder that is missing, empty, or already holds `.livecheck/` may be
    set up; any other content is someone else's."""
    if vault.exists() and not vault.is_dir():
        raise KitError("%s is not a folder" % vault)
    if vault.is_dir() and any(vault.iterdir()) and not livecheck_dir(vault).is_dir():
        raise KitError(
            "%s is not empty and has no .livecheck/; refusing to set it up" % vault
        )


def cmd_setup(args):
    vault = Path(args.dir).resolve()
    check_target(vault)
    if not PILOT.is_file():
        raise KitError("pilot fixture missing at %s" % PILOT)
    pilot = PILOT.read_bytes()

    files = {
        "pilot.fountain": pilot,
        "pilot-crlf.fountain": pilot.replace(b"\n", b"\r\n"),
        "pilot-bom.fountain": BOM + pilot,
        "pilot-no-final-newline.fountain": pilot.rstrip(b"\r\n"),
    }
    if not args.offline:
        for name in SAMPLES:
            data = download(name)
            files[name] = data
            files[name.replace("_crlf.fountain", "_kit-crlf.fountain")] = to_crlf(data)

    plugins = {}
    for plugin in PLUGIN_IDS:
        src = OBSIDIAN_SRC / plugin
        shipped = sorted(p for p in src.iterdir() if p.is_file()) if src.is_dir() else []
        if not shipped:
            raise KitError("no bundled files for plugin %s in %s" % (plugin, src))
        plugins[plugin] = shipped

    vault.mkdir(parents=True, exist_ok=True)
    state = livecheck_dir(vault)
    if state.is_dir():
        shutil.rmtree(state)
    (state / "baseline").mkdir(parents=True)

    for name, data in files.items():
        (vault / name).write_bytes(data)
        (state / "baseline" / name).write_bytes(data)
    (vault / "links.md").write_bytes(LINKS_NOTE.encode("utf-8"))

    obsidian = vault / ".obsidian"
    for plugin, shipped in plugins.items():
        dest = obsidian / "plugins" / plugin
        dest.mkdir(parents=True, exist_ok=True)
        for src_file in shipped:
            (dest / src_file.name).write_bytes(src_file.read_bytes())
    write_listing(obsidian / "community-plugins.json", list(PLUGIN_IDS))

    vscode = vault / ".vscode"
    vscode.mkdir(exist_ok=True)
    write_json(vscode / "settings.json", {SCENES_KEY: False})

    baseline = {name: fingerprint(data) for name, data in sorted(files.items())}
    (state / "baseline.json").write_text(
        json.dumps(baseline, indent=2) + "\n", encoding="utf-8"
    )
    print("scratch vault ready at %s (%d scripts)" % (vault, len(files)))


def write_json(path, value):
    write_atomic(path, (json.dumps(value, indent=4) + "\n").encode("utf-8"))


def write_listing(path, ids):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, (json.dumps(ids, indent=2) + "\n").encode("utf-8"))


def launch_obsidian(path):
    url = "obsidian://open?path=" + urllib.parse.quote(str(path), safe="")
    if sys.platform.startswith("win"):
        os.startfile(url)
    elif sys.platform == "darwin":
        subprocess.run(["open", url], check=False)
    else:
        subprocess.run(["xdg-open", url], check=False)
    print("opened in Obsidian: %s" % path)


def launch_vscode(vault, path):
    code = shutil.which("code")
    if not code:
        raise KitError("the `code` command is not on PATH")
    subprocess.run([code, str(vault), "-g", str(path)], check=False)
    print("opened in VS Code: %s" % path)


def cmd_open(args):
    vault = Path(args.dir).resolve()
    script = Path(args.script)
    path = script if script.is_absolute() else vault / script
    if not path.is_file():
        raise KitError("no such script: %s" % path)
    if args.editor in ("vscode", "both") and not shutil.which("code"):
        raise KitError("the `code` command is not on PATH")
    if args.editor in ("obsidian", "both"):
        launch_obsidian(path)
    if args.editor in ("vscode", "both"):
        launch_vscode(vault, path)


def cmd_scenes(args):
    path = Path(args.dir).resolve() / ".vscode" / "settings.json"
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise KitError("%s is missing or does not parse; left unchanged" % path)
    if not isinstance(settings, dict):
        raise KitError("%s is not an object; left unchanged" % path)
    settings[SCENES_KEY] = args.state == "on"
    write_json(path, settings)
    print("%s = %s" % (SCENES_KEY, "true" if args.state == "on" else "false"))


def cmd_hash(args):
    vault = Path(args.dir).resolve()
    baseline = load_baseline(vault)
    names = sorted(set(baseline) | set(scripts_in(vault)))
    record = {}
    blocks = []
    for name in names:
        path = vault / name
        before = baseline.get(name)
        if not path.is_file():
            record[name] = {"status": "missing"}
            blocks.append(["%s: missing" % name])
            continue
        data = path.read_bytes()
        now = fingerprint(data)
        if before is None:
            status = "new"
        else:
            status = "unchanged" if now["sha256"] == before["sha256"] else "changed"
        record[name] = dict(now, status=status)
        header = "%s: %s CRLF %d LF %d CR %d BOM %s final-newline %s" % (
            name,
            status,
            now["crlf"],
            now["lf"],
            now["cr"],
            yes_no(now["bom"]),
            yes_no(now["final_newline"]),
        )
        if before is not None and status == "changed":
            for key, label in (("bom", "BOM"), ("final_newline", "final-newline")):
                if now[key] != before[key]:
                    header += " (%s was %s)" % (label, yes_no(before[key]))
        block = [header]
        if status == "changed":
            old = (livecheck_dir(vault) / "baseline" / name).read_bytes()
            block.extend("    " + line for line in diff_lines(old, data, name))
        blocks.append(block)

    entry = {
        "step": args.step,
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "scripts": record,
    }
    with (livecheck_dir(vault) / "steps.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    print("step %s" % args.step)
    for block in blocks:
        for line in block:
            print(line)


def read_listing(path):
    """The listing as a list of ids; a missing file is an empty list."""
    if not path.exists():
        return []
    try:
        ids = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise KitError("%s does not parse; left unchanged" % path)
    if not isinstance(ids, list):
        raise KitError("%s is not a list; left unchanged" % path)
    return ids


def cmd_listing(args):
    path = Path(args.dir).resolve() / ".obsidian" / "community-plugins.json"
    ids = read_listing(path)
    if args.add is None and args.remove is None:
        print(json.dumps(ids, indent=2))
        return
    if args.add is not None and args.add not in ids:
        ids.append(args.add)
    if args.remove is not None:
        ids = [x for x in ids if x != args.remove]
    write_listing(path, ids)
    print(json.dumps(ids, indent=2))


def cmd_report(args):
    vault = Path(args.dir).resolve()
    baseline = load_baseline(vault)
    path = livecheck_dir(vault) / "steps.jsonl"
    steps = []
    if path.is_file():
        for number, line in enumerate(path.read_text("utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                steps.append(json.loads(line))
            except ValueError:
                raise KitError("%s: line %d is not valid JSON" % (path, number))
    names = sorted(set(baseline) | {n for s in steps for n in s["scripts"]})
    labels = [s["step"] for s in steps]
    print("| script | " + " | ".join(labels) + " |" if labels else "| script |")
    print("|---|" + "---|" * len(labels))
    for name in names:
        cells = [s["scripts"].get(name, {}).get("status", "absent") for s in steps]
        print("| %s | %s |" % (name, " | ".join(cells)) if cells else "| %s |" % name)


def cmd_versions(args):
    manifest = OBSIDIAN_SRC / "fountain" / "manifest.json"
    try:
        version = json.loads(manifest.read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        version = "unknown"
    print("Fountain (bundled): %s" % version)
    code = shutil.which("code")
    found = "not found"
    if code:
        proc = subprocess.run(
            [code, "--list-extensions", "--show-versions"],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in proc.stdout.splitlines():
            if line.strip().lower().startswith("piersdeseilligny.betterfountain@"):
                found = line.strip().split("@")[-1]
    print("BetterFountain (VS Code): %s" % found)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("setup", help="build the scratch vault")
    p.add_argument("dir")
    p.add_argument("--offline", action="store_true", help="skip the sample downloads")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("open", help="open a script in the editors")
    p.add_argument("dir")
    p.add_argument("script")
    p.add_argument("--editor", choices=("obsidian", "vscode", "both"), default="both")
    p.set_defaults(func=cmd_open)

    p = sub.add_parser("scenes", help="set numberScenesOnSave in the folder's settings")
    p.add_argument("dir")
    p.add_argument("state", choices=("on", "off"))
    p.set_defaults(func=cmd_scenes)

    p = sub.add_parser("hash", help="fingerprint every script and log the step")
    p.add_argument("dir")
    p.add_argument("--step", required=True)
    p.set_defaults(func=cmd_hash)

    p = sub.add_parser("listing", help="show or edit community-plugins.json")
    p.add_argument("dir")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--add")
    group.add_argument("--remove")
    p.set_defaults(func=cmd_listing)

    p = sub.add_parser("report", help="a markdown table of every step")
    p.add_argument("dir")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("versions", help="bundled Fountain and installed BetterFountain")
    p.set_defaults(func=cmd_versions)
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except KitError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
