#!/usr/bin/env bash
set -euo pipefail

work=$(cd "$(dirname "$0")" && pwd -P)
bench=$(cat "$work/bench-home.path")
cd "$work/.."
taskset -c 31 python3 "$work/native-host.py" "$work/native-preflight-clean-repeat.csv" --until-quiet
taskset -c 31 python3 "$work/native-host.py" "$work/native-host-clean-repeat.csv" &
monitor=$!
trap 'kill "$monitor" 2>/dev/null || true' EXIT
taskset -c 0-15 python3 "$work/measure.py" --mode wall --pairs 48 --seed 510492 \
    --base "$work/bin/matched-base" --candidate "$work/bin/semver" \
    --source "$work/uv" --cargo-home "$bench/cargo" --target replica \
    --result "$work/cumulative-wall-clean-repeat" --endpoints build check test
