#!/usr/bin/env bash
set -euo pipefail

work=$(cd "$(dirname "$0")" && pwd -P)
cd "$work/.."
bench=$(cat "$work/bench-home.path")
for path in "$work/cumulative-wall" "$work/cumulative-wall-replica" "$work/std-path-stack-wall" "$work/std-path-stack-wall-replica" "$work/native-host.csv"; do
    if [[ -e "$path" ]]; then printf 'Existing results at %s\n' "$path" >&2; exit 1; fi
done
taskset -c 31 python3 "$work/native-host.py" "$work/native-host.csv" &
monitor=$!
trap 'kill "$monitor" 2>/dev/null || true' EXIT

measure_warm() {
    local result=$1 target=$2 source=$3 cargo_home=$4 seed=$5 parent=$6 candidate=$7
    shift 7
    taskset -c 0-15 python3 "$work/measure.py" --mode wall --pairs 48 --seed "$seed" \
        --base "$parent" --candidate "$candidate" \
        --source "$source" --cargo-home "$cargo_home" --target "$target" \
        --result "$work/$result" --endpoints "$@" | tee "$work/logs/$result.log"
}

measure_warm cumulative-wall native-wall "$bench/u" "$bench/cargo-native" 510281 "$work/bin/matched-base" "$work/bin/semver" check build test
measure_warm cumulative-wall-replica replica "$work/uv" "$bench/cargo" 510282 "$work/bin/matched-base" "$work/bin/semver" test build check
for study in cumulative-wall cumulative-wall-replica; do
    taskset -c 0-15 sh "$work/edit-holdout-$study/measure.sh" | tee "$work/logs/edit-$study.log"
done
stack="$work/path-compare/build/bin"
measure_warm std-path-stack-wall native-wall "$bench/u" "$bench/cargo-native" 510383 "$stack/base" "$stack/guard-stack" check build test
measure_warm std-path-stack-wall-replica replica "$work/uv" "$bench/cargo" 510384 "$stack/base" "$stack/guard-stack" test build check
for study in toolchain-wall toolchain-wall-replica; do
    taskset -c 0-15 sh "$work/toolchain_wall.sh" measure "$study" | tee "$work/logs/edit-$study.log"
done
