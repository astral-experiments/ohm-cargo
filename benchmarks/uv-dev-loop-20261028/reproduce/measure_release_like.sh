#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bench_dir=$(cat work/bench-home.path)
while ! rg -q '^\s*Finished ' work/logs/native-warm-test.log; do sleep 5; done
for row in 'base unit test 475868' 'unit warnings check 144088' 'warnings feature check 519449' 'feature depfile build 683195' 'depfile semver check 607447'; do
    read -r parent head endpoint seed <<< "$row"
    while ! rg -q " $head complete " work/release-like/logs/timeline.log; do sleep 5; done
    python3 work/measure.py --base "work/release-like/bin/$parent" --candidate "work/release-like/bin/$head" \
        --result "work/$head-release-like" --target native-wall --source "$bench_dir/u" \
        --cargo-home "$bench_dir/cargo-native" --mode instructions --endpoints "$endpoint" \
        --pairs 8 --seed "$seed" > "work/logs/$head-release-like.log" 2>&1
done
