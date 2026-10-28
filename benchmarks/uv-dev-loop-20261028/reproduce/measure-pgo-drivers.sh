#!/usr/bin/env bash
set -euo pipefail

work=$(cd "$(dirname "$0")" && pwd -P)
bench=$(cat "$work/bench-home.path")
build=$(cd "${1:?supply the matched PGO build directory}" && pwd -P)
base="$build/bin/base"
head="$build/bin/guard-stack"
test -x "$base" && test -x "$head"
cd "$work/.."
exec 8>"$work/native-wall-measurement.lock"
flock -x 8
python3 -B "$work/measure.py" --mode dynamorio --settle-counter --pairs 12 --seed 611390 \
    --base "$base" --candidate "$head" --source "$bench/u" --cargo-home "$bench/cargo-native" \
    --target native-wall --result "$work/pgo-confirm" --endpoints check build test | tee "$work/logs/pgo-confirm.log"
python3 -B "$work/measure.py" --mode instructions --settle-counter --pairs 8 --seed 611391 \
    --base "$base" --candidate "$head" --source "$work/uv" --cargo-home "$bench/cargo" \
    --target replica --result "$work/pgo-replica" --endpoints test build check | tee "$work/logs/pgo-replica.log"

# Each comparison below includes the distribution's build and training differences.
for row in 'base 611394' 'guard-stack 611395'; do
    read -r driver seed <<< "$row"
    python3 -B "$work/measure.py" --mode dynamorio --settle-counter --pairs 8 --seed "$seed" \
        --base "$work/toolchain/bin/cargo" --candidate "$build/bin/$driver" \
        --source "$bench/u" --cargo-home "$bench/cargo-native" --target native-wall \
        --result "$work/distributed-pgo-$driver" --endpoints build check test | tee "$work/logs/distributed-pgo-$driver.log"
done

flock -u 8
OHM_BENCH_WORK="$work" OHM_BENCH_DRIVERS="$build/bin" OHM_BENCH_OUTPUT="$work/pgo-ordinary" OHM_BENCH_SEED=611397 \
    bash "$work/rerun-uv-warm.sh" | tee "$work/logs/pgo-ordinary.log"
