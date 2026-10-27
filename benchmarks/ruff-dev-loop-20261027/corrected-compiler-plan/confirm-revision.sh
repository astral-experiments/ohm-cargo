#!/usr/bin/env bash
set -euo pipefail
root=/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027
asset="$root/parser-assets/stage2/revision-series"
cd "$asset"
if [[ $# != 2 || $1 != +([0-9a-f]) || $2 != +([0-9a-f]) || ${#1} != 40 || ${#2} != 64 ]]; then
    echo "Expected a complete compiler source commit and release-like driver digest" >&2
    exit 2
fi
name="revision-native-${1:0:12}"
driver="$root/subjects/driver-$2"
logdir="$root/$name-logs"
mkdir "$logdir"
exec >"$logdir/launch.log" 2>&1
trap 'echo "$?" >"$logdir/launch.rc"' EXIT
printf '%s  %s\n' "$2" "$driver" | sha256sum -c -
printf '%s\n' "$1" >"$logdir/source-commit"
printf '%s\n' "$2" >"$logdir/driver-sha256"
python3 revision-series.py "$name" "$driver" "$2" >"$logdir/paired.log" 2>&1
python3 analyze-native.py "$root/results-$name-build" "$root/results-$name-test" >"$logdir/primary-statistics.json"
python3 revision-reference.py "$name" "$driver" "$2" >"$logdir/cold.log" 2>&1
python3 revision-check.py "$name" "$driver" "$2" >"$logdir/check.log" 2>&1
python3 revision-current-cost.py "$name" "$driver" "$2" >"$logdir/cost.log" 2>&1
