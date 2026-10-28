#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
exec taskset -c 6-31 python3 -u work/pgo-holdout/run.py \
  --scratch work/pgo-confirmation-v2 --materials work/pgo-materials \
  --cargo-repo work/ohm-cargo --toolchain work/toolchain \
  --std-patch work/path-compare/std-path-mismatch-guarded.patch \
  --seed-home work/path-compare/build/cargo-home \
  --training-seed work/pgo-confirmation/seed-home \
  --arms base guard-stack --jobs 8
