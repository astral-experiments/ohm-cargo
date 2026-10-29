set -euo pipefail
r=$1;p=$2;uid=$(id -u);gid=$(id -g);o=$r/genoa-supplement-v1
test ! -e "$r/genoa-supplement-clock-release.json" && test ! -e "$r/genoa-supplement-scored"
exec 9>"$r/native.lock";flock -n 9
if test ! -f "$r/genoa-supplement-admission.json"; then
 sudo -n unshare --mount --propagation private bash -c 'set -eu; mount -t btrfs -o loop,ro,nosuid,nodev "$1/common-store-v1.btrfs" "$2/volume"; setpriv --reuid="$3" --regid="$4" --clear-groups --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all env HOME="$5" USER=dev-user LOGNAME=dev-user taskset -c 0-7 python3 -IB "$1/genoa-supplement-v1/admit.py"' -- "$r" "$p" "$uid" "$gid" "$HOME"
fi
for d in child-to-parent parent-to-child; do
  for arm in A B A2 B2; do
    sudo -n unshare --mount --propagation private bash "$o/proof-namespace.sh" "$r" "$p" "$uid" "$gid" "$HOME" rehearse "$d-$arm"
  done
done
