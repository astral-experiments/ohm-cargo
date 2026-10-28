set -euo pipefail
D=/home/dev-user/.cache/ohm-ron-consumed-cargo-20261028/rc18-composed
X=/dev/shm/ohm-ron-consumed-v1-20261028
H=/home/dev-user/.cache/ohm-rc18-testsuite-20261028
F=/dev/shm/ohm-ron-derive-checked-suite-20261028
export CARGO_TARGET_DIR="$F/target" CARGO_BUILD_BUILD_DIR="$F/shared" CARGO_HOME="$F/home" CARGO_NET_OFFLINE=true
export RUSTUP_HOME="$X/joins/rustup" RUSTUP_TOOLCHAIN=ohm RUSTUP_AUTO_INSTALL=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_PROFILE_DEV_DEBUG=0 CARGO_INCREMENTAL=0 CFG_RELEASE_CHANNEL=dev PATH="/home/dev-user/.cargo/bin:$PATH"
base=(bwrap --die-with-parent --ro-bind / / --dev /dev --proc /proc --ro-bind /dev/shm /dev/shm --tmpfs /tmp --bind "$H" "$F" --chdir "$F/src")
test "$(df -B1 --output=avail /home/dev-user | tail -1)" -gt 15000000000
"${base[@]}" -- taskset -c 12-23 cargo +ohm test --locked --offline -p cargo --features ohm-defaults --lib --no-run --message-format=json -j12 > "$D/lib-build.jsonl" 2> "$D/lib-build.err"
exe=$(python3 -c 'import json,sys;print(next(x["executable"] for x in map(json.loads,open(sys.argv[1])) if x.get("executable") and x["target"]["kind"]==["lib"]))' "$D/lib-build.jsonl")
printf '%s\n' "$exe" > "$D/lib.exe"
cc -O2 -fPIC -shared "$D/lock-fork.c" -o "$H/lock-probe.so"
shim="$F/lock-probe.so"; log="$F/prune-hooks"
"${base[@]}" --setenv LD_PRELOAD "$shim" --setenv FORK_AUDIT "$log" -- taskset -c 12-15 "$exe" --exact compiler::ohm_thinlto_cache::tests::evicts_oldest_across_namespaces_and_expires_unused_entries --test-threads=1 --nocapture > "$D/lock-fork.out" 2>&1
grep -q '1 passed' "$D/lock-fork.out";grep -q 'child holds inherited fd' "$H/prune-hooks";grep -q 'op=8' "$H/prune-hooks";cp "$H/prune-hooks" "$D/lock-fork.raw"
"${base[@]}" -- taskset -c 12-15 "$exe" compiler::fingerprint::dep_info::tests:: --test-threads=1 --nocapture > "$D/lib-depinfo.out" 2>&1
tail -4 "$D/lock-fork.out"; cat "$D/lock-fork.raw";tail -4 "$D/lib-depinfo.out"
