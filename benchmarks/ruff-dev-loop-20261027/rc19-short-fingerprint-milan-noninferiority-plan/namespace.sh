#!/bin/bash
# Called only within a fresh private mount namespace. Cargo itself runs as the ordinary user.
set -euo pipefail
[[ $# == 8 && $(id -u) == 0 ]]
base=$1; run=$2; trial=$3; writable=$4; owner=$5; group=$6; arm=$7; action=$8
account=$(getent passwd "$owner" | cut -d: -f6)
oldroot="$account/.cache/ohm-ruff-multi-select-20261029-v1"
p="$oldroot/pending-clock-stable-v2"
source_tree="$account/code/oss/ruff-ohm-pending-physical-20261029-h3"
[[ $arm == B || $arm == E ]]
[[ $action == qualify || $action == measure || $action == holdout || $action == inspect ]]
[[ $owner != 0 && $(stat -c '%u' "$base") == "$owner" && "$account/.cache/ohm-cargo-short-read-milan-20261029-v1" == "$base" ]]
[[ $trial == "$base/restore/active" && $run == "$base/reports/"* && $writable == /dev/shm/ohm-cargo-short-read-milan-20261029-v1/* ]]
mount --make-rprivate /
for spec in "src:$source_tree" "home:$oldroot/cargo-home"; do
    name=${spec%%:*}; dest=${spec#*:}
    mount -t overlay overlay -o "lowerdir=$dest,upperdir=$writable/$name-u,workdir=$writable/$name-w" "$dest"
done
mount --bind "$trial" "$p/state"
mount --bind "$base/images/$arm" "$p/active-image"
for dest in "$p/active-image" "$p/rustup" "$p/sdk" "$oldroot/sdk-18" "$account/code/oss/ruff-ohm-multi-select-seed-20261029-h3/.git"; do
    [[ $dest == "$p/active-image" ]] || mount --bind "$dest" "$dest"
    mount -o remount,bind,ro "$dest"
done
mount --bind "$writable/tmp" /tmp
cd "$base"
exec setpriv --reuid="$owner" --regid="$group" --init-groups --no-new-privs     env -i HOME="$account" USER="$(id -nu "$owner")" LOGNAME="$(id -nu "$owner")" LANG=C.UTF-8 PATH=/usr/local/bin:/usr/bin:/bin     python3 -IB "$base/ops/visit.py" "$run" "$arm" "$action"
