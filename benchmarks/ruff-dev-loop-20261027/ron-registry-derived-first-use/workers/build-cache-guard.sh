set -euo pipefail
X=/dev/shm/ohm-ron-consumed-v1-20261028
D=/home/dev-user/.cache/ohm-ron-consumed-cargo-20261028
B=/home/dev-user/.cache/ohm-mixed-cargo-release-20261027
[ "$(hostname)" = charlie-ohm-relink-b-1024 ]
[ "$(df -B1 --output=avail /dev/shm | tail -1)" -gt 10000000000 ]
[ "$(sha256sum "$D/known-observer-v1.patch" | cut -d' ' -f1)" = 4350d34f8f950cb3cf1f3ba5038d088cdb24ff741506bc2feee971d0ae209cb2 ]
mkdir "$X/build-derive-guard" "$X/shared-derive-guard" "$X/target-derive-guard"
cd "$X/build-derive-guard"
tar -xzf "$D/source.tgz"
git apply "$D/known-observer-v1.patch"
[ "$(sha256sum src/compiler/mod.rs | cut -d' ' -f1)" = 295600d6d96c989a9a22ff3702bed58ab0a5bece1515392b827dc5258d47e56e ]
sha256sum src/compiler/mod.rs Cargo.lock "$D/source.tgz" "$D/known-observer-v1.patch" > "$D/guard-inputs.sha"
export RUSTUP_HOME="$X/joins/rustup" RUSTUP_AUTO_INSTALL=0 CARGO_HOME="$X/cargo-builder" CARGO_NET_OFFLINE=true
export CARGO_TARGET_DIR="$X/target-derive-guard" CARGO_BUILD_BUILD_DIR="$X/shared-derive-guard"
export CARGO_PROFILE_TEST_DEBUG=0 CARGO_PROFILE_DEV_DEBUG=0 CARGO_INCREMENTAL=0 CFG_RELEASE_CHANNEL=dev PATH="/home/dev-user/.cargo/bin:$PATH"
unset CARGO_ENCODED_RUSTFLAGS RUSTFLAGS RUSTC_WRAPPER RUSTC_WORKSPACE_WRAPPER CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST
if [ -f "$B/src-parent/git-commit-info" ]; then cp "$B/src-parent/git-commit-info" git-commit-info; fi
taskset -c 12-23 cargo +ohm build --locked --offline -p cargo --bin cargo --features ohm-defaults -j12
sha256sum "$X/target-derive-guard/debug/cargo" > "$D/derive-guard.sha"
