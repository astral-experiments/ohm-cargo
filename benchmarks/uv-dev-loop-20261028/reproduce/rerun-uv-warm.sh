#!/usr/bin/env bash
set -euo pipefail

# Run against the frozen profile-trained Cargo binaries and warm uv target on this devbox.
work=${OHM_BENCH_WORK:-$(cd "$(dirname "$0")/../work" && pwd -P)}
bench=$(cat "$work/bench-home.path")
build=${OHM_BENCH_DRIVERS:-"$work/$(cat "$work/pgo-final-path.txt")/bin"}
source_dir="$bench/u"
test "$(git -C "$source_dir" rev-parse HEAD)" = c22e6b71933443e9cd299d4b6ac8de035ed4825b
git -C "$source_dir" diff --quiet HEAD --
python3 - "$work/pgo-confirm/protocol.json" "$build" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

frozen = json.loads(Path(sys.argv[1]).read_text())['cargo_sha256']
for arm, name in [('base', 'base'), ('candidate', 'guard-stack')]:
    with (Path(sys.argv[2]) / name).open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != frozen[arm]:
        raise SystemExit(f'{arm} driver does not match the archived SHA-256')
PY

export OHM_BENCH_WORK="$work" OHM_BENCH_ROOT="$bench" OHM_TOOLCHAIN_BIN="$work/toolchain/bin"
exec 8>"$work/native-wall-measurement.lock"
flock -x 8
lock_hash=$(sha256sum "$source_dir/Cargo.lock")
if [[ -n ${OHM_BENCH_OUTPUT:-} ]]; then
    out=$OHM_BENCH_OUTPUT
else
    mkdir -p "$work/reruns"
    out=$(mktemp -d "$work/reruns/plain-cargo.XXXXXXXX")/pairs
fi
printf 'Writing fresh instruction counts to %s\n' "$out"
python3 -B "$work/measure.py" --mode dynamorio --ordinary --settle-counter --pairs 8 \
    --seed "${OHM_BENCH_SEED:-$(date +%s)}" --base "$build/base" --candidate "$build/guard-stack" \
    --source "$source_dir" --cargo-home "$bench/cargo-native" --target native-wall \
    --result "$out" --endpoints check build test
test "$(sha256sum "$source_dir/Cargo.lock")" = "$lock_hash"
