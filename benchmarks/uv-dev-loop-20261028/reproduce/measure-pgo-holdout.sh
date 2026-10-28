#!/usr/bin/env bash
set -euo pipefail

work=$(cd "$(dirname "$0")" && pwd -P)
cd "$work/.."
export GH_AUTO_ACCOUNT=oss
python3 -B "$work/pgo-holdout/provision.py" "$work/pgo-materials" --oss-repo "$work/ohm-cargo"
python3 -B "$work/pgo-holdout/run.py" --scratch "$work/pgo-confirmation" --materials "$work/pgo-materials" \
    --cargo-repo "$work/ohm-cargo" --toolchain "$work/toolchain" \
    --std-patch "$work/path-compare/std-path-mismatch-guarded.patch" --seed-home "$work/path-compare/build/cargo-home" \
    --arms base guard-stack --jobs 8
bash "$work/measure-pgo-drivers.sh" "$work/pgo-confirmation"
