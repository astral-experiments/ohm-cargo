#!/usr/bin/env bash
set -euo pipefail

# Run in a clean detached Ohm Cargo checkout at the published #235 commit.
# Supply an absolute STOCK_BIN and a fresh BUILD_ROOT with a seeded cargo-home.
: "${STOCK_BIN:?set STOCK_BIN to the stock Rust 1.99.0 bin directory}"
: "${BUILD_ROOT:?set BUILD_ROOT to an absolute experiment directory}"
evidence=$(cd "$(dirname "$0")" && pwd)
test -d "$BUILD_ROOT/cargo-home"
test ! -e "$BUILD_ROOT/target" && test ! -e "$BUILD_ROOT/artifacts"
test -z "$(git status --porcelain=v1)"
test "$(git rev-parse HEAD)" = fd7a25d7bed7503d628c90879ba265e173343b28
test "$(git write-tree)" = ca7507690099e7523754432ae09abb07b969c962
"$STOCK_BIN/rustc" -V | grep -E '^rustc 1\.99\.0 '
echo '151c473e1a11532946ba9421ab1beeb238f98eb1f8cd4e5f94f9811003abd5a7  Cargo.lock' | sha256sum -c -
mkdir "$BUILD_ROOT/artifacts" "$BUILD_ROOT/tmp"
touch "$BUILD_ROOT/gitconfig"

build() {
    local arm=$1
    env -i HOME="$HOME" USER="$USER" LOGNAME="$USER" SHELL=/usr/bin/zsh \
        LANG=C.UTF-8 LC_ALL=C.UTF-8 PATH="$STOCK_BIN:/usr/bin:/bin" \
        RUSTC="$STOCK_BIN/rustc" RUSTDOC="$STOCK_BIN/rustdoc" \
        CARGO_HOME="$BUILD_ROOT/cargo-home" CARGO_TARGET_DIR="$BUILD_ROOT/target" \
        CARGO_BUILD_JOBS=24 CARGO_INCREMENTAL=0 CARGO_TERM_COLOR=never \
        CARGO_PROFILE_RELEASE_OPT_LEVEL=3 CARGO_PROFILE_RELEASE_LTO=thin \
        CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1 CARGO_PROFILE_RELEASE_DEBUG=1 \
        CARGO_PROFILE_RELEASE_INCREMENTAL=false CARGO_PROFILE_RELEASE_STRIP=none \
        CFG_RELEASE_CHANNEL=dev LIBZ_SYS_STATIC=1 TMPDIR="$BUILD_ROOT/tmp" \
        SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt SSL_CERT_DIR=/usr/lib/ssl/certs \
        GIT_CONFIG_GLOBAL="$BUILD_ROOT/gitconfig" \
        taskset -c 0-23 "$STOCK_BIN/cargo" build --release --locked --offline \
            --bin cargo --features all-static,ohm-defaults -j 24 -v
    cp "$BUILD_ROOT/target/release/cargo" "$BUILD_ROOT/artifacts/$arm.full"
    objcopy --strip-debug "$BUILD_ROOT/artifacts/$arm.full" "$BUILD_ROOT/artifacts/$arm"
    chmod 755 "$BUILD_ROOT/artifacts/$arm" "$BUILD_ROOT/artifacts/$arm.full"
    "$BUILD_ROOT/artifacts/$arm" -Vv > "$BUILD_ROOT/artifacts/$arm.version"
}

build baseline
git apply --index "$evidence/candidate.patch"
test "$(git write-tree)" = d7d6bfacf88bd31caf2591e82e3446f226151afa
build candidate
cmp "$BUILD_ROOT/artifacts/baseline.version" "$BUILD_ROOT/artifacts/candidate.version"
sha256sum "$BUILD_ROOT/artifacts/baseline" "$BUILD_ROOT/artifacts/candidate"
