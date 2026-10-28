#!/usr/bin/env bash
set -euo pipefail

work=$(cd "$(dirname "$0")" && pwd -P)
bench=$(cat "$work/bench-home.path")
cd "$work/.."
for row in 'base 611040' 'guard-stack 611041'; do
    read -r driver seed <<< "$row"
    python3 "$work/measure.py" --mode instructions --settle-counter --pairs 8 --seed "$seed" \
        --base "$work/toolchain/bin/cargo" --candidate "$work/path-compare/build/bin/$driver" \
        --source "$bench/u" --cargo-home "$bench/cargo-native" --target native-wall \
        --result "$work/distributed-$driver" --endpoints build check test | tee "$work/logs/distributed-$driver.log"
done
