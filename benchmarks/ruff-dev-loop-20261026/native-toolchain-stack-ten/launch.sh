#!/usr/bin/env bash
set -euo pipefail
export PATH=/home/dev-user/.cargo/bin:/usr/local/bin:/usr/bin:/bin
study=$HOME/.cache/ohm-ruff-ten-stack-20261026
previous=$HOME/.cache/ohm-ruff-final-stack-20261026
cd "$study"
exec python3 -u replay.py "$1" --state /dev/shm/ohm-ruff-final-stack-20261026 --prior "$previous" --ruff "$HOME/code/oss/ruff-ohm-frontend-holdout-20261026" --ten-cargo "$previous/cargo-stack-ten-pgo" --out "$study/data"
