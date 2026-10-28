#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
exec taskset -c 0-15 python3 -u work/pgo-holdout/run.py \
  --scratch work/pgo-confirmation-v2 --intermediate-output work/pgo-intermediates \
  --materials work/pgo-materials --cargo-repo work/ohm-cargo --toolchain work/toolchain \
  --std-patch work/path-compare/std-path-mismatch-guarded.patch \
  --seed-home work/path-compare/build/cargo-home \
  --arms unit warnings feature depfile semver --jobs 8
