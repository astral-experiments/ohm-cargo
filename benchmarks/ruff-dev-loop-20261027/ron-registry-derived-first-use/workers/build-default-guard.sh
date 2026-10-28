set -euo pipefail
X=/dev/shm/ohm-ron-consumed-v1-20261028
D=/home/dev-user/.cache/ohm-ron-consumed-cargo-20261028
B=/home/dev-user/.cache/ohm-mixed-cargo-release-20261027
[ "$(hostname)" = charlie-ohm-relink-b-1024 ]
[ "$(df -B1 --output=avail /dev/shm | tail -1)" -gt 10000000000 ]
[ "$(sha256sum "$D/uncertified-default-v2.patch" | cut -d' ' -f1)" = 434aa578f350ef13f2135add343baa623c87e36020d82b2e91d4daaba8790a49 ]
mkdir "$X/build-default-guard" "$X/shared-default-guard" "$X/target-default-guard"
cd "$X/build-default-guard"
tar -xzf "$D/source.tgz"
git apply "$D/uncertified-default-v2.patch"
[ "$(sha256sum src/compiler/mod.rs | cut -d' ' -f1)" = 8b9b506316854f5e974ae0bf27e2420a3860c4d28ef0bde5df8a1b67f15987a2 ]
sha256sum src/compiler/mod.rs Cargo.lock "$D/source.tgz" "$D/uncertified-default-v2.patch" > "$D/v2-guard-inputs.sha"
export RUSTUP_HOME="$X/joins/rustup" RUSTUP_AUTO_INSTALL=0 CARGO_HOME="$X/cargo-builder" CARGO_NET_OFFLINE=true
export CARGO_TARGET_DIR="$X/target-default-guard" CARGO_BUILD_BUILD_DIR="$X/shared-default-guard"
export CARGO_PROFILE_TEST_DEBUG=0 CARGO_PROFILE_DEV_DEBUG=0 CARGO_INCREMENTAL=0 CFG_RELEASE_CHANNEL=dev PATH="/home/dev-user/.cargo/bin:$PATH"
unset CARGO_ENCODED_RUSTFLAGS RUSTFLAGS RUSTC_WRAPPER RUSTC_WORKSPACE_WRAPPER CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST
if [ -f "$B/src-parent/git-commit-info" ]; then cp "$B/src-parent/git-commit-info" git-commit-info; fi
taskset -c 12-23 cargo +ohm build --locked --offline -p cargo --bin cargo --features ohm-defaults -j12
sha256sum "$X/target-default-guard/debug/cargo" > "$D/default-guard.sha"
