set -euo pipefail
D=/home/dev-user/.cache/ohm-ron-consumed-cargo-20261028/rc18-composed
X=/dev/shm/ohm-ron-consumed-v1-20261028
F=/dev/shm/ohm-ron-derive-checked-suite-20261028
H=/home/dev-user/.cache/ohm-rc18-testsuite-20261028
test "$(df -B1 --output=avail /home/dev-user | tail -1)" -gt 20000000000
test "$(sha256sum "$X/target-rc18-composed/debug/cargo" | cut -d' ' -f1)" = 1c328d9c2e078019989b2c677acd666820caa093f4993ca8c606d141cf8574e4
mkdir "$H" "$H/src"
cp -a --reflink=auto "$F/target" "$F/shared" "$F/home" "$H/"
tar -xzf "$D/source.tgz" -C "$H/src"
cd "$H/src"; sha256sum -c "$D/changed-inputs.sha"
export CARGO_TARGET_DIR="$F/target" CARGO_BUILD_BUILD_DIR="$F/shared" CARGO_HOME="$F/home" CARGO_NET_OFFLINE=true
export RUSTUP_HOME="$X/joins/rustup" RUSTUP_TOOLCHAIN=ohm RUSTUP_AUTO_INSTALL=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_PROFILE_DEV_DEBUG=0 CARGO_INCREMENTAL=0 CFG_RELEASE_CHANNEL=dev
unset CARGO_ENCODED_RUSTFLAGS RUSTFLAGS RUSTC_WRAPPER RUSTC_WORKSPACE_WRAPPER CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST
export PATH="/home/dev-user/.cargo/bin:$PATH"
base=(bwrap --die-with-parent --ro-bind / / --dev /dev --proc /proc --ro-bind /dev/shm /dev/shm --tmpfs /tmp --bind "$H" "$F" --chdir "$F/src")
"${base[@]}" -- taskset -c 12-23 cargo +ohm test --locked --offline -p cargo --features ohm-defaults --test testsuite --no-run --message-format=json -j12 > "$D/suite-build.jsonl" 2> "$D/suite-build.err"
exe=$(python3 -c 'import json,sys;print(next(x["executable"] for x in map(json.loads,open(sys.argv[1])) if x.get("executable") and x["target"]["name"]=="testsuite"))' "$D/suite-build.jsonl")
test -n "$exe"
printf '%s\n' "$exe" > "$D/suite.exe"
for spec in freshness::early_native_integration_tests_default_and_fallback freshness::early_native_integration_tests_warm_evidence_and_fallback build_script::generate_good_d_files rustflags::ohm_defaults_reexpand_derive_after_native_input_changes ohm_ready_tests::terminal_cancellation_restores_the_shell_and_stops_descendants; do
  f=${spec##*::}
  # All source/harness/temp targets are a private copy. The Cargo under test is a readonly bind of the exact composed dev binary.
  set +e
  "${base[@]}" --ro-bind "$X/target-rc18-composed/debug/cargo" "$F/target/debug/cargo" -- taskset -c 12-17 strace -qq -ff -s 8192 -e trace=execve -o "$F/$f.exec" "$exe" --exact "$spec" --test-threads=1 --nocapture > "$D/$f.out" 2>&1
  rc=$?
  set -e
  echo "$rc" > "$D/$f.exit"
  printf '%s %s\n' "$spec" "$rc"
done
