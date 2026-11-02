"""A scriptable stand-in for `claude` whose whole behavior comes from a JSON spec.

Run as `python probe_claude.py <ignored arguments>` with PROBE_SPEC naming a JSON
file. Spec keys, all optional:

    stdin_out    path; the bytes read from stdin are written there
    transcript   {"text": str, "age": seconds}; written as the project's newest
                 transcript under $CLAUDE_CONFIG_DIR/projects/<encoded cwd>/,
                 its modification time set `age` seconds into the past
    grandchild   seconds; a child process that inherits stdout and sleeps that long
    stdout_text  text written to stdout as UTF-8
    stdout_hex   bytes (hex) written to stdout after `stdout_text`
    sleep        seconds to sleep after writing, with stdout flushed
    code         the exit code (default 0)
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def main():
    spec = json.loads(Path(os.environ["PROBE_SPEC"]).read_text(encoding="utf-8"))
    if spec.get("stdin_out"):
        Path(spec["stdin_out"]).write_bytes(sys.stdin.buffer.read())
    transcript = spec.get("transcript")
    if transcript is not None:
        folder = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", os.getcwd())
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "probe.jsonl"
        path.write_bytes(transcript["text"].encode("utf-8"))
        moment = time.time() - transcript.get("age", 0)
        os.utime(path, (moment, moment))
    if spec.get("grandchild"):
        subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({spec['grandchild']})"])
    sys.stdout.buffer.write(spec.get("stdout_text", "").encode("utf-8") + bytes.fromhex(spec.get("stdout_hex", "")))
    sys.stdout.buffer.flush()
    if spec.get("sleep"):
        time.sleep(spec["sleep"])
    sys.exit(spec.get("code", 0))


if __name__ == "__main__":
    main()
