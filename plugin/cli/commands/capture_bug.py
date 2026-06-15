"""`compass capture-bug "<message>" [--command <name>]` - record a Compass bug.

For an agent or human who notices Compass misbehaving (a CLI quirk, a validate
false positive, a skill bug) and wants it logged for a GitHub issue. The same
message dedups to one local record. CLI internal crashes are captured
automatically; this is the manual entry point. File the queue with
`compass file-bugs`.
"""

import re
import sys

import bugs
import vaultlib


def _version(vault_root):
    path = vault_root / "meta" / "plugin.yaml"
    if path.is_file():
        match = re.search(r"^\s*version:\s*(\S+)", path.read_text(encoding="utf-8"), re.MULTILINE)
        if match:
            return match.group(1)
    return None


def run(args):
    command = "manual"
    if "--command" in args:
        i = args.index("--command")
        command = args[i + 1] if i + 1 < len(args) else "manual"
        message = " ".join(args[:i] + args[i + 2:]).strip()
    else:
        message = " ".join(args).strip()

    if not message:
        sys.stderr.write('usage: compass capture-bug "<message>" [--command <name>]\n')
        return 1

    vault_root = vaultlib.find_vault_root()
    fp = bugs.capture(vault_root, command, message, message, _version(vault_root))
    sys.stdout.write(f"captured bug {fp}: {message}\n")
    sys.stdout.write("file it to GitHub with: compass file-bugs --apply\n")
    return 0
