#!/usr/bin/env bash
set -euo pipefail

lab=$(cd "$(dirname "$0")" && pwd -P)
work=$(dirname "$lab")
name=${1:?supply a variant name}
cd "$lab/src"
export CARGO_HOME="$lab/cargo-home" CARGO_TARGET_DIR="$lab/target"
export RUSTC="$work/toolchain/bin/rustc" RUSTDOC="$work/toolchain/bin/rustdoc"
export PATH="$work/toolchain/bin:$PATH"
export CARGO_PROFILE_RELEASE_LTO=thin CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1
export CARGO_PROFILE_RELEASE_OPT_LEVEL=3 CARGO_PROFILE_RELEASE_INCREMENTAL=false
export CARGO_PROFILE_RELEASE_DEBUG=false CARGO_PROFILE_RELEASE_DEBUG_ASSERTIONS=false
export CARGO_PROFILE_RELEASE_OVERFLOW_CHECKS=false
export LIBZ_SYS_STATIC=1 CARGO_TERM_COLOR=never
export CFG_RELEASE=1.99.0-dev CFG_RELEASE_CHANNEL=dev CFG_VER_DESCRIPTION=ohm-1.99.0-17
host=x86_64-unknown-linux-gnu
args=(-Zohm-defaults=no build --target "$host" --release --locked --bin cargo
      --features ohm-defaults,all-static -j8)
if [[ "$name" != base ]]; then args+=(--offline); fi
start=$(date +%s)
printf '%s %s begin\n' "$(date -u --iso-8601=seconds)" "$name" >> "$lab/logs/timeline.log"
printf '%q ' "$work/toolchain/bin/cargo" "${args[@]}" > "$lab/logs/$name.command"
printf '\n' >> "$lab/logs/$name.command"
"$work/toolchain/bin/cargo" "${args[@]}" > "$lab/logs/$name.build.log" 2>&1
cp "$lab/target/$host/release/cargo" "$lab/bin/$name"
chmod a-w "$lab/bin/$name"
{
    "$lab/bin/$name" -Vv
    sha256sum "$lab/bin/$name"
    ldd "$lab/bin/$name"
    elapsed=$(( $(date +%s) - start ))
    printf 'elapsed_seconds=%s\n' "$elapsed"
} > "$lab/logs/$name.binary.txt"
printf '%s %s complete %ss\n' "$(date -u --iso-8601=seconds)" "$name" "$elapsed" >> "$lab/logs/timeline.log"
