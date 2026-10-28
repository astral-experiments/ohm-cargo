#!/usr/bin/env bash
set -euo pipefail
base=$(cd "$(dirname "$0")" && pwd)
docker run --rm --pull=never --network=none --read-only --security-opt=no-new-privileges \
 --cap-drop=ALL --cap-add=SETFCAP --cap-add=CHOWN --cap-add=SETUID --cap-add=SETGID \
 --tmpfs /work:rw,nosuid,nodev,mode=1777 --tmpfs /tmp:rw,nosuid,nodev,mode=1777 \
 --mount "type=bind,src=$base/cap-probe.py,dst=/probe.py,readonly" \
 --mount "type=bind,src=$1,dst=/stock,readonly" --mount "type=bind,src=$2,dst=/candidate,readonly" \
 docker.io/library/rust@sha256:8bf7188ae46ad73b801c8d405eedc13ce63a7852b562885743a56890723549a8 python3 -IB /probe.py
