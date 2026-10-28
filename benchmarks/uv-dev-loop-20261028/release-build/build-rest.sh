#!/usr/bin/env bash
set -euo pipefail

lab=$(cd "$(dirname "$0")" && pwd -P)
cd "$lab/src"
grep -q 'base complete' "$lab/logs/timeline.log"

for entry in 'unit:unit-deps' 'warnings:manifest-warnings' 'feature:feature-deps-small' 'depfile:depfile-render'; do
    name=${entry%%:*}
    patch_name=${entry#*:}
    file="$lab/patches/$patch_name.patch"
    patch --batch --forward --fuzz=0 --dry-run -p1 < "$file" > "$lab/logs/$name.patch.log"
    patch --batch --forward --fuzz=0 -p1 < "$file" >> "$lab/logs/$name.patch.log"
    sha256sum -c "$lab/source-lock.sha256"
    xargs -d '\n' sha256sum < "$lab/affected-files.txt" > "$lab/logs/$name.source.sha256"
    bash "$lab/build-one.sh" "$name"
done
