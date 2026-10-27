#!/bin/bash
set -euo pipefail
D=/dev/shm/ohm-dedent-link-attribution-20261027/diagnostic-wild
R=/mnt/devbox-scratch/dev-user/ohm-packaged-16-macro-20261027
cd "$D"
python3 -B unpack-vendor.py
mkdir -p cargo-home target shared
export RUSTUP_HOME="$R/rustup" RUSTUP_AUTO_INSTALL=0 CARGO_HOME="$D/cargo-home" CARGO_TARGET_DIR="$D/target" CARGO_BUILD_BUILD_DIR="$D/shared" CARGO_NET_OFFLINE=true
export PATH="/home/dev-user/.cargo/bin:/usr/local/bin:/usr/bin:/bin"
cd "$D/source"
exec cargo +ohm -Zohm-defaults=no build -p wild-linker --bin wild --release --locked --offline -j8 --config 'source.crates-io.replace-with="vendored-sources"' --config "source.vendored-sources.directory=\"$D/vendor\""
