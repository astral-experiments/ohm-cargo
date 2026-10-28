#!/usr/bin/env bash
set -eu
q=$(cd "$(dirname "$0")" && pwd)
while ! python3 - "$q/summary.json" <<'PY'
from pathlib import Path
import json,sys
try:
 r=json.loads(Path(sys.argv[1]).read_text());s=[q['state'] for q in r['cohorts'].values()];ready='rejected' in s or all(x in ['qualified','inconclusive'] for x in s)
except (OSError,ValueError,KeyError):ready=False
sys.exit(0 if ready else 1)
PY
do sleep 6;done
taskset -c 24-25 python3 -I -S "$q/verify.py" > "$q/portable-summary.json"
taskset -c 24-25 python3 -I -S "$q/package.py"
taskset -c 24-25 python3 -I -S "$q/archive-check.py"
