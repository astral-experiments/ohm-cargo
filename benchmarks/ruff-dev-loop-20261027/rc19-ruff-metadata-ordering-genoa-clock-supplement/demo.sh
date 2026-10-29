set -euo pipefail
r=$1;p=$2;uid=$3;gid=$4;hm=$5;o=$r/genoa-supplement-v1
mount -t btrfs -o loop,nosuid,nodev,user_subvol_rm_allowed "$r/common-store-v1.btrfs" "$p/volume"
asuser=(setpriv --reuid="$uid" --regid="$gid" --clear-groups --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all env HOME="$hm" USER=dev-user LOGNAME=dev-user taskset -c 0-7 python3 -IB)
"${asuser[@]}" "$o/snapshot_check.py" freeze
python3 -IB "$o/owned_gc.py" "$r" "$p/volume" "$uid" demo
"${asuser[@]}" "$o/snapshot_check.py" after
