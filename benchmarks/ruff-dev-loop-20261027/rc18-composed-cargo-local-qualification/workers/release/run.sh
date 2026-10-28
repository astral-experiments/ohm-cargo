set -euo pipefail
D=/home/dev-user/.cache/ohm-ron-consumed-cargo-20261028/rc18-pgo
T=/home/dev-user/.cache/ohm-ron-consumed-cargo-20261028/rc18-composed
X=/dev/shm/ohm-ron-consumed-v1-20261028
S=/dev/shm/ohm-published-member-h2-20261028/installed17
P=/mnt/devbox-scratch/dev-user/ohm-rc18-pgo-qualification-20261028/cargo
HASH=cfc66a7ceee5cad8f8939245d359e4db0d2b6f2abb5760c7cbefa6c9a1d454f8
test "$(sha256sum "$P" | cut -d' ' -f1)" = "$HASH"
if [ "$1" = derive ]; then
  python3 -B "$D/derive/natural-v2.py" v2 rc18-pgo --cargo-sha "$HASH" > "$D/derive-new.out"
  python3 -B "$D/derive/migration-v3.py" official rc18-pgo-from17 --new-sha "$HASH" > "$D/derive-from17.out"
  python3 -B "$D/derive/migration-v3.py" 261 rc18-pgo-from261 --new-sha "$HASH" > "$D/derive-from261.out"
elif [ "$1" = includes ]; then
  python3 -B "$D/migrate.py" > "$D/migrate.out"
elif [ "$1" = dep ]; then
  python3 -B "$D/public-dep.py" > "$D/dep.out"
elif [ "$1" = typed ]; then
  bwrap --die-with-parent --ro-bind / / --dev /dev --proc /proc --ro-bind /dev/shm /dev/shm --tmpfs /tmp --bind "$D/typed" "$D/typed" --ro-bind "$P" "$S/bin/cargo" -- taskset -c 20-23 python3 -B "$D/typed/column-rmeta.py" --sdk "$S" --root "$D/typed/status" > "$D/typed/output" 2> "$D/typed/error"
elif [ "$1" = suite ]; then
  F=/dev/shm/ohm-ron-derive-checked-suite-20261028
  H=/home/dev-user/.cache/ohm-rc18-testsuite-20261028
  mkdir "$D/suite-work" "$D/traces"
  export CARGO_TARGET_DIR="$F/target" CARGO_BUILD_BUILD_DIR="$F/shared" CARGO_HOME="$F/home" CARGO_NET_OFFLINE=true
  export RUSTUP_HOME="$X/joins/rustup" RUSTUP_TOOLCHAIN=ohm RUSTUP_AUTO_INSTALL=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_PROFILE_DEV_DEBUG=0 CARGO_INCREMENTAL=0 CFG_RELEASE_CHANNEL=dev PATH="/home/dev-user/.cargo/bin:$PATH"
  exe=$(cat "$T/suite.exe")
  base=(bwrap --die-with-parent --ro-bind / / --dev /dev --proc /proc --ro-bind /dev/shm /dev/shm --tmpfs /tmp --ro-bind "$H" "$F" --bind "$D/suite-work" "$F/target/tmp" --bind "$D/traces" "$D/traces" --chdir "$F/src" --ro-bind "$P" "$F/target/debug/cargo")
  for spec in freshness::early_native_integration_tests_default_and_fallback freshness::early_native_integration_tests_warm_evidence_and_fallback build_script::generate_good_d_files rustflags::ohm_defaults_reexpand_derive_after_native_input_changes; do
    f=${spec##*::}
    set +e
    "${base[@]}" -- taskset -c 12-17 strace -qq -ff -s 8192 -e trace=execve -o "$D/traces/$f.exec" "$exe" --exact "$spec" --test-threads=1 --nocapture > "$D/$f.out" 2>&1
    rc=$?;set -e;echo "$rc" > "$D/$f.exit"
    if [ "$rc" -ne 0 ]; then cat "$D/$f.out"; exit "$rc"; fi
    grep -q '1 passed; 0 failed' "$D/$f.out"; tail -2 "$D/$f.out"
  done
else exit 2; fi
printf '%s\n' 0 > "$D/$1.exit"
