set -euo pipefail
X=/dev/shm/ohm-ron-consumed-v1-20261028
D=/home/dev-user/.cache/ohm-ron-consumed-cargo-20261028/rc18-composed
B=/home/dev-user/.cache/ohm-mixed-cargo-release-20261027
I=/mnt/devbox-scratch/dev-user/ohm-ron-consumed-cargo-images-20261028
test "$(hostname)" = charlie-ohm-relink-b-1024
test "$(df -B1 --output=avail /dev/shm | tail -1)" -gt 10000000000
test "$(df -B1 --output=avail "$I" | tail -1)" -gt 10737418240
test "$(sha256sum "$D/source.tgz" | cut -d' ' -f1)" = 8840f1d37fe67cc994270de6af6b73c13d3fd6e9765d104c6c83565044117c36
mkdir "$X/build-rc18-composed" "$X/target-rc18-composed" "$X/shared-rc18-composed"
tar -xzf "$D/source.tgz" -C "$X/build-rc18-composed"
cd "$X/build-rc18-composed"
sha256sum -c "$D/changed-inputs.sha"
if [ -f "$B/src-parent/git-commit-info" ]; then cp "$B/src-parent/git-commit-info" git-commit-info; fi
export RUSTUP_HOME="$X/joins/rustup" RUSTUP_AUTO_INSTALL=0 CARGO_HOME="$X/cargo-builder" CARGO_NET_OFFLINE=true
export CARGO_TARGET_DIR="$X/target-default-guard" CARGO_BUILD_BUILD_DIR="$X/shared-default-guard"
export CARGO_PROFILE_TEST_DEBUG=0 CARGO_PROFILE_DEV_DEBUG=0 CARGO_INCREMENTAL=0 CFG_RELEASE_CHANNEL=dev PATH="/home/dev-user/.cargo/bin:$PATH"
unset CARGO_ENCODED_RUSTFLAGS RUSTFLAGS RUSTC_WRAPPER RUSTC_WORKSPACE_WRAPPER CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST
bwrap --die-with-parent --ro-bind / / --dev /dev --proc /proc --ro-bind /dev/shm /dev/shm --tmpfs /tmp \
 --bind "$X" "$X" --bind "$X/build-rc18-composed" "$X/build-default-guard" \
 --bind "$X/target-rc18-composed" "$X/target-default-guard" --bind "$X/shared-rc18-composed" "$X/shared-default-guard" \
 --chdir "$X/build-default-guard" -- taskset -c 12-23 cargo +ohm build --locked --offline -p cargo --bin cargo --features ohm-defaults -j12
P="$X/target-rc18-composed/debug/cargo"; A="$I/cargo-7181bfa6-pathmatched-dev.zst"
test ! -e "$A"; test "$(df -B1 --output=avail "$I" | tail -1)" -gt 10770972672
zstd -q -T2 -4 "$P" -o "$A"
sha256sum "$P" "$A" "$X/target-default-guard/debug/cargo" "$X/target-default-control/debug/cargo" > "$D/rc18-dev.sha"
zstd -qdc "$A" | sha256sum
cat "$D/rc18-dev.sha"
