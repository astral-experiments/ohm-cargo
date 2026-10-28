#!/usr/bin/env bash
set -euo pipefail

repo=$(git -C "${1:?Ohm Cargo checkout}" rev-parse --show-toplevel)
parent=${2:?parent Git ref}
candidate=${3:?candidate Git ref}
destination=${4:?benchmark binary directory}
mkdir -p "$destination"
destination=$(cd "$destination" && pwd -P)
scratch=$(mktemp -d "${TMPDIR:-/tmp}/ohm-driver-build.XXXXXXXX")
release=a0c7d08c898d3fdff992f2f431dec57d2486add2
compiler=${OHM_DRIVER_TOOLCHAIN:-1.99.1}
export CFG_RELEASE_CHANNEL=dev
export CARGO_TARGET_DIR="$scratch/target"

build() {
    local name=$1 ref=$2
    mkdir "$scratch/src"
    git -C "$repo" archive "$ref" | tar -xf - -C "$scratch/src"
    git -C "$repo" show -s --format='%H%n%h%n%cs' --abbrev=9 "$release" > "$scratch/src/git-commit-info"
    (cd "$scratch/src" && rustup run "$compiler" cargo build --release --locked --bin cargo --features ohm-defaults)
    cp "$scratch/target/release/cargo" "$destination/$name"
    "$destination/$name" -Vv
    mv "$scratch/src" "$scratch/src-$name"
    mv "$scratch/target" "$scratch/target-$name"
}

# Both clean builds see exactly the same absolute source and target paths.
build parent "$parent"
build candidate "$candidate"
sha256sum "$destination/parent" "$destination/candidate"
printf 'Clean build directories are in %s\n' "$scratch"
