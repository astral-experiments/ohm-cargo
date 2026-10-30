#!/bin/bash
set -euo pipefail
umask 077
external=$(dirname "$(dirname "$(readlink -f "$0")")")
test "$(id -u)" = 0
test -n "${ORIGINAL_MOUNT_NS:-}" && test "$(readlink /proc/self/ns/mnt)" != "$ORIGINAL_MOUNT_NS"
test "$(stat -c '%u:%a' "$external")" = 1000:700
test "$(taskset -pc $$ | sed 's/.*: //')" = 0-3
cd /
mount --make-rprivate /
ordinary=(/usr/bin/setpriv --reuid=1000 --regid=1000 --init-groups --no-new-privs)
"${ordinary[@]}" /usr/bin/python3 -IB "$external/site/prepare_image.py"
mkdir -- "$external/receiver" "$external/spool"
for d in "$external/receiver" "$external/spool"; do
    # Underlying empty directory allocations are hidden while the private mounts exist.
    test "$(stat -c '%b' "$d")" -le 16
done
mount -t ext4 -o loop,nodev,nosuid,noexec,nodiscard "$external/receiver.ext4" "$external/receiver"
install -d -o 1000 -g 1000 -m700 "$external/receiver/store"
mount -t tmpfs -o size=384M,nodev,nosuid,mode=0700,uid=1000,gid=1000 cli-external-receipts "$external/spool"
# The ordinary controller starts each root-only mount helper through a narrowly
# verified supervisor. Native work runs as UID 1000 with no capabilities.
# NNP is applied to every actual Cargo and the FD sender; the controller needs
# its existing host sudo for unshare only. It inherits no open receiver file.
exec /usr/bin/setpriv --reuid=1000 --regid=1000 --init-groups /usr/bin/python3 -IB "$external/site/dispatch.py"
