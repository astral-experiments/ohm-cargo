#!/usr/bin/env bash
set -euo pipefail

work=$(cd "$(dirname "$0")" && pwd -P)
bench=$(cat "$work/bench-home.path")
cargo="$work/toolchain/bin/cargo"
exec 8>"$work/native-wall-measurement.lock"
flock -x 8
python3 -B "$work/measure.py" --mode dynamorio --ordinary --settle-counter --pairs 8 --seed 611396 \
    --base "$cargo" --candidate "$cargo" --source "$bench/u" --cargo-home "$bench/cargo-native" \
    --target native-wall --result "$work/distributed-control" --endpoints check build test
