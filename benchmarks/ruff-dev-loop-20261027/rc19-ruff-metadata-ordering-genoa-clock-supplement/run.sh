set -euo pipefail
r=$1;p=$2;o=$r/genoa-supplement-v1;st=$r/genoa-supplement-scored;uid=$(id -u);gid=$(id -g)
test -f "$r/genoa-supplement-clock-release.json" && test -f "$r/genoa-supplement-ready.json" && test ! -e "$st" && test ! -e "$r/admin-pgo-scored"
exec 9>"$r/native.lock";flock -n 9
failure(){ if test -d "$st"; then printf 'pair=%s visit=%s stage=%s exit=%s\n' "$n" "$pos" "$phase" "$1" >"$st/first-stop.txt"; fi; }
trap 's=$?; if ((s!=0));then failure "$s"; fi' EXIT
for n in $(seq 0 31); do
  for pos in 0 1; do
    phase=ordinary;sudo -n unshare --mount --propagation private /bin/bash "$o/ordinary-namespace.sh" "$r" "$p" "$uid" "$gid" "$HOME" "$n" "$pos"
  done
  phase=post-pair
  for pos in 0 1; do
    arm=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[int(sys.argv[2])]["order"][int(sys.argv[3])])' "$r/protocol-v1/genoa.json" "$n" "$pos")
    [[ "$arm" = A || "$arm" = B ]];printf -v name 'pair-%02d-visit-%d-%s' "$n" "$pos" "$arm"
    sudo -n unshare --mount --propagation private /bin/bash "$o/proof-namespace.sh" "$r" "$p" "$uid" "$gid" "$HOME" score "$name"
  done
  phase=close-pair
  sudo -n unshare --mount --propagation private /bin/bash -c 'set -eu; mount -t btrfs -o loop,nosuid,nodev,user_subvol_rm_allowed "$1/common-store-v1.btrfs" "$2/volume"; setpriv --reuid="$3" --regid="$4" --clear-groups --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all env HOME="$5" USER=dev-user LOGNAME=dev-user taskset -c 0-7 python3 -IB "$1/genoa-supplement-v1/pair.py" "$6" validate; python3 -IB "$1/genoa-supplement-v1/owned_gc.py" "$1" "$2/volume" "$3" score "$6"; setpriv --reuid="$3" --regid="$4" --clear-groups --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all env HOME="$5" USER=dev-user LOGNAME=dev-user taskset -c 0-7 python3 -IB "$1/genoa-supplement-v1/pair.py" "$6" seal' -- "$r" "$p" "$uid" "$gid" "$HOME" "$n"
  printf 'validated adjacent pair %d\n' "$n"
done
phase=closed;python3 -IB "$o/finish.py"
