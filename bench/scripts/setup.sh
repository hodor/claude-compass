#!/usr/bin/env bash
# One-time setup. Creates a Python venv, installs analyze.py dependencies,
# clones each external benchmark repo into bench/external/, prints the
# per-benchmark invocation hints that downstream scripts need.

set -euo pipefail

BENCH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BENCH_ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

if [[ -f .venv/bin/activate ]]; then
  VENV_ACTIVATE=".venv/bin/activate"
  VENV_PY=".venv/bin/python"
elif [[ -f .venv/Scripts/activate ]]; then
  VENV_ACTIVATE=".venv/Scripts/activate"
  VENV_PY=".venv/Scripts/python.exe"
else
  echo "venv created but no activate script found at .venv/{bin,Scripts}/activate" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$VENV_ACTIVATE"
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -r requirements.txt

mkdir -p external

python3 - <<'PY'
import yaml, pathlib, subprocess
cfg = yaml.safe_load(open('configs/benchmarks.yaml'))
for name, b in cfg['benchmarks'].items():
    target = pathlib.Path('external') / name
    if target.exists():
        print(f'[skip] {name} already cloned at {target}')
        continue
    print(f'[clone] {name} <- {b["repo"]}')
    subprocess.check_call(['git', 'clone', '--depth=1', '--branch', b.get('ref', 'main'), b['repo'], str(target)])
PY

chmod +x agents/compass-agent.sh agents/baseline-agent.sh

cat <<'MSG'

Setup complete.

Next steps:
  1. Inspect external/<benchmark>/README.md for the harness entry point.
  2. Each external benchmark accepts an agent script differently.
     Hand it agents/compass-agent.sh or agents/baseline-agent.sh as the
     agent under test.
  3. Run the smoke subset on each arm before any full run.
  4. After both arms produce results, run:
       python scripts/analyze.py results/<run-dir>

MSG
