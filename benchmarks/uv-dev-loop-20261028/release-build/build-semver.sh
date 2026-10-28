#!/usr/bin/env bash
set -euo pipefail
lab=$(cd "$(dirname "$0")" && pwd -P)
cd "$lab/src"
grep -q 'depfile complete' "$lab/logs/timeline.log"
file="$lab/patches/lock-version-req.patch"
patch --batch --forward --fuzz=0 --dry-run -p1 < "$file" > "$lab/logs/semver.patch.log"
patch --batch --forward --fuzz=0 -p1 < "$file" >> "$lab/logs/semver.patch.log"
sha256sum -c "$lab/source-lock.sha256"
xargs -d '\n' sha256sum < "$lab/affected-files.txt" > "$lab/logs/semver.source.sha256"
bash "$lab/build-one.sh" semver
