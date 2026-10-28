#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
phase=${1:?supply warm, seal or measure}
study=${2:?supply toolchain-wall or toolchain-wall-replica}
bench_root=$(cat work/bench-home.path)
run_endpoint() {
    seed=$(python3 -B -c 'import json,sys; print(json.load(open(sys.argv[1]))["cohorts"][sys.argv[2]][sys.argv[3]])' work/toolchain-wall-plan.json "$study" "$1")
    python3 -B work/edit_holdout.py "$phase" "$1" --study "$study" \
        --result "work/edit-holdout-$study" --base work/path-compare/build/bin/base \
        --candidate work/path-compare/build/bin/guard-stack --seed "$seed" --workspace \
        --cargo-home "$bench_root/cargo-edit-$study-$1" --mode wall \
        --toolchain-plan work/toolchain-wall-plan.json
}
if [ "$#" = 3 ]; then
    run_endpoint "$3"
else
    for ep in check build test; do run_endpoint "$ep"; done
    if [ "$phase" = measure ]; then
        python3 -B work/edit_holdout_summary.py "work/edit-holdout-$study"
    fi
fi
