#!/usr/bin/env bash
set -euo pipefail
arm=$1; rev=$2
case "$arm" in parent253|guardv3|stackv5) ;; *) exit 2;; esac
[[ $rev =~ ^[a-f0-9]{40}$ ]]
d=/home/dev-user/.cache/ohm-ruff-cargo-link-skip-20261027/native-span-observer
h="$d/ruff-sdk-prefetch-corrected"; outputs="$d/ruff-sdk-prefetch-corrected-subjects"
r=/dev/shm/ohm-cargo-scout-sdk-pgo-build-20261027
w=/home/dev-user/code/oss/ohm-cargo-observer-sdk-prefetch-20261027
canonical=/home/dev-user/code/oss/ohm-ruff-pgo-study-20261026
target=/mnt/devbox-scratch/dev-user/ohm-ruff-loop-20261026/pgo-subjects-target
shared=/home/dev-user/.cache/ohm-build-shared
cache=/home/dev-user/.cache/ohm-ruff-loop-20261026
profile=/home/dev-user/.cache/ohm-ruff-empty-lint-scope-20261026/release/receipts/rustc-pgo.profdata
exec 9> "$r/corrected-pgo.lock";flock -x 9
[[ ! -e "$outputs/$arm" ]]; src="$r/corrected-source-$arm"; mkdir "$src"
git -C "$w" cat-file -e "$rev^{commit}"
git -C "$w" archive --format=tar "$rev" | tee >(sha256sum | cut -d' ' -f1 > "$h/$arm.archive-sha256") | tar -xf - -C "$src"
# Use Cargo's official release-tarball commit metadata instead of a different linked checkout on each arm.
# This keeps the displayed version and its parser cache key fixed across the three source trees.
git -C "$w" log -1 --date=short --format='%H%n%h%n%cd' --abbrev=9 b0a4df740b57589ecec3c83e30d5d326ab52a56d > "$src/git-commit-info"
test ! -e "$src/.git"; test -s "$src/git-commit-info"
for f in Cargo.lock build.rs src/compiler/fingerprint/dep_info.rs src/compiler/fingerprint/mod.rs src/compiler/mod.rs src/ops/cargo_worktree/mod.rs;do
    git -C "$w" show "$rev:$f" | cmp -s - "$src/$f"; done
# These are exact Git source bytes. Their materialization times cannot make a different downloaded Cargo subject appear fresh.
touch -- "$src/build.rs" "$src/src/compiler/fingerprint/dep_info.rs" "$src/src/compiler/fingerprint/mod.rs" "$src/src/compiler/mod.rs" "$src/src/ops/cargo_worktree/mod.rs"
{ echo "source $rev";git -C "$w" rev-parse "$rev^{tree}"; sha256sum "$src/git-commit-info" "$src/Cargo.lock" "$src/src/compiler/fingerprint/mod.rs" "$profile"; } > "$h/$arm.inputs"
printf '%s  %s\n' 481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7 "$profile" | sha256sum -c -
export RUSTUP_HOME=/home/dev-user/.cache/ohm-lint-cli-scout-20261026/release14-comparisons/private-rustup
export CARGO_HOME="$cache/registry-home" CARGO_TARGET_DIR="$target" CARGO_BUILD_BUILD_DIR="$shared"
export CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST=all CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST=all
export CARGO_PROFILE_RELEASE_INCREMENTAL=false CFG_RELEASE_CHANNEL=dev
export RUSTFLAGS="-Cprofile-use=$profile -Cllvm-args=-pgo-warn-missing-function=false"
sha256sum "$RUSTUP_HOME/toolchains/ohm/bin/rustc" "$RUSTUP_HOME/toolchains/ohm/bin/cargo" "$RUSTUP_HOME"/toolchains/ohm/lib/librustc_driver*.so >> "$h/$arm.inputs"
taskset -c 0-3 bwrap --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp --bind "$r" "$r" \
  --ro-bind "$cache/registry-home/registry" "$r/registry-ro" --bind "$r/cargo-home" "$CARGO_HOME" \
  --bind "$r/target" "$target" --bind "$r/shared" "$shared" --ro-bind "$src" "$canonical" \
  --chdir "$canonical" -- /home/dev-user/.cargo/bin/cargo +ohm build --release --locked --offline -p cargo --bin cargo --features ohm-defaults -j6
cp -- "$r/target/release/cargo" "$outputs/$arm"; chmod 555 "$outputs/$arm"
sha256sum "$outputs/$arm" |tee "$h/$arm.sha256"; "$outputs/$arm" -Vv |tee "$h/$arm.version"
rg -q 'commit-hash: b0a4df740b57589ecec3c83e30d5d326ab52a56d' "$h/$arm.version"
