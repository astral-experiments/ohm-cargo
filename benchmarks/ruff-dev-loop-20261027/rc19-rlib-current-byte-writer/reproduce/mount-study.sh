set -eu
study=$1
work=$2
report=$3
kind=$4
uid=$5
gid=$6
as_user() {
  setpriv --reuid="$uid" --regid="$gid" --clear-groups --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all "$@"
}
if [ "$kind" = btrfs ]; then
  mount -t btrfs -o loop,nosuid,nodev "$report/private.btrfs" "$work"
  trap 'umount "$study/inputs"; umount "$work"' EXIT
  chown "$uid:$gid" "$work"
fi
as_user /usr/bin/python3 -IB "$study/native-study.py" prepare "$work"
mount --bind "$report/empty" "$study/inputs"
mount -o remount,bind,ro "$study/inputs"
if [ "$kind" = ext4 ]; then trap 'umount "$study/inputs"' EXIT; fi
as_user /usr/bin/python3 -IB "$study/native-study.py" run "$work" "$report" "$kind"

