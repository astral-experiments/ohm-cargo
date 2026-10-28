set -euo pipefail
D=/home/dev-user/.cache/ohm-ron-consumed-cargo-20261028/rc18-composed
X=/dev/shm/ohm-ron-consumed-v1-20261028
F=/dev/shm/ohm-ron-derive-checked-suite-20261028
H=/home/dev-user/.cache/ohm-rc18-testsuite-20261028
S=/dev/shm/ohm-published-member-h2-20261028/installed17
export CARGO_TARGET_DIR="$F/target" CARGO_BUILD_BUILD_DIR="$F/shared" CARGO_HOME="$F/home" CARGO_NET_OFFLINE=true
export RUSTUP_HOME="$X/joins/rustup" RUSTUP_TOOLCHAIN=ohm RUSTUP_AUTO_INSTALL=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_PROFILE_DEV_DEBUG=0 CARGO_INCREMENTAL=0 CFG_RELEASE_CHANNEL=dev PATH="/home/dev-user/.cargo/bin:$PATH"
exe=$(cat "$D/suite.exe")
for arm in released composed; do
  if [ "$arm" = released ]; then image="$S/bin/cargo"; else image="$X/target-rc18-composed/debug/cargo"; fi
  test ! -e "$D/pty-$arm.out"
  sha256sum "$image" > "$D/pty-$arm.sha"
  set +e
  bwrap --die-with-parent --ro-bind / / --dev /dev --proc /proc --ro-bind /dev/shm /dev/shm --tmpfs /tmp --bind "$H" "$F" --chdir "$F/src" --ro-bind "$image" "$F/target/debug/cargo" -- taskset -c 12-17 "$exe" --exact ohm_ready_tests::terminal_cancellation_restores_the_shell_and_stops_descendants --test-threads=1 --nocapture > "$D/pty-$arm.out" 2>&1
  rc=$?;set -e
  echo "$rc" > "$D/pty-$arm.exit";tail -4 "$D/pty-$arm.out";printf '%s %s\n' "$arm" "$rc"
done
