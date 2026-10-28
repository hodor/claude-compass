"""VS Code and Cursor as review surfaces, through the Compass Review extension.

The extension runs in every editor window and claims the requests under
`<folder>/.compass/tmp/review/` for the folders that window has open: a request
whose `surface` is `vscode` or `cursor` becomes a card in the extension's
panel, and the verdict is written beside the request. A request is delivered
by running `<command> <folder>`, which raises the window that holds the folder
or opens one on it. The extension never minimizes the window, so the editor
stays in front after an answer.

An editor is configured for a document when the document sits below a
`.compass` vault and the editor's command is on the PATH. The request's `file`
is relative to the folder holding the vault. The extension is installed once
for the user, from the `.vsix` shipped beside it.

`VSCODE` and `CURSOR` are the two surfaces; they differ in their name and
command. This module is itself the `vscode` surface.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from review_surfaces import foreground

EXTENSION_DIR_NAME = "compass-review"
INSTALL_TIMEOUT = 180
LIST_TIMEOUT = 60


def vault_folder(path):
    """The folder holding the nearest `.compass` at or above `path`, or None."""
    current = Path(path).resolve()
    for candidate in (current, *current.parents):
        if candidate.name == ".compass" and candidate.is_dir():
            return candidate.parent
    return None


def shipped_extension_dir(shipped_root=None):
    """The folder holding the extension and its `.vsix`: `vscode/compass-review`
    under `shipped_root` (an install's `.claude/`), else beside the CLI
    (`plugin/vscode/compass-review` in the source tree, `.claude/vscode/...`
    in an install)."""
    base = Path(shipped_root) if shipped_root else Path(__file__).resolve().parents[2]
    return base / "vscode" / EXTENSION_DIR_NAME


def shipped_vsix(shipped_root=None):
    """The newest `.vsix` in the extension folder, or None."""
    packed = sorted(shipped_extension_dir(shipped_root).glob("*.vsix"))
    return packed[-1] if packed else None


def extension_id(shipped_root=None):
    """The id an editor lists the extension under: lower-cased
    `publisher.name` from the shipped `package.json`, or None when it cannot
    be read."""
    try:
        package = json.loads((shipped_extension_dir(shipped_root) / "package.json").read_text(encoding="utf-8"))
        return f"{package['publisher']}.{package['name']}".lower()
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _no_console():
    """Popen/run flags that keep a console window from flashing when the
    editor's `.cmd` shim starts on Windows."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def _command_line(command, folder):
    """What to run to hand `folder` to the editor: an argument list, except for
    a Windows `.cmd` or `.bat` shim, where it is a command line with the folder
    in double quotes so cmd.exe reads `&`, `^` and the like as part of the
    name."""
    if sys.platform == "win32" and command.lower().endswith((".cmd", ".bat")):
        quoted = folder + "\\" if folder.endswith("\\") else folder
        return f'{subprocess.list2cmdline([command])} "{quoted}"'
    return [command, folder]


def _first_line(*texts):
    for text in texts:
        for line in (text or "").splitlines():
            if line.strip():
                return line.strip()[:200]
    return "no output"


class Editor:
    """One editor of the VS Code family as a review surface."""

    def __init__(self, name, command, label, executables):
        self.NAME = name
        self.command = command
        self.label = label
        self.executables = executables

    def configuration(self, document):
        """`({"root", "command"}, None)` when `document` can be reviewed in
        this editor, else `(None, reason)` naming what is missing. `root` is
        the folder holding the vault; `command` is the editor's executable."""
        root = vault_folder(document)
        if root is None:
            return None, f"no .compass vault contains {document}"
        command = shutil.which(self.command)
        if command is None:
            return None, f"`{self.command}` is not on the PATH, so {self.label} cannot be opened"
        return {"root": root, "command": command}, None

    def deliver(self, context, request_path):
        """Raise the editor window holding the folder, or open one on it. The
        extension in that window finds the request on its own."""
        subprocess.Popen(
            _command_line(context["command"], str(context["root"])),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=_no_console(),
        )

    def resolve(self, request, compass_vault):
        """The document `request` names: its `file` under the folder holding
        `compass_vault`, or None."""
        root = vault_folder(compass_vault)
        if root is None or not isinstance(request.get("file"), str):
            return None
        return root / request["file"]

    def has_focus(self):
        """True when the foreground window belongs to this editor. Windows
        only; elsewhere False."""
        return foreground.executable() in self.executables

    def install(self, compass_vault, shipped_root=None):
        """Install the shipped `.vsix` into the editor with
        `<command> --install-extension`. Returns one line saying what was
        done or why nothing was; never raises."""
        command = shutil.which(self.command)
        if command is None:
            return f"skipped: `{self.command}` is not on the PATH"
        vsix = shipped_vsix(shipped_root)
        if vsix is None:
            return f"skipped: no .vsix is shipped in {shipped_extension_dir(shipped_root)}"
        try:
            done = subprocess.run(
                [command, "--install-extension", str(vsix), "--force"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=INSTALL_TIMEOUT, check=False, creationflags=_no_console(),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return f"failed: `{self.command}` could not install {vsix.name} ({exc})"
        if done.returncode != 0:
            return f"failed: `{self.command}` exited {done.returncode}: {_first_line(done.stderr, done.stdout)}"
        return f"installed {vsix.name} with `{self.command}`"

    def doctor(self, compass_vault):
        """`(status, detail, fix)` for reviewing in this editor. An editor
        whose command is not on the PATH is OK (reviews go elsewhere); an
        extension the editor does not list, or a listing that cannot be read,
        WARNs."""
        command = shutil.which(self.command)
        if command is None:
            return "OK", f"`{self.command}` is not on the PATH; reviews do not open in {self.label}", None
        wanted = extension_id()
        if wanted is None:
            return "WARN", "the shipped Compass Review extension has no readable package.json", "run /compass:update"
        try:
            listed = subprocess.run(
                [command, "--list-extensions"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=LIST_TIMEOUT, check=False, creationflags=_no_console(),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return "WARN", f"`{self.command} --list-extensions` could not run ({exc})", f"check that `{self.command}` starts"
        if listed.returncode != 0:
            return ("WARN", f"`{self.command} --list-extensions` exited {listed.returncode}: "
                    f"{_first_line(listed.stderr, listed.stdout)}", f"check that `{self.command}` starts")
        ids = {line.strip().split("@")[0].lower() for line in listed.stdout.splitlines() if line.strip()}
        if wanted not in ids:
            return ("WARN", f"the Compass Review extension is not installed in {self.label}",
                    "run `compass review --install`")
        return "OK", f"the Compass Review extension is installed in {self.label}", None


VSCODE = Editor("vscode", "code", "VS Code", ("code.exe", "code - insiders.exe"))
CURSOR = Editor("cursor", "cursor", "Cursor", ("cursor.exe",))

NAME = VSCODE.NAME
configuration = VSCODE.configuration
deliver = VSCODE.deliver
resolve = VSCODE.resolve
has_focus = VSCODE.has_focus
install = VSCODE.install
doctor = VSCODE.doctor
