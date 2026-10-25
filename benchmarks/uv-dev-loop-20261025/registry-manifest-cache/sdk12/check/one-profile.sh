#!/usr/bin/env bash
set -eu
umask 077
active="$study_root/bin/cargo"
state="$sample_root/fixture"
mkdir -p "$sample_root"
test -f "$active"
test ! -L "$active"
cp -p "$active" "$sample_root/original-cargo"
python3 "$evidence_root/dirty_fixture.py" init --state "$state" \
  --source "$study_root/uv/crates/uv/src/lib.rs" --workspace "$study_root/uv" \
  --baseline-target "$study_root/target" --candidate-target "$study_root/unused" \
  --shared-build-dir "$study_root/shared"
cleanup() {
  prior_status=$?
  restore_status=0
  python3 "$evidence_root/dirty_fixture.py" restore --state "$state" || restore_status=$?
  cp -p "$sample_root/original-cargo" "$active" || restore_status=$?
  if [ "$prior_status" -ne 0 ]; then exit "$prior_status"; fi
  exit "$restore_status"
}
trap cleanup EXIT
cp "$selected_cargo" "$active"
chmod --reference="$sample_root/original-cargo" "$active"
python3 "$evidence_root/dirty_fixture.py" prepare --state "$state" \
  --batch "$block_root" --stage measurement --pair "$pair_index" --variant baseline -- \
  taskset -c 0-7 "$active" -Zohm-defaults=yes check --locked --offline -j 8 \
  >"$sample_root/before.stdout" 2>"$sample_root/before.stderr"
cd "$study_root/uv"
LD_PRELOAD="$profiling_root/ohm-valgrind-env.so" \
  "$tracer" -f -qq --seccomp-bpf -v -s 65536 -e trace=execve,execveat \
  -o "$sample_root/exec.trace" taskset -c 0-7 \
  "$profiling_root/valgrind/usr/bin/valgrind.bin" --tool=callgrind \
  --trace-children=no --demangle=no \
  --extra-debuginfo-path="$profiling_root/valgrind/usr/lib/debug" \
  --callgrind-out-file="$sample_root/profile.%p.callgrind" \
  "$active" -Zohm-defaults=yes check --locked --offline -j 8 \
  >"$sample_root/after.stdout" 2>"$sample_root/after.stderr"
