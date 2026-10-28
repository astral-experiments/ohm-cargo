#!/usr/bin/env bash
set -euo pipefail

work=$(cd "$(dirname "$0")" && pwd -P)
while ! grep -q '^test: 8 pairs' "$work/logs/std-path-stack-confirm.log"; do sleep 3; done
for expected in 'std-path-confirm 73' 'cumulative-repro-remaining 33' 'cumulative-rc18 49' 'std-path-stack-confirm 49' 'std-path-stack-replica 17'; do
    read -r study lines <<< "$expected"
    test "$(wc -l < "$work/$study/pairs.csv")" -eq "$lines"
done

preflight="$work/native-preflight.csv"
taskset -c 31 python3 "$work/native-host.py" "$preflight" &
monitor=$!
trap 'kill "$monitor" 2>/dev/null || true' EXIT
while ! python3 - "$preflight" <<'PY'
import csv
from pathlib import Path
import sys

path = Path(sys.argv[1])
rows = list(csv.DictReader(path.open())) if path.exists() else []
ready = len(rows) >= 2 and all(
    float(row['cpu0_15_busy_fraction']) < 0.05 and float(row['cpu0_15_iowait_fraction']) < 0.02
    and int(row['dirty_kib']) < 65536 and int(row['writeback_kib']) < 8192
    for row in rows[-2:]
)
sys.exit(0 if ready else 1)
PY
do sleep 3; done
kill "$monitor"
wait "$monitor" || true
trap - EXIT
date -u '+Native preflight passed at %FT%TZ'
exec bash "$work/run-native-cohorts.sh"
